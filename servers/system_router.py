"""Sistem/durum uçları (refactor B1 Faz A: api_server.py'den ayrıldı — modüler router).

Davranış BİREBİR korunur. Paylaşılan runtime durumu (`_APP_VERSION`, `state`, `_live_state`,
`_live_state_lock`, `_build_ws_snapshot`, `_ws_broadcast_sync`) çağrı-zamanı lazy import ile
`servers.api_server`'dan okunur — böylece circular import olmaz (api_server bu router'ı include
eder; router app'i yalnız handler ÇAĞRILINCA import eder). Yollar aynen korunur.

NOT (gelecek cleanup): paylaşılan durum ileride servers/live_state.py'ye taşınmalı; şu an
davranış-koruyan ARTIMLI extraction için lazy-import deseni kullanılıyor.
"""
import logging
import time
from datetime import datetime

from fastapi import APIRouter

router = APIRouter(tags=["system"])
logger = logging.getLogger("system_router")


@router.get("/api/system/info")
async def system_info():
    """Return software/hardware version, device ID, uptime."""
    from servers import api_server as _api
    try:
        from utils.path_utils import get_unique_device_id
        device_id = get_unique_device_id()
    except Exception:
        device_id = "PEMF-001"
    # Eşleştirme kodu — FE bu cihazın kodunu kullanıcıya gösterir.
    try:
        from utils.path_utils import get_pairing_code
        pairing_code = get_pairing_code()
    except Exception:
        pairing_code = None
    try:
        from servers.tunnel_manager import get_tunnel_url
        tunnel_url = get_tunnel_url() or None
    except Exception:
        tunnel_url = None
    return {
        "softwareVersion": _api._APP_VERSION,
        "hardwareVersion": "HW-2025.1",
        "deviceId": device_id,
        "pairingCode": pairing_code,
        "tunnelUrl": tunnel_url,
        "stmConnected": _api.state.core.stm_is_connected if _api.state.core else False,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }


@router.get("/api/gateway/status")
async def gateway_status():
    """Return Mosquitto/Network/Bridge status."""
    from servers import api_server as _api
    with _api._live_state_lock:
        mqtt_state = _api._live_state.get("mqtt", "warning")
        gateway_state = _api._live_state.get("gateway", "offline")
        stm_state = _api._live_state.get("stm", "warning")
    service_status = _api.state.core.get_service_status() if _api.state.core and hasattr(_api.state.core, "get_service_status") else {}
    mosquitto_status = service_status.get("mosquitto", {})
    network_status = service_status.get("network", {})
    return {
        "mqttConnected": mqtt_state == "online" or bool(mosquitto_status.get("port_open")),
        "brokerRunning": bool(mosquitto_status.get("running") or mosquitto_status.get("port_open")),
        "bridgeConnected": gateway_state == "online",
        "gatewayState": gateway_state,
        "stmConnected": stm_state == "online",
        "networkOnline": bool(network_status.get("internet_connected")) or gateway_state == "online" or mqtt_state == "online",
        "hotspotActive": bool(network_status.get("hotspot_active")),
        "mosquitto": mosquitto_status,
        "network": network_status,
    }


@router.get("/api/dashboard-snapshot")
async def get_dashboard_snapshot():
    """Donanımdan ve broker'dan alınan gerçek zamanlı veriler (React Native için)."""
    from servers import api_server as _api
    snapshot = _api._build_ws_snapshot()

    # Eksik olan 'patient' ve 'sessions' alanlarını React hata vermesin diye ekliyoruz
    snapshot["patient"] = {
        "name": "Bilinmeyen",
        "species": "Belirsiz",
        "breed": "Belirsiz",
        "owner": "Bilinmeyen"
    }
    snapshot["sessions"] = []

    return snapshot


@router.post("/api/notifications/clear")
async def clear_notifications():
    """Clear in-memory notifications shown in React clients."""
    from servers import api_server as _api
    with _api._live_state_lock:
        _api._live_state["notifications"].clear()
    _api._ws_broadcast_sync({"type": "notifications_cleared", "data": {"timestamp": time.time()}})
    return {"status": "success"}
