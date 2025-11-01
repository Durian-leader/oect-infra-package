"""
芯片特征绘制接口

提供按芯片ID绘制特征数据的接口，支持多设备对比和数据预处理功能。
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
import warnings
warnings.filterwarnings('ignore')

########################### 日志设置 ################################
from ..logger_config import get_module_logger
logger = get_module_logger()
#####################################################################

from ..features import BatchManager, FeatureReader, FeatureData


class ChipFeaturePlotter:
    """
    芯片特征绘制器
    
    提供按芯片ID绘制特征数据的功能，支持：
    - 按device_id排序显示多个设备
    - 数据预处理（去除前N点、首点归一化）
    - 自动查找和加载特征文件
    """
    
    def __init__(self, features_dir: str):
        """
        初始化绘制器
        
        Args:
            features_dir: 特征文件所在目录
        """
        self.batch_manager = BatchManager(features_dir)
        
    def plot_chip_feature(self,
                         chip_id: str,
                         feature_name: str,
                         skip_points: int = 0,
                         normalize_to_first: bool = False,
                         data_type: str = "transfer",
                         figsize: Tuple[int, int] = (12, 8),
                         title: str = None,
                         save_path: str = None,
                         colormap: str = "plasma",
                         linewidth: float = 2.0,
                         markersize: float = 4.0) -> plt.Figure:
        """
        绘制指定芯片的特征数据
        
        Args:
            chip_id: 芯片ID
            feature_name: 特征名称
            skip_points: 去除前多少个点（默认为0）
            normalize_to_first: 是否做首点归一化（默认为False）
            data_type: 数据类型，"transfer"或"transient"
            figsize: 图形大小
            title: 自定义标题
            save_path: 保存路径，None表示不保存
            colormap: 颜色映射方案，支持：
                - "plasma": 等离子体配色（紫→红→黄）
                - "viridis": 绿黄配色（紫→蓝→绿→黄）
                - "coolwarm": 冷暖配色（蓝→白→红）
                - "RdYlBu": 红黄蓝配色（红→黄→蓝）
                - "hot": 热色系配色（黑→红→橙→黄→白）
                - "inferno": 地狱配色（黑→紫→红→橙→黄）
            linewidth: 线条粗细，默认2.0
            markersize: 点的大小，默认4.0，设置为0则不显示点
            
        Returns:
            matplotlib图形对象
            
        Examples:
            >>> plotter = ChipFeaturePlotter("/mnt/d/UserData/lidonghaowsl/data/Stability_PS/features/")
            >>> fig = plotter.plot_chip_feature(
            ...     chip_id="#20250804008",
            ...     feature_name="gm_max_forward",
            ...     skip_points=5,
            ...     normalize_to_first=True
            ... )
            >>> plt.show()
        """
        logger.info(f"开始绘制芯片 {chip_id} 的特征 {feature_name}")
        
        # 查找该芯片的所有特征文件
        chip_files = self.batch_manager.find_files(chip_id=chip_id)
        
        if not chip_files:
            raise ValueError(f"未找到芯片 {chip_id} 的特征文件")
        
        logger.info(f"找到 {len(chip_files)} 个特征文件")
        
        # 按device_id排序
        chip_files.sort(key=lambda x: int(x['info'].device_id))
        
        # 收集数据
        plot_data = []
        
        for file_data in chip_files:
            filepath = str(file_data['path'])
            device_info = file_data['info']
            
            try:
                reader = FeatureReader(filepath)
                
                # 检查特征是否存在
                available_features = reader.list_features(data_type)
                if feature_name not in available_features:
                    logger.warning(f"特征 {feature_name} 不存在于文件 {device_info.device_id}")
                    continue
                
                # 读取特征数据
                feature_data = reader.get_feature(feature_name, data_type)
                
                if feature_data is None or len(feature_data) == 0:
                    logger.warning(f"特征数据为空: {device_info.device_id}")
                    continue
                
                plot_data.append({
                    'device_id': device_info.device_id,
                    'data': feature_data,
                    'filepath': filepath,
                    'file_info': device_info
                })
                
            except Exception as e:
                logger.error(f"读取文件 {device_info.device_id} 失败: {e}")
                continue
        
        if not plot_data:
            raise ValueError(f"未能成功加载任何特征数据")
        
        logger.info(f"成功加载 {len(plot_data)} 个设备的数据")
        
        # 数据预处理和绘制
        fig, ax = plt.subplots(figsize=figsize)
        
        # 为每个设备选择热图风格的颜色
        try:
            cmap = plt.cm.get_cmap(colormap)
            colors = cmap(np.linspace(0, 1, len(plot_data)))
        except ValueError:
            logger.warning(f"未知的颜色映射 '{colormap}'，使用默认的 'plasma'")
            colors = plt.cm.plasma(np.linspace(0, 1, len(plot_data)))
        
        processed_info = []
        
        for i, device_data in enumerate(plot_data):
            device_id = device_data['device_id']
            raw_data = device_data['data']
            
            # 应用skip_points
            if skip_points > 0 and len(raw_data) > skip_points:
                processed_data = raw_data[skip_points:]
                x_data = np.arange(skip_points, len(raw_data))
            else:
                processed_data = raw_data
                x_data = np.arange(len(raw_data))
            
            # 应用首点归一化
            if normalize_to_first and len(processed_data) > 0:
                first_value = processed_data[0]
                if first_value != 0:
                    processed_data = processed_data / first_value
                else:
                    logger.warning(f"设备 {device_id} 首点值为0，跳过归一化")
            
            # 绘制数据
            plot_kwargs = {
                'color': colors[i],
                'linewidth': linewidth,
                'label': f'Device {device_id}',
                'alpha': 0.8
            }
            
            # 只有当markersize > 0时才显示标记点
            if markersize > 0:
                plot_kwargs.update({
                    'marker': 'o',
                    'markersize': markersize
                })
            
            ax.plot(x_data, processed_data, **plot_kwargs)
            
            # 记录处理信息
            processed_info.append({
                'device_id': device_id,
                'original_points': len(raw_data),
                'processed_points': len(processed_data),
                'skipped_points': skip_points,
                'normalized': normalize_to_first,
                'first_value': raw_data[0] if len(raw_data) > 0 else None,
                'final_range': (processed_data.min(), processed_data.max()) if len(processed_data) > 0 else None
            })
        
        # 设置图形属性
        ax.set_xlabel('Step Index', fontsize=12)
        
        # Y轴标签
        if normalize_to_first:
            ax.set_ylabel(f'{feature_name} (Normalized to First Point)', fontsize=12)
        else:
            ax.set_ylabel(f'{feature_name}', fontsize=12)
        
        # 标题
        if title is None:
            title_parts = [f'Chip {chip_id} - {feature_name}']
            if skip_points > 0:
                title_parts.append(f'(Skip first {skip_points} points)')
            if normalize_to_first:
                title_parts.append(f'(Normalized)')
            title = ' '.join(title_parts)
        
        ax.set_title(title, fontsize=14, fontweight='bold')
        
        # 图例
        ax.legend(loc='best', framealpha=0.9)
        
        # 网格
        ax.grid(True, alpha=0.3)
        
        # 美化
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        plt.tight_layout()
        
        # 打印处理信息
        logger.info("数据处理摘要:")
        for info in processed_info:
            logger.info(f"  设备 {info['device_id']}: {info['original_points']} -> {info['processed_points']} 点")
            if info['final_range']:
                logger.info(f"    数据范围: {info['final_range'][0]:.2e} ~ {info['final_range'][1]:.2e}")
        
        # 保存图片
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            logger.info(f"图片已保存到: {save_path}")
        
        return fig
    
    def list_chip_features(self, chip_id: str, data_type: str = "transfer") -> List[str]:
        """
        列出指定芯片的所有可用特征
        
        Args:
            chip_id: 芯片ID
            data_type: 数据类型
            
        Returns:
            特征名称列表
        """
        chip_files = self.batch_manager.find_files(chip_id=chip_id)
        
        if not chip_files:
            return []
        
        # 找到所有文件的共同特征
        file_paths = [str(file_data['path']) for file_data in chip_files]
        common_features = self.batch_manager.find_common_features(file_paths, data_type)
        
        return common_features
    
    def get_chip_info(self, chip_id: str) -> Dict[str, Any]:
        """
        获取指定芯片的基本信息
        
        Args:
            chip_id: 芯片ID
            
        Returns:
            芯片信息字典
        """
        chip_files = self.batch_manager.find_files(chip_id=chip_id)
        
        if not chip_files:
            return {'error': f'未找到芯片 {chip_id}'}
        
        # 统计信息
        device_ids = [file_data['info'].device_id for file_data in chip_files]
        descriptions = list(set(file_data['info'].description for file_data in chip_files))
        
        return {
            'chip_id': chip_id,
            'total_files': len(chip_files),
            'device_ids': sorted(device_ids, key=int),
            'descriptions': descriptions,
            'file_paths': [str(file_data['path']) for file_data in chip_files]
        }
    


def plot_chip_feature(chip_id: str,
                     feature_name: str,
                     skip_points: int = 0,
                     normalize_to_first: bool = False,
                     features_dir: str = "/mnt/d/UserData/lidonghaowsl/data/Stability_PS/features/",
                     colormap: str = "plasma",
                     linewidth: float = 2.0,
                     markersize: float = 4.0,
                     **kwargs) -> plt.Figure:
    """
    便捷函数：绘制指定芯片的特征数据
    
    Args:
        chip_id: 芯片ID
        feature_name: 特征名称
        skip_points: 去除前多少个点（默认为0）
        normalize_to_first: 是否做首点归一化（默认为False）
        features_dir: 特征文件目录
        colormap: 颜色映射方案（默认plasma）
        linewidth: 线条粗细（默认2.0）
        markersize: 点的大小（默认4.0，设置为0则不显示点）
        **kwargs: 其他绘图参数
        
    Returns:
        matplotlib图形对象
        
    Examples:
        >>> fig = plot_chip_feature("#20250804008", "gm_max_forward", skip_points=5, normalize_to_first=True)
        >>> plt.show()
    """
    plotter = ChipFeaturePlotter(features_dir)
    return plotter.plot_chip_feature(
        chip_id=chip_id,
        feature_name=feature_name,
        skip_points=skip_points,
        normalize_to_first=normalize_to_first,
        colormap=colormap,
        linewidth=linewidth,
        markersize=markersize,
        **kwargs
    )


if __name__ == "__main__":
    # 示例使用
    plotter = ChipFeaturePlotter("/mnt/d/UserData/lidonghaowsl/data/Stability_PS/features/")
    
    # 查看可用芯片和特征
    print("测试芯片信息查询...")
    chip_info = plotter.get_chip_info("#20250804008")
    print(f"芯片信息: {chip_info}")
    
    if not chip_info.get('error'):
        # 查看可用特征
        features = plotter.list_chip_features("#20250804008")
        print(f"可用特征: {features[:5]}...")  # 显示前5个
        
        if features:
            # 绘制单个特征
            print(f"\n绘制特征: {features[0]}")
            fig = plotter.plot_chip_feature(
                chip_id="#20250804008",
                feature_name=features[0],
                skip_points=2,
                normalize_to_first=True
            )
            plt.show()