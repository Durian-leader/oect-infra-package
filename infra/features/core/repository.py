"""
特征数据仓库

负责特征数据的存储、读取和管理，包括列式存储和注册表维护
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

from ..models.feature_data import FeatureData, FeatureMetadata
from ..models.feature_registry import FeatureRegistry, FeatureInfo


class FeatureRepository:
    """
    特征数据仓库
    
    提供特征数据的存储、读取和管理功能：
    - 列式特征存储到分桶结构
    - 特征注册表的维护和更新
    - 支持按名称、桶、版本等多种方式的特征管理
    - 高效的数据压缩和存储优化
    """
    
    def __init__(self, filepath: str):
        """
        初始化特征数据仓库
        
        Args:
            filepath: 特征文件路径
        """
        self.filepath = Path(filepath)
        
        if not self.filepath.exists():
            raise FileNotFoundError(f"Feature file not found: {filepath}")
        
        # 验证文件格式
        self._validate_file_format()
    
    def _validate_file_format(self) -> None:
        """验证特征文件格式"""
        try:
            with h5py.File(self.filepath, 'r') as f:
                if f.attrs.get('file_type') != 'feature':
                    raise ValueError("Not a feature file")
        except Exception as e:
            raise ValueError(f"Invalid feature file format: {e}")
    
    def store_feature(self,
                     feature_name: str,
                     feature_data: np.ndarray,
                     data_type: str = "transfer",
                     metadata: FeatureMetadata = None,
                     bucket_name: str = None,
                     overwrite: bool = False) -> bool:
        """
        存储特征数据到列式仓库
        
        Args:
            feature_name: 特征名称
            feature_data: 特征数据数组，形状为 (n_steps,)
            data_type: 数据类型，'transfer' 或 'transient'
            metadata: 特征元数据
            bucket_name: 目标桶名称，如果为None则自动分配
            overwrite: 是否覆盖现有特征
            
        Returns:
            是否成功存储
            
        Examples:
            >>> repo = FeatureRepository("/data/features/test.h5")
            >>> metadata = FeatureMetadata(
            ...     name="gm_max_forward",
            ...     unit="S",
            ...     description="Forward sweep maximum transconductance"
            ... )
            >>> success = repo.store_feature(
            ...     "gm_max_forward", 
            ...     np.array([1e-6, 2e-6, 1.5e-6]),
            ...     metadata=metadata
            ... )
        """
        if data_type not in ['transfer', 'transient']:
            raise ValueError("data_type must be 'transfer' or 'transient'")
        
        if not isinstance(feature_data, np.ndarray) or feature_data.ndim != 1:
            raise ValueError("feature_data must be a 1D numpy array")
        
        try:
            with h5py.File(self.filepath, 'a') as f:
                # 获取或创建注册表
                registry = self._load_registry(f, data_type)
                
                # 检查特征是否已存在
                if feature_name in registry.features and not overwrite:
                    raise ValueError(f"Feature '{feature_name}' already exists. Use overwrite=True to replace.")
                
                # 确定桶名称
                if bucket_name is None:
                    bucket_name = self._assign_bucket(registry, data_type)
                
                # 确保桶存在
                self._ensure_bucket_exists(f, data_type, bucket_name)
                
                # 存储特征数据
                feature_path = f"/{data_type}/columns/buckets/{bucket_name}/{feature_name}"
                
                # 删除现有数据（如果覆盖）
                if feature_path in f:
                    del f[feature_path]
                
                # 确保数据是正确格式的numpy数组
                feature_data_converted = np.asarray(feature_data, dtype=np.float32)
                
                # 创建数据集，使用HDFView兼容的压缩方式
                chunks = (min(len(feature_data_converted), 16384),)
                dataset = f.create_dataset(
                    feature_path,
                    data=feature_data_converted,
                    chunks=chunks,
                    compression='gzip',  # 改为gzip，HDFView兼容性更好
                    compression_opts=6,
                    shuffle=True
                )
                
                # 设置数据集属性
                dataset.attrs['created_at'] = datetime.now().isoformat()
                if metadata:
                    if metadata.unit:
                        dataset.attrs['unit'] = metadata.unit
                    if metadata.description:
                        dataset.attrs['description'] = metadata.description
                
                # 更新注册表
                feature_info = FeatureInfo(
                    name=feature_name,
                    unit=metadata.unit if metadata else None,
                    description=metadata.description if metadata else None,
                    alias=metadata.alias if metadata else None,
                    data_type="float32",
                    bucket=bucket_name,
                    hdf5_path=feature_path,
                    created_at=datetime.now()
                )
                
                registry.add_feature(feature_info)
                
                # 创建软链接索引
                index_path = f"/{data_type}/columns/_registry/by_name/{feature_name}"
                if index_path in f:
                    del f[index_path]
                f[index_path] = h5py.SoftLink(feature_path)
                
                # 保存更新的注册表（使用结构化数组，HDFView兼容格式）
                self._save_registry_structured(f, data_type, registry)
                
                # 更新文件属性
                self._update_file_attributes(f, data_type)
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to store feature {feature_name}: {e}")
            return False
    
    def store_multiple_features(self,
                              features: Dict[str, np.ndarray],
                              data_type: str = "transfer",
                              metadata_dict: Dict[str, FeatureMetadata] = None,
                              bucket_name: str = None,
                              overwrite: bool = False) -> Dict[str, bool]:
        """
        批量存储多个特征
        
        Args:
            features: 特征名称到数据的字典
            data_type: 数据类型
            metadata_dict: 特征元数据字典  
            bucket_name: 目标桶名称
            overwrite: 是否覆盖现有特征
            
        Returns:
            每个特征的存储结果
        """
        results = {}
        metadata_dict = metadata_dict or {}
        
        for feature_name, feature_data in features.items():
            metadata = metadata_dict.get(feature_name)
            results[feature_name] = self.store_feature(
                feature_name, feature_data, data_type, 
                metadata, bucket_name, overwrite
            )
        
        return results
    
    def get_feature(self,
                   feature_name: str,
                   data_type: str = "transfer") -> Optional[np.ndarray]:
        """
        读取特征数据
        
        Args:
            feature_name: 特征名称或别名
            data_type: 数据类型
            
        Returns:
            特征数据数组，如果不存在返回None
        """
        try:
            with h5py.File(self.filepath, 'r') as f:
                # 首先尝试从新的简化结构中读取
                simple_path = f"{data_type}/{feature_name}"
                if simple_path in f:
                    return np.array(f[simple_path])
                
                # 向后兼容：尝试通过旧的索引读取
                index_path = f"/{data_type}/columns/_registry/by_name/{feature_name}"
                if index_path in f:
                    dataset = f[index_path]
                    return np.array(dataset)
                
                # 向后兼容：尝试通过注册表查找别名
                try:
                    registry = self._load_registry(f, data_type)
                    feature_info = registry.get_feature(feature_name)
                    if feature_info and feature_info.hdf5_path:
                        if feature_info.hdf5_path in f:
                            dataset = f[feature_info.hdf5_path]
                            return np.array(dataset)
                except:
                    # 如果旧格式读取失败，忽略错误
                    pass
                
                return None
                
        except Exception as e:
            logger.error(f"Failed to read feature {feature_name}: {e}")
            return None
    
    def get_multiple_features(self,
                            feature_names: List[str],
                            data_type: str = "transfer") -> Dict[str, Optional[np.ndarray]]:
        """
        批量读取多个特征
        
        Args:
            feature_names: 特征名称列表
            data_type: 数据类型
            
        Returns:
            特征名称到数据的字典
        """
        results = {}
        for feature_name in feature_names:
            results[feature_name] = self.get_feature(feature_name, data_type)
        return results
    
    def get_features_by_bucket(self,
                              bucket_name: str,
                              data_type: str = "transfer") -> Dict[str, np.ndarray]:
        """
        读取指定桶中的所有特征
        
        Args:
            bucket_name: 桶名称
            data_type: 数据类型
            
        Returns:
            特征名称到数据的字典
        """
        features = {}
        
        try:
            with h5py.File(self.filepath, 'r') as f:
                bucket_path = f"/{data_type}/columns/buckets/{bucket_name}"
                if bucket_path in f:
                    bucket_group = f[bucket_path]
                    for feature_name in bucket_group.keys():
                        dataset = bucket_group[feature_name]
                        features[feature_name] = np.array(dataset)
        
        except Exception as e:
            logger.error(f"Failed to read bucket {bucket_name}: {e}")
        
        return features
    
    def list_features(self, data_type: str = "transfer") -> List[str]:
        """
        列出所有特征名称
        
        Args:
            data_type: 数据类型
            
        Returns:
            特征名称列表
        """
        try:
            with h5py.File(self.filepath, 'r') as f:
                registry = self._load_registry(f, data_type)
                return list(registry.features.keys())
        except Exception as e:
            logger.error(f"Failed to list features: {e}")
            return []
    
    def get_feature_info(self,
                        feature_name: str,
                        data_type: str = "transfer") -> Optional[FeatureInfo]:
        """
        获取特征元信息
        
        Args:
            feature_name: 特征名称
            data_type: 数据类型
            
        Returns:
            特征信息对象
        """
        try:
            with h5py.File(self.filepath, 'r') as f:
                registry = self._load_registry(f, data_type)
                return registry.get_feature(feature_name)
        except Exception as e:
            logger.error(f"Failed to get feature info: {e}")
            return None
    
    def get_registry(self, data_type: str = "transfer") -> Optional[FeatureRegistry]:
        """
        获取特征注册表
        
        Args:
            data_type: 数据类型
            
        Returns:
            特征注册表对象
        """
        try:
            with h5py.File(self.filepath, 'r') as f:
                return self._load_registry(f, data_type)
        except Exception as e:
            logger.error(f"Failed to get registry: {e}")
            return None
    
    def search_features(self,
                       keyword: str,
                       data_type: str = "transfer",
                       search_in: List[str] = None) -> List[FeatureInfo]:
        """
        搜索特征
        
        Args:
            keyword: 搜索关键词
            data_type: 数据类型
            search_in: 搜索字段列表
            
        Returns:
            匹配的特征列表
        """
        try:
            with h5py.File(self.filepath, 'r') as f:
                registry = self._load_registry(f, data_type)
                return registry.search_features(keyword, search_in)
        except Exception as e:
            logger.error(f"Failed to search features: {e}")
            return []
    
    def delete_feature(self,
                      feature_name: str,
                      data_type: str = "transfer") -> bool:
        """
        删除特征
        
        Args:
            feature_name: 特征名称
            data_type: 数据类型
            
        Returns:
            是否成功删除
        """
        try:
            with h5py.File(self.filepath, 'a') as f:
                registry = self._load_registry(f, data_type)
                feature_info = registry.get_feature(feature_name)
                
                if not feature_info:
                    return False
                
                # 删除数据集
                if feature_info.hdf5_path and feature_info.hdf5_path in f:
                    del f[feature_info.hdf5_path]
                
                # 删除索引
                index_path = f"/{data_type}/columns/_registry/by_name/{feature_name}"
                if index_path in f:
                    del f[index_path]
                
                # 从注册表中删除
                registry.remove_feature(feature_name)
                
                # 保存注册表
                self._save_registry(f, data_type, registry)
                
                # 更新文件属性
                self._update_file_attributes(f, data_type)
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to delete feature {feature_name}: {e}")
            return False
    
    def get_statistics(self, data_type: str = "transfer") -> Dict[str, Any]:
        """
        获取仓库统计信息
        
        Args:
            data_type: 数据类型
            
        Returns:
            统计信息字典
        """
        try:
            with h5py.File(self.filepath, 'r') as f:
                registry = self._load_registry(f, data_type)
                
                stats = registry.get_statistics()
                
                # 添加存储信息
                total_size = 0
                feature_sizes = {}
                
                for feature_name, feature_info in registry.features.items():
                    if feature_info.hdf5_path and feature_info.hdf5_path in f:
                        dataset = f[feature_info.hdf5_path]
                        size = dataset.nbytes
                        total_size += size
                        feature_sizes[feature_name] = size
                
                stats['storage_info'] = {
                    'total_size_bytes': total_size,
                    'total_size_mb': total_size / (1024 * 1024),
                    'feature_sizes': feature_sizes
                }
                
                return stats
                
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {}
    
    def _load_registry(self, hdf5_file: h5py.File, data_type: str) -> FeatureRegistry:
        """加载特征注册表（支持结构化数组和JSON格式）"""
        registry_path = f"/{data_type}/columns/_registry/table"
        registry_group_path = f"/{data_type}/columns/_registry"
        
        if registry_path in hdf5_file:
            dataset = hdf5_file[registry_path]
            
            # 检查是否是新的结构化数组格式
            if hasattr(dataset, 'dtype') and len(dataset.dtype.names or []) > 1:
                # 新的结构化数组格式
                return self._load_registry_from_structured_array(hdf5_file, data_type, dataset)
            else:
                # 旧的JSON格式
                return self._load_registry_from_json(dataset)
                
        elif registry_group_path in hdf5_file:
            # 如果只有组但没有table，可能是空的注册表
            registry_group = hdf5_file[registry_group_path]
            registry_version = registry_group.attrs.get('registry_version', '1.0')
            created_at_str = registry_group.attrs.get('created_at', '')
            created_at = datetime.fromisoformat(created_at_str) if created_at_str else datetime.now()
            
            return FeatureRegistry(
                data_type=data_type,
                registry_version=registry_version,
                created_at=created_at
            )
        else:
            # 创建新的注册表
            return FeatureRegistry(data_type=data_type, created_at=datetime.now())
    
    def _load_registry_from_structured_array(self, hdf5_file: h5py.File, data_type: str, dataset: h5py.Dataset) -> FeatureRegistry:
        """从结构化数组加载注册表"""
        registry_group = hdf5_file[f"/{data_type}/columns/_registry"]
        
        # 读取注册表级别信息
        registry_version = registry_group.attrs.get('registry_version', '1.0')
        created_at_str = registry_group.attrs.get('created_at', '')
        updated_at_str = registry_group.attrs.get('updated_at', '')
        
        created_at = datetime.fromisoformat(created_at_str) if created_at_str else datetime.now()
        updated_at = datetime.fromisoformat(updated_at_str) if updated_at_str else None
        
        # 创建注册表
        registry = FeatureRegistry(
            data_type=data_type,
            registry_version=registry_version,
            created_at=created_at,
            updated_at=updated_at
        )
        
        # 读取特征信息
        structured_data = dataset[...]
        for row in structured_data:
            feature_info = FeatureInfo(
                name=row['name'].decode('utf-8') if isinstance(row['name'], bytes) else row['name'],
                unit=row['unit'].decode('utf-8') if isinstance(row['unit'], bytes) else (row['unit'] or None),
                description=row['description'].decode('utf-8') if isinstance(row['description'], bytes) else (row['description'] or None),
                alias=row['alias'].decode('utf-8') if isinstance(row['alias'], bytes) else (row['alias'] or None),
                data_type=row['data_type'].decode('utf-8') if isinstance(row['data_type'], bytes) else row['data_type'],
                bucket=row['bucket'].decode('utf-8') if isinstance(row['bucket'], bytes) else row['bucket'],
                hdf5_path=row['hdf5_path'].decode('utf-8') if isinstance(row['hdf5_path'], bytes) else row['hdf5_path'],
                version=row['version'].decode('utf-8') if isinstance(row['version'], bytes) else (row['version'] or None),
                version_index=int(row['version_index']) if row['version_index'] != -1 else None,
                is_active=bool(row['is_active']),
                is_versioned=bool(row['is_versioned']),
                created_at=datetime.fromisoformat(row['created_at'].decode('utf-8')) if row['created_at'] else datetime.now(),
                updated_at=datetime.fromisoformat(row['updated_at'].decode('utf-8')) if row['updated_at'] else None
            )
            registry.add_feature(feature_info)
        
        # 读取桶信息
        if 'buckets' in registry_group:
            bucket_data = registry_group['buckets'][...]
            registry.buckets = [row['bucket_name'].decode('utf-8') if isinstance(row['bucket_name'], bytes) else row['bucket_name'] 
                              for row in bucket_data]
        
        # 读取版本信息
        if 'versions' in registry_group:
            version_data = registry_group['versions'][...]
            registry.versions = [row['version_name'].decode('utf-8') if isinstance(row['version_name'], bytes) else row['version_name'] 
                               for row in version_data]
        
        return registry
    
    def _load_registry_from_json(self, dataset: h5py.Dataset) -> FeatureRegistry:
        """从JSON格式加载注册表（向后兼容）"""
        registry_bytes = dataset[...]
        # 处理numpy数组格式的bytes
        if isinstance(registry_bytes, np.ndarray):
            registry_bytes = registry_bytes.item()  # 从numpy标量中提取Python对象
        
        if isinstance(registry_bytes, bytes):
            registry_str = registry_bytes.decode('utf-8')
        else:
            registry_str = str(registry_bytes)
        
        if registry_str.strip():  # 确保不是空字符串
            registry_data = json.loads(registry_str)
            return FeatureRegistry.from_dict(registry_data)
        else:
            return FeatureRegistry(data_type="transfer", created_at=datetime.now())
    
    def _save_registry(self, hdf5_file: h5py.File, data_type: str, registry: FeatureRegistry) -> None:
        """保存特征注册表"""
        registry_path = f"/{data_type}/columns/_registry/table"
        
        # 删除现有数据集
        if registry_path in hdf5_file:
            del hdf5_file[registry_path]
        
        # 创建新数据集
        registry_data = json.dumps(registry.to_dict(), ensure_ascii=False)
        hdf5_file.create_dataset(registry_path, data=registry_data.encode('utf-8'))
    
    def _assign_bucket(self, registry: FeatureRegistry, data_type: str, max_bucket_size: int = 20) -> str:
        """分配桶名称"""
        # 获取现有桶的使用情况
        bucket_usage = {}
        for feature_info in registry.features.values():
            if feature_info.bucket:
                bucket_usage[feature_info.bucket] = bucket_usage.get(feature_info.bucket, 0) + 1
        
        # 寻找未满的桶
        for bucket, count in bucket_usage.items():
            if count < max_bucket_size:
                return bucket
        
        # 创建新桶
        bucket_index = len([b for b in registry.buckets if b.startswith('bk_')])
        return f"bk_{bucket_index:02d}"
    
    def _ensure_bucket_exists(self, hdf5_file: h5py.File, data_type: str, bucket_name: str) -> None:
        """确保桶存在"""
        bucket_path = f"/{data_type}/columns/buckets/{bucket_name}"
        if bucket_path not in hdf5_file:
            hdf5_file.create_group(bucket_path)
    
    def _update_file_attributes(self, hdf5_file: h5py.File, data_type: str) -> None:
        """更新文件级别属性"""
        registry = self._load_registry(hdf5_file, data_type)
        
        if data_type == 'transfer':
            hdf5_file.attrs['has_transfer_features'] = registry.active_features > 0
            hdf5_file.attrs['total_transfer_features'] = registry.active_features
        else:
            hdf5_file.attrs['has_transient_features'] = registry.active_features > 0
            hdf5_file.attrs['total_transient_features'] = registry.active_features
    
    def _update_file_attributes_simple(self, hdf5_file: h5py.File, data_type: str) -> None:
        """更新文件级别属性 - 简化版本，直接统计数据集数量"""
        if data_type in hdf5_file:
            data_group = hdf5_file[data_type]
            # 统计直接存储在组下的数据集数量（排除子组）
            feature_count = sum(1 for key in data_group.keys() 
                              if isinstance(data_group[key], h5py.Dataset))
            
            if data_type == 'transfer':
                hdf5_file.attrs['has_transfer_features'] = feature_count > 0
                hdf5_file.attrs['total_transfer_features'] = feature_count
            else:
                hdf5_file.attrs['has_transient_features'] = feature_count > 0
                hdf5_file.attrs['total_transient_features'] = feature_count
        else:
            # 如果组不存在，设置为0
            if data_type == 'transfer':
                hdf5_file.attrs['has_transfer_features'] = False
                hdf5_file.attrs['total_transfer_features'] = 0
            else:
                hdf5_file.attrs['has_transient_features'] = False
                hdf5_file.attrs['total_transient_features'] = 0
    
    def _save_registry_structured(self, hdf5_file: h5py.File, data_type: str, registry: FeatureRegistry) -> None:
        """使用HDF5结构化数组保存特征注册表，HDFView友好"""
        registry_path = f"/{data_type}/columns/_registry/table"
        
        # 删除现有数据集
        if registry_path in hdf5_file:
            del hdf5_file[registry_path]
        
        # 将特征信息转换为结构化数组
        features = list(registry.features.values())
        if not features:
            # 如果没有特征，创建空的注册表组
            registry_group = hdf5_file.require_group(f"/{data_type}/columns/_registry")
            registry_group.attrs['registry_version'] = registry.registry_version
            registry_group.attrs['created_at'] = registry.created_at.isoformat() if registry.created_at else ""
            registry_group.attrs['updated_at'] = registry.updated_at.isoformat() if registry.updated_at else ""
            registry_group.attrs['data_type'] = data_type
            registry_group.attrs['total_features'] = 0
            return
        
        # 创建结构化数组的数据类型（完全匹配create_final_features.py格式）
        dtype = [
            ('name', h5py.string_dtype(length=32)),
            ('unit', h5py.string_dtype(length=8)),
            ('description', h5py.string_dtype(length=64)),
            ('alias', h5py.string_dtype(length=16)),
            ('data_type', h5py.string_dtype(length=16)),
            ('bucket', h5py.string_dtype(length=16)),
            ('hdf5_path', h5py.string_dtype(length=128)),
            ('version', h5py.string_dtype(length=16)),
            ('version_index', 'i4'),
            ('is_active', 'bool'),
            ('is_versioned', 'bool'),
            ('created_at', h5py.string_dtype(length=32)),
            ('updated_at', h5py.string_dtype(length=32))
        ]
        
        # 准备数据（确保字符串长度不超过dtype限制）
        data = []
        for feature in features:
            data.append((
                (feature.name or '')[:32],  # 限制名称长度
                (feature.unit or '')[:8],   # 限制单位长度
                (feature.description or '')[:64],  # 限制描述长度
                (feature.alias or '')[:16], # 限制别名长度
                (feature.data_type or 'float32')[:16], # 限制数据类型长度
                (feature.bucket or '')[:16], # 限制桶名长度
                (feature.hdf5_path or '')[:128], # 限制路径长度
                (feature.version or '')[:16], # 限制版本长度
                feature.version_index if feature.version_index is not None else -1,
                bool(feature.is_active),
                bool(feature.is_versioned),
                (feature.created_at.isoformat() if feature.created_at else '')[:32],
                (feature.updated_at.isoformat() if feature.updated_at else '')[:32]
            ))
        
        # 创建结构化数组数据集
        structured_array = np.array(data, dtype=dtype)
        registry_group = hdf5_file.require_group(f"/{data_type}/columns/_registry")
        
        # 存储结构化数组
        dataset = registry_group.create_dataset('table', data=structured_array, compression='gzip')
        
        # 设置注册表级别的属性
        registry_group.attrs['registry_version'] = registry.registry_version
        registry_group.attrs['created_at'] = registry.created_at.isoformat() if registry.created_at else ""
        registry_group.attrs['updated_at'] = registry.updated_at.isoformat() if registry.updated_at else ""
        registry_group.attrs['data_type'] = data_type
        registry_group.attrs['total_features'] = len(features)
        registry_group.attrs['active_features'] = sum(1 for f in features if f.is_active)
        registry_group.attrs['versioned_features'] = sum(1 for f in features if f.is_versioned)
        
        # 存储桶列表和版本列表（使用h5py兼容的字符串类型）
        if registry.buckets:
            bucket_dtype = [('bucket_name', h5py.string_dtype(length=16)), ('feature_count', 'i4')]
            bucket_data = [(bucket, sum(1 for f in features if f.bucket == bucket)) 
                          for bucket in registry.buckets]
            bucket_array = np.array(bucket_data, dtype=bucket_dtype)
            if 'buckets' in registry_group:
                del registry_group['buckets']
            registry_group.create_dataset('buckets', data=bucket_array, compression='gzip')
        
        # 存储版本列表（如果有，使用h5py兼容的字符串类型）
        if registry.versions:
            version_dtype = [('version_name', h5py.string_dtype(length=16)), ('created_at', h5py.string_dtype(length=32))]
            version_data = [(version, '') for version in registry.versions]  # 简化版本信息
            version_array = np.array(version_data, dtype=version_dtype)
            if 'versions' in registry_group:
                del registry_group['versions']
            registry_group.create_dataset('versions', data=version_array, compression='gzip')