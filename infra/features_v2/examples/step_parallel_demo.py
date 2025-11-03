"""
Step 级并行架构演示脚本

演示如何使用 StepLevelParallelExecutor 实现最大并行度的特征提取

性能对比：
- 旧架构（实验级并行）：80实验 → ~42秒（48核）
- 新架构（Step 级并行）：400 step 任务 → ~10秒（48核）预期

作者: Claude Code
日期: 2025-11-04
"""

import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import time
from infra.catalog import UnifiedExperimentManager
from infra.logger_config import get_module_logger

logger = get_module_logger()


def test_step_parallel_basic():
    """基础测试：单个实验，多个特征"""
    print("="*80)
    print("测试 1: 单个实验 - Transfer 特征提取（Step 级并行）")
    print("="*80)

    # 初始化管理器
    manager = UnifiedExperimentManager('catalog_config.yaml')

    # 获取一个实验
    exp = manager.get_experiment(chip_id="#20250804008", device_id="3")

    if not exp:
        print("❌ 未找到实验")
        return

    print(f"✓ 加载实验: {exp.id} ({exp.chip_id} Device {exp.device_id})")
    print(f"  Steps: {exp.transfer_steps}")

    # 使用 Step 级并行提取
    start = time.time()

    result = manager.batch_extract_features_v2(
        experiments=[exp],
        feature_config='v2_transfer_basic',
        execution_mode='step',  # ← Step 级并行
        n_workers=4,  # 小规模测试用 4 个worker
        force_recompute=True
    )

    elapsed = time.time() - start

    print(f"\n✅ 提取完成:")
    print(f"  成功: {len(result['successful'])}")
    print(f"  失败: {len(result['failed'])}")
    print(f"  总耗时: {elapsed:.2f}秒")

    # 验证结果
    exp_reloaded = manager.get_experiment(exp_id=exp.id)
    if exp_reloaded.has_v2_features():
        print(f"  ✓ V2 特征已保存")
        df = exp_reloaded.get_v2_feature_dataframe()
        print(f"  ✓ 特征数: {len(df.columns) - 1}")  # -1 for step_index
        print(f"  ✓ 行数: {len(df)}")
    else:
        print(f"  ❌ V2 特征未保存")


def test_step_parallel_batch():
    """批量测试：多个实验，多个特征"""
    print("\n" + "="*80)
    print("测试 2: 批量实验 - Transfer 特征提取（Step 级并行）")
    print("="*80)

    # 初始化管理器
    manager = UnifiedExperimentManager('catalog_config.yaml')

    # 获取多个实验
    experiments = manager.search(chip_id="#20250804008")

    if not experiments:
        print("❌ 未找到实验")
        return

    print(f"✓ 加载实验: {len(experiments)} 个")

    # 计算任务数
    total_steps = sum(exp.transfer_steps for exp in experiments)
    n_features = 5  # v2_transfer_basic 的特征数
    total_tasks = total_steps * n_features

    print(f"  总 steps: {total_steps}")
    print(f"  总任务数: {total_tasks} (steps × features)")

    # Step 级并行提取
    start = time.time()

    result = manager.batch_extract_features_v2(
        experiments=experiments,
        feature_config='v2_transfer_basic',
        execution_mode='step',  # ← Step 级并行
        n_workers=8,  # 使用 8 个worker测试
        force_recompute=True
    )

    elapsed = time.time() - start

    print(f"\n✅ Step 级并行提取完成:")
    print(f"  成功: {len(result['successful'])}")
    print(f"  失败: {len(result['failed'])}")
    print(f"  总耗时: {elapsed:.2f}秒")
    print(f"  平均每实验: {elapsed/len(experiments):.2f}秒")
    print(f"  平均每任务: {elapsed/total_tasks*1000:.2f}ms")


def test_experiment_parallel_comparison():
    """对比测试：Step 级 vs 实验级"""
    print("\n" + "="*80)
    print("测试 3: 性能对比 - Step 级 vs 实验级并行")
    print("="*80)

    # 初始化管理器
    manager = UnifiedExperimentManager('catalog_config.yaml')

    # 获取测试实验（5个）
    experiments = manager.search(chip_id="#20250804008")[:5]

    if len(experiments) < 5:
        print("❌ 测试实验不足 5 个")
        return

    print(f"✓ 测试实验: {len(experiments)} 个")

    # 测试 1: 实验级并行
    print("\n方式 1: 实验级并行（旧架构）")
    start1 = time.time()

    result1 = manager.batch_extract_features_v2(
        experiments=experiments,
        feature_config='v2_transfer_basic',
        execution_mode='experiment',  # ← 实验级并行
        n_workers=5,
        force_recompute=True
    )

    elapsed1 = time.time() - start1
    print(f"  耗时: {elapsed1:.2f}秒")

    # 测试 2: Step 级并行
    print("\n方式 2: Step 级并行（新架构）")
    start2 = time.time()

    result2 = manager.batch_extract_features_v2(
        experiments=experiments,
        feature_config='v2_transfer_basic',
        execution_mode='step',  # ← Step 级并行
        n_workers=5,
        force_recompute=True
    )

    elapsed2 = time.time() - start2
    print(f"  耗时: {elapsed2:.2f}秒")

    # 对比
    print(f"\n📊 性能对比:")
    print(f"  实验级并行: {elapsed1:.2f}秒")
    print(f"  Step 级并行: {elapsed2:.2f}秒")
    print(f"  提升倍数: {elapsed1/elapsed2:.2f}x")


def test_transient_autotau():
    """测试 Transient 特征（包括 AutoTau）"""
    print("\n" + "="*80)
    print("测试 4: Transient 特征提取（Step 级并行）")
    print("="*80)

    # 初始化管理器
    manager = UnifiedExperimentManager('catalog_config.yaml')

    # 获取有 transient 数据的实验
    experiments = manager.search(chip_id="#20250804008")

    # 过滤出有 transient 数据的实验
    transient_exps = [exp for exp in experiments if exp.transient_steps > 0]

    if not transient_exps:
        print("❌ 未找到包含 Transient 数据的实验")
        return

    print(f"✓ 找到 {len(transient_exps)} 个包含 Transient 数据的实验")

    # 使用 transient 配置
    print("\n使用配置: transient_tau（包含 AutoTau 特征）")

    start = time.time()

    result = manager.batch_extract_features_v2(
        experiments=transient_exps[:2],  # 先测试2个
        feature_config='transient_tau',  # 假设有这个配置
        execution_mode='step',
        n_workers=8,
        force_recompute=True
    )

    elapsed = time.time() - start

    print(f"\n✅ Transient 特征提取完成:")
    print(f"  成功: {len(result['successful'])}")
    print(f"  失败: {len(result['failed'])}")
    print(f"  总耗时: {elapsed:.2f}秒")


if __name__ == '__main__':
    print("="*80)
    print("Step 级并行架构 - 演示与测试")
    print("="*80)

    # 运行测试
    tests = [
        ('基础测试', test_step_parallel_basic),
        ('批量测试', test_step_parallel_batch),
        ('性能对比', test_experiment_parallel_comparison),
        # ('Transient测试', test_transient_autotau),  # 需要 AutoTau 安装
    ]

    for test_name, test_func in tests:
        try:
            test_func()
        except Exception as e:
            print(f"\n❌ {test_name} 失败: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "="*80)
    print("测试完成")
    print("="*80)
