"""
特征数据模型

定义特征文件的基本数据结构和元数据
"""
from typing import Optional, Dict, List, Any, Union
from datetime import datetime
from pydantic import BaseModel, validator
import numpy as np

########################### 日志设置 ################################
from ...logger_config import get_module_logger
logger = get_module_logger()
#####################################################################


class FeatureMetadata(BaseModel):
    """
    单个特征的元数据信息
    
    包含特征的名称、单位、描述、别名等信息
    """
    name: str  # 特征名称
    unit: Optional[str] = None  # 特征单位
    description: Optional[str] = None  # 特征描述
    alias: Optional[str] = None  # 特征别名
    data_type: str = "float32"  # 数据类型
    bucket: Optional[str] = None  # 所属桶名称
    version: Optional[str] = None  # 所属版本
    created_at: Optional[datetime] = None  # 创建时间
    
    class Config:
        extra = 'allow'
        
    def to_registry_entry(self) -> dict:
        """转换为注册表条目格式"""
        return {
            'name': self.name,
            'unit': self.unit,
            'description': self.description,
            'alias': self.alias,
            'data_type': self.data_type,
            'bucket': self.bucket,
            'version': self.version,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class VersionedFeatures(BaseModel):
    """
    版本化特征矩阵数据
    
    包含特征矩阵及其对应的元数据
    """
    version: str  # 版本号 (v1, v2, ...)
    matrix_shape: tuple  # 矩阵形状 (n_steps, n_features)
    feature_names: List[str]  # 特征名称列表
    feature_units: Optional[List[str]] = None  # 特征单位列表
    feature_descriptions: Optional[List[str]] = None  # 特征描述列表
    feature_aliases: Optional[List[str]] = None  # 特征别名列表
    created_at: Optional[datetime] = None  # 版本创建时间
    is_frozen: bool = True  # 是否已固化，默认为True
    
    @validator('matrix_shape')
    def validate_shape(cls, v):
        if not isinstance(v, tuple) or len(v) != 2:
            raise ValueError("Matrix shape must be a tuple of length 2")
        return v
    
    @validator('feature_names')
    def validate_names_length(cls, v, values):
        if 'matrix_shape' in values and values['matrix_shape']:
            expected_features = values['matrix_shape'][1]
            if len(v) != expected_features:
                raise ValueError(f"Feature names length ({len(v)}) must match matrix width ({expected_features})")
        return v
    
    class Config:
        extra = 'allow'
    
    @property
    def n_steps(self) -> int:
        """获取步骤数"""
        return self.matrix_shape[0]
    
    @property
    def n_features(self) -> int:
        """获取特征数"""
        return self.matrix_shape[1]
    
    def get_feature_metadata_list(self) -> List[FeatureMetadata]:
        """获取所有特征的元数据列表"""
        metadata_list = []
        for i, name in enumerate(self.feature_names):
            metadata = FeatureMetadata(
                name=name,
                unit=self.feature_units[i] if self.feature_units and i < len(self.feature_units) else None,
                description=self.feature_descriptions[i] if self.feature_descriptions and i < len(self.feature_descriptions) else None,
                alias=self.feature_aliases[i] if self.feature_aliases and i < len(self.feature_aliases) else None,
                version=self.version,
                created_at=self.created_at
            )
            metadata_list.append(metadata)
        return metadata_list


class FeatureData(BaseModel):
    """
    特征文件的根级别数据模型
    
    包含从文件名解析的元数据信息和特征文件的属性
    """
    
    # 从文件名解析的基本信息
    chip_id: str  # 芯片ID (如 #20250804007)
    device_id: str  # 设备编号 (如 1, 2, 3...)
    description: str  # 测试描述 (如 稳定性测试)
    test_id: str  # 测试标识符 (如 feat_20250815134210_290e653d)
    
    # 特征文件属性
    built_with: Optional[str] = None  # 特征提取工具版本
    feature_tool_hash: Optional[str] = None  # 特征提取代码版本hash
    created_at: Optional[datetime] = None  # 特征文件创建时间
    
    # 数据组织信息
    has_transfer_features: bool = False  # 是否包含Transfer特征
    has_transient_features: bool = False  # 是否包含Transient特征
    
    # 版本信息
    transfer_versions: Optional[List[str]] = None  # Transfer特征可用版本
    transient_versions: Optional[List[str]] = None  # Transient特征可用版本
    
    # 统计信息
    total_transfer_features: Optional[int] = None  # Transfer特征总数
    total_transient_features: Optional[int] = None  # Transient特征总数
    
    class Config:
        extra = 'allow'
    
    @classmethod
    def parse_from_filename(cls, filename: str, **kwargs) -> "FeatureData":
        """
        从特征文件名解析基本信息
        
        Args:
            filename: 特征文件名，格式: {chip_id}-{device_id}-{description}-feat_{timestamp}_{hash}.h5
            **kwargs: 其他属性
            
        Returns:
            FeatureData实例
            
        Examples:
            >>> feature_data = FeatureData.parse_from_filename(
            ...     "#20250804007-1-稳定性测试-feat_20250815134210_290e653d.h5"
            ... )
            >>> print(feature_data.chip_id)  # "#20250804007"
            >>> print(feature_data.device_id)  # "1"
        """
        import re
        from pathlib import Path
        
        # 去掉路径和扩展名，只保留文件名
        basename = Path(filename).stem
        
        # 匹配文件名模式: {chip_id}-{device_id}-{description}-feat_{timestamp}_{hash}
        pattern = r'^(.+)-(\d+)-(.+)-feat_([a-f0-9]+_[a-f0-9]+)$'
        match = re.match(pattern, basename)
        
        if not match:
            raise ValueError(f"Invalid feature filename format: {filename}")
        
        chip_id, device_id, description, test_suffix = match.groups()
        test_id = f"feat_{test_suffix}"
        
        return cls(
            chip_id=chip_id,
            device_id=device_id, 
            description=description,
            test_id=test_id,
            **kwargs
        )
    
    def get_original_test_id(self) -> str:
        """
        获取对应的原始数据文件的test_id
        
        Returns:
            原始文件的test_id (feat_ -> test_)
        """
        if self.test_id.startswith('feat_'):
            return self.test_id.replace('feat_', 'test_', 1)
        return self.test_id
    
    def get_corresponding_raw_filename(self) -> str:
        """
        获取对应的原始数据文件名
        
        Returns:
            原始数据文件名
        """
        original_test_id = self.get_original_test_id()
        return f"{self.chip_id}-{self.device_id}-{self.description}-{original_test_id}.h5"
    
    def get_summary(self) -> Dict[str, Any]:
        """
        获取特征文件摘要信息
        
        Returns:
            包含基本信息、特征统计等的摘要字典
        """
        return {
            'basic_info': {
                'chip_id': self.chip_id,
                'device_id': self.device_id,
                'description': self.description,
                'test_id': self.test_id,
                'corresponding_raw_file': self.get_corresponding_raw_filename()
            },
            'build_info': {
                'built_with': self.built_with,
                'feature_tool_hash': self.feature_tool_hash,
                'created_at': self.created_at.isoformat() if self.created_at else None
            },
            'data_info': {
                'has_transfer_features': self.has_transfer_features,
                'has_transient_features': self.has_transient_features,
                'total_transfer_features': self.total_transfer_features,
                'total_transient_features': self.total_transient_features
            },
            'versions': {
                'transfer_versions': self.transfer_versions or [],
                'transient_versions': self.transient_versions or []
            }
        }
    
    def get_basic_info(self) -> Dict[str, str]:
        """获取基本标识信息"""
        return {
            'chip_id': self.chip_id,
            'device_id': self.device_id,
            'description': self.description,
            'test_id': self.test_id
        }
    
    def get_build_info(self) -> Dict[str, Optional[str]]:
        """获取构建信息"""
        return {
            'built_with': self.built_with,
            'feature_tool_hash': self.feature_tool_hash,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }