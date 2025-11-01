"""
工作流配置数据模型

定义实验工作流的各种步骤类型和循环结构
"""
from typing import List, Dict, Any, Union, Literal
from pydantic import BaseModel, Field


class TransferStepConfig(BaseModel):
    """转移特性测试步骤配置"""
    id: str
    type: Literal["transfer"] = "transfer"
    command_id: int
    params: Dict[str, Any] = {
        "isSweep": 0,
        "timeStep": 0,
        "sourceVoltage": 0,
        "drainVoltage": 0,
        "gateVoltageStart": 0,
        "gateVoltageEnd": 0,
        "gateVoltageStep": 0
    }

    class Config:
        extra = 'allow'  # 允许额外字段


class TransientStepConfig(BaseModel):
    """瞬态特性测试步骤配置"""
    id: str
    type: Literal["transient"] = "transient"
    command_id: int
    params: Dict[str, Any] = {
        "timeStep": 0,
        "sourceVoltage": 0,
        "drainVoltage": 0,
        "bottomTime": 0,
        "topTime": 0,
        "gateVoltageBottom": 0,
        "gateVoltageTop": 0,
        "cycles": 0
    }

    class Config:
        extra = 'allow'  # 允许额外字段


class OutputStepConfig(BaseModel):
    """输出特性测试步骤配置"""
    id: str
    type: Literal["output"] = "output"
    command_id: int
    params: Dict[str, Any] = {
        "isSweep": 0,
        "timeStep": 0,
        "sourceVoltage": 0,
        "gateVoltage": 0,
        "drainVoltageStart": 0,
        "drainVoltageEnd": 0,
        "drainVoltageStep": 0
    }

    class Config:
        extra = 'allow'  # 允许额外字段


class LoopConfig(BaseModel):
    """循环配置"""
    id: str
    type: Literal["loop"] = "loop"
    iterations: int = Field(..., gt=0, description="循环次数")
    steps: List[Union["TransferStepConfig", "TransientStepConfig", "OutputStepConfig", "LoopConfig"]]

    class Config:
        extra = 'allow'  # 允许额外字段


# 更新前向引用以支持递归类型
LoopConfig.model_rebuild()

# 类型别名定义
WorkflowStep = Union[TransferStepConfig, TransientStepConfig, OutputStepConfig, LoopConfig]
Workflow = List[WorkflowStep]


def parse_workflow_json(workflow_data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> Workflow:
    """
    解析工作流JSON数据为Workflow对象
    
    Args:
        workflow_data: 工作流JSON数据，可以是单个步骤字典或步骤列表
        
    Returns:
        Workflow: 解析后的工作流对象
    """
    if isinstance(workflow_data, dict):
        # 如果是单个步骤，转换为列表
        steps_data = [workflow_data]
    else:
        # 如果已经是列表
        steps_data = workflow_data
    
    def parse_step(step_data: Dict[str, Any]) -> WorkflowStep:
        """解析单个步骤"""
        step_type = step_data.get('type')
        
        if step_type == 'transfer':
            return TransferStepConfig(**step_data)
        elif step_type == 'transient':
            return TransientStepConfig(**step_data)
        elif step_type == 'output':
            return OutputStepConfig(**step_data)
        elif step_type == 'loop':
            # 递归解析循环中的步骤
            loop_data = step_data.copy()
            loop_data['steps'] = [parse_step(sub_step) for sub_step in loop_data.get('steps', [])]
            return LoopConfig(**loop_data)
        else:
            raise ValueError(f"未知的步骤类型: {step_type}")
    
    return [parse_step(step_data) for step_data in steps_data]