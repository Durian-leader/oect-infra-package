"""
归一化转换

提供多种归一化方法
"""

import numpy as np
from typing import Literal


class Normalize:
    """归一化转换器

    支持的方法：
    - 'minmax': 最小-最大归一化到 [0, 1]
    - 'zscore': Z-score 标准化（均值0，标准差1）
    - 'robust': 鲁棒归一化（使用中位数和四分位距）
    - 'l2': L2 归一化
    """

    def __init__(
        self,
        method: Literal['minmax', 'zscore', 'robust', 'l2'] = 'minmax',
        feature_range: tuple = (0, 1),
    ):
        """
        Args:
            method: 归一化方法
            feature_range: 目标范围（仅用于 minmax）
        """
        self.method = method
        self.feature_range = feature_range

    def transform(self, data: np.ndarray) -> np.ndarray:
        """应用归一化

        Args:
            data: 输入数组 (n_steps,) 或 (n_steps, k)

        Returns:
            归一化后的数组
        """
        if self.method == 'minmax':
            return self._minmax(data)
        elif self.method == 'zscore':
            return self._zscore(data)
        elif self.method == 'robust':
            return self._robust(data)
        elif self.method == 'l2':
            return self._l2(data)
        else:
            raise ValueError(f"未知的归一化方法: {self.method}")

    def _minmax(self, data: np.ndarray) -> np.ndarray:
        """最小-最大归一化"""
        data_min = np.nanmin(data, axis=0, keepdims=True)
        data_max = np.nanmax(data, axis=0, keepdims=True)

        # 避免除以零
        range_val = data_max - data_min
        range_val[range_val == 0] = 1

        # 归一化到 [0, 1]
        normalized = (data - data_min) / range_val

        # 缩放到目标范围
        min_val, max_val = self.feature_range
        return normalized * (max_val - min_val) + min_val

    def _zscore(self, data: np.ndarray) -> np.ndarray:
        """Z-score 标准化"""
        mean = np.nanmean(data, axis=0, keepdims=True)
        std = np.nanstd(data, axis=0, keepdims=True)

        # 避免除以零
        std[std == 0] = 1

        return (data - mean) / std

    def _robust(self, data: np.ndarray) -> np.ndarray:
        """鲁棒归一化（使用中位数和 IQR）"""
        median = np.nanmedian(data, axis=0, keepdims=True)
        q75 = np.nanpercentile(data, 75, axis=0, keepdims=True)
        q25 = np.nanpercentile(data, 25, axis=0, keepdims=True)

        iqr = q75 - q25
        iqr[iqr == 0] = 1

        return (data - median) / iqr

    def _l2(self, data: np.ndarray) -> np.ndarray:
        """L2 归一化"""
        if data.ndim == 1:
            norm = np.linalg.norm(data)
            return data / norm if norm > 0 else data
        else:
            # 按行归一化
            norms = np.linalg.norm(data, axis=1, keepdims=True)
            norms[norms == 0] = 1
            return data / norms

    def __call__(self, data: np.ndarray) -> np.ndarray:
        """便捷调用"""
        return self.transform(data)
