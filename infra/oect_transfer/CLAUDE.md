# oect_transfer 模块（CLAUDE 指南）

面向 OECT（有机电化学晶体管）转移特性（Transfer Characteristics）的数据分析模块。提供单次与批量转移曲线的序列数据与关键特征提取，便于算法复用与上层特征管理对接。

版本：0.4.3

## 模块定位
- 输入：
  - 单次分析：1D 数组 `Vg`（栅极电压）、`Id`（漏极电流）
  - 批量分析：3D 数组，形状 `[steps, data_types, data_points]`，其中 `data_types` 维度 0=Vg、1=Id
- 输出：
  - 分方向（raw/forward/reverse）的序列数据
  - 关键特征点（值与其坐标 Vg, Id）
- 设备类型：`device_type` 支持 "N" 或 "P"，影响阈值电压 Von 的取法（N 取最大斜率，P 取最小斜率）

## 对外 API
从 `oect_transfer` 导入：
- 类：`Transfer`, `Sequence`, `Point`, `BatchTransfer`, `BatchSequence`, `BatchPoint`
- 函数：`create_batch_transfer_from_experiment_data`, `analyze_experiment_transfer_batch`

### Transfer
- 构造：`Transfer(x: 1D array, y: 1D array, device_type: str = "N")`
- 属性（序列，类型均为 `Sequence`）：
  - `Vg`：栅极电压序列
  - `I`：漏极电流序列
  - `gm`：跨导序列（dId/dVg）
- 属性（特征点，类型均为 `Point`，每个方向的值为 `(value, (Vg, Id))`）：
  - `absgm_max`：|gm| 最大点
  - `gm_max` / `gm_min`：gm 的最大/最小点
  - `absI_max` / `absI_min`：|I| 的最大/最小点
  - `I_max` / `I_min`：I 的最大/最小点
  - `Von`：阈值电压点（按 log(|Id|) 对 Vg 的斜率极值确定）

说明：
- `Sequence` 含 `raw`, `forward`, `reverse` 三个方向；转折点位于中点索引 `tp_idx=(n-1)//2`，`forward` 含索引 `[:tp_idx+1]`，`reverse` 含 `[tp_idx+1:]`，避免转折点重复计入。
- 派生量 `gm` 通过稳定差分计算（边界用前/后向差分，内部用前后向平均的中心差分），实现见 `safe_diff`（numba 加速）。
- `Von` 通过 log10(|Id|) 对 Vg 的导数极值点对应的 Vg 作为阈值电压，N 型取最大斜率，P 型取最小斜率。

### 数据结构
- `Sequence(raw, forward, reverse)`：各为 1D ndarray
- `Point(raw, forward, reverse)`：各方向为 `(value: float, (Vg: float, Id: float))`

### BatchTransfer
- 构造：`BatchTransfer(data_3d: 3D array, device_type: str = "N")`
- 输入形状：`[steps, data_types, data_points]`，`data_types`：`0=Vg, 1=Id`
- 属性（序列，类型均为 `BatchSequence`，值为 2D ndarray）：
  - `Vg`, `I`, `gm`：形状均约为 `[steps, points]`（`forward`/`reverse` 在点数上按转折点分割）
- 属性（特征点，类型均为 `BatchPoint`）：
  - 值：`raw`, `forward`, `reverse`（形状 `[steps]`）
  - 坐标：`raw_coords`, `forward_coords`, `reverse_coords`（形状 `[steps, 2]`，依次为 `(Vg, Id)`）
  - 特征种类与 `Transfer` 一致：`absgm_max`, `gm_max`, `gm_min`, `absI_max`, `I_max`, `absI_min`, `I_min`, `Von`
- 方法：`get_data_summary() -> dict`：返回批量数据的尺寸、范围等摘要信息。

### 便利函数
- `create_batch_transfer_from_experiment_data(transfer_data_3d, device_type="N") -> BatchTransfer`
  - 直接由实验 API 返回的 3D transfer 数据构建 `BatchTransfer`
- `analyze_experiment_transfer_batch(experiment_path, device_type="N") -> Optional[BatchTransfer]`
  - 从 HDF5 实验文件路径加载并构建（依赖 `experiment.Experiment` 可用）

## 数据校验与约束
- 单次与批量均会校验：
  - 维度/形状正确性与一致性
  - 非空，且不含 NaN/Inf
- 批量：`steps > 0` 且 `data_points > 0`；`data_types == 2`
- 转折点固定为中点索引，用于切分 `forward/reverse`

## 最小示例
- 单次分析：
```python
from oect_transfer import Transfer

t = Transfer(vg_array, id_array, device_type="N")
value, (vg_at, id_at) = t.gm_max.forward
```

- 批量分析（已备好 3D 数据）：
```python
from oect_transfer import BatchTransfer

bt = BatchTransfer(data_3d, device_type="P")
values = bt.Von.forward              # [steps]
coords = bt.Von.forward_coords       # [steps, 2] -> (Vg, Id)
```

- 从实验文件加载（需要 experiment 模块可用）：
```python
from oect_transfer import analyze_experiment_transfer_batch

bt = analyze_experiment_transfer_batch('path/to/file.h5', device_type="N")
if bt:
    print(bt.get_data_summary())
```

## 实现要点
- 派生量计算：稳定差分（前/后向差分 + 中心差分平均），避免极小步长导致的数值问题
- 性能：`Transfer.safe_diff` 使用 `numba.jit(nopython=True)` 的实现
- 坐标约定：特征点坐标统一为 `(Vg, Id)`

> 注：本文仅描述 `oect_transfer` 模块本身的能力与接口，不涉及外部模块实现细节。
