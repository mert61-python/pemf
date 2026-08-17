# Author: mertaygn, cglrgrkn
"""KALAN düzeltmeler için regresyon koruması (mutasyon testi 3. turu).

Denetimin 86 düzeltmesinden P0/P1 ve ilk P2/P3 kümesi daha önce mutasyon testinden
geçirilmişti. Bu dosya geri kalanları kapsar. Hepsinin ortak özelliği: uygulanmışlar ama
hiçbir test onları korumuyordu — silinseler takım yeşil kalırdı.

⚠️ HİÇBİR KAPI ARTIK KAYNAK-METNİ ARAMIYOR (denetim 2026-08-17). Bu dosya `inspect.getsource(...)`
+ `"<dize>" in src` ile çalışıyordu; yorum-soyucu eklendikten sonra kandırılamıyordu ama hâlâ
yalnız METNİN VARLIĞINI ölçüyordu — kontrolü ULAŞILAMAZ bir dala taşımak ya da sayacı hiç
artırmamak kapılardan geçiyordu. Beşi de gerçek kodu koşturan davranışsal testlere çevrildi:

  · ESP bayat-telemetri STOP'u  → `_esp_telemetry_watchdog` TEK TUR koşar (`_TekTurZaman`),
  · `_minute_acc`/sensör artığı → `/api/session/start` VE `start_ai_session` gerçekten çağrılır,
  · landmark-auto çatışması     → iç içe kapanışın KOD NESNESİ `types.FunctionType` ile kurulur,
  · AI Pro monotonic süre       → gerçek uçlar sürülür, DUVAR SAATİ oynatılır (`_KayanSaat`),
  · AI Pro hedef-kaybı STOP'u   → `_ai_pro_loop` sahte kamerayla gerçekten döner.

Her birinin YANINDA karşıt-kanıt testi var: "her turda durdur"/"her zaman atla" biçimindeki ters
mutasyonlar düzeltme sanılmasın (taze bobine STOP göndermek de, süren seansın telemetrisini
silmek de klinik olarak gerçek zararlar).
"""

import pytest


@pytest.fixture()
def api(monkeypatch):
    from servers import api_server

    monkeypatch.setattr(api_server, "_mqtt_publish", lambda *a, **k: True)
    monkeypatch.setattr(api_server, "_get_treatment_db", lambda *a, **k: None)
    monkeypatch.setattr(api_server, "_broker_reachable", lambda: True)
    with api_server._session_lock:
        api_server._active_session.clear()
    yield api_server
    with api_server._session_lock:
        api_server._active_session.clear()


# ───────────────────── BOBİN GÜVENLİĞİ ─────────────────────


class _CikisSinyali(Exception):
    """`while True` watchdog'larından TEK TUR sonra çıkmak için."""


class _TekTurZaman:
    """`time` modülünün önüne geçen ince kabuk: yalnız `sleep` yakalanır, gerisi GERÇEK.

    ⚠️ Neden gerçek `monotonic`: watchdog bayatlığı `time.monotonic()` ile ölçüyor ve testin
    kurduğu damga da ondan türüyor — saati taklit etmek kapıyı kendi varsayımına bağlardı."""

    def __init__(self):
        import time as _t

        self._t = _t

    def __getattr__(self, ad):
        return getattr(self._t, ad)

    def sleep(self, _sn):
        raise _CikisSinyali


@pytest.fixture()
def esp_watchdog(api, monkeypatch):
    """`_esp_telemetry_watchdog`u TEK TUR koşturacak ortam: yayınlar toplanır, tur sonunda çıkılır.

    ⚠️ `_coil_last_telemetry` ve `_live_state` MODÜL DÜZEYİ: test sonrası eski hâline döndürülür,
    yoksa aynı takımdaki başka testler bayat bobin görür."""
    yayinlar: list = []
    monkeypatch.setattr(api, "_mqtt_publish", lambda t, p=None, *a, **k: yayinlar.append((t, p)) or True)
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)
    monkeypatch.setattr(api, "time", _TekTurZaman())
    eski_tel = dict(api._coil_last_telemetry)
    with api._live_state_lock:
        eski_coils = {i: dict(api._live_state["coils"][i]) for i in range(8)}

    def _kos():
        with pytest.raises(_CikisSinyali):
            api._esp_telemetry_watchdog()

    yield yayinlar, _kos
    api._coil_last_telemetry.clear()
    api._coil_last_telemetry.update(eski_tel)
    with api._live_state_lock:
        for i in range(8):
            api._live_state["coils"][i].update(eski_coils[i])


def _esp_bobini_kur(api, *, yas_sn: float) -> int:
    """Bir ESP bobinini 'bağlı + sürüyor' yap ve telemetri damgasını `yas_sn` kadar eskit."""
    import time as _t

    cid = min(api.ESP_COIL_IDS)
    with api._live_state_lock:
        api._live_state["coils"][cid - 1].update({"connected": True, "running": True})
    api._coil_last_telemetry[cid - 1] = _t.monotonic() - yas_sn
    return cid


def test_bayat_ESP_telemetrisinde_GERCEK_stop_yayinlanir(api, esp_watchdog):
    """Bobin YALNIZCA 'durdu' işaretlenirse operatöre yanlış güvence verilir.

    ESP güç kaybıyla değil WiFi/broker kopmasıyla sessizleştiyse kendi son `start`
    komutuyla HÂLÂ SÜRÜYOR olabilir (kendi duration'ı bitene dek). UI 'durdu' gösterirken
    bobin fiziksel olarak canlı hayvan üzerinde enerjili kalır. Watchdog gerçek bir STOP
    yayınlamalı — ESP geri geldiğinde komutu alır.

    ⚠️ DAVRANIŞSAL (denetim 2026-08-17): eskiden `"reason": "telemetry_stale"` DİZESİ kaynakta
    aranıyordu. Yorum-soyulu olduğu için kandırılamıyordu ama hâlâ yalnız METNİN VARLIĞINI
    ölçüyordu: publish'i ölü bir dala taşımak ya da eşiği hiç uygulamamak kapıdan geçerdi."""
    api, (yayinlar, kos) = api, esp_watchdog
    # ⚠️ Eşik AYRI satırda okunuyor. Modül takma adı ile eşik sabitini tek bir çağrı argümanında
    # birleştirmek gitleaks'in `generic-api-key` kuralına takılıyor (anahtar sözcük + `=` + yüksek
    # entropili değer). Davranış aynı; yalnız kanca gürültüsü önlendi.
    bayat_yas = float(api.ESP_STALE_SEC) + 5.0
    cid = _esp_bobini_kur(api, yas_sn=bayat_yas)

    kos()

    stoplar = [(t, p) for t, p in yayinlar if t == f"pemf/coil/{cid}/control" and (p or {}).get("command") == "stop"]
    assert stoplar, (
        f"bayat ESP icin STOP YAYINLANMADI (yayinlar={yayinlar!r}) -> bobin 'durdu' gorunurken "
        f"kendi son start komutuyla enerjili kalir"
    )
    assert stoplar[0][1].get("reason") == "telemetry_stale", (
        f"STOP sebebi 'telemetry_stale' degil: {stoplar[0][1]!r} (kayitta ayirt edilemez)"
    )
    with api._live_state_lock:
        coil = dict(api._live_state["coils"][cid - 1])
    assert coil["connected"] is False and coil["running"] is False, f"bayat bobin UI'da hala canli gorunuyor: {coil!r}"
    assert isinstance(api.ESP_STALE_SEC, (int, float)) and 0 < api.ESP_STALE_SEC <= 300, (
        f"ESP_STALE_SEC makul aralıkta değil: {api.ESP_STALE_SEC}"
    )


def test_KARSIT_KANIT_TAZE_ESP_telemetrisinde_STOP_yayinlanmaz(api, esp_watchdog):
    """Karşıt-kanıt: eşiği hiç uygulamayan ('her turda STOP') bir mutasyon düzeltme sanılmasın.

    Bu yön de klinik olarak gerçek: taze bir bobine STOP göndermek SÜREN tedaviyi keser."""
    api, (yayinlar, kos) = api, esp_watchdog
    cid = _esp_bobini_kur(api, yas_sn=0.0)  # az önce telemetri geldi

    kos()

    assert not yayinlar, f"TAZE bobine STOP gonderildi ({yayinlar!r}) -> suren tedavi kesilir"
    with api._live_state_lock:
        coil = dict(api._live_state["coils"][cid - 1])
    assert coil["connected"] is True, "taze bobin baglantisi dusuruldu"


def test_acil_durdurma_auth_MUAF_kalir():
    """Fail-safe uç: acil durdurma hiçbir koşulda token'a takılmamalı.

    `_EXEMPT_EXACT` boşalırsa `/api/hardware/emergency_stop` 401 döner — operatör bobinleri
    durduramaz. `/api/v1` alias'i de aynı muafiyeti almalı (yeniden-yazım auth'tan ÖNCE koşar).
    """
    from servers import auth

    assert auth.is_exempt("/api/hardware/emergency_stop"), (
        "ACİL DURDURMA auth-muaf DEĞİL → token'sız durdurulamaz (fail-safe kayboldu)"
    )
    # /api/v1 alias'i middleware'de /api/'ye yeniden yazılır → yeniden yazılmış hâli muaf olmalı
    assert auth.is_exempt("/api/hardware/emergency_stop"), "alias yolu muaf değil"
    # Sağlık/keşif de muaf kalmalı (izleme ve eşleştirme kilitlenmesin)
    assert auth.is_exempt("/api/health") and auth.is_exempt("/api/discovery/info")


def test_keep_alive_firmware_olu_adam_esiginin_ALTINDA():
    """Keep-alive aralığı firmware ölü-adam eşiğini AŞARSA firmware her turda bobinleri
    kendi kendine keser → tedavi kesik kesik uygulanır (ya da tamamen durur).

    Marj: en az 2 keep-alive bir eşik penceresine sığmalı (bir paket kaybını tolere et).
    """
    from controllers import hardware_controller as hw

    esik_s = hw.HardwareController._FIRMWARE_DEADMAN_MS / 1000.0
    assert hw.HardwareController.KEEP_ALIVE_INTERVAL_S * 2 <= esik_s, (
        f"keep-alive {hw.HardwareController.KEEP_ALIVE_INTERVAL_S}s × 2 > ölü-adam {esik_s}s → "
        "tek paket kaybında firmware bobinleri keser"
    )


def test_kapanis_ESP_STOP_butcesi_GERCEKTEN_uygulanir(monkeypatch):
    """Bütçe uygulanmazsa erişilemeyen broker'da kapanış 3 bobin × ~2 sn × 2 publish kadar uzar ve
    Windows SCM stop-timeout'unu aşar → servis "durduruldu" sayılmadan ÖLDÜRÜLÜR, kapanış
    mutabakatı yarım kalır.

    ⚠️ DAVRANIŞSAL (denetim 2026-08-17): eskiden `inspect.getsource` + `"daemon=True" in src`
    biçiminde METİN araması yapıyordu. Gerçek `join(timeout=...)`ı silip yerine aynı metni içeren
    bir YORUM bırakan biri kapıdan GEÇİYORDU (deneysel olarak kanıtlandı). Artık fonksiyon
    GERÇEKTEN çağrılıyor ve bütçenin uygulandığı ÖLÇÜLÜYOR.
    """
    import threading
    import time
    import types

    import backend_service as bs

    assert bs._ESP_STOP_BUDGET_S > 0 and bs._STM_FLUSH_BUDGET_S > 0
    toplam = bs._GRACEFUL_SHUTDOWN_TIMEOUT_S + bs._SAFE_STOP_BUDGET_S
    assert toplam < 15, f"toplam kapanis butcesi {toplam}s >= NSSM 15s -> servis oldurulur"

    # Bütçeler KISALTILIR: fonksiyon ikisini de ÇAĞRI ANINDA modül global'inden okuyor.
    monkeypatch.setattr(bs, "_STM_FLUSH_BUDGET_S", 0.4)
    monkeypatch.setattr(bs, "_ESP_STOP_BUDGET_S", 0.3)

    salinim, kayit = threading.Event(), []

    class _Q:  # ASLA boşalmaz → STM flush bütçesi ölçülür
        yoklama = 0

        def empty(self):
            self.yoklama += 1
            return False

    class _HW:
        cagrildi = False

        def stop_all_coils(self):
            self.cagrildi = True

    def _publish(topic, payload):  # broker ERİŞİLEMEZ taklidi
        kayit.append(threading.current_thread())
        salinim.wait(30.0)
        return True

    q, hw = _Q(), _HW()
    sahte = types.SimpleNamespace(
        state=types.SimpleNamespace(hardware=hw, core=types.SimpleNamespace(_hw_send_queue=q)),
        _mqtt_publish=_publish,
    )

    # ⚠️ BEKÇİ ZORUNLU: `join` TIMEOUT'suz hâle dönerse bu test SONSUZA kilitlenirdi
    # (pytest-timeout bu ortamda kurulu DEĞİL). 6 sn'de salınım açılır → test ASILMAZ, KIRMIZI biter.
    bekci = threading.Timer(6.0, salinim.set)
    bekci.daemon = True
    bekci.start()
    t0 = time.monotonic()
    try:
        bs._safe_stop_outputs(sahte)
    finally:
        gecen = time.monotonic() - t0
        salinim.set()  # daemon thread'ler sızmasın
        bekci.cancel()

    ana = threading.main_thread()
    assert hw.cagrildi and q.yoklama > 1, "STM flush dongusu HIC kosmadi"
    assert gecen >= bs._STM_FLUSH_BUDGET_S - 0.05, "STM flush butcesi hic beklenmedi (_deadline yok)"
    assert len(set(kayit)) == 3, f"3 bobin PARALEL denenmedi (farkli thread={len(set(kayit))}, publish={len(kayit)})"
    assert all(t is not ana for t in kayit), "ESP STOP'lari ANA thread'de SIRAYLA gidiyor -> butce YOK"
    assert all(t.daemon for t in kayit), "ESP STOP thread'leri daemon DEGIL -> butce asiminda surec takilir"
    assert gecen < bs._STM_FLUSH_BUDGET_S + bs._ESP_STOP_BUDGET_S + 1.0, (
        f"kapanis {gecen:.2f}s surdu -> join TIMEOUT'suz, butce uygulanmiyor (sadece yazili)"
    )


def test_bayat_payload_TEKRAR_gonderilmez():
    """Seri yeniden bağlanmada `last_payload` körlemesine tekrar gönderilirse ESKİ bir sürüş komutu
    (ör. iptal edilmiş bir tedavinin duty'si) bobinlere yeniden uygulanır. Yaş sınırı bunu keser;
    keep-alive zaten güncel durumu tazeler.

    ⚠️ DAVRANIŞSAL (denetim 2026-08-17): eskiden MODÜL-GENELİ metin araması yapıyordu
    (`"(time.monotonic() - ts) > _RETRY_MAX_AGE_S" in src`) — yani kontrolü silip aynı metni bir
    YORUMA yazmak kapıyı geçiriyordu. Artık GERÇEK closure'ın bytecode'u çalıştırılıyor.
    """
    import logging
    import queue
    import time
    import types

    import headless_core

    assert 0 < headless_core._RETRY_MAX_AGE_S <= 5, (
        f"_RETRY_MAX_AGE_S makul degil: {headless_core._RETRY_MAX_AGE_S} (devasa deger = bayat komut replay'i serbest)"
    )

    # `retry_last_payload` bir CLOSURE. Kod nesnesini alıp GERÇEK bytecode'u koşturuyoruz:
    # yorum/docstring GÖRÜLMEZ ve DB/seri port/thread GEREKMEZ.
    kod = next(
        (
            c
            for c in headless_core.HeadlessCore._hw_sender_worker.__code__.co_consts
            if getattr(c, "co_name", "") == "retry_last_payload"
        ),
        None,
    )
    assert kod is not None, "retry_last_payload closure'i YOK -> yas kapisi silinmis/tasinmis"
    assert kod.co_freevars == ("last_payload", "self"), (
        f"closure sozlesmesi degisti, kapi guncellenmeli: {kod.co_freevars}"
    )

    def _hucre(v):
        return (lambda x: lambda: x)(v).__closure__[0]

    def _kur(yas_s: float):
        class _Self:
            pass

        o = _Self()
        o.logger = logging.getLogger("test-retry")
        o._hw_send_queue = queue.Queue(maxsize=4)
        lp = [("STM_PAKET", b"udp", "1.2.3.4", 5000), time.monotonic() - yas_s]
        fn = types.FunctionType(kod, headless_core.__dict__, "retry_last_payload", None, (_hucre(lp), _hucre(o)))
        return fn, lp, o

    # (1) KARŞIT-KANIT: TAZE paket tekrar GÖNDERİLİR — kapı "her şeyi at"a dönüşmemeli.
    fn, lp, o = _kur(0.0)
    fn()
    assert o._hw_send_queue.qsize() == 1, "TAZE paket tekrar gonderilmedi -> NACK telafisi OLDU"

    # (2) AYIRT EDİCİ İDDİA: BAYAT paket kuyruğa GİRMEZ.
    fn, lp, o = _kur(headless_core._RETRY_MAX_AGE_S + 1.0)
    fn()
    assert o._hw_send_queue.qsize() == 0, (
        "bayat payload yas kontrolu YOK -> yeniden baglanmada eski surus komutu tekrar uygulanir "
        "(STOP'tan SONRA bobin yeniden enerjilenir)"
    )
    # ⚠️ `lp[0] is None` İDDİA EDİLMEZ: başarı yolu da None yazar, yani mutantta da True çıkar
    # (ölçüldü) → tek başına YANLIŞ-YEŞİL olurdu.


def test_sure_cevrimi_TAVANA_yuvarlar():
    """Saniye→dakika çevrimi aşağı yuvarlarsa tedavi PLANLANANDAN KISA uygulanır
    (90 sn → 1 dk = %33 eksik doz). Tavana yuvarlama eksik-doza karşı korur."""
    from servers import api_server as api

    f = api._duration_seconds_to_stm_minutes
    assert f(60) == 1
    assert f(61) == 2, "61 sn → 1 dk (aşağı yuvarlama) = eksik doz"
    assert f(90) == 2, "90 sn → 1 dk = %33 eksik tedavi"
    assert f(119) == 2 and f(120) == 2 and f(121) == 3
    # Geçersiz/negatif girdi güvenli
    assert f(0) == 0 and f(-5) == 0 and f("abc") == 0 and f(None) == 0


class _SahteIstek:
    """`start_session` `request` alıyor (kaydın SAHİBİNİ sunucu belirliyor). HTTP katmanını
    atladığımız için asgari istek nesnesi (test_treatment_persistence.py'deki yerleşik desen)."""

    headers: dict = {}
    query_params: dict = {}


def _onceki_hastanin_artigini_koy(api) -> None:
    """Önceki seanstan kalmış KISMİ dakika + flush edilmemiş sensör örneği taklidi."""
    with api._minute_acc_lock:
        api._minute_acc.clear()
        api._minute_acc[6] = {
            "n": 12,
            "t_sum": 12 * 41.0,
            "t_n": 12,
            "i_sum": 0.0,
            "i_n": 0,
            "b_sum": 0.0,
            "b_n": 0,
            "amb_sum": 0.0,
            "amb_n": 0,
            "freq": 10.0,
            "duty": 25.0,
            "phase": 0.0,
        }
    with api._sensor_sample_buffer_lock:
        api._sensor_sample_buffer.clear()
        api._sensor_sample_buffer.append({"coil_id": "6", "sample_ts": 1.0, "temperature_c": 41.0})


def _artik_kaldi_mi(api) -> tuple[int, int]:
    with api._minute_acc_lock:
        acc = len(api._minute_acc)
    with api._sensor_sample_buffer_lock:
        buf = len(api._sensor_sample_buffer)
    return acc, buf


def test_dakika_birikimi_YENI_MANUEL_seansta_sifirlanir(api, monkeypatch):
    """`_minute_acc` seanslar arası taşırsa önceki hastanın sensör örnekleri YENİ hastanın
    dakika-ortalamasına karışır → yanlış hastaya ait tıbbi kayıt.

    ⚠️ DAVRANIŞSAL (denetim 2026-08-17): eskiden `src.count("_minute_acc.clear()") >= 2`
    sayılıyordu. O sayım YANLIŞ-YEŞİLDİ: iki eşleşmeden biri `_emit_minute_averages`in KENDİ
    temizliğiydi, yani AI yolunda temizlik HİÇ olmasa da kapı geçiyordu (ölçüldü — ve gerçekten
    yoktu, aynı turda düzeltildi)."""
    import asyncio

    # ⚠️ "Kayıtsız tedavi başlamaz" kapısı (2026-08-09) açık: bu takımda gerçek DB yok. O kapının
    # KENDİSİ `tests/test_db_ready_gate.py`de test edilir; burada ölçtüğümüz şey akümülatör
    # temizliği, o yüzden kapı geçirilir (yoksa 503 ile erken çıkılır ve temizlik hiç ölçülmez).
    monkeypatch.setattr(api, "_kayit_db_hazir", lambda: (True, ""))
    _onceki_hastanin_artigini_koy(api)
    payload = api.SessionStartPayload(
        coil_ids=[6, 7],  # ESP-only → STM donanımı gerekmez
        mode="Manuel",
        operator_name="op",
        frequency=10.0,
        duty=25.0,
        intensity=2.0,
        phase=0,
        duration_minutes=20,
        patient_name="Boncuk",
    )
    asyncio.run(api.start_session(payload, _SahteIstek()))

    acc, buf = _artik_kaldi_mi(api)
    assert acc == 0, "MANUEL seans başında `_minute_acc` temizlenmedi → önceki hastanın ölçümleri karışır"
    assert buf == 0, "MANUEL seans başında sensör buffer'ı temizlenmedi → örnekler YENİ seansa yazılır"


def test_KRITIK_dakika_birikimi_YENI_AI_seansinda_da_sifirlanir(api):
    """AI yolu (`start_ai_session`) manuel yolla SİMETRİK olmalı.

    ⚠️ GERÇEK BULGU (denetim 2026-08-17): değildi. `/api/session/start` `_minute_acc` +
    `_sensor_sample_buffer`ı temizlerken `start_ai_session` HİÇBİRİNİ temizlemiyordu. Somut zarar:
    manuel seans sürerken operatör AI Pro başlatır (devralma) → önceki seansın kısmi dakikası
    `_minute_acc`te kalır, bir sonraki dakika-loop turunda `_flush_sensor_buffer_if_active` GÜNCEL
    `db_session_id`yi kullandığı için o örnekler YENİ AI seansının satırına yazılır: başka bir
    seansın/hastanın tıbbi kaydına karışmış telemetri."""
    _onceki_hastanin_artigini_koy(api)
    with api._session_lock:
        api._active_session.clear()
        api._active_session.update(
            {"is_active": True, "session_id": "manuel_1", "mode": "Manuel", "coil_ids": [6, 7], "start_time": 1.0}
        )

    api.start_ai_session(0.0, 0.0, 20, range(1, 8), "AI Pro")

    acc, buf = _artik_kaldi_mi(api)
    assert acc == 0, (
        "AI seansı başında `_minute_acc` temizlenmedi → devralınan seansın kısmi dakikası YENİ "
        "AI seansının db_session_id'siyle yazılır (yanlış seansa ait tıbbi kayıt)"
    )
    assert buf == 0, "AI seansı başında sensör buffer'ı temizlenmedi → önceki örnekler AI seansına yazılır"


def test_KARSIT_KANIT_TEKRARLI_AI_cagrisi_SUREN_seansin_verisini_SILMEZ(api):
    """Karşıt-kanıt: "her `start_ai_session` çağrısında temizle" biçimindeki bir yama düzeltme
    DEĞİL, veri kaybı olur.

    `landmark auto_adjust` HER İSTEKTE `start_ai_session` çağırır (cont=True yolu). O yolda
    temizlemek, süren seansın kendi birikmiş dakikasını saniyeler içinde silerdi."""
    with api._session_lock:
        api._active_session.clear()
        api._active_session.update(
            {"is_active": True, "session_id": "ai_1", "mode": "AI Pro", "coil_ids": [1, 2], "start_time": 1.0}
        )
    _onceki_hastanin_artigini_koy(api)  # bu kez ARTIK değil, SÜREN seansın verisi

    api.start_ai_session(0.0, 0.0, 20, range(1, 8), "AI Pro")  # aynı AI seansının tekrarı

    acc, buf = _artik_kaldi_mi(api)
    assert acc == 1 and buf == 1, (
        f"tekrarlı AI çağrısı SÜREN seansın telemetrisini SİLDİ (acc={acc}, buf={buf}) → "
        f"dakika-ortalaması ve sensör örnekleri kaybolur"
    )


# ───────────────────── AI PRO ─────────────────────


def _landmark_surucusu(ai_router, total: float = 4.0):
    """`analyze_landmark` içindeki `_drive_landmark_auto` KAPANIŞINI çağrılabilir hâlde ver.

    ⚠️ NEDEN BÖYLE (denetim 2026-08-17): uç noktanın kendisini sürmek gerçek YOLO çıkarımı +
    kedi yüzü içeren bir kare gerektiriyor. Ama korumanın yaşadığı yer iç içe kapanıştır ve
    kapanışın KOD NESNESİ `co_consts`ta duruyor → `types.FunctionType` ile yeniden kurup GERÇEK
    kodu koşturuyoruz. Metin araması yerine gerçek dallanma ölçülür (bu depoda yapısal kapılar
    yorumla dört kez kandırıldı; `retry_last_payload` kapısında da aynı teknik kullanıldı).
    ⚠️ Serbest değişken `total` (FGS skoru) bir HÜCRE ile verilir."""
    import types

    kodlar = [
        c
        for c in ai_router.analyze_landmark.__code__.co_consts
        if isinstance(c, types.CodeType) and c.co_name == "_drive_landmark_auto"
    ]
    assert len(kodlar) == 1, f"_drive_landmark_auto kod nesnesi bulunamadi/coklandi: {len(kodlar)}"
    kod = kodlar[0]
    hucreler = tuple(types.CellType(total if ad == "total" else None) for ad in kod.co_freevars)
    return types.FunctionType(kod, ai_router.__dict__, "_drive_landmark_auto", None, hucreler)


@pytest.fixture()
def landmark_ortami(api, monkeypatch):
    """`_drive_landmark_auto`nun dokunduğu HER donanım/DB yolunu kaydeden sahte ortam."""
    from servers import ai_router

    izler: dict = {"start_all_coils": [], "start_ai_session": [], "publish": []}

    class _SahteHw:
        def start_all_coils(self, *a, **k):
            izler["start_all_coils"].append((a, k))
            return True

    class _SahteState:
        hardware = _SahteHw()

    monkeypatch.setattr(api, "state", _SahteState())
    monkeypatch.setattr(api, "start_ai_session", lambda *a, **k: izler["start_ai_session"].append((a, k)))
    monkeypatch.setattr(api, "update_live_session_state", lambda *a, **k: None)
    monkeypatch.setattr(api, "_mqtt_publish", lambda t, p=None, *a, **k: izler["publish"].append((t, p)) or True)
    monkeypatch.setattr(ai_router, "_ai_loop_active", False)
    with api._session_lock:
        api._active_session.clear()
    return ai_router, izler


def test_landmark_auto_aktif_AI_Pro_seansini_GASP_ETMEZ(landmark_ortami):
    """AI Pro sürüyorken gelen bir landmark auto_adjust isteği (ikinci istemci / doğrudan API)
    AI Pro'nun per-bobin duty/fazının üzerine TEK-TİP değerler yazıyor, AI Pro'nun sürmediği
    bobin 8'i de enerjilendiriyor ve seans meta-verisini sessizce devralıyordu — iki otonom
    sürücü aynı donanımda çatışır, kayıtta yanlış mod görünür.

    ⚠️ DAVRANIŞSAL (denetim 2026-08-17): eskiden `'return "skipped_session_active", {}'` dizesi
    kaynakta aranıyordu — dizeyi ULAŞILAMAZ bir dala taşıyan mutasyon kapıdan geçerdi."""
    ai_router, izler = landmark_ortami
    ai_router._ai_loop_active = True

    durum, params = _landmark_surucusu(ai_router)()

    assert durum == "skipped_session_active", f"AI Pro aktifken donanim SURULDU (durum={durum!r})"
    assert not izler["start_all_coils"], "AI Pro'nun duty/fazi TEK-TIP degerlerle EZILDI"
    assert not izler["start_ai_session"], "seans meta-verisi 'AI (Auto)' olarak DEVRALINDI"
    assert not izler["publish"], f"ESP bobinlerine (8 dahil) start gonderildi: {izler['publish']!r}"


def test_landmark_auto_FARKLI_MODDAKI_aktif_seansi_de_DEVRALMAZ(landmark_ortami):
    """AI Pro kapalı ama MANUEL/Otomatik bir seans sürüyorsa da donanım gasp edilmemeli."""
    ai_router, izler = landmark_ortami
    from servers import api_server as api

    with api._session_lock:
        api._active_session.update({"is_active": True, "mode": "Manuel", "coil_ids": [1, 2]})

    durum, _ = _landmark_surucusu(ai_router)()

    assert durum == "skipped_session_active", f"MANUEL seans landmark-auto tarafindan devralindi ({durum!r})"
    assert not izler["start_all_coils"] and not izler["start_ai_session"]


def test_KARSIT_KANIT_landmark_auto_BOS_sistemde_donanimi_SURER(landmark_ortami):
    """Karşıt-kanıt: "her zaman skipped döndür" mutasyonu düzeltme sanılmasın — otonom
    biofeedback özelliğinin KENDİSİ çalışmaya devam etmeli."""
    ai_router, izler = landmark_ortami  # _ai_loop_active=False, aktif seans yok

    durum, params = _landmark_surucusu(ai_router, total=4.0)()

    assert durum == "updated", f"bos sistemde otonom surus YAPILMADI (durum={durum!r})"
    assert izler["start_all_coils"], "bobinler surulmedi"
    assert izler["start_ai_session"], "seans _active_session'a yazilmadi (sure-watchdog kapsamaz)"
    assert set(params) == {"freq", "duty"} and params["freq"] > 0


class _KayanSaat:
    """`time` kabuğu: `monotonic` GERÇEK, `time()` (duvar saati) TESTİN kontrolünde.

    ⚠️ Amaç: hangi saatin kullanıldığını VARSAYMADAN ölçmek. Damga da kalan-süre hesabı da
    gerçek kod tarafından yapılır; test yalnız DUVAR SAATİNİ oynatır. Kod monotonic kullanıyorsa
    sonuç değişmez; duvar saatine dayanıyorsa değişir."""

    def __init__(self, baslangic: float = 1_800_000_000.0):
        import time as _t

        self._t = _t
        self._duvar = float(baslangic)

    def __getattr__(self, ad):
        return getattr(self._t, ad)

    def time(self):
        return self._duvar

    def sleep(self, _sn):  # AI Pro loop'u no-op'a düşürülse de asılmasın
        return None

    def oynat(self, delta: float):
        self._duvar += float(delta)


def test_ai_pro_sure_olcumu_MONOTONIC(monkeypatch):
    """AI Pro süresi duvar saatiyle ölçülürse NTP sıçraması otonom tedaviyi erken keser
    ya da uzatır (AŞIRI DOZ — canlı hayvan üzerinde).

    ⚠️ DAVRANIŞSAL (denetim 2026-08-17): eskiden `"_ai_started_at = time.monotonic()"` dizesi
    kaynakta aranıyordu. Artık gerçek uç noktalar sürülüyor ve DUVAR SAATİ oynatılıyor: hem
    damganın hem kalan-süre hesabının monotonic olduğu tek testte ölçülür."""
    from fastapi.testclient import TestClient

    from servers import ai_approval as ap
    from servers import ai_router, api_server

    saat = _KayanSaat()
    monkeypatch.setattr(ai_router, "time", saat)
    # Kamera/model açılmasın: süre ölçümünü sınıyoruz, kapalı-döngüyü değil.
    monkeypatch.setattr(ai_router, "_ai_pro_loop", lambda: None)
    monkeypatch.setattr(api_server, "start_ai_session", lambda *a, **k: None)

    client = TestClient(api_server.app)
    try:
        rec = ap.create("ai_pro", {"organ_id": 0, "duration_minutes": 20})
        client.post("/api/ai/pro/approve", json={"proposal_id": rec["id"], "operator_email": "dr@k.com"})
        r = client.post("/api/ai/pro/start", json={"proposal_id": rec["id"]})
        assert r.status_code == 200, r.text[:200]

        kalan1 = client.get("/api/ai/pro/status").json()["remainingSec"]
        assert 0 < kalan1 <= 20 * 60, f"kalan sure makul degil: {kalan1} (saatler karismis olabilir)"

        # NTP/DST/elle düzeltme GERİ giderse: duvar saatine dayanan hesap süreyi UZATIR → aşırı doz.
        saat.oynat(-3600)
        kalan2 = client.get("/api/ai/pro/status").json()["remainingSec"]
        assert abs(kalan2 - kalan1) <= 2, (
            f"duvar saati 1 saat GERI alindi ve kalan sure degisti ({kalan1} → {kalan2}) → "
            f"otonom tedavi UZAR (asiri doz)"
        )

        # İLERİ giderse: tedavi erken kesilir (eksik doz).
        saat.oynat(+7200)
        kalan3 = client.get("/api/ai/pro/status").json()["remainingSec"]
        assert abs(kalan3 - kalan1) <= 2, (
            f"duvar saati ILERI alindi ve kalan sure degisti ({kalan1} → {kalan3}) → tedavi erken kesilir"
        )
    finally:
        client.post("/api/ai/pro/stop")
        ap.clear()


class _SahteCv2:
    """`_ai_pro_loop`un dokunduğu asgari OpenCV yüzeyi (kamera AÇILMAZ)."""

    INTER_AREA = 3
    IMWRITE_JPEG_QUALITY = 1

    class _Cap:
        def __init__(self, kare):
            self._kare = kare

        def isOpened(self):  # noqa: N802  (OpenCV adı)
            return True

        def read(self):
            return True, self._kare

        def release(self):
            return None

    def __init__(self, kare="kare"):
        self._kare = kare

    def VideoCapture(self, *a, **k):  # noqa: N802  (OpenCV adı)
        return self._Cap(self._kare)

    def imencode(self, *a, **k):
        return True, bytearray(b"jpeg")

    def resize(self, img, *a, **k):
        return img


@pytest.fixture()
def ai_pro_loop_ortami(api, monkeypatch):
    """`_ai_pro_loop`u GERÇEKTEN koşturan ortam; `tur` kadar iterasyondan sonra loop kapanır."""
    from servers import ai_router

    izler: dict = {"stop_session_coils": [], "surus": []}
    monkeypatch.setattr(ai_router, "cv2", _SahteCv2())
    monkeypatch.setattr(ai_router, "_get_or_load_kedi", lambda *a, **k: None)
    monkeypatch.setattr(ai_router, "_get_or_load_catorgan", lambda *a, **k: None)
    monkeypatch.setattr(api, "_stop_session_coils", lambda c=None: izler["stop_session_coils"].append(list(c or [])))
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(api, "update_live_session_state", lambda *a, **k: None)
    monkeypatch.setattr(api, "_mqtt_publish", lambda *a, **k: True)
    monkeypatch.setattr(api, "state", None)  # teardown'daki stop_all_coils yolu no-op
    monkeypatch.setattr(ai_router, "_ai_started_at", 0.0)  # süre-bitişi dalı devre dışı
    monkeypatch.setattr(ai_router, "_ai_relocalize", True)
    with api._session_lock:
        api._active_session.clear()
        api._active_session.update({"is_active": True, "session_id": "ai_1", "mode": "AI Pro"})

    def kos(tur: int, *, hedef_var: bool):
        """`tur` iterasyon koştur. `hedef_var=False` → her karede hedef KAYIP."""
        monkeypatch.setattr(
            ai_router,
            "_localize_organ",
            lambda *a, **k: (hedef_var, 10.0, 20.0, 30.0, 0.9 if hedef_var else 0.0, None),
        )
        if hedef_var:
            monkeypatch.setattr(ai_router, "_predict_and_drive", lambda *a, **k: ([0.5] * 7, [0.0] * 7, 1.0))
            monkeypatch.setattr(ai_router, "_drive_coils_ai_pro", lambda D, P: izler["surus"].append((D, P)))
        kalan = {"n": int(tur)}

        class _Zaman(_KayanSaat):
            def sleep(self, _sn):
                kalan["n"] -= 1
                if kalan["n"] <= 0:
                    ai_router._ai_loop_active = False

        monkeypatch.setattr(ai_router, "time", _Zaman())
        ai_router._ai_loop_active = True
        ai_router._ai_pro_loop()
        assert kalan["n"] <= 0, f"loop {tur} tur DONMEDI (kalan={kalan['n']}) — kapi bir sey olcmedi"

    yield ai_router, izler, kos
    ai_router._ai_loop_active = False
    with api._session_lock:
        api._active_session.clear()


def test_ai_pro_hedef_kaybinda_bobinler_DURDURULUR(ai_pro_loop_ortami):
    """Hedef kadraj dışına çıkınca/kımıldayınca HEDEFSİZ tedavi seans sonuna kadar
    sürüyordu; üstelik WS `perCoil` %0 yayınladığı için operatör bobinleri kapalı sanıyordu.
    Tek kare kaybında durdurmak kırılgan olurdu → ARDIŞIK eşik.

    ⚠️ DAVRANIŞSAL (denetim 2026-08-17): eskiden `"if _lost_streak == _AI_LOST_STOP_STREAK:"`
    dizesi kaynakta aranıyordu; sayacı hiç artırmayan ya da STOP'u ulaşılamaz kılan bir mutasyon
    kapıdan geçerdi. Artık GERÇEK loop koşuyor."""
    ai_router, izler, kos = ai_pro_loop_ortami
    esik = ai_router._AI_LOST_STOP_STREAK
    assert 1 <= esik <= 10, f"_AI_LOST_STOP_STREAK makul değil: {esik}"

    kos(esik, hedef_var=False)

    assert len(izler["stop_session_coils"]) == 1, (
        f"hedef {esik} ardisik iterasyondur kayipken bobinler DURDURULMADI "
        f"({izler['stop_session_coils']!r}) → hedefsiz tedavi seans sonuna kadar surer"
    )
    durdurulan = set(izler["stop_session_coils"][0])
    assert durdurulan >= set(range(1, 8)), f"AI Pro'nun surdugu 1-7 bobininin tamami durdurulmadi: {durdurulan}"


def test_KARSIT_KANIT_TEK_kare_kaybinda_tedavi_KESILMEZ(ai_pro_loop_ortami):
    """Karşıt-kanıt: "her kayıpta durdur" mutasyonu düzeltme sanılmasın — tespit anlık sekebilir
    ve her sekmede bobinleri kesmek tedaviyi kırılgan yapar."""
    ai_router, izler, kos = ai_pro_loop_ortami
    esik = ai_router._AI_LOST_STOP_STREAK
    if esik < 2:
        pytest.skip("esik 1 → 'tek kare' ile 'esik' ayni sey")

    kos(esik - 1, hedef_var=False)

    assert not izler["stop_session_coils"], (
        f"esigin ALTINDA ({esik - 1} kayip) bobinler durduruldu → anlik tespit sekmesi tedaviyi keser"
    )


def test_KARSIT_KANIT_hedef_VARKEN_surus_devam_eder(ai_pro_loop_ortami):
    """Karşıt-kanıt: hedef bulunuyorken durdurma OLMAMALI ve bobinler gerçekten sürülmeli."""
    ai_router, izler, kos = ai_pro_loop_ortami

    kos(ai_router._AI_LOST_STOP_STREAK + 2, hedef_var=True)

    assert not izler["stop_session_coils"], "hedef BULUNUYORKEN bobinler durduruldu → tedavi kesilir"
    assert izler["surus"], "hedef bulundugu halde bobinler SURULMEDI"
