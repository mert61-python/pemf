"""Faz-1 (B-2.2 refactor-ÖNCESİ DAVRANIŞ KİLİDİ): api_server canlı-durum (live-state) çekirdeği.

`_live_state`, `update_live_*`, `_build_ws_snapshot`, `_push_notification`, `_emergency_stop_all`,
`get_active_session` — B-2.2 shared-state modül ayrımında TAŞINACAK olan çekirdek. Bu testler MEVCUT
davranışı kilitler → refactor sonrası AYNI testler yeşil kalmalı ("davranış değişmedi" kanıtı).

Tasarım: `_event_loop` None (TestClient yok) → `_ws_broadcast_sync` erken-return no-op; yalnız SAF
state geçişleri sınanır. `state.hardware` None (STM yok) + `_mqtt_publish` mock (broker yok) →
donanım/USB gerekmez. Hiç TestClient/thread yok → watchdog kurulan seansı bozamaz (deterministik)."""
import os

os.environ.pop("PEMF_SIMULATE", None)
import pytest


@pytest.fixture()
def api(monkeypatch):
    """İzole api_server: ESP publish mock + _live_state/_active_session bilinen temiz zemine sıfırla."""
    from servers import api_server

    monkeypatch.setattr(api_server, "_mqtt_publish", lambda *a, **k: True)
    with api_server._live_state_lock:
        for i in range(8):
            api_server._live_state["coils"][i].update({
                "connected": False, "running": False, "frequencyHz": 0, "dutyCycle": 0,
                "magneticMt": 0.0, "objectTemp": 0.0, "ambientTemp": 0.0, "currentA": 0.0,
                "stm32Driven": i < 5,
            })
        api_server._live_state["activeTreatment"].update({
            "mode": "Sistem Hazır", "frequencyHz": 0, "intensityMt": 0.0,
            "remainingMin": 0, "elapsedSec": 0, "durationSec": 0, "isActive": False,
        })
        api_server._live_state["notifications"].clear()
        api_server._live_state["stm"] = "warning"
        api_server._live_state["mqtt"] = "warning"
    with api_server._session_lock:
        api_server._active_session.clear()
    return api_server


# ── _build_ws_snapshot: WS ilk-bağlantı özeti sözleşmesi ──────────────────────
def test_build_ws_snapshot_shape(api):
    snap = api._build_ws_snapshot()
    # İstemci (React/WS) bu anahtarlara bağlı — refactor bunları KORUMALI.
    for key in ("gateway", "mqtt", "stm", "activeTreatment", "coils", "notifications", "system"):
        assert key in snap, f"WS snapshot '{key}' anahtarını kaybetti (istemci sözleşmesi kırıldı)"
    assert isinstance(snap["coils"], list) and len(snap["coils"]) == 8, "coils tam 8 bobin listesi olmalı"
    assert all("id" in c for c in snap["coils"]), "her bobin 'id' taşımalı"
    # notifications ilk-snapshot'ta en çok 10 (WS payload sınırı)
    assert len(snap["notifications"]) <= 10


# ── update_live_session_state: aktif-tedavi özeti (activeTreatment) ───────────
def test_update_live_session_state_activates(api):
    api.update_live_session_state(
        is_active=True, mode="AI", freq=50, intensity=2.0,
        remaining_min=20, elapsed_sec=5, duration_sec=1200,
    )
    at = api._live_state["activeTreatment"]
    assert at["isActive"] is True
    assert at["mode"] == "AI"
    assert at["frequencyHz"] == 50
    assert at["intensityMt"] == 2.0
    assert at["durationSec"] == 1200
    # Snapshot da aynısını yansıtmalı (React canlı bunu okur)
    assert api._build_ws_snapshot()["activeTreatment"]["isActive"] is True


def test_update_live_session_state_deactivates(api):
    api.update_live_session_state(is_active=True, mode="AI")
    api.update_live_session_state(is_active=False, mode="Sistem Hazır")
    assert api._live_state["activeTreatment"]["isActive"] is False
    assert api._live_state["activeTreatment"]["mode"] == "Sistem Hazır"


# ── update_live_coil_from_stm: STM USB → bobin durumu ────────────────────────
def test_update_live_coil_from_stm_updates_coil(api):
    api.update_live_coil_from_stm(coil_id=3, duty=25.0, freq=50, phase=0, duration_min=20, running=True)
    coil = api._live_state["coils"][2]  # coil_id 3 → index 2
    assert coil["connected"] is True
    assert coil["running"] is True
    assert coil["frequencyHz"] == 50
    assert coil["dutyCycle"] == 25.0
    assert coil["stm32Driven"] is True
    assert api._live_state["stm"] == "online", "STM verisi gelince stm 'online' olmalı"


def test_update_live_coil_from_stm_ignores_out_of_range(api):
    before = api._build_ws_snapshot()["coils"]
    # 0 ve 9 geçersiz (1-8 dışı) → sessizce yok sayılmalı, çökME/mutasyon YOK
    api.update_live_coil_from_stm(coil_id=0, duty=99, freq=99, phase=0, duration_min=1, running=True)
    api.update_live_coil_from_stm(coil_id=9, duty=99, freq=99, phase=0, duration_min=1, running=True)
    after = api._build_ws_snapshot()["coils"]
    assert after == before, "geçersiz coil_id live-state'i değiştirmemeli"


# ── update_live_stm_status + _sync_stm_coils_locked: STM bağlantısı → 1-5 bobin ─
def test_update_live_stm_status_syncs_stm_coils(api):
    api.update_live_stm_status(connected=True)
    assert api._live_state["stm"] == "online"
    for idx in range(5):  # bobin 1-5 STM-tahrikli → bağlı olmalı
        assert api._live_state["coils"][idx]["connected"] is True

    api.update_live_stm_status(connected=False)
    assert api._live_state["stm"] == "warning"
    for idx in range(5):  # STM düşünce 1-5 kopar + durur (güvenlik)
        assert api._live_state["coils"][idx]["connected"] is False
        assert api._live_state["coils"][idx]["running"] is False


# ── _push_notification: baş-ekle + 50-cap + monoton sayaç ────────────────────
def test_push_notification_front_insert_and_cap(api):
    for i in range(55):
        api._push_notification(f"olay-{i}", "info")
    notifs = api._live_state["notifications"]
    assert len(notifs) == 50, "bildirim listesi 50'de sınırlanmalı (bellek koruması)"
    # En yeni başta (insert(0, ...)) → ilk eleman en yüksek id
    assert notifs[0]["id"] > notifs[-1]["id"], "en yeni bildirim başa eklenmeli"
    assert notifs[0]["message"] == "olay-54"


# ── _emergency_stop_all: tüm bobin STOP + seans kapat + yanıt sözleşmesi ──────
def test_emergency_stop_all_ends_session_and_stops_coils(api):
    import time
    with api._session_lock:
        api._active_session.update({
            "is_active": True, "session_id": "es_test", "coil_ids": [6, 7, 8],
            "duration_minutes": 20, "start_time": time.time(),
        })
    # birkaç bobin "çalışıyor" görünsün → estop hepsini durdurmalı
    with api._live_state_lock:
        for idx in (0, 5, 6):
            api._live_state["coils"][idx].update({"running": True, "dutyCycle": 25.0})

    result = api._emergency_stop_all(reason="test")

    assert result["status"] == "success"
    assert result["reason"] == "test"
    with api._session_lock:
        assert api._active_session["is_active"] is False, "acil-durdurma seansı kapatmalı"
    for idx in range(8):  # TÜM bobinler durmalı + duty sıfırlanmalı (yanık/maruziyet riski)
        assert api._live_state["coils"][idx]["running"] is False
        assert api._live_state["coils"][idx]["dutyCycle"] == 0.0
    # ESP bobinleri (6,7,8) için MQTT stop sonucu dönmeli
    estopped = {r["coilId"] for r in result["mqttResults"]}
    assert estopped == {6, 7, 8}, "ESP bobinlerine (6-8) acil-stop publish edilmeli"


def test_emergency_stop_all_defaults_to_all_coils_without_session(api):
    # Seans yokken bile acil-durdurma TÜM transport'ları kapatmalı (fail-safe)
    result = api._emergency_stop_all(reason="manual")
    assert result["status"] == "success"
    estopped = {r["coilId"] for r in result["mqttResults"]}
    assert estopped == {6, 7, 8}, "seanssız estop ESP 6-8'i varsayılan kapsamalı"


# ── B-2.2 refactor kilidi: lifespan event-loop'u live_state'e bağlar (tek davranış-değişim noktası) ─
def test_lifespan_wires_event_loop_into_live_state():
    """Eskiden `api_server._event_loop` modül-global'iydi; B-2.2'de canlı-durum modülüne taşındı.
    lifespan STARTUP artık `live_state.set_event_loop()` çağırmalı → aksi halde thread'lerden gelen
    WS broadcast'ler sessizce no-op olur (istemci güncelleme almaz). Bu, refactor'un TEK gerçek
    davranış-değişim noktasını uçtan-uca kilitler."""
    from fastapi.testclient import TestClient

    from servers import api_server, live_state

    live_state.set_event_loop(None)  # sıfırla → lifespan'in GERÇEKTEN set ettiğini kanıtla
    with TestClient(api_server.app):  # lifespan STARTUP
        assert live_state._event_loop is not None, (
            "lifespan event-loop'u live_state'e bağlamadı → WS broadcast no-op (istemci canlı-güncelleme almaz)"
        )


# ── get_active_session: süre-dolmuş seansta SALT-OKUNUR (global mutasyon YOK) ──
def test_get_active_session_is_readonly_on_expiry(api):
    import asyncio
    import time
    with api._session_lock:
        api._active_session.update({
            "is_active": True, "session_id": "ro", "coil_ids": [6],
            "duration_minutes": 1, "start_time": time.time() - 120,  # 1dk seans, 2dk önce → dolmuş
        })
    # B-2.2: get_active_session servers/session_router.py'ye taşındı (davranış birebir; global _active_session'ı
    # lazy-import ile okur → aynı salt-okunur invariant). Test yeni konumu çağırır.
    from servers import session_router
    resp = asyncio.run(session_router.get_active_session())
    # Yanıtta süre-dolmuş → is_active False GÖSTERİLİR...
    assert resp["is_active"] is False
    assert resp["remaining_sec"] == 0
    # ...AMA global _active_session MUTATE EDİLMEZ — gerçek durdurma watchdog'un işi; GET onu bastıramaz
    with api._session_lock:
        assert api._active_session["is_active"] is True, (
            "get_active_session global state'i mutate etti → watchdog STOP'unu bastırıp "
            "bobinler fiziksel açık kalabilir (GÜVENLİK regresyonu)"
        )
