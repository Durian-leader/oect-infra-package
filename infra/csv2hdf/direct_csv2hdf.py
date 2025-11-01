# -*- coding: utf-8 -*-
"""
直接从CSV生成新格式HDF5文件

这个模块替代了传统的step-by-step存储方式，直接将CSV数据组织为新的批量格式：
- Transfer数据: 3D numpy数组 [步骤索引, 数据类型, 数据点索引]
- Transient数据: 2D numpy数组 [数据类型, 数据点索引] (所有步骤拼接)
"""
from __future__ import annotations
import os
import json
from typing import Any, Dict, List, Tuple, Optional
import numpy as np
import pandas as pd
import h5py
from glob import glob

# 多进程支持
try:
    from .parallel_csv_processing import (
        process_experiment_csvs_parallel, 
        ProcessedCSVResult,
        optimize_process_count
    )
    PARALLEL_SUPPORT = True
except ImportError:
    PARALLEL_SUPPORT = False
    logger.warning("Parallel CSV processing not available")

########################### 日志设置 ################################
from ..logger_config import get_module_logger
logger = get_module_logger()
#####################################################################


def _to_vlen_str():
    """创建可变长度UTF-8字符串数据类型"""
    return h5py.string_dtype(encoding="utf-8", length=None)


def _read_json(json_path: str) -> Dict[str, Any]:
    """读取JSON文件"""
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _find_csvs_for_step(step_info: Dict[str, Any], csv_dir: str, step_idx: int) -> List[str]:
    """为步骤查找对应的CSV文件"""
    # 1) 从步骤信息中查找CSV路径
    candidates = []
    
    # 递归搜索所有字符串值，查找.csv文件名
    def collect_csv_paths(obj):
        if isinstance(obj, dict):
            for v in obj.values():
                collect_csv_paths(v)
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                collect_csv_paths(v)
        elif isinstance(obj, str) and obj.lower().endswith(".csv"):
            candidates.append(os.path.basename(obj))
    
    collect_csv_paths(step_info)
    
    # 检查候选文件是否存在
    for candidate in candidates:
        full_path = os.path.join(csv_dir, candidate)
        if os.path.exists(full_path):
            return [full_path]
    
    # 2) 回退方案：使用步骤索引模式查找
    patterns = [
        os.path.join(csv_dir, f"{step_idx}_*.csv"),
        os.path.join(csv_dir, f"step{step_idx}_*.csv"),
        os.path.join(csv_dir, f"{step_idx}.csv")
    ]
    
    for pattern in patterns:
        matches = sorted(glob(pattern))
        if matches:
            return matches
    
    return []


def _load_csv_data(csv_path: str, step_type: str) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """
    加载CSV文件并根据步骤类型提取相应数据
    
    Args:
        csv_path: CSV文件路径
        step_type: 步骤类型 ('transfer' 或 'transient')
        
    Returns:
        根据步骤类型返回相应的数据数组对
    """
    try:
        # 尝试多种编码方式读取CSV
        try:
            df = pd.read_csv(csv_path)
        except UnicodeDecodeError:
            try:
                df = pd.read_csv(csv_path, encoding="utf-8-sig")
            except UnicodeDecodeError:
                df = pd.read_csv(csv_path, encoding="gbk")
    except Exception as e:
        logger.warning(f"无法读取CSV文件 {csv_path}: {e}")
        return None
    
    if step_type == 'transfer':
        # Transfer数据：查找Vg和Id列
        vg_data = None
        id_data = None
        
        for vg_col in ['Vg', 'gate_voltage', 'vg']:
            if vg_col in df.columns:
                vg_data = df[vg_col].to_numpy()
                break
        
        for id_col in ['Id', 'drain_current', 'id']:
            if id_col in df.columns:
                id_data = df[id_col].to_numpy()
                break
        
        if vg_data is not None and id_data is not None:
            # 确保数据长度一致
            min_len = min(len(vg_data), len(id_data))
            return vg_data[:min_len], id_data[:min_len]
    
    elif step_type == 'transient':
        # Transient数据：查找Time和Id列
        time_data = None
        id_data = None
        
        for time_col in ['Time', 'timestamp', 'time']:
            if time_col in df.columns:
                time_data = df[time_col].to_numpy()
                break
        
        for id_col in ['Id', 'drain_current', 'id']:
            if id_col in df.columns:
                id_data = df[id_col].to_numpy()
                break
        
        if time_data is not None and id_data is not None:
            # 确保数据长度一致
            min_len = min(len(time_data), len(id_data))
            return time_data[:min_len], id_data[:min_len]
    
    return None


def _flatten_dict(d: Dict[str, Any], prefix: str = "", separator: str = "_") -> Dict[str, Any]:
    """将嵌套字典展平为单层字典"""
    flattened = {}
    for key, value in d.items():
        new_key = f"{prefix}{separator}{key}" if prefix else key
        if isinstance(value, dict):
            flattened.update(_flatten_dict(value, new_key, separator))
        elif value is not None:
            flattened[new_key] = value
    return flattened


def _extract_step_info(step_info: Dict[str, Any], step_idx: int) -> Dict[str, Any]:
    """从步骤信息中提取并展平所有信息"""
    info = {'step_index': step_idx}
    
    # 提取基本字段
    basic_fields = ['type', 'start_time', 'end_time', 'reason', 'data_file']
    for field in basic_fields:
        if field in step_info:
            info[field] = step_info[field]
    
    # 展平parameters
    if 'parameters' in step_info:
        params = _flatten_dict(step_info['parameters'], 'param')
        info.update(params)
    
    # 展平workflow信息
    if 'workflow_info' in step_info:
        workflow = _flatten_dict(step_info['workflow_info'], 'workflow')
        info.update(workflow)
    
    return info


def _store_dataframe_as_structured_array(group: h5py.Group, dataset_name: str, df: pd.DataFrame):
    """将pandas DataFrame存储为HDF5结构化数组"""
    if df.empty:
        return
    
    # 创建结构化数组的dtype
    dtypes = []
    data_arrays = []
    
    for col in df.columns:
        col_data = df[col]
        if pd.api.types.is_string_dtype(col_data) or pd.api.types.is_object_dtype(col_data):
            # 字符串列
            max_len = col_data.astype(str).str.len().max() if not col_data.empty else 10
            max_len = max(max_len, 10)  # 最少10个字符
            dtypes.append((str(col), f'S{max_len}'))
            data_arrays.append(col_data.fillna('').astype(str).str.encode('utf-8'))
        elif pd.api.types.is_integer_dtype(col_data):
            # 整数列
            dtypes.append((str(col), 'i8'))
            data_arrays.append(col_data.fillna(0).astype(np.int64))
        elif pd.api.types.is_float_dtype(col_data):
            # 浮点列
            dtypes.append((str(col), 'f8'))
            data_arrays.append(col_data.fillna(np.nan).astype(np.float64))
        else:
            # 其他类型，转为字符串
            dtypes.append((str(col), 'S50'))
            data_arrays.append(col_data.astype(str).fillna('').str.encode('utf-8'))
    
    # 创建结构化数组
    structured_array = np.empty(len(df), dtype=dtypes)
    for i, col in enumerate(df.columns):
        structured_array[str(col)] = data_arrays[i]
    
    # 存储到HDF5
    if dataset_name in group:
        del group[dataset_name]
    
    dataset = group.create_dataset(
        dataset_name,
        data=structured_array,
        compression='gzip',
        compression_opts=4,
        shuffle=True,
        fletcher32=True
    )
    
    # 添加属性
    dataset.attrs['description'] = "Step information table stored as structured array"
    dataset.attrs['columns'] = np.array(list(df.columns), dtype=_to_vlen_str())


def direct_csv_to_new_hdf5(json_path: str, csv_dir: str, output_h5_path: str):
    """
    直接从CSV和JSON生成新格式的HDF5文件
    
    Args:
        json_path: test_info.json文件路径
        csv_dir: 包含CSV文件的目录
        output_h5_path: 输出的HDF5文件路径
    """
    logger.info(f"开始直接转换: JSON={json_path}, CSV_DIR={csv_dir} -> HDF5={output_h5_path}")
    
    # 读取JSON文件
    json_data = _read_json(json_path)
    steps = json_data.get('steps', [])
    
    if not steps:
        raise ValueError("JSON文件中没有找到steps数据")
    
    # 分类步骤数据
    transfer_steps = []
    transient_steps = []
    transfer_step_infos = []
    transient_step_infos = []
    
    for step_idx, step_info in enumerate(steps):
        step_type = step_info.get('type', '').lower()
        
        if step_type not in ['transfer', 'transient']:
            continue
        
        # 查找CSV文件
        csv_files = _find_csvs_for_step(step_info, csv_dir, step_idx + 1)
        if not csv_files:
            logger.warning(f"步骤 {step_idx + 1} ({step_type}) 未找到对应的CSV文件")
            continue
        
        # 加载CSV数据
        csv_data = _load_csv_data(csv_files[0], step_type)
        if csv_data is None:
            logger.warning(f"步骤 {step_idx + 1} ({step_type}) CSV数据加载失败")
            continue
        
        data1, data2 = csv_data
        
        if step_type == 'transfer':
            # Transfer数据: [Vg, Id]
            step_data = np.array([data1, data2])  # [2, n_points]
            transfer_steps.append(step_data)
            
            # 提取步骤信息
            step_info_flat = _extract_step_info(step_info, len(transfer_steps) - 1)
            transfer_step_infos.append(step_info_flat)
            
            logger.debug(f"Transfer步骤 {len(transfer_steps)}: Vg={len(data1)}, Id={len(data2)} 点")
        
        elif step_type == 'transient':
            # 收集transient数据用于后续拼接
            # 获取timeStep参数用于生成连续时间
            time_step_ms = 1.0  # 默认1ms
            if 'parameters' in step_info and 'timeStep' in step_info['parameters']:
                time_step_ms = step_info['parameters']['timeStep']
            
            transient_steps.append({
                'original_time': data1,
                'drain_current': data2,
                'time_step_ms': time_step_ms,
                'step_info': step_info
            })
            
            # 提取步骤信息
            step_info_flat = _extract_step_info(step_info, len(transient_steps) - 1)
            transient_step_infos.append(step_info_flat)
            
            logger.debug(f"Transient步骤 {len(transient_steps)}: Time={len(data1)}, Id={len(data2)} 点, timeStep={time_step_ms}ms")
    
    # 创建HDF5文件
    output_dir = os.path.dirname(output_h5_path)
    if output_dir:  # 只有当目录不为空时才创建
        os.makedirs(output_dir, exist_ok=True)
    
    with h5py.File(output_h5_path, "w") as h5:
        # 写入根级别属性
        h5.attrs["format_version"] = "2.0_direct_new_storage"
        
        # 写入所有JSON根级别属性
        for key, value in json_data.items():
            if key != 'steps' and not isinstance(value, (dict, list)):
                if isinstance(value, str):
                    h5.attrs[key] = value.encode('utf-8')
                else:
                    h5.attrs[key] = value
        
        # 备份原始JSON
        raw_group = h5.create_group("raw")
        raw_group.create_dataset("json", data=json.dumps(json_data).encode('utf-8'))
        
        # 处理Transfer数据
        if transfer_steps:
            transfer_group = h5.create_group('transfer')
            
            # 构建3D数组: [步骤索引, 数据类型, 数据点索引]
            max_points = max(step_data.shape[1] for step_data in transfer_steps)
            n_steps = len(transfer_steps)
            n_data_types = 2  # Vg, Id
            
            # 创建3D数组，用NaN填充
            measurement_data = np.full((n_steps, n_data_types, max_points), np.nan, dtype=np.float64)
            
            for step_idx, step_data in enumerate(transfer_steps):
                n_points = step_data.shape[1]
                measurement_data[step_idx, :, :n_points] = step_data
            
            # 存储3D测量数据
            dataset = transfer_group.create_dataset(
                'measurement_data',
                data=measurement_data,
                compression='gzip',
                compression_opts=4,
                shuffle=True,
                fletcher32=True
            )
            dataset.attrs['dimension_labels'] = np.array(['step_index', 'data_type', 'data_point'], dtype=_to_vlen_str())
            dataset.attrs['data_type_labels'] = np.array(['Vg', 'Id'], dtype=_to_vlen_str())
            dataset.attrs['description'] = "3D transfer measurement data: [step_index, data_type, data_point]"
            
            # 存储步骤信息表格
            if transfer_step_infos:
                step_info_df = pd.DataFrame(transfer_step_infos)
                _store_dataframe_as_structured_array(transfer_group, 'step_info_table', step_info_df)
            
            logger.info(f"Transfer数据: {n_steps}个步骤, 3D数组形状 {measurement_data.shape}")
        
        # 处理Transient数据
        if transient_steps:
            transient_group = h5.create_group('transient')

            # 拼接所有步骤的数据
            continuous_time = []
            original_time = []
            drain_current = []
            current_time_offset = 0.0
            current_data_index = 0  # 跟踪当前数据索引

            for i, step_data in enumerate(transient_steps):
                step_original_time = step_data['original_time']
                step_drain_current = step_data['drain_current']
                time_step_ms = step_data['time_step_ms']

                # 生成连续时间序列
                n_points = len(step_original_time)
                step_continuous_time = np.arange(n_points) * (time_step_ms / 1000.0) + current_time_offset

                # 拼接数据
                continuous_time.append(step_continuous_time)
                original_time.append(step_original_time)
                drain_current.append(step_drain_current)

                # 记录此步骤的数据索引范围
                transient_step_infos[i]['start_data_index'] = current_data_index
                transient_step_infos[i]['end_data_index'] = current_data_index + n_points
                current_data_index += n_points

                # 更新时间偏移
                current_time_offset = step_continuous_time[-1] + (time_step_ms / 1000.0)
            
            # 合并为最终数组
            continuous_time_array = np.concatenate(continuous_time)
            original_time_array = np.concatenate(original_time)
            drain_current_array = np.concatenate(drain_current)
            
            # 创建2D数组: [数据类型, 数据点索引]
            measurement_data = np.array([
                continuous_time_array,  # 数据类型0: 连续时间
                original_time_array,    # 数据类型1: 原始时间
                drain_current_array     # 数据类型2: 电流
            ])
            
            # 存储2D测量数据
            dataset = transient_group.create_dataset(
                'measurement_data',
                data=measurement_data,
                compression='gzip',
                compression_opts=4,
                shuffle=True,
                fletcher32=True
            )
            dataset.attrs['dimension_labels'] = np.array(['data_type', 'data_point'], dtype=_to_vlen_str())
            dataset.attrs['data_type_labels'] = np.array(['continuous_time', 'original_time', 'drain_current'], dtype=_to_vlen_str())
            dataset.attrs['description'] = "2D transient measurement data: [data_type, data_point]"
            
            # 存储步骤信息表格
            if transient_step_infos:
                step_info_df = pd.DataFrame(transient_step_infos)
                _store_dataframe_as_structured_array(transient_group, 'step_info_table', step_info_df)
            
            logger.info(f"Transient数据: {len(transient_steps)}个步骤, 2D数组形状 {measurement_data.shape}, 总点数: {measurement_data.shape[1]}")
    
    logger.info(f"新格式HDF5文件创建完成: {output_h5_path}")


def direct_csv_to_new_hdf5_parallel(
    json_path: str, 
    csv_dir: str, 
    output_h5_path: str,
    max_workers: Optional[int] = None,
    enable_parallel: bool = True
):
    """
    多进程版本：直接从CSV和JSON生成新格式的HDF5文件
    
    通过并行处理CSV文件来提升转换性能，特别适合有大量步骤的实验。
    
    Args:
        json_path: test_info.json文件路径
        csv_dir: 包含CSV文件的目录
        output_h5_path: 输出的HDF5文件路径
        max_workers: 最大工作进程数，None为自动优化
        enable_parallel: 是否启用并行处理，False时回退到串行模式
    """
    if not PARALLEL_SUPPORT or not enable_parallel:
        logger.info("使用串行模式进行转换")
        return direct_csv_to_new_hdf5(json_path, csv_dir, output_h5_path)
    
    logger.info(f"开始多进程转换: JSON={json_path}, CSV_DIR={csv_dir} -> HDF5={output_h5_path}")
    
    # 读取JSON文件
    json_data = _read_json(json_path)
    steps = json_data.get('steps', [])
    
    if not steps:
        raise ValueError("JSON文件中没有找到steps数据")
    
    # 使用多进程处理CSV文件
    logger.info(f"使用多进程处理 {len(steps)} 个步骤的CSV文件")
    processed_results = process_experiment_csvs_parallel(
        steps, csv_dir, _find_csvs_for_step, max_workers
    )
    
    # 分类处理结果
    transfer_results = []
    transient_results = []
    
    for result in processed_results:
        if not result.success:
            logger.warning(f"步骤 {result.step_idx} 处理失败: {result.error_message}")
            continue
            
        if result.step_type == 'transfer':
            transfer_results.append(result)
        elif result.step_type == 'transient':
            transient_results.append(result)
    
    logger.info(f"成功处理: Transfer步骤 {len(transfer_results)}个, Transient步骤 {len(transient_results)}个")
    
    # 创建HDF5文件
    with h5py.File(output_h5_path, "w") as h5:
        # 写入根级别属性
        h5.attrs['format_version'] = "2.0_new_storage"
        h5.attrs['creation_method'] = "direct_csv2hdf_parallel"
        h5.attrs['total_steps'] = len(steps)
        h5.attrs['successful_steps'] = len(transfer_results) + len(transient_results)
        
        # 复制根级别元数据
        for key, value in json_data.items():
            if key != 'steps' and not isinstance(value, (dict, list)):
                try:
                    if isinstance(value, str):
                        dt = h5py.string_dtype(encoding="utf-8", length=None)
                        h5.attrs[key] = np.array(value, dtype=dt)
                    else:
                        h5.attrs[key] = value
                except Exception as e:
                    logger.warning(f"无法写入属性 {key}: {e}")
        
        # 存储原始JSON备份
        raw_group = h5.create_group('raw')
        json_str = json.dumps(json_data, ensure_ascii=False, separators=(',', ':'))
        dt = h5py.string_dtype(encoding="utf-8", length=None)
        raw_group.create_dataset('json', data=json_str, dtype=dt)
        
        # 处理Transfer数据
        if transfer_results:
            transfer_group = h5.create_group('transfer')
            
            # 确定最大数据点数和数据类型数
            max_points = 0
            data_types = 2  # Vg, Id
            n_steps = len(transfer_results)
            transfer_step_infos = []
            
            # 分析数据规模
            for result in transfer_results:
                if 'Vg' in result.data_arrays and 'Id' in result.data_arrays:
                    max_points = max(max_points, len(result.data_arrays['Vg']))
                
                # 提取步骤信息
                step_info = _extract_step_info(steps[result.step_idx], result.step_idx)
                transfer_step_infos.append(step_info)
            
            # 创建3D数组: [步骤索引, 数据类型, 数据点索引]
            measurement_data = np.full((n_steps, data_types, max_points), np.nan, dtype=np.float64)
            
            # 填充数据
            for i, result in enumerate(transfer_results):
                if 'Vg' in result.data_arrays and 'Id' in result.data_arrays:
                    vg_data = result.data_arrays['Vg']
                    id_data = result.data_arrays['Id']
                    
                    n_points = min(len(vg_data), len(id_data), max_points)
                    measurement_data[i, 0, :n_points] = vg_data[:n_points]  # Vg
                    measurement_data[i, 1, :n_points] = id_data[:n_points]  # Id
            
            # 存储3D测量数据
            dataset = transfer_group.create_dataset(
                'measurement_data',
                data=measurement_data,
                compression='gzip',
                compression_opts=4,
                shuffle=True,
                fletcher32=True
            )
            dataset.attrs['dimension_labels'] = np.array(['step_index', 'data_type', 'data_point'], dtype=h5py.string_dtype(encoding="utf-8", length=None))
            dataset.attrs['data_type_labels'] = np.array(['Vg', 'Id'], dtype=h5py.string_dtype(encoding="utf-8", length=None))
            dataset.attrs['description'] = "3D transfer measurement data: [step_index, data_type, data_point]"
            
            # 存储步骤信息表格
            if transfer_step_infos:
                step_info_df = pd.DataFrame(transfer_step_infos)
                _store_dataframe_as_structured_array(transfer_group, 'step_info_table', step_info_df)
            
            logger.info(f"Transfer数据: {n_steps}个步骤, 3D数组形状 {measurement_data.shape}")
        
        # 处理Transient数据
        if transient_results:
            transient_group = h5.create_group('transient')
            
            # 拼接所有步骤的数据
            continuous_time = []
            original_time = []
            drain_current = []
            current_time_offset = 0.0
            current_data_index = 0  # 跟踪当前数据索引
            transient_step_infos = []

            for result in transient_results:
                # 提取步骤信息
                step_info = _extract_step_info(steps[result.step_idx], result.step_idx)

                if 'Time' in result.data_arrays and 'Id' in result.data_arrays:
                    step_original_time = result.data_arrays['Time']
                    step_drain_current = result.data_arrays['Id']

                    # 从步骤信息中获取时间步长
                    step_info_raw = steps[result.step_idx]
                    time_step_ms = _get_time_step_ms(step_info_raw)

                    # 生成连续时间序列
                    n_points = len(step_original_time)
                    step_continuous_time = np.arange(n_points) * (time_step_ms / 1000.0) + current_time_offset

                    # 拼接数据
                    continuous_time.append(step_continuous_time)
                    original_time.append(step_original_time)
                    drain_current.append(step_drain_current)

                    # 记录此步骤的数据索引范围
                    step_info['start_data_index'] = current_data_index
                    step_info['end_data_index'] = current_data_index + n_points
                    current_data_index += n_points

                    # 更新时间偏移
                    current_time_offset = step_continuous_time[-1] + (time_step_ms / 1000.0)

                transient_step_infos.append(step_info)
            
            if continuous_time:
                # 合并为最终数组
                continuous_time_array = np.concatenate(continuous_time)
                original_time_array = np.concatenate(original_time)
                drain_current_array = np.concatenate(drain_current)
                
                # 创建2D数组: [数据类型, 数据点索引]
                measurement_data = np.array([
                    continuous_time_array,  # 数据类型0: 连续时间
                    original_time_array,    # 数据类型1: 原始时间
                    drain_current_array     # 数据类型2: 电流
                ])
                
                # 存储2D测量数据
                dataset = transient_group.create_dataset(
                    'measurement_data',
                    data=measurement_data,
                    compression='gzip',
                    compression_opts=4,
                    shuffle=True,
                    fletcher32=True
                )
                dataset.attrs['dimension_labels'] = np.array(['data_type', 'data_point'], dtype=h5py.string_dtype(encoding="utf-8", length=None))
                dataset.attrs['data_type_labels'] = np.array(['continuous_time', 'original_time', 'drain_current'], dtype=h5py.string_dtype(encoding="utf-8", length=None))
                dataset.attrs['description'] = "2D transient measurement data: [data_type, data_point]"
                
                logger.info(f"Transient数据: {len(transient_results)}个步骤, 2D数组形状 {measurement_data.shape}, 总点数: {measurement_data.shape[1]}")
            
            # 存储步骤信息表格
            if transient_step_infos:
                step_info_df = pd.DataFrame(transient_step_infos)
                _store_dataframe_as_structured_array(transient_group, 'step_info_table', step_info_df)
    
    logger.info(f"多进程转换完成: {output_h5_path}")


def _get_time_step_ms(step_info: Dict[str, Any]) -> float:
    """从步骤信息中提取时间步长(毫秒)"""
    # 查找时间步长参数
    time_step_ms = 1.0  # 默认值
    
    # 递归查找timeStep参数
    def find_time_step(obj):
        nonlocal time_step_ms
        if isinstance(obj, dict):
            if 'timeStep' in obj:
                time_step_ms = float(obj['timeStep'])
                return True
            for v in obj.values():
                if find_time_step(v):
                    return True
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                if find_time_step(v):
                    return True
        return False
    
    find_time_step(step_info)
    return time_step_ms


# 兼容性别名和便利函数
def direct_convert_csvjson_to_hdf5(
    source_dir: str, 
    output_h5_path: str,
    enable_parallel: bool = True,
    max_workers: Optional[int] = None
):
    """
    便利函数：从源目录直接转换为HDF5
    
    Args:
        source_dir: 包含test_info.json和CSV文件的源目录
        output_h5_path: 输出的HDF5文件路径  
        enable_parallel: 是否启用并行处理
        max_workers: 最大工作进程数
    """
    json_path = os.path.join(source_dir, "test_info.json")
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"未找到test_info.json文件: {json_path}")
    
    return direct_csv_to_new_hdf5_parallel(
        json_path, source_dir, output_h5_path, 
        max_workers=max_workers, 
        enable_parallel=enable_parallel
    )


if __name__ == "__main__":
    # 测试代码
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="直接从CSV+JSON生成新格式HDF5文件")
    parser.add_argument("json_path", help="test_info.json文件路径")
    parser.add_argument("csv_dir", help="包含CSV文件的目录")
    parser.add_argument("output_h5", help="输出的HDF5文件路径")
    parser.add_argument("--parallel", action="store_true", default=True, help="启用多进程处理（默认启用）")
    parser.add_argument("--serial", action="store_true", help="强制使用串行模式")
    parser.add_argument("--max-workers", type=int, help="最大工作进程数")
    
    if len(sys.argv) == 1:
        parser.print_help()
    else:
        args = parser.parse_args()
        
        # 确定是否使用并行模式
        enable_parallel = args.parallel and not args.serial
        
        if enable_parallel and PARALLEL_SUPPORT:
            logger.info(f"使用多进程模式，最大进程数: {args.max_workers or '自动优化'}")
            direct_csv_to_new_hdf5_parallel(
                args.json_path, 
                args.csv_dir, 
                args.output_h5,
                max_workers=args.max_workers,
                enable_parallel=True
            )
        else:
            if not PARALLEL_SUPPORT:
                logger.warning("多进程支持不可用，使用串行模式")
            else:
                logger.info("使用串行模式")
            direct_csv_to_new_hdf5(args.json_path, args.csv_dir, args.output_h5)