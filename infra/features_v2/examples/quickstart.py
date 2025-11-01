"""
快速开始示例

演示 features_v2 的基本用法
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infra.features_v2 import FeatureSet
from infra.catalog import UnifiedExperimentManager
from infra.logger_config import get_module_logger

# 确保 transfer 提取器被注册
import infra.features_v2.extractors.transfer  # noqa

logger = get_module_logger()


def main():
    """基础示例：提取 Transfer 特征"""

    # 1. 加载实验数据
    print("=" * 60)
    print("特征工程系统 2.0 - 快速开始")
    print("=" * 60)

    # 使用 catalog 管理器获取实验
    manager = UnifiedExperimentManager('infra/catalog_config.yaml')

    # 获取一个实验（请根据实际情况修改 chip_id 和 device_id）
    experiments = manager.search(chip_id="#20250804008", device_id="3")

    if not experiments:
        print("❌ 未找到实验，请检查 catalog 配置")
        return

    exp = experiments[0]
    print(f"✅ 加载实验: {exp.chip_id}-{exp.device_id}")

    # 2. 创建特征集合
    print("\n" + "-" * 60)
    print("创建特征集合...")
    print("-" * 60)

    features = FeatureSet(experiment=exp)

    # 3. 添加特征（多种方式演示）

    # 方式 1: 使用注册的提取器
    features.add(
        'gm_max_forward',
        extractor='transfer.gm_max',
        input='transfer',
        params={'direction': 'forward', 'device_type': 'N'}
    )

    features.add(
        'gm_max_reverse',
        extractor='transfer.gm_max',
        input='transfer',
        params={'direction': 'reverse', 'device_type': 'N'}
    )

    features.add(
        'Von_forward',
        extractor='transfer.Von',
        input='transfer',
        params={'direction': 'forward', 'device_type': 'N'}
    )

    features.add(
        'absI_max',
        extractor='transfer.absI_max',
        input='transfer',
        params={'device_type': 'N'}
    )

    # 方式 2: 使用 lambda 创建派生特征
    features.add(
        'gm_max_normalized',
        func=lambda gm: (gm - gm.mean()) / gm.std(),
        input='gm_max_forward',
        output_shape=('n_steps',)
    )

    print(f"✅ 已添加 {len(features.graph.nodes)} 个特征")

    # 4. 可视化计算图
    print("\n" + "-" * 60)
    print("计算图结构:")
    print("-" * 60)
    print(features.visualize_graph())

    # 5. 执行计算
    print("\n" + "-" * 60)
    print("执行计算...")
    print("-" * 60)

    result = features.compute()

    # 6. 输出结果
    print("\n" + "-" * 60)
    print("计算结果:")
    print("-" * 60)

    for name, array in result.items():
        print(f"  {name:20s} : shape={array.shape}, dtype={array.dtype}")
        print(f"    {'':20s}   范围=[{array.min():.3e}, {array.max():.3e}]")

    # 7. 导出为 DataFrame
    print("\n" + "-" * 60)
    print("导出为 DataFrame:")
    print("-" * 60)

    df = features.to_dataframe()
    print(df.head(10))

    # 8. 保存到 Parquet
    output_path = 'output/quickstart_features.parquet'
    Path(output_path).parent.mkdir(exist_ok=True)
    features.to_parquet(output_path)

    print(f"\n✅ 已保存到 {output_path}")

    # 9. 性能统计
    print("\n" + "-" * 60)
    print("性能统计:")
    print("-" * 60)

    stats = features.get_statistics()
    print(f"  总特征数: {stats['total_features']}")
    print(f"  总耗时: {stats['total_time_ms']:.2f} ms")
    print(f"  平均耗时/特征: {stats['avg_time_per_feature_ms']:.2f} ms")
    print(f"  缓存命中: {stats['cache_hits']}")
    print(f"  缓存未命中: {stats['cache_misses']}")

    if stats['slowest_feature']:
        name, time_ms = stats['slowest_feature']
        print(f"  最慢特征: {name} ({time_ms:.2f} ms)")

    print("\n" + "=" * 60)
    print("✅ 快速开始示例完成！")
    print("=" * 60)


if __name__ == '__main__':
    main()
