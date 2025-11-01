"""
测试修复后的一致性检查机制
"""
from infra.catalog import UnifiedExperimentManager
import sqlite3
import json
from pathlib import Path

manager = UnifiedExperimentManager('catalog_config.yaml')

print("=" * 80)
print("测试：文件存在性验证机制")
print("=" * 80)

# 获取所有实验
all_experiments = manager.search()
print(f"\n总实验数: {len(all_experiments)}")

# 统计有 V2 特征的实验（使用新的验证机制）
experiments_with_v2 = []
experiments_without_v2 = []
auto_fixed = []

for exp in all_experiments:
    # 先检查数据库中的原始元数据
    db_path = manager.catalog.config.get_database_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT v2_feature_metadata
        FROM experiments
        WHERE chip_id = ? AND device_id = ?
    """, (exp.chip_id, exp.device_id))
    row = cursor.fetchone()
    conn.close()

    db_metadata = None
    if row and row[0]:
        try:
            db_metadata = json.loads(row[0])
        except:
            pass

    # 使用新的验证机制
    has_v2 = exp.has_v2_features(validate_files=True)

    if db_metadata and not has_v2:
        # 数据库有记录但验证后发现没有有效特征，说明被自动修复了
        auto_fixed.append((exp.chip_id, exp.device_id, db_metadata))
        print(f"✓ 自动修复: {exp.chip_id}-{exp.device_id}")
        print(f"  原数据库记录: configs={db_metadata.get('configs_used')}, files={len(db_metadata.get('output_files', []))}")

    if has_v2:
        experiments_with_v2.append(exp)
    else:
        experiments_without_v2.append(exp)

print(f"\n" + "=" * 80)
print(f"验证结果:")
print(f"=" * 80)
print(f"有 V2 特征（文件存在）: {len(experiments_with_v2)}")
print(f"无 V2 特征: {len(experiments_without_v2)}")
print(f"自动修复的不一致: {len(auto_fixed)}")

if auto_fixed:
    print(f"\n自动修复的实验:")
    for chip_id, device_id, old_metadata in auto_fixed:
        print(f"  - {chip_id}-{device_id}")

# 验证文件系统
features_v2_dir = Path("/home/lidonghaowsl/develop_win/hdd/data/Stability_PS20250929/features_v2")
parquet_files = list(features_v2_dir.glob("*v2_ml_ready*.parquet"))
print(f"\n实际文件数: {len(parquet_files)}")

# 检查一致性
file_experiments = set()
for pf in parquet_files:
    parts = pf.stem.split("-")
    if len(parts) >= 2:
        chip_id = parts[0]
        device_id = parts[1]
        file_experiments.add((chip_id, device_id))

db_experiments = set((exp.chip_id, exp.device_id) for exp in experiments_with_v2)

print(f"\n一致性检查:")
print(f"  数据库中有 V2 特征的实验: {len(db_experiments)}")
print(f"  文件系统中的实验: {len(file_experiments)}")

if db_experiments == file_experiments:
    print("  ✓ 数据库和文件系统完全一致！")
else:
    db_only = db_experiments - file_experiments
    file_only = file_experiments - db_experiments

    if db_only:
        print(f"  ✗ 只在数据库中: {len(db_only)}")
        for chip_id, device_id in list(db_only)[:5]:
            print(f"    - {chip_id}-{device_id}")

    if file_only:
        print(f"  ⚠️ 只在文件中: {len(file_only)}")
        for chip_id, device_id in list(file_only)[:5]:
            print(f"    - {chip_id}-{device_id}")

print("\n" + "=" * 80)
print("测试完成！")
print("=" * 80)
