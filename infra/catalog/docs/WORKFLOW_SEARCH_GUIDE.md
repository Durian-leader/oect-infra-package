# Workflow 参数搜索与元数据导出功能指南

## 概述

本指南介绍了两个核心功能：
1. **Workflow 元数据导出** - 在导出 DataFrame 时包含工作流参数信息
2. **Workflow 参数搜索** - 根据工作流参数搜索和过滤实验

这些功能已集成到 `catalog` 模块的 `UnifiedExperimentManager` 和 `UnifiedExperiment` 类中，
并通过**数据库缓存优化**实现了高性能访问。

---

## 架构优化

### 性能优化策略

为了避免每次搜索和导出都重新计算 workflow 元数据，系统采用了**数据库缓存**策略：

1. **初始化阶段**：调用 `manager.initialize_workflow_metadata()` 将所有实验的 workflow 信息扁平化并存储到数据库
2. **使用阶段**：所有搜索和导出操作直接从数据库读取缓存的 metadata（JSON 字符串），无需重新计算
3. **自动回退**：如果数据库中没有缓存，会自动实时计算（向后兼容）

### 性能对比

- **优化前**：每次搜索需要遍历所有实验并实时计算 workflow metadata
- **优化后**：直接从数据库读取 JSON 字符串并解析（提升 **10-100倍**）

---

## 快速开始

### Step 1: 初始化 Workflow Metadata（一次性操作）

```python
from catalog import UnifiedExperimentManager

manager = UnifiedExperimentManager("catalog_config.yaml")

# 批量初始化所有实验的 workflow metadata 到数据库
# 这个操作只需要运行一次，或者在添加新实验后运行
result = manager.initialize_workflow_metadata()

print(f"成功更新 {result['updated']} 个实验")
```

**参数说明**：
- `force_update=False`（默认）：只更新没有 workflow metadata 的实验
- `force_update=True`：强制更新所有实验（用于数据修复）

**返回结果**：
```python
{
    'total': 80,          # 总实验数
    'updated': 80,        # 成功更新数
    'skipped': 0,         # 跳过数
    'failed': 0,          # 失败数
    'errors': []          # 错误列表
}
```

### Step 2: 使用搜索和导出功能

初始化完成后，所有操作都会自动使用缓存的数据，无需修改代码！

---

## 功能 1: Workflow 元数据导出

### 使用方法

#### 1.1 单个实验导出

```python
from catalog import UnifiedExperimentManager

manager = UnifiedExperimentManager("catalog_config.yaml")

# 获取一个实验
exp = manager.get_experiment(70)

# 导出特征 DataFrame，包含 workflow 元数据
df = exp.get_feature_dataframe(
    version='v1',
    data_type='transfer',
    include_workflow=True  # 设置为 True 以包含 workflow 元数据列
)

# 导出到 Excel
df.to_excel("features_with_workflow.xlsx", index=False)
```

#### 1.2 批量实验导出

```python
# 获取多个实验
experiments = manager.search(chip_id="#20250829016")

# 创建组合 DataFrame，包含 workflow 元数据
df = manager.create_combined_features_dataframe(
    experiments,
    feature_names=['absgm_max_forward', 'Von_forward', 'Vt', 'SS'],
    data_type='transfer',
    include_workflow=True  # 设置为 True 以包含 workflow 元数据列
)

# 导出到 CSV
df.to_csv("combined_features_with_workflow.csv", index=False)
```

### Workflow 元数据列格式

导出的 workflow 元数据列采用以下命名格式：

- `workflow_step_1_type` - 第 1 个步骤的类型
- `workflow_step_1_id` - 第 1 个步骤的 ID
- `workflow_step_1_iterations` - 第 1 个步骤的迭代次数
- `workflow_step_1_1_type` - 第 1 个步骤的第 1 个子步骤类型
- `workflow_step_1_1_param_Vd` - 第 1 个步骤的第 1 个子步骤的参数 Vd
- ...

---

## 功能 2: Workflow 参数搜索

### 核心设计

**简单统一的接口**：直接使用扁平化的 workflow metadata 键名作为搜索参数

- 所有以 `workflow_` 开头的参数自动用于 workflow 过滤
- 其他参数用于数据库查询（chip_id, device_id 等）
- 多个 workflow 条件使用 AND 逻辑（必须全部匹配）

### 使用方法

#### 2.1 按步骤类型搜索

```python
from catalog import UnifiedExperimentManager

manager = UnifiedExperimentManager("catalog_config.yaml")

# 搜索第一个步骤类型为 'loop' 的实验
experiments = manager.search(workflow_step_1_type='loop')
print(f"找到 {len(experiments)} 个实验")

# 搜索第一个步骤的第一个子步骤类型为 'transfer' 的实验
experiments = manager.search(workflow_step_1_1_type='transfer')
```

#### 2.2 按迭代次数搜索

```python
# 搜索第一个步骤的迭代次数为 5000 的实验
experiments = manager.search(workflow_step_1_iterations=5000)
```

#### 2.3 按参数值搜索

```python
# 搜索 drainVoltage=100 的实验
experiments = manager.search(workflow_step_1_1_param_drainVoltage=100)

# 搜索 gateVoltageTop=600 的实验
experiments = manager.search(workflow_step_1_2_param_gateVoltageTop=600)
```

#### 2.4 多个条件组合（AND 逻辑）

```python
# 搜索同时满足多个 workflow 条件的实验
experiments = manager.search(
    workflow_step_1_type='loop',
    workflow_step_1_iterations=5000,
    workflow_step_1_1_type='transfer',
    workflow_step_1_1_param_drainVoltage=100
)
```

#### 2.5 数据库 + workflow 组合搜索

```python
# 同时使用数据库过滤和 workflow 过滤
experiments = manager.search(
    chip_id="#20250829016",                    # 数据库过滤
    workflow_step_1_type='loop',               # workflow 过滤
    workflow_step_1_1_param_drainVoltage=100   # workflow 过滤
)
```

### 如何找到可用的 workflow 字段

使用 `get_workflow_metadata()` 查看实验的所有 workflow 字段：

```python
# 获取一个实验
exp = manager.get_experiment(70)

# 查看所有 workflow metadata 字段
workflow_metadata = exp.get_workflow_metadata()
for key, value in workflow_metadata.items():
    print(f"{key}: {value}")
```

输出示例：
```
workflow_step_1_type: loop
workflow_step_1_iterations: 5000
workflow_step_1_1_type: transfer
workflow_step_1_1_param_drainVoltage: 100
workflow_step_1_1_param_gateVoltageStart: -300
workflow_step_1_2_type: transient
workflow_step_1_2_param_gateVoltageTop: 600
...
```

然后直接使用这些键名作为搜索参数！

---

## 完整示例

### 示例 1: 初始化后导出数据

```python
from catalog import UnifiedExperimentManager

manager = UnifiedExperimentManager("catalog_config.yaml")

# Step 1: 初始化 workflow metadata（一次性操作）
result = manager.initialize_workflow_metadata()
print(f"初始化完成：{result['updated']} 个实验")

# Step 2: 搜索特定芯片的实验
experiments = manager.search(chip_id="#20250829016")

# Step 3: 导出组合特征和 workflow 元数据
df = manager.create_combined_features_dataframe(
    experiments,
    feature_names=['absgm_max_forward', 'Von_forward', 'Vt', 'SS'],
    data_type='transfer',
    include_workflow=True
)

# Step 4: 保存到 Excel
df.to_excel(f"chip_data_with_workflow.xlsx", index=False)
print(f"导出 {len(experiments)} 个实验的数据，共 {df.shape[0]} 行")
```

### 示例 2: 按 workflow 参数筛选和分析

```python
from catalog import UnifiedExperimentManager

manager = UnifiedExperimentManager("catalog_config.yaml")

# 搜索特定配置的实验
group_600V = manager.search(workflow_step_1_2_param_gateVoltageTop=600)
group_500V = manager.search(workflow_step_1_2_param_gateVoltageTop=500)

print(f"gateVoltageTop=600V: {len(group_600V)} 个实验")
print(f"gateVoltageTop=500V: {len(group_500V)} 个实验")

# 导出对比数据
df_600V = manager.create_combined_features_dataframe(
    group_600V, ['absgm_max_forward'], include_workflow=True
)
df_500V = manager.create_combined_features_dataframe(
    group_500V, ['absgm_max_forward'], include_workflow=True
)

# 绘制对比图
import matplotlib.pyplot as plt
plt.hist(df_600V['absgm_max_forward'], alpha=0.5, label='600V')
plt.hist(df_500V['absgm_max_forward'], alpha=0.5, label='500V')
plt.legend()
plt.savefig('voltage_comparison.png')
```

---

## 测试

运行测试脚本验证功能：

```bash
conda run --name mlpytorch python test_workflow_optimization.py
```

测试内容：
1. Workflow metadata 初始化（80 个实验，约 7 秒）
2. 搜索性能测试（< 60 ms）
3. DataFrame 导出测试（包含 workflow 列）
4. 数据库缓存验证（< 0.1 ms）

---

## 性能指标

### 优化效果

| 操作 | 优化前 | 优化后 | 提升倍数 |
|------|--------|--------|----------|
| 初始化 workflow metadata | 每次搜索都计算 | 一次性初始化（7秒/80实验） | N/A |
| 获取单个实验 metadata | ~10 ms | < 0.1 ms | **100x** |
| workflow 参数搜索（80实验） | ~800 ms | < 60 ms | **13x** |
| 导出 DataFrame（含 workflow） | ~500 ms | ~110 ms | **4.5x** |

### 性能注意事项

#### Workflow 元数据导出
- ✅ **极快**：直接从数据库读取 JSON 字符串并解析（< 0.1 ms）
- ✅ **内存友好**：元数据列只是简单的标量值
- ✅ **自动回退**：如果数据库中没有缓存，自动实时计算

#### Workflow 参数搜索
- ✅ **高性能**：先数据库查询，然后快速过滤 JSON 数据
- ✅ **灵活组合**：数据库和 workflow 条件可以混合使用
- ⚠️ **建议**：先使用数据库条件（chip_id, batch_id等）缩小范围，再使用 workflow 过滤

**推荐搜索模式**：
```python
# 推荐：先用数据库过滤缩小范围
experiments = manager.search(
    chip_id="#20250829016",           # 数据库过滤（快）
    workflow_step_1_type='loop'       # workflow 过滤（从缓存读取，也很快）
)

# 也可以：直接 workflow 过滤（数据库有缓存，也很快）
experiments = manager.search(
    workflow_step_1_2_param_gateVoltageTop=600
)
```

---

## 维护指南

### 何时需要重新初始化

在以下情况需要运行 `initialize_workflow_metadata()`：

1. **首次使用**：新安装或升级到优化版本后
2. **添加新实验**：批量导入新的实验数据后
3. **数据修复**：如果怀疑缓存数据不一致

```python
# 增量更新（只更新新实验）
result = manager.initialize_workflow_metadata(force_update=False)

# 强制全量更新（修复数据）
result = manager.initialize_workflow_metadata(force_update=True)
```

### 自动化建议

可以在数据导入流程中自动初始化：

```python
from catalog import UnifiedExperimentManager

manager = UnifiedExperimentManager("catalog_config.yaml")

# 导入新数据
manager.process_data_pipeline(source_directory="path/to/new/data")

# 自动更新 workflow metadata
manager.initialize_workflow_metadata()
```

---

## 总结

这两个功能提供了强大的工具来：
1. 将实验配置信息与测量数据关联导出，便于后续分析
2. 根据实验配置快速查找和筛选实验
3. 通过数据库缓存实现高性能访问

**核心特点**：
- ✅ **高性能**：数据库缓存，避免重复计算
- ✅ **简单直观**：直接使用扁平化的 workflow metadata 键名
- ✅ **自动识别**：以 `workflow_` 开头的参数自动用于 workflow 过滤
- ✅ **灵活组合**：数据库和 workflow 条件可以混合使用
- ✅ **向后兼容**：自动回退到实时计算，无需修改现有代码

功能已完全集成到现有的 catalog API 中，使用简单直观！
