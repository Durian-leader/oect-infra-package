# Catalog 模块 - 统一数据管理（HDF5/Parquet 元信息与双向同步）

## 模块概述

`catalog` 提供 OECT 实验数据（HDF5/Parquet）的统一索引、查询与双向同步能力，核心职责：
- 文件发现与元信息提取（原始/特征文件）
- 将文件元信息结构化存入 SQLite 数据库
- 文件系统 ↔ 数据库 的增量/双向同步与冲突处理
- **Workflow 元数据缓存与搜索**（数据库缓存优化，支持按工作流参数搜索）
- 提供统一的高层接口（UnifiedExperiment/Manager）以便访问实验数据、特征与可视化
- 提供命令行工具（CLI）支持初始化、扫描、查询、同步、统计、维护与 Features V2 提取

依赖的相关模块功能请见对应文档：
- 实验数据访问与摘要：详见 `experiment/CLAUDE.md`
- 特征读取与版本矩阵：详见 `features/CLAUDE.md`
- 特征计算流水线（v1）：详见 `features_version/CLAUDE.md`
- 可视化绘图：详见 `visualization/CLAUDE.md`
- **Workflow 参数搜索与元数据导出详细指南**：详见 `catalog/docs/WORKFLOW_SEARCH_GUIDE.md`


## 目录结构

```
catalog/
├── __init__.py                # 包导出与便捷函数
├── __main__.py                # CLI 入口 (python -m catalog)
├── cli.py                     # 命令行实现
├── config.py                  # 配置加载与校验
├── models.py                  # 数据模型与枚举（Pydantic/dataclass）
├── repository.py              # SQLite 持久化层（含 workflow metadata 管理）
├── scanner.py                 # HDF5 扫描与元信息提取
├── sync.py                    # 文件↔数据库 同步与冲突处理
├── service.py                 # 业务服务层（聚合 Scanner/Repository/Sync）
├── unified.py                 # 统一接口（Manager/Experiment）
├── CLAUDE.md                  # 本文档
├── feature_configs/           # 预定义的 Features V2 配置（YAML）
├── examples/                  # V2 集成示例脚本
├── docs/
│   └── WORKFLOW_SEARCH_GUIDE.md   # Workflow 功能详细指南
└── example/
    ├── catalog_config.yaml
    └── catalog.ipynb
```


## 关键约定（扫描与匹配）
- 文件模式（可配置，默认）：
  - 原始数据：`*-test_*.h5`
  - 特征数据：`*-feat_*.h5`
  - V2 特征数据（Parquet）：
    - 新格式：`{chip_id}-{device_id}-{config_name}-feat_*.parquet`（推荐，支持配置名识别）
    - 旧格式：`{chip_id}-{device_id}-v2_*-feat_*.parquet`（向后兼容）
    - 扫描器同时支持两种格式，自动识别
- 元信息解码：统一将 HDF5 attrs 中的 bytes 解码为 UTF-8 字符串。
- 设备编号解析：
  - 若 `attrs['file_type'] == 'feature'`，使用 `attrs['device_id']`
  - 否则使用 `attrs['device_number']`（两者均转为字符串）
- 原始文件与特征文件的关联键：`(chip_id, device_id)`（存在对应即合并到同一记录）


## 对外 API（Python）

以下 API 均来自包内可直接导入或由统一接口暴露，具体实现参考：
- 统一接口：`catalog/unified.py`
- 服务层：`catalog/service.py`
- 配置：`catalog/config.py`
- 模型：`catalog/models.py`

### 1) 统一管理器与统一实验对象

- `UnifiedExperimentManager(config_path: str = 'catalog_config.yaml')`
  - `get_experiment(exp_id: Optional[int] = None, **filters) -> Optional[UnifiedExperiment]`（支持按 `chip_id/device_id/test_id` 等条件）
  - `search(**filters) -> List[UnifiedExperiment]`（**支持 workflow 参数过滤**，以 `workflow_` 开头的参数用于过滤工作流元数据）
  - `get_experiments_by_chip(chip_id) -> List[UnifiedExperiment]`
  - `get_experiments_by_batch(batch_id) -> List[UnifiedExperiment]`
  - `get_completed_experiments() -> List[UnifiedExperiment]`
  - `get_experiments_missing_features() -> List[UnifiedExperiment]`
  - **Workflow 元数据管理**（详见 `docs/WORKFLOW_SEARCH_GUIDE.md`）：
    - `initialize_workflow_metadata(force_update: bool = False) -> Dict`（批量初始化/更新实验的 workflow 元数据到数据库，用于性能优化）
      - 返回字典包含：`total`（总实验数）、`updated`（成功更新数）、`skipped`（跳过数）、`failed`（失败数）、`errors`（错误列表）
      - `force_update=False`：只更新没有 workflow metadata 的实验（增量更新）
      - `force_update=True`：强制更新所有实验（数据修复）
  - 数据预处理/转换（依赖 csv2hdf 与 features_version，细节见对应模块 CLAUDE.md）：
    - `clean_json_files(source_directory, pattern='test_info.json') -> Dict`
    - `discover_test_directories(source_directory, exclude_output_dir=True) -> List[str]`
    - `batch_convert_folders(test_directories, num_workers=20, conflict_strategy='skip', show_progress=True) -> Dict`
    - `process_data_pipeline(source_directory, clean_json=True, num_workers=20, conflict_strategy='skip', auto_extract_features=False, feature_version='v1'|'v2'|'both', v2_feature_config='v2_transfer_basic', show_progress=True) -> Dict`
    - `batch_extract_features(experiments_or_query, version='v1') -> Dict`（V1 提取后建议执行 `scan_and_index(incremental=False)` 以重新关联）
  - 批量导出与组合特征：
    - `export_experiments_info(experiments, output_path) -> bool`
    - `create_combined_features_dataframe(experiments, feature_names, data_type='transfer', include_workflow: bool = False) -> Optional[pd.DataFrame]`（**支持导出 workflow 元数据**，设置 `include_workflow=True` 将 workflow 元数据作为列导出）
  - 一致性与维护：
    - `check_consistency() -> Dict`（调用 `CatalogService.validate_data_integrity`）
    - `auto_fix_inconsistencies(issues=None) -> Dict[str, int]`
  - 生命周期与同步：
    - `create_experiment(source_dir, auto_extract_features=True, feature_versions=None) -> Optional[UnifiedExperiment]`
    - `sync_all() -> Dict`（等价 `CatalogService.bidirectional_sync`）
    - `get_statistics() -> Dict`

- `UnifiedExperiment`（单个实验的统一视图，内部懒加载 `experiment`/`features`/`visualization`）
  - 基本属性：`id/chip_id/device_id/test_id/batch_id/description/status/completion_percentage/is_completed/created_at/completed_at/duration/file_path`
  - 特征可用性：`has_features(version: Optional[str] = None) -> bool`
  - 原始数据：
    - `get_transfer_data(step_index: Optional[int] = None) -> Optional[Dict]`
    - `get_transient_data(step_index: Optional[int] = None) -> Optional[Dict]`
  - 特征数据（依赖 features）：
    - `get_features(feature_names: List[str], data_type: str = 'transfer') -> Optional[Dict[str, np.ndarray]]`
    - `get_feature_matrix(version: str = 'v1', data_type: str = 'transfer') -> Optional[np.ndarray]`
    - `get_feature_dataframe(version: str = 'v1', data_type: str = 'transfer', include_workflow: bool = False) -> Optional[pd.DataFrame]`（**支持导出 workflow 元数据**，设置 `include_workflow=True` 将 workflow 元数据作为列导出）
  - 可视化（依赖 visualization）：
    - `plot_transfer_single(step_index, **kwargs)` / `plot_transfer_multiple(step_indices, **kwargs)`
    - `plot_transfer_evolution(**kwargs)` / `plot_transient_single(step_index, **kwargs)` / `plot_transient_all(**kwargs)`
    - `create_transfer_animation(**kwargs)` / `create_transfer_video(output_path, **kwargs) -> Optional[str]`
    - `get_plotter_experiment_info() -> Optional[Dict]`
  - 摘要/工作流（依赖 experiment）：
    - `get_experiment_summary()` / `get_transfer_summary()` / `get_transient_summary()` / `get_data_summary()`
    - `has_workflow()` / `get_workflow()` / `get_workflow_summary()`
    - `get_workflow_metadata() -> Dict`（**获取扁平化的 workflow 元数据**，优先从数据库缓存读取，性能提升 100 倍）
    - `print_workflow(indent=0, show_all_params=False)` / `export_workflow_json(output_path)` / `export_workflow(output_path)`
  - 步骤级访问：
    - `get_transfer_step_measurement(step_index)` / `get_transient_step_measurement(step_index)`
    - `get_transfer_all_measurement()` / `get_transient_all_measurement()`
    - `get_transfer_step_info_table()` / `get_transient_step_info_table()`
  - 便利属性与信息：`transfer_steps` / `transient_steps` / `get_info() -> Dict`

### 2) Catalog 服务层（程序化使用）

- `CatalogService(config_path: Optional[str] = None, base_dir: Optional[str] = None)`
  - 初始化/配置：
    - `initialize_catalog(force: bool = False) -> Dict`
    - `get_config_info() -> Dict`
  - 扫描与索引：
    - `scan_and_index(scan_paths: Optional[List[str]] = None, incremental: bool = True) -> SyncResult`
    - `index_file(file_path: str) -> Optional[FileRecord]`
  - 查询与检索：
    - `find_experiments(**filter_kwargs) -> List[FileRecord]`
    - `get_experiment_by_id(id) -> Optional[FileRecord]`
    - `get_experiment_by_test_id(test_id) -> Optional[FileRecord]`
    - `search_experiments(query: str, limit: Optional[int] = None) -> List[FileRecord]`
    - `get_experiments_by_chip(chip_id)` / `get_experiments_by_batch(batch_id)`
    - `get_experiments_missing_features()` / `get_completed_experiments()`
  - 同步：
    - `sync_files_to_database(scan_paths=None, incremental=True) -> SyncResult`
    - `sync_database_to_files(experiment_filter: Optional[ExperimentFilter] = None) -> SyncResult`
    - `bidirectional_sync(scan_paths=None, conflict_strategy: Optional[ConflictStrategy] = None) -> SyncResult`
    - `get_sync_status() -> Dict` / `force_resync(experiment_ids: Optional[List[int]] = None) -> SyncResult`
  - 统计与报告：
    - `get_statistics() -> CatalogStatistics`
    - `get_summary_report() -> Dict` / `get_chip_statistics() -> Dict[str, Dict]`
  - 维护：
    - `validate_data_integrity() -> Dict[str, List]`
    - `clean_orphaned_records() -> int`
    - `vacuum_database() -> bool` / `backup_database(backup_path: Optional[str] = None) -> str`
  - 与其他模块集成（按需返回对象，具体功能见对应模块文档）：
    - `get_experiment_file_path(experiment_id, file_type='raw'|'features') -> Optional[str]`
    - `create_experiment_loader(experiment_id)`（来自 `experiment`）
    - `create_feature_reader(experiment_id)`（来自 `features`）
    - `create_plotter(experiment_id)`（来自 `visualization`）
  - 实用：`update_experiment(experiment_id, **updates) -> bool` / `delete_experiment(experiment_id) -> bool`

### 3) 配置与模型

- 配置（`CatalogConfig`，见 `catalog/config.py`）
  - 加载/保存：构造函数自动加载 YAML；`create_default_config(config_path, base_dir=None, auto_detect=True)` 生成默认配置并建目录
  - 目录/路径：`get_absolute_path(path_type, relative_path='')` / `get_relative_path(path_type, absolute_path)` / `get_database_path()` / `get_log_path()`
  - 校验/更新：`validate_config() -> List[str]` / `update_config(updates: Dict)` / `reload_config()` / `to_dict()`
  - 支持的配置段：`roots`、`database`、`sync`、`discovery`、`logging`

- 模型与枚举（见 `catalog/models.py`）
  - `FileRecord`、`SyncHistoryRecord`、`SyncResult`、`ExperimentFilter`、`CatalogStatistics`
  - `ExperimentStatus`、`DeviceType`、`SyncStatus`、`SyncDirection`、`ConflictStrategy`
  - `DatabaseConfig`、`SyncConfig`、`DiscoveryConfig`

- 便捷函数（见 `catalog/__init__.py`）
  - `quick_start(config_path='catalog_config.yaml') -> UnifiedExperimentManager`
  - `init_catalog(config_path='catalog_config.yaml', base_dir=None, auto_detect=True) -> CatalogService`
  - `find_experiments(**filters) -> List[UnifiedExperiment]`（一次性管理器）
  - `get_experiment_by_id(exp_id) -> Optional[UnifiedExperiment]`
  - `sync_all() -> Dict`


## 对外 API（CLI）

入口：`python -m catalog`（或作为库内 `catalog.cli` 调用）。全局选项：`--config <path>`, `--verbose/-v`, `--quiet/-q`。

- `init`：初始化与配置
  - `--root-dir <dir>`、`--auto-config`、`--force`
- `scan`：扫描与索引
  - `--path <dir>`（可多次）、`--recursive`、`--max-depth`、`--incremental`、`--parallel <n>`、`--dry-run`
- `sync`：同步
  - `--direction [both|file2db|db2file]`、`--resolve-conflicts [auto|manual|ignore]`、`--experiment-id <id>`（可多次）、`--batch-size`、`--timeout`
- `query`：查询
  - `--chip`、`--status [completed|running|failed|pending]`、`--device-type [N-type|P-type]`、`--missing-features`、`--date-range YYYY-MM-DD,YYYY-MM-DD`、`--batch-id`、`--text`、`--output [table|json|csv]`、`--file`、`--limit`
- `stats`：统计
  - `--detailed`、`--by-chip`、`--by-date`、`--storage`、`--timeline`、`--days`、`--export`、`--format [json|csv|html]`、`--file`
- `maintenance`：维护
  - `--validate`、`--fix-conflicts`、`--check-files`、`--check-integrity`、`--remove-orphans`、`--vacuum`、`--backup <path>`
 - `v2`：Features V2 特征提取
   - `configs`：列出可用配置
   - `extract --exp-id <id> --feature-config <name> [--output dict|dataframe|parquet]`
   - `extract-batch [--chip <id>] [--device <id>] --feature-config <name> [--workers N] [--force]`
   - `stats [--detailed]`

### 常用示例（批量 V2 提取）
- 推荐在仓库根目录执行（两种等价写法，取决于 `PYTHONPATH`）：
  - `python -m infra.catalog --config catalog_config.yaml v2 extract-batch --feature-config v2_ml_ready --workers 1`
  - `python -m catalog --config catalog_config.yaml v2 extract-batch --feature-config v2_ml_ready --workers 1`
- 说明：
  - 为避免与内部并行（如某些特征实现或后续改造中启用的多进程）发生嵌套冲突，建议将 `--workers` 设为 `1`。
  - 若明确未使用任何内部多进程执行器，可将 `--workers` 提高以按“实验维度”并行加速。


## 使用示例

- 统一接口（推荐）：
```python
from catalog import UnifiedExperimentManager

manager = UnifiedExperimentManager('catalog_config.yaml')
exp = manager.get_experiment(chip_id="#20250804008", device_id="3")
if exp:
    df = exp.get_feature_dataframe('v1', data_type='transfer')  # 依赖 features
    fig = exp.plot_transfer_evolution()  # 依赖 visualization
```

- 服务层扫描与同步：
```python
from catalog import CatalogService

catalog = CatalogService('catalog_config.yaml')
catalog.initialize_catalog()
scan_result = catalog.scan_and_index(incremental=True)
sync_result = catalog.bidirectional_sync()
```

- CLI：
```bash
python -m catalog init --auto-config
python -m catalog scan --path data/raw --recursive
python -m catalog sync --direction both
python -m catalog query --chip "#20250804008" --output table
```


## Features V2 集成

Catalog 模块已完整集成 `features_v2` 特征提取系统，提供统一的 API 和批量处理能力。

### V2 特征提取 API

**单实验提取**（`UnifiedExperiment`）:
- `extract_features_v2(feature_config, output_format='parquet', output_dir=None, save_metadata=True, force_recompute=False) -> Union[Dict, pd.DataFrame, str]`
  - `feature_config`: 配置文件名（如 `'v2_transfer_basic'`）或内联字典
  - `output_format`: `'dict'`, `'dataframe'`, `'parquet'`
  - `force_recompute`: 强制重算（跳过缓存）
  - 自动保存元数据到数据库（`v2_feature_metadata`）
- `has_v2_features(validate_files: bool = True) -> bool` - 检查是否已有 V2 特征，并可自动清理失效的文件记录
- `get_v2_features_metadata(validate_files: bool = True) -> Optional[Dict]` - 获取/校验 V2 特征元数据
- `get_v2_feature_dataframe(config_name: Optional[str] = None, file_path: Optional[str] = None) -> Optional[pd.DataFrame]` - 读取已计算的 V2 特征（优先读取元数据记录的文件，缺失时回退扫描文件系统）
- `sync_v2_features_from_filesystem(auto_remove_missing: bool = True) -> Dict` - 从文件系统扫描并同步元数据（新/旧命名均支持）
- `clear_v2_features_metadata() -> None` - 清空数据库中的 V2 元数据（不删除磁盘文件）

**批量提取**（`UnifiedExperimentManager`）:
- `batch_extract_features_v2(experiments, feature_config, save_format='parquet', n_workers=1, force_recompute=False) -> Dict`
  - 支持多实验并行处理（`n_workers`）
  - 自动跳过已有特征的实验（可通过 `force_recompute` 强制）
  - 返回详细统计：`{'successful': [...], 'failed': [...], 'timings': {...}}`

### 预定义配置

位置: `infra/catalog/feature_configs/`

| 配置文件 | 特征数 | 用途 |
|---------|--------|------|
| `v2_transfer_basic.yaml` | 5 | 基础 Transfer 特征 |
| `v2_quick_analysis.yaml` | 3 | 快速数据探索 |
| `v2_ml_ready.yaml` | 12 | 机器学习训练 |

### V2 使用示例

- 单实验提取:
```python
exp = manager.get_experiment(chip_id="#20250804008", device_id="3")
result_df = exp.extract_features_v2('v2_transfer_basic', output_format='dataframe')
```

- 批量提取:
```python
experiments = manager.search(chip_id="#20250804008")
result = manager.batch_extract_features_v2(
    experiments, 'v2_ml_ready', n_workers=4
)
```

- 内联配置:
```python
result = exp.extract_features_v2({
    'gm_max': {'extractor': 'transfer.gm_max', 'input': 'transfer'}
})
```

### V2 CLI 快速上手

```bash
# 列出可用配置（来自 catalog/feature_configs 与 features_v2/templates）
python -m catalog v2 configs

# 单实验提取（保存为 Parquet 并写入 v2_feature_metadata）
python -m catalog v2 extract --exp-id 123 \
  --feature-config v2_transfer_basic --output parquet

# 批量提取（按芯片筛选 + 并行处理）
python -m catalog v2 extract-batch --chip "#20250804008" \
  --feature-config v2_ml_ready --workers 4

# 查看 V2 特征统计（包含配置使用情况）
python -m catalog v2 stats --detailed
```

### V1 vs V2 对比与共存

| 特性 | V1 | V2 |
|------|----|----|
| **输出格式** | HDF5 | Parquet |
| **文件命名** | `*-feat_*.h5` | 新：`{chip}-{device}-{config}-feat_*.parquet`；旧：`*-v2_features-*.parquet` |
| **配置方式** | 硬编码 | YAML 配置 |
| **多维特征** | ❌ | ✅ |
| **数据库字段** | `feature_file_path` | `v2_feature_metadata` (JSON) |

V1 和 V2 **完全独立**，可同时使用，不会冲突。

详细说明见: `catalog/V2_INTEGRATION_GUIDE.md`


## 重要说明
- 本模块只聚焦索引、同步与统一访问，不在内部计算/生成特征或绘图；这些通过依赖模块完成（详情见相应 CLAUDE.md）。
- 配置文件仅解析 `roots/database/sync/discovery/logging` 段，其他字段若存在会被忽略。
- 数据库存储采用 SQLite（表：`experiments`, `sync_history`），字段与统计口径以 `catalog/repository.py` 与 `catalog/models.py` 为准；V2 元数据字段为 `experiments.v2_feature_metadata`（JSON）。
- 扫描/关联依据文件命名与 HDF5 属性，请确保数据产线遵守命名与属性写入规范。


## 参考文件
- 统一接口：`catalog/unified.py`
- 服务层：`catalog/service.py`
- 同步：`catalog/sync.py`
- 扫描：`catalog/scanner.py`
- 仓库：`catalog/repository.py`
- 配置：`catalog/config.py`
- 模型：`catalog/models.py`
- CLI：`catalog/cli.py`
