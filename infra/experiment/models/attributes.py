"""
实验属性数据模型

定义实验的基本属性和元数据结构
"""
from typing import Optional
from pydantic import BaseModel


class ExperimentAttributes(BaseModel):
    """
    实验属性的Pydantic模型，从HDF5文件根级别加载
    
    包含实验的所有元数据信息，如测试ID、设备信息、进度状态等
    """
    
    # 基本测试信息
    sync_mode: Optional[bool] = None
    batch_id: Optional[str] = None
    test_id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    
    # 测试单元信息
    test_unit_id: Optional[str] = None
    port: Optional[str] = None
    baudrate: Optional[int] = None
    
    # 设备信息
    chip_id: Optional[str] = None
    device_number: Optional[str] = None
    
    # 时间信息
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    
    # 进度信息
    status: Optional[str] = None
    total_steps: Optional[int] = None
    completed_steps: Optional[int] = None
    completion_percentage: Optional[float] = None

    class Config:
        extra = 'allow'  # 允许未明确定义的额外字段
        
    def get_progress_info(self) -> dict:
        """获取实验进度信息"""
        return {
            'status': self.status,
            'total_steps': self.total_steps,
            'completed_steps': self.completed_steps,
            'completion_percentage': self.completion_percentage,
            'is_completed': self.status == 'completed' if self.status else False
        }
    
    def get_test_info(self) -> dict:
        """获取基本测试信息"""
        return {
            'sync_mode': self.sync_mode,
            'batch_id': self.batch_id,
            'test_id': self.test_id,
            'name': self.name,
            'description': self.description
        }
    
    def get_test_unit_info(self) -> dict:
        """获取测试单元和连接信息"""
        return {
            'test_unit_id': self.test_unit_id,
            'port': self.port,
            'baudrate': self.baudrate
        }
    
    def get_device_info(self) -> dict:
        """获取设备/芯片信息"""
        return {
            'chip_id': self.chip_id,
            'device_number': self.device_number
        }