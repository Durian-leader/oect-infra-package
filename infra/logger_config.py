"""
# 在其他文件中的使用示例：
---
########################### 日志设置 ################################
from logger_config import get_module_logger
logger = get_module_logger() 
#####################################################################
---
"""
import logging
import logging.config
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional

class LoggerManager:
    """日志管理器：统一配置和管理所有模块的日志"""
    
    def __init__(self, log_dir="logs", default_level=logging.INFO, console_level=logging.WARNING,
                 max_bytes=10*1024*1024, backup_count=5):
        """
        初始化日志管理器
        
        Args:
            log_dir: 日志文件目录
            default_level: 默认文件日志级别
            console_level: 控制台日志级别
            max_bytes: 单个日志文件最大字节数 (默认10MB)
            backup_count: 保留的备份文件数量 (默认5个)
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.default_level = default_level
        self.console_level = console_level
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.loggers = {}
        
    def get_logger(self, module_name: str, level: Optional[int] = None) -> logging.Logger:
        """
        为指定模块获取专用logger
        
        Args:
            module_name: 模块名称，将作为日志文件名
            level: 日志级别，如果未指定则使用默认级别
        
        Returns:
            配置好的logger对象
        """
        if module_name in self.loggers:
            return self.loggers[module_name]
            
        # 创建logger
        logger = logging.getLogger(module_name)
        logger.setLevel(level or self.default_level)
        
        # 避免重复添加handler
        if not logger.handlers:
            # 轮转文件handler - 每个模块独立的日志文件，支持自动轮转
            log_file = self.log_dir / f"{module_name}.log"
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=self.max_bytes,      # 文件大小上限
                backupCount=self.backup_count, # 备份文件数量
                encoding='utf-8'
            )
            file_handler.setLevel(level or self.default_level)
            
            # 控制台handler - 便于开发调试
            console_handler = logging.StreamHandler()
            console_handler.setLevel(self.console_level)
            
            # 格式化器
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            
            file_handler.setFormatter(formatter)
            console_handler.setFormatter(formatter)
            
            # 添加处理器
            logger.addHandler(file_handler)
            logger.addHandler(console_handler)
            
        self.loggers[module_name] = logger
        return logger
    
    def set_global_level(self, level: Optional[int] = None):
        """设置所有已创建logger的级别"""
        self.default_level = level
        for logger in self.loggers.values():
            logger.setLevel(level)
            for handler in logger.handlers:
                if isinstance(handler, (logging.FileHandler, RotatingFileHandler)):
                    handler.setLevel(level)
    
    def set_console_level(self, level: Optional[int] = None):
        """设置控制台输出级别"""
        self.console_level = level
        for logger in self.loggers.values():
            for handler in logger.handlers:
                if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                    handler.setLevel(level)
    
    def set_levels(self, file_level: Optional[int] = None, console_level: Optional[int] = None):
        """同时设置文件和控制台级别"""
        if file_level is not None:
            self.set_global_level(file_level)
        if console_level is not None:
            self.set_console_level(console_level)

# 全局日志管理器实例 - 可以在这里设置默认的控制台级别和轮转配置
log_manager = LoggerManager(
    console_level=logging.INFO,     # 控制台显示INFO及以上级别
    max_bytes=5*1024*1024,        # 单个日志文件最大5MB
    backup_count=5                 # 保留5个备份文件
)

def get_module_logger(module_name: str = None) -> logging.Logger:
    """
    便捷函数：获取模块logger
    如果不指定module_name，则使用调用者的模块名
    """
    if module_name is None:
        import inspect
        frame = inspect.currentframe().f_back
        module_name = frame.f_globals.get('__name__', 'unknown')
        if module_name == '__main__':
            module_name = 'main'
    
    return log_manager.get_logger(module_name)
