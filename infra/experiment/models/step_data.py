"""
实验步骤数据模型

定义步骤信息和测量数据的结构
"""
from typing import Optional, Dict, Any, Literal
import numpy as np
from pydantic import BaseModel, Field


class IterationInfo(BaseModel):
    """循环迭代信息"""
    type: str
    parent: Optional[Any] = None
    total: int
    current: int


class WorkflowInfo(BaseModel):
    """工作流执行信息"""
    step_index: int
    total_steps: int
    path_readable: str
    iteration_info: Optional[IterationInfo] = None


class StepInfo(BaseModel):
    """实验步骤信息"""
    type: Literal["transfer", "transient"]
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    params: Dict[str, Any]
    reason: str
    workflow_info: Optional[WorkflowInfo] = None
    data_file: Optional[str] = None

    class Config:
        extra = 'allow'


class TransferData(BaseModel):
    """转移特性测试数据"""
    timestamp: Optional[np.ndarray] = Field(default=None, description="时间戳")
    gate_voltage: Optional[np.ndarray] = Field(default=None, description="栅极电压 (Vg)")
    drain_current: Optional[np.ndarray] = Field(default=None, description="漏极电流 (Id)")
    source_current: Optional[np.ndarray] = Field(default=None, description="源极电流 (Is)")
    
    class Config:
        arbitrary_types_allowed = True
        
    def get_data_summary(self) -> dict:
        """获取数据摘要信息"""
        summary = {}
        for field_name in ['timestamp', 'gate_voltage', 'drain_current', 'source_current']:
            field_value = getattr(self, field_name, None)
            if field_value is not None and hasattr(field_value, '__len__'):
                summary[field_name] = len(field_value)
            else:
                summary[field_name] = 0
        return summary


class TransientData(BaseModel):
    """瞬态特性测试数据"""
    timestamp: Optional[np.ndarray] = Field(default=None, description="时间戳")
    gate_voltage: Optional[np.ndarray] = Field(default=None, description="栅极电压 (Vg)")
    drain_current: Optional[np.ndarray] = Field(default=None, description="漏极电流 (Id)")
    source_current: Optional[np.ndarray] = Field(default=None, description="源极电流 (Is)")
    
    class Config:
        arbitrary_types_allowed = True
        
    def get_data_summary(self) -> dict:
        """获取数据摘要信息"""
        summary = {}
        for field_name in ['timestamp', 'gate_voltage', 'drain_current', 'source_current']:
            field_value = getattr(self, field_name, None)
            if field_value is not None and hasattr(field_value, '__len__'):
                summary[field_name] = len(field_value)
            else:
                summary[field_name] = 0
        return summary