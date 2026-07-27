"""
PEMF Auto-Discovery Service
============================
mDNS (Bonjour/Zeroconf): Aynı Wi-Fi ağındaki telefonlar LattePanda'yı otomatik
bulur, hiçbir konfigürasyon gerekmez. (Farklı ağdan erişim: Cloudflare tüneli +
Supabase cihaz-kaydı; QR kod KALDIRILDI — React arayüzü kullanılıyor.)

Kullanım:
    from servers.auto_discovery import start_mdns, stop_mdns
    start_mdns(port=8000)
"""
from __future__ import annotations

import logging
import socket

logger = logging.getLogger(__name__)

# ── mDNS (Zeroconf) Servisi ────────────────────────────────────────────────────
_zeroconf_instance = None
_mdns_service_info = None
_mdns_port = 8000
_mdns_device_name = "PEMF-Vet"


def _build_info(local_ip: str, port: int, device_name: str):
    """_pemfvet ServiceInfo'yu güncel IP ile kurar (start_mdns + re-register ortak kullanır)."""
    import socket as _socket

    from zeroconf import ServiceInfo
    return ServiceInfo(
        type_="_pemfvet._tcp.local.",
        name=f"{device_name}._pemfvet._tcp.local.",
        addresses=[_socket.inet_aton(local_ip)],
        port=port,
        properties={b"version": b"1.5", b"api": b"/api", b"ws": b"/ws"},
        server=f"{device_name}.local.",
    )


def _reregister() -> None:
    """Zeroconf arayüz/IP değişimiyle YENİDEN yaratıldığında _pemfvet servisini yeni instance'a
    GÜNCEL IP ile re-register eder (zeroconf_singleton.ensure_interfaces_current çağırır). Bu ayrıca
    auto_discovery'nin eskiden HİÇ olmayan IP-değişim yeniden-kaydını da kapatır. start_mdns
    çağrılmadıysa no-op."""
    global _zeroconf_instance, _mdns_service_info
    if _mdns_service_info is None:
        return
    try:
        from utils.zeroconf_singleton import get_shared_zeroconf
        ip = _get_local_ip()
        # Audit P3: loopback (127.*) ServiceInfo YAYINLAMA — telefon/ESP 127.0.0.1'i çözüp kendi
        # loopback'ine gider (sessiz başarısız). Gerçek LAN IP yoksa kaydı ATLA (sonraki tur tekrar dener).
        if not ip or ip.startswith("127."):
            logger.debug("mDNS re-register atlandı: geçerli LAN IP yok (ip=%r).", ip)
            return
        info = _build_info(ip, _mdns_port, _mdns_device_name)
        zc = get_shared_zeroconf()
        zc.register_service(info)
        _zeroconf_instance = zc
        _mdns_service_info = info
        logger.info("mDNS (_pemfvet) yeni arayüzlere re-register edildi: %s", ip)
    except Exception as e:
        logger.warning("_pemfvet re-register hatası: %s", e)


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
    global _zeroconf_instance, _mdns_service_info, _mdns_port, _mdns_device_name
    try:
        from utils.zeroconf_singleton import add_reregister_callback, get_shared_zeroconf

        _mdns_port, _mdns_device_name = port, device_name
        local_ip = _get_local_ip()
        info = _build_info(local_ip, port, device_name)

        zc = get_shared_zeroconf()  # paylasilan TEK Zeroconf (MDNSService ile ayni instance → 5343 cakismasi yok)
        zc.register_service(info)
        _zeroconf_instance = zc
        _mdns_service_info = info
        add_reregister_callback(_reregister)  # arayüz/IP değişiminde yeni instance'a otomatik re-register

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
            _zeroconf_instance.unregister_service(_mdns_service_info)  # ortak Zeroconf'u CLOSE ETME (MDNSService da kullanir)
        except Exception:
            pass
    _zeroconf_instance = None
    _mdns_service_info = None
    logger.info("mDNS servisi durduruldu.")
