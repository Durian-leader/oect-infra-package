"""
Features Package - OECT特征数据存储和管理

features包是与experiment包完全独立的同级包，专门负责特征文件的存储、版本管理和读取。

主要功能：
- 特征文件的创建和初始化
- 列式特征存储和版本化管理
- 高效的特征数据读取和批量文件管理
- 支持上千特征的扩展性存储

主要组件：
- FeatureFileCreator: 特征文件创建器
- FeatureRepository: 特征数据仓库
- VersionManager: 版本管理器
- FeatureReader: 特征数据读取器
- BatchManager: 批量文件管理器
"""

from .core.file_creator import FeatureFileCreator
from .core.repository import FeatureRepository  
from .core.version_manager import VersionManager
from .readers.feature_reader import FeatureReader
from .readers.batch_manager import BatchManager
from .models.feature_data import FeatureData, FeatureMetadata, VersionedFeatures
from .models.feature_registry import FeatureRegistry, FeatureInfo

__version__ = "1.0.0"
__author__ = "OECT Data Processing Team"

__all__ = [
    "FeatureFileCreator",
    "FeatureRepository", 
    "VersionManager",
    "FeatureReader",
    "BatchManager",
    "FeatureData",
    "FeatureMetadata",
    "VersionedFeatures",
    "FeatureRegistry",
    "FeatureInfo",
]