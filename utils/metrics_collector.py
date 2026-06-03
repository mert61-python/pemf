# -*- coding: utf-8 -*-
"""
Metrics Collection System for PEMF GUI Application
Collects performance metrics and statistics without heavy logging.

@author: merta
@date: 2025-12-01
"""

import time
import threading
from collections import defaultdict, deque
from typing import Dict,Optional, Tuple
from dataclasses import dataclass, field



@dataclass
class MetricStats:
    """Statistics for a single metric"""
    count: int = 0
    total: float = 0.0
    min_value: float = float('inf')
    max_value: float = float('-inf')
    last_value: float = 0.0
    last_timestamp: float = 0.0
    
    def update(self, value: float, timestamp: Optional[float] = None):
        """Update metric with new value"""
        # None value kontrolü
        if value is None:
            return
        
        self.count += 1
        self.total += value
        self.min_value = min(self.min_value, value)
        self.max_value = max(self.max_value, value)
        self.last_value = value
        self.last_timestamp = timestamp or time.time()
    
    @property
    def average(self) -> float:
        """Calculate average value"""
        return self.total / self.count if self.count > 0 else 0.0
    
    def reset(self):
        """Reset statistics"""
        self.count = 0
        self.total = 0.0
        self.min_value = float('inf')
        self.max_value = float('-inf')
        self.last_value = 0.0
        self.last_timestamp = 0.0


@dataclass
class TimingMetric:
    """Timing metric for measuring durations"""
    name: str
    samples: deque = field(default_factory=lambda: deque(maxlen=100))  # Keep last 100 samples
    total_time: float = 0.0
    count: int = 0
    
    def add_sample(self, duration: float):
        """Add timing sample"""
        self.samples.append(duration)
        self.total_time += duration
        self.count += 1
    
    @property
    def average(self) -> float:
        """Average duration"""
        return self.total_time / self.count if self.count > 0 else 0.0
    
    @property
    def recent_average(self) -> float:
        """Average of recent samples"""
        return sum(self.samples) / len(self.samples) if self.samples else 0.0
    
    @property
    def min(self) -> float:
        """Minimum duration"""
        return min(self.samples) if self.samples else 0.0
    
    @property
    def max(self) -> float:
        """Maximum duration"""
        return max(self.samples) if self.samples else 0.0


class MetricsCollector:
    """
    Performance metrics collector for PEMF GUI.
    
    Features:
    - Counter metrics (incremental values)
    - Gauge metrics (current values)
    - Timing metrics (duration measurements)
    - Thread-safe operations
    - Low overhead
    
    Usage:
        metrics = get_metrics_collector()
        
        # Counter
        metrics.increment('mqtt_messages_received')
        
        # Gauge
        metrics.set_gauge('active_coils', 8)
        
        # Timing
        with metrics.timer('graph_update'):
            update_graph()
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return
        
        self._initialized = True
        self._lock = threading.Lock()
        
        # Metrics storage
        self.counters: Dict[str, int] = defaultdict(int)
        self.gauges: Dict[str, MetricStats] = defaultdict(MetricStats)
        self.timings: Dict[str, TimingMetric] = {}
        
        # Error tracking
        self.error_counts: Dict[str, int] = defaultdict(int)
        self.last_errors: Dict[str, Tuple[str, float]] = {}  # error_type -> (message, timestamp)
        
        # Performance tracking
        self.start_time = time.time()
    
    def increment(self, name: str, value: int = 1):
        """Increment counter metric"""
        with self._lock:
            self.counters[name] += value
    
    def decrement(self, name: str, value: int = 1):
        """Decrement counter metric"""
        with self._lock:
            self.counters[name] -= value
    
    def set_gauge(self, name: str, value: float):
        """Set gauge metric value"""
        # None value kontrolü
        if value is None:
            return
        
        with self._lock:
            self.gauges[name].update(value)
    
    def record_timing(self, name: str, duration: float):
        """Record timing metric"""
        with self._lock:
            if name not in self.timings:
                self.timings[name] = TimingMetric(name)
            self.timings[name].add_sample(duration)
    
    def record_error(self, error_type: str, message: str):
        """Record error occurrence"""
        with self._lock:
            self.error_counts[error_type] += 1
            self.last_errors[error_type] = (message, time.time())
    
    def timer(self, name: str):
        """Context manager for timing operations"""
        return TimerContext(self, name)
    
    def get_counter(self, name: str) -> int:
        """Get counter value"""
        with self._lock:
            return self.counters.get(name, 0)
    
    def get_gauge(self, name: str) -> Optional[MetricStats]:
        """Get gauge statistics"""
        with self._lock:
            return self.gauges.get(name)
    
    def get_timing(self, name: str) -> Optional[TimingMetric]:
        """Get timing statistics"""
        with self._lock:
            return self.timings.get(name)
    
    def get_all_counters(self) -> Dict[str, int]:
        """Get all counter values"""
        with self._lock:
            return dict(self.counters)
    
    def get_all_gauges(self) -> Dict[str, MetricStats]:
        """Get all gauge statistics"""
        with self._lock:
            return dict(self.gauges)
    
    def get_all_timings(self) -> Dict[str, TimingMetric]:
        """Get all timing statistics"""
        with self._lock:
            return dict(self.timings)
    
    def get_error_summary(self) -> Dict[str, Tuple[int, str, float]]:
        """Get error summary (count, last_message, last_timestamp)"""
        with self._lock:
            summary = {}
            for error_type, count in self.error_counts.items():
                last_msg, last_ts = self.last_errors.get(error_type, ("", 0))
                summary[error_type] = (count, last_msg, last_ts)
            return summary
    
    def reset_counter(self, name: str):
        """Reset specific counter"""
        with self._lock:
            self.counters[name] = 0
    
    def reset_all_counters(self):
        """Reset all counters"""
        with self._lock:
            self.counters.clear()
    
    def reset_gauge(self, name: str):
        """Reset specific gauge"""
        with self._lock:
            if name in self.gauges:
                self.gauges[name].reset()
    
    def reset_all_gauges(self):
        """Reset all gauges"""
        with self._lock:
            for gauge in self.gauges.values():
                gauge.reset()
    
    def get_uptime(self) -> float:
        """Get system uptime in seconds"""
        return time.time() - self.start_time
    
    def get_summary(self) -> str:
        """Get formatted metrics summary"""
        with self._lock:
            lines = []
            lines.append("=" * 60)
            lines.append("PEMF GUI Metrics Summary")
            lines.append(f"Uptime: {self.get_uptime():.2f} seconds")
            lines.append("=" * 60)
            
            # Counters
            if self.counters:
                lines.append("\n📊 Counters:")
                for name, value in sorted(self.counters.items()):
                    lines.append(f"  • {name}: {value}")
            
            # Gauges
            if self.gauges:
                lines.append("\n📈 Gauges:")
                for name, stats in sorted(self.gauges.items()):
                    lines.append(f"  • {name}:")
                    lines.append(f"      Count: {stats.count}")
                    lines.append(f"      Average: {stats.average:.2f}")
                    lines.append(f"      Min: {stats.min_value:.2f}")
                    lines.append(f"      Max: {stats.max_value:.2f}")
                    lines.append(f"      Last: {stats.last_value:.2f}")
            
            # Timings
            if self.timings:
                lines.append("\n⏱️  Timings:")
                for name, timing in sorted(self.timings.items()):
                    lines.append(f"  • {name}:")
                    lines.append(f"      Count: {timing.count}")
                    lines.append(f"      Average: {timing.average*1000:.2f}ms")
                    lines.append(f"      Recent: {timing.recent_average*1000:.2f}ms")
                    lines.append(f"      Min: {timing.min*1000:.2f}ms")
                    lines.append(f"      Max: {timing.max*1000:.2f}ms")
            
            # Errors
            error_summary = self.get_error_summary()
            if error_summary:
                lines.append("\n❌ Errors:")
                for error_type, (count, last_msg, last_ts) in sorted(error_summary.items()):
                    time_ago = time.time() - last_ts if last_ts > 0 else 0
                    lines.append(f"  • {error_type}: {count} occurrences")
                    if last_msg:
                        lines.append(f"      Last: {last_msg} ({time_ago:.1f}s ago)")
            
            lines.append("=" * 60)
            return "\n".join(lines)
    
    def export_to_dict(self) -> dict:
        """Export metrics to dictionary for JSON serialization"""
        with self._lock:
            return {
                'uptime': self.get_uptime(),
                'timestamp': time.time(),
                'counters': dict(self.counters),
                'gauges': {
                    name: {
                        'count': stats.count,
                        'average': stats.average,
                        'min': stats.min_value if stats.min_value != float('inf') else 0,
                        'max': stats.max_value if stats.max_value != float('-inf') else 0,
                        'last': stats.last_value
                    }
                    for name, stats in self.gauges.items()
                },
                'timings': {
                    name: {
                        'count': timing.count,
                        'average_ms': timing.average * 1000,
                        'recent_average_ms': timing.recent_average * 1000,
                        'min_ms': timing.min * 1000,
                        'max_ms': timing.max * 1000
                    }
                    for name, timing in self.timings.items()
                },
                'errors': self.get_error_summary()
            }


class TimerContext:
    """Context manager for timing operations"""
    
    def __init__(self, collector: MetricsCollector, name: str):
        self.collector = collector
        self.name = name
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        self.collector.record_timing(self.name, duration)
        return False


# Singleton instance
_metrics_collector = None
_collector_lock = threading.Lock()


def get_metrics_collector() -> MetricsCollector:
    """Get singleton metrics collector instance"""
    global _metrics_collector
    if _metrics_collector is None:
        with _collector_lock:
            if _metrics_collector is None:
                _metrics_collector = MetricsCollector()
    return _metrics_collector


# Convenience functions
def increment_counter(name: str, value: int = 1):
    """Increment counter metric"""
    get_metrics_collector().increment(name, value)


def set_gauge(name: str, value: float):
    """Set gauge metric"""
    get_metrics_collector().set_gauge(name, value)


def record_timing(name: str, duration: float):
    """Record timing metric"""
    get_metrics_collector().record_timing(name, duration)


def record_error(error_type: str, message: str):
    """Record error occurrence"""
    get_metrics_collector().record_error(error_type, message)


def timer(name: str):
    """Context manager for timing"""
    return get_metrics_collector().timer(name)
