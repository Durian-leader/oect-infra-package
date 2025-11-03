"""
任务定义 - Step 级并行执行

定义细粒度提取任务和结果的数据结构
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List


@dataclass
class ExtractionTask:
    """细粒度提取任务（Feature × Step × Experiment）

    任务粒度：单特征 + 单step + 单实验
    这是并行执行的最小单位

    Attributes:
        exp_id: 实验ID
        feature_name: 特征名称（如 'gm_max', 'Von', 'transfer'）
        step_idx: Step 索引（None 表示数据源加载任务）
        chip_id: 芯片ID
        device_id: 设备ID
        file_path: HDF5 文件路径
        params: 提取参数
        dependency_layer: 依赖层级（用于分阶段执行）
        input_sources: 输入数据源列表（如 ['transfer'] 或 ['transient']）
    """
    exp_id: int
    feature_name: str
    step_idx: Optional[int]  # None = 数据源加载
    chip_id: str
    device_id: str
    file_path: str
    params: Dict[str, Any]
    dependency_layer: int
    input_sources: List[str] = field(default_factory=list)  # 输入数据源

    def __repr__(self):
        if self.step_idx is None:
            return f"Task(exp={self.exp_id}, src={self.feature_name})"
        return f"Task(exp={self.exp_id}, feat={self.feature_name}, step={self.step_idx})"


@dataclass
class ExtractionResult:
    """提取结果

    从 Worker 进程返回给消费者进程的结果对象

    Attributes:
        exp_id: 实验ID
        feature_name: 特征名称
        step_idx: Step 索引（None 表示数据源）
        data: 提取的数据（标量、数组或None表示失败）
        elapsed_ms: 执行耗时（毫秒）
        error: 错误信息（None 表示成功）
    """
    exp_id: int
    feature_name: str
    step_idx: Optional[int]
    data: Any
    elapsed_ms: float
    error: Optional[str] = None

    @property
    def is_success(self) -> bool:
        """任务是否成功"""
        return self.error is None

    def __repr__(self):
        status = "✅" if self.is_success else "❌"
        if self.step_idx is None:
            return f"Result({status} exp={self.exp_id}, src={self.feature_name}, {self.elapsed_ms:.1f}ms)"
        return f"Result({status} exp={self.exp_id}, feat={self.feature_name}, step={self.step_idx}, {self.elapsed_ms:.1f}ms)"
