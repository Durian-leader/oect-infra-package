"""
特征文件创建器

负责创建和初始化特征文件的基本结构，包括目录组织、属性设置、注册表初始化等
"""
import h5py
import json
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any, Union

########################### 日志设置 ################################
from ...logger_config import get_module_logger
logger = get_module_logger()
#####################################################################

from ..models.feature_data import FeatureData
from ..models.feature_registry import FeatureRegistry, FeatureInfo


class FeatureFileCreator:
    """
    特征文件创建器
    
    负责创建符合架构设计的特征HDF5文件，包括：
    - 文件基本结构和属性设置
    - Transfer和Transient数据组的初始化 
    - 列式仓库和版本化存储区域的创建
    - 特征注册表的初始化
    """
    
    def __init__(self):
        """初始化特征文件创建器"""
        pass
    
    def create_feature_file(self,
                           filepath: str,
                           chip_id: str,
                           device_id: str, 
                           description: str,
                           test_id: str = None,
                           built_with: str = None,
                           feature_tool_hash: str = None,
                           **kwargs) -> str:
        """
        创建新的特征文件
        
        Args:
            filepath: 特征文件路径
            chip_id: 芯片ID
            device_id: 设备编号  
            description: 测试描述
            test_id: 测试标识符，如果未提供则自动生成
            built_with: 特征提取工具版本
            feature_tool_hash: 特征提取代码版本hash
            **kwargs: 其他属性
            
        Returns:
            创建的文件路径
            
        Examples:
            >>> creator = FeatureFileCreator()
            >>> filepath = creator.create_feature_file(
            ...     "/data/features/test.h5",
            ...     chip_id="#20250804008",
            ...     device_id="3", 
            ...     description="稳定性测试",
            ...     built_with="features v1.0.0"
            ... )
        """
        # 确保目录存在
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        
        # 如果test_id未提供，则从文件名解析
        if test_id is None:
            try:
                feature_data = FeatureData.parse_from_filename(Path(filepath).name)
                test_id = feature_data.test_id
            except ValueError:
                # 如果解析失败，生成默认的test_id
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                import hashlib
                hash_str = hashlib.md5(f"{chip_id}{device_id}{description}{timestamp}".encode()).hexdigest()[:8]
                test_id = f"feat_{timestamp}_{hash_str}"
        
        # 创建HDF5文件
        with h5py.File(filepath, 'w') as f:
            # 设置根级别属性
            self._set_root_attributes(
                f, chip_id, device_id, description, test_id,
                built_with, feature_tool_hash, **kwargs
            )
            
            # 创建Transfer数据结构
            self._create_transfer_structure(f)
            
            # 创建Transient数据结构
            self._create_transient_structure(f)
        
        return filepath
    
    def create_from_raw_file(self,
                            raw_filepath: str,
                            output_dir: str = None,
                            built_with: str = None,
                            feature_tool_hash: str = None) -> str:
        """
        根据原始数据文件创建对应的特征文件
        
        Args:
            raw_filepath: 原始数据文件路径
            output_dir: 输出目录，默认为原始文件所在目录的features子目录
            built_with: 特征提取工具版本
            feature_tool_hash: 特征提取代码版本hash
            
        Returns:
            创建的特征文件路径
            
        Examples:
            >>> creator = FeatureFileCreator()
            >>> raw_file = "/data/raw/#20250804008-3-稳定性测试-test_20250815134211_3fa6110a.h5"
            >>> feature_file = creator.create_from_raw_file(raw_file)
        """
        raw_path = Path(raw_filepath)
        
        # 解析原始文件名获取信息
        try:
            # 假设原始文件名格式：{chip_id}-{device_id}-{description}-test_{timestamp}_{hash}.h5
            basename = raw_path.stem
            
            import re
            pattern = r'^(.+)-(\d+)-(.+)-test_([a-f0-9]+_[a-f0-9]+)$'
            match = re.match(pattern, basename)
            
            if not match:
                raise ValueError(f"Invalid raw filename format: {raw_path.name}")
            
            chip_id, device_id, description, test_suffix = match.groups()
            
        except Exception as e:
            raise ValueError(f"Failed to parse raw filename {raw_path.name}: {e}")
        
        # 确定输出目录
        if output_dir is None:
            output_dir = raw_path.parent / "features"
        else:
            output_dir = Path(output_dir)
        
        # 生成特征文件名
        feature_filename = f"{chip_id}-{device_id}-{description}-feat_{test_suffix}.h5"
        feature_filepath = output_dir / feature_filename
        
        # 创建特征文件
        return self.create_feature_file(
            str(feature_filepath),
            chip_id=chip_id,
            device_id=device_id,
            description=description,
            test_id=f"feat_{test_suffix}",
            built_with=built_with,
            feature_tool_hash=feature_tool_hash
        )
    
    def _set_root_attributes(self,
                            hdf5_file: h5py.File,
                            chip_id: str,
                            device_id: str,
                            description: str, 
                            test_id: str,
                            built_with: str = None,
                            feature_tool_hash: str = None,
                            **kwargs) -> None:
        """
        设置根级别属性
        
        Args:
            hdf5_file: HDF5文件对象
            chip_id: 芯片ID
            device_id: 设备编号
            description: 测试描述
            test_id: 测试标识符
            built_with: 特征提取工具版本
            feature_tool_hash: 特征提取代码版本hash
            **kwargs: 其他属性
        """
        # 基本标识信息
        hdf5_file.attrs['chip_id'] = chip_id
        hdf5_file.attrs['device_id'] = device_id
        hdf5_file.attrs['description'] = description
        hdf5_file.attrs['test_id'] = test_id
        
        # 特征文件特有属性
        hdf5_file.attrs['file_type'] = 'feature'
        hdf5_file.attrs['format_version'] = 'feature_v1.0'
        hdf5_file.attrs['created_at'] = datetime.now().isoformat()
        
        if built_with:
            hdf5_file.attrs['built_with'] = built_with
        if feature_tool_hash:
            hdf5_file.attrs['feature_tool_hash'] = feature_tool_hash
        
        # 数据组织信息
        hdf5_file.attrs['has_transfer_features'] = False
        hdf5_file.attrs['has_transient_features'] = False
        
        # 其他属性
        for key, value in kwargs.items():
            if isinstance(value, (str, int, float, bool)):
                hdf5_file.attrs[key] = value
            elif isinstance(value, (list, tuple)):
                hdf5_file.attrs[key] = list(value)
    
    def _create_transfer_structure(self, hdf5_file: h5py.File) -> None:
        """
        创建Transfer数据结构
        
        Args:
            hdf5_file: HDF5文件对象
        """
        transfer_group = hdf5_file.create_group('transfer')
        
        # 创建列式仓库结构
        columns_group = transfer_group.create_group('columns')
        buckets_group = columns_group.create_group('buckets')
        
        # 创建注册表结构
        registry_group = columns_group.create_group('_registry')
        by_name_group = registry_group.create_group('by_name')
        
        # 初始化注册表（使用create_final_features.py的格式）
        registry_group.attrs['registry_version'] = '1.0'
        registry_group.attrs['created_at'] = datetime.now().isoformat()
        registry_group.attrs['data_type'] = 'transfer'
        registry_group.attrs['total_features'] = 0
        registry_group.attrs['active_features'] = 0
        registry_group.attrs['versioned_features'] = 0
        
        # 创建空的结构化数组注册表（HDFView兼容格式）
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
        
        # 创建空的结构化数组
        empty_array = np.array([], dtype=dtype)
        registry_group.create_dataset('table', data=empty_array, compression='gzip')
        
        # 创建版本化存储区域  
        versions_group = transfer_group.create_group('versions')
    
    def _create_transient_structure(self, hdf5_file: h5py.File) -> None:
        """
        创建Transient数据结构
        
        Args:
            hdf5_file: HDF5文件对象  
        """
        transient_group = hdf5_file.create_group('transient')
        
        # 创建列式仓库结构
        columns_group = transient_group.create_group('columns')
        buckets_group = columns_group.create_group('buckets')
        
        # 创建注册表结构
        registry_group = columns_group.create_group('_registry')
        by_name_group = registry_group.create_group('by_name')
        
        # 初始化注册表（使用create_final_features.py的格式）
        registry_group.attrs['registry_version'] = '1.0'
        registry_group.attrs['created_at'] = datetime.now().isoformat()
        registry_group.attrs['data_type'] = 'transient'
        registry_group.attrs['total_features'] = 0
        registry_group.attrs['active_features'] = 0
        registry_group.attrs['versioned_features'] = 0
        
        # 创建空的结构化数组注册表（HDFView兼容格式）
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
        
        # 创建空的结构化数组
        empty_array = np.array([], dtype=dtype)
        registry_group.create_dataset('table', data=empty_array, compression='gzip')
        
        # 创建版本化存储区域
        versions_group = transient_group.create_group('versions')
    
    def initialize_buckets(self,
                          filepath: str,
                          data_type: str,
                          bucket_names: List[str]) -> None:
        """
        初始化数据桶
        
        Args:
            filepath: 特征文件路径
            data_type: 数据类型，'transfer' 或 'transient'
            bucket_names: 桶名称列表
            
        Examples:
            >>> creator = FeatureFileCreator()
            >>> creator.initialize_buckets(
            ...     "/data/features/test.h5",
            ...     "transfer", 
            ...     ["bk_00", "bk_01", "bk_02"]
            ... )
        """
        with h5py.File(filepath, 'a') as f:
            buckets_path = f"{data_type}/columns/buckets"
            
            if buckets_path not in f:
                raise ValueError(f"Buckets path {buckets_path} not found in file")
            
            buckets_group = f[buckets_path]
            
            for bucket_name in bucket_names:
                if bucket_name not in buckets_group:
                    buckets_group.create_group(bucket_name)
    
    def update_file_attributes(self,
                             filepath: str, 
                             **attributes) -> None:
        """
        更新文件属性
        
        Args:
            filepath: 特征文件路径
            **attributes: 要更新的属性
        """
        with h5py.File(filepath, 'a') as f:
            for key, value in attributes.items():
                if isinstance(value, (str, int, float, bool)):
                    f.attrs[key] = value
                elif isinstance(value, (list, tuple)):
                    f.attrs[key] = list(value)
                elif value is None:
                    # 删除属性
                    if key in f.attrs:
                        del f.attrs[key]
    
    @staticmethod
    def generate_feature_filename(chip_id: str,
                                 device_id: str,
                                 description: str,
                                 timestamp_str: str = None,
                                 hash_str: str = None) -> str:
        """
        生成标准的特征文件名
        
        Args:
            chip_id: 芯片ID
            device_id: 设备编号
            description: 测试描述  
            timestamp_str: 时间戳字符串，默认使用当前时间
            hash_str: 哈希字符串，默认自动生成
            
        Returns:
            特征文件名
        """
        if timestamp_str is None:
            timestamp_str = datetime.now().strftime("%Y%m%d%H%M%S")
        
        if hash_str is None:
            import hashlib
            hash_str = hashlib.md5(f"{chip_id}{device_id}{description}{timestamp_str}".encode()).hexdigest()[:8]
        
        return f"{chip_id}-{device_id}-{description}-feat_{timestamp_str}_{hash_str}.h5"
    
    @staticmethod
    def parse_raw_filename_to_feature(raw_filename: str) -> str:
        """
        将原始数据文件名转换为对应的特征文件名
        
        Args:
            raw_filename: 原始数据文件名
            
        Returns:
            对应的特征文件名
            
        Examples:
            >>> feature_name = FeatureFileCreator.parse_raw_filename_to_feature(
            ...     "#20250804008-3-稳定性测试-test_20250815134211_3fa6110a.h5"
            ... )
            >>> print(feature_name)  # "#20250804008-3-稳定性测试-feat_20250815134211_3fa6110a.h5"
        """
        from pathlib import Path
        
        basename = Path(raw_filename).stem
        
        # 检查是否为test_格式
        if "-test_" in basename:
            feature_basename = basename.replace("-test_", "-feat_", 1)
            return f"{feature_basename}.h5"
        else:
            raise ValueError(f"Invalid raw filename format: {raw_filename}")
    
    def validate_file_structure(self, filepath: str) -> Dict[str, Any]:
        """
        验证特征文件结构的完整性
        
        Args:
            filepath: 特征文件路径
            
        Returns:
            验证结果字典
        """
        results = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'structure_info': {}
        }
        
        try:
            with h5py.File(filepath, 'r') as f:
                # 检查根属性
                required_attrs = ['chip_id', 'device_id', 'description', 'test_id', 'file_type']
                for attr in required_attrs:
                    if attr not in f.attrs:
                        results['errors'].append(f"Missing required attribute: {attr}")
                        results['valid'] = False
                
                # 检查数据组结构
                for data_type in ['transfer', 'transient']:
                    if data_type in f:
                        group_info = self._validate_data_group_structure(f[data_type], data_type)
                        results['structure_info'][data_type] = group_info
                        if not group_info['valid']:
                            results['valid'] = False
                            results['errors'].extend(group_info['errors'])
                    else:
                        results['warnings'].append(f"Missing {data_type} group")
        
        except Exception as e:
            results['valid'] = False
            results['errors'].append(f"Failed to read file: {e}")
        
        return results
    
    def _validate_data_group_structure(self, group: h5py.Group, data_type: str) -> Dict[str, Any]:
        """验证数据组结构"""
        info = {
            'valid': True,
            'errors': [],
            'has_columns': False,
            'has_registry': False,
            'bucket_count': 0,
            'version_count': 0
        }
        
        # 检查columns结构
        if 'columns' in group:
            info['has_columns'] = True
            columns_group = group['columns']
            
            # 检查buckets
            if 'buckets' in columns_group:
                info['bucket_count'] = len(list(columns_group['buckets'].keys()))
            
            # 检查注册表
            if '_registry' in columns_group and 'table' in columns_group['_registry']:
                info['has_registry'] = True
            else:
                info['errors'].append(f"Missing registry in {data_type}/columns")
                info['valid'] = False
        else:
            info['errors'].append(f"Missing columns structure in {data_type}")
            info['valid'] = False
        
        # 统计版本数量
        version_keys = [k for k in group.keys() if k.startswith('v') and k[1:].isdigit()]
        info['version_count'] = len(version_keys)
        
        return info