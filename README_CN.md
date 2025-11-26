# OECT-Infra

**用于 OECT(有机电化学晶体管)实验的综合数据处理基础设施**

[![PyPI version](https://badge.fury.io/py/oect-infra.svg)](https://badge.fury.io/py/oect-infra)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 概述

OECT-Infra 是一个端到端的平台,将原始实验数据转换为高性能的结构化格式,为 OECT 研究提供标准化的特征工程、可视化和报告生成能力。

### 核心功能

- **🔄 数据转换**: 从 CSV/JSON 并行批量转换为标准化 HDF5 格式
- **📊 延迟加载 API**: 通过智能缓存高效访问实验元数据和测量数据
- **🔧 特征工程**:
  - **V1**: 以列式 HDF5 格式提取转移特性(gm、Von、|I| 等)
  - **V2**: 基于 DAG 的高级提取,支持 YAML 配置、Parquet 存储和 HuggingFace 风格的 API
- **📁 统一数据目录**: 基于 SQLite 的索引,支持文件↔数据库双向同步
- **📈 可视化**: 高性能绘图,支持动画/视频导出
- **📄 自动报告生成**: 可配置的 PowerPoint 稳定性分析报告生成
- **📉 降解分析**: 17+ 种幂律模型,支持多指标比较框架

## 安装

```bash
pip install oect-infra
```

### 系统要求

- Python 3.11 或更高版本
- 核心依赖: h5py、pandas、numpy、matplotlib、pydantic、scipy、scikit-learn、PyYAML

## 快速入门

### 使用统一接口

```python
from infra.catalog import UnifiedExperimentManager

# 初始化管理器
manager = UnifiedExperimentManager('catalog_config.yaml')

# 获取实验
exp = manager.get_experiment(chip_id="#20250804008", device_id="3")

# 访问数据
transfer_data = exp.get_transfer_data()
features = exp.get_features(['gm_max_forward', 'Von_forward'])

# 可视化
fig = exp.plot_transfer_evolution()
```

### 使用命令行界面

```bash
# 初始化目录系统
catalog init --auto-config

# 扫描并索引 HDF5 文件
catalog scan --path data/raw --recursive

# 同步数据
catalog sync --direction both

# 查询实验
catalog query --chip "#20250804008" --output table

# 提取特征 V2
catalog v2 extract-batch --feature-config v2_ml_ready --workers 4
```

### 特征 V2 提取

```python
# 使用 V2 提取单个实验
exp = manager.get_experiment(chip_id="#20250804008", device_id="3")
result_df = exp.extract_features_v2('v2_transfer_basic', output_format='dataframe')

# 批量提取
experiments = manager.search(chip_id="#20250804008")
result = manager.batch_extract_features_v2(
    experiments=experiments,
    feature_config='v2_ml_ready',
    save_format='parquet',
    n_workers=4
)
```

## 架构

### 分层设计

**核心基础层 (L0)**
- `csv2hdf`: 数据转换
- `experiment`: 数据访问
- `oect_transfer`: 转移特性分析
- `features`: 特征存储

**业务应用层 (L1)**
- `features_version`: 特征工作流 V1
- `features_v2`: 特征工程 V2 系统
- `visualization`: 绘图工具

**应用集成层 (L2)**
- `catalog`: 统一管理
- `stability_report`: 报告生成

### 数据流管道

```
CSV/JSON → csv2hdf → 原始 HDF5 → experiment (延迟加载)
         → [V1] oect_transfer & features_version → 特征 HDF5
         → [V2] features_v2 (DAG 计算图) → 特征 Parquet
         → catalog (索引 + 工作流元数据) → visualization/stability_report
```

## 配置

OECT-Infra 使用 YAML 配置文件。创建 `catalog_config.yaml`:

```yaml
roots:
  raw_data: "data/raw"
  features_v1: "data/features"
  features_v2: "data/features_v2"

database:
  path: "catalog.db"

sync:
  conflict_strategy: "keep_newer"
```

## 文档

- [完整文档](https://github.com/Durian-leader/oect-infra-package/blob/main/README.md)
- 已安装包中包含的软件包文档
- 详细的模块文档请参阅 `infra/` 子目录

## 示例

在源代码[仓库](https://github.com/Durian-leader/oect-infra-package)中查看示例笔记本:
- 包中包含示例笔记本和脚本
- 模块文档字符串中包含全面的 API 文档

## 贡献

欢迎贡献! 请随时提交 Pull Request。

## 许可证

本项目采用 MIT 许可证 - 详情请参阅 [LICENSE](LICENSE) 文件。

## 引用

如果您在研究中使用 OECT-Infra,请引用:

```bibtex
@software{oect_infra,
  author = {lidonghao},
  title = {OECT-Infra: Data Processing Infrastructure for OECT Experiments},
  year = {2025},
  url = {https://github.com/Durian-leader/oect-infra-package}
}
```

## 支持

如有问题和疑问:
- GitHub Issues: https://github.com/Durian-leader/oect-infra-package/issues
- 邮箱: lidonghao100@outlook.com

## 致谢

本项目是为 OECT(有机电化学晶体管)研究开发的,为材料科学和电化学研究提供高效的数据管理、分析和可视化工具。