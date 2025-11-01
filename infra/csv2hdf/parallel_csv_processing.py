# -*- coding: utf-8 -*-
"""
多进程CSV处理模块 - 优化单个实验的CSV数据处理速度

通过并行处理多个CSV文件来显著提升数据转换性能。
支持Transfer和Transient数据类型的并行处理。
"""

from __future__ import annotations
import os
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional, Union
import numpy as np
import pandas as pd

########################### 日志设置 ################################
from ..logger_config import get_module_logger
logger = get_module_logger()
#####################################################################


@dataclass
class CSVProcessingTask:
    """CSV处理任务定义"""
    step_idx: int
    step_info: Dict[str, Any]
    csv_paths: List[str]
    csv_dir: str
    expected_columns: Dict[str, str]  # 列名映射


@dataclass
class ProcessedCSVResult:
    """处理后的CSV数据结果"""
    step_idx: int
    step_type: str
    data_arrays: Dict[str, np.ndarray]  # 列名 -> 数据数组
    column_info: Dict[str, Any]  # 列的元数据
    success: bool
    error_message: Optional[str] = None


def _process_single_csv_file(task: CSVProcessingTask) -> ProcessedCSVResult:
    """
    处理单个CSV文件的工作函数（用于多进程调用）
    
    Args:
        task: CSV处理任务
        
    Returns:
        ProcessedCSVResult: 处理结果
    """
    try:
        step_type = task.step_info.get('type', 'unknown')
        logger.debug(f"Processing step {task.step_idx} ({step_type}) with {len(task.csv_paths)} CSV files")
        
        # 合并所有CSV文件的数据
        combined_data = {}
        column_info = {}
        
        for csv_path in task.csv_paths:
            if not os.path.exists(csv_path):
                logger.warning(f"CSV file not found: {csv_path}")
                continue
                
            try:
                # 读取CSV文件
                df = pd.read_csv(csv_path)
                logger.debug(f"Loaded CSV {os.path.basename(csv_path)}: {df.shape}")
                
                # 处理每一列
                for col in df.columns:
                    if col not in combined_data:
                        combined_data[col] = []
                        column_info[col] = {
                            'source_files': [],
                            'pandas_dtype': str(df[col].dtype),
                            'has_nulls': df[col].isnull().any()
                        }
                    
                    # 转换为numpy数组并添加到合并数据中
                    col_data = df[col].values
                    if pd.api.types.is_numeric_dtype(col_data):
                        # 数值类型，转换为float64
                        col_data = col_data.astype(np.float64, copy=False)
                    
                    combined_data[col].append(col_data)
                    column_info[col]['source_files'].append(os.path.basename(csv_path))
                    
            except Exception as e:
                logger.error(f"Error reading CSV {csv_path}: {e}")
                continue
        
        # 合并数据数组
        final_arrays = {}
        for col, data_list in combined_data.items():
            if data_list:
                # 拼接所有数据
                final_arrays[col] = np.concatenate(data_list)
                logger.debug(f"Column {col}: {final_arrays[col].shape} points")
        
        return ProcessedCSVResult(
            step_idx=task.step_idx,
            step_type=step_type,
            data_arrays=final_arrays,
            column_info=column_info,
            success=True
        )
        
    except Exception as e:
        error_msg = f"Error processing step {task.step_idx}: {e}"
        logger.error(error_msg)
        return ProcessedCSVResult(
            step_idx=task.step_idx,
            step_type=task.step_info.get('type', 'unknown'),
            data_arrays={},
            column_info={},
            success=False,
            error_message=error_msg
        )


def optimize_process_count(num_tasks: int, max_workers: Optional[int] = None) -> int:
    """
    根据任务数量和系统资源优化进程数
    
    Args:
        num_tasks: 任务数量
        max_workers: 最大工作进程数限制
        
    Returns:
        int: 优化后的进程数
    """
    if num_tasks == 0:
        return 1
    
    # 获取CPU核心数
    cpu_count = mp.cpu_count()
    
    # 基本策略：不超过CPU核心数，也不超过任务数
    optimal_count = min(cpu_count, num_tasks)
    
    # 如果任务数很少，减少进程数以避免过度开销
    if num_tasks <= 4:
        optimal_count = min(2, num_tasks)
    
    # 应用用户限制
    if max_workers is not None:
        optimal_count = min(optimal_count, max_workers)
    
    # 至少使用1个进程
    return max(1, optimal_count)


def parallel_process_csv_files(
    tasks: List[CSVProcessingTask],
    max_workers: Optional[int] = None,
    show_progress: bool = True
) -> List[ProcessedCSVResult]:
    """
    并行处理多个CSV文件任务
    
    Args:
        tasks: CSV处理任务列表
        max_workers: 最大工作进程数，None为自动优化
        show_progress: 是否显示处理进度
        
    Returns:
        List[ProcessedCSVResult]: 处理结果列表
    """
    if not tasks:
        logger.warning("No CSV tasks to process")
        return []
    
    # 优化进程数
    num_workers = optimize_process_count(len(tasks), max_workers)
    logger.info(f"Processing {len(tasks)} CSV tasks with {num_workers} processes")
    
    results = []
    
    if num_workers == 1:
        # 单进程模式
        for i, task in enumerate(tasks, 1):
            if show_progress:
                logger.info(f"Processing task {i}/{len(tasks)}: step {task.step_idx}")
            result = _process_single_csv_file(task)
            results.append(result)
    else:
        # 多进程模式
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            # 提交所有任务
            future_to_task = {
                executor.submit(_process_single_csv_file, task): task 
                for task in tasks
            }
            
            # 收集结果
            completed = 0
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                completed += 1
                
                try:
                    result = future.result()
                    results.append(result)
                    
                    if show_progress:
                        status = "✓" if result.success else "✗"
                        logger.info(f"[{completed}/{len(tasks)}] {status} Step {result.step_idx} ({result.step_type})")
                        
                except Exception as e:
                    error_msg = f"Task failed for step {task.step_idx}: {e}"
                    logger.error(error_msg)
                    results.append(ProcessedCSVResult(
                        step_idx=task.step_idx,
                        step_type=task.step_info.get('type', 'unknown'),
                        data_arrays={},
                        column_info={},
                        success=False,
                        error_message=error_msg
                    ))
    
    # 按step_idx排序结果
    results.sort(key=lambda r: r.step_idx)
    
    # 统计结果
    successful = sum(1 for r in results if r.success)
    failed = len(results) - successful
    logger.info(f"CSV processing completed: {successful} successful, {failed} failed")
    
    return results


def create_csv_processing_tasks(
    steps_info: List[Dict[str, Any]], 
    csv_dir: str,
    find_csv_func: callable
) -> List[CSVProcessingTask]:
    """
    从步骤信息创建CSV处理任务
    
    Args:
        steps_info: 步骤信息列表
        csv_dir: CSV文件目录
        find_csv_func: 查找CSV文件的函数
        
    Returns:
        List[CSVProcessingTask]: 任务列表
    """
    tasks = []
    
    for step_idx, step_info in enumerate(steps_info):
        csv_paths = find_csv_func(step_info, csv_dir, step_idx)
        
        if csv_paths:
            # 根据步骤类型确定期望的列
            step_type = step_info.get('type', '')
            expected_columns = {}
            
            if step_type == 'transfer':
                expected_columns = {'Vg': 'gate_voltage', 'Id': 'drain_current'}
            elif step_type == 'transient':
                expected_columns = {'Time': 'time', 'Id': 'drain_current'}
            
            task = CSVProcessingTask(
                step_idx=step_idx,
                step_info=step_info,
                csv_paths=csv_paths,
                csv_dir=csv_dir,
                expected_columns=expected_columns
            )
            tasks.append(task)
        else:
            logger.warning(f"No CSV files found for step {step_idx}")
    
    return tasks


# 兼容性函数 - 方便从其他模块调用
def process_experiment_csvs_parallel(
    steps_info: List[Dict[str, Any]],
    csv_dir: str,
    find_csv_func: callable,
    max_workers: Optional[int] = None
) -> List[ProcessedCSVResult]:
    """
    并行处理一个实验的所有CSV文件
    
    这是一个便利函数，组合了任务创建和并行处理
    
    Args:
        steps_info: 步骤信息列表
        csv_dir: CSV文件目录
        find_csv_func: 查找CSV文件的函数
        max_workers: 最大工作进程数
        
    Returns:
        List[ProcessedCSVResult]: 处理结果列表
    """
    # 创建处理任务
    tasks = create_csv_processing_tasks(steps_info, csv_dir, find_csv_func)
    
    if not tasks:
        logger.warning("No CSV processing tasks created")
        return []
    
    # 并行处理
    return parallel_process_csv_files(tasks, max_workers=max_workers)


if __name__ == "__main__":
    # 简单的测试代码
    print(f"Optimal process count for 8 tasks: {optimize_process_count(8)}")
    print(f"Optimal process count for 2 tasks: {optimize_process_count(2)}")
    print(f"Available CPU cores: {mp.cpu_count()}")