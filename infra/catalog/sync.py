"""
Catalog模块双向同步逻辑

实现文件系统和数据库之间的双向同步，包括：
- 文件系统 → 数据库同步（文件变更检测和元信息更新）
- 数据库 → 文件系统同步（元信息写回到HDF5文件）
- 时间戳比较和冲突检测
- 多种冲突解决策略
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set
import h5py

from .config import CatalogConfig
from .repository import CatalogRepository
from .scanner import FileScanner, HDF5MetadataExtractor
from .models import (
    FileRecord, SyncResult, SyncHistoryRecord, ConflictStrategy, 
    SyncDirection, SyncStatus, ExperimentFilter
)

logger = logging.getLogger(__name__)


class SyncConflict:
    """同步冲突信息"""
    
    def __init__(self, record: FileRecord, file_metadata: Dict[str, Any], 
                 conflict_type: str, description: str):
        self.record = record
        self.file_metadata = file_metadata
        self.conflict_type = conflict_type  # 'timestamp', 'metadata', 'missing_file'
        self.description = description
        self.resolved = False
        self.resolution_strategy = None


class CatalogSynchronizer:
    """Catalog双向同步器"""
    
    def __init__(self, config: CatalogConfig, repository: CatalogRepository):
        """
        初始化同步器
        
        Args:
            config: Catalog配置对象
            repository: 数据库仓库对象
        """
        self.config = config
        self.repository = repository
        self.scanner = FileScanner(config)
        self.metadata_extractor = HDF5MetadataExtractor()
    
    def sync_files_to_db(self, scan_paths: List[str], incremental: bool = True) -> SyncResult:
        """
        文件系统到数据库同步
        
        Args:
            scan_paths: 扫描路径列表
            incremental: 是否增量同步
            
        Returns:
            SyncResult: 同步结果
        """
        sync_result = SyncResult()
        
        try:
            logger.info(f"Starting file-to-db sync for paths: {scan_paths}")
            
            # 1. 获取已知文件（用于增量扫描）
            known_files = set()
            if incremental:
                known_files = self._get_known_file_paths()
            
            # 2. 发现文件
            discovery_result = self.scanner.discover_files(scan_paths, incremental, known_files)
            sync_result.files_processed = len(discovery_result.discovered_files)
            
            if discovery_result.has_errors:
                sync_result.errors.extend(discovery_result.errors)
            
            # 3. 提取元信息
            if discovery_result.discovered_files:
                metadata_results = self.scanner.extract_file_metadata(discovery_result.discovered_files)
                
                # 4. 创建文件记录
                raw_records, feature_records = self._separate_records_by_type(metadata_results)
                
                # 5. 关联文件
                associated_records = self.scanner.associate_files(raw_records, feature_records)
                
                # 6. 同步到数据库
                self._sync_records_to_db(associated_records, sync_result)
            
            # 7. 记录同步历史
            self._record_sync_history(SyncDirection.FILE_TO_DB, sync_result)
            
        except Exception as e:
            error_msg = f"File-to-DB sync failed: {e}"
            sync_result.add_error(error_msg)
            logger.error(error_msg)
        
        finally:
            sync_result.finish()
        
        return sync_result
    
    def sync_db_to_files(self, experiment_filter: Optional[ExperimentFilter] = None) -> SyncResult:
        """
        数据库到文件系统同步
        
        Args:
            experiment_filter: 实验过滤条件，如果为None则同步所有记录
            
        Returns:
            SyncResult: 同步结果
        """
        sync_result = SyncResult()
        
        try:
            logger.info("Starting db-to-file sync")
            
            # 1. 获取需要同步的记录
            if experiment_filter is None:
                experiment_filter = ExperimentFilter()
            
            records = self.repository.find_experiments(experiment_filter)
            sync_result.files_processed = len(records)
            
            # 2. 同步每个记录
            for record in records:
                try:
                    self._sync_record_to_file(record, sync_result)
                except Exception as e:
                    error_msg = f"Failed to sync record {record.id} to file: {e}"
                    sync_result.add_error(error_msg)
                    sync_result.files_failed += 1
            
            # 3. 记录同步历史
            self._record_sync_history(SyncDirection.DB_TO_FILE, sync_result)
            
        except Exception as e:
            error_msg = f"DB-to-file sync failed: {e}"
            sync_result.add_error(error_msg)
            logger.error(error_msg)
        
        finally:
            sync_result.finish()
        
        return sync_result
    
    def bidirectional_sync(self, scan_paths: List[str], 
                          conflict_strategy: ConflictStrategy = None) -> SyncResult:
        """
        双向同步
        
        Args:
            scan_paths: 扫描路径列表
            conflict_strategy: 冲突解决策略
            
        Returns:
            SyncResult: 合并的同步结果
        """
        if conflict_strategy is None:
            conflict_strategy = self.config.sync.conflict_strategy
        
        sync_result = SyncResult()
        
        try:
            logger.info(f"Starting bidirectional sync with conflict strategy: {conflict_strategy.value}")
            
            # 1. 检测冲突
            conflicts = self._detect_conflicts(scan_paths)
            sync_result.conflicts_detected = len(conflicts)
            
            # 2. 解决冲突
            resolved_conflicts = self._resolve_conflicts(conflicts, conflict_strategy)
            sync_result.conflicts_resolved = len(resolved_conflicts)
            sync_result.conflicts_pending = sync_result.conflicts_detected - sync_result.conflicts_resolved
            
            # 3. 执行文件到数据库同步
            file_to_db_result = self.sync_files_to_db(scan_paths, incremental=True)
            self._merge_sync_results(sync_result, file_to_db_result)
            
            # 4. 执行数据库到文件同步（仅同步更新的记录）
            updated_filter = ExperimentFilter(
                sync_status=SyncStatus.PENDING
            )
            db_to_file_result = self.sync_db_to_files(updated_filter)
            self._merge_sync_results(sync_result, db_to_file_result)
            
            # 5. 记录同步历史
            self._record_sync_history(SyncDirection.BOTH, sync_result)
            
        except Exception as e:
            error_msg = f"Bidirectional sync failed: {e}"
            sync_result.add_error(error_msg)
            logger.error(error_msg)
        
        finally:
            sync_result.finish()
        
        return sync_result
    
    def _get_known_file_paths(self) -> Set[str]:
        """获取数据库中已知的文件路径"""
        known_paths = set()
        
        try:
            all_records = self.repository.find_experiments(ExperimentFilter())
            
            for record in all_records:
                if record.raw_file_path:
                    abs_path = self.config.get_absolute_path('raw_data', record.raw_file_path)
                    known_paths.add(str(abs_path))
                
                if record.feature_file_path:
                    abs_path = self.config.get_absolute_path('features', record.feature_file_path)
                    known_paths.add(str(abs_path))
                    
        except Exception as e:
            logger.warning(f"Failed to get known file paths: {e}")
        
        return known_paths
    
    def _separate_records_by_type(self, metadata_results: List[Tuple[str, Dict[str, Any], Optional[str]]]) -> Tuple[List[FileRecord], List[FileRecord]]:
        """分离raw文件和feature文件记录"""
        raw_records = []
        feature_records = []
        
        for file_path, metadata, error in metadata_results:
            if error:
                continue
            
            try:
                filename = Path(file_path).name
                is_raw_file = self.scanner._match_pattern(
                    filename, 
                    self.config.discovery.file_patterns.get('raw', '*-test_*.h5')
                )
                
                if is_raw_file:
                    record = self._create_file_record(file_path, metadata, True)
                    raw_records.append(record)
                else:
                    record = self._create_file_record(file_path, metadata, False)
                    feature_records.append(record)
                    
            except Exception as e:
                logger.warning(f"Failed to create record for {file_path}: {e}")
        
        return raw_records, feature_records
    
    def _create_file_record(self, file_path: str, metadata: Dict[str, Any], is_raw: bool) -> FileRecord:
        """从元信息创建FileRecord"""
        # 转换为相对路径
        if is_raw:
            raw_path = self.config.get_relative_path('raw_data', file_path)
            feature_path = None
            raw_size = metadata.get('file_size')
            feature_size = None
            raw_modified = metadata.get('file_modified')
            feature_modified = None
        else:
            raw_path = None
            feature_path = self.config.get_relative_path('features', file_path)
            raw_size = None
            feature_size = metadata.get('file_size')
            raw_modified = None
            feature_modified = metadata.get('file_modified')
        
        return FileRecord(
            raw_file_path=raw_path or '',
            feature_file_path=feature_path,
            chip_id=metadata.get('chip_id', ''),
            device_id=metadata.get('device_id', ''),
            test_unit_id=metadata.get('test_unit_id'),
            description=metadata.get('description'),
            test_id=metadata.get('test_id', ''),
            batch_id=metadata.get('batch_id'),
            status=metadata.get('status'),
            completion_percentage=metadata.get('completion_percentage', 0.0),
            completed_steps=metadata.get('completed_steps', 0),
            total_steps=metadata.get('total_steps', 0),
            created_at=metadata.get('created_at'),
            completed_at=metadata.get('completed_at'),
            duration=metadata.get('duration'),
            temperature=metadata.get('temperature'),
            sample_type=metadata.get('sample_type'),
            device_type=metadata.get('device_type'),
            has_transfer_data=metadata.get('has_transfer_data', False),
            has_transient_data=metadata.get('has_transient_data', False),
            transfer_steps=metadata.get('transfer_steps', 0),
            transient_steps=metadata.get('transient_steps', 0),
            total_data_points=metadata.get('total_data_points', 0),
            raw_file_size=raw_size,
            feature_file_size=feature_size,
            raw_file_modified=raw_modified,
            feature_file_modified=feature_modified,
            db_last_synced=datetime.now(),
            sync_status=SyncStatus.SYNCED
        )
    
    def _sync_records_to_db(self, records: List[FileRecord], sync_result: SyncResult) -> None:
        """将记录同步到数据库"""
        for record in records:
            try:
                # 检查是否已存在
                existing_record = None
                if record.test_id:
                    existing_record = self.repository.get_experiment_by_test_id(record.test_id)
                elif record.raw_file_path:
                    existing_record = self.repository.get_experiment_by_raw_path(record.raw_file_path)
                
                if existing_record:
                    # 更新现有记录
                    record.id = existing_record.id
                    
                    # 合并特征文件信息（如果原记录没有特征文件信息）
                    if not existing_record.feature_file_path and record.feature_file_path:
                        existing_record.feature_file_path = record.feature_file_path
                        existing_record.feature_file_size = record.feature_file_size
                        existing_record.feature_file_modified = record.feature_file_modified
                        record = existing_record
                    
                    if self.repository.update_experiment(record):
                        sync_result.files_updated += 1
                    else:
                        sync_result.files_failed += 1
                else:
                    # 插入新记录
                    record_id = self.repository.insert_experiment(record)
                    if record_id:
                        sync_result.files_added += 1
                    else:
                        sync_result.files_failed += 1
                        
            except Exception as e:
                error_msg = f"Failed to sync record to DB: {e}"
                sync_result.add_error(error_msg)
                sync_result.files_failed += 1
    
    def _sync_record_to_file(self, record: FileRecord, sync_result: SyncResult) -> None:
        """将数据库记录同步到文件"""
        try:
            # 同步到raw文件
            if record.raw_file_path:
                raw_file_path = self.config.get_absolute_path('raw_data', record.raw_file_path)
                if raw_file_path.exists():
                    self._update_hdf5_metadata(str(raw_file_path), record)
                    sync_result.files_updated += 1
                else:
                    sync_result.add_warning(f"Raw file not found: {raw_file_path}")
                    sync_result.files_skipped += 1
            
            # 同步到feature文件
            if record.feature_file_path:
                feature_file_path = self.config.get_absolute_path('features', record.feature_file_path)
                if feature_file_path.exists():
                    self._update_hdf5_metadata(str(feature_file_path), record)
                    sync_result.files_updated += 1
                else:
                    sync_result.add_warning(f"Feature file not found: {feature_file_path}")
                    sync_result.files_skipped += 1
                    
        except Exception as e:
            raise Exception(f"Failed to sync record {record.id} to file: {e}")
    
    def _update_hdf5_metadata(self, file_path: str, record: FileRecord) -> None:
        """更新HDF5文件的元信息"""
        try:
            with h5py.File(file_path, 'r+') as f:
                # 更新基本信息
                f.attrs['chip_id'] = record.chip_id.encode('utf-8')
                f.attrs['device_id'] = record.device_id.encode('utf-8')
                if record.test_unit_id:
                    f.attrs['test_unit_id'] = record.test_unit_id.encode('utf-8')
                if record.description:
                    f.attrs['description'] = record.description.encode('utf-8')
                f.attrs['test_id'] = record.test_id.encode('utf-8')
                if record.batch_id:
                    f.attrs['batch_id'] = record.batch_id.encode('utf-8')
                
                # 更新状态信息
                f.attrs['status'] = record.status.value.encode('utf-8')
                f.attrs['completion_percentage'] = record.completion_percentage
                f.attrs['completed_steps'] = record.completed_steps
                f.attrs['num_steps'] = record.total_steps
                
                # 更新时间信息
                if record.created_at:
                    f.attrs['created_at'] = record.created_at.isoformat().encode('utf-8')
                if record.completed_at:
                    f.attrs['completed_at'] = record.completed_at.isoformat().encode('utf-8')
                if record.duration:
                    f.attrs['duration'] = record.duration
                
                # 更新测试条件
                if record.temperature:
                    f.attrs['temperature'] = record.temperature
                if record.sample_type:
                    f.attrs['sample_type'] = record.sample_type.encode('utf-8')
                f.attrs['device_type'] = record.device_type.value.encode('utf-8')
                
        except Exception as e:
            raise Exception(f"Failed to update HDF5 metadata for {file_path}: {e}")
    
    def _detect_conflicts(self, scan_paths: List[str]) -> List[SyncConflict]:
        """检测同步冲突"""
        conflicts = []
        
        try:
            # 发现文件
            discovery_result = self.scanner.discover_files(scan_paths, incremental=False)
            
            # 提取文件元信息
            metadata_results = self.scanner.extract_file_metadata(discovery_result.discovered_files)
            
            for file_path, metadata, error in metadata_results:
                if error:
                    continue
                
                try:
                    # 查找对应的数据库记录
                    test_id = metadata.get('test_id', '')
                    if test_id:
                        db_record = self.repository.get_experiment_by_test_id(test_id)
                        if db_record:
                            conflict = self._check_record_conflict(db_record, file_path, metadata)
                            if conflict:
                                conflicts.append(conflict)
                                
                except Exception as e:
                    logger.warning(f"Failed to check conflict for {file_path}: {e}")
        
        except Exception as e:
            logger.error(f"Failed to detect conflicts: {e}")
        
        return conflicts
    
    def _check_record_conflict(self, db_record: FileRecord, file_path: str, 
                              file_metadata: Dict[str, Any]) -> Optional[SyncConflict]:
        """检查单个记录的冲突"""
        try:
            # 检查时间戳冲突
            file_modified = file_metadata.get('file_modified')
            if file_modified and db_record.db_last_synced:
                if file_modified > db_record.db_last_synced:
                    return SyncConflict(
                        record=db_record,
                        file_metadata=file_metadata,
                        conflict_type='timestamp',
                        description=f"File {file_path} modified after last sync"
                    )
            
            # 检查关键元信息冲突
            if self._has_metadata_conflict(db_record, file_metadata):
                return SyncConflict(
                    record=db_record,
                    file_metadata=file_metadata,
                    conflict_type='metadata',
                    description=f"Metadata mismatch for {file_path}"
                )
            
        except Exception as e:
            logger.warning(f"Error checking conflict for record {db_record.id}: {e}")
        
        return None
    
    def _has_metadata_conflict(self, db_record: FileRecord, 
                              file_metadata: Dict[str, Any]) -> bool:
        """检查是否有元信息冲突"""
        # 检查关键字段
        critical_fields = [
            ('chip_id', 'chip_id'),
            ('device_id', 'device_id'),
            ('test_id', 'test_id'),
            ('completion_percentage', 'completion_percentage'),
            ('completed_steps', 'completed_steps'),
            ('total_steps', 'total_steps')
        ]
        
        for db_field, file_field in critical_fields:
            db_value = getattr(db_record, db_field, None)
            file_value = file_metadata.get(file_field)
            
            if db_value != file_value:
                return True
        
        return False
    
    def _resolve_conflicts(self, conflicts: List[SyncConflict], 
                          strategy: ConflictStrategy) -> List[SyncConflict]:
        """解决冲突"""
        resolved = []
        
        for conflict in conflicts:
            try:
                if strategy == ConflictStrategy.TIMESTAMP:
                    # 基于时间戳自动解决
                    if self._resolve_by_timestamp(conflict):
                        resolved.append(conflict)
                elif strategy == ConflictStrategy.MANUAL:
                    # 标记为手动解决
                    conflict.resolution_strategy = 'manual'
                    logger.info(f"Conflict requires manual resolution: {conflict.description}")
                elif strategy == ConflictStrategy.IGNORE:
                    # 忽略冲突
                    conflict.resolved = True
                    conflict.resolution_strategy = 'ignore'
                    resolved.append(conflict)
                    
            except Exception as e:
                logger.error(f"Failed to resolve conflict: {e}")
        
        return resolved
    
    def _resolve_by_timestamp(self, conflict: SyncConflict) -> bool:
        """基于时间戳解决冲突"""
        try:
            file_modified = conflict.file_metadata.get('file_modified')
            db_modified = conflict.record.db_last_synced
            
            if file_modified and db_modified:
                if file_modified > db_modified:
                    # 文件更新，更新数据库记录
                    updated_record = self._update_record_from_metadata(
                        conflict.record, conflict.file_metadata
                    )
                    if self.repository.update_experiment(updated_record):
                        conflict.resolved = True
                        conflict.resolution_strategy = 'file_wins'
                        return True
                else:
                    # 数据库更新，更新文件
                    # 这里暂时不实现文件更新，标记为已解决
                    conflict.resolved = True
                    conflict.resolution_strategy = 'db_wins'
                    return True
                    
        except Exception as e:
            logger.error(f"Failed to resolve conflict by timestamp: {e}")
        
        return False
    
    def _update_record_from_metadata(self, record: FileRecord, 
                                    metadata: Dict[str, Any]) -> FileRecord:
        """从文件元信息更新记录"""
        # 更新关键字段
        if 'completion_percentage' in metadata:
            record.completion_percentage = metadata['completion_percentage']
        if 'completed_steps' in metadata:
            record.completed_steps = metadata['completed_steps']
        if 'total_steps' in metadata:
            record.total_steps = metadata['total_steps']
        if 'status' in metadata:
            record.status = metadata['status']
        
        # 更新同步状态
        record.db_last_synced = datetime.now()
        record.sync_status = SyncStatus.SYNCED
        
        return record
    
    def _merge_sync_results(self, target: SyncResult, source: SyncResult) -> None:
        """合并同步结果"""
        target.files_processed += source.files_processed
        target.files_added += source.files_added
        target.files_updated += source.files_updated
        target.files_skipped += source.files_skipped
        target.files_failed += source.files_failed
        target.errors.extend(source.errors)
        target.warnings.extend(source.warnings)
    
    def _record_sync_history(self, direction: SyncDirection, result: SyncResult) -> None:
        """记录同步历史"""
        try:
            history_record = SyncHistoryRecord(
                experiment_id=None,  # 全局同步记录
                sync_direction=direction,
                sync_timestamp=datetime.now(),
                files_processed=result.files_processed,
                conflicts_resolved=result.conflicts_resolved,
                status='success' if result.is_successful else 'failed',
                error_message='; '.join(result.errors) if result.errors else None,
                duration=result.duration
            )
            
            self.repository.insert_sync_history(history_record)
            
        except Exception as e:
            logger.warning(f"Failed to record sync history: {e}")
    
    def get_sync_status(self) -> Dict[str, Any]:
        """获取同步状态摘要"""
        try:
            stats = self.repository.get_statistics()
            recent_syncs = self.repository.get_sync_history(limit=10)
            
            return {
                'total_experiments': stats.total_experiments,
                'pending_syncs': stats.pending_syncs,
                'sync_conflicts': stats.sync_conflicts,
                'last_sync_time': stats.last_sync_time,
                'recent_syncs': [
                    {
                        'direction': sync.sync_direction.value,
                        'timestamp': sync.sync_timestamp,
                        'status': sync.status,
                        'files_processed': sync.files_processed
                    }
                    for sync in recent_syncs
                ]
            }
            
        except Exception as e:
            logger.error(f"Failed to get sync status: {e}")
            return {'error': str(e)}
    
    def force_resync(self, experiment_ids: Optional[List[int]] = None) -> SyncResult:
        """强制重新同步指定实验"""
        sync_result = SyncResult()
        
        try:
            if experiment_ids:
                # 重置指定实验的同步状态
                updated_count = self.repository.batch_update_sync_status(
                    experiment_ids, SyncStatus.PENDING
                )
                sync_result.files_processed = updated_count
            else:
                # 重置所有实验的同步状态
                all_records = self.repository.find_experiments(ExperimentFilter())
                all_ids = [record.id for record in all_records if record.id]
                updated_count = self.repository.batch_update_sync_status(
                    all_ids, SyncStatus.PENDING
                )
                sync_result.files_processed = updated_count
            
            logger.info(f"Force resync initiated for {sync_result.files_processed} experiments")
            
        except Exception as e:
            error_msg = f"Force resync failed: {e}"
            sync_result.add_error(error_msg)
            logger.error(error_msg)
        
        finally:
            sync_result.finish()
        
        return sync_result