# Lambda 完整序列化解决方案

**修复日期**: 2025-10-31
**问题来源**: `features_v2_incremental_demo.ipynb` Cell[21] 及后续 cells 报错
**影响范围**: Features V2 所有 lambda 函数序列化
**解决方案**: 源代码保留机制（source_code 字段）

---

## 问题描述

### 第一阶段症状（已修复）
当用户添加多参数 lambda 函数（如 `lambda gm, i: gm / (i + 1e-10)`）并保存配置时，lambda 在第一个逗号处被截断：

```python
# 期望提取: lambda gm, i: gm / (i + 1e-10)
# 实际提取: lambda gm
```

### 第二阶段症状（本次修复的核心问题）
从配置文件加载的 lambda 函数无法重新序列化：

```
⚠️ 无法序列化特征 'gm_normalized': could not get source code
⚠️ 无法序列化特征 'gm_to_current_ratio': could not get source code
⚠️ 无法序列化特征 'gm_smooth': could not get source code
```

### 根本原因分析

**第一阶段问题**（已在之前修复）：
Lambda 提取算法在解析源代码时存在缺陷：

```python
# 问题代码（修复前）
if char in (',', '\n') and paren_count == 0 and bracket_count == 0:
    end_idx = i
    break
```

对于多参数 lambda（如 `lambda gm, von: gm / (abs(von) + 1e-10)`），算法在**第一个逗号**（参数分隔符）处就停止了，导致提取结果为：
- ❌ 实际提取: `'lambda gm'`
- ✅ 应该提取: `'lambda gm, von: gm / (abs(von) + 1e-10)'`

**第二阶段问题**（本次修复）：
从配置文件加载的 lambda 是通过 `eval()` 创建的，无法通过 `inspect.getsource()` 获取源代码：

```python
# 工作流程：
# 1. 用户定义 lambda → 2. 保存到 YAML → 3. 从 YAML 加载（eval 创建） → 4. 尝试再次保存
#                                                    ↑
#                                                    inspect.getsource() 失败！
```

原因：`eval()` 创建的函数对象没有关联的源文件，`inspect.getsource()` 无法工作。

---

## 修复方案

### 第一阶段修复：冒号检测机制（已完成）

在 `infra/features_v2/core/feature_set.py` 添加 `colon_found` 标志：

```python
# 智能提取：使用括号平衡算法找到 lambda 表达式的结尾
paren_count = 0
bracket_count = 0
in_string = False
quote_char = None
colon_found = False  # 🔑 关键改进：标记是否已经遇到冒号
end_idx = len(remaining)

for i, char in enumerate(remaining):
    # ... 字符串处理 ...
    # ... 括号计数 ...

    # 标记冒号位置（参数列表结束，表达式开始）
    if char == ':' and paren_count == 0 and bracket_count == 0:
        colon_found = True

    # 检查是否到达 lambda 表达式结尾
    # 🔑 只有在冒号之后，遇到逗号或换行时才结束
    if colon_found and char in (',', '\n') and paren_count == 0 and bracket_count == 0:
        end_idx = i
        break
```

### 关键逻辑

1. **阶段识别**: 区分 lambda 的参数列表（`:` 之前）和表达式体（`:` 之后）
2. **停止条件**: 只有在冒号**之后**遇到逗号或换行才停止，而不是在参数列表中的逗号处停止
3. **向后兼容**: 对单参数 lambda（如 `lambda x: x.mean()`）仍然正常工作

### 第二阶段修复：源代码保留机制（本次实施）⭐

**核心思想**：在添加特征时立即提取并保存 lambda 源代码，序列化时优先使用保存的源代码。

#### 1. 扩展 ComputeNode 数据结构

在 `infra/features_v2/core/compute_graph.py` 添加 `source_code` 字段：

```python
@dataclass
class ComputeNode:
    name: str
    func: Any
    inputs: List[str]
    params: Dict[str, Any] = field(default_factory=dict)
    output_shape: Optional[Tuple] = None
    is_extractor: bool = False
    source_code: Optional[str] = None  # 🔑 新增：保存 lambda 源代码
```

#### 2. 在 add() 时提取源代码

在 `infra/features_v2/core/feature_set.py` 的 `add()` 方法中：

```python
# 尝试提取 lambda 源代码（用于序列化）
source_code = None
if callable(func):
    source_code = self._extract_lambda_source(func)

node = ComputeNode(
    name=name,
    func=func,
    inputs=inputs,
    params=params,
    output_shape=output_shape,
    is_extractor=False,
    source_code=source_code,  # 🔑 保存源代码
)
```

新增辅助方法 `_extract_lambda_source()` 封装提取逻辑（复用第一阶段的括号平衡算法）。

#### 3. 序列化时优先使用保存的源代码

在 `save_as_config()` 中：

```python
# 🔑 优先使用保存的源代码
if node.source_code:
    spec['func'] = node.source_code
    logger.debug(f"✓ 使用保存的源代码: {node_name} <- {node.source_code[:60]}...")
# 检查是否为 lambda（回退方案）
elif '<lambda>' in node.func.__name__:
    # 原有的提取逻辑...
else:
    # 命名函数警告
    ...
```

#### 4. 从配置加载时同步保存源代码

在 `infra/features_v2/config/parser.py` 的 `_add_feature()` 中：

```python
func = self._parse_func(spec.func)
features.add(
    name=spec.name,
    func=func,
    ...
)

# 🔑 手动设置源代码（因为 eval 创建的函数无法通过 inspect 获取）
node = features.graph.nodes[spec.name]
node.source_code = spec.func
```

### 完整工作流程

```
定义 lambda → 提取源代码 → 保存到 ComputeNode.source_code
    ↓
保存配置 → 使用 source_code → 写入 YAML
    ↓
加载配置 → eval 创建函数 → 手动设置 source_code = YAML 中的字符串
    ↓
再次保存 → 使用 source_code → 成功写入 YAML ✅
```

---

## 修复验证

### 测试用例

```python
# 测试 1: 单参数 lambda
lambda x: (x - x.mean()) / x.std()
✅ 提取成功: 'lambda x: (x - x.mean()) / x.std()'

# 测试 2: 多参数 lambda（核心测试）
lambda gm, von: gm / (abs(von) + 1e-10)
✅ 提取成功: 'lambda gm, von: gm / (abs(von) + 1e-10)'

# 测试 3: numpy 函数
lambda x: np.convolve(x, np.ones(10)/10, mode='same')
✅ 提取成功: 'lambda x: np.convolve(x, np.ones(10)/10, mode='same')'
```

### 完整流程验证（三阶段测试）

```python
# 阶段 1：定义并保存
features_stage1 = FeatureSet(unified_experiment=exp)
features_stage1.add('single_param', func=lambda x: (x - x.mean()) / x.std(), input='gm_max')
features_stage1.add('multi_param', func=lambda gm, von: gm / (abs(von) + 1e-10), input=['gm_max', 'Von'])
features_stage1.add('numpy_func', func=lambda x: np.convolve(x, np.ones(10)/10, mode='same'), input='gm_max')
features_stage1.compute()
features_stage1.save_as_config('test_serialization', save_parquet=True)
✅ 所有 lambda 成功序列化

# 阶段 2：从配置加载并重新保存（核心测试）
features_stage2 = FeatureSet.from_config('test_serialization.yaml', unified_experiment=exp)
✅ 配置加载成功，所有节点的 source_code 字段均有值
result_stage2 = features_stage2.compute()
✅ 计算成功，数据一致

# 关键：重新保存配置
features_stage2.save_as_config('test_serialization_v2', save_parquet=True)
✅ 成功保存！所有 lambda 均正确序列化（无 UNSUPPORTED）

# 阶段 3：第三次加载验证可重复性
features_stage3 = FeatureSet.from_config('test_serialization_v2.yaml', unified_experiment=exp)
✅ 加载成功
result_stage3 = features_stage3.compute()
✅ 计算成功，数据一致

# 验证结果
所有 lambda 特征成功序列化: 3/3
所有阶段数据一致性验证通过
🎉 完整序列化测试通过！
```

---

## 连带改进

### 1. 优雅降级机制
在 `infra/features_v2/config/parser.py:84-99` 添加 try-catch：

```python
elif spec.func:
    try:
        func = self._parse_func(spec.func)
        features.add(name=spec.name, func=func, ...)
    except ValueError as e:
        # 跳过无法解析的特征，发出警告
        logger.warning(f"⚠️ 跳过特征 '{spec.name}'：{e}")
        logger.warning(f"   建议：使用提取器或简化 lambda 表达式")
```

**好处**: 即使配置文件中有无法解析的特征（如旧版本的 `# UNSUPPORTED`），系统也不会崩溃，而是跳过该特征并继续加载其他特征。

### 2. 改进验证逻辑
在 `infra/features_v2/core/feature_set.py:572-586`：

```python
# 使用 compile 验证语法（不执行）
compile(lambda_expr, '<lambda>', 'eval')
# 再用 eval 创建函数对象（验证可调用性）
func_obj = eval(lambda_expr, test_namespace)
if not callable(func_obj):
    raise ValueError(f"'{lambda_expr}' 不是可调用对象")
```

**好处**: 两阶段验证（编译 + 执行）确保提取的 lambda 既有正确的语法，也是可调用的函数对象。

---

## 影响范围

### 文件修改清单

| 文件 | 修改类型 | 说明 |
|------|---------|------|
| `infra/features_v2/core/feature_set.py` | 🔧 修复 | 添加 `colon_found` 标志，修复多参数 lambda 提取 |
| `infra/features_v2/config/parser.py` | ✨ 改进 | 添加优雅降级机制，跳过无法解析的特征 |
| `~/.my_features/demo_incremental_basics.yaml` | 🔧 修复 | 恢复 `gm_to_current_ratio` 特征定义 |

### 向后兼容性

✅ **完全向后兼容**
- 单参数 lambda: 继续正常工作
- 命名函数: 仍然标记为 `# UNSUPPORTED`（预期行为）
- 旧配置文件: 通过优雅降级机制可以部分加载

---

## 最佳实践建议

### 推荐的 Lambda 使用方式

1. **简单派生特征**: 使用 lambda ✅
   ```yaml
   - name: gm_normalized
     input: gm_max
     func: 'lambda gm: (gm - gm.mean()) / (gm.std() + 1e-10)'
   ```

2. **多参数特征**: 使用 lambda ✅（现已支持）
   ```yaml
   - name: gm_to_current_ratio
     input: [gm_max, absI_max]
     func: 'lambda gm, i: gm / (i + 1e-10)'
   ```

3. **复杂业务逻辑**: 创建自定义提取器 ✅
   ```python
   @register('custom.complex_feature')
   class ComplexFeature(BaseExtractor):
       def extract(self, data, params):
           # 复杂计算逻辑
           ...
   ```

### 不支持的情况

❌ **命名函数** (仍不支持)
```python
def my_function(x):
    return x * 2

features.add('my_feat', func=my_function, ...)  # 无法序列化
```

**解决方案**:
- 转换为 lambda: `lambda x: x * 2`
- 或创建提取器: `@register('custom.double')`

---

## 测试结果

### 自动化测试
```bash
conda run --name mlpytorch python test_lambda_serialization.py

================================================================================
测试总结
================================================================================
✅ 序列化成功: 3/3 个派生特征
✅ 所有 lambda 均成功序列化！
✅ 重新加载后数据完全一致！

================================================================================
🎉 核心测试通过：多参数 lambda 成功序列化！
================================================================================
```

### Notebook 验证
原始报错的 `features_v2_incremental_demo.ipynb` Cell[21] 现在可以正常运行：

```python
features_stage3 = FeatureSet.from_config(
    str(config_file),
    unified_experiment=exp
)
# ✅ 成功加载，包含 gm_to_current_ratio 特征
```

---

## 相关文档

- **Features V2 文档**: `infra/features_v2/CLAUDE.md`
- **配置解析文档**: `infra/features_v2/docs/IMPLEMENTATION_SUMMARY.md`
- **Catalog 集成**: `infra/catalog/docs/V2_INTEGRATION_GUIDE.md`

---

## 未来改进方向

1. **AST 解析**: 使用 Python AST 模块替代字符串解析（更可靠）
2. **序列化库**: 考虑使用 `dill` 或 `cloudpickle` 支持更复杂的函数
3. **配置验证工具**: 提供 CLI 命令验证配置文件完整性

---

**修复完成时间**: 2025-10-31 17:16
**测试状态**: ✅ 三阶段测试全部通过
**部署状态**: ✅ 已部署到主分支
**版本**: v2.1.1（完整序列化支持）
