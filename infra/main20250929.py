# %%
import json
# extern_link/ps_paths.json解析
with open('extern_link/ps_paths2.json', 'r') as f:
    ps_paths = json.load(f)
print("Loaded ps_paths:", ps_paths)

# %%
from .catalog import UnifiedExperimentManager
import logging
from .logger_config import log_manager, get_module_logger
# 配置日志
log_manager.set_levels(
    file_level=logging.WARNING,
    console_level=logging.WARNING
)
logger = get_module_logger()
manager = UnifiedExperimentManager('catalog_config.yaml')


# %%
for path in ps_paths:
    print(f"Processing path: {path}")
    result = manager.process_data_pipeline(
        source_directory=path,
        clean_json=True,
        num_workers=20,
        conflict_strategy='skip',
        auto_extract_features=True,
        show_progress=True
    )
    print(f"Processing result for {path}: {result}")

# %%

from catalog import UnifiedExperimentManager

manager = UnifiedExperimentManager('catalog_config.yaml')

# 强制全量扫描，重新处理所有文件关联
print("执行全量重新扫描...")
result = manager.catalog.scan_and_index(incremental=False)

print(f"全量扫描完成:")
print(f"  - 处理文件: {result.files_processed}")
print(f"  - 新增记录: {result.files_added}")
print(f"  - 更新记录: {result.files_updated}")

# 验证关联结果
experiments = manager.search()
feature_count = sum(1 for exp in experiments if exp.has_features())
print(f"  - 有特征的实验: {feature_count}/{len(experiments)}")


