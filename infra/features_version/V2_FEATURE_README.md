# V2 Feature Extraction - Transient Tau Features

## 概述

`v2_feature.py` 模块提供了基于 **autotau** 包的 transient 数据时间常数（tau_on 和 tau_off）提取功能，支持多核并行处理。

### 核心特性

- ✅ **自动 tau 提取**：使用 autotau 的智能窗口搜索算法
- ✅ **多核并行**：利用 ProcessPoolExecutor 加速窗口搜索
- ✅ **灵活配置**：支持自定义周期、窗口参数等
- ✅ **自动周期估计**：如果未指定周期，可从数据中自动估计
- ✅ **统一存储**：与 V1 features 使用相同的 HDF5 存储格式
- ✅ **版本管理**：自动创建 v2 版本矩阵

## 安装依赖

```bash
# autotau 已安装在 mlpytorch 环境中
conda activate mlpytorch

# 如果需要手动安装
pip install autotau
```

## 快速开始

### 基本用法

```python
from infra.features_version import v2_feature

# 提取 tau 特征（自动估计周期）
feature_file = v2_feature(
    raw_file_path="data/raw/chip-device-test_*.h5",
    output_dir="data/features",
    max_workers=4  # 使用4个CPU核心
)
```

### 指定周期

```python
# 如果知道实验的确切周期（秒）
feature_file = v2_feature(
    raw_file_path="data/raw/chip-device-test_*.h5",
    output_dir="data/features",
    period=10.0,  # 10秒周期
    max_workers=8
)
```

### 批量处理

```python
from infra.features_version import batch_create_features, v2_feature

def processing_func(raw_file: str, out_dir: str) -> str:
    return v2_feature(
        raw_file_path=raw_file,
        output_dir=out_dir,
        max_workers=4
    )

batch_create_features(
    source_directory="data/raw",
    output_dir="data/features",
    processing_func=processing_func
)
```

## API 文档

### v2_feature()

```python
def v2_feature(
    raw_file_path: str,
    output_dir: str = "data/features",
    period: Optional[float] = None,
    max_workers: Optional[int] = None,
    window_scalar_min: float = 0.2,
    window_scalar_max: float = 0.333,
    window_points_step: int = 10,
    show_progress: bool = False
) -> str
```

#### 参数说明

- **raw_file_path** (`str`): 原始实验 HDF5 文件路径（必须包含 transient 数据）
- **output_dir** (`str`, 默认 `"data/features"`): 特征文件输出目录
- **period** (`Optional[float]`, 默认 `None`):
  - transient 信号周期（秒）
  - 如果为 `None`，将从数据中自动估计
- **max_workers** (`Optional[int]`, 默认 `None`):
  - 并行工作进程数
  - `None` 表示使用 CPU 核心数
- **window_scalar_min** (`float`, 默认 `0.2`): 窗口搜索的最小标量（相对于周期）
- **window_scalar_max** (`float`, 默认 `0.333`): 窗口搜索的最大标量（相对于周期）
- **window_points_step** (`int`, 默认 `10`): 窗口点数步长
- **show_progress** (`bool`, 默认 `False`): 是否显示进度条

#### 返回值

- `str`: 生成的特征文件路径

#### 异常

- `ValueError`: 如果原始文件不包含 transient 数据

### 提取的特征

v2_feature 提取以下特征（每个周期一个值）：

| 特征名 | 单位 | 描述 |
|-------|------|------|
| `tau_on` | 秒 (s) | 开启时间常数 |
| `tau_off` | 秒 (s) | 关闭时间常数 |
| `tau_on_r2` | - | tau_on 拟合的 R² 值 |
| `tau_off_r2` | - | tau_off 拟合的 R² 值 |

所有特征存储在 `data_type='transient'`，版本名为 `'v2'`。

## 读取特征

### 使用 FeatureRepository

```python
from infra.features import FeatureRepository

repo = FeatureRepository("data/features/chip-device-feat_*.h5")

# 读取单个特征
tau_on = repo.get_feature('tau_on', data_type='transient')
tau_off = repo.get_feature('tau_off', data_type='transient')

print(f"tau_on: {tau_on}")
print(f"tau_off: {tau_off}")
```

### 读取版本矩阵

```python
from infra.features import VersionManager

version_mgr = VersionManager("data/features/chip-device-feat_*.h5")

# 获取 v2 版本矩阵（包含所有特征）
matrix = version_mgr.get_version_matrix('v2', data_type='transient')
print(f"Version matrix shape: {matrix.shape}")
# 输出: (n_cycles, 4)  # 4个特征
```

### 使用 UnifiedExperimentManager

```python
from infra.catalog import UnifiedExperimentManager

manager = UnifiedExperimentManager('catalog_config.yaml')
exp = manager.get_experiment(chip_id="#20250804008", device_id="3")

# 获取 transient 特征（V2）
df = exp.get_feature_dataframe('v2', data_type='transient')
print(df.head())
```

## 与 V1 特征的比较

| 特性 | V1 (transfer) | V2 (transient) |
|------|---------------|----------------|
| **数据类型** | Transfer 曲线 | Transient 时序 |
| **提取算法** | oect_transfer.BatchTransfer | autotau.CyclesAutoTauFitter |
| **特征内容** | gm, Von, \|I\|, 坐标 | tau_on, tau_off, R² |
| **并行方式** | 内置批处理 | ProcessPoolExecutor |
| **data_type** | `'transfer'` | `'transient'` |
| **版本名** | `'v1'` | `'v2'` |
| **步骤数量** | Transfer 步骤数 | Transient 周期数 |

## 性能调优

### 并行度设置

```python
import os

# 获取 CPU 核心数
n_cores = os.cpu_count()

# 推荐设置
# - 小文件（<1000个周期）：max_workers = 2-4
# - 中等文件（1000-5000个周期）：max_workers = 4-8
# - 大文件（>5000个周期）：max_workers = 8-16

feature_file = v2_feature(
    raw_file_path=raw_file,
    max_workers=min(8, n_cores - 1)  # 保留1个核心给系统
)
```

### 窗口参数调优

```python
# 更精细的窗口搜索（速度慢但准确）
feature_file = v2_feature(
    raw_file_path=raw_file,
    window_scalar_min=0.15,
    window_scalar_max=0.4,
    window_points_step=5,  # 更小的步长
    max_workers=8
)

# 更快的窗口搜索（速度快但可能不够准确）
feature_file = v2_feature(
    raw_file_path=raw_file,
    window_scalar_min=0.2,
    window_scalar_max=0.35,
    window_points_step=20,  # 更大的步长
    max_workers=8
)
```

## autotau 版本兼容性

v2_feature 使用 autotau v0.3.0+ 的新 API：

- ✅ **推荐**：`CyclesAutoTauFitter` + `fitter_factory` 模式
- ❌ **废弃**：`ParallelAutoTauFitter` 和 `ParallelCyclesAutoTauFitter`

### 新 API 优势

1. **灵活的并行策略**：可以与上层框架（如 features_v2）协调
2. **避免嵌套并行问题**：不会与其他并行工具冲突
3. **更好的资源控制**：可以精确控制并行度

## 故障排除

### 问题1：找不到 transient 数据

```
ValueError: 无法分析 Transient 特征，文件中没有 Transient 数据
```

**解决方案**：
- 确认原始文件包含 transient 测量数据
- 使用 `exp.has_transient_data()` 检查

### 问题2：周期估计不准确

**症状**：提取的 tau 值不合理或 R² 值很低

**解决方案**：
- 手动指定 `period` 参数
- 使用 `estimate_period_from_signal()` 辅助函数

```python
from infra.features_version import estimate_period_from_signal
from infra.experiment import Experiment

exp = Experiment(raw_file)
data = exp.get_transient_all_measurement()

period = estimate_period_from_signal(
    data['continuous_time'],
    data['drain_current']
)
print(f"Estimated period: {period}s")

# 使用估计的周期
feature_file = v2_feature(raw_file, period=period)
```

### 问题3：内存不足

**症状**：处理大文件时内存溢出

**解决方案**：
- 减少 `max_workers` 数量
- 增大 `window_points_step`（减少搜索精度）
- 处理较短的数据段

## 示例代码

完整示例请参考：`example/v2_feature_demo.py`

```bash
cd infra/features_version/example
python v2_feature_demo.py
```

## 文件结构

```
features_version/
├── v1_feature.py              # V1: Transfer features
├── v2_feature.py              # V2: Transient tau features (NEW)
├── batch_create_feature.py    # Batch processing
├── create_version_utils.py    # Version management
├── __init__.py                # Module exports
├── V2_FEATURE_README.md       # This file
└── example/
    └── v2_feature_demo.py     # Usage examples
```

## 参考文档

- **autotau**: [GitHub](https://github.com/Durian-leader/autotau) | [Documentation](https://autotau.readthedocs.io/)
- **features 模块**: `package/infra/features/CLAUDE.md`
- **experiment 模块**: `package/infra/experiment/CLAUDE.md`
- **features_version 模块**: `package/infra/features_version/CLAUDE.md`

## 版本历史

- **v2.0.0** (2025-11): 初始版本
  - 基于 autotau v0.3.0+ 实现
  - 支持多核并行处理
  - 自动周期估计
  - 与 V1 features 统一存储

## 许可证

本项目遵循与 oect-infra 包相同的许可证。
