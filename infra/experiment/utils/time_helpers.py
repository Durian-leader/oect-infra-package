"""
时间处理工具函数

提供实验时间相关的计算和格式化功能
"""
from datetime import datetime
from typing import Optional


def calculate_duration(start_time: Optional[str], end_time: Optional[str]) -> Optional[str]:
    """
    计算实验持续时间
    
    Args:
        start_time: 开始时间字符串 (ISO格式)
        end_time: 结束时间字符串 (ISO格式)
        
    Returns:
        人类可读的持续时间字符串，计算失败返回None
    """
    if not (start_time and end_time):
        return None
    
    try:
        # 解析ISO格式的时间字符串
        start = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        
        duration = end - start
        
        # 格式化持续时间为可读字符串
        days = duration.days
        hours, remainder = divmod(duration.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}天")
        if hours > 0:
            parts.append(f"{hours}小时")
        if minutes > 0:
            parts.append(f"{minutes}分钟")
        if seconds > 0 or not parts:
            parts.append(f"{seconds}秒")
        
        return "".join(parts)
        
    except Exception:
        return "无法计算持续时间"


def get_timing_info(created_at: Optional[str], completed_at: Optional[str]) -> dict:
    """
    获取实验时间信息
    
    Args:
        created_at: 创建时间字符串
        completed_at: 完成时间字符串
        
    Returns:
        包含时间信息的字典
    """
    return {
        'created_at': created_at,
        'completed_at': completed_at,
        'duration': calculate_duration(created_at, completed_at)
    }