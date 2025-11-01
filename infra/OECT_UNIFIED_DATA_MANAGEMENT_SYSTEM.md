# OECT 统一数据管理系统

**版本**: 2.0.0
**项目**: Minitest-OECT-dataprocessing
**更新日期**: 2025-09-28

---

## 📋 系统概述

OECT统一数据管理系统是专为OECT（Organic Electrochemical Transistor）测试数据设计的完整解决方案，提供从原始数据到特征分析的端到端数据处理能力。

### 🎯 核心功能

- **双文件架构**: 原始数据文件（raw）与特征数据文件（features）分离管理
- **统一索引管理**: Catalog模块提供HDF5文件元信息管理和双向同步
- **高性能数据访问**: 批量格式存储，支持4.8M数据点0.3秒加载
- **完整可视化**: Transfer/Transient曲线绘图、演化动画、高性能视频生成
- **版本化特征管理**: 支持特征集合的版本演进和HDFView兼容存储
- **数据预处理管道**: 从CSV/JSON到HDF5的完整自动化转换流程

---

## 🏗️ 系统架构

### 双文件架构设计

系统采用**双文件架构**，实现数据和特征的职责分离：

```
data/
├── raw/                    # 原始数据文件
│   └── {chip_id}-{device_id}-{description}-test_{timestamp}_{hash}.h5
└── features/               # 特征数据文件
    └── {chip_id}-{device_id}-{description}-feat_{timestamp}_{hash}.h5
```

#### 文件命名规范
- **原始文件**: `{chip_id}-{device_id}-{description}-test_{timestamp}_{hash}.h5`
- **特征文件**: `{chip_id}-{device_id}-{description}-feat_{timestamp}_{hash}.h5`
- **示例对应关系**:
  - 原始: `#20250804007-1-稳定性测试-test_20250815134210_290e653d.h5`
  - 特征: `#20250804007-1-稳定性测试-feat_20250815134210_290e653d.h5`

### 模块职责分工

#### 1. `experiment` 包（原始数据专用）
**职责**: 专注于原始数据的处理和访问，**仅处理 raw/ 目录下的文件**
- **核心功能**:
  - 原始HDF5文件的读取、解析、访问
  - 批量数据格式的懒加载和缓存
  - 实验元数据、工作流信息的管理
  - Step数据的高性能访问接口
- **工作范围**: `data/raw/` 目录下的原始数据文件

**API 示例**:
```python
from experiment import Experiment

# 专注原始数据访问
raw_path = "/data/raw/#20250804007-1-稳定性测试-test_20250815134210_290e653d.h5"
exp = Experiment(raw_path)
transfer_data = exp.get_transfer_step_measurement(0)
transient_data = exp.get_transient_step_measurement(0)

# 获取实验元数据
experiment_info = exp.get_experiment_summary()
workflow_info = exp.get_workflow() if exp.has_workflow() else None
```

#### 2. `features` 包（特征数据专用）
**职责**: 专注于特征的存储、版本管理和读取，**仅处理 features/ 目录下的文件**
- **核心模块**:
  - `FeatureFileCreator`: 特征文件的创建和初始化
  - `FeatureRepository`: 特征文件的存储和读取仓库
  - `VersionManager`: 特征版本的管理和固化
  - `FeatureReader`: 特征数据的读取接口
  - `BatchManager`: 批量特征文件管理和操作
- **工作范围**: `data/features/` 目录下的特征数据文件

**核心职责**:
- **特征存储**: 支持列式存储大量特征，分桶管理
- **版本管理**: 特征集合的版本化固化，支持矩阵格式
- **数据读取**: 高效读取特征矩阵或指定特征列
- **HDFView兼容**: 完全兼容HDFView的特征数据存储格式

#### 3. `features_version` 包（特征版本管理）
**职责**: 提供高级特征版本管理和批量处理工具
- **核心功能**:
  - `v1_feature`: v1版本特征提取引擎
  - `v2_feature`: v2版本特征提取引擎
  - `batch_create_feature`: 批量特征文件创建工具
  - `create_version_utils`: 版本创建实用工具

#### 4. `visualization` 包（高性能可视化）
**职责**: OECT数据的专业可视化和动画生成
- **核心组件**:
  - `OECTPlotter`: OECT数据绘图器，专注核心功能
  - `ChipFeaturePlotter`: 芯片特征绘图器
- **核心功能**:
  - **Transfer曲线绘图**: `plot_transfer_single()`, `plot_transfer_multiple()`, `plot_transfer_evolution()`
  - **Transient曲线绘图**: `plot_transient_single()`, `plot_transient_all()`
  - **传统动画生成**: `create_transfer_animation()` - matplotlib动画版本
  - **多进程动画生成**: `create_transfer_video_parallel()` - 高性能多进程版本

#### 5. `catalog` 包（统一数据管理）
**职责**: HDF5文件元信息管理和双向同步系统
- **核心组件**:
  - `CatalogService`: 核心catalog服务
  - `UnifiedExperimentManager`: 统一实验管理器
  - `UnifiedExperiment`: 统一实验对象
  - **双向同步机制**: 基于时间戳的文件与数据库同步
  - **智能文件发现**: 并行扫描和自动关联
  - **统一查询接口**: 复杂条件的实验数据查询

### 包间关系：完全独立

#### 1. 独立性原则
- **experiment包** 不知道特征文件的存在，专注原始数据处理
- **features包** 不依赖experiment包，可以独立运行
- **catalog包** 作为统一接口层，可选择性地集成其他包
- **文件关联** 通过约定的文件命名规范实现（`-test_` vs `-feat_`）
- **无强制校验** 不进行跨文件完整性检查，各包管好自己的文件

#### 2. 上层业务逻辑
**特征提取与分析**（更高层的模块）：
- **FeatureExtractor**：特征提取引擎
  - 依赖experiment包读取原始数据
  - 依赖features包存储提取的特征
  - 实现具体的特征计算算法
- **FeatureAnalyzer**：特征分析工具
  - 依赖features包读取特征数据
  - 实现统计分析、可视化等功能
  - 支持跨实验、跨批次的对比分析

---

## 📊 数据格式设计

### 原始数据文件结构

采用**批量格式存储** (Format Version 2.0_new_storage)，优化大规模数据访问：

```
HDF5 File (Format Version 2.0_new_storage)
├── Root Attributes (experiment metadata)
├── /raw/ (原始数据备份)
│   ├── json (test_info.json backup)
│   └── workflow (workflow.json backup)
├── /transfer/ (Transfer数据 - 批量格式)
│   ├── step_info_table (展平的步骤信息，结构化数组)
│   └── measurement_data (3D数组: [步骤索引, 数据类型, 数据点])
└── /transient/ (Transient数据 - 批量格式)
    ├── step_info_table (展平的步骤信息，结构化数组)
    └── measurement_data (2D数组: [数据类型, 拼接的数据点])
```

### 特征文件结构

支持HDFView完全兼容的特征数据存储：

```
/
├── @attrs                 # 特征文件属性
│   ├── chip_id, device_id, description, test_id
│   ├── built_with         # 特征提取工具版本
│   └── created_at         # 特征文件创建时间
├── /transfer/             # Transfer特征数据
│   ├── v1/, v2/, ...      # 版本化特征矩阵
│   │   ├── matrix        # (n_steps, n_features) 特征矩阵
│   │   ├── names         # 特征名称列表
│   │   ├── units         # 特征单位列表
│   │   └── desc          # 特征描述列表
│   └── columns/          # 列式特征仓库（增量开发）
│       ├── buckets/      # 分桶存储特征列
│       └── _registry/    # 特征注册表
└── /transient/           # Transient特征数据（结构同transfer）
```

### 批量格式存储优势

1. **高性能访问**: 4.8M数据点0.3秒加载
2. **内存效率**: 3D/2D数组格式减少内存碎片
3. **分析便利**: Transient数据自动拼接为连续时间序列
4. **压缩存储**: 使用gzip压缩和shuffle过滤器

---

## 🗂️ Catalog模块 - 统一数据管理核心

### 核心功能

- **统一索引管理**: 为raw数据文件和features特征文件建立统一元信息索引
- **智能双向同步**: 基于时间戳的HDF5文件与SQLite数据库双向同步
- **高效查询检索**: 支持复杂条件的实验数据快速查询和筛选
- **可移植性设计**: 相对路径存储配合配置化根目录，支持跨环境部署
- **统一接口**: 通过UnifiedExperimentManager提供单一入口点

### 数据库设计

#### 主表结构 (`experiments`)

```sql
CREATE TABLE IF NOT EXISTS experiments (
    -- 主键和标识
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 文件路径 (相对路径，基于配置的根目录)
    raw_file_path TEXT NOT NULL UNIQUE,       -- 相对于raw_data根目录
    feature_file_path TEXT,                   -- 相对于features根目录(可能为空)

    -- 实验标识信息
    chip_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    test_unit_id TEXT,
    description TEXT,
    test_id TEXT NOT NULL,
    batch_id TEXT,

    -- 实验状态和进度
    status TEXT,                              -- completed/running/failed/pending
    completion_percentage REAL DEFAULT 0,     -- 完成百分比 (0-100)
    completed_steps INTEGER DEFAULT 0,
    total_steps INTEGER DEFAULT 0,

    -- 时间信息
    created_at DATETIME,
    completed_at DATETIME,
    duration REAL,

    -- 测试条件和环境参数
    temperature REAL,
    sample_type TEXT,
    device_type TEXT,                         -- 器件类型: N-type/P-type

    -- 数据内容摘要
    has_transfer_data BOOLEAN DEFAULT 0,
    has_transient_data BOOLEAN DEFAULT 0,
    transfer_steps INTEGER DEFAULT 0,
    transient_steps INTEGER DEFAULT 0,
    total_data_points INTEGER DEFAULT 0,

    -- 文件信息
    raw_file_size INTEGER,
    feature_file_size INTEGER,

    -- 同步管理字段
    raw_file_modified DATETIME,
    feature_file_modified DATETIME,
    db_last_synced DATETIME NOT NULL,
    sync_status TEXT DEFAULT 'synced',

    -- 约束条件
    UNIQUE(chip_id, device_id),
    UNIQUE(test_id),
    CHECK(completion_percentage >= 0 AND completion_percentage <= 100)
);
```

### 双向同步机制

基于**时间戳比较**的策略，确保数据库和HDF5文件之间的数据一致性：

1. **时间戳作为仲裁者**: 比较文件修改时间与数据库记录的同步时间
2. **冲突检测机制**: 识别并记录同步冲突，支持多种解决策略
3. **增量处理**: 只处理自上次同步后发生变更的文件和记录
4. **事务保护**: 确保同步操作的原子性，避免数据不一致

---

## 🚀 统一接口 - UnifiedExperimentManager

### 设计理念

**目标**: 完全隐藏底层模块(experiment/features/catalog)的分割，提供统一、直观的顶层接口。

**原则**:
1. **单一入口**: 用户只需要了解 `UnifiedExperimentManager` 一个类
2. **智能路由**: 自动判断数据来源，选择最优的底层模块
3. **懒加载**: 按需加载数据，优化内存使用
4. **统一元信息**: 自动整合来自不同源的元信息，消除重复和冲突

### 基本使用方法

#### 1. 统一接口使用（推荐）

```python
from catalog import UnifiedExperimentManager

# 初始化统一管理器 - 唯一需要了解的类
manager = UnifiedExperimentManager('catalog_config.yaml')

# ==================== 获取单个实验 ====================
# 方式1: 通过ID获取
exp = manager.get_experiment(42)

# 方式2: 通过条件获取
exp = manager.get_experiment(chip_id="#20250804008", device_id="3")

# 统一的属性访问
print(f"芯片: {exp.chip_id}")
print(f"设备: {exp.device_id}")
print(f"状态: {exp.status}")

# 获取步骤数 - 现在支持直接属性访问！
print(f"Transfer步骤: {exp.transfer_steps}")
print(f"Transient步骤: {exp.transient_steps}")

# 检查特征版本（推荐的版本列表）
available_versions = ['v1', 'v2']  # 当前支持的版本
has_features = {v: exp.has_features(v) for v in available_versions}
print(f"特征版本状态: {has_features}")

# ==================== 数据访问 ====================
# 原始数据
transfer_data = exp.get_transfer_data(step_index=0)  # 单步数据
all_transfer = exp.get_transfer_data()  # 所有数据
transient_data = exp.get_transient_data(step_index=0)

# 特征数据
features = exp.get_features(['gm_max_forward', 'Von_forward'])
feature_matrix = exp.get_feature_matrix(version='v1')
features_df = exp.get_feature_dataframe(version='v1')

# 工作流信息 - 现在完全支持！
if exp.has_workflow():
    workflow = exp.get_workflow()
    exp.print_workflow()  # 打印工作流结构

    # 获取工作流摘要
    workflow_summary = exp.get_workflow_summary()
    print(f"工作流摘要: {workflow_summary}")

    # 导出工作流到文件
    if exp.export_workflow_json('workflow_export.json'):
        print("工作流导出成功!")
else:
    print("当前实验没有工作流信息")

# ==================== 可视化 ====================
# Transfer曲线绘图
fig = exp.plot_transfer_single(step_index=0, log_scale=False)  # 单步Transfer曲线
fig = exp.plot_transfer_multiple([0, 10, 20, 30])           # 多步对比
fig = exp.plot_transfer_evolution(max_steps=100)            # 演化图

# Transient曲线绘图
fig = exp.plot_transient_single(step_index=0, dual_time_axis=True)  # 单步（双时间轴）
fig = exp.plot_transient_all()                                      # 所有Transient整体图

# Transfer演化动画/视频
ani = exp.create_transfer_animation(max_steps=100, interval=200)     # 传统动画
video_path = exp.create_transfer_video('evolution.mp4', fps=15)     # 高性能视频

# 特征数据可视化
fig = exp.plot_feature_trend('gm_max_forward', version='v1')         # 单个特征趋势

# 绘图器信息
plotter_info = exp.get_plotter_experiment_info()                    # 获取绘图器实验信息
```

#### 2. 批量操作

```python
# ==================== 搜索实验 ====================
# 基本搜索
experiments = manager.search(chip_id="#20250804008")
completed_exps = manager.search(status='completed')
missing_features = manager.search(missing_features=True)

# 高级搜索
experiments = manager.search(
    chip_id="#20250804008",
    status='completed',
    has_transfer_data=True,
    created_after='2025-08-01'
)

# ==================== 批量特征处理 ====================
# 批量提取特征
results = manager.batch_extract_features(
    experiments,
    version='v1'
)
print(f"特征提取: 成功{len(results['successful'])}, 失败{len(results['failed'])}")

# ⚠️ 重要：特征提取完成后需要手动重新扫描以关联文件
print("重新扫描以关联新特征文件...")
scan_result = manager.catalog.scan_and_index(incremental=False)
print(f"扫描完成: {scan_result.files_processed}文件, {scan_result.files_updated}更新")

# ==================== 数据完整性管理 ====================
# 检查一致性
issues = manager.check_consistency()
print(f"缺少特征文件: {len(issues['missing_feature_files'])}")

# 自动修复
fixes = manager.auto_fix_inconsistencies(issues)
print(f"修复了 {fixes['fixed']} 个问题")
```

#### 3. 数据预处理管道（🆕 新增功能）

```python
# ==================== 完整数据处理管道（一键处理）====================
# 最简单的方式：一键完成JSON清理 -> 目录发现 -> 批量转换 -> 可选特征提取
pipeline_result = manager.process_data_pipeline(
    source_directory="/path/to/csv/data/",  # 包含测试目录的根目录
    clean_json=True,                        # 先清理JSON文件
    num_workers=20,                         # 并行工作进程数
    conflict_strategy='skip',               # 跳过已存在的文件
    auto_extract_features=True,             # 自动提取特征
    show_progress=True                      # 显示进度条
)

print(f"处理结果: {pipeline_result['overall_success']}")
print(f"完成步骤: {pipeline_result['steps_completed']}")
if pipeline_result['overall_success']:
    conversion_stats = pipeline_result['results']['conversion']
    print(f"成功转换: {conversion_stats['successful_conversions']}/{conversion_stats['total_directories']}")

# ==================== 分步处理（灵活控制）====================

# 步骤1: 清理JSON文件（整理test_info.json格式）
clean_result = manager.clean_json_files(
    source_directory="/path/to/csv/data/",
    pattern="test_info.json"                # 默认值
)
print(f"JSON清理结果: {clean_result['success']}")

# 步骤2: 发现测试目录（查找包含test_info.json的目录）
test_directories = manager.discover_test_directories(
    source_directory="/path/to/csv/data/",
    exclude_output_dir=True                 # 排除输出目录，避免循环处理
)
print(f"发现 {len(test_directories)} 个测试目录")

# 步骤3: 批量转换到HDF5格式
conversion_result = manager.batch_convert_folders(
    test_directories=test_directories,
    num_workers=20,                         # 并行工作数
    conflict_strategy='skip',               # 'overwrite', 'skip', 'rename'
    show_progress=True
)
print(f"转换完成: {conversion_result['successful_conversions']}/{len(test_directories)}")

# 步骤4: 转换后自动提取特征（可选）
if conversion_result['successful_conversions'] > 0:
    # 重新扫描以获取新转换的实验
    manager.catalog.scan_and_index()

    # 查找新实验并提取特征
    new_experiments = manager.search(missing_features=True)
    if new_experiments:
        feature_results = manager.batch_extract_features(new_experiments, version='v1')
        print(f"特征提取完成: {len(feature_results['successful'])} 个实验")

        # ⚠️ 重要：特征提取后需要重新扫描以关联文件
        print("重新扫描以关联新特征文件...")
        manager.catalog.scan_and_index(incremental=False)
```

### CLI工具使用

```bash
# 初始化catalog系统
python -m catalog init --auto-config

# 扫描文件
python -m catalog scan --path data/raw --recursive

# 双向同步
python -m catalog sync --direction both

# 查询实验
python -m catalog query --chip "#20250804008" --output table

# 统计信息
python -m catalog stats --detailed

# 数据验证和维护
python -m catalog validate --fix-conflicts
python -m catalog cleanup --vacuum
```

---

## 🎨 可视化系统

### OECTPlotter - 核心绘图器

```python
from visualization.plotter import OECTPlotter

# 初始化绘图器
plotter = OECTPlotter('path/to/experiment.h5')

# ===================
# Transfer曲线绘图
# ===================

# 单步骤Transfer曲线
fig = plotter.plot_transfer_single(step_index=0, log_scale=False)  # 线性坐标
fig = plotter.plot_transfer_single(step_index=0, log_scale=True)   # 对数坐标

# 多步骤对比
fig = plotter.plot_transfer_multiple([0, 10, 20, 30])  # 对比多个步骤

# Transfer演化图（彩色映射）
fig = plotter.plot_transfer_evolution()  # 默认显示所有步骤
fig = plotter.plot_transfer_evolution(max_steps=100, colormap='viridis')

# ===================
# Transient曲线绘图 ✨ 支持双横轴时间显示
# ===================

# 单步骤Transient曲线 - 基础用法
fig = plotter.plot_transient_single(step_index=0)

# 双横轴显示（同时显示continuous_time和step_time）
fig = plotter.plot_transient_single(
    step_index=0,
    dual_time_axis=True        # 默认开启双横轴
)

# 所有Transient步骤连续显示
fig = plotter.plot_transient_all()  # 使用批量接口，高效处理大数据

# ===================
# 动画生成（两种方法）
# ===================

# 方法1: 传统matplotlib动画 (适合小数据集)
ani = plotter.create_transfer_animation(
    max_steps=100,           # 限制步骤数
    interval=200,            # 帧间隔(ms)
    save_path="evolution.mp4",
    layout='dual'            # 'dual', 'linear', 'log'
)

# 方法2: 多进程高性能视频生成 ✨ (适合大数据集，5000+步骤)
video_path = plotter.create_transfer_video_parallel(
    max_steps=None,          # 使用所有步骤
    fps=10,                  # 视频帧率
    save_path="transfer_evolution_parallel.mp4",
    figsize=(12, 5),         # 图像尺寸
    layout='dual',           # 布局方式
    n_workers=None,          # 自动选择进程数
    verbose=True             # 显示进度
)
```

### 多进程动画特性

- **轻量级数据结构**: `VideoFrameData` - 最小化进程间数据传输
- **并行帧渲染**: 使用 `ProcessPoolExecutor` 并行生成视频帧
- **自动性能优化**: 自动选择最优工作进程数和批处理大小
- **内存效率**: 独立的worker函数 `_generate_single_video_frame()`
- **格式支持**: 输出MP4视频文件，支持自定义fps和分辨率

### 性能优势说明

- **create_transfer_video_parallel()** 相比传统方法的优势:
  - 🚀 **多进程并行**: 显著加速大数据集处理
  - 💾 **内存效率**: 轻量级数据结构，最小化进程间传输
  - 🎯 **自动优化**: 自动选择最优工作进程数
  - 📊 **进度显示**: 实时进度反馈
  - 🔧 **高度可配置**: VideoConfig支持详细参数调整
  - 🎬 **专业输出**: 直接生成高质量MP4视频文件

**推荐使用场景**:
- 步骤数 < 100: 使用 `create_transfer_animation()`
- 步骤数 >= 100: 使用 `create_transfer_video_parallel()`
- 步骤数 > 1000: 强烈推荐多进程版本，性能差异显著

---

## 🎯 Features包 - HDFView兼容特征管理

### 核心组件

```python
from features import (
    FeatureFileCreator, FeatureRepository, VersionManager,
    FeatureReader, BatchManager, FeatureMetadata
)

# 1. 创建特征文件
creator = FeatureFileCreator()

# 从原始数据文件创建对应的特征文件
raw_file = "data/raw/#20250804008-3-稳定性测试-test_20250815134211_3fa6110a.h5"
feature_file = creator.create_from_raw_file(raw_file, output_dir="data/features/")

# 2. 存储特征数据到列式仓库
repo = FeatureRepository(feature_file)

# 单个特征存储
metadata = FeatureMetadata(
    name="gm_max_forward",
    unit="S",
    description="Forward sweep maximum transconductance"
)
repo.store_feature("gm_max_forward", feature_array, metadata=metadata)

# 批量特征存储
features = {
    'gm_max_forward': gm_forward_array,
    'Von_forward': von_forward_array,
    'absgm_max': absgm_max_array
}
metadata_dict = {name: FeatureMetadata(name=name) for name in features.keys()}
results = repo.store_multiple_features(features, metadata_dict=metadata_dict)

# 3. 创建版本化特征矩阵
version_manager = VersionManager(repo)
success = version_manager.create_version(
    "v1",
    ["gm_max_forward", "Von_forward", "absgm_max"],
    data_type="transfer",
    feature_units=["S", "V", "S"],
    feature_descriptions=[
        "Forward sweep maximum transconductance",
        "Forward threshold voltage",
        "Maximum absolute transconductance"
    ]
)

# 4. 高效读取特征数据
reader = FeatureReader(feature_file)

# 读取版本化矩阵 (高性能)
matrix = reader.get_version_matrix("v1", "transfer")  # Shape: (n_steps, n_features)
df = reader.get_version_dataframe("v1", "transfer")   # pandas DataFrame

# 读取列式特征 (灵活选择)
features_data = reader.get_features(["gm_max_forward", "Von_forward"], data_type="transfer")
single_feature = reader.get_feature("gm_max_forward", "transfer")

# 获取文件摘要信息
summary = reader.get_summary()
print(f"特征文件摘要: {summary['file_info']['basic_info']}")
```

### HDFView兼容性

**✨ 新特性** - 完全兼容HDFView的特征数据管理：
- **结构化数组注册表**: 使用`h5py.string_dtype()`确保HDFView完全兼容
- **gzip压缩**: 统一使用gzip压缩，HDFView原生支持
- **版本化矩阵**: 位于`/transfer/versions/v1/matrix`，高性能批量访问
- **软链接索引**: 通过`by_name`组提供快速特征查找

### 双重存储策略

- **列式仓库**: 日常开发中灵活添加新特征，支持分桶管理
- **版本化矩阵**: 阶段性固化为高性能访问格式 `(n_steps, n_features)`

### 🚀 快速创建特征文件 - 使用features_version包

```python
from features_version.v1_feature import v1_feature
from features_version.batch_create_feature import batch_create_features
import logging
from logger_config import log_manager, get_module_logger

# 配置日志级别 (简洁输出模式)
log_manager.set_levels(
    file_level=logging.WARNING,
    console_level=logging.WARNING
)
logger = get_module_logger()

# 单个文件处理
feature_file = v1_feature("/path/to/raw/file.h5", output_dir="data/features/")
print(f"特征文件已创建: {feature_file}")

# 批量处理目录下所有原始文件 (推荐方式)
batch_create_features("/path/to/raw/data/directory/", "data/features/", v1_feature)
```

---

## 🔧 核心技术特性

### 批量格式存储优势

1. **批量数据访问**: 支持一次性加载所有transfer或transient步骤数据
2. **内存效率**: 3D/2D数组格式减少内存碎片，提高缓存效率
3. **分析便利**: Transient数据自动拼接为连续时间序列，无需手动处理步骤边界
4. **压缩存储**: 使用gzip压缩和shuffle过滤器，文件体积更小

### 懒加载架构

- **性能突破**: 真正的懒加载机制，摘要访问从GB级内存使用降至MB级
- **三层架构**:
  - 元数据层：毫秒级HDF5属性和shape信息读取
  - 摘要层：基于元数据计算摘要，无需加载大数组
  - 数据层：按需加载特定步骤数据，支持LRU智能缓存
- **性能指标**:
  - 实例化: 0.02秒
  - 数据摘要: 0.05秒，内存峰值0.04MB
  - 单步数据加载: 0.02-0.08秒，支持缓存

### Transfer特性计算

**BatchTransfer类**: 高效批量处理3D numpy数组 `[步骤索引, 数据类型（2）, 数据点索引]`
- **统一API接口**: 与原Transfer类相同的属性访问逻辑，但增加步骤维度
- **坐标存储**: BatchPoint包含`*_coords`属性存储特征点坐标 `[steps, 2]`
- **核心特性**:
  - `batch_transfer.Vg.raw`: 所有步骤的门电压数据 `[steps, data_points]`
  - `batch_transfer.gm.raw`: 所有步骤的跨导数据 `[steps, data_points]`
  - `batch_transfer.absgm_max.raw`: 所有步骤的最大跨导值 `[steps]`
  - `batch_transfer.Von.raw`: 所有步骤的阈值电压 `[steps]`

---

## ⚙️ 系统配置

### 配置文件设置

创建 `catalog_config.yaml`：

```yaml
# 根目录配置
roots:
  raw_data: "/home/lidonghaowsl/develop_win/hdd/data/Stability_PS/raw"
  features: "/home/lidonghaowsl/develop_win/hdd/data/Stability_PS/features"

# 数据库配置
database:
  path: "/home/lidonghaowsl/develop_win/hdd/data/Stability_PS/catalog.db"
  auto_backup: false
  backup_interval: 86400
  connection_pool_size: 10

# 同步配置
sync:
  auto_sync: false
  auto_sync_interval: 3600
  conflict_strategy: "timestamp"  # timestamp/manual/ignore
  batch_size: 100
  timeout: 300

# 文件发现配置
discovery:
  recursive: true
  max_depth: 10
  parallel_workers: 4
  file_patterns:
    raw: "*-test_*.h5"
    features: "*-feat_*.h5"
  ignore_patterns:
    - "*.tmp"
    - ".*"
    - "_*"

# 日志配置
logging:
  level: "INFO"
  file: "/home/lidonghaowsl/develop_win/hdd/data/Stability_PS/logs/catalog.log"
  rotation: "1 week"
  retention: "4 weeks"
```

### 初始化系统

```bash
# 方式1: 自动初始化（推荐）
python -m catalog init --auto-config

# 方式2: 手动指定配置
python -m catalog init --config catalog_config.yaml

# 方式3: 完全自动检测
python -m catalog init --root-dir /path/to/data --auto-config
```

---

## 📊 使用场景示例

### 1. 完整数据处理工作流

```python
from catalog import UnifiedExperimentManager
import logging
from logger_config import log_manager, get_module_logger

# 配置日志
log_manager.set_levels(
    file_level=logging.WARNING,
    console_level=logging.WARNING
)
logger = get_module_logger()

def complete_data_processing_workflow(source_dir: str):
    """完整的数据处理工作流"""

    manager = UnifiedExperimentManager('catalog_config.yaml')

    # 1. 创建新实验（从CSV/JSON到HDF5）
    print("创建新实验...")
    new_exp = manager.create_experiment(
        source_dir=source_dir,
        auto_extract_features=True,
        feature_versions=['v1']
    )

    # 2. 数据验证
    print("验证数据完整性...")
    if not new_exp.has_features('v1'):
        print("特征提取失败，重试...")
        manager.batch_extract_features([new_exp], version='v1')
        manager.catalog.scan_and_index(incremental=False)  # 重新扫描

    # 3. 生成可视化
    print("生成可视化...")
    # Transfer演化图
    fig = new_exp.plot_transfer_evolution()
    fig.savefig(f"outputs/{new_exp.chip_id}_{new_exp.device_id}_evolution.png")

    # Transfer演化视频（高性能并行版本）
    if new_exp.transfer_steps > 50:
        video_path = new_exp.create_transfer_video(
            save_path=f"outputs/{new_exp.chip_id}_{new_exp.device_id}_video.mp4",
            fps=15,
            verbose=True
        )

    # Transient图
    if new_exp.transient_steps > 0:
        fig = new_exp.plot_transient_single(step_index=0, dual_time_axis=True)
        fig.savefig(f"outputs/{new_exp.chip_id}_{new_exp.device_id}_transient.png")

    # 4. 特征分析
    if new_exp.has_features('v1'):
        features_df = new_exp.get_feature_dataframe('v1')

        # 特征趋势图
        key_features = ['gm_max_forward', 'Von_forward', 'absgm_max']
        available_features = [f for f in key_features if f in features_df.columns]

        if available_features:
            fig = new_exp.plot_feature_trend(available_features[0], version='v1')
            fig.savefig(f"outputs/{new_exp.chip_id}_{new_exp.device_id}_feature_trend.png")

    # 5. 数据导出
    print("导出数据...")
    exported_files = []

    # 导出特征数据
    if new_exp.has_features('v1'):
        features_df = new_exp.get_feature_dataframe('v1')
        if features_df is not None:
            export_path = f"exports/{new_exp.chip_id}_{new_exp.device_id}_features.csv"
            features_df.to_csv(export_path, index=False)
            exported_files.append(export_path)

    # 6. 生成报告
    report = {
        'experiment_id': new_exp.id,
        'chip_id': new_exp.chip_id,
        'device_id': new_exp.device_id,
        'status': new_exp.status,
        'transfer_steps': new_exp.transfer_steps,
        'transient_steps': new_exp.transient_steps,
        'has_features': new_exp.has_features('v1'),
        'exported_files': exported_files,
        'created_at': new_exp.created_at
    }

    print(f"实验处理完成: {new_exp.chip_id}-{new_exp.device_id}")
    return report
```

### 2. 批量芯片分析

```python
def batch_chip_analysis(manager, chip_ids: list, feature_version: str = 'v1'):
    """批量芯片数据分析"""

    results = {}

    for chip_id in chip_ids:
        print(f"分析芯片: {chip_id}")

        # 获取芯片所有实验
        experiments = manager.search(chip_id=chip_id, status='completed')

        chip_stats = {
            'total_experiments': len(experiments),
            'devices': {},
            'feature_statistics': {}
        }

        # 按设备分析
        for exp in experiments:
            device_id = exp.device_id
            if device_id not in chip_stats['devices']:
                chip_stats['devices'][device_id] = {
                    'transfer_steps': exp.transfer_steps,
                    'has_features': exp.has_features(feature_version),
                    'status': exp.status
                }

            # 特征统计
            if exp.has_features(feature_version):
                features_df = exp.get_feature_dataframe(feature_version)

                for feature_name in features_df.columns:
                    if feature_name not in chip_stats['feature_statistics']:
                        chip_stats['feature_statistics'][feature_name] = []

                    chip_stats['feature_statistics'][feature_name].extend(
                        features_df[feature_name].tolist()
                    )

        # 计算统计量
        for feature_name, values in chip_stats['feature_statistics'].items():
            import numpy as np
            chip_stats['feature_statistics'][feature_name] = {
                'mean': float(np.mean(values)),
                'std': float(np.std(values)),
                'min': float(np.min(values)),
                'max': float(np.max(values)),
                'count': len(values)
            }

        results[chip_id] = chip_stats

    return results

# 使用示例
manager = UnifiedExperimentManager('catalog_config.yaml')
chip_analysis = batch_chip_analysis(
    manager,
    chip_ids=["#20250804008", "#20250804009"],
    feature_version='v1'
)

# 生成对比报告
import pandas as pd
import matplotlib.pyplot as plt

for chip_id, stats in chip_analysis.items():
    print(f"\n芯片 {chip_id}:")
    print(f"  - 总实验数: {stats['total_experiments']}")
    print(f"  - 设备数: {len(stats['devices'])}")
    print(f"  - 特征数: {len(stats['feature_statistics'])}")
```

---

## 🔧 故障排除

### 常见问题和解决方案

#### 1. 配置文件找不到
```bash
# 检查配置文件位置
ls -la catalog_config.yaml

# 重新生成配置
python -m catalog init --auto-config
```

#### 2. 数据库连接错误
```bash
# 检查数据库文件权限
ls -la data/catalog.db

# 重新初始化数据库
python -m catalog init --force
```

#### 3. 文件路径问题
```bash
# 验证路径配置
python -c "from catalog.config import CatalogConfig; config = CatalogConfig(); print(config.to_dict())"

# 检查文件完整性
python -m catalog maintenance --validate
```

#### 4. 性能问题
```bash
# 优化数据库
python -m catalog maintenance --vacuum

# 检查索引
python -m catalog stats --detailed
```

### 日志查看和调试

```python
# 启用详细日志
import logging
from logger_config import log_manager

log_manager.set_levels(
    file_level=logging.DEBUG,
    console_level=logging.INFO
)

# 查看日志文件
tail -f logs/catalog.log
```

---

## 🚀 性能优化建议

### 1. 批量操作优化

```python
def optimized_batch_processing():
    """优化的批量处理示例"""

    manager = UnifiedExperimentManager('catalog_config.yaml')

    # 使用批量接口而不是循环
    experiments = manager.search(status='completed', limit=1000)

    # 批量特征提取
    missing_features = [exp for exp in experiments if not exp.has_features('v1')]
    if missing_features:
        # 批量处理比逐个处理快得多
        results = manager.batch_extract_features(missing_features, version='v1')
        # 特征提取后重新扫描
        manager.catalog.scan_and_index(incremental=False)

    # 批量导出
    export_results = []
    for exp in experiments[:10]:  # 限制数量避免内存问题
        # 使用可用的方法导出特征数据
        if exp.has_features('v1'):
            features_df = exp.get_feature_dataframe('v1')
            if features_df is not None:
                export_path = f'exports/{exp.chip_id}_{exp.device_id}_features.csv'
                features_df.to_csv(export_path, index=False)
                export_results.append(export_path)
```

### 2. 内存优化

```python
def memory_efficient_processing():
    """内存高效的处理方式"""

    manager = UnifiedExperimentManager('catalog_config.yaml')

    # 分批处理大量实验
    batch_size = 50
    all_experiments = manager.search(status='completed')

    for i in range(0, len(all_experiments), batch_size):
        batch = all_experiments[i:i+batch_size]

        # 处理当前批次
        for exp in batch:
            # 处理单个实验
            if exp.transfer_steps > 1000:  # 只处理大数据集
                # 使用高性能视频生成
                video_path = exp.create_transfer_video(
                    save_path=f"videos/{exp.chip_id}_{exp.device_id}.mp4",
                    fps=10,
                    verbose=False  # 减少输出
                )

        # 清理缓存（如果需要）
        import gc
        gc.collect()
```

---

## 📈 系统总结

OECT统一数据管理系统提供了完整的数据处理解决方案，通过统一接口隐藏了底层复杂性，支持：

### ✨ 核心优势

1. **统一数据访问**: 通过UnifiedExperimentManager一站式访问所有数据
2. **智能同步机制**: 自动处理文件系统和数据库的同步
3. **完整可视化接口**: 集成visualization包的核心功能
   - **OECTPlotter全功能**: Transfer/Transient曲线绘图，动画/视频生成
   - **高性能视频生成**: 多进程并行视频生成，支持大规模数据处理
   - **单实验层级**: 专注单个实验的可视化分析
4. **完整生命周期**: 从数据创建到分析导出的全流程支持
5. **扩展性设计**: 易于与现有experiment、features、visualization模块集成

### 🎯 技术亮点

- ✅ **OECTPlotter集成**: 补全了OECTPlotter的核心方法到catalog统一接口
- ✅ **Transfer/Transient绘图**: 支持单步、多步对比、演化图等多种绘图模式
- ✅ **动画/视频生成**: 集成传统动画和高性能并行视频生成
- ✅ **HDFView兼容**: Features包完全兼容HDFView，支持版本化特征管理
- ✅ **高性能数据访问**: 批量格式存储，4.8M数据点0.3秒加载
- 🆕 **数据预处理管道**: 新增完整的CSV到HDF5数据处理工作流
  - `clean_json_files()`: JSON文件清理和格式化
  - `discover_test_directories()`: 智能测试目录发现
  - `batch_convert_folders()`: 并行批量转换到HDF5
  - `process_data_pipeline()`: 一键式完整数据处理管道
- 🆕 **智能目录处理**: 自动排除输出目录，避免循环处理
- 🆕 **灵活冲突策略**: 支持overwrite/skip/rename三种文件冲突处理策略
- 🆕 **进度可视化**: 集成进度条显示，实时监控处理状态

### 🎨 架构设计

- **完全独立的模块**: experiment、features、visualization、catalog各自专注核心职责
- **双文件架构**: 原始数据与特征数据分离管理，提高系统可维护性
- **懒加载机制**: 智能的数据加载策略，优化内存使用
- **版本化管理**: 支持特征版本演进，确保实验可复现性
- **统一接口**: 隐藏底层复杂性，提供直观的用户体验

**推荐使用模式**: 优先使用UnifiedExperimentManager统一接口，享受核心可视化功能集成和数据预处理管道，必要时再调用底层API。新的数据预处理功能让从原始CSV数据到最终分析的完整工作流更加自动化和高效。

---

*本文档版本: v2.0.0*
*最后更新: 2025-09-28*
*项目: Minitest-OECT-dataprocessing*