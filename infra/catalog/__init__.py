"""
Catalog模块 - OECT HDF5文件元信息管理和双向同步系统

这个模块提供了完整的catalog系统功能，包括：
- 文件索引和查询
- 双向同步机制  
- 统一的实验数据管理接口
- 与现有模块的深度集成

## 快速开始

### 使用统一接口（推荐）
```python
from catalog import UnifiedExperimentManager

# 初始化管理器
manager = UnifiedExperimentManager()

# 获取实验
exp = manager.get_experiment(chip_id="#20250804008", device_id="3")

# 获取数据
transfer_data = exp.get_transfer_data()
features = exp.get_features(['gm_max_forward', 'Von_forward'])

# 绘图
fig = exp.plot_transfer_evolution()
```

### 使用catalog服务
```python
from catalog import CatalogService

# 初始化服务
catalog = CatalogService()

# 扫描和索引文件
result = catalog.scan_and_index()

# 查询实验
experiments = catalog.find_experiments(chip_id="#20250804008")

# 同步数据
sync_result = catalog.bidirectional_sync()
```

### 使用CLI工具
```bash
# 初始化catalog系统
python -m catalog init --auto-config

# 扫描文件
python -m catalog scan --path data/raw --recursive

# 双向同步
python -m catalog sync --direction both

# 查询实验
python -m catalog query --chip "#20250804008" --output table
```
"""

# 版本信息
__version__ = "1.0.0"
__author__ = "OECT Data Processing Team"
__description__ = "OECT HDF5文件元信息管理和双向同步系统"

# 核心API导出
from .service import CatalogService
from .unified import UnifiedExperimentManager, UnifiedExperiment
from .config import CatalogConfig, create_default_config

# 数据模型导出
from .models import (
    FileRecord,
    ExperimentFilter,
    SyncResult,
    CatalogStatistics,
    ExperimentStatus,
    DeviceType,
    SyncDirection,
    ConflictStrategy
)

# 错误类导出
from .service import CatalogServiceError
from .unified import UnifiedExperimentError
from .config import CatalogConfigError

# CLI工具导出
from . import cli

# 便利函数
def quick_start(config_path: str = 'catalog_config.yaml') -> UnifiedExperimentManager:
    """
    快速启动catalog系统
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        UnifiedExperimentManager: 统一实验管理器
        
    Example:
        >>> manager = quick_start()
        >>> experiments = manager.search(chip_id="#20250804008")
    """
    return UnifiedExperimentManager(config_path)

def init_catalog(config_path: str = 'catalog_config.yaml', 
                base_dir: str = None,
                auto_detect: bool = True) -> CatalogService:
    """
    初始化catalog系统
    
    Args:
        config_path: 配置文件路径
        base_dir: 基础目录
        auto_detect: 是否自动检测目录结构
        
    Returns:
        CatalogService: Catalog服务对象
        
    Example:
        >>> catalog = init_catalog()
        >>> result = catalog.scan_and_index()
    """
    # 如果配置文件不存在，创建默认配置
    config = create_default_config(config_path, base_dir, auto_detect)
    
    # 创建服务
    service = CatalogService(config_path, base_dir)
    
    # 初始化
    init_result = service.initialize_catalog()
    if not init_result['success']:
        raise CatalogServiceError(f"Failed to initialize catalog: {init_result['message']}")
    
    return service

# 模块级别的便利API
def find_experiments(**kwargs) -> list:
    """
    快速查找实验（使用默认配置）
    
    Args:
        **kwargs: 查询条件
        
    Returns:
        list: UnifiedExperiment对象列表
        
    Example:
        >>> experiments = find_experiments(chip_id="#20250804008")
    """
    manager = quick_start()
    try:
        return manager.search(**kwargs)
    finally:
        manager.close()

def get_experiment_by_id(exp_id: int):
    """
    根据ID获取实验（使用默认配置）
    
    Args:
        exp_id: 实验ID
        
    Returns:
        UnifiedExperiment: 实验对象或None
        
    Example:
        >>> exp = get_experiment_by_id(42)
    """
    manager = quick_start()
    try:
        return manager.get_experiment(exp_id)
    finally:
        manager.close()

def sync_all() -> dict:
    """
    执行完整同步（使用默认配置）
    
    Returns:
        dict: 同步结果
        
    Example:
        >>> result = sync_all()
        >>> print(f"Processed {result['files_processed']} files")
    """
    manager = quick_start()
    try:
        return manager.sync_all()
    finally:
        manager.close()

# 导出的主要组件
__all__ = [
    # 核心类
    'CatalogService',
    'UnifiedExperimentManager', 
    'UnifiedExperiment',
    'CatalogConfig',
    
    # 数据模型
    'FileRecord',
    'ExperimentFilter', 
    'SyncResult',
    'CatalogStatistics',
    'ExperimentStatus',
    'DeviceType',
    'SyncDirection',
    'ConflictStrategy',
    
    # 错误类
    'CatalogServiceError',
    'UnifiedExperimentError',
    'CatalogConfigError',
    
    # 便利函数
    'quick_start',
    'init_catalog',
    'create_default_config',
    'find_experiments',
    'get_experiment_by_id',
    'sync_all',
    
    # CLI模块
    'cli',
    
    # 版本信息
    '__version__',
    '__author__',
    '__description__'
]

# 模块初始化时的提示
import logging
logger = logging.getLogger(__name__)
logger.debug(f"Catalog module v{__version__} initialized")

# 检查依赖关系
def _check_dependencies():
    """检查模块依赖"""
    required_modules = ['infra.experiment', 'infra.features', 'infra.features_version', 'infra.visualization']
    missing_modules = []

    for module in required_modules:
        try:
            __import__(module)
        except ImportError:
            missing_modules.append(module)
    
    if missing_modules:
        logger.warning(f"Some optional dependencies are missing: {missing_modules}")
        logger.warning("Catalog will work with limited functionality")

# 延迟检查依赖，避免循环导入
import threading
def _lazy_check():
    try:
        _check_dependencies()
    except Exception:
        pass

check_thread = threading.Thread(target=_lazy_check)
check_thread.daemon = True
check_thread.start()