# features_version 模块说明（中文）

本模块提供“特征文件生成 + 版本化管理”的实用封装，围绕 Transfer 数据的一键式特征提取（v1）、批量处理与通用版本矩阵创建/校验等能力展开。模块依赖以下内部子系统（细节见各自 CLAUDE.md）：
- `features`：特征文件的创建、读取、写入与版本管理（见 `features/CLAUDE.md`）
- `experiment`：原始实验数据的读取与概要信息获取（见 `experiment/CLAUDE.md`）
- `oect_transfer`：Transfer 数据的批量分析与特征计算（见 `oect_transfer/CLAUDE.md`）

## 目录结构

```
features_version/
├── v1_feature.py              # V1：一键提取/写入 Transfer 特征并创建版本
├── batch_create_feature.py    # 批量遍历原始文件并调用自定义处理函数
├── create_version_utils.py    # 通用：基于仓库内“已存储特征”创建/校验版本
└── example/                   # Jupyter 示例（可选）
```

## 对外 API（函数）

- `v1_feature(raw_file_path: str, output_dir: str = "data/features") -> str`
  - 作用：
    - 基于原始实验文件提取 Transfer 特征并写入 HDF5 特征文件（代码注释标明兼容 HDFView 浏览）。
    - 若目标特征文件不存在，则通过 `features.FeatureFileCreator` 新建基础结构；存在则复用并覆盖对应特征数据。
    - 写入完成后，调用通用版本化工具创建版本矩阵（版本名固定为 `"v1"`，数据类型为 `"transfer"`），并执行结构校验。
  - 输入：
    - `raw_file_path`：原始实验 H5 文件路径。
    - `output_dir`：输出目录，默认 `data/features`。
  - 返回：生成（或更新）的特征文件完整路径字符串。
  - 依赖与数据流：
    - `experiment.Experiment`：读取实验概要与 Transfer 数据。
    - `oect_transfer.BatchTransfer`：从 3D Transfer 数据计算特征（内部固定 `device_type="N"`）。
    - `features.FeatureRepository`：写入特征到 `data_type="transfer"`、`bucket_name="bk_00"`，覆盖写入（`overwrite=True`）。
    - `create_version_from_all_features(...)`：基于“仓库内此数据类型的全部可读特征”创建版本矩阵并校验。
  - 输出特征键（逐步数组）：
    - 数值类：`absgm_max_forward`、`absgm_max_reverse`、`Von_forward`、`Von_reverse`、`absI_max_raw`
    - 坐标类：
      - `absgm_max_forward_Vg`、`absgm_max_forward_Id`
      - `absgm_max_reverse_Vg`、`absgm_max_reverse_Id`
      - `Von_forward_Vg`、`Von_forward_Id`
      - `Von_reverse_Vg`、`Von_reverse_Id`
      - `absI_max_raw_Vg`、`absI_max_raw_Id`
    - 元数据单位在函数内按名称规则赋值：包含 `gm`→`S`，包含 `Von`→`V`，包含 `absI`→`A`，其余为空字符串。
  - 异常：若原始文件不含可用 Transfer 数据，将抛出 `ValueError`。
  - 文件命名：目标文件名由 `features.FeatureFileCreator.parse_raw_filename_to_feature(...)` 从原始文件名推导。

- `batch_create_features(source_directory: str, output_dir: str, processing_func: Callable[[str, str], str]) -> None`
  - 作用：遍历 `source_directory` 下所有匹配 `*-test_*.h5` 的原始文件，逐个调用 `processing_func(raw_file_path, output_dir)` 进行处理（如 `v1_feature`）。
  - 行为：
    - 使用 `tqdm` 展示进度；单个文件出错不会中断整体流程；处理完在控制台与日志输出统计结果。
  - 参数：
    - `source_directory`：原始数据目录（按通配符 `*-test_*.h5` 搜索）。
    - `output_dir`：特征文件输出目录。
    - `processing_func`：接收 `(raw_file_path, output_dir)` 并返回生成的特征文件路径字符串。
  - 返回：无（统计信息打印到标准输出并写入日志）。

- `create_version_from_all_features(repo: FeatureRepository, version_name: str, exp: Experiment, data_type: str = "transfer", include_verification: bool = True) -> bool`
  - 作用：从给定 `repo` 中“当前 `data_type` 下已存储且可读取”的所有特征构建版本矩阵，并可选执行校验。
  - 行为：
    - 通过 `repo.list_features(data_type)` 枚举特征；用 `repo.get_feature(...)` 过滤不可读项。
    - 对于可读特征，调用 `repo.get_feature_info(...)` 读取单位与描述（如不存在则使用默认占位）。
    - 使用 `features.VersionManager.create_version(...)` 创建版本矩阵（`force_overwrite=True`）。版本矩阵的物理写入位置与格式由 `features` 模块定义。
    - `include_verification=True` 时调用下述校验函数。
  - 参数：
    - `repo`：`FeatureRepository` 实例。
    - `version_name`：版本名称（如 `"v1"`、`"v2"`）。
    - `exp`：`Experiment` 实例，用于记录/日志中的步骤数信息。
    - `data_type`：`"transfer"` 或 `"transient"`（仅影响枚举与矩阵归类）。
    - `include_verification`：是否在创建后执行校验。
  - 返回：是否成功创建并（如启用）通过校验。

- `verify_feature_file_structure(repo: FeatureRepository, version_manager: VersionManager, version_name: str, version_features: List[str], data_type: str = "transfer") -> bool`
  - 作用：最小化检查以验证文件结构可读性。
  - 行为：
    - 读取一个示例特征 `repo.get_feature(...)` 验证数据可读。
    - 读取版本矩阵 `version_manager.get_version_matrix(...)` 验证矩阵存在且可读。
  - 返回：校验是否通过。

## 使用示例

- 单文件一键处理（V1）：
  ```python
  from features_version.v1_feature import v1_feature

  feature_file = v1_feature("path/to/raw.h5", output_dir="data/features")
  print(feature_file)
  ```

- 批量处理：
  ```python
  from features_version.batch_create_feature import batch_create_features
  from features_version.v1_feature import v1_feature

  batch_create_features(
      source_directory="data/raw/",
      output_dir="data/features/",
      processing_func=v1_feature,
  )
  ```

- 自定义创建版本（基于仓库中已写入的特征）：
  ```python
  from features import FeatureRepository
  from experiment import Experiment
  from features_version.create_version_utils import create_version_from_all_features

  repo = FeatureRepository("path/to/feature.h5")
  exp = Experiment("path/to/raw.h5")

  ok = create_version_from_all_features(
      repo=repo,
      version_name="vX",
      exp=exp,
      data_type="transfer",
      include_verification=True,
  )
  ```

## 约束与注意事项

- 输入文件需包含可用的 Transfer 数据；否则 `v1_feature` 会抛出 `ValueError`。
- `v1_feature` 将把特征写入 `data_type="transfer"`、`bucket_name="bk_00"`，并使用覆盖模式。
- 版本创建会包含“仓库中该数据类型下所有可读特征”，不仅限于本次新写入的键；同名版本会被强制覆盖。
- 目标特征文件名由 `features.FeatureFileCreator.parse_raw_filename_to_feature(...)` 从原始文件名推导；基础文件结构通过 `FeatureFileCreator.create_feature_file(...)` 新建。
- 模块日志通过 `logger_config.get_module_logger()` 记录到控制台/文件。

以上内容仅描述 `features_version` 模块本身；涉及读取/写入细节、特征仓库格式、实验数据结构与 Transfer 计算，请分别查阅 `features/CLAUDE.md`、`experiment/CLAUDE.md`、`oect_transfer/CLAUDE.md`。

