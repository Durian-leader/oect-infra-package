"""
Catalog模块业务服务层

提供catalog系统的核心业务API，整合所有底层组件：
- 实验索引和查询服务
- 同步管理服务
- 统计和分析服务  
- 维护和管理服务
- 与现有模块的集成接口
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Tuple
from datetime import datetime

from .config import CatalogConfig, create_default_config
from .repository import CatalogRepository
from .scanner import FileScanner
from .sync import CatalogSynchronizer
from .models import (
    FileRecord, ExperimentFilter, SyncResult, CatalogStatistics,
    ExperimentStatus, DeviceType, SyncDirection, ConflictStrategy
)

logger = logging.getLogger(__name__)


class CatalogServiceError(Exception):
    """Catalog服务错误"""
    pass


class CatalogService:
    """
    Catalog服务主类
    
    提供catalog系统的完整功能接口，是用户与catalog系统交互的主要入口点
    """
    
    def __init__(self, config_path: Optional[str] = None, base_dir: Optional[str] = None):
        """
        初始化Catalog服务
        
        Args:
            config_path: 配置文件路径，如果不存在会自动创建默认配置
            base_dir: 基础目录，默认为当前工作目录
        """
        try:
            # 初始化配置
            if config_path and Path(config_path).exists():
                self.config = CatalogConfig(config_path, base_dir)
            else:
                # 创建默认配置
                config_path = config_path or "catalog_config.yaml"
                self.config = create_default_config(config_path, base_dir, auto_detect=True)
            
            # 验证配置
            config_errors = self.config.validate_config()
            if config_errors:
                raise CatalogServiceError(f"Invalid configuration: {'; '.join(config_errors)}")
            
            # 确保目录存在
            self.config.ensure_directories()
            
            # 初始化核心组件
            self.repository = CatalogRepository(self.config)
            self.scanner = FileScanner(self.config)
            self.synchronizer = CatalogSynchronizer(self.config, self.repository)
            
            logger.info(f"CatalogService initialized with config: {self.config.config_path}")
            
        except Exception as e:
            raise CatalogServiceError(f"Failed to initialize CatalogService: {e}")
    
    # ==================== 初始化和配置管理 ====================
    
    def initialize_catalog(self, force: bool = False) -> Dict[str, Any]:
        """
        初始化catalog系统
        
        Args:
            force: 是否强制重新初始化
            
        Returns:
            Dict[str, Any]: 初始化结果
        """
        result = {
            'success': False,
            'message': '',
            'statistics': None
        }
        
        try:
            if force:
                # 清空数据库（如果需要）
                logger.warning("Force initialization requested - this will clear existing data")
            
            # 确保数据库初始化
            self.repository._initialize_tables()
            
            # 获取初始统计
            stats = self.repository.get_statistics()
            
            result.update({
                'success': True,
                'message': 'Catalog initialized successfully',
                'statistics': {
                    'total_experiments': stats.total_experiments,
                    'database_path': str(self.config.get_database_path()),
                    'raw_data_path': str(self.config.get_absolute_path('raw_data')),
                    'features_path': str(self.config.get_absolute_path('features'))
                }
            })
            
            logger.info("Catalog initialization completed successfully")
            
        except Exception as e:
            error_msg = f"Catalog initialization failed: {e}"
            result['message'] = error_msg
            logger.error(error_msg)
        
        return result
    
    def get_config_info(self) -> Dict[str, Any]:
        """获取配置信息"""
        return {
            'config_path': str(self.config.config_path),
            'base_directory': str(self.config.base_dir),
            'database_path': str(self.config.get_database_path()),
            'raw_data_path': str(self.config.get_absolute_path('raw_data')),
            'features_path': str(self.config.get_absolute_path('features')),
            'configuration': self.config.to_dict()
        }
    
    # ==================== 文件索引和扫描 ====================
    
    def scan_and_index(self, scan_paths: Optional[List[str]] = None, 
                       incremental: bool = True) -> SyncResult:
        """
        扫描和索引文件
        
        Args:
            scan_paths: 扫描路径列表，如果为None则扫描默认路径
            incremental: 是否增量扫描
            
        Returns:
            SyncResult: 扫描和索引结果
        """
        if scan_paths is None:
            scan_paths = [
                str(self.config.get_absolute_path('raw_data')),
                str(self.config.get_absolute_path('features'))
            ]
        
        try:
            logger.info(f"Starting scan and index for paths: {scan_paths}")
            result = self.synchronizer.sync_files_to_db(scan_paths, incremental)
            
            logger.info(f"Scan completed: {result.files_processed} files processed, "
                       f"{result.files_added} added, {result.files_updated} updated")
            
            return result
            
        except Exception as e:
            error_msg = f"Scan and index failed: {e}"
            logger.error(error_msg)
            result = SyncResult()
            result.add_error(error_msg)
            result.finish()
            return result
    
    def index_file(self, file_path: str) -> Optional[FileRecord]:
        """
        索引单个文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            Optional[FileRecord]: 创建的文件记录，失败返回None
        """
        try:
            # 提取元信息
            metadata_results = self.scanner.extract_file_metadata([file_path])
            
            if not metadata_results or metadata_results[0][2]:  # 有错误
                return None
            
            # 创建记录
            file_path, metadata, _ = metadata_results[0]
            records, errors = self.scanner.create_file_records([(file_path, metadata, None)])
            
            if errors or not records:
                return None
            
            record = records[0]
            
            # 插入数据库
            record_id = self.repository.insert_experiment(record)
            if record_id:
                record.id = record_id
                return record
            
        except Exception as e:
            logger.error(f"Failed to index file {file_path}: {e}")
        
        return None
    
    # ==================== 实验查询和检索 ====================
    
    def find_experiments(self, **filter_kwargs) -> List[FileRecord]:
        """
        查找实验
        
        Args:
            **filter_kwargs: 过滤条件关键字参数
            
        Returns:
            List[FileRecord]: 匹配的实验记录列表
        """
        try:
            # 构建过滤器
            filter_obj = ExperimentFilter(**filter_kwargs)
            return self.repository.find_experiments(filter_obj)
            
        except Exception as e:
            logger.error(f"Find experiments failed: {e}")
            return []
    
    def get_experiment_by_id(self, experiment_id: int) -> Optional[FileRecord]:
        """根据ID获取实验"""
        try:
            return self.repository.get_experiment_by_id(experiment_id)
        except Exception as e:
            logger.error(f"Get experiment by ID failed: {e}")
            return None
    
    def get_experiment_by_test_id(self, test_id: str) -> Optional[FileRecord]:
        """根据test_id获取实验"""
        try:
            return self.repository.get_experiment_by_test_id(test_id)
        except Exception as e:
            logger.error(f"Get experiment by test_id failed: {e}")
            return None
    
    def search_experiments(self, query: str, limit: Optional[int] = None) -> List[FileRecord]:
        """
        全文搜索实验
        
        Args:
            query: 搜索查询字符串
            limit: 结果数量限制
            
        Returns:
            List[FileRecord]: 搜索结果列表
        """
        try:
            filter_obj = ExperimentFilter(text_search=query, limit=limit)
            return self.repository.find_experiments(filter_obj)
        except Exception as e:
            logger.error(f"Search experiments failed: {e}")
            return []
    
    def get_experiments_by_chip(self, chip_id: str) -> List[FileRecord]:
        """获取指定芯片的所有实验"""
        return self.find_experiments(chip_id=chip_id)
    
    def get_experiments_by_batch(self, batch_id: str) -> List[FileRecord]:
        """获取指定批次的所有实验"""
        return self.find_experiments(batch_id=batch_id)
    
    def get_experiments_missing_features(self) -> List[FileRecord]:
        """获取缺少特征文件的实验"""
        return self.find_experiments(missing_features=True)
    
    def get_completed_experiments(self) -> List[FileRecord]:
        """获取已完成的实验"""
        return self.find_experiments(status=ExperimentStatus.COMPLETED)
    
    # ==================== 同步管理 ====================
    
    def sync_files_to_database(self, scan_paths: Optional[List[str]] = None, 
                              incremental: bool = True) -> SyncResult:
        """文件系统到数据库同步"""
        if scan_paths is None:
            scan_paths = [
                str(self.config.get_absolute_path('raw_data')),
                str(self.config.get_absolute_path('features'))
            ]
        
        return self.synchronizer.sync_files_to_db(scan_paths, incremental)
    
    def sync_database_to_files(self, experiment_filter: Optional[ExperimentFilter] = None) -> SyncResult:
        """数据库到文件系统同步"""
        return self.synchronizer.sync_db_to_files(experiment_filter)
    
    def bidirectional_sync(self, scan_paths: Optional[List[str]] = None, 
                          conflict_strategy: Optional[ConflictStrategy] = None) -> SyncResult:
        """双向同步"""
        if scan_paths is None:
            scan_paths = [
                str(self.config.get_absolute_path('raw_data')),
                str(self.config.get_absolute_path('features'))
            ]
        
        return self.synchronizer.bidirectional_sync(scan_paths, conflict_strategy)
    
    def get_sync_status(self) -> Dict[str, Any]:
        """获取同步状态"""
        return self.synchronizer.get_sync_status()
    
    def force_resync(self, experiment_ids: Optional[List[int]] = None) -> SyncResult:
        """强制重新同步"""
        return self.synchronizer.force_resync(experiment_ids)
    
    # ==================== 统计和分析 ====================
    
    def get_statistics(self) -> CatalogStatistics:
        """获取catalog统计信息"""
        try:
            return self.repository.get_statistics()
        except Exception as e:
            logger.error(f"Get statistics failed: {e}")
            return CatalogStatistics()
    
    def get_summary_report(self) -> Dict[str, Any]:
        """获取摘要报告"""
        try:
            stats = self.get_statistics()
            
            return {
                'overview': {
                    'total_experiments': stats.total_experiments,
                    'completed_experiments': stats.completed_experiments,
                    'completion_rate': stats.completion_rate,
                    'unique_chips': stats.unique_chips,
                    'unique_batches': stats.unique_batches
                },
                'files': {
                    'total_raw_files': stats.total_raw_files,
                    'total_feature_files': stats.total_feature_files,
                    'feature_coverage': stats.feature_coverage,
                    'missing_feature_files': stats.missing_feature_files
                },
                'storage': {
                    'total_raw_size': stats.total_raw_size,
                    'total_feature_size': stats.total_feature_size,
                    'total_storage_size': stats.total_storage_size
                },
                'data': {
                    'total_data_points': stats.total_data_points
                },
                'sync': {
                    'last_sync_time': stats.last_sync_time,
                    'pending_syncs': stats.pending_syncs,
                    'sync_conflicts': stats.sync_conflicts
                }
            }
            
        except Exception as e:
            logger.error(f"Get summary report failed: {e}")
            return {'error': str(e)}
    
    def get_chip_statistics(self) -> Dict[str, Dict[str, Any]]:
        """获取按芯片分组的统计信息"""
        try:
            all_experiments = self.find_experiments()
            chip_stats = {}
            
            for exp in all_experiments:
                chip_id = exp.chip_id
                if chip_id not in chip_stats:
                    chip_stats[chip_id] = {
                        'total_experiments': 0,
                        'completed_experiments': 0,
                        'devices': set(),
                        'batches': set(),
                        'has_features': 0,
                        'total_data_points': 0
                    }
                
                stats = chip_stats[chip_id]
                stats['total_experiments'] += 1
                stats['devices'].add(exp.device_id)
                if exp.batch_id:
                    stats['batches'].add(exp.batch_id)
                if exp.is_completed:
                    stats['completed_experiments'] += 1
                if exp.has_features:
                    stats['has_features'] += 1
                stats['total_data_points'] += exp.total_data_points
            
            # 转换set为数量
            for chip_id, stats in chip_stats.items():
                stats['unique_devices'] = len(stats['devices'])
                stats['unique_batches'] = len(stats['batches'])
                stats['completion_rate'] = (stats['completed_experiments'] / 
                                          stats['total_experiments']) if stats['total_experiments'] > 0 else 0
                stats['feature_coverage'] = (stats['has_features'] / 
                                            stats['total_experiments']) if stats['total_experiments'] > 0 else 0
                del stats['devices']
                del stats['batches']
            
            return chip_stats
            
        except Exception as e:
            logger.error(f"Get chip statistics failed: {e}")
            return {}
    
    # ==================== 维护和管理 ====================
    
    def validate_data_integrity(self) -> Dict[str, List[Any]]:
        """验证数据完整性"""
        issues = {
            'missing_raw_files': [],
            'missing_feature_files': [],
            'orphaned_records': [],
            'database_errors': [],
            'metadata_inconsistencies': []
        }
        
        try:
            # 检查数据库完整性
            db_errors = self.repository.check_database_integrity()
            issues['database_errors'] = db_errors
            
            # 检查孤立记录
            orphaned = self.repository.get_orphaned_records()
            issues['orphaned_records'] = [
                {
                    'id': record.id,
                    'test_id': record.test_id,
                    'raw_file_path': record.raw_file_path
                }
                for record in orphaned
            ]
            
            # 检查文件存在性
            all_experiments = self.find_experiments()
            for exp in all_experiments:
                # 检查raw文件
                if exp.raw_file_path:
                    raw_path = self.config.get_absolute_path('raw_data', exp.raw_file_path)
                    if not raw_path.exists():
                        issues['missing_raw_files'].append({
                            'id': exp.id,
                            'test_id': exp.test_id,
                            'path': str(raw_path)
                        })
                
                # 检查feature文件
                if exp.feature_file_path:
                    feature_path = self.config.get_absolute_path('features', exp.feature_file_path)
                    if not feature_path.exists():
                        issues['missing_feature_files'].append({
                            'id': exp.id,
                            'test_id': exp.test_id,
                            'path': str(feature_path)
                        })
            
        except Exception as e:
            logger.error(f"Data integrity validation failed: {e}")
            issues['database_errors'].append(str(e))
        
        return issues
    
    def clean_orphaned_records(self) -> int:
        """清理孤立记录"""
        try:
            return self.repository.clean_orphaned_records()
        except Exception as e:
            logger.error(f"Clean orphaned records failed: {e}")
            return 0
    
    def vacuum_database(self) -> bool:
        """压缩数据库"""
        try:
            self.repository.vacuum_database()
            return True
        except Exception as e:
            logger.error(f"Database vacuum failed: {e}")
            return False
    
    def backup_database(self, backup_path: Optional[str] = None) -> str:
        """
        备份数据库
        
        Args:
            backup_path: 备份文件路径，如果为None则自动生成
            
        Returns:
            str: 备份文件路径
        """
        try:
            if backup_path is None:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_path = f"data/backups/catalog_{timestamp}.db"
            
            self.repository.backup_database(backup_path)
            logger.info(f"Database backup created: {backup_path}")
            return backup_path
            
        except Exception as e:
            error_msg = f"Database backup failed: {e}"
            logger.error(error_msg)
            raise CatalogServiceError(error_msg)
    
    # ==================== 与现有模块集成 ====================
    
    def get_experiment_file_path(self, experiment_id: int, file_type: str = 'raw') -> Optional[str]:
        """
        获取实验文件的绝对路径
        
        Args:
            experiment_id: 实验ID
            file_type: 文件类型 ('raw' 或 'features')
            
        Returns:
            Optional[str]: 文件绝对路径，如果不存在返回None
        """
        try:
            record = self.repository.get_experiment_by_id(experiment_id)
            if not record:
                return None
            
            if file_type == 'raw' and record.raw_file_path:
                return str(self.config.get_absolute_path('raw_data', record.raw_file_path))
            elif file_type == 'features' and record.feature_file_path:
                return str(self.config.get_absolute_path('features', record.feature_file_path))
            
        except Exception as e:
            logger.error(f"Get experiment file path failed: {e}")
        
        return None
    
    def create_experiment_loader(self, experiment_id: int):
        """
        为指定实验创建experiment模块的加载器
        
        Args:
            experiment_id: 实验ID
            
        Returns:
            Experiment: experiment模块的Experiment对象，如果失败返回None
        """
        try:
            file_path = self.get_experiment_file_path(experiment_id, 'raw')
            if file_path and Path(file_path).exists():
                from ..experiment import Experiment
                return Experiment(file_path)
                
        except Exception as e:
            logger.error(f"Create experiment loader failed: {e}")
        
        return None
    
    def create_feature_reader(self, experiment_id: int):
        """
        为指定实验创建features模块的读取器
        
        Args:
            experiment_id: 实验ID
            
        Returns:
            FeatureReader: features模块的FeatureReader对象，如果失败返回None
        """
        try:
            file_path = self.get_experiment_file_path(experiment_id, 'features')
            if file_path and Path(file_path).exists():
                from ..features import FeatureReader
                return FeatureReader(file_path)
                
        except Exception as e:
            logger.error(f"Create feature reader failed: {e}")
        
        return None
    
    def create_plotter(self, experiment_id: int):
        """
        为指定实验创建visualization模块的绘图器
        
        Args:
            experiment_id: 实验ID
            
        Returns:
            OECTPlotter: visualization模块的OECTPlotter对象，如果失败返回None
        """
        try:
            file_path = self.get_experiment_file_path(experiment_id, 'raw')
            if file_path and Path(file_path).exists():
                from ..visualization.plotter import OECTPlotter
                return OECTPlotter(file_path)
                
        except Exception as e:
            logger.error(f"Create plotter failed: {e}")
        
        return None
    
    # ==================== 实用工具方法 ====================
    
    def update_experiment(self, experiment_id: int, **updates) -> bool:
        """
        更新实验记录
        
        Args:
            experiment_id: 实验ID
            **updates: 更新字段
            
        Returns:
            bool: 是否更新成功
        """
        try:
            record = self.repository.get_experiment_by_id(experiment_id)
            if not record:
                return False
            
            # 更新字段
            for key, value in updates.items():
                if hasattr(record, key):
                    setattr(record, key, value)
            
            return self.repository.update_experiment(record)
            
        except Exception as e:
            logger.error(f"Update experiment failed: {e}")
            return False
    
    def delete_experiment(self, experiment_id: int) -> bool:
        """删除实验记录"""
        try:
            return self.repository.delete_experiment(experiment_id)
        except Exception as e:
            logger.error(f"Delete experiment failed: {e}")
            return False
    
    def close(self):
        """关闭catalog服务，释放资源"""
        try:
            # 这里可以添加清理逻辑
            logger.info("CatalogService closed")
        except Exception as e:
            logger.error(f"Error closing CatalogService: {e}")
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()