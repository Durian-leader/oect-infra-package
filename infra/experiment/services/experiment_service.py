"""
实验业务逻辑服务

处理实验相关的核心业务逻辑
"""
from typing import Optional, Dict, Any, Union
from ..models import ExperimentAttributes, StepInfo, TransferData, TransientData
from ..repositories import BaseRepository
from ..utils import get_timing_info


class ExperimentService:
    """实验服务类"""
    
    def __init__(self, repository: BaseRepository):
        self.repository = repository
        self._attributes_cache: Optional[ExperimentAttributes] = None
    
    def get_attributes(self) -> ExperimentAttributes:
        """获取实验属性（带缓存）"""
        if self._attributes_cache is None:
            self._attributes_cache = self.repository.load_attributes()
        return self._attributes_cache
    
    def get_progress_info(self) -> Dict[str, Any]:
        """获取实验进度信息"""
        attributes = self.get_attributes()
        return attributes.get_progress_info()
    
    def get_test_info(self) -> Dict[str, Any]:
        """获取基本测试信息"""
        attributes = self.get_attributes()
        return attributes.get_test_info()
    
    def get_test_unit_info(self) -> Dict[str, Any]:
        """获取测试单元和连接信息"""
        attributes = self.get_attributes()
        return attributes.get_test_unit_info()
    
    def get_device_info(self) -> Dict[str, Any]:
        """获取设备/芯片信息"""
        attributes = self.get_attributes()
        return attributes.get_device_info()
    
    def get_timing_info(self) -> Dict[str, Any]:
        """获取实验时间信息"""
        attributes = self.get_attributes()
        return get_timing_info(attributes.created_at, attributes.completed_at)
    
    def get_step_info(self, step_index: int) -> Optional[StepInfo]:
        """获取步骤信息"""
        # 检查步骤索引是否超过已完成步骤
        attributes = self.get_attributes()
        if attributes.completed_steps is not None and step_index > attributes.completed_steps:
            raise ValueError(f"步骤索引 {step_index} 超过已完成步骤 {attributes.completed_steps}")
        
        return self.repository.load_step_info(step_index)
    
    def get_step_data(self, step_index: int) -> Optional[Union[TransferData, TransientData]]:
        """获取步骤测量数据"""
        # 先获取步骤信息确定类型
        step_info = self.get_step_info(step_index)
        if not step_info:
            return None
        
        return self.repository.load_step_data(step_index, step_info.type)
    
    def get_experiment_summary(self) -> Dict[str, Any]:
        """获取实验完整摘要信息"""
        attributes = self.get_attributes()
        
        return {
            'basic_info': attributes.get_test_info(),
            'device_info': attributes.get_device_info(),
            'test_unit_info': attributes.get_test_unit_info(),
            'progress_info': attributes.get_progress_info(),
            'timing_info': self.get_timing_info(),
            'has_workflow': self.repository.has_workflow()
        }
    
    def is_completed(self) -> bool:
        """检查实验是否已完成"""
        attributes = self.get_attributes()
        return attributes.status == 'completed' if attributes.status else False
    
    def get_completion_percentage(self) -> float:
        """获取完成百分比"""
        attributes = self.get_attributes()
        return attributes.completion_percentage or 0.0
    
    def get_completed_steps_count(self) -> int:
        """获取已完成步骤数"""
        attributes = self.get_attributes()
        return attributes.completed_steps or 0
    
    def get_total_steps_count(self) -> int:
        """获取总步骤数"""
        attributes = self.get_attributes()
        return attributes.total_steps or 0
    
    def clear_attributes_cache(self):
        """清除属性缓存，强制重新加载"""
        self._attributes_cache = None