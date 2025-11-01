"""
OECT绘图器 - 简化版本，专注核心功能

只依赖experiment和features包，不依赖oect_transfer包
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.colors import LinearSegmentedColormap, Normalize
from typing import Union, List, Optional, Tuple, Dict, Any
from pathlib import Path
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
import cv2
import time
from dataclasses import dataclass

from ..experiment import Experiment


@dataclass
class VideoFrameData:
    """视频帧数据结构 - 轻量级数据传输用"""
    frame_index: int
    step_index: int
    filename: str
    
    # 原始测量数据（numpy数组）
    gate_voltage: np.ndarray
    drain_current: np.ndarray
    
    # 元数据
    data_points: int
    experiment_id: str
    
    # 设备信息
    chip_id: str
    device_id: str


@dataclass 
class VideoConfig:
    """视频生成配置"""
    # 视频设置
    fps: int = 10
    dpi: int = 150
    codec: str = 'mp4v'
    figsize: Tuple[float, float] = (12, 5)
    
    # 坐标轴设置
    xlim: Optional[Tuple[float, float]] = None
    ylim_linear: Optional[Tuple[float, float]] = None
    ylim_log: Optional[Tuple[float, float]] = None
    
    # 性能设置
    n_workers: Optional[int] = None
    batch_size: int = 50
    
    # 视觉设置
    show_parameters: bool = True  # 是否显示参数文本框
    show_step_info: bool = True   # 是否显示步骤信息
    
    # 布局设置
    layout: str = 'dual'  # 'dual': 左线性右log, 'linear': 仅线性, 'log': 仅log


def _generate_single_video_frame(frame_data: VideoFrameData, config: Dict[str, Any]) -> np.ndarray:
    """
    生成单个视频帧（工作函数，用于多进程）
    
    Args:
        frame_data: 帧数据
        config: 配置字典
        
    Returns:
        视频帧（numpy数组）
    """
    # 创建图形和子图
    layout = config.get('layout', 'dual')
    
    if layout == 'dual':
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=config['figsize'], dpi=config['dpi'])
    else:
        fig, ax1 = plt.subplots(figsize=config['figsize'], dpi=config['dpi'])
        ax2 = None
    
    # 获取数据
    vg = frame_data.gate_voltage
    id = frame_data.drain_current
    id_abs = np.abs(id)  # 正确处理：先取绝对值
    
    # 绘制左侧图（线性或单独图）
    if layout == 'dual':
        # 左侧：线性坐标
        ax1.plot(vg, id, 'b-', linewidth=2, alpha=0.8)
        ax1.set_xlabel('Gate Voltage (V)')
        ax1.set_ylabel('Drain Current (A)')
        ax1.set_title('Transfer Curve (Linear)')
        ax1.grid(True, alpha=0.3)
        ax1.set_xlim(config['xlim'])
        ax1.set_ylim(config['ylim_linear'])
        
        # 右侧：对数坐标
        ax2.semilogy(vg, id_abs, 'b-', linewidth=2, alpha=0.8)  # 使用绝对值
        ax2.set_xlabel('Gate Voltage (V)')
        ax2.set_ylabel('|Drain Current| (A)')
        ax2.set_title('Transfer Curve (Log)')
        ax2.grid(True, alpha=0.3)
        ax2.set_xlim(config['xlim'])
        ax2.set_ylim(config['ylim_log'])
        
    elif layout == 'log':
        # 仅对数坐标
        ax1.semilogy(vg, id_abs, 'b-', linewidth=2, alpha=0.8)  # 使用绝对值
        ax1.set_xlabel('Gate Voltage (V)')
        ax1.set_ylabel('|Drain Current| (A)')
        ax1.set_title('Transfer Curve (Log)')
        ax1.grid(True, alpha=0.3)
        ax1.set_xlim(config['xlim'])
        ax1.set_ylim(config['ylim_log'])
        
    else:  # linear
        # 仅线性坐标
        ax1.plot(vg, id, 'b-', linewidth=2, alpha=0.8)
        ax1.set_xlabel('Gate Voltage (V)')
        ax1.set_ylabel('Drain Current (A)')
        ax1.set_title('Transfer Curve (Linear)')
        ax1.grid(True, alpha=0.3)
        ax1.set_xlim(config['xlim'])
        ax1.set_ylim(config['ylim_linear'])
    
    # 添加参数文本框
    if config.get('show_parameters', True):
        if layout == 'dual' and ax2 is not None:
            # 对于dual布局，右侧log图不显示任何文本框（避免冗余信息）
            pass
        else:
            # 对于单图布局，显示完整信息
            total_steps = config.get('total_steps', frame_data.step_index + 1)
            param_text = f"""Step: {frame_data.step_index}/{total_steps - 1}
Chip: {frame_data.chip_id}
Device: {frame_data.device_id}
Data points: {frame_data.data_points}"""
            ax1.text(0.02, 0.98, param_text, transform=ax1.transAxes, 
                    verticalalignment='top', horizontalalignment='left',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='lightblue', alpha=0.9),
                    fontsize=9, zorder=20)
    
    # 添加步骤信息
    if config.get('show_step_info', True):
        total_steps = config.get('total_steps', frame_data.step_index + 1)  # 获取总步数
        step_text = f"Step {frame_data.step_index}/{total_steps - 1} | Chip: {frame_data.chip_id} | Device: {frame_data.device_id}\n{frame_data.experiment_id}"
        fig.suptitle(step_text, fontsize=10)
    
    plt.tight_layout()
    
    # 转换为numpy数组
    fig.canvas.draw()
    
    # 兼容不同matplotlib版本
    try:
        # 现代matplotlib
        buf = fig.canvas.buffer_rgba()
        frame = np.asarray(buf)
        # 转换RGBA到RGB
        frame = frame[:, :, :3]
    except AttributeError:
        try:
            # 旧版matplotlib
            frame = np.frombuffer(fig.canvas.tostring_rgb(), dtype=np.uint8)
            frame = frame.reshape(fig.canvas.get_width_height()[::-1] + (3,))
        except AttributeError:
            # 最后的备选方案
            buf = fig.canvas.tostring_argb()
            frame = np.frombuffer(buf, dtype=np.uint8)
            frame = frame.reshape(fig.canvas.get_width_height()[::-1] + (4,))
            # 转换ARGB到RGB
            frame = frame[:, :, 1:4]
    
    plt.close(fig)  # 关闭图形释放内存
    
    return frame


class OECTPlotter:
    """
    OECT数据绘图器 - 简化版本
    
    专注于6个核心功能，直接使用experiment包的批量接口
    
    Examples:
        plotter = OECTPlotter('data/experiment.h5')
        
        # Transfer绘图
        plotter.plot_transfer_single(0)
        plotter.plot_transfer_multiple([0, 1, 2])
        plotter.plot_transfer_evolution()
        
        # Transient绘图
        plotter.plot_transient_single(0)
        plotter.plot_transient_all()
        
        # 演化视频
        plotter.create_transfer_animation()
    """
    
    def __init__(self, experiment_file: Union[str, Path]):
        """
        初始化绘图器
        
        Args:
            experiment_file: 实验HDF5文件路径
        """
        self.exp_file = Path(experiment_file)
        if not self.exp_file.exists():
            raise FileNotFoundError(f"实验文件不存在: {experiment_file}")
        
        self.exp = Experiment(str(self.exp_file))
        
        # 获取数据摘要
        self.transfer_summary = self.exp.get_transfer_summary()
        self.transient_summary = self.exp.get_transient_summary()
        
        # 设置默认样式
        plt.rcParams.update({
            'figure.figsize': (10, 6),
            'font.size': 12,
            'lines.linewidth': 2,
            'grid.alpha': 0.3
        })
    
    def plot_transfer_single(self, 
                           step_index: int,
                           log_scale: bool = False,
                           figsize: Tuple[int, int] = (10, 6),
                           save_path: Optional[str] = None) -> plt.Figure:
        """
        绘制指定步骤的Transfer曲线
        
        Args:
            step_index: 步骤索引 (0-based)
            log_scale: 是否使用对数坐标 (True, False)
            figsize: 图片尺寸
            save_path: 保存路径（可选）
            
        Returns:
            matplotlib Figure对象
        """
        if not self.transfer_summary:
            raise ValueError("该实验文件不包含Transfer数据")
        
        if step_index >= self.transfer_summary['step_count']:
            raise IndexError(f"步骤索引超出范围: {step_index} >= {self.transfer_summary['step_count']}")
        
        # 获取单步数据
        step_data = self.exp.get_transfer_step_measurement(step_index)
        if not step_data or 'Vg' not in step_data or 'Id' not in step_data:
            raise ValueError(f"步骤 {step_index} 没有有效的Transfer数据")
        
        vg = step_data['Vg']
        id = step_data['Id']
        
        fig, ax = plt.subplots(figsize=figsize)
        
        # 决定是否使用对数坐标
        use_log = self._should_use_log_scale(log_scale)
        
        if use_log:
            # 对数坐标：先取绝对值，过滤零值
            id_abs = np.abs(id)
            id_plot = np.where(id_abs > 0, id_abs, np.nan)
            ax.plot(vg, id_plot, 'b-', linewidth=2)
            ax.set_yscale('log')
            ylabel = 'Drain Current (A) - Log Scale'
        else:
            # 线性坐标：直接绘制原始数据
            ax.plot(vg, id, 'b-', linewidth=2)
            ylabel = 'Drain Current (A)'
        
        ax.set_xlabel('Gate Voltage (V)', fontweight='bold')
        ax.set_ylabel(ylabel, fontweight='bold')
        ax.set_title(f'Transfer Characteristic - Step {step_index}', fontweight='bold')
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        
        return fig
    
    def plot_transfer_multiple(self, 
                             step_indices: List[int],
                             log_scale: bool = False,
                             figsize: Tuple[int, int] = (12, 8),
                             save_path: Optional[str] = None) -> plt.Figure:
        """
        绘制多个步骤的Transfer曲线到一个图里
        
        Args:
            step_indices: 步骤索引列表 (0-based)
            log_scale: 是否使用对数坐标 (True, False)
            figsize: 图片尺寸
            save_path: 保存路径（可选）
            
        Returns:
            matplotlib Figure对象
        """
        if not self.transfer_summary:
            raise ValueError("该实验文件不包含Transfer数据")
        
        fig, ax = plt.subplots(figsize=figsize)
        colors = plt.cm.tab10(np.linspace(0, 1, len(step_indices)))
        
        # 收集所有数据以决定对数坐标
        all_data = []
        valid_data = []
        
        for i, step_index in enumerate(step_indices):
            if step_index >= self.transfer_summary['step_count']:
                print(f"警告: 步骤索引超出范围: {step_index}")
                continue
            
            step_data = self.exp.get_transfer_step_measurement(step_index)
            if not step_data or 'Vg' not in step_data or 'Id' not in step_data:
                print(f"警告: 步骤 {step_index} 没有有效数据")
                continue
            
            vg = step_data['Vg']
            id = step_data['Id']
            all_data.extend(id)
            valid_data.append((step_index, vg, id, colors[i]))
        
        # 决定是否使用对数坐标
        use_log = self._should_use_log_scale(log_scale)
        
        # 绘制所有有效数据
        for step_index, vg, id, color in valid_data:
            if use_log:
                # 对数坐标：先取绝对值，过滤零值
                id_abs = np.abs(id)
                id_plot = np.where(id_abs > 0, id_abs, np.nan)
                ax.plot(vg, id_plot, color=color, linewidth=2, 
                       label=f'Step {step_index}', alpha=0.8)
            else:
                # 线性坐标：直接绘制原始数据
                ax.plot(vg, id, color=color, linewidth=2, 
                       label=f'Step {step_index}', alpha=0.8)
        
        if use_log:
            ax.set_yscale('log')
            ylabel = 'Drain Current (A) - Log Scale'
        else:
            ylabel = 'Drain Current (A)'
        
        ax.set_xlabel('Gate Voltage (V)', fontweight='bold')
        ax.set_ylabel(ylabel, fontweight='bold')
        ax.set_title('Transfer Characteristics Comparison', fontweight='bold')
        ax.grid(True, alpha=0.3)
        ax.legend()
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        
        return fig
    
    def plot_transfer_evolution(self, 
                              max_steps: Optional[int] = None,
                              log_scale: bool = False,
                              figsize: Tuple[int, int] = (12, 8),
                              save_path: Optional[str] = None) -> plt.Figure:
        """
        绘制Transfer演化图（从红到黑）
        
        直接调用experiment的获取全部transfer的接口
        
        Args:
            max_steps: 最大显示步骤数，None表示使用所有步骤
            log_scale: 是否使用对数坐标 (True, False)
            figsize: 图片尺寸
            save_path: 保存路径（可选）
            
        Returns:
            matplotlib Figure对象
        """
        if not self.transfer_summary:
            raise ValueError("该实验文件不包含Transfer数据")
        
        # 直接获取所有Transfer数据
        transfer_all = self.exp.get_transfer_all_measurement()
        if not transfer_all:
            raise ValueError("无法获取批量Transfer数据")
        
        measurement_data = transfer_all['measurement_data']  # Shape: [steps, data_types, data_points]
        data_info = transfer_all['data_info']
        
        # 获取Vg和Id的索引
        data_types = data_info['data_types']
        try:
            vg_idx = data_types.index('Vg')
            id_idx = data_types.index('Id')
        except ValueError:
            raise ValueError("Transfer数据中缺少Vg或Id")
        
        # 确定要处理的步骤数
        total_steps = measurement_data.shape[0]
        if max_steps is None:
            n_steps = total_steps  # 默认使用所有步骤
        else:
            n_steps = min(total_steps, max_steps)
        
        fig, ax = plt.subplots(figsize=figsize)
        
        # 创建从红到黑的颜色映射
        red_to_black = np.linspace(0, 1, n_steps)  # 0=红色, 1=黑色
        colors = []
        for i in range(n_steps):
            # 从红(1,0,0)渐变到黑(0,0,0)
            intensity = 1 - red_to_black[i]  # 从1到0
            colors.append((intensity, 0, 0))  # RGB格式
        
        # 决定是否使用对数坐标
        use_log = self._should_use_log_scale(log_scale)
        
        for step_idx in range(n_steps):
            vg = measurement_data[step_idx, vg_idx, :]
            id = measurement_data[step_idx, id_idx, :]
            
            # 透明度从浅到深
            alpha = 0.3 + 0.7 * (step_idx / (n_steps - 1))
            
            if use_log:
                # 对数坐标：先取绝对值，过滤零值
                id_abs = np.abs(id)
                id_plot = np.where(id_abs > 0, id_abs, np.nan)
                ax.plot(vg, id_plot, color=colors[step_idx], linewidth=2, alpha=alpha)
            else:
                # 线性坐标：直接绘制原始数据
                ax.plot(vg, id, color=colors[step_idx], linewidth=2, alpha=alpha)
        
        if use_log:
            ax.set_yscale('log')
            ylabel = 'Drain Current (A) - Log Scale'
        else:
            ylabel = 'Drain Current (A)'
        
        ax.set_xlabel('Gate Voltage (V)', fontweight='bold')
        ax.set_ylabel(ylabel, fontweight='bold')
        ax.set_title(f'Transfer Evolution ({n_steps} steps)', fontweight='bold')
        ax.grid(True, alpha=0.3)
        
        # 添加颜色条表示演化
        red_to_black_cmap = LinearSegmentedColormap.from_list(
            'red_to_black', [(1, 0, 0), (0, 0, 0)]
        )
        sm = plt.cm.ScalarMappable(cmap=red_to_black_cmap, 
                                  norm=Normalize(vmin=0, vmax=n_steps-1))
        sm.set_array([])
        cbar = plt.colorbar(sm, ax=ax)
        cbar.set_label('Step Index', fontweight='bold')
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        
        return fig
    
    def plot_transient_single(self, 
                            step_index: int,
                            time_range: Optional[Tuple[float, float]] = None,
                            time_range_type: str = 'original',
                            dual_time_axis: bool = True,
                            figsize: Tuple[int, int] = (12, 6),
                            save_path: Optional[str] = None) -> plt.Figure:
        """
        绘制指定步骤的Transient时序图，支持双横轴显示
        
        Args:
            step_index: 步骤索引 (0-based)
            time_range: 时间范围 (start_time, end_time)，可选
            time_range_type: 时间范围类型 ('original': original_time, 'continuous': continuous_time) [默认:'original']
            dual_time_axis: 是否显示双横轴 (True: 显示两种时间, False: 仅显示主时间轴)
            figsize: 图片尺寸
            save_path: 保存路径（可选）
            
        Returns:
            matplotlib Figure对象
        """
        if not self.transient_summary:
            raise ValueError("该实验文件不包含Transient数据")
        
        if step_index >= self.transient_summary['step_count']:
            raise IndexError(f"步骤索引超出范围: {step_index} >= {self.transient_summary['step_count']}")
        
        step_data = self.exp.get_transient_step_measurement(step_index)
        if not step_data or 'continuous_time' not in step_data or 'drain_current' not in step_data:
            raise ValueError(f"步骤 {step_index} 没有有效的Transient数据")
        
        continuous_time = step_data['continuous_time']
        original_time = step_data.get('original_time', continuous_time - continuous_time[0])
        current = step_data['drain_current']
        
        # 根据时间范围类型进行筛选
        if time_range:
            start_time, end_time = time_range
            if time_range_type == 'continuous':
                mask = (continuous_time >= start_time) & (continuous_time <= end_time)
            elif time_range_type == 'original':
                mask = (original_time >= start_time) & (original_time <= end_time)
            else:
                raise ValueError("time_range_type必须是'continuous'或'original'")
            
            continuous_time = continuous_time[mask]
            original_time = original_time[mask]
            current = current[mask]
        
        fig, ax1 = plt.subplots(figsize=figsize)
        
        # 主横轴（continuous_time）
        ax1.plot(continuous_time, current, 'b-', linewidth=2, label='Drain Current')
        ax1.set_xlabel('Continuous Time (s)', fontweight='bold', color='b')
        ax1.set_ylabel('Drain Current (A)', fontweight='bold')
        ax1.tick_params(axis='x', labelcolor='b')
        ax1.grid(True, alpha=0.3)
        
        # 设置标题
        title = f'Transient Response - Step {step_index}'
        if time_range:
            time_unit = 'continuous' if time_range_type == 'continuous' else 'step'
            title += f' (t={time_range[0]:.1f}~{time_range[1]:.1f}s {time_unit})'
        
        # 双横轴支持
        if dual_time_axis and len(original_time) > 0:
            # 创建次横轴（original_time/step_time）
            ax2 = ax1.twiny()
            
            # 关键：确保上下刻度数量完全一致
            # 方法：让次轴使用与主轴相同的刻度数量和位置
            
            # 先让matplotlib自动设置主轴刻度，然后获取刻度位置
            plt.draw()  # 强制更新以获取自动刻度
            main_ticks = ax1.get_xticks()
            
            # 过滤掉超出数据范围的刻度
            data_min, data_max = continuous_time.min(), continuous_time.max()
            valid_ticks = main_ticks[(main_ticks >= data_min) & (main_ticks <= data_max)]
            
            # 为每个主轴刻度位置找到对应的次轴标签
            secondary_labels = []
            for tick_pos in valid_ticks:
                # 找到最接近该刻度位置的数据点
                closest_idx = np.argmin(np.abs(continuous_time - tick_pos))
                corresponding_original_time = original_time[closest_idx]
                secondary_labels.append(f'{corresponding_original_time:.1f}')
            
            # 设置次轴的刻度位置和标签，确保与主轴完全匹配
            ax2.set_xlim(ax1.get_xlim())  # 与主轴范围完全一致
            ax2.set_xticks(valid_ticks)   # 使用与主轴相同的刻度位置
            ax2.set_xticklabels(secondary_labels)  # 对应的次轴标签
            
            ax2.set_xlabel('Step Time (s)', fontweight='bold', color='r')
            ax2.tick_params(axis='x', labelcolor='r')
            
            title += ' - Dual Time Axis'
        
        ax1.set_title(title, fontweight='bold')
        
        # plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        
        return fig
    
    def plot_transient_all(self, 
                         time_range: Optional[Tuple[float, float]] = None,
                         figsize: Tuple[int, int] = (15, 8),
                         save_path: Optional[str] = None) -> plt.Figure:
        """
        绘制所有Transient数据的整体图
        
        直接调用experiment的获取全部transient的接口
        
        Args:
            time_range: 时间范围 (start_time, end_time)，可选
            figsize: 图片尺寸
            save_path: 保存路径（可选）
            
        Returns:
            matplotlib Figure对象
        """
        if not self.transient_summary:
            raise ValueError("该实验文件不包含Transient数据")
        
        # 直接获取所有Transient数据
        all_data = self.exp.get_transient_all_measurement()
        if not all_data:
            raise ValueError("无法获取批量Transient数据")
        
        time = all_data['continuous_time']
        current = all_data['drain_current']
        
        # 应用时间范围筛选
        if time_range:
            start_time, end_time = time_range
            mask = (time >= start_time) & (time <= end_time)
            time = time[mask]
            current = current[mask]
        
        fig, ax = plt.subplots(figsize=figsize)
        ax.plot(time, current, 'b-', linewidth=1.5, alpha=0.8)
        
        ax.set_xlabel('Time (s)', fontweight='bold')
        ax.set_ylabel('Drain Current (A)', fontweight='bold')
        title = 'Complete Transient Response'
        if time_range:
            title += f' (t={time_range[0]:.1f}~{time_range[1]:.1f}s)'
        ax.set_title(title, fontweight='bold')
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        
        return fig
    
    def create_transfer_animation(self, 
                                max_steps: Optional[int] = None,
                                interval: int = 200,
                                save_path: Optional[str] = None,
                                figsize: Tuple[int, int] = (10, 8),
                                layout: str = 'dual') -> animation.FuncAnimation:
        """
        创建Transfer演化视频 - 传统matplotlib动画版本
        
        Args:
            max_steps: 最大步骤数，None表示使用所有步骤
            interval: 帧间隔（毫秒）
            save_path: 保存路径（可选，.mp4或.gif）
            figsize: 图片尺寸
            layout: 布局方式 ('dual': 左线性右log, 'linear': 仅线性, 'log': 仅log)
            
        Returns:
            matplotlib动画对象
        """
        if not self.transfer_summary:
            raise ValueError("该实验文件不包含Transfer数据")
        
        # 直接获取所有Transfer数据
        transfer_all = self.exp.get_transfer_all_measurement()
        if not transfer_all:
            raise ValueError("无法获取批量Transfer数据")
        
        measurement_data = transfer_all['measurement_data']
        data_info = transfer_all['data_info']
        
        # 获取Vg和Id的索引
        data_types = data_info['data_types']
        try:
            vg_idx = data_types.index('Vg')
            id_idx = data_types.index('Id')
        except ValueError:
            raise ValueError("Transfer数据中缺少Vg或Id")
        
        # 确定要处理的步骤数
        total_steps = measurement_data.shape[0]
        if max_steps is None:
            n_steps = total_steps  # 默认使用所有步骤
        else:
            n_steps = min(total_steps, max_steps)
        
        # 根据布局设置图片
        if layout == 'dual':
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize)
        else:
            fig, ax1 = plt.subplots(figsize=figsize)
            ax2 = None
        
        # 确定坐标轴范围
        all_vg = measurement_data[:n_steps, vg_idx, :].flatten()
        all_id = measurement_data[:n_steps, id_idx, :].flatten()
        all_id_abs = np.abs(all_id)  # 正确处理：先取绝对值
        all_id_abs_positive = all_id_abs[all_id_abs > 0]  # 过滤零值用于对数坐标
        
        xlim = (all_vg.min() * 1.1, all_vg.max() * 1.1)
        ylim_linear = (all_id.min() * 1.1, all_id.max() * 1.1)
        ylim_log = (all_id_abs_positive.min() * 0.1, all_id_abs_positive.max() * 10) if len(all_id_abs_positive) > 0 else (1e-12, 1e-3)
        
        # 设置左侧坐标轴（线性）
        ax1.set_xlim(xlim)
        ax1.set_xlabel('Gate Voltage (V)', fontweight='bold')
        ax1.grid(True, alpha=0.3)
        
        if layout == 'dual':
            ax1.set_ylim(ylim_linear)
            ax1.set_ylabel('Drain Current (A)', fontweight='bold')
            ax1.set_title('Transfer Curve (Linear)', fontweight='bold')
            line1, = ax1.plot([], [], 'b-', linewidth=2)
            
            # 设置右侧坐标轴（对数）
            ax2.set_xlim(xlim)
            ax2.set_ylim(ylim_log)
            ax2.set_yscale('log')
            ax2.set_xlabel('Gate Voltage (V)', fontweight='bold')
            ax2.set_ylabel('|Drain Current| (A)', fontweight='bold')
            ax2.set_title('Transfer Curve (Log)', fontweight='bold')
            ax2.grid(True, alpha=0.3)
            line2, = ax2.plot([], [], 'b-', linewidth=2)
        
        elif layout == 'log':
            ax1.set_ylim(ylim_log)
            ax1.set_yscale('log')
            ax1.set_ylabel('|Drain Current| (A)', fontweight='bold')
            ax1.set_title('Transfer Curve (Log)', fontweight='bold')
            line1, = ax1.plot([], [], 'b-', linewidth=2)
        
        else:  # linear
            ax1.set_ylim(ylim_linear)
            ax1.set_ylabel('Drain Current (A)', fontweight='bold')
            ax1.set_title('Transfer Curve (Linear)', fontweight='bold')
            line1, = ax1.plot([], [], 'b-', linewidth=2)
        
        title = fig.suptitle('', fontweight='bold')
        
        def animate(frame):
            if frame < n_steps:
                vg = measurement_data[frame, vg_idx, :]
                id = measurement_data[frame, id_idx, :]
                id_abs = np.abs(id)  # 正确处理：先取绝对值
                
                if layout == 'dual':
                    line1.set_data(vg, id)  # 线性：原始数据
                    line2.set_data(vg, id_abs)  # 对数：绝对值
                    title.set_text(f'Transfer Evolution - Step {frame}/{n_steps - 1}')
                    return line1, line2, title
                
                elif layout == 'log':
                    line1.set_data(vg, id_abs)  # 对数：绝对值
                else:
                    line1.set_data(vg, id)  # 线性：原始数据
                
                title.set_text(f'Transfer Evolution - Step {frame}/{n_steps - 1}')
            
            return line1, title
        
        ani = animation.FuncAnimation(fig, animate, frames=n_steps, 
                                    interval=interval, blit=True, repeat=True)
        
        if save_path:
            if save_path.endswith('.gif'):
                ani.save(save_path, writer='pillow', fps=1000//interval)
            elif save_path.endswith('.mp4'):
                ani.save(save_path, writer='ffmpeg', fps=1000//interval)
            else:
                ani.save(save_path + '.gif', writer='pillow', fps=1000//interval)
        
        return ani
    
    def create_transfer_video_parallel(self, 
                                     max_steps: Optional[int] = None,
                                     fps: int = 10,
                                     save_path: str = "transfer_evolution_parallel.mp4",
                                     figsize: Tuple[float, float] = (12, 5),
                                     layout: str = 'dual',
                                     n_workers: Optional[int] = None,
                                     verbose: bool = True) -> str:
        """
        创建Transfer演化视频 - 高性能多进程版本
        
        这个版本使用多进程并行生成视频帧，显著加速大数据集的处理。
        特别适合5000+步骤的大规模数据。
        
        Args:
            max_steps: 最大步骤数，None表示使用所有步骤
            fps: 视频帧率
            save_path: 保存路径（.mp4格式）
            figsize: 图片尺寸
            layout: 布局方式 ('dual': 左线性右log, 'linear': 仅线性, 'log': 仅log)
            n_workers: 工作进程数，None表示自动选择
            verbose: 是否显示进度
            
        Returns:
            str: 保存的视频文件路径
        """
        if not self.transfer_summary:
            raise ValueError("该实验文件不包含Transfer数据")
        
        if verbose:
            print(f"使用多进程并行生成Transfer演化视频...")
            print(f"数据规模: {self.transfer_summary['step_count']} 步骤")
        
        start_time = time.time()
        
        # Phase 1: 批量提取数据
        frame_data_list = self._extract_transfer_frame_data(max_steps, verbose)
        
        extraction_time = time.time()
        if verbose:
            print(f"数据提取完成: {extraction_time - start_time:.2f}s")
        
        # Phase 2: 创建配置对象
        config = VideoConfig(
            fps=fps,
            figsize=figsize,
            layout=layout,
            n_workers=n_workers,
            show_parameters=True,
            show_step_info=True
        )
        
        # Phase 3: 自动确定坐标范围
        self._auto_determine_ranges(frame_data_list, config, verbose)
        
        # Phase 4: 并行生成帧
        frames = self._generate_video_frames_parallel(frame_data_list, config, verbose)
        
        generation_time = time.time()
        if verbose:
            print(f"帧生成完成: {generation_time - extraction_time:.2f}s")
        
        # Phase 5: 写入视频
        self._write_video_file(frames, save_path, config, verbose)
        
        total_time = time.time()
        if verbose:
            print(f"总用时: {total_time - start_time:.2f}s")
            print(f"视频已保存: {save_path}")
        
        return save_path
    
    def _extract_transfer_frame_data(self, 
                                   max_steps: Optional[int],
                                   verbose: bool) -> List[VideoFrameData]:
        """
        提取Transfer数据用于多进程视频生成
        """
        # 直接获取所有Transfer数据
        transfer_all = self.exp.get_transfer_all_measurement()
        if not transfer_all:
            raise ValueError("无法获取批量Transfer数据")
        
        measurement_data = transfer_all['measurement_data']
        data_info = transfer_all['data_info']
        
        # 获取Vg和Id的索引
        data_types = data_info['data_types']
        try:
            vg_idx = data_types.index('Vg')
            id_idx = data_types.index('Id')
        except ValueError:
            raise ValueError("Transfer数据中缺少Vg或Id")
        
        # 确定要处理的步骤数
        total_steps = measurement_data.shape[0]
        if max_steps is None:
            n_steps = total_steps
        else:
            n_steps = min(total_steps, max_steps)
        
        if verbose:
            print(f"准备提取 {n_steps}/{total_steps} 步骤的数据...")
        
        # 创建轻量级帧数据列表
        frame_data_list = []
        for step_idx in range(n_steps):
            vg = measurement_data[step_idx, vg_idx, :].copy()
            id = measurement_data[step_idx, id_idx, :].copy()
            
            frame_data = VideoFrameData(
                frame_index=step_idx,
                step_index=step_idx,
                filename=f"step_{step_idx:06d}",
                gate_voltage=vg,
                drain_current=id,
                data_points=len(vg),
                experiment_id=str(self.exp.test_id or ""),
                chip_id=str(self.exp.chip_id or ""),
                device_id=str(self.exp.device_number or "")
            )
            frame_data_list.append(frame_data)
        
        if verbose:
            print(f"成功提取 {len(frame_data_list)} 帧数据")
        
        return frame_data_list
    
    def _auto_determine_ranges(self, 
                             frame_data_list: List[VideoFrameData],
                             config: VideoConfig,
                             verbose: bool) -> None:
        """
        自动确定坐标轴范围
        """
        if not frame_data_list:
            return
        
        # 收集所有数据用于范围计算
        all_vg = []
        all_id = []
        all_id_abs = []
        
        for frame_data in frame_data_list:
            all_vg.extend(frame_data.gate_voltage)
            all_id.extend(frame_data.drain_current)
            all_id_abs.extend(np.abs(frame_data.drain_current))
        
        # X轴（门电压）范围
        if config.xlim is None:
            vg_min, vg_max = np.min(all_vg), np.max(all_vg)
            margin = (vg_max - vg_min) * 0.05
            config.xlim = (vg_min - margin, vg_max + margin)
        
        # Y轴线性范围
        if config.ylim_linear is None:
            id_min, id_max = np.min(all_id), np.max(all_id)
            margin = (id_max - id_min) * 0.1
            config.ylim_linear = (id_min - margin, id_max + margin)
        
        # Y轴对数范围
        if config.ylim_log is None:
            if len(all_id_abs) > 0:
                all_id_abs_positive = [x for x in all_id_abs if x > 0]
                if len(all_id_abs_positive) > 0:
                    id_abs_min, id_abs_max = np.min(all_id_abs_positive), np.max(all_id_abs_positive)
                    config.ylim_log = (id_abs_min * 0.1, id_abs_max * 10)
                else:
                    config.ylim_log = (1e-12, 1e-3)
            else:
                config.ylim_log = (1e-12, 1e-3)
        
        if verbose:
            print(f"自动确定坐标范围:")
            print(f"  X轴: {config.xlim}")
            print(f"  Y轴(线性): {config.ylim_linear}")
            print(f"  Y轴(对数): {config.ylim_log}")
    
    def _should_use_log_scale(self, log_scale_setting: bool) -> bool:
        """
        决定是否使用对数坐标
        
        Args:
            log_scale_setting: 对数坐标设置 (True, False)
            
        Returns:
            是否使用对数坐标
        """
        return bool(log_scale_setting)
    
    def get_experiment_info(self) -> dict:
        """获取实验基本信息"""
        summary = self.exp.get_experiment_summary()
        return {
            'chip_id': self.exp.chip_id,
            'device_number': self.exp.device_number,
            'status': summary['progress_info']['status'],
            'transfer_steps': self.transfer_summary['step_count'] if self.transfer_summary else 0,
            'transient_steps': self.transient_summary['step_count'] if self.transient_summary else 0
        }
    
    def create_transfer_video_optimized(self,
                                      step_indices: Optional[List[int]] = None,
                                      output_path: str = "transfer_evolution_optimized.mp4",
                                      config: Optional[VideoConfig] = None,
                                      verbose: bool = True) -> str:
        """
        创建高性能Transfer演化视频 - 延续历史应用层样式
        
        特性：
        - 左线性右log双面板布局（可配置）
        - 高性能并行帧生成
        - 正确的log处理（先取绝对值再log）
        - 参数文本框显示
        
        Args:
            step_indices: 步骤索引列表 (0-based)，None表示使用所有步骤
            output_path: 输出视频路径
            config: 视频配置，None使用默认配置
            verbose: 是否显示进度
            
        Returns:
            输出视频文件路径
        """
        if not self.transfer_summary:
            raise ValueError("该实验文件不包含Transfer数据")
        
        if config is None:
            config = VideoConfig()
        
        if verbose:
            print(f"使用高性能视频生成架构创建Transfer演化视频...")
        
        start_time = time.time()
        
        # 阶段1：批量提取帧数据
        frame_data_list = self._extract_video_frame_data(
            step_indices, verbose
        )
        
        extraction_time = time.time()
        if verbose:
            print(f"数据提取完成，用时 {extraction_time - start_time:.2f}s")
        
        # 阶段2：自动确定坐标范围
        self._auto_determine_video_ranges(frame_data_list, config, verbose)
        
        # 阶段3：并行生成帧
        frames = self._generate_video_frames_parallel(frame_data_list, config, verbose)
        
        generation_time = time.time()
        if verbose:
            print(f"帧生成完成，用时 {generation_time - extraction_time:.2f}s")
        
        # 阶段4：写入视频
        self._write_video_file(frames, output_path, config, verbose)
        
        total_time = time.time()
        if verbose:
            print(f"视频生成完成，总用时 {total_time - start_time:.2f}s")
            print(f"视频保存至: {output_path}")
        
        return output_path
    
    def create_transfer_video_single(self,
                                   layout: str = 'linear',
                                   step_indices: Optional[List[int]] = None,
                                   output_path: Optional[str] = None,
                                   **kwargs) -> str:
        """
        创建单一布局的Transfer演化视频
        
        Args:
            layout: 布局类型 ('linear': 线性, 'log': 对数, 'dual': 双面板)
            step_indices: 步骤索引列表
            output_path: 输出路径，None则自动生成
            **kwargs: 其他配置参数
            
        Returns:
            输出视频文件路径
        """
        if output_path is None:
            output_path = f"transfer_{layout}.mp4"
        
        config = VideoConfig(layout=layout, **kwargs)
        return self.create_transfer_video_optimized(
            step_indices, output_path, config, 
            verbose=kwargs.get('verbose', True)
        )
    
    def _extract_video_frame_data(self,
                                 step_indices: Optional[List[int]],
                                 verbose: bool) -> List[VideoFrameData]:
        """
        批量提取视频帧数据
        """
        if verbose:
            print("提取帧数据...")
        
        # 获取所有Transfer数据
        transfer_all = self.exp.get_transfer_all_measurement()
        if not transfer_all:
            raise ValueError("无法获取批量Transfer数据")
        
        measurement_data = transfer_all['measurement_data']
        data_info = transfer_all['data_info']
        
        # 获取Vg和Id的索引
        data_types = data_info['data_types']
        try:
            vg_idx = data_types.index('Vg')
            id_idx = data_types.index('Id')
        except ValueError:
            raise ValueError("Transfer数据中缺少Vg或Id")
        
        # 确定要处理的步骤
        total_steps = measurement_data.shape[0]
        if step_indices is None:
            step_indices = list(range(total_steps))
        else:
            # 验证索引有效性
            step_indices = [i for i in step_indices if 0 <= i < total_steps]
        
        if verbose:
            print(f"处理 {len(step_indices)} 个步骤")
        
        frame_data_list = []
        
        for i, step_idx in enumerate(step_indices):
            try:
                # 提取数据
                vg = measurement_data[step_idx, vg_idx, :].copy()
                id = measurement_data[step_idx, id_idx, :].copy()
                
                # 创建帧数据
                frame_data = VideoFrameData(
                    frame_index=i,
                    step_index=step_idx,
                    filename=f"step_{step_idx:06d}",
                    gate_voltage=vg,
                    drain_current=id,
                    data_points=len(vg),
                    experiment_id=str(self.exp.test_id or "")
                )
                
                frame_data_list.append(frame_data)
                
            except Exception as e:
                if verbose:
                    print(f"警告: 处理步骤 {step_idx} 失败: {e}")
                continue
        
        if verbose:
            print(f"成功提取 {len(frame_data_list)} 帧数据")
        
        return frame_data_list
    
    def _auto_determine_video_ranges(self,
                                   frame_data_list: List[VideoFrameData],
                                   config: VideoConfig,
                                   verbose: bool) -> None:
        """
        自动确定视频坐标范围
        """
        if not frame_data_list:
            return
        
        # 收集所有数据用于范围计算
        all_vg = []
        all_id = []
        all_id_abs = []
        
        for frame_data in frame_data_list:
            all_vg.extend(frame_data.gate_voltage)
            all_id.extend(frame_data.drain_current)
            all_id_abs.extend(np.abs(frame_data.drain_current))
        
        # X轴（门电压）范围
        if config.xlim is None:
            vg_min, vg_max = np.min(all_vg), np.max(all_vg)
            margin = (vg_max - vg_min) * 0.05
            config.xlim = (vg_min - margin, vg_max + margin)
        
        # Y轴线性范围
        if config.ylim_linear is None:
            id_min, id_max = np.min(all_id), np.max(all_id)
            margin = (id_max - id_min) * 0.1
            config.ylim_linear = (id_min - margin, id_max + margin)
        
        # Y轴对数范围
        if config.ylim_log is None:
            if len(all_id_abs) > 0:
                all_id_abs_positive = [x for x in all_id_abs if x > 0]
                if len(all_id_abs_positive) > 0:
                    id_abs_min, id_abs_max = np.min(all_id_abs_positive), np.max(all_id_abs_positive)
                    config.ylim_log = (id_abs_min * 0.1, id_abs_max * 10)
                else:
                    config.ylim_log = (1e-12, 1e-3)
            else:
                config.ylim_log = (1e-12, 1e-3)
        
        if verbose:
            print(f"自动确定坐标范围:")
            print(f"  X轴: {config.xlim}")
            print(f"  Y轴(线性): {config.ylim_linear}")
            print(f"  Y轴(对数): {config.ylim_log}")
    
    def _generate_video_frames_parallel(self,
                                      frame_data_list: List[VideoFrameData],
                                      config: VideoConfig,
                                      verbose: bool) -> List[np.ndarray]:
        """
        并行生成视频帧
        """
        if not frame_data_list:
            return []
        
        n_workers = config.n_workers or min(mp.cpu_count(), len(frame_data_list))
        
        if verbose:
            print(f"使用 {n_workers} 个工作进程并行生成 {len(frame_data_list)} 帧...")
        
        # 创建配置字典（可序列化）
        config_dict = {
            'figsize': config.figsize,
            'dpi': config.dpi,
            'xlim': config.xlim,
            'ylim_linear': config.ylim_linear,
            'ylim_log': config.ylim_log,
            'show_parameters': config.show_parameters,
            'show_step_info': config.show_step_info,
            'layout': config.layout,
            'total_steps': len(frame_data_list)  # 添加总步数信息
        }
        
        frames = [None] * len(frame_data_list)  # 预分配以保持顺序
        
        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            # 提交所有任务
            future_to_index = {
                executor.submit(_generate_single_video_frame, frame_data, config_dict): i
                for i, frame_data in enumerate(frame_data_list)
            }
            
            completed = 0
            for future in as_completed(future_to_index):
                frame_index = future_to_index[future]
                try:
                    frame = future.result()
                    frames[frame_index] = frame
                    completed += 1
                    
                    if verbose and (completed % max(1, len(frame_data_list) // 10) == 0 or completed == len(frame_data_list)):
                        print(f"进度: {completed}/{len(frame_data_list)} 帧 ({completed/len(frame_data_list)*100:.1f}%)")
                        
                except Exception as e:
                    if verbose:
                        print(f"警告: 生成帧 {frame_index} 失败: {e}")
                    frames[frame_index] = None
        
        # 过滤失败的帧
        valid_frames = [f for f in frames if f is not None]
        
        if verbose:
            print(f"成功生成 {len(valid_frames)}/{len(frame_data_list)} 帧")
        
        return valid_frames
    
    def _write_video_file(self,
                        frames: List[np.ndarray],
                        output_path: str,
                        config: VideoConfig,
                        verbose: bool) -> None:
        """
        写入视频文件
        """
        if not frames:
            raise ValueError("没有可写入的帧")
        
        # 确保输出目录存在
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        
        if verbose:
            print(f"写入 {len(frames)} 帧到视频文件...")
        
        # 获取视频属性
        height, width = frames[0].shape[:2]
        
        # 初始化视频写入器
        fourcc = cv2.VideoWriter_fourcc(*config.codec)
        out = cv2.VideoWriter(output_path, fourcc, config.fps, (width, height))
        
        try:
            for i, frame in enumerate(frames):
                # 转换RGB到BGR
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                out.write(frame_bgr)
                
                if verbose and (i % max(1, len(frames) // 10) == 0 or i == len(frames) - 1):
                    print(f"写入进度: {i+1}/{len(frames)} 帧 ({(i+1)/len(frames)*100:.1f}%)")
        finally:
            out.release()
        
        if verbose:
            file_size_mb = Path(output_path).stat().st_size / 1024 / 1024
            print(f"视频写入成功: {file_size_mb:.2f} MB")