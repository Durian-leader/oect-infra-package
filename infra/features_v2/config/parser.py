"""
配置文件解析器

将配置文件转换为 FeatureSet
"""

from typing import Any, Callable, Dict, Optional
import numpy as np

from infra.features_v2.config.schema import FeatureConfig, FeatureSpec
from infra.features_v2.core.feature_set import FeatureSet
from infra.logger_config import get_module_logger

logger = get_module_logger()


class ConfigParser:
    """配置解析器

    负责将配置文件转换为 FeatureSet 对象
    """

    def __init__(self, config: FeatureConfig):
        """
        Args:
            config: 配置对象
        """
        self.config = config

    def parse(self, experiment=None, unified_experiment=None) -> FeatureSet:
        """解析配置并创建 FeatureSet

        Args:
            experiment: Experiment 实例
            unified_experiment: UnifiedExperiment 实例

        Returns:
            FeatureSet 对象
        """
        # 创建 FeatureSet（传递配置元数据）
        features = FeatureSet(
            experiment=experiment,
            unified_experiment=unified_experiment,
            config_name=self.config.name,
            config_version=self.config.config_version
        )

        # 添加特征
        for spec in self.config.features:
            self._add_feature(features, spec)

        logger.info(f"从配置加载了 {len(self.config.features)} 个特征")

        return features

    def _add_feature(self, features: FeatureSet, spec: FeatureSpec):
        """添加单个特征

        Args:
            features: FeatureSet 对象
            spec: 特征配置
        """
        # 规范化 input
        if isinstance(spec.input, str):
            input_list = [spec.input]
        else:
            input_list = spec.input

        # 转换 output_shape
        output_shape = None
        if spec.output_shape:
            output_shape = tuple(spec.output_shape)

        if spec.extractor:
            # 使用注册的提取器
            features.add(
                name=spec.name,
                extractor=spec.extractor,
                input=input_list,
                params=spec.params,
            )
            logger.debug(f"添加提取器特征: {spec.name} <- {spec.extractor}")

        elif spec.func:
            # 使用自定义函数（Python 表达式）
            try:
                func = self._parse_func(spec.func)
                features.add(
                    name=spec.name,
                    func=func,
                    input=input_list,
                    params=spec.params,
                    output_shape=output_shape or ('n_steps',),
                )

                # 🔑 手动设置源代码（因为 eval 创建的函数无法通过 inspect 获取）
                node = features.graph.nodes[spec.name]
                node.source_code = spec.func

                logger.debug(f"添加函数特征: {spec.name} <- {spec.func}")
            except ValueError as e:
                # 跳过无法解析的特征，发出警告
                logger.warning(f"⚠️ 跳过特征 '{spec.name}'：{e}")
                logger.warning(f"   建议：使用提取器或简化 lambda 表达式")

        else:
            raise ValueError(f"特征 '{spec.name}' 必须提供 extractor 或 func")

    def _parse_func(self, func_str: str) -> Callable:
        """解析函数字符串

        支持的格式：
        - "lambda x: x.mean()" - lambda 表达式
        - "np.mean" - 模块函数
        - "custom.my_func" - 自定义函数

        Args:
            func_str: 函数字符串

        Returns:
            可调用对象
        """
        # 移除空白
        func_str = func_str.strip()

        # 如果是 lambda 表达式
        if func_str.startswith('lambda'):
            try:
                # 安全的命名空间（只包含 numpy）
                namespace = {'np': np, 'numpy': np}
                func = eval(func_str, namespace)
                return func
            except Exception as e:
                raise ValueError(f"无法解析 lambda 表达式 '{func_str}': {e}")

        # 如果是模块函数（如 "np.mean"）
        if '.' in func_str:
            try:
                parts = func_str.split('.')
                module_name = parts[0]

                # 支持的模块
                if module_name == 'np' or module_name == 'numpy':
                    module = np
                else:
                    raise ValueError(f"不支持的模块: {module_name}")

                # 逐级获取属性
                func = module
                for part in parts[1:]:
                    func = getattr(func, part)

                return func
            except Exception as e:
                raise ValueError(f"无法解析函数 '{func_str}': {e}")

        # 否则作为内置函数
        try:
            namespace = {'np': np}
            func = eval(func_str, namespace)
            if not callable(func):
                raise ValueError(f"'{func_str}' 不是可调用对象")
            return func
        except Exception as e:
            raise ValueError(f"无法解析函数 '{func_str}': {e}")

    @classmethod
    def from_file(cls, config_path: str, experiment=None, unified_experiment=None) -> FeatureSet:
        """从配置文件直接创建 FeatureSet（便捷方法）

        Args:
            config_path: 配置文件路径
            experiment: Experiment 实例
            unified_experiment: UnifiedExperiment 实例

        Returns:
            FeatureSet 对象
        """
        from pathlib import Path

        # 加载配置
        config = FeatureConfig.load(config_path)

        # 如果配置中没有名称，从文件路径提取
        if not config.name:
            config.name = Path(config_path).stem

        parser = cls(config)
        return parser.parse(experiment=experiment, unified_experiment=unified_experiment)
