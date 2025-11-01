"""
计算图构建与优化

实现 DAG（有向无环图）用于特征依赖管理
- 拓扑排序确定执行顺序
- 识别可并行节点
- 共享数据加载
"""

from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, deque
import numpy as np


@dataclass
class ComputeNode:
    """计算图节点

    Attributes:
        name: 特征名称
        func: 计算函数（可调用对象或提取器名称）
        inputs: 输入依赖（特征名或数据源名）
        params: 函数参数
        output_shape: 输出形状声明（如 ('n_steps', 100)）
        is_extractor: 是否为注册的提取器
        source_code: lambda 函数的源代码（用于序列化）
    """
    name: str
    func: Any  # Callable 或 str（提取器名称）
    inputs: List[str]
    params: Dict[str, Any] = field(default_factory=dict)
    output_shape: Optional[Tuple] = None
    is_extractor: bool = False
    source_code: Optional[str] = None  # 🔑 新增：保存 lambda 源代码

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return self.name == other.name if isinstance(other, ComputeNode) else False


class ComputeGraph:
    """计算图管理器

    构建特征依赖的 DAG 并提供拓扑排序、并行分组等优化
    """

    def __init__(self):
        self.nodes: Dict[str, ComputeNode] = {}
        self.adj_list: Dict[str, Set[str]] = defaultdict(set)  # 邻接表
        self.reverse_adj: Dict[str, Set[str]] = defaultdict(set)  # 反向邻接表（用于找前驱）

    def add_node(self, node: ComputeNode):
        """添加计算节点"""
        if node.name in self.nodes:
            raise ValueError(f"节点 '{node.name}' 已存在")

        self.nodes[node.name] = node

        # 构建边（从输入到当前节点）
        for input_name in node.inputs:
            self.adj_list[input_name].add(node.name)
            self.reverse_adj[node.name].add(input_name)

    def topological_sort(self) -> List[str]:
        """拓扑排序（Kahn算法）

        Returns:
            节点执行顺序列表

        Raises:
            ValueError: 如果检测到循环依赖
        """
        # 计算入度（只统计图中实际存在的前驱节点，忽略数据源）
        in_degree = defaultdict(int)
        for node_name in self.nodes:
            # 过滤掉不在 nodes 中的数据源
            in_degree[node_name] = len([
                pred for pred in self.reverse_adj[node_name]
                if pred in self.nodes
            ])

        # 初始化队列（入度为0的节点）
        queue = deque([name for name, deg in in_degree.items() if deg == 0])
        result = []

        while queue:
            node_name = queue.popleft()
            result.append(node_name)

            # 更新后继节点的入度
            for neighbor in self.adj_list[node_name]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # 检查是否有环
        if len(result) != len(self.nodes):
            raise ValueError("检测到循环依赖，无法构建计算图")

        return result

    def group_parallel_nodes(self) -> List[List[str]]:
        """分组可并行执行的节点

        Returns:
            分组列表，每组内的节点可并行执行

        示例：
            如果依赖关系为：
                a, b 依赖 raw_data
                c 依赖 a, b
            返回：[[a, b], [c]]
        """
        # 先拓扑排序
        sorted_nodes = self.topological_sort()

        # 计算每个节点的层级（最长路径）
        levels = {}

        def compute_level(node_name: str) -> int:
            if node_name in levels:
                return levels[node_name]

            # 过滤出实际存在于图中的前驱节点（忽略数据源）
            preds_in_graph = [
                pred for pred in self.reverse_adj[node_name]
                if pred in self.nodes
            ]

            # 如果没有前驱，层级为0
            if not preds_in_graph:
                levels[node_name] = 0
                return 0

            # 层级 = max(前驱层级) + 1
            max_pred_level = max(
                compute_level(pred) for pred in preds_in_graph
            )
            levels[node_name] = max_pred_level + 1
            return levels[node_name]

        # 计算所有节点的层级
        for node_name in sorted_nodes:
            compute_level(node_name)

        # 按层级分组
        level_groups = defaultdict(list)
        for node_name, level in levels.items():
            level_groups[level].append(node_name)

        # 返回有序分组
        max_level = max(levels.values()) if levels else 0
        return [level_groups[i] for i in range(max_level + 1) if level_groups[i]]

    def get_dependencies(self, node_name: str) -> Set[str]:
        """获取节点的所有依赖（递归）"""
        if node_name not in self.nodes:
            # 可能是数据源（如 'transfer', 'transient'）
            return set()

        deps = set()
        for input_name in self.reverse_adj[node_name]:
            deps.add(input_name)
            deps.update(self.get_dependencies(input_name))

        return deps

    def get_data_sources(self) -> Set[str]:
        """获取所有数据源（没有前驱的节点）"""
        sources = set()
        for node_name in self.nodes:
            if not self.reverse_adj[node_name]:
                sources.add(node_name)

        # 同时检查 inputs 中提到但不在 nodes 中的
        for node in self.nodes.values():
            for input_name in node.inputs:
                if input_name not in self.nodes:
                    sources.add(input_name)

        return sources

    def visualize(self) -> str:
        """生成图的文本表示（用于调试）"""
        lines = ["计算图结构："]
        sorted_nodes = self.topological_sort()

        for node_name in sorted_nodes:
            node = self.nodes.get(node_name)
            if node:
                inputs_str = ', '.join(node.inputs) if node.inputs else '(无依赖)'
                lines.append(f"  {node_name} ← {inputs_str}")
            else:
                lines.append(f"  {node_name} (数据源)")

        return '\n'.join(lines)

    def __len__(self):
        return len(self.nodes)

    def __contains__(self, node_name: str):
        return node_name in self.nodes

    def __repr__(self):
        return f"ComputeGraph(nodes={len(self.nodes)})"
