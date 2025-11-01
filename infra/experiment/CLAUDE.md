# experiment 模块（CLAUDE 指南）

本文件面向 AI 与人类协作，简明说明 `experiment` 模块的定位、可直接使用的对外 API 及其返回/约束，避免臆测，仅依据代码实现。

## 模块定位
- 面向 OECT 实验数据的读取与分析，专为“批量格式”HDF5 数据懒加载优化。
- 采用“元数据→摘要→按需数据”的三级懒加载与缓存策略，减少内存占用与I/O。

## 顶层导出（public API）
从 `experiment` 包可直接导入以下名称：
- 核心类
  - `Experiment(hdf5_path: str, cache_size: int = 20)`：主入口，基于批量格式HDF5 的懒加载实验对象。
- 便利函数
  - `load_experiment(hdf5_path: str) -> Experiment`
- 数据模型（Pydantic/结构化数据）
  - `ExperimentAttributes`
  - `TransferStepConfig`, `TransientStepConfig`, `OutputStepConfig`, `LoopConfig`
  - `WorkflowStep`, `Workflow`
  - `StepInfo`, `TransferData`, `TransientData`
  - `WorkflowInfo`, `IterationInfo`
  - `BatchExperimentData`
- 服务类（业务逻辑）
  - `ExperimentService`, `WorkflowService`
- 仓库类（数据访问层）
  - `BaseRepository`, `HDF5Repository`, `BatchHDF5Repository`
- 元信息
  - `__version__`, `__author__`

注：顶层导出以 `experiment/__init__.py` 的 `__all__` 为准。

## Experiment 实例能力
- 属性与基础信息
  - `get_attributes() -> ExperimentAttributes`
  - `to_dict() -> dict`
  - `get_progress_info() -> dict`
  - `get_test_info() -> dict`
  - `get_test_unit_info() -> dict`
  - `get_device_info() -> dict`
  - `get_timing_info() -> dict`
  - `get_experiment_summary() -> dict`
- 工作流
  - `has_workflow() -> bool`
  - `get_workflow() -> Optional[Workflow]`
  - `get_workflow_summary() -> dict`
  - `print_workflow(indent: int = 0, show_all_params: bool = False) -> None`
  - `export_workflow_json(output_path: str, indent: int = 2) -> bool`
  - `export_workflow(output_path: str) -> bool`（同上，兼容旧命名）
- 高效摘要（仅基于元数据，避免加载大数组）
  - `get_transfer_summary() -> Optional[dict]`
  - `get_transient_summary() -> Optional[dict]`
  - `get_data_summary() -> dict`
  - `has_transfer_data() -> bool`
  - `has_transient_data() -> bool`
- 按需加载测量数据（推荐）
  - `get_transfer_step_measurement(step_index: int) -> Optional[dict]`
    - 返回键：`'Vg'`, `'Id'`（numpy 数组）
    - 索引从 0 开始（0-based）
  - `get_transient_step_measurement(step_index: int) -> Optional[dict]`
    - 返回键：`'continuous_time'`, `'original_time'`, `'drain_current'`
    - 索引从 0 开始（0-based）
  - 步骤信息表
    - `get_transfer_step_info_table() -> Optional[pd.DataFrame]`
    - `get_transient_step_info_table() -> Optional[pd.DataFrame]`
- 全量数据访问（谨慎使用，可能占用大量内存）
  - `get_transfer_all_measurement() -> Optional[dict]`
    - 返回键：`'measurement_data'`(3D数组), `'data_info'`
  - `get_transient_all_measurement() -> Optional[dict]`
    - 返回键：`'continuous_time'`, `'original_time'`, `'drain_current'`
- 批量数据对象
  - `get_batch_data() -> LazyBatchExperimentData`（懒加载封装，含 transfer/transient 子对象）
- 缓存与性能
  - `clear_cache() -> None`
  - `get_cache_stats() -> dict`
  - `optimize_cache_for_sequential_access(data_type: str = 'transfer', max_steps: int = 10) -> None`

约束与错误：
- 非批量格式 HDF5 或文件不存在：在构造 `Experiment` 时抛出 `ValueError` / `FileNotFoundError`。
- 步骤索引：`Experiment` 的按需加载接口使用 0-based 索引。

## 服务与仓库（扩展/高级用法）
- ExperimentService（基于仓库的基础信息聚合）
  - `get_attributes()`, 各类 `get_*_info()`，`get_experiment_summary()`，以及进度/完成度等便捷方法。
- WorkflowService（工作流解析/展示/导出）
  - `get_workflow()`, `has_workflow()`, `get_workflow_summary()`, `print_workflow(...)`, `export_workflow_json(...)`。
- 仓库层
  - `BaseRepository`：抽象接口（`load_attributes()`, `load_workflow()`, `has_workflow()`, `load_step_info()`, `load_step_data()`）。
  - `HDF5Repository`：传统逐步数据格式的实现（按步骤1-based读取，供兼容/非批量格式场景）。
  - `BatchHDF5Repository`：批量格式懒加载实现，提供：
    - 元数据/摘要：`get_transfer_summary()`, `get_transient_summary()` 等
    - 步骤信息表懒加载：`get_transfer_step_info_table()`, `get_transient_step_info_table()`
    - 按需单步数据：`get_transfer_step_data(step_index: int)`, `get_transient_step_data(step_index: int)`（0-based）
    - 批量数据包装：`load_batch_data() -> LazyBatchExperimentData`
    - 工作流：`has_workflow()`, `load_workflow_json()`
    - 缓存管理：`clear_cache()`, `get_cache_stats()`

## 版本与作者
- `__version__ = "2.0.0"`
- `__author__ = "科学数据处理团队"`

## 最小示例
```python
from experiment import Experiment
exp = Experiment('path/to/experiment.h5')
print(exp.get_progress_info())
if exp.has_workflow():
    exp.print_workflow()
summary = exp.get_data_summary()
step = exp.get_transfer_step_measurement(0)
```

