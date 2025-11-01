"""
OECT数据可视化包

提供完整的OECT数据和特征可视化功能，包含两个核心绘图器：

1. OECTPlotter: OECT原始实验数据可视化
   - Transfer曲线绘图（单步、多步、演化）  
   - Transient时序绘图（单步、全体）
   - Transfer演化动画和视频生成
   - 高性能多进程视频生成

2. ChipFeaturePlotter: 芯片特征数据可视化
   - 按芯片ID绘制特征演化
   - 多设备对比和数据预处理
   - 支持数据跳点、归一化等预处理
   - 多特征对比图

核心特性：
- 依赖experiment和features包，架构清晰
- 支持多种颜色映射方案和绘图样式
- 高质量图片输出（DPI=300）
- 完整的错误处理和日志记录
"""

from .plotter import OECTPlotter
from .feature_plotter import ChipFeaturePlotter, plot_chip_feature

__version__ = "2.1.0"
__all__ = ["OECTPlotter", "ChipFeaturePlotter", "plot_chip_feature"]