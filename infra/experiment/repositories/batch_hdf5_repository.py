"""
懒加载批量HDF5数据仓库实现

真正的懒加载机制：
1. 元数据层：只读取HDF5属性和shape信息
2. 摘要层：基于元数据计算摘要，无需加载大数组
3. 数据层：按需加载特定步骤数据，支持智能缓存
"""
import json
import h5py
import numpy as np
import pandas as pd
from typing import Optional, Dict, Any, Tuple
from pathlib import Path
from collections import OrderedDict

from .base import BaseRepository
from ..models import (
    ExperimentAttributes,
    TransferBatchData,
    TransientBatchData,
    BatchExperimentData
)

# 导入工具函数
from ..utils.hdf5_helpers import (
    load_structured_array_as_dataframe, 
    check_new_format_version,
    get_hdf5_format_version
)

########################### 日志设置 ################################
from ...logger_config import get_module_logger
logger = get_module_logger()
#####################################################################


class DataCache:
    """智能数据缓存，支持LRU淘汰策略"""
    
    def __init__(self, max_size: int = 20):
        self._cache = OrderedDict()  # 保持访问顺序
        self._max_size = max_size
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存数据，支持LRU"""
        if key in self._cache:
            # LRU: 移到最近访问位置
            value = self._cache.pop(key)
            self._cache[key] = value
            self._hits += 1
            return value
        
        self._misses += 1
        return None
    
    def put(self, key: str, value: Any):
        """添加到缓存，支持LRU淘汰"""
        if key in self._cache:
            # 更新现有数据
            self._cache.pop(key)
        elif len(self._cache) >= self._max_size:
            # LRU淘汰最旧的数据
            self._cache.popitem(last=False)
        
        self._cache[key] = value
    
    def clear(self):
        """清空缓存"""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        total_requests = self._hits + self._misses
        hit_rate = self._hits / total_requests if total_requests > 0 else 0
        return {
            'hits': self._hits,
            'misses': self._misses,
            'hit_rate': hit_rate,
            'cache_size': len(self._cache),
            'max_size': self._max_size
        }


class BatchHDF5Repository(BaseRepository):
    """懒加载批量HDF5文件数据仓库"""
    
    def __init__(self, file_path: str, cache_size: int = 20):
        super().__init__(file_path)
        if not Path(file_path).exists():
            raise FileNotFoundError(f"HDF5文件不存在: {file_path}")
        
        # 验证是否为批量格式文件
        if not self._is_batch_format():
            raise ValueError(f"文件不是批量格式HDF5文件: {file_path}")
        
        # 缓存系统
        self._metadata_cache = {}       # 元数据缓存
        self._summary_cache = {}        # 摘要缓存
        self._data_cache = DataCache(cache_size)  # 数据缓存
        self._step_info_cache = {}      # 步骤信息缓存
    
    def _is_batch_format(self) -> bool:
        """检查HDF5文件是否为批量格式"""
        format_version = get_hdf5_format_version(self.file_path)
        return check_new_format_version(format_version)
    
    # ===================
    # 抽象方法实现（批量格式不使用这些方法）
    # ===================
    
    def load_step_data(self, step_index: int):
        """批量格式不支持传统的step-by-step访问"""
        raise NotImplementedError("批量格式使用懒加载数据访问")
    
    def load_step_info(self, step_index: int):
        """批量格式不支持传统的step-by-step访问"""
        raise NotImplementedError("批量格式使用懒加载数据访问")
    
    def load_workflow(self):
        """批量格式工作流访问通过load_workflow_json()"""
        workflow_json = self.load_workflow_json()
        if not workflow_json:
            return None
        
        try:
            from ..models.workflow import Workflow, parse_workflow_json
            return parse_workflow_json(workflow_json)
        except Exception as e:
            logger.warning(f"解析工作流失败: {e}")
            return None
    
    # ===================
    # 第1层：元数据懒加载 (毫秒级)
    # ===================
    
    def get_transfer_metadata(self) -> Optional[Dict[str, Any]]:
        """
        只读取transfer组的元数据，不加载数组数据
        
        Returns:
            Dict包含: has_step_info_table, has_measurement_data, step_info_shape, measurement_shape, measurement_dtype
        """
        if 'transfer_metadata' not in self._metadata_cache:
            try:
                with h5py.File(self.file_path, 'r') as f:
                    if 'transfer' not in f:
                        self._metadata_cache['transfer_metadata'] = None
                        return None
                    
                    transfer_group = f['transfer']
                    metadata = {
                        'has_step_info_table': 'step_info_table' in transfer_group,
                        'has_measurement_data': 'measurement_data' in transfer_group,
                        'step_info_shape': None,
                        'measurement_shape': None,
                        'measurement_dtype': None
                    }
                    
                    if metadata['has_step_info_table']:
                        metadata['step_info_shape'] = transfer_group['step_info_table'].shape
                    
                    if metadata['has_measurement_data']:
                        metadata['measurement_shape'] = transfer_group['measurement_data'].shape
                        metadata['measurement_dtype'] = str(transfer_group['measurement_data'].dtype)
                    
                    self._metadata_cache['transfer_metadata'] = metadata
            
            except Exception as e:
                logger.warning(f"加载transfer元数据失败: {e}")
                self._metadata_cache['transfer_metadata'] = None
        
        return self._metadata_cache['transfer_metadata']
    
    def get_transient_metadata(self) -> Optional[Dict[str, Any]]:
        """
        只读取transient组的元数据，不加载数组数据
        
        Returns:
            Dict包含: has_step_info_table, has_measurement_data, step_info_shape, measurement_shape, measurement_dtype
        """
        if 'transient_metadata' not in self._metadata_cache:
            try:
                with h5py.File(self.file_path, 'r') as f:
                    if 'transient' not in f:
                        self._metadata_cache['transient_metadata'] = None
                        return None
                    
                    transient_group = f['transient']
                    metadata = {
                        'has_step_info_table': 'step_info_table' in transient_group,
                        'has_measurement_data': 'measurement_data' in transient_group,
                        'step_info_shape': None,
                        'measurement_shape': None,
                        'measurement_dtype': None
                    }
                    
                    if metadata['has_step_info_table']:
                        metadata['step_info_shape'] = transient_group['step_info_table'].shape
                    
                    if metadata['has_measurement_data']:
                        metadata['measurement_shape'] = transient_group['measurement_data'].shape
                        metadata['measurement_dtype'] = str(transient_group['measurement_data'].dtype)
                    
                    self._metadata_cache['transient_metadata'] = metadata
            
            except Exception as e:
                logger.warning(f"加载transient元数据失败: {e}")
                self._metadata_cache['transient_metadata'] = None
        
        return self._metadata_cache['transient_metadata']
    
    # ===================
    # 第2层：摘要懒加载 (无需加载大数组)
    # ===================
    
    def get_transfer_summary(self) -> Optional[Dict[str, Any]]:
        """基于元数据生成transfer摘要，避免加载大数组"""
        if 'transfer_summary' not in self._summary_cache:
            metadata = self.get_transfer_metadata()
            if not metadata or not metadata['has_measurement_data']:
                self._summary_cache['transfer_summary'] = None
                return None
            
            # 只从元数据计算摘要
            summary = {
                'step_count': metadata['measurement_shape'][0] if metadata['measurement_shape'] else 0,
                'measurement_data_shape': metadata['measurement_shape'],
                'data_types': ['Vg', 'Id'],
                'step_info_columns': self._get_step_info_columns_lazy('transfer')
            }
            self._summary_cache['transfer_summary'] = summary
        
        return self._summary_cache['transfer_summary']
    
    def get_transient_summary(self) -> Optional[Dict[str, Any]]:
        """基于元数据生成transient摘要，避免加载大数组"""
        if 'transient_summary' not in self._summary_cache:
            metadata = self.get_transient_metadata()
            if not metadata or not metadata['has_measurement_data']:
                self._summary_cache['transient_summary'] = None
                return None
            
            # 只从元数据计算摘要
            summary = {
                'step_count': metadata['step_info_shape'][0] if metadata['step_info_shape'] else 0,
                'total_data_points': metadata['measurement_shape'][1] if metadata['measurement_shape'] else 0,
                'measurement_data_shape': metadata['measurement_shape'],
                'step_info_columns': self._get_step_info_columns_lazy('transient')
            }
            self._summary_cache['transient_summary'] = summary
        
        return self._summary_cache['transient_summary']
    
    def _get_step_info_columns_lazy(self, data_type: str) -> Optional[list]:
        """懒加载获取step_info_table的列名，无需加载完整数据"""
        cache_key = f"{data_type}_step_info_columns"
        
        if cache_key not in self._metadata_cache:
            try:
                with h5py.File(self.file_path, 'r') as f:
                    if data_type not in f or 'step_info_table' not in f[data_type]:
                        self._metadata_cache[cache_key] = None
                        return None
                    
                    step_info_dataset = f[data_type]['step_info_table']
                    # 获取结构化数组的字段名（列名）
                    if hasattr(step_info_dataset.dtype, 'names') and step_info_dataset.dtype.names:
                        columns = list(step_info_dataset.dtype.names)
                    else:
                        columns = None
                    
                    self._metadata_cache[cache_key] = columns
            
            except Exception as e:
                logger.warning(f"获取{data_type}列名失败: {e}")
                self._metadata_cache[cache_key] = None
        
        return self._metadata_cache[cache_key]
    
    # ===================
    # 第3层：按需数据懒加载
    # ===================
    
    def get_transfer_step_data(self, step_index: int) -> Optional[Dict[str, np.ndarray]]:
        """
        只加载指定transfer步骤的数据切片，支持缓存
        
        Args:
            step_index: 步骤索引 (0-based)
            
        Returns:
            包含'Vg'和'Id'数组的字典，如果索引无效则返回None
        """
        cache_key = f"transfer_step_{step_index}"
        
        # 检查缓存
        cached_data = self._data_cache.get(cache_key)
        if cached_data is not None:
            return cached_data
        
        # 验证索引有效性
        metadata = self.get_transfer_metadata()
        if (not metadata or 
            not metadata['has_measurement_data'] or
            step_index < 0 or
            step_index >= metadata['measurement_shape'][0]):
            return None
        
        # 从HDF5加载特定步骤数据
        try:
            with h5py.File(self.file_path, 'r') as f:
                transfer_group = f['transfer']
                measurement_dataset = transfer_group['measurement_data']
                
                # 只读取特定步骤的数据 [step_index, :, :]
                step_data = measurement_dataset[step_index, :, :]
                
                # 移除NaN值（用于处理不等长数据的填充）
                vg_data = step_data[0, :]  # 第0维是Vg
                id_data = step_data[1, :]  # 第1维是Id
                
                # 找到有效数据的长度（去除NaN填充）
                vg_valid = ~np.isnan(vg_data)
                id_valid = ~np.isnan(id_data)
                valid_mask = vg_valid & id_valid
                
                if not np.any(valid_mask):
                    return None
                
                result = {
                    'Vg': vg_data[valid_mask],
                    'Id': id_data[valid_mask]
                }
                
                # 缓存结果
                self._data_cache.put(cache_key, result)
                return result
        
        except Exception as e:
            logger.warning(f"加载transfer步骤{step_index}数据失败: {e}")
            return None
    
    def get_transient_step_data(self, step_index: int) -> Optional[Dict[str, np.ndarray]]:
        """
        只加载指定transient步骤的数据切片，支持缓存
        
        Args:
            step_index: 步骤索引 (0-based)
            
        Returns:
            包含'continuous_time'、'original_time'和'drain_current'数组的字典
        """
        cache_key = f"transient_step_{step_index}"
        
        # 检查缓存
        cached_data = self._data_cache.get(cache_key)
        if cached_data is not None:
            return cached_data
        
        # 验证索引有效性和获取步骤信息
        step_info_table = self.get_transient_step_info_table()
        if (step_info_table is None or
            step_index < 0 or 
            step_index >= len(step_info_table)):
            return None
        
        metadata = self.get_transient_metadata()
        if not metadata or not metadata['has_measurement_data']:
            return None
        
        # 从步骤信息表中获取该步骤的数据范围
        try:
            step_info = step_info_table.iloc[step_index]
            
            # 计算数据范围（假设有start_index和end_index字段）
            if 'start_data_index' in step_info and 'end_data_index' in step_info:
                start_idx = int(step_info['start_data_index'])
                end_idx = int(step_info['end_data_index'])
            else:
                # 回退到均匀分布计算
                total_points = metadata['measurement_shape'][1]
                step_count = len(step_info_table)
                points_per_step = total_points // step_count
                
                start_idx = step_index * points_per_step
                end_idx = start_idx + points_per_step
                
                # 对于最后一个步骤，包含所有剩余数据点
                if step_index == step_count - 1:
                    end_idx = total_points
            
            # 从HDF5加载特定范围的数据
            with h5py.File(self.file_path, 'r') as f:
                transient_group = f['transient']
                measurement_dataset = transient_group['measurement_data']
                
                # 读取数据范围 [:, start_idx:end_idx]
                data_slice = measurement_dataset[:, start_idx:end_idx]
                
                result = {
                    'continuous_time': data_slice[0, :],      # 连续时间序列
                    'original_time': data_slice[1, :],        # 原始时间序列
                    'drain_current': data_slice[2, :]         # 电流序列
                }
                
                # 缓存结果
                self._data_cache.put(cache_key, result)
                return result
        
        except Exception as e:
            logger.warning(f"加载transient步骤{step_index}数据失败: {e}")
            return None
    
    # ===================
    # 步骤信息懒加载
    # ===================
    
    def get_transfer_step_info_table(self) -> Optional[pd.DataFrame]:
        """懒加载transfer步骤信息表格"""
        if 'transfer_step_info_table' not in self._step_info_cache:
            metadata = self.get_transfer_metadata()
            if not metadata or not metadata['has_step_info_table']:
                self._step_info_cache['transfer_step_info_table'] = None
                return None
            
            try:
                with h5py.File(self.file_path, 'r') as f:
                    transfer_group = f['transfer']
                    step_info_table = load_structured_array_as_dataframe(transfer_group['step_info_table'])
                    self._step_info_cache['transfer_step_info_table'] = step_info_table
            
            except Exception as e:
                logger.warning(f"加载transfer步骤信息表格失败: {e}")
                self._step_info_cache['transfer_step_info_table'] = None
        
        return self._step_info_cache['transfer_step_info_table']
    
    def get_transient_step_info_table(self) -> Optional[pd.DataFrame]:
        """懒加载transient步骤信息表格"""
        if 'transient_step_info_table' not in self._step_info_cache:
            metadata = self.get_transient_metadata()
            if not metadata or not metadata['has_step_info_table']:
                self._step_info_cache['transient_step_info_table'] = None
                return None
            
            try:
                with h5py.File(self.file_path, 'r') as f:
                    transient_group = f['transient']
                    step_info_table = load_structured_array_as_dataframe(transient_group['step_info_table'])
                    self._step_info_cache['transient_step_info_table'] = step_info_table
            
            except Exception as e:
                logger.warning(f"加载transient步骤信息表格失败: {e}")
                self._step_info_cache['transient_step_info_table'] = None
        
        return self._step_info_cache['transient_step_info_table']
    
    # ===================
    # 兼容性方法（支持原有API）
    # ===================
    
    def load_attributes(self) -> ExperimentAttributes:
        """从HDF5根级别加载实验属性"""
        attrs_dict = {}
        
        try:
            with h5py.File(self.file_path, 'r') as f:
                # 加载所有根级别属性
                for attr_name, attr_value in f.attrs.items():
                    if attr_name == 'format_version':
                        continue  # 跳过格式版本属性
                    
                    # 转换numpy类型为Python类型
                    if isinstance(attr_value, bytes):
                        attrs_dict[attr_name] = attr_value.decode('utf-8')
                    elif hasattr(attr_value, 'item'):
                        value = attr_value.item()
                        if isinstance(value, bytes):
                            attrs_dict[attr_name] = value.decode('utf-8')
                        else:
                            attrs_dict[attr_name] = value
                    else:
                        attrs_dict[attr_name] = attr_value
        
        except Exception as e:
            raise RuntimeError(f"加载属性失败 {self.file_path}: {e}")
        
        return ExperimentAttributes(**attrs_dict)
    
    def load_batch_data(self) -> 'LazyBatchExperimentData':
        """
        懒加载批量格式的实验数据 - 不再预加载所有数据
        
        Returns:
            包含懒加载Transfer和Transient数据的LazyBatchExperimentData
        """
        try:
            # 创建懒加载的数据对象，而不是预加载数据
            transfer_data = None
            if self.get_transfer_metadata():
                transfer_data = LazyTransferBatchData(self)
            
            transient_data = None
            if self.get_transient_metadata():
                transient_data = LazyTransientBatchData(self)
            
            return LazyBatchExperimentData(
                transfer_data=transfer_data,
                transient_data=transient_data
            )
        except Exception as e:
            raise RuntimeError(f"创建懒加载批量格式数据对象失败: {e}")
    
    def has_workflow(self) -> bool:
        """检查实验是否有工作流配置"""
        try:
            with h5py.File(self.file_path, 'r') as f:
                return 'raw' in f and 'workflow' in f['raw']
        except Exception:
            return False
    
    def load_workflow_json(self) -> Optional[Dict[str, Any]]:
        """加载工作流JSON数据"""
        try:
            with h5py.File(self.file_path, 'r') as f:
                if 'raw' not in f or 'workflow' not in f['raw']:
                    return None
                
                workflow_dataset = f['raw']['workflow']
                workflow_str = workflow_dataset[()]
                
                if isinstance(workflow_str, bytes):
                    workflow_str = workflow_str.decode('utf-8')
                elif hasattr(workflow_str, 'item'):
                    workflow_str = workflow_str.item()
                    if isinstance(workflow_str, bytes):
                        workflow_str = workflow_str.decode('utf-8')
                
                return json.loads(workflow_str)
                
        except Exception as e:
            logger.warning(f"加载工作流JSON失败: {e}")
            return None
    
    # ===================
    # 缓存管理
    # ===================
    
    def clear_cache(self):
        """清空所有缓存"""
        self._metadata_cache.clear()
        self._summary_cache.clear()
        self._data_cache.clear()
        self._step_info_cache.clear()
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        return {
            'data_cache': self._data_cache.get_stats(),
            'metadata_cache_size': len(self._metadata_cache),
            'summary_cache_size': len(self._summary_cache),
            'step_info_cache_size': len(self._step_info_cache)
        }


# ===================
# 懒加载数据模型 (独立类，不继承Pydantic模型)
# ===================

class LazyTransferBatchData:
    """懒加载的Transfer批量数据 - 独立实现，避免Pydantic继承问题"""
    
    def __init__(self, repository: BatchHDF5Repository):
        self._repository = repository
        self._step_info_table = None  # 延迟加载
    
    @property
    def step_info_table(self) -> Optional[pd.DataFrame]:
        """懒加载step_info_table"""
        if self._step_info_table is None:
            self._step_info_table = self._repository.get_transfer_step_info_table()
        return self._step_info_table
    
    @property  
    def measurement_data(self) -> Optional[np.ndarray]:
        """measurement_data不再预加载，返回None以避免意外的全量加载"""
        return None
    
    def get_step_measurement_data(self, step_index: int) -> Optional[Dict[str, np.ndarray]]:
        """只加载特定步骤的数据，而非整个3D数组"""
        return self._repository.get_transfer_step_data(step_index)
        
    def get_data_summary(self) -> Dict[str, Any]:
        """使用元数据生成摘要，无需加载数据"""
        return self._repository.get_transfer_summary() or {}
    
    def get_step_count(self) -> int:
        """获取步骤数量"""
        summary = self._repository.get_transfer_summary()
        return summary['step_count'] if summary else 0
    
    def get_all_measurement_data(self) -> Optional[Dict[str, Any]]:
        """
        警告：这个方法会加载所有transfer步骤的3D数组数据
        
        只有在确实需要所有数据时才调用此方法
        
        Returns:
            包含measurement_data(3D数组)和data_info的字典
        """
        logger.warning("正在加载所有transfer数据，这可能会消耗大量内存")
        
        try:
            with h5py.File(self._repository.file_path, 'r') as f:
                if 'transfer' not in f or 'measurement_data' not in f['transfer']:
                    return None
                
                # 加载完整的3D数组
                measurement_data = np.array(f['transfer']['measurement_data'][:])
                
                summary = self._repository.get_transfer_summary()
                if not summary:
                    return None
                
                return {
                    'measurement_data': measurement_data,  # 实际的3D数组
                    'data_info': {
                        'shape': measurement_data.shape,
                        'step_count': summary['step_count'],
                        'data_types': summary['data_types'],
                        'description': 'Shape: [steps, data_types, data_points]. 3D array with all transfer data.'
                    }
                }
        except Exception as e:
            logger.warning(f"加载所有transfer数据失败: {e}")
            return None
    
    def get_step_info_by_index(self, step_index: int) -> Optional[Dict[str, Any]]:
        """根据相对步骤索引获取步骤信息"""
        table = self.step_info_table
        if table is None or step_index < 0 or step_index >= len(table):
            return None
        return table.iloc[step_index].to_dict()


class LazyTransientBatchData:
    """懒加载的Transient批量数据 - 独立实现，避免Pydantic继承问题"""
    
    def __init__(self, repository: BatchHDF5Repository):
        self._repository = repository
        self._step_info_table = None  # 延迟加载
    
    @property
    def step_info_table(self) -> Optional[pd.DataFrame]:
        """懒加载step_info_table"""
        if self._step_info_table is None:
            self._step_info_table = self._repository.get_transient_step_info_table()
        return self._step_info_table
    
    @property
    def measurement_data(self) -> Optional[np.ndarray]:
        """measurement_data不再预加载，返回None以避免意外的全量加载"""
        return None
    
    def get_step_measurement_data(self, step_index: int) -> Optional[Dict[str, np.ndarray]]:
        """只加载特定步骤的数据"""
        return self._repository.get_transient_step_data(step_index)
    
    def get_data_summary(self) -> Dict[str, Any]:
        """使用元数据生成摘要，无需加载数据"""
        return self._repository.get_transient_summary() or {}
    
    def get_step_count(self) -> int:
        """获取步骤数量"""
        summary = self._repository.get_transient_summary()
        return summary['step_count'] if summary else 0
    
    def get_total_data_points(self) -> int:
        """获取总数据点数"""
        summary = self._repository.get_transient_summary()
        return summary['total_data_points'] if summary else 0
    
    def get_all_measurement_data(self) -> Optional[Dict[str, np.ndarray]]:
        """
        警告：这个方法会加载所有拼接后的transient数据
        
        只有在确实需要所有数据时才调用此方法
        """
        logger.warning("正在加载所有transient数据，这可能会消耗大量内存")
        
        try:
            with h5py.File(self._repository.file_path, 'r') as f:
                if 'transient' not in f or 'measurement_data' not in f['transient']:
                    return None
                
                measurement_data = np.array(f['transient']['measurement_data'][:])
                return {
                    'continuous_time': measurement_data[0, :],      # 连续时间序列
                    'original_time': measurement_data[1, :],        # 原始时间序列
                    'drain_current': measurement_data[2, :]         # 电流序列
                }
        except Exception as e:
            logger.warning(f"加载所有transient数据失败: {e}")
            return None
    
    def get_step_info_by_index(self, step_index: int) -> Optional[Dict[str, Any]]:
        """根据相对步骤索引获取步骤信息"""
        table = self.step_info_table
        if table is None or step_index < 0 or step_index >= len(table):
            return None
        return table.iloc[step_index].to_dict()


class LazyBatchExperimentData:
    """
    懒加载批量实验数据模型 - 独立实现
    
    包含transfer和transient的懒加载数据
    """
    
    def __init__(self, transfer_data: Optional[LazyTransferBatchData] = None, 
                 transient_data: Optional[LazyTransientBatchData] = None):
        self.transfer_data = transfer_data
        self.transient_data = transient_data
    
    def has_transfer_data(self) -> bool:
        """检查是否有transfer数据"""
        return self.transfer_data is not None
    
    def has_transient_data(self) -> bool:
        """检查是否有transient数据"""
        return self.transient_data is not None
    
    def get_transfer_step_count(self) -> int:
        """获取transfer步骤数"""
        return self.transfer_data.get_step_count() if self.transfer_data else 0
    
    def get_transient_step_count(self) -> int:
        """获取transient步骤数"""
        return self.transient_data.get_step_count() if self.transient_data else 0
    
    def get_total_step_count(self) -> int:
        """获取总步骤数"""
        return self.get_transfer_step_count() + self.get_transient_step_count()
    
    def get_data_summary(self) -> Dict[str, Any]:
        """获取数据摘要"""
        summary = {
            'has_transfer_data': self.has_transfer_data(),
            'has_transient_data': self.has_transient_data(),
            'total_step_count': self.get_total_step_count()
        }
        
        if self.transfer_data:
            summary['transfer_summary'] = self.transfer_data.get_data_summary()
        
        if self.transient_data:
            summary['transient_summary'] = self.transient_data.get_data_summary()
        
        return summary