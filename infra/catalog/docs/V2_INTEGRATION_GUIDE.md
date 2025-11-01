# Features V2 集成指南

**版本**: 1.0.0
**日期**: 2025-10-30
**状态**: ✅ 生产就绪

---

## 概述

Catalog 模块已完整集成 Features V2 特征提取系统，提供统一的 API 和批量处理能力。

###关键特性

- ✅ **单实验交互式提取** - `exp.extract_features_v2()`
- ✅ **批量自动化处理** - `manager.batch_extract_features_v2()`
- ✅ **配置文件管理** - 预定义配置模板
- ✅ **数据库集成** - 自动跟踪 V2 特征元数据
- ✅ **V1/V2 共存** - 完全独立，互不影响

---

## 快速开始

### 1. 单实验提取

```python
from infra.catalog import UnifiedExperimentManager

# 初始化
manager = UnifiedExperimentManager('catalog_config.yaml')

# 获取实验
exp = manager.get_experiment(chip_id="#20250804008", device_id="3")

# 使用预定义配置提取
result_df = exp.extract_features_v2('v2_transfer_basic', output_format='dataframe')

print(result_df.head())
```

### 2. 批量提取

```python
# 搜索实验
experiments = manager.search(chip_id="#20250804008")

# 批量提取
result = manager.batch_extract_features_v2(
    experiments=experiments,
    feature_config='v2_ml_ready',
    save_format='parquet',
    n_workers=4  # 并行处理4个实验
)

print(f"成功: {len(result['successful'])}/{len(experiments)}")
```

---

## API 参考

### UnifiedExperiment.extract_features_v2()

```python
def extract_features_v2(
    feature_config: Union[str, Dict],
    output_format: str = 'parquet',
    output_dir: Optional[str] = None,
    save_metadata: bool = True,
) -> Union[Dict, pd.DataFrame, str]
```

**参数**:
- `feature_config`: 配置文件名或内联字典
- `output_format`: `'dict'`, `'dataframe'`, `'parquet'`
- `output_dir`: 输出目录（None=使用默认）
- `save_metadata`: 是否保存到数据库

**返回**: 根据 output_format 返回相应类型

### UnifiedExperimentManager.batch_extract_features_v2()

```python
def batch_extract_features_v2(
    experiments: Union[List[UnifiedExperiment], str],
    feature_config: Union[str, Dict],
    output_dir: Optional[str] = None,
    save_format: str = 'parquet',
    n_workers: int = 1,
    force_recompute: bool = False,
) -> Dict[str, Any]
```

**参数**:
- `experiments`: 实验列表或搜索条件
- `feature_config`: 配置
- `save_format`: `'parquet'` 或 `'none'`
- `n_workers`: 并行工作进程数
- `force_recompute`: 强制重新计算

**返回**:
```python
{
    'successful': [exp_id, ...],
    'failed': [(exp_id, error), ...],
    'skipped': [exp_id, ...],
    'timings': {exp_id: time_ms, ...},
    'total_time_ms': float
}
```

---

## 配置文件

### 预定义配置

| 配置名 | 特征数 | 用途 |
|--------|--------|------|
| `v2_transfer_basic` | 5 | 基础 Transfer 特征 |
| `v2_quick_analysis` | 3 | 快速分析 |
| `v2_ml_ready` | 12 | ML 训练 |

**位置**: `infra/catalog/feature_configs/`

### 使用配置

```python
# 方式 1: 使用配置名
exp.extract_features_v2('v2_transfer_basic')

# 方式 2: 使用完整路径
exp.extract_features_v2('/path/to/custom_config.yaml')

# 方式 3: 使用内联配置
exp.extract_features_v2({
    'gm_max': {
        'extractor': 'transfer.gm_max',
        'input': 'transfer',
        'params': {'direction': 'forward'}
    }
})
```

---

## 数据库集成

### V2 特征元数据

每个实验的 `v2_feature_metadata` 字段存储 JSON：

```json
{
  "configs_used": ["v2_transfer_basic"],
  "last_computed": "2025-10-30T10:30:00",
  "feature_count": 5,
  "output_files": [
    "data/features/#20250804008-3-v2_features-feat_20251030-103000_a1b2c3d4.parquet"
  ],
  "computation_stats": {
    "total_time_ms": 1234.56,
    "cache_hits": 5,
    "cache_misses": 3
  }
}
```

### 查询 V2 特征

```python
# 检查是否有 V2 特征
if exp.has_v2_features():
    print("有 V2 特征")

# 获取元数据
metadata = exp.get_v2_features_metadata()
print(metadata['configs_used'])
```

---

## 文件命名规则

### V2 特征文件

**格式**: `{chip_id}-{device_id}-v2_features-feat_{timestamp}_{config_hash}.parquet`

**示例**: `#20250804008-3-v2_features-feat_20251030-103000_a1b2c3d4.parquet`

**说明**:
- `v2_features`: 标识 V2 特征（区别于 V1）
- `config_hash`: 配置 MD5 的前8位（避免重复计算）
- `.parquet`: 使用 Parquet 格式（比 HDF5 更快）

---

## V1 vs V2 对比

| 特性 | V1 (features) | V2 (features_v2) |
|------|---------------|------------------|
| **API** | `batch_extract_features(version='v1')` | `batch_extract_features_v2(config='...')` |
| **配置** | 硬编码在 v1_feature.py | YAML 配置文件 |
| **输出格式** | HDF5 | Parquet |
| **文件名** | `*-feat_*.h5` | `*-v2_features-*.parquet` |
| **数据库字段** | `feature_file_path` | `v2_feature_metadata` (JSON) |
| **扩展性** | 需要修改代码 | `@register` 装饰器 |
| **多维特征** | ❌ 只支持 1D | ✅ 任意维度 |
| **并行** | ❌ | ✅ 支持 |

### 共存策略

V1 和 V2 **完全独立**，可以同时使用：

```python
# 提取 V1 特征
manager.batch_extract_features(experiments, version='v1')

# 提取 V2 特征
manager.batch_extract_features_v2(experiments, feature_config='v2_transfer_basic')
```

---

## 最佳实践

### 1. 配置文件管理

- ✅ 使用预定义配置作为起点
- ✅ 为不同分析场景创建专用配置
- ✅ 使用版本控制管理配置文件
- ✅ 在配置中添加详细注释

### 2. 性能优化

```python
# 批量处理时启用并行
manager.batch_extract_features_v2(
    experiments,
    feature_config='v2_transfer_basic',
    n_workers=4,  # 根据 CPU 核心数调整
)

# 避免重复计算
result = manager.batch_extract_features_v2(
    experiments,
    feature_config='v2_ml_ready',
    force_recompute=False,  # 跳过已有特征的实验
)
```

### 3. 数据管理

```python
# 定期检查 V2 特征
experiments = manager.search()
v2_count = sum(1 for exp in experiments if exp.has_v2_features())
print(f"{v2_count}/{len(experiments)} 个实验有 V2 特征")

# 清理旧的 V2 特征
for exp in experiments:
    metadata = exp.get_v2_features_metadata()
    if metadata:
        # 根据 last_computed 决定是否重新计算
        pass
```

---

## 常见问题

### Q1: V1 和 V2 应该使用哪个？

**推荐**：
- **新项目**: 使用 V2（更灵活、更快）
- **现有项目**: 保持 V1（稳定、兼容）
- **ML 项目**: 使用 V2（支持多维特征）

### Q2: V2 配置文件存放在哪里？

两个位置：
1. `infra/catalog/feature_configs/` - catalog 集成专用
2. `infra/features_v2/config/templates/` - features_v2 原始模板

### Q3: 如何查看已有的 V2 特征？

```python
metadata = exp.get_v2_features_metadata()
if metadata:
    print(f"配置: {metadata['configs_used']}")
    print(f"文件: {metadata['output_files']}")
```

### Q4: 如何迁移 V1 到 V2？

暂不需要迁移，两者可共存。如需迁移：

```python
# 1. 使用 V2 重新提取
manager.batch_extract_features_v2(experiments, 'v2_ml_ready')

# 2. （可选）验证结果一致性
v1_df = exp.get_feature_dataframe('v1')
v2_df = exp.extract_features_v2('v2_transfer_basic', output_format='dataframe')

# 3. 对比关键特征
# ...
```

---

## 示例脚本

完整示例见：`infra/catalog/examples/v2_integration_demo.py`

运行：
```bash
conda run --name mlpytorch python infra/catalog/examples/v2_integration_demo.py
```

---

## 故障排查

### 配置文件找不到

**错误**: `ValueError: 配置文件不存在: v2_xxx`

**解决**:
1. 检查配置文件是否在 `infra/catalog/feature_configs/` 中
2. 使用完整路径
3. 检查文件名拼写

### 数据库迁移失败

**错误**: `sqlite3.OperationalError: no such column: v2_feature_metadata`

**解决**:
- 数据库会自动迁移
- 如果失败，手动执行迁移（下一版本将提供脚本）

### 提取失败

**错误**: `ValueError: 无法加载实验`

**解决**:
1. 检查实验是否在 catalog 中: `exp.file_path`
2. 检查原始文件是否存在
3. 检查是否有 Transfer/Transient 数据

---

## 反馈与支持

- **Bug 报告**: 项目 Issue Tracker
- **功能请求**: 描述使用场景
- **性能问题**: 提供数据规模

---

**最后更新**: 2025-10-30
