"""
Features Core Module - 核心特征存储功能

包含特征文件的核心管理功能：
- FeatureFileCreator: 特征文件创建和初始化
- FeatureRepository: 特征数据的存储和管理仓库
- VersionManager: 特征版本的管理和固化
"""

from .file_creator import FeatureFileCreator
from .repository import FeatureRepository
from .version_manager import VersionManager

__all__ = [
    "FeatureFileCreator",
    "FeatureRepository", 
    "VersionManager",
]