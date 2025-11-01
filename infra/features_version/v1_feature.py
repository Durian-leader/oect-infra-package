import numpy as np
from ..experiment import Experiment
from ..oect_transfer import analyze_experiment_transfer_batch
from ..features import (
    FeatureFileCreator, FeatureRepository, FeatureMetadata
)
import os
from pathlib import Path
from .create_version_utils import create_version_from_all_features

########################### 日志设置 ################################
from ..logger_config import get_module_logger
logger = get_module_logger() 
#####################################################################

def v1_feature(raw_file_path: str, output_dir: str = "data/features") -> str:
    """
    使用features包创建最终的HDFView兼容特征文件
    
    Args:
        raw_file_path: 原始实验数据文件路径
        output_dir: 输出目录，默认为data/features/
        
    Returns:
        创建的特征文件路径
    """
    logger.info(f"=== 创建HDFView兼容特征文件 ===")
    logger.info(f"原始文件: {raw_file_path}")
    
    # 确定输出目录和文件名（output_dir现在有默认值）
    
    # 从原始文件名生成特征文件名
    raw_path = Path(raw_file_path)
    feature_filename = FeatureFileCreator.parse_raw_filename_to_feature(raw_path.name)
    final_feature_file = os.path.join(output_dir, feature_filename)
    
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    logger.info(f"输出文件: {final_feature_file}")
    
    # 🔍 检查特征文件是否已存在，决定是否需要创建HDF5文件结构
    if os.path.exists(final_feature_file):
        logger.info(f"✅ 特征文件已存在，跳过HDF5文件结构创建")
        logger.info(f"使用现有文件: {final_feature_file}")
    else:
        logger.info("📁 特征文件不存在，创建HDF5文件结构...")
        # 需要先加载实验数据以获取元数据信息
        exp = Experiment(raw_file_path)
        summary = exp.get_experiment_summary()
        
        creator = FeatureFileCreator()
        creator.create_feature_file(
            final_feature_file,
            chip_id=summary['device_info']['chip_id'],
            device_id=summary['device_info']['device_number'],
            description=summary['basic_info']['description'],
            test_id=summary['basic_info']['test_id'],
            built_with="features v1.0.0"
        )
        logger.info(f"✅ HDF5文件结构创建成功：{final_feature_file}")
    
    # 📊 无论文件是否存在，都要进行特征提取和保存（这是数据更新操作）
    logger.info("=" * 50)
    logger.info("开始特征提取和保存...")
    
    # 1. 加载实验数据
    logger.info("1. 加载实验数据...")
    exp = Experiment(raw_file_path)
    summary = exp.get_experiment_summary()
    logger.info(f"实验信息: {summary['basic_info']}")
    logger.info(f"设备信息: {summary['device_info']}")
    
    # 2. 计算Transfer特征
    logger.info("2. 计算Transfer特征...")
    transfer_data = exp.get_transfer_all_measurement()

    from ..oect_transfer import BatchTransfer
    if transfer_data is not None and 'measurement_data' in transfer_data:
        measurement_3d = transfer_data['measurement_data']
        batch_transfer = BatchTransfer(measurement_3d, device_type="N")
    else:
        logger.error(f"No transfer data found in {raw_file_path}")
        batch_transfer = None
    if batch_transfer is None:
        raise ValueError("无法分析Transfer特征，可能没有Transfer数据")
    
    step_count = batch_transfer.Vg.raw.shape[0]
    logger.info(f"分析了 {step_count} 个Transfer步骤")
    
    # 3. 提取特征数据
    logger.info("3. 提取特征数据...")
    features_data = {
        # 特征值
        'absgm_max_forward': batch_transfer.absgm_max.forward,
        'absgm_max_reverse': batch_transfer.absgm_max.reverse,
        'Von_forward': batch_transfer.Von.forward,
        'Von_reverse': batch_transfer.Von.reverse,
        'absI_max_raw': batch_transfer.absI_max.raw,
        
        # 坐标数据 (拆分为Vg和Id)
        'absgm_max_forward_Vg': batch_transfer.absgm_max.forward_coords[:, 0],
        'absgm_max_forward_Id': batch_transfer.absgm_max.forward_coords[:, 1],
        'absgm_max_reverse_Vg': batch_transfer.absgm_max.reverse_coords[:, 0],
        'absgm_max_reverse_Id': batch_transfer.absgm_max.reverse_coords[:, 1],
        'Von_forward_Vg': batch_transfer.Von.forward_coords[:, 0],
        'Von_forward_Id': batch_transfer.Von.forward_coords[:, 1],
        'Von_reverse_Vg': batch_transfer.Von.reverse_coords[:, 0],
        'Von_reverse_Id': batch_transfer.Von.reverse_coords[:, 1],
        'absI_max_raw_Vg': batch_transfer.absI_max.raw_coords[:, 0],
        'absI_max_raw_Id': batch_transfer.absI_max.raw_coords[:, 1],
    }
    
    feature_count = len(features_data)
    logger.info(f"提取了 {feature_count} 个特征，{step_count} 个步骤")
    
    # 4. 存储特征数据
    logger.info("4. 存储特征数据...")
    repo = FeatureRepository(final_feature_file)
    
    # 定义特征元数据
    feature_metadata = {}
    for feature_name in features_data.keys():
        if 'gm' in feature_name:
            unit = 'S'
            description = f'Transconductance feature {feature_name}'
        elif 'Von' in feature_name:
            unit = 'V'
            description = f'Threshold voltage feature {feature_name}'
        elif 'absI' in feature_name:
            unit = 'A'
            description = f'Current feature {feature_name}'
        else:
            unit = ''
            description = f'Feature {feature_name}'
        
        feature_metadata[feature_name] = FeatureMetadata(
            name=feature_name,
            unit=unit,
            description=description
        )
    
    # 批量存储特征（覆盖模式）
    results = repo.store_multiple_features(
        {name: np.array(data, dtype=np.float32) for name, data in features_data.items()},
        data_type="transfer",
        metadata_dict=feature_metadata,
        bucket_name="bk_00",
        overwrite=True
    )
    
    successful_features = sum(results.values())
    logger.info(f"成功存储 {successful_features}/{feature_count} 个特征")
    
    # 6-7. 使用通用版本化工具创建版本和验证
    version_success = create_version_from_all_features(
        repo=repo,
        version_name="v1",
        exp=exp,
        data_type="transfer",
        include_verification=True
    )
    
    if not version_success:
        logger.error(f"❌ 版本v1创建或验证失败")
    
    # 完成状态
    if version_success:
        logger.info(f"✅ 特征文件创建完成: {Path(final_feature_file).name}")
    else:
        logger.error(f"❌ 特征文件创建失败: {Path(final_feature_file).name}")
    
    return final_feature_file
