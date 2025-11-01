"""
过滤转换

提供基于条件的数据过滤
"""

import numpy as np
from typing import Callable, Optional


class Filter:
    """过滤转换器

    支持基于条件的数据过滤和异常值处理
    """

    def __init__(
        self,
        condition: Optional[Callable[[np.ndarray], np.ndarray]] = None,
        remove_outliers: bool = False,
        outlier_method: str = 'iqr',
        outlier_threshold: float = 1.5,
    ):
        """
        Args:
            condition: 过滤条件函数（接收数组，返回布尔数组）
            remove_outliers: 是否移除异常值
            outlier_method: 异常值检测方法（'iqr', 'zscore'）
            outlier_threshold: 异常值阈值
        """
        self.condition = condition
        self.remove_outliers = remove_outliers
        self.outlier_method = outlier_method
        self.outlier_threshold = outlier_threshold

    def transform(self, data: np.ndarray) -> np.ndarray:
        """应用过滤

        Args:
            data: 输入数组

        Returns:
            过滤后的数组（异常值替换为 NaN）
        """
        result = data.copy()

        # 应用条件过滤
        if self.condition is not None:
            mask = self.condition(data)
            result[~mask] = np.nan

        # 移除异常值
        if self.remove_outliers:
            outlier_mask = self._detect_outliers(data)
            result[outlier_mask] = np.nan

        return result

    def _detect_outliers(self, data: np.ndarray) -> np.ndarray:
        """检测异常值

        Returns:
            布尔数组（True=异常值）
        """
        if self.outlier_method == 'iqr':
            return self._detect_outliers_iqr(data)
        elif self.outlier_method == 'zscore':
            return self._detect_outliers_zscore(data)
        else:
            raise ValueError(f"未知的异常值检测方法: {self.outlier_method}")

    def _detect_outliers_iqr(self, data: np.ndarray) -> np.ndarray:
        """IQR 方法检测异常值"""
        q75 = np.nanpercentile(data, 75, axis=0, keepdims=True)
        q25 = np.nanpercentile(data, 25, axis=0, keepdims=True)
        iqr = q75 - q25

        lower_bound = q25 - self.outlier_threshold * iqr
        upper_bound = q75 + self.outlier_threshold * iqr

        return (data < lower_bound) | (data > upper_bound)

    def _detect_outliers_zscore(self, data: np.ndarray) -> np.ndarray:
        """Z-score 方法检测异常值"""
        mean = np.nanmean(data, axis=0, keepdims=True)
        std = np.nanstd(data, axis=0, keepdims=True)

        z_scores = np.abs((data - mean) / std)

        return z_scores > self.outlier_threshold

    def __call__(self, data: np.ndarray) -> np.ndarray:
        """便捷调用"""
        return self.transform(data)
