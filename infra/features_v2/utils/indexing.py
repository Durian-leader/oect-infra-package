"""
高效索引工具

针对 Transient 拼接存储优化的索引结构
"""

from typing import List, Optional, Tuple
import numpy as np
import pandas as pd

from infra.logger_config import get_module_logger

logger = get_module_logger()


class TransientIndexer:
    """Transient 数据高效索引器

    针对拼接存储的 transient 数据提供高效的批量切片和提取
    """

    def __init__(self, step_info_table: pd.DataFrame):
        """
        Args:
            step_info_table: 步骤信息表，必须包含 'start_data_index' 和 'end_data_index'
        """
        if 'start_data_index' not in step_info_table.columns:
            raise ValueError("step_info_table 必须包含 'start_data_index' 列")
        if 'end_data_index' not in step_info_table.columns:
            raise ValueError("step_info_table 必须包含 'end_data_index' 列")

        self.step_info = step_info_table
        self.n_steps = len(step_info_table)

        # 预计算索引范围
        self.ranges = [
            (int(row['start_data_index']), int(row['end_data_index']))
            for _, row in step_info_table.iterrows()
        ]

        # 计算统计信息
        self.lengths = [end - start for start, end in self.ranges]
        self.max_length = max(self.lengths)
        self.min_length = min(self.lengths)
        self.avg_length = sum(self.lengths) / len(self.lengths)

        logger.debug(
            f"TransientIndexer 初始化：{self.n_steps} 步，"
            f"长度范围 [{self.min_length}, {self.max_length}]，"
            f"平均长度 {self.avg_length:.1f}"
        )

    def get_step_slice(
        self, measurement_data: np.ndarray, step_index: int
    ) -> np.ndarray:
        """获取单个 step 的数据切片

        Args:
            measurement_data: (3, total_points) 拼接数组
            step_index: 步骤索引

        Returns:
            (3, step_length) 数组
        """
        start, end = self.ranges[step_index]
        return measurement_data[:, start:end]

    def batch_slice(
        self, measurement_data: np.ndarray, step_indices: Optional[List[int]] = None
    ) -> np.ndarray:
        """批量提取多个 step 的数据

        Args:
            measurement_data: (3, total_points) 拼接数组
            step_indices: 要提取的 step 索引列表（None=全部）

        Returns:
            (n_selected_steps, 3, max_points) 数组，不足部分填充 NaN
        """
        if step_indices is None:
            step_indices = list(range(self.n_steps))

        # 计算最大长度
        selected_ranges = [self.ranges[i] for i in step_indices]
        max_len = max(end - start for start, end in selected_ranges)

        # 预分配结果数组
        result = np.full((len(step_indices), 3, max_len), np.nan, dtype=np.float32)

        # 批量填充
        for i, (start, end) in enumerate(selected_ranges):
            length = end - start
            result[i, :, :length] = measurement_data[:, start:end]

        return result

    def parallel_extract(
        self,
        measurement_data: np.ndarray,
        extractor_func: callable,
        n_workers: int = 4,
    ) -> np.ndarray:
        """并行提取特征

        Args:
            measurement_data: (3, total_points) 拼接数组
            extractor_func: 提取函数，接收 (3, length) 数组，返回特征值或数组
            n_workers: 工作进程数

        Returns:
            特征数组 (n_steps,) 或 (n_steps, k)
        """
        from concurrent.futures import ProcessPoolExecutor
        import multiprocessing as mp

        # 分块（每个进程处理连续的 step 范围）
        chunk_size = max(1, self.n_steps // n_workers)
        chunks = [
            range(i * chunk_size, min((i + 1) * chunk_size, self.n_steps))
            for i in range(n_workers)
        ]

        # 过滤空块
        chunks = [c for c in chunks if len(c) > 0]

        logger.debug(f"并行提取：{len(chunks)} 个块，每块约 {chunk_size} 步")

        # 并行执行
        with ProcessPoolExecutor(max_workers=len(chunks)) as pool:
            futures = [
                pool.submit(
                    _extract_chunk,
                    measurement_data,
                    list(chunk),
                    self.ranges,
                    extractor_func,
                )
                for chunk in chunks
            ]
            results = [f.result() for f in futures]

        # 合并结果
        if isinstance(results[0], np.ndarray) and results[0].ndim > 1:
            # 多维结果
            return np.vstack(results)
        else:
            # 一维结果
            return np.concatenate([np.atleast_1d(r) for r in results])

    def get_statistics(self) -> dict:
        """获取统计信息"""
        return {
            'n_steps': self.n_steps,
            'max_length': self.max_length,
            'min_length': self.min_length,
            'avg_length': self.avg_length,
            'total_points': sum(self.lengths),
        }


def _extract_chunk(
    measurement_data: np.ndarray,
    step_indices: List[int],
    ranges: List[Tuple[int, int]],
    extractor_func: callable,
):
    """子进程执行的函数（用于并行提取）

    Args:
        measurement_data: (3, total_points) 拼接数组
        step_indices: 要处理的 step 索引列表
        ranges: 所有 step 的索引范围
        extractor_func: 提取函数

    Returns:
        特征数组（对应 step_indices 的结果）
    """
    results = []
    for idx in step_indices:
        start, end = ranges[idx]
        step_data = measurement_data[:, start:end]
        feature = extractor_func(step_data)
        results.append(feature)

    # 转换为数组
    if isinstance(results[0], (int, float, np.number)):
        # 标量结果
        return np.array(results)
    elif isinstance(results[0], np.ndarray):
        # 数组结果
        return np.array(results)
    else:
        return np.array(results)
