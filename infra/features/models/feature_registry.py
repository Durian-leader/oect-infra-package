"""
特征注册表模型

定义特征注册表的数据结构，用于管理特征元数据和索引
"""
from typing import Optional, Dict, List, Any, Set, Union
from datetime import datetime
from pydantic import BaseModel, validator
from pathlib import Path


class FeatureInfo(BaseModel):
    """
    单个特征的注册信息
    
    记录特征的完整元数据，包括存储位置、版本信息等
    """
    name: str  # 特征名称
    unit: Optional[str] = None  # 特征单位
    description: Optional[str] = None  # 特征描述  
    alias: Optional[str] = None  # 特征别名
    data_type: str = "float32"  # 数据类型
    
    # 存储位置信息
    bucket: Optional[str] = None  # 所属桶名称 (如 bk_00, bk_01)
    hdf5_path: Optional[str] = None  # HDF5内部路径
    
    # 版本信息
    version: Optional[str] = None  # 所属版本 (如 v1, v2)
    version_index: Optional[int] = None  # 在版本矩阵中的列索引
    
    # 状态信息
    is_active: bool = True  # 是否活跃（可用）
    is_versioned: bool = False  # 是否已被纳入版本化矩阵
    
    # 时间信息
    created_at: Optional[datetime] = None  # 创建时间
    updated_at: Optional[datetime] = None  # 更新时间
    
    class Config:
        extra = 'allow'
    
    def get_storage_path(self, data_type: str = "transfer") -> str:
        """
        获取特征在HDF5中的完整存储路径
        
        Args:
            data_type: 数据类型，"transfer" 或 "transient"
            
        Returns:
            HDF5内部路径
        """
        if self.hdf5_path:
            return self.hdf5_path
        
        if self.bucket:
            return f"/{data_type}/columns/buckets/{self.bucket}/{self.name}"
        
        return f"/{data_type}/columns/{self.name}"
    
    def get_index_path(self, data_type: str = "transfer") -> str:
        """
        获取特征索引的HDF5路径
        
        Args:
            data_type: 数据类型，"transfer" 或 "transient"
            
        Returns:
            索引路径
        """
        return f"/{data_type}/columns/_registry/by_name/{self.name}"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'name': self.name,
            'unit': self.unit,
            'description': self.description,
            'alias': self.alias,
            'data_type': self.data_type,
            'bucket': self.bucket,
            'hdf5_path': self.hdf5_path,
            'version': self.version,
            'version_index': self.version_index,
            'is_active': self.is_active,
            'is_versioned': self.is_versioned,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class FeatureRegistry(BaseModel):
    """
    特征注册表
    
    管理所有特征的元数据和索引信息，支持按名称、桶、版本等多种方式查询
    """
    # 注册表基本信息
    data_type: str  # 数据类型：'transfer' 或 'transient'  
    registry_version: str = "1.0"  # 注册表版本
    created_at: Optional[datetime] = None  # 创建时间
    updated_at: Optional[datetime] = None  # 更新时间
    
    # 特征信息
    features: Dict[str, FeatureInfo] = {}  # 按名称索引的特征信息
    
    # 组织信息
    buckets: List[str] = []  # 所有桶名称列表
    versions: List[str] = []  # 所有版本列表
    
    # 统计信息
    total_features: int = 0  # 总特征数
    active_features: int = 0  # 活跃特征数
    versioned_features: int = 0  # 已版本化特征数
    
    class Config:
        extra = 'allow'
    
    @validator('data_type')
    def validate_data_type(cls, v):
        if v not in ['transfer', 'transient']:
            raise ValueError("data_type must be 'transfer' or 'transient'")
        return v
    
    def add_feature(self, feature_info: FeatureInfo) -> None:
        """
        添加新特征到注册表
        
        Args:
            feature_info: 特征信息
        """
        self.features[feature_info.name] = feature_info
        
        # 更新桶列表
        if feature_info.bucket and feature_info.bucket not in self.buckets:
            self.buckets.append(feature_info.bucket)
            self.buckets.sort()
        
        # 更新版本列表
        if feature_info.version and feature_info.version not in self.versions:
            self.versions.append(feature_info.version)
            self.versions.sort()
        
        # 更新统计信息
        self._update_statistics()
        self.updated_at = datetime.now()
    
    def remove_feature(self, feature_name: str) -> bool:
        """
        从注册表中移除特征
        
        Args:
            feature_name: 特征名称
            
        Returns:
            是否成功移除
        """
        if feature_name in self.features:
            del self.features[feature_name]
            self._update_statistics()
            self.updated_at = datetime.now()
            return True
        return False
    
    def get_feature(self, feature_name: str) -> Optional[FeatureInfo]:
        """
        获取特征信息
        
        Args:
            feature_name: 特征名称或别名
            
        Returns:
            特征信息，如果不存在返回None
        """
        # 首先按名称查找
        if feature_name in self.features:
            return self.features[feature_name]
        
        # 然后按别名查找
        for feature_info in self.features.values():
            if feature_info.alias == feature_name:
                return feature_info
        
        return None
    
    def get_features_by_bucket(self, bucket_name: str) -> List[FeatureInfo]:
        """
        获取指定桶中的所有特征
        
        Args:
            bucket_name: 桶名称
            
        Returns:
            特征信息列表
        """
        return [
            feature for feature in self.features.values()
            if feature.bucket == bucket_name and feature.is_active
        ]
    
    def get_features_by_version(self, version: str) -> List[FeatureInfo]:
        """
        获取指定版本的所有特征
        
        Args:
            version: 版本号
            
        Returns:
            特征信息列表，按version_index排序
        """
        features = [
            feature for feature in self.features.values()
            if feature.version == version and feature.is_active
        ]
        
        # 按版本索引排序
        features.sort(key=lambda x: x.version_index or 0)
        return features
    
    def get_active_features(self) -> List[FeatureInfo]:
        """
        获取所有活跃特征
        
        Returns:
            活跃特征列表
        """
        return [
            feature for feature in self.features.values()
            if feature.is_active
        ]
    
    def get_unversioned_features(self) -> List[FeatureInfo]:
        """
        获取所有未版本化的特征
        
        Returns:
            未版本化特征列表
        """
        return [
            feature for feature in self.features.values()
            if feature.is_active and not feature.is_versioned
        ]
    
    def search_features(self, 
                       keyword: str,
                       search_in: List[str] = None) -> List[FeatureInfo]:
        """
        搜索特征
        
        Args:
            keyword: 搜索关键词
            search_in: 搜索字段列表，默认为['name', 'description', 'alias']
            
        Returns:
            匹配的特征列表
        """
        if search_in is None:
            search_in = ['name', 'description', 'alias']
        
        keyword_lower = keyword.lower()
        matches = []
        
        for feature in self.features.values():
            if not feature.is_active:
                continue
                
            for field in search_in:
                value = getattr(feature, field, None)
                if value and keyword_lower in str(value).lower():
                    matches.append(feature)
                    break
        
        return matches
    
    def get_available_buckets(self) -> List[str]:
        """获取所有可用桶名称"""
        return self.buckets.copy()
    
    def get_available_versions(self) -> List[str]:
        """获取所有可用版本"""
        return self.versions.copy()
    
    def _update_statistics(self) -> None:
        """更新统计信息"""
        self.total_features = len(self.features)
        self.active_features = sum(1 for f in self.features.values() if f.is_active)
        self.versioned_features = sum(1 for f in self.features.values() if f.is_versioned and f.is_active)
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取注册表统计信息
        
        Returns:
            统计信息字典
        """
        self._update_statistics()
        
        bucket_stats = {}
        for bucket in self.buckets:
            bucket_features = self.get_features_by_bucket(bucket)
            bucket_stats[bucket] = len(bucket_features)
        
        version_stats = {}
        for version in self.versions:
            version_features = self.get_features_by_version(version)
            version_stats[version] = len(version_features)
        
        return {
            'basic_stats': {
                'data_type': self.data_type,
                'total_features': self.total_features,
                'active_features': self.active_features,
                'versioned_features': self.versioned_features,
                'unversioned_features': self.active_features - self.versioned_features
            },
            'bucket_stats': bucket_stats,
            'version_stats': version_stats,
            'registry_info': {
                'registry_version': self.registry_version,
                'created_at': self.created_at.isoformat() if self.created_at else None,
                'updated_at': self.updated_at.isoformat() if self.updated_at else None
            }
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'data_type': self.data_type,
            'registry_version': self.registry_version,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'features': {name: feature.to_dict() for name, feature in self.features.items()},
            'buckets': self.buckets,
            'versions': self.versions,
            'statistics': self.get_statistics()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FeatureRegistry":
        """
        从字典创建FeatureRegistry实例
        
        Args:
            data: 字典数据
            
        Returns:
            FeatureRegistry实例
        """
        # 解析特征信息
        features = {}
        if 'features' in data:
            for name, feature_data in data['features'].items():
                # 处理时间字段
                if feature_data.get('created_at'):
                    feature_data['created_at'] = datetime.fromisoformat(feature_data['created_at'])
                if feature_data.get('updated_at'):
                    feature_data['updated_at'] = datetime.fromisoformat(feature_data['updated_at'])
                
                features[name] = FeatureInfo(**feature_data)
        
        # 处理时间字段
        created_at = None
        if data.get('created_at'):
            created_at = datetime.fromisoformat(data['created_at'])
        
        updated_at = None
        if data.get('updated_at'):
            updated_at = datetime.fromisoformat(data['updated_at'])
        
        registry = cls(
            data_type=data['data_type'],
            registry_version=data.get('registry_version', '1.0'),
            created_at=created_at,
            updated_at=updated_at,
            features=features,
            buckets=data.get('buckets', []),
            versions=data.get('versions', [])
        )
        
        # 更新统计信息
        registry._update_statistics()
        
        return registry