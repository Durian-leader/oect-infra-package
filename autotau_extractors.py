"""
AutoTau Feature Extractor for OECT Transient Analysis

基于 autotau 包的自动拟合特征提取器，同时提取 tau_on 和 tau_off 时间常数序列。
支持 Step 级并行架构。

功能：
- ✅ 自动从 workflow 获取采样参数（period, sample_rate）
- ✅ 单 step 提取接口（用于 step 级并行）
- ✅ 同时提取 tau_on 和 tau_off 序列
- ✅ 完整错误处理和 fallback 机制
- ✅ 输出形状：(n_cycles, 2) - 单 step，[tau_on, tau_off]

依赖：
    pip install autotau

作者: User + Claude Code
日期: 2025-11-04（Step 级并行架构重构）
"""

import numpy as np
from typing import Dict, Any, Optional, List, Tuple
import warnings

from infra.features_v2.extractors.base import BaseExtractor, register
from infra.features_v2.core.context import get_current_context
from infra.logger_config import get_module_logger

logger = get_module_logger()

try:
    from autotau import CyclesAutoTauFitter
except ImportError:
    raise ImportError(
        "autotau package not found. Please install it:\n"
        "    pip install autotau"
    )


@register('transient.tau_on_off')
class TauOnOffExtractor(BaseExtractor):
    """
    同时提取 Tau On 和 Tau Off 时间常数序列（Step 级并行版 v1.0.0）

    使用 autotau 的 CyclesAutoTauFitter 自动拟合 transient 响应，
    同时提取每个 cycle 的 tau_on（开启时间常数）和 tau_off（关闭时间常数）。

    架构更新（v1.0.0）：
    - ✨ 单 step 提取接口（extract_single_step）
    - ✨ 完全由 StepLevelParallelExecutor 控制并行度
    - ✨ 移除内部并行逻辑（避免嵌套并行）
    - ✨ 输出形状：(n_cycles, 2) - 单 step

    输出形状（单 step）：(n_cycles, 2)
        - 维度 0: cycles
        - 维度 1: [tau_on, tau_off]

    参数：
        r_squared_threshold: R² 阈值（默认 0.99）
        window_scalar_min: 窗口最小倍数（默认 0.1）
        window_scalar_max: 窗口最大倍数（默认 3/8）
        window_points_step: 窗口点数步长（默认 5）
        window_start_idx_step: 窗口起始索引步长（默认 1）
        period: 周期（秒），优先从 workflow 获取
        sample_rate: 采样率（Hz），优先从 workflow 获取

    示例（推荐用法）：
        features.add(
            'tau_cycles',
            extractor='transient.tau_on_off',
            input='transient',
            params={
                'r_squared_threshold': 0.99
            }
        )

        # 使用 StepLevelParallelExecutor 批量提取（48核 step 级并行）
        executor = StepLevelParallelExecutor(n_workers=47)
        executor.execute(features.graph, experiments)

    访问结果：
        # DataFrame 中会展开为：
        # tau_cycles_0_0 (cycle0, tau_on)
        # tau_cycles_0_1 (cycle0, tau_off)
        # tau_cycles_1_0 (cycle1, tau_on)
        # tau_cycles_1_1 (cycle1, tau_off)
        # ...
    """

    def extract(self, data: Any, params: Dict[str, Any]) -> np.ndarray:
        """批量提取（向后兼容）

        Args:
            data: Transient 数据列表
            params: 参数字典

        Returns:
            (n_steps, n_cycles, 2) 数组
        """
        transient_list = data['transient'] if isinstance(data, dict) else data

        # 调用单 step 提取并聚合
        results = []
        for step_data in transient_list:
            tau_on_off = self.extract_single_step(step_data, params)
            results.append(tau_on_off)

        # 聚合为 (n_steps, n_cycles, 2)
        return self._aggregate_tau_on_off(results)

    def extract_single_step(self, step_data: Any, params: Dict[str, Any]) -> np.ndarray:
        """单 step 提取（用于 step 级并行）

        Args:
            step_data: 单个 step 的 transient 数据
                      {'continuous_time': array, 'drain_current': array, ...}
            params: 参数字典

        Returns:
            (n_cycles, 2) 数组，每行为 [tau_on, tau_off]
            如果拟合失败，返回空数组 (0, 2)
        """
        # 获取采样参数
        period, sample_rate = self._get_sampling_params(params)

        # 获取拟合参数
        r_squared_threshold = params.get('r_squared_threshold', 0.99)
        window_scalar_min = params.get('window_scalar_min', 0.1)
        window_scalar_max = params.get('window_scalar_max', 3/8)
        window_points_step = params.get('window_points_step', 5)
        window_start_idx_step = params.get('window_start_idx_step', 1)

        try:
            time = step_data['continuous_time']
            current = step_data['drain_current']

            # 创建拟合器（串行模式，无内部并行）
            fitter = CyclesAutoTauFitter(
                time,
                current,
                period=period,
                sample_rate=sample_rate,
                fitter_factory=None,  # 串行模式
                window_scalar_min=window_scalar_min,
                window_scalar_max=window_scalar_max,
                window_points_step=window_points_step,
                window_start_idx_step=window_start_idx_step,
                normalize=False,
                language='en',
                show_progress=False  # 关闭内部进度
            )

            # 拟合所有 cycles
            fitter.fit_all_cycles(r_squared_threshold=r_squared_threshold)

            # 获取摘要数据
            summary_df = fitter.get_summary_data()

            if summary_df is not None and not summary_df.empty:
                tau_on = summary_df['tau_on'].to_numpy()
                tau_off = summary_df['tau_off'].to_numpy()

                # 堆叠为 (n_cycles, 2)
                tau_on_off = np.stack([tau_on, tau_off], axis=1).astype(np.float32)
                return tau_on_off
            else:
                # 拟合失败，返回空数组
                logger.debug("AutoTau 拟合结果为空")
                return np.empty((0, 2), dtype=np.float32)

        except Exception as e:
            logger.debug(f"AutoTau 拟合失败: {e}")
            return np.empty((0, 2), dtype=np.float32)

    def _get_sampling_params(self, params: Dict[str, Any]) -> Tuple[float, float]:
        """获取采样参数（period, sample_rate）

        优先级：
        1. workflow 参数（从 context）
        2. 手动传递的 params

        Returns:
            (period, sample_rate) 元组

        Raises:
            ValueError: 如果无法获取必要参数
        """
        # 从 context 获取 workflow 参数
        ctx = get_current_context()
        period = None
        sample_rate = None

        if ctx and ctx.workflow:
            try:
                # 从 workflow 获取采样参数
                top_time = ctx.workflow.get('workflow_step_1_2_param_topTime')
                bottom_time = ctx.workflow.get('workflow_step_1_2_param_bottomTime')
                time_step = ctx.workflow.get('workflow_step_1_2_param_timeStep')

                if top_time is not None and bottom_time is not None and time_step is not None:
                    period = (top_time + bottom_time) / 1000  # 转换为秒
                    sample_rate = 1 / (time_step / 1000)  # 转换为 Hz
                    logger.debug(
                        f"从 workflow 获取参数: period={period:.4f}s, "
                        f"sample_rate={sample_rate:.1f}Hz"
                    )
            except Exception as e:
                logger.warning(f"从 workflow 获取参数时出错: {e}")

        # Fallback: 从 params 获取
        if period is None:
            period = params.get('period', None)
        if sample_rate is None:
            sample_rate = params.get('sample_rate', None)

        # 验证必要参数
        if period is None or sample_rate is None:
            raise ValueError(
                "缺少必要参数：period 和 sample_rate。\n"
                "请确保在 workflow 中配置了 workflow_step_1_2_param_* 参数，\n"
                "或通过 params 手动传递 'period' 和 'sample_rate'。"
            )

        return period, sample_rate

    def _aggregate_tau_on_off(self, results: List[np.ndarray]) -> np.ndarray:
        """聚合单 step 结果为批量结果

        Args:
            results: 单 step 结果列表，每个元素为 (n_cycles_i, 2)

        Returns:
            (n_steps, max_cycles, 2) 数组，不足部分填充 NaN
        """
        n_steps = len(results)
        max_cycles = max(len(r) for r in results) if results else 0

        if max_cycles == 0:
            return np.empty((n_steps, 0, 2), dtype=np.float32)

        # 对齐所有 step 的结果（不足部分填充 NaN）
        aggregated = np.full((n_steps, max_cycles, 2), np.nan, dtype=np.float32)
        for i, tau_on_off in enumerate(results):
            if len(tau_on_off) > 0:
                aggregated[i, :len(tau_on_off), :] = tau_on_off

        return aggregated

    @property
    def output_shape(self) -> Tuple:
        return ('n_cycles', 2)  # 单 step 输出 (n_cycles, 2)


# ============================================================================
# 使用示例
# ============================================================================

if __name__ == '__main__':
    print(__doc__)
    print("\n" + "="*70)
    print("使用示例（Step 级并行架构）")
    print("="*70)

    print("""
1️⃣ 基础用法（使用 StepLevelParallelExecutor）：

from infra.features_v2 import FeatureSet
from infra.features_v2.core.step_parallel_executor import StepLevelParallelExecutor
from infra.catalog import UnifiedExperimentManager
import autotau_extractors  # 导入本文件以注册 extractor

manager = UnifiedExperimentManager('catalog_config.yaml')
experiments = manager.search(chip_id="#20250804008")

# 创建 FeatureSet
features = FeatureSet()

# 添加 tau_on_off 特征
features.add(
    'tau_cycles',
    extractor='transient.tau_on_off',
    input='transient',
    params={
        'r_squared_threshold': 0.99,
        'show_progress': False  # 在并行模式下建议关闭
    }
)

# 使用 Step 级并行执行器（47 workers + 1 consumer = 48核）
executor = StepLevelParallelExecutor(n_workers=47)
executor.execute(features.graph, experiments)

# 结果自动保存为 Parquet（消费者进程处理）


2️⃣ 手动指定参数（无 workflow 或需要覆盖时）：

features.add(
    'tau_cycles',
    extractor='transient.tau_on_off',
    input='transient',
    params={
        'period': 0.1,          # 手动指定 period (秒)
        'sample_rate': 1000,    # 手动指定 sample_rate (Hz)
        'r_squared_threshold': 0.99
    }
)


3️⃣ 结果访问（从保存的 Parquet 读取）：

import pandas as pd

# 读取 Parquet 文件
df = pd.read_parquet('path/to/output.parquet')

# 提取所有 tau_on 列（偶数列）
tau_on_cols = [col for col in df.columns if col.startswith('tau_cycles') and col.endswith('_0')]

# 提取所有 tau_off 列（奇数列）
tau_off_cols = [col for col in df.columns if col.startswith('tau_cycles') and col.endswith('_1')]

# 统计分析
step_0_tau_on = df.loc[0, tau_on_cols].values
step_0_tau_off = df.loc[0, tau_off_cols].values

mean_tau_on = step_0_tau_on.mean()
mean_tau_off = step_0_tau_off.mean()


4️⃣ 性能对比：

旧架构（实验级并行）：
- 80 实验 × 5 steps = 400 个串行拟合
- 并行度: 48核实验级 → ~42秒

新架构（Step 级并行）：
- 400 个 step 并行拟合
- 并行度: 48核 step 级 → ~10秒（预期 4x 提升）


5️⃣ 高级参数调优：

features.add(
    'tau_cycles',
    extractor='transient.tau_on_off',
    input='transient',
    params={
        'r_squared_threshold': 0.99,     # 提高阈值提升拟合质量
        'window_scalar_min': 0.1,        # 拟合窗口最小倍数
        'window_scalar_max': 0.375,      # 拟合窗口最大倍数
        'window_points_step': 5,         # 窗口点数搜索步长
        'window_start_idx_step': 1       # 窗口起始索引步长
    }
)
""")

    print("="*70)
    print("\n已注册的 extractor:")
    print("  - transient.tau_on_off  (同时提取 tau_on 和 tau_off)")
    print("\n单 step 输出形状: (n_cycles, 2)")
    print("  - 维度 0: cycles")
    print("  - 维度 1: [tau_on, tau_off]")
    print("\n✅ 准备就绪！使用 StepLevelParallelExecutor 获得最佳性能。")
