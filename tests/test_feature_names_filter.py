#!/usr/bin/env python3
"""
测试 get_v2_feature_dataframe 的 feature_names 参数功能

测试场景：
1. 无参数调用（现有行为）
2. 标量特征筛选
3. 多维特征筛选
4. 多个特征筛选
5. 通配符匹配
6. 异常处理（不存在的特征）
"""

import sys
import os
from pathlib import Path

# 添加包路径
sys.path.insert(0, str(Path(__file__).parent))

from infra.catalog import UnifiedExperimentManager


def test_feature_names_filter():
    """测试特征名筛选功能"""

    # 初始化管理器
    config_path = '/home/lidonghaowsl/develop/Minitest-OECT-dataprocessing/catalog_config20251101.yaml'

    print(f"使用配置文件: {config_path}")
    manager = UnifiedExperimentManager(str(config_path))

    # 获取测试实验（使用实际有 V2 特征的实验）
    exp = manager.get_experiment(chip_id="#20250804007", device_id="1")
    if not exp:
        print("❌ 找不到测试实验 (chip_id=#20250804007, device_id=1)")
        return

    print(f"✅ 找到实验: {exp.chip_id}-{exp.device_id}")

    # 尝试读取 V2 特征（即使元数据不存在，也应该从文件系统回退读取）
    df_test = exp.get_v2_feature_dataframe()
    if df_test is None:
        print("❌ 无法读取 V2 特征")
        return

    print(f"✅ 成功读取 V2 特征: {df_test.shape}")
    print(f"   前10列: {list(df_test.columns[:10])}")

    print("\n" + "="*80)
    print("测试 1: 无参数调用（现有行为）")
    print("="*80)
    try:
        df = exp.get_v2_feature_dataframe()
        if df is not None:
            print(f"✅ 成功读取 DataFrame: {df.shape}")
            print(f"   列: {list(df.columns)[:10]}...")  # 只显示前10列
        else:
            print("⚠️ 返回 None")
    except Exception as e:
        print(f"❌ 错误: {e}")

    print("\n" + "="*80)
    print("测试 2: 单个标量特征筛选")
    print("="*80)
    try:
        df = exp.get_v2_feature_dataframe(feature_names='gm_max')
        if df is not None:
            print(f"✅ 成功读取 DataFrame: {df.shape}")
            print(f"   列: {list(df.columns)}")
            assert 'step_index' in df.columns, "缺少 step_index"
            assert 'gm_max' in df.columns, "缺少 gm_max"
            print(f"   前5行:\n{df.head()}")
        else:
            print("⚠️ 返回 None")
    except Exception as e:
        print(f"❌ 错误: {e}")

    print("\n" + "="*80)
    print("测试 3: 多个标量特征筛选")
    print("="*80)
    try:
        df = exp.get_v2_feature_dataframe(feature_names=['gm_max', 'Von', 'absI_max'])
        if df is not None:
            print(f"✅ 成功读取 DataFrame: {df.shape}")
            print(f"   列: {list(df.columns)}")
            assert 'step_index' in df.columns, "缺少 step_index"
            for feat in ['gm_max', 'Von', 'absI_max']:
                assert feat in df.columns, f"缺少 {feat}"
            print(f"   前5行:\n{df.head()}")
        else:
            print("⚠️ 返回 None")
    except Exception as e:
        print(f"❌ 错误: {e}")

    print("\n" + "="*80)
    print("测试 4: 通配符匹配")
    print("="*80)
    try:
        df = exp.get_v2_feature_dataframe(feature_names='gm_*')
        if df is not None:
            print(f"✅ 成功读取 DataFrame: {df.shape}")
            print(f"   列: {list(df.columns)}")
            assert 'step_index' in df.columns, "缺少 step_index"
            # 检查是否有 gm 开头的列
            gm_cols = [col for col in df.columns if col.startswith('gm_')]
            print(f"   匹配的 gm 特征: {gm_cols}")
            assert len(gm_cols) > 0, "没有匹配到任何 gm 特征"
        else:
            print("⚠️ 返回 None")
    except Exception as e:
        print(f"❌ 错误: {e}")

    print("\n" + "="*80)
    print("测试 5: 多维特征筛选")
    print("="*80)
    try:
        # 尝试读取可能的多维特征
        # 先读取完整 DataFrame 看有哪些特征
        df_full = exp.get_v2_feature_dataframe()
        if df_full is not None:
            # 查找可能的多维特征（_dim 后缀）
            multidim_cols = [col for col in df_full.columns if '_dim' in col]
            if multidim_cols:
                # 提取基础特征名（去除 _dimN 后缀）
                base_name = multidim_cols[0].rsplit('_dim', 1)[0]
                print(f"   找到多维特征: {base_name}")

                df = exp.get_v2_feature_dataframe(feature_names=base_name)
                if df is not None:
                    print(f"✅ 成功读取 DataFrame: {df.shape}")
                    print(f"   列: {list(df.columns)}")
                    assert 'step_index' in df.columns, "缺少 step_index"
                    # 检查是否包含所有维度
                    expected_cols = [col for col in df_full.columns if col.startswith(f'{base_name}_dim')]
                    for col in expected_cols:
                        assert col in df.columns, f"缺少 {col}"
                    print(f"   多维特征的所有维度: {[col for col in df.columns if col.startswith(base_name)]}")
            else:
                print("⚠️ 没有找到多维特征")
        else:
            print("⚠️ 无法读取完整 DataFrame")
    except Exception as e:
        print(f"❌ 错误: {e}")

    print("\n" + "="*80)
    print("测试 6: 异常处理（不存在的特征）")
    print("="*80)
    try:
        df = exp.get_v2_feature_dataframe(feature_names='non_existent_feature')
        print(f"❌ 应该抛出异常但没有: {df}")
    except KeyError as e:
        print(f"✅ 正确抛出 KeyError: {e}")
    except Exception as e:
        print(f"⚠️ 抛出了其他异常: {type(e).__name__}: {e}")

    print("\n" + "="*80)
    print("测试完成！")
    print("="*80)


if __name__ == '__main__':
    test_feature_names_filter()
