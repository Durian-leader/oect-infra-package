"""
工具函数模块

提供实验数据处理相关的通用工具函数
"""

from .hdf5_helpers import (
    decode_hdf5_attr_value,
    handle_null_values,
    safe_decode_attr,
    extract_group_attributes,
    build_step_group_name
)

from .time_helpers import (
    calculate_duration,
    get_timing_info
)

__all__ = [
    # HDF5工具函数
    'decode_hdf5_attr_value',
    'handle_null_values', 
    'safe_decode_attr',
    'extract_group_attributes',
    'build_step_group_name',
    
    # 时间工具函数
    'calculate_duration',
    'get_timing_info'
]