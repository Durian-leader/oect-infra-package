"""
并行执行引擎

使用多进程并行执行计算图中的独立节点
"""

from typing import Dict, List, Any
from concurrent.futures import ProcessPoolExecutor, as_completed
import time
import numpy as np

from infra.features_v2.core.executor import Executor, ExecutionContext
from infra.features_v2.core.compute_graph import ComputeGraph, ComputeNode
from infra.logger_config import get_module_logger

logger = get_module_logger()


class ParallelExecutor(Executor):
    """并行执行引擎

    在保持正确依赖顺序的前提下，并行执行独立的特征计算节点
    """

    def __init__(self, *args, n_workers: int = 4, **kwargs):
        """
        Args:
            n_workers: 工作进程数（默认 4）
            其他参数同 Executor
        """
        super().__init__(*args, **kwargs)
        self.n_workers = n_workers

    def execute(self) -> ExecutionContext:
        """并行执行计算图

        策略：
        1. 使用 group_parallel_nodes() 将节点分层
        2. 同一层内的节点可并行执行
        3. 跨层串行执行
        """
        context = ExecutionContext()

        # 获取并行分组
        parallel_groups = self.graph.group_parallel_nodes()

        logger.info(
            f"开始并行执行计算图：{len(parallel_groups)} 层，"
            f"{len(self.graph.nodes)} 个节点，{self.n_workers} 个工作进程"
        )

        # 逐层执行
        for layer_idx, group in enumerate(parallel_groups):
            logger.debug(f"执行第 {layer_idx} 层：{len(group)} 个节点")

            if len(group) == 1:
                # 单节点：串行执行
                self._execute_node(group[0], context)
            else:
                # 多节点：并行执行
                self._execute_group_parallel(group, context)

        # 输出统计信息
        stats = context.get_statistics()
        logger.info(
            f"并行执行完成：{stats['total_features']} 个特征，"
            f"总耗时 {stats['total_time_ms']:.2f}ms"
        )

        return context

    def _execute_group_parallel(
        self, group: List[str], context: ExecutionContext
    ):
        """并行执行一组节点

        Args:
            group: 节点名称列表
            context: 执行上下文
        """
        # 过滤已计算的节点
        pending_nodes = [name for name in group if not context.has(name)]

        if not pending_nodes:
            return

        logger.debug(f"并行执行 {len(pending_nodes)} 个节点")

        # 使用 ProcessPoolExecutor 并行执行
        with ProcessPoolExecutor(max_workers=min(self.n_workers, len(pending_nodes))) as pool:
            # 提交任务
            futures = {}
            for node_name in pending_nodes:
                # 检查是否为数据源
                if node_name not in self.graph:
                    # 数据源：串行加载（避免重复加载）
                    self._execute_node(node_name, context)
                    continue

                node = self.graph.nodes[node_name]

                # 解析输入
                inputs = self._resolve_inputs(node, context)

                # 提交任务
                future = pool.submit(
                    _compute_node_wrapper,
                    node,
                    inputs,
                    self.extractor_registry,
                )
                futures[future] = node_name

            # 收集结果
            for future in as_completed(futures):
                node_name = futures[future]
                try:
                    result, elapsed = future.result()
                    context.set(node_name, result, elapsed)
                    logger.debug(
                        f"节点 '{node_name}' 计算完成：{elapsed:.2f}ms，"
                        f"形状 {result.shape}"
                    )
                except Exception as e:
                    logger.error(f"节点 '{node_name}' 执行失败: {e}")
                    raise


def _compute_node_wrapper(
    node: ComputeNode,
    inputs: Dict[str, Any],
    extractor_registry: Dict[str, Any],
) -> tuple:
    """节点计算包装器（用于多进程）

    Args:
        node: 计算节点
        inputs: 输入数据
        extractor_registry: 提取器注册表

    Returns:
        (result, elapsed_ms) 元组
    """
    start = time.perf_counter()

    if node.is_extractor:
        # 使用注册的提取器
        extractor_name = node.func
        if extractor_name not in extractor_registry:
            raise ValueError(f"未找到提取器 '{extractor_name}'")

        extractor = extractor_registry[extractor_name]
        result = extractor.extract(inputs, node.params)

    elif callable(node.func):
        # 直接调用函数
        if len(inputs) == 1:
            result = node.func(list(inputs.values())[0], **node.params)
        else:
            result = node.func(inputs, **node.params)
    else:
        raise TypeError(f"节点 '{node.name}' 的 func 类型无效")

    # 验证输出
    if not isinstance(result, np.ndarray):
        raise TypeError(
            f"节点 '{node.name}' 的输出必须是 numpy 数组，"
            f"实际类型：{type(result)}"
        )

    elapsed = (time.perf_counter() - start) * 1000  # ms

    return result, elapsed
