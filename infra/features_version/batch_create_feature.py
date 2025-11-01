
from pathlib import Path
from typing import Callable
import inspect
from tqdm import tqdm

########################### 日志设置 ################################
from ..logger_config import get_module_logger
logger = get_module_logger() 
#####################################################################


def batch_create_features(
    source_directory: str, 
    output_dir: str,
    processing_func: Callable[[str, str], str]
) -> None:
    """
    批量处理目录下的所有原始数据文件
    
    Args:
        source_directory: 原始数据文件目录
        output_dir: 输出目录
        processing_func: 用于处理单个文件的函数，应该接受(raw_file_path, output_dir)参数并返回特征文件路径。
    """
    if processing_func is None:
        raise ValueError("processing_func参数为必填参数，不能为None")
    
    # 开始批量处理
    logger.info("=== 批量创建特征文件 ===")
    logger.info(f"源目录: {source_directory}")
    logger.info(f"输出目录: {output_dir}")
    
    # 查找所有原始数据文件
    source_path = Path(source_directory)
    raw_files = list(source_path.glob("*-test_*.h5"))
    
    if not raw_files:
        logger.error("❌ 未找到原始数据文件")
        return
    
    logger.info(f"找到 {len(raw_files)} 个原始数据文件")
    
    successful_count = 0
    failed_files = []
    
    # 使用tqdm显示进度条
    with tqdm(raw_files, desc="处理特征文件", unit="文件") as pbar:
        for raw_file in pbar:
            # 更新进度条描述，显示当前文件名
            current_file_short = raw_file.name[:50] + "..." if len(raw_file.name) > 50 else raw_file.name
            pbar.set_description(f"处理: {current_file_short}")
            
            try:
                feature_file = processing_func(str(raw_file), output_dir)
                successful_count += 1
                
                # 更新进度条后缀，显示统计信息
                pbar.set_postfix({
                    "成功": successful_count, 
                    "失败": len(failed_files),
                    "进度": f"{successful_count + len(failed_files)}/{len(raw_files)}"
                })
                
                # 详细日志记录到文件，不影响进度条显示
                logger.info(f"✅ 成功: {raw_file.name} -> {Path(feature_file).name}")
                
            except Exception as e:
                failed_files.append((raw_file.name, str(e)))
                
                # 更新进度条后缀
                pbar.set_postfix({
                    "成功": successful_count, 
                    "失败": len(failed_files),
                    "进度": f"{successful_count + len(failed_files)}/{len(raw_files)}"
                })
                
                # 详细错误日志记录到文件
                logger.error(f"❌ 失败: {raw_file.name} - {e}")
    
    # 最终结果统计（同时显示在控制台和日志中）
    print(f"\n=== 批量处理完成 ===")
    print(f"✅ 成功: {successful_count}/{len(raw_files)} 个文件")
    
    if failed_files:
        print(f"❌ 失败: {len(failed_files)} 个文件")
        print("失败的文件:")
        for filename, error in failed_files:
            print(f"  - {filename}: {error}")
    
    # 同时记录到日志文件
    logger.info(f"批量处理完成 - 成功: {successful_count}/{len(raw_files)}, 失败: {len(failed_files)}")
    if failed_files:
        logger.warning("失败的文件列表:")
        for filename, error in failed_files:
            logger.warning(f"  - {filename}: {error}")