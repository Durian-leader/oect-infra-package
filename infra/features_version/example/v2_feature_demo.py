"""
v2_feature 使用示例

演示如何使用 v2_feature 提取 transient 数据的 tau_on 和 tau_off 特征。

该脚本展示：
1. 单个文件的特征提取
2. 批量文件的特征提取
3. 自定义参数设置
4. 多核并行处理

使用前确保：
- 已安装 autotau 包：pip install autotau
- 有包含 transient 数据的原始 HDF5 文件
"""

import sys
from pathlib import Path

# 添加 infra 包到路径（如果需要）
# sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from infra.features_version import v2_feature, batch_create_features
from infra.logger_config import get_module_logger

logger = get_module_logger()


def example_single_file():
    """示例1：单个文件的 tau 特征提取"""
    print("\n" + "=" * 60)
    print("示例1：单个文件的 tau 特征提取")
    print("=" * 60)

    # 原始数据文件路径（包含 transient 数据）
    raw_file = "path/to/your/raw-test_*.h5"

    # 输出目录
    output_dir = "data/features"

    # 提取特征（使用自动估计的周期）
    try:
        feature_file = v2_feature(
            raw_file_path=raw_file,
            output_dir=output_dir,
            period=None,  # 自动估计周期
            max_workers=4,  # 使用4个工作进程
            show_progress=False
        )
        print(f"✅ 特征文件已创建: {feature_file}")
    except Exception as e:
        print(f"❌ 提取失败: {e}")


def example_with_custom_period():
    """示例2：指定周期的特征提取"""
    print("\n" + "=" * 60)
    print("示例2：指定周期的特征提取")
    print("=" * 60)

    raw_file = "path/to/your/raw-test_*.h5"
    output_dir = "data/features"

    # 如果你知道实验的确切周期，可以指定它
    period = 10.0  # 10秒的周期

    try:
        feature_file = v2_feature(
            raw_file_path=raw_file,
            output_dir=output_dir,
            period=period,  # 指定周期
            max_workers=8,  # 使用8个工作进程
            window_scalar_min=0.2,  # 自定义窗口参数
            window_scalar_max=0.35,
            window_points_step=5,
            show_progress=True  # 显示进度
        )
        print(f"✅ 特征文件已创建: {feature_file}")
    except Exception as e:
        print(f"❌ 提取失败: {e}")


def example_batch_processing():
    """示例3：批量文件处理"""
    print("\n" + "=" * 60)
    print("示例3：批量文件处理")
    print("=" * 60)

    source_directory = "data/raw"
    output_dir = "data/features"

    # 定义处理函数（带自定义参数）
    def processing_func(raw_file_path: str, out_dir: str) -> str:
        """自定义的处理函数"""
        return v2_feature(
            raw_file_path=raw_file_path,
            output_dir=out_dir,
            period=None,  # 自动估计
            max_workers=4,
            show_progress=False
        )

    # 批量处理
    try:
        batch_create_features(
            source_directory=source_directory,
            output_dir=output_dir,
            processing_func=processing_func
        )
        print("✅ 批量处理完成")
    except Exception as e:
        print(f"❌ 批量处理失败: {e}")


def example_read_features():
    """示例4：读取提取的特征"""
    print("\n" + "=" * 60)
    print("示例4：读取提取的特征")
    print("=" * 60)

    from infra.features import FeatureRepository

    feature_file = "data/features/your-feature-file.h5"

    try:
        repo = FeatureRepository(feature_file)

        # 读取单个特征
        tau_on = repo.get_feature('tau_on', data_type='transient')
        tau_off = repo.get_feature('tau_off', data_type='transient')

        print(f"tau_on shape: {tau_on.shape if tau_on is not None else 'N/A'}")
        print(f"tau_off shape: {tau_off.shape if tau_off is not None else 'N/A'}")

        if tau_on is not None:
            print(f"tau_on range: [{tau_on.min():.6f}, {tau_on.max():.6f}]s")
        if tau_off is not None:
            print(f"tau_off range: [{tau_off.min():.6f}, {tau_off.max():.6f}]s")

        # 读取版本矩阵
        from infra.features import VersionManager
        version_mgr = VersionManager(feature_file)

        version_matrix = version_mgr.get_version_matrix('v2', data_type='transient')
        if version_matrix is not None:
            print(f"Version matrix shape: {version_matrix.shape}")

    except Exception as e:
        print(f"❌ 读取失败: {e}")


def example_compare_with_v1():
    """示例5：V1 和 V2 特征的比较"""
    print("\n" + "=" * 60)
    print("示例5：V1 (Transfer) 和 V2 (Transient) 特征的比较")
    print("=" * 60)

    from infra.features_version import v1_feature

    raw_file = "path/to/your/raw-test_*.h5"
    output_dir = "data/features"

    try:
        # V1: Transfer features
        print("提取 V1 特征（Transfer）...")
        feature_file_v1 = v1_feature(
            raw_file_path=raw_file,
            output_dir=output_dir
        )
        print(f"✅ V1 特征: {feature_file_v1}")

        # V2: Transient features
        print("\n提取 V2 特征（Transient）...")
        feature_file_v2 = v2_feature(
            raw_file_path=raw_file,
            output_dir=output_dir,
            max_workers=4
        )
        print(f"✅ V2 特征: {feature_file_v2}")

        # 注意：V1 和 V2 会写入同一个特征文件的不同 data_type
        # - V1 写入 data_type='transfer'
        # - V2 写入 data_type='transient'

    except Exception as e:
        print(f"❌ 提取失败: {e}")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("v2_feature 使用示例")
    print("=" * 60)

    # 运行示例（根据需要取消注释）

    # 示例1：单个文件
    # example_single_file()

    # 示例2：自定义周期
    # example_with_custom_period()

    # 示例3：批量处理
    # example_batch_processing()

    # 示例4：读取特征
    # example_read_features()

    # 示例5：V1 和 V2 比较
    # example_compare_with_v1()

    print("\n" + "=" * 60)
    print("请修改文件路径后运行相应的示例")
    print("=" * 60)
