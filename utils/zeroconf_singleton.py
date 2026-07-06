"""Process-genelinde TEK paylaşılan Zeroconf örneği.

python-zeroconf host başına TEK instance önerir. Bu backend'de İKİ ayrı yayıncı vardı:
  - MosquittoSupervisor → MDNSService  (_mqtt._tcp, 1883)
  - api_server startup   → auto_discovery (_pemfvet._tcp, 8000)
Her biri kendi `Zeroconf()`'unu açıyordu → UDP 5353'te iki ayrı multicast soket/responder;
birinin `close()`'u diğerinin soketini bozabiliyor, kayıt (record) flapping'i / aralıklı
"cihaz bulunamadı" oluşturabiliyordu. Artık ikisi de bu paylaşılan örnek üzerinde KENDİ
ServiceInfo'sunu register/unregister eder; ortak Zeroconf yalnızca process kapanışında kapatılır.
"""
from __future__ import annotations

import threading

_lock = threading.Lock()
_zc = None


def get_shared_zeroconf():
    """Paylaşılan Zeroconf örneğini döndürür (lazy, thread-safe). Yayıncılar bunun üzerinde
    kendi register_service/unregister_service'lerini yapar; close ETMEZ."""
    global _zc
    with _lock:
        if _zc is None:
            from zeroconf import Zeroconf
            _zc = Zeroconf()
        return _zc


def close_shared_zeroconf() -> None:
    """Yalnızca process/servis kapanışında çağrılır — paylaşılan Zeroconf soketlerini kapatır."""
    global _zc
    with _lock:
        if _zc is not None:
            try:
                _zc.close()
            except Exception:
                pass
            _zc = None
