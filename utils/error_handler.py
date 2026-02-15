"""
Enhanced Error Handling and Logging Module for PEMF Web Server
Provides comprehensive error management, logging, and monitoring capabilities.
"""

import logging
import traceback
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from functools import wraps
import sys


class PEMFLogger:
    """Enhanced logging system for PEMF web server"""
    
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # Create different log files for different purposes
        self.setup_loggers()
        
    def setup_loggers(self):
        """Setup multiple loggers for different components"""
        
        # Main application logger
        self.app_logger = self._create_logger(
            'pemf_app', 
            self.log_dir / 'app.log',
            logging.INFO
        )
        
        # Security logger
        self.security_logger = self._create_logger(
            'pemf_security',
            self.log_dir / 'security.log',
            logging.WARNING
        )
        
        # Error logger
        self.error_logger = self._create_logger(
            'pemf_errors',
            self.log_dir / 'errors.log',
            logging.ERROR
        )
        
        # Performance logger
        self.performance_logger = self._create_logger(
            'pemf_performance',
            self.log_dir / 'performance.log',
            logging.INFO
        )
        
        # WebSocket logger
        self.websocket_logger = self._create_logger(
            'pemf_websocket',
            self.log_dir / 'websocket.log',
            logging.INFO
        )
    
    def _create_logger(self, name: str, log_file: Path, level: int) -> logging.Logger:
        """Create a configured logger"""
        logger = logging.getLogger(name)
        logger.setLevel(level)
        
        # Remove existing handlers to avoid duplicates
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        # File handler
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.WARNING)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        return logger

class ErrorHandler:
    """Comprehensive error handling system"""
    
    def __init__(self, logger: PEMFLogger):
        self.logger = logger
        self.error_counts = {}
        self.error_history = []
        
    def handle_exception(self, exc_type, exc_value, exc_traceback, context: str = ""):
        """Handle and log exceptions with full context"""
        error_id = f"{exc_type.__name__}_{int(time.time())}"
        
        error_info = {
            'error_id': error_id,
            'type': exc_type.__name__,
            'message': str(exc_value),
            'context': context,
            'timestamp': datetime.now().isoformat(),
            'traceback': traceback.format_exception(exc_type, exc_value, exc_traceback)
        }
        
        # Log the error
        self.logger.error_logger.error(
            f"Error {error_id}: {exc_type.__name__} in {context} - {exc_value}"
        )
        
        # Store error for monitoring
        self.error_history.append(error_info)
        self.error_counts[exc_type.__name__] = self.error_counts.get(exc_type.__name__, 0) + 1
        
        # Keep only last 100 errors
        if len(self.error_history) > 100:
            self.error_history.pop(0)
        
        return error_info
    
    def log_security_event(self, event_type: str, details: Dict[str, Any], severity: str = "WARNING"):
        """Log security-related events"""
        security_info = {
            'event_type': event_type,
            'details': details,
            'severity': severity,
            'timestamp': datetime.now().isoformat()
        }
        
        log_message = f"Security Event: {event_type} - {json.dumps(details, ensure_ascii=False)}"
        
        if severity == "CRITICAL":
            self.logger.security_logger.critical(log_message)
        elif severity == "ERROR":
            self.logger.security_logger.error(log_message)
        else:
            self.logger.security_logger.warning(log_message)
    
    def log_performance_metric(self, operation: str, duration: float, details: Dict[str, Any] = None):
        """Log performance metrics"""
        perf_info = {
            'operation': operation,
            'duration_ms': round(duration * 1000, 2),
            'details': details or {},
            'timestamp': datetime.now().isoformat()
        }
        
        self.logger.performance_logger.info(
            f"Performance: {operation} took {perf_info['duration_ms']}ms - {json.dumps(details or {}, ensure_ascii=False)}"
        )
    
    def get_error_summary(self) -> Dict[str, Any]:
        """Get summary of recent errors"""
        return {
            'total_errors': len(self.error_history),
            'error_counts': self.error_counts,
            'recent_errors': self.error_history[-10:] if self.error_history else [],
            'timestamp': datetime.now().isoformat()
        }

def error_handler_decorator(error_handler: ErrorHandler, context: str = ""):
    """Decorator for automatic error handling"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                start_time = time.time()
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                
                # Log performance if it takes more than 100ms
                if duration > 0.1:
                    error_handler.log_performance_metric(
                        f"{func.__name__}",
                        duration,
                        {'args_count': len(args), 'kwargs_count': len(kwargs)}
                    )
                
                return result
            except Exception as e:
                error_handler.handle_exception(
                    type(e), e, e.__traceback__, 
                    context or f"{func.__module__}.{func.__name__}"
                )
                raise
        return wrapper
    return decorator

def performance_monitor(error_handler: ErrorHandler, operation_name: str = ""):
    """Decorator for performance monitoring"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                
                error_handler.log_performance_metric(
                    operation_name or func.__name__,
                    duration,
                    {'success': True}
                )
                
                return result
            except Exception as e:
                duration = time.time() - start_time
                error_handler.log_performance_metric(
                    operation_name or func.__name__,
                    duration,
                    {'success': False, 'error': str(e)}
                )
                raise
        return wrapper
    return decorator

# Global error handler instance
_error_handler = None
_logger = None

def get_error_handler() -> ErrorHandler:
    """Get global error handler instance"""
    global _error_handler, _logger
    if _error_handler is None:
        _logger = PEMFLogger()
        _error_handler = ErrorHandler(_logger)
    return _error_handler

def get_logger() -> PEMFLogger:
    """Get global logger instance"""
    global _logger
    if _logger is None:
        _logger = PEMFLogger()
    return _logger

class HTTPErrorResponse:
    """Standard HTTP error responses"""
    
    @staticmethod
    def bad_request(message: str = "Bad Request") -> Dict[str, Any]:
        return {
            'error': 'Bad Request',
            'message': message,
            'status_code': 400,
            'timestamp': datetime.now().isoformat()
        }
    
    @staticmethod
    def unauthorized(message: str = "Unauthorized") -> Dict[str, Any]:
        return {
            'error': 'Unauthorized',
            'message': message,
            'status_code': 401,
            'timestamp': datetime.now().isoformat()
        }
    
    @staticmethod
    def forbidden(message: str = "Forbidden") -> Dict[str, Any]:
        return {
            'error': 'Forbidden',
            'message': message,
            'status_code': 403,
            'timestamp': datetime.now().isoformat()
        }
    
    @staticmethod
    def not_found(message: str = "Not Found") -> Dict[str, Any]:
        return {
            'error': 'Not Found',
            'message': message,
            'status_code': 404,
            'timestamp': datetime.now().isoformat()
        }
    
    @staticmethod
    def rate_limited(message: str = "Rate Limit Exceeded") -> Dict[str, Any]:
        return {
            'error': 'Rate Limit Exceeded',
            'message': message,
            'status_code': 429,
            'timestamp': datetime.now().isoformat()
        }
    
    @staticmethod
    def internal_error(message: str = "Internal Server Error") -> Dict[str, Any]:
        return {
            'error': 'Internal Server Error',
            'message': message,
            'status_code': 500,
            'timestamp': datetime.now().isoformat()
        }
