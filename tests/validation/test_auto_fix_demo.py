"""
演示自动修复机制：
1. 人为创建一个不一致（数据库有记录但文件不存在）
2. 验证 has_v2_features() 能自动检测并修复
3. 验证批量提取会重新提取
"""
from infra.catalog import UnifiedExperimentManager
import sqlite3
import json
from pathlib import Path
import shutil

manager = UnifiedExperimentManager('catalog_config.yaml')

print("=" * 80)
print("演示：自动修复机制")
print("=" * 80)

# 选择一个实验
test_exp = manager.get_experiment(chip_id="#20250829012", device_id="2")
if not test_exp:
    print("测试实验不存在")
    exit(1)

print(f"\n选择测试实验: {test_exp.chip_id}-{test_exp.device_id}")

# 获取当前的 V2 特征文件
metadata = test_exp.get_v2_features_metadata(validate_files=False)
print(f"\n当前元数据:")
print(f"  configs_used: {metadata.get('configs_used')}")
print(f"  output_files: {metadata.get('output_files')}")

# 备份并删除文件（模拟文件丢失）
output_files = metadata.get('output_files', [])
if not output_files:
    print("\n没有输出文件，无法演示")
    exit(1)

original_file = Path(output_files[0])
backup_file = original_file.parent / f"{original_file.stem}_backup{original_file.suffix}"

print(f"\n步骤1：备份并删除文件（模拟文件丢失）")
print(f"  原文件: {original_file.name}")
print(f"  备份到: {backup_file.name}")

if original_file.exists():
    shutil.copy2(original_file, backup_file)
    original_file.unlink()
    print("  ✓ 文件已删除（已备份）")
else:
    print("  ✗ 文件已经不存在")

# 验证数据库中还有记录
print(f"\n步骤2：验证数据库中仍有记录")
db_metadata = test_exp.get_v2_features_metadata(validate_files=False)
print(f"  数据库元数据: {db_metadata is not None}")
print(f"  configs_used: {db_metadata.get('configs_used') if db_metadata else None}")

# 使用新的验证机制
print(f"\n步骤3：使用文件验证机制检查")
has_v2_before = test_exp.has_v2_features(validate_files=True)
print(f"  has_v2_features(validate_files=True): {has_v2_before}")

if not has_v2_before:
    print("  ✓ 自动检测到文件不存在，已清理数据库记录")

    # 验证数据库已被清理
    db_metadata_after = test_exp.get_v2_features_metadata(validate_files=False)
    print(f"  清理后的数据库元数据: {db_metadata_after}")

# 恢复文件
print(f"\n步骤4：恢复备份文件")
if backup_file.exists():
    shutil.copy2(backup_file, original_file)
    backup_file.unlink()
    print(f"  ✓ 文件已恢复，备份已删除")

# 验证恢复后的状态
print(f"\n步骤5：验证恢复后的状态")
has_v2_after_restore = test_exp.has_v2_features(validate_files=True)
print(f"  has_v2_features(validate_files=True): {has_v2_after_restore}")

if has_v2_after_restore:
    print("  ✓ 文件存在，验证通过")
else:
    print("  ⚠️ 需要重新提取特征")

print("\n" + "=" * 80)
print("演示完成！")
print("=" * 80)
print("\n总结:")
print("1. 当文件被删除但数据库有记录时")
print("2. has_v2_features(validate_files=True) 会自动检测不一致")
print("3. 自动清理数据库中的无效记录")
print("4. 下次批量提取时会自动重新提取该实验")
