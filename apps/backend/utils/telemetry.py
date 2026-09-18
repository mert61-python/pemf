# Author: mertaygn, cglrgrkn
"""Opsiyonel uzaktan hata-izleme/telemetri (audit B-5.1).

VARSAYILAN KAPALI — KVKK: hata verisi buluta OTOMATİK gitmez. Yalnız operatör `PEMF_SENTRY_DSN`
ayarlarsa VE sentry-sdk kuruluysa aktifleşir. PII-scrub açık (request/user bloğu ve stack-locals
gönderilmez); yalnız hata olayları (performans-izleme kapalı). Sentry-sdk yoksa/DSN boşsa NO-OP.

Aktifleştirme (opt-in):
    setx PEMF_SENTRY_DSN "https://<key>@<host>/<project>"   (self-hosted Sentry önerilir; KVKK)
Kapatma: değişkeni kaldır (varsayılan).
"""

import logging
import os

logger = logging.getLogger(__name__)

_initialized = False


def _scrub_event(event, hint):
    """KVKK: olası PII taşıyan blokları at. Audit P3: eskiden yalnız request/user/frame-vars atılıyordu;
    breadcrumbs (LoggingIntegration log satırları), extra, logentry/message ve exception.value de PII
    taşıyabilir → onları da temizle."""
    try:
        for k in ("request", "user", "breadcrumbs", "extra"):
            event.pop(k, None)
        # logentry.message + üst-düzey message maskele (hasta adı/telefonu log satırında olabilir)
        if event.get("logentry"):
            event["logentry"] = {"message": "[scrubbed]"}
        if "message" in event:
            event["message"] = "[scrubbed]"
        # istisna değeri (mesajı) + stack-frame local'leri hasta verisi taşıyabilir → temizle
        for exc in (event.get("exception", {}) or {}).get("values", []) or []:
            if "value" in exc:
                exc["value"] = "[scrubbed]"
            for frame in (exc.get("stacktrace", {}) or {}).get("frames", []) or []:
                frame.pop("vars", None)
    except Exception:
        pass
    return event


def init_telemetry() -> bool:
    """PEMF_SENTRY_DSN + sentry-sdk varsa Sentry'yi başlat (PII-scrub, hata-only). Dönüş: aktif mi."""
    global _initialized
    if _initialized:
        return True
    dsn = os.environ.get("PEMF_SENTRY_DSN", "").strip()
    if not dsn:
        return False  # opt-in değil → sessiz no-op (varsayılan)
    try:
        import sentry_sdk
    except Exception:
        logger.warning("PEMF_SENTRY_DSN ayarlı ama sentry-sdk kurulu değil → telemetri KAPALI.")
        return False
    try:
        sentry_sdk.init(
            dsn=dsn,
            traces_sample_rate=0.0,  # yalnız hata; performans izleme yok
            send_default_pii=False,  # KVKK
            before_send=_scrub_event,
            before_breadcrumb=lambda _crumb, _hint: (
                None
            ),  # Audit P3: breadcrumb'ları TAMAMEN düşür (log-PII buluta gitmesin)
            environment=os.environ.get("PEMF_DEVICE_NAME", "pemf-device"),
            release=(os.environ.get("PEMF_VERSION", "").strip() or None),
        )
        _initialized = True
        logger.info("Sentry telemetri AKTİF (hata-only, PII-scrub).")
        return True
    except Exception:
        logger.exception("Sentry init başarısız (non-fatal) → telemetri kapalı.")
        return False
