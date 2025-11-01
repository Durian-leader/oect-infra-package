# infra 模块（CLAUDE 指南）

本文件仅基于当前代码与提交历史核实后的真实能力，集中说明 `infra/` 包自身的对外接口与常用入口；涉及子模块的实现细节，请查阅对应目录下的 CLAUDE.md。

## 模块定位
- `infra/` 是 OECT（有机电化学晶体管）数据处理的基础设施包，统一收纳数据转换、实验访问、特征工程、可视化、编目与报告等子模块。
- 统一的目录与命名规范使原始数据（HDF5 test）与特征数据（HDF5/Parquet feat）通过 `(chip_id, device_id)` 自动关联。详细规则见 `OECT_UNIFIED_DATA_MANAGEMENT_SYSTEM.md` 与各子模块文档。

## 目录总览（模块详情见对应模块的 CLAUDE.md）
- `csv2hdf/`：CSV+JSON → HDF5 批量转换与并行加速（见 `csv2hdf/CLAUDE.md`）。
- `experiment/`：面向批量 HDF5 的懒加载实验 API（见 `experiment/CLAUDE.md`）。
- `oect_transfer/`：转移特性分析（gm、Von、|I| 及坐标；见 `oect_transfer/CLAUDE.md`）。
- `features/`：特征文件（HDF5）列式存储、版本矩阵与读取（见 `features/CLAUDE.md`）。
- `features_version/`：V1 一键特征提取与版本固化（见 `features_version/CLAUDE.md`）。
- `features_v2/`：声明式特征工程 2.0（DAG 执行、Parquet 导出；见 `features_v2/CLAUDE.md`）。
- `visualization/`：实验数据/特征可视化与并行视频（见 `visualization/CLAUDE.md`）。
- `catalog/`：统一编目/索引/同步 + 统一实验接口 + CLI（见 `catalog/CLAUDE.md`）。
- `stability_report/`：两阶段与三阶段可组合的报告流水线与 CLI（见 `stability_report/CLAUDE.md`）。
- `logger_config.py`：统一日志获取（`get_module_logger`/`log_manager`）。

## 推荐入口与对外 API

### 1) Python 高层入口：统一实验接口（catalog.unified）
- `from catalog import UnifiedExperimentManager, UnifiedExperiment`
- 配置文件默认路径：`catalog_config.yaml`（`infra/` 下已提供示例）。

UnifiedExperimentManager（统一管理器，首选入口）
- 构造：`UnifiedExperimentManager(config_path: str = 'catalog_config.yaml')`
- 单个实验：
  - `get_experiment(exp_id: Optional[int] = None, **filters) -> Optional[UnifiedExperiment]`
  - `get_experiment_by_test_id(test_id: str) -> Optional[UnifiedExperiment]`
- 批量检索：
  - `search(**filters) -> List[UnifiedExperiment]`（支持 workflow 元数据过滤；以 `workflow_` 前缀键匹配，已实现于 `unified.py`）
  - `get_experiments_by_chip(chip_id)` / `get_experiments_by_batch(batch_id)` / `get_completed_experiments()` / `get_experiments_missing_features()`
- 同步/索引：
  - `sync_all() -> Dict`（封装 `bidirectional_sync`）
  - `catalog.scan_and_index(scan_paths=None, incremental=True) -> SyncResult`
- 统计：`get_statistics() -> Dict`
- Workflow 元数据：`initialize_workflow_metadata(force_update: bool = False) -> Dict`
- 特征批量：
  - V1：`batch_extract_features(experiments_or_query, version='v1') -> Dict`
  - V2：`batch_extract_features_v2(experiments_or_query, feature_config, output_dir=None, save_format='parquet', n_workers=1, force_recompute=False) -> Dict`
- 数据管道：`process_data_pipeline(source_directory, clean_json=True, num_workers=20, conflict_strategy='skip', auto_extract_features=False, feature_version='v1'|'v2'|'both', v2_feature_config='v2_transfer_basic', show_progress=True) -> Dict`

UnifiedExperiment（统一实验对象）
- 数据访问：
  - `get_transfer_data(step_index: Optional[int] = None) -> Optional[Dict]`
  - `get_transient_data(step_index: Optional[int] = None) -> Optional[Dict]`
- 特征读取（V1/HDF5）：
  - `get_features(feature_names: List[str], data_type='transfer') -> Optional[Dict[str, np.ndarray]]`
  - `get_feature_matrix(version='v1', data_type='transfer') -> Optional[np.ndarray]`
  - `get_feature_dataframe(version='v1', data_type='transfer', include_workflow=False) -> Optional[pd.DataFrame]`
- 特征计算与读取（V2/Parquet）：
  - `has_v2_features(validate_files: bool = True) -> bool`
  - `get_v2_features_metadata(validate_files: bool = True) -> Optional[Dict]`
  - `get_v2_feature_dataframe(config_name: Optional[str] = None, file_path: Optional[str] = None) -> Optional[pd.DataFrame]`
  - `extract_features_v2(feature_config, output_format='parquet'|'dataframe'|'dict', output_dir=None, save_metadata=True, force_recompute=False) -> Union[str, pd.DataFrame, Dict]`
  - `clear_v2_features_metadata() -> None`
- 可视化（包装 `visualization.OECTPlotter`）：
  - `plot_transfer_single/plot_transfer_multiple/plot_transfer_evolution`
  - `plot_transient_single/plot_transient_all`
  - `create_transfer_animation/create_transfer_video`
- 摘要/工作流：
  - `get_experiment_summary()` / `get_transfer_summary()` / `get_transient_summary()`
  - `has_workflow()` / `get_workflow()` / `get_workflow_summary()` / `print_workflow()` / `export_workflow_json()`

> 具体签名、返回结构与边界条件均以 `infra/catalog/unified.py` 的实现为准。

### 2) CLI 入口
- Catalog CLI：
  - 常用：`python -m infra.catalog ...`（仓库根目录执行）
  - 备用：`python -m catalog ...`（当 `infra` 已加入 `PYTHONPATH` 时）
  - `init | scan | sync | query | stats | maintenance`（详见 `catalog/CLAUDE.md`）
  - `v2` 子命令（Features V2 集成）：`configs | extract | extract-batch | stats`（已实现于 `catalog/cli.py`）
- 稳定性报告 CLI：`python -m stability_report.reporting.cli`（组合式三阶段：assets/slides/reports；见 `stability_report/CLAUDE.md`）

常用批量 V2 提取命令（建议用法）
- `python -m infra.catalog --config catalog_config.yaml v2 extract-batch --feature-config v2_ml_ready --workers 1`
- 说明：
  - 为避免与特征内部并行（例如并行执行器或某些工具函数的多进程实现）发生嵌套冲突，建议 `--workers 1`；若明确未启用内部多进程，可增大 `--workers` 提升“跨实验”并行度。

## 子模块能力速记（只列对外名称）
- csv2hdf（见 `csv2hdf/CLAUDE.md`）
  - `process_folders_parallel(...) -> List[JobResult]`
  - `batch_clean_json_files(...)`
  - 直接/并行单实验转换：`direct_convert_csvjson_to_hdf5(...)` 等
- experiment（见 `experiment/CLAUDE.md`）
  - `Experiment`、`load_experiment(...)` 及 `get_*_summary/measurement` 等懒加载接口
- features（见 `features/CLAUDE.md`）
  - `FeatureFileCreator`、`FeatureRepository`、`VersionManager`、`FeatureReader`、`BatchManager`
- features_v2（见 `features_v2/CLAUDE.md`）
  - `FeatureSet`：DAG 计算图、增量计算（需 `unified_experiment` + `config_name`）
  - `save_as_config()`：配置固化（YAML + Parquet）
  - 内置提取器注册（`transfer.*` / `transient.*`）
  - 增量工作流示例：`examples/incremental_workflow_demo.py`
- visualization（见 `visualization/CLAUDE.md`）
  - `OECTPlotter`、`ChipFeaturePlotter`、`plot_chip_feature`
- catalog（见 `catalog/CLAUDE.md`）
  - `CatalogService`、`UnifiedExperimentManager/UnifiedExperiment`、CLI
- stability_report（见 `stability_report/CLAUDE.md`）
  - 两阶段脚本 `stability_report_pipeline_v2.py` 与组合式 CLI `reporting/cli.py`
- 日志（当前仓库内）：`logger_config.get_module_logger()` / `logger_config.log_manager`

## 常见工作流（按真实实现）
- 原始→编目：使用 `csv2hdf.process_folders_parallel` 生成 HDF5；随后 `python -m catalog scan` 或 `UnifiedExperimentManager.sync_all()` 建索引并同步。
- 实验探索：`manager.get_experiment(...).get_transfer_data()/get_transient_data()`；需要绘图时直接用 `exp.plot_*`。
- 特征（V1）：`UnifiedExperimentManager.batch_extract_features(...)` 生成/补齐 HDF5 特征并在需要时 `scan_and_index(...)` 重建索引。
- 特征（V2）：通过 `catalog v2` 子命令或 `UnifiedExperiment.extract_features_v2(...)`/`manager.batch_extract_features_v2(...)` 计算并落地 Parquet，元数据写回数据库，可用 `get_v2_feature_dataframe()` 读取。
- 报告：依场景选择 `stability_report_pipeline_v2.py`（两阶段）或 `python -m stability_report.reporting.cli`（可组合三阶段）。

## 文档与配置
- `catalog_config.yaml`：Catalog 所需目录/数据库配置（`infra/` 下已提供示例）。
- 详细 API、约束与异常说明：见各子模块 `CLAUDE.md` 与 `catalog/docs/WORKFLOW_SEARCH_GUIDE.md`。

以上内容仅覆盖 `infra/` 包内已实现的能力；涉及依赖模块的细节请查阅各自文档，不在此处复述。
