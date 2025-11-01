# visualization 模块说明（CLAUDE）

本模块用于 OECT 实验与特征数据的可视化，提供两类绘图器与一个便捷函数：
- `OECTPlotter`：原始实验数据（Transfer/Transient）可视化与动画/视频输出
- `ChipFeaturePlotter`：按芯片ID的特征演化对比可视化
- `plot_chip_feature`：快速绘制单个芯片某项特征的便捷函数

对外能力均通过包入口 `visualization/__init__.py` 暴露。

## 对外 API

- 包级导出（`from visualization import ...`）：
  - `OECTPlotter`
  - `ChipFeaturePlotter`
  - `plot_chip_feature`

### OECTPlotter
- 构造：`OECTPlotter(experiment_file: str | Path)`
  - 传入实验 HDF5 文件路径；数据访问依赖 `experiment.Experiment`（模块详情见 `experiment/CLAUDE.md`）。

- 方法：
  - `plot_transfer_single(step_index, log_scale=False, figsize=(10, 6), save_path=None) -> matplotlib.figure.Figure`
  - `plot_transfer_multiple(step_indices, log_scale=False, figsize=(12, 8), save_path=None) -> matplotlib.figure.Figure`
  - `plot_transfer_evolution(max_steps=None, log_scale=False, figsize=(12, 8), save_path=None) -> matplotlib.figure.Figure`
  - `plot_transient_single(step_index, time_range=None, time_range_type='original', dual_time_axis=True, figsize=(12, 6), save_path=None) -> matplotlib.figure.Figure`
  - `plot_transient_all(time_range=None, figsize=(15, 8), save_path=None) -> matplotlib.figure.Figure`
  - `create_transfer_animation(max_steps=None, interval=200, save_path=None, figsize=(10, 8), layout='dual') -> matplotlib.animation.FuncAnimation`
  - `create_transfer_video_parallel(max_steps=None, fps=10, save_path='transfer_evolution_parallel.mp4', figsize=(12, 5), layout='dual', n_workers=None, verbose=True) -> str`
  - `create_transfer_video_optimized(step_indices=None, output_path='transfer_evolution_optimized.mp4', config=None, verbose=True) -> str`
  - `create_transfer_video_single(layout='linear', step_indices=None, output_path=None, **kwargs) -> str`
  - `get_experiment_info() -> dict`

- 说明要点：
  - Transfer 对数坐标绘图对电流取绝对值并过滤零值；线性绘图使用原始数据。
  - Transient 支持双横轴：主轴为 `continuous_time`，次轴映射为 `original_time`（步内时间），刻度与主轴位置一一对应。
  - 动画保存使用 Matplotlib（`pillow` 或 `ffmpeg` writer）；并行视频写入使用 OpenCV（`cv2.VideoWriter`）。

### ChipFeaturePlotter
- 构造：`ChipFeaturePlotter(features_dir: str)`
  - 传入特征文件目录；数据访问依赖 `features.BatchManager/FeatureReader`（模块详情见 `features/CLAUDE.md`）。

- 方法：
  - `plot_chip_feature(chip_id, feature_name, skip_points=0, normalize_to_first=False, data_type='transfer', figsize=(12, 8), title=None, save_path=None, colormap='plasma', linewidth=2.0, markersize=4.0) -> matplotlib.figure.Figure`
  - `list_chip_features(chip_id, data_type='transfer') -> List[str]`
  - `get_chip_info(chip_id) -> Dict[str, Any]`

- 说明要点：
  - 多设备按 `device_id` 自动排序，图例一致。
  - 预处理支持：去除前 N 点、首点归一化。
  - 颜色映射：支持 `plasma`（默认）、`viridis`、`coolwarm`、`RdYlBu`、`hot`、`inferno`。

### 便捷函数：plot_chip_feature
- 签名：
  - `plot_chip_feature(chip_id, feature_name, skip_points=0, normalize_to_first=False, features_dir='/mnt/d/UserData/lidonghaowsl/data/Stability_PS/features/', colormap='plasma', linewidth=2.0, markersize=4.0, **kwargs) -> matplotlib.figure.Figure`
- 作用：内部构造 `ChipFeaturePlotter` 并调用同名方法，参数与类方法一致（额外透传 `**kwargs`）。

## 基本用法

- 实验数据绘图：
  ```python
  from visualization import OECTPlotter

  plotter = OECTPlotter('experiment.h5')

  plotter.plot_transfer_single(0)
  plotter.plot_transfer_multiple([0, 10, 20])
  plotter.plot_transfer_evolution(max_steps=100)

  plotter.plot_transient_single(0, dual_time_axis=True)
  plotter.plot_transient_all()

  # 小规模动画（<100 步）
  ani = plotter.create_transfer_animation(save_path='evolution.mp4')

  # 大规模并行视频（≥100 步）
  video = plotter.create_transfer_video_parallel(fps=10, save_path='evolution_parallel.mp4')
  ```

- 芯片特征绘图：
  ```python
  from visualization import ChipFeaturePlotter, plot_chip_feature
  import matplotlib.pyplot as plt

  # 便捷函数
  fig = plot_chip_feature('#20250804008', 'Von_forward', skip_points=5, normalize_to_first=True, colormap='viridis')
  plt.show()

  # 类接口
  fp = ChipFeaturePlotter('/path/to/features/')
  info = fp.get_chip_info('#20250804008')
  features = fp.list_chip_features('#20250804008')
  fig = fp.plot_chip_feature('#20250804008', 'Von_forward', skip_points=10, normalize_to_first=True)
  plt.show()
  ```

## 依赖与数据来源

- 内部依赖：
  - `experiment` 模块（实验数据访问；见 `experiment/CLAUDE.md`）
  - `features` 模块（特征数据访问；见 `features/CLAUDE.md`）
  - `logger_config`（日志配置）

- 第三方：
  - `matplotlib`、`numpy`
  - `cv2`（OpenCV，用于并行视频写入）
  - `multiprocessing` 与 `concurrent.futures`（并行帧生成）

## 文件结构

```
visualization/
├── __init__.py            # 包导出入口
├── plotter.py             # OECTPlotter 实现与并行视频工具
├── feature_plotter.py     # ChipFeaturePlotter 与便捷函数
└── example/               # 使用示例
```

## 注意事项

- 对数坐标绘制会对电流取绝对值并忽略零值，避免数学错误。
- `create_transfer_animation` 保存 `.mp4` 需系统可用的 `ffmpeg`；保存 `.gif` 需已安装 `pillow`。
- `create_transfer_video_parallel`/`*_optimized` 依赖 OpenCV 写视频（`.mp4`）。
- 当步骤数较多（≥100/≥1000）时，优先使用并行视频接口以获得更好性能。

