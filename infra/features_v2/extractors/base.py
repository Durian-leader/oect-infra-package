"""
特征提取器基类和注册机制

用户可通过继承 BaseExtractor 并使用 @register 装饰器来添加自定义提取器
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple, Union
import numpy as np

from infra.logger_config import get_module_logger

logger = get_module_logger()

# 全局提取器注册表
EXTRACTOR_REGISTRY: Dict[str, type] = {}


def register(name: str):
    """提取器注册装饰器

    用法：
        @register('custom.my_extractor')
        class MyExtractor(BaseExtractor):
            ...

    Args:
        name: 提取器名称（建议格式：category.name）
    """

    def decorator(cls):
        if not issubclass(cls, BaseExtractor):
            raise TypeError(f"'{cls.__name__}' 必须继承自 BaseExtractor")

        if name in EXTRACTOR_REGISTRY:
            logger.warning(f"提取器 '{name}' 已存在，将被覆盖")

        EXTRACTOR_REGISTRY[name] = cls
        logger.debug(f"注册提取器: {name} -> {cls.__name__}")
        return cls

    return decorator


def get_extractor(name: str, params: Optional[Dict[str, Any]] = None):
    """获取提取器实例

    Args:
        name: 提取器名称
        params: 初始化参数

    Returns:
        提取器实例

    Raises:
        KeyError: 如果提取器未注册
    """
    if name not in EXTRACTOR_REGISTRY:
        available = ', '.join(EXTRACTOR_REGISTRY.keys())
        raise KeyError(
            f"未找到提取器 '{name}'。可用提取器：{available}"
        )

    extractor_cls = EXTRACTOR_REGISTRY[name]
    return extractor_cls(params or {})


class BaseExtractor(ABC):
    """特征提取器基类

    子类必须实现：
    - extract(): 批量计算逻辑（向后兼容，但不推荐）
    - extract_single_step(): 单 step 计算逻辑（**推荐使用**，用于 step 级并行）
    - output_shape: 输出形状声明

    可选实现：
    - validate_inputs(): 输入验证
    - preprocess(): 预处理
    - postprocess(): 后处理

    新架构说明：
    - extract_single_step() 是核心方法，用于 StepLevelParallelExecutor
    - extract() 可通过调用 extract_single_step() 实现（推荐）
    """

    def __init__(self, params: Dict[str, Any]):
        """
        Args:
            params: 提取器参数（来自配置文件或 API 调用）
        """
        self.params = params

    @abstractmethod
    def extract(self, data: Any, params: Dict[str, Any]) -> np.ndarray:
        """提取特征 - 批量模式（向后兼容）

        注意：此方法仅用于向后兼容，新代码应实现 extract_single_step()

        Args:
            data: 输入数据
                  - 单输入：直接传递数据（如 list of dicts）
                  - 多输入：字典 {'input1': data1, 'input2': data2}
            params: 运行时参数（通常与 self.params 相同）

        Returns:
            特征数组，形状可以是：
            - (n_steps,) - 标量特征
            - (n_steps, k) - 多维特征
            - (n_steps, k, m) - 高维特征
        """
        pass

    @abstractmethod
    def extract_single_step(self, step_data: Any, params: Dict[str, Any]) -> Any:
        """提取特征 - 单 step 模式（**推荐**）

        这是 Step 级并行架构的核心方法

        Args:
            step_data: 单个 step 的输入数据
                      - Transfer: {'Vg': array, 'Id': array}
                      - Transient: {'continuous_time': array, 'drain_current': array, ...}
            params: 运行时参数（通常与 self.params 相同）

        Returns:
            单 step 的特征值（类型取决于特征）：
            - 标量：float/int
            - 数组：np.ndarray (k,) 或 (k, m)
            - None：表示提取失败（将填充 NaN）

        示例：
            # 标量特征（如 gm_max）
            return 0.5

            # 多维特征（如 cycles）
            return np.array([0.1, 0.2, ..., 0.n])  # (n_cycles,)

            # 失败
            return None  # 或 np.nan
        """
        pass

    @property
    @abstractmethod
    def output_shape(self) -> Tuple:
        """声明输出形状（每个 step 的输出）

        Returns:
            形状元组，如：
            - () - 标量（如 gm_max）
            - (100,) - 固定长度数组（如 cycles，100个周期）
            - (2,) - 固定维度向量（如 Von_coords）
            - ('n_cycles', 2) - 动态维度（如 tau_on_off）

            注意：不需要包含 'n_steps' 维度（会自动聚合）
        """
        pass

    def validate_inputs(self, data: Any):
        """输入验证（可选）

        Args:
            data: 输入数据

        Raises:
            ValueError: 如果输入无效
        """
        pass

    def preprocess(self, data: Any) -> Any:
        """预处理（可选）

        Args:
            data: 原始输入

        Returns:
            预处理后的数据
        """
        return data

    def postprocess(self, result: np.ndarray) -> np.ndarray:
        """后处理（可选）

        Args:
            result: 提取结果

        Returns:
            后处理后的结果
        """
        return result

    def __call__(self, data: Any) -> np.ndarray:
        """执行完整的提取流程

        这是用户调用的主接口
        """
        # 验证输入
        self.validate_inputs(data)

        # 预处理
        data = self.preprocess(data)

        # 提取
        result = self.extract(data, self.params)

        # 后处理
        result = self.postprocess(result)

        # 验证输出
        if not isinstance(result, np.ndarray):
            raise TypeError(
                f"{self.__class__.__name__}.extract() 必须返回 numpy 数组，"
                f"实际类型：{type(result)}"
            )

        return result

    def __repr__(self):
        return f"{self.__class__.__name__}(params={self.params})"


class LambdaExtractor(BaseExtractor):
    """基于函数的简单提取器（用于快速原型）

    不需要注册，直接在运行时创建
    """

    def __init__(self, func: callable, output_shape: Tuple, params: Optional[Dict] = None):
        super().__init__(params or {})
        self.func = func
        self._output_shape = output_shape

    def extract(self, data: Any, params: Dict[str, Any]) -> np.ndarray:
        return self.func(data)

    @property
    def output_shape(self) -> Tuple:
        return self._output_shape
