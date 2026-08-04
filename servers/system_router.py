"""Sistem/durum uçları (refactor B1 Faz A: api_server.py'den ayrıldı — modüler router).

Davranış BİREBİR korunur. Paylaşılan runtime durumu (`_APP_VERSION`, `state`, `_live_state`,
`_live_state_lock`, `_build_ws_snapshot`, `_ws_broadcast_sync`) çağrı-zamanı lazy import ile
`servers.api_server`'dan okunur — böylece circular import olmaz (api_server bu router'ı include
eder; router app'i yalnız handler ÇAĞRILINCA import eder). Yollar aynen korunur.

NOT (gelecek cleanup): paylaşılan durum ileride servers/live_state.py'ye taşınmalı; şu an
davranış-koruyan ARTIMLI extraction için lazy-import deseni kullanılıyor.
"""
import logging
import os
import time
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import Response

router = APIRouter(tags=["system"])


def _cloud_registry_status() -> str:
    """Bulut cihaz-registry yayin durumu (ok | secret_mismatch | rpc_missing | error | unknown).
    Lazy import: sync_worker opsiyoneldir, saglik ucunu ASLA bozmamali."""
    try:
        from servers.sync_worker import get_registry_status
        return get_registry_status()
    except Exception:
        return "unknown"


logger = logging.getLogger("system_router")


@router.get("/api/system/info")
async def system_info(request: Request):
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
    # Audit P3 (K1 tutarlılık): pairingCode/tunnelUrl UZAK (tünel) istemciye SIZDIRILMAZ — /api/health
    # bunu K1 ile _local'e kapatmıştı; system_info tutarsız kalmıştı. Yalnız YEREL/LAN'a ver.
    _h = request.headers
    _via_proxy = bool(_h.get("cf-connecting-ip") or _h.get("cf-ray") or _h.get("x-forwarded-for"))
    from servers.auth import is_local_request
    _local = is_local_request(request.client.host if request.client else "", _via_proxy)
    return {
        "softwareVersion": _api._APP_VERSION,
        "hardwareVersion": "HW-2025.1",
        "deviceId": (device_id if _local else None),  # Audit P2: tenant-anahtarı uzak sızıntısı kapatıldı
        "pairingCode": (pairing_code if _local else None),
        "tunnelUrl": ((tunnel_url or None) if _local else None),
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

    # 'patient' artık _build_ws_snapshot() içinde (aktif seansın GERÇEK hastası ya da None) — eski
    # sabit "Bilinmeyen" placeholder'ı KALDIRILDI (Hasta Özeti kartı yanlış/boş gösteriyordu).
    snapshot.setdefault("patient", None)
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
async def health_check(request: Request):
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
    # K1 fix (uzaktan auth-bypass): pairingCode/tunnelUrl UZAK (tünel) istemciye SIZDIRILMAZ — aksi
    # halde health→kod→/api/auth/exchange→token zinciri KİMLİKSİZ token verir. Yalnız YEREL/LAN'a ver;
    # uzak app pairing-kodunu operatörden (cihaz ekranından) OUT-OF-BAND alır.
    _h = request.headers
    _via_proxy = bool(_h.get("cf-connecting-ip") or _h.get("cf-ray") or _h.get("x-forwarded-for"))
    from servers.auth import is_local_request
    _local = is_local_request(request.client.host if request.client else "", _via_proxy)
    service_status = _api.state.core.get_service_status() if _api.state.core and hasattr(_api.state.core, "get_service_status") else {}
    # At-rest şifreleme durumu (görünürlük — düz-metin fallback'i sessizce gizleme).
    at_rest_encrypted = None
    try:
        from database.treatment_history_db import get_treatment_db
        _tdb = get_treatment_db(_api._app_data_dir())
        at_rest_encrypted = bool(getattr(_tdb, "at_rest_encrypted", False))
    except Exception:
        pass
    # ── DENETİM 2026-08-04 (P2 #13): LAUNCHER NONCE'U ────────────────────────────────────
    # SORUN: launcher `find_free_port` ile portu bind edip HEMEN BIRAKIYOR; frozen backend'in
    # o portu gerçekten bind etmesi onlarca saniye sürüyor. Bu pencerede loopback'e bağlanabilen
    # HERHANGİ bir yerel süreç portu kapabilir ve `wait_for_health` yalnız HTTP 200'e baktığı için
    # launcher onu "backend hazır" sanardı. Sonuç TIBBİ: kapanışta gönderilen
    # `POST /api/hardware/emergency_stop` SALDIRGANIN dinleyicisine gider → E-stop SESSİZCE
    # "başarılı" görünür, gerçek bobinler HASTANIN ÜZERİNDE çalışmaya devam eder.
    # ÇÖZÜM: launcher, çocuk sürece `PEMF_HEALTH_NONCE` ortam değişkeniyle tek-seferlik rastgele
    # bir değer verir; yalnız GERÇEK backend onu geri yansıtabilir (port kapan süreç bilemez).
    #
    # ⚠️ YALNIZ LOOPBACK'e verilir. `/api/health` auth-muaftır ve tünelden de erişilebilir;
    # nonce LAN'a/tünele sızarsa doğrulama anlamsızlaşır. LAN de yeterli DEĞİL — launcher
    # daima 127.0.0.1'den sorar.
    _health_nonce = os.getenv("PEMF_HEALTH_NONCE", "").strip()
    _peer = (request.client.host if request.client else "") or ""
    # ⚠️ DENETİM 2026-08-04 (P3): loopback kontrolü ham soket-IP'siydi. Ama CLOUDFLARED DE
    # 127.0.0.1'DEN BAĞLANIR — tünelden gelen bir istek proxy başlığı taşımıyorsa `_via_proxy`
    # False kalır ve nonce + aktif-seans bilgisi TÜNELE SIZARDI. `is_local_request` bu tuzağa
    # karşı `_trusted_proxies()`i ayrıca eler; burada da elemek gerekiyordu.
    # NOT: `is_local_request`'in KENDİSİ kullanılamaz — o LAN'ı da yerel sayar, oysa bu iki alan
    # için kasıtlı olarak YALNIZ loopback yeterlidir (launcher daima 127.0.0.1'den sorar).
    _peer_proxy = False
    try:
        import ipaddress as _ipa

        from servers.auth import _trusted_proxies as _tp

        _ip = _ipa.ip_address(_peer.strip())
        _peer_proxy = any(_ip in net for net in _tp())
    except Exception:
        _peer_proxy = False
    _loopback_only = (not _via_proxy) and (not _peer_proxy) and _peer in ("127.0.0.1", "::1")

    # Aktif tedavi bayrağı — okuma ASLA health'i düşürmemeli (fail-safe: bilinmiyorsa "aktif" say,
    # böylece launcher şüphede kalırsa tedaviyi kesmek yerine güncellemeyi erteler).
    #
    # ⚠️ DENETİM 2026-08-04 (P3): burada YALNIZ `_active_session["is_active"]` okunuyordu. Oysa
    # AYNI tehlike için olgun bir kontrol zaten var: `update_manager._has_active_treatment()` —
    # o, resmi seans DIŞINDA sürülen bobinleri de (`/api/coil/{id}/control`, AI Pro kare akışı)
    # AKTİF sayar ve fail-closed'dur. Ayrışma somut bir boşluk yaratıyordu: veteriner bobinleri
    # manuel sürerken `is_active` False olur → launcher "seans yok" deyip SESSİZ güncellemeyi
    # sürdürür → NSIS `taskkill` → bobinler HASTANIN ÜZERİNDE kontrolcüsüz kalır.
    # Tek kaynağa bağlandı. Yalnız loopback için hesaplanır (dışarıya zaten verilmiyor).
    _session_active = True
    if _loopback_only:
        try:
            from servers.update_manager import _has_active_treatment

            _session_active = bool(_has_active_treatment())
        except Exception:
            _session_active = True

    return {
        "status": "online",
        "service": "PEMF-Vet",
        # Launcher'ın "bu port GERÇEKTEN benim başlattığım backend mi?" doğrulaması (bkz. üstteki not).
        "launcherNonce": (_health_nonce if (_health_nonce and _loopback_only) else None),
        # ── DENETİM 2026-08-04: AKTİF TEDAVİ BAYRAĞI (launcher oto-güncellemesi için) ─────────
        # Launcher açılışta manifest'e bakıp yeni sürümü SESSİZCE indirip `/S` ile kurar. NSIS
        # yükseltme kancası `taskkill /F /IM PEMF_Backend.exe` çalıştırır → HASTA ÜZERİNDE SÜREN
        # bir seans yarıda kesilir. (E-stop kancası bobinleri güvene alır, yani hasta güvenliği
        # korunur; ama tedavi kaydı yarım kalır ve veteriner sebebini göremez.) Launcher artık
        # güncellemeden ÖNCE bunu okuyup seans varsa ERTELİYOR.
        # ⚠️ launcherNonce ile aynı gerekçeyle YALNIZ loopback: `/api/health` auth-muaftır ve
        # tünelden erişilebilir; "şu an tedavi sürüyor" bilgisi dışarıya sızmamalı.
        "sessionActive": (_session_active if _loopback_only else None),
        # Audit P2: deviceId de _local'e kapatıldı — bulut RPC'lerinin tek tenant/yetki anahtarı;
        # uzak sızıntısı upsert_device-zehirleme + cross-tenant-IDOR zincirlerini köprülüyordu.
        "deviceId": (device_id if _local else None),
        "pairingCode": (pairing_code if _local else None),
        "localIp": local_ip,
        "tunnelUrl": ((tunnel_url or None) if _local else None),
        "core_initialized": _api.state.core is not None,
        "stmConnected": bool(getattr(_api.state.core, "stm_is_connected", False)) if _api.state.core else False,
        "atRestEncrypted": at_rest_encrypted,
        # DENETIM P2: bulut cihaz-registry'sinin son yayin durumu. 'secret_mismatch' KALICI bir
        # durumdur (TOFU muhru — yeniden kurulum sonrasi device_secret degisti) ve eskiden yalnizca
        # log'a dusuyordu; operator uzaktan erisimin neden sessizce guncellenmedigini goremiyordu.
        "cloudRegistry": _cloud_registry_status(),
        "services": service_status,
    }


@router.get("/favicon.ico")
async def favicon():
    # Tek kaynak ikon (pemf_heart_emf_icon.ico) — dev + frozen fallback'li servis.
    import sys
    from pathlib import Path
    bases = [Path(__file__).resolve().parent.parent]
    if getattr(sys, "frozen", False):
        bases += [Path(getattr(sys, "_MEIPASS", ".")), Path(sys.executable).resolve().parent]
    for base in bases:
        ico = base / "pemf_gui" / "resources" / "icons" / "pemf_heart_emf_icon.ico"
        try:
            if ico.exists():
                return Response(content=ico.read_bytes(), media_type="image/x-icon")
        except Exception:
            pass
    return Response(status_code=204)


@router.get("/api/discovery")
async def discovery_info(request: Request):
    """Otomatik keşf endpoint'i. Telefon uygulaması bu endpoint'i sorgular."""
    from servers import api_server as _api
    from servers.auto_discovery import _get_local_ip
    from servers.auth import is_local_request
    from servers.tunnel_manager import get_tunnel_url
    # DENETIM P3: bu uc auth-MUAF (kesif icin) ve tunnelUrl'yi KOSULSUZ veriyordu; oysa
    # /api/health ve /api/system/info ayni alani bilincli olarak _local'e kapatiyor (K1).
    # Tunel uzerinden gelen kimliksiz bir cagirici icin tunnelUrl yeni bilgi degildir ama
    # LAN'a sizmis herhangi bir cihaz icin cihazin INTERNET adresini ifsa eder → tutarli ol.
    _h = request.headers
    _via_proxy = bool(_h.get("cf-connecting-ip") or _h.get("cf-ray") or _h.get("x-forwarded-for"))
    _local = is_local_request(request.client.host if request.client else "", _via_proxy)
    return {
        "service": "PEMF-Vet",
        "version": _api._APP_VERSION,
        "localIp": _get_local_ip(),
        "port": 8000,
        "tunnelUrl": ((get_tunnel_url() or None) if _local else None),
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
        log_path = app_data / "client_errors.jsonl"
        # Audit P2: sinirsiz append → dolu-disk → SQLCipher tedavi DB'si yazamaz (LAN'da auth+rate-limit
        # muaf, ErrorBoundary flood mumkun). ~2MB'ta tek-dosya rotasyon (.jsonl + .1 = ~4MB tavan).
        try:
            if log_path.exists() and log_path.stat().st_size > 2_000_000:
                bak = app_data / "client_errors.jsonl.1"
                if bak.exists():
                    bak.unlink()
                log_path.rename(bak)
        except Exception:
            try:
                log_path.write_text("", encoding="utf-8")
            except Exception:
                pass
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(_json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        logging.getLogger("system_router").exception("client error log yazılamadı")
    return {"status": "ok"}
