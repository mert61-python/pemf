"""
PEMF Auto-Discovery Service
============================
İki katmanlı otomatik bağlantı sistemi:

1. mDNS (Bonjour/Zeroconf): Aynı Wi-Fi ağındaki telefonlar LattePanda'yı
   otomatik bulur. Hiçbir konfigürasyon gerekmez.

2. QR Kod: Farklı ağdayken, tünel URL'si hazır olunca LattePanda ekranında
   (veya PyQt penceresinde) QR kod gösterilir. Telefon kamerasıyla bir kez
   tarar, adres otomatik kaydedilir.

Kullanım:
    from servers.auto_discovery import start_mdns, stop_mdns, generate_qr_pixmap
    start_mdns(port=8000)
    pixmap = generate_qr_pixmap("https://xxxx.trycloudflare.com")
"""
from __future__ import annotations

import io
import logging
import socket
import threading
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# ── mDNS (Zeroconf) Servisi ────────────────────────────────────────────────────
_zeroconf_instance = None
_mdns_service_info = None


def _get_local_ip() -> str:
    """Makinenin yerel ağ IP adresini tespit eder."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def start_mdns(port: int = 8000, device_name: str = "PEMF-Vet") -> bool:
    """
    mDNS servisi başlatır. Aynı ağdaki telefonlar bu servis üzerinden
    LattePanda'yı otomatik keşfedebilir.
    Servis tipi: _pemfvet._tcp.local.
    """
    global _zeroconf_instance, _mdns_service_info
    try:
        from zeroconf import Zeroconf, ServiceInfo
        import socket as _socket

        local_ip = _get_local_ip()
        ip_bytes = _socket.inet_aton(local_ip)

        info = ServiceInfo(
            type_="_pemfvet._tcp.local.",
            name=f"{device_name}._pemfvet._tcp.local.",
            addresses=[ip_bytes],
            port=port,
            properties={
                b"version": b"1.5",
                b"api": b"/api",
                b"ws": b"/ws",
            },
            server=f"{device_name}.local.",
        )

        zc = Zeroconf()
        zc.register_service(info)
        _zeroconf_instance = zc
        _mdns_service_info = info

        logger.info("mDNS servisi başlatıldı: %s:%d (%s)", local_ip, port, device_name)
        return True
    except Exception as e:
        logger.warning("mDNS başlatılamadı: %s", e)
        return False


def stop_mdns() -> None:
    """mDNS servisini durdurur."""
    global _zeroconf_instance, _mdns_service_info
    if _zeroconf_instance and _mdns_service_info:
        try:
            _zeroconf_instance.unregister_service(_mdns_service_info)
            _zeroconf_instance.close()
        except Exception:
            pass
    _zeroconf_instance = None
    _mdns_service_info = None
    logger.info("mDNS servisi durduruldu.")


# ── QR Kod Üreteci ──────────────────────────────────────────────────────────────

def generate_qr_image_bytes(url: str) -> bytes | None:
    """
    Verilen URL için QR kod PNG bytes'ı döndürür.
    Pillow ile PNG, QR ile kod üretilir.
    """
    try:
        import qrcode
        from PIL import Image

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=3,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        logger.error("QR kod üretilemedi: %s", e)
        return None


def generate_qr_pixmap(url: str):
    """
    PyQt6 QPixmap döndürür (QLabel'da göstermek için).
    PyQt6 olmayan ortamlarda None döner.
    """
    try:
        from PyQt6.QtGui import QPixmap
        from PyQt6.QtCore import QByteArray

        png_bytes = generate_qr_image_bytes(url)
        if not png_bytes:
            return None

        ba = QByteArray(png_bytes)
        pixmap = QPixmap()
        pixmap.loadFromData(ba, "PNG")
        return pixmap
    except Exception as e:
        logger.error("QR Pixmap oluşturulamadı: %s", e)
        return None


def save_qr_to_file(url: str, path: Path | str) -> bool:
    """QR kodu dosyaya kaydeder (PNG)."""
    try:
        png_bytes = generate_qr_image_bytes(url)
        if png_bytes:
            Path(path).write_bytes(png_bytes)
            return True
    except Exception as e:
        logger.error("QR dosyaya kaydedilemedi: %s", e)
    return False


# ── FastAPI endpoint: /api/qr ──────────────────────────────────────────────────
# Bu fonksiyon api_server.py tarafından import edilerek endpoint olarak eklenir.

def get_qr_png_response(url: str):
    """
    FastAPI Response döndürür: GET /api/qr → PNG QR kodu.
    Mobil uygulama bu endpoint'i çağırarak QR kodu yükler (opsiyonel).
    """
    try:
        from fastapi.responses import Response
        png_bytes = generate_qr_image_bytes(url)
        if png_bytes:
            return Response(content=png_bytes, media_type="image/png")
    except Exception:
        pass
    return None
