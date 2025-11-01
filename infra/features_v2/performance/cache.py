"""
多层缓存系统

提供内存 + 磁盘的两级缓存
"""

from typing import Any, Optional
from collections import OrderedDict
from pathlib import Path
import numpy as np
import pickle
import hashlib
import threading

from infra.logger_config import get_module_logger

logger = get_module_logger()


class LRUCache:
    """LRU（最近最少使用）缓存"""

    def __init__(self, maxsize: int = 100):
        """
        Args:
            maxsize: 最大缓存项数
        """
        self.maxsize = maxsize
        self.cache = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        """获取缓存项"""
        if key in self.cache:
            # 移到末尾（标记为最近使用）
            self.cache.move_to_end(key)
            self.hits += 1
            return self.cache[key]
        else:
            self.misses += 1
            return None

    def put(self, key: str, value: Any):
        """存入缓存"""
        if key in self.cache:
            # 更新并移到末尾
            self.cache.move_to_end(key)
        self.cache[key] = value

        # 如果超过容量，移除最旧的项
        if len(self.cache) > self.maxsize:
            self.cache.popitem(last=False)

    def clear(self):
        """清空缓存"""
        self.cache.clear()
        self.hits = 0
        self.misses = 0

    def get_statistics(self) -> dict:
        """获取统计信息"""
        total = self.hits + self.misses
        hit_rate = self.hits / total if total > 0 else 0
        return {
            'size': len(self.cache),
            'maxsize': self.maxsize,
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': hit_rate,
        }


class MultiLevelCache:
    """多层缓存系统

    L1: 内存缓存（LRU，快速）
    L2: 磁盘缓存（Pickle，持久）
    """

    def __init__(
        self,
        memory_size_mb: int = 512,
        disk_cache_dir: Optional[str] = '.cache',
        enable_disk: bool = True,
    ):
        """
        Args:
            memory_size_mb: 内存缓存大小（MB）
            disk_cache_dir: 磁盘缓存目录
            enable_disk: 是否启用磁盘缓存
        """
        # L1: 内存缓存
        # 估算：假设每个特征数组 (5000 步) 约 40KB，512MB ≈ 13000 个数组
        estimated_items = int((memory_size_mb * 1024 * 1024) / (5000 * 8))
        self.memory = LRUCache(maxsize=max(estimated_items, 100))

        # L2: 磁盘缓存
        self.enable_disk = enable_disk
        if enable_disk and disk_cache_dir:
            self.disk_dir = Path(disk_cache_dir)
            self.disk_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.disk_dir = None

        # 线程锁（用于线程安全）
        self.lock = threading.Lock()

        logger.debug(
            f"MultiLevelCache 初始化：内存 {estimated_items} 项，"
            f"磁盘缓存 {'启用' if enable_disk else '禁用'}"
        )

    def get(self, key: str) -> Optional[np.ndarray]:
        """获取缓存项（自动穿透 L1 → L2）

        Args:
            key: 缓存键

        Returns:
            缓存的数组，如果不存在返回 None
        """
        with self.lock:
            # L1: 内存缓存
            value = self.memory.get(key)
            if value is not None:
                logger.debug(f"缓存命中（内存）: {key}")
                return value

            # L2: 磁盘缓存
            if self.enable_disk and self.disk_dir:
                disk_path = self._get_disk_path(key)
                if disk_path.exists():
                    try:
                        with open(disk_path, 'rb') as f:
                            value = pickle.load(f)

                        # 加载到内存缓存
                        self.memory.put(key, value)
                        logger.debug(f"缓存命中（磁盘）: {key}")
                        return value
                    except Exception as e:
                        logger.warning(f"磁盘缓存读取失败: {key}, {e}")
                        # 删除损坏的缓存文件
                        disk_path.unlink(missing_ok=True)

            return None

    def put(self, key: str, value: np.ndarray):
        """存入缓存（写入 L1 和 L2）

        Args:
            key: 缓存键
            value: 数组
        """
        with self.lock:
            # L1: 内存缓存
            self.memory.put(key, value)

            # L2: 磁盘缓存（异步写入，避免阻塞）
            if self.enable_disk and self.disk_dir:
                threading.Thread(
                    target=self._write_to_disk,
                    args=(key, value),
                    daemon=True,
                ).start()

    def _write_to_disk(self, key: str, value: np.ndarray):
        """写入磁盘缓存（后台线程）"""
        try:
            disk_path = self._get_disk_path(key)
            with open(disk_path, 'wb') as f:
                pickle.dump(value, f, protocol=pickle.HIGHEST_PROTOCOL)
            logger.debug(f"缓存写入磁盘: {key}")
        except Exception as e:
            logger.warning(f"磁盘缓存写入失败: {key}, {e}")

    def _get_disk_path(self, key: str) -> Path:
        """获取磁盘缓存路径"""
        # 使用 MD5 哈希避免文件名过长
        hash_key = hashlib.md5(key.encode()).hexdigest()
        return self.disk_dir / f"{hash_key}.pkl"

    def clear_memory(self):
        """清空内存缓存"""
        with self.lock:
            self.memory.clear()
            logger.info("内存缓存已清空")

    def clear_disk(self):
        """清空磁盘缓存"""
        if self.disk_dir and self.disk_dir.exists():
            for file in self.disk_dir.glob('*.pkl'):
                file.unlink()
            logger.info("磁盘缓存已清空")

    def clear_all(self):
        """清空所有缓存"""
        self.clear_memory()
        self.clear_disk()

    def get_statistics(self) -> dict:
        """获取统计信息"""
        mem_stats = self.memory.get_statistics()

        # 磁盘缓存统计
        if self.disk_dir and self.disk_dir.exists():
            disk_files = list(self.disk_dir.glob('*.pkl'))
            disk_count = len(disk_files)
            disk_size_mb = sum(f.stat().st_size for f in disk_files) / (1024 * 1024)
        else:
            disk_count = 0
            disk_size_mb = 0

        return {
            'memory': mem_stats,
            'disk': {
                'enabled': self.enable_disk,
                'count': disk_count,
                'size_mb': disk_size_mb,
            },
        }


class CachedExecutor:
    """带缓存的执行器包装器（预留，可集成到 Executor）"""

    def __init__(self, executor, cache: MultiLevelCache):
        self.executor = executor
        self.cache = cache

    def execute(self):
        """执行计算图（使用缓存）"""
        # TODO: 集成缓存到执行流程
        # 1. 在 _execute_node 前检查缓存
        # 2. 计算后存入缓存
        raise NotImplementedError("缓存集成将在后续版本实现")
