"""
特征数据读取器

提供简化的特征数据读取接口，支持矩阵和列式数据的高效访问
"""
import h5py
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any, Union, Tuple

########################### 日志设置 ################################
from ...logger_config import get_module_logger
logger = get_module_logger()
#####################################################################

from ..models.feature_data import FeatureData, VersionedFeatures
from ..models.feature_registry import FeatureRegistry, FeatureInfo
from ..core.repository import FeatureRepository
from ..core.version_manager import VersionManager


class FeatureReader:
    """
    特征数据读取器
    
    提供便捷的特征数据访问接口：
    - 版本化矩阵的高效读取
    - 列式特征的按需加载
    - 支持特征选择和数据格式转换
    - 内置缓存机制优化重复读取
    """
    
    def __init__(self, filepath: str):
        """
        初始化特征数据读取器
        
        Args:
            filepath: 特征文件路径
        """
        self.filepath = Path(filepath)
        
        if not self.filepath.exists():
            raise FileNotFoundError(f"Feature file not found: {filepath}")
        
        # 初始化基础组件
        self.repository = FeatureRepository(str(self.filepath))
        self.version_manager = VersionManager(self.repository)
        
        # 加载文件元数据
        self.file_info = self._load_file_info()
        
        # 缓存
        self._matrix_cache = {}
        self._feature_cache = {}
    
    def _load_file_info(self) -> FeatureData:
        """加载文件基本信息"""
        try:
            return FeatureData.parse_from_filename(self.filepath.name)
        except Exception as e:
            # 如果文件名解析失败，尝试从HDF5属性读取
            with h5py.File(self.filepath, 'r') as f:
                return FeatureData(
                    chip_id=f.attrs.get('chip_id', 'unknown'),
                    device_id=f.attrs.get('device_id', 'unknown'),
                    description=f.attrs.get('description', 'unknown'),
                    test_id=f.attrs.get('test_id', 'unknown'),
                    created_at=datetime.fromisoformat(f.attrs['created_at']) if 'created_at' in f.attrs else None
                )
    
    def get_version_matrix(self,
                          version: str = "latest",
                          data_type: str = "transfer",
                          use_cache: bool = True) -> Optional[np.ndarray]:
        """
        读取版本化特征矩阵
        
        Args:
            version: 版本名称，"latest" 表示最新版本
            data_type: 数据类型，'transfer' 或 'transient'
            use_cache: 是否使用缓存
            
        Returns:
            特征矩阵，形状为 (n_steps, n_features)
            
        Examples:
            >>> reader = FeatureReader("/data/features/test.h5")
            >>> matrix = reader.get_version_matrix("v1", "transfer")
            >>> print(matrix.shape)  # (n_steps, n_features)
        """
        # 解析版本名称
        if version == "latest":
            available_versions = self.version_manager.list_versions(data_type)
            if not available_versions:
                return None
            version = available_versions[-1]  # 假设版本按名称排序，最后一个是最新的
        
        # 检查缓存
        cache_key = f"{version}_{data_type}_matrix"
        if use_cache and cache_key in self._matrix_cache:
            return self._matrix_cache[cache_key]
        
        # 读取矩阵
        matrix = self.version_manager.get_version_matrix(version, data_type)
        
        # 缓存结果
        if use_cache and matrix is not None:
            self._matrix_cache[cache_key] = matrix
        
        return matrix
    
    def get_version_dataframe(self,
                             version: str = "latest",
                             data_type: str = "transfer",
                             feature_names: List[str] = None) -> Optional[pd.DataFrame]:
        """
        读取版本化特征矩阵并转换为DataFrame
        
        Args:
            version: 版本名称
            data_type: 数据类型
            feature_names: 指定特征名称列表，None表示使用所有特征
            
        Returns:
            特征DataFrame，列名为特征名称
        """
        matrix = self.get_version_matrix(version, data_type)
        if matrix is None:
            return None
        
        # 获取版本信息
        version_info = self.version_manager.get_version(version, data_type)
        if not version_info:
            return None
        
        # 创建DataFrame
        df = pd.DataFrame(matrix, columns=version_info.feature_names)
        
        # 如果指定了特征名称，则筛选
        if feature_names:
            available_features = [name for name in feature_names if name in df.columns]
            if not available_features:
                return None
            df = df[available_features]
        
        return df
    
    def get_features(self,
                    feature_names: List[str],
                    data_type: str = "transfer",
                    as_dataframe: bool = False) -> Union[Dict[str, np.ndarray], pd.DataFrame, None]:
        """
        读取指定的特征数据（从列式仓库）
        
        Args:
            feature_names: 特征名称列表
            data_type: 数据类型
            as_dataframe: 是否返回DataFrame格式
            
        Returns:
            特征数据字典或DataFrame
            
        Examples:
            >>> reader = FeatureReader("/data/features/test.h5")
            >>> features = reader.get_features(
            ...     ["gm_max_forward", "Von_forward"], 
            ...     data_type="transfer"
            ... )
            >>> print(features["gm_max_forward"])  # numpy array
        """
        features_data = self.repository.get_multiple_features(feature_names, data_type)
        
        # 过滤掉None值
        valid_features = {name: data for name, data in features_data.items() if data is not None}
        
        if not valid_features:
            return None
        
        if as_dataframe:
            # 确保所有特征长度一致
            lengths = [len(data) for data in valid_features.values()]
            if len(set(lengths)) > 1:
                logger.warning(f"Features have inconsistent lengths: {dict(zip(valid_features.keys(), lengths))}")
                # 取最小长度
                min_length = min(lengths)
                valid_features = {name: data[:min_length] for name, data in valid_features.items()}
            
            return pd.DataFrame(valid_features)
        
        return valid_features
    
    def get_feature(self,
                   feature_name: str,
                   data_type: str = "transfer") -> Optional[np.ndarray]:
        """
        读取单个特征数据
        
        Args:
            feature_name: 特征名称或别名
            data_type: 数据类型
            
        Returns:
            特征数据数组
        """
        return self.repository.get_feature(feature_name, data_type)
    
    def get_features_by_bucket(self,
                              bucket_name: str,
                              data_type: str = "transfer",
                              as_dataframe: bool = False) -> Union[Dict[str, np.ndarray], pd.DataFrame, None]:
        """
        读取指定桶中的所有特征
        
        Args:
            bucket_name: 桶名称
            data_type: 数据类型
            as_dataframe: 是否返回DataFrame格式
            
        Returns:
            特征数据字典或DataFrame
        """
        features_data = self.repository.get_features_by_bucket(bucket_name, data_type)
        
        if not features_data:
            return None
        
        if as_dataframe:
            return pd.DataFrame(features_data)
        
        return features_data
    
    def list_versions(self, data_type: str = "transfer") -> List[str]:
        """
        列出可用版本
        
        Args:
            data_type: 数据类型
            
        Returns:
            版本名称列表
        """
        return self.version_manager.list_versions(data_type)
    
    def list_features(self, data_type: str = "transfer") -> List[str]:
        """
        列出所有特征名称
        
        Args:
            data_type: 数据类型
            
        Returns:
            特征名称列表
        """
        return self.repository.list_features(data_type)
    
    def list_buckets(self, data_type: str = "transfer") -> List[str]:
        """
        列出所有桶名称
        
        Args:
            data_type: 数据类型
            
        Returns:
            桶名称列表
        """
        registry = self.repository.get_registry(data_type)
        if registry:
            return registry.get_available_buckets()
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
        return self.repository.get_feature_info(feature_name, data_type)
    
    def get_version_info(self,
                        version: str,
                        data_type: str = "transfer") -> Optional[VersionedFeatures]:
        """
        获取版本信息
        
        Args:
            version: 版本名称
            data_type: 数据类型
            
        Returns:
            版本化特征对象
        """
        return self.version_manager.get_version(version, data_type)
    
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
        return self.repository.search_features(keyword, data_type, search_in)
    
    def get_summary(self) -> Dict[str, Any]:
        """
        获取文件摘要信息 - 适配新的简化格式
        
        Returns:
            文件摘要字典
        """
        summary = {
            'file_info': self.file_info.get_summary(),
            'transfer_info': {},
            'transient_info': {}
        }
        
        try:
            with h5py.File(self.filepath, 'r') as f:
                # 获取Transfer信息（新格式）
                if 'transfer' in f:
                    transfer_group = f['transfer']
                    feature_names = [key for key in transfer_group.keys() 
                                   if isinstance(transfer_group[key], h5py.Dataset)]
                    
                    summary['transfer_info'] = {
                        'statistics': {
                            'basic_stats': {
                                'data_type': 'transfer',
                                'total_features': len(feature_names),
                                'active_features': len(feature_names),
                                'versioned_features': 0,
                                'unversioned_features': len(feature_names)
                            },
                            'feature_names': feature_names,
                            'created_at': transfer_group.attrs.get('created_at'),
                            'updated_at': transfer_group.attrs.get('updated_at')
                        },
                        'versions': [],
                        'latest_version': None,
                        'features': {name: self._get_feature_info_simple(f, 'transfer', name) 
                                   for name in feature_names}
                    }
                else:
                    # 尝试使用旧格式
                    try:
                        transfer_registry = self.repository.get_registry('transfer')
                        if transfer_registry:
                            transfer_stats = transfer_registry.get_statistics()
                            transfer_versions = self.list_versions('transfer')
                            
                            summary['transfer_info'] = {
                                'statistics': transfer_stats,
                                'versions': transfer_versions,
                                'latest_version': transfer_versions[-1] if transfer_versions else None
                            }
                    except:
                        summary['transfer_info'] = {'statistics': {'basic_stats': {'total_features': 0}}}
                
                # 获取Transient信息（新格式）
                if 'transient' in f:
                    transient_group = f['transient']
                    feature_names = [key for key in transient_group.keys() 
                                   if isinstance(transient_group[key], h5py.Dataset)]
                    
                    summary['transient_info'] = {
                        'statistics': {
                            'basic_stats': {
                                'data_type': 'transient',
                                'total_features': len(feature_names),
                                'active_features': len(feature_names),
                                'versioned_features': 0,
                                'unversioned_features': len(feature_names)
                            },
                            'feature_names': feature_names,
                            'created_at': transient_group.attrs.get('created_at'),
                            'updated_at': transient_group.attrs.get('updated_at')
                        },
                        'versions': [],
                        'latest_version': None,
                        'features': {name: self._get_feature_info_simple(f, 'transient', name) 
                                   for name in feature_names}
                    }
                else:
                    # 尝试使用旧格式
                    try:
                        transient_registry = self.repository.get_registry('transient')
                        if transient_registry:
                            transient_stats = transient_registry.get_statistics()
                            transient_versions = self.list_versions('transient')
                            
                            summary['transient_info'] = {
                                'statistics': transient_stats,
                                'versions': transient_versions,
                                'latest_version': transient_versions[-1] if transient_versions else None
                            }
                    except:
                        summary['transient_info'] = {'statistics': {'basic_stats': {'total_features': 0}}}
        
        except Exception as e:
            logger.error(f"Error loading summary: {e}")
            # 返回基本结构
            summary['transfer_info'] = {'statistics': {'basic_stats': {'total_features': 0}}}
            summary['transient_info'] = {'statistics': {'basic_stats': {'total_features': 0}}}
        
        return summary
    
    def _get_feature_info_simple(self, hdf5_file: h5py.File, data_type: str, feature_name: str) -> Dict[str, Any]:
        """获取简化格式的特征信息"""
        try:
            dataset = hdf5_file[f"{data_type}/{feature_name}"]
            return {
                'name': feature_name,
                'unit': dataset.attrs.get('unit', ''),
                'description': dataset.attrs.get('description', ''),
                'shape': dataset.shape,
                'dtype': str(dataset.dtype),
                'created_at': dataset.attrs.get('created_at', '')
            }
        except:
            return {'name': feature_name}
    
    def get_data_preview(self,
                        data_type: str = "transfer",
                        max_features: int = 10,
                        max_rows: int = 5) -> Optional[pd.DataFrame]:
        """
        获取数据预览
        
        Args:
            data_type: 数据类型
            max_features: 最大特征数量
            max_rows: 最大行数
            
        Returns:
            预览DataFrame
        """
        # 优先使用最新版本的矩阵
        versions = self.list_versions(data_type)
        if versions:
            df = self.get_version_dataframe(versions[-1], data_type)
            if df is not None:
                # 限制特征数量和行数
                if len(df.columns) > max_features:
                    df = df.iloc[:, :max_features]
                if len(df) > max_rows:
                    df = df.head(max_rows)
                return df
        
        # 如果没有版本，尝试从列式仓库读取
        feature_names = self.list_features(data_type)
        if feature_names:
            selected_features = feature_names[:max_features]
            features_data = self.get_features(selected_features, data_type, as_dataframe=True)
            if features_data is not None and len(features_data) > max_rows:
                features_data = features_data.head(max_rows)
            return features_data
        
        return None
    
    def export_features(self,
                       output_path: str,
                       feature_names: List[str] = None,
                       version: str = None,
                       data_type: str = "transfer",
                       format: str = "csv") -> bool:
        """
        导出特征数据到外部文件
        
        Args:
            output_path: 输出文件路径
            feature_names: 特征名称列表，None表示所有特征
            version: 版本名称，None表示从列式仓库读取
            data_type: 数据类型
            format: 输出格式，支持 'csv', 'parquet', 'h5'
            
        Returns:
            是否成功导出
        """
        try:
            # 获取数据
            if version:
                df = self.get_version_dataframe(version, data_type, feature_names)
            else:
                if feature_names:
                    df = self.get_features(feature_names, data_type, as_dataframe=True)
                else:
                    all_features = self.list_features(data_type)
                    df = self.get_features(all_features, data_type, as_dataframe=True)
            
            if df is None or df.empty:
                return False
            
            # 导出数据
            output_path = Path(output_path)
            
            if format.lower() == 'csv':
                df.to_csv(output_path, index=False)
            elif format.lower() == 'parquet':
                df.to_parquet(output_path, index=False)
            elif format.lower() == 'h5':
                df.to_hdf(output_path, key='features', mode='w')
            else:
                raise ValueError(f"Unsupported format: {format}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to export features: {e}")
            return False
    
    def clear_cache(self):
        """清理缓存"""
        self._matrix_cache.clear()
        self._feature_cache.clear()
    
    @property
    def chip_id(self) -> str:
        """芯片ID"""
        return self.file_info.chip_id
    
    @property
    def device_id(self) -> str:
        """设备ID"""
        return self.file_info.device_id
    
    @property
    def description(self) -> str:
        """测试描述"""
        return self.file_info.description
    
    @property
    def test_id(self) -> str:
        """测试ID"""
        return self.file_info.test_id
    
    def __repr__(self) -> str:
        return f"FeatureReader({self.filepath.name})"