# AutoTau 0.3.1 迁移指南

## 概述

本文档记录了 `v2_feature.py` 从 autotau v0.3.0 迁移到 v0.3.1 的所有更改。

**迁移日期**: 2025-11-04
**autotau 版本**: 0.3.0 → 0.3.1 (commit: c03bf3a)

## 主要变更

### 1. 移除并行执行器模式

**旧版本 (v0.3.0)**:
```python
from concurrent.futures import ProcessPoolExecutor

executor = ProcessPoolExecutor(max_workers=max_workers)

def fitter_factory(time_slice, signal_slice, **kwargs):
    return AutoTauFitter(
        time=time_slice,
        signal=signal_slice,
        executor=executor  # 注入并行执行器
    )

cycles_fitter = CyclesAutoTauFitter(
    time=time,
    signal=signal,
    period=period,
    sample_rate=sample_rate,
    fitter_factory=fitter_factory  # 使用工厂模式
)
```

**新版本 (v0.3.1)**:
```python
# 不再需要 ProcessPoolExecutor 和 fitter_factory

cycles_fitter = CyclesAutoTauFitter(
    time=time,
    signal=signal,
    period=period,
    sample_rate=sample_rate,
    window_scalar_min=window_scalar_min,
    window_scalar_max=window_scalar_max,
    window_points_step=window_points_step,
    window_start_idx_step=window_start_idx_step,
    normalize=normalize,
    language=language,
    show_progress=show_progress
)
```

### 2. 函数签名变更

**移除的参数**:
- `max_workers: Optional[int]` - 不再需要外部并行控制

**新增的参数**:
- `window_start_idx_step: int = 1` - 窗口起始位置步长
- `normalize: bool = False` - 是否归一化信号
- `language: str = 'en'` - 界面语言选择

**默认值调整**:
- `window_scalar_max`: 0.4 → 0.333
- `window_points_step`: 5 → 10

### 3. 返回结果字段名变更

**旧版本字段**:
```python
cycle_result.get('status')  # 'success' 或其他
cycle_result.get('tau_on_r2')
cycle_result.get('tau_off_r2')
```

**新版本字段**:
```python
# 没有 'status' 字段
cycle_result.get('tau_on_r_squared')  # 改名
cycle_result.get('tau_off_r_squared')  # 改名
cycle_result.get('was_refitted')  # 新增，指示是否重新拟合
```

### 4. 结果解析逻辑变更

**旧版本**:
```python
if cycle_result.get('status') == 'success':
    tau_on = cycle_result.get('tau_on', np.nan)
    tau_on_r2 = cycle_result.get('tau_on_r2', np.nan)
else:
    tau_on = np.nan
    tau_on_r2 = np.nan
```

**新版本**:
```python
# 直接获取值，失败时为 None 或不存在
tau_on = cycle_result.get('tau_on', np.nan)
tau_on_r2 = cycle_result.get('tau_on_r_squared', np.nan)

# 将 None 转换为 np.nan
if tau_on is None:
    tau_on = np.nan
if tau_on_r2 is None:
    tau_on_r2 = np.nan
```

## 兼容性说明

### 不向后兼容的变更

1. **函数签名**: 移除了 `max_workers` 参数，调用时需要移除此参数
2. **返回格式**: 字段名从 `tau_on_r2` 改为 `tau_on_r_squared`
3. **状态检查**: 不再有 `status` 字段

### 迁移步骤

如果您的代码使用了 `v2_feature()` 函数：

1. **移除 `max_workers` 参数**:
   ```python
   # 旧代码
   v2_feature(raw_file, max_workers=8)

   # 新代码
   v2_feature(raw_file)
   ```

2. **添加新参数（可选）**:
   ```python
   v2_feature(
       raw_file,
       window_start_idx_step=2,  # 新增
       normalize=True,           # 新增
       language='cn'             # 新增
   )
   ```

3. **如果直接使用返回结果**，确保使用新的字段名：
   ```python
   # 不推荐直接解析，应该使用 features API
   r2 = cycle_result['tau_on_r_squared']  # 新字段名
   ```

## 性能影响

- **移除外部并行**: autotau 0.3.1 内部实现了自己的优化策略，不再需要外部并行控制
- **窗口搜索**: `window_points_step` 从 5 增加到 10，可能略微降低精度但提升速度
- **默认参数**: `window_scalar_max` 从 0.4 降到 0.333，减少搜索范围，提升速度

## 测试验证

运行以下命令验证迁移：

```bash
# 导入测试
python -c "from infra.features_version.v2_feature import v2_feature; print('✅ 导入成功')"

# 接口验证
python -c "
from infra.features_version.v2_feature import v2_feature
import inspect
sig = inspect.signature(v2_feature)
assert 'max_workers' not in sig.parameters, '应该移除 max_workers'
assert 'window_start_idx_step' in sig.parameters, '应该包含 window_start_idx_step'
print('✅ 接口验证通过')
"
```

## 相关文档

- `v2_feature.py` - 主实现文件
- `CLAUDE.md` - features_version 模块说明
- `V2_FEATURE_README.md` - V2 特征详细文档

## 变更历史

- **2025-11-04**: 完成迁移到 autotau 0.3.1
- **2025-11-03**: autotau 0.3.1 发布 (commit: c03bf3a)
