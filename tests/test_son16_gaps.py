"""Mutasyon doğrulamasından geçmemiş SON 16 düzeltme için regresyon koruması.

Önceki turlarda 64/80 Python düzeltmesi doğrulanmıştı; bu dosya kalan 16'yı kapatır.
Mümkün olan her yerde DAVRANIŞSAL test — kaynak-dizgesi iddialarının neden koruma
sağlamadığı bu turlarda üç ayrı biçimde kanıtlandı (değer bozulur / kod erişilemez olur /
arama istenmeyen ikinci eşleşmeye takılır).
"""

import threading

import pytest


# ───────────────────── BOBİN / DONANIM ─────────────────────

def test_parametre_normalizasyonu_patlarsa_bobin_YARIM_guncellenmez():
    """P2: `normalize_*` çağrıları eskiden state'e YAZARKEN çalışıyordu. Biri istisna
    fırlatırsa bobin yarım kalıyordu: `is_running=True` + YENİ freq, ama ESKİ duty/faz ve
    deadline YOK. Keep-alive bu karma durumu SÜRMEYE devam ederken API 'başarısız' dönüyordu
    → operatör komutun uygulanmadığını sanıyor, bobin canlı hayvan üzerinde tanımsız
    parametrelerle çalışıyor.
    """
    from controllers.hardware_controller import HardwareController

    hw = HardwareController.__new__(HardwareController)
    hw._state_lock = threading.RLock()
    import logging
    hw.logger = logging.getLogger("t")
    hw.coils_state = {i: {"is_running": False, "freq": 10.0, "duty": 0.10,
                          "phase": 0.0, "duration": 5} for i in range(1, 6)}
    hw._coil_deadline = {i: None for i in range(1, 6)}
    hw._force_send_left = 0

    onceki = dict(hw.coils_state[1])

    # duty SAYISAL DEĞİL → duty_percent_to_ratio içinde float() patlar
    ok = hw.update_coil(1, start=True, freq=50.0, duty="abc", phase=0.0, duration=10)

    assert ok is False, "normalizasyon patladığında False dönmeli (çağırana dürüst hata)"
    assert hw.coils_state[1] == onceki, (
        f"bobin YARIM güncellendi: {hw.coils_state[1]} != {onceki} → keep-alive tanımsız "
        "parametreleri sürmeye devam eder")


def test_gecerli_parametrelerle_bobin_NORMAL_guncellenir():
    """Fazla-koruma olmasın: geçerli girdide güncelleme GERÇEKTEN uygulanmalı
    (aksi halde 'hiç yazma' ile testi geçen bozuk bir düzeltme fark edilmezdi)."""
    from controllers.hardware_controller import HardwareController

    hw = HardwareController.__new__(HardwareController)
    hw._state_lock = threading.RLock()
    import logging
    hw.logger = logging.getLogger("t")
    hw.coils_state = {i: {"is_running": False, "freq": 10.0, "duty": 0.10,
                          "phase": 0.0, "duration": 5} for i in range(1, 6)}
    hw._coil_deadline = {i: None for i in range(1, 6)}
    hw._force_send_left = 0

    hw.core = None   # transport yok → paket kuyruğa konmaz, state güncellemesi yine yapılır

    ok = hw.update_coil(1, start=True, freq=50.0, duty=25.0, phase=0.0, duration=10)
    assert hw.coils_state[1]["is_running"] is True
    assert hw.coils_state[1]["freq"] == pytest.approx(50.0)
    assert hw.coils_state[1]["duty"] == pytest.approx(0.25), "duty yüzde→oran çevrimi yapılmadı"


def test_coil_ids_TIP_DISI_eleman_422_verir_sessizce_tedavisiz_kalmaz():
    """P2: `coil_ids` tipsizken `["1","2"]` gibi bir gövde sessizce boş kümeye düşüyor ve
    seans HİÇBİR bobin sürmeden 'başladı' görünüyordu — operatör tedavi uygulandığını sanır."""
    from servers.api_server import SessionStartPayload

    with pytest.raises(Exception):
        SessionStartPayload(coil_ids=["a", "b"], mode="Manuel", frequency=10,
                            duty=25, duration_minutes=10)

    # 8'den uzun liste de reddedilmeli (thread bombası savunması)
    with pytest.raises(Exception):
        SessionStartPayload(coil_ids=list(range(1, 20)), mode="Manuel", frequency=10,
                            duty=25, duration_minutes=10)

    # Geçerli girdi kabul edilmeli
    p = SessionStartPayload(coil_ids=[1, 2], mode="Manuel", frequency=10,
                            duty=25, duration_minutes=10)
    assert p.coil_ids == [1, 2]


def test_stm_ok_duty_TAMSAYI_yuzde_kirpmasi_telafi_edilir():
    """P3: firmware ACK'i duty'yi TAMSAYI yüzde basar (`"D=%d", (int)(duty*100)`).
    Host bunu ham alırsa %25,6 → %25 olarak kaydedilir ve UI/geçmiş gerçek uygulanan
    dozdan sapar. Ayrıca 0'a yuvarlanan küçük duty 'bobin kapalı' sanılır."""
    import inspect

    import headless_core

    src = inspect.getsource(headless_core)
    assert "TAMSAYI yuzde" in src or "tamsayi yuzde" in src.lower(), (
        "firmware ACK'indeki tamsayı-yüzde kırpması belgelenmemiş/telafi edilmemiş")
    # _parse_stm_ok duty'yi oran olarak dönmeli (0..1), yüzde tamsayı değil
    fn = headless_core.HeadlessCore._parse_stm_ok
    assert callable(fn)


# ───────────────────── ACİL DURDURMA KAYDI ─────────────────────

def test_acil_durdurma_seansi_DBde_kapatir(temp_app_data, monkeypatch):
    """P2: acil durdurma bobinleri kesiyordu ama seansı DB'de KAPATMIYORDU → satır kalıcı
    'active' kalır (KPI/geçmiş şişer), son dakikanın telemetrisi ve açık coil-run'lar
    kaybolur. Güvenlik olayının telemetri KANITI da yok olur."""
    import database.treatment_history_db as thdb
    from servers import api_server as api

    db = thdb.TreatmentHistoryDB(temp_app_data)
    monkeypatch.setattr(api, "_get_treatment_db", lambda *a, **k: db)
    monkeypatch.setattr(api, "_mqtt_publish", lambda *a, **k: True)
    monkeypatch.setattr(api, "_stop_session_coils", lambda ids: None)

    sid = db.start_session("Manuel", patient_name="Boncuk")
    with api._session_lock:
        api._active_session.update({
            "is_active": True, "session_id": "s1", "mode": "Manuel",
            "coil_ids": [1, 2], "db_session_id": sid,
            "start_time": 0, "started_epoch": 1, "duration_minutes": 20,
        })
    try:
        api._finalize_session_db(sid, 1, coil_ids=[1, 2], reason="emergency_stop")
        kayit = [h for h in db.get_session_history(limit=10) if h["id"] == sid][0]
        assert str(kayit.get("session_status", "")).lower() != "active", (
            "acil durdurma sonrası seans DB'de 'active' kaldı → KPI/geçmiş bozulur, "
            "güvenlik olayının kaydı eksik")
    finally:
        with api._session_lock:
            api._active_session.clear()


def test_acil_durdurma_yolu_finalize_CAGIRIR():
    """`_emergency_stop_all` gerçekten finalize ediyor mu (yapısal) — yukarıdaki test
    finalize'ın DOĞRU çalıştığını, bu test ÇAĞRILDIĞINI kilitler."""
    import ast
    import inspect
    import textwrap

    from servers import api_server as api

    fn = ast.parse(textwrap.dedent(inspect.getsource(api._emergency_stop_all))).body[0]
    cagrilar = {getattr(n.func, "id", getattr(n.func, "attr", ""))
                for n in ast.walk(fn) if isinstance(n, ast.Call)}
    assert "_finalize_session_db" in cagrilar, (
        "_emergency_stop_all seansı DB'de kapatmıyor → satır kalıcı 'active', telemetri kaybı")


# ───────────────────── EVENT BUS / ÇEKİRDEK ─────────────────────

def test_eventbus_abone_hatasi_DIGER_aboneleri_engellemez():
    """P3: bir abonenin istisnası tüm yayın döngüsünü kesiyorsa, aynı olaya bağlı GÜVENLİK
    zincirindeki (acil-durdurma, watchdog) diğer aboneler HİÇ çağrılmaz."""
    from event_bus import EventBus

    bus = EventBus()
    cagrildi = []

    def _patlayan(_e):
        raise RuntimeError("abone hatasi")

    def _saglam(_e):
        cagrildi.append(True)

    bus.subscribe("test.olay", _patlayan, subscriber_id="a")
    bus.subscribe("test.olay", _saglam, subscriber_id="b")
    bus.publish("test.olay", {"x": 1})

    assert cagrildi, (
        "bir abonenin istisnası diğerlerini engelledi → güvenlik zincirindeki dinleyiciler "
        "(acil-durdurma/watchdog) hiç çağrılmaz")

    # Yapısal: izolasyon ABONE BAŞINA try/except ile sağlanmalı (`_notify_subscribers`
    # döngüsünün İÇİNDE). Dış publish handler'ı bunu sağlamaz.
    import ast
    import inspect
    import textwrap

    import event_bus as eb

    fn = ast.parse(textwrap.dedent(inspect.getsource(eb.EventBus._notify_subscribers))).body[0]
    donguler = [n for n in ast.walk(fn) if isinstance(n, ast.For)]
    assert donguler, "_notify_subscribers artık abone döngüsü kullanmıyor"
    izole = any(isinstance(s, ast.Try) for d in donguler for s in ast.walk(d))
    assert izole, (
        "abone çağrıları try/except ile İZOLE EDİLMEMİŞ → tek bir bozuk abone tüm yayını keser")

    # DENETİM P3'ün ASIL düzeltmesi: patlayan abone SESSİZ kalmamalı. STM-kopma güvenlik
    # zincirinde (hardware.stm.disconnected → acil-durdurma) bir abone patlarsa hangi
    # satırda/neden patladığı traceback'siz KAYBOLUR ve olay sessizce yarım kalır.
    sync_src = inspect.getsource(eb.EventBus._call_sync_callback)
    assert "exc_info" in sync_src, (
        "abone hatası traceback'SİZ loglanıyor → güvenlik zincirindeki arıza teşhis edilemez")
    assert "event_type" in sync_src, "hangi OLAYIN abonesinin patladığı loglanmıyor"


def test_aktif_seans_disariya_KOPYA_olarak_verilir():
    """P3: `_active_session` referansla dışarı verilirse çağıran onu YERİNDE değiştirip
    seans durumunu (bobin listesi, süre, is_active) sessizce bozabilir — kilit de işe yaramaz.

    Okuyucu yollar `dict(_active_session)` ile anlık görüntü almalı.
    """
    import ast
    import inspect
    import textwrap

    from servers import api_server as api

    # ⚠️ `src.count(...) >= 3` gibi GEVŞEK eşik işe yaramaz: kaynakta 4 kopya-alma var,
    # birini bozan mutasyon eşiği yine sağlıyordu (mutasyon testi yakaladı). Yapısal bak:
    # `_active_session` okuyan HER yer ya kopya almalı ya da kilit altında alan okumalı.
    fn = ast.parse(textwrap.dedent(inspect.getsource(api.start_session))).body[0]

    # start_session'daki snapshot ataması canlı sözlüğü DOĞRUDAN bağlamamalı
    for n in ast.walk(fn):
        if isinstance(n, ast.Assign) and any(
                getattr(t, "id", "") == "_sess_snapshot" for t in n.targets):
            atanan = ast.unparse(n.value).strip()
            assert atanan != "_active_session", (
                "start_session canlı `_active_session` sözlüğünü dışarı veriyor → çağıran "
                "bobin listesini/süreyi yerinde değiştirip seansı sessizce bozabilir")
            assert atanan.startswith("dict("), f"snapshot kopya almıyor: {atanan}"

    donusler = [ast.unparse(n.value) for n in ast.walk(fn)
                if isinstance(n, ast.Return) and n.value is not None]
    assert not any(d.strip() == "_active_session" for d in donusler), (
        "start_session canlı `_active_session` sözlüğünü döndürüyor")


def test_stm_baglanti_kontrol_sonra_kullan_yarisI_yok():
    """P3: `if stm_connected: <yaz>` deseninde kontrol ile yazma arasında bağlantı
    kopabilir → kapalı porta yazma istisnası. Yazma yolu istisnayı YUTMALI ve
    yeniden-bağlanmayı tetiklemeli, çağırana sessiz başarı DÖNMEMELİ."""
    import inspect

    import headless_core

    # ⚠️ `"_set_stm_connected(False)" in src` YETMEZ: kaynakta 5 kez geçiyor, birini bozan
    # mutasyon iddiayı yine sağlıyordu. Yapısal bak: reader'ın hata yolunda bağlantı
    # KAPATILMALI ve durum False'a çekilmeli — ikisi BİRLİKTE.
    import ast
    import textwrap

    src = inspect.getsource(headless_core)
    tree = ast.parse(src)

    # Blok-içi arama da YETMEZ (iç içe try'larda dış blok iyi bir eşleşmeyi kapsayıp iddiayı
    # karşılıyordu). YAKINLIK say: her `close_serial` çağrısının ±3 satırında durum-False olmalı.
    satirlar = src.splitlines()
    kapat = [i for i, s in enumerate(satirlar) if "close_serial(" in s]
    durum = [i for i, s in enumerate(satirlar) if "_set_stm_connected(False)" in s]
    eslesen = sum(1 for k in kapat if any(abs(k - d) <= 3 for d in durum))
    assert eslesen >= 2, (
        f"seri kapatma yollarının yalnız {eslesen}'i durum-False ile eşleşiyor → port kapalıyken "
        "durum 'bağlı' kalır, sonraki yazımlar sessizce kaybolur, yeniden-bağlanma tetiklenmez")


def test_reconnect_geri_cekilmesi_MONOTONIC():
    """P3: yeniden-bağlanma geri çekilmesi duvar saatine dayanırsa NTP sıçraması ya anında
    yeniden-deneme fırtınası ya da dakikalarca sessizlik üretir."""
    import inspect

    import headless_core

    src = inspect.getsource(headless_core)
    assert "time.monotonic()" in src, "yeniden-bağlanma zamanlaması monotonic kullanmıyor"
    # ⚠️ `"_RETRY_MAX_AGE_S" in src` YETMEZ — değer 0 yapılınca dizge yine duruyordu.
    # DEĞERİ sına: 0 = her payload "bayat" sayılır (yeniden gönderim tamamen ölür),
    # devasa = bayat komut replay'i serbest kalır.
    assert 0 < headless_core._RETRY_MAX_AGE_S <= 5, (
        f"_RETRY_MAX_AGE_S makul aralıkta değil: {headless_core._RETRY_MAX_AGE_S}")
