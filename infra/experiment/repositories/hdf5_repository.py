"""
HDF5数据仓库实现

处理HDF5文件的具体数据访问操作
"""
import json
import h5py
import numpy as np
from typing import Optional, Dict, Any, List, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from .base import BaseRepository
from ..models import (
    ExperimentAttributes,
    Workflow,
    StepInfo,
    TransferData,
    TransientData,
    TransferStepConfig,
    TransientStepConfig,
    OutputStepConfig,
    LoopConfig,
    WorkflowInfo,
    IterationInfo,
    TransferBatchData,
    TransientBatchData,
    BatchExperimentData
)
from ..utils import (
    decode_hdf5_attr_value,
    safe_decode_attr,
    extract_group_attributes,
    build_step_group_name
)

########################### 日志设置 ################################
from ...logger_config import get_module_logger
logger = get_module_logger()
#####################################################################


class HDF5Repository(BaseRepository):
    """HDF5文件数据仓库"""
    
    def __init__(self, file_path: str):
        super().__init__(file_path)
        self._workflow_cache: Optional[Workflow] = None
    
    def load_attributes(self) -> ExperimentAttributes:
        """从HDF5根级别加载实验属性"""
        attrs_dict = {}
        
        try:
            with h5py.File(self.file_path, 'r') as f:
                # 加载所有根级别属性
                for attr_name, attr_value in f.attrs.items():
                    # 转换numpy类型为Python类型以兼容pydantic
                    if hasattr(attr_value, 'item'):
                        # 处理numpy标量
                        attrs_dict[attr_name] = attr_value.item()
                    elif isinstance(attr_value, bytes):
                        # 处理字节字符串
                        attrs_dict[attr_name] = attr_value.decode('utf-8')
                    else:
                        attrs_dict[attr_name] = attr_value
        
        except Exception as e:
            raise RuntimeError(f"加载属性失败 {self.file_path}: {e}")
        
        return ExperimentAttributes(**attrs_dict)
    
    def load_workflow(self) -> Optional[Workflow]:
        """从HDF5 raw/workflow数据集加载工作流配置"""
        # 返回缓存结果
        if self._workflow_cache is not None:
            return self._workflow_cache
        
        try:
            with h5py.File(self.file_path, 'r') as f:
                # 检查raw组是否存在
                if 'raw' not in f:
                    self._workflow_cache = None
                    return None
                
                raw_group = f['raw']
                
                # 检查workflow数据集是否存在
                if 'workflow' not in raw_group:
                    self._workflow_cache = None
                    return None
                
                # 读取workflow数据集
                workflow_dataset = raw_group['workflow']
                workflow_json_str = workflow_dataset[()]
                
                # 处理不同的数据格式
                if isinstance(workflow_json_str, bytes):
                    workflow_json_str = workflow_json_str.decode('utf-8')
                elif hasattr(workflow_json_str, 'item'):
                    workflow_json_str = workflow_json_str.item()
                    if isinstance(workflow_json_str, bytes):
                        workflow_json_str = workflow_json_str.decode('utf-8')
                
                # 解析JSON字符串
                workflow_list = json.loads(workflow_json_str)
                
                # 使用相应的Pydantic模型解析每个步骤
                parsed_steps = []
                for step_dict in workflow_list:
                    step_type = step_dict.get('type')
                    if step_type == 'transfer':
                        step = TransferStepConfig(**step_dict)
                    elif step_type == 'transient':
                        step = TransientStepConfig(**step_dict)
                    elif step_type == 'output':
                        step = OutputStepConfig(**step_dict)
                    elif step_type == 'loop':
                        step = LoopConfig(**step_dict)
                    else:
                        logger.warning(f"未知工作流步骤类型: {step_type}")
                        continue
                    parsed_steps.append(step)
                
                # 缓存并返回解析的工作流
                self._workflow_cache = parsed_steps
                return self._workflow_cache
                
        except Exception as e:
            logger.warning(f"加载工作流失败 {self.file_path}: {e}")
            self._workflow_cache = None
            return None
    
    def has_workflow(self) -> bool:
        """检查实验是否有工作流配置"""
        try:
            with h5py.File(self.file_path, 'r') as f:
                return 'raw' in f and 'workflow' in f['raw']
        except Exception:
            return False
    
    def clear_workflow_cache(self):
        """清除工作流缓存，强制重新加载"""
        self._workflow_cache = None
    
    def load_step_info(self, step_index: int) -> Optional[StepInfo]:
        """加载步骤信息"""
        if step_index < 1:
            raise ValueError("步骤索引必须从1开始")
        
        try:
            with h5py.File(self.file_path, 'r') as f:
                return self._load_step_info_from_file(f, step_index)
        except Exception as e:
            logger.error(f"加载步骤 {step_index} 信息失败: {e}")
            return None
    
    def load_step_data(self, step_index: int, step_type: str) -> Optional[Union[TransferData, TransientData]]:
        """加载步骤测量数据"""
        if step_index < 1:
            raise ValueError("步骤索引必须从1开始")
        
        try:
            with h5py.File(self.file_path, 'r') as f:
                return self._load_step_data_from_file(f, step_index, step_type)
        except Exception as e:
            logger.error(f"加载步骤 {step_index} 数据失败: {e}")
            return None
    
    
    def _load_step_info_from_file(self, h5_file, step_index: int) -> Optional[StepInfo]:
        """从已打开的HDF5文件加载步骤信息"""
        step_group_name = build_step_group_name(step_index)
        
        if step_group_name not in h5_file:
            return None
        
        step_group = h5_file[step_group_name]
        
        # 提取步骤信息
        step_data = {}
        
        # 获取步骤类型
        step_type = None
        if 'type' in step_group.attrs:
            step_type = decode_hdf5_attr_value(step_group.attrs['type'])
        elif 'reason' in step_group.attrs:
            step_type = decode_hdf5_attr_value(step_group.attrs['reason'])
        
        # 只处理transfer和transient步骤
        if step_type not in ['transfer', 'transient']:
            return None
        
        step_data['type'] = step_type
        
        # 提取基本属性
        attr_mappings = {
            'start_time': 'start_time',
            'end_time': 'end_time',
            'reason': 'reason',
            'data_file': 'data_file'
        }
        
        for attr_name, field_name in attr_mappings.items():
            if attr_name in step_group.attrs:
                value = decode_hdf5_attr_value(step_group.attrs[attr_name])
                # 处理'null'字符串值
                if isinstance(value, str) and value.lower() == 'null':
                    value = None
                step_data[field_name] = value
        
        # 从params子组提取参数
        params = {}
        if 'params' in step_group:
            params_group = step_group['params']
            if hasattr(params_group, 'attrs'):
                params = extract_group_attributes(params_group)
        
        step_data['params'] = params
        
        # 提取工作流信息
        workflow_info = self._extract_workflow_info(step_group)
        step_data['workflow_info'] = workflow_info
        
        # 创建并返回StepInfo
        return StepInfo(**step_data)
    
    def _load_step_data_from_file(self, h5_file, step_index: int, step_type: str) -> Optional[Union[TransferData, TransientData]]:
        """从已打开的HDF5文件加载步骤数据"""
        step_group_name = build_step_group_name(step_index)
        
        if step_group_name not in h5_file:
            return None
        
        step_group = h5_file[step_group_name]
        
        # 提取测量数据
        data_dict = {}
        
        # 通用列映射
        column_mappings = {
            'timestamp': ['Time', 'timestamp', 'time', 't'],
            'gate_voltage': ['Vg', 'gate_voltage', 'vg', 'gate_v'],
            'drain_current': ['Id', 'drain_current', 'id', 'drain_i'],
            'source_current': ['Is', 'source_current', 'is', 'source_i']
        }
        
        # 在步骤组数据集中查找数据
        for field_name, possible_columns in column_mappings.items():
            for col_name in possible_columns:
                try:
                    if col_name in step_group:
                        dataset = step_group[col_name]
                        if hasattr(dataset, 'shape'):  # 检查是否为数据集
                            data_dict[field_name] = np.array(dataset[:])
                            break
                except Exception:
                    continue
        
        # 根据步骤类型创建相应的数据对象
        if step_type == 'transfer':
            return TransferData(**data_dict)
        elif step_type == 'transient':
            return TransientData(**data_dict)
        else:
            return None
    
    def _extract_workflow_info(self, step_group) -> Optional[WorkflowInfo]:
        """从步骤组提取工作流信息"""
        try:
            if 'workflow_info' not in step_group:
                return None
            
            workflow_group = step_group['workflow_info']
            if not hasattr(workflow_group, 'attrs'):
                return None
            
            # 提取工作流信息属性
            workflow_data = extract_group_attributes(workflow_group)
            
            # 提取迭代信息（如果可用）
            iteration_info = None
            if 'iteration_info' in workflow_group:
                iteration_group = workflow_group['iteration_info']
                if hasattr(iteration_group, 'attrs'):
                    iteration_data = extract_group_attributes(iteration_group)
                    if iteration_data:
                        iteration_info = IterationInfo(**iteration_data)
            
            if iteration_info:
                workflow_data['iteration_info'] = iteration_info
            
            if workflow_data:
                return WorkflowInfo(**workflow_data)
                
        except Exception as e:
            logger.warning(f"提取工作流信息失败: {e}")
        
        return None
    
    def is_new_format(self) -> bool:
        """检查HDF5文件是否为新格式"""
        try:
            with h5py.File(self.file_path, 'r') as f:
                format_version = f.attrs.get('format_version', '')
                if isinstance(format_version, bytes):
                    format_version = format_version.decode('utf-8')
                elif hasattr(format_version, 'item'):
                    format_version = format_version.item()
                    if isinstance(format_version, bytes):
                        format_version = format_version.decode('utf-8')
                
                # 检查是否为新格式版本
                return str(format_version).startswith('2.0_new_storage')
        except Exception:
            return False
    
    def load_new_format_data(self) -> Optional[BatchExperimentData]:
        """加载新格式的实验数据"""
        if not self.is_new_format():
            return None
        
        try:
            transfer_data = self._load_transfer_batch_data()
            transient_data = self._load_transient_batch_data()
            
            if transfer_data is None and transient_data is None:
                return None
            
            return BatchExperimentData(
                transfer_data=transfer_data,
                transient_data=transient_data
            )
        except Exception as e:
            logger.error(f"加载新格式数据失败: {e}")
            return None
    
    def _load_transfer_batch_data(self) -> Optional[TransferBatchData]:
        """加载transfer批量数据"""
        try:
            with h5py.File(self.file_path, 'r') as f:
                if 'transfer' not in f:
                    return None
                
                transfer_group = f['transfer']
                
                # 加载步骤信息表格
                step_info_table = None
                if 'step_info_table' in transfer_group:
                    # 读取结构化数组并转换为DataFrame
                    from csv2hdf.new_format_storage import _load_structured_array_as_dataframe
                    step_info_table = _load_structured_array_as_dataframe(transfer_group['step_info_table'])
                
                # 加载3D测量数据
                measurement_data = None
                if 'measurement_data' in transfer_group:
                    measurement_data = np.array(transfer_group['measurement_data'][:])
                
                if step_info_table is None and measurement_data is None:
                    return None
                
                return TransferBatchData(
                    step_info_table=step_info_table,
                    measurement_data=measurement_data
                )
                
        except Exception as e:
            logger.error(f"加载transfer批量数据失败: {e}")
            return None
    
    def _load_transient_batch_data(self) -> Optional[TransientBatchData]:
        """加载transient批量数据"""
        try:
            with h5py.File(self.file_path, 'r') as f:
                if 'transient' not in f:
                    return None
                
                transient_group = f['transient']
                
                # 加载步骤信息表格
                step_info_table = None
                if 'step_info_table' in transient_group:
                    # 读取结构化数组并转换为DataFrame
                    from csv2hdf.new_format_storage import _load_structured_array_as_dataframe
                    step_info_table = _load_structured_array_as_dataframe(transient_group['step_info_table'])
                
                # 加载2D测量数据
                measurement_data = None
                if 'measurement_data' in transient_group:
                    measurement_data = np.array(transient_group['measurement_data'][:])
                
                if step_info_table is None and measurement_data is None:
                    return None
                
                return TransientBatchData(
                    step_info_table=step_info_table,
                    measurement_data=measurement_data
                )
                
        except Exception as e:
            logger.error(f"加载transient批量数据失败: {e}")
            return None
    
