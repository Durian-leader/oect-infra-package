"""
通用版本化工具

提供特征版本化的通用逻辑，供v1_feature.py, v2_feature.py等复用
"""
from typing import List
from ..features import FeatureRepository, VersionManager
from ..experiment import Experiment

########################### 日志设置 ################################
from ..logger_config import get_module_logger
logger = get_module_logger() 
#####################################################################


def create_version_from_all_features(
    repo: FeatureRepository,
    version_name: str,
    exp: Experiment,
    data_type: str = "transfer",
    include_verification: bool = True
) -> bool:
    """
    从所有可用特征创建版本化特征矩阵
    
    Args:
        repo: 特征数据仓库实例
        version_name: 版本名称 (如 "v1", "v2", "v3")
        exp: 实验对象，用于获取步骤信息
        data_type: 数据类型，'transfer' 或 'transient'
        include_verification: 是否包含文件结构验证步骤
        
    Returns:
        是否成功创建版本
        
    Examples:
        >>> from features_version.create_version_utils import create_version_from_all_features
        >>> repo = FeatureRepository("path/to/feature.h5")
        >>> exp = Experiment("path/to/raw.h5")
        >>> success = create_version_from_all_features(repo, "v1", exp)
    """
    logger.info(f"6. 创建版本化特征矩阵（包含所有可用特征）...")
    
    # 🚀 获取所有已存储的特征，而不是固定列表
    all_available_features = repo.list_features(data_type)
    logger.info(f"发现 {len(all_available_features)} 个已存储的特征")
    logger.debug(f"特征列表: {all_available_features}")
    
    # 验证所有特征都能正确读取，并从存储的元数据中获取单位和描述
    valid_features = []
    feature_units = []
    feature_descriptions = []
    
    for feature_name in all_available_features:
        feature_data = repo.get_feature(feature_name, data_type)
        if feature_data is not None and len(feature_data) > 0:
            valid_features.append(feature_name)
            
            # 🎯 从已存储的特征元数据中读取单位和描述
            feature_info = repo.get_feature_info(feature_name, data_type)
            if feature_info:
                unit = feature_info.unit or ''  # 使用存储的单位
                desc = feature_info.description or f'Feature: {feature_name}'  # 使用存储的描述
            else:
                # 如果元数据不存在，使用默认值
                unit = ''
                desc = f'Feature: {feature_name}'
            
            feature_units.append(unit)
            feature_descriptions.append(desc)
        else:
            logger.warning(f"⚠️ 跳过无效特征: {feature_name}")
    
    version_features = valid_features
    logger.info(f"验证通过的特征: {len(version_features)}个")
    
    if len(version_features) == 0:
        logger.warning(f"⚠️ 没有有效特征可以版本化")
        return False
    
    # 创建版本化特征矩阵
    version_manager = VersionManager(repo)
    version_success = version_manager.create_version(
        version_name, 
        version_features,
        data_type=data_type,
        feature_units=feature_units,
        feature_descriptions=feature_descriptions,
        force_overwrite=True  # 🔄 确保版本创建使用覆盖模式
    )
    
    if version_success:
        logger.info(f"✅ 版本{version_name}创建成功: 包含 {len(version_features)} 个特征")
        
        # 获取步骤数信息
        if data_type == "transfer":
            summary = exp.get_transfer_summary()
            step_count = summary['step_count'] if summary else 'unknown'
        else:  # transient
            summary = exp.get_transient_summary()
            step_count = summary['step_count'] if summary else 'unknown'
            
        logger.info(f"版本化特征矩阵形状: ({step_count}, {len(version_features)})")
        logger.debug("包含的特征:")
        for i, (name, unit, desc) in enumerate(zip(version_features, feature_units, feature_descriptions)):
            logger.debug(f"   {i+1:2d}. {name:<25} [{unit or 'unitless'}] - {desc}")
    else:
        logger.error(f"❌ 版本{version_name}创建失败")
        return False
    
    # 7. 验证文件结构（可选）
    if include_verification:
        logger.info("7. 验证特征文件结构...")
        verification_success = verify_feature_file_structure(repo, version_manager, version_name, version_features, data_type)
        if not verification_success:
            logger.warning(f"⚠️ 版本{version_name}验证失败")
            return False
    
    return True


def verify_feature_file_structure(
    repo: FeatureRepository,
    version_manager: VersionManager,
    version_name: str,
    version_features: List[str],
    data_type: str = "transfer"
) -> bool:
    """
    验证特征文件结构
    
    Args:
        repo: 特征数据仓库实例
        version_manager: 版本管理器实例
        version_name: 版本名称
        version_features: 版本特征列表
        data_type: 数据类型
        
    Returns:
        是否验证成功
    """
    try:
        # 验证数据可以正常读取（使用第一个有效特征进行测试）
        if version_features:
            test_feature_name = version_features[0]
            test_feature = repo.get_feature(test_feature_name, data_type)
            if test_feature is not None:
                logger.debug(f"✓ 特征数据读取正常: {test_feature.shape}, {test_feature.dtype}")
                logger.debug(f"✓ 测试特征: {test_feature_name}")
            else:
                logger.warning(f"⚠️ 测试特征读取失败: {test_feature_name}")
                return False
        
        # 验证版本矩阵
        version_matrix = version_manager.get_version_matrix(version_name, data_type)
        if version_matrix is not None:
            logger.debug(f"✓ 版本矩阵读取正常: {version_matrix.shape}, {version_matrix.dtype}")
            logger.debug(f"✓ 包含 {version_matrix.shape[0]} 个步骤 × {version_matrix.shape[1]} 个特征")
        else:
            logger.warning(f"⚠️ 版本矩阵读取失败")
            return False
            
        logger.info("✅ 文件结构验证通过！")
        return True
        
    except Exception as e:
        logger.warning(f"⚠️ 验证警告: {e}")
        return False