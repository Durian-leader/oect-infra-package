"""
版本管理器

负责特征版本的管理和固化，实现从列式存储向版本化矩阵的转换
"""
import h5py
import json
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any, Union, Tuple

########################### 日志设置 ################################
from ...logger_config import get_module_logger
logger = get_module_logger()
#####################################################################

from ..models.feature_data import VersionedFeatures
from ..models.feature_registry import FeatureRegistry, FeatureInfo
from .repository import FeatureRepository


class VersionManager:
    """
    版本管理器
    
    负责特征集合的版本化固化：
    - 从列式仓库选择特征组合生成版本化矩阵
    - 管理版本的创建、查询和维护
    - 支持版本间的特征差异对比
    - 确保版本的不可变性和数据完整性
    """
    
    def __init__(self, repository: FeatureRepository):
        """
        初始化版本管理器
        
        Args:
            repository: 特征数据仓库实例
        """
        self.repository = repository
        self.filepath = repository.filepath
    
    def create_version(self,
                      version_name: str,
                      feature_names: List[str],
                      data_type: str = "transfer",
                      feature_units: List[str] = None,
                      feature_descriptions: List[str] = None,
                      feature_aliases: List[str] = None,
                      force_overwrite: bool = False) -> bool:
        """
        创建版本化特征矩阵
        
        Args:
            version_name: 版本名称 (如 v1, v2, v3)
            feature_names: 特征名称列表，按矩阵列顺序
            data_type: 数据类型，'transfer' 或 'transient'
            feature_units: 特征单位列表（可选）
            feature_descriptions: 特征描述列表（可选）
            feature_aliases: 特征别名列表（可选）
            force_overwrite: 是否强制覆盖已存在的版本
            
        Returns:
            是否成功创建版本
            
        Examples:
            >>> version_manager = VersionManager(repository)
            >>> success = version_manager.create_version(
            ...     "v1",
            ...     ["gm_max_forward", "gm_max_reverse", "Von_forward", "Von_reverse"],
            ...     data_type="transfer",
            ...     feature_units=["S", "S", "V", "V"],
            ...     feature_descriptions=[
            ...         "Forward sweep maximum transconductance",
            ...         "Reverse sweep maximum transconductance", 
            ...         "Forward threshold voltage",
            ...         "Reverse threshold voltage"
            ...     ]
            ... )
        """
        try:
            with h5py.File(self.filepath, 'a') as f:
                # 使用正确的版本路径格式（匹配create_final_features.py）
                version_path = f"/{data_type}/versions/{version_name}"
                
                # 检查版本是否已存在
                if version_path in f and not force_overwrite:
                    raise ValueError(f"Version {version_name} already exists. Use force_overwrite=True to replace.")
                
                # 验证所有特征都存在
                missing_features = []
                feature_data_arrays = []
                
                for feature_name in feature_names:
                    feature_data = self.repository.get_feature(feature_name, data_type)
                    if feature_data is None:
                        missing_features.append(feature_name)
                    else:
                        feature_data_arrays.append(feature_data)
                
                if missing_features:
                    raise ValueError(f"Missing features: {missing_features}")
                
                # 验证所有特征数据形状一致
                n_steps = len(feature_data_arrays[0])
                for i, feature_data in enumerate(feature_data_arrays[1:], 1):
                    if len(feature_data) != n_steps:
                        raise ValueError(f"Feature {feature_names[i]} has inconsistent length: {len(feature_data)} vs {n_steps}")
                
                # 创建特征矩阵
                feature_matrix = np.column_stack(feature_data_arrays).astype(np.float32)
                n_features = len(feature_names)
                
                # 删除现有版本（如果覆盖）
                if version_path in f:
                    del f[version_path]
                
                # 创建版本组
                version_group = f.create_group(version_path)
                
                # 存储特征矩阵（使用create_final_features.py的压缩设置）
                chunks = (min(n_steps, 1024), n_features)
                matrix_dataset = version_group.create_dataset(
                    'matrix',
                    data=feature_matrix,
                    chunks=chunks,
                    compression='gzip',
                    compression_opts=6,
                    shuffle=True
                )
                
                # 存储特征名称（使用正确的名称和数据类型）
                feature_names_dt = h5py.string_dtype(length=32)
                feature_names_dataset = version_group.create_dataset(
                    'feature_names',
                    data=feature_names,
                    dtype=feature_names_dt
                )
                
                # 存储特征单位（如果提供）
                if feature_units:
                    if len(feature_units) != n_features:
                        raise ValueError(f"Units length ({len(feature_units)}) must match features length ({n_features})")
                    feature_units_dt = h5py.string_dtype(length=8)
                    feature_units_dataset = version_group.create_dataset(
                        'feature_units', 
                        data=feature_units,
                        dtype=feature_units_dt
                    )
                
                # 存储特征描述（如果提供）
                if feature_descriptions:
                    if len(feature_descriptions) != n_features:
                        raise ValueError(f"Descriptions length ({len(feature_descriptions)}) must match features length ({n_features})")
                    feature_descriptions_dt = h5py.string_dtype(length=64)
                    feature_descriptions_dataset = version_group.create_dataset(
                        'feature_descriptions',
                        data=feature_descriptions, 
                        dtype=feature_descriptions_dt
                    )
                
                # 存储特征别名（如果提供）
                if feature_aliases:
                    if len(feature_aliases) != n_features:
                        raise ValueError(f"Aliases length ({len(feature_aliases)}) must match features length ({n_features})")
                    feature_aliases_dt = h5py.string_dtype(length=16)
                    feature_aliases_dataset = version_group.create_dataset(
                        'feature_aliases',
                        data=feature_aliases,
                        dtype=feature_aliases_dt
                    )
                
                # 设置版本组属性（匹配create_final_features.py格式）
                version_group.attrs['version'] = version_name
                version_group.attrs['data_type'] = data_type
                version_group.attrs['created_at'] = datetime.now().isoformat()
                version_group.attrs['feature_count'] = n_features
                version_group.attrs['step_count'] = n_steps
                version_group.attrs['matrix_shape'] = feature_matrix.shape
                version_group.attrs['description'] = f'Version {version_name} feature matrix'
                version_group.attrs['format_version'] = 'v1.0'
                version_group.attrs['is_finalized'] = True
                
                # 更新注册表，标记特征为已版本化
                registry = self.repository._load_registry(f, data_type)
                
                for i, feature_name in enumerate(feature_names):
                    feature_info = registry.get_feature(feature_name)
                    if feature_info:
                        feature_info.is_versioned = True
                        feature_info.version = version_name
                        feature_info.version_index = i
                        registry.features[feature_name] = feature_info
                
                # 添加版本到注册表版本列表
                if version_name not in registry.versions:
                    registry.versions.append(version_name)
                    registry.versions.sort()
                
                # 保存注册表（使用结构化数组格式）
                self.repository._save_registry_structured(f, data_type, registry)
                
                # 更新注册表组属性
                registry_group = f[f"/{data_type}/columns/_registry"]
                registry_group.attrs['versioned_features'] = len([f for f in registry.features.values() if f.is_versioned])
                registry_group.attrs['available_versions'] = len(registry.versions)
                registry_group.attrs['latest_version'] = version_name
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to create version {version_name}: {e}")
            return False
    
    def get_version(self,
                   version_name: str,
                   data_type: str = "transfer") -> Optional[VersionedFeatures]:
        """
        获取版本化特征信息
        
        Args:
            version_name: 版本名称
            data_type: 数据类型
            
        Returns:
            版本化特征对象，如果不存在返回None
        """
        try:
            with h5py.File(self.filepath, 'r') as f:
                # 使用正确的版本路径格式
                version_path = f"/{data_type}/versions/{version_name}"
                
                if version_path not in f:
                    return None
                
                version_group = f[version_path]
                
                # 读取基本信息
                if 'matrix' not in version_group:
                    return None
                
                matrix_shape = version_group['matrix'].shape
                # 使用正确的数据集名称
                feature_names = [name.decode('utf-8') for name in version_group['feature_names'][...]]
                
                # 读取可选信息
                feature_units = None
                if 'feature_units' in version_group:
                    feature_units = [unit.decode('utf-8') for unit in version_group['feature_units'][...]]
                
                feature_descriptions = None
                if 'feature_descriptions' in version_group:
                    feature_descriptions = [desc.decode('utf-8') for desc in version_group['feature_descriptions'][...]]
                
                feature_aliases = None
                if 'feature_aliases' in version_group:
                    feature_aliases = [alias.decode('utf-8') for alias in version_group['feature_aliases'][...]]
                
                # 读取创建时间
                created_at = None
                if 'created_at' in version_group.attrs:
                    created_at = datetime.fromisoformat(version_group.attrs['created_at'])
                
                return VersionedFeatures(
                    version=version_name,
                    matrix_shape=matrix_shape,
                    feature_names=feature_names,
                    feature_units=feature_units,
                    feature_descriptions=feature_descriptions,
                    feature_aliases=feature_aliases,
                    created_at=created_at
                )
                
        except Exception as e:
            logger.error(f"Failed to get version {version_name}: {e}")
            return None
    
    def get_version_matrix(self,
                          version_name: str,
                          data_type: str = "transfer") -> Optional[np.ndarray]:
        """
        获取版本化特征矩阵数据
        
        Args:
            version_name: 版本名称
            data_type: 数据类型
            
        Returns:
            特征矩阵，形状为 (n_steps, n_features)
        """
        try:
            with h5py.File(self.filepath, 'r') as f:
                # 使用正确的版本路径格式
                matrix_path = f"/{data_type}/versions/{version_name}/matrix"
                
                if matrix_path in f:
                    return np.array(f[matrix_path])
                else:
                    return None
                    
        except Exception as e:
            logger.error(f"Failed to get version matrix {version_name}: {e}")
            return None
    
    def list_versions(self, data_type: str = "transfer") -> List[str]:
        """
        列出所有版本
        
        Args:
            data_type: 数据类型
            
        Returns:
            版本名称列表
        """
        try:
            with h5py.File(self.filepath, 'r') as f:
                registry = self.repository._load_registry(f, data_type)
                return registry.get_available_versions()
        except Exception as e:
            logger.error(f"Failed to list versions: {e}")
            return []
    
    def delete_version(self,
                      version_name: str,
                      data_type: str = "transfer",
                      update_registry: bool = True) -> bool:
        """
        删除版本
        
        Args:
            version_name: 版本名称
            data_type: 数据类型
            update_registry: 是否更新注册表中的版本化状态
            
        Returns:
            是否成功删除
        """
        try:
            with h5py.File(self.filepath, 'a') as f:
                # 使用正确的版本路径格式
                version_path = f"/{data_type}/versions/{version_name}"
                
                if version_path not in f:
                    return False
                
                # 删除版本组
                del f[version_path]
                
                if update_registry:
                    # 更新注册表
                    registry = self.repository._load_registry(f, data_type)
                    
                    # 取消特征的版本化标记
                    for feature_info in registry.features.values():
                        if feature_info.version == version_name:
                            feature_info.is_versioned = False
                            feature_info.version = None
                            feature_info.version_index = None
                    
                    # 从版本列表中删除
                    if version_name in registry.versions:
                        registry.versions.remove(version_name)
                    
                    # 保存注册表（使用结构化数组格式）
                    self.repository._save_registry_structured(f, data_type, registry)
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to delete version {version_name}: {e}")
            return False
    
    def compare_versions(self,
                        version1: str,
                        version2: str,
                        data_type: str = "transfer") -> Dict[str, Any]:
        """
        比较两个版本的差异
        
        Args:
            version1: 第一个版本名称
            version2: 第二个版本名称
            data_type: 数据类型
            
        Returns:
            版本差异信息字典
        """
        v1_info = self.get_version(version1, data_type)
        v2_info = self.get_version(version2, data_type)
        
        if not v1_info or not v2_info:
            return {'error': 'One or both versions not found'}
        
        comparison = {
            'version1': version1,
            'version2': version2,
            'basic_comparison': {
                'shape_comparison': {
                    'v1_shape': v1_info.matrix_shape,
                    'v2_shape': v2_info.matrix_shape,
                    'same_shape': v1_info.matrix_shape == v2_info.matrix_shape
                },
                'feature_count_comparison': {
                    'v1_features': v1_info.n_features,
                    'v2_features': v2_info.n_features,
                    'difference': v2_info.n_features - v1_info.n_features
                }
            },
            'feature_comparison': {
                'common_features': list(set(v1_info.feature_names) & set(v2_info.feature_names)),
                'v1_only_features': list(set(v1_info.feature_names) - set(v2_info.feature_names)),
                'v2_only_features': list(set(v2_info.feature_names) - set(v1_info.feature_names)),
                'feature_order_changed': v1_info.feature_names != v2_info.feature_names
            }
        }
        
        return comparison
    
    def get_version_statistics(self,
                             version_name: str,
                             data_type: str = "transfer") -> Dict[str, Any]:
        """
        获取版本统计信息
        
        Args:
            version_name: 版本名称
            data_type: 数据类型
            
        Returns:
            版本统计信息
        """
        version_info = self.get_version(version_name, data_type)
        if not version_info:
            return {}
        
        matrix = self.get_version_matrix(version_name, data_type)
        if matrix is None:
            return {}
        
        stats = {
            'basic_info': {
                'version': version_name,
                'data_type': data_type,
                'shape': version_info.matrix_shape,
                'n_steps': version_info.n_steps,
                'n_features': version_info.n_features,
                'created_at': version_info.created_at.isoformat() if version_info.created_at else None
            },
            'data_statistics': {
                'matrix_mean': float(np.mean(matrix)),
                'matrix_std': float(np.std(matrix)),
                'matrix_min': float(np.min(matrix)),
                'matrix_max': float(np.max(matrix)),
                'has_nan': bool(np.isnan(matrix).any()),
                'has_inf': bool(np.isinf(matrix).any())
            },
            'feature_statistics': {}
        }
        
        # 计算每个特征的统计信息
        for i, feature_name in enumerate(version_info.feature_names):
            feature_data = matrix[:, i]
            stats['feature_statistics'][feature_name] = {
                'mean': float(np.mean(feature_data)),
                'std': float(np.std(feature_data)),
                'min': float(np.min(feature_data)),
                'max': float(np.max(feature_data)),
                'has_nan': bool(np.isnan(feature_data).any()),
                'has_inf': bool(np.isinf(feature_data).any())
            }
        
        return stats
    
    def _update_version_attributes(self, hdf5_file: h5py.File, data_type: str, registry: FeatureRegistry) -> None:
        """更新文件级别的版本属性"""
        versions = registry.get_available_versions()
        
        if data_type == 'transfer':
            hdf5_file.attrs['transfer_versions'] = versions
        else:
            hdf5_file.attrs['transient_versions'] = versions