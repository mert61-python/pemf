# Author: mertaygn, cglrgrkn
"""Faz-1 (B-2.2 refactor-ÖNCESİ DAVRANIŞ KİLİDİ): api_server canlı-durum (live-state) çekirdeği.

`_live_state`, `update_live_*`, `_build_ws_snapshot`, `_push_notification`, `_emergency_stop_all`,
`get_active_session` — B-2.2 shared-state modül ayrımında TAŞINACAK olan çekirdek. Bu testler MEVCUT
davranışı kilitler → refactor sonrası AYNI testler yeşil kalmalı ("davranış değişmedi" kanıtı).

Tasarım: `_event_loop` None (TestClient yok) → `_ws_broadcast_sync` erken-return no-op; yalnız SAF
state geçişleri sınanır. `state.hardware` None (STM yok) + `_mqtt_publish` mock (broker yok) →
donanım/USB gerekmez. Hiç TestClient/thread yok → watchdog kurulan seansı bozamaz (deterministik)."""

import pytest
from topoloji import ESP_BOBIN, TUM_ESP, TUM_STM  # faz 4: literal bobin numarasi YASAK


@pytest.fixture()
def api(monkeypatch):
    """İzole api_server: ESP publish mock + _live_state/_active_session bilinen temiz zemine sıfırla."""
    from servers import api_server

    monkeypatch.setattr(api_server, "_mqtt_publish", lambda *a, **k: True)
    with api_server._live_state_lock:
        for i in range(8):
            api_server._live_state["coils"][i].update(
                {
                    "connected": False,
                    "running": False,
                    "frequencyHz": 0,
                    "dutyCycle": 0,
                    "magneticMt": 0.0,
                    "objectTemp": 0.0,
                    "ambientTemp": 0.0,
                    "currentA": 0.0,
                    # D0Ö.14 (B-10.140): üretimdeki gibi topolojiden (faz 4: bobin 1-7 STM); eskiden `i < 5`.
                    "stm32Driven": (i + 1) in TUM_STM,
                    "unipolar": None,
                }
            )
        api_server._live_state["activeTreatment"].update(
            {
                "mode": "Sistem Hazır",
                "frequencyHz": 0,
                "intensityMt": 0.0,
                "remainingMin": 0,
                "elapsedSec": 0,
                "durationSec": 0,
                "isActive": False,
            }
        )
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
        is_active=True,
        mode="AI",
        freq=50,
        intensity=2.0,
        remaining_min=20,
        elapsed_sec=5,
        duration_sec=1200,
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
    """D1.74 (B-1.19): bobin verisi STM BAĞLANTI DURUMUNU YAZMAZ — "online" yalnız `update_live_stm_status(True)`'dan
    gelir; bobinin `connected` alanı canlı STM durumundan türer. Bu test eskiden koşulsuz "online" yazımını PİNLİYORDU:
    kopuştan sonra firmware watchdog satırının SENTETİK sıfırlama yayını başlatma kapısını yeniden açıyordu."""
    api.update_live_stm_status(True)
    api.update_live_coil_from_stm(coil_id=3, duty=25.0, freq=50, phase=0, duration_min=20, running=True)
    coil = api._live_state["coils"][2]  # coil_id 3 → index 2
    assert coil["connected"] is True
    assert coil["running"] is True
    assert coil["frequencyHz"] == 50
    assert coil["dutyCycle"] == 25.0
    assert coil["stm32Driven"] is True
    assert api._live_state["stm"] == "online"

    api.update_live_stm_status(False)
    api.update_live_coil_from_stm(coil_id=3, duty=0.0, freq=0, phase=0, duration_min=0, running=False)
    assert api._live_state["stm"] == "warning", "bobin verisi kopuk STM'i 'online' yapmamali (D1.74)"
    assert api._live_state["coils"][2]["connected"] is False, "kopuk STM'de bobin 'bagli' gorundu"


def test_update_live_coil_from_stm_ignores_out_of_range(api):
    before = api._build_ws_snapshot()["coils"]
    # 0 ve 9 geçersiz (1-8 dışı) → sessizce yok sayılmalı, çökME/mutasyon YOK
    api.update_live_coil_from_stm(coil_id=0, duty=99, freq=99, phase=0, duration_min=1, running=True)
    api.update_live_coil_from_stm(coil_id=9, duty=99, freq=99, phase=0, duration_min=1, running=True)
    after = api._build_ws_snapshot()["coils"]
    assert after == before, "geçersiz coil_id live-state'i değiştirmemeli"


# ── update_live_stm_status + _sync_stm_coils_locked: STM bağlantısı → TÜM STM bobinleri ─
def test_update_live_stm_status_syncs_stm_coils(api, monkeypatch):
    """D0Ö.14 (B-10.140): kapsam `topoloji.TUM_STM`'den TÜRER ve bobinler kopuştan ÖNCE GERÇEKTEN çalışır.

    Eski hâli `range(5)`e bakıyordu (faz 4'te bobin 6-7 STM'e geçti, görünmüyordu) ve bobinleri hiç
    çalıştırmıyordu: fixture zaten `running=False` kurduğu için "STM düşünce durur" iddiası
    kendiliğinden doğruydu — sıfırlamayı `idx < 5` ile sınırlayan mutant YEŞİL kalıyordu. Bobin 6-7
    kopuşta "çalışıyor" kalsa arayüz onları sürülüyor sanar (İG-6.1 / B-1.19 / B-6.13 önkoşulu).

    D0Ö.14 ek (bağımsız inceleme tur 4): istemcinin GÖRDÜĞÜ şey `_live_state` değil WS YÜKÜDÜR —
    kopuşta `stm_status{connected: False}` ve her STM bobini için `stm_coil_update` yayını
    (connected/running False, kip None). Anlık görüntü sıfırlamadan önce alınsa ya da yayın döngüsü
    yalnız ilk 5 bobine gitse `_live_state` doğru kalır ama arayüz 6-7'yi çalışıyor görürdü.
    ⚠️ D0Ö.14 ek-2 (tur 5): yayın SIRASI bu kapının konusu DEĞİL — bugünkü sıra İG-6.1'in tetik
    dizisidir ve düzeltmesi onu değiştirecek (bkz. `test_KARAKTERIZASYON_kopus_yayin_SIRASI`).
    """
    from servers import live_state

    api.update_live_stm_status(connected=True)
    assert api._live_state["stm"] == "online"
    bagli_degil = [cid for cid in sorted(TUM_STM) if api._live_state["coils"][cid - 1]["connected"] is not True]
    assert not bagli_degil, f"STM bağlıyken bu STM bobinleri bağlı görünmüyor: {bagli_degil}"

    # Üretim yolu: her STM bobini ACK'le çalışıyor + firmware kipi bildirilmiş (ACK `K=`).
    for cid in sorted(TUM_STM):
        api.update_live_coil_from_stm(coil_id=cid, duty=25.0, freq=50, phase=0, duration_min=20, running=True)
        api.update_live_coil_kip(cid, True)
    kurulmayan = [
        cid
        for cid in sorted(TUM_STM)
        if api._live_state["coils"][cid - 1]["running"] is not True
        or api._live_state["coils"][cid - 1]["unipolar"] is not True
    ]
    assert not kurulmayan, f"kurulum: bu bobinler çalışır/kipli görünmüyor, kapı anlamsız olur: {kurulmayan}"

    yayinlar: list[dict] = []
    monkeypatch.setattr(live_state, "_ws_broadcast_sync", yayinlar.append)  # modül-içi global: yayın buradan
    api.update_live_stm_status(connected=False)
    assert api._live_state["stm"] == "warning"

    durumlar = [i for i, y in enumerate(yayinlar) if y.get("type") == "stm_status"]
    assert durumlar and yayinlar[durumlar[0]]["data"]["connected"] is False, f"stm_status yayını yok: {yayinlar}"
    bobin_yuku = {y["coilId"]: (i, y["data"]) for i, y in enumerate(yayinlar) if y.get("type") == "stm_coil_update"}
    yayinsiz = sorted(TUM_STM - set(bobin_yuku))
    assert not yayinsiz, f"kopuşta bu STM bobinleri için stm_coil_update YAYINLANMADI (arayüz bayat kalır): {yayinsiz}"
    # D0Ö.14 ek-2: `unipolar` anahtarı YOKSA da kırmızı — istemci `{...coil, ...data}` birleştirir, anahtarsız
    # yük önceki `unipolar: true`yu KORUR (kopuşta kip unutulmaz).
    yanlis_yuk = {
        cid: {k: veri.get(k, "ANAHTAR-YOK") for k in ("connected", "running", "unipolar")}
        for cid, (_i, veri) in bobin_yuku.items()
        if cid in TUM_STM
        and (
            veri.get("connected") is not False
            or veri.get("running") is not False
            or "unipolar" not in veri
            or veri["unipolar"] is not None
        )
    }
    assert not yanlis_yuk, f"istemciye giden yük kopmayı/durmayı söylemiyor (arayüz sürülüyor sanar): {yanlis_yuk}"
    kalan = {
        cid: {k: api._live_state["coils"][cid - 1][k] for k in ("connected", "running", "unipolar")}
        for cid in sorted(TUM_STM)
        if api._live_state["coils"][cid - 1]["connected"] is not False
        or api._live_state["coils"][cid - 1]["running"] is not False
        or api._live_state["coils"][cid - 1]["unipolar"] is not None
    }
    assert not kalan, f"STM düşünce bu STM bobinleri kopmadı/durmadı/kipi unutulmadı (güvenlik): {kalan}"


def test_KARAKTERIZASYON_kopus_yayin_SIRASI(api, monkeypatch):
    """KARAKTERİZASYON — kapı DEĞİL (D0Ö.14 ek-2, bağımsız inceleme tur 5): bugünkü kopuş yayın sırası
    önce `stm_status{connected: False}`, sonra her STM bobini için `stm_coil_update`.

    ⚠️ Bu sıra İG-6.1'in TETİK DİZİSİDİR (plan :458): arayüz sonradan gelen bobin yükünü birleştirirken
    STM'i yeniden "online" gösterebilir (`LiveDataContext.tsx` stm_coil_update dalı). İG-6.1 / B-1.19
    düzeltmesi bu sırayı BİLİNÇLİ değiştirir ve bu testi günceller — o zaman kırmızı bir REGRESYON değil,
    davranış değişikliğinin kaydıdır. (Tur 4'te bu iddia ana kapıda "ÖNCE geldi = kusur" diye yazılmıştı;
    geçerli bir İG-6.1 hafifletmesini regresyon diye adlandırırdı.)
    """
    from servers import live_state

    api.update_live_stm_status(connected=True)
    yayinlar: list[dict] = []
    monkeypatch.setattr(live_state, "_ws_broadcast_sync", yayinlar.append)
    api.update_live_stm_status(connected=False)
    turler = [y.get("type") for y in yayinlar if y.get("type") in ("stm_status", "stm_coil_update")]
    assert turler and turler[0] == "stm_status" and set(turler[1:]) == {"stm_coil_update"}, (
        f"kopuş yayın SIRASI değişti: {turler} — İG-6.1/B-1.19 düzeltmesi mi? Bu karakterizasyonu bilinçli güncelleyin."
    )


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
        api._active_session.update(
            {
                "is_active": True,
                "session_id": "es_test",
                "coil_ids": sorted(TUM_ESP),
                "duration_minutes": 20,
                "start_time": time.time(),
            }
        )
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
    assert estopped == TUM_ESP, "ESP bobinlerine (6-8) acil-stop publish edilmeli"


def test_emergency_stop_all_defaults_to_all_coils_without_session(api):
    # Seans yokken bile acil-durdurma TÜM transport'ları kapatmalı (fail-safe)
    result = api._emergency_stop_all(reason="manual")
    assert result["status"] == "success"
    estopped = {r["coilId"] for r in result["mqttResults"]}
    assert estopped == TUM_ESP, "seanssız estop ESP 6-8'i varsayılan kapsamalı"


def test_emergency_stop_all_ignores_narrow_session_scope(api, monkeypatch):
    """DENETIM P0 regresyonu: acil-durdurma ESP kapsamını AKTİF SEANSIN coil_ids'ine DARALTMAMALI.

    Hata: `_estop_coils = [cid for cid in coil_ids if cid in ESP_COIL_IDS]`. Seans coil_ids=[1,2,3]
    (yalnız STM) iken seans-DIŞI sürülen bobin 7'ye (ör. /api/coil/7/control) hiç stop yayınlanmıyor;
    üstelik boş mqtt_results `_esp_ok=True` sayıldığı için yanıt "success"/confirmed=True dönüyor ve
    canlı-durum 8 bobini de "durdu" gösteriyordu → operatöre YANLIŞ güvence. STM tarafı zaten
    koşulsuz stop_all_coils() çağırıyordu; bu asimetri hatanın kasıtsız olduğunun kanıtı.
    """
    import time

    published = []
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: published.append(topic) or True)

    with api._session_lock:
        api._active_session.update(
            {
                "is_active": True,
                "session_id": "narrow",
                "coil_ids": [1, 2, 3],
                "duration_minutes": 20,
                "start_time": time.time(),
            }
        )
    # Bobin 7 seans DIŞINDA sürülüyor
    with api._live_state_lock:
        api._live_state["coils"][6].update({"running": True, "dutyCycle": 40.0})

    result = api._emergency_stop_all(reason="test")

    estopped = {r["coilId"] for r in result["mqttResults"]}
    assert estopped == TUM_ESP, f"dar seans kapsamı ESP stop'unu daraltmamalı; gelen: {estopped}"
    # FAZ 4: bobin 7 STM'e tasindi → "seans-disi ESP bobini" artik TUM_ESP'in bir uyesi.
    # Iddia AYNI: acil durdurma seans kapsamiyla SINIRLANDIRILAMAZ.
    _disari = max(TUM_ESP)
    assert any(f"/{_disari}/" in t for t in published), f"seans-disi bobin {_disari}'ye STOP publish edilmeliydi"
    # Seans kapsamı ARTIK yalnız denetim izinde; durdurma kapsamını belirlemez.
    assert result["sessionCoilIds"] == [1, 2, 3]


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
        api._active_session.update(
            {
                "is_active": True,
                "session_id": "ro",
                "coil_ids": [ESP_BOBIN],
                "duration_minutes": 1,
                "start_time": time.time() - 120,  # 1dk seans, 2dk önce → dolmuş
            }
        )
    # B-2.2: get_active_session apps/backend/servers/session_router.py'ye taşındı (davranış birebir; global _active_session'ı
    # lazy-import ile okur → aynı salt-okunur invariant). Test yeni konumu çağırır.
    from servers import session_router

    resp = session_router.get_active_session()  # P-1a: async def -> def (FastAPI threadpool); artık senkron
    # Yanıtta süre-dolmuş → is_active False GÖSTERİLİR...
    assert resp["is_active"] is False
    assert resp["remaining_sec"] == 0
    # ...AMA global _active_session MUTATE EDİLMEZ — gerçek durdurma watchdog'un işi; GET onu bastıramaz
    with api._session_lock:
        assert api._active_session["is_active"] is True, (
            "get_active_session global state'i mutate etti → watchdog STOP'unu bastırıp "
            "bobinler fiziksel açık kalabilir (GÜVENLİK regresyonu)"
        )


def test_ws_broadcast_closes_dead_clients_and_bounds_backlog(api):
    """DENETIM P2 regresyonu: ölü WS istemcisi KAPATILMALI + yayın kuyruğu SINIRLI olmalı.

    (1) Yanıt vermeyen istemci yayın listesinden çıkarılıyordu ama SOKET kapatılmıyordu →
        istemci kendini 'bağlı' sanıp DONMUŞ telemetri gösteriyor, reconnect de tetiklenmiyordu.
    (2) Her yayın için ayrı coroutine planlanıp tek kilitte sıraya giriyordu; yavaş bir istemci
        her turda 5 sn tuttuğu için arkada sınırsız iş + JSON gövdesi birikiyordu.

    ⚠️ D0Ö.14 (B-10.141): bu iki iddia artık KAYNAK METNİYLE değil DAVRANIŞLA ölçülür
    (`test_KRITIK_ws_olu_istemci_KAPATILIR_ve_geri_basinc_sayaci_SIZMAZ`). Eski `".close(" in src`
    denetimi kapatma satırı yoruma alınınca da yeşildi (yorum metni `.close(` içerir); sayaç
    denetimi yalnız erken-dönüş yoluna bakıyordu.
    """
    from servers import live_state

    assert live_state._WS_MAX_PENDING_BROADCASTS > 0

    # Sayaç sızmamalı: event-loop yokken erken dönüşte artırılmamalı
    before = live_state._ws_pending
    live_state._ws_broadcast_sync({"type": "noop"})
    assert live_state._ws_pending == before, "erken dönüşte bekleyen sayacı sızmamalı"


def test_KRITIK_ws_olu_istemci_KAPATILIR_ve_geri_basinc_sayaci_SIZMAZ(monkeypatch):
    """D0Ö.14 (B-10.141): GERÇEK `_ws_broadcast_sync` yeni bir event loop'a, `send_text`'te hata atan
    sahte (ölü) istemciye karşı koşar.

    Sınırın bir fazlası kadar yayın: sınırda DURUR (biri düşürülür, sayaç +1), döngü koşunca
    `_ws_pending` BAŞLANGIÇ değerine döner (her planlanan gönderim `finally`'de geri sayar), ölü
    istemci listeden ÇIKAR ve soketi 1011 ile KAPATILIR (istemci kopmayı görüp yeniden bağlansın).
    MUTASYON: `finally`'deki `_ws_pending -= 1` → `-= 0` ya da `await d.close(...)` yoruma → KIRMIZI.
    """
    import asyncio

    from servers import live_state

    class _OluIstemci:
        def __init__(self):
            self.gonderim = 0
            self.kapatmalar = []

        async def send_text(self, data):
            self.gonderim += 1
            raise ConnectionResetError("d0o14: istemci öldü")

        async def close(self, code=None):
            self.kapatmalar.append(code)

    olu = _OluIstemci()
    dongu = asyncio.new_event_loop()
    monkeypatch.setattr(live_state, "_event_loop", dongu)
    monkeypatch.setattr(live_state, "_ws_clients", [olu])
    monkeypatch.setattr(live_state, "_ws_send_lock", None)  # kilit bu döngüde taze kurulsun
    monkeypatch.setattr(live_state, "_ws_pending", 0)
    monkeypatch.setattr(live_state, "_ws_dropped_total", live_state._ws_dropped_total)
    sinir = live_state._WS_MAX_PENDING_BROADCASTS
    dusen_once = live_state._ws_dropped_total
    try:
        # D1.71: sınırda düşen artık EN ESKİ PERİYODİK iletidir; bilinmeyen/tek seferlik tür ASLA düşmez → kapı periyodik
        # türle (telemetri) doldurur. İddia aynı: sınırda durur, düşürme sayılır, sayaç sızmaz.
        for i in range(sinir + 1):
            live_state._ws_broadcast_sync({"type": "sensor_data", "n": i})
        assert live_state._ws_pending == sinir, f"geri-basınç sınırda durmadı: {live_state._ws_pending} != {sinir}"
        assert live_state._ws_dropped_total == dusen_once + 1, "sınırı aşan yayın düşürülüp SAYILMADI"
        for _ in range(200):
            dongu.run_until_complete(asyncio.sleep(0.005))
            if live_state._ws_pending == 0:
                break
    finally:
        dongu.close()
    assert olu.gonderim >= 1, "kurulum: gönderim hiç denenmedi, kapı anlamsız olur"
    assert live_state._ws_pending == 0, (
        f"bekleyen yayın sayacı SIZDI: {live_state._ws_pending} (başlangıç 0) — sınıra takılan sunucu "
        "bundan sonra HER yayını düşürür, istemciler donmuş telemetri görür"
    )
    assert olu not in live_state._ws_clients, "ölü istemci yayın listesinden çıkarılmadı"
    assert olu.kapatmalar, "ölü istemcinin soketi KAPATILMADI — istemci kendini bağlı sanıp yeniden bağlanmaz"
    assert set(olu.kapatmalar) == {1011}, f"kapatma kodu 1011 (sunucu düşürdü) değil: {set(olu.kapatmalar)}"


def test_ws_IPTAL_edilen_gonderim_de_sayaci_geri_sayar(monkeypatch):
    """D0Ö.14 ek: geri sayım `finally`'de olmalı — `CancelledError` (BaseException) gönderimdeki
    `except Exception`a YAKALANMAZ; sayım `try` gövdesinin sonuna taşınsa İPTAL yolunda (ör. döngü
    kapanışında görev iptali) sayaç SIZAR. Ölü-istemci kapısı bunu ayırt edemez (orada her hata
    yakalanır). (D0Ö.14 ek-2: çalışma sırasında tekrarlanan bir iptal kaynağı GÖSTERİLMEDİ — iptal
    yalnız kapanıştaysa sızıntının etkisi sınırlıdır; kapı `finally` yerleşimini pinler.)"""
    import asyncio

    from servers import live_state

    class _IptalIstemci:
        def __init__(self):
            self.gonderim = 0

        async def send_text(self, data):
            self.gonderim += 1
            raise asyncio.CancelledError()

        async def close(self, code=None):
            pass

    istemci = _IptalIstemci()
    dongu = asyncio.new_event_loop()
    monkeypatch.setattr(live_state, "_event_loop", dongu)
    monkeypatch.setattr(live_state, "_ws_clients", [istemci])
    monkeypatch.setattr(live_state, "_ws_send_lock", None)
    monkeypatch.setattr(live_state, "_ws_pending", 0)
    monkeypatch.setattr(live_state, "_ws_dropped_total", live_state._ws_dropped_total)
    try:
        for i in range(5):
            live_state._ws_broadcast_sync({"type": "d0o14-iptal", "n": i})
        assert live_state._ws_pending == 5
        for _ in range(200):
            dongu.run_until_complete(asyncio.sleep(0.005))
            if live_state._ws_pending == 0:
                break
    finally:
        dongu.close()
    assert istemci.gonderim >= 1, "kurulum: gönderim hiç denenmedi, kapı anlamsız olur"
    assert live_state._ws_pending == 0, f"iptal edilen gönderimde sayaç SIZDI: {live_state._ws_pending}"


def test_ws_bekleyen_sayaci_HER_gonderimde_BIRER_azalir(monkeypatch):
    """D0Ö.14 ek-2 (bağımsız inceleme tur 5): geri sayım `-= 1` olmalı. `finally`'de sayacı SIFIRLAYAN
    mutant (`_ws_pending = 0`) iki WS kapısında da yeşildi — ikisi de yalnız SON değere (0) bakıyordu.
    O mutantta her tamamlanan gönderim sayacı sıfırlar; yavaş istemcide sınır her turda 64 yeni yer açar
    ve P2'nin sınırsız birikimi geri gelir. İstemci her gönderimde bir izin bekler: her izinde TAM BİR
    gönderim tamamlanır ve sayaç TAM BİR azalır."""
    import asyncio

    from servers import live_state

    class _KademeliIstemci:
        def __init__(self):
            self.izin = asyncio.Event()
            self.gonderim = 0

        async def send_text(self, data):
            await self.izin.wait()
            self.izin.clear()
            self.gonderim += 1

        async def close(self, code=None):
            pass

    istemci = _KademeliIstemci()
    dongu = asyncio.new_event_loop()
    monkeypatch.setattr(live_state, "_event_loop", dongu)
    monkeypatch.setattr(live_state, "_ws_clients", [istemci])
    monkeypatch.setattr(live_state, "_ws_send_lock", None)
    monkeypatch.setattr(live_state, "_ws_pending", 0)
    monkeypatch.setattr(live_state, "_ws_dropped_total", live_state._ws_dropped_total)
    n = 4
    gorulen = []
    try:
        for i in range(n):
            live_state._ws_broadcast_sync({"type": "d0o14-kademe", "n": i})
        dongu.run_until_complete(asyncio.sleep(0.02))
        gorulen.append(live_state._ws_pending)
        for _ in range(n):
            istemci.izin.set()
            dongu.run_until_complete(asyncio.sleep(0.02))
            gorulen.append(live_state._ws_pending)
    finally:
        istemci.izin.set()
        for _ in range(50):
            if live_state._ws_pending <= 0:
                break
            istemci.izin.set()
            dongu.run_until_complete(asyncio.sleep(0.005))
        dongu.close()
    assert istemci.gonderim == n, f"kurulum: {istemci.gonderim}/{n} gönderim tamamlandı"
    assert gorulen == list(range(n, -1, -1)), (
        f"bekleyen sayacı her gönderimde BİRER azalmadı: {gorulen} (beklenen {list(range(n, -1, -1))}) — "
        "sayaç sıfırlanıyorsa sınır yavaş istemcide sürekli yeniden açılır (P2 birikimi)"
    )


@pytest.fixture(autouse=True)
def _aktif_seans_SIZMAZ():
    """D1.41 (B-10.243): bu dosyanın testleri seansı AKTİF bırakıyordu (tam süitte ölçüldü) — sonraki dosyanın
    ilk seans testi 409 alır, çalışan bir süre-watchdog'u başka testin seansını durdururdu. Test sonrası
    seans durumu temizlenir; `conftest._seans_ve_watchdog_nobeti` bunu doğrular."""
    yield
    from servers import api_server as _api

    with _api._session_lock:
        _api._active_session.clear()
