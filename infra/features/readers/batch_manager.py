"""
批量文件管理器

支持按条件筛选和批量操作多个特征文件
"""
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any, Union, Tuple, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

########################### 日志设置 ################################
from ...logger_config import get_module_logger
logger = get_module_logger()
#####################################################################

from ..models.feature_data import FeatureData
from ..readers.feature_reader import FeatureReader


class BatchManager:
    """
    批量文件管理器
    
    提供批量特征文件的发现、筛选和操作功能：
    - 按芯片、设备、描述等条件筛选特征文件
    - 批量读取多个文件的特征数据
    - 跨文件的特征数据聚合和分析
    - 支持并行处理提高处理速度
    """
    
    def __init__(self, features_dir: str):
        """
        初始化批量文件管理器
        
        Args:
            features_dir: 特征文件所在目录
        """
        self.features_dir = Path(features_dir)
        
        if not self.features_dir.exists():
            raise FileNotFoundError(f"Features directory not found: {features_dir}")
        
        # 扫描并缓存文件信息
        self._file_cache = {}
        self._scan_files()
    
    def _scan_files(self) -> None:
        """扫描目录中的特征文件"""
        self._file_cache.clear()
        
        for filepath in self.features_dir.rglob("*.h5"):
            try:
                file_info = FeatureData.parse_from_filename(filepath.name)
                self._file_cache[str(filepath)] = {
                    'path': filepath,
                    'info': file_info,
                    'filename': filepath.name
                }
            except ValueError:
                # 跳过无法解析的文件
                continue
    
    def refresh_file_list(self) -> None:
        """刷新文件列表"""
        self._scan_files()
    
    def list_all_files(self) -> List[Dict[str, Any]]:
        """
        列出所有特征文件
        
        Returns:
            文件信息列表
        """
        return list(self._file_cache.values())
    
    def find_files(self,
                   chip_id: str = None,
                   device_id: str = None, 
                   description: str = None,
                   test_id: str = None,
                   pattern: str = None) -> List[Dict[str, Any]]:
        """
        按条件筛选特征文件
        
        Args:
            chip_id: 芯片ID，支持模糊匹配
            device_id: 设备ID，支持模糊匹配
            description: 测试描述，支持模糊匹配
            test_id: 测试ID，支持模糊匹配
            pattern: 文件名模式匹配
            
        Returns:
            匹配的文件信息列表
            
        Examples:
            >>> manager = BatchManager("/data/features/")
            >>> files = manager.find_files(chip_id="#20250804008", device_id="3")
            >>> print(f"Found {len(files)} files")
        """
        matches = []
        
        for file_data in self._file_cache.values():
            file_info = file_data['info']
            
            # 检查各个条件
            if chip_id and chip_id not in file_info.chip_id:
                continue
            
            if device_id and device_id not in file_info.device_id:
                continue
            
            if description and description not in file_info.description:
                continue
            
            if test_id and test_id not in file_info.test_id:
                continue
            
            if pattern and pattern not in file_data['filename']:
                continue
            
            matches.append(file_data)
        
        return matches
    
    def get_experiments_summary(self) -> pd.DataFrame:
        """
        获取所有实验的摘要信息
        
        Returns:
            实验摘要DataFrame
        """
        summaries = []
        
        for file_data in self._file_cache.values():
            file_info = file_data['info']
            filepath = file_data['path']
            
            try:
                # 快速读取文件统计信息
                reader = FeatureReader(str(filepath))
                summary = reader.get_summary()
                
                record = {
                    'filepath': str(filepath),
                    'filename': filepath.name,
                    'chip_id': file_info.chip_id,
                    'device_id': file_info.device_id,
                    'description': file_info.description,
                    'test_id': file_info.test_id,
                    'has_transfer_features': summary['file_info']['data_info']['has_transfer_features'],
                    'has_transient_features': summary['file_info']['data_info']['has_transient_features'],
                    'total_transfer_features': summary['file_info']['data_info']['total_transfer_features'],
                    'total_transient_features': summary['file_info']['data_info']['total_transient_features'],
                    'transfer_versions': len(summary['file_info']['versions']['transfer_versions']),
                    'transient_versions': len(summary['file_info']['versions']['transient_versions']),
                    'created_at': summary['file_info']['build_info']['created_at']
                }
                
                summaries.append(record)
                
            except Exception as e:
                # 如果读取失败，添加基本信息
                summaries.append({
                    'filepath': str(filepath),
                    'filename': filepath.name,
                    'chip_id': file_info.chip_id,
                    'device_id': file_info.device_id,
                    'description': file_info.description,
                    'test_id': file_info.test_id,
                    'error': str(e)
                })
        
        return pd.DataFrame(summaries)
    
    def batch_read_features(self,
                           feature_names: List[str],
                           file_paths: List[str] = None,
                           data_type: str = "transfer",
                           max_workers: int = 4) -> Dict[str, Dict[str, np.ndarray]]:
        """
        批量读取多个文件的特征数据
        
        Args:
            feature_names: 特征名称列表
            file_paths: 文件路径列表，None表示处理所有文件
            data_type: 数据类型
            max_workers: 并行处理的最大线程数
            
        Returns:
            文件路径到特征数据字典的映射
            
        Examples:
            >>> manager = BatchManager("/data/features/")
            >>> features = manager.batch_read_features(
            ...     ["gm_max_forward", "Von_forward"],
            ...     data_type="transfer"
            ... )
            >>> for filepath, data in features.items():
            ...     print(f"{filepath}: {list(data.keys())}")
        """
        if file_paths is None:
            file_paths = list(self._file_cache.keys())
        
        results = {}
        
        def read_file_features(filepath):
            try:
                reader = FeatureReader(filepath)
                features_data = reader.get_features(feature_names, data_type)
                return filepath, features_data
            except Exception as e:
                return filepath, {'error': str(e)}
        
        # 并行处理
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_path = {executor.submit(read_file_features, path): path for path in file_paths}
            
            for future in as_completed(future_to_path):
                filepath, features_data = future.result()
                results[filepath] = features_data
        
        return results
    
    def batch_read_version_matrices(self,
                                   version: str = "latest",
                                   file_paths: List[str] = None,
                                   data_type: str = "transfer",
                                   max_workers: int = 4) -> Dict[str, np.ndarray]:
        """
        批量读取多个文件的版本化矩阵
        
        Args:
            version: 版本名称
            file_paths: 文件路径列表
            data_type: 数据类型
            max_workers: 并行处理线程数
            
        Returns:
            文件路径到特征矩阵的映射
        """
        if file_paths is None:
            file_paths = list(self._file_cache.keys())
        
        results = {}
        
        def read_file_matrix(filepath):
            try:
                reader = FeatureReader(filepath)
                matrix = reader.get_version_matrix(version, data_type)
                return filepath, matrix
            except Exception as e:
                return filepath, None
        
        # 并行处理
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_path = {executor.submit(read_file_matrix, path): path for path in file_paths}
            
            for future in as_completed(future_to_path):
                filepath, matrix = future.result()
                if matrix is not None:
                    results[filepath] = matrix
        
        return results
    
    def aggregate_features(self,
                          feature_names: List[str],
                          file_paths: List[str] = None,
                          data_type: str = "transfer",
                          aggregation_method: str = "concat") -> Dict[str, np.ndarray]:
        """
        聚合多个文件的特征数据
        
        Args:
            feature_names: 特征名称列表
            file_paths: 文件路径列表
            data_type: 数据类型
            aggregation_method: 聚合方法，'concat'（拼接）或 'stack'（堆叠）
            
        Returns:
            聚合后的特征数据字典
        """
        batch_features = self.batch_read_features(feature_names, file_paths, data_type)
        
        aggregated = {}
        
        for feature_name in feature_names:
            feature_arrays = []
            
            for filepath, features_data in batch_features.items():
                if isinstance(features_data, dict) and feature_name in features_data:
                    feature_data = features_data[feature_name]
                    if feature_data is not None:
                        feature_arrays.append(feature_data)
            
            if feature_arrays:
                if aggregation_method == "concat":
                    aggregated[feature_name] = np.concatenate(feature_arrays)
                elif aggregation_method == "stack":
                    # 确保所有数组形状一致
                    min_length = min(len(arr) for arr in feature_arrays)
                    trimmed_arrays = [arr[:min_length] for arr in feature_arrays]
                    aggregated[feature_name] = np.stack(trimmed_arrays)
                else:
                    raise ValueError(f"Unsupported aggregation method: {aggregation_method}")
        
        return aggregated
    
    def create_combined_dataframe(self,
                                 feature_names: List[str],
                                 file_paths: List[str] = None,
                                 data_type: str = "transfer",
                                 include_metadata: bool = True) -> pd.DataFrame:
        """
        创建组合的特征DataFrame
        
        Args:
            feature_names: 特征名称列表
            file_paths: 文件路径列表
            data_type: 数据类型
            include_metadata: 是否包含元数据列
            
        Returns:
            组合的特征DataFrame
        """
        all_records = []
        batch_features = self.batch_read_features(feature_names, file_paths, data_type)
        
        for filepath, features_data in batch_features.items():
            if 'error' in features_data:
                continue
            
            # 获取文件信息
            file_info = None
            for file_data in self._file_cache.values():
                if str(file_data['path']) == filepath:
                    file_info = file_data['info']
                    break
            
            if file_info is None:
                continue
            
            # 确定数据长度
            valid_features = {name: data for name, data in features_data.items() if data is not None}
            if not valid_features:
                continue
            
            data_length = len(next(iter(valid_features.values())))
            
            # 创建记录
            for i in range(data_length):
                record = {}
                
                if include_metadata:
                    record.update({
                        'chip_id': file_info.chip_id,
                        'device_id': file_info.device_id,
                        'description': file_info.description,
                        'test_id': file_info.test_id,
                        'filepath': filepath,
                        'step_index': i
                    })
                
                # 添加特征数据
                for feature_name in feature_names:
                    if feature_name in valid_features:
                        record[feature_name] = valid_features[feature_name][i]
                    else:
                        record[feature_name] = np.nan
                
                all_records.append(record)
        
        return pd.DataFrame(all_records)
    
    def get_feature_statistics(self,
                             feature_names: List[str],
                             file_paths: List[str] = None,
                             data_type: str = "transfer") -> Dict[str, Dict[str, float]]:
        """
        计算特征的跨文件统计信息
        
        Args:
            feature_names: 特征名称列表
            file_paths: 文件路径列表
            data_type: 数据类型
            
        Returns:
            特征统计信息字典
        """
        aggregated_features = self.aggregate_features(feature_names, file_paths, data_type, "concat")
        
        statistics = {}
        
        for feature_name, feature_data in aggregated_features.items():
            # 过滤掉NaN和inf值
            valid_data = feature_data[np.isfinite(feature_data)]
            
            if len(valid_data) > 0:
                statistics[feature_name] = {
                    'count': len(valid_data),
                    'mean': float(np.mean(valid_data)),
                    'std': float(np.std(valid_data)),
                    'min': float(np.min(valid_data)),
                    'max': float(np.max(valid_data)),
                    'q25': float(np.percentile(valid_data, 25)),
                    'q50': float(np.percentile(valid_data, 50)),
                    'q75': float(np.percentile(valid_data, 75)),
                    'missing_rate': float((len(feature_data) - len(valid_data)) / len(feature_data))
                }
            else:
                statistics[feature_name] = {
                    'count': 0,
                    'error': 'No valid data'
                }
        
        return statistics
    
    def find_common_features(self,
                           file_paths: List[str] = None,
                           data_type: str = "transfer") -> List[str]:
        """
        查找所有文件都包含的共同特征
        
        Args:
            file_paths: 文件路径列表
            data_type: 数据类型
            
        Returns:
            共同特征名称列表
        """
        if file_paths is None:
            file_paths = list(self._file_cache.keys())
        
        if not file_paths:
            return []
        
        # 获取第一个文件的特征列表作为基准
        try:
            first_reader = FeatureReader(file_paths[0])
            common_features = set(first_reader.list_features(data_type))
        except Exception:
            return []
        
        # 与其他文件的特征列表求交集
        for filepath in file_paths[1:]:
            try:
                reader = FeatureReader(filepath)
                file_features = set(reader.list_features(data_type))
                common_features &= file_features
            except Exception:
                continue
        
        return sorted(list(common_features))
    
    def export_batch_features(self,
                            output_path: str,
                            feature_names: List[str],
                            file_paths: List[str] = None,
                            data_type: str = "transfer",
                            format: str = "csv",
                            include_metadata: bool = True) -> bool:
        """
        批量导出特征数据
        
        Args:
            output_path: 输出文件路径
            feature_names: 特征名称列表
            file_paths: 文件路径列表
            data_type: 数据类型
            format: 输出格式
            include_metadata: 是否包含元数据
            
        Returns:
            是否成功导出
        """
        try:
            df = self.create_combined_dataframe(
                feature_names, file_paths, data_type, include_metadata
            )
            
            if df.empty:
                return False
            
            output_path = Path(output_path)
            
            if format.lower() == 'csv':
                df.to_csv(output_path, index=False)
            elif format.lower() == 'parquet':
                df.to_parquet(output_path, index=False)
            elif format.lower() == 'h5':
                df.to_hdf(output_path, key='batch_features', mode='w')
            else:
                raise ValueError(f"Unsupported format: {format}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to export batch features: {e}")
            return False
    
    def get_directory_statistics(self) -> Dict[str, Any]:
        """
        获取目录统计信息
        
        Returns:
            目录统计信息字典
        """
        total_files = len(self._file_cache)
        
        if total_files == 0:
            return {'total_files': 0}
        
        # 按芯片分组统计
        chip_counts = {}
        device_counts = {}
        description_counts = {}
        
        for file_data in self._file_cache.values():
            info = file_data['info']
            
            chip_counts[info.chip_id] = chip_counts.get(info.chip_id, 0) + 1
            device_counts[info.device_id] = device_counts.get(info.device_id, 0) + 1
            description_counts[info.description] = description_counts.get(info.description, 0) + 1
        
        return {
            'total_files': total_files,
            'unique_chips': len(chip_counts),
            'unique_devices': len(device_counts),
            'unique_descriptions': len(description_counts),
            'chip_distribution': chip_counts,
            'device_distribution': device_counts,
            'description_distribution': description_counts,
            'directory_path': str(self.features_dir)
        }