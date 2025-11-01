"""
增量式特征工程工作流演示

展示如何使用 Features V2 的增量计算和配置固化功能：
1. 首次探索：定义基础特征 → 计算 → 固化
2. 增量扩展：加载配置 → 添加派生特征 → 增量计算 → 再次固化
3. 缓存验证：自动检测源文件变化

依赖：需要 UnifiedExperimentManager 和真实实验数据
"""

from pathlib import Path
import sys

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from infra.features_v2 import FeatureSet
from infra.catalog import UnifiedExperimentManager
from infra.logger_config import get_module_logger

logger = get_module_logger()


def demo_stage_1_initial_exploration():
    """阶段 1：首次探索 - 定义基础特征"""
    print("\n" + "=" * 80)
    print("阶段 1：首次探索 - 定义基础特征")
    print("=" * 80)

    # 初始化管理器
    manager = UnifiedExperimentManager('catalog_config.yaml')

    # 获取实验（请替换为实际的 chip_id 和 device_id）
    exp = manager.get_experiment(chip_id="#20250804008", device_id="3")

    if not exp:
        print("❌ 未找到实验，请检查 chip_id 和 device_id")
        return None

    print(f"✓ 加载实验: {exp.chip_id}-{exp.device_id}")

    # 创建特征集
    features = FeatureSet(
        unified_experiment=exp,
        config_name='demo_incremental',
        config_version='1.0'
    )

    # 添加基础特征
    print("\n📋 定义基础特征...")
    features.add('gm_max', extractor='transfer.gm_max', input='transfer',
                 params={'direction': 'forward', 'device_type': 'N'})
    features.add('Von', extractor='transfer.Von', input='transfer',
                 params={'direction': 'forward', 'device_type': 'N'})
    features.add('absI_max', extractor='transfer.absI_max', input='transfer',
                 params={'device_type': 'N'})

    print(f"  ✓ 添加了 {len(features.graph.nodes)} 个特征")

    # 计算特征（可能需要较长时间）
    print("\n⚙️ 开始计算特征...")
    result = features.compute()

    print(f"\n✅ 计算完成:")
    print(f"  - 特征数量: {len(result)}")
    stats = features.get_statistics()
    print(f"  - 总耗时: {stats['total_time_ms']:.2f}ms")

    # 固化配置和数据
    print("\n💾 固化配置和数据...")
    save_result = features.save_as_config(
        config_name='demo_incremental',
        save_parquet=True,
        config_dir='user',
        description="增量特征工程演示 - 基础特征"
    )

    print(f"  ✓ 配置文件: {save_result['config_file']}")
    print(f"  ✓ Parquet 文件: {save_result['parquet_file']}")
    print(f"  ✓ 配置版本: {save_result['config_version']}")

    return exp


def demo_stage_2_incremental_extension(exp):
    """阶段 2：增量扩展 - 添加派生特征"""
    print("\n" + "=" * 80)
    print("阶段 2：增量扩展 - 添加派生特征")
    print("=" * 80)

    # 加载已固化的配置
    config_path = Path.home() / '.my_features' / 'demo_incremental.yaml'

    if not config_path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        return

    print(f"✓ 加载配置: {config_path}")

    features_v2 = FeatureSet.from_config(
        str(config_path),
        unified_experiment=exp
    )

    # 添加派生特征
    print("\n📋 添加派生特征...")
    features_v2.add(
        'gm_normalized',
        func=lambda gm: (gm - gm.mean()) / gm.std(),
        input='gm_max',
        output_shape=('n_steps',)
    )
    features_v2.add(
        'gm_to_current_ratio',
        func=lambda gm, i: gm / (i + 1e-10),
        input=['gm_max', 'absI_max'],
        output_shape=('n_steps',)
    )

    print(f"  ✓ 当前特征总数: {len(features_v2.graph.nodes)}")

    # 增量计算（基础特征从缓存读取）
    print("\n⚙️ 增量计算...")
    result_v2 = features_v2.compute()

    print(f"\n✅ 计算完成:")
    print(f"  - 特征数量: {len(result_v2)}")
    stats = features_v2.get_statistics()
    print(f"  - 总耗时: {stats['total_time_ms']:.2f}ms")
    print(f"  - 缓存命中: {stats['cache_hits']}")
    print(f"  - 缓存未命中: {stats['cache_misses']}")

    # 增量保存（合并到原配置）
    print("\n💾 增量保存...")
    save_result = features_v2.save_as_config(
        'demo_incremental',
        append=True,  # ✅ 智能合并
        save_parquet=True,
        config_dir='user'
    )

    print(f"  ✓ 新增特征: {save_result['features_added']}")
    print(f"  ✓ 配置版本: {save_result['config_version']}")


def demo_stage_3_cache_validation(exp):
    """阶段 3：缓存验证 - 演示自动失效检测"""
    print("\n" + "=" * 80)
    print("阶段 3：缓存验证 - 演示自动失效检测")
    print("=" * 80)

    config_path = Path.home() / '.my_features' / 'demo_incremental.yaml'

    # 再次加载配置
    features_v3 = FeatureSet.from_config(
        str(config_path),
        unified_experiment=exp
    )

    print(f"✓ 加载配置: {config_path.name}")
    print(f"  - 特征数量: {len(features_v3.graph.nodes)}")

    # 计算（应该全部从缓存读取）
    print("\n⚙️ 计算（应该全部命中缓存）...")
    result_v3 = features_v3.compute()

    stats = features_v3.get_statistics()
    print(f"\n✅ 缓存性能:")
    print(f"  - 缓存命中: {stats['cache_hits']}")
    print(f"  - 缓存未命中: {stats['cache_misses']}")
    cache_hit_rate = stats['cache_hits'] / (stats['cache_hits'] + stats['cache_misses'])
    print(f"  - 命中率: {cache_hit_rate:.1%}")
    print(f"  - 耗时: {stats['total_time_ms']:.2f}ms")


def main():
    """主函数"""
    print("""
╔══════════════════════════════════════════════════════════════════════════╗
║                Features V2 增量式特征工程演示                              ║
║                                                                            ║
║  本示例演示完整的增量式特征工程工作流：                                    ║
║  1️⃣  首次探索：定义基础特征 → 计算 → 固化                                ║
║  2️⃣  增量扩展：加载配置 → 添加派生特征 → 增量计算 → 再次固化            ║
║  3️⃣  缓存验证：自动检测源文件变化                                        ║
╚══════════════════════════════════════════════════════════════════════════╝
    """)

    try:
        # 阶段 1：首次探索
        exp = demo_stage_1_initial_exploration()

        if exp:
            # 阶段 2：增量扩展
            demo_stage_2_incremental_extension(exp)

            # 阶段 3：缓存验证
            demo_stage_3_cache_validation(exp)

        print("\n" + "=" * 80)
        print("✅ 演示完成！")
        print("=" * 80)
        print("\n💡 提示:")
        print("  - 配置文件保存在: ~/.my_features/demo_incremental.yaml")
        print("  - Parquet 文件保存在: ~/.my_features/data/features_v2/")
        print("  - 你可以修改 chip_id 和 device_id 来测试其他实验")

    except Exception as e:
        logger.error(f"演示失败: {e}", exc_info=True)
        print(f"\n❌ 演示失败: {e}")
        print("\n请检查:")
        print("  1. catalog_config.yaml 是否正确配置")
        print("  2. 实验数据是否存在 (chip_id=#20250804008, device_id=3)")
        print("  3. 数据库是否包含该实验的索引")


if __name__ == '__main__':
    main()
