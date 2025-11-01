"""
Transient 特征提取器

提取瞬态响应数据的特征
"""

from typing import Any, Dict, List, Tuple
import numpy as np
from scipy import signal, optimize

from infra.features_v2.extractors.base import BaseExtractor, register
from infra.logger_config import get_module_logger

logger = get_module_logger()


@register('transient.cycles')
class TransientCyclesExtractor(BaseExtractor):
    """提取 Transient 的 Cycle 峰值特征

    从每个 step 的 transient 数据中提取 N 个 cycle 的峰值电流

    参数：
        n_cycles: 提取的 cycle 数量（默认 100）
        method: 峰值检测方法
            - 'peak_detection': 使用 scipy.signal.find_peaks
            - 'fixed_interval': 固定间隔采样
            - 'percentile': 百分位数采样
        min_distance: 峰值间最小距离（数据点数，默认 10）
        prominence: 峰值显著性（默认 None，自动）
    """

    def extract(self, data: Any, params: Dict[str, Any]) -> np.ndarray:
        transient_list = data['transient'] if isinstance(data, dict) else data

        n_cycles = params.get('n_cycles', 100)
        method = params.get('method', 'peak_detection')

        n_steps = len(transient_list)
        result = np.zeros((n_steps, n_cycles), dtype=np.float32)

        for i, step_data in enumerate(transient_list):
            drain_current = step_data['drain_current']

            if method == 'peak_detection':
                cycles = self._extract_by_peaks(drain_current, n_cycles, params)
            elif method == 'fixed_interval':
                cycles = self._extract_by_interval(drain_current, n_cycles)
            elif method == 'percentile':
                cycles = self._extract_by_percentile(drain_current, n_cycles)
            else:
                raise ValueError(f"未知的方法: {method}")

            # 填充结果（如果提取的 cycle 少于 n_cycles，用 NaN 填充）
            actual_cycles = min(len(cycles), n_cycles)
            result[i, :actual_cycles] = cycles[:actual_cycles]
            if actual_cycles < n_cycles:
                result[i, actual_cycles:] = np.nan

        return result

    def _extract_by_peaks(
        self, drain_current: np.ndarray, n_cycles: int, params: Dict
    ) -> np.ndarray:
        """使用峰值检测提取 cycle"""
        min_distance = params.get('min_distance', 10)
        prominence = params.get('prominence', None)

        # 使用绝对值检测峰值
        abs_current = np.abs(drain_current)

        # 如果 prominence 未指定，使用自适应值
        if prominence is None:
            prominence = np.percentile(abs_current, 75) * 0.1

        try:
            peaks, properties = signal.find_peaks(
                abs_current,
                distance=min_distance,
                prominence=prominence,
            )

            if len(peaks) == 0:
                # 如果没有找到峰值，使用固定间隔
                return self._extract_by_interval(drain_current, n_cycles)

            # 提取峰值对应的电流值
            peak_currents = drain_current[peaks]

            # 如果峰值太多，选择最显著的 n_cycles 个
            if len(peak_currents) > n_cycles:
                # 按绝对值排序，选择最大的
                indices = np.argsort(np.abs(peak_currents))[-n_cycles:]
                indices = np.sort(indices)  # 恢复时间顺序
                peak_currents = peak_currents[indices]

            return peak_currents

        except Exception as e:
            logger.warning(f"峰值检测失败: {e}，回退到固定间隔")
            return self._extract_by_interval(drain_current, n_cycles)

    def _extract_by_interval(
        self, drain_current: np.ndarray, n_cycles: int
    ) -> np.ndarray:
        """固定间隔采样"""
        total_points = len(drain_current)
        if total_points < n_cycles:
            # 数据点不足，填充 NaN
            result = np.full(n_cycles, np.nan, dtype=np.float32)
            result[:total_points] = drain_current
            return result

        # 均匀采样
        indices = np.linspace(0, total_points - 1, n_cycles, dtype=int)
        return drain_current[indices]

    def _extract_by_percentile(
        self, drain_current: np.ndarray, n_cycles: int
    ) -> np.ndarray:
        """按百分位数采样（选择高电流区域）"""
        abs_current = np.abs(drain_current)
        threshold = np.percentile(abs_current, 100 * (1 - n_cycles / len(drain_current)))

        # 选择超过阈值的点
        mask = abs_current >= threshold
        selected = drain_current[mask]

        if len(selected) < n_cycles:
            # 补充
            result = np.full(n_cycles, np.nan, dtype=np.float32)
            result[:len(selected)] = selected
            return result
        else:
            # 均匀采样
            indices = np.linspace(0, len(selected) - 1, n_cycles, dtype=int)
            return selected[indices]

    @property
    def output_shape(self) -> Tuple:
        n_cycles = self.params.get('n_cycles', 100)
        return ('n_steps', n_cycles)


@register('transient.peak_current')
class TransientPeakCurrentExtractor(BaseExtractor):
    """提取 Transient 的峰值电流（单个标量）

    参数：
        use_abs: 是否使用绝对值（默认 True）
    """

    def extract(self, data: Any, params: Dict[str, Any]) -> np.ndarray:
        transient_list = data['transient'] if isinstance(data, dict) else data

        use_abs = params.get('use_abs', True)
        n_steps = len(transient_list)
        result = np.zeros(n_steps, dtype=np.float32)

        for i, step_data in enumerate(transient_list):
            drain_current = step_data['drain_current']

            if use_abs:
                result[i] = np.max(np.abs(drain_current))
            else:
                result[i] = np.max(drain_current)

        return result

    @property
    def output_shape(self) -> Tuple:
        return ('n_steps',)


@register('transient.decay_time')
class TransientDecayTimeExtractor(BaseExtractor):
    """提取 Transient 的衰减时间常数

    拟合指数衰减模型：I(t) = I0 * exp(-t/tau)

    参数：
        fit_range: 拟合范围（百分比，如 [0.1, 0.9] 表示使用中间 80% 的数据）
        method: 拟合方法（'exponential', 'linear'）
    """

    def extract(self, data: Any, params: Dict[str, Any]) -> np.ndarray:
        transient_list = data['transient'] if isinstance(data, dict) else data

        fit_range = params.get('fit_range', [0.1, 0.9])
        method = params.get('method', 'exponential')

        n_steps = len(transient_list)
        result = np.full(n_steps, np.nan, dtype=np.float32)

        for i, step_data in enumerate(transient_list):
            continuous_time = step_data['continuous_time']
            drain_current = step_data['drain_current']

            try:
                if method == 'exponential':
                    tau = self._fit_exponential(
                        continuous_time, drain_current, fit_range
                    )
                elif method == 'linear':
                    tau = self._fit_linear(
                        continuous_time, drain_current, fit_range
                    )
                else:
                    raise ValueError(f"未知的方法: {method}")

                result[i] = tau
            except Exception as e:
                logger.debug(f"Step {i} 衰减拟合失败: {e}")
                result[i] = np.nan

        return result

    def _fit_exponential(
        self, time: np.ndarray, current: np.ndarray, fit_range: list
    ) -> float:
        """指数衰减拟合"""
        # 选择拟合范围
        n_points = len(time)
        start_idx = int(n_points * fit_range[0])
        end_idx = int(n_points * fit_range[1])

        t_fit = time[start_idx:end_idx]
        I_fit = np.abs(current[start_idx:end_idx])  # 使用绝对值

        # 过滤零值和 NaN
        valid_mask = (I_fit > 0) & np.isfinite(I_fit) & np.isfinite(t_fit)
        t_fit = t_fit[valid_mask]
        I_fit = I_fit[valid_mask]

        if len(t_fit) < 3:
            raise ValueError("有效数据点不足")

        # 指数衰减模型
        def exp_decay(t, I0, tau):
            return I0 * np.exp(-t / tau)

        # 初始猜测
        I0_guess = I_fit[0]
        tau_guess = (t_fit[-1] - t_fit[0]) / 2

        # 拟合
        try:
            popt, _ = optimize.curve_fit(
                exp_decay,
                t_fit - t_fit[0],  # 归零时间
                I_fit,
                p0=[I0_guess, tau_guess],
                maxfev=1000,
                bounds=([0, 0], [np.inf, np.inf]),
            )
            tau = popt[1]
            return tau
        except Exception:
            # 拟合失败，使用半衰期估计
            half_max = I_fit[0] / 2
            idx = np.argmin(np.abs(I_fit - half_max))
            tau = (t_fit[idx] - t_fit[0]) / np.log(2)
            return tau

    def _fit_linear(
        self, time: np.ndarray, current: np.ndarray, fit_range: list
    ) -> float:
        """对数线性拟合（log(I) vs t）"""
        n_points = len(time)
        start_idx = int(n_points * fit_range[0])
        end_idx = int(n_points * fit_range[1])

        t_fit = time[start_idx:end_idx]
        I_fit = np.abs(current[start_idx:end_idx])

        # 过滤
        valid_mask = (I_fit > 0) & np.isfinite(I_fit) & np.isfinite(t_fit)
        t_fit = t_fit[valid_mask]
        I_fit = I_fit[valid_mask]

        if len(t_fit) < 3:
            raise ValueError("有效数据点不足")

        # log(I) = log(I0) - t/tau
        log_I = np.log(I_fit)

        # 线性拟合
        coeffs = np.polyfit(t_fit - t_fit[0], log_I, 1)
        slope = coeffs[0]

        # tau = -1 / slope
        tau = -1 / slope

        return tau

    @property
    def output_shape(self) -> Tuple:
        return ('n_steps',)


# 预注册所有 transient 提取器
__all__ = [
    'TransientCyclesExtractor',
    'TransientPeakCurrentExtractor',
    'TransientDecayTimeExtractor',
]
