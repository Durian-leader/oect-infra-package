#!/usr/bin/env python3
"""
Visualization模块视频生成功能演示

展示历史应用层样式的视频生成功能：
- 左线性右log双面板布局
- 正确的log处理（先取绝对值再log）
- 参数文本框显示
- 高性能并行处理
- 支持单独视频生成
"""

from visualization import OECTPlotter, VideoConfig
from pathlib import Path


def demo_dual_panel_video():
    """演示双面板视频生成"""
    print("=== 双面板视频生成演示 ===")
    
    # 初始化绘图器（需要指定实际的HDF5文件路径）
    exp_file = "data/raw/some_experiment.h5"  # 请替换为实际文件路径
    if not Path(exp_file).exists():
        print(f"请提供有效的实验文件路径: {exp_file}")
        return
    
    plotter = OECTPlotter(exp_file)
    
    # 配置视频参数
    config = VideoConfig(
        layout='dual',           # 左线性右log
        fps=15,                 # 帧率
        dpi=150,                # 分辨率
        figsize=(12, 5),        # 图片尺寸
        show_parameters=True,    # 显示参数文本框
        show_step_info=True,    # 显示步骤信息
        n_workers=4             # 并行工作进程数
    )
    
    # 生成视频 - 默认使用所有步骤
    output_path = plotter.create_transfer_video_optimized(
        step_indices=None,      # None = 使用所有步骤（默认行为）
        output_path="transfer_dual_panel.mp4",
        config=config,
        verbose=True
    )
    
    print(f"双面板视频已生成: {output_path}")
    
    # 获取实验信息
    info = plotter.get_experiment_info()
    print(f"视频包含 {info['transfer_steps']} 个Transfer步骤")


def demo_single_layout_videos():
    """演示单一布局视频生成"""
    print("=== 单一布局视频生成演示 ===")
    
    exp_file = "data/raw/some_experiment.h5"  # 请替换为实际文件路径
    if not Path(exp_file).exists():
        print(f"请提供有效的实验文件路径: {exp_file}")
        return
    
    plotter = OECTPlotter(exp_file)
    
    # 生成线性版本
    linear_video = plotter.create_transfer_video_single(
        layout='linear',
        output_path="transfer_linear.mp4",
        fps=10,
        verbose=True
    )
    print(f"线性视频已生成: {linear_video}")
    
    # 生成对数版本
    log_video = plotter.create_transfer_video_single(
        layout='log', 
        output_path="transfer_log.mp4",
        fps=10,
        verbose=True
    )
    print(f"对数视频已生成: {log_video}")
    
    # 生成双面板版本
    dual_video = plotter.create_transfer_video_single(
        layout='dual',
        output_path="transfer_dual.mp4", 
        fps=10,
        verbose=True
    )
    print(f"双面板视频已生成: {dual_video}")


def demo_custom_step_selection():
    """演示自定义步骤选择"""
    print("=== 自定义步骤选择演示 ===")
    
    exp_file = "data/raw/some_experiment.h5"  # 请替换为实际文件路径
    if not Path(exp_file).exists():
        print(f"请提供有效的实验文件路径: {exp_file}")
        return
    
    plotter = OECTPlotter(exp_file)
    
    # 获取实验信息
    info = plotter.get_experiment_info()
    print(f"实验信息: {info}")
    
    # 选择前20个步骤
    selected_steps = list(range(0, min(20, info['transfer_steps'])))
    
    output_path = plotter.create_transfer_video_optimized(
        step_indices=selected_steps,
        output_path="transfer_first_20_steps.mp4",
        verbose=True
    )
    
    print(f"前20步骤视频已生成: {output_path}")


def demo_high_performance_settings():
    """演示高性能设置"""
    print("=== 高性能设置演示 ===")
    
    exp_file = "data/raw/some_experiment.h5"  # 请替换为实际文件路径
    if not Path(exp_file).exists():
        print(f"请提供有效的实验文件路径: {exp_file}")
        return
    
    plotter = OECTPlotter(exp_file)
    
    # 高性能配置
    config = VideoConfig(
        layout='dual',
        fps=30,                 # 高帧率
        dpi=100,                # 较低DPI提高速度
        figsize=(10, 4),        # 较小图片提高速度
        show_parameters=True,
        show_step_info=True,
        n_workers=8,            # 最大并行度
        batch_size=100          # 大批处理
    )
    
    output_path = plotter.create_transfer_video_optimized(
        step_indices=None,
        output_path="transfer_high_performance.mp4",
        config=config,
        verbose=True
    )
    
    print(f"高性能视频已生成: {output_path}")


def main():
    """主函数"""
    print("Visualization模块视频生成功能演示")
    print("延续历史应用层样式的视频生成")
    print()
    
    print("特性:")
    print("✅ 左线性右log双面板布局")
    print("✅ 正确的log处理（先取绝对值再log）")  
    print("✅ 参数文本框显示")
    print("✅ 高性能并行处理")
    print("✅ 支持单独视频生成")
    print()
    
    # 演示各种功能
    try:
        demo_dual_panel_video()
        print()
        demo_single_layout_videos()
        print()
        demo_custom_step_selection()
        print()
        demo_high_performance_settings()
        
    except Exception as e:
        print(f"演示运行失败: {e}")
        print("请确保:")
        print("1. 安装了所需依赖: opencv-python, matplotlib")
        print("2. 提供了有效的实验文件路径")
        print("3. 实验文件包含Transfer数据")


if __name__ == "__main__":
    main()