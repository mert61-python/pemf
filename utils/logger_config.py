# -*- coding: utf-8 -*-
"""
Centralized Logger Configuration for PEMF GUI Application
Provides clean, performant, and structured logging system.

@author: merta
@date: 2025-01-28
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler, QueueHandler, QueueListener
from queue import Queue
import threading


# Custom TRACE level (compatible with ESP32 Logger.h)
# ESP32: TRACE=0, DEBUG=1, INFO=2, WARN=3, ERROR=4, FATAL=5
# Python: NOTSET=0, DEBUG=10, INFO=20, WARNING=30, ERROR=40, CRITICAL=50
TRACE = 5  # Between NOTSET and DEBUG
logging.addLevelName(TRACE, 'TRACE')

def trace(self, message, *args, **kwargs):
    """Log message with TRACE level"""
    if self.isEnabledFor(TRACE):
        self._log(TRACE, message, args, **kwargs)

# Add trace method to Logger class
logging.Logger.trace = trace


class LogLevel:
    """Log level constants (compatible with ESP32)"""
    TRACE = TRACE
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


class ColoredFormatter(logging.Formatter):
    """Colored console formatter for better readability"""
    
    # ANSI color codes
    COLORS = {
        'TRACE': '\033[90m',      # Dark gray
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m'        # Reset
    }
    
    def format(self, record):
        # Add color to level name
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{self.COLORS['RESET']}"
        
        return super().format(record)


class PEMFLoggerConfig:
    """
    Centralized logger configuration for PEMF GUI.
    
    Features:
    - Async logging (non-blocking)
    - Rotating file handlers
    - Colored console output
    - Module-specific loggers
    - Performance optimized
    """
    
    _instance = None
    _lock = threading.Lock()
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.log_queue = Queue(-1)  # Unlimited queue
        self.queue_listener = None
        self.handlers = []
        
    def setup_logging(
        self,
        log_dir: Path,
        console_level: int = logging.WARNING,  # Only warnings and above to console
        file_level: int = logging.INFO,
        enable_console: bool = True,
        enable_file: bool = True,
        max_file_size: int = 10 * 1024 * 1024,  # 10 MB (rotation size)
        backup_count: int = 5  # Keep 5 backup files
    ):
        """
        Setup centralized logging system.
        
        Args:
            log_dir: Directory for log files
            console_level: Minimum level for console output (default: WARNING)
            file_level: Minimum level for file output (default: INFO)
            enable_console: Enable console logging (default: True)
            enable_file: Enable file logging (default: True)
            max_file_size: Maximum size of each log file in bytes (default: 10 MB)
                          When exceeded, file is rotated and a new one is created
            backup_count: Number of backup log files to keep (default: 5)
                         Old files are named: pemf_gui_YYYYMMDD.log.1, .2, etc.
                         
        Log Rotation:
            - Main log: pemf_gui_YYYYMMDD.log
            - When size exceeds max_file_size:
              * Current log → pemf_gui_YYYYMMDD.log.1
              * .log.1 → .log.2, etc.
              * Oldest backup (beyond backup_count) is deleted
        """
        # Create log directory
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Clear existing handlers
        self.handlers.clear()
        
        # File handler with rotation
        if enable_file:
            log_filename = f"pemf_gui_{datetime.now().strftime('%Y%m%d')}.log"
            log_file_path = log_dir / log_filename
            
            file_handler = RotatingFileHandler(
                log_file_path,
                maxBytes=max_file_size,
                backupCount=backup_count,
                encoding='utf-8'
            )
            file_handler.setLevel(file_level)
            file_formatter = logging.Formatter(
                '%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(file_formatter)
            self.handlers.append(file_handler)
        
        # Console handler with colors
        if enable_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(console_level)
            console_formatter = ColoredFormatter(
                '%(levelname)-8s | %(name)-15s | %(message)s'
            )
            console_handler.setFormatter(console_formatter)
            self.handlers.append(console_handler)
        
        # Setup queue listener for async logging
        if self.handlers:
            self.queue_listener = QueueListener(
                self.log_queue,
                *self.handlers,
                respect_handler_level=True
            )
            self.queue_listener.start()
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)  # Capture everything, handlers will filter
        
        # Remove existing handlers
        root_logger.handlers.clear()
        
        # Add queue handler to root logger
        queue_handler = QueueHandler(self.log_queue)
        root_logger.addHandler(queue_handler)
        
        # Log initialization
        logger = self.get_logger('LoggerConfig')
        logger.info("=== PEMF GUI Logger Initialized ===")
        logger.info(f"Log directory: {log_dir}")
        logger.info(f"Console level: {logging.getLevelName(console_level)}")
        logger.info(f"File level: {logging.getLevelName(file_level)}")
        if enable_file:
            logger.info(f"Log rotation: {max_file_size / (1024*1024):.1f} MB per file, {backup_count} backups")
            logger.info(f"Total log capacity: {(max_file_size * (backup_count + 1)) / (1024*1024):.1f} MB")
    
    def get_logger(self, name: str) -> logging.Logger:
        """
        Get a logger for a specific module.
        
        Args:
            name: Logger name (usually module name)
            
        Returns:
            logging.Logger: Configured logger instance
        """
        return logging.getLogger(name)
    
    def set_console_level(self, level: int):
        """Change console logging level dynamically"""
        for handler in self.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, RotatingFileHandler):
                handler.setLevel(level)
    
    def set_file_level(self, level: int):
        """Change file logging level dynamically"""
        for handler in self.handlers:
            if isinstance(handler, RotatingFileHandler):
                handler.setLevel(level)
    
    def shutdown(self):
        """Shutdown logging system gracefully"""
        if self.queue_listener:
            self.queue_listener.stop()
        
        # Close all handlers
        for handler in self.handlers:
            handler.close()
        
        logger = self.get_logger('LoggerConfig')
        logger.info("=== PEMF GUI Logger Shutdown ===")


# Singleton instance
_logger_config = None
_config_lock = threading.Lock()


def get_logger_config() -> PEMFLoggerConfig:
    """Get singleton logger config instance"""
    global _logger_config
    if _logger_config is None:
        with _config_lock:
            if _logger_config is None:
                _logger_config = PEMFLoggerConfig()
    return _logger_config


def get_logger(name: str) -> logging.Logger:
    """
    Convenience function to get a logger.
    
    Usage:
        from utils.logger_config import get_logger
        logger = get_logger(__name__)
        logger.info("Message")
    """
    return get_logger_config().get_logger(name)


# Module-specific logger helpers
class LoggerMixin:
    """Mixin class to add logger to any class"""
    
    @property
    def logger(self) -> logging.Logger:
        """Get logger for this class"""
        if not hasattr(self, '_logger'):
            self._logger = get_logger(self.__class__.__name__)
        return self._logger


# Debug helper
def log_function_call(func):
    """Decorator to log function calls (for debugging)"""
    def wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)
        logger.debug(f"Calling {func.__name__}()")
        try:
            result = func(*args, **kwargs)
            logger.debug(f"{func.__name__}() completed")
            return result
        except Exception as e:
            logger.error(f"{func.__name__}() failed: {e}")
            raise
    return wrapper

