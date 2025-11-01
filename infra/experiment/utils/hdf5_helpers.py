"""
HDF5文件操作工具函数

提供HDF5文件读取和数据解码的通用工具
"""
import numpy as np
import pandas as pd
import h5py
from typing import Any


def decode_hdf5_attr_value(value: Any) -> Any:
    """
    解码HDF5属性值，处理字节字符串和numpy标量
    
    Args:
        value: 从HDF5属性中读取的原始值
        
    Returns:
        解码后的Python值
    """
    if isinstance(value, bytes):
        return value.decode('utf-8')
    elif isinstance(value, np.ndarray) and value.size == 1:
        # 处理numpy标量数组
        item = value.item()
        if isinstance(item, bytes):
            return item.decode('utf-8')
        return item
    elif hasattr(value, 'item'):
        # 处理numpy标量
        decoded = value.item()
        if isinstance(decoded, bytes):
            return decoded.decode('utf-8')
        return decoded
    else:
        return value


def handle_null_values(value: Any) -> Any:
    """
    处理字符串形式的null值，转换为Python的None
    
    Args:
        value: 原始值
        
    Returns:
        处理后的值，如果是'null'字符串则返回None
    """
    if isinstance(value, str) and value.lower() == 'null':
        return None
    return value


def safe_decode_attr(attrs_dict: dict, attr_name: str) -> Any:
    """
    安全地解码HDF5属性，包含错误处理
    
    Args:
        attrs_dict: HDF5属性字典
        attr_name: 属性名称
        
    Returns:
        解码后的属性值，如果解码失败返回None
    """
    if attr_name not in attrs_dict:
        return None
        
    try:
        raw_value = attrs_dict[attr_name]
        decoded_value = decode_hdf5_attr_value(raw_value)
        return handle_null_values(decoded_value)
    except Exception:
        return None


def extract_group_attributes(group, exclude_types: bool = True) -> dict:
    """
    从HDF5组中提取所有属性
    
    Args:
        group: HDF5组对象
        exclude_types: 是否排除__type属性
        
    Returns:
        属性名到值的字典
    """
    attrs = {}
    for attr_name in group.attrs.keys():
        if exclude_types and attr_name.endswith('__type'):
            continue
        attrs[attr_name] = safe_decode_attr(group.attrs, attr_name)
    return attrs


def build_step_group_name(step_index: int) -> str:
    """
    构建步骤组名称
    
    Args:
        step_index: 步骤索引(1-based)
        
    Returns:
        格式化的步骤组名称，如'step_000001'
    """
    return f"step_{step_index:06d}"


def load_structured_array_as_dataframe(dataset: h5py.Dataset) -> pd.DataFrame:
    """
    从HDF5结构化数组加载为pandas DataFrame
    
    这个函数专门处理新格式HDF5文件中的步骤信息表格。
    
    Args:
        dataset: HDF5结构化数组数据集
        
    Returns:
        pd.DataFrame: 转换后的DataFrame
    """
    try:
        # 读取结构化数组数据
        data = dataset[:]
        df = pd.DataFrame(data)
        
        # 解码bytes字符串列
        for col in df.columns:
            if df[col].dtype.kind in ['S', 'a']:  # bytes字符串
                try:
                    df[col] = df[col].astype(str).str.decode('utf-8', errors='ignore')
                except (AttributeError, UnicodeDecodeError):
                    # 如果解码失败，保持原样
                    pass
        
        return df
        
    except Exception as e:
        raise RuntimeError(f"加载结构化数组为DataFrame失败: {e}")


def check_new_format_version(format_version: Any) -> bool:
    """
    检查格式版本是否为新格式
    
    统一的新格式检测逻辑，确保各个仓库类的一致性。
    
    Args:
        format_version: 从HDF5文件读取的格式版本属性
        
    Returns:
        bool: 是否为新格式
    """
    try:
        # 解码格式版本字符串
        if isinstance(format_version, bytes):
            version_str = format_version.decode('utf-8')
        elif hasattr(format_version, 'item'):
            version_item = format_version.item()
            if isinstance(version_item, bytes):
                version_str = version_item.decode('utf-8')
            else:
                version_str = str(version_item)
        else:
            version_str = str(format_version)
        
        # 检查是否为新格式版本
        # 支持 "2.0_new_storage" 格式
        return version_str.startswith('2.0_') and 'new_storage' in version_str
        
    except Exception:
        return False


def get_hdf5_format_version(file_path: str) -> str:
    """
    获取HDF5文件的格式版本
    
    Args:
        file_path: HDF5文件路径
        
    Returns:
        str: 格式版本字符串，如果无法获取返回空字符串
    """
    try:
        with h5py.File(file_path, 'r') as f:
            format_version = f.attrs.get('format_version', '')
            return decode_hdf5_attr_value(format_version)
    except Exception:
        return ""