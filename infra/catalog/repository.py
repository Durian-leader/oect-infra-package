"""
Catalog模块数据库操作层

实现SQLite数据库的所有操作，包括：
- 数据库连接和表结构管理
- experiments和sync_history表的CRUD操作
- 复杂查询和过滤
- 事务管理和批量操作
"""

import sqlite3
import logging
import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Iterator, Tuple, Union

from .models import (
    FileRecord, SyncHistoryRecord, ExperimentFilter, CatalogStatistics,
    ExperimentStatus, DeviceType, SyncStatus, SyncDirection
)
from .config import CatalogConfig

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """数据库操作错误"""
    pass


class CatalogRepository:
    """Catalog数据库仓库
    
    负责所有数据库操作，包括表管理、CRUD操作、查询等
    """
    
    def __init__(self, config: CatalogConfig):
        """
        初始化数据库仓库
        
        Args:
            config: Catalog配置对象
        """
        self.config = config
        self.db_path = config.get_database_path()
        self._ensure_database_exists()
        self._initialize_tables()
    
    def _ensure_database_exists(self) -> None:
        """确保数据库文件和目录存在"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row  # 启用行字典访问
            conn.execute("PRAGMA foreign_keys = ON")  # 启用外键约束
            return conn
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to connect to database {self.db_path}: {e}")
    
    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        """事务上下文管理器"""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def _initialize_tables(self) -> None:
        """初始化数据库表结构"""
        with self._transaction() as conn:
            cursor = conn.cursor()
            
            # 创建experiments表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS experiments (
                    -- 主键和标识
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    
                    -- 文件路径 (相对路径，基于配置的根目录)
                    raw_file_path TEXT NOT NULL UNIQUE,
                    feature_file_path TEXT,
                    
                    -- 实验标识信息
                    chip_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    test_unit_id TEXT,
                    description TEXT,
                    test_id TEXT NOT NULL UNIQUE,
                    batch_id TEXT,
                    
                    -- 实验状态和进度
                    status TEXT DEFAULT 'pending',
                    completion_percentage REAL DEFAULT 0,
                    completed_steps INTEGER DEFAULT 0,
                    total_steps INTEGER DEFAULT 0,
                    
                    -- 时间信息
                    created_at DATETIME,
                    completed_at DATETIME,
                    duration REAL,
                    
                    -- 测试条件和环境参数
                    temperature REAL,
                    sample_type TEXT,
                    device_type TEXT DEFAULT 'unknown',
                    
                    -- 数据内容摘要
                    has_transfer_data BOOLEAN DEFAULT 0,
                    has_transient_data BOOLEAN DEFAULT 0,
                    transfer_steps INTEGER DEFAULT 0,
                    transient_steps INTEGER DEFAULT 0,
                    total_data_points INTEGER DEFAULT 0,
                    
                    -- 文件信息
                    raw_file_size INTEGER,
                    feature_file_size INTEGER,
                    
                    -- 同步管理字段
                    raw_file_modified DATETIME,
                    feature_file_modified DATETIME,
                    db_last_synced DATETIME NOT NULL,
                    sync_status TEXT DEFAULT 'synced',

                    -- Workflow 元数据（扁平化的 JSON 字符串）
                    workflow_metadata TEXT,

                    -- 约束条件
                    CHECK(completion_percentage >= 0 AND completion_percentage <= 100),
                    CHECK(completed_steps >= 0),
                    CHECK(total_steps >= completed_steps OR total_steps = 0)
                )
            """)

            # 迁移现有数据库：如果 workflow_metadata 列不存在则添加
            try:
                cursor.execute("SELECT workflow_metadata FROM experiments LIMIT 1")
            except sqlite3.OperationalError:
                logger.info("Adding workflow_metadata column to experiments table")
                cursor.execute("ALTER TABLE experiments ADD COLUMN workflow_metadata TEXT")

            # 迁移现有数据库：如果 v2_feature_metadata 列不存在则添加
            try:
                cursor.execute("SELECT v2_feature_metadata FROM experiments LIMIT 1")
            except sqlite3.OperationalError:
                logger.info("Adding v2_feature_metadata column to experiments table")
                cursor.execute("ALTER TABLE experiments ADD COLUMN v2_feature_metadata TEXT")

            # 创建sync_history表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sync_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    experiment_id INTEGER,
                    sync_direction TEXT NOT NULL,
                    sync_timestamp DATETIME NOT NULL,
                    files_processed INTEGER DEFAULT 0,
                    conflicts_resolved INTEGER DEFAULT 0,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    duration REAL,
                    
                    FOREIGN KEY (experiment_id) REFERENCES experiments(id) ON DELETE CASCADE
                )
            """)
            
            # 创建索引
            self._create_indexes(cursor)
    
    def _create_indexes(self, cursor: sqlite3.Cursor) -> None:
        """创建性能优化索引"""
        indexes = [
            # experiments表索引
            "CREATE INDEX IF NOT EXISTS idx_chip_device ON experiments(chip_id, device_id)",
            "CREATE INDEX IF NOT EXISTS idx_status ON experiments(status)",
            "CREATE INDEX IF NOT EXISTS idx_created_at ON experiments(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_batch_id ON experiments(batch_id)",
            "CREATE INDEX IF NOT EXISTS idx_sync_status ON experiments(sync_status)",
            "CREATE INDEX IF NOT EXISTS idx_has_features ON experiments(feature_file_path) WHERE feature_file_path IS NOT NULL",
            "CREATE INDEX IF NOT EXISTS idx_test_id ON experiments(test_id)",
            "CREATE INDEX IF NOT EXISTS idx_device_type ON experiments(device_type)",
            "CREATE INDEX IF NOT EXISTS idx_completion ON experiments(completion_percentage)",
            "CREATE INDEX IF NOT EXISTS idx_workflow_metadata ON experiments(workflow_metadata) WHERE workflow_metadata IS NOT NULL",

            # sync_history表索引
            "CREATE INDEX IF NOT EXISTS idx_sync_timestamp ON sync_history(sync_timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_sync_direction ON sync_history(sync_direction)",
            "CREATE INDEX IF NOT EXISTS idx_sync_experiment ON sync_history(experiment_id)",
        ]

        for index_sql in indexes:
            cursor.execute(index_sql)
    
    # ==================== FileRecord CRUD操作 ====================
    
    def insert_experiment(self, record: FileRecord) -> int:
        """
        插入新的实验记录
        
        Args:
            record: 实验记录
        
        Returns:
            int: 插入记录的ID
        """
        with self._transaction() as conn:
            cursor = conn.cursor()
            
            sql = """
                INSERT INTO experiments (
                    raw_file_path, feature_file_path, chip_id, device_id, test_unit_id, 
                    description, test_id, batch_id, status, completion_percentage,
                    completed_steps, total_steps, created_at, completed_at, duration,
                    temperature, sample_type, device_type, has_transfer_data, 
                    has_transient_data, transfer_steps, transient_steps, total_data_points,
                    raw_file_size, feature_file_size, raw_file_modified, 
                    feature_file_modified, db_last_synced, sync_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            # 安全处理枚举值
            def safe_enum_value(enum_obj):
                if enum_obj is None:
                    return None
                return enum_obj.value if hasattr(enum_obj, 'value') else str(enum_obj)
            
            values = (
                record.raw_file_path, record.feature_file_path, record.chip_id, record.device_id,
                record.test_unit_id, record.description, record.test_id, record.batch_id,
                safe_enum_value(record.status),
                record.completion_percentage, record.completed_steps, record.total_steps,
                record.created_at, record.completed_at, record.duration,
                record.temperature, record.sample_type,
                safe_enum_value(record.device_type),
                record.has_transfer_data, record.has_transient_data,
                record.transfer_steps, record.transient_steps, record.total_data_points,
                record.raw_file_size, record.feature_file_size,
                record.raw_file_modified, record.feature_file_modified,
                record.db_last_synced, safe_enum_value(record.sync_status)
            )
            
            cursor.execute(sql, values)
            return cursor.lastrowid
    
    def update_experiment(self, record: FileRecord) -> bool:
        """
        更新实验记录
        
        Args:
            record: 实验记录，必须包含id
        
        Returns:
            bool: 是否更新成功
        """
        if not record.id:
            raise ValueError("Record must have an id for update")
        
        with self._transaction() as conn:
            cursor = conn.cursor()
            
            # 安全处理枚举值
            def safe_enum_value(enum_obj):
                if enum_obj is None:
                    return None
                return enum_obj.value if hasattr(enum_obj, 'value') else str(enum_obj)
            
            sql = """
                UPDATE experiments SET
                    raw_file_path=?, feature_file_path=?, chip_id=?, device_id=?, test_unit_id=?,
                    description=?, test_id=?, batch_id=?, status=?, completion_percentage=?,
                    completed_steps=?, total_steps=?, created_at=?, completed_at=?, duration=?,
                    temperature=?, sample_type=?, device_type=?, has_transfer_data=?,
                    has_transient_data=?, transfer_steps=?, transient_steps=?, total_data_points=?,
                    raw_file_size=?, feature_file_size=?, raw_file_modified=?,
                    feature_file_modified=?, db_last_synced=?, sync_status=?
                WHERE id=?
            """
            
            values = (
                record.raw_file_path, record.feature_file_path, record.chip_id, record.device_id,
                record.test_unit_id, record.description, record.test_id, record.batch_id,
                safe_enum_value(record.status),
                record.completion_percentage, record.completed_steps, record.total_steps,
                record.created_at, record.completed_at, record.duration,
                record.temperature, record.sample_type,
                safe_enum_value(record.device_type),
                record.has_transfer_data, record.has_transient_data,
                record.transfer_steps, record.transient_steps, record.total_data_points,
                record.raw_file_size, record.feature_file_size,
                record.raw_file_modified, record.feature_file_modified,
                record.db_last_synced, safe_enum_value(record.sync_status),
                record.id
            )
            
            cursor.execute(sql, values)
            return cursor.rowcount > 0
    
    def delete_experiment(self, experiment_id: int) -> bool:
        """
        删除实验记录
        
        Args:
            experiment_id: 实验ID
        
        Returns:
            bool: 是否删除成功
        """
        with self._transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM experiments WHERE id = ?", (experiment_id,))
            return cursor.rowcount > 0
    
    def get_experiment_by_id(self, experiment_id: int) -> Optional[FileRecord]:
        """
        根据ID获取实验记录
        
        Args:
            experiment_id: 实验ID
        
        Returns:
            Optional[FileRecord]: 实验记录，如果不存在则返回None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM experiments WHERE id = ?", (experiment_id,))
            row = cursor.fetchone()
            
            if row:
                return self._row_to_file_record(row)
            return None
    
    def get_experiment_by_test_id(self, test_id: str) -> Optional[FileRecord]:
        """根据test_id获取实验记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM experiments WHERE test_id = ?", (test_id,))
            row = cursor.fetchone()
            
            if row:
                return self._row_to_file_record(row)
            return None
    
    def get_experiment_by_raw_path(self, raw_file_path: str) -> Optional[FileRecord]:
        """根据原始文件路径获取实验记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM experiments WHERE raw_file_path = ?", (raw_file_path,))
            row = cursor.fetchone()
            
            if row:
                return self._row_to_file_record(row)
            return None
    
    def find_experiments(self, filter_obj: ExperimentFilter) -> List[FileRecord]:
        """
        根据过滤条件查找实验记录
        
        Args:
            filter_obj: 过滤条件对象
        
        Returns:
            List[FileRecord]: 匹配的实验记录列表
        """
        sql, params = self._build_filter_query(filter_obj)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            return [self._row_to_file_record(row) for row in rows]
    
    def _build_filter_query(self, filter_obj: ExperimentFilter) -> Tuple[str, List[Any]]:
        """构建过滤查询SQL"""
        sql = "SELECT * FROM experiments WHERE 1=1"
        params = []
        
        # 基本过滤条件
        if filter_obj.chip_id:
            sql += " AND chip_id = ?"
            params.append(filter_obj.chip_id)
        
        if filter_obj.device_id:
            sql += " AND device_id = ?"
            params.append(filter_obj.device_id)
        
        if filter_obj.test_id:
            sql += " AND test_id = ?"
            params.append(filter_obj.test_id)
        
        if filter_obj.batch_id:
            sql += " AND batch_id = ?"
            params.append(filter_obj.batch_id)
        
        def safe_enum_value(enum_obj):
            if enum_obj is None:
                return None
            return enum_obj.value if hasattr(enum_obj, 'value') else str(enum_obj)
        
        if filter_obj.status:
            sql += " AND status = ?"
            params.append(safe_enum_value(filter_obj.status))
        
        if filter_obj.device_type:
            sql += " AND device_type = ?"
            params.append(safe_enum_value(filter_obj.device_type))
        
        # 特征文件过滤
        if filter_obj.has_features is not None:
            if filter_obj.has_features:
                sql += " AND feature_file_path IS NOT NULL AND feature_file_path != ''"
            else:
                sql += " AND (feature_file_path IS NULL OR feature_file_path = '')"
        
        if filter_obj.missing_features:
            sql += " AND (feature_file_path IS NULL OR feature_file_path = '')"
        
        # 数据类型过滤
        if filter_obj.has_transfer_data is not None:
            sql += " AND has_transfer_data = ?"
            params.append(filter_obj.has_transfer_data)
        
        if filter_obj.has_transient_data is not None:
            sql += " AND has_transient_data = ?"
            params.append(filter_obj.has_transient_data)
        
        # 时间范围过滤
        if filter_obj.created_after:
            sql += " AND created_at >= ?"
            params.append(filter_obj.created_after)
        
        if filter_obj.created_before:
            sql += " AND created_at <= ?"
            params.append(filter_obj.created_before)
        
        if filter_obj.completed_after:
            sql += " AND completed_at >= ?"
            params.append(filter_obj.completed_after)
        
        if filter_obj.completed_before:
            sql += " AND completed_at <= ?"
            params.append(filter_obj.completed_before)
        
        # 数值范围过滤
        if filter_obj.min_completion is not None:
            sql += " AND completion_percentage >= ?"
            params.append(filter_obj.min_completion)
        
        if filter_obj.max_completion is not None:
            sql += " AND completion_percentage <= ?"
            params.append(filter_obj.max_completion)
        
        if filter_obj.min_steps is not None:
            sql += " AND total_steps >= ?"
            params.append(filter_obj.min_steps)
        
        if filter_obj.max_steps is not None:
            sql += " AND total_steps <= ?"
            params.append(filter_obj.max_steps)
        
        # 全文搜索
        if filter_obj.text_search:
            search_term = f"%{filter_obj.text_search}%"
            sql += " AND (chip_id LIKE ? OR description LIKE ? OR test_id LIKE ?)"
            params.extend([search_term, search_term, search_term])
        
        # 排序
        if filter_obj.order_by:
            order_direction = "DESC" if filter_obj.order_desc else "ASC"
            sql += f" ORDER BY {filter_obj.order_by} {order_direction}"
        
        # 分页
        if filter_obj.limit:
            sql += " LIMIT ?"
            params.append(filter_obj.limit)
            
            if filter_obj.offset:
                sql += " OFFSET ?"
                params.append(filter_obj.offset)
        
        return sql, params
    
    def _row_to_file_record(self, row: sqlite3.Row) -> FileRecord:
        """将数据库行转换为FileRecord对象"""
        
        # 安全处理枚举值转换
        def safe_enum_convert(enum_class, value, default):
            if not value:
                return default
            try:
                return enum_class(value)
            except (ValueError, TypeError):
                return default
        
        return FileRecord(
            id=row['id'],
            raw_file_path=row['raw_file_path'],
            feature_file_path=row['feature_file_path'],
            chip_id=row['chip_id'],
            device_id=row['device_id'],
            test_unit_id=row['test_unit_id'],
            description=row['description'],
            test_id=row['test_id'],
            batch_id=row['batch_id'],
            status=safe_enum_convert(ExperimentStatus, row['status'], ExperimentStatus.PENDING),
            completion_percentage=row['completion_percentage'] or 0,
            completed_steps=row['completed_steps'] or 0,
            total_steps=row['total_steps'] or 0,
            created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
            completed_at=datetime.fromisoformat(row['completed_at']) if row['completed_at'] else None,
            duration=row['duration'],
            temperature=row['temperature'],
            sample_type=row['sample_type'],
            device_type=safe_enum_convert(DeviceType, row['device_type'], DeviceType.UNKNOWN),
            has_transfer_data=bool(row['has_transfer_data']),
            has_transient_data=bool(row['has_transient_data']),
            transfer_steps=row['transfer_steps'] or 0,
            transient_steps=row['transient_steps'] or 0,
            total_data_points=row['total_data_points'] or 0,
            raw_file_size=row['raw_file_size'],
            feature_file_size=row['feature_file_size'],
            raw_file_modified=datetime.fromisoformat(row['raw_file_modified']) if row['raw_file_modified'] else None,
            feature_file_modified=datetime.fromisoformat(row['feature_file_modified']) if row['feature_file_modified'] else None,
            db_last_synced=datetime.fromisoformat(row['db_last_synced']),
            sync_status=safe_enum_convert(SyncStatus, row['sync_status'], SyncStatus.SYNCED),
            workflow_metadata=row['workflow_metadata'] if 'workflow_metadata' in row.keys() else None
        )
    
    # ==================== SyncHistory CRUD操作 ====================
    
    def insert_sync_history(self, record: SyncHistoryRecord) -> int:
        """插入同步历史记录"""
        with self._transaction() as conn:
            cursor = conn.cursor()
            
            # 安全处理枚举值
            def safe_enum_value(enum_obj):
                if enum_obj is None:
                    return None
                return enum_obj.value if hasattr(enum_obj, 'value') else str(enum_obj)
            
            sql = """
                INSERT INTO sync_history (
                    experiment_id, sync_direction, sync_timestamp, files_processed,
                    conflicts_resolved, status, error_message, duration
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            values = (
                record.experiment_id,
                safe_enum_value(record.sync_direction),
                record.sync_timestamp,
                record.files_processed,
                record.conflicts_resolved,
                record.status,
                record.error_message,
                record.duration
            )
            
            cursor.execute(sql, values)
            return cursor.lastrowid
    
    def get_sync_history(self, experiment_id: Optional[int] = None, 
                        limit: Optional[int] = None) -> List[SyncHistoryRecord]:
        """获取同步历史记录"""
        sql = "SELECT * FROM sync_history"
        params = []
        
        if experiment_id is not None:
            sql += " WHERE experiment_id = ?"
            params.append(experiment_id)
        
        sql += " ORDER BY sync_timestamp DESC"
        
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            return [self._row_to_sync_history_record(row) for row in rows]
    
    def _row_to_sync_history_record(self, row: sqlite3.Row) -> SyncHistoryRecord:
        """将数据库行转换为SyncHistoryRecord对象"""
        return SyncHistoryRecord(
            id=row['id'],
            experiment_id=row['experiment_id'],
            sync_direction=SyncDirection(row['sync_direction']),
            sync_timestamp=datetime.fromisoformat(row['sync_timestamp']),
            files_processed=row['files_processed'],
            conflicts_resolved=row['conflicts_resolved'],
            status=row['status'],
            error_message=row['error_message'],
            duration=row['duration']
        )
    
    # ==================== 批量操作 ====================
    
    def batch_insert_experiments(self, records: List[FileRecord]) -> List[int]:
        """批量插入实验记录"""
        inserted_ids = []
        
        with self._transaction() as conn:
            cursor = conn.cursor()
            
            for record in records:
                sql = """
                    INSERT OR IGNORE INTO experiments (
                        raw_file_path, feature_file_path, chip_id, device_id, test_unit_id, 
                        description, test_id, batch_id, status, completion_percentage,
                        completed_steps, total_steps, created_at, completed_at, duration,
                        temperature, sample_type, device_type, has_transfer_data, 
                        has_transient_data, transfer_steps, transient_steps, total_data_points,
                        raw_file_size, feature_file_size, raw_file_modified, 
                        feature_file_modified, db_last_synced, sync_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                
                values = (
                    record.raw_file_path, record.feature_file_path, record.chip_id, record.device_id,
                    record.test_unit_id, record.description, record.test_id, record.batch_id,
                    record.status.value if record.status else None,
                    record.completion_percentage, record.completed_steps, record.total_steps,
                    record.created_at, record.completed_at, record.duration,
                    record.temperature, record.sample_type,
                    record.device_type.value if record.device_type else None,
                    record.has_transfer_data, record.has_transient_data,
                    record.transfer_steps, record.transient_steps, record.total_data_points,
                    record.raw_file_size, record.feature_file_size,
                    record.raw_file_modified, record.feature_file_modified,
                    record.db_last_synced, record.sync_status.value if record.sync_status else None
                )
                
                cursor.execute(sql, values)
                if cursor.lastrowid:
                    inserted_ids.append(cursor.lastrowid)
        
        return inserted_ids
    
    def batch_update_sync_status(self, experiment_ids: List[int], 
                                sync_status: SyncStatus) -> int:
        """批量更新同步状态"""
        if not experiment_ids:
            return 0
        
        placeholders = ','.join('?' * len(experiment_ids))
        sql = f"UPDATE experiments SET sync_status = ?, db_last_synced = ? WHERE id IN ({placeholders})"
        
        with self._transaction() as conn:
            cursor = conn.cursor()
            params = [sync_status.value, datetime.now()] + experiment_ids
            cursor.execute(sql, params)
            return cursor.rowcount
    
    # ==================== 统计和分析 ====================
    
    def get_statistics(self) -> CatalogStatistics:
        """获取catalog统计信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            stats = CatalogStatistics()
            
            # 基本统计
            cursor.execute("SELECT COUNT(*) FROM experiments")
            stats.total_experiments = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM experiments WHERE status = 'completed'")
            stats.completed_experiments = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM experiments WHERE status = 'running'")
            stats.running_experiments = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM experiments WHERE status = 'failed'")
            stats.failed_experiments = cursor.fetchone()[0]
            
            # 文件统计
            cursor.execute("SELECT COUNT(*) FROM experiments WHERE raw_file_path IS NOT NULL")
            stats.total_raw_files = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM experiments WHERE feature_file_path IS NOT NULL AND feature_file_path != ''")
            stats.total_feature_files = cursor.fetchone()[0]
            
            stats.missing_feature_files = stats.total_experiments - stats.total_feature_files
            
            # 存储统计
            cursor.execute("SELECT SUM(COALESCE(raw_file_size, 0)) FROM experiments")
            result = cursor.fetchone()[0]
            stats.total_raw_size = result or 0
            
            cursor.execute("SELECT SUM(COALESCE(feature_file_size, 0)) FROM experiments")
            result = cursor.fetchone()[0]
            stats.total_feature_size = result or 0
            
            # 数据统计
            cursor.execute("SELECT COUNT(DISTINCT chip_id) FROM experiments")
            stats.unique_chips = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(DISTINCT batch_id) FROM experiments WHERE batch_id IS NOT NULL")
            stats.unique_batches = cursor.fetchone()[0]
            
            cursor.execute("SELECT SUM(COALESCE(total_data_points, 0)) FROM experiments")
            result = cursor.fetchone()[0]
            stats.total_data_points = result or 0
            
            # 同步统计
            cursor.execute("SELECT MAX(sync_timestamp) FROM sync_history")
            last_sync = cursor.fetchone()[0]
            if last_sync:
                stats.last_sync_time = datetime.fromisoformat(last_sync)
            
            cursor.execute("SELECT COUNT(*) FROM experiments WHERE sync_status = 'pending'")
            stats.pending_syncs = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM experiments WHERE sync_status = 'conflict'")
            stats.sync_conflicts = cursor.fetchone()[0]
            
            return stats
    
    # ==================== 维护操作 ====================
    
    def vacuum_database(self) -> None:
        """压缩和优化数据库"""
        with self._get_connection() as conn:
            conn.execute("VACUUM")
    
    def backup_database(self, backup_path: str) -> None:
        """备份数据库"""
        backup_file = Path(backup_path)
        backup_file.parent.mkdir(parents=True, exist_ok=True)
        
        with self._get_connection() as conn:
            with sqlite3.connect(str(backup_file)) as backup:
                conn.backup(backup)
    
    def get_orphaned_records(self) -> List[FileRecord]:
        """获取孤立记录（对应文件不存在的记录）"""
        records = self.find_experiments(ExperimentFilter())
        orphaned = []
        
        for record in records:
            raw_path = self.config.get_absolute_path('raw_data', record.raw_file_path)
            if not raw_path.exists():
                orphaned.append(record)
        
        return orphaned
    
    def clean_orphaned_records(self) -> int:
        """清理孤立记录"""
        orphaned = self.get_orphaned_records()
        cleaned_count = 0
        
        for record in orphaned:
            if self.delete_experiment(record.id):
                cleaned_count += 1
        
        return cleaned_count
    
    def check_database_integrity(self) -> List[str]:
        """检查数据库完整性"""
        errors = []
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 检查外键约束
            cursor.execute("PRAGMA foreign_key_check")
            fk_errors = cursor.fetchall()
            for error in fk_errors:
                errors.append(f"Foreign key constraint violation: {error}")
            
            # 检查完整性
            cursor.execute("PRAGMA integrity_check")
            integrity_result = cursor.fetchone()[0]
            if integrity_result != "ok":
                errors.append(f"Database integrity check failed: {integrity_result}")

        return errors

    # ==================== Workflow Metadata 管理 ====================

    def update_workflow_metadata(self, experiment_id: int, workflow_metadata_json: str) -> bool:
        """
        更新实验的 workflow 元数据

        Args:
            experiment_id: 实验 ID
            workflow_metadata_json: workflow 元数据的 JSON 字符串

        Returns:
            bool: 是否更新成功
        """
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE experiments SET workflow_metadata = ? WHERE id = ?",
                    (workflow_metadata_json, experiment_id)
                )
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to update workflow metadata for experiment {experiment_id}: {e}")
            return False

    def get_workflow_metadata(self, experiment_id: int) -> Optional[str]:
        """
        获取实验的 workflow 元数据 JSON 字符串

        Args:
            experiment_id: 实验 ID

        Returns:
            Optional[str]: workflow 元数据的 JSON 字符串，如果不存在返回 None
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT workflow_metadata FROM experiments WHERE id = ?",
                    (experiment_id,)
                )
                row = cursor.fetchone()
                return row[0] if row else None
        except sqlite3.Error as e:
            logger.error(f"Failed to get workflow metadata for experiment {experiment_id}: {e}")
            return None

    def update_v2_feature_metadata(self, experiment_id: int, metadata: Dict[str, Any]) -> bool:
        """更新实验的 V2 特征元数据

        Args:
            experiment_id: 实验 ID
            metadata: V2 特征元数据字典，将自动转换为 JSON

        Returns:
            bool: 是否更新成功
        """
        try:
            metadata_json = json.dumps(metadata, ensure_ascii=False)

            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE experiments SET v2_feature_metadata = ? WHERE id = ?",
                    (metadata_json, experiment_id)
                )
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to update v2 feature metadata for experiment {experiment_id}: {e}")
            return False

    def get_v2_feature_metadata(self, experiment_id: int) -> Optional[Dict[str, Any]]:
        """获取实验的 V2 特征元数据

        Args:
            experiment_id: 实验 ID

        Returns:
            Optional[Dict]: V2 特征元数据字典，如果不存在返回 None
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT v2_feature_metadata FROM experiments WHERE id = ?",
                    (experiment_id,)
                )
                row = cursor.fetchone()
                if row and row[0]:
                    return json.loads(row[0])
                return None
        except sqlite3.Error as e:
            logger.error(f"Failed to get v2 feature metadata for experiment {experiment_id}: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in v2 feature metadata for experiment {experiment_id}: {e}")
            return None

    def find_experiments_with_v2_features(self, config_name: Optional[str] = None) -> List[FileRecord]:
        """查找包含 V2 特征的实验

        Args:
            config_name: 配置名称过滤（可选）

        Returns:
            List[FileRecord]: 实验记录列表
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                if config_name:
                    # 使用 JSON 查询（SQLite 3.38+ 支持）
                    query = """
                        SELECT * FROM experiments
                        WHERE v2_feature_metadata IS NOT NULL
                        AND v2_feature_metadata LIKE ?
                    """
                    cursor.execute(query, (f'%"{config_name}"%',))
                else:
                    query = "SELECT * FROM experiments WHERE v2_feature_metadata IS NOT NULL"
                    cursor.execute(query)

                rows = cursor.fetchall()
                return [self._row_to_file_record(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Failed to find experiments with v2 features: {e}")
            return []

    def batch_update_workflow_metadata(self, updates: List[Tuple[int, str]]) -> int:
        """
        批量更新 workflow 元数据

        Args:
            updates: [(experiment_id, workflow_metadata_json), ...] 元组列表

        Returns:
            int: 成功更新的记录数
        """
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.executemany(
                    "UPDATE experiments SET workflow_metadata = ? WHERE id = ?",
                    [(json_str, exp_id) for exp_id, json_str in updates]
                )
                return cursor.rowcount
        except sqlite3.Error as e:
            logger.error(f"Failed to batch update workflow metadata: {e}")
            return 0

    def get_experiments_without_workflow_metadata(self) -> List[FileRecord]:
        """
        获取所有没有 workflow 元数据的实验记录

        Returns:
            List[FileRecord]: 没有 workflow 元数据的实验列表
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM experiments
                    WHERE workflow_metadata IS NULL OR workflow_metadata = ''
                """)
                rows = cursor.fetchall()
                return [self._row_to_file_record(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Failed to get experiments without workflow metadata: {e}")
            return []
