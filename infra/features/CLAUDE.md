# features 模块（说明与用法）

本模块负责“特征文件”的创建、列式存储、版本化矩阵固化与高效读取，底层使用 HDF5。本文仅描述本模块自身的能力与文件结构，不涉及外部模块。

---

## 一、对外 API（从 `features` 直接导入）

- `FeatureFileCreator`
  - `create_feature_file(filepath, chip_id, device_id, description, test_id=None, built_with=None, feature_tool_hash=None, **kwargs) -> str`
  - `create_from_raw_file(raw_filepath, output_dir=None, built_with=None, feature_tool_hash=None) -> str`
  - `initialize_buckets(filepath, data_type, bucket_names) -> None`
  - `validate_file_structure(filepath) -> dict`
  - 实用函数：`generate_feature_filename(...) -> str`, `parse_raw_filename_to_feature(raw_filename) -> str`

- `FeatureRepository(filepath)`
  - 写入：`store_feature(name, data: np.ndarray, data_type='transfer', metadata: FeatureMetadata=None, bucket_name=None, overwrite=False) -> bool`
  - 批量写入：`store_multiple_features(features: Dict[str, np.ndarray], data_type='transfer', metadata_dict=None, bucket_name=None, overwrite=False) -> Dict[str, bool>`
  - 读取：`get_feature(name, data_type='transfer') -> Optional[np.ndarray]`
  - 批量读取：`get_multiple_features(names, data_type='transfer') -> Dict[str, Optional[np.ndarray]]`
  - 按桶读取：`get_features_by_bucket(bucket_name, data_type='transfer') -> Dict[str, np.ndarray]`
  - 索引与查询：`list_features(data_type='transfer') -> List[str]`, `get_feature_info(name, data_type='transfer') -> Optional[FeatureInfo]`, `get_registry(data_type='transfer') -> Optional[FeatureRegistry]`, `search_features(keyword, search_in=['name','description','alias']) -> List[FeatureInfo]`
  - 维护：`delete_feature(name, data_type='transfer') -> bool`, `get_statistics(data_type='transfer') -> Dict[str, Any]`

- `VersionManager(repository: FeatureRepository)`
  - 创建版本：`create_version(version_name, feature_names, data_type='transfer', feature_units=None, feature_descriptions=None, feature_aliases=None, force_overwrite=False) -> bool`
  - 读取版本：`get_version(version_name, data_type='transfer') -> Optional[VersionedFeatures]`, `get_version_matrix(version_name, data_type='transfer') -> Optional[np.ndarray]`
  - 管理版本：`list_versions(data_type='transfer') -> List[str]`, `delete_version(version_name, data_type='transfer', update_registry=True) -> bool`, `compare_versions(v1, v2, data_type='transfer') -> Dict[str, Any]`, `get_version_statistics(version_name, data_type='transfer') -> Dict[str, Any]`

- `FeatureReader(filepath)`（面向使用侧的便捷读取）
  - 版本化读取：`get_version_matrix(version='latest', data_type='transfer', use_cache=True) -> Optional[np.ndarray]`, `get_version_dataframe(version='latest', data_type='transfer', feature_names=None) -> Optional[pd.DataFrame]`
  - 列式读取：`get_features(feature_names, data_type='transfer', as_dataframe=False) -> Union[Dict[str, np.ndarray], pd.DataFrame, None]`, `get_feature(name, data_type='transfer') -> Optional[np.ndarray]`, `get_features_by_bucket(bucket_name, data_type='transfer', as_dataframe=False)`
  - 信息与导出：`list_versions(...)`, `list_features(...)`, `get_feature_info(...)`, `search_features(...)`, `get_summary() -> Dict[str, Any]`, `export_features(output_path, feature_names=None, version=None, data_type='transfer', format='csv'|'parquet'|'h5') -> bool`, `clear_cache()`

- `BatchManager(features_dir)`（批量场景）
  - 文件发现与筛选：`list_all_files()`, `find_files(...)`, `refresh_file_list()`
  - 批量读取：`batch_read_features(...)`, `batch_read_version_matrices(...)`
  - 聚合与导出：`create_combined_dataframe(...)`, `aggregate_features(...)`, `export_batch_features(...)`, `get_feature_statistics(...)`, `find_common_features(...)`, `get_directory_statistics()`

- 数据模型（便于类型提示与序列化）：`FeatureData`, `FeatureMetadata`, `VersionedFeatures`, `FeatureRegistry`, `FeatureInfo`

---

## 二、HDF5 文件结构（标准化约定）

文件名规范：`{chip_id}-{device_id}-{description}-feat_{timestamp}_{hash}.h5`

根组 Attributes（关键项）
- `chip_id`, `device_id`, `description`, `test_id`
- `file_type='feature'`, `format_version='feature_v1.0'`, `created_at`
- 可选：`built_with`, `feature_tool_hash`
- 统计与可用性：`has_transfer_features`/`has_transient_features`（bool），`total_transfer_features`/`total_transient_features`（int）
- 可用版本：`transfer_versions`、`transient_versions`（字符串列表）

目录组织
```
/                                    # 根
├── transfer/                        # Transfer 特征区
│   ├── columns/                    # 列式仓库
│   │   ├── buckets/               # 分桶存储（bk_00, bk_01, ...）
│   │   │   └── bk_xx/
│   │   │       └── <feature_name>        [Dataset: (n_steps,) float32]
│   │   │           └── attrs: unit, description, created_at
│   │   └── _registry/             # 特征注册表（HDFView 友好）
│   │       ├── table              [Dataset: 结构化数组，见下]
│   │       ├── by_name/           [Group: 软链接，name -> 实际数据集路径]
│   │       ├── buckets            [Dataset: 结构化数组，可选]
│   │       └── versions           [Dataset: 结构化数组，可选]
│   └── versions/                  # 版本化矩阵区
│       └── vN/                    # 版本名称（如 v1, v2）
│           ├── matrix             [Dataset: (n_steps, n_features) float32]
│           ├── feature_names      [Dataset: (n_features,) str(len=32)]
│           ├── feature_units      [Dataset: (n_features,) str(len=8)]（可选）
│           ├── feature_descriptions [Dataset: (n_features,) str(len=64)]（可选）
│           └── feature_aliases    [Dataset: (n_features,) str(len=16)]（可选）
│           └── attrs: version, data_type, created_at, feature_count, step_count, matrix_shape,
│                     description, format_version='v1.0', is_finalized=True
└── transient/                      # Transient 特征区（结构同上）
```

注册表结构化数组（`/transfer|transient/columns/_registry/table`）
- 字段与长度（固定长度字符串，HDFView 友好）：
  - `name(32)`, `unit(8)`, `description(64)`, `alias(16)`, `data_type(16)`
  - `bucket(16)`, `hdf5_path(128)`, `version(16)`, `version_index(int32)`
  - `is_active(bool)`, `is_versioned(bool)`, `created_at(32)`, `updated_at(32)`
- `by_name/` 下为指向实际数据集的软链接，便于快速定位。

压缩与分块
- 列式特征：`compression='gzip'`, `compression_opts=6`, `shuffle=True`, `chunks=(min(n_steps, 16384),)`；`dtype=float32`
- 版本矩阵：`compression='gzip'`, `compression_opts=6`, `shuffle=True`, `chunks=(min(n_steps, 1024), n_features)`；`dtype=float32`

桶策略
- 默认每桶最多约 20 个特征（自动分配 `bk_00`, `bk_01`, ...）。

兼容性
- 读取侧兼容“简化路径”`{data_type}/{feature_name}`（若存在），并优先通过软链接与注册表解析旧结构。

---

## 三、典型用法

创建文件并写入列式特征
```python
from features import FeatureFileCreator, FeatureRepository, FeatureMetadata
import numpy as np

creator = FeatureFileCreator()
feature_file = creator.create_feature_file(
    filepath="/data/features/#20250804008-3-稳定性测试-feat_20250815134211_3fa6110a.h5",
    chip_id="#20250804008", device_id="3", description="稳定性测试",
)

repo = FeatureRepository(feature_file)
repo.store_feature(
    "gm_max_forward",
    np.asarray([1e-6, 2e-6, 1.5e-6], dtype=np.float32),
    metadata=FeatureMetadata(name="gm_max_forward", unit="S", description="正向扫描最大跨导"),
)
```

创建版本化矩阵并读取
```python
from features import VersionManager, FeatureReader

vm = VersionManager(repo)
vm.create_version(
    version_name="v1",
    feature_names=["gm_max_forward"],
    data_type="transfer",
    feature_units=["S"],
)

reader = FeatureReader(feature_file)
matrix = reader.get_version_matrix("v1", "transfer")  # (n_steps, n_features)
```

导出特征
```python
from features import FeatureReader
reader = FeatureReader(feature_file)
reader.export_features("/tmp/features_v1.csv", version="v1", data_type="transfer", format="csv")
```

---

## 四、设计要点与约束

- 同一实验内的所有列式特征必须长度一致（与步骤数匹配），版本矩阵按列堆叠这些一维特征。
- 已创建的版本视为固化（`is_finalized=True`），若需变更请创建新版本。
- 注册表使用结构化数组与固定长度字符串，便于 HDFView 直接查看与检索。

如需扩展字段或数据类型，保持上述目录/属性约定与压缩策略一致即可。

