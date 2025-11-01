# csv2hdf 模块（说明与用法）

本模块用于将每个实验目录中的 CSV 测量数据与 `test_info.json` 元数据直接转换为结构化、压缩的 HDF5 文件。对外主要接口是 `process_folders_parallel`，负责批量并行处理多个实验目录并落地标准化的 `.h5` 文件。

---

## 一、对外 API

以下均可从 `csv2hdf` 包直接导入（见 `__init__.py`）：

- `process_folders_parallel(folders, out_dir, num_workers=None, json_name='test_info.json', conflict_strategy='overwrite'|'skip'|'rename', show_progress=True) -> List[JobResult]`
  - 批量并行将多个目录中的 CSV+JSON 转为 HDF5。
  - 文件命名由 JSON 的四个字段拼接：`chip_id-device_number-description-test_id.h5`；缺失字段自动用 `NA` 代替，并做文件名安全化。
  - 冲突策略：
    - `overwrite` 覆盖同名文件
    - `skip` 已存在则跳过
    - `rename` 自动追加 `_2/_3/...` 保证唯一
  - 返回 `JobResult` 列表。`JobResult` 字段：`folder, h5_path, ok, message, steps, csv_written(None), workflow_stored(bool|None), skipped`。

- `batch_clean_json_files(directory, pattern='test_info.json')`
  - 批量清理目录树内的 `test_info.json`：移除冗余、扁平化 `metadata/summary` 等，便于后续命名与属性写入。

- 直接/并行单实验转换（通常无需直接调用，供高级用例）：
  - `direct_convert_csvjson_to_hdf5(source_dir, output_h5_path, enable_parallel=True, max_workers=None)`
  - `direct_csv_to_new_hdf5(json_path, csv_dir, output_h5_path)`
  - `direct_csv_to_new_hdf5_parallel(json_path, csv_dir, output_h5_path, max_workers=None, enable_parallel=True)`

- CSV 并行处理辅助（仅当你需要自定义流水线时）：
  - `parallel_process_csv_files(tasks, max_workers=None, show_progress=True)`
  - `optimize_process_count(num_tasks, max_workers=None) -> int`

提示：常规批量生产场景建议仅使用 `process_folders_parallel`。

---

## 二、输入目录要求

- 每个源目录至少包含：
  - `test_info.json`（可通过 `json_name` 参数自定义文件名）
  - 若干与步骤对应的 CSV 文件（见后述匹配规则）
- 可选：`workflow.json`（若存在，会原样写入 HDF5 `raw/workflow`）

CSV 匹配规则（每个 step）：
- 优先在步骤信息中递归查找以 `.csv` 结尾的文件名字段，并在目录下定位该文件。
- 否则按模式回退查找：`{step_index}_*.csv`、`step{step_index}_*.csv`、`{step_index}.csv`（step 从 1 开始）。

列名约定：
- transfer：`Vg` 与 `Id`（也会尝试 `gate_voltage/vg` 与 `drain_current/id` 的宽松匹配）
- transient：`Time` 与 `Id`（也会尝试 `timestamp/time` 与 `drain_current/id`）

---

## 三、生成的 HDF5 文件结构

文件组织与属性写入由 `direct_csv2hdf.py` 与 `batch_csvjson2hdf.py` 实现。核心思想：
- transfer 步骤以 3D 数组批量化存储：[step_index, data_type, data_point]
- transient 步骤先按顺序拼接所有步骤，再以 2D 数组存储：[data_type, data_point]
- 同时将步骤元信息以结构化表存一份，便于检索与笛卡尔关联

顶层（root）
- Attributes
  - `format_version`: `2.0_direct_new_storage`（串行直写）或 `2.0_new_storage`（并行直写）
  - 复制 `test_info.json` 的根级简单字段为属性（字符串按 UTF‑8 存储）
  - 由批处理写入的溯源属性（见下）：
    - `source_folder_name`, `source_folder_path`, `source_json_name`, `export_time_utc`
    - `chip_id`, `device_number`, `description`, `test_id`（来自 JSON，用于自描述与索引）
    - `output_filename`（最终输出文件名）

- 组 `raw/`
  - 数据集 `json`：完整 `test_info.json` 文本（UTF‑8）
  - 数据集 `workflow`（可选）：完整 `workflow.json` 文本（UTF‑8）

- 组 `transfer/`（若存在 transfer 步骤）
  - 数据集 `measurement_data`：float64，形状 `[n_steps, 2, max_points]`
    - 属性 `dimension_labels`：`['step_index','data_type','data_point']`
    - 属性 `data_type_labels`：`['Vg','Id']`
    - 属性 `description`
    - 说明：各步长度对齐到 `max_points`，右侧用 `NaN` 填充
  - 数据集 `step_info_table`：结构化数组（由 pandas DataFrame 写入）
    - 属性 `columns`：列名数组
    - 属性 `description`
    - 字段来源：`step_index/type/start_time/end_time/reason/data_file`，以及展平后的 `parameters.*`、`workflow_info.*`

- 组 `transient/`（若存在 transient 步骤）
  - 数据集 `measurement_data`：float64，形状 `[3, total_points]`
    - 属性 `dimension_labels`：`['data_type','data_point']`
    - 属性 `data_type_labels`：`['continuous_time','original_time','drain_current']`
    - 属性 `description`
    - 说明：将所有 transient 步骤按顺序拼接；`continuous_time` 基于 `timeStep(ms)` 生成并确保跨步连续
  - 数据集 `step_info_table`：结构化数组（同上）

压缩与校验（对上述数据集统一生效）：
- `compression='gzip', compression_opts=4, shuffle=True, fletcher32=True`

---

## 四、核心行为与细节

- 文件命名：从清理后的 JSON 根级字段读取 `chip_id/device_number/description/test_id`；缺失用 `NA`，并替换非法文件名字符；冲突按策略处理（覆盖/跳过/重命名）。
- 溯源标注：批处理在写入完成后追加顶层属性，记录来源目录、JSON 文件名、导出时间等。
- 容错：若某步未找到 CSV 或列名不匹配，将跳过该步并记录日志，不中断其余步骤/目录。
- 编码：CSV 读取尝试 `utf-8`、`utf-8-sig`、`gbk`；HDF5 字符串使用 UTF‑8 可变长或字节串按需存储。

---

## 五、最简用法示例

```python
from csv2hdf import process_folders_parallel

folders = [
    "/data/exp/A1",
    "/data/exp/A2",
]
results = process_folders_parallel(
    folders,
    out_dir="/data/h5_out",
    conflict_strategy="rename",   # 或 'overwrite' / 'skip'
)

ok = sum(r.ok for r in results)
skipped = sum(r.skipped for r in results)
print(f"OK={ok}, SKIP={skipped}, FAIL={len(results)-ok}")
```

---

## 六、与并行 CSV 处理的关系（可选）

`direct_csv_to_new_hdf5_parallel` 内部会利用 `parallel_csv_processing.py` 对单实验内的多步 CSV 并行解析，再写入同样的 HDF5 结构；顶层 `process_folders_parallel` 则是在“目录粒度”上做并行。若无特殊需求，无需直接调用这些底层函数。

---

如需扩展字段或新增数据类型，请保持：
- 数据在测量维度（步/类型/点）上的一致性
- 伴随的 `step_info_table` 字段同步更新
- 顶层溯源与 `raw/json` 的可追溯性

