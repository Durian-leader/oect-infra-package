"""
features_version 模块

提供特征文件生成和版本化管理的实用封装。

功能：
- v1_feature: Transfer 特征提取（gm, Von, |I|）
- v2_feature: Transient 特征提取（tau_on, tau_off）使用 autotau 并行处理
- 批量处理和版本矩阵创建
"""

from .v1_feature import v1_feature
from .v2_feature import v2_feature, estimate_period_from_signal
from .batch_create_feature import batch_create_features
from .create_version_utils import (
    create_version_from_all_features,
    verify_feature_file_structure
)

__all__ = [
    # V1 - Transfer features
    'v1_feature',

    # V2 - Transient features (tau_on/tau_off)
    'v2_feature',
    'estimate_period_from_signal',

    # Batch processing
    'batch_create_features',

    # Version management utilities
    'create_version_from_all_features',
    'verify_feature_file_structure',
]
