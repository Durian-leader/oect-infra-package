# 模块依赖关系图

## 层级架构

```
┌─────────────────────────────────────────────────────────────┐
│                      应用集成层 (Layer 2)                    │
├─────────────────────────────────────────────────────────────┤
│  stability_report/     稳定性报告生成                        │
│    └── catalog                                              │
│                                                             │
│  catalog/              元数据管理与统一接口                  │
│    ├── csv2hdf                                              │
│    ├── experiment                                           │
│    ├── features                                             │
│    ├── features_version                                     │
│    └── visualization                                        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                      业务应用层 (Layer 1)                    │
├─────────────────────────────────────────────────────────────┤
│  features_version/     特征版本化工具                        │
│    ├── experiment                                           │
│    ├── oect_transfer                                        │
│    └── features                                             │
│                                                             │
│  visualization/        数据可视化                           │
│    └── experiment                                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                      核心基础层 (Layer 0)                    │
├─────────────────────────────────────────────────────────────┤
│  csv2hdf/              CSV→HDF5数据转换                      │
│  experiment/           实验数据管理核心API                    │
│  features/             特征数据存储核心                       │
│  oect_transfer/        传输特性分析                          │
└─────────────────────────────────────────────────────────────┘
```

## 数据流向

```
CSV + JSON
    ↓
[csv2hdf]
    ↓
HDF5 原始数据 ────┐
    ↓            │
[experiment] ←───┤
    ↓            │
    ├→ [oect_transfer] → [features_version] → HDF5 特征文件
    ├→ [visualization]
    └→ [catalog] → [stability_report]
```

## 完整依赖树

```
stability_report/
└── catalog/
    ├── csv2hdf/
    ├── experiment/
    ├── features/
    ├── features_version/
    │   ├── experiment/
    │   ├── oect_transfer/
    │   └── features/
    └── visualization/
        └── experiment/

catalog/
├── csv2hdf/
├── experiment/
├── features/
├── features_version/
└── visualization/

features_version/
├── experiment/
├── oect_transfer/
└── features/

visualization/
└── experiment/

csv2hdf/            (独立)
experiment/         (独立)
features/           (独立)
oect_transfer/      (独立)
```

## 核心依赖规则

### 基础层特点
- **完全独立**：不依赖项目内其他业务模块
- **稳定核心**：为上层提供基础API
- **并行开发**：模块间互不影响

### 应用层特点
- **单向依赖**：仅依赖基础层，不反向依赖
- **功能扩展**：基于核心模块提供增强功能
- **可组合性**：可按需选用不同模块

### 集成层特点
- **统一接口**：整合多个下层模块
- **高层抽象**：提供端到端解决方案
- **最大复用**：充分利用现有功能

## 模块职责矩阵

| 模块 | 层级 | 核心功能 | 依赖数量 |
|------|------|----------|---------|
| csv2hdf | L0 | 数据转换 | 0 |
| experiment | L0 | 数据管理 | 0 |
| features | L0 | 特征存储 | 0 |
| oect_transfer | L0 | 传输分析 | 0 |
| visualization | L1 | 数据可视化 | 1 |
| features_version | L1 | 特征版本化 | 3 |
| catalog | L2 | 元数据管理 | 5 |
| stability_report | L2 | 报告生成 | 1 (间接依赖更多) |

> 已归档模块：`oect_transfer_analysis/`、`oect_transient/`（目录已移除，可在版本历史中查阅旧实现）。

## 关键设计原则

1. **分层隔离**：上层可依赖下层，下层不依赖上层
2. **最小耦合**：基础层模块完全独立，互不依赖
3. **清晰职责**：每个模块有明确的单一职责
4. **依赖透明**：模块依赖关系清晰可见
5. **扩展友好**：新增功能优先扩展上层模块