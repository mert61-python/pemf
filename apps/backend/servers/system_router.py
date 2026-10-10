# Author: mertaygn, cglrgrkn
"""Sistem/durum uçları (refactor B1 Faz A: api_server.py'den ayrıldı — modüler router).

Davranış BİREBİR korunur. Paylaşılan runtime durumu (`_APP_VERSION`, `state`, `_live_state`,
`_live_state_lock`, `_build_ws_snapshot`, `_ws_broadcast_sync`) çağrı-zamanı lazy import ile
`servers.api_server`'dan okunur — böylece circular import olmaz (api_server bu router'ı include
eder; router app'i yalnız handler ÇAĞRILINCA import eder). Yollar aynen korunur.

NOT (gelecek cleanup): paylaşılan durum ileride servers/live_state.py'ye taşınmalı; şu an
davranış-koruyan ARTIMLI extraction için lazy-import deseni kullanılıyor.
"""

import asyncio
import concurrent.futures
import logging
import os
import threading
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from utils.path_utils import HARDWARE_VERSION  # TEK donanim-surumu kaynagi (M6); leaf util, circular yok

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
        "hardwareVersion": HARDWARE_VERSION,
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
    service_status = (
        _api.state.core.get_service_status()
        if _api.state.core and hasattr(_api.state.core, "get_service_status")
        else {}
    )
    mosquitto_status = service_status.get("mosquitto", {})
    network_status = service_status.get("network", {})
    return {
        "mqttConnected": mqtt_state == "online" or bool(mosquitto_status.get("port_open")),
        "brokerRunning": bool(mosquitto_status.get("running") or mosquitto_status.get("port_open")),
        "bridgeConnected": gateway_state == "online",
        "gatewayState": gateway_state,
        "stmConnected": stm_state == "online",
        # ⚠️ `networkOnline` = İNTERNET, cihaz ağı DEĞİL (sahip bildirimi 2026-09-12).
        # Eskiden `or gateway_state == "online" or mqtt_state == "online"` vardı. `gateway`
        # hotspot ya da herhangi bir mod açıkken online olur; `mqtt` ise 127.0.0.1'deki YEREL
        # mosquitto'dur — ikisi de internetin VARLIĞINI kanıtlamaz. Sonuç: "İnternet Bağlantısı"
        # satırı kablo çekiliyken bile YEŞİL kalıyordu, yani hiçbir zaman "Kapalı" diyemiyordu.
        # Yalan-yeşil, yalan-kırmızıdan daha tehlikelidir: operatörün bakacağı satır odur.
        # Cihaz ağı bilgisi kaybolmadı — `bridgeConnected` / `hotspotActive` alanlarında duruyor.
        "networkOnline": bool(network_status.get("internet_connected")),
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
    service_status = (
        _api.state.core.get_service_status()
        if _api.state.core and hasattr(_api.state.core, "get_service_status")
        else {}
    )
    # At-rest şifreleme durumu (görünürlük — düz-metin fallback'i sessizce gizleme).
    at_rest_encrypted = None
    try:
        from database.treatment_history_db import get_treatment_db

        _tdb = get_treatment_db(_api._app_data_dir())
        at_rest_encrypted = bool(getattr(_tdb, "at_rest_encrypted", False))
    except Exception:
        pass
    # ⚠️ DENETİM 2026-08-09: TIBBİ KAYIT DB'Sİ HAZIR MI (dbReady).
    # `/api/session/start` ile AYNI kaynaktan hesaplanır (api_server._kayit_db_hazir) — aksi hâlde
    # "sağlık yeşil ama seans 503" gibi teşhis edilemez bir tutarsızlık çıkardı. Bu alan olmadan
    # DB arızası ancak veteriner seans başlatmayı DENEYİNCE, yani hasta masadayken görülüyordu.
    # Sağlığın kendisini DÜŞÜRMEZ: backend ayakta ve acil durdurma yolu çalışıyor.
    _hazir_sebep = ""
    try:
        _hazir, _hazir_sebep = _api._kayit_db_hazir()
        db_ready = bool(_hazir)
    except Exception:
        db_ready = False
    # D1.37 (B-3.8): DB'siz (kısıtlı) açılışta NEDEN — ör. "Hasta veritabanı göç bekliyor …".
    # Yalnız açılış kaydından (yol/istisna ayrıntısı yok: bu uç auth-muaf ve tünelden erişilebilir).
    # D1.77 (B-3.9): disk kritikse o nedenin KENDİSİ (sabit metin + MB; yol/istisna içermez — `is_ready`).
    db_sebep = None
    if not db_ready:
        try:
            _disk = str(_hazir_sebep or "") if str(_hazir_sebep or "").startswith("Disk boş alanı kritik") else ""
            db_sebep = (
                _api._db_acilis_hatasi() or _disk or "Tıbbi kayıt veritabanı hazır değil; yeni seans başlatılamaz."
            )
        except Exception:
            db_sebep = "Tıbbi kayıt veritabanı hazır değil; yeni seans başlatılamaz."
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

    # ⚠️ E2-3.10 (Ö.4-Y8): sürücü türü sorgusu (GetDriveTypeW — ağ sürücüsünde asılabilir) olay döngüsünde KOŞMAZ; satır içi
    # çağrıda asılınca ACİL DURDUR bekliyordu (ölçüldü 2,1 sn / 3 sn benzetim). Ortak havuzda (`to_thread`) da DEĞİL: zaman aşımı
    # yalnız bekleyeni bırakır, asılı işi değil — her yoklama bir havuz iş parçacığı sızdırıp havuzu tüketiyordu (25 yoklamada 20,
    # ölçüldü). Kendi daemon iş parçacığında, TEK uçuşta; bilinemezse None (arayüz susar).
    _veri_agda = await _veri_koku_agda_dongu_disi(_api) if _local else None

    return {
        "status": "online",
        "service": "PEMF-Vet",
        # ── SÜRÜM GÖRÜNÜRLÜĞÜ (2026-08-09 denetimi, Tier 3) ─────────────────────────────────
        # `/api/health` saha teşhisinin ilk durağı ama sürümü HİÇ söylemiyordu; destek telefonda
        # "hangi sürüm" diye sorup operatöre menü tarif etmek zorunda kalıyordu. `buildId`
        # sürümün söyleyemediğini söyler: aynı 1.9.5 farklı paket içeriği çalıştırabilir.
        "version": _api._APP_VERSION,
        "buildId": (_api._BUILD_ID or None),
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
        # ⚠️ "BAĞLI" ile "UYUMLU" AYRI SORULARDIR (2026-09-18). Kart konuşuyor olabilir ama
        # backend'in gönderdiği paket genişliğini anlamayan bir firmware koşuyor olabilir;
        # o hâlde gösterge YEŞİL, hata yok, HİÇBİR bobin çalışmıyor. `stmConnected` bu ayrımı
        # yapamaz, o yüzden AYRI alan. Üç durum: true=uyumlu · false=KESİN uyumsuz (seans
        # reddedilir) · null=banner okunamadı/henüz görülmedi (seans ENGELLENMEZ).
        "stmUyumlu": getattr(_api.state.core, "stm_uyumlu", None) if _api.state.core else None,
        "stmUyumsuzlukSebebi": (getattr(_api.state.core, "stm_uyumsuzluk_sebebi", "") if _api.state.core else ""),
        "atRestEncrypted": at_rest_encrypted,
        # Tıbbi kayıt yazılabilir mi. false → yeni seans REDDEDİLİR (bkz. /api/session/start).
        "dbReady": db_ready,
        # dbReady false iken nedeni (true iken null). Launcher yalnız `dbReady`e bakar.
        "dbSebep": db_sebep,
        # DENETIM P2: bulut cihaz-registry'sinin son yayin durumu. 'secret_mismatch' KALICI bir
        # durumdur (TOFU muhru — yeniden kurulum sonrasi device_secret degisti) ve eskiden yalnizca
        # log'a dusuyordu; operator uzaktan erisimin neden sessizce guncellenmedigini goremiyordu.
        "cloudRegistry": _cloud_registry_status(),
        "services": service_status,
        # D1.81 · Y4 (yalnız-ek): ACİL DURDURMA MANDALI — kuruluyken hiçbir START kabul edilmez; arayüz (oturumsuz
        # Karşılama/Giriş ekranları dahil) durumu ve "Sıfırla"yı buradan/WS'ten gösterir. Neden/zaman ayrıntısı
        # yalnız yerel/LAN'a (bu uç auth-muaf ve tünelden erişilebilir); uzak istemci yalnız `aktif`i görür.
        "estopMandali": (_estop_mandali_durumu() if _local else {"aktif": _estop_mandali_durumu().get("aktif")}),
        # D1.116 · B-4.11 (yalnız-ek): oto-firmware durumu — açılış denetiminin kararı (eylem/gerekçe) ve son yakma sonucu
        # (`hata` = "[kod] …"). Eskiden yalnız servis günlüğündeydi ("fail-quiet ≠ fail-silent" vaadi fiilen gizliydi).
        # Gerekçe/hata metni ayrıntı (sürüm, yol) taşır → yalnız yerel/LAN; tünel (uzak) istemcisine None.
        "firmwareGuncelleme": (_firmware_guncelleme_durumu() if _local else None),
        # Y118 (yalnız-ek): veri klasörü AĞ PAYLAŞIMINDA mı (SQLite bu kipte güvenilir değil — arayüz bandı). Yalnız bayrak (yol
        # günlükte); yalnız yerel/LAN'a, tünel (uzak) istemcisine None.
        "veriKokuAgda": _veri_agda,
    }


_veri_agda_ucusta = None  # (anahtar, concurrent.futures.Future) — sürmekte olan TEK sürücü türü sorgusu
_veri_agda_kilit = threading.Lock()


async def _veri_koku_agda_dongu_disi(_api, sinir_sn: float = 2.0):
    """E2-3.10: `_veri_koku_agda`yı kendi daemon iş parçacığında koşar; önceki sorgu bitmediyse YENİSİNİ BAŞLATMAZ, onu bekler.
    `sinir_sn` içinde sonuç yoksa None (sorgu arka planda sürer, sonraki yoklama onu yeniden kullanır)."""
    global _veri_agda_ucusta
    try:
        from utils import path_utils as _pu

        anahtar = (
            str(_api._app_data_dir()),
            id(_pu._surucu_turu),
        )  # üretimde sabit; testte kök/sorgu değişince yeni uçuş
    except Exception:
        anahtar = None
    with _veri_agda_kilit:
        onceki = _veri_agda_ucusta
        f = onceki[1] if onceki and onceki[0] == anahtar else None
        if f is None or f.done():
            f = concurrent.futures.Future()

            def _is(gelecek=f):
                try:
                    gelecek.set_result(_veri_koku_agda(_api))
                except BaseException:
                    gelecek.set_result(None)

            threading.Thread(target=_is, daemon=True, name="pemf-veri-koku-ag").start()
            _veri_agda_ucusta = (anahtar, f)
    try:
        return await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(f)), timeout=sinir_sn)
    except Exception:
        return None


def _veri_koku_agda(_api):
    """Y118: veri kökü ağ paylaşımında mı (bilinemezse None — arayüz susar)."""
    try:
        from utils.path_utils import veri_koku_ag_paylasiminda_mi

        return bool(veri_koku_ag_paylasiminda_mi(_api._app_data_dir()))
    except Exception:
        return None


def _estop_mandali_durumu() -> dict:
    from utils import estop_mandali

    return estop_mandali.durum()


def _firmware_guncelleme_durumu() -> dict | None:
    """D1.116: `firmware_manager.durum()` anlık görüntüsü; okunamazsa None (sağlık ucu ASLA düşmez)."""
    try:
        from servers import firmware_manager

        return firmware_manager.durum()
    except Exception:
        return None


@router.get("/favicon.ico")
async def favicon():
    # Tek kaynak ikon (pemf_heart_emf_icon.ico) — dev + frozen fallback'li servis.
    import sys
    from pathlib import Path

    from utils.path_utils import kaynak_kokunu_bul

    bases = [kaynak_kokunu_bul(__file__)]
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
    from servers.auth import is_local_request
    from servers.auto_discovery import _get_local_ip, get_api_port
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
        "port": get_api_port(),  # ⚠️ GERÇEK port (denetim 2026-08-17); env yoksa 8000
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
                "SELECT COUNT(*) FROM treatment_sessions WHERE LOWER(COALESCE(session_status,'')) = 'completed'"
            )
            completed = int(cur.fetchone()[0] or 0)

            # ⚠️ ACİL DURDURMA da "durdurulan" sayılır (kampanya bulgusu S09, 2026-08-14).
            # Eskiden e-stop `'completed'` yazıyordu → gösterge tablosu `stoppedSessions=0` deyip
            # "her şey yolunda" gösteriyordu. Durum sabiti TEK KAYNAKTAN gelir; burada elle string
            # yazmak, yazan ile okuyanın ayrışıp sayacın SESSİZCE sıfırlanması demekti.
            from database.treatment_history_db import SEANS_DURUMU_ACIL_DURDURMA

            cur.execute(
                "SELECT COUNT(*) FROM treatment_sessions "
                "WHERE LOWER(COALESCE(session_status,'')) IN ('stopped','error','interrupted',?) "
                "   OR LOWER(COALESCE(session_status,'')) LIKE '%abort%'",
                (SEANS_DURUMU_ACIL_DURDURMA.lower(),),
            )
            stopped = int(cur.fetchone()[0] or 0)

            cur.execute("SELECT AVG(duration_minutes) FROM treatment_sessions WHERE duration_minutes IS NOT NULL")
            _avg = cur.fetchone()[0]
            avg_dur = round(float(_avg), 1) if _avg is not None else 0.0

            modes = {}
            for _r in cur.execute(
                "SELECT COALESCE(treatment_mode,'Manuel') AS m, COUNT(*) FROM treatment_sessions GROUP BY m"
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
                {
                    "date": (now_local - timedelta(days=_i)).strftime("%Y-%m-%d"),
                    "count": day_counts.get((now_local - timedelta(days=_i)).strftime("%Y-%m-%d"), 0),
                }
                for _i in range(0, 7)
            ]

            # coilUsage: bobin-bazli kosum sayisi (ayni SQLCipher-farkindali baglanti)
            try:
                for _row in cur.execute("SELECT coil_id, COUNT(*) FROM session_coil_runs GROUP BY coil_id").fetchall():
                    _cid = int(_row[0]) if _row[0] is not None else 0
                    if 1 <= _cid <= 8:
                        result["coilUsage"][str(_cid)] = int(_row[1] or 0)
            except Exception:
                pass  # session_coil_runs yok/bos → coilUsage 0 kalir

        result.update(
            {
                "totalSessions": total,
                "completedSessions": completed,
                "stoppedSessions": stopped,
                "avgDurationMin": avg_dur,
                "modeDistribution": modes,
                "last7Days": last7,
            }
        )
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


# ══════════════════════════════════════════════════════════════════════════════════════════
# FELAKET KURTARMA GÖRÜNÜRLÜĞÜ (2026-08-09 denetimi, ENGEL'in ikinci yarısı)
#
# `utils/backup_recovery.py` 150-bitlik bir kurtarma kodu üretir ve anahtarları o koda bağlı bir
# zarfla yedeklerin yanına yazar. Kod ise `<veri-dizini>\KURTARMA-KODU.txt` dosyasına yazılıp
# YALNIZCA LOG'a bir uyarı düşüyordu. Veteriner log okumaz.
#
# SONUÇ: kod, şifreli veritabanıyla AYNI diskte duruyor. Disk ölürse ikisi de gider ve off-site
# yedekler — zarf orada olsa bile — SONSUZA DEK açılamaz. Yani kurtarma mekanizması, operatör
# kodu makine dışına kopyalamadıkça HİÇBİR ŞEY korumuyordu; operatöre ise varlığı hiç söylenmiyordu.
#
# ⚠️ KOD, DURUM UCUNDAN DÖNMEZ. Kod tüm hasta verisinin ana anahtarıdır; `/api/health` gibi
# LAN'dan/tünelden erişilebilen bir yere sızarsa at-rest şifreleme anlamsızlaşır. Kodun kendisi
# YALNIZ loopback'ten (cihazın kendi ekranı) okunur — `desktop-session` ile aynı gerekçe.
_KURTARMA_ONAY_ANAHTARI = "recovery_code_acknowledged_at"
# ⚠️ D2.13 (B-3.39): onay KODA bağlıdır. Onay anındaki `KURTARMA-KODU.txt` içeriğinin parmak izi saklanır; kod değişip dosya yeniden
# yazılınca parmak izi tutmaz → onay YENİ kodu onaylamış SAYILMAZ, uyarı bandı geri gelir (operatör kasadaki eski kodla kalmaz).
# Parmak izi DOSYA İÇERİĞİNİN tek yönlü özetidir (16 hex); kodun kendisi saklanmaz/döndürülmez. Parmak izi olmayan eski onaylar
# (bu sürümden önce verilmiş) mevcut koda verilmiş sayılır — güncellemede herkes yeniden uyarılmasın.
_KURTARMA_ONAY_IZI_ANAHTARI = "recovery_code_acknowledged_fp"


def _kod_dosyasi_izi(kod_dosyasi) -> str:
    """`KURTARMA-KODU.txt`deki KODUN parmak izi (yoksa / okunamazsa ""). ⚠️ E2-1.9: eskiden dosya METNİNİN özetiydi → yalnız metin
    şablonu değişince (kod AYNI) onay düşüyor, bant geri geliyordu. Kod 150 bit — 16 hex özeti kaba kuvvetle açılamaz."""
    import hashlib
    import re

    try:
        metin = kod_dosyasi.read_text(encoding="utf-8")
    except Exception:
        return ""
    m = re.search(r"[A-Z2-7]{5}(?:-[A-Z2-7]{5}){5}", metin)
    govde = ("kod:" + m.group(0)).encode("ascii") if m else metin.encode("utf-8")
    return hashlib.sha256(govde).hexdigest()[:16]


def _loopback_mu(request: Request) -> bool:
    """SADECE 127.0.0.1/::1. `is_local_request` KULLANILMAZ — o LAN'ı da yerel sayar."""
    from servers.auth import is_loopback_request

    h = request.headers
    via_proxy = bool(h.get("cf-connecting-ip") or h.get("cf-ray") or h.get("x-forwarded-for"))
    return is_loopback_request(request.client.host if request.client else "", via_proxy)


def _kurtarma_durumu():
    """(at_rest, kod_dosyasi_var, onay_zamani|None, kod_dosyasi_yolu)."""
    from pathlib import Path

    from utils.backup_recovery import CODE_FILE_NAME

    from servers import api_server as _api

    app_data = Path(_api._app_data_dir())
    kod_dosyasi = app_data / CODE_FILE_NAME
    at_rest = False
    onay = None
    try:
        from database.treatment_history_db import get_treatment_db

        tdb = get_treatment_db(app_data)
        at_rest = bool(getattr(tdb, "at_rest_encrypted", False))
        onay = tdb._get_system_setting(_KURTARMA_ONAY_ANAHTARI)
        # D2.13: onay bugünkü kod dosyasına verilmemişse (kod değişti) onay YOK sayılır → uyarı geri gelir.
        onay_izi = tdb._get_system_setting(_KURTARMA_ONAY_IZI_ANAHTARI)
        if onay and onay_izi and onay_izi != _kod_dosyasi_izi(kod_dosyasi):
            onay = None
    except Exception:
        logging.getLogger("system_router").debug("kurtarma durumu okunamadi", exc_info=True)
    return at_rest, kod_dosyasi.exists(), onay, str(kod_dosyasi)


@router.get("/api/system/recovery-status")
async def recovery_status(request: Request):
    """Kurtarma kodu var mı ve operatör makine dışına kopyaladığını ONAYLADI mı?

    Kodun KENDİSİNİ döndürmez (bkz. üstteki not). Arayüz bunu okuyup onaylanana kadar kalıcı
    bir uyarı gösterir — uyarının amacı tam olarak "diskiniz ölürse yedekleriniz açılmaz"
    durumunu operatöre önceden anlatmaktır.
    """
    from servers.auth import enforce_privileged

    enforce_privileged(request)
    at_rest, kod_var, onay, yol = _kurtarma_durumu()
    return {
        "atRestEncrypted": at_rest,
        "codeExists": kod_var,
        "acknowledged": bool(onay),
        "acknowledgedAt": onay,
        # Operatör dosyayı bulup kopyalayabilsin diye YOL verilir; içerik verilmez.
        "codeFilePath": yol,
        # Uyarı gösterilmeli mi: kod VAR ama operatör (bu koda) henüz onay vermedi. ⚠️ D2.60 (B-3.64): şifreleme KAPALIYKEN de —
        # zarf `patient_fernet_key`i taşır (hasta alanları onunla şifreli); kod dosyası yalnız kurtarılacak anahtar varken yazılır.
        "warn": bool(kod_var and not onay),
    }


@router.get("/api/system/recovery-code")
async def recovery_code(request: Request):
    """Kurtarma kodunu göster — YALNIZ LOOPBACK (cihazın kendi ekranı).

    ⚠️ LAN/tünel KESİNLİKLE HAYIR: bu kod tüm hasta verisinin ana anahtarıdır ve zarfla
    birleştiğinde at-rest şifrelemeyi tamamen geçersiz kılar.
    """
    from fastapi import HTTPException

    if not _loopback_mu(request):
        raise HTTPException(status_code=403, detail="Kurtarma kodu yalnızca cihazın kendi ekranından görüntülenebilir.")
    from pathlib import Path

    from utils.backup_recovery import CODE_FILE_NAME

    from servers import api_server as _api

    yol = Path(_api._app_data_dir()) / CODE_FILE_NAME
    if not yol.exists():
        # D2.60 (B-3.94): "şifreleme kapalı olabilir" demiyor — dosya, kod üretilmiş ama yazılamamışken ya da operatör kodu dışarı
        # alıp sildikten sonra da yok olabilir (o durumda geri yazılmaz).
        raise HTTPException(
            status_code=404,
            detail="Kurtarma kodu dosyası bu cihazda yok: ya henüz yazılmadı (kurtarılacak anahtar varsa bir sonraki yedek turunda "
            "yazılır; yazılamıyorsa günlükte 'kurtarma kodu dosyasi YAZILAMADI' satırına bakın) ya da kod dışarı alındıktan sonra "
            "silindi.",
        )
    try:
        return {"status": "success", "codeFilePath": str(yol), "content": yol.read_text(encoding="utf-8")}
    except Exception:
        logging.getLogger("system_router").exception("kurtarma kodu okunamadi")
        raise HTTPException(status_code=500, detail="Kurtarma kodu okunamadı.")


@router.post("/api/system/recovery-ack")
async def recovery_ack(request: Request):
    """Operatör kodu makine DIŞINA kopyaladığını onayladı → uyarıyı sustur."""
    from fastapi import HTTPException

    from servers.auth import enforce_privileged

    enforce_privileged(request)
    from pathlib import Path

    from servers import api_server as _api

    try:
        from database.treatment_history_db import get_treatment_db

        def _yaz():
            from utils.backup_recovery import CODE_FILE_NAME

            app_data = Path(_api._app_data_dir())
            tdb = get_treatment_db(app_data)
            # D2.13: onay, operatörün GÖRDÜĞÜ kod dosyasına bağlanır (önce iz, sonra zaman — yarım yazımda iz eski onayı bozmasın).
            tdb._set_system_setting(
                _KURTARMA_ONAY_IZI_ANAHTARI,
                _kod_dosyasi_izi(app_data / CODE_FILE_NAME),
                "Onaylanan KURTARMA-KODU.txt iceriginin parmak izi (kod degisirse onay gecersiz)",
            )
            tdb._set_system_setting(
                _KURTARMA_ONAY_ANAHTARI,
                datetime.now().isoformat(timespec="seconds"),
                "Operator kurtarma kodunu makine disina kopyaladigini onayladi",
            )
            # E2-1.10: yedek turu (DB'ye bağlanmadan) "operatör kodu aldı" bilgisini görsün → onaydan sonra silinen dosya geri yazılmaz,
            # onaysız yok olan dosya bir kez daha yazılır. İşaret yazılamazsa onay yine geçerli (yalnız dosya bir kez geri gelebilir).
            try:
                from utils.backup_recovery import ONAY_ISARETI_ADI

                (app_data / ONAY_ISARETI_ADI).write_text(_kod_dosyasi_izi(app_data / CODE_FILE_NAME), encoding="utf-8")
            except Exception:
                logging.getLogger("system_router").warning("kurtarma onay isareti yazilamadi", exc_info=True)

        # C2-4.1 (Ö.4-Y8): DB yazımı olay döngüsünde DEĞİL — tedavi DB'si kilitliyken döngü donup ACİL DURDUR beklemesin.
        await asyncio.to_thread(_yaz)
    except Exception:
        logging.getLogger("system_router").exception("kurtarma onayi yazilamadi")
        raise HTTPException(status_code=500, detail="Onay kaydedilemedi.")
    return {"status": "success"}


# ══════════════════════════════════════════════════════════════════════════════════════════
# VERİ SAKLAMA / PII MASKELEME AYARI (2026-08-09 denetimi, Tier 1)
#
# Seans kayıtlarındaki hasta/operatör adı ve notlar, süre dolunca `[REDACTED]` ile GERİ
# DÖNÜŞSÜZ maskeleniyordu. Süre yalnız `PEMF_RETAIN_PII_DAYS` ortam değişkeniyle
# ayarlanabiliyordu — hiçbir veteriner bunu bilmez. Sonuç: klinik 366. günde hasta adı yerine
# `[REDACTED]` görüyor, sebebini hiçbir yerde bulamıyor.
#
# Tıbbi-hukuki saklama süresi ülkeye/kliniğe göre değişir (KVKK silmeyi ister, açılmış bir dava
# dosyası saklamayı) → KARAR OPERATÖRÜNDÜR. Bu uçlar o kararı görünür ve yönetilebilir kılar.
_PII_VARSAYILAN_GUN = 365


def _pii_ortam_gunu() -> int:
    """Operatör süre seçmemişse etkin süre: `PEMF_RETAIN_PII_DAYS`, yoksa 365 — headless bakım turunun AYNI okuyucusuyla (geçersiz
    değer → varsayılan). D2.55: onay bu süreye bağlı; ekran ile bakım turu farklı süre okursa onay hiç tutmaz ya da yanlış süreye tutar."""
    from services.headless_db_maintenance import HeadlessDBMaintenance

    return HeadlessDBMaintenance._retain_days("PEMF_RETAIN_PII_DAYS", _PII_VARSAYILAN_GUN)


def _pii_ayar_db():
    from pathlib import Path

    from database.treatment_history_db import get_treatment_db

    from servers import api_server as _api

    return get_treatment_db(Path(_api._app_data_dir()))


@router.get("/api/settings/retention")
async def retention_durumu(request: Request):
    """Saklama süresi + kaç kaydın maskelenmeyi beklediği + onay durumu."""
    from servers.auth import enforce_privileged

    enforce_privileged(request)

    def _oku():
        db = _pii_ayar_db()
        secilen = db.pii_suresi_oku()
        etkin = secilen if secilen is not None else _pii_ortam_gunu()
        bekleyen = db.redaksiyon_bekleyen_sayisi(etkin) if etkin > 0 else 0
        return secilen, etkin, db.pii_onayi_var_mi(etkin), db.pii_onayi_oku(), bekleyen

    try:
        # C2-4.1 (Ö.4-Y8): DB okumaları olay döngüsünde DEĞİL (tedavi DB'si kilitliyken döngü donup ACİL DURDUR beklemesin).
        secilen, etkin, onayli, onay, bekleyen = await asyncio.to_thread(_oku)
        anonim = await asyncio.to_thread(_anonimlestirme_durumu)
        return {
            "days": etkin,
            "configured": secilen is not None,
            "acknowledged": onayli,
            # Onay yoksa VE maskelenecek kayıt varsa arayüz sormalı.
            "pending": 0 if onayli else bekleyen,
            # D2.55 · A-09: onay BU süreye ve kapsama mı verildi? Kayıtlı ama geçersiz onay (süre/kapsam değişti ya da süresiz eski
            # biçim) → `approvalStale`; arayüz "önceki onay N gün içindi, yeni onay gerekiyor" der.
            "approvedDays": (onay or {}).get("gun"),
            "approvedCount": (onay or {}).get("sayi"),
            "approvalStale": bool(onay) and not onayli,
            "default": _PII_VARSAYILAN_GUN,
            # D2.54 · A-06: 5 yıl inaktif hasta anonimleştirmesi — onay yoksa bekleyen sayı gösterilir ve arayüz sorar.
            "anonymization": anonim,
        }
    except Exception:
        logger.exception("retention durumu okunamadi")
        raise HTTPException(status_code=500, detail="Ayar okunamadı.")


# ═══════════════════════════════════════════════════════════════════════════════════════════
# DENETİM İZİ OKUMA (2026-08-09 denetimi, Tier 3)
# Yazılıp hiç bakılmayan bir iz, olmayan izle aynıdır. Bu uç kliniğe "cihazımda ne oldu"
# sorusunun cevabını verir; destek paketine de buradan girer.
# ⚠️ enforce_privileged: iz, kimin ne sildiğini gösterir — LAN'daki rastgele bir cihaz
# okuyamamalı. Kayıt İÇERİĞİ zaten yazılmaz, ama kapsam+kimlik bile hassastır.
# ═══════════════════════════════════════════════════════════════════════════════════════════


@router.get("/api/audit/events")
async def denetim_olaylari(request: Request, limit: int = 200, event_type: str = ""):
    """Son denetim olayları (en yeni önce). Ekleme-only tablodan salt-okuma."""
    from servers.auth import enforce_privileged

    enforce_privileged(request)

    def _oku():
        db = _pii_ayar_db()
        n = max(1, min(int(limit), 1000))
        return {
            "status": "success",
            "total": db.denetim_sayisi(),
            "events": db.denetim_oku(n, (event_type or "").strip()[:64]),
        }

    try:
        # C2-4.1 (Ö.4-Y8): DB okuması olay döngüsünde DEĞİL (tedavi DB'si kilitliyken döngü donup ACİL DURDUR beklemesin).
        return await asyncio.to_thread(_oku)
    except Exception:
        logger.exception("denetim izi okunamadi")
        raise HTTPException(status_code=500, detail="Denetim izi okunamadı.")


@router.post("/api/support/bundle")
async def destek_paketi(request: Request):
    """Tek tuşla PII-maskeli destek paketi (base64 zip).

    ⚠️ Saha teşhisi bugüne kadar "telefonda operatöre ProgramData yolunu tarif etmek"ti; log
    dosyaları 60 MB ve içlerinde hasta adı geçebiliyor — yani "logu yolla" demek kontrolsüz bir
    kişisel veri aktarımı istemekti. Bu uç, cihazdaki GERÇEK hasta/sahip adlarını ve operatör
    e-postalarını (DB'den okuyup) maskeler; sır dosyaları ve veritabanları pakete GİRMEZ.
    Paket bir `OZET.json` taşır: ne alındı, ne atlandı, kaç eşleşme maskelendi.
    """
    import asyncio as _a
    import base64 as _b64
    from pathlib import Path as _Path

    from servers.auth import enforce_privileged

    enforce_privileged(request)
    try:
        from utils.support_bundle import dosya_adi, olustur

        from servers import api_server as _api

        veri, ozet = await _a.to_thread(olustur, _Path(_api._app_data_dir()))
    except Exception:
        logger.exception("destek paketi olusturulamadi")
        raise HTTPException(status_code=500, detail="Destek paketi oluşturulamadı.")
    # Paketin üretilmesi de bir dışa-aktarma olayıdır: denetim izine yazılır.
    try:
        from servers import audit_log as _iz

        _iz.kimlikli_yaz(
            request,
            "support.bundle",
            scope="teshis",
            item_count=len(ozet.get("alinan_dosyalar") or []),
            detail={"maskelenen": ozet.get("maskelenen_eslesme")},
        )
    except Exception:
        pass
    return {
        "status": "success",
        "filename": dosya_adi(),
        "data_b64": _b64.b64encode(veri).decode("ascii"),
        "summary": ozet,
    }


def _anonimlestirme_durumu() -> dict:
    """D2.54 · A-06 / A-09: anonimleştirme eşiği, onayın BU eşiğe verilip verilmediği ve bekleyen hasta sayısı (sayılamazsa None —
    arayüz "sayılamadı" der; "0 bekleyen" yalanı yok). Olay döngüsü DIŞINDA çağrılır."""
    from database.patient_database import get_patient_database
    from services import kvkk_anonimlestirme as _kv

    db = _pii_ayar_db()
    onay = db.anonim_onayi_oku()
    onayli = bool(onay) and int(onay.get("gun") or 0) == int(_kv.ESIK_GUN)
    try:
        bekleyen = _kv.bekleyen_sayisi(get_patient_database(), _kv.ESIK_GUN)
    except Exception:
        logger.warning("KVKK anonimlestirme bekleyen sayisi okunamadi", exc_info=True)
        bekleyen = None
    return {
        "days": int(_kv.ESIK_GUN),
        "acknowledged": onayli,
        "pending": bekleyen,
        "approvedAt": (onay or {}).get("zaman") if onayli else None,
        "approvedCount": (onay or {}).get("sayi") if onayli else None,
    }


class _RetentionAyar(BaseModel):
    #: Saklama süresi (gün). 0 → maskeleme KAPALI (kayıtlar süresiz tam kalır).
    days: Optional[int] = None
    #: Operatör geri dönüşsüz maskelemeyi anladığını onaylıyor.
    acknowledge: bool = False
    #: D2.55 · A-09: onay ekranının GÖSTERDİĞİ süre — etkin süreden farklıysa onay yazılmaz (409; bayat ekrandan onay yok).
    acknowledge_days: Optional[int] = None
    #: D2.54 · A-06: operatör 5 yıl inaktif hastaların geri dönüşsüz anonimleştirmesini onaylıyor (o anki bekleyen sayıyla kayda geçer).
    anonymize_acknowledge: bool = False


@router.post("/api/settings/retention")
async def retention_ayarla(payload: _RetentionAyar, request: Request):
    """Süreyi ayarla ve/veya geri dönüşsüz maskelemeyi onayla.

    ⚠️ Onay AYRI bir alandır: süreyi değiştirmek tek başına maskelemeyi BAŞLATMAZ. Operatör
    "anladım" demeden hiçbir kayıt maskelenmez (bkz. apply_data_retention_policy).
    """
    from servers.auth import enforce_privileged

    enforce_privileged(request)
    if payload.days is not None and (payload.days < 0 or payload.days > 36500):
        raise HTTPException(status_code=400, detail="Saklama süresi 0–36500 gün aralığında olmalı.")
    try:
        # D2.55 (Ö.4-Y8): süre ve onay yazımları da olay döngüsü DIŞINDA — eskiden döngüde senkron yazılıyordu (D2.54 yalnız
        # anonimleştirme onayını taşımıştı); tedavi DB'si kilitliyken döngü donup ACİL DURDUR bekliyordu.
        db = await asyncio.to_thread(_pii_ayar_db)
        from servers import audit_log as _iz

        def _pii_yaz():
            """⚠️ D2.55 · A-09: süre DEĞİŞİNCE kayıtlı onay iptal edilir (geri dönüş eski onayı canlandırmaz); onay o anki etkin
            SÜREYE + kapsama + etkilenecek kayıt SAYISINA bağlı yazılır. `acknowledge_days` (ekranın gösterdiği süre) etkin süreden
            farklıysa HİÇBİR ŞEY yazılmaz → 409: operatör görmediği kapsamı onaylamış olmasın."""
            from servers.auth import cozumlenmis_operator

            secilen = db.pii_suresi_oku()
            onceki = secilen if secilen is not None else _pii_ortam_gunu()
            yeni = int(payload.days) if payload.days is not None else onceki
            if payload.acknowledge and payload.acknowledge_days is not None and int(payload.acknowledge_days) != yeni:
                return {"cakisma": yeni}
            sonuc = {"onceki": onceki, "yeni": yeni}
            if payload.days is not None:
                sonuc["onay_dustu"] = yeni != onceki and db.pii_onayi_var_mi(onceki)
                db.pii_suresi_yaz(payload.days)
                if yeni != onceki:
                    db.pii_onayi_iptal("sure_degisti")
            if payload.acknowledge:
                sayi = db.redaksiyon_bekleyen_sayisi(yeni) if yeni > 0 else 0
                db.pii_onayla(gun=yeni, sayi=sayi, kim=cozumlenmis_operator(request))
                sonuc["onay_sayi"] = sayi
            return sonuc

        s = await asyncio.to_thread(_pii_yaz)
        if "cakisma" in s:
            raise HTTPException(
                status_code=409,
                detail=f"Saklama süresi bu ekran açıldıktan sonra değişti ({s['cakisma']} gün). Ekranı yenileyin, etkilenecek "
                "kayıt sayısını görüp yeniden onaylayın — onay kaydedilmedi.",
            )
        if payload.days is not None:
            _iz.kimlikli_yaz(
                request,
                "retention.sure",
                scope="pii",
                item_count=int(payload.days),
                detail={"onceki": s["onceki"], "onay_dustu": bool(s.get("onay_dustu"))},
            )
        if payload.acknowledge:
            logger.warning(
                "KVKK: operatör geri dönüşsüz PII maskelemesini ONAYLADI (%d gün, %d kayıt).", s["yeni"], s["onay_sayi"]
            )
            # ⚠️ Bu onay, geri dönüşsüz maskelemenin ANAHTARIDIR. Kimin ve ne zaman verdiği
            # kayıtlı olmazsa, aylar sonra ortaya çıkan [REDACTED] kayıtların sorumlusu
            # bulunamaz — ve klinik haklı olarak "ben onaylamadım" der.
            _iz.kimlikli_yaz(
                request,
                "retention.onay",
                scope="pii",
                item_count=s["onay_sayi"],
                outcome="onaylandi",
                detail={"gun": s["yeni"]},
            )
        if payload.anonymize_acknowledge:
            # ⚠️ D2.54 · A-06 / A-09: onay ESİĞE ve o anki bekleyen SAYIYA bağlı yazılır (eşik değişirse geçersiz); kim, ne zaman, kaç
            # hasta — denetim izinde. DB işleri olay döngüsü DIŞINDA (Ö.4-Y8).
            def _anonim_onayla():
                from database.patient_database import get_patient_database
                from services import kvkk_anonimlestirme as _kv

                from servers.auth import cozumlenmis_operator

                sayi = _kv.bekleyen_sayisi(get_patient_database(), _kv.ESIK_GUN)
                db.anonim_onayi_yaz(gun=_kv.ESIK_GUN, sayi=sayi, kim=cozumlenmis_operator(request))
                return int(_kv.ESIK_GUN), sayi

            gun, sayi = await asyncio.to_thread(_anonim_onayla)
            logger.warning("KVKK: operator 5 yil inaktif hasta anonimlestirmesini ONAYLADI (%d hasta bekliyor).", sayi)
            _iz.kimlikli_yaz(
                request,
                "retention.anonim_onay",
                scope="kvkk",
                item_count=sayi,
                outcome="onaylandi",
                detail={"gun": gun},
            )
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception:
        logger.exception("retention ayarlanamadi")
        raise HTTPException(status_code=500, detail="Ayar kaydedilemedi.")


@router.get("/api/jeton/bakiye")
async def jeton_bakiye(request: Request):
    """Kullanıcının kalan jeton hakkı — arayüzdeki rozet bunu okur.

    ⚠️ NEDEN `ai_router`DA DEĞİL: o router'ın bağımlılıklarında `jeton_gate` var ve
    `_islem_turu` tanımadığı yolu "goruntu" (1 jeton) sınıfına düşürür → **bakiyeyi
    sormak jeton yakardı**. Sistem router'ı kapısızdır.

    ⚠️ Sözleşme `jeton.bakiye_ozeti` içinde: bayrak kapalıyken `etkin:false` (rozet
    çizilmez), okunamazsa `bilinmiyor:true` (arayüz "—" gösterir). Hiçbir koşulda
    UYDURMA bir sayı dönmez — "0 jeton" yazmak, sınırsız çalışan bir klinikte hakkı
    bitmiş gibi görünmek demektir.
    """
    from servers.jeton import bakiye_ozeti

    return await asyncio.to_thread(bakiye_ozeti, request)
