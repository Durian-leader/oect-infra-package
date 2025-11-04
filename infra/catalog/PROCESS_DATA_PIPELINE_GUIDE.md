# process_data_pipeline 使用指南

## 概述

`process_data_pipeline` 是 `UnifiedExperimentManager` 的完整数据处理管道方法，支持从源数据到特征提取的全流程自动化处理。

## 重构说明（2025-11-04）

### 参数变更

**旧版本**（已废弃）:
```python
process_data_pipeline(
    source_directory,
    auto_extract_features=False,      # 已移除
    feature_version='v1',              # 已移除
    v2_feature_config='v2_transfer_basic'  # 已移除
)
```

**新版本**（当前）:
```python
process_data_pipeline(
    source_directory,
    v1_feature_versions=None,          # 新增：列表形式
    v2_feature_configs=None            # 新增：列表形式
)
```

### 主要改进

1. **更清晰的逻辑**：
   - 移除 `auto_extract_features` 参数，通过 `v1_feature_versions` 和 `v2_feature_configs` 是否为 None/空列表来决定是否提取特征
   - 参数名更准确地反映其含义

2. **更灵活的配置**：
   - `v1_feature_versions` 支持多个版本同时提取（如 `['v1', 'v2']`）
   - `v2_feature_configs` 支持多个配置同时提取（如 `['v2_transfer_basic', 'v2_ml_ready']`）

3. **动态模块匹配**：
   - `v1_feature_versions` 中的版本自动匹配 `features_version/` 目录下的 `{version}_feature.py` 文件
   - `v2_feature_configs` 中的配置匹配 `features_v2/` 模块的配置名

## API 文档

### 方法签名

```python
def process_data_pipeline(
    self,
    source_directory: Union[str, Path],
    clean_json: bool = True,
    num_workers: int = 20,
    conflict_strategy: str = 'skip',
    v1_feature_versions: Optional[List[str]] = None,
    v2_feature_configs: Optional[List[str]] = None,
    show_progress: bool = True
) -> Dict[str, Any]
```

### 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `source_directory` | `Union[str, Path]` | - | 源数据目录路径（必需） |
| `clean_json` | `bool` | `True` | 是否先清理 JSON 文件 |
| `num_workers` | `int` | `20` | 并行工作进程数 |
| `conflict_strategy` | `str` | `'skip'` | 冲突处理策略 |
| `v1_feature_versions` | `Optional[List[str]]` | `None` | features_version 模块的版本列表<br>例如: `['v1', 'v2']`<br>对应文件: `v1_feature.py`, `v2_feature.py`<br>`None` 或 `[]` 表示不使用 |
| `v2_feature_configs` | `Optional[List[str]]` | `None` | features_v2 模块的配置名列表<br>例如: `['v2_transfer_basic']`<br>`None` 或 `[]` 表示不使用 |
| `show_progress` | `bool` | `True` | 是否显示进度条 |

### 返回值

返回 `Dict[str, Any]` 包含以下字段：

```python
{
    'source_directory': str,           # 源目录路径
    'steps_completed': List[str],      # 完成的步骤列表
    'overall_success': bool,           # 总体成功标志
    'results': {
        'json_cleaning': {...},        # JSON 清理结果（可选）
        'discovery': {...},            # 目录发现结果
        'conversion': {...},           # HDF5 转换结果
        'v1_feature_extraction_{version}': {...},  # V1 特征提取结果（每个版本一个）
        'v2_feature_extraction_{config}': {...}    # V2 特征提取结果（每个配置一个）
    }
}
```

## 处理流程

管道按以下顺序执行：

```
步骤1: JSON 清理（可选）
   ↓
步骤2: 发现测试目录
   ↓
步骤3: 批量转换为 HDF5
   ↓
步骤4a: features_version 特征提取（可选，多版本）
   ↓
步骤4b: features_v2 特征提取（可选，多配置）
```

## 使用示例

### 示例1：仅转换数据（不提取特征）

```python
from infra.catalog import UnifiedExperimentManager

manager = UnifiedExperimentManager('catalog_config.yaml')

# 仅转换，不提取任何特征
result = manager.process_data_pipeline(
    source_directory='data/source',
    clean_json=True,
    num_workers=20,
    v1_feature_versions=None,  # 不使用 features_version
    v2_feature_configs=None    # 不使用 features_v2
)

print(f"Converted {result['results']['conversion']['successful_conversions']} files")
```

### 示例2：转换 + V1 特征提取

```python
# 提取 V1 Transfer 特征（gm, Von, |I|）
result = manager.process_data_pipeline(
    source_directory='data/source',
    v1_feature_versions=['v1'],  # 使用 v1_feature.py
    v2_feature_configs=None
)

# 查看 V1 特征提取结果
v1_result = result['results']['v1_feature_extraction_v1']
print(f"V1: {len(v1_result['successful'])} successful, "
      f"{len(v1_result['failed'])} failed, "
      f"{len(v1_result['skipped'])} skipped")
```

### 示例3：转换 + V2 Transient tau 特征提取

```python
# 提取 V2 Transient tau 特征（tau_on, tau_off）
result = manager.process_data_pipeline(
    source_directory='data/source',
    v1_feature_versions=['v2'],  # 使用 v2_feature.py（transient tau）
    v2_feature_configs=None
)

# 查看 V2 特征提取结果
v2_result = result['results']['v1_feature_extraction_v2']
print(f"V2 (tau): {len(v2_result['successful'])} successful")
```

### 示例4：转换 + V1 和 V2 特征同时提取

```python
# 同时提取 V1 Transfer 和 V2 Transient tau
result = manager.process_data_pipeline(
    source_directory='data/source',
    v1_feature_versions=['v1', 'v2'],  # 两个版本都提取
    v2_feature_configs=None
)

# V1 和 V2 会写入同一个特征文件的不同 data_type
# V1 → data_type='transfer'
# V2 → data_type='transient'
```

### 示例5：转换 + features_v2 特征提取

```python
# 使用 features_v2 提取多个配置
result = manager.process_data_pipeline(
    source_directory='data/source',
    v1_feature_versions=None,
    v2_feature_configs=['v2_transfer_basic', 'v2_ml_ready']
)

# 查看每个配置的结果
for config in ['v2_transfer_basic', 'v2_ml_ready']:
    config_result = result['results'][f'v2_feature_extraction_{config}']
    print(f"{config}: {len(config_result['successful'])} successful")
```

### 示例6：完整管道（全部特征）

```python
# 提取所有可用特征
result = manager.process_data_pipeline(
    source_directory='data/source',
    clean_json=True,
    num_workers=20,
    conflict_strategy='skip',
    v1_feature_versions=['v1', 'v2'],  # Transfer + Transient tau
    v2_feature_configs=['v2_transfer_basic', 'v2_ml_ready'],  # features_v2 配置
    show_progress=True
)

# 查看完成的步骤
print("Completed steps:", result['steps_completed'])
# 输出示例:
# ['json_cleaning', 'discovery', 'conversion',
#  'v1_feature_extraction_v1', 'v1_feature_extraction_v2',
#  'v2_feature_extraction_v2_transfer_basic',
#  'v2_feature_extraction_v2_ml_ready']
```

## features_version vs features_v2

### features_version（通过 `v1_feature_versions` 控制）

- **位置**: `package/oect-infra-package/infra/features_version/`
- **文件**: `v1_feature.py`, `v2_feature.py`, ...
- **特征存储**: HDF5 格式
- **版本对应**:
  - `'v1'` → `v1_feature.py` → Transfer 特征（gm, Von, |I|）
  - `'v2'` → `v2_feature.py` → Transient tau 特征（tau_on, tau_off）
- **data_type**:
  - V1 写入 `data_type='transfer'`
  - V2 写入 `data_type='transient'`

### features_v2（通过 `v2_feature_configs` 控制）

- **位置**: `package/oect-infra-package/infra/features_v2/`
- **配置**: YAML 配置文件
- **特征存储**: Parquet 格式
- **配置示例**:
  - `'v2_transfer_basic'` → 5 个基础 Transfer 特征
  - `'v2_ml_ready'` → 12 个 ML 训练特征
- **优势**: DAG 执行、多维特征、增量计算

## 特征提取行为

### 跳过逻辑

- 如果实验已有对应版本/配置的特征，将自动跳过
- 可通过 `force_recompute` 参数（在 `batch_extract_features_v2` 中）强制重算

### 并行控制

- `num_workers`: 控制 HDF5 转换的并行度
- features_v2 提取时自动限制为 `min(num_workers, 4)` 以避免冲突

### 错误处理

- 单个实验的特征提取失败不会中断整个管道
- 所有错误记录在 `results['failed']` 中

## 注意事项

1. **特征提取后需要重新扫描**：
   ```python
   # 特征提取完成后，重新扫描以关联特征文件
   manager.catalog.scan_and_index(incremental=False)
   ```

2. **版本命名规范**：
   - `v1_feature_versions` 中的版本必须对应 `features_version/{version}_feature.py`
   - 文件中必须有同名函数 `{version}_feature()`

3. **配置名规范**：
   - `v2_feature_configs` 中的配置名必须存在于 `features_v2` 系统中
   - 可通过 `python -m catalog v2 configs` 查看可用配置

4. **多版本提取顺序**：
   - 按列表顺序依次提取
   - 建议先提取 V1（Transfer）再提取 V2（Transient）

5. **资源控制**：
   - V2 transient 特征提取可能使用多核并行（autotau）
   - 建议不要同时使用过多并行工作进程

## 故障排除

### 问题1：导入失败

```
ERROR: Failed to import v2_feature from ..features_version.v2_feature
```

**解决方案**：
- 确认 `features_version/v2_feature.py` 文件存在
- 确认文件中有 `v2_feature()` 函数
- 检查 `features_version/__init__.py` 是否导出该函数

### 问题2：特征提取失败

**症状**：`results['failed']` 包含多个实验

**解决方案**：
- 检查原始文件是否包含所需数据类型（transfer 或 transient）
- 查看日志获取详细错误信息
- 单独测试失败的实验：
  ```python
  from infra.features_version import v2_feature
  v2_feature('path/to/raw.h5', max_workers=2)
  ```

### 问题3：配置不存在

```
ERROR: Feature config 'xxx' not found
```

**解决方案**：
- 查看可用配置：`python -m catalog v2 configs`
- 确认配置文件在 `catalog/feature_configs/` 或 `features_v2/templates/`

## 版本历史

- **v2.0.0** (2025-11-04): 重构为列表参数，支持多版本/多配置提取
- **v1.0.0**: 初始版本（已废弃的 `auto_extract_features` 模式）

---

**最后更新**: 2025-11-04
