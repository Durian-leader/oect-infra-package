# infra/features_v2 — 模块说明（中文）

本模块提供一个现代化的特征工程系统（features_v2），面向 OECT 实验数据的“声明式定义 → 依赖图执行 → 结果导出”。文档仅描述本模块真实存在的能力与 API，不涉及模块外实现。

## 模块定位
- 核心理念：DAG 计算图、惰性求值、列式导出（Parquet）。
- 主要场景：基于 Experiment 的 Transfer/Transient 数据批量提取，支持多维特征（如 transient cycles）。
- 顶层出口：`FeatureSet`、`BaseExtractor`、`register`（参见 `infra/features_v2/__init__.py`）。

## 目录结构（简要）
- `core/`：计算图与执行引擎（`ComputeGraph`、`Executor` 等）以及存储帮助。
- `extractors/`：内置特征提取器与注册机制（Transfer/Transient）。
- `config/`：Pydantic 配置 Schema 与解析器（从 YAML/JSON 加载特征定义）。
- `performance/`：并行执行和多级缓存工具（需手动使用）。
- `transforms/`：常用变换（归一化、过滤），独立工具。
- `utils/`：辅助工具（如 `TransientIndexer`）。
- `examples/`：使用示例脚本。

## 依赖与数据输入约定
- 依赖 Experiment：`FeatureSet` 期望一个实验对象 `experiment`，需提供：
  - `get_transfer_all_measurement()` → 包含 `measurement_data` 的结构；模块在内部转换为每步 `{'Vg', 'Id'}` 列表。
  - `get_transient_all_measurement()` → 返回 `step_info_table` 与 `measurement_data`；模块在内部转换为每步 `{'continuous_time','original_time','drain_current'}` 列表。
  - 具体 Experiment/数据目录结构见对应模块的 CLAUDE.md。
- Transfer 提取依赖：`infra.oect_transfer.BatchTransfer`（模块详情见对应模块的 CLAUDE.md）。
- Transient 提取器使用 `scipy`（`signal/optimize`）。

## 核心 API（对外）

### FeatureSet（用户主入口）

#### 构造与配置
- 构造：`FeatureSet(experiment=None, unified_experiment=None, config_name=None, config_version='1.0')`
  - `experiment`：底层 Experiment 实例
  - `unified_experiment`：UnifiedExperiment 实例（推荐，支持增量计算）
  - `config_name`：配置名称（用于缓存查找）
  - `config_version`：配置版本号（默认 '1.0'）
- `from_config(config_path: str, experiment=None, unified_experiment=None) -> FeatureSet`
  - 从 YAML/JSON 配置文件加载 FeatureSet
  - 自动提取配置名称（从文件名）

#### 特征定义
- `add(name, extractor=None, func=None, input=None, params=None, output_shape=None)`
  - `extractor`：注册名（如 `'transfer.gm_max'`）
  - `func`：自定义函数；单输入直接传值，多输入按顺序解包；需返回 `np.ndarray`
  - `input`：字符串或列表；可为数据源（`'transfer'|'transient'`）或其他特征名
  - `output_shape`：使用 `func` 时建议显式给出，默认按标量特征处理

#### 执行与导出
- `compute() -> Dict[str, np.ndarray]` **✨ 支持增量计算**
  - 优先从 Parquet 缓存加载已有特征（需提供 `unified_experiment` 和 `config_name`）
  - 自动验证缓存有效性（基于源文件哈希）
  - 只计算缺失的特征，大幅提升性能
  - 返回特征字典（不包含数据源条目）
- `to_dataframe(expand_multidim=True) -> pd.DataFrame`
  - 多维特征在展开模式下拆为多列，附 `step_index`
- `to_parquet(output_path, merge_existing=False, save_metadata=True)` **✨ 增强版**
  - `merge_existing`：增量合并已有文件（覆盖同名列，追加新列）
  - `save_metadata`：保存元数据（chip_id, device_id, source_hash 等，用于缓存验证）
  - 自动验证行数一致性

#### 配置固化（新功能）
- `save_as_config(config_name, save_parquet=True, append=False, config_dir='user', description='') -> Dict` **✨ 新增**
  - 将当前特征集固化为 YAML 配置 + Parquet 数据
  - `append=True`：智能合并已有配置（去重、版本递增）
  - `config_dir`：
    - `'user'`：保存到 `~/.my_features/`（个人配置）
    - `'global'`：保存到 `infra/catalog/feature_configs/`（全局共享）
    - 其他：自定义路径
  - 返回：`{'config_file', 'parquet_file', 'features_added', 'config_version'}`

#### 其他工具
- `get_statistics() -> Dict[str, Any]`
  - 包括 `total_features/total_time_ms/cache_hits/cache_misses/avg_time_per_feature_ms/slowest_feature`
- `visualize_graph() -> str`：文本化展示计算图

#### 注意事项
- 当涉及数据源（`'transfer'|'transient'`）时必须先设置 `experiment`，否则 `compute()` 会报错
- 增量计算需要 `unified_experiment` 和 `config_name` 配合使用
- Lambda 函数可序列化到配置，命名函数会收到警告

### 提取器注册机制
- `BaseExtractor`：提取器基类，需实现：
  - `extract(data, params) -> np.ndarray`
  - `output_shape` 属性（如 `('n_steps',)` 或 `('n_steps', k)`）。
- `register(name: str)`：装饰器，将提取器类注册为给定名称（建议 `category.name`）。
- `infra.features_v2.extractors.get_extractor(name, params)`：按名实例化（供内部使用，也可外部手动使用）。

### ✨ Context Access（上下文访问）**新功能 v2.1.0**

特征提取器可以透明访问实验元数据和 workflow 参数，**无需手动配置**。

#### 核心 API
- `get_current_context() -> Optional[ExtractionContext]`
  - 获取当前执行上下文（特征提取期间可用）
  - 返回 `None` 如果在提取外调用
- `require_context() -> ExtractionContext`
  - 获取上下文或抛出异常（用于强制要求上下文的 extractor）
- `has_context() -> bool`
  - 检查上下文是否可用

#### ExtractionContext 属性
- `chip_id: str` - 芯片 ID（如 `'#20250804008'`）
- `device_id: str` - 器件 ID（如 `'3'`）
- `config_name: Optional[str]` - 特征配置名称
- `config_version: Optional[str]` - 配置版本
- `workflow: Dict[str, Any]` - 扁平化的 workflow 元数据
- `get_workflow_param(param_path, default=None)` - 安全访问 workflow 参数
- `has_workflow_param(param_path) -> bool` - 检查参数是否存在
- `unified_experiment` - UnifiedExperiment 实例

#### 使用示例
```python
from infra.features_v2.extractors.base import BaseExtractor, register
from infra.features_v2.core.context import get_current_context

@register('my_feature.smart_charge')
class SmartChargeExtractor(BaseExtractor):
    def extract(self, data, params):
        # ✅ 直接访问上下文（零配置）
        ctx = get_current_context()

        if ctx:
            # 访问 workflow 参数
            sampling_rate = ctx.get_workflow_param(
                'workflow_step_1_1_param_sampling_rate',
                default=1000
            )

            # 访问实验元数据
            chip_id = ctx.chip_id
            device_id = ctx.device_id

            print(f"处理 {chip_id} Device {device_id}, 采样率={sampling_rate}Hz")
        else:
            # Fallback（无上下文时）
            sampling_rate = params.get('fallback_sampling_rate', 1000)

        # 使用 sampling_rate 计算特征...
        transient_list = data
        result = []
        for step_data in transient_list:
            time = step_data.get('continuous_time')
            if time is None:
                time = np.arange(len(step_data['drain_current'])) / sampling_rate
            charge = np.trapz(step_data['drain_current'], time)
            result.append(charge)

        return np.array(result)

    @property
    def output_shape(self):
        return ('n_steps',)
```

#### 最佳实践
1. **始终检查上下文可用性**：使用 `if ctx:` 提供 fallback
2. **使用 `get_workflow_param()` 安全访问**：避免 KeyError
3. **提供默认值**：确保在无上下文时也能工作
4. **需要 UnifiedExperiment**：上下文需要通过 `FeatureSet(unified_experiment=exp)` 设置

#### 线程安全性
- 使用 Python `contextvars` 实现，天然支持多线程/异步
- 每个执行上下文自动隔离，无需担心并发问题

#### 完整示例
参见：`infra/features_v2/extractors/examples/context_usage_demo.py`
- 4 个完整示例 extractor
- 涵盖常见用例（采样率、归一化、元数据等）

## 内置提取器（已实现）

以下名称均为可在 `FeatureSet.add(..., extractor=...)` 中使用的注册名：

### Transfer（依赖 `infra.oect_transfer.BatchTransfer`）
- `transfer.gm_max`
  - 参数：`direction: 'forward'|'reverse'|'both'`（默认 `'forward'`），`device_type: 'N'|'P'`（默认 `'N'`）。
  - 输出：`(n_steps,)` 或当 `direction='both'` 时 `(n_steps, 2)`。
- `transfer.Von`
  - 参数同上；输出与 `gm_max` 相同的形状规则。
- `transfer.absI_max`
  - 参数：`device_type: 'N'|'P'`（默认 `'N'`）。
  - 输出：`(n_steps,)`。
- `transfer.gm_max_coords`
  - 参数：`direction: 'forward'|'reverse'`；可选 `return_vg_only`、`return_id_only`（二者互斥）。
  - 输出：`(n_steps, 2)`；当仅返回单列时为 `(n_steps,)`。
- `transfer.Von_coords`
  - 参数与 `gm_max_coords` 一致；输出同形状规则。

输入约定（本模块内部已完成转换）：每步为 `{'Vg': array, 'Id': array}` 的列表；长度不等时使用 NaN 对齐。

### Transient（依赖 `scipy`）
- `transient.cycles`
  - 参数：`n_cycles`（默认 100）；`method: 'peak_detection'|'fixed_interval'|'percentile'` 及其细化参数（如 `min_distance/prominence`）。
  - 输出：`(n_steps, n_cycles)`（不足部分以 NaN 填充）。
- `transient.peak_current`
  - 参数：`use_abs: bool`（默认 True）。
  - 输出：`(n_steps,)`。
- `transient.decay_time`
  - 参数：`fit_range`（比例范围，默认 `[0.1, 0.9]`），`method: 'exponential'|'linear'`。
  - 输出：`(n_steps,)`（拟合失败返回 NaN）。

输入约定：每步为 `{'continuous_time','original_time','drain_current'}` 的列表。

## 配置系统（`config/`）
- Schema：`FeatureConfig`、`FeatureSpec`、`DataSourceConfig`、`PostProcessStep`、`VersioningConfig`（Pydantic）。
- 解析：`ConfigParser.from_file(config_path, experiment)` → `FeatureSet`。
- `FeatureSpec` 关键字段：
  - `name`、`extractor` 或 `func`（二选一）、`input`、`params`、`output_shape`（使用 `func` 时建议显式提供）。
  - `func` 支持 `lambda` 与 `numpy` 函数字符串（解析时仅暴露 `np/numpy` 命名空间）。
- 模板：见 `config/templates/*.yaml`（如 `v2_transfer_basic.yaml`、`v2_transient_cycles.yaml`、`v2_mixed.yaml`）。

重要说明：Schema 中定义的 `postprocessing/advanced.transforms` 等字段当前解析器未自动应用到执行流程；如需使用变换，请在业务层手动调用 `transforms` 中工具（见下）。

## 执行与性能
- 串行执行：`core.Executor`（`FeatureSet.compute()` 默认使用）。
- 并行执行：`performance.parallel.ParallelExecutor`
  - 策略：按 `ComputeGraph.group_parallel_nodes()` 分层；同层并行、跨层串行。
  - 需手动构造并传入与 `Executor` 相同依赖（示例见 `examples/phase2_demo.py`）。
- 统计：通过 `ExecutionContext` 聚合单节点耗时等信息。
- 缓存：`performance.cache.MultiLevelCache` 提供“内存 LRU + 磁盘”两级缓存；当前未集成到默认执行器，需要手动使用。文件级包装器 `CachedExecutor` 仍为占位实现。

## 变换与工具
- `transforms.Normalize`：方法 `minmax|zscore|robust|l2`；`__call__/transform(np.ndarray)->np.ndarray`。
- `transforms.Filter`：条件过滤与异常值（IQR/Z-score）处理；返回 NaN 掩蔽后的数组。
- `utils.indexing.TransientIndexer`：面向拼接存储的高效切片/并行提取（`get_step_slice/batch_slice/parallel_extract/get_statistics`）。
- 存储辅助（`core/storage.py`）：
  - `save_features(features, output_path, metadata=None, compression='zstd')`
  - `load_features(parquet_path, feature_names=None, restore_multidim=False)`

## 使用示例

### 基础示例
```python
from infra.features_v2 import FeatureSet
import infra.features_v2.extractors.transfer  # 确保注册

features = FeatureSet(experiment=exp)
features.add(
    'gm_max_forward', extractor='transfer.gm_max', input='transfer',
    params={'direction': 'forward', 'device_type': 'N'}
)
features.add(
    'gm_norm', func=lambda x: (x - x.mean())/x.std(), input='gm_max_forward',
    output_shape=('n_steps',)
)
result = features.compute()
df = features.to_dataframe()
features.to_parquet('out.parquet')
```

### ✨ 增量式工作流示例（新功能）

**阶段 1：首次探索 - 定义基础特征**
```python
from infra.features_v2 import FeatureSet
from infra.catalog import UnifiedExperimentManager

manager = UnifiedExperimentManager('catalog_config.yaml')
exp = manager.get_experiment(chip_id="#20250804008", device_id="3")

# 创建特征集（指定配置名称）
features = FeatureSet(
    unified_experiment=exp,
    config_name='my_base_features',
    config_version='1.0'
)

# 添加基础特征
features.add('gm_max', extractor='transfer.gm_max', input='transfer')
features.add('Von', extractor='transfer.Von', input='transfer')
features.add('absI_max', extractor='transfer.absI_max', input='transfer')

# 计算（耗时 82 分钟，示例数据）
result = features.compute()

# 固化配置和数据
info = features.save_as_config(
    config_name='my_base_features',
    save_parquet=True,
    config_dir='user',  # 保存到 ~/.my_features/
    description="我的基础特征集合"
)
print(f"✓ 配置: {info['config_file']}")
print(f"✓ Parquet: {info['parquet_file']}")
```

**阶段 2：增量扩展 - 添加派生特征**
```python
# 加载已固化的配置
features_v2 = FeatureSet.from_config(
    '~/.my_features/my_base_features.yaml',
    unified_experiment=exp
)

# 添加派生特征
features_v2.add(
    'gm_normalized',
    func=lambda gm: (gm - gm.mean()) / gm.std(),
    input='gm_max',  # ✅ 从 Parquet 缓存读取
    output_shape=('n_steps',)
)
features_v2.add(
    'gm_to_current_ratio',
    func=lambda gm, i: gm / (i + 1e-10),
    input=['gm_max', 'absI_max'],  # ✅ 都从缓存读取
    output_shape=('n_steps',)
)

# 增量计算
result_v2 = features_v2.compute()
# ✅ gm_max, Von, absI_max 从 Parquet 读取（<1秒）
# ⚙️ 只计算 gm_normalized, gm_to_current_ratio（~1秒）
# 总耗时：~2秒 vs 82分钟 🚀

# 增量保存（合并到原配置）
info = features_v2.save_as_config(
    'my_base_features',
    append=True,  # ✅ 智能合并
    save_parquet=True
)
print(f"✓ 新增特征: {info['features_added']}")
# ['gm_normalized', 'gm_to_current_ratio']
print(f"✓ 配置版本: {info['config_version']}")  # 1.1
```

**阶段 3：缓存自动失效**
```python
# 再次加载（应该全部命中缓存）
features_v3 = FeatureSet.from_config(
    '~/.my_features/my_base_features.yaml',
    unified_experiment=exp
)

result_v3 = features_v3.compute()
# ✅ 全部特征从缓存读取，耗时 ~1秒

# 如果 HDF5 文件被重新生成...
# ⚠️ 系统自动检测源文件哈希改变，缓存失效
# ⚙️ 自动重新计算所有特征
```

**完整演示脚本**：
- `examples/incremental_workflow_demo.py` - 完整的三阶段演示

## 版本
- 本模块版本：`__version__ = '2.0.0'`（见 `infra/features_v2/__init__.py`）。
- **增量式特征工程**: v2.1.0（2025-10-31 新增）

## 限制与注意
- 使用 `func` 自定义特征时，需返回 `np.ndarray`；未显式 `output_shape` 时将按标量特征处理并给出警告。
- `FeatureSet.compute()` 只返回特征节点结果，不包含数据源条目。
- Transient 提取器依赖 `scipy`；Parquet 导出依赖 `pandas` 的相应引擎。
- 并行与缓存工具当前不自动随 `FeatureSet.compute()` 生效，需按需手动接入。
