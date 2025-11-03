"""
Context Usage Demo - 展示如何在 Extractor 中访问上下文信息

本示例演示如何使用 ExtractionContext 访问：
- Workflow 元数据（采样率、Gate 电压等）
- 实验元数据（chip_id、device_id）
- 配置信息（config_name）

作者: Claude Code
日期: 2025-11-03
"""

import numpy as np
from infra.features_v2.extractors.base import BaseExtractor, register
from infra.features_v2.core.context import get_current_context


# ============================================================================
# 示例 1：基础用法 - 访问 Workflow 参数
# ============================================================================

@register('demo.charge_with_sampling_rate')
class ChargeWithSamplingRate(BaseExtractor):
    """
    使用 workflow 中的采样率计算电荷积分

    这是最常见的用例：从 workflow 中获取测试参数（如采样率）
    来正确计算物理量。
    """

    def extract(self, data, params):
        """
        计算电荷积分：Q = ∫ I(t) dt

        Args:
            data: Transient 数据列表
            params: 提取参数（可选的 fallback_sampling_rate）

        Returns:
            每个 step 的电荷积分 (n_steps,)
        """
        transient_list = data
        n_steps = len(transient_list)
        charge = np.zeros(n_steps, dtype=np.float32)

        # ✅ 访问当前上下文
        ctx = get_current_context()

        # 尝试从 workflow 获取采样率
        if ctx:
            sampling_rate = ctx.get_workflow_param(
                'workflow_step_1_1_param_sampling_rate',
                default=None
            )
            if sampling_rate:
                print(f"✓ 使用 workflow 采样率: {sampling_rate} Hz")
        else:
            sampling_rate = None

        # Fallback: 使用参数或默认值
        if sampling_rate is None:
            sampling_rate = params.get('fallback_sampling_rate', 1000)
            print(f"⚠ 使用 fallback 采样率: {sampling_rate} Hz")

        # 计算电荷积分
        for i, step_data in enumerate(transient_list):
            current = step_data['drain_current']

            # 如果有 continuous_time，优先使用
            if 'continuous_time' in step_data:
                time = step_data['continuous_time']
            else:
                # 否则根据采样率生成时间轴
                time = np.arange(len(current)) / sampling_rate

            # 梯形法则积分
            charge[i] = np.trapz(np.abs(current), time)

        return charge

    @property
    def output_shape(self):
        return ('n_steps',)


# ============================================================================
# 示例 2：访问多个 Workflow 参数
# ============================================================================

@register('demo.normalized_transient_response')
class NormalizedTransientResponse(BaseExtractor):
    """
    使用 workflow 参数归一化 transient 响应

    展示如何访问多个 workflow 参数并进行复杂计算。
    """

    def extract(self, data, params):
        """
        计算归一化的 transient 响应：I_norm = I / (Vg * Vd)

        Args:
            data: Transient 数据列表
            params: 提取参数

        Returns:
            归一化响应 (n_steps,)
        """
        transient_list = data
        n_steps = len(transient_list)
        normalized_response = np.zeros(n_steps, dtype=np.float32)

        # ✅ 访问上下文
        ctx = get_current_context()

        if ctx:
            # 获取多个 workflow 参数
            vg = ctx.get_workflow_param('workflow_vg_gate_voltage', 0.6)
            vd = ctx.get_workflow_param('workflow_step_1_1_param_Vd', -0.6)

            print(f"✓ 使用 workflow 参数: Vg={vg}V, Vd={vd}V")

            # 计算归一化因子
            norm_factor = abs(vg * vd) + 1e-10  # 避免除零
        else:
            # Fallback
            norm_factor = 1.0
            print("⚠ 无 context，使用归一化因子 1.0")

        # 计算归一化响应
        for i, step_data in enumerate(transient_list):
            current = step_data['drain_current']
            # 使用峰值电流归一化
            peak_current = np.max(np.abs(current))
            normalized_response[i] = peak_current / norm_factor

        return normalized_response

    @property
    def output_shape(self):
        return ('n_steps',)


# ============================================================================
# 示例 3：访问实验元数据
# ============================================================================

@register('demo.metadata_aware_feature')
class MetadataAwareFeature(BaseExtractor):
    """
    根据实验元数据（chip_id、device_id）调整特征提取策略

    展示如何访问实验级别的元数据。
    """

    def extract(self, data, params):
        """
        根据 chip_id 和 device_id 调整特征提取

        Args:
            data: Transfer 数据列表
            params: 提取参数

        Returns:
            调整后的特征 (n_steps,)
        """
        transfer_list = data
        n_steps = len(transfer_list)
        features = np.zeros(n_steps, dtype=np.float32)

        # ✅ 访问上下文获取元数据
        ctx = get_current_context()

        if ctx:
            chip_id = ctx.chip_id
            device_id = ctx.device_id
            config_name = ctx.config_name

            print(f"✓ 处理实验: {chip_id} - Device {device_id}")
            print(f"  配置: {config_name}")

            # 示例：根据 device_id 调整处理策略
            # （实际应用中可能根据不同设备使用不同算法）
            if device_id == '1':
                scaling_factor = 1.0
            elif device_id == '2':
                scaling_factor = 0.95
            else:
                scaling_factor = 1.0
        else:
            scaling_factor = 1.0
            print("⚠ 无 context，使用默认缩放因子")

        # 提取特征（示例：使用 Id 的最大绝对值）
        for i, step_data in enumerate(transfer_list):
            id_current = step_data['Id']
            features[i] = np.max(np.abs(id_current)) * scaling_factor

        return features

    @property
    def output_shape(self):
        return ('n_steps',)


# ============================================================================
# 示例 4：完整的最佳实践
# ============================================================================

@register('demo.smart_decay_time')
class SmartDecayTime(BaseExtractor):
    """
    智能衰减时间计算 - 展示完整的最佳实践

    包含：
    - Context 访问
    - 错误处理
    - Fallback 机制
    - 日志记录
    """

    def extract(self, data, params):
        """
        计算 transient 衰减时间，考虑 workflow 参数

        Args:
            data: Transient 数据列表
            params: 提取参数
                - fit_range: 拟合范围 [start_ratio, end_ratio]
                - fallback_sampling_rate: 备用采样率

        Returns:
            衰减时间 (n_steps,)
        """
        from scipy.optimize import curve_fit

        transient_list = data
        n_steps = len(transient_list)
        decay_times = np.full(n_steps, np.nan, dtype=np.float32)

        # 获取参数
        fit_range = params.get('fit_range', [0.1, 0.9])
        fallback_rate = params.get('fallback_sampling_rate', 1000)

        # ✅ 访问上下文
        ctx = get_current_context()

        if ctx:
            # 尝试获取采样率
            sampling_rate = ctx.get_workflow_param(
                'workflow_step_1_1_param_sampling_rate',
                fallback_rate
            )

            # 获取实验信息（用于日志）
            exp_info = f"{ctx.chip_id} Device {ctx.device_id}"
        else:
            sampling_rate = fallback_rate
            exp_info = "Unknown Experiment"

        print(f"✓ 计算衰减时间 ({exp_info})")
        print(f"  采样率: {sampling_rate} Hz, 拟合范围: {fit_range}")

        # 指数衰减模型：I(t) = I0 * exp(-t/τ) + I_offset
        def exp_decay(t, I0, tau, I_offset):
            return I0 * np.exp(-t / tau) + I_offset

        # 逐 step 拟合
        for i, step_data in enumerate(transient_list):
            try:
                current = step_data['drain_current']

                # 生成时间轴
                if 'continuous_time' in step_data:
                    time = step_data['continuous_time']
                else:
                    time = np.arange(len(current)) / sampling_rate

                # 选择拟合范围
                start_idx = int(len(current) * fit_range[0])
                end_idx = int(len(current) * fit_range[1])

                t_fit = time[start_idx:end_idx]
                i_fit = current[start_idx:end_idx]

                # 初始猜测
                I0_guess = i_fit[0] - i_fit[-1]
                tau_guess = (t_fit[-1] - t_fit[0]) / 3
                I_offset_guess = i_fit[-1]

                # 拟合
                popt, _ = curve_fit(
                    exp_decay,
                    t_fit,
                    i_fit,
                    p0=[I0_guess, tau_guess, I_offset_guess],
                    maxfev=1000
                )

                # 提取衰减时间
                decay_times[i] = popt[1]

            except Exception as e:
                # 拟合失败，保持 NaN
                print(f"  ⚠ Step {i} 拟合失败: {e}")
                continue

        return decay_times

    @property
    def output_shape(self):
        return ('n_steps',)


# ============================================================================
# 使用示例
# ============================================================================

if __name__ == '__main__':
    """
    完整使用示例

    运行此脚本需要：
    1. 有效的 UnifiedExperiment 实例
    2. 包含 transient 数据的实验
    """
    print("Context Usage Demo Extractors")
    print("=" * 60)
    print()
    print("已注册的示例 extractors:")
    print("  1. demo.charge_with_sampling_rate")
    print("  2. demo.normalized_transient_response")
    print("  3. demo.metadata_aware_feature")
    print("  4. demo.smart_decay_time")
    print()
    print("使用方法:")
    print()
    print("from infra.features_v2 import FeatureSet")
    print("from infra.catalog import UnifiedExperimentManager")
    print("import infra.features_v2.extractors.examples.context_usage_demo")
    print()
    print("manager = UnifiedExperimentManager('catalog_config.yaml')")
    print("exp = manager.get_experiment(chip_id='#20250804008', device_id='3')")
    print()
    print("features = FeatureSet(")
    print("    unified_experiment=exp,")
    print("    config_name='context_demo'")
    print(")")
    print()
    print("# 使用示例 extractor")
    print("features.add(")
    print("    'charge_integral',")
    print("    extractor='demo.charge_with_sampling_rate',")
    print("    input='transient',")
    print("    params={'fallback_sampling_rate': 1000}")
    print(")")
    print()
    print("result = features.compute()")
    print("df = features.to_dataframe()")
    print()
    print("=" * 60)
