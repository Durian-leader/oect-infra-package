"""
仓库模式抽象基类

定义数据访问层的统一接口
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Union
from pathlib import Path

from ..models import (
    ExperimentAttributes, 
    Workflow,
    StepInfo,
    TransferData,
    TransientData
)


class BaseRepository(ABC):
    """数据仓库抽象基类"""
    
    def __init__(self, file_path: str):
        """
        初始化仓库
        
        Args:
            file_path: 数据文件路径
        """
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"数据文件不存在: {file_path}")
    
    @abstractmethod
    def load_attributes(self) -> ExperimentAttributes:
        """加载实验属性"""
        pass
    
    @abstractmethod 
    def load_workflow(self) -> Optional[Workflow]:
        """加载工作流配置"""
        pass
    
    @abstractmethod
    def has_workflow(self) -> bool:
        """检查是否有工作流配置"""
        pass
    
    @abstractmethod
    def load_step_info(self, step_index: int) -> Optional[StepInfo]:
        """加载步骤信息"""
        pass
    
    @abstractmethod
    def load_step_data(self, step_index: int, step_type: str) -> Optional[Union[TransferData, TransientData]]:
        """加载步骤数据"""
        pass
    
