"""
Catalog模块数据模型

定义了catalog系统中使用的所有数据模型，包括实验记录、同步结果等。
基于Pydantic提供类型安全和数据验证。
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass
from pydantic import BaseModel, Field, validator


class ExperimentStatus(str, Enum):
    """实验状态枚举"""
    COMPLETED = "completed"
    RUNNING = "running" 
    FAILED = "failed"
    PENDING = "pending"


class DeviceType(str, Enum):
    """器件类型枚举"""
    N_TYPE = "N-type"
    P_TYPE = "P-type"
    UNKNOWN = "unknown"


class SyncStatus(str, Enum):
    """同步状态枚举"""
    SYNCED = "synced"
    PENDING = "pending"
    CONFLICT = "conflict"


class SyncDirection(str, Enum):
    """同步方向枚举"""
    FILE_TO_DB = "file_to_db"
    DB_TO_FILE = "db_to_file"
    BOTH = "both"


class ConflictStrategy(str, Enum):
    """冲突解决策略枚举"""
    TIMESTAMP = "timestamp"  # 基于时间戳自动解决
    MANUAL = "manual"        # 手动解决
    IGNORE = "ignore"        # 忽略冲突


class FileRecord(BaseModel):
    """实验文件记录模型
    
    对应数据库中的experiments表结构
    """
    # 主键和标识
    id: Optional[int] = None
    
    # 文件路径 (相对路径)
    raw_file_path: str = Field(..., description="原始数据文件相对路径")
    feature_file_path: Optional[str] = Field(None, description="特征文件相对路径")
    
    # 实验标识信息
    chip_id: str = Field(..., description="芯片ID")
    device_id: str = Field(..., description="设备ID") 
    test_unit_id: Optional[str] = Field(None, description="测试单元ID")
    description: Optional[str] = Field(None, description="实验描述")
    test_id: str = Field(..., description="测试ID，全局唯一")
    batch_id: Optional[str] = Field(None, description="批次ID")
    
    # 实验状态和进度
    status: Optional[ExperimentStatus] = Field(ExperimentStatus.PENDING, description="实验状态")
    completion_percentage: float = Field(0.0, ge=0, le=100, description="完成百分比")
    completed_steps: int = Field(0, ge=0, description="已完成步骤数")
    total_steps: int = Field(0, ge=0, description="总步骤数")
    
    # 时间信息
    created_at: Optional[datetime] = Field(None, description="实验创建时间")
    completed_at: Optional[datetime] = Field(None, description="实验完成时间")
    duration: Optional[float] = Field(None, ge=0, description="实验持续时间(秒)")
    
    # 测试条件和环境参数
    temperature: Optional[float] = Field(None, description="测试温度")
    sample_type: Optional[str] = Field(None, description="样品类型")
    device_type: Optional[DeviceType] = Field(DeviceType.UNKNOWN, description="器件类型")
    
    # 数据内容摘要
    has_transfer_data: bool = Field(False, description="是否包含transfer数据")
    has_transient_data: bool = Field(False, description="是否包含transient数据")
    transfer_steps: int = Field(0, ge=0, description="transfer步骤数")
    transient_steps: int = Field(0, ge=0, description="transient步骤数")
    total_data_points: int = Field(0, ge=0, description="总数据点数")
    
    # 文件信息
    raw_file_size: Optional[int] = Field(None, ge=0, description="原始文件大小(字节)")
    feature_file_size: Optional[int] = Field(None, ge=0, description="特征文件大小(字节)")
    
    # 同步管理字段
    raw_file_modified: Optional[datetime] = Field(None, description="原始文件最后修改时间")
    feature_file_modified: Optional[datetime] = Field(None, description="特征文件最后修改时间")
    db_last_synced: datetime = Field(default_factory=datetime.now, description="数据库记录最后同步时间")
    sync_status: SyncStatus = Field(SyncStatus.SYNCED, description="同步状态")

    # Workflow 元数据
    workflow_metadata: Optional[str] = Field(None, description="扁平化的 workflow 元数据 JSON 字符串")

    @validator('completed_steps')
    def validate_completed_steps(cls, v, values):
        """验证已完成步骤数不能超过总步骤数"""
        total_steps = values.get('total_steps', 0)
        if total_steps > 0 and v > total_steps:
            raise ValueError('completed_steps cannot exceed total_steps')
        return v
    
    @property
    def has_features(self) -> bool:
        """是否有特征文件"""
        return self.feature_file_path is not None and len(self.feature_file_path.strip()) > 0
    
    @property
    def is_completed(self) -> bool:
        """实验是否已完成"""
        return self.status == ExperimentStatus.COMPLETED
    
    @property
    def progress_ratio(self) -> float:
        """进度比例 (0-1)"""
        return self.completion_percentage / 100.0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.dict()

    class Config:
        use_enum_values = True
        arbitrary_types_allowed = True


class SyncHistoryRecord(BaseModel):
    """同步历史记录模型
    
    对应数据库中的sync_history表结构  
    """
    id: Optional[int] = None
    experiment_id: Optional[int] = Field(None, description="关联的实验ID")
    sync_direction: SyncDirection = Field(..., description="同步方向")
    sync_timestamp: datetime = Field(default_factory=datetime.now, description="同步执行时间")
    files_processed: int = Field(0, ge=0, description="处理的文件数量")
    conflicts_resolved: int = Field(0, ge=0, description="解决的冲突数量")
    status: str = Field(..., description="同步状态: success/partial/failed")
    error_message: Optional[str] = Field(None, description="错误信息")
    duration: Optional[float] = Field(None, ge=0, description="同步耗时(秒)")

    class Config:
        use_enum_values = True


class SyncResult(BaseModel):
    """同步操作结果统计"""
    
    # 处理统计
    files_processed: int = Field(0, ge=0, description="处理的文件总数")
    files_added: int = Field(0, ge=0, description="新增的文件记录数")
    files_updated: int = Field(0, ge=0, description="更新的文件记录数") 
    files_skipped: int = Field(0, ge=0, description="跳过的文件数")
    files_failed: int = Field(0, ge=0, description="处理失败的文件数")
    
    # 冲突处理
    conflicts_detected: int = Field(0, ge=0, description="检测到的冲突数")
    conflicts_resolved: int = Field(0, ge=0, description="解决的冲突数")
    conflicts_pending: int = Field(0, ge=0, description="待处理的冲突数")
    
    # 时间统计
    start_time: datetime = Field(default_factory=datetime.now, description="开始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")
    duration: Optional[float] = Field(None, ge=0, description="总耗时(秒)")
    
    # 错误信息
    errors: List[str] = Field(default_factory=list, description="错误消息列表")
    warnings: List[str] = Field(default_factory=list, description="警告消息列表")
    
    @property
    def success_rate(self) -> float:
        """成功率计算"""
        if self.files_processed == 0:
            return 1.0
        return (self.files_processed - self.files_failed) / self.files_processed
    
    @property
    def is_successful(self) -> bool:
        """同步是否成功"""
        return self.files_failed == 0 and len(self.errors) == 0
    
    def add_error(self, error: str):
        """添加错误信息"""
        self.errors.append(error)
        
    def add_warning(self, warning: str):
        """添加警告信息"""
        self.warnings.append(warning)
        
    def finish(self):
        """标记同步完成"""
        self.end_time = datetime.now()
        if self.start_time and self.end_time:
            self.duration = (self.end_time - self.start_time).total_seconds()


class ExperimentFilter(BaseModel):
    """实验查询过滤条件"""
    
    # 基本过滤条件
    chip_id: Optional[str] = Field(None, description="芯片ID")
    device_id: Optional[str] = Field(None, description="设备ID")
    test_id: Optional[str] = Field(None, description="测试ID")
    batch_id: Optional[str] = Field(None, description="批次ID")
    status: Optional[ExperimentStatus] = Field(None, description="实验状态")
    device_type: Optional[DeviceType] = Field(None, description="器件类型")
    
    # 特征文件过滤
    has_features: Optional[bool] = Field(None, description="是否有特征文件")
    missing_features: Optional[bool] = Field(None, description="缺少特征文件")
    
    # 数据类型过滤  
    has_transfer_data: Optional[bool] = Field(None, description="是否有transfer数据")
    has_transient_data: Optional[bool] = Field(None, description="是否有transient数据")
    
    # 时间范围过滤
    created_after: Optional[datetime] = Field(None, description="创建时间起始")
    created_before: Optional[datetime] = Field(None, description="创建时间截止")
    completed_after: Optional[datetime] = Field(None, description="完成时间起始")
    completed_before: Optional[datetime] = Field(None, description="完成时间截止")
    
    # 数值范围过滤
    min_completion: Optional[float] = Field(None, ge=0, le=100, description="最小完成度")
    max_completion: Optional[float] = Field(None, ge=0, le=100, description="最大完成度")
    min_steps: Optional[int] = Field(None, ge=0, description="最小步骤数")
    max_steps: Optional[int] = Field(None, ge=0, description="最大步骤数")
    
    # 全文搜索
    text_search: Optional[str] = Field(None, description="全文搜索关键词")
    
    # 排序和分页
    order_by: Optional[str] = Field("created_at", description="排序字段")
    order_desc: bool = Field(True, description="是否降序排列")
    limit: Optional[int] = Field(None, ge=1, description="结果数量限制")
    offset: Optional[int] = Field(None, ge=0, description="结果偏移量")

    class Config:
        use_enum_values = True


class FileDiscoveryResult(BaseModel):
    """文件发现结果"""
    
    discovered_files: List[str] = Field(default_factory=list, description="发现的文件路径列表")
    raw_files: List[str] = Field(default_factory=list, description="原始数据文件列表")
    feature_files: List[str] = Field(default_factory=list, description="特征文件列表")
    orphaned_files: List[str] = Field(default_factory=list, description="孤立文件列表")
    scan_duration: Optional[float] = Field(None, ge=0, description="扫描耗时(秒)")
    errors: List[str] = Field(default_factory=list, description="扫描错误列表")
    
    @property
    def total_files(self) -> int:
        """总文件数"""
        return len(self.discovered_files)
    
    @property
    def has_errors(self) -> bool:
        """是否有扫描错误"""
        return len(self.errors) > 0


@dataclass
class DatabaseConfig:
    """数据库配置"""
    path: str
    auto_backup: bool = False
    backup_interval: int = 86400  # 24小时
    connection_pool_size: int = 10


@dataclass  
class SyncConfig:
    """同步配置"""
    auto_sync: bool = False
    auto_sync_interval: int = 3600  # 1小时
    conflict_strategy: ConflictStrategy = ConflictStrategy.TIMESTAMP
    batch_size: int = 100
    timeout: int = 300  # 5分钟


@dataclass
class DiscoveryConfig:
    """文件发现配置"""
    recursive: bool = True
    max_depth: int = 10
    parallel_workers: int = 4
    file_patterns: Dict[str, str] = None
    ignore_patterns: List[str] = None
    
    def __post_init__(self):
        if self.file_patterns is None:
            self.file_patterns = {
                "raw": "*-test_*.h5",
                "features": "*-feat_*.h5"
            }
        if self.ignore_patterns is None:
            self.ignore_patterns = ["*.tmp", ".*", "_*"]


class CatalogStatistics(BaseModel):
    """Catalog统计信息"""
    
    # 基本统计
    total_experiments: int = Field(0, ge=0, description="实验总数")
    completed_experiments: int = Field(0, ge=0, description="已完成实验数")
    running_experiments: int = Field(0, ge=0, description="运行中实验数")
    failed_experiments: int = Field(0, ge=0, description="失败实验数")
    
    # 文件统计
    total_raw_files: int = Field(0, ge=0, description="原始文件总数")
    total_feature_files: int = Field(0, ge=0, description="特征文件总数")
    missing_feature_files: int = Field(0, ge=0, description="缺少特征文件数")
    
    # 存储统计
    total_raw_size: int = Field(0, ge=0, description="原始文件总大小(字节)")
    total_feature_size: int = Field(0, ge=0, description="特征文件总大小(字节)")
    
    # 数据统计
    unique_chips: int = Field(0, ge=0, description="唯一芯片数")
    unique_batches: int = Field(0, ge=0, description="唯一批次数")
    total_data_points: int = Field(0, ge=0, description="总数据点数")
    
    # 同步统计
    last_sync_time: Optional[datetime] = Field(None, description="最后同步时间")
    pending_syncs: int = Field(0, ge=0, description="待同步记录数")
    sync_conflicts: int = Field(0, ge=0, description="同步冲突数")
    
    @property
    def completion_rate(self) -> float:
        """完成率"""
        if self.total_experiments == 0:
            return 0.0
        return self.completed_experiments / self.total_experiments
    
    @property
    def feature_coverage(self) -> float:
        """特征文件覆盖率"""
        if self.total_experiments == 0:
            return 0.0
        return self.total_feature_files / self.total_experiments
        
    @property
    def total_storage_size(self) -> int:
        """总存储大小"""
        return self.total_raw_size + self.total_feature_size