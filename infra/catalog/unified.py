"""
Catalog模块统一接口

提供完全统一的实验数据管理接口，隐藏底层模块的复杂性：
- UnifiedExperimentManager: 统一管理器,用户唯一需要了解的类
- UnifiedExperiment: 统一实验对象，整合所有数据源
- 智能路由和懒加载
- 与experiment、features、visualization模块的无缝集成
"""

import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Union
import pandas as pd
import numpy as np
import json

from .service import CatalogService
from .models import FileRecord

logger = logging.getLogger(__name__)


# ==================== 工作流元数据提取工具函数 ====================

def normalize_value(value):
    """
    标准化值为可序列化的格式

    Args:
        value: 任意值

    Returns:
        标准化后的值（str, int, float, bool, None）
    """
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return json.dumps(value)


def flatten_workflow(exp: 'UnifiedExperiment') -> Dict[str, Any]:
    """
    从实验中提取工作流信息并扁平化

    Args:
        exp: UnifiedExperiment 对象

    Returns:
        Dict[str, Any]: 扁平化的工作流元数据字典
    """
    workflow = exp.get_workflow()
    if not workflow:
        return {}

    flattened = {}

    def walk(steps, path):
        for idx, step in enumerate(steps, start=1):
            step_path = path + [str(idx)]
            base = f"workflow_step_{'_'.join(step_path)}"

            flattened[f"{base}_type"] = getattr(step, "type", None)

            if hasattr(step, "id"):
                flattened[f"{base}_id"] = step.id

            if hasattr(step, "command_id"):
                flattened[f"{base}_command_id"] = step.command_id

            if hasattr(step, "iterations"):
                flattened[f"{base}_iterations"] = step.iterations

            params = getattr(step, "params", None)
            if params:
                for key, value in params.items():
                    flattened[f"{base}_param_{key}"] = normalize_value(value)

            child_steps = getattr(step, "steps", None)
            if child_steps:
                walk(child_steps, step_path)

    walk(workflow, [])
    return flattened


def match_workflow_filters(exp: 'UnifiedExperiment', workflow_filters: Dict[str, Any]) -> bool:
    """
    检查实验的扁平化 workflow metadata 是否匹配给定的过滤条件

    Args:
        exp: UnifiedExperiment 对象
        workflow_filters: 扁平化的 workflow 过滤条件字典
            键名格式与 get_workflow_metadata() 返回的键名相同
            例如: {'workflow_step_1_type': 'loop', 'workflow_step_1_1_param_Vd': -0.1}

    Returns:
        bool: 是否所有条件都匹配（AND 逻辑）
    """
    if not workflow_filters:
        return True

    # 获取实验的扁平化 workflow metadata
    workflow_metadata = exp.get_workflow_metadata()
    if not workflow_metadata:
        return False

    # 检查所有过滤条件是否都匹配
    for key, expected_value in workflow_filters.items():
        # 如果 metadata 中不存在该键，则不匹配
        if key not in workflow_metadata:
            return False

        # 比较值（标准化后比较）
        actual_value = workflow_metadata[key]
        if normalize_value(actual_value) != normalize_value(expected_value):
            return False

    return True


class UnifiedExperimentError(Exception):
    """统一实验接口错误"""
    pass


class UnifiedExperiment:
    """
    统一的实验对象
    
    整合所有数据源的单一接口，自动管理experiment、features、visualization模块
    """
    
    def __init__(self, catalog_record: FileRecord, manager: 'UnifiedExperimentManager'):
        """
        初始化统一实验对象
        
        Args:
            catalog_record: Catalog数据库记录
            manager: 统一管理器引用
        """
        self._record = catalog_record
        self._manager = manager
        
        # 懒加载缓存
        self._experiment = None
        self._feature_reader = None
        self._plotter = None
        self._cache_valid = True
    
    # ==================== 基本属性访问 ====================
    
    @property
    def id(self) -> Optional[int]:
        """实验ID"""
        return self._record.id
    
    @property
    def chip_id(self) -> str:
        """芯片ID"""
        return self._record.chip_id
    
    @property
    def device_id(self) -> str:
        """设备ID"""
        return self._record.device_id
    
    @property
    def test_id(self) -> str:
        """测试ID"""
        return self._record.test_id
    
    @property
    def batch_id(self) -> Optional[str]:
        """批次ID"""
        return self._record.batch_id
    
    @property
    def description(self) -> Optional[str]:
        """实验描述"""
        return self._record.description
    
    @property
    def status(self) -> str:
        """实验状态"""
        if not self._record.status:
            return 'unknown'
        return self._record.status.value if hasattr(self._record.status, 'value') else str(self._record.status)
    
    @property
    def completion_percentage(self) -> float:
        """完成百分比"""
        return self._record.completion_percentage
    
    @property
    def is_completed(self) -> bool:
        """是否已完成"""
        return self._record.is_completed
    
    def has_features(self, version: Optional[str] = None) -> bool:
        """是否有特征文件"""
        if version is None:
            return self._record.has_features
        else:
            # 检查特定版本的特征 - 简化检查逻辑
            feature_reader = self._get_feature_reader()
            if feature_reader:
                try:
                    # 尝试获取版本矩阵来检查版本是否存在
                    matrix = feature_reader.get_version_matrix(version, "transfer")
                    return matrix is not None
                except:
                    return False
            return False
    
    @property
    def created_at(self) -> Optional[str]:
        """创建时间"""
        return self._record.created_at.isoformat() if self._record.created_at else None
    
    @property
    def completed_at(self) -> Optional[str]:
        """完成时间"""
        return self._record.completed_at.isoformat() if self._record.completed_at else None
    
    @property
    def duration(self) -> Optional[float]:
        """实验持续时间（秒）"""
        return self._record.duration
    
    @property
    def file_path(self) -> Optional[str]:
        """原始数据文件路径（绝对路径）"""
        if self.id is not None:
            return self._manager.catalog.get_experiment_file_path(self.id, 'raw')
        return None
    
    # ==================== 数据访问接口 ====================
    
    def get_transfer_data(self, step_index: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        获取Transfer数据
        
        Args:
            step_index: 步骤索引，如果为None则返回所有数据
            
        Returns:
            Dict[str, Any]: Transfer数据字典
        """
        experiment = self._get_experiment()
        if not experiment:
            return None
        
        try:
            if step_index is None:
                return experiment.get_transfer_all_measurement()
            else:
                return experiment.get_transfer_step_measurement(step_index)
        except Exception as e:
            logger.error(f"Failed to get transfer data: {e}")
            return None
    
    def get_transient_data(self, step_index: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        获取Transient数据
        
        Args:
            step_index: 步骤索引，如果为None则返回所有数据
            
        Returns:
            Dict[str, Any]: Transient数据字典
        """
        experiment = self._get_experiment()
        if not experiment:
            return None
        
        try:
            if step_index is None:
                return experiment.get_transient_all_measurement()
            else:
                return experiment.get_transient_step_measurement(step_index)
        except Exception as e:
            logger.error(f"Failed to get transient data: {e}")
            return None
    
    def get_features(self, feature_names: List[str], 
                    data_type: str = 'transfer') -> Optional[Dict[str, np.ndarray]]:
        """
        获取特征数据
        
        Args:
            feature_names: 特征名称列表
            data_type: 数据类型 ('transfer' 或 'transient')
            
        Returns:
            Dict[str, np.ndarray]: 特征数据字典
        """
        feature_reader = self._get_feature_reader()
        if not feature_reader:
            return None
        
        try:
            result = feature_reader.get_features(feature_names, data_type)
            # 确保返回的是字典类型
            if isinstance(result, dict):
                return result
            return None
        except Exception as e:
            logger.error(f"Failed to get features: {e}")
            return None
    
    def get_feature_matrix(self, version: str = 'v1', 
                          data_type: str = 'transfer') -> Optional[np.ndarray]:
        """
        获取特征矩阵
        
        Args:
            version: 特征版本
            data_type: 数据类型
            
        Returns:
            np.ndarray: 特征矩阵 (n_steps, n_features)
        """
        feature_reader = self._get_feature_reader()
        if not feature_reader:
            return None
        
        try:
            return feature_reader.get_version_matrix(version, data_type)
        except Exception as e:
            logger.error(f"Failed to get feature matrix: {e}")
            return None
    
    def get_feature_dataframe(self, version: str = 'v1',
                             data_type: str = 'transfer',
                             include_workflow: bool = False) -> Optional[pd.DataFrame]:
        """
        获取特征DataFrame

        Args:
            version: 特征版本
            data_type: 数据类型
            include_workflow: 是否包含工作流元数据列

        Returns:
            pd.DataFrame: 特征DataFrame，如果 include_workflow=True，则包含工作流元数据列
        """
        feature_reader = self._get_feature_reader()
        if not feature_reader:
            return None

        try:
            df = feature_reader.get_version_dataframe(version, data_type)

            if df is None:
                return None

            # 如果需要包含工作流元数据，则添加这些列
            if include_workflow:
                workflow_metadata = self.get_workflow_metadata()
                if workflow_metadata:
                    # 将工作流元数据添加到每一行
                    for col_name, col_value in workflow_metadata.items():
                        df[col_name] = col_value

            return df
        except Exception as e:
            logger.error(f"Failed to get feature dataframe: {e}")
            return None

    # ==================== Features V2 集成 ====================

    def has_v2_features(self, validate_files: bool = True) -> bool:
        """检查是否已有 V2 特征

        Args:
            validate_files: 是否验证文件是否存在（默认 True，自动修复不一致）

        Returns:
            bool: 如果数据库中有 v2_feature_metadata 且文件存在，返回 True

        注意：
            - validate_files=True 时，会自动验证 output_files 中的文件是否存在
            - 如果文件不存在，会自动清理数据库记录并返回 False
            - 这确保了数据库和文件系统的一致性
        """
        if self.id is None:
            return False

        if not validate_files:
            # 旧行为：只检查数据库记录
            metadata = self._manager.catalog.repository.get_v2_feature_metadata(self.id)
            return metadata is not None and len(metadata) > 0

        # 新行为：验证文件存在性
        metadata = self.get_v2_features_metadata(validate_files=True)

        if not metadata:
            return False

        # 检查是否有有效的输出文件
        output_files = metadata.get('output_files', [])
        configs_used = metadata.get('configs_used', [])

        # 如果没有配置或没有文件，说明没有有效特征
        if not configs_used or not output_files:
            logger.debug(f"实验 {self.id} 没有有效的 V2 特征（configs={configs_used}, files={len(output_files)}）")
            # 清理无效的元数据
            if metadata.get('configs_used') or metadata.get('output_files'):
                self.clear_v2_features_metadata()
            return False

        return True

    def get_v2_features_metadata(self, validate_files: bool = True) -> Optional[Dict[str, Any]]:
        """获取 V2 特征元数据

        Args:
            validate_files: 是否验证文件是否存在（自动过滤不存在的文件）

        Returns:
            Dict: V2 特征元数据，包含：
                - configs_used: 使用的配置列表
                - last_computed: 最后计算时间
                - feature_count: 特征数量
                - output_files: 输出文件列表
                - computation_stats: 计算统计
        """
        if self.id is None:
            return None

        metadata = self._manager.catalog.repository.get_v2_feature_metadata(self.id)

        # 自动过滤不存在的文件
        if validate_files and metadata and 'output_files' in metadata:
            from pathlib import Path
            original_files = metadata['output_files']
            valid_files = [f for f in original_files if Path(f).exists()]

            if len(valid_files) < len(original_files):
                removed_count = len(original_files) - len(valid_files)
                logger.info(f"自动移除 {removed_count} 个不存在的特征文件")
                metadata['output_files'] = valid_files

                # 更新数据库
                self._manager.catalog.repository.update_v2_feature_metadata(self.id, metadata)

        return metadata

    def clear_v2_features_metadata(self):
        """清空 V2 特征元数据

        注意：这只清空数据库中的元数据，不删除文件系统中的实际文件
        """
        if self.id is None:
            logger.warning("实验 ID 为空，无法清空元数据")
            return

        # 完全移除元数据（设置为 None）
        self._manager.catalog.repository.update_v2_feature_metadata(self.id, None)
        logger.info(f"已清空实验 {self.id} 的 V2 特征元数据")

    def sync_v2_features_from_filesystem(self, auto_remove_missing: bool = True) -> Dict[str, Any]:
        """从文件系统扫描并同步 V2 特征元数据

        Args:
            auto_remove_missing: 是否自动移除已经不存在的文件

        Returns:
            Dict: 同步结果
                - found_files: 找到的文件数
                - added_files: 新增的文件数
                - removed_files: 移除的文件数
                - configs_found: 找到的配置列表
        """
        from pathlib import Path
        import pandas as pd

        if self.id is None:
            logger.warning("实验 ID 为空，无法同步")
            return {'error': 'No experiment ID'}

        # 扫描文件系统
        features_v2_dir = self._manager.catalog.config.get_absolute_path('features_v2')
        if not features_v2_dir.exists():
            logger.warning(f"V2 特征目录不存在: {features_v2_dir}")
            return {'error': 'Directory not found'}

        # 标准格式：包含配置名
        pattern = f"{self.chip_id}-{self.device_id}-*-feat_*.parquet"
        found_files = list(features_v2_dir.glob(pattern))

        # 去重
        found_files = list(set(found_files))

        logger.info(f"扫描到 {len(found_files)} 个特征文件")

        # 提取配置名
        configs_found = set()
        file_config_map = {}  # {file_path: config_name}

        for file_path in found_files:
            # 尝试从文件名提取配置名
            config_name = None
            filename = file_path.name

            # 新格式：chip-device-config-feat_timestamp_hash.parquet（精确匹配）
            for known_config in ['v2_transfer_basic', 'v2_ml_ready', 'v2_quick_analysis']:
                if f"-{known_config}-" in filename:
                    config_name = known_config
                    configs_found.add(config_name)
                    break

            file_config_map[str(file_path)] = config_name

        # 读取现有元数据
        existing_metadata = self.get_v2_features_metadata(validate_files=False) or {}
        existing_files = set(existing_metadata.get('output_files', []))
        existing_configs = set(existing_metadata.get('configs_used', []))

        # 计算差异
        found_files_set = set(str(f) for f in found_files)
        new_files = found_files_set - existing_files
        removed_files = existing_files - found_files_set if auto_remove_missing else set()

        # 更新元数据
        updated_files = list(found_files_set - removed_files)
        updated_configs = list(configs_found | existing_configs)

        # 获取特征数量（从最新的文件）
        feature_count = 0
        if updated_files:
            try:
                latest_file = max((Path(f) for f in updated_files if Path(f).exists()),
                                  key=lambda p: p.stat().st_mtime)
                df = pd.read_parquet(latest_file)
                feature_count = len(df.columns) - 1  # 减去 step_index
            except Exception as e:
                logger.warning(f"读取特征数量失败: {e}")

        from datetime import datetime
        updated_metadata = {
            'configs_used': updated_configs,
            'output_files': updated_files,
            'last_computed': existing_metadata.get('last_computed', datetime.now().isoformat()),
            'feature_count': feature_count,
            'computation_stats': existing_metadata.get('computation_stats', {}),
        }

        self._manager.catalog.repository.update_v2_feature_metadata(self.id, updated_metadata)

        result = {
            'found_files': len(found_files),
            'added_files': len(new_files),
            'removed_files': len(removed_files),
            'configs_found': list(configs_found),
            'total_files': len(updated_files),
        }

        logger.info(
            f"同步完成: 找到 {result['found_files']} 个文件, "
            f"新增 {result['added_files']}, 移除 {result['removed_files']}"
        )

        return result

    def get_v2_feature_dataframe(
        self,
        config_name: Optional[str] = None,
        file_path: Optional[str] = None
    ) -> Optional[pd.DataFrame]:
        """读取已计算的 V2 特征（从 Parquet 文件）

        Args:
            config_name: 配置名称（用于从元数据中查找文件）
            file_path: 直接指定 Parquet 文件路径（优先级高于 config_name）

        Returns:
            pd.DataFrame: 特征数据框，如果文件不存在返回 None

        Examples:
            # 方式1: 通过配置名称读取（从元数据查找）
            df = exp.get_v2_feature_dataframe('v2_transfer_basic')

            # 方式2: 直接指定文件路径
            df = exp.get_v2_feature_dataframe(file_path='path/to/features.parquet')

            # 方式3: 读取最新的特征文件（不指定配置）
            df = exp.get_v2_feature_dataframe()
        """
        import pandas as pd
        from pathlib import Path

        # 如果直接指定文件路径
        if file_path:
            if Path(file_path).exists():
                logger.info(f"从文件读取 V2 特征: {file_path}")
                return pd.read_parquet(file_path)
            else:
                logger.warning(f"V2 特征文件不存在: {file_path}")
                return None

        # 从元数据中查找
        metadata = self.get_v2_features_metadata()

        # 如果元数据存在，从中获取文件路径
        if metadata and 'output_files' in metadata and metadata['output_files']:
            output_files = metadata['output_files']

            # 如果指定了配置名称，尝试精确匹配文件名
            if config_name:
                # 精确匹配：格式为 chip-device-config-feat_xxx.parquet
                matching_files = [f for f in output_files if f"-{config_name}-" in f]
                if not matching_files:
                    logger.debug(
                        f"元数据中没有找到配置 '{config_name}' 的特征文件 "
                        f"(需要文件名包含 '-{config_name}-')"
                    )
                else:
                    target_file = matching_files[-1]  # 使用最新的
                    if Path(target_file).exists():
                        df = pd.read_parquet(target_file)
                        # 验证配置名是否匹配
                        if self._validate_v2_feature_file(df, config_name, target_file):
                            logger.info(f"从元数据读取 V2 特征: {Path(target_file).name}")
                            return df
                        else:
                            logger.warning(f"文件验证失败，将触发重新计算")
                    else:
                        logger.warning(f"元数据中的文件不存在: {target_file}")
            else:
                # 使用最新的文件
                target_file = output_files[-1]
                if Path(target_file).exists():
                    logger.info(f"从文件读取 V2 特征: {target_file}")
                    return pd.read_parquet(target_file)

        # Fallback: 元数据缺失或文件不存在，尝试从文件系统搜索
        logger.warning(f"实验 {self.id} 元数据缺失，尝试从文件系统搜索...")
        features_v2_dir = self._manager.catalog.config.get_absolute_path('features_v2')

        if not features_v2_dir.exists():
            logger.warning(f"V2 特征目录不存在: {features_v2_dir}")
            return None

        # 搜索匹配的 parquet 文件（支持新旧两种格式）
        # 旧格式: chip-device-v2_*-feat_*.parquet
        # 新格式: chip-device-{config_name}-feat_*.parquet
        pattern = f"{self.chip_id}-{self.device_id}-*-feat_*.parquet"
        matching_files = list(features_v2_dir.glob(pattern))

        if not matching_files:
            logger.warning(f"在 {features_v2_dir} 中没有找到匹配的 V2 特征文件: {pattern}")
            return None

        # 如果指定了配置名称，进一步过滤
        if config_name:
            # 精确匹配：配置名必须在文件名中（格式：chip-device-config-feat_xxx）
            config_filtered = [f for f in matching_files if f"-{config_name}-" in f.name]
            if config_filtered:
                matching_files = config_filtered
            else:
                # 没有找到匹配的文件，返回 None（避免返回错误配置的缓存）
                logger.warning(
                    f"未找到配置 '{config_name}' 的特征文件。"
                    f"扫描到 {len(matching_files)} 个文件，但都不匹配。"
                )
                return None

        # 使用最新的文件（按修改时间排序）
        target_file = max(matching_files, key=lambda p: p.stat().st_mtime)
        logger.info(f"从文件系统找到 V2 特征文件: {target_file.name}")

        # 读取文件并验证
        df = pd.read_parquet(target_file)

        # 验证文件是否匹配配置
        if config_name and not self._validate_v2_feature_file(df, config_name, str(target_file)):
            logger.warning(f"文件验证失败: {target_file.name}")
            return None

        # 自动修复元数据
        if self.id is not None:
            self._auto_fix_v2_metadata_from_file(str(target_file), config_name)

        return df

    def _validate_v2_feature_file(
        self, df: pd.DataFrame, config_name: Optional[str], file_path: str
    ) -> bool:
        """验证 V2 特征文件是否匹配配置

        Args:
            df: 特征DataFrame
            config_name: 配置名称
            file_path: 文件路径

        Returns:
            bool: 是否验证通过
        """
        if config_name is None:
            return True  # 没有指定配置，跳过验证

        # 验证1：文件名必须包含配置名
        if f"-{config_name}-" not in file_path:
            logger.warning(f"文件名不匹配配置 '{config_name}': {Path(file_path).name}")
            return False

        # 验证2：特征数量合理性检查（基于已知配置）
        expected_counts = {
            'v2_transfer_basic': 5,    # 5个基础特征
            'v2_ml_ready': 12,          # 12个特征（含派生）
            'v2_quick_analysis': 3,     # 3个快速分析特征
        }

        actual_count = len(df.columns) - 1  # 减去 step_index
        expected_count = expected_counts.get(config_name)

        if expected_count and actual_count != expected_count:
            logger.warning(
                f"特征数量不匹配: 配置 '{config_name}' 期望 {expected_count} 个特征, "
                f"实际文件有 {actual_count} 个"
            )
            return False

        logger.debug(f"文件验证通过: {Path(file_path).name}")
        return True

    def _auto_fix_v2_metadata_from_file(self, file_path: str, config_name: Optional[str] = None):
        """从文件系统扫描结果自动修复 V2 元数据

        Args:
            file_path: 找到的特征文件路径
            config_name: 配置名称（如果已知）
        """
        from datetime import datetime
        from pathlib import Path
        import pandas as pd

        try:
            # 读取现有元数据
            existing_metadata = self.get_v2_features_metadata() or {}

            # 如果没有配置名，尝试从文件名推断
            if config_name is None:
                filename = Path(file_path).name
                # 精确匹配常见配置名（格式：chip-device-config-feat_xxx）
                for known_config in ['v2_transfer_basic', 'v2_ml_ready', 'v2_quick_analysis']:
                    if f"-{known_config}-" in filename:
                        config_name = known_config
                        break

            # 合并配置列表
            existing_configs = existing_metadata.get('configs_used', [])
            if config_name and config_name not in existing_configs:
                configs_used = existing_configs + [config_name]
            else:
                configs_used = existing_configs

            # 合并文件列表
            existing_files = existing_metadata.get('output_files', [])
            if file_path not in existing_files:
                output_files = existing_files + [file_path]
            else:
                output_files = existing_files

            # 读取文件获取特征数量
            df = pd.read_parquet(file_path)
            feature_count = len(df.columns) - 1  # 减去 step_index

            # 更新元数据
            new_metadata = {
                'configs_used': configs_used,
                'last_computed': existing_metadata.get('last_computed', datetime.now().isoformat()),
                'feature_count': feature_count,
                'output_files': output_files,
                'computation_stats': existing_metadata.get('computation_stats', {}),
            }

            self._manager.catalog.repository.update_v2_feature_metadata(self.id, new_metadata)
            logger.info(f"✓ 自动修复元数据：添加配置 {config_name}, 文件 {Path(file_path).name}")

        except Exception as e:
            logger.warning(f"自动修复元数据失败: {e}")

    def extract_features_v2(
        self,
        feature_config: Union[str, Dict],
        output_format: str = 'parquet',
        output_dir: Optional[str] = None,
        save_metadata: bool = True,
        force_recompute: bool = False,
    ) -> Union[Dict[str, np.ndarray], pd.DataFrame, str]:
        """使用 features_v2 提取特征

        Args:
            feature_config: 特征配置
                - str: 配置文件名（如 'v2_transfer_basic'）或完整路径
                - Dict: 内联配置字典
            output_format: 输出格式
                - 'dict': 返回特征字典
                - 'dataframe': 返回 DataFrame
                - 'parquet': 保存为 Parquet 并返回文件路径
            output_dir: 输出目录（None 使用默认）
            save_metadata: 是否保存元数据到数据库
            force_recompute: 是否强制重新计算（默认 False，会尝试读取已有特征）

        Returns:
            根据 output_format 返回相应类型

        Raises:
            ValueError: 如果无法加载实验或配置无效
        """
        from infra.features_v2 import FeatureSet
        import infra.features_v2.extractors.transfer  # 注册提取器
        import infra.features_v2.extractors.transient  # 注册提取器
        import time
        from datetime import datetime

        # 获取底层 Experiment 对象
        experiment = self._get_experiment()
        if not experiment:
            raise ValueError(f"无法加载实验 {self.id}")

        # 解析配置
        if isinstance(feature_config, str):
            # 检查是否为配置文件路径（必须有 .yaml 或 .yml 后缀）
            config_path = Path(feature_config)
            is_valid_config_file = (
                config_path.suffix in ['.yaml', '.yml'] and
                config_path.exists() and
                config_path.is_file()
            )

            if not is_valid_config_file:
                # 尝试从 catalog 配置目录加载
                catalog_config_path = (
                    self._manager.catalog.config.base_dir /
                    'infra/catalog/feature_configs' / f'{feature_config}.yaml'
                )
                if catalog_config_path.exists():
                    config_path = catalog_config_path
                else:
                    # 尝试从 features_v2 模板目录加载
                    template_path = (
                        self._manager.catalog.config.base_dir /
                        'infra/features_v2/config/templates' / f'{feature_config}.yaml'
                    )
                    if template_path.exists():
                        config_path = template_path
                    else:
                        raise ValueError(
                            f"配置文件不存在: {feature_config}, "
                            f"也未在 catalog/feature_configs 或 features_v2/config/templates 中找到"
                        )

            config_name = config_path.stem
            features = FeatureSet.from_config(str(config_path), experiment=experiment)
        else:
            # 内联配置字典
            config_name = 'inline_config'
            features = FeatureSet(experiment=experiment)

            for name, spec in feature_config.items():
                features.add(
                    name=name,
                    extractor=spec.get('extractor'),
                    func=spec.get('func'),
                    input=spec.get('input'),
                    params=spec.get('params', {}),
                    output_shape=tuple(spec['output_shape']) if 'output_shape' in spec else None,
                )

        # 检查是否已有特征（缓存读取）
        if not force_recompute:
            logger.debug(f"检查配置 '{config_name}' 的缓存...")
            existing_df = self.get_v2_feature_dataframe(config_name=config_name)
            if existing_df is not None:
                logger.info(
                    f"✓ 使用已有的 V2 特征（配置: {config_name}, "
                    f"{len(existing_df.columns)-1} 个特征），跳过计算"
                )

                # 检查元数据完整性，确保当前配置已记录
                # 注意：fallback 时已经通过 _auto_fix_v2_metadata_from_file() 自动修复了
                # 这里只是额外的安全检查
                if save_metadata:
                    metadata = self.get_v2_features_metadata()
                    if metadata and config_name not in metadata.get('configs_used', []):
                        logger.info(f"元数据中缺少配置 {config_name}，自动添加")
                        # 扫描文件系统找到对应文件
                        features_v2_dir = self._manager.catalog.config.get_absolute_path('features_v2')
                        pattern = f"{self.chip_id}-{self.device_id}-v2_*-feat_*.parquet"
                        matching_files = list(features_v2_dir.glob(pattern))
                        config_file = [str(f) for f in matching_files if f"-{config_name}-" in f.name]

                        if config_file:
                            self._auto_fix_v2_metadata_from_file(config_file[0], config_name)

                # 根据输出格式返回
                if output_format == 'dict':
                    return existing_df.to_dict('list')
                elif output_format == 'dataframe':
                    return existing_df
                elif output_format == 'parquet':
                    # 返回已有文件路径
                    metadata = self.get_v2_features_metadata()
                    if metadata and 'output_files' in metadata:
                        matching_files = [f for f in metadata['output_files'] if config_name in f]
                        if matching_files:
                            return matching_files[-1]
                    # 如果找不到文件路径，重新保存
                    if output_dir is None:
                        output_dir = str(self._manager.catalog.config.get_absolute_path('features_v2'))
                    output_path = self._generate_v2_feature_path(config_name, output_dir)
                    existing_df.to_parquet(output_path)
                    logger.info(f"已有特征重新保存到: {output_path}")
                    return output_path

        # 计算特征
        logger.info(f"⚙️ 开始计算 V2 特征（实验 {self.id}, 配置: {config_name}）...")
        start_time = time.time()

        result = features.compute()

        elapsed_ms = (time.time() - start_time) * 1000
        stats = features.get_statistics()

        logger.info(
            f"✅ V2 特征计算完成: {len(result)} 个特征，"
            f"耗时 {elapsed_ms:.2f}ms "
            f"(缓存命中: {stats.get('cache_hits', 0)}, 未命中: {stats.get('cache_misses', 0)})"
        )

        # 处理输出
        output_path = None

        if output_format == 'parquet':
            # 生成输出路径
            if output_dir is None:
                output_dir = str(self._manager.catalog.config.get_absolute_path('features_v2'))

            output_path = self._generate_v2_feature_path(config_name, output_dir)
            features.to_parquet(output_path)
            logger.info(f"V2 特征已保存: {output_path}")

        # 保存元数据到数据库（合并已有元数据）
        if save_metadata and self.id is not None:
            # 读取现有元数据
            existing_metadata = self.get_v2_features_metadata() or {}

            # 合并配置列表（去重）
            existing_configs = existing_metadata.get('configs_used', [])
            if config_name not in existing_configs:
                configs_used = existing_configs + [config_name]
            else:
                configs_used = existing_configs

            # 合并输出文件列表（去重：删除同一配置的旧文件）
            existing_files = existing_metadata.get('output_files', [])

            # 找出同一配置的旧文件并删除
            old_files_to_remove = []
            for old_file in existing_files:
                # 检查文件名是否包含当前配置名
                # 文件名格式: {chip_id}-{device_id}-{config_name}-feat_{timestamp}_{hash}.parquet
                if f"-{config_name}-" in old_file:
                    old_files_to_remove.append(old_file)

            # 删除旧文件（文件系统）
            for old_file in old_files_to_remove:
                old_path = Path(old_file)
                if old_path.exists():
                    try:
                        old_path.unlink()
                        logger.info(f"已删除旧文件: {old_path.name}")
                    except Exception as e:
                        logger.warning(f"删除旧文件失败 {old_path.name}: {e}")

            # 从列表中移除旧文件路径
            output_files = [f for f in existing_files if f not in old_files_to_remove]

            # 添加新文件路径
            if output_path and output_path not in output_files:
                output_files.append(output_path)

            # 创建更新后的元数据
            metadata = {
                'configs_used': configs_used,
                'last_computed': datetime.now().isoformat(),
                'feature_count': len(result),
                'computation_stats': {
                    'total_time_ms': elapsed_ms,
                    'cache_hits': stats.get('cache_hits', 0),
                    'cache_misses': stats.get('cache_misses', 0),
                },
                'output_files': output_files,
            }

            self._manager.catalog.repository.update_v2_feature_metadata(self.id, metadata)
            logger.debug(f"V2 特征元数据已保存到数据库（配置: {config_name}）")

        # 返回结果
        if output_format == 'dict':
            return result
        elif output_format == 'dataframe':
            return features.to_dataframe()
        elif output_format == 'parquet':
            return output_path
        else:
            raise ValueError(f"无效的 output_format: {output_format}")

    def _generate_v2_feature_path(self, config_name: str, output_dir: str) -> str:
        """生成 V2 特征文件路径

        格式: {chip_id}-{device_id}-{config_name}-feat_{timestamp}_{config_hash}.parquet

        Args:
            config_name: 配置名称
            output_dir: 输出目录

        Returns:
            完整文件路径
        """
        from hashlib import md5
        from datetime import datetime

        # 配置哈希（用于验证）
        config_hash = md5(config_name.encode()).hexdigest()[:8]

        # 时间戳
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')

        # 文件名（包含配置名，方便查找和识别）
        filename = (
            f"{self.chip_id}-{self.device_id}-{config_name}-"
            f"feat_{timestamp}_{config_hash}.parquet"
        )

        # 完整路径
        return str(Path(output_dir) / filename)

    # ==================== 可视化接口 ====================
    
    def plot_transfer_single(self, step_index: int, **kwargs):
        """绘制单步Transfer曲线"""
        plotter = self._get_plotter()
        if plotter:
            try:
                return plotter.plot_transfer_single(step_index, **kwargs)
            except Exception as e:
                logger.error(f"Failed to plot transfer single: {e}")
        return None
    
    def plot_transfer_evolution(self, **kwargs):
        """绘制Transfer演化图"""
        plotter = self._get_plotter()
        if plotter:
            try:
                return plotter.plot_transfer_evolution(**kwargs)
            except Exception as e:
                logger.error(f"Failed to plot transfer evolution: {e}")
        return None
    
    def plot_transient_single(self, step_index: int, **kwargs):
        """绘制单步Transient曲线"""
        plotter = self._get_plotter()
        if plotter:
            try:
                return plotter.plot_transient_single(step_index, **kwargs)
            except Exception as e:
                logger.error(f"Failed to plot transient single: {e}")
        return None
    
    def plot_transfer_multiple(self, step_indices: List[int], **kwargs):
        """绘制多个步骤的Transfer曲线对比"""
        plotter = self._get_plotter()
        if plotter:
            try:
                return plotter.plot_transfer_multiple(step_indices, **kwargs)
            except Exception as e:
                logger.error(f"Failed to plot transfer multiple: {e}")
        return None
    
    def plot_transient_all(self, **kwargs):
        """绘制所有Transient数据的整体图"""
        plotter = self._get_plotter()
        if plotter:
            try:
                return plotter.plot_transient_all(**kwargs)
            except Exception as e:
                logger.error(f"Failed to plot transient all: {e}")
        return None
    
    def create_transfer_animation(self, **kwargs):
        """创建Transfer演化动画（传统matplotlib版本）"""
        plotter = self._get_plotter()
        if plotter:
            try:
                return plotter.create_transfer_animation(**kwargs)
            except Exception as e:
                logger.error(f"Failed to create transfer animation: {e}")
        return None
    
    def create_transfer_video(self, output_path: str, **kwargs) -> Optional[str]:
        """创建Transfer演化视频"""
        plotter = self._get_plotter()
        if plotter:
            try:
                return plotter.create_transfer_video_parallel(save_path=output_path, **kwargs)
            except Exception as e:
                logger.error(f"Failed to create transfer video: {e}")
        return None
    
    def get_plotter_experiment_info(self) -> Optional[Dict[str, Any]]:
        """获取绘图器实验信息"""
        plotter = self._get_plotter()
        if plotter:
            try:
                return plotter.get_experiment_info()
            except Exception as e:
                logger.error(f"Failed to get plotter experiment info: {e}")
        return None
    
    # ==================== 特征分析接口 ====================
    
    def plot_feature_trend(self, feature_name: str, data_type: str = 'transfer', **kwargs):
        """
        绘制特征趋势图

        Args:
            feature_name: 特征名称
            data_type: 数据类型 ('transfer' 或 'transient')
            **kwargs: 绘图参数，支持：
                - title (str): 图表标题，默认为 '{feature_name} Trend - {chip_id}-{device_id}'
                - figsize (tuple): 图表尺寸，默认 (10, 6)
                - 其他 matplotlib.pyplot.plot 支持的参数 (如 color, linewidth, marker, linestyle 等)
        """
        feature_data = self.get_features([feature_name], data_type)
        if feature_data and feature_name in feature_data:
            try:
                import matplotlib.pyplot as plt

                data = feature_data[feature_name]

                # 提取特殊参数
                title = kwargs.pop('title', None)
                figsize = kwargs.pop('figsize', (10, 6))

                fig, ax = plt.subplots(figsize=figsize)

                ax.plot(range(len(data)), data, **kwargs)
                ax.set_xlabel('Step Index')
                ax.set_ylabel(feature_name)
                ax.set_title(title if title is not None else f'{feature_name} Trend - {self.chip_id}-{self.device_id}')
                ax.grid(True, alpha=0.3)

                return fig
            except Exception as e:
                logger.error(f"Failed to plot feature trend: {e}")

        return None
    
    
    # ==================== 实验摘要和工作流接口 ====================
    # 通过底层experiment对象提供完整的实验功能
    
    def get_experiment_summary(self) -> Optional[Dict[str, Any]]:
        """
        获取实验完整摘要
        
        Returns:
            Optional[Dict[str, Any]]: 实验摘要信息
        """
        experiment = self._get_experiment()
        if experiment:
            try:
                return experiment.get_experiment_summary()
            except Exception as e:
                logger.error(f"Failed to get experiment summary: {e}")
        return None
    
    def has_workflow(self) -> bool:
        """
        检查是否有工作流配置
        
        Returns:
            bool: 是否有工作流
        """
        experiment = self._get_experiment()
        if experiment:
            try:
                return experiment.has_workflow()
            except Exception as e:
                logger.error(f"Failed to check workflow: {e}")
        return False
    
    def get_workflow(self):
        """
        获取工作流配置
        
        Returns:
            Optional[Workflow]: 工作流对象
        """
        experiment = self._get_experiment()
        if experiment:
            try:
                return experiment.get_workflow()
            except Exception as e:
                logger.error(f"Failed to get workflow: {e}")
        return None
    
    def get_workflow_summary(self) -> Optional[Dict[str, Any]]:
        """
        获取工作流摘要信息
        
        Returns:
            Optional[Dict[str, Any]]: 工作流摘要
        """
        experiment = self._get_experiment()
        if experiment:
            try:
                return experiment.get_workflow_summary()
            except Exception as e:
                logger.error(f"Failed to get workflow summary: {e}")
        return None
    
    def print_workflow(self, indent: int = 0, show_all_params: bool = False):
        """
        以人类可读格式打印工作流
        
        Args:
            indent: 缩进级别
            show_all_params: 是否显示所有参数
        """
        experiment = self._get_experiment()
        if experiment:
            try:
                experiment.print_workflow(indent, show_all_params)
            except Exception as e:
                logger.error(f"Failed to print workflow: {e}")
                print(f"无法打印工作流: {e}")
    
    def export_workflow_json(self, output_path: str, indent: int = 2) -> bool:
        """
        导出工作流配置到JSON文件
        
        Args:
            output_path: 输出文件路径
            indent: JSON缩进
            
        Returns:
            bool: 是否成功
        """
        experiment = self._get_experiment()
        if experiment:
            try:
                return experiment.export_workflow_json(output_path, indent)
            except Exception as e:
                logger.error(f"Failed to export workflow: {e}")
        return False
    
    def export_workflow(self, output_path: str) -> bool:
        """
        导出工作流配置到JSON文件 (兼容方法名)

        Args:
            output_path: 输出文件路径

        Returns:
            bool: 是否成功
        """
        return self.export_workflow_json(output_path)

    def get_workflow_metadata(self) -> Dict[str, Any]:
        """
        获取扁平化的工作流元数据

        优先从数据库读取缓存的 workflow metadata，
        如果数据库中没有则实时计算（向后兼容）。

        Returns:
            Dict[str, Any]: 扁平化的工作流元数据字典
        """
        try:
            # 优先从数据库缓存读取
            if self._record.workflow_metadata:
                return json.loads(self._record.workflow_metadata)

            # 如果数据库中没有，实时计算（向后兼容）
            logger.debug(f"Workflow metadata not cached for experiment {self.id}, computing on-the-fly")
            return flatten_workflow(self)

        except Exception as e:
            logger.error(f"Failed to get workflow metadata: {e}")
            return {}

    # ==================== 数据摘要接口 ====================
    
    def get_transfer_summary(self) -> Optional[Dict[str, Any]]:
        """
        获取Transfer数据摘要
        
        Returns:
            Optional[Dict[str, Any]]: Transfer数据摘要
        """
        experiment = self._get_experiment()
        if experiment:
            try:
                return experiment.get_transfer_summary()
            except Exception as e:
                logger.error(f"Failed to get transfer summary: {e}")
        return None
    
    def get_transient_summary(self) -> Optional[Dict[str, Any]]:
        """
        获取Transient数据摘要
        
        Returns:
            Optional[Dict[str, Any]]: Transient数据摘要
        """
        experiment = self._get_experiment()
        if experiment:
            try:
                return experiment.get_transient_summary()
            except Exception as e:
                logger.error(f"Failed to get transient summary: {e}")
        return None
    
    def get_data_summary(self) -> Optional[Dict[str, Any]]:
        """
        获取完整数据摘要
        
        Returns:
            Optional[Dict[str, Any]]: 完整数据摘要
        """
        experiment = self._get_experiment()
        if experiment:
            try:
                return experiment.get_data_summary()
            except Exception as e:
                logger.error(f"Failed to get data summary: {e}")
        return None
    
    # ==================== 步骤数据访问接口 ====================
    
    def get_transfer_step_measurement(self, step_index: int) -> Optional[Dict[str, Any]]:
        """
        获取指定Transfer步骤的测量数据
        
        Args:
            step_index: 步骤索引 (0-based)
            
        Returns:
            Optional[Dict[str, Any]]: 测量数据
        """
        experiment = self._get_experiment()
        if experiment:
            try:
                return experiment.get_transfer_step_measurement(step_index)
            except Exception as e:
                logger.error(f"Failed to get transfer step measurement: {e}")
        return None
    
    def get_transient_step_measurement(self, step_index: int) -> Optional[Dict[str, Any]]:
        """
        获取指定Transient步骤的测量数据
        
        Args:
            step_index: 步骤索引 (0-based)
            
        Returns:
            Optional[Dict[str, Any]]: 测量数据
        """
        experiment = self._get_experiment()
        if experiment:
            try:
                return experiment.get_transient_step_measurement(step_index)
            except Exception as e:
                logger.error(f"Failed to get transient step measurement: {e}")
        return None
    
    def get_transfer_all_measurement(self) -> Optional[Dict[str, Any]]:
        """
        获取所有Transfer步骤的测量数据
        
        Returns:
            Optional[Dict[str, Any]]: 所有测量数据
        """
        experiment = self._get_experiment()
        if experiment:
            try:
                return experiment.get_transfer_all_measurement()
            except Exception as e:
                logger.error(f"Failed to get all transfer measurements: {e}")
        return None
    
    def get_transient_all_measurement(self) -> Optional[Dict[str, Any]]:
        """
        获取所有Transient步骤的测量数据
        
        Returns:
            Optional[Dict[str, Any]]: 所有测量数据
        """
        experiment = self._get_experiment()
        if experiment:
            try:
                return experiment.get_transient_all_measurement()
            except Exception as e:
                logger.error(f"Failed to get all transient measurements: {e}")
        return None
    
    def get_transfer_step_info_table(self):
        """
        获取Transfer步骤信息表格
        
        Returns:
            Optional[pd.DataFrame]: 步骤信息表格
        """
        experiment = self._get_experiment()
        if experiment:
            try:
                return experiment.get_transfer_step_info_table()
            except Exception as e:
                logger.error(f"Failed to get transfer step info table: {e}")
        return None
    
    def get_transient_step_info_table(self):
        """
        获取Transient步骤信息表格
        
        Returns:
            Optional[pd.DataFrame]: 步骤信息表格
        """
        experiment = self._get_experiment()
        if experiment:
            try:
                return experiment.get_transient_step_info_table()
            except Exception as e:
                logger.error(f"Failed to get transient step info table: {e}")
        return None
    
    # ==================== 便利属性 ====================
    
    @property
    def transfer_steps(self) -> int:
        """Transfer步骤数 (便利属性)"""
        summary = self.get_transfer_summary()
        return summary.get('step_count', 0) if summary else 0
    
    @property
    def transient_steps(self) -> int:
        """Transient步骤数 (便利属性)"""
        summary = self.get_transient_summary()
        return summary.get('step_count', 0) if summary else 0
    
    # ==================== 内部方法 ====================
    
    def _get_experiment(self):
        """获取experiment对象（懒加载）"""
        if not self._cache_valid:
            self._experiment = None
        
        if self._experiment is None and self.id is not None:
            self._experiment = self._manager.catalog.create_experiment_loader(self.id)
            
        return self._experiment
    
    def _get_feature_reader(self):
        """获取feature reader对象（懒加载）"""
        if not self._cache_valid:
            self._feature_reader = None
        
        if self._feature_reader is None and self.id is not None:
            self._feature_reader = self._manager.catalog.create_feature_reader(self.id)
            
        return self._feature_reader
    
    def _get_plotter(self):
        """获取plotter对象（懒加载）"""
        if not self._cache_valid:
            self._plotter = None
        
        if self._plotter is None and self.id is not None:
            self._plotter = self._manager.catalog.create_plotter(self.id)
            
        return self._plotter
    
    def _invalidate_cache(self):
        """使缓存失效"""
        self._cache_valid = False
    
    def get_info(self) -> Dict[str, Any]:
        """获取实验完整信息"""
        return {
            'basic_info': {
                'id': self.id,
                'chip_id': self.chip_id,
                'device_id': self.device_id,
                'test_id': self.test_id,
                'batch_id': self.batch_id,
                'description': self.description
            },
            'status_info': {
                'status': self.status,
                'completion_percentage': self.completion_percentage,
                'is_completed': self.is_completed,
                'created_at': self.created_at,
                'completed_at': self.completed_at,
                'duration': self.duration
            },
            'data_info': {
                'has_transfer_data': self._record.has_transfer_data,
                'has_transient_data': self._record.has_transient_data,
                'transfer_steps': self._record.transfer_steps,
                'transient_steps': self._record.transient_steps,
                'total_data_points': self._record.total_data_points
            },
            'file_info': {
                'has_features': self.has_features(),
                'raw_file_size': self._record.raw_file_size,
                'feature_file_size': self._record.feature_file_size
            }
        }
    
    def __str__(self) -> str:
        """字符串表示"""
        return f"UnifiedExperiment({self.chip_id}-{self.device_id}, {self.test_id})"
    
    def __repr__(self) -> str:
        """详细字符串表示"""
        return (f"UnifiedExperiment(id={self.id}, chip_id='{self.chip_id}', "
                f"device_id='{self.device_id}', test_id='{self.test_id}', "
                f"status='{self.status}', completion={self.completion_percentage:.1f}%)")


class UnifiedExperimentManager:
    """
    统一的实验数据管理器
    
    用户唯一需要了解的接口，隐藏所有底层模块的复杂性
    """
    
    def __init__(self, config_path: str = 'catalog_config.yaml'):
        """
        初始化统一管理器
        
        Args:
            config_path: 配置文件路径
        """
        try:
            self.catalog = CatalogService(config_path)
            logger.info("UnifiedExperimentManager initialized successfully")
        except Exception as e:
            raise UnifiedExperimentError(f"Failed to initialize UnifiedExperimentManager: {e}")
    
    # ==================== 单个实验操作 ====================
    
    def get_experiment(self, exp_id: Optional[int] = None, **kwargs) -> Optional[UnifiedExperiment]:
        """
        获取统一的实验对象 - 单一入口点
        
        Args:
            exp_id: 实验ID (可选)
            **kwargs: 查询条件 (chip_id, device_id, test_id等)
        
        Returns:
            UnifiedExperiment: 统一的实验对象，自动整合所有数据源
        
        Examples:
            >>> exp = manager.get_experiment(42)
            >>> exp = manager.get_experiment(chip_id="#20250804008", device_id="3")
        """
        try:
            if exp_id is not None:
                record = self.catalog.get_experiment_by_id(exp_id)
            elif 'test_id' in kwargs:
                record = self.catalog.get_experiment_by_test_id(kwargs['test_id'])
            else:
                experiments = self.catalog.find_experiments(**kwargs)
                record = experiments[0] if experiments else None
            
            if record:
                return UnifiedExperiment(record, self)
                
        except Exception as e:
            logger.error(f"Failed to get experiment: {e}")
        
        return None
    
    # ==================== 批量操作 ====================

    def search(self, **filters) -> List[UnifiedExperiment]:
        """
        批量搜索实验 - 返回统一的实验对象列表

        自动区分数据库过滤条件和 workflow 过滤条件：
        - 以 'workflow_' 开头的参数用于过滤 workflow metadata
        - 其他参数用于数据库查询（chip_id, device_id, batch_id 等）

        Args:
            **filters: 过滤条件，支持：
                - 数据库字段: chip_id, device_id, batch_id, status, etc.
                - Workflow 字段: workflow_step_1_type, workflow_step_1_iterations,
                  workflow_step_1_1_param_Vd, etc.

        Returns:
            List[UnifiedExperiment]: 匹配的实验对象列表

        Examples:
            >>> # 基本搜索（仅数据库过滤）
            >>> experiments = manager.search(chip_id="#20250829016")

            >>> # 按 workflow metadata 搜索
            >>> experiments = manager.search(workflow_step_1_type='loop')

            >>> # 按 workflow 参数值搜索
            >>> experiments = manager.search(workflow_step_1_1_param_Vd=-0.1)

            >>> # 组合搜索（数据库 + workflow）
            >>> experiments = manager.search(
            ...     chip_id="#20250829016",
            ...     workflow_step_1_type='loop',
            ...     workflow_step_1_iterations=5000
            ... )

            >>> # 多个 workflow 条件（AND 逻辑）
            >>> experiments = manager.search(
            ...     workflow_step_1_type='loop',
            ...     workflow_step_1_1_type='transfer',
            ...     workflow_step_1_1_param_drainVoltage=100
            ... )
        """
        try:
            # 1. 分离数据库过滤条件和 workflow 过滤条件
            db_filters = {}
            workflow_filters = {}

            for key, value in filters.items():
                if key.startswith('workflow_'):
                    workflow_filters[key] = value
                else:
                    db_filters[key] = value

            # 2. 执行数据库查询
            records = self.catalog.find_experiments(**db_filters)
            experiments = [UnifiedExperiment(record, self) for record in records]

            # 3. 如果没有 workflow 过滤条件，直接返回
            if not workflow_filters:
                return experiments

            # 4. 在内存中过滤 workflow 条件
            logger.info(f"Filtering {len(experiments)} experiments by workflow filters: {workflow_filters}")
            filtered_experiments = []

            for exp in experiments:
                try:
                    if match_workflow_filters(exp, workflow_filters):
                        filtered_experiments.append(exp)
                except Exception as e:
                    logger.warning(f"Failed to check workflow for experiment {exp.id}: {e}")
                    continue

            logger.info(f"Found {len(filtered_experiments)} experiments matching workflow criteria")
            return filtered_experiments

        except Exception as e:
            logger.error(f"Failed to search experiments: {e}")
            return []
    
    def get_experiments_by_chip(self, chip_id: str) -> List[UnifiedExperiment]:
        """获取指定芯片的所有实验"""
        return self.search(chip_id=chip_id)
    
    def get_experiments_by_batch(self, batch_id: str) -> List[UnifiedExperiment]:
        """获取指定批次的所有实验"""
        return self.search(batch_id=batch_id)
    
    def get_completed_experiments(self) -> List[UnifiedExperiment]:
        """获取已完成的实验"""
        return self.search(status='completed')
    
    def get_experiments_missing_features(self) -> List[UnifiedExperiment]:
        """获取缺少特征文件的实验"""
        return self.search(missing_features=True)
    
    # ==================== 数据预处理 ====================
    
    def clean_json_files(self, source_directory: Union[str, Path], 
                        pattern: str = "test_info.json") -> Dict[str, Any]:
        """
        清理指定目录下的JSON文件
        
        Args:
            source_directory: 源数据目录路径
            pattern: JSON文件匹配模式，默认为"test_info.json"
            
        Returns:
            Dict[str, Any]: 清理结果统计
        """
        try:
            from ..csv2hdf import batch_clean_json_files
            
            # 转换路径类型
            directory_str = str(source_directory)
            
            logger.info(f"Cleaning JSON files in directory: {directory_str}")
            
            # 执行JSON清理
            result = batch_clean_json_files(directory=directory_str, pattern=pattern)
            
            logger.info(f"JSON cleaning completed for directory: {directory_str}")
            return {
                'success': True,
                'directory': directory_str,
                'pattern': pattern,
                'result': result
            }
            
        except Exception as e:
            error_msg = f"Failed to clean JSON files in {source_directory}: {e}"
            logger.error(error_msg)
            return {
                'success': False,
                'directory': str(source_directory),
                'pattern': pattern,
                'error': error_msg
            }
    
    def discover_test_directories(self, source_directory: Union[str, Path], 
                                 exclude_output_dir: bool = True) -> List[str]:
        """
        发现包含test_info.json的测试目录
        
        Args:
            source_directory: 搜索的根目录
            exclude_output_dir: 是否排除输出目录
            
        Returns:
            List[str]: 测试目录路径列表
        """
        try:
            import os
            
            base_dir = str(source_directory)
            output_dir = str(self.catalog.config.get_absolute_path('raw_data')) if exclude_output_dir else None
            
            test_dirs = []
            for root, _, files in os.walk(base_dir):
                if 'test_info.json' in files:
                    if not exclude_output_dir or root != output_dir:
                        test_dirs.append(root)
            
            logger.info(f"Discovered {len(test_dirs)} test directories in {base_dir}")
            return test_dirs
            
        except Exception as e:
            logger.error(f"Failed to discover test directories in {source_directory}: {e}")
            return []
    
    def batch_convert_folders(self, test_directories: List[str], 
                             num_workers: int = 20,
                             conflict_strategy: str = 'skip',
                             show_progress: bool = True) -> Dict[str, Any]:
        """
        批量转换测试目录到HDF5格式
        
        Args:
            test_directories: 测试目录路径列表
            num_workers: 并行工作进程数
            conflict_strategy: 冲突处理策略 ('overwrite', 'skip', 'rename')
            show_progress: 是否显示进度条
            
        Returns:
            Dict[str, Any]: 转换结果统计
        """
        try:
            from ..csv2hdf import process_folders_parallel
            
            output_dir = str(self.catalog.config.get_absolute_path('raw_data'))
            
            logger.info(f"Starting batch conversion of {len(test_directories)} directories")
            
            # 执行并行转换
            results = process_folders_parallel(
                folders=test_directories,
                out_dir=output_dir,
                num_workers=num_workers,
                conflict_strategy=conflict_strategy,
                show_progress=show_progress,
            )
            
            # 统计结果
            successful = sum(1 for r in results if r.ok)
            failed = len(results) - successful
            
            conversion_result = {
                'success': True,
                'total_directories': len(test_directories),
                'successful_conversions': successful,
                'failed_conversions': failed,
                'output_directory': output_dir,
                'detailed_results': results
            }
            
            logger.info(f"Batch conversion completed: {successful}/{len(test_directories)} successful")
            
            # 转换完成后，重新扫描以更新catalog
            if successful > 0:
                logger.info("Scanning converted files to update catalog...")
                self.catalog.scan_and_index()
            
            return conversion_result
            
        except Exception as e:
            error_msg = f"Failed to batch convert folders: {e}"
            logger.error(error_msg)
            return {
                'success': False,
                'total_directories': len(test_directories),
                'successful_conversions': 0,
                'failed_conversions': len(test_directories),
                'error': error_msg
            }
    
    def process_data_pipeline(self, source_directory: Union[str, Path],
                             clean_json: bool = True,
                             num_workers: int = 20,
                             conflict_strategy: str = 'skip',
                             auto_extract_features: bool = False,
                             feature_version: str = 'v1',
                             v2_feature_config: Optional[str] = 'v2_transfer_basic',
                             show_progress: bool = True) -> Dict[str, Any]:
        """
        执行完整的数据处理管道：JSON清理 -> 目录发现 -> 批量转换 -> 可选特征提取

        Args:
            source_directory: 源数据目录路径
            clean_json: 是否先清理JSON文件
            num_workers: 并行工作进程数
            conflict_strategy: 冲突处理策略
            auto_extract_features: 是否自动提取特征
            feature_version: 特征版本（'v1', 'v2', 'both'）
            v2_feature_config: V2 配置（仅当 feature_version='v2' 或 'both' 时使用）
            show_progress: 是否显示进度条

        Returns:
            Dict[str, Any]: 完整处理结果
        """
        pipeline_result = {
            'source_directory': str(source_directory),
            'steps_completed': [],
            'overall_success': True,
            'results': {}
        }
        
        try:
            # 步骤1: JSON清理（可选）
            if clean_json:
                logger.info("Pipeline Step 1: Cleaning JSON files...")
                clean_result = self.clean_json_files(source_directory)
                pipeline_result['results']['json_cleaning'] = clean_result
                pipeline_result['steps_completed'].append('json_cleaning')
                
                if not clean_result['success']:
                    logger.warning("JSON cleaning failed, but continuing with pipeline...")
            
            # 步骤2: 发现测试目录
            logger.info("Pipeline Step 2: Discovering test directories...")
            test_directories = self.discover_test_directories(source_directory)
            pipeline_result['results']['discovery'] = {
                'success': True,
                'directories_found': len(test_directories),
                'directories': test_directories
            }
            pipeline_result['steps_completed'].append('discovery')
            
            if not test_directories:
                raise Exception("No test directories found with test_info.json files")
            
            # 步骤3: 批量转换
            logger.info("Pipeline Step 3: Converting directories to HDF5...")
            convert_result = self.batch_convert_folders(
                test_directories=test_directories,
                num_workers=num_workers,
                conflict_strategy=conflict_strategy,
                show_progress=show_progress
            )
            pipeline_result['results']['conversion'] = convert_result
            pipeline_result['steps_completed'].append('conversion')
            
            if not convert_result['success']:
                raise Exception(f"Conversion failed: {convert_result.get('error', 'Unknown error')}")
            
            # 步骤4: 特征提取（可选）
            if auto_extract_features and convert_result['successful_conversions'] > 0:
                logger.info("Pipeline Step 4: Extracting features...")

                # 获取新转换的实验
                recent_experiments = self.search()  # 简化：获取所有实验，实际可以根据时间戳过滤

                if recent_experiments:
                    # V1 特征提取
                    if feature_version in ['v1', 'both']:
                        logger.info("Extracting V1 features...")
                        feature_result_v1 = self.batch_extract_features(recent_experiments)
                        pipeline_result['results']['feature_extraction_v1'] = feature_result_v1
                        pipeline_result['steps_completed'].append('feature_extraction_v1')

                    # V2 特征提取
                    if feature_version in ['v2', 'both']:
                        logger.info(f"Extracting V2 features (config: {v2_feature_config})...")
                        feature_result_v2 = self.batch_extract_features_v2(
                            recent_experiments,
                            feature_config=v2_feature_config,
                            n_workers=min(num_workers, 4),  # 限制并行数
                        )
                        pipeline_result['results']['feature_extraction_v2'] = feature_result_v2
                        pipeline_result['steps_completed'].append('feature_extraction_v2')

            logger.info(f"Data processing pipeline completed successfully for {source_directory}")
            return pipeline_result
            
        except Exception as e:
            error_msg = f"Data processing pipeline failed: {e}"
            logger.error(error_msg)
            pipeline_result['overall_success'] = False
            pipeline_result['error'] = error_msg
            return pipeline_result
    
    # ==================== 批量特征处理 ====================
    
    def batch_extract_features(self, experiments: Union[List[UnifiedExperiment], str], 
                              version: str = 'v1') -> Dict[str, Any]:
        """
        批量提取特征 - 智能处理依赖关系
        
        Args:
            experiments: 实验列表或查询条件字符串
            version: 特征版本
            
        Returns:
            Dict[str, Any]: 处理结果
            
        注意：特征提取完成后需要手动执行全量扫描以重新关联文件：
            manager.catalog.scan_and_index(incremental=False)
        """
        if isinstance(experiments, str):
            experiments = self.search(text_search=experiments)
        
        results = {'successful': [], 'failed': [], 'skipped': []}
        
        for exp in experiments:
            try:
                if exp.has_features(version):
                    results['skipped'].append(exp.id)
                    continue
                
                # 获取原始数据路径
                if exp.id is not None:
                    raw_path = self.catalog.get_experiment_file_path(exp.id, 'raw')
                    if not raw_path or not Path(raw_path).exists():
                        results['failed'].append((exp.id, "Raw file not found"))
                        continue
                    
                    # 提取特征
                    from ..features_version.v1_feature import v1_feature
                    features_dir = str(self.catalog.config.get_absolute_path('features'))
                    v1_feature(raw_path, output_dir=features_dir)  # 执行特征提取
                else:
                    results['failed'].append((exp.id, "Invalid experiment ID"))
                    continue
                
                # 刷新实验对象缓存
                exp._invalidate_cache()
                
                results['successful'].append(exp.id)

            except Exception as e:
                results['failed'].append((exp.id, str(e)))

        return results

    def batch_extract_features_v2(
        self,
        experiments: Union[List[UnifiedExperiment], str],
        feature_config: Union[str, Dict],
        output_dir: Optional[str] = None,
        save_format: str = 'parquet',
        n_workers: int = 1,
        use_parallel_executor: bool = False,
        force_recompute: bool = False,
    ) -> Dict[str, Any]:
        """批量使用 features_v2 提取特征

        Args:
            experiments: 实验列表或查询条件字符串
            feature_config: 特征配置（字符串或字典）
            output_dir: 输出目录（None 使用默认）
            save_format: 保存格式（'parquet', 'none'）
            n_workers: 并行工作进程数（多实验并行）
            use_parallel_executor: 是否在每个实验内部使用并行执行
            force_recompute: 是否强制重新计算（忽略已有特征）

        Returns:
            Dict: 处理结果
                - successful: 成功的实验ID列表
                - failed: 失败的实验列表 [(id, error), ...]
                - skipped: 跳过的实验ID列表
                - timings: 每个实验的耗时
                - total_time_ms: 总耗时

        注意：
            - 如果 save_format='parquet'，会自动更新数据库元数据
            - 不需要手动扫描（元数据直接写入数据库）
        """
        from concurrent.futures import ProcessPoolExecutor, as_completed
        import time

        if isinstance(experiments, str):
            experiments = self.search(text_search=experiments)

        results = {
            'successful': [],
            'failed': [],
            'skipped': [],
            'timings': {},
        }

        output_dir = output_dir or str(self.catalog.config.get_absolute_path('features_v2'))

        # 过滤已有 V2 特征的实验
        if not force_recompute:
            pending_experiments = []
            for exp in experiments:
                if exp.has_v2_features():
                    results['skipped'].append(exp.id)
                    logger.debug(f"跳过实验 {exp.id}（已有 V2 特征）")
                else:
                    pending_experiments.append(exp)
        else:
            pending_experiments = experiments

        logger.info(
            f"开始批量提取 V2 特征: {len(pending_experiments)} 个实验，"
            f"{n_workers} 个工作进程"
        )

        total_start = time.time()

        if n_workers == 1:
            # 串行处理
            for exp in pending_experiments:
                self._extract_single_v2(
                    exp, feature_config, output_dir, save_format, results, force_recompute
                )
        else:
            # 并行处理（多实验并行）
            with ProcessPoolExecutor(max_workers=n_workers) as executor:
                futures = {
                    executor.submit(
                        _extract_v2_wrapper,
                        exp.id,
                        exp.chip_id,
                        exp.device_id,
                        exp.file_path,
                        feature_config,
                        output_dir,
                        save_format,
                    ): exp
                    for exp in pending_experiments
                }

                for future in as_completed(futures):
                    exp = futures[future]
                    try:
                        result_data = future.result()
                        results['successful'].append(result_data['exp_id'])
                        results['timings'][result_data['exp_id']] = result_data['time_ms']

                        # 更新数据库元数据
                        if save_format != 'none' and result_data.get('metadata'):
                            self.catalog.repository.update_v2_feature_metadata(
                                result_data['exp_id'],
                                result_data['metadata']
                            )

                    except Exception as e:
                        logger.error(f"实验 {exp.id} 提取失败: {e}")
                        results['failed'].append((exp.id, str(e)))

        total_elapsed = (time.time() - total_start) * 1000
        results['total_time_ms'] = total_elapsed

        logger.info(
            f"批量提取完成: 成功 {len(results['successful'])}, "
            f"失败 {len(results['failed'])}, "
            f"跳过 {len(results['skipped'])}, "
            f"总耗时 {total_elapsed:.2f}ms"
        )

        return results

    def _extract_single_v2(
        self, exp, feature_config, output_dir, save_format, results, force_recompute=False
    ):
        """单个实验的 V2 特征提取（内部辅助方法）"""
        import time

        try:
            start = time.time()

            if save_format == 'parquet':
                output_path = exp.extract_features_v2(
                    feature_config,
                    output_format='parquet',
                    output_dir=output_dir,
                    save_metadata=True,
                    force_recompute=force_recompute,
                )
            else:
                # 只计算不保存
                result = exp.extract_features_v2(
                    feature_config,
                    output_format='dict',
                    save_metadata=False,
                    force_recompute=force_recompute,
                )

            elapsed = (time.time() - start) * 1000
            results['successful'].append(exp.id)
            results['timings'][exp.id] = elapsed

        except Exception as e:
            logger.error(f"实验 {exp.id} 提取失败: {e}")
            results['failed'].append((exp.id, str(e)))

    # ==================== 批量导出 ====================
    
    def export_experiments_info(self, experiments: List[UnifiedExperiment], 
                               output_path: str) -> bool:
        """导出实验信息到CSV文件"""
        try:
            import pandas as pd
            
            data = []
            for exp in experiments:
                info = exp.get_info()
                row = {**info['basic_info'], **info['status_info'], **info['data_info']}
                data.append(row)
            
            df = pd.DataFrame(data)
            df.to_csv(output_path, index=False)
            
            logger.info(f"Exported {len(experiments)} experiments to {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export experiments info: {e}")
            return False
    
    def create_combined_features_dataframe(self, experiments: List[UnifiedExperiment],
                                         feature_names: List[str],
                                         data_type: str = 'transfer',
                                         include_workflow: bool = False) -> Optional[pd.DataFrame]:
        """
        创建组合特征DataFrame

        Args:
            experiments: 实验列表
            feature_names: 特征名称列表
            data_type: 数据类型 ('transfer' 或 'transient')
            include_workflow: 是否包含工作流元数据列

        Returns:
            Optional[pd.DataFrame]: 组合特征DataFrame，如果 include_workflow=True，则包含工作流元数据列
        """
        try:
            import pandas as pd

            combined_data = []

            for exp in experiments:
                # 获取工作流元数据（如果需要）
                workflow_metadata = {}
                if include_workflow:
                    workflow_metadata = exp.get_workflow_metadata()

                feature_data = exp.get_features(feature_names, data_type)
                if feature_data:
                    for step_idx in range(len(next(iter(feature_data.values())))):
                        row = {
                            'experiment_id': exp.id,
                            'chip_id': exp.chip_id,
                            'device_id': exp.device_id,
                            'test_id': exp.test_id,
                            'step_index': step_idx
                        }

                        # 添加特征值
                        for feature_name in feature_names:
                            if feature_name in feature_data:
                                row[feature_name] = feature_data[feature_name][step_idx]

                        # 添加工作流元数据
                        if include_workflow and workflow_metadata:
                            row.update(workflow_metadata)

                        combined_data.append(row)

            return pd.DataFrame(combined_data)

        except Exception as e:
            logger.error(f"Failed to create combined features dataframe: {e}")
            return None
    
    # ==================== 智能管理 ====================
    
    def check_consistency(self) -> Dict[str, List[str]]:
        """检查数据一致性 - 智能发现问题"""
        return self.catalog.validate_data_integrity()
    
    def auto_fix_inconsistencies(self, issues: Optional[Dict[str, List[str]]] = None) -> Dict[str, int]:
        """自动修复不一致问题"""
        if issues is None:
            issues = self.check_consistency()
        
        fixes = {'fixed': 0, 'failed': 0}
        
        # 修复缺少的特征文件
        missing_features = issues.get('missing_feature_files', [])
        if missing_features:
            # 假设missing_features是包含id信息的字典列表
            exp_ids = [item.get('id') if isinstance(item, dict) else item for item in missing_features]
            # 过滤掉None值并确保是整数ID
            valid_exp_ids = [exp_id for exp_id in exp_ids if exp_id is not None and isinstance(exp_id, int)]
            experiments = [self.get_experiment(exp_id) for exp_id in valid_exp_ids]
            experiments = [exp for exp in experiments if exp]
            
            if experiments:
                results = self.batch_extract_features(experiments)
                fixes['fixed'] += len(results['successful'])
                fixes['failed'] += len(results['failed'])
        
        # 清理孤立记录
        orphaned = issues.get('orphaned_records', [])
        if orphaned:
            cleaned = self.catalog.clean_orphaned_records()
            fixes['fixed'] += cleaned
        
        return fixes
    
    # ==================== 生命周期管理 ====================
    
    def create_experiment(self, source_dir: str, auto_extract_features: bool = True,
                         feature_versions: Optional[List[str]] = None) -> Optional[UnifiedExperiment]:
        """创建新实验 - 完整的生命周期管理"""
        try:
            # 1. 转换CSV/JSON到HDF5 - 需要确保导入路径正确
            try:
                from ..csv2hdf.direct_csv2hdf import direct_convert_csvjson_to_hdf5
            except ImportError:
                logger.error("Cannot import direct_convert_csvjson_to_hdf5")
                return None
                
            raw_dir = str(self.catalog.config.get_absolute_path('raw_data'))
            hdf5_file = direct_convert_csvjson_to_hdf5(source_dir, raw_dir)
            
            # 2. 检查转换结果并索引到catalog
            if not hdf5_file:
                logger.error("Failed to convert CSV/JSON to HDF5")
                return None
                
            record = self.catalog.index_file(hdf5_file)
            if not record:
                return None
            
            # 3. 创建统一实验对象
            exp = UnifiedExperiment(record, self)
            
            # 4. 自动提取特征
            if auto_extract_features:
                versions_to_use = feature_versions if feature_versions else ['v1']
                for version in versions_to_use:
                    self.batch_extract_features([exp], version)
            
            return exp
            
        except Exception as e:
            logger.error(f"Failed to create experiment: {e}")
            return None
    
    def sync_all(self) -> Dict[str, Any]:
        """执行完整同步"""
        try:
            result = self.catalog.bidirectional_sync()
            return {
                'success': result.is_successful,
                'files_processed': result.files_processed,
                'files_added': result.files_added,
                'files_updated': result.files_updated,
                'errors': result.errors,
                'duration': result.duration
            }
        except Exception as e:
            logger.error(f"Sync failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取系统统计信息"""
        try:
            return self.catalog.get_summary_report()
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {'error': str(e)}

    # ==================== Workflow Metadata 初始化 ====================

    def initialize_workflow_metadata(self, force_update: bool = False) -> Dict[str, Any]:
        """
        批量初始化/更新实验的 workflow 元数据到数据库

        将所有实验的 workflow 信息扁平化并存储到数据库，
        这样后续的搜索和查询就不需要每次都重新计算。

        Args:
            force_update: 是否强制更新所有实验（包括已有 workflow metadata 的）

        Returns:
            Dict[str, Any]: 执行结果统计
                - total: 总实验数
                - updated: 成功更新的实验数
                - skipped: 跳过的实验数
                - failed: 失败的实验数
                - errors: 错误列表
        """
        logger.info(f"Starting workflow metadata initialization (force_update={force_update})")

        # 获取需要更新的实验
        if force_update:
            experiments = self.search()
            logger.info(f"Force update mode: processing all {len(experiments)} experiments")
        else:
            # 只获取没有 workflow metadata 的实验
            records = self.catalog.repository.get_experiments_without_workflow_metadata()
            experiments = [UnifiedExperiment(record, self) for record in records]
            logger.info(f"Incremental update mode: processing {len(experiments)} experiments without metadata")

        total = len(experiments)
        updated = 0
        skipped = 0
        failed = 0
        errors = []

        # 批量准备更新数据
        updates = []

        for i, exp in enumerate(experiments):
            try:
                # 提取 workflow metadata
                workflow_metadata_dict = flatten_workflow(exp)

                if not workflow_metadata_dict:
                    logger.debug(f"Experiment {exp.id} ({exp.chip_id}-{exp.device_id}) has no workflow")
                    skipped += 1
                    continue

                # 转换为 JSON 字符串
                workflow_metadata_json = json.dumps(workflow_metadata_dict, ensure_ascii=False)

                # 添加到批量更新列表
                updates.append((exp.id, workflow_metadata_json))

                if (i + 1) % 100 == 0:
                    logger.info(f"Processed {i + 1}/{total} experiments")

            except Exception as e:
                error_msg = f"Failed to extract workflow for experiment {exp.id}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
                failed += 1

        # 执行批量更新
        if updates:
            logger.info(f"Updating {len(updates)} experiments in database...")
            updated_count = self.catalog.repository.batch_update_workflow_metadata(updates)
            updated = updated_count
            logger.info(f"Successfully updated {updated} experiments")

        result = {
            'total': total,
            'updated': updated,
            'skipped': skipped,
            'failed': failed,
            'errors': errors
        }

        logger.info(f"Workflow metadata initialization completed: {result}")
        return result

    def close(self):
        """关闭管理器，释放资源"""
        try:
            self.catalog.close()
            logger.info("UnifiedExperimentManager closed")
        except Exception as e:
            logger.error(f"Error closing UnifiedExperimentManager: {e}")
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        # 参数未使用，但是标准的上下文管理器接口要求这些参数
        _ = exc_type, exc_val, exc_tb
        self.close()


# ==================== 并行提取辅助函数 ====================

def _extract_v2_wrapper(
    exp_id, chip_id, device_id, file_path, feature_config, output_dir, save_format
):
    """V2 特征提取包装函数（用于多进程）

    Args:
        exp_id: 实验ID
        chip_id: 芯片ID
        device_id: 设备ID
        file_path: 原始数据文件路径
        feature_config: 特征配置
        output_dir: 输出目录
        save_format: 保存格式

    Returns:
        Dict: 包含 exp_id, time_ms, metadata 等信息
    """
    from infra.features_v2 import FeatureSet
    from infra.experiment import Experiment
    import infra.features_v2.extractors.transfer
    import infra.features_v2.extractors.transient
    import time
    from datetime import datetime
    from hashlib import md5

    # 加载实验
    experiment = Experiment(file_path)

    # 解析配置
    if isinstance(feature_config, str):
        from infra.features_v2.config.parser import ConfigParser

        # 检查是否为完整路径
        config_path = Path(feature_config)
        is_valid_config_file = (
            config_path.suffix in ['.yaml', '.yml'] and
            config_path.exists() and
            config_path.is_file()
        )

        if not is_valid_config_file:
            # 尝试从多个位置查找配置文件
            # 1. catalog/feature_configs
            catalog_config_path = Path(__file__).parent / 'feature_configs' / f'{feature_config}.yaml'
            if catalog_config_path.exists():
                config_path = catalog_config_path
            else:
                # 2. features_v2/config/templates
                template_path = Path(__file__).parent.parent / 'features_v2' / 'config' / 'templates' / f'{feature_config}.yaml'
                if template_path.exists():
                    config_path = template_path
                else:
                    raise ValueError(
                        f"配置文件不存在: {feature_config}, "
                        f"也未在 catalog/feature_configs 或 features_v2/config/templates 中找到"
                    )

        config_name = config_path.stem
        features = FeatureSet.from_config(str(config_path), experiment=experiment)
    else:
        config_name = 'inline_config'
        features = FeatureSet(experiment=experiment)
        for name, spec in feature_config.items():
            features.add(
                name=name,
                extractor=spec.get('extractor'),
                func=spec.get('func'),
                input=spec.get('input'),
                params=spec.get('params', {}),
            )

    # 计算
    start = time.time()
    result = features.compute()
    elapsed_ms = (time.time() - start) * 1000
    stats = features.get_statistics()

    # 保存
    output_path = None
    if save_format == 'parquet':
        config_hash = md5(config_name.encode()).hexdigest()[:8]
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        filename = (
            f"{chip_id}-{device_id}-{config_name}-"
            f"feat_{timestamp}_{config_hash}.parquet"
        )
        output_path = str(Path(output_dir) / filename)
        features.to_parquet(output_path)

    # 准备元数据
    metadata = {
        'configs_used': [config_name],
        'last_computed': datetime.now().isoformat(),
        'feature_count': len(result),
        'computation_stats': {
            'total_time_ms': elapsed_ms,
            'cache_hits': stats.get('cache_hits', 0),
            'cache_misses': stats.get('cache_misses', 0),
        },
    }

    if output_path:
        metadata['output_files'] = [output_path]

    return {
        'exp_id': exp_id,
        'time_ms': elapsed_ms,
        'metadata': metadata,
        'output_path': output_path,
    }