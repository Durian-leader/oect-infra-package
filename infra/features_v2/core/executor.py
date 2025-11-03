"""
执行引擎

负责执行计算图，支持：
- 串行/并行执行
- 结果缓存
- 性能监控
"""

from typing import Any, Callable, Dict, Optional, TYPE_CHECKING
import time
import numpy as np
from pathlib import Path

from infra.features_v2.core.compute_graph import ComputeGraph, ComputeNode
from infra.logger_config import get_module_logger

if TYPE_CHECKING:
    from infra.catalog.unified_experiment import UnifiedExperiment

logger = get_module_logger()


class ExecutionContext:
    """执行上下文

    存储执行过程中的中间结果和元数据
    """

    def __init__(self):
        self.results: Dict[str, np.ndarray] = {}  # 计算结果
        self.timings: Dict[str, float] = {}  # 执行时间（ms）
        self.cache_hits = 0
        self.cache_misses = 0

    def set(self, name: str, value: np.ndarray, exec_time_ms: float = 0):
        """存储结果"""
        self.results[name] = value
        if exec_time_ms > 0:
            self.timings[name] = exec_time_ms

    def get(self, name: str) -> Optional[np.ndarray]:
        """获取结果"""
        return self.results.get(name)

    def has(self, name: str) -> bool:
        """检查是否已计算"""
        return name in self.results

    def get_total_time(self) -> float:
        """获取总执行时间（ms）"""
        return sum(self.timings.values())

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        # 获取最慢特征
        slowest = None
        if self.timings:
            slowest_tuple = max(self.timings.items(), key=lambda x: x[1])
            slowest = {
                'name': slowest_tuple[0],
                'time_ms': slowest_tuple[1]
            }

        return {
            'total_features': len(self.results),
            'total_time_ms': self.get_total_time(),
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'avg_time_per_feature_ms': (
                self.get_total_time() / len(self.timings) if self.timings else 0
            ),
            'slowest_feature': slowest,
        }


class Executor:
    """执行引擎（串行版本）

    后续版本将添加：
    - 并行执行（ProcessPoolExecutor）
    - 多层缓存（内存 + 磁盘）
    - Numba JIT 加速
    """

    def __init__(
        self,
        compute_graph: ComputeGraph,
        data_loaders: Optional[Dict[str, Callable]] = None,
        extractor_registry: Optional[Dict[str, Any]] = None,
    ):
        """
        Args:
            compute_graph: 计算图
            data_loaders: 数据源加载器 {'transfer': func, 'transient': func}
            extractor_registry: 提取器注册表（提取器名称 → 提取器实例）
        """
        self.graph = compute_graph
        self.data_loaders = data_loaders or {}
        self.extractor_registry = extractor_registry or {}

        # Context injection attributes (set by FeatureSet)
        self.unified_experiment: Optional['UnifiedExperiment'] = None
        self.config_name: Optional[str] = None
        self.config_version: Optional[str] = None

    def execute(self, initial_context: Optional[ExecutionContext] = None) -> ExecutionContext:
        """执行计算图

        Args:
            initial_context: 预填充的上下文（用于缓存特征）

        Returns:
            执行上下文（包含所有计算结果）
        """
        context = initial_context or ExecutionContext()

        # 拓扑排序确定执行顺序
        execution_order = self.graph.topological_sort()

        logger.info(f"开始执行计算图，共 {len(execution_order)} 个节点")

        # 逐个执行节点
        for node_name in execution_order:
            self._execute_node(node_name, context)

        # 输出统计信息
        stats = context.get_statistics()
        logger.info(
            f"计算图执行完成：{stats['total_features']} 个特征，"
            f"总耗时 {stats['total_time_ms']:.2f}ms"
        )

        return context

    def _execute_node(self, node_name: str, context: ExecutionContext):
        """执行单个节点"""
        # 如果已计算，跳过（缓存命中）
        if context.has(node_name):
            context.cache_hits += 1
            logger.debug(f"跳过已缓存节点: {node_name}")
            return

        context.cache_misses += 1

        # 检查是否为数据源
        if node_name not in self.graph:
            # 这是一个数据源（如 'transfer', 'transient'）
            if node_name in self.data_loaders:
                start = time.perf_counter()
                data = self.data_loaders[node_name]()
                elapsed = (time.perf_counter() - start) * 1000

                context.set(node_name, data, elapsed)
                logger.debug(f"加载数据源 '{node_name}' 耗时 {elapsed:.2f}ms")
            else:
                raise ValueError(f"未找到数据源 '{node_name}' 的加载器")
            return

        # 获取节点
        node = self.graph.nodes[node_name]

        # 解析输入
        inputs = self._resolve_inputs(node, context)

        # 执行计算（注入 extraction context 如果可用）
        start = time.perf_counter()

        # 检查是否需要注入上下文
        if self.unified_experiment is not None:
            # 导入 execution_context（延迟导入避免循环依赖）
            from infra.features_v2.core.context import execution_context

            # 使用上下文管理器包裹计算
            with execution_context(
                unified_experiment=self.unified_experiment,
                config_name=self.config_name,
                config_version=self.config_version
            ):
                result = self._compute_node(node, inputs)
        else:
            # 无上下文，直接计算
            result = self._compute_node(node, inputs)

        elapsed = (time.perf_counter() - start) * 1000

        # 存储结果
        context.set(node_name, result, elapsed)
        logger.debug(
            f"计算特征 '{node_name}' 耗时 {elapsed:.2f}ms, "
            f"输出形状 {result.shape}"
        )

    def _resolve_inputs(
        self, node: ComputeNode, context: ExecutionContext
    ) -> Dict[str, Any]:
        """解析节点的输入依赖"""
        resolved = {}

        for input_name in node.inputs:
            # 如果输入尚未计算，尝试加载（可能是数据源）
            if not context.has(input_name):
                # 检查是否为数据源
                if input_name not in self.graph:
                    # 自动加载数据源
                    self._execute_node(input_name, context)
                else:
                    raise RuntimeError(
                        f"节点 '{node.name}' 的输入 '{input_name}' 尚未计算"
                    )

            resolved[input_name] = context.get(input_name)

        return resolved

    def _compute_node(self, node: ComputeNode, inputs: Dict[str, Any]) -> np.ndarray:
        """计算节点"""
        if node.is_extractor:
            # 使用注册的提取器
            extractor_name = node.func
            if extractor_name not in self.extractor_registry:
                raise ValueError(f"未找到提取器 '{extractor_name}'")

            extractor = self.extractor_registry[extractor_name]

            # 简化单输入（与 Lambda 函数保持一致）
            if len(inputs) == 1:
                inputs = list(inputs.values())[0]

            result = extractor.extract(inputs, node.params)

        elif callable(node.func):
            # 直接调用函数
            # 判断输入类型
            if len(inputs) == 1:
                # 单输入：直接传递
                result = node.func(list(inputs.values())[0], **node.params)
            else:
                # 多输入：按 node.inputs 顺序解包为位置参数
                args = [inputs[input_name] for input_name in node.inputs]
                result = node.func(*args, **node.params)

        else:
            raise TypeError(
                f"节点 '{node.name}' 的 func 必须是可调用对象或提取器名称"
            )

        # 验证输出
        if not isinstance(result, np.ndarray):
            raise TypeError(
                f"节点 '{node.name}' 的输出必须是 numpy 数组，"
                f"实际类型：{type(result)}"
            )

        return result


class ParallelExecutor(Executor):
    """并行执行引擎（预留，Phase 2 实现）"""

    def __init__(self, *args, n_workers: int = 4, **kwargs):
        super().__init__(*args, **kwargs)
        self.n_workers = n_workers

    def execute(self) -> ExecutionContext:
        """并行执行计算图"""
        # TODO: Phase 2 实现
        # 1. 使用 compute_graph.group_parallel_nodes() 分组
        # 2. 同组内节点使用 ProcessPoolExecutor 并行执行
        # 3. 跨组串行执行
        raise NotImplementedError("并行执行将在 Phase 2 实现")
