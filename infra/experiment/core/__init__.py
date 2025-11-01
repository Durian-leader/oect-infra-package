"""
核心模块

提供实验相关的核心领域对象
"""

# 使用简化的批量格式专用实验类
from .experiment import Experiment, load_experiment

__all__ = [
    'Experiment',
    'load_experiment'
]