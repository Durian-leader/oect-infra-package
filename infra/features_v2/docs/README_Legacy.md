# Features V2 - 现代化特征工程系统

## 🎯 核心理念

**"计算图 + 惰性求值 + 列式存储"** - 提供类似 Polars/Dask 的声明式 API，兼具 HuggingFace datasets 的易用性。

### 设计目标

- ✅ **易用性**：声明式 API，5 行代码完成特征提取
- ✅ **灵活性**：原生支持多维特征（如 100 个 transient cycles）
- ✅ **高性能**：计算图优化、并行执行、多层缓存
- ✅ **可扩展**：插件式提取器注册机制

---

## 🚀 快速开始

### 基础用法

```python
from infra.features_v2 import FeatureSet
from infra.catalog import UnifiedExperimentManager
import infra.features_v2.extractors.transfer  # 注册 transfer 提取器

# 1. 加载实验
manager = UnifiedExperimentManager('catalog_config.yaml')
exp = manager.get_experiment(chip_id="#20250804008", device_id="3")

# 2. 创建特征集合
features = FeatureSet(experiment=exp)

# 3. 添加特征
features.add('gm_max', extractor='transfer.gm_max',
             input='transfer', params={'direction': 'forward'})
features.add('Von', extractor='transfer.Von',
             input='transfer', params={'direction': 'forward'})

# 4. 计算
result = features.compute()  # 返回 Dict[str, np.ndarray]

# 5. 导出
df = features.to_dataframe()
features.to_parquet('output.parquet')
```

运行示例：
```bash
conda run --name mlpytorch python infra/features_v2/examples/quickstart.py
```

---

## 📋 核心功能

### 1. 多种特征定义方式

#### 方式 1: 使用预定义提取器
```python
features.add('gm_max_forward',
             extractor='transfer.gm_max',
             input='transfer',
             params={'direction': 'forward', 'device_type': 'N'})
```

#### 方式 2: 使用 Lambda 函数
```python
features.add('mean_current',
             func=lambda transfer: np.mean([s['Id'] for s in transfer]),
             input='transfer',
             output_shape=('n_steps',))
```

#### 方式 3: 创建派生特征（依赖其他特征）
```python
features.add('gm_normalized',
             func=lambda gm: (gm - gm.mean()) / gm.std(),
             input='gm_max_forward',
             output_shape=('n_steps',))
```

### 2. 计算图自动优化

系统自动构建特征依赖的 DAG，并进行：
- ✅ 拓扑排序（确定执行顺序）
- ✅ 识别可并行节点（Phase 2 将实现并行执行）
- ✅ 共享数据加载（数据源只加载一次）

可视化计算图：
```python
print(features.visualize_graph())
```

输出示例：
```
计算图结构：
  gm_max_forward ← transfer
  gm_max_reverse ← transfer
  Von_forward ← transfer
  gm_max_normalized ← gm_max_forward
```

### 3. 性能监控

```python
stats = features.get_statistics()
print(f"总耗时: {stats['total_time_ms']:.2f} ms")
print(f"最慢特征: {stats['slowest_feature']}")
```

---

## 🔧 自定义提取器

### 创建自定义提取器

```python
from infra.features_v2.extractors.base import BaseExtractor, register
import numpy as np

@register('custom.my_extractor')
class MyExtractor(BaseExtractor):
    """自定义提取器"""

    def extract(self, data, params):
        """
        Args:
            data: 输入数据（根据 input 参数自动传入）
                  - input='transfer' → list of {'Vg': array, 'Id': array}
                  - input='transient' → list of {'drain_current': array, ...}
            params: 配置参数

        Returns:
            np.ndarray: 特征数组
                - (n_steps,) - 标量特征
                - (n_steps, k) - 多维特征
        """
        n_cycles = params.get('n_cycles', 100)
        transfer_list = data['transfer'] if isinstance(data, dict) else data

        result = np.zeros((len(transfer_list), n_cycles))
        for i, step_data in enumerate(transfer_list):
            result[i] = self._compute_cycles(step_data, n_cycles)

        return result

    def _compute_cycles(self, step_data, n_cycles):
        # 实现具体逻辑
        return np.random.rand(n_cycles)  # 示例

    @property
    def output_shape(self):
        n_cycles = self.params.get('n_cycles', 100)
        return ('n_steps', n_cycles)
```

### 使用自定义提取器

```python
# 确保提取器模块被导入（触发 @register 装饰器）
import my_extractors

features.add('my_feature',
             extractor='custom.my_extractor',
             input='transfer',
             params={'n_cycles': 100})
```

---

## 📦 已实现的提取器

### Transfer 特征提取器

| 提取器名称 | 功能 | 输出形状 | 参数 |
|-----------|------|---------|------|
| `transfer.gm_max` | 最大跨导绝对值 | `(n_steps,)` 或 `(n_steps, 2)` | `direction`: 'forward', 'reverse', 'both' |
| `transfer.Von` | 开启电压 | `(n_steps,)` 或 `(n_steps, 2)` | `direction`: 'forward', 'reverse', 'both' |
| `transfer.absI_max` | 最大电流绝对值 | `(n_steps,)` | - |
| `transfer.gm_max_coords` | 最大跨导坐标 (Vg, Id) | `(n_steps, 2)` | `direction`, `return_vg_only`, `return_id_only` |
| `transfer.Von_coords` | Von 坐标 (Vg, Id) | `(n_steps, 2)` | 同上 |

所有提取器支持 `device_type` 参数：`'N'` 或 `'P'`（默认 `'N'`）。

---

## 🗂️ 模块结构

```
features_v2/
├── core/                      # 核心引擎
│   ├── feature_set.py        # FeatureSet（用户主接口）
│   ├── compute_graph.py      # 计算图（DAG 构建、拓扑排序）
│   ├── executor.py           # 执行引擎（串行/并行）
│   └── storage.py            # Parquet 存储
├── extractors/                # 特征提取器
│   ├── base.py               # BaseExtractor + 注册机制
│   ├── transfer.py           # Transfer 提取器
│   └── transient.py          # Transient 提取器（TODO）
├── config/                    # 配置系统（Phase 2）
├── performance/               # 性能优化（缓存、并行）
├── examples/                  # 使用示例
│   └── quickstart.py         # 快速开始
└── README.md                  # 本文档
```

---

## 🎯 Phase 1 完成状态 (当前)

### ✅ 已实现

- [x] 核心架构
  - [x] ComputeGraph（DAG 构建、拓扑排序、并行分组）
  - [x] Executor（串行执行）
  - [x] ExecutionContext（结果缓存、性能监控）

- [x] FeatureSet API
  - [x] `add()` 方法（支持提取器和函数）
  - [x] `compute()` 方法
  - [x] `to_dataframe()` 和 `to_parquet()` 导出

- [x] 提取器系统
  - [x] BaseExtractor 抽象类
  - [x] `@register` 装饰器
  - [x] Transfer 特征提取器（5 个）

- [x] 数据加载
  - [x] 自动加载 Transfer 数据
  - [x] 自动加载 Transient 数据（准备就绪）

- [x] 存储层
  - [x] Parquet 保存/加载
  - [x] 支持多维特征展开

### 📊 性能基准

**当前性能**（Phase 1，5001 步数据）：
- Transfer 数据加载：~28s（包含所有 5001 步）
- 单个特征计算：~1-7s
- 总计（5 个特征）：~28s

**性能瓶颈分析**：
1. 数据加载占主要时间（加载 5001 步的 3D 数组）
2. BatchTransfer 计算相对较快
3. 无并行优化

---

## 🚧 Phase 2 规划

### 性能优化

- [ ] **并行执行**
  - [ ] `ParallelExecutor` 实现
  - [ ] 基于 `group_parallel_nodes()` 并行同层节点
  - [ ] ProcessPoolExecutor 或 Ray

- [ ] **多层缓存**
  - [ ] L1: 内存缓存（LRU）
  - [ ] L2: 磁盘缓存（Parquet）
  - [ ] L3: 预计算索引

- [ ] **JIT 编译**
  - [ ] Numba 加速关键计算
  - [ ] NumPy 向量化优化

- [ ] **Transient 批量优化**
  - [ ] `TransientIndexer`（高效索引）
  - [ ] 批量切片（利用拼接存储的局部性）

### 功能扩展

- [ ] **Transient 提取器**
  - [ ] Cycle 提取
  - [ ] FFT 分析
  - [ ] 衰减拟合

- [ ] **配置文件系统**
  - [ ] YAML/JSON 配置解析
  - [ ] `FeatureSet.from_config()` 实现
  - [ ] 配置模板库

- [ ] **Transform 系统**
  - [ ] Normalize
  - [ ] Filter
  - [ ] Aggregate

---

## 🔍 对比：V1 vs V2

| 特性 | V1 (features) | V2 (features_v2) |
|------|--------------|------------------|
| **数据模型** | 只支持 1D 标量 | 原生支持多维（任意维度） |
| **API 风格** | 命令式（`repo.store_feature()`） | 声明式（`features.add()`） |
| **计算优化** | 无 | 计算图自动优化 |
| **自定义** | 需要修改代码 | `@register` 装饰器 |
| **性能监控** | 无 | 内置统计 |
| **版本管理** | 固化的版本矩阵 | 动态特征组合 |
| **扩展性** | 低（紧耦合） | 高（插件式） |

---

## 💡 最佳实践

### 1. 命名约定

- **提取器名称**：`category.name`
  - 示例：`transfer.gm_max`, `transient.cycles`, `custom.my_feature`

- **特征名称**：描述性 + 后缀
  - 示例：`gm_max_forward`, `Von_reverse`, `cycles_mean`

### 2. 性能优化建议

- **按需加载**：只添加需要的特征
- **复用计算**：使用派生特征而非重复计算
- **缓存结果**：多次使用同一特征集时，缓存 Parquet 文件

### 3. 调试技巧

```python
# 可视化计算图
print(features.visualize_graph())

# 查看性能瓶颈
stats = features.get_statistics()
print(f"最慢特征: {stats['slowest_feature']}")

# 单独测试提取器
from infra.features_v2.extractors import get_extractor
extractor = get_extractor('transfer.gm_max', {'direction': 'forward'})
result = extractor.extract(transfer_data, {})
```

---

## 📚 示例库

### 示例 1：基础 Transfer 特征

见 `examples/quickstart.py`

### 示例 2：自定义提取器（TODO）

见 `examples/custom_extractor.py`

### 示例 3：批量处理（TODO）

见 `examples/batch_processing.py`

---

## 🤝 贡献指南

### 添加新提取器

1. 在 `extractors/` 下创建文件（如 `transient.py`）
2. 继承 `BaseExtractor` 并使用 `@register` 装饰器
3. 实现 `extract()` 和 `output_shape` 属性
4. 在 `examples/` 中添加使用示例

### 性能优化

1. 在 `examples/benchmark.py` 中添加基准测试
2. 使用 `cProfile` 或 `line_profiler` 分析瓶颈
3. 优化后确保通过原有测试

---

## 📞 反馈与支持

- **Bug 报告**：在项目 issue tracker 中提交
- **功能请求**：描述使用场景和预期 API
- **性能问题**：提供数据规模和性能分析结果

---

**版本**：2.0.0
**最后更新**：2025-10-30
**状态**：Phase 1 完成 ✅
