# Author: mertaygn, cglrgrkn
"""Request-correlation-id bağlamı (audit O-1).

Nötr modül: hem `servers.api_server` (middleware, id'yi SET eder + yanıt header'ına echo'lar)
hem `backend_service` (JSON log formatter, id'yi log satırına EKLER) buradan import eder →
circular-import olmaz. Değer request başına ayarlanır; arka-plan thread'lerinde varsayılan "-".
"""

import contextvars

# Aktif isteğin korelasyon id'si (X-Request-ID). İstek dışı/arka-plan → "-".
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def get_request_id() -> str:
    return request_id_var.get()
