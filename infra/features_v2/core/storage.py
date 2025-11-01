"""
存储层 - Arrow/Parquet 支持

提供高效的特征数据持久化
"""

from typing import Dict, Any
import numpy as np
import pandas as pd
from pathlib import Path

from infra.logger_config import get_module_logger

logger = get_module_logger()


def save_features(
    features: Dict[str, np.ndarray],
    output_path: str,
    metadata: Dict[str, Any] = None,
    compression: str = 'zstd',
):
    """保存特征到 Parquet 文件

    Args:
        features: 特征字典 {name: ndarray}
        output_path: 输出路径
        metadata: 元数据（如 chip_id, device_id）
        compression: 压缩算法（zstd, gzip, snappy）
    """
    output_path = Path(output_path)

    # 转换为 DataFrame
    data_dict = {}
    n_steps = None

    for name, array in features.items():
        if n_steps is None:
            n_steps = array.shape[0]
        elif array.shape[0] != n_steps:
            raise ValueError(f"特征 '{name}' 的步数不一致")

        if array.ndim == 1:
            # 标量特征
            data_dict[name] = array
        elif array.ndim == 2:
            # 多维特征：展开为多列
            for i in range(array.shape[1]):
                data_dict[f'{name}_dim{i}'] = array[:, i]
        else:
            logger.warning(
                f"特征 '{name}' 的维度为 {array.ndim}，暂不支持保存"
            )

    df = pd.DataFrame(data_dict)
    df.insert(0, 'step_index', np.arange(n_steps))

    # 添加元数据
    if metadata:
        for key, value in metadata.items():
            df.attrs[key] = value

    # 保存
    df.to_parquet(output_path, compression=compression, index=False)
    logger.info(f"已保存 {len(data_dict)} 个特征到 {output_path}")


def load_features(
    parquet_path: str,
    feature_names: list = None,
    restore_multidim: bool = False,
) -> Dict[str, np.ndarray]:
    """从 Parquet 文件加载特征

    Args:
        parquet_path: Parquet 文件路径
        feature_names: 要加载的特征名列表（None=全部）
        restore_multidim: 是否还原多维特征（如 name_dim0, name_dim1 → name）

    Returns:
        特征字典
    """
    parquet_path = Path(parquet_path)
    df = pd.read_parquet(parquet_path)

    # 移除 step_index 列
    if 'step_index' in df.columns:
        df = df.drop(columns=['step_index'])

    features = {}

    if not restore_multidim:
        # 简单模式：直接转换
        for col in df.columns:
            if feature_names is None or col in feature_names:
                features[col] = df[col].to_numpy()
    else:
        # 还原多维特征
        processed_cols = set()

        for col in df.columns:
            if col in processed_cols:
                continue

            # 检查是否为多维特征的一部分
            if '_dim' in col:
                base_name = col.rsplit('_dim', 1)[0]

                # 查找所有相关列
                related_cols = [
                    c for c in df.columns
                    if c.startswith(f'{base_name}_dim')
                ]

                if len(related_cols) > 1:
                    # 堆叠为多维数组
                    arrays = [df[c].to_numpy() for c in sorted(related_cols)]
                    features[base_name] = np.column_stack(arrays)

                    processed_cols.update(related_cols)
                    continue

            # 标量特征
            if feature_names is None or col in feature_names:
                features[col] = df[col].to_numpy()
                processed_cols.add(col)

    logger.info(f"从 {parquet_path} 加载了 {len(features)} 个特征")
    return features


def save_features_arrow(features: Dict[str, np.ndarray], output_path: str):
    """保存为 Arrow IPC 格式（预留，Phase 2 实现）

    Arrow IPC 比 Parquet 更快，但文件更大
    """
    try:
        import pyarrow as pa
        import pyarrow.feather as feather
    except ImportError:
        raise ImportError("需要安装 pyarrow: pip install pyarrow")

    # TODO: 实现 Arrow 原生格式存储（支持嵌套类型）
    raise NotImplementedError("Arrow 存储将在 Phase 2 实现")


def load_features_arrow(arrow_path: str) -> Dict[str, np.ndarray]:
    """从 Arrow IPC 格式加载（预留）"""
    raise NotImplementedError("Arrow 加载将在 Phase 2 实现")
