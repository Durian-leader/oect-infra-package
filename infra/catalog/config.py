"""
Catalog模块配置管理

负责加载和管理catalog系统的配置，包括：
- YAML配置文件的加载和解析
- 相对路径和绝对路径的转换
- 配置验证和默认值管理
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

from .models import DatabaseConfig, SyncConfig, DiscoveryConfig, ConflictStrategy


class CatalogConfigError(Exception):
    """Catalog配置错误"""
    pass


@dataclass
class LoggingConfig:
    """日志配置"""
    level: str = "INFO"
    file: str = "logs/catalog.log"
    rotation: str = "1 week"
    retention: str = "4 weeks"


@dataclass
class RootPathConfig:
    """根目录路径配置"""
    raw_data: str = "data/raw"
    features: str = "data/features"
    features_v2: str = "data/features_v2"


class CatalogConfig:
    """Catalog配置管理器
    
    负责加载、验证和管理catalog系统的所有配置项
    """
    
    def __init__(self, config_path: Optional[str] = None, base_dir: Optional[str] = None):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径，默认为catalog_config.yaml
            base_dir: 基础目录，用于相对路径解析，默认为当前工作目录
        """
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()
        self.config_path = Path(config_path) if config_path else self.base_dir / "catalog_config.yaml"
        
        # 配置组件
        self.roots: Optional[RootPathConfig] = None
        self.database: Optional[DatabaseConfig] = None
        self.sync: Optional[SyncConfig] = None
        self.discovery: Optional[DiscoveryConfig] = None
        self.logging: Optional[LoggingConfig] = None
        
        # 原始配置数据
        self._raw_config: Dict[str, Any] = {}
        
        # 加载配置
        self.load_config()
    
    def load_config(self) -> None:
        """加载配置文件"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self._raw_config = yaml.safe_load(f) or {}
            else:
                # 使用默认配置
                self._raw_config = self._get_default_config()
                self._save_default_config()
            
            # 解析配置组件
            self._parse_config()
            
        except Exception as e:
            raise CatalogConfigError(f"Failed to load config from {self.config_path}: {e}")
    
    def _parse_config(self) -> None:
        """解析配置各组件"""
        # 根目录配置
        roots_data = self._raw_config.get('roots', {})
        self.roots = RootPathConfig(
            raw_data=roots_data.get('raw_data', 'data/raw'),
            features=roots_data.get('features', 'data/features'),
            features_v2=roots_data.get('features_v2', 'data/features_v2')
        )
        
        # 数据库配置
        db_data = self._raw_config.get('database', {})
        self.database = DatabaseConfig(
            path=db_data.get('path', 'data/catalog.db'),
            auto_backup=db_data.get('auto_backup', False),
            backup_interval=db_data.get('backup_interval', 86400),
            connection_pool_size=db_data.get('connection_pool_size', 10)
        )
        
        # 同步配置
        sync_data = self._raw_config.get('sync', {})
        conflict_strategy_str = sync_data.get('conflict_strategy', 'timestamp')
        try:
            conflict_strategy = ConflictStrategy(conflict_strategy_str)
        except ValueError:
            conflict_strategy = ConflictStrategy.TIMESTAMP
            
        self.sync = SyncConfig(
            auto_sync=sync_data.get('auto_sync', False),
            auto_sync_interval=sync_data.get('auto_sync_interval', 3600),
            conflict_strategy=conflict_strategy,
            batch_size=sync_data.get('batch_size', 100),
            timeout=sync_data.get('timeout', 300)
        )
        
        # 文件发现配置
        discovery_data = self._raw_config.get('discovery', {})
        self.discovery = DiscoveryConfig(
            recursive=discovery_data.get('recursive', True),
            max_depth=discovery_data.get('max_depth', 10),
            parallel_workers=discovery_data.get('parallel_workers', 4),
            file_patterns=discovery_data.get('file_patterns', {
                "raw": "*-test_*.h5",
                "features": "*-feat_*.h5"
            }),
            ignore_patterns=discovery_data.get('ignore_patterns', ["*.tmp", ".*", "_*"])
        )
        
        # 日志配置
        logging_data = self._raw_config.get('logging', {})
        self.logging = LoggingConfig(
            level=logging_data.get('level', 'INFO'),
            file=logging_data.get('file', 'logs/catalog.log'),
            rotation=logging_data.get('rotation', '1 week'),
            retention=logging_data.get('retention', '4 weeks')
        )
    
    def get_absolute_path(self, path_type: str, relative_path: str = "") -> Path:
        """
        获取绝对路径

        Args:
            path_type: 路径类型 ('raw_data', 'features', 'features_v2', 'database', 'logs')
            relative_path: 相对路径

        Returns:
            Path: 绝对路径
        """
        if path_type == 'raw_data':
            base = self.base_dir / self.roots.raw_data
        elif path_type == 'features':
            base = self.base_dir / self.roots.features
        elif path_type == 'features_v2':
            base = self.base_dir / self.roots.features_v2
        elif path_type == 'database':
            base = self.base_dir / Path(self.database.path).parent
        elif path_type == 'logs':
            base = self.base_dir / Path(self.logging.file).parent
        else:
            raise CatalogConfigError(f"Unknown path type: {path_type}")
        
        if relative_path:
            return base / relative_path
        return base
    
    def get_relative_path(self, path_type: str, absolute_path: str) -> str:
        """
        将绝对路径转换为相对路径
        
        Args:
            path_type: 路径类型
            absolute_path: 绝对路径
        
        Returns:
            str: 相对路径
        """
        abs_path = Path(absolute_path)
        base_path = self.get_absolute_path(path_type)
        
        try:
            return str(abs_path.relative_to(base_path))
        except ValueError:
            # 如果不在基础路径下，返回绝对路径
            return str(abs_path)
    
    def ensure_directories(self) -> None:
        """确保所有必要的目录存在"""
        directories = [
            self.get_absolute_path('raw_data'),
            self.get_absolute_path('features'),
            self.get_absolute_path('features_v2'),
            self.get_absolute_path('database'),
            self.get_absolute_path('logs')
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    def get_database_path(self) -> Path:
        """获取数据库文件的绝对路径"""
        if Path(self.database.path).is_absolute():
            return Path(self.database.path)
        return self.base_dir / self.database.path
    
    def get_log_path(self) -> Path:
        """获取日志文件的绝对路径"""
        if Path(self.logging.file).is_absolute():
            return Path(self.logging.file)
        return self.base_dir / self.logging.file
    
    def validate_config(self) -> List[str]:
        """
        验证配置的有效性
        
        Returns:
            List[str]: 验证错误消息列表，空列表表示配置有效
        """
        errors = []
        
        # 验证路径配置
        try:
            raw_path = self.get_absolute_path('raw_data')
            if not raw_path.parent.exists():
                errors.append(f"Raw data parent directory does not exist: {raw_path.parent}")
        except Exception as e:
            errors.append(f"Invalid raw_data path configuration: {e}")
        
        try:
            features_path = self.get_absolute_path('features')
            if not features_path.parent.exists():
                errors.append(f"Features parent directory does not exist: {features_path.parent}")
        except Exception as e:
            errors.append(f"Invalid features path configuration: {e}")
        
        # 验证数据库配置
        if self.database.connection_pool_size <= 0:
            errors.append("Database connection_pool_size must be positive")
        
        if self.database.backup_interval <= 0:
            errors.append("Database backup_interval must be positive")
        
        # 验证同步配置
        if self.sync.batch_size <= 0:
            errors.append("Sync batch_size must be positive")
        
        if self.sync.timeout <= 0:
            errors.append("Sync timeout must be positive")
        
        # 验证文件发现配置
        if self.discovery.max_depth <= 0:
            errors.append("Discovery max_depth must be positive")
        
        if self.discovery.parallel_workers <= 0:
            errors.append("Discovery parallel_workers must be positive")
        
        return errors
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            'roots': {
                'raw_data': 'data/raw',
                'features': 'data/features',
                'features_v2': 'data/features_v2'
            },
            'database': {
                'path': 'data/catalog.db',
                'auto_backup': False,
                'backup_interval': 86400,
                'connection_pool_size': 10
            },
            'sync': {
                'auto_sync': False,
                'auto_sync_interval': 3600,
                'conflict_strategy': 'timestamp',
                'batch_size': 100,
                'timeout': 300
            },
            'discovery': {
                'recursive': True,
                'max_depth': 10,
                'parallel_workers': 4,
                'file_patterns': {
                    'raw': '*-test_*.h5',
                    'features': '*-feat_*.h5'
                },
                'ignore_patterns': ['*.tmp', '.*', '_*']
            },
            'logging': {
                'level': 'INFO',
                'file': 'logs/catalog.log',
                'rotation': '1 week',
                'retention': '4 weeks'
            }
        }
    
    def _save_default_config(self) -> None:
        """保存默认配置到文件"""
        try:
            # 确保配置文件目录存在
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self._raw_config, f, default_flow_style=False, 
                         allow_unicode=True, sort_keys=False)
        except Exception as e:
            # 不抛出异常，仅记录警告
            print(f"Warning: Could not save default config to {self.config_path}: {e}")
    
    def reload_config(self) -> None:
        """重新加载配置"""
        self.load_config()
    
    def update_config(self, updates: Dict[str, Any]) -> None:
        """
        更新配置
        
        Args:
            updates: 配置更新字典
        """
        # 深度合并配置
        self._deep_merge(self._raw_config, updates)
        
        # 重新解析配置
        self._parse_config()
        
        # 保存更新的配置
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self._raw_config, f, default_flow_style=False,
                         allow_unicode=True, sort_keys=False)
        except Exception as e:
            raise CatalogConfigError(f"Failed to save updated config: {e}")
    
    def _deep_merge(self, target: Dict[str, Any], source: Dict[str, Any]) -> None:
        """深度合并两个字典"""
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._deep_merge(target[key], value)
            else:
                target[key] = value
    
    def to_dict(self) -> Dict[str, Any]:
        """将配置转换为字典"""
        return {
            'roots': {
                'raw_data': self.roots.raw_data,
                'features': self.roots.features
            },
            'database': {
                'path': self.database.path,
                'auto_backup': self.database.auto_backup,
                'backup_interval': self.database.backup_interval,
                'connection_pool_size': self.database.connection_pool_size
            },
            'sync': {
                'auto_sync': self.sync.auto_sync,
                'auto_sync_interval': self.sync.auto_sync_interval,
                'conflict_strategy': self.sync.conflict_strategy.value,
                'batch_size': self.sync.batch_size,
                'timeout': self.sync.timeout
            },
            'discovery': {
                'recursive': self.discovery.recursive,
                'max_depth': self.discovery.max_depth,
                'parallel_workers': self.discovery.parallel_workers,
                'file_patterns': self.discovery.file_patterns,
                'ignore_patterns': self.discovery.ignore_patterns
            },
            'logging': {
                'level': self.logging.level,
                'file': self.logging.file,
                'rotation': self.logging.rotation,
                'retention': self.logging.retention
            }
        }
    
    def __str__(self) -> str:
        """字符串表示"""
        return f"CatalogConfig(config_path={self.config_path}, base_dir={self.base_dir})"
    
    def __repr__(self) -> str:
        """详细字符串表示"""
        return (f"CatalogConfig(config_path={self.config_path}, "
                f"base_dir={self.base_dir}, "
                f"raw_data={self.roots.raw_data}, "
                f"features={self.roots.features})")


def create_default_config(config_path: str, base_dir: Optional[str] = None, 
                         auto_detect: bool = True) -> CatalogConfig:
    """
    创建默认配置文件
    
    Args:
        config_path: 配置文件路径
        base_dir: 基础目录
        auto_detect: 是否自动检测现有目录结构
    
    Returns:
        CatalogConfig: 配置对象
    """
    config = CatalogConfig(config_path, base_dir)
    
    if auto_detect:
        # 自动检测现有目录结构并调整配置
        base_path = Path(base_dir) if base_dir else Path.cwd()
        
        # 检测raw数据目录
        possible_raw_dirs = ['data/raw', 'data', 'raw_data', 'data/h5_outputs']
        for raw_dir in possible_raw_dirs:
            if (base_path / raw_dir).exists():
                config.update_config({'roots': {'raw_data': raw_dir}})
                break
        
        # 检测features目录
        possible_feature_dirs = ['data/features', 'features']
        for feature_dir in possible_feature_dirs:
            if (base_path / feature_dir).exists():
                config.update_config({'roots': {'features': feature_dir}})
                break

        # 检测features_v2目录
        possible_feature_v2_dirs = ['data/features_v2', 'features_v2']
        for feature_v2_dir in possible_feature_v2_dirs:
            if (base_path / feature_v2_dir).exists():
                config.update_config({'roots': {'features_v2': feature_v2_dir}})
                break

    # 确保目录存在
    config.ensure_directories()
    
    return config