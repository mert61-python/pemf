# Author: mertaygn, cglrgrkn
"""Small Qt-free signal helper for headless services."""

from __future__ import annotations

import logging
import threading
from typing import Callable, List


class SimpleSignal:
    """Minimal signal object with a PyQt-like connect/disconnect/emit API."""

    def __init__(self) -> None:
        self._callbacks: List[Callable] = []
        self._lock = threading.RLock()
        self._logger = logging.getLogger(__name__)

    def connect(self, callback: Callable) -> None:
        if not callable(callback):
            raise TypeError("Signal callback must be callable")
        with self._lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)

    def disconnect(self, callback: Callable | None = None) -> None:
        with self._lock:
            if callback is None:
                self._callbacks.clear()
                return
            try:
                self._callbacks.remove(callback)
            except ValueError:
                pass

    def emit(self, *args, **kwargs) -> None:
        with self._lock:
            callbacks = list(self._callbacks)
        for callback in callbacks:
            try:
                callback(*args, **kwargs)
            except Exception:
                self._logger.exception("Signal callback failed")
