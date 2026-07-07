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

from fastapi import APIRouter, Request
from fastapi.responses import Response

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


@router.get("/api/health")
async def health_check():
    """Sistemin ayakta olup olmadığını kontrol eder. Otomatik keşf için de kullanılır."""
    from servers import api_server as _api
    from servers.auto_discovery import _get_local_ip
    from servers.tunnel_manager import get_tunnel_url
    local_ip = _get_local_ip()
    tunnel_url = get_tunnel_url()
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
    service_status = _api.state.core.get_service_status() if _api.state.core and hasattr(_api.state.core, "get_service_status") else {}
    # At-rest şifreleme durumu (görünürlük — düz-metin fallback'i sessizce gizleme).
    at_rest_encrypted = None
    try:
        from database.treatment_history_db import get_treatment_db
        _tdb = get_treatment_db(_api._app_data_dir())
        at_rest_encrypted = bool(getattr(_tdb, "at_rest_encrypted", False))
    except Exception:
        pass
    return {
        "status": "online",
        "service": "PEMF-Vet",
        "deviceId": device_id,
        "pairingCode": pairing_code,
        "localIp": local_ip,
        "tunnelUrl": tunnel_url or None,
        "core_initialized": _api.state.core is not None,
        "stmConnected": bool(getattr(_api.state.core, "stm_is_connected", False)) if _api.state.core else False,
        "atRestEncrypted": at_rest_encrypted,
        "services": service_status,
    }


@router.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


@router.get("/api/discovery")
async def discovery_info():
    """Otomatik keşf endpoint'i. Telefon uygulaması bu endpoint'i sorgular."""
    from servers import api_server as _api
    from servers.auto_discovery import _get_local_ip
    from servers.tunnel_manager import get_tunnel_url
    return {
        "service": "PEMF-Vet",
        "version": _api._APP_VERSION,
        "localIp": _get_local_ip(),
        "port": 8000,
        "tunnelUrl": get_tunnel_url() or None,
        "capabilities": ["rest", "websocket", "mqtt", "ai", "database"],
    }


@router.get("/api/kpi/summary")
def get_kpi_summary():
    """KPI Özeti — DB'den seans istatistikleri."""
    from servers import api_server as _api
    result = {
        "totalSessions": 0,
        "completedSessions": 0,
        "stoppedSessions": 0,
        "avgDurationMin": 0.0,
        "coilUsage": {str(i): 0 for i in range(1, 9)},
        "modeDistribution": {},
        "last7Days": [],
    }
    try:
        # P2 audit 2026-06-28: Eskiden duz sqlite3.connect ile DB okunuyordu; SQLCipher sifreli iken
        # (PEMF_ENCRYPT_AT_REST=1) acilamiyor → 'except: pass' yutuyor → KPI SESSIZCE BOS. SQLCipher-
        # farkindali _get_treatment_db()._get_connection() kullan.
        # Audit 2026-07-01: Eskiden son 200 satir RAM'e cekilip Python'da toplaniyordu →
        # 200+ seansli klinikte "Toplam Seans" 200'de takiliyor, oran/grafik yaniltici oluyordu.
        # Simdi tum agregasyon SQL'de (LIMIT yok) → dogru toplam/oran; ayni SQLCipher baglantisi.
        db = _api._get_treatment_db()
        if db is None:
            return result
        from datetime import timedelta

        with db._get_connection() as conn:
            cur = conn.cursor()

            cur.execute("SELECT COUNT(*) FROM treatment_sessions")
            total = int(cur.fetchone()[0] or 0)

            cur.execute(
                "SELECT COUNT(*) FROM treatment_sessions "
                "WHERE LOWER(COALESCE(session_status,'')) = 'completed'"
            )
            completed = int(cur.fetchone()[0] or 0)

            cur.execute(
                "SELECT COUNT(*) FROM treatment_sessions "
                "WHERE LOWER(COALESCE(session_status,'')) IN ('stopped','error','interrupted') "
                "   OR LOWER(COALESCE(session_status,'')) LIKE '%abort%'"
            )
            stopped = int(cur.fetchone()[0] or 0)

            cur.execute(
                "SELECT AVG(duration_minutes) FROM treatment_sessions "
                "WHERE duration_minutes IS NOT NULL"
            )
            _avg = cur.fetchone()[0]
            avg_dur = round(float(_avg), 1) if _avg is not None else 0.0

            modes = {}
            for _r in cur.execute(
                "SELECT COALESCE(treatment_mode,'Manuel') AS m, COUNT(*) "
                "FROM treatment_sessions GROUP BY m"
            ).fetchall():
                modes[str(_r[0] or "Manuel")] = int(_r[1] or 0)

            # Son 7 TAKVIM gunu (bugun dahil geriye 7); bos gunler 0 ile doldurulur.
            # Eskiden yalniz seans OLAN gunler donuyordu → ardisik olmayan tarihler bitisik
            # cizilip "son 7 gun trendi" gibi yaniltiyordu.
            now_local = datetime.now()
            since = (now_local - timedelta(days=6)).strftime("%Y-%m-%d")
            day_counts = {}
            for _r in cur.execute(
                "SELECT substr(session_date,1,10) AS d, COUNT(*) FROM treatment_sessions "
                "WHERE substr(session_date,1,10) >= ? GROUP BY d",
                (since,),
            ).fetchall():
                if _r[0]:
                    day_counts[str(_r[0])] = int(_r[1] or 0)
            # En yeni gun once (FE .reverse() ile eskiden yeniye cizer) — eski sozlesme korunur.
            last7 = [
                {"date": (now_local - timedelta(days=_i)).strftime("%Y-%m-%d"),
                 "count": day_counts.get((now_local - timedelta(days=_i)).strftime("%Y-%m-%d"), 0)}
                for _i in range(0, 7)
            ]

            # coilUsage: bobin-bazli kosum sayisi (ayni SQLCipher-farkindali baglanti)
            try:
                for _row in cur.execute(
                    "SELECT coil_id, COUNT(*) FROM session_coil_runs GROUP BY coil_id"
                ).fetchall():
                    _cid = int(_row[0]) if _row[0] is not None else 0
                    if 1 <= _cid <= 8:
                        result["coilUsage"][str(_cid)] = int(_row[1] or 0)
            except Exception:
                pass  # session_coil_runs yok/bos → coilUsage 0 kalir

        result.update({
            "totalSessions": total,
            "completedSessions": completed,
            "stoppedSessions": stopped,
            "avgDurationMin": avg_dur,
            "modeDistribution": modes,
            "last7Days": last7,
        })
    except Exception:
        logging.getLogger(__name__).exception("KPI ozeti hesaplanamadi")  # P2: sessiz yutma yerine logla
    return result


@router.post("/api/client/error")
async def log_client_error(request: Request):
    """F-7: Frontend ErrorBoundary crash raporu (fire-and-forget). client_errors.jsonl'e ekler;
    boyut-sınırlı. Hata olsa da 200 döner (istemci akışını bozmaz). Not: stack kod-yolu içerir,
    hasta PII genelde bulunmaz; dosya app_data'da (ACL-bağlamlı) yerel kalır."""
    import json as _json
    try:
        body = await request.json()
    except Exception:
        body = {}
    body = body or {}
    try:
        from servers import api_server as _api
        app_data = _api._app_data_dir()
        app_data.mkdir(parents=True, exist_ok=True)
        rec = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "message": str(body.get("message") or "")[:500],
            "stack": str(body.get("stack") or "")[:2000],
            "route": str(body.get("route") or "")[:80],
        }
        with open(app_data / "client_errors.jsonl", "a", encoding="utf-8") as f:
            f.write(_json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        logging.getLogger("system_router").exception("client error log yazılamadı")
    return {"status": "ok"}
