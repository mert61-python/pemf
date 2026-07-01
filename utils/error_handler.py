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


class ErrorHandler:
    """Comprehensive error handling system"""
    
    def __init__(self):
        self.error_counts = {}
        self.error_history = []
        
        # Standart Python logger'ları (logger_config tarafından yapılandırılır)
        self.app_logger = logging.getLogger('pemf_app')
        self.security_logger = logging.getLogger('pemf_security')
        self.error_logger = logging.getLogger('pemf_errors')
        self.performance_logger = logging.getLogger('pemf_performance')
        self.websocket_logger = logging.getLogger('pemf_websocket')
        
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
        self.error_logger.error(
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
            self.security_logger.critical(log_message)
        elif severity == "ERROR":
            self.security_logger.error(log_message)
        else:
            self.security_logger.warning(log_message)
    
    def log_performance_metric(self, operation: str, duration: float, details: Dict[str, Any] = None):
        """Log performance metrics"""
        perf_info = {
            'operation': operation,
            'duration_ms': round(duration * 1000, 2),
            'details': details or {},
            'timestamp': datetime.now().isoformat()
        }
        
        self.performance_logger.info(
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

def get_error_handler() -> ErrorHandler:
    """Get global error handler instance"""
    global _error_handler
    if _error_handler is None:
        _error_handler = ErrorHandler()
    return _error_handler

def get_logger() -> logging.Logger:
    """
    Get standard global logger instance.
    (Backwards compatible with old PEMFLogger calls that expected a .error() method)
    """
    return logging.getLogger('pemf_app')
