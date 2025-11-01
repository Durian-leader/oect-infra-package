"""
Catalog模块文件扫描器

负责HDF5文件的发现、扫描和元信息提取，包括：
- 并行文件扫描和发现
- HDF5文件元信息提取
- Raw文件和Features文件的关联匹配
- 增量扫描支持
"""

import os
import logging
import fnmatch
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Tuple, Set
from datetime import datetime
import h5py

from .config import CatalogConfig
from .models import FileRecord, FileDiscoveryResult, ExperimentStatus, DeviceType

logger = logging.getLogger(__name__)


class ScannerError(Exception):
    """扫描器错误"""
    pass


class HDF5MetadataExtractor:
    """HDF5文件元信息提取器"""
    
    @staticmethod
    def decode_hdf5_attr_value(value: Any) -> Any:
        """解码HDF5属性值"""
        if isinstance(value, bytes):
            return value.decode('utf-8')
        elif hasattr(value, 'item'):
            decoded = value.item()
            if isinstance(decoded, bytes):
                return decoded.decode('utf-8')
            return decoded
        return value
    
    @staticmethod
    def safe_decode_attr(attrs_dict: dict, attr_name: str, default: Any = None) -> Any:
        """安全地解码HDF5属性"""
        if attr_name not in attrs_dict:
            return default
        
        try:
            raw_value = attrs_dict[attr_name]
            decoded_value = HDF5MetadataExtractor.decode_hdf5_attr_value(raw_value)
            if isinstance(decoded_value, str) and decoded_value.lower() == 'null':
                return None
            return decoded_value
        except Exception:
            return default
    
    @staticmethod
    def extract_metadata(file_path: str) -> Dict[str, Any]:
        """
        从HDF5文件提取元信息
        
        Args:
            file_path: HDF5文件路径
            
        Returns:
            Dict[str, Any]: 元信息字典
        """
        try:
            with h5py.File(file_path, 'r') as f:
                metadata = {}
                
                # 基本文件信息
                metadata['file_path'] = file_path
                metadata['file_size'] = Path(file_path).stat().st_size
                metadata['file_modified'] = datetime.fromtimestamp(Path(file_path).stat().st_mtime)
                
                # 格式版本
                metadata['format_version'] = HDF5MetadataExtractor.safe_decode_attr(
                    f.attrs, 'format_version', ''
                )
                
                # 实验基本信息
                metadata['chip_id'] = HDF5MetadataExtractor.safe_decode_attr(
                    f.attrs, 'chip_id', ''
                )
                # 根据文件类型选择device_id字段
                file_type = HDF5MetadataExtractor.safe_decode_attr(f.attrs, 'file_type', '')
                if file_type == 'feature':
                    # 特征文件直接使用device_id字段
                    device_id = HDF5MetadataExtractor.safe_decode_attr(f.attrs, 'device_id', '')
                else:
                    # 原始文件使用device_number字段
                    device_id = HDF5MetadataExtractor.safe_decode_attr(f.attrs, 'device_number', '')
                metadata['device_id'] = str(device_id)
                metadata['test_unit_id'] = HDF5MetadataExtractor.safe_decode_attr(
                    f.attrs, 'test_unit_id'
                )
                metadata['description'] = HDF5MetadataExtractor.safe_decode_attr(
                    f.attrs, 'description'
                )
                metadata['test_id'] = HDF5MetadataExtractor.safe_decode_attr(
                    f.attrs, 'test_id', ''
                )
                metadata['batch_id'] = HDF5MetadataExtractor.safe_decode_attr(
                    f.attrs, 'batch_id'
                )
                
                # 实验状态和进度
                status_str = HDF5MetadataExtractor.safe_decode_attr(f.attrs, 'status', 'pending')
                try:
                    metadata['status'] = ExperimentStatus(status_str.lower())
                except (ValueError, AttributeError):
                    metadata['status'] = ExperimentStatus.PENDING
                
                metadata['completion_percentage'] = HDF5MetadataExtractor.safe_decode_attr(
                    f.attrs, 'completion_percentage', 0.0
                )
                metadata['completed_steps'] = HDF5MetadataExtractor.safe_decode_attr(
                    f.attrs, 'completed_steps', 0
                )
                metadata['total_steps'] = HDF5MetadataExtractor.safe_decode_attr(
                    f.attrs, 'num_steps', 0
                )
                
                # 时间信息
                created_at_str = HDF5MetadataExtractor.safe_decode_attr(f.attrs, 'created_at')
                if created_at_str:
                    try:
                        metadata['created_at'] = datetime.fromisoformat(created_at_str)
                    except (ValueError, TypeError):
                        metadata['created_at'] = None
                else:
                    metadata['created_at'] = None
                
                completed_at_str = HDF5MetadataExtractor.safe_decode_attr(f.attrs, 'completed_at')
                if completed_at_str:
                    try:
                        metadata['completed_at'] = datetime.fromisoformat(completed_at_str)
                    except (ValueError, TypeError):
                        metadata['completed_at'] = None
                else:
                    metadata['completed_at'] = None
                
                metadata['duration'] = HDF5MetadataExtractor.safe_decode_attr(f.attrs, 'duration')
                
                # 测试条件
                metadata['temperature'] = HDF5MetadataExtractor.safe_decode_attr(f.attrs, 'temperature')
                metadata['sample_type'] = HDF5MetadataExtractor.safe_decode_attr(f.attrs, 'sample_type')
                
                device_type_str = HDF5MetadataExtractor.safe_decode_attr(f.attrs, 'device_type', 'unknown')
                try:
                    metadata['device_type'] = DeviceType(device_type_str)
                except (ValueError, TypeError):
                    metadata['device_type'] = DeviceType.UNKNOWN
                
                # 数据内容摘要 - 检查批量格式
                metadata.update(HDF5MetadataExtractor._extract_data_summary(f))
                
                return metadata
                
        except Exception as e:
            raise ScannerError(f"Failed to extract metadata from {file_path}: {e}")
    
    @staticmethod
    def _extract_data_summary(hdf5_file: h5py.File) -> Dict[str, Any]:
        """提取数据内容摘要"""
        summary = {
            'has_transfer_data': False,
            'has_transient_data': False,
            'transfer_steps': 0,
            'transient_steps': 0,
            'total_data_points': 0
        }
        
        try:
            # 检查批量格式
            if 'transfer' in hdf5_file and 'measurement_data' in hdf5_file['transfer']:
                summary['has_transfer_data'] = True
                transfer_data = hdf5_file['transfer/measurement_data']
                if len(transfer_data.shape) >= 3:  # [步骤, 数据类型, 数据点]
                    summary['transfer_steps'] = transfer_data.shape[0]
                    summary['total_data_points'] += transfer_data.size
            
            if 'transient' in hdf5_file and 'measurement_data' in hdf5_file['transient']:
                summary['has_transient_data'] = True
                # 从步骤信息表获取步骤数
                if 'step_info_table' in hdf5_file['transient']:
                    step_table = hdf5_file['transient/step_info_table']
                    summary['transient_steps'] = len(step_table)
                
                transient_data = hdf5_file['transient/measurement_data']
                summary['total_data_points'] += transient_data.size
            
            # 如果不是批量格式，检查传统格式
            if not summary['has_transfer_data'] and not summary['has_transient_data']:
                summary.update(HDF5MetadataExtractor._extract_legacy_data_summary(hdf5_file))
                
        except Exception as e:
            logger.warning(f"Failed to extract data summary: {e}")
        
        return summary
    
    @staticmethod
    def _extract_legacy_data_summary(hdf5_file: h5py.File) -> Dict[str, Any]:
        """提取传统格式的数据摘要"""
        summary = {
            'has_transfer_data': False,
            'has_transient_data': False,
            'transfer_steps': 0,
            'transient_steps': 0,
            'total_data_points': 0
        }
        
        try:
            # 扫描step组
            transfer_steps = 0
            transient_steps = 0
            total_points = 0
            
            for key in hdf5_file.keys():
                if key.startswith('step_'):
                    step_group = hdf5_file[key]
                    step_type = HDF5MetadataExtractor.safe_decode_attr(step_group.attrs, 'type', '')
                    
                    if step_type == 'transfer':
                        transfer_steps += 1
                        summary['has_transfer_data'] = True
                        # 计算数据点数
                        if 'Id' in step_group:
                            total_points += len(step_group['Id'])
                    elif step_type == 'transient':
                        transient_steps += 1
                        summary['has_transient_data'] = True
                        if 'Id' in step_group:
                            total_points += len(step_group['Id'])
            
            summary['transfer_steps'] = transfer_steps
            summary['transient_steps'] = transient_steps
            summary['total_data_points'] = total_points
            
        except Exception as e:
            logger.warning(f"Failed to extract legacy data summary: {e}")
        
        return summary


class FileScanner:
    """文件扫描器 - 负责发现和扫描HDF5文件"""
    
    def __init__(self, config: CatalogConfig):
        """
        初始化文件扫描器
        
        Args:
            config: Catalog配置对象
        """
        self.config = config
        self.metadata_extractor = HDF5MetadataExtractor()
    
    def discover_files(self, scan_paths: List[str], incremental: bool = True,
                      known_files: Optional[Set[str]] = None) -> FileDiscoveryResult:
        """
        发现HDF5文件
        
        Args:
            scan_paths: 扫描路径列表
            incremental: 是否增量扫描
            known_files: 已知文件集合（用于增量扫描）
        
        Returns:
            FileDiscoveryResult: 文件发现结果
        """
        start_time = datetime.now()
        result = FileDiscoveryResult()
        
        try:
            # 并行扫描目录
            all_files = []
            with ThreadPoolExecutor(max_workers=self.config.discovery.parallel_workers) as executor:
                futures = []
                for scan_path in scan_paths:
                    future = executor.submit(self._scan_directory, scan_path, known_files if incremental else None)
                    futures.append(future)
                
                for future in as_completed(futures):
                    try:
                        files, errors = future.result()
                        all_files.extend(files)
                        result.errors.extend(errors)
                    except Exception as e:
                        result.errors.append(f"Directory scan failed: {e}")
            
            # 按文件类型分类
            for file_path in all_files:
                result.discovered_files.append(file_path)
                
                # 判断文件类型
                filename = Path(file_path).name
                if self._match_pattern(filename, self.config.discovery.file_patterns.get('raw', '*-test_*.h5')):
                    result.raw_files.append(file_path)
                elif self._match_pattern(filename, self.config.discovery.file_patterns.get('features', '*-feat_*.h5')):
                    result.feature_files.append(file_path)
                elif filename.endswith('.parquet') and '-feat_' in filename:
                    # V2 Parquet 特征文件（暂不处理，元数据已在数据库中）
                    logger.debug(f"发现 V2 特征文件（跳过扫描）: {filename}")
                    pass
                else:
                    result.orphaned_files.append(file_path)
            
            # 计算扫描时间
            end_time = datetime.now()
            result.scan_duration = (end_time - start_time).total_seconds()
            
            logger.info(f"File discovery completed: {len(result.discovered_files)} files found in {result.scan_duration:.2f}s")
            
        except Exception as e:
            result.errors.append(f"File discovery failed: {e}")
            logger.error(f"File discovery failed: {e}")
        
        return result
    
    def _scan_directory(self, directory: str, known_files: Optional[Set[str]] = None) -> Tuple[List[str], List[str]]:
        """
        扫描单个目录
        
        Args:
            directory: 目录路径
            known_files: 已知文件集合
        
        Returns:
            Tuple[List[str], List[str]]: 发现的文件列表和错误列表
        """
        files = []
        errors = []
        
        try:
            dir_path = Path(directory)
            if not dir_path.exists():
                errors.append(f"Directory does not exist: {directory}")
                return files, errors
            
            # 构建文件模式列表
            patterns = [
                self.config.discovery.file_patterns.get('raw', '*-test_*.h5'),
                self.config.discovery.file_patterns.get('features', '*-feat_*.h5'),
                '*-feat_*.parquet',  # V2 特征文件（Parquet格式）
            ]
            
            # 递归扫描文件
            for file_path in self._walk_directory(dir_path, patterns, self.config.discovery.max_depth):
                file_str = str(file_path)
                
                # 增量扫描：跳过已知文件
                if known_files and file_str in known_files:
                    continue
                
                # 检查文件是否应该被忽略
                if self._should_ignore_file(file_path.name):
                    continue
                
                # 验证是否为有效的HDF5文件
                if self._is_valid_hdf5(file_str):
                    files.append(file_str)
                else:
                    errors.append(f"Invalid HDF5 file: {file_str}")
                    
        except Exception as e:
            errors.append(f"Failed to scan directory {directory}: {e}")
        
        return files, errors
    
    def _walk_directory(self, directory: Path, patterns: List[str], max_depth: int, 
                       current_depth: int = 0) -> List[Path]:
        """递归遍历目录"""
        files = []
        
        if current_depth >= max_depth:
            return files
        
        try:
            for item in directory.iterdir():
                if item.is_file():
                    # 检查文件是否匹配模式
                    for pattern in patterns:
                        if self._match_pattern(item.name, pattern):
                            files.append(item)
                            break
                elif item.is_dir() and self.config.discovery.recursive:
                    # 递归扫描子目录
                    if not self._should_ignore_file(item.name):
                        files.extend(self._walk_directory(item, patterns, max_depth, current_depth + 1))
        except PermissionError:
            logger.warning(f"Permission denied for directory: {directory}")
        except Exception as e:
            logger.warning(f"Error walking directory {directory}: {e}")
        
        return files
    
    def _match_pattern(self, filename: str, pattern: str) -> bool:
        """检查文件名是否匹配模式"""
        return fnmatch.fnmatch(filename, pattern)
    
    def _should_ignore_file(self, filename: str) -> bool:
        """检查文件是否应该被忽略"""
        for pattern in self.config.discovery.ignore_patterns:
            if self._match_pattern(filename, pattern):
                return True
        return False
    
    def _is_valid_hdf5(self, file_path: str) -> bool:
        """检查是否为有效的HDF5文件"""
        try:
            with h5py.File(file_path, 'r') as f:
                return True
        except Exception:
            return False
    
    def extract_file_metadata(self, file_paths: List[str]) -> List[Tuple[str, Dict[str, Any], Optional[str]]]:
        """
        并行提取文件元信息
        
        Args:
            file_paths: 文件路径列表
        
        Returns:
            List[Tuple[str, Dict[str, Any], Optional[str]]]: (文件路径, 元信息字典, 错误信息)列表
        """
        results = []
        
        # 使用进程池进行并行处理
        with ProcessPoolExecutor(max_workers=self.config.discovery.parallel_workers) as executor:
            futures = {
                executor.submit(extract_metadata_worker, file_path): file_path 
                for file_path in file_paths
            }
            
            for future in as_completed(futures):
                file_path = futures[future]
                try:
                    metadata = future.result()
                    results.append((file_path, metadata, None))
                except Exception as e:
                    error_msg = f"Failed to extract metadata: {e}"
                    results.append((file_path, {}, error_msg))
        
        return results
    
    def create_file_records(self, metadata_results: List[Tuple[str, Dict[str, Any], Optional[str]]]) -> Tuple[List[FileRecord], List[str]]:
        """
        从元信息创建FileRecord对象
        
        Args:
            metadata_results: 元信息提取结果列表
        
        Returns:
            Tuple[List[FileRecord], List[str]]: 文件记录列表和错误列表
        """
        file_records = []
        errors = []
        
        for file_path, metadata, error in metadata_results:
            if error:
                errors.append(f"{file_path}: {error}")
                continue
            
            try:
                # 确定文件类型
                filename = Path(file_path).name
                is_raw_file = self._match_pattern(filename, self.config.discovery.file_patterns.get('raw', '*-test_*.h5'))
                
                # 转换为相对路径
                if is_raw_file:
                    relative_path = self.config.get_relative_path('raw_data', file_path)
                    feature_path = None
                else:
                    relative_path = None
                    feature_path = self.config.get_relative_path('features', file_path)
                
                # 创建FileRecord
                record = FileRecord(
                    raw_file_path=relative_path if is_raw_file else '',
                    feature_file_path=feature_path,
                    chip_id=metadata.get('chip_id', ''),
                    device_id=metadata.get('device_id', ''),
                    test_unit_id=metadata.get('test_unit_id'),
                    description=metadata.get('description'),
                    test_id=metadata.get('test_id', ''),
                    batch_id=metadata.get('batch_id'),
                    status=metadata.get('status', ExperimentStatus.PENDING),
                    completion_percentage=metadata.get('completion_percentage', 0.0),
                    completed_steps=metadata.get('completed_steps', 0),
                    total_steps=metadata.get('total_steps', 0),
                    created_at=metadata.get('created_at'),
                    completed_at=metadata.get('completed_at'),
                    duration=metadata.get('duration'),
                    temperature=metadata.get('temperature'),
                    sample_type=metadata.get('sample_type'),
                    device_type=metadata.get('device_type', DeviceType.UNKNOWN),
                    has_transfer_data=metadata.get('has_transfer_data', False),
                    has_transient_data=metadata.get('has_transient_data', False),
                    transfer_steps=metadata.get('transfer_steps', 0),
                    transient_steps=metadata.get('transient_steps', 0),
                    total_data_points=metadata.get('total_data_points', 0),
                    raw_file_size=metadata.get('file_size') if is_raw_file else None,
                    feature_file_size=metadata.get('file_size') if not is_raw_file else None,
                    raw_file_modified=metadata.get('file_modified') if is_raw_file else None,
                    feature_file_modified=metadata.get('file_modified') if not is_raw_file else None,
                    db_last_synced=datetime.now()
                )
                
                file_records.append(record)
                
            except Exception as e:
                errors.append(f"Failed to create record for {file_path}: {e}")
        
        return file_records, errors
    
    def associate_files(self, raw_records: List[FileRecord], 
                       feature_records: List[FileRecord]) -> List[FileRecord]:
        """
        关联raw文件和feature文件
        
        Args:
            raw_records: 原始文件记录列表
            feature_records: 特征文件记录列表
        
        Returns:
            List[FileRecord]: 关联后的文件记录列表
        """
        # 创建特征文件映射：(chip_id, device_id) -> feature_record
        feature_map = {}
        for feature_record in feature_records:
            key = (feature_record.chip_id, feature_record.device_id)
            feature_map[key] = feature_record
        
        # 关联文件
        associated_records = []
        
        for raw_record in raw_records:
            key = (raw_record.chip_id, raw_record.device_id)
            feature_record = feature_map.get(key)
            
            if feature_record:
                # 合并记录
                raw_record.feature_file_path = feature_record.feature_file_path
                raw_record.feature_file_size = feature_record.feature_file_size
                raw_record.feature_file_modified = feature_record.feature_file_modified
                
                # 移除已关联的特征记录
                del feature_map[key]
            
            associated_records.append(raw_record)
        
        # 孤立的特征文件不创建独立记录，而是记录为警告
        orphaned_feature_count = len(feature_map)
        if orphaned_feature_count > 0:
            logger.warning(f"Found {orphaned_feature_count} orphaned feature files without corresponding raw files")
        
        return associated_records


def extract_metadata_worker(file_path: str) -> Dict[str, Any]:
    """
    工作进程函数：提取单个文件的元信息
    
    Args:
        file_path: 文件路径
    
    Returns:
        Dict[str, Any]: 元信息字典
    """
    return HDF5MetadataExtractor.extract_metadata(file_path)