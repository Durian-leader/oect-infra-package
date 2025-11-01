"""特征提取器模块

提供基类和注册机制，支持用户自定义提取器
"""

from infra.features_v2.extractors.base import BaseExtractor, register, get_extractor, EXTRACTOR_REGISTRY

__all__ = ['BaseExtractor', 'register', 'get_extractor', 'EXTRACTOR_REGISTRY']
