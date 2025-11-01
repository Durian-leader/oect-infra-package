"""
Phase 2 功能演示

展示所有新功能：
- 配置文件加载
- Transient 提取器
- 并行执行
- 多层缓存
- Transform 系统
"""

import sys
from pathlib import Path
import time

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infra.features_v2 import FeatureSet
from infra.catalog import UnifiedExperimentManager
from infra.logger_config import get_module_logger

# 注册提取器
import infra.features_v2.extractors.transfer  # noqa
import infra.features_v2.extractors.transient  # noqa

logger = get_module_logger()


def demo_config_loading():
    """演示 1: 从配置文件加载特征"""
    print("\n" + "=" * 70)
    print("演示 1: 从配置文件加载特征")
    print("=" * 70)

    manager = UnifiedExperimentManager('../infra/catalog_config.yaml')
    experiments = manager.search(chip_id="#20250804008", device_id="3")

    if not experiments:
        print("❌ 未找到实验")
        return None

    exp = experiments[0]
    print(f"✅ 加载实验: {exp.chip_id}-{exp.device_id}")

    # 从配置文件加载
    config_path = '../infra/features_v2/config/templates/v2_transfer_basic.yaml'
    print(f"\n从配置文件加载: {config_path}")

    start = time.time()
    features = FeatureSet.from_config(config_path, experiment=exp)
    print(f"配置解析耗时: {(time.time() - start) * 1000:.2f}ms")

    print(f"\n✅ 已加载 {len(features.graph.nodes)} 个特征")
    print("\n计算图:")
    print(features.visualize_graph())

    return features, exp


def demo_transient_extractors():
    """演示 2: Transient 提取器"""
    print("\n" + "=" * 70)
    print("演示 2: Transient 特征提取")
    print("=" * 70)

    manager = UnifiedExperimentManager('../infra/catalog_config.yaml')
    experiments = manager.search(chip_id="#20250804008", device_id="3")

    if not experiments:
        print("❌ 未找到实验")
        return

    exp = experiments[0]

    # 检查是否有 transient 数据
    if not exp.has_transient_data():
        print("⚠️  该实验没有 Transient 数据，跳过演示")
        return

    features = FeatureSet(experiment=exp)

    # 添加 Transient 特征
    features.add(
        'transient_peak',
        extractor='transient.peak_current',
        input='transient',
        params={'use_abs': True},
    )

    features.add(
        'transient_decay',
        extractor='transient.decay_time',
        input='transient',
        params={'method': 'exponential'},
    )

    # 如果数据量小，可以尝试 cycles
    # features.add(
    #     'transient_cycles',
    #     extractor='transient.cycles',
    #     input='transient',
    #     params={'n_cycles': 50, 'method': 'peak_detection'},
    # )

    print(f"✅ 已添加 {len(features.graph.nodes)} 个 Transient 特征")

    # 计算
    start = time.time()
    result = features.compute()
    elapsed = (time.time() - start) * 1000

    print(f"\n计算完成，耗时 {elapsed:.2f}ms")

    for name, array in result.items():
        print(f"  {name:20s}: shape={array.shape}, 有效值={np.sum(~np.isnan(array))}")


def demo_parallel_execution(features, exp):
    """演示 3: 并行执行"""
    print("\n" + "=" * 70)
    print("演示 3: 并行执行（对比串行 vs 并行）")
    print("=" * 70)

    from infra.features_v2.core.executor import Executor
    from infra.features_v2.performance.parallel import ParallelExecutor
    from infra.features_v2.extractors import get_extractor

    # 准备提取器实例
    extractor_instances = {}
    for node_name, node in features.graph.nodes.items():
        if node.is_extractor:
            extractor_instances[node.func] = get_extractor(node.func, node.params)

    # 串行执行
    print("\n1. 串行执行...")
    executor_serial = Executor(
        compute_graph=features.graph,
        data_loaders=features.data_loaders,
        extractor_registry=extractor_instances,
    )

    start = time.time()
    context_serial = executor_serial.execute()
    time_serial = (time.time() - start) * 1000

    print(f"   串行耗时: {time_serial:.2f}ms")

    # 并行执行
    print("\n2. 并行执行...")
    executor_parallel = ParallelExecutor(
        compute_graph=features.graph,
        data_loaders=features.data_loaders,
        extractor_registry=extractor_instances,
        n_workers=4,
    )

    start = time.time()
    context_parallel = executor_parallel.execute()
    time_parallel = (time.time() - start) * 1000

    print(f"   并行耗时: {time_parallel:.2f}ms")

    # 对比
    speedup = time_serial / time_parallel if time_parallel > 0 else 1.0
    print(f"\n✅ 加速比: {speedup:.2f}x")
    print(f"   节省时间: {time_serial - time_parallel:.2f}ms ({(1 - 1/speedup) * 100:.1f}%)")


def demo_cache():
    """演示 4: 多层缓存"""
    print("\n" + "=" * 70)
    print("演示 4: 多层缓存系统")
    print("=" * 70)

    from infra.features_v2.performance.cache import MultiLevelCache
    import numpy as np

    # 创建缓存
    cache = MultiLevelCache(
        memory_size_mb=256,
        disk_cache_dir='output/.cache',
        enable_disk=True,
    )

    # 生成测试数据
    test_data = {
        f'feature_{i}': np.random.rand(5000).astype(np.float32)
        for i in range(10)
    }

    # 写入缓存
    print("\n1. 写入缓存...")
    for key, value in test_data.items():
        cache.put(key, value)

    print("   ✅ 已写入 10 个特征到缓存")

    # 读取缓存（内存）
    print("\n2. 读取缓存（内存）...")
    start = time.time()
    for key in test_data.keys():
        cached = cache.get(key)
        assert cached is not None
    time_memory = (time.time() - start) * 1000

    print(f"   内存读取耗时: {time_memory:.2f}ms")

    # 清空内存缓存
    cache.clear_memory()

    # 读取缓存（磁盘）
    print("\n3. 读取缓存（磁盘）...")
    start = time.time()
    for key in test_data.keys():
        cached = cache.get(key)
        assert cached is not None
    time_disk = (time.time() - start) * 1000

    print(f"   磁盘读取耗时: {time_disk:.2f}ms")

    # 统计信息
    stats = cache.get_statistics()
    print(f"\n✅ 缓存统计:")
    print(f"   内存: {stats['memory']['size']}/{stats['memory']['maxsize']} 项")
    print(f"   命中率: {stats['memory']['hit_rate']:.1%}")
    print(f"   磁盘: {stats['disk']['count']} 个文件, {stats['disk']['size_mb']:.2f} MB")

    # 清理
    cache.clear_all()


def demo_transforms():
    """演示 5: Transform 系统"""
    print("\n" + "=" * 70)
    print("演示 5: Transform 系统（归一化和过滤）")
    print("=" * 70)

    from infra.features_v2.transforms import Normalize, Filter
    import numpy as np

    # 生成测试数据（包含异常值）
    data = np.random.randn(1000) * 10 + 50
    data[100] = 1000  # 异常值
    data[500] = -500  # 异常值

    print(f"\n原始数据: 均值={data.mean():.2f}, 标准差={data.std():.2f}")
    print(f"          范围=[{data.min():.2f}, {data.max():.2f}]")

    # 1. 归一化
    print("\n1. 归一化")
    normalizer = Normalize(method='minmax')
    normalized = normalizer(data)
    print(f"   MinMax归一化: 范围=[{normalized.min():.4f}, {normalized.max():.4f}]")

    normalizer_z = Normalize(method='zscore')
    z_normalized = normalizer_z(data)
    print(f"   Z-score归一化: 均值={z_normalized.mean():.4f}, 标准差={z_normalized.std():.4f}")

    # 2. 过滤
    print("\n2. 过滤异常值")
    filter_obj = Filter(remove_outliers=True, outlier_method='iqr', outlier_threshold=1.5)
    filtered = filter_obj(data)
    valid_count = np.sum(~np.isnan(filtered))
    print(f"   过滤后: {valid_count}/{len(data)} 个有效值 ({valid_count/len(data)*100:.1f}%)")
    print(f"   过滤数据: 范围=[{np.nanmin(filtered):.2f}, {np.nanmax(filtered):.2f}]")


def main():
    """主函数"""
    print("=" * 70)
    print("Features V2 - Phase 2 功能演示")
    print("=" * 70)

    try:
        # 演示 1: 配置文件加载
        features, exp = demo_config_loading()

        if features and exp:
            # 演示 3: 并行执行（需要先有 features）
            demo_parallel_execution(features, exp)

        # 演示 2: Transient 提取器
        demo_transient_extractors()

        # 演示 4: 多层缓存
        demo_cache()

        # 演示 5: Transform 系统
        demo_transforms()

        print("\n" + "=" * 70)
        print("✅ 所有演示完成！")
        print("=" * 70)

    except Exception as e:
        logger.error(f"演示失败: {e}", exc_info=True)
        print(f"\n❌ 演示失败: {e}")


if __name__ == '__main__':
    import numpy as np  # noqa: 放在这里避免演示函数报错

    main()
