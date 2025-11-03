"""
FeatureSet - 特征集合管理器（用户主接口）

提供声明式 API 用于定义和计算特征
"""

from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
from pathlib import Path

from infra.features_v2.core.compute_graph import ComputeGraph, ComputeNode
from infra.features_v2.core.executor import Executor, ExecutionContext
from infra.features_v2.extractors.base import (
    BaseExtractor,
    LambdaExtractor,
    get_extractor,
    EXTRACTOR_REGISTRY,
)
from infra.logger_config import get_module_logger

logger = get_module_logger()


class FeatureSet:
    """特征集合管理器

    用法：
        # 创建特征集合
        features = FeatureSet(experiment=exp)

        # 添加特征（多种方式）
        features.add('gm_max', extractor='transfer.gm_max')
        features.add('custom', func=lambda x: x.mean(), input='transfer')

        # 计算
        result = features.compute()

        # 导出
        features.to_dataframe()
        features.to_parquet('output.parquet')
    """

    def __init__(
        self,
        experiment=None,
        unified_experiment=None,
        config_name=None,
        config_version='1.0'
    ):
        """
        Args:
            experiment: Experiment 实例（可选，稍后可通过 set_experiment 设置）
            unified_experiment: UnifiedExperiment 对象（优先使用）
            config_name: 配置名称（用于缓存查找）
            config_version: 配置内容版本号
        """
        self.unified_experiment = unified_experiment
        self.config_name = config_name
        self.config_version = config_version

        # 自动提取底层 experiment
        if unified_experiment and not experiment:
            experiment = unified_experiment._get_experiment()

        self.experiment = experiment
        self.graph = ComputeGraph()
        self.data_loaders = {}
        self._computed_results: Optional[ExecutionContext] = None

        # 如果提供了 experiment，自动注册数据加载器
        if experiment:
            self._setup_data_loaders()

    def set_experiment(self, experiment):
        """设置实验对象并注册数据加载器"""
        self.experiment = experiment
        self._setup_data_loaders()

    def _setup_data_loaders(self):
        """注册数据加载器"""
        if not self.experiment:
            return

        # Transfer 数据加载器
        def load_transfer():
            logger.debug("加载 Transfer 数据...")
            transfer_data = self.experiment.get_transfer_all_measurement()
            # 转换为列表格式（每个 step 一个字典）
            n_steps = transfer_data['measurement_data'].shape[0]
            result = []
            for i in range(n_steps):
                step_data = {
                    'Vg': transfer_data['measurement_data'][i, 0, :],
                    'Id': transfer_data['measurement_data'][i, 1, :],
                }
                # 过滤 NaN
                valid_mask = ~np.isnan(step_data['Vg'])
                result.append({
                    'Vg': step_data['Vg'][valid_mask],
                    'Id': step_data['Id'][valid_mask],
                })
            return result

        # Transient 数据加载器
        def load_transient():
            logger.debug("加载 Transient 数据...")

            # 获取步骤信息表
            step_info = self.experiment.get_transient_step_info_table()
            if step_info is None:
                raise ValueError("无法获取 transient step_info_table")

            # 获取拼接后的测量数据
            transient_data = self.experiment.get_transient_all_measurement()
            if transient_data is None:
                raise ValueError("无法获取 transient measurement data")

            # 将数据字典转换为 2D 数组格式 (3, total_points)
            measurement = np.array([
                transient_data['continuous_time'],
                transient_data['original_time'],
                transient_data['drain_current']
            ])

            # 检查是否有索引信息（新版 HDF5 文件）
            if 'start_data_index' in step_info.columns and 'end_data_index' in step_info.columns:
                # 使用索引快速切片（推荐方式，高效）
                logger.debug("使用 step_info_table 索引切片数据")
                result = []
                for _, row in step_info.iterrows():
                    start_idx = int(row['start_data_index'])
                    end_idx = int(row['end_data_index'])

                    step_data = {
                        'continuous_time': measurement[0, start_idx:end_idx],
                        'original_time': measurement[1, start_idx:end_idx],
                        'drain_current': measurement[2, start_idx:end_idx],
                    }
                    result.append(step_data)
            else:
                # 旧版 HDF5 文件没有索引，回退到逐步加载
                logger.warning(
                    "step_info_table 缺少索引字段，回退到逐步加载（较慢）。"
                    "建议重新生成 HDF5 文件以获得更好性能。"
                )
                n_steps = len(step_info)
                result = []
                for step_idx in range(n_steps):
                    step_data = self.experiment.get_transient_step_measurement(step_idx)
                    if step_data is None:
                        logger.warning(f"无法加载 transient step {step_idx}，跳过")
                        continue

                    # 确保数据格式正确
                    if not all(k in step_data for k in ['continuous_time', 'drain_current']):
                        logger.warning(f"Step {step_idx} 数据不完整，跳过")
                        continue

                    result.append(step_data)

            if len(result) == 0:
                raise ValueError("没有成功加载任何 transient 步骤数据")

            logger.debug(f"成功加载 {len(result)} 个 transient 步骤")
            return result

        self.data_loaders['transfer'] = load_transfer
        self.data_loaders['transient'] = load_transient

    def add(
        self,
        name: str,
        extractor: Optional[str] = None,
        func: Optional[Callable] = None,
        input: Union[str, List[str]] = None,
        params: Optional[Dict[str, Any]] = None,
        output_shape: Optional[Tuple] = None,
    ):
        """添加特征

        支持多种使用方式：
        1. 使用注册的提取器：
           features.add('gm_max', extractor='transfer.gm_max', input='transfer')

        2. 使用自定义函数：
           features.add('mean_id', func=lambda x: np.mean([s['Id'] for s in x]),
                       input='transfer')

        3. 使用 lambda（依赖其他特征）：
           features.add('gm_norm', func=lambda gm: (gm - gm.mean()) / gm.std(),
                       input='gm_max')

        Args:
            name: 特征名称
            extractor: 注册的提取器名称（如 'transfer.gm_max'）
            func: 自定义函数（与 extractor 二选一）
            input: 输入依赖（数据源或其他特征名）
            params: 参数字典
            output_shape: 输出形状（使用 func 时必须提供）

        Raises:
            ValueError: 如果参数不合法
        """
        if extractor is None and func is None:
            raise ValueError("必须提供 extractor 或 func 之一")

        if extractor and func:
            raise ValueError("extractor 和 func 不能同时提供")

        # 规范化 input
        if input is None:
            inputs = []
        elif isinstance(input, str):
            inputs = [input]
        else:
            inputs = input

        params = params or {}

        # 创建计算节点
        if extractor:
            # 使用注册的提取器
            node = ComputeNode(
                name=name,
                func=extractor,
                inputs=inputs,
                params=params,
                is_extractor=True,
            )

        else:
            # 使用自定义函数
            if output_shape is None:
                # 尝试推断（假设为标量）
                output_shape = ('n_steps',)
                logger.warning(
                    f"特征 '{name}' 未指定 output_shape，假设为 {output_shape}"
                )

            # 🔑 尝试提取 lambda 源代码（用于序列化）
            source_code = None
            if callable(func):
                source_code = self._extract_lambda_source(func)

            node = ComputeNode(
                name=name,
                func=func,
                inputs=inputs,
                params=params,
                output_shape=output_shape,
                is_extractor=False,
                source_code=source_code,  # 🔑 保存源代码
            )

        # 添加到计算图
        self.graph.add_node(node)
        logger.debug(f"添加特征: {name} (输入: {inputs})")

        return self

    def _extract_lambda_source(self, func: Callable) -> Optional[str]:
        """提取 lambda 函数的源代码

        Args:
            func: Lambda 函数对象

        Returns:
            Lambda 源代码字符串，失败返回 None
        """
        try:
            import inspect

            # 只处理 lambda 函数
            if '<lambda>' not in func.__name__:
                return None

            # 获取源代码
            source = inspect.getsource(func).strip()

            # 查找 lambda 关键字
            if 'lambda' not in source:
                return None

            start_idx = source.find('lambda')
            remaining = source[start_idx:]

            # 使用括号平衡算法找到 lambda 表达式的结尾
            paren_count = 0
            bracket_count = 0
            in_string = False
            quote_char = None
            colon_found = False
            end_idx = len(remaining)

            for i, char in enumerate(remaining):
                # 处理字符串（跳过字符串内的括号）
                if char in ('"', "'") and (i == 0 or remaining[i-1] != '\\'):
                    if not in_string:
                        in_string = True
                        quote_char = char
                    elif char == quote_char:
                        in_string = False

                if not in_string:
                    # 统计括号
                    if char == '(':
                        paren_count += 1
                    elif char == ')':
                        paren_count -= 1
                    elif char == '[':
                        bracket_count += 1
                    elif char == ']':
                        bracket_count -= 1

                    # 标记冒号位置（参数列表结束，表达式开始）
                    if char == ':' and paren_count == 0 and bracket_count == 0:
                        colon_found = True

                    # 检查是否到达 lambda 表达式结尾
                    # 只有在冒号之后，遇到逗号或换行时才结束
                    if colon_found and char in (',', '\n') and paren_count == 0 and bracket_count == 0:
                        end_idx = i
                        break

            lambda_expr = remaining[:end_idx].strip()

            # 验证提取的 lambda 语法
            try:
                compile(lambda_expr, '<lambda>', 'eval')
                return lambda_expr
            except SyntaxError:
                return None

        except Exception:
            # 提取失败不影响功能
            return None

    def compute(self) -> Dict[str, np.ndarray]:
        """执行计算图（支持增量计算）

        优先从 Parquet 缓存加载已有特征，只计算缺失的特征。

        Returns:
            特征字典 {feature_name: ndarray}
        """
        if not self.experiment and self.graph.get_data_sources():
            raise RuntimeError("未设置 experiment，无法加载数据")

        # 1️⃣ 尝试加载缓存
        cached_features = {}
        if self.unified_experiment and self.config_name:
            try:
                cached_df = self.unified_experiment.get_v2_feature_dataframe(self.config_name)

                if cached_df is not None:
                    # 验证缓存有效性
                    if self._validate_cache(cached_df):
                        logger.info(f"✓ 发现有效缓存（配置: {self.config_name}）")

                        # 提取所有缓存特征
                        for col in cached_df.columns:
                            if col != 'step_index' and col in self.graph.nodes:
                                cached_features[col] = cached_df[col].to_numpy()
                                logger.info(f"  ✓ 从缓存加载: {col}")
                    else:
                        logger.warning("⚠ 缓存失效（源文件已改变），重新计算")
            except Exception as e:
                logger.warning(f"加载缓存失败: {e}，将重新计算")

        # 2️⃣ 检查是否全部命中缓存
        all_features = set(self.graph.nodes.keys())
        cached_feature_names = set(cached_features.keys())
        missing_features = all_features - cached_feature_names

        if not missing_features:
            # 全部命中缓存
            logger.info(f"✓ 全部 {len(cached_features)} 个特征从缓存加载，无需计算")

            # 填充 ExecutionContext
            self._computed_results = ExecutionContext()
            for name, value in cached_features.items():
                self._computed_results.set(name, value, 0)
            self._computed_results.cache_hits = len(cached_features)

            return cached_features

        # 3️⃣ 部分命中：增量计算
        logger.info(
            f"⚙️ 增量计算：{len(cached_features)} 个从缓存，"
            f"{len(missing_features)} 个需计算"
        )

        # 创建初始上下文（预填充缓存特征）
        initial_context = ExecutionContext()
        for name, value in cached_features.items():
            initial_context.set(name, value, 0)
        initial_context.cache_hits = len(cached_features)

        # 实例化提取器（只需要未缓存的）
        extractor_instances = {}
        for node_name in missing_features:
            if node_name in self.graph.nodes:
                node = self.graph.nodes[node_name]
                if node.is_extractor:
                    extractor_instances[node.func] = get_extractor(node.func, node.params)

        # 执行计算（传入初始上下文）
        executor = Executor(
            compute_graph=self.graph,
            data_loaders=self.data_loaders,
            extractor_registry=extractor_instances,
        )

        # 注入上下文信息（供 extractors 访问）
        executor.unified_experiment = self.unified_experiment
        executor.config_name = self.config_name
        executor.config_version = self.config_version

        context = executor.execute(initial_context=initial_context)
        self._computed_results = context

        # 4️⃣ 返回所有特征
        features = {}
        for name in self.graph.nodes:
            if name in context.results:
                features[name] = context.results[name]

        # 修正统计数据（只统计特征节点，不含数据源）
        # ExecutionContext 的 cache_hits 包含了数据源节点，需要修正
        actual_cache_hits = len(cached_features)
        actual_cache_misses = len(missing_features)
        context.cache_hits = actual_cache_hits
        context.cache_misses = actual_cache_misses

        # 输出统计（包含缓存信息）
        cache_hit_rate = len(cached_features) / len(all_features) if all_features else 0
        logger.info(
            f"✅ 计算完成：{len(features)} 个特征，"
            f"缓存命中率 {cache_hit_rate:.1%}，"
            f"耗时 {context.get_total_time():.2f}ms"
        )

        return features

    def to_dataframe(self, expand_multidim: bool = True) -> pd.DataFrame:
        """转换为 pandas DataFrame

        Args:
            expand_multidim: 是否展开多维特征（如 (n_steps, 100) → 100 列）

        Returns:
            DataFrame
        """
        if not self._computed_results:
            raise RuntimeError("请先调用 compute()")

        data_dict = {}

        for name, array in self._computed_results.results.items():
            if name in self.graph.nodes:  # 只包含特征（不含数据源）
                if array.ndim == 1:
                    # 标量特征
                    data_dict[name] = array
                elif array.ndim == 2 and expand_multidim:
                    # 多维特征：展开为多列
                    for i in range(array.shape[1]):
                        data_dict[f'{name}_{i}'] = array[:, i]
                elif not expand_multidim:
                    # 保持嵌套（转为列表）
                    data_dict[name] = list(array)
                else:
                    logger.warning(
                        f"特征 '{name}' 的维度为 {array.ndim}，暂不支持转换"
                    )

        df = pd.DataFrame(data_dict)
        df.insert(0, 'step_index', np.arange(len(df)))
        return df

    def to_parquet(
        self,
        output_path: str,
        merge_existing: bool = False,
        save_metadata: bool = True
    ):
        """导出为 Parquet 文件（支持增量合并和元数据）

        Args:
            output_path: 输出路径
            merge_existing: 是否合并已有文件（增量模式）
            save_metadata: 是否保存元数据（用于缓存验证）
        """
        output_path = Path(output_path)
        new_df = self.to_dataframe(expand_multidim=True)

        # 增量合并
        if merge_existing and output_path.exists():
            logger.info(f"🔄 增量合并到已有文件: {output_path.name}")
            try:
                existing_df = pd.read_parquet(output_path)

                # 保留旧元数据（稍后更新）
                old_attrs = existing_df.attrs.copy() if hasattr(existing_df, 'attrs') else {}

                # 验证行数一致性
                if len(existing_df) != len(new_df):
                    raise ValueError(
                        f"Parquet 合并失败：行数不匹配 "
                        f"(existing: {len(existing_df)}, new: {len(new_df)})"
                    )

                # 合并列（覆盖同名，追加新列）
                for col in new_df.columns:
                    if col != 'step_index':
                        if col in existing_df.columns:
                            logger.debug(f"  覆盖列: {col}")
                        else:
                            logger.debug(f"  新增列: {col}")
                        existing_df[col] = new_df[col]

                final_df = existing_df

                # 更新特征计数
                if save_metadata:
                    old_attrs['feature_count'] = len(final_df.columns) - 1
                    old_attrs['updated_at'] = pd.Timestamp.now().isoformat()
                    final_df.attrs = old_attrs

            except Exception as e:
                logger.error(f"合并失败: {e}，将覆盖写入")
                final_df = new_df
        else:
            final_df = new_df

        # 添加元数据
        if save_metadata and self.unified_experiment:
            final_df.attrs = {
                'chip_id': self.unified_experiment.chip_id,
                'device_id': self.unified_experiment.device_id,
                'config_name': self.config_name or 'unknown',
                'config_version': self.config_version,
                'source_file': str(self.unified_experiment._get_experiment().hdf5_path),  # 转换为字符串
                'source_hash': self._compute_source_hash(),
                'created_at': pd.Timestamp.now().isoformat(),
                'feature_count': len(final_df.columns) - 1
            }
            logger.debug(f"已添加元数据: source_hash={final_df.attrs['source_hash']}")

        # 保存
        final_df.to_parquet(output_path, compression='zstd', index=False)
        logger.info(
            f"✅ 已保存到 {output_path} "
            f"({len(final_df)} 行 × {len(final_df.columns)} 列)"
        )

    def get_statistics(self) -> Dict[str, Any]:
        """获取执行统计信息"""
        if not self._computed_results:
            raise RuntimeError("请先调用 compute()")

        return self._computed_results.get_statistics()

    @classmethod
    def from_config(cls, config_path: str, experiment=None, unified_experiment=None):
        """从配置文件加载

        Args:
            config_path: 配置文件路径（.yaml 或 .json）
            experiment: Experiment 实例
            unified_experiment: UnifiedExperiment 实例

        Returns:
            FeatureSet 对象

        示例:
            features = FeatureSet.from_config('config/v2_transfer.yaml', experiment=exp)
            # 或使用 UnifiedExperiment
            features = FeatureSet.from_config('~/.my_features/my_config.yaml', unified_experiment=exp)
        """
        from infra.features_v2.config.parser import ConfigParser
        return ConfigParser.from_file(config_path, experiment, unified_experiment)

    def visualize_graph(self) -> str:
        """可视化计算图"""
        return self.graph.visualize()

    def save_as_config(
        self,
        config_name: str,
        save_parquet: bool = True,
        append: bool = False,
        config_dir: str = 'user',
        description: str = ""
    ) -> Dict[str, Any]:
        """固化当前特征集为配置 + Parquet

        将当前计算的特征集保存为 YAML 配置文件，可选同时保存 Parquet 数据。

        Args:
            config_name: 配置名称
            save_parquet: 是否保存 Parquet 数据
            append: 是否增量追加（合并已有配置）
            config_dir: 配置保存位置
                - 'user': ~/.my_features/ （个人配置）
                - 'global': infra/catalog/feature_configs/ （全局共享）
                - 其他: 自定义路径
            description: 配置描述

        Returns:
            {'config_file': '...', 'parquet_file': '...', 'features_added': [...], 'config_version': '...'}

        Raises:
            RuntimeError: 如果未先调用 compute()
        """
        import yaml

        if not self._computed_results:
            raise RuntimeError("请先调用 compute() 计算特征")

        # 1️⃣ 确定保存路径
        if config_dir == 'user':
            base_dir = Path.home() / '.my_features'
        elif config_dir == 'global':
            base_dir = Path(__file__).parent.parent.parent.parent / 'catalog' / 'feature_configs'
        else:
            base_dir = Path(config_dir)

        base_dir.mkdir(parents=True, exist_ok=True)
        config_file = base_dir / f"{config_name}.yaml"

        # 2️⃣ 构建配置字典
        feature_specs = []
        unsupported_features = []

        for node_name, node in self.graph.nodes.items():
            spec = {
                'name': node_name,
                'input': node.inputs[0] if len(node.inputs) == 1 else node.inputs,
            }

            # 添加参数（如果存在）
            if node.params:
                spec['params'] = node.params

            if node.is_extractor:
                # 提取器特征：保存提取器名称
                spec['extractor'] = node.func
            elif callable(node.func):
                # Lambda/函数特征：尝试序列化
                try:
                    import inspect

                    # 🔑 优先使用保存的源代码
                    if node.source_code:
                        spec['func'] = node.source_code
                        logger.debug(f"✓ 使用保存的源代码: {node_name} <- {node.source_code[:60]}...")
                    # 检查是否为 lambda（回退方案）
                    elif '<lambda>' in node.func.__name__:
                        # 提取纯 lambda 表达式（使用括号平衡算法）
                        source = inspect.getsource(node.func).strip()

                        # 查找 lambda 关键字位置
                        if 'lambda' in source:
                            start_idx = source.find('lambda')
                            remaining = source[start_idx:]

                            # 智能提取：使用括号平衡算法找到 lambda 表达式的结尾
                            paren_count = 0
                            bracket_count = 0
                            in_string = False
                            quote_char = None
                            colon_found = False  # 关键：标记是否已经遇到冒号
                            end_idx = len(remaining)

                            for i, char in enumerate(remaining):
                                # 处理字符串（跳过字符串内的括号）
                                if char in ('"', "'") and (i == 0 or remaining[i-1] != '\\'):
                                    if not in_string:
                                        in_string = True
                                        quote_char = char
                                    elif char == quote_char:
                                        in_string = False

                                if not in_string:
                                    # 统计括号
                                    if char == '(':
                                        paren_count += 1
                                    elif char == ')':
                                        paren_count -= 1
                                    elif char == '[':
                                        bracket_count += 1
                                    elif char == ']':
                                        bracket_count -= 1

                                    # 标记冒号位置（参数列表结束，表达式开始）
                                    if char == ':' and paren_count == 0 and bracket_count == 0:
                                        colon_found = True

                                    # 检查是否到达 lambda 表达式结尾
                                    # 只有在冒号之后，遇到逗号或换行时才结束
                                    if colon_found and char in (',', '\n') and paren_count == 0 and bracket_count == 0:
                                        end_idx = i
                                        break

                            lambda_expr = remaining[:end_idx].strip()
                            logger.debug(f"提取的 lambda: '{lambda_expr}'")

                            # 验证提取的 lambda 语法是否有效
                            test_namespace = {'np': np, 'numpy': np}
                            try:
                                # 使用 compile 验证语法（不执行）
                                compile(lambda_expr, '<lambda>', 'eval')
                                # 再用 eval 创建函数对象（验证可调用性）
                                func_obj = eval(lambda_expr, test_namespace)
                                if not callable(func_obj):
                                    raise ValueError(f"'{lambda_expr}' 不是可调用对象")
                            except SyntaxError as e:
                                raise ValueError(f"Lambda 语法错误: {e}")

                            spec['func'] = lambda_expr
                            logger.debug(f"✓ 序列化 lambda: {lambda_expr[:60]}...")
                        else:
                            raise ValueError("无法在源代码中找到 lambda 关键字")
                    else:
                        # 命名函数：警告无法序列化
                        logger.warning(
                            f"特征 '{node_name}' 使用命名函数，无法完整序列化到配置文件"
                        )
                        spec['func'] = f"# UNSUPPORTED: {node.func.__name__}"
                        unsupported_features.append(node_name)
                except Exception as e:
                    logger.warning(f"无法序列化特征 '{node_name}' 的函数: {e}")
                    spec['func'] = "# UNSUPPORTED"
                    unsupported_features.append(node_name)

                # 添加输出形状
                if node.output_shape:
                    spec['output_shape'] = list(node.output_shape)
            else:
                logger.warning(f"跳过特征 '{node_name}'：不支持的类型")
                continue

            feature_specs.append(spec)

        if unsupported_features:
            logger.warning(
                f"以下特征无法完整序列化: {unsupported_features}。"
                "建议使用提取器或简单 lambda 表达式。"
            )

        config_dict = {
            'version': 'v2',
            'name': config_name,
            'config_version': self.config_version,
            'description': description or f"Auto-generated config for {config_name}",
            'data_type': 'transfer',  # TODO: 从数据源推断
            'features': feature_specs
        }

        # 3️⃣ 处理 append 模式
        features_added = []
        if append and config_file.exists():
            logger.info(f"📝 增量模式：合并已有配置 {config_file.name}")
            with open(config_file, 'r', encoding='utf-8') as f:
                existing_config = yaml.safe_load(f)

            # 合并特征（智能去重）
            existing_features = {f['name']: f for f in existing_config.get('features', [])}

            for spec in feature_specs:
                name = spec['name']
                if name in existing_features:
                    # 检查定义是否相同
                    if existing_features[name] == spec:
                        logger.info(f"  特征 '{name}' 已存在且定义相同，跳过")
                    else:
                        # 定义不同，更新
                        logger.warning(f"  特征 '{name}' 定义已更新")
                        existing_features[name] = spec
                        features_added.append(name)
                else:
                    # 新特征
                    existing_features[name] = spec
                    features_added.append(name)
                    logger.info(f"  添加新特征: {name}")

            config_dict['features'] = list(existing_features.values())

            # 递增版本号
            old_version = existing_config.get('config_version', '1.0')
            try:
                major, minor = map(int, old_version.split('.'))
                config_dict['config_version'] = f"{major}.{minor + 1}"
            except ValueError:
                logger.warning(f"无法解析版本号 '{old_version}'，重置为 1.1")
                config_dict['config_version'] = "1.1"

            logger.info(f"  ✓ 配置版本更新: {old_version} → {config_dict['config_version']}")
        else:
            features_added = [spec['name'] for spec in feature_specs]

        # 4️⃣ 保存配置文件
        with open(config_file, 'w', encoding='utf-8') as f:
            yaml.dump(config_dict, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        logger.info(f"✓ 配置已保存: {config_file}")

        # 5️⃣ 保存 Parquet（可选）
        parquet_file = None
        if save_parquet:
            if self.unified_experiment:
                # 获取 catalog 配置的 features_v2 目录（与现有 V2 提取保持一致）
                try:
                    parquet_dir = self.unified_experiment._manager.catalog.config.get_absolute_path('features_v2')
                except Exception:
                    # Fallback: 使用默认路径
                    parquet_dir = Path('data') / 'features_v2'

                parquet_dir.mkdir(parents=True, exist_ok=True)

                chip_id = self.unified_experiment.chip_id
                device_id = self.unified_experiment.device_id

                # 删除同配置的旧文件（保持唯一性）
                old_pattern = f"{chip_id}-{device_id}-{config_name}-feat_*.parquet"
                old_files = list(parquet_dir.glob(old_pattern))
                if old_files:
                    logger.info(f"🗑️  删除 {len(old_files)} 个旧 Parquet 文件（同配置）")
                    for old_file in old_files:
                        old_file.unlink()
                        logger.debug(f"   删除: {old_file.name}")

                # 生成新文件名
                timestamp = pd.Timestamp.now().strftime('%Y%m%d-%H%M%S')
                import hashlib
                hash_suffix = hashlib.md5(f"{chip_id}{device_id}{config_name}{timestamp}".encode()).hexdigest()[:8]

                parquet_file = parquet_dir / f"{chip_id}-{device_id}-{config_name}-feat_{timestamp}_{hash_suffix}.parquet"

                self.to_parquet(
                    str(parquet_file),
                    merge_existing=False,  # 配置固化时总是创建新文件
                    save_metadata=True
                )
                logger.info(f"✓ Parquet 已保存: {parquet_file}")

                # 更新数据库元数据（关键！）
                self._update_v2_metadata_in_database(str(parquet_file), config_name)
            else:
                logger.warning("未提供 unified_experiment，跳过 Parquet 保存")

        return {
            'config_file': str(config_file),
            'parquet_file': str(parquet_file) if parquet_file else None,
            'features_added': features_added,
            'config_version': config_dict['config_version']
        }

    def _compute_source_hash(self) -> str:
        """计算源文件轻量级哈希

        基于元数据（chip_id, device_id, mtime, size）计算哈希，
        避免读取完整文件内容。

        Returns:
            哈希字符串（MD5 前16位）
        """
        import hashlib

        if not self.unified_experiment:
            return ""

        try:
            exp = self.unified_experiment._get_experiment()
            file_path = Path(exp.hdf5_path)

            if not file_path.exists():
                logger.warning(f"源文件不存在: {file_path}")
                return ""

            stat = file_path.stat()
            hash_input = (
                f"{self.unified_experiment.chip_id}|"
                f"{self.unified_experiment.device_id}|"
                f"{stat.st_mtime}|"
                f"{stat.st_size}"
            )

            hash_value = hashlib.md5(hash_input.encode()).hexdigest()[:16]
            logger.debug(f"计算源文件哈希: {hash_value} (基于 {file_path.name})")
            return hash_value

        except Exception as e:
            logger.error(f"计算源文件哈希失败: {e}")
            return ""

    def _update_v2_metadata_in_database(self, parquet_file: str, config_name: str):
        """更新数据库中的 V2 特征元数据

        Args:
            parquet_file: Parquet 文件路径
            config_name: 配置名称
        """
        if not self.unified_experiment:
            return

        try:
            # 构建元数据
            metadata = {
                'config_name': config_name,
                'config_version': self.config_version,
                'output_files': [parquet_file],
                'created_at': pd.Timestamp.now().isoformat(),
                'feature_count': len(self.graph.nodes)
            }

            # 获取数据库仓库
            repo = self.unified_experiment._manager.catalog.repository

            # 读取现有元数据
            exp_id = self.unified_experiment.id
            existing_metadata = repo.get_v2_feature_metadata(exp_id)

            if existing_metadata:
                # 合并文件列表（避免重复）
                existing_files = existing_metadata.get('output_files', [])
                if parquet_file not in existing_files:
                    existing_files.append(parquet_file)
                    metadata['output_files'] = existing_files
                else:
                    metadata['output_files'] = existing_files

            # 更新到数据库
            repo.update_v2_feature_metadata(exp_id, metadata)
            logger.info(f"✓ 已更新数据库元数据: exp_id={exp_id}, config={config_name}")

        except Exception as e:
            logger.warning(f"更新数据库元数据失败: {e}（不影响 Parquet 保存）")

    def _validate_cache(self, cached_df: pd.DataFrame, strict: bool = False) -> bool:
        """验证 Parquet 缓存是否有效

        通过比较源文件哈希判断缓存是否仍然有效。

        Args:
            cached_df: 缓存的 DataFrame
            strict: 严格模式（缺少 hash 时返回 False）

        Returns:
            缓存是否有效
        """
        if not hasattr(cached_df, 'attrs'):
            logger.warning("缓存 DataFrame 缺少 attrs 属性")
            return not strict

        metadata = cached_df.attrs
        cached_hash = metadata.get('source_hash')

        if not cached_hash:
            if strict:
                logger.error("严格模式：缓存缺少 source_hash，视为无效")
                return False
            else:
                # 向后兼容：旧缓存没有 hash，假设有效
                logger.warning("缓存缺少 source_hash，向后兼容模式下假设有效")
                return True

        # 计算当前源文件哈希
        current_hash = self._compute_source_hash()

        if not current_hash:
            logger.warning("无法计算当前源文件哈希，假设缓存有效")
            return True

        if current_hash != cached_hash:
            logger.debug(f"源文件哈希不匹配: 当前={current_hash}, 缓存={cached_hash}")
            return False

        logger.debug("缓存验证通过：源文件哈希匹配")
        return True

    def __repr__(self):
        return f"FeatureSet(features={len(self.graph.nodes)})"
