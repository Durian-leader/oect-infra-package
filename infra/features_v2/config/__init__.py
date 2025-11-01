"""配置系统模块

支持从 YAML/JSON 文件加载特征提取配置
"""

from infra.features_v2.config.schema import (
    FeatureConfig,
    FeatureSpec,
    DataSourceConfig,
    PostProcessStep,
    VersioningConfig,
)
from infra.features_v2.config.parser import ConfigParser

__all__ = [
    'FeatureConfig',
    'FeatureSpec',
    'DataSourceConfig',
    'PostProcessStep',
    'VersioningConfig',
    'ConfigParser',
]
