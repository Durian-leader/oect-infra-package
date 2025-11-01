"""
测试去重机制：
1. 提取一个实验的 V2 特征
2. 再次提取同一个实验
3. 验证只保留最新的文件，旧文件被自动删除
"""
from infra.catalog import UnifiedExperimentManager
from pathlib import Path
import time

manager = UnifiedExperimentManager('catalog_config.yaml')

# 选择测试实验
test_exp = manager.get_experiment(chip_id="#20250829012", device_id="2")
if not test_exp:
    print("测试实验不存在")
    exit(1)

features_v2_dir = Path("/home/lidonghaowsl/develop_win/hdd/data/Stability_PS20250929/features_v2")

print("=" * 80)
print("测试：V2 特征提取去重机制")
print("=" * 80)

print(f"\n测试实验: {test_exp.chip_id}-{test_exp.device_id}")

# 检查当前文件数
def count_files_for_exp(chip_id, device_id, config_name):
    pattern = f"{chip_id}-{device_id}-{config_name}-*.parquet"
    files = list(features_v2_dir.glob(pattern))
    return files

# 第一次提取
print("\n步骤1：第一次提取 V2 特征")
result1 = test_exp.extract_features_v2('v2_ml_ready', force_recompute=True)
print(f"  ✓ 提取完成: {result1}")

files_after_first = count_files_for_exp("#20250829012", "2", "v2_ml_ready")
print(f"  文件数: {len(files_after_first)}")
for f in files_after_first:
    print(f"    - {f.name}")

# 等待1秒，确保时间戳不同
time.sleep(1)

# 第二次提取（应该删除旧文件）
print("\n步骤2：第二次提取 V2 特征（force_recompute=True）")
result2 = test_exp.extract_features_v2('v2_ml_ready', force_recompute=True)
print(f"  ✓ 提取完成: {result2}")

files_after_second = count_files_for_exp("#20250829012", "2", "v2_ml_ready")
print(f"  文件数: {len(files_after_second)}")
for f in files_after_second:
    print(f"    - {f.name}")

# 验证结果
print("\n=" * 80)
print("验证结果:")
print("=" * 80)

if len(files_after_second) == 1:
    print("✓ 去重成功！只保留了最新的文件")

    # 检查文件是否是新的
    new_file = files_after_second[0]
    old_files = [f for f in files_after_first if f.name != new_file.name]

    if old_files:
        print(f"✓ 旧文件已删除:")
        for f in old_files:
            print(f"    - {f.name}")
    else:
        print("⚠️ 没有旧文件被删除（可能文件名相同）")

else:
    print(f"✗ 去重失败！仍有 {len(files_after_second)} 个文件")
    print("  这表明去重机制未生效")

# 检查数据库元数据
metadata = test_exp.get_v2_features_metadata(validate_files=False)
if metadata:
    print(f"\n数据库元数据:")
    print(f"  configs_used: {metadata.get('configs_used')}")
    print(f"  output_files 数量: {len(metadata.get('output_files', []))}")
    for f in metadata.get('output_files', []):
        print(f"    - {Path(f).name}")

print("\n" + "=" * 80)
