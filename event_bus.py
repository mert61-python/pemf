# -*- coding: utf-8 -*-
"""
EventBus - Mediator Pattern Implementation
PEMF Medical System için merkezi event yönetim sistemi

Bu modül, sistem bileşenleri arasında gevşek bağlılık sağlar ve
event-driven architecture implementasyonu sunar.

@author: merta
"""

import logging
import asyncio
import threading
import time
import weakref
from weakref import WeakMethod, ref as weakref_ref
from typing import Dict, List, Callable, Any, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class EventPriority(Enum):
    """Event öncelik seviyeleri"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class Event:
    """Event veri yapısı"""
    event_type: str
    data: Any
    timestamp: datetime = field(default_factory=datetime.now)
    priority: EventPriority = EventPriority.NORMAL
    source: Optional[str] = None
    correlation_id: Optional[str] = None


@dataclass
class Subscription:
    """Event subscription bilgisi (weakref support)"""
    callback_ref: Any  # weakref.ref or WeakMethod
    event_type: str
    subscriber_id: str
    is_async: bool = False
    priority: EventPriority = EventPriority.NORMAL
    filter_func: Optional[Callable[[Event], bool]] = None
    is_qt_callback: bool = False
    
    def get_callback(self) -> Optional[Callable]:
        """Get actual callback from weakref (None if dead)"""
        if self.callback_ref is None:
            return None
        callback = self.callback_ref()
        return callback if callback is not None else None


class EventBus:
    """
    Merkezi Event Bus - Mediator Pattern implementasyonu
    
    Sistem bileşenleri arasında gevşek bağlılık sağlar ve
    event-driven communication'ı mümkün kılar.
    """
    
    def __init__(self, max_workers: int = 4):
        """
        EventBus'ı başlatır.
        
        Args:
            max_workers: Async event işleme için maksimum worker sayısı
        """
        self._subscribers: Dict[str, List[Subscription]] = defaultdict(list)
        self._event_history: List[Event] = []
        self._max_history_size = 100  # Memory leak fix: 1000 -> 100
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._running = True
        self._stats = {
            'events_published': 0,
            'events_processed': 0,
            'failed_deliveries': 0
        }
        
        # Memory leak fix: Track async tasks
        self._pending_tasks = set()
        self._task_lock = threading.Lock()
        
        # Memory leak fix: Periodic cleanup timer
        self._cleanup_interval = 60  # seconds
        self._last_cleanup = time.time()
        
        # Qt desteği için (PyQt6 only)
        self._qt_app = None
        self._qt_main_thread = None
        try:
            from PyQt6.QtWidgets import QApplication
            from PyQt6.QtCore import QThread
            self._qt_app = QApplication.instance()
            if self._qt_app:
                self._qt_main_thread = QThread.currentThread()
        except ImportError:
            # PyQt6 yoksa Qt desteği devre dışı
            logger.debug("PyQt6 not available, Qt callbacks will be disabled")
            pass
        
        logger.info("EventBus initialized with memory leak fixes")
    
    def subscribe(self, 
                  event_type: str, 
                  callback: Callable,
                  subscriber_id: str,
                  priority: EventPriority = EventPriority.NORMAL,
                  filter_func: Optional[Callable[[Event], bool]] = None,
                  is_qt_callback: bool = False) -> bool:
        """
        Event'e abone ol.
        
        Args:
            event_type: Dinlenecek event tipi (wildcard destekli: "esp.*")
            callback: Event geldiğinde çağrılacak fonksiyon
            subscriber_id: Abone kimliği (unsubscribe için gerekli)
            priority: Callback önceliği
            filter_func: Event filtreleme fonksiyonu (opsiyonel)
            
        Returns:
            bool: Subscription başarılı ise True
        """
        try:
            with self._lock:
                # Async callback kontrolü
                is_async = asyncio.iscoroutinefunction(callback)
                
                # CRITICAL FIX: Use weakref to prevent memory leaks
                # For bound methods, use WeakMethod; for functions, use weakref_ref
                if hasattr(callback, '__self__'):
                    # Bound method
                    callback_ref = WeakMethod(callback)
                else:
                    # Function or lambda
                    callback_ref = weakref_ref(callback)
                
                subscription = Subscription(
                    callback_ref=callback_ref,
                    event_type=event_type,
                    subscriber_id=subscriber_id,
                    is_async=is_async,
                    priority=priority,
                    filter_func=filter_func,
                    is_qt_callback=is_qt_callback
                )
                
                self._subscribers[event_type].append(subscription)
                
                # Önceliğe göre sırala
                self._subscribers[event_type].sort(
                    key=lambda s: s.priority.value, 
                    reverse=True
                )
                
                logger.debug(f"Subscription added: {subscriber_id} -> {event_type}")
                return True
                
        except Exception as e:
            logger.error(f"Subscription failed: {e}")
            return False
    
    def unsubscribe(self, event_type: str, subscriber_id: str) -> bool:
        """
        Event aboneliğini iptal et.
        
        Args:
            event_type: Event tipi
            subscriber_id: Abone kimliği
            
        Returns:
            bool: Unsubscribe başarılı ise True
        """
        try:
            with self._lock:
                if event_type in self._subscribers:
                    self._subscribers[event_type] = [
                        sub for sub in self._subscribers[event_type]
                        if sub.subscriber_id != subscriber_id
                    ]
                    
                    # Boş liste ise sil
                    if not self._subscribers[event_type]:
                        del self._subscribers[event_type]
                    
                    logger.debug(f"Unsubscribed: {subscriber_id} from {event_type}")
                    return True
                return False
                
        except Exception as e:
            logger.error(f"Unsubscribe failed: {e}")
            return False
    
    def publish(self, 
                event_type: str, 
                data: Any,
                priority: EventPriority = EventPriority.NORMAL,
                source: Optional[str] = None,
                correlation_id: Optional[str] = None) -> bool:
        """
        Event yayınla.
        
        Args:
            event_type: Event tipi
            data: Event verisi
            priority: Event önceliği
            source: Event kaynağı
            correlation_id: İlişkili event'ler için ID
            
        Returns:
            bool: Publish başarılı ise True
        """
        if not self._running:
            return False
            
        try:
            event = Event(
                event_type=event_type,
                data=data,
                priority=priority,
                source=source,
                correlation_id=correlation_id
            )
            
            with self._lock:
                self._stats['events_published'] += 1
                
                # Event history'ye ekle
                self._add_to_history(event)
                
                # Matching subscribers'ı bul
                matching_subscribers = self._find_matching_subscribers(event_type)
                
            # Subscribers'ı bilgilendir (lock dışında)
            self._notify_subscribers(event, matching_subscribers)
            
            logger.debug(f"Event published: {event_type} to {len(matching_subscribers)} subscribers")
            return True
            
        except Exception as e:
            logger.error(f"Event publish failed: {e}")
            return False
    
    async def publish_async(self, 
                           event_type: str, 
                           data: Any,
                           priority: EventPriority = EventPriority.NORMAL,
                           source: Optional[str] = None,
                           correlation_id: Optional[str] = None) -> bool:
        """
        Async event yayınla.
        
        Returns:
            bool: Publish başarılı ise True
        """
        try:
            # Modern asyncio API kullan (Python 3.7+)
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Event loop yoksa yeni oluştur veya mevcut olanı al
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                # Hiç event loop yoksa oluştur
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        
        return await loop.run_in_executor(
            self._executor,
            self.publish, event_type, data, priority, source, correlation_id
        )
    
    def _find_matching_subscribers(self, event_type: str) -> List[Subscription]:
        """Event type'a matching olan subscribers'ı bul (wildcard destekli)"""
        matching = []
        
        for subscribed_type, subscribers in self._subscribers.items():
            if self._event_matches(event_type, subscribed_type):
                matching.extend(subscribers)
        
        return matching
    
    def _event_matches(self, event_type: str, subscribed_type: str) -> bool:
        """Event type matching (wildcard destekli)"""
        if subscribed_type == "*":  # Tüm event'ler
            return True
        
        if subscribed_type.endswith("*"):  # Prefix matching
            prefix = subscribed_type[:-1]
            return event_type.startswith(prefix)
        
        return event_type == subscribed_type
    
    def _notify_subscribers(self, event: Event, subscribers: List[Subscription]):
        """Subscribers'ı bilgilendir (Memory leak fix: weakref + task tracking)"""
        for subscription in subscribers:
            try:
                # CRITICAL FIX: Get callback from weakref (skip if dead)
                callback = subscription.get_callback()
                if callback is None:
                    # Callback is dead (garbage collected), skip
                    continue
                
                # Filter kontrolü
                if subscription.filter_func and not subscription.filter_func(event):
                    continue
                
                if subscription.is_qt_callback and self._qt_app:
                    # Qt callback - main thread'de çalıştır
                    self._call_qt_callback(subscription, event)
                elif subscription.is_async:
                    # Async callback with task tracking and event loop check
                    try:
                        # Event loop var mı kontrol et
                        loop = asyncio.get_running_loop()
                        # Event loop varsa task oluştur
                        task = loop.create_task(self._call_async_callback(subscription, event))
                        with self._task_lock:
                            self._pending_tasks.add(task)
                        task.add_done_callback(lambda t: self._remove_task(t))
                    except RuntimeError:
                        # Event loop yoksa executor'da çalıştır
                        logger.warning("No event loop available for async callback, using executor")
                        future = self._executor.submit(
                            self._run_async_in_executor, 
                            subscription, 
                            event
                        )
                else:
                    # Sync callback
                    future = self._executor.submit(self._call_sync_callback, subscription, event)
                    # Future'lar otomatik cleanup yapılır, tracking gerekmez
                    
            except Exception as e:
                logger.error(f"Subscriber notification failed: {e}")
                self._stats['failed_deliveries'] += 1
    
    def _run_async_in_executor(self, subscription: Subscription, event: Event):
        """Async callback'i executor'da çalıştır (event loop yoksa)"""
        try:
            # Yeni event loop oluştur ve çalıştır
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._call_async_callback(subscription, event))
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Async callback execution in executor failed: {e}")
            self._stats['failed_deliveries'] += 1
    
    def _remove_task(self, task):
        """Completed task'ı pending_tasks'tan kaldır (Memory leak fix)"""
        with self._task_lock:
            self._pending_tasks.discard(task)
    
    async def _call_async_callback(self, subscription: Subscription, event: Event):
        """Async callback çağır (weakref safe)"""
        try:
            callback = subscription.get_callback()
            if callback is None:
                logger.debug("Async callback is dead (weakref), skipping")
                return
            await callback(event)
            self._stats['events_processed'] += 1
        except asyncio.CancelledError:
            # Task iptal edildi, normal durum
            logger.debug("Async callback task cancelled")
            raise  # Re-raise to properly handle cancellation
        except Exception as e:
            logger.error(f"Async callback failed: {e}")
            self._stats['failed_deliveries'] += 1
    
    def _call_sync_callback(self, subscription: Subscription, event: Event):
        """Sync callback çağır (weakref safe)"""
        try:
            callback = subscription.get_callback()
            if callback is None:
                logger.debug("Sync callback is dead (weakref), skipping")
                return
            callback(event)
            self._stats['events_processed'] += 1
        except Exception as e:
            logger.error(f"Sync callback failed: {e}")
            self._stats['failed_deliveries'] += 1
    
    def _call_qt_callback(self, subscription: Subscription, event: Event):
        """Qt callback çağır - main thread'de (PyQt6 only, weakref safe)"""
        try:
            # CRITICAL FIX: Get callback from weakref
            callback = subscription.get_callback()
            if callback is None:
                logger.debug("Qt callback is dead (weakref), skipping")
                return
            
            # Qt callback'leri main thread'de çalıştır
            if self._qt_app and self._qt_main_thread:
                from PyQt6.QtCore import QThread, QTimer
                current_thread = QThread.currentThread()
                
                if current_thread == self._qt_main_thread:
                    # Zaten main thread'deyiz, direkt çağır
                    callback(event)
                    self._stats['events_processed'] += 1
                else:
                    # Main thread'de değiliz, QTimer.singleShot ile queue'ya ekle
                    # Bu Qt'nin thread-safe event posting mekanizmasıdır
                    def execute_callback():
                        try:
                            cb = subscription.get_callback()
                            if cb is not None:
                                cb(event)
                                self._stats['events_processed'] += 1
                        except Exception as e:
                            logger.error(f"Qt callback execution failed: {e}")
                            self._stats['failed_deliveries'] += 1
                    
                    # QTimer.singleShot ile main thread'de çalıştır
                    QTimer.singleShot(0, execute_callback)
            else:
                # Qt app yok, normal callback olarak çalıştır
                callback(event)
                self._stats['events_processed'] += 1
            
        except ImportError:
            # PyQt6 yok, normal callback olarak çalıştır
            logger.warning("PyQt6 not available, executing Qt callback as normal callback")
            try:
                subscription.callback(event)
                self._stats['events_processed'] += 1
            except Exception as e:
                logger.error(f"Callback execution failed: {e}")
                self._stats['failed_deliveries'] += 1
        except Exception as e:
            logger.error(f"Qt callback failed: {e}")
            self._stats['failed_deliveries'] += 1
    
    def _add_to_history(self, event: Event):
        """Event'i history'ye ekle (Memory leak fix: aggressive cleanup)"""
        self._event_history.append(event)
        
        # History boyutunu kontrol et (agresif cleanup)
        if len(self._event_history) > self._max_history_size:
            # Sadece son max_history_size kadar tut
            self._event_history = self._event_history[-self._max_history_size:]
        
        # Periodic cleanup check
        current_time = time.time()
        if current_time - self._last_cleanup > self._cleanup_interval:
            self._perform_cleanup()
            self._last_cleanup = current_time
    
    def _perform_cleanup(self):
        """
        Periodic cleanup: Dead subscribers ve eski event'leri temizle.
        Memory leak fix: Dead subscriber detection via weakref
        """
        dead_count = 0
        with self._lock:
            # Dead subscribers'ı temizle (weakref kontrolü)
            for event_type in list(self._subscribers.keys()):
                # Callback'i çağrılabilir olmayan subscription'ları kaldır
                valid_subs = []
                for sub in self._subscribers[event_type]:
                    try:
                        # CRITICAL FIX: Check if weakref callback is alive
                        callback = sub.get_callback()
                        if callback is not None:
                            valid_subs.append(sub)
                        else:
                            logger.debug(f"Dead subscriber removed (weakref GC'd): {sub.subscriber_id}")
                            dead_count += 1
                    except Exception as e:
                        # Callback erişilemez, kaldır
                        logger.debug(f"Inaccessible subscriber removed: {sub.subscriber_id} - {e}")
                        dead_count += 1
                
                if valid_subs:
                    self._subscribers[event_type] = valid_subs
                else:
                    # Tüm subscriber'lar dead, event type'ı kaldır
                    del self._subscribers[event_type]
            
            # Eski event'leri temizle (son 50 event dışında)
            if len(self._event_history) > 50:
                self._event_history = self._event_history[-50:]
            
            logger.debug(f"Cleanup completed: {dead_count} dead subscribers removed, {len(self._subscribers)} event types, {len(self._event_history)} events in history")
    
    def get_event_history(self, 
                         event_type: Optional[str] = None,
                         limit: int = 100) -> List[Event]:
        """
        Event history'sini al.
        
        Args:
            event_type: Belirli event type'ı filtrele (opsiyonel)
            limit: Maksimum event sayısı
            
        Returns:
            List[Event]: Event listesi
        """
        with self._lock:
            history = self._event_history.copy()
        
        if event_type:
            history = [e for e in history if self._event_matches(e.event_type, event_type)]
        
        return history[-limit:]
    
    def get_stats(self) -> Dict[str, Any]:
        """EventBus istatistiklerini al (Memory leak fix: detailed stats)"""
        with self._lock:
            with self._task_lock:
                return {
                    **self._stats,
                    'active_subscriptions': sum(len(subs) for subs in self._subscribers.values()),
                    'event_types': list(self._subscribers.keys()),
                    'history_size': len(self._event_history),
                    'pending_async_tasks': len(self._pending_tasks),
                    'last_cleanup': self._last_cleanup,
                    'cleanup_interval': self._cleanup_interval
                }
    
    def clear_history(self):
        """Event history'sini temizle"""
        with self._lock:
            self._event_history.clear()
            logger.info("Event history cleared")
    
    def shutdown(self):
        """EventBus'ı kapat (Memory leak fix: cleanup all resources)"""
        self._running = False
        
        # Pending async tasks'ları iptal et
        with self._task_lock:
            tasks_to_cancel = list(self._pending_tasks)
            self._pending_tasks.clear()
        
        # Task'ları iptal et (event loop varsa)
        for task in tasks_to_cancel:
            if not task.done():
                try:
                    task.cancel()
                    # Task'ın iptal edilmesini bekle (timeout ile)
                    try:
                        # Event loop varsa task'ı bekle
                        loop = asyncio.get_running_loop()
                        # Task'ı bekleme işlemini executor'da yap
                        self._executor.submit(lambda: None)  # Placeholder
                    except RuntimeError:
                        # Event loop yok, task zaten iptal edildi
                        pass
                except Exception as e:
                    logger.warning(f"Failed to cancel async task: {e}")
        
        # ThreadPoolExecutor'ı kapat
        try:
            self._executor.shutdown(wait=True, timeout=5)
        except Exception as e:
            logger.warning(f"Executor shutdown warning: {e}")
        
        # Tüm subscriber'ları ve history'yi temizle
        with self._lock:
            self._subscribers.clear()
            self._event_history.clear()
        
        # Qt referanslarını temizle
        self._qt_app = None
        self._qt_main_thread = None
        
        logger.info("EventBus shutdown completed with resource cleanup")


# Singleton EventBus instance
_event_bus_instance: Optional[EventBus] = None
_instance_lock = threading.Lock()


def get_event_bus() -> EventBus:
    """Singleton EventBus instance'ını al"""
    global _event_bus_instance
    
    if _event_bus_instance is None:
        with _instance_lock:
            if _event_bus_instance is None:
                _event_bus_instance = EventBus()
    
    return _event_bus_instance


# Convenience functions
def subscribe(event_type: str, callback: Callable, subscriber_id: str, **kwargs) -> bool:
    """Global subscribe function"""
    return get_event_bus().subscribe(event_type, callback, subscriber_id, **kwargs)


def unsubscribe(event_type: str, subscriber_id: str) -> bool:
    """Global unsubscribe function"""
    return get_event_bus().unsubscribe(event_type, subscriber_id)


def publish(event_type: str, data: Any, **kwargs) -> bool:
    """Global publish function"""
    return get_event_bus().publish(event_type, data, **kwargs)


async def publish_async(event_type: str, data: Any, **kwargs) -> bool:
    """Global async publish function"""
    return await get_event_bus().publish_async(event_type, data, **kwargs)


# Event type constants
class EventTypes:
    """Sistem event type'ları"""
    
    # ESP Connection Events
    ESP_CONNECTED = "esp.connected"
    ESP_DISCONNECTED = "esp.disconnected"
    ESP_HEARTBEAT = "esp.heartbeat"
    ESP_DATA_RECEIVED = "esp.data_received"
    ESP_ERROR = "esp.error"
    
    # System Events
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_ERROR = "system.error"
    
    # GUI Events
    GUI_WINDOW_OPENED = "gui.window_opened"
    GUI_WINDOW_CLOSED = "gui.window_closed"
    GUI_USER_ACTION = "gui.user_action"
    
    # Data Events
    DATA_SENSOR_UPDATE = "data.sensor_update"
    DATA_PWM_UPDATE = "data.pwm_update"
    DATA_CONFIG_CHANGED = "data.config_changed"
    
    # Configuration Events
    CONFIG_CHANGED = "config.changed"
    CONFIG_LOADED = "config.loaded"
    CONFIG_SAVED = "config.saved"
    CONFIG_RESET = "config.reset"
    
    # Wildcard patterns
    ESP_ALL = "esp.*"
    SYSTEM_ALL = "system.*"
    GUI_ALL = "gui.*"
    DATA_ALL = "data.*"
    CONFIG_ALL = "config.*"
