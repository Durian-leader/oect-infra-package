"""
Step 级并行执行器 + 生产者-消费者架构

核心设计：
- 任务粒度：Feature × Step × Experiment（最细粒度）
- 进程架构：47 Worker 进程 + 1 消费者进程
- 依赖处理：拓扑排序 + 分阶段执行
- 内存管理：按实验聚合 + 即时保存释放
"""

import multiprocessing
import time
from typing import List, Dict, Any, Set, Optional
from pathlib import Path
from datetime import datetime
from hashlib import md5
import numpy as np
import pandas as pd

from infra.features_v2.core.task import ExtractionTask, ExtractionResult
from infra.features_v2.core.compute_graph import ComputeGraph
from infra.logger_config import get_module_logger

logger = get_module_logger()


class StepLevelParallelExecutor:
    """Step 级并行执行器

    架构：
    1. 主进程：调度器（生成任务 + 协调）
    2. Worker Pool（n_workers 个进程）：执行任务
    3. 消费者进程（1个）：聚合结果 + 保存释放

    执行流程：
    1. 拓扑排序分层（按依赖关系）
    2. 逐层生成任务（Feature × Step × Experiment）
    3. Worker 并行执行任务
    4. 消费者实时聚合结果
    5. 实验完成立即保存 Parquet 并释放内存
    """

    def __init__(
        self,
        n_workers: int = 47,
        consumer_buffer_size: int = 10000,
        output_dir: Optional[str] = None,
        extra_imports: Optional[List[str]] = None
    ):
        """初始化执行器

        Args:
            n_workers: Worker 进程数量（默认47，配合1个消费者=48核）
            consumer_buffer_size: 结果队列缓冲区大小
            output_dir: Parquet 输出目录
            extra_imports: 外部模块导入列表（如 ['autotau_extractors']）
        """
        self.n_workers = n_workers
        self.consumer_buffer_size = consumer_buffer_size
        self.output_dir = output_dir
        self.extra_imports = extra_imports or []

        # 进程间通信队列
        self.task_queue = None
        self.result_queue = None
        self.completion_counter = None  # 用于跟踪层级完成进度

        # 进程池
        self.worker_pool = []
        self.consumer_process = None

        logger.info(
            f"StepLevelParallelExecutor 初始化: "
            f"{n_workers} workers + 1 consumer"
        )

    def execute(
        self,
        compute_graph: ComputeGraph,
        experiments: List,  # List[UnifiedExperiment]
        config_name: str = 'step_parallel_config'
    ) -> Dict[str, Any]:
        """执行并行特征提取

        Args:
            compute_graph: 计算图（包含所有特征节点）
            experiments: 实验列表
            config_name: 配置名称（用于生成文件名）

        Returns:
            执行统计信息
        """
        logger.info(
            f"开始 Step 级并行执行:\n"
            f"  实验数: {len(experiments)}\n"
            f"  特征数: {len(compute_graph.nodes)}\n"
            f"  Worker数: {self.n_workers}"
        )

        start_time = time.time()

        # 1. 创建进程间队列
        self._init_queues()

        # 2. 拓扑排序分层
        layers = self._group_by_dependency_layers(compute_graph)
        logger.info(f"依赖层级: {len(layers)} 层")

        # 3. 启动消费者进程
        self._start_consumer(experiments, compute_graph, config_name)

        # 4. 启动 Worker Pool
        self._start_workers()

        # 5. 逐层提交任务并等待完成
        total_tasks = 0
        for layer_idx, layer_features in enumerate(layers):
            logger.info(
                f"执行第 {layer_idx}/{len(layers)} 层: "
                f"{len(layer_features)} 个特征"
            )

            # 生成本层任务
            tasks = self._generate_layer_tasks(
                experiments, compute_graph, layer_features, layer_idx
            )
            total_tasks += len(tasks)

            # 提交任务到队列
            for task in tasks:
                self.task_queue.put(task)

            logger.info(f"  提交了 {len(tasks)} 个任务")

            # 等待本层完成
            self._wait_layer_completion(layer_idx, len(tasks))

        # 6. 发送终止信号
        logger.info("所有任务已提交，等待 Worker 完成...")
        for _ in range(self.n_workers):
            self.task_queue.put(None)  # Poison pill

        # 7. 等待所有进程结束
        for worker in self.worker_pool:
            worker.join()

        self.result_queue.put(None)  # 通知消费者结束
        self.consumer_process.join()

        total_elapsed = (time.time() - start_time) * 1000

        logger.info(
            f"✅ Step 级并行执行完成:\n"
            f"  总任务数: {total_tasks}\n"
            f"  总耗时: {total_elapsed:.2f}ms\n"
            f"  平均任务耗时: {total_elapsed/total_tasks:.2f}ms"
        )

        return {
            'total_tasks': total_tasks,
            'total_time_ms': total_elapsed,
            'n_workers': self.n_workers,
            'n_layers': len(layers)
        }

    def _init_queues(self):
        """初始化进程间队列"""
        self.task_queue = multiprocessing.Queue()
        self.result_queue = multiprocessing.Queue(maxsize=self.consumer_buffer_size)
        self.completion_counter = multiprocessing.Value('i', 0)  # 共享计数器

    def _group_by_dependency_layers(self, graph: ComputeGraph) -> List[List[str]]:
        """按依赖关系分层

        Returns:
            [[L0特征...], [L1特征...], ...]
        """
        # 使用拓扑排序
        sorted_nodes = graph.topological_sort()

        # 计算每个节点的层级
        node_layers = {}
        for node_name in sorted_nodes:
            if node_name not in graph.nodes:
                # 数据源
                node_layers[node_name] = 0
            else:
                # 特征节点：层级 = max(依赖节点层级) + 1
                node = graph.nodes[node_name]
                if not node.inputs:
                    node_layers[node_name] = 0
                else:
                    max_dep_layer = max(
                        node_layers.get(inp, 0) for inp in node.inputs
                    )
                    node_layers[node_name] = max_dep_layer + 1

        # 按层级分组
        max_layer = max(node_layers.values())
        layers = [[] for _ in range(max_layer + 1)]
        for node_name, layer in node_layers.items():
            layers[layer].append(node_name)

        return layers

    def _generate_layer_tasks(
        self,
        experiments: List,
        graph: ComputeGraph,
        layer_features: List[str],
        layer_idx: int
    ) -> List[ExtractionTask]:
        """生成本层的所有任务

        Args:
            experiments: 实验列表
            graph: 计算图
            layer_features: 本层特征列表
            layer_idx: 层级索引

        Returns:
            任务列表
        """
        tasks = []

        for exp in experiments:
            for feature_name in layer_features:
                # 检查是否为数据源
                if feature_name not in graph.nodes:
                    # 数据源：单任务加载全部
                    tasks.append(ExtractionTask(
                        exp_id=exp.id,
                        feature_name=feature_name,
                        step_idx=None,  # None 表示数据源
                        chip_id=exp.chip_id,
                        device_id=exp.device_id,
                        file_path=exp.file_path,
                        params={},
                        dependency_layer=layer_idx,
                        input_sources=[]
                    ))
                else:
                    # 特征提取：拆分为 step 级任务
                    node = graph.nodes[feature_name]
                    n_steps = exp.transfer_steps  # 从实验获取 step 数量

                    # 确定输入数据源（递归查找）
                    input_sources = self._find_input_sources(graph, feature_name)

                    for step_idx in range(n_steps):
                        tasks.append(ExtractionTask(
                            exp_id=exp.id,
                            feature_name=feature_name,
                            step_idx=step_idx,
                            chip_id=exp.chip_id,
                            device_id=exp.device_id,
                            file_path=exp.file_path,
                            params=node.params,
                            dependency_layer=layer_idx,
                            input_sources=input_sources
                        ))

        return tasks

    def _find_input_sources(self, graph: ComputeGraph, feature_name: str) -> List[str]:
        """递归查找特征的输入数据源

        Args:
            graph: 计算图
            feature_name: 特征名称

        Returns:
            数据源列表（如 ['transfer'] 或 ['transient']）
        """
        if feature_name not in graph.nodes:
            # 已经是数据源
            return [feature_name]

        node = graph.nodes[feature_name]
        sources = set()

        for inp in node.inputs:
            sub_sources = self._find_input_sources(graph, inp)
            sources.update(sub_sources)

        return list(sources)

    def _start_workers(self):
        """启动 Worker Pool"""
        logger.info(f"启动 {self.n_workers} 个 Worker 进程...")

        for worker_id in range(self.n_workers):
            worker = multiprocessing.Process(
                target=_worker_process_func,
                args=(
                    self.task_queue,
                    self.result_queue,
                    self.completion_counter,
                    worker_id,
                    self.extra_imports  # ✨ 传递额外导入列表
                ),
                name=f"Worker-{worker_id}"
            )
            worker.start()
            self.worker_pool.append(worker)

        logger.info(f"✅ Worker Pool 启动完成")

    def _start_consumer(self, experiments, graph, config_name):
        """启动消费者进程"""
        logger.info("启动消费者进程...")

        self.consumer_process = multiprocessing.Process(
            target=_consumer_process_func,
            args=(
                self.result_queue,
                experiments,
                graph,
                config_name,
                self.output_dir
            ),
            name="Consumer"
        )
        self.consumer_process.start()

        logger.info("✅ 消费者进程启动完成")

    def _wait_layer_completion(self, layer_idx: int, expected_tasks: int):
        """等待本层所有任务完成

        Args:
            layer_idx: 层级索引
            expected_tasks: 预期任务数
        """
        logger.info(f"等待第 {layer_idx} 层完成...")

        start_time = time.time()
        last_progress = 0

        while True:
            with self.completion_counter.get_lock():
                completed = self.completion_counter.value

            # 进度更新
            if completed > last_progress:
                progress_pct = (completed / expected_tasks) * 100
                elapsed = time.time() - start_time
                logger.info(
                    f"  进度: {completed}/{expected_tasks} "
                    f"({progress_pct:.1f}%), 耗时: {elapsed:.1f}s"
                )
                last_progress = completed

            # 检查是否完成
            if completed >= expected_tasks:
                break

            time.sleep(0.5)

        # 重置计数器
        with self.completion_counter.get_lock():
            self.completion_counter.value = 0

        elapsed = time.time() - start_time
        logger.info(f"✅ 第 {layer_idx} 层完成，耗时 {elapsed:.1f}s")


# =============================================================================
# Worker 进程函数（全局函数，避免 pickle 问题）
# =============================================================================

def _worker_process_func(
    task_queue: multiprocessing.Queue,
    result_queue: multiprocessing.Queue,
    completion_counter: multiprocessing.Value,
    worker_id: int,
    extra_imports: List[str] = None
):
    """Worker 进程执行函数

    从任务队列中获取任务，执行提取，将结果放入结果队列

    Args:
        task_queue: 任务队列
        result_queue: 结果队列
        completion_counter: 完成计数器（共享）
        worker_id: Worker ID
        extra_imports: 外部模块导入列表
    """
    # 导入必要的模块（在子进程中导入，避免序列化问题）
    from infra.experiment import Experiment
    from infra.features_v2.extractors import get_extractor
    import infra.features_v2.extractors.transfer
    import infra.features_v2.extractors.transient

    # ✨ 动态导入外部模块（如 autotau_extractors）
    if extra_imports:
        import importlib
        for module_name in extra_imports:
            try:
                importlib.import_module(module_name)
                # 仅在第一个 worker 打印日志
                if worker_id == 0:
                    logger = get_module_logger()
                    logger.info(f"✓ Worker 成功导入外部模块: {module_name}")
            except Exception as e:
                logger = get_module_logger()
                logger.warning(f"⚠️ Worker-{worker_id} 导入模块 '{module_name}' 失败: {e}")

    logger = get_module_logger()
    logger.info(f"Worker-{worker_id} 启动")

    # 缓存实验对象（避免重复加载 HDF5）
    experiment_cache: Dict[int, Experiment] = {}

    # 缓存数据源（避免重复加载）
    data_source_cache: Dict[tuple, Any] = {}  # (exp_id, source_name) -> data

    tasks_processed = 0

    while True:
        # 获取任务
        task = task_queue.get()

        if task is None:  # Poison pill
            logger.info(
                f"Worker-{worker_id} 收到终止信号，"
                f"已处理 {tasks_processed} 个任务"
            )
            break

        try:
            # 执行任务
            result = _execute_task(
                task,
                experiment_cache,
                data_source_cache
            )

            # 放入结果队列
            result_queue.put(result)

            # 更新计数器
            with completion_counter.get_lock():
                completion_counter.value += 1

            tasks_processed += 1

        except Exception as e:
            logger.error(f"Worker-{worker_id} 任务失败: {task}, 错误: {e}")
            # 放入失败结果
            result_queue.put(ExtractionResult(
                exp_id=task.exp_id,
                feature_name=task.feature_name,
                step_idx=task.step_idx,
                data=None,
                elapsed_ms=0.0,
                error=str(e)
            ))

            # 更新计数器（失败也算完成）
            with completion_counter.get_lock():
                completion_counter.value += 1

    logger.info(f"Worker-{worker_id} 退出")


def _execute_task(
    task: ExtractionTask,
    experiment_cache: Dict,
    data_source_cache: Dict
) -> ExtractionResult:
    """执行单个任务

    Args:
        task: 提取任务
        experiment_cache: 实验对象缓存
        data_source_cache: 数据源缓存

    Returns:
        提取结果
    """
    from infra.experiment import Experiment
    from infra.features_v2.extractors import get_extractor

    start_time = time.time()

    # 1. 加载实验（缓存）
    if task.exp_id not in experiment_cache:
        experiment_cache[task.exp_id] = Experiment(task.file_path)

    exp = experiment_cache[task.exp_id]

    # 2. 数据源加载任务
    if task.step_idx is None:
        cache_key = (task.exp_id, task.feature_name)

        if cache_key not in data_source_cache:
            if task.feature_name == 'transfer':
                # 加载 Transfer 数据
                raw_data = exp.get_transfer_all_measurement()
                # 转换为列表格式
                data_source_cache[cache_key] = _convert_transfer_to_list(raw_data)

            elif task.feature_name == 'transient':
                # 加载 Transient 数据
                raw_data = exp.get_transient_all_measurement()
                # 转换为列表格式
                data_source_cache[cache_key] = _convert_transient_to_list(raw_data, exp)

        elapsed_ms = (time.time() - start_time) * 1000

        return ExtractionResult(
            exp_id=task.exp_id,
            feature_name=task.feature_name,
            step_idx=None,
            data=None,  # 数据源不返回数据（已缓存）
            elapsed_ms=elapsed_ms
        )

    # 3. 特征提取任务
    else:
        # 获取提取器
        extractor = get_extractor(task.feature_name, task.params)

        # 获取单 step 数据
        step_data = _get_single_step_data(
            exp,
            task,
            data_source_cache
        )

        # 执行提取
        result_data = extractor.extract_single_step(step_data, task.params)

        elapsed_ms = (time.time() - start_time) * 1000

        return ExtractionResult(
            exp_id=task.exp_id,
            feature_name=task.feature_name,
            step_idx=task.step_idx,
            data=result_data,
            elapsed_ms=elapsed_ms
        )


def _convert_transfer_to_list(raw_data: Dict) -> List[Dict]:
    """将 Transfer 原始数据转换为列表格式

    Args:
        raw_data: {'measurement_data': (n_steps, 2, n_points)}

    Returns:
        [{'Vg': array, 'Id': array}, ...]
    """
    measurement_3d = raw_data['measurement_data']
    n_steps = measurement_3d.shape[0]

    transfer_list = []
    for i in range(n_steps):
        transfer_list.append({
            'Vg': measurement_3d[i, 0],
            'Id': measurement_3d[i, 1]
        })

    return transfer_list


def _convert_transient_to_list(raw_data: Dict, exp) -> List[Dict]:
    """将 Transient 原始数据转换为列表格式

    Args:
        raw_data: get_transient_all_measurement() 返回值
        exp: Experiment 实例

    Returns:
        [{'continuous_time': array, 'drain_current': array, 'original_time': array}, ...]
    """
    # 获取 step 信息表
    step_info = exp.get_transient_step_info_table()
    n_steps = len(step_info)

    transient_list = []

    # Transient 数据通常是拼接存储的，需要按索引切片
    for i in range(n_steps):
        try:
            # 使用 Experiment 的 API 获取单 step 数据
            step_measurement = exp.get_transient_step_measurement(i)

            transient_list.append({
                'continuous_time': step_measurement.get('continuous_time', np.array([])),
                'drain_current': step_measurement.get('drain_current', np.array([])),
                'original_time': step_measurement.get('original_time', np.array([]))
            })
        except Exception as e:
            logger.warning(f"加载 Transient Step {i} 失败: {e}")
            # 使用空数组
            transient_list.append({
                'continuous_time': np.array([]),
                'drain_current': np.array([]),
                'original_time': np.array([])
            })

    return transient_list


def _get_single_step_data(
    exp,
    task: ExtractionTask,
    data_source_cache: Dict
) -> Any:
    """获取单 step 数据

    Args:
        exp: Experiment 实例
        task: 提取任务
        data_source_cache: 数据源缓存

    Returns:
        单 step 数据（格式取决于特征类型）
    """
    # 使用 input_sources 信息获取数据
    if not task.input_sources:
        logger.warning(f"任务 {task} 缺少 input_sources 信息")
        return {}

    # 如果只有一个输入数据源，直接返回
    if len(task.input_sources) == 1:
        source_name = task.input_sources[0]
        cache_key = (task.exp_id, source_name)

        if cache_key in data_source_cache:
            data_list = data_source_cache[cache_key]
            if task.step_idx < len(data_list):
                return data_list[task.step_idx]
            else:
                logger.error(
                    f"Step 索引越界: {task.step_idx} >= {len(data_list)}"
                )
                return {}
        else:
            logger.error(f"数据源缓存未找到: {cache_key}")
            return {}

    # 如果有多个输入数据源，返回字典
    else:
        step_data = {}
        for source_name in task.input_sources:
            cache_key = (task.exp_id, source_name)
            if cache_key in data_source_cache:
                data_list = data_source_cache[cache_key]
                if task.step_idx < len(data_list):
                    step_data[source_name] = data_list[task.step_idx]
        return step_data


# =============================================================================
# 消费者进程函数（全局函数）
# =============================================================================

def _consumer_process_func(
    result_queue: multiprocessing.Queue,
    experiments: List,
    graph,
    config_name: str,
    output_dir: Optional[str]
):
    """消费者进程执行函数

    从结果队列中获取结果，按实验聚合，实验完成后保存并释放内存

    Args:
        result_queue: 结果队列
        experiments: 实验列表
        graph: 计算图
        config_name: 配置名称
        output_dir: 输出目录
    """
    logger = get_module_logger()
    logger.info("消费者进程启动")

    # 初始化实验缓冲区
    experiment_buffers = _init_experiment_buffers(experiments, graph)

    # 统计
    total_results_processed = 0
    experiments_saved = 0

    while True:
        # 获取结果
        result = result_queue.get()

        if result is None:  # 终止信号
            logger.info("消费者进程收到终止信号")
            break

        # 跳过数据源结果（不需要聚合）
        if result.step_idx is None:
            continue

        # 聚合结果
        _aggregate_result(result, experiment_buffers)

        total_results_processed += 1

        # 检查实验是否完成
        exp_buf = experiment_buffers[result.exp_id]
        if _is_experiment_complete(exp_buf):
            # 保存并释放
            _save_and_release(exp_buf, config_name, output_dir)
            experiments_saved += 1

            logger.info(
                f"已保存 {experiments_saved}/{len(experiments)} 个实验"
            )

    logger.info(
        f"消费者进程退出:\n"
        f"  处理结果数: {total_results_processed}\n"
        f"  保存实验数: {experiments_saved}"
    )


def _init_experiment_buffers(experiments: List, graph) -> Dict:
    """初始化实验缓冲区

    为每个实验创建存储空间

    Returns:
        {exp_id: {
            'data': {feature_name: [None]*n_steps},
            'completed_features': set(),
            'total_features': int,
            'n_steps': int,
            'exp_obj': UnifiedExperiment
        }}
    """
    # 统计非数据源特征数量
    non_source_features = [
        name for name in graph.nodes
        if name not in ['transfer', 'transient']
    ]

    buffers = {}
    for exp in experiments:
        n_steps = exp.transfer_steps

        # 预分配存储空间
        data = {}
        for feature_name in non_source_features:
            data[feature_name] = [None] * n_steps

        buffers[exp.id] = {
            'data': data,
            'completed_features': set(),
            'total_features': len(non_source_features),
            'n_steps': n_steps,
            'exp_obj': exp
        }

    return buffers


def _aggregate_result(result: ExtractionResult, buffers: Dict):
    """聚合单个结果到缓冲区

    Args:
        result: 提取结果
        buffers: 实验缓冲区
    """
    exp_buf = buffers[result.exp_id]

    # 存储数据
    exp_buf['data'][result.feature_name][result.step_idx] = result.data

    # 检查特征是否完成
    if all(v is not None for v in exp_buf['data'][result.feature_name]):
        exp_buf['completed_features'].add(result.feature_name)


def _is_experiment_complete(exp_buf: Dict) -> bool:
    """检查实验是否完成

    Args:
        exp_buf: 实验缓冲区

    Returns:
        是否完成
    """
    return len(exp_buf['completed_features']) == exp_buf['total_features']


def _save_and_release(exp_buf: Dict, config_name: str, output_dir: Optional[str]):
    """保存 Parquet 并释放内存

    Args:
        exp_buf: 实验缓冲区
        config_name: 配置名称
        output_dir: 输出目录
    """
    logger = get_module_logger()

    exp = exp_buf['exp_obj']

    # 构建 DataFrame
    df_data = {'step_index': list(range(exp_buf['n_steps']))}

    for feature_name, values in exp_buf['data'].items():
        # 处理多维特征（展开为多列）
        if values and isinstance(values[0], np.ndarray):
            # 多维特征
            if values[0].ndim == 1:
                # 1D 数组：展开为多列
                max_len = max(len(v) for v in values if v is not None)
                for col_idx in range(max_len):
                    col_name = f"{feature_name}_{col_idx}"
                    df_data[col_name] = [
                        v[col_idx] if v is not None and col_idx < len(v) else np.nan
                        for v in values
                    ]
            else:
                # 2D+ 数组：flatten 或其他策略
                # 这里简化处理：转换为字符串（后续可优化）
                df_data[feature_name] = [str(v) for v in values]
        else:
            # 标量特征
            df_data[feature_name] = values

    df = pd.DataFrame(df_data)

    # 生成输出路径
    if output_dir is None:
        output_dir = Path.cwd() / 'features_v2'
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    config_hash = md5(config_name.encode()).hexdigest()[:8]
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    filename = (
        f"{exp.chip_id}-{exp.device_id}-{config_name}-"
        f"feat_{timestamp}_{config_hash}.parquet"
    )
    output_path = output_dir / filename

    # 保存 Parquet
    df.to_parquet(output_path, index=False)

    # 释放内存
    exp_buf['data'].clear()

    logger.info(f"✅ 实验 {exp.id} 保存完成: {output_path}")
