"""
批量HDF5数据模型

支持批量数据存储格式：
- Transfer: 3D numpy数组 + pandas DataFrame
- Transient: 2D numpy数组 + pandas DataFrame
"""
from typing import Optional, Dict, Any, Literal
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field


class TransferBatchData(BaseModel):
    """
    Transfer批量数据模型
    
    包含所有transfer步骤的数据和信息
    """
    step_info_table: pd.DataFrame = Field(description="步骤信息表格（展平的stepinfo）")
    measurement_data: np.ndarray = Field(description="3D测量数据数组 [步骤索引, 数据类型, 数据点索引]")
    
    class Config:
        arbitrary_types_allowed = True
    
    def get_step_count(self) -> int:
        """获取步骤数量"""
        return self.measurement_data.shape[0] if self.measurement_data is not None else 0
    
    def get_step_info_by_index(self, step_index: int) -> Optional[Dict[str, Any]]:
        """
        根据相对步骤索引获取步骤信息
        
        Args:
            step_index: 相对步骤索引（从0开始）
            
        Returns:
            步骤信息字典，如果索引无效则返回None
        """
        if self.step_info_table is None or step_index < 0 or step_index >= len(self.step_info_table):
            return None
        
        return self.step_info_table.iloc[step_index].to_dict()
    
    def get_step_measurement_data(self, step_index: int) -> Optional[Dict[str, np.ndarray]]:
        """
        获取指定步骤的测量数据
        
        Args:
            step_index: 相对步骤索引（从0开始）
            
        Returns:
            包含'Vg'和'Id'数组的字典，如果索引无效则返回None
        """
        if (self.measurement_data is None or 
            step_index < 0 or 
            step_index >= self.measurement_data.shape[0]):
            return None
        
        # 提取该步骤的数据 [数据类型, 数据点索引]
        step_data = self.measurement_data[step_index, :, :]
        
        # 移除NaN值（用于处理不等长数据的填充）
        vg_data = step_data[0, :]  # 第0维是Vg
        id_data = step_data[1, :]  # 第1维是Id
        
        # 找到有效数据的长度（去除NaN填充）
        vg_valid = ~np.isnan(vg_data)
        id_valid = ~np.isnan(id_data)
        valid_mask = vg_valid & id_valid
        
        if not np.any(valid_mask):
            return None
        
        return {
            'Vg': vg_data[valid_mask],
            'Id': id_data[valid_mask]
        }
    
    def get_all_measurement_data(self) -> Optional[Dict[str, Any]]:
        """
        获取所有transfer步骤的原始测量数据（3D数组）
        
        Returns:
            包含'measurement_data'(3D数组)和'data_info'的字典
            measurement_data: [steps, data_types, data_points] 形状的3D数组
                - 第0维: 步骤索引
                - 第1维: 数据类型 (0=Vg, 1=Id)
                - 第2维: 数据点索引
        """
        if self.measurement_data is None:
            return None
        
        return {
            'measurement_data': self.measurement_data,  # 原始3D数组
            'data_info': {
                'shape': self.measurement_data.shape,
                'step_count': self.get_step_count(),
                'data_types': ['Vg', 'Id'],
                'description': 'Shape: [steps, data_types, data_points]'
            }
        }
    
    def get_data_summary(self) -> Dict[str, Any]:
        """获取数据摘要"""
        return {
            'step_count': self.get_step_count(),
            'measurement_data_shape': self.measurement_data.shape if self.measurement_data is not None else None,
            'step_info_columns': list(self.step_info_table.columns) if self.step_info_table is not None else None
        }


class TransientBatchData(BaseModel):
    """
    Transient批量数据模型
    
    包含所有transient步骤拼接后的数据
    """
    step_info_table: pd.DataFrame = Field(description="步骤信息表格（展平的stepinfo）")
    measurement_data: np.ndarray = Field(description="2D测量数据数组 [数据类型, 数据点索引]")
    
    class Config:
        arbitrary_types_allowed = True
    
    def get_step_count(self) -> int:
        """获取步骤数量"""
        return len(self.step_info_table) if self.step_info_table is not None else 0
    
    def get_total_data_points(self) -> int:
        """获取总数据点数"""
        return self.measurement_data.shape[1] if self.measurement_data is not None else 0
    
    def get_step_info_by_index(self, step_index: int) -> Optional[Dict[str, Any]]:
        """
        根据相对步骤索引获取步骤信息
        
        Args:
            step_index: 相对步骤索引（从0开始）
            
        Returns:
            步骤信息字典，如果索引无效则返回None
        """
        if self.step_info_table is None or step_index < 0 or step_index >= len(self.step_info_table):
            return None
        
        return self.step_info_table.iloc[step_index].to_dict()
    
    def get_step_measurement_data(self, step_index: int) -> Optional[Dict[str, np.ndarray]]:
        """
        获取指定步骤的测量数据（从拼接数据中提取）
        
        Args:
            step_index: 相对步骤索引（从0开始）
            
        Returns:
            包含'continuous_time'、'original_time'和'drain_current'数组的字典，如果索引无效则返回None
        """
        if (self.measurement_data is None or 
            self.step_info_table is None or
            step_index < 0 or 
            step_index >= len(self.step_info_table)):
            return None
        
        # 计算每个步骤的数据点数（假设均匀分布）
        total_points = self.measurement_data.shape[1]
        step_count = len(self.step_info_table)
        points_per_step = total_points // step_count
        
        # 计算该步骤的数据范围
        start_idx = step_index * points_per_step
        end_idx = start_idx + points_per_step
        
        # 对于最后一个步骤，包含所有剩余数据点
        if step_index == step_count - 1:
            end_idx = total_points
        
        # 提取该步骤的数据
        return {
            'continuous_time': self.measurement_data[0, start_idx:end_idx],    # 连续时间序列
            'original_time': self.measurement_data[1, start_idx:end_idx],      # 原始时间序列
            'drain_current': self.measurement_data[2, start_idx:end_idx]       # 电流序列
        }
    
    def get_all_measurement_data(self) -> Optional[Dict[str, np.ndarray]]:
        """
        获取所有拼接后的测量数据
        
        Returns:
            包含'continuous_time'、'original_time'和'drain_current'数组的字典
        """
        if self.measurement_data is None:
            return None
        
        return {
            'continuous_time': self.measurement_data[0, :],    # 连续时间序列
            'original_time': self.measurement_data[1, :],      # 原始时间序列
            'drain_current': self.measurement_data[2, :]       # 电流序列
        }
    
    def get_data_summary(self) -> Dict[str, Any]:
        """获取数据摘要"""
        return {
            'step_count': self.get_step_count(),
            'total_data_points': self.get_total_data_points(),
            'measurement_data_shape': self.measurement_data.shape if self.measurement_data is not None else None,
            'step_info_columns': list(self.step_info_table.columns) if self.step_info_table is not None else None
        }


class BatchExperimentData(BaseModel):
    """
    批量实验数据模型
    
    包含transfer和transient的批量数据
    """
    transfer_data: Optional[TransferBatchData] = Field(default=None, description="Transfer批量数据")
    transient_data: Optional[TransientBatchData] = Field(default=None, description="Transient批量数据")
    
    def has_transfer_data(self) -> bool:
        """检查是否有transfer数据"""
        return self.transfer_data is not None
    
    def has_transient_data(self) -> bool:
        """检查是否有transient数据"""
        return self.transient_data is not None
    
    def get_transfer_step_count(self) -> int:
        """获取transfer步骤数"""
        return self.transfer_data.get_step_count() if self.transfer_data else 0
    
    def get_transient_step_count(self) -> int:
        """获取transient步骤数"""
        return self.transient_data.get_step_count() if self.transient_data else 0
    
    def get_total_step_count(self) -> int:
        """获取总步骤数"""
        return self.get_transfer_step_count() + self.get_transient_step_count()
    
    def get_data_summary(self) -> Dict[str, Any]:
        """获取数据摘要"""
        summary = {
            'has_transfer_data': self.has_transfer_data(),
            'has_transient_data': self.has_transient_data(),
            'total_step_count': self.get_total_step_count()
        }
        
        if self.transfer_data:
            summary['transfer_summary'] = self.transfer_data.get_data_summary()
        
        if self.transient_data:
            summary['transient_summary'] = self.transient_data.get_data_summary()
        
        return summary