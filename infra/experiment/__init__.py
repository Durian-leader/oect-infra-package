"""
实验数据处理模块

提供科学实验数据的读取、分析和处理功能

主要特性:
- 从HDF5文件加载实验数据和元数据
- 工作流配置的解析和分析
- 单步数据处理
- 类型安全的数据模型（基于Pydantic）
- 清晰的分层架构设计

基本用法:
    from experiment import Experiment
    
    # 创建实验实例
    exp = Experiment('path/to/experiment.h5')
    
    # 获取基本信息
    print(exp.test_id)
    print(exp.get_progress_info())
    
    # 工作流操作
    if exp.has_workflow():
        exp.print_workflow()
        exp.export_workflow_json('workflow.json')
    
    # 步骤数据
    step_info = exp.get_step_info(1)
    step_data = exp.get_step_data(1)
"""

# 核心类
from .core import Experiment

# 数据模型 (供高级用法使用)
from .models import (
    ExperimentAttributes,
    TransferStepConfig,
    TransientStepConfig,
    OutputStepConfig,
    LoopConfig,
    WorkflowStep,
    Workflow,
    StepInfo,
    TransferData,
    TransientData,
    WorkflowInfo,
    IterationInfo,
    BatchExperimentData
)

# 服务类 (供扩展使用)
from .services import (
    ExperimentService,
    WorkflowService
)

# 仓库类 (供自定义数据源使用)
from .repositories import (
    BaseRepository,
    HDF5Repository,
    BatchHDF5Repository
)

# 版本信息
__version__ = "2.0.0"
__author__ = "科学数据处理团队"

# 公开API
__all__ = [
    # 核心类（主要接口）
    'Experiment',
    
    # 数据模型
    'ExperimentAttributes',
    'TransferStepConfig',
    'TransientStepConfig',
    'OutputStepConfig',
    'LoopConfig',
    'WorkflowStep',
    'Workflow',
    'StepInfo',
    'TransferData',
    'TransientData',
    'WorkflowInfo',
    'IterationInfo',
    'BatchExperimentData',
    
    # 服务类
    'ExperimentService',
    'WorkflowService',
    
    # 仓库类
    'BaseRepository',
    'HDF5Repository',
    'BatchHDF5Repository',
    
    # 元数据
    '__version__',
    '__author__'
]


# 便利函数
def load_experiment(hdf5_path: str) -> Experiment:
    """
    便利函数：加载实验
    
    Args:
        hdf5_path: HDF5文件路径
        
    Returns:
        Experiment: 实验实例
    """
    return Experiment(hdf5_path)


# 添加便利函数到公开API
__all__.append('load_experiment')