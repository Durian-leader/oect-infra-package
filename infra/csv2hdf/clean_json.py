import json
import os
from typing import Dict, Any

########################### 日志设置 ################################
from ..logger_config import get_module_logger
logger = get_module_logger()
#####################################################################

def clean_test_info_json(input_file: str, output_file: str = None) -> Dict[str, Any]:
    """
    清理test_info.json文件，去除冗余信息并扁平化结构
    
    Args:
        input_file: 输入JSON文件路径
        output_file: 输出JSON文件路径（可选，不提供则覆盖原文件）
    
    Returns:
        清理后的JSON数据
    """
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 删除test_type字段
    if 'test_type' in data:
        del data['test_type']
    
    # 重命名device_id为test_unit_id
    if 'device_id' in data:
        data['test_unit_id'] = data.pop('device_id')
    
    # 将metadata中的内容扁平化到根级别
    if 'metadata' in data:
        metadata = data.pop('metadata')
        # 去除raw_params
        if 'raw_params' in metadata:
            del metadata['raw_params']
        # 将剩余的metadata内容直接添加到根级别
        for key, value in metadata.items():
            if key not in data:  # 避免覆盖已有的键
                data[key] = value
    
    # 将summary扁平化并去除冗余的total_steps
    if 'summary' in data:
        summary = data.pop('summary')
        if 'completed_steps' in summary:
            data['completed_steps'] = summary['completed_steps']
        if 'completion_percentage' in summary:
            data['completion_percentage'] = summary['completion_percentage']
        # summary中的total_steps是冗余的，不再添加
    
    # 去除steps中每个step的workflow_info中的冗余信息（如果需要）
    if 'steps' in data:
        for step in data['steps']:
            if 'workflow_info' in step:
                # 保留关键信息，去除过于详细的path信息
                if 'path' in step['workflow_info']:
                    del step['workflow_info']['path']
    
    # 重新排序字段，使其更适合人类阅读
    ordered_data = {}
    
    # 0. 新增字段（放在最前面）
    if 'sync_mode' in data:
        ordered_data['sync_mode'] = data['sync_mode']
    if 'batch_id' in data:
        ordered_data['batch_id'] = data['batch_id']
    
    # 1. 基本信息
    if 'test_id' in data:
        ordered_data['test_id'] = data['test_id']
    if 'name' in data:
        ordered_data['name'] = data['name']
    if 'description' in data:
        ordered_data['description'] = data['description']
    
    # 2. 设备信息
    if 'test_unit_id' in data:
        ordered_data['test_unit_id'] = data['test_unit_id']
    if 'chip_id' in data:
        ordered_data['chip_id'] = data['chip_id']
    if 'device_number' in data:
        ordered_data['device_number'] = data['device_number']
    
    # 3. 连接信息
    if 'port' in data:
        ordered_data['port'] = data['port']
    if 'baudrate' in data:
        ordered_data['baudrate'] = data['baudrate']
    
    # 4. 时间信息
    if 'created_at' in data:
        ordered_data['created_at'] = data['created_at']
    if 'completed_at' in data:
        ordered_data['completed_at'] = data['completed_at']
    
    # 5. 状态和统计
    if 'status' in data:
        ordered_data['status'] = data['status']
    if 'total_steps' in data:
        ordered_data['total_steps'] = data['total_steps']
    if 'completed_steps' in data:
        ordered_data['completed_steps'] = data['completed_steps']
    if 'completion_percentage' in data:
        ordered_data['completion_percentage'] = data['completion_percentage']
    
    # 6. 详细步骤数据
    if 'steps' in data:
        ordered_data['steps'] = data['steps']
    
    # 7. 添加任何遗漏的字段
    for key, value in data.items():
        if key not in ordered_data:
            ordered_data[key] = value
    
    # 如果没有指定输出文件，则覆盖原文件
    if output_file is None:
        output_file = input_file
    
    # 写入清理后的JSON
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(ordered_data, f, indent=4, ensure_ascii=False)
    
    logger.info(f"已清理JSON文件: {input_file}")
    logger.info(f"输出到: {output_file}")
    
    return data

def batch_clean_json_files(directory: str, pattern: str = "test_info.json"):
    """
    批量清理目录下所有匹配的JSON文件
    
    Args:
        directory: 要扫描的目录
        pattern: 文件名模式
    """
    count = 0
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file == pattern:
                file_path = os.path.join(root, file)
                try:
                    clean_test_info_json(file_path)
                    count += 1
                except Exception as e:
                    logger.error(f"处理文件失败 {file_path}: {e}")
    
    logger.info(f"共处理了 {count} 个文件")

if __name__ == "__main__":
    # 示例用法
    test_file = r"D:\课题组\Topic\ForInflux\20250814\Test_Unit_C1_20250813214025_20250813-214025_workflow_test_20250813214025_95399ab5\test_info.json"
    
    # 清理单个文件
    clean_test_info_json(test_file, test_file.replace(".json", "_cleaned.json"))
    
    # 或者批量清理整个目录下的所有test_info.json文件
    # batch_clean_json_files(r"D:\课题组\Topic\ForInflux\20250814")