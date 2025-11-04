"""
process_data_pipeline 使用示例

演示如何使用重构后的 process_data_pipeline 方法进行数据处理管道。
"""

from infra.catalog import UnifiedExperimentManager


def example_01_convert_only():
    """示例1：仅转换数据，不提取任何特征"""
    print("\n" + "="*60)
    print("示例1：仅转换数据（不提取特征）")
    print("="*60)

    manager = UnifiedExperimentManager('catalog_config.yaml')

    result = manager.process_data_pipeline(
        source_directory='data/source',
        clean_json=True,
        num_workers=20,
        v1_feature_versions=None,  # 不使用 features_version
        v2_feature_configs=None    # 不使用 features_v2
    )

    print(f"✅ Converted {result['results']['conversion']['successful_conversions']} files")
    print(f"Steps completed: {result['steps_completed']}")


def example_02_v1_transfer_features():
    """示例2：转换 + V1 Transfer 特征提取（gm, Von, |I|）"""
    print("\n" + "="*60)
    print("示例2：转换 + V1 Transfer 特征")
    print("="*60)

    manager = UnifiedExperimentManager('catalog_config.yaml')

    result = manager.process_data_pipeline(
        source_directory='data/source',
        v1_feature_versions=['v1'],  # 使用 v1_feature.py
        v2_feature_configs=None
    )

    # 查看 V1 特征提取结果
    if 'v1_feature_extraction_v1' in result['results']:
        v1_result = result['results']['v1_feature_extraction_v1']
        print(f"✅ V1 Transfer: {len(v1_result['successful'])} successful, "
              f"{len(v1_result['failed'])} failed, "
              f"{len(v1_result['skipped'])} skipped")


def example_03_v2_transient_tau():
    """示例3：转换 + V2 Transient tau 特征提取（tau_on, tau_off）"""
    print("\n" + "="*60)
    print("示例3：转换 + V2 Transient tau 特征")
    print("="*60)

    manager = UnifiedExperimentManager('catalog_config.yaml')

    result = manager.process_data_pipeline(
        source_directory='data/source',
        v1_feature_versions=['v2'],  # 使用 v2_feature.py（transient tau）
        v2_feature_configs=None
    )

    # 查看 V2 特征提取结果
    if 'v1_feature_extraction_v2' in result['results']:
        v2_result = result['results']['v1_feature_extraction_v2']
        print(f"✅ V2 Transient tau: {len(v2_result['successful'])} successful, "
              f"{len(v2_result['failed'])} failed, "
              f"{len(v2_result['skipped'])} skipped")


def example_04_both_v1_and_v2():
    """示例4：转换 + V1 和 V2 特征同时提取"""
    print("\n" + "="*60)
    print("示例4：同时提取 V1 Transfer 和 V2 Transient tau")
    print("="*60)

    manager = UnifiedExperimentManager('catalog_config.yaml')

    result = manager.process_data_pipeline(
        source_directory='data/source',
        v1_feature_versions=['v1', 'v2'],  # 两个版本都提取
        v2_feature_configs=None
    )

    # 查看两个版本的结果
    for version in ['v1', 'v2']:
        key = f'v1_feature_extraction_{version}'
        if key in result['results']:
            ver_result = result['results'][key]
            print(f"✅ {version}: {len(ver_result['successful'])} successful")


def example_05_features_v2():
    """示例5：转换 + features_v2 特征提取（多配置）"""
    print("\n" + "="*60)
    print("示例5：使用 features_v2 提取多个配置")
    print("="*60)

    manager = UnifiedExperimentManager('catalog_config.yaml')

    result = manager.process_data_pipeline(
        source_directory='data/source',
        v1_feature_versions=None,
        v2_feature_configs=['v2_transfer_basic', 'v2_ml_ready']
    )

    # 查看每个配置的结果
    for config in ['v2_transfer_basic', 'v2_ml_ready']:
        key = f'v2_feature_extraction_{config}'
        if key in result['results']:
            config_result = result['results'][key]
            print(f"✅ {config}: {len(config_result.get('successful', []))} successful")


def example_06_full_pipeline():
    """示例6：完整管道（所有特征）"""
    print("\n" + "="*60)
    print("示例6：完整管道（提取所有特征）")
    print("="*60)

    manager = UnifiedExperimentManager('catalog_config.yaml')

    result = manager.process_data_pipeline(
        source_directory='data/source',
        clean_json=True,
        num_workers=20,
        conflict_strategy='skip',
        v1_feature_versions=['v1', 'v2'],  # Transfer + Transient tau
        v2_feature_configs=['v2_transfer_basic', 'v2_ml_ready'],  # features_v2 配置
        show_progress=True
    )

    # 打印完成的步骤
    print("\n✅ Completed steps:")
    for step in result['steps_completed']:
        print(f"  - {step}")

    # 打印各步骤的统计
    print("\n📊 Statistics:")

    # 转换统计
    conv = result['results']['conversion']
    print(f"  Conversion: {conv['successful_conversions']}/{conv['total_directories']} successful")

    # V1 特征统计
    for version in ['v1', 'v2']:
        key = f'v1_feature_extraction_{version}'
        if key in result['results']:
            ver_result = result['results'][key]
            print(f"  {version} features: {len(ver_result['successful'])} successful, "
                  f"{len(ver_result['failed'])} failed, "
                  f"{len(ver_result['skipped'])} skipped")

    # V2 配置统计
    for config in ['v2_transfer_basic', 'v2_ml_ready']:
        key = f'v2_feature_extraction_{config}'
        if key in result['results']:
            config_result = result['results'][key]
            print(f"  {config}: {len(config_result.get('successful', []))} successful, "
                  f"{len(config_result.get('failed', []))} failed, "
                  f"{len(config_result.get('skipped', []))} skipped")


def example_07_custom_workflow():
    """示例7：自定义工作流（分步执行）"""
    print("\n" + "="*60)
    print("示例7：自定义工作流（分步控制）")
    print("="*60)

    manager = UnifiedExperimentManager('catalog_config.yaml')

    # 第一步：仅转换
    print("\n步骤1: 转换数据...")
    result1 = manager.process_data_pipeline(
        source_directory='data/source',
        v1_feature_versions=None,
        v2_feature_configs=None
    )

    if result1['overall_success']:
        print(f"✅ 转换完成: {result1['results']['conversion']['successful_conversions']} files")

        # 第二步：提取 V1 特征
        print("\n步骤2: 提取 V1 Transfer 特征...")
        result2 = manager.process_data_pipeline(
            source_directory='data/source',
            clean_json=False,  # 跳过 JSON 清理（已完成）
            v1_feature_versions=['v1']
        )

        # 第三步：提取 V2 特征（如果需要）
        print("\n步骤3: 提取 V2 Transient tau 特征...")
        result3 = manager.process_data_pipeline(
            source_directory='data/source',
            clean_json=False,
            v1_feature_versions=['v2']
        )

        print("\n✅ 所有步骤完成")


def example_08_error_handling():
    """示例8：错误处理"""
    print("\n" + "="*60)
    print("示例8：错误处理和失败实验处理")
    print("="*60)

    manager = UnifiedExperimentManager('catalog_config.yaml')

    result = manager.process_data_pipeline(
        source_directory='data/source',
        v1_feature_versions=['v1', 'v2']
    )

    # 检查总体结果
    if result['overall_success']:
        print("✅ Pipeline completed successfully")
    else:
        print(f"❌ Pipeline failed: {result.get('error', 'Unknown error')}")

    # 检查每个步骤的失败情况
    for version in ['v1', 'v2']:
        key = f'v1_feature_extraction_{version}'
        if key in result['results']:
            ver_result = result['results'][key]

            # 处理失败的实验
            if ver_result.get('failed'):
                print(f"\n⚠️ {version} 特征提取失败的实验:")
                for exp_id, error in ver_result['failed']:
                    print(f"  - Experiment {exp_id}: {error}")

            # 处理跳过的实验
            if ver_result.get('skipped'):
                print(f"\n⏭️  {version} 特征提取跳过的实验（已有特征）:")
                print(f"  - {len(ver_result['skipped'])} experiments skipped")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("process_data_pipeline 使用示例")
    print("="*60)

    # 运行示例（根据需要取消注释）

    # 示例1：仅转换
    # example_01_convert_only()

    # 示例2：V1 Transfer 特征
    # example_02_v1_transfer_features()

    # 示例3：V2 Transient tau 特征
    # example_03_v2_transient_tau()

    # 示例4：V1 和 V2 同时提取
    # example_04_both_v1_and_v2()

    # 示例5：features_v2 多配置
    # example_05_features_v2()

    # 示例6：完整管道
    # example_06_full_pipeline()

    # 示例7：自定义工作流
    # example_07_custom_workflow()

    # 示例8：错误处理
    # example_08_error_handling()

    print("\n" + "="*60)
    print("请修改源目录路径并取消注释相应的示例")
    print("="*60)
