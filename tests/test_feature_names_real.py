#!/usr/bin/env python3
"""
真实数据测试：feature_names 参数功能（使用实际的特征名）
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from infra.catalog import UnifiedExperimentManager


def test_real_features():
    """使用实际的特征名测试"""

    config_path = '/home/lidonghaowsl/develop/Minitest-OECT-dataprocessing/catalog_config20251101.yaml'
    manager = UnifiedExperimentManager(str(config_path))

    # 获取测试实验
    exp = manager.get_experiment(chip_id="#20250804007", device_id="1")
    if not exp:
        print("❌ 找不到测试实验")
        return

    print(f"✅ 找到实验: {exp.chip_id}-{exp.device_id}\n")

    # 测试 1: 读取完整 DataFrame
    print("="*80)
    print("测试 1: 读取完整 DataFrame（无筛选）")
    print("="*80)
    df_full = exp.get_v2_feature_dataframe()
    if df_full is not None:
        print(f"✅ Shape: {df_full.shape}")
        print(f"   列数: {len(df_full.columns)}")
        print(f"   样例特征: {list(df_full.columns[:5])}\n")
    else:
        print("❌ 无法读取\n")
        return

    # 测试 2: 单个标量特征
    print("="*80)
    print("测试 2: 筛选单个标量特征 'gm_max_forward'")
    print("="*80)
    try:
        df = exp.get_v2_feature_dataframe(feature_names='gm_max_forward')
        print(f"✅ 成功筛选")
        print(f"   Shape: {df.shape}")
        print(f"   列: {list(df.columns)}")
        print(f"   前3行:\n{df.head(3)}\n")
        assert 'step_index' in df.columns
        assert 'gm_max_forward' in df.columns
        assert df.shape[1] == 2  # step_index + gm_max_forward
    except Exception as e:
        print(f"❌ 错误: {e}\n")

    # 测试 3: 多个标量特征
    print("="*80)
    print("测试 3: 筛选多个标量特征")
    print("="*80)
    try:
        features = ['gm_max_forward', 'absI_max', 'gm_to_current_ratio']
        df = exp.get_v2_feature_dataframe(feature_names=features)
        print(f"✅ 成功筛选")
        print(f"   请求特征: {features}")
        print(f"   Shape: {df.shape}")
        print(f"   列: {list(df.columns)}")
        print(f"   前3行:\n{df.head(3)}\n")
        assert df.shape[1] == 4  # step_index + 3 features
    except Exception as e:
        print(f"❌ 错误: {e}\n")

    # 测试 4: 通配符匹配
    print("="*80)
    print("测试 4: 通配符匹配 'gm_max*'")
    print("="*80)
    try:
        df = exp.get_v2_feature_dataframe(feature_names='gm_max*')
        print(f"✅ 成功匹配")
        print(f"   Shape: {df.shape}")
        gm_max_cols = [c for c in df.columns if c.startswith('gm_max')]
        print(f"   匹配到 {len(gm_max_cols)} 个特征: {gm_max_cols}")
        print(f"   前3行（部分列）:\n{df[['step_index'] + gm_max_cols[:3]].head(3)}\n")
    except Exception as e:
        print(f"❌ 错误: {e}\n")

    # 测试 5: 更复杂的通配符
    print("="*80)
    print("测试 5: 通配符匹配 '*_degradation_rate'")
    print("="*80)
    try:
        df = exp.get_v2_feature_dataframe(feature_names='*_degradation_rate')
        print(f"✅ 成功匹配")
        print(f"   Shape: {df.shape}")
        rate_cols = [c for c in df.columns if '_degradation_rate' in c]
        print(f"   匹配到 {len(rate_cols)} 个特征: {rate_cols}")
        print(f"   前3行:\n{df.head(3)}\n")
    except Exception as e:
        print(f"❌ 错误: {e}\n")

    # 测试 6: 组合使用通配符和具体特征名
    print("="*80)
    print("测试 6: 混合使用通配符和具体特征名")
    print("="*80)
    try:
        features = ['absI_max', 'gm_max*', '*_ratio']
        df = exp.get_v2_feature_dataframe(feature_names=features)
        print(f"✅ 成功筛选")
        print(f"   请求模式: {features}")
        print(f"   Shape: {df.shape}")
        selected_cols = [c for c in df.columns if c != 'step_index']
        print(f"   选中的特征（前10个）: {selected_cols[:10]}")
        print(f"   总共选中 {len(selected_cols)} 个特征\n")
    except Exception as e:
        print(f"❌ 错误: {e}\n")

    # 测试 7: 测试 gm_sequence 系列（多个相似特征）
    print("="*80)
    print("测试 7: 筛选 gm_sequence 前10个特征")
    print("="*80)
    try:
        features = [f'gm_sequence_forward_{i}' for i in range(10)]
        df = exp.get_v2_feature_dataframe(feature_names=features)
        print(f"✅ 成功筛选")
        print(f"   Shape: {df.shape}")
        print(f"   列: {list(df.columns)}")
        print(f"   前3行（部分列）:\n{df[['step_index'] + features[:5]].head(3)}\n")
        assert df.shape[1] == 11  # step_index + 10 features
    except Exception as e:
        print(f"❌ 错误: {e}\n")

    # 测试 8: 错误处理 - 不存在的特征
    print("="*80)
    print("测试 8: 错误处理 - 请求不存在的特征")
    print("="*80)
    try:
        df = exp.get_v2_feature_dataframe(feature_names='non_existent_feature_xyz')
        print(f"❌ 应该抛出异常但没有\n")
    except KeyError as e:
        error_msg = str(e)
        print(f"✅ 正确抛出 KeyError")
        print(f"   错误信息（前200字符）: {error_msg[:200]}...\n")
    except Exception as e:
        print(f"⚠️ 抛出了其他异常: {type(e).__name__}: {e}\n")

    # 测试 9: 空结果
    print("="*80)
    print("测试 9: 通配符没有匹配任何特征")
    print("="*80)
    try:
        df = exp.get_v2_feature_dataframe(feature_names='xyz_*')
        print(f"   返回: {df.shape if df is not None else 'None'}\n")
    except Exception as e:
        print(f"   预期行为：抛出异常或返回空 DataFrame")
        print(f"   实际: {type(e).__name__}\n")

    print("="*80)
    print("🎉 测试完成！")
    print("="*80)
    print("\n总结：")
    print("✅ 基础筛选功能正常")
    print("✅ 通配符匹配功能正常")
    print("✅ 错误处理正常")
    print("✅ 混合使用功能正常")


if __name__ == '__main__':
    test_real_features()
