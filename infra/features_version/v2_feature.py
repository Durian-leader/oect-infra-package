import numpy as np
from concurrent.futures import ProcessPoolExecutor
from typing import Optional, Dict, Any
from ..experiment import Experiment
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

def v2_feature(
    raw_file_path: str,
    output_dir: str = "data/features",
    period: Optional[float] = None,
    max_workers: Optional[int] = None,
    window_scalar_min: float = 0.2,
    window_scalar_max: float = 0.333,
    window_points_step: int = 10,
    show_progress: bool = False
) -> str:
    """
    使用 autotau 包和 features 包创建 transient 特征文件（tau_on 和 tau_off）

    该函数利用 autotau 的并行能力提取 transient 数据的时间常数特征。

    Args:
        raw_file_path: 原始实验数据文件路径
        output_dir: 输出目录，默认为 data/features/
        period: transient 信号周期（秒），如果为 None 将从数据中自动估计
        max_workers: 并行工作进程数，None 表示使用 CPU 核心数
        window_scalar_min: 窗口搜索的最小标量（相对于周期），默认 0.2
        window_scalar_max: 窗口搜索的最大标量（相对于周期），默认 0.333
        window_points_step: 窗口点数步长，默认 10
        show_progress: 是否显示进度条，默认 False

    Returns:
        创建的特征文件路径

    Raises:
        ValueError: 如果原始文件不包含 transient 数据
    """
    logger.info(f"=== 创建 Transient 特征文件（tau_on/tau_off） ===")
    logger.info(f"原始文件: {raw_file_path}")

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
            built_with="features v2.0.0 (autotau)"
        )
        logger.info(f"✅ HDF5文件结构创建成功：{final_feature_file}")

    # 📊 无论文件是否存在，都要进行特征提取和保存（这是数据更新操作）
    logger.info("=" * 50)
    logger.info("开始 Transient 特征提取和保存...")

    # 1. 加载实验数据
    logger.info("1. 加载实验数据...")
    exp = Experiment(raw_file_path)
    summary = exp.get_experiment_summary()
    logger.info(f"实验信息: {summary['basic_info']}")
    logger.info(f"设备信息: {summary['device_info']}")

    # 2. 检查并加载 Transient 数据
    logger.info("2. 加载 Transient 数据...")
    if not exp.has_transient_data():
        raise ValueError(f"无法分析 Transient 特征，文件中没有 Transient 数据: {raw_file_path}")

    transient_data = exp.get_transient_all_measurement()
    if transient_data is None:
        raise ValueError(f"无法加载 Transient 数据: {raw_file_path}")

    time = transient_data['continuous_time']
    signal = transient_data['drain_current']

    logger.info(f"Transient 数据点数: {len(time)}")
    logger.info(f"时间范围: {time[0]:.6f}s ~ {time[-1]:.6f}s")

    # 3. 估计采样率和周期
    logger.info("3. 估计采样率和周期...")
    # 计算采样率（Hz）
    dt = np.diff(time)
    sample_rate = 1.0 / np.mean(dt)
    logger.info(f"采样率: {sample_rate:.2f} Hz")

    # 如果用户未提供周期，从数据中估计
    if period is None:
        # 简单估计：假设数据包含多个完整周期，取总时长除以周期数
        # 这里需要根据实际情况调整，或要求用户提供
        total_duration = time[-1] - time[0]
        # 假设至少有10个周期
        estimated_cycles = max(10, int(total_duration * sample_rate / 100))
        period = total_duration / estimated_cycles
        logger.info(f"⚠️ 未指定周期，自动估计: {period:.6f}s ({estimated_cycles} 个周期)")
    else:
        logger.info(f"使用指定周期: {period:.6f}s")

    # 计算理论周期数
    total_cycles = int((time[-1] - time[0]) / period)
    logger.info(f"理论周期数: {total_cycles}")

    # 4. 使用 autotau 提取 tau_on 和 tau_off（多核并行）
    logger.info("4. 使用 autotau 提取 tau_on 和 tau_off（多核并行）...")

    try:
        from autotau import CyclesAutoTauFitter, AutoTauFitter

        # 创建并行执行器
        executor = ProcessPoolExecutor(max_workers=max_workers)
        logger.info(f"并行工作进程数: {max_workers if max_workers else '默认（CPU核心数）'}")

        # 定义 fitter_factory 以注入并行能力
        def fitter_factory(time_slice, signal_slice, **kwargs):
            """创建支持并行窗口搜索的 AutoTauFitter"""
            return AutoTauFitter(
                time=time_slice,
                signal=signal_slice,
                sample_step=int(kwargs.get('sample_step', 1)),
                period=kwargs.get('period', period),
                window_scalar_min=window_scalar_min,
                window_scalar_max=window_scalar_max,
                window_points_step=window_points_step,
                normalize=False,
                show_progress=False,  # 单个周期不显示进度
                executor=executor  # 🚀 注入并行执行器
            )

        # 创建 CyclesAutoTauFitter
        cycles_fitter = CyclesAutoTauFitter(
            time=time,
            signal=signal,
            period=period,
            sample_rate=sample_rate,
            fitter_factory=fitter_factory
        )

        logger.info("开始拟合所有周期...")

        # 拟合所有周期
        results = cycles_fitter.fit_all_cycles(
            interp=True,
            points_after_interp=100,
            r_squared_threshold=0.95
        )

        # 关闭执行器
        executor.shutdown(wait=True)

        logger.info(f"拟合完成，共 {len(results)} 个周期")

    except Exception as e:
        logger.error(f"❌ autotau 拟合失败: {e}")
        raise

    # 5. 提取特征数据
    logger.info("5. 提取特征数据...")

    # 初始化特征数组
    tau_on_list = []
    tau_off_list = []
    tau_on_r2_list = []
    tau_off_r2_list = []

    for cycle_idx, cycle_result in enumerate(results):
        # 检查拟合是否成功
        if cycle_result.get('status') == 'success':
            tau_on = cycle_result.get('tau_on', np.nan)
            tau_off = cycle_result.get('tau_off', np.nan)
            tau_on_r2 = cycle_result.get('tau_on_r2', np.nan)
            tau_off_r2 = cycle_result.get('tau_off_r2', np.nan)
        else:
            tau_on = np.nan
            tau_off = np.nan
            tau_on_r2 = np.nan
            tau_off_r2 = np.nan
            logger.warning(f"周期 {cycle_idx} 拟合失败")

        tau_on_list.append(tau_on)
        tau_off_list.append(tau_off)
        tau_on_r2_list.append(tau_on_r2)
        tau_off_r2_list.append(tau_off_r2)

    # 转换为 numpy 数组
    features_data = {
        'tau_on': np.array(tau_on_list, dtype=np.float32),
        'tau_off': np.array(tau_off_list, dtype=np.float32),
        'tau_on_r2': np.array(tau_on_r2_list, dtype=np.float32),
        'tau_off_r2': np.array(tau_off_r2_list, dtype=np.float32),
    }

    step_count = len(tau_on_list)
    feature_count = len(features_data)
    logger.info(f"提取了 {feature_count} 个特征，{step_count} 个步骤（周期）")

    # 统计拟合质量
    valid_tau_on = np.sum(~np.isnan(features_data['tau_on']))
    valid_tau_off = np.sum(~np.isnan(features_data['tau_off']))
    logger.info(f"有效 tau_on: {valid_tau_on}/{step_count}")
    logger.info(f"有效 tau_off: {valid_tau_off}/{step_count}")

    if valid_tau_on > 0:
        mean_tau_on = np.nanmean(features_data['tau_on'])
        std_tau_on = np.nanstd(features_data['tau_on'])
        logger.info(f"tau_on 统计: mean={mean_tau_on:.6f}s, std={std_tau_on:.6f}s")

    if valid_tau_off > 0:
        mean_tau_off = np.nanmean(features_data['tau_off'])
        std_tau_off = np.nanstd(features_data['tau_off'])
        logger.info(f"tau_off 统计: mean={mean_tau_off:.6f}s, std={std_tau_off:.6f}s")

    # 6. 存储特征数据
    logger.info("6. 存储特征数据...")
    repo = FeatureRepository(final_feature_file)

    # 定义特征元数据
    feature_metadata = {
        'tau_on': FeatureMetadata(
            name='tau_on',
            unit='s',
            description='Turn-on time constant extracted by autotau'
        ),
        'tau_off': FeatureMetadata(
            name='tau_off',
            unit='s',
            description='Turn-off time constant extracted by autotau'
        ),
        'tau_on_r2': FeatureMetadata(
            name='tau_on_r2',
            unit='',
            description='R-squared for tau_on fit'
        ),
        'tau_off_r2': FeatureMetadata(
            name='tau_off_r2',
            unit='',
            description='R-squared for tau_off fit'
        ),
    }

    # 批量存储特征（覆盖模式）
    results = repo.store_multiple_features(
        features_data,
        data_type="transient",
        metadata_dict=feature_metadata,
        bucket_name="bk_00",
        overwrite=True
    )

    successful_features = sum(results.values())
    logger.info(f"成功存储 {successful_features}/{feature_count} 个特征")

    # 7. 使用通用版本化工具创建版本和验证
    logger.info("7. 创建版本 v2 并验证...")
    version_success = create_version_from_all_features(
        repo=repo,
        version_name="v2",
        exp=exp,
        data_type="transient",
        include_verification=True
    )

    if not version_success:
        logger.error(f"❌ 版本v2创建或验证失败")

    # 完成状态
    if version_success:
        logger.info(f"✅ 特征文件创建完成: {Path(final_feature_file).name}")
    else:
        logger.error(f"❌ 特征文件创建失败: {Path(final_feature_file).name}")

    return final_feature_file


def estimate_period_from_signal(time: np.ndarray, signal: np.ndarray) -> float:
    """
    从信号中自动估计周期

    使用自相关或 FFT 方法估计信号的主要周期

    Args:
        time: 时间数组
        signal: 信号数组

    Returns:
        估计的周期（秒）
    """
    try:
        from scipy import signal as sp_signal
        from scipy.fft import fft, fftfreq

        # 方法1：使用 FFT 找到主频率
        N = len(signal)
        sample_rate = 1.0 / np.mean(np.diff(time))

        # 去除直流分量
        signal_detrend = signal - np.mean(signal)

        # FFT
        yf = fft(signal_detrend)
        xf = fftfreq(N, 1.0 / sample_rate)

        # 只看正频率部分
        pos_mask = xf > 0
        xf_pos = xf[pos_mask]
        yf_pos = np.abs(yf[pos_mask])

        # 找到最大幅值对应的频率
        peak_idx = np.argmax(yf_pos)
        dominant_freq = xf_pos[peak_idx]

        if dominant_freq > 0:
            period = 1.0 / dominant_freq
            logger.info(f"FFT 估计周期: {period:.6f}s (频率: {dominant_freq:.2f} Hz)")
            return period
        else:
            raise ValueError("无法从 FFT 中找到有效频率")

    except Exception as e:
        logger.warning(f"自动估计周期失败: {e}")
        # 降级方案：使用简单的经验值
        total_duration = time[-1] - time[0]
        estimated_period = total_duration / 10  # 假设至少10个周期
        logger.info(f"使用降级方案估计周期: {estimated_period:.6f}s")
        return estimated_period
