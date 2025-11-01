"""
Features V2 与 Catalog 集成演示

展示如何通过 catalog 使用 features_v2
"""

import sys
from pathlib import Path

# 添加项目根目录
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infra.catalog import UnifiedExperimentManager


def demo_single_experiment():
    """演示 1: 单实验交互式提取"""
    print("=" * 70)
    print("演示 1: 单实验交互式提取")
    print("=" * 70)

    # 初始化管理器
    manager = UnifiedExperimentManager('../infra/catalog_config.yaml')

    # 获取实验
    exp = manager.get_experiment(chip_id="#20250804008", device_id="3")

    if not exp:
        print("❌ 未找到实验")
        return

    print(f"✅ 加载实验: {exp.chip_id}-{exp.device_id}")

    # 检查是否已有 V2 特征
    if exp.has_v2_features():
        print("  ⚠️  实验已有 V2 特征")
        metadata = exp.get_v2_features_metadata()
        print(f"  配置: {metadata.get('configs_used')}")
        print(f"  特征数: {metadata.get('feature_count')}")
        print(f"  最后计算: {metadata.get('last_computed')}")

    # 使用配置文件提取
    print("\n使用配置文件 'v2_transfer_basic' 提取特征...")

    result_df = exp.extract_features_v2(
        'v2_transfer_basic',
        output_format='dataframe'
    )

    print(f"\n✅ 提取完成！")
    print(f"特征数量: {len(result_df.columns) - 1}")  # 减去 step_index
    print(f"步骤数量: {len(result_df)}")
    print("\n前5行数据:")
    print(result_df.head())

    # 保存为 Parquet
    print("\n保存为 Parquet 文件...")
    parquet_path = exp.extract_features_v2(
        'v2_transfer_basic',
        output_format='parquet'
    )
    print(f"✅ 已保存: {parquet_path}")


def demo_batch_extraction():
    """演示 2: 批量自动化处理"""
    print("\n" + "=" * 70)
    print("演示 2: 批量自动化处理")
    print("=" * 70)

    manager = UnifiedExperimentManager('../infra/catalog_config.yaml')

    # 搜索实验
    experiments = manager.search(chip_id="#20250804008")
    print(f"找到 {len(experiments)} 个实验")

    if not experiments:
        print("❌ 未找到实验")
        return

    # 批量提取（限制数量以加快演示）
    demo_experiments = experiments[:3]  # 只取前 3 个
    print(f"\n使用 {len(demo_experiments)} 个实验进行演示...")

    result = manager.batch_extract_features_v2(
        experiments=demo_experiments,
        feature_config='v2_quick_analysis',  # 使用快速配置
        save_format='parquet',
        n_workers=2,  # 并行处理
        force_recompute=False,
    )

    print(f"\n✅ 批量提取完成！")
    print(f"成功: {len(result['successful'])}")
    print(f"失败: {len(result['failed'])}")
    print(f"跳过: {len(result['skipped'])}")
    print(f"总耗时: {result['total_time_ms'] / 1000:.2f}s")

    if result['timings']:
        avg_time = sum(result['timings'].values()) / len(result['timings'])
        print(f"平均耗时/实验: {avg_time / 1000:.2f}s")


def demo_config_comparison():
    """演示 3: 不同配置的对比"""
    print("\n" + "=" * 70)
    print("演示 3: 不同配置的对比")
    print("=" * 70)

    manager = UnifiedExperimentManager('../infra/catalog_config.yaml')
    exp = manager.get_experiment(chip_id="#20250804008", device_id="3")

    if not exp:
        print("❌ 未找到实验")
        return

    configs = [
        ('v2_quick_analysis', '快速分析'),
        ('v2_transfer_basic', '基础特征'),
        ('v2_ml_ready', 'ML 就绪'),
    ]

    print(f"对比 {len(configs)} 种配置...")
    print()

    for config_name, desc in configs:
        try:
            result_df = exp.extract_features_v2(
                config_name,
                output_format='dataframe',
                save_metadata=False,  # 不保存元数据（演示用）
            )

            print(f"{desc:12s} ({config_name:20s}): {len(result_df.columns) - 1} 个特征")
        except FileNotFoundError:
            print(f"{desc:12s} ({config_name:20s}): ❌ 配置文件不存在")
        except Exception as e:
            print(f"{desc:12s} ({config_name:20s}): ❌ 提取失败 - {e}")


def demo_inline_config():
    """演示 4: 使用内联配置"""
    print("\n" + "=" * 70)
    print("演示 4: 使用内联配置（自定义特征）")
    print("=" * 70)

    manager = UnifiedExperimentManager('../infra/catalog_config.yaml')
    exp = manager.get_experiment(chip_id="#20250804008", device_id="3")

    if not exp:
        print("❌ 未找到实验")
        return

    # 内联配置（字典）
    custom_config = {
        'gm_max': {
            'extractor': 'transfer.gm_max',
            'input': 'transfer',
            'params': {'direction': 'forward', 'device_type': 'N'},
        },
        'gm_normalized': {
            'func': 'lambda gm: (gm - gm.mean()) / gm.std()',
            'input': 'gm_max',
            'output_shape': ['n_steps'],
        },
    }

    print("使用内联配置提取 2 个特征...")

    result = exp.extract_features_v2(
        custom_config,
        output_format='dict',
        save_metadata=False,
    )

    print(f"\n✅ 提取完成！")
    for name, array in result.items():
        print(f"  {name:20s}: shape={array.shape}, 范围=[{array.min():.3e}, {array.max():.3e}]")


def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("Features V2 与 Catalog 集成演示")
    print("=" * 70)

    try:
        # 演示 1: 单实验
        demo_single_experiment()

        # 演示 2: 批量处理
        demo_batch_extraction()

        # 演示 3: 配置对比
        demo_config_comparison()

        # 演示 4: 内联配置
        demo_inline_config()

        print("\n" + "=" * 70)
        print("✅ 所有演示完成！")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ 演示失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
