"""
features_v2 - 现代化特征工程系统

设计理念：计算图 + 惰性求值 + 列式存储
- 类似 Polars/Dask 的声明式 API
- HuggingFace datasets 的易用性
- 原生支持多维特征
- <100ms 性能目标

核心组件：
- FeatureSet: 用户主接口
- ComputeGraph: 计算图构建与优化
- Executor: 执行引擎（并行、缓存）
- BaseExtractor: 特征提取器基类

示例用法：
    from infra.features_v2 import FeatureSet

    features = FeatureSet(experiment=exp)
    features.add('gm_max', extractor='transfer.gm_max')
    features.add('cycles', extractor='transient.cycles', params={'n': 100})

    result = features.compute()  # <100ms
    features.to_parquet('output.parquet')
"""

from infra.features_v2.core.feature_set import FeatureSet
from infra.features_v2.extractors.base import BaseExtractor, register

__version__ = '2.1.0'
__all__ = ['FeatureSet', 'BaseExtractor', 'register']
