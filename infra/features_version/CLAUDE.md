# features_version 模块说明（中文）

本模块提供"特征文件生成 + 版本化管理"的实用封装，支持：
- **V1 特征提取**：Transfer 数据的一键式特征提取（gm、Von、|I|）
- **V2 特征提取**：Transient 数据的时间常数提取（tau_on、tau_off），基于 autotau 包并支持多核并行
- 批量处理与通用版本矩阵创建/校验

模块依赖以下内部子系统（细节见各自 CLAUDE.md）：
- `features`：特征文件的创建、读取、写入与版本管理（见 `features/CLAUDE.md`）
- `experiment`：原始实验数据的读取与概要信息获取（见 `experiment/CLAUDE.md`）
- `oect_transfer`：Transfer 数据的批量分析与特征计算（见 `oect_transfer/CLAUDE.md`）
- `autotau`：Transient 数据的时间常数自动拟合（外部包，需单独安装）

## 目录结构

```
features_version/
├── v1_feature.py              # V1：一键提取/写入 Transfer 特征并创建版本
├── v2_feature.py              # V2：一键提取/写入 Transient tau 特征并创建版本（多核并行）
├── batch_create_feature.py    # 批量遍历原始文件并调用自定义处理函数
├── create_version_utils.py    # 通用：基于仓库内"已存储特征"创建/校验版本
├── __init__.py                # 模块导出
├── V2_FEATURE_README.md       # V2 特征详细文档
└── example/                   # 示例代码
    └── v2_feature_demo.py     # V2 特征使用示例
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

- `v2_feature(raw_file_path: str, output_dir: str = "data/features", sample_rate: Optional[float] = 1000, period: Optional[float] = 0.25, window_scalar_min: float = 0.2, window_scalar_max: float = 0.333, window_points_step: int = 10, window_start_idx_step: int = 1, normalize: bool = False, language: str = 'en', show_progress: bool = False) -> str`
  - 作用：
    - 基于原始实验文件提取 Transient 特征（tau_on 和 tau_off）并写入 HDF5 特征文件。
    - 使用 **autotau 0.3.1** 包的 `CyclesAutoTauFitter` 进行自动窗口搜索和拟合。
    - 若目标特征文件不存在，则通过 `features.FeatureFileCreator` 新建基础结构；存在则复用并覆盖对应特征数据。
    - 写入完成后，调用通用版本化工具创建版本矩阵（版本名固定为 `"v2"`，数据类型为 `"transient"`），并执行结构校验。
  - 输入：
    - `raw_file_path`：原始实验 H5 文件路径（必须包含 Transient 数据）。
    - `output_dir`：输出目录，默认 `data/features`。
    - `sample_rate`：采样率（Hz），默认 1000。
    - `period`：Transient 信号周期（秒），默认 0.25。
    - `window_scalar_min`：窗口搜索的最小标量（相对于周期），默认 0.2。
    - `window_scalar_max`：窗口搜索的最大标量（相对于周期），默认 0.333。
    - `window_points_step`：窗口点数步长，默认 10。
    - `window_start_idx_step`：窗口起始位置步长，默认 1。
    - `normalize`：是否归一化信号，默认 False。
    - `language`：界面语言（'cn' 或 'en'），默认 'en'。
    - `show_progress`：是否显示进度条，默认 False。
  - 返回：生成（或更新）的特征文件完整路径字符串。
  - 依赖与数据流：
    - `experiment.Experiment`：读取实验概要与 Transient 数据。
    - `autotau.CyclesAutoTauFitter`：从时序数据拟合 tau_on 和 tau_off。
    - `features.FeatureRepository`：写入特征到 `data_type="transient"`、`bucket_name="bk_00"`，覆盖写入（`overwrite=True`）。
    - `create_version_from_all_features(...)`：基于"仓库内此数据类型的全部可读特征"创建版本矩阵并校验。
  - 输出特征键（逐周期数组）：
    - `tau_on`：开启时间常数（秒）
    - `tau_off`：关闭时间常数（秒）
    - `tau_on_r2`：tau_on 拟合的 R² 值
    - `tau_off_r2`：tau_off 拟合的 R² 值
  - 异常：若原始文件不含可用 Transient 数据，将抛出 `ValueError`。
  - 文件命名：目标文件名由 `features.FeatureFileCreator.parse_raw_filename_to_feature(...)` 从原始文件名推导。
  - 版本要求：
    - autotau 版本：v0.3.1+（使用简化的接口，不再需要外部并行执行器）。
  - 迁移说明：
    - 如果从 autotau v0.3.0 升级，请参考 `AUTOTAU_0.3.1_MIGRATION.md`。
    - 主要变更：移除了 `max_workers` 参数，添加了 `window_start_idx_step`、`normalize`、`language` 参数。

- `estimate_period_from_signal(time: np.ndarray, signal: np.ndarray) -> float`
  - 作用：从信号中自动估计周期（使用 FFT 或自相关方法）。
  - 输入：
    - `time`：时间数组。
    - `signal`：信号数组。
  - 返回：估计的周期（秒）。
  - 用途：当 `period` 参数未知时，可使用此函数辅助估计。

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

### V1 特征提取（Transfer）

- 单文件一键处理：
  ```python
  from infra.features_version import v1_feature

  feature_file = v1_feature("path/to/raw.h5", output_dir="data/features")
  print(feature_file)
  ```

- 批量处理：
  ```python
  from infra.features_version import batch_create_features, v1_feature

  batch_create_features(
      source_directory="data/raw/",
      output_dir="data/features/",
      processing_func=v1_feature,
  )
  ```

### V2 特征提取（Transient）

- 单文件一键处理（自动估计周期）：
  ```python
  from infra.features_version import v2_feature

  feature_file = v2_feature(
      raw_file_path="path/to/raw.h5",
      output_dir="data/features",
      max_workers=4  # 使用4个CPU核心
  )
  print(feature_file)
  ```

- 指定周期的特征提取：
  ```python
  from infra.features_version import v2_feature

  feature_file = v2_feature(
      raw_file_path="path/to/raw.h5",
      output_dir="data/features",
      period=10.0,  # 10秒周期
      max_workers=8,
      window_scalar_min=0.2,
      window_scalar_max=0.35
  )
  ```

- 批量处理（V2）：
  ```python
  from infra.features_version import batch_create_features, v2_feature

  def processing_func(raw_file: str, out_dir: str) -> str:
      return v2_feature(
          raw_file_path=raw_file,
          output_dir=out_dir,
          max_workers=4
      )

  batch_create_features(
      source_directory="data/raw/",
      output_dir="data/features/",
      processing_func=processing_func
  )
  ```

- 使用周期估计辅助函数：
  ```python
  from infra.features_version import v2_feature, estimate_period_from_signal
  from infra.experiment import Experiment

  exp = Experiment("path/to/raw.h5")
  data = exp.get_transient_all_measurement()

  # 估计周期
  period = estimate_period_from_signal(
      data['continuous_time'],
      data['drain_current']
  )
  print(f"Estimated period: {period}s")

  # 使用估计的周期
  feature_file = v2_feature(
      "path/to/raw.h5",
      period=period,
      max_workers=8
  )
  ```

### 读取特征

- 读取 V1 特征（Transfer）：
  ```python
  from infra.features import FeatureRepository

  repo = FeatureRepository("data/features/chip-device-feat_*.h5")

  # 读取单个特征
  tau_on = repo.get_feature('absgm_max_forward', data_type='transfer')
  Von = repo.get_feature('Von_forward', data_type='transfer')
  ```

- 读取 V2 特征（Transient）：
  ```python
  from infra.features import FeatureRepository

  repo = FeatureRepository("data/features/chip-device-feat_*.h5")

  # 读取 tau 特征
  tau_on = repo.get_feature('tau_on', data_type='transient')
  tau_off = repo.get_feature('tau_off', data_type='transient')

  print(f"tau_on shape: {tau_on.shape}")
  print(f"tau_off range: [{tau_off.min():.6f}, {tau_off.max():.6f}]s")
  ```

### 通用版本管理

- 自定义创建版本（基于仓库中已写入的特征）：
  ```python
  from infra.features import FeatureRepository
  from infra.experiment import Experiment
  from infra.features_version import create_version_from_all_features

  repo = FeatureRepository("path/to/feature.h5")
  exp = Experiment("path/to/raw.h5")

  # 为 transfer 数据创建版本
  ok = create_version_from_all_features(
      repo=repo,
      version_name="v1",
      exp=exp,
      data_type="transfer",
      include_verification=True,
  )

  # 为 transient 数据创建版本
  ok = create_version_from_all_features(
      repo=repo,
      version_name="v2",
      exp=exp,
      data_type="transient",
      include_verification=True,
  )
  ```

## 约束与注意事项

### V1 特征（Transfer）
- 输入文件需包含可用的 Transfer 数据；否则 `v1_feature` 会抛出 `ValueError`。
- `v1_feature` 将把特征写入 `data_type="transfer"`、`bucket_name="bk_00"`，并使用覆盖模式。

### V2 特征（Transient）
- 输入文件需包含可用的 Transient 数据；否则 `v2_feature` 会抛出 `ValueError`。
- `v2_feature` 将把特征写入 `data_type="transient"`、`bucket_name="bk_00"`，并使用覆盖模式。
- **依赖要求**：需要安装 `autotau` 包（v0.3.0+）：`pip install autotau`
- **多核并行**：
  - 使用 `ProcessPoolExecutor` 实现窗口搜索并行化。
  - 推荐根据数据规模调整 `max_workers`：小文件 2-4，大文件 8-16。
  - 避免与上层框架（如 `features_v2`）的并行策略冲突。
- **周期参数**：
  - 如果 `period=None`，将使用简单的经验估计（可能不准确）。
  - 推荐使用 `estimate_period_from_signal()` 或手动指定准确的周期值。
- **性能优化**：
  - 增大 `window_points_step` 可加快速度但降低精度。
  - 减小 `window_scalar_min` 和增大 `window_scalar_max` 可扩大搜索范围但增加计算量。

### 通用约束
- 版本创建会包含"仓库中该数据类型下所有可读特征"，不仅限于本次新写入的键；同名版本会被强制覆盖。
- 目标特征文件名由 `features.FeatureFileCreator.parse_raw_filename_to_feature(...)` 从原始文件名推导；基础文件结构通过 `FeatureFileCreator.create_feature_file(...)` 新建。
- V1 和 V2 可以写入同一个特征文件的不同 `data_type`：
  - V1 写入 `data_type='transfer'`，版本名 `'v1'`
  - V2 写入 `data_type='transient'`，版本名 `'v2'`
- 模块日志通过 `logger_config.get_module_logger()` 记录到控制台/文件。

## 相关文档

- **V2 特征详细文档**：`V2_FEATURE_README.md`（包含完整的 API 文档、性能调优、故障排除）
- **V2 示例代码**：`example/v2_feature_demo.py`
- **features 模块**：`features/CLAUDE.md`（特征存储与版本管理）
- **experiment 模块**：`experiment/CLAUDE.md`（实验数据读取）
- **oect_transfer 模块**：`oect_transfer/CLAUDE.md`（Transfer 特征计算）
- **autotau 包**：[GitHub](https://github.com/Durian-leader/autotau)（Transient tau 拟合）

以上内容仅描述 `features_version` 模块本身；涉及读取/写入细节、特征仓库格式、实验数据结构与算法实现，请查阅对应文档。

