"""
简化版visualization包使用示例

演示6个核心功能的使用方法
"""

from visualization import OECTPlotter
import matplotlib.pyplot as plt

def example_usage():
    """使用示例"""
    
    # 初始化绘图器
    experiment_file = "data/your_experiment.h5"  # 替换为实际文件路径
    plotter = OECTPlotter(experiment_file)
    
    # 获取实验信息
    info = plotter.get_experiment_info()
    print(f"实验信息: {info}")
    
    # ===== Transfer相关绘图 =====
    
    # 1. 绘制指定步骤的Transfer曲线（默认线性坐标）
    print("1. 绘制单个Transfer步骤...")
    fig1 = plotter.plot_transfer_single(0, save_path="transfer_step_0.png")
    plt.show()
    
    # 1b. 使用对数坐标
    print("1b. 绘制单个Transfer步骤（对数坐标）...")
    fig1b = plotter.plot_transfer_single(0, log_scale=True, save_path="transfer_step_0_log.png")
    plt.show()
    
    # 2. 绘制多个步骤的Transfer曲线
    print("2. 绘制多个Transfer步骤...")
    fig2 = plotter.plot_transfer_multiple([0, 1, 2, 5, 10], save_path="transfer_multiple.png")
    plt.show()
    
    # 3. 绘制Transfer演化图（从红到黑渐变）
    print("3. 绘制Transfer演化图（红→黑渐变）...")
    fig3 = plotter.plot_transfer_evolution(max_steps=20, save_path="transfer_evolution.png")
    plt.show()
    
    # 3b. 对数坐标的演化图
    print("3b. 绘制Transfer演化图（对数坐标，红→黑）...")
    fig3b = plotter.plot_transfer_evolution(max_steps=20, log_scale=True, save_path="transfer_evolution_log.png")
    plt.show()
    
    # 3c. 大量步骤的演化图
    print("3c. 绘制大量步骤的演化图...")
    fig3c = plotter.plot_transfer_evolution(max_steps=100, save_path="transfer_evolution_detailed.png")
    plt.show()
    
    # ===== Transient相关绘图 =====
    
    # 4. 绘制单个步骤的Transient图
    print("4. 绘制单个Transient步骤...")
    fig4 = plotter.plot_transient_single(0, save_path="transient_step_0.png")
    plt.show()
    
    # 4b. 绘制指定时间范围的Transient图
    print("4b. 绘制指定时间范围的Transient...")
    fig4b = plotter.plot_transient_single(0, time_range=(0, 100), save_path="transient_step_0_limited.png")
    plt.show()
    
    # 5. 绘制所有Transient数据的整体图
    print("5. 绘制完整Transient数据...")
    fig5 = plotter.plot_transient_all(save_path="transient_all.png")
    plt.show()
    
    # 5b. 绘制指定时间范围的完整Transient数据
    print("5b. 绘制指定时间范围的完整Transient数据...")
    fig5b = plotter.plot_transient_all(time_range=(0, 500), save_path="transient_all_limited.png")
    plt.show()
    
    # 6. 创建Transfer演化视频
    print("6. 创建Transfer演化视频...")
    ani = plotter.create_transfer_animation(
        max_steps=30, 
        interval=300, 
        save_path="transfer_evolution.gif"
    )
    plt.show()  # 显示动画窗口
    
    print("所有示例完成！")

def quick_examples():
    """快速使用示例"""
    
    plotter = OECTPlotter("data/your_experiment.h5")
    
    # 最简单的使用方式（默认线性坐标）
    plotter.plot_transfer_single(0)
    plt.show()
    
    plotter.plot_transfer_multiple([0, 1, 2])
    plt.show()
    
    plotter.plot_transfer_evolution()
    plt.show()
    
    # 对数坐标示例
    plotter.plot_transfer_single(0, log_scale=True)
    plt.show()
    
    plotter.plot_transient_single(0)
    plt.show()
    
    plotter.plot_transient_all()
    plt.show()

def batch_processing_example():
    """批量处理示例"""
    
    experiment_files = [
        "data/exp1.h5",
        "data/exp2.h5", 
        "data/exp3.h5"
    ]
    
    for i, exp_file in enumerate(experiment_files):
        try:
            plotter = OECTPlotter(exp_file)
            
            # 为每个实验创建概览图
            plotter.plot_transfer_evolution(save_path=f"exp_{i}_transfer.png")
            plotter.plot_transient_all(save_path=f"exp_{i}_transient.png")
            
            print(f"处理完成: {exp_file}")
            
        except Exception as e:
            print(f"处理失败 {exp_file}: {e}")

if __name__ == "__main__":
    # 根据需要运行不同的示例
    
    # 完整示例 (需要有效的实验文件)
    # example_usage()
    
    # 快速示例
    # quick_examples()
    
    # 批量处理示例
    # batch_processing_example()
    
    print("请根据实际情况取消注释相应的示例函数")