"""
简化的实验类 - 支持懒加载批量格式HDF5

提供新格式实验数据访问的统一接口，专门为懒加载批量格式优化
真正的懒加载：只在需要时加载数据，大幅提升性能
"""
from typing import Optional, Dict, Any
from pathlib import Path

from ..models import (
    ExperimentAttributes,
    Workflow
)
from ..repositories.batch_hdf5_repository import BatchHDF5Repository
from ..services.workflow_service import WorkflowService
from ..utils.hdf5_helpers import get_hdf5_format_version, check_new_format_version
from ..utils.time_helpers import get_timing_info


class Experiment:
    """
    懒加载实验类 - 支持批量格式HDF5
    
    专门为批量格式HDF5文件优化，提供真正的懒加载数据访问
    性能提升：摘要操作从GB级内存使用降至MB级
    """
    
    def __init__(self, hdf5_path: str, cache_size: int = 20):
        """
        从批量格式HDF5文件路径初始化实验
        
        Args:
            hdf5_path: 批量格式HDF5文件路径
            cache_size: 数据缓存大小 (默认20个步骤数据)
            
        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 文件不是批量格式
        """
        self.hdf5_path = Path(hdf5_path)
        if not self.hdf5_path.exists():
            raise FileNotFoundError(f"HDF5文件不存在: {hdf5_path}")
        
        # 检查是否为批量格式
        format_version = get_hdf5_format_version(str(hdf5_path))
        if not check_new_format_version(format_version):
            raise ValueError(f"文件不是批量格式HDF5文件: {hdf5_path} (格式版本: {format_version})")
        
        # 使用懒加载批量格式仓库
        self._repository = BatchHDF5Repository(str(hdf5_path), cache_size=cache_size)
        self._workflow_service = WorkflowService(self._repository)
        self._attributes = None  # 延迟加载
    
    def __getattr__(self, name):
        """
        允许直接访问实验属性
        
        示例: experiment.test_id 而不是 experiment.get_attributes().test_id
        """
        try:
            attributes = self.get_attributes()
            if hasattr(attributes, name):
                return getattr(attributes, name)
        except Exception:
            pass
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
    
    def __repr__(self):
        """字符串表示"""
        try:
            test_id = getattr(self, 'test_id', 'Unknown')
            return f"<Experiment(test_id='{test_id}', path='{self.hdf5_path.name}')>"
        except Exception:
            return f"<Experiment(path='{self.hdf5_path.name}')>"
    
    # ===================
    # 属性访问方法
    # ===================
    
    def get_attributes(self) -> ExperimentAttributes:
        """
        获取实验属性 (懒加载)
        
        Returns:
            ExperimentAttributes: 实验属性对象
        """
        if self._attributes is None:
            self._attributes = self._repository.load_attributes()
        return self._attributes
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典格式
        
        Returns:
            Dict[str, Any]: 属性字典
        """
        return self.get_attributes().model_dump()
    
    # ===================
    # 基本信息获取方法
    # ===================
    
    def get_progress_info(self) -> Dict[str, Any]:
        """获取实验进度信息"""
        attributes = self.get_attributes()
        return attributes.get_progress_info()
    
    def get_test_info(self) -> Dict[str, Any]:
        """获取基本测试信息"""
        attributes = self.get_attributes()
        return attributes.get_test_info()
    
    def get_test_unit_info(self) -> Dict[str, Any]:
        """获取测试单元和连接信息"""
        attributes = self.get_attributes()
        return attributes.get_test_unit_info()
    
    def get_device_info(self) -> Dict[str, Any]:
        """获取设备/芯片信息"""
        attributes = self.get_attributes()
        return attributes.get_device_info()
    
    def get_timing_info(self) -> Dict[str, Any]:
        """获取实验时间信息"""
        attributes = self.get_attributes()
        return get_timing_info(attributes.created_at, attributes.completed_at)
    
    def get_experiment_summary(self) -> Dict[str, Any]:
        """获取实验完整摘要"""
        return {
            'basic_info': self.get_test_info(),
            'device_info': self.get_device_info(),
            'test_unit_info': self.get_test_unit_info(),
            'progress_info': self.get_progress_info(),
            'timing_info': self.get_timing_info(),
            'has_transfer_data': self.has_transfer_data(),
            'has_transient_data': self.has_transient_data(),
            'has_workflow': self.has_workflow()
        }
    
    # ===================
    # 工作流相关方法
    # ===================
    
    def get_workflow(self) -> Optional[Workflow]:
        """获取工作流配置"""
        return self._workflow_service.get_workflow()
    
    def has_workflow(self) -> bool:
        """检查是否有工作流配置"""
        return self._workflow_service.has_workflow()
    
    def get_workflow_summary(self) -> Dict[str, Any]:
        """获取工作流摘要信息"""
        return self._workflow_service.get_workflow_summary()
    
    def print_workflow(self, indent: int = 0, show_all_params: bool = False):
        """以人类可读格式打印工作流"""
        self._workflow_service.print_workflow(indent, show_all_params)
    
    def export_workflow_json(self, output_path: str, indent: int = 2) -> bool:
        """导出工作流配置到JSON文件"""
        return self._workflow_service.export_workflow_json(output_path, indent)
    
    def export_workflow(self, output_path: str) -> bool:
        """导出工作流配置到JSON文件 (兼容旧方法名)"""
        return self.export_workflow_json(output_path)
    
    # ===================
    # 🚀 高效摘要方法 (毫秒级，无需加载大数组)
    # ===================
    
    def get_transfer_summary(self) -> Optional[Dict[str, Any]]:
        """
        获取Transfer数据摘要 (超高效 - 基于元数据)
        
        性能优化：从GB级内存使用降至KB级
        
        Returns:
            Optional[Dict[str, Any]]: Transfer数据摘要，如果不存在返回None
        """
        return self._repository.get_transfer_summary()
    
    def get_transient_summary(self) -> Optional[Dict[str, Any]]:
        """
        获取Transient数据摘要 (超高效 - 基于元数据)
        
        性能优化：从GB级内存使用降至KB级
        
        Returns:
            Optional[Dict[str, Any]]: Transient数据摘要，如果不存在返回None
        """
        return self._repository.get_transient_summary()
    
    def get_data_summary(self) -> Dict[str, Any]:
        """
        获取完整数据摘要 (超高效 - 基于元数据)
        
        性能优化：最大的性能提升，无需加载任何大数组
        
        Returns:
            Dict[str, Any]: 包含Transfer和Transient数据摘要的字典
        """
        summary = {
            'has_transfer_data': self.has_transfer_data(),
            'has_transient_data': self.has_transient_data(),
            'file_path': str(self.hdf5_path),
            'format_version': get_hdf5_format_version(str(self.hdf5_path))
        }
        
        # 添加Transfer数据摘要 (无需加载数据)
        transfer_summary = self.get_transfer_summary()
        if transfer_summary:
            summary['transfer_data'] = transfer_summary
        
        # 添加Transient数据摘要 (无需加载数据)
        transient_summary = self.get_transient_summary()
        if transient_summary:
            summary['transient_data'] = transient_summary
        
        return summary
    
    # ===================
    # 🚀 按需数据访问方法 (只加载需要的步骤)
    # ===================
    
    def get_transfer_step_measurement(self, step_index: int) -> Optional[Dict[str, Any]]:
        """
        获取指定Transfer步骤的测量数据 (按需加载 + 智能缓存)
        
        性能优化：只加载单个步骤，支持LRU缓存
        
        Args:
            step_index: Transfer步骤索引 (0-based)
            
        Returns:
            Optional[Dict[str, Any]]: 测量数据字典，包含Vg和Id数组
        """
        return self._repository.get_transfer_step_data(step_index)
    
    def get_transient_step_measurement(self, step_index: int) -> Optional[Dict[str, Any]]:
        """
        获取指定Transient步骤的测量数据 (按需加载 + 智能缓存)
        
        性能优化：只加载单个步骤，支持LRU缓存
        
        Args:
            step_index: Transient步骤索引 (0-based)
            
        Returns:
            Optional[Dict[str, Any]]: 测量数据字典，包含continuous_time、original_time和drain_current数组
        """
        return self._repository.get_transient_step_data(step_index)
    
    # ===================
    # 批量数据对象访问
    # ===================
    
    def get_batch_data(self):
        """
        获取懒加载批量数据对象
        
        Returns:
            LazyBatchExperimentData: 懒加载批量实验数据对象
        """
        return self._repository.load_batch_data()
    
    # ===================
    # 步骤信息访问 (延迟加载)
    # ===================
    
    def get_transfer_step_info_table(self) -> Optional[Any]:
        """
        获取Transfer步骤信息表格 (懒加载)
        
        Returns:
            Optional[pd.DataFrame]: Transfer步骤信息表格，包含所有步骤的元数据
        """
        return self._repository.get_transfer_step_info_table()
    
    def get_transient_step_info_table(self) -> Optional[Any]:
        """
        获取Transient步骤信息表格 (懒加载)
        
        Returns:
            Optional[pd.DataFrame]: Transient步骤信息表格，包含所有步骤的元数据
        """
        return self._repository.get_transient_step_info_table()
    
    # ===================
    # ⚠️ 全量数据访问方法 (谨慎使用)
    # ===================
    
    def get_transfer_all_measurement(self) -> Optional[Dict[str, Any]]:
        """
        获取所有Transfer步骤的测量数据 (⚠️ 会加载所有数据)
        
        ⚠️ 警告：这个方法会加载所有transfer数据的3D数组到内存
        只有在确实需要所有数据时才调用此方法
        推荐使用 get_transfer_step_measurement() 来按需获取具体步骤数据
        
        Returns:
            Optional[Dict[str, Any]]: 包含measurement_data(3D数组)和data_info的字典
        """
        batch_data = self._repository.load_batch_data()  # 这现在是懒加载的
        if batch_data and batch_data.has_transfer_data() and batch_data.transfer_data:
            return batch_data.transfer_data.get_all_measurement_data()
        return None
    
    def get_transient_all_measurement(self) -> Optional[Dict[str, Any]]:
        """
        获取所有Transient步骤的连续测量数据 (⚠️ 会加载所有数据)
        
        ⚠️ 警告：这个方法会加载所有transient数据到内存
        只有在确实需要所有数据时才调用此方法
        推荐使用 get_transient_step_measurement() 来按需获取步骤数据
        
        Returns:
            Optional[Dict[str, Any]]: 测量数据字典，包含连续时间序列
        """
        batch_data = self._repository.load_batch_data()  # 这现在是懒加载的
        if batch_data and batch_data.has_transient_data() and batch_data.transient_data:
            return batch_data.transient_data.get_all_measurement_data()
        return None
    
    # ===================
    # 便利方法
    # ===================
    
    def has_transfer_data(self) -> bool:
        """检查是否有Transfer数据 (高效 - 基于元数据)"""
        return self.get_transfer_summary() is not None
    
    def has_transient_data(self) -> bool:
        """检查是否有Transient数据 (高效 - 基于元数据)"""
        return self.get_transient_summary() is not None
    
    # ===================
    # 缓存和性能管理
    # ===================
    
    def clear_cache(self):
        """清除所有缓存"""
        self._attributes = None
        self._repository.clear_cache()
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            Dict包含缓存命中率等性能指标
        """
        return self._repository.get_cache_stats()
    
    def optimize_cache_for_sequential_access(self, data_type: str = 'transfer', max_steps: int = 10):
        """
        为顺序访问优化缓存
        
        预加载连续步骤的数据以提高顺序访问性能
        
        Args:
            data_type: 'transfer' 或 'transient'
            max_steps: 预加载的最大步骤数
        """
        if data_type == 'transfer':
            summary = self.get_transfer_summary()
            if summary:
                step_count = min(summary['step_count'], max_steps)
                for i in range(step_count):
                    self.get_transfer_step_measurement(i)
        elif data_type == 'transient':
            summary = self.get_transient_summary()
            if summary:
                step_count = min(summary['step_count'], max_steps)
                for i in range(step_count):
                    self.get_transient_step_measurement(i)


# 便利函数
def load_experiment(hdf5_path: str, cache_size: int = 20) -> Experiment:
    """
    便利函数：加载懒加载批量格式实验
    
    Args:
        hdf5_path: HDF5文件路径
        cache_size: 数据缓存大小 (默认20个步骤数据)
        
    Returns:
        Experiment: 懒加载实验实例
    """
    return Experiment(hdf5_path, cache_size=cache_size)