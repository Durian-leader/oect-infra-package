# Catalog V2 特征配置模板库

此目录包含预定义的 Features V2 配置文件，可直接用于 catalog 集成。

---

## 可用配置

| 配置文件 | 特征数量 | 用途 | 推荐场景 |
|---------|---------|------|---------|
| `v2_transfer_basic.yaml` | 5 | 基础 Transfer 特征 | 日常分析、报告生成 |
| `v2_quick_analysis.yaml` | 3 | 快速分析 | 数据质量检查、快速探索 |
| `v2_ml_ready.yaml` | 12 | ML 就绪 | 机器学习训练、特征工程 |

---

## 使用方式

### 单实验提取

```python
from infra.catalog import UnifiedExperimentManager

manager = UnifiedExperimentManager()
exp = manager.get_experiment(chip_id="#20250804008", device_id="3")

# 使用预定义配置
result = exp.extract_features_v2('v2_transfer_basic', output_format='dataframe')
```

### 批量提取

```python
experiments = manager.search(chip_id="#20250804008")

manager.batch_extract_features_v2(
    experiments=experiments,
    feature_config='v2_ml_ready',
    save_format='parquet',
    n_workers=4  # 并行处理
)
```

### CLI 使用

```bash
# 列出可用配置
python -m catalog v2 configs

# 批量提取
python -m catalog v2 extract-batch --chip="#20250804008" --config=v2_ml_ready
```

---

## 自定义配置

你可以复制这些模板并修改，或创建新的配置文件。

配置文件格式请参考：`infra/features_v2/config/templates/`

---

**最后更新**: 2025-10-30
