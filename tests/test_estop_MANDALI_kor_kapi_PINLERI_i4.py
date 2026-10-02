# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.81 · Y4 · 1-C bağımsız inceleme i4 — mandal / nesil kapılarının KÖR noktalarına pinler (ürün DOĞRU; kapı ölçmüyordu).

i4, D1.81 kapılarının (42 test) ve geniş kümelerin 17 gerçekçi gerilemeyi YEŞİL geçirdiğini ölçtü (tam süit 4032 testte
de kör: P1/P8/P16). Her pin aşağıdaki mutantta KIRMIZI olur (mutant = gerçek gerileme, eşdeğer değil):
  F-01 mandal E-stop STOP'undan SONRA kurulursa arada tekil START sürer (P1)   F-02 mandal yalnız nesilsiz niyette (P8)
  F-03 sıradan durdurma mandalı kaldırır (P16)                                F-04 STM yeniden bağlanınca mandal kalkar (P17)
  F-05 seans girişi 409'u yok → ESP bobinli seans "başarılı" (P10)           F-06 Sıfırla auth-muaf (P6)
  F-07 `_esp_start_yayinla` niyet neslini yok sayar (P4)                      F-08 telafi STOP'u yalnız mandalda (P5)
  F-09 AI Pro süren AI (Auto) seansını devralır → mühür None (P15)            F-10 `stop_all_coils` nesil++ kilit dışında (P2)
  F-11 seanssız STM kopması nesli artırmaz (P13)                             F-12 Sıfırla denetim izi yok (P18)
  F-13 batch / legacy 409 + "Sıfırla" eylemi yok (P11 / P12)                 F-14 sağlık ucu uzağa mandal ayrıntısı (P7)
  F-15 son savunma büyük harfli "START"ı geçirir (P9)                         F-17 olumlu kontrol: onaylı döngü GERÇEK HC ile sürer (K3)
Ölçüt HTTP değil: donanıma giden paket (firmware aynası çözücü), `coils_state`, ESP teli, mandal durumu. Aparat: GERÇEK uçlar
+ GERÇEK `HardwareController` (`kayitci_donanim.gercek_hc`); yarış pencereleri `threading.Event` ile ZORLANIR.
"""

from __future__ import annotations

import json
import threading
import time
import types

import ai_pro_aparati as ap
import pytest


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc
    from servers import api_server as _api

    gercek_yayin = _api._mqtt_publish  # ap.kur yamalamadan ÖNCE: P9 kolu GERÇEK tek boğaz noktasını sınar
    ns = ap.kur(monkeypatch, tmp_path)
    ns.gercek_yayin = gercek_yayin
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.geri()


def _m():
    from utils import estop_mandali

    return estop_mandali


def _tekil_start(o, bobin: int = 2):
    return o.c.post(
        f"/api/coil/{bobin}/control", json={"start": True, "freq": 100, "duty": 40, "phase": 0, "duration": 60}
    )


def _landmark_surucusu(air, **degerler):
    """`analyze_landmark` içindeki GERÇEK `_drive_landmark_auto` kapanışı (kod nesnesinden; test_kalan_regression_gaps
    ile aynı teknik). Serbest değişkenler adla verilir; kapanış imzası değişirse aparat KIRMIZI olur (sessiz değil)."""
    kodlar = [
        c
        for c in air.analyze_landmark.__code__.co_consts
        if isinstance(c, types.CodeType) and c.co_name == "_drive_landmark_auto"
    ]
    assert len(kodlar) == 1, f"aparat: _drive_landmark_auto kod nesnesi sayısı {len(kodlar)}"
    kod = kodlar[0]
    eksik = set(kod.co_freevars) - set(degerler)
    assert not eksik, f"aparat: kapanışın serbest değişkenleri değişti: {sorted(eksik)}"
    hucreler = tuple(types.CellType(degerler[ad]) for ad in kod.co_freevars)
    return types.FunctionType(kod, air.__dict__, "_drive_landmark_auto", None, hucreler)


def _esp_komutlari(o, bobin: int = 8, once: int = 0) -> list:
    return [str(p.get("command")) for t, p in o.yayin[once:] if t == f"pemf/coil/{bobin}/control"]


# ── P1: E-stop'ta mandal STOP'tan ÖNCE kurulur ─────────────────────────────────────────────────────
def test_KRITIK_i4F01_estop_STM_STOP_ile_mandal_ARASINDA_tekil_START_GECMEZ(o, monkeypatch):
    """D1.81 tasarımı (`_emergency_stop_all` yorumu): mandal STOP'tan ÖNCE kurulur — "arada kabul edilen bir START, bu
    E-stop'un STOP'undan sonra keep-alive ile sürerdi". E-stop, STM STOP'u gittikten hemen sonra (ESP STOP'ları
    sürerken) ZORLA bekletilir ve tekil START verilir: reddedilmeli, STOP'tan sonra duty>0 paket gitmemeli."""
    dur, devam = threading.Event(), threading.Event()
    orj = o.hc.stop_all_coils

    def _sarili():
        r = orj()
        if threading.current_thread().name == "inc-estop":
            dur.set()
            devam.wait(10)
        return r

    monkeypatch.setattr(o.hc, "stop_all_coils", _sarili)
    t = threading.Thread(target=o.api._emergency_stop_all, args=("manual",), name="inc-estop", daemon=True)
    t.start()
    try:
        assert dur.wait(10), "aparat: E-stop STM STOP'una ulaşmadı"
        n = ap.paket_sayisi(o)
        r = _tekil_start(o, 2)
    finally:
        devam.set()
        t.join(15)
    assert not t.is_alive(), "aparat: E-stop bitmedi"
    assert not ap.surus_paketleri(o, n), (
        f"E-stop'un STM STOP'undan SONRA tekil START donanımı sürdü: {ap.surus_paketleri(o, n)}"
    )
    assert ap.calisan(o) == [], f"E-stop bittikten sonra ÇALIŞAN bobin: {ap.calisan(o)}"
    assert r.status_code == 409, f"E-stop sürerken tekil START {r.status_code}: {r.text[:160]}"


# ── P2: stop_all_coils nesli DURUM KİLİDİ ALTINDA artırır (mandalsız durdurma kolu) ────────────────────
def test_KRITIK_i4F10_stop_all_coils_SURERKEN_eski_niyetli_START_STOPtan_sonra_GECMEZ(o, monkeypatch):
    """`HardwareController.stop_all_coils` yorumu: nesil++ durum kilidi ALTINDA — "kilide takılı bir START ya bu
    STOP'tan önce yazılır ya da bayat nesille reddedilir". Mevcut kilit kolu yalnız E-stop'la koşar (mandal bunu
    örter); burada MANDALSIZ durdurma (legacy stop_all_coils / reset_pwm / AI Pro teardown). Eşzamanlı START tam
    nesil artışı anında verilir; kilit altındaysa kilide takılır (zaman aşımı), değilse hemen koşar."""
    m = _m()
    tok = m.nesil()
    orj_artir = m.nesil_artir
    sonuc: dict = {}

    def _artir():
        if threading.current_thread().name == "inc-stopall" and "t" not in sonuc:
            t2 = threading.Thread(
                target=lambda: sonuc.update(r=o.hc.update_coil(2, 100.0, 40.0, 0.0, 5, start=True, nesil=tok)),
                name="inc-start",
                daemon=True,
            )
            sonuc["t"] = t2
            t2.start()
            t2.join(1.0)
        return orj_artir()

    monkeypatch.setattr(m, "nesil_artir", _artir)
    n = ap.paket_sayisi(o)
    s = threading.Thread(target=o.hc.stop_all_coils, name="inc-stopall", daemon=True)
    s.start()
    s.join(10)
    assert "t" in sonuc, "aparat: stop_all_coils nesil artırmadı (nesil_artir çağrılmadı)"
    sonuc["t"].join(10)
    assert not ap.surus_paketleri(o, n), (
        f"stop_all_coils sürerken alınan ESKİ niyetli START, STOP'tan SONRA sürdü: {ap.surus_paketleri(o, n)}"
    )
    assert ap.calisan(o) == [], f"stop_all_coils sonrası ÇALIŞAN bobin: {ap.calisan(o)}"
    assert sonuc.get("r") is False, f"eski niyetli START kabul edildi: {sonuc.get('r')}"


# ── P4: _esp_start_yayinla niyet neslini denetler (AI (Auto) ESP yolu) ───────────────────────────────
def test_KRITIK_i4F07_AI_Auto_STM_basladiktan_sonra_gelen_DURDURMA_ESP_START_yayinini_ENGELLER(o, monkeypatch):
    """GERÇEK AI (Auto) kapanışı: STM `start_all_coils` kabul edildikten hemen sonra operatör DURDUR'a basar
    (`/api/session/stop` → yetki kesilir, ESP bobin 8'e STOP). Kapanış ardından ESP bobin 8'e START yayınlar —
    bayat niyet: yayınlanmamalı. Ölçüt: bobin 8 telinde operatörün STOP'undan (İLK STOP) sonra HİÇ START yok.
    (1-C: i4'ün "SON STOP'tan sonra START yok" ölçütü i1-F2 sonrası KÖRDÜ — telafi STOP'u bayat START'ı izleyince tel
    `stop, start, stop` olur ve son komut STOP görünür; oysa bayat START yine yayınlanmış ve bobin kısa süre enerjilenmiştir.)"""
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    m = _m()
    o.air._ai_loop_active = False
    tok = m.nesil()
    orj = o.hc.start_all_coils
    durdurma: dict = {}

    def _sarili(*a, **k):
        r = orj(*a, **k)
        durdurma["r"] = o.c.post("/api/session/stop")  # operatör tam bu anda DURDUR
        return r

    monkeypatch.setattr(o.hc, "start_all_coils", _sarili)
    once = len(o.yayin)
    durum, _ = _landmark_surucusu(o.air, total=4.0, _niyet_nesli=tok, _landmark_operator="")()
    assert durdurma.get("r") is not None and durdurma["r"].status_code == 200, f"aparat: durdurma koşmadı ({durum})"
    kom = _esp_komutlari(o, 8, once)
    assert "stop" in kom, f"aparat: durdurma ESP bobin 8'e STOP göndermedi: {kom}"
    ilk_stop = kom.index("stop")
    assert "start" not in kom[ilk_stop + 1 :], (
        f"DURDURMADAN SONRA ESP bobin 8'e START yayınlandı (bayat AI (Auto) niyeti): {kom}"
    )


# ── P5: ESP START yayını sürerken MANDALSIZ durdurma → telafi STOP'u ───────────────────────────────────
def test_KRITIK_i4F08_ESP_START_yayini_SURERKEN_SEANSSIZ_durdurma_TELAFI_STOP(o, monkeypatch):
    """`_esp_start_yayinla`: "yayın SIRASINDA durdurma / acil durdurma geldiyse (nesil değişti YA DA mandal kuruldu)
    → telafi STOP'u". Mevcut kapı yalnız E-stop kolunu (mandal) ölçer; burada mandal yok, yalnız nesil değişir
    (seanssız `/api/session/stop`)."""
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    gelen, birak = threading.Event(), threading.Event()
    tel: list = []

    def _yayin(topic, payload):
        if str(payload.get("command")) == "start":
            gelen.set()
            assert birak.wait(10), "aparat: START yayını serbest bırakılmadı"
        tel.append((topic, str(payload.get("command"))))
        return True

    monkeypatch.setattr(o.api, "_mqtt_publish", _yayin)
    kutu: dict = {}
    t = threading.Thread(target=lambda: kutu.update(r=_tekil_start(o, 8)), daemon=True)
    t.start()
    try:
        assert gelen.wait(10), "aparat: START yayını başlamadı"
        rs = o.c.post("/api/session/stop")
        assert rs.status_code == 200, rs.text[:160]
    finally:
        birak.set()
        t.join(15)
    b8 = [k for tp, k in tel if tp == "pemf/coil/8/control"]
    assert "start" in b8 and "stop" in b8, f"aparat: bobin 8 teli {b8}"
    son_start = len(b8) - 1 - b8[::-1].index("start")
    assert "stop" in b8[son_start + 1 :], (
        f"DURDURMA ESP START yayını SÜRERKEN geldi; telde son komut START kaldı (telafi STOP'u yok): {b8}"
    )


# ── P6: Sıfırla ucu auth-muaf DEĞİL ────────────────────────────────────────────────────────────────
def test_KRITIK_i4F06_SIFIRLA_ucu_UZAK_jetonsuz_istemciye_KAPALI_jetonla_ACIK(o, monkeypatch):
    """Tasarım: Sıfırla ucu muaf DEĞİL (yerel / LAN / jeton). Auth zorunluyken tünelden (uzak) JETONSUZ istek
    mandalı KALDIRAMAZ (Y4: operatörün bilinçli eylemi). Jeton SAHTE (test değeri; gerçek sır değil)."""
    from servers import auth

    monkeypatch.setattr(auth, "_require", True)
    monkeypatch.setattr(auth, "_warned", True)
    monkeypatch.setattr(auth, "get_api_token", lambda: "inc-sahte-jeton")
    o.api._emergency_stop_all("manual")
    uzak = {"cf-connecting-ip": "203.0.113.9"}
    r = o.c.post("/api/hardware/estop_mandali/sifirla", headers=uzak, json={"onay": True})
    assert r.status_code == 401, f"uzak JETONSUZ Sıfırla {r.status_code} döndü (401 bekleniyor): {r.text[:160]}"
    assert _m().mandalli_mi(), "uzak JETONSUZ istek mandalı KALDIRDI"
    r2 = o.c.post(
        "/api/hardware/estop_mandali/sifirla", headers={**uzak, "X-API-Key": "inc-sahte-jeton"}, json={"onay": True}
    )
    assert r2.status_code == 200 and not _m().mandalli_mi(), f"KARŞIT: jetonlu Sıfırla çalışmadı: {r2.status_code}"


# ── P7: /api/health uzak istemciye yalnız `aktif` ──────────────────────────────────────────────────
def test_KRITIK_i4F14_saglik_ucu_UZAK_istemciye_YALNIZ_aktif_yerel_istemciye_AYRINTI(o):
    """system_router yorumu: "Neden/zaman ayrıntısı yalnız yerel/LAN'a (bu uç auth-muaf ve tünelden erişilebilir);
    uzak istemci yalnız `aktif`i görür"."""
    from fastapi.testclient import TestClient

    o.api._emergency_stop_all("stm_disconnected")
    h_uzak = o.c.get("/api/health", headers={"cf-connecting-ip": "203.0.113.9"}).json()
    assert set((h_uzak.get("estopMandali") or {}).keys()) == {"aktif"}, (
        f"uzak (tünel) istemciye mandal AYRINTISI sızdı: {h_uzak.get('estopMandali')}"
    )
    yerel = TestClient(o.api.app, client=("127.0.0.1", 50123))
    h_yerel = yerel.get("/api/health").json()
    assert (h_yerel.get("estopMandali") or {}).get("neden") == "stm_disconnected", (
        f"KARŞIT: yerel istemci nedeni görmüyor: {h_yerel.get('estopMandali')}"
    )


# ── P8: mandal, niyet nesli VERİLMİŞ (taze) START'ı da reddeder ─────────────────────────────────────
def test_KRITIK_i4F02_mandalliyken_TAZE_nesilli_START_REDDEDILIR_HC_ve_AI_Auto(o):
    """Mandal kuruluyken alınmış (E-stop'tan SONRA gelen) niyetin nesli günceldir — yalnız mandal ayırt eder.
    Mevcut kapılar HC'yi yalnız nesilsiz çağırır; nesil taşıyan yollar (AI (Auto)) ön denetimleri de aynı
    `baslatma_engeli`ne dayandığından HTTP 409 katmanı yoktur."""
    m = _m()
    o.api._emergency_stop_all("manual")
    n = ap.paket_sayisi(o)
    taze = m.nesil()
    o.air._ai_loop_active = False
    durum, _ = _landmark_surucusu(o.air, total=4.0, _niyet_nesli=taze, _landmark_operator="")()
    with o.api._session_lock:
        _aktif_iz = bool(o.api._active_session.get("is_active"))
    paketler_ai_auto = ap.surus_paketleri(o, n)
    calisan_ai_auto = ap.calisan(o)
    o.hc.stop_all_coils()  # AI (Auto) kolu ayrı ölçüldü; HC kolu temiz durumdan
    with o.api._session_lock:
        o.api._active_session["is_active"] = False
    o.api._emergency_stop_all("manual")
    n2 = ap.paket_sayisi(o)
    taze2 = m.nesil()
    hc_tek = o.hc.update_coil(3, 100.0, 40.0, 0.0, 5, start=True, nesil=taze2)
    with m.surus_baglami(taze2):
        hc_hepsi = o.hc.start_all_coils(100.0, 40.0, 0.0, 5)
    assert not paketler_ai_auto, f"mandallıyken AI (Auto) bobinleri SÜRDÜ ({durum}): {paketler_ai_auto}"
    assert calisan_ai_auto == [] and not _aktif_iz, (
        f"mandallıyken AI (Auto): çalışan {calisan_ai_auto}, seans {_aktif_iz}"
    )
    assert hc_tek is False, "mandallıyken TAZE nesilli update_coil KABUL edildi"
    assert hc_hepsi is False, "mandallıyken bağlamdaki taze nesil (start_all_coils) KABUL edildi"
    assert not ap.surus_paketleri(o, n2), f"mandallıyken HC taze nesille sürdü: {ap.surus_paketleri(o, n2)}"
    assert ap.calisan(o) == [], f"mandallıyken çalışan bobin: {ap.calisan(o)}"
    assert durum == "skipped_estop_latched", durum


# ── P9: _mqtt_publish son savunması büyük/küçük harf duyarsız (S3 firmware `toUpperCase`) ──────────────
def test_KRITIK_i4F15_mqtt_publish_SON_SAVUNMA_buyuk_harf_START_de_YAYINLANMAZ(o, monkeypatch):
    """ESP-S3 firmware'i komutu `toUpperCase()` ile karşılaştırır: "START"/"Start" BAŞLATIR. Son savunma hattı bunları
    da kesmeli (GERÇEK `_mqtt_publish`; paho sahte, broker sondası yamalı — ağa çıkılmaz)."""
    import socket

    import paho.mqtt.client as pm

    yayinlanan: list = []

    class _SahteIstemci:
        def __init__(self, *a, **k):
            pass

        def username_pw_set(self, *a, **k):
            pass

        def connect(self, *a, **k):
            pass

        def loop_start(self):
            pass

        def loop_stop(self):
            pass

        def disconnect(self):
            pass

        def publish(self, topic, veri, *a, **k):
            yayinlanan.append((topic, veri))
            return types.SimpleNamespace(wait_for_publish=lambda timeout=None: None, is_published=lambda: True)

    monkeypatch.setattr(o.api, "_mqtt_publish", o.gercek_yayin)
    monkeypatch.setattr(pm, "Client", _SahteIstemci)
    monkeypatch.setattr(o.ls, "esp_etkin", lambda: True)
    monkeypatch.setattr(o.api, "_mqtt_credentials", lambda: (None, None))
    monkeypatch.setattr(o.api, "_kaydet_esp_komut_niyeti", lambda *a, **k: None)
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: types.SimpleNamespace(close=lambda: None))
    o.api._emergency_stop_all("manual")
    once = len(yayinlanan)
    for kom in ("START", "Start"):
        o.api._mqtt_publish("pemf/coil/8/control", {"command": kom, "command_id": "inc-" + kom, "freq": 10, "duty": 5})
    assert len(yayinlanan) == once, f"mandallıyken büyük harfli START YAYINLANDI: {yayinlanan[once:]}"
    assert o.api._mqtt_publish("pemf/coil/8/control", {"command": "stop", "command_id": "inc-stop"}) is True
    assert len(yayinlanan) == once + 1, "KARŞIT: mandallıyken STOP yayınlanmadı (Ö.4-Y8)"


# ── P10: seans girişindeki mandal 409'u (katman maskesi: ESP bobinli seans) ───────────────────────────
@pytest.mark.parametrize("bobinler", [[8], [1, 8]])
def test_KRITIK_i4F05_mandalliyken_ESP_bobinli_SEANS_ACILMAZ_409(o, monkeypatch, bobinler):
    """Mevcut seans kolu yalnız STM bobinleriyle koşar; STM reddi sonrası ikinci 409 girişteki 409'u ÖRTER. ESP
    bobini olan seansta ikinci katman YOK (ESP yayını arka planda, "hiç bobin sürülmedi" denetimi ESP'yi sayar).
    1-C: i1-F5'in DB yazımı sonrası erken iptali artık ikinci katmandır (giriş 409'u kalksa da 409 döner) — giriş
    409'unun ayırt edici sonucu: reddedilen başlatma DB'ye HİÇ seans satırı yazmaz (boşuna "İptal Edildi" kaydı yok)."""
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    o.api._emergency_stop_all("manual")
    r = o.c.post(
        "/api/session/start",
        json={"coil_ids": bobinler, "frequency": 100, "duty": 40, "phase": 0, "duration_minutes": 5, "mode": "Manuel"},
    )
    time.sleep(0.3)  # seans yolu ESP yayınını arka planda yapar
    with o.api._session_lock:
        aktif = bool(o.api._active_session.get("is_active"))
    assert r.status_code == 409 and not aktif, (
        f"mandallıyken ESP bobinli seans {bobinler}: HTTP {r.status_code}, seans aktif={aktif}: {r.text[:160]}"
    )
    assert "Sıfırla" in r.json().get("detail", ""), r.text[:160]
    with o.db._get_connection() as conn:
        satir = conn.execute("SELECT COUNT(*) FROM treatment_sessions").fetchone()[0]
    assert satir == 0, (
        f"mandallıyken reddedilen seans başlatması DB'ye {satir} seans satırı yazdı (girişte reddedilmeli)"
    )


# ── P11/P12: batch ve legacy 409 + eylem (katman maskesi: HC reddi HTTP 200 döner) ──────────────────────
def test_KRITIK_i4F13_mandalliyken_BATCH_START_409_ve_SIFIRLA_eylemi(o):
    o.api._emergency_stop_all("manual")
    r = o.c.post(
        "/api/coil/batch",
        json={"coil_ids": [1, 2, 3], "start": True, "freq": 100, "duty": 40, "phase": 0, "duration": 60},
    )
    assert r.status_code == 409 and "Sıfırla" in r.json().get("detail", ""), (
        f"mandallıyken batch START: HTTP {r.status_code} (409 + 'Sıfırla' bekleniyor): {r.text[:200]}"
    )


@pytest.mark.parametrize("komut", ["start_coil", "start_all_coils"])
def test_KRITIK_i4F13_mandalliyken_LEGACY_START_409_ve_SIFIRLA_eylemi(o, komut):
    o.api._emergency_stop_all("manual")
    r = o.c.post("/api/hardware/command", json={"command": komut, "params": {"coil_id": 2, "duty": 40, "freq": 100}})
    assert r.status_code == 409 and "Sıfırla" in r.json().get("detail", ""), (
        f"mandallıyken legacy {komut}: HTTP {r.status_code} (409 + 'Sıfırla' bekleniyor): {r.text[:200]}"
    )


# ── P13: STM kopması (seanssız) eski niyetleri geçersiz kılar ────────────────────────────────────────
def test_KRITIK_i4F11_STM_kopmasi_SEANSSIZ_eski_niyeti_gecersiz_kilar(o):
    """`on_disconnect` yorumu: "bağlantı kopmadan ÖNCE kurulmuş START niyeti, bağlantı dönünce bobini ESKİ niyetle
    enerjilemesin". Aktif STM seansı YOKKEN kopmada E-stop (mandal) koşmaz → yalnız nesil korur. GERÇEK olay zinciri
    (`_handle_backend_event`)."""
    m = _m()
    tok = m.nesil()

    def _olay(tur):
        return types.SimpleNamespace(event_type=tur, data={})

    o.api._handle_backend_event(_olay("hardware.stm.disconnected"))
    assert not m.mandalli_mi(), "aparat: seanssız kopma mandal kurmamalı (E-stop yalnız aktif STM seansında)"
    o.api._handle_backend_event(_olay("hardware.stm.connected"))
    n = ap.paket_sayisi(o)
    _eski = o.hc.update_coil(2, 100.0, 40.0, 0.0, 5, start=True, nesil=tok)
    assert _eski is False, "STM kopmadan ÖNCEKİ niyet, bağlantı dönünce bobini SÜRDÜ"
    assert not ap.surus_paketleri(o, n)
    assert o.hc.update_coil(2, 100.0, 40.0, 0.0, 5, start=True, nesil=m.nesil()) is True, (
        "KARŞIT: taze niyet reddedildi"
    )


# ── P15: AI Pro, süren AI (Auto) seansını DEVRALMAZ (yeni mühür, yeni başlangıç) ─────────────────────────
def test_KRITIK_i4F09_suren_AI_Auto_seansi_USTUNE_AI_Pro_YENI_muhurlu_seans_acar(o):
    """`start_ai_session` yorumu: "AI Pro her başlatmada YENİ mühürlü seanstır: önceki AI (Auto) seansının
    başlangıcını/satırını devralsaydı mühürdeki süre (başlangıç + onaylanan dk) yanlış hesaplanırdı"."""
    m = _m()
    o.api.start_ai_session(10.0, 25.0, 30, range(1, 9), "AI (Auto)", tur="ai_auto", surus_nesli=m.nesil())
    with o.api._session_lock:
        o.api._active_session["start_mono"] = time.monotonic() - 600  # 10 dk'dır süren AI (Auto)
    _pid, r = ap.onayli_baslat(o, sure_dk=5)
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:200]
    with o.api._session_lock:
        bas = o.api._active_session.get("start_mono")
    assert bas is not None and time.monotonic() - float(bas) < 5, (
        f"AI Pro seansı AI (Auto) başlangıcını DEVRALDI (başlangıç {time.monotonic() - float(bas):.0f} sn önce)"
    )
    muhur = o.air._ai_pro_surus_muhru()
    assert muhur is not None and 280 <= muhur["kalan_s"] <= 301, (
        f"onaylı 5 dk'lık AI Pro mührü yanlış: {None if muhur is None else round(muhur['kalan_s'])} sn"
    )
    j = ap.kare(o).json()
    assert j.get("driven") is True, f"onaylı AI Pro seansında /frame sürmedi: {j.get('driven')}"


# ── P16: sıradan DURDURMA mandalı kaldırmaz (yalnız ayrı ve bilinçli Sıfırla) ──────────────────────────
@pytest.mark.parametrize("durdurma", ["/api/session/stop", "/api/ai/pro/stop", "/api/hardware/reset_pwm"])
def test_KRITIK_i4F03_estop_SONRASI_siradan_DURDURMA_mandali_KALDIRMAZ(o, durdurma):
    o.api._emergency_stop_all("manual")
    rs = o.c.post(durdurma)
    assert rs.status_code == 200, rs.text[:160]
    time.sleep(0.2)  # reset_pwm arka planda
    assert _m().mandalli_mi(), f"{durdurma} acil durdurma mandalını KALDIRDI (Y4: yalnız ayrı ve bilinçli Sıfırla)"
    n = ap.paket_sayisi(o)
    r = _tekil_start(o, 1)
    assert r.status_code == 409 and not ap.surus_paketleri(o, n), f"{durdurma} sonrası START {r.status_code}"


# ── P17: STM yeniden bağlanınca mandal KALKMAZ ──────────────────────────────────────────────────────
def test_KRITIK_i4F04_STM_kopmasi_mandali_YENIDEN_BAGLANINCA_KALKMAZ(o):
    """Y4 "her kaynak": STM kopmasıyla kurulan mandal, bağlantı dönünce kendiliğinden kalkmamalı."""
    o.api._emergency_stop_all("stm_disconnected", mode="STM Bağlantı Kaybı")
    o.api._handle_backend_event(types.SimpleNamespace(event_type="hardware.stm.connected", data={}))
    assert _m().mandalli_mi(), "STM yeniden bağlanınca acil durdurma mandalı KENDİLİĞİNDEN kalktı"
    n = ap.paket_sayisi(o)
    r = _tekil_start(o, 1)
    assert r.status_code == 409 and not ap.surus_paketleri(o, n), f"yeniden bağlantı sonrası START {r.status_code}"


# ── P18: Sıfırla'nın denetim izi (append-only session_events) ─────────────────────────────────────────
def test_KRITIK_i4F12_SIFIRLA_denetim_izi_session_events_e_YAZILIR(o):
    """Tasarım (Sıfırla ucu): "Kim sıfırladı → denetim izi (`session_events`, append-only)". Mandal KURULUYKEN
    Sıfırla bir `estop_mandali_sifirlandi` olayı yazar (neden = mandalın kaynağı); mandal yokken Sıfırla iz YAZMAZ."""
    o.api._emergency_stop_all("stm_watchdog_timeout")
    assert o.c.post("/api/hardware/estop_mandali/sifirla", json={"onay": True}).status_code == 200
    assert (
        o.c.post("/api/hardware/estop_mandali/sifirla", json={"onay": True}).status_code == 200
    )  # mandal yokken: iz yazılmaz

    with o.db._get_connection() as conn:
        satirlar = conn.execute(
            "SELECT severity, payload FROM session_events WHERE event_type = ?", ("estop_mandali_sifirlandi",)
        ).fetchall()
    assert len(satirlar) == 1, f"Sıfırla denetim izi: {len(satirlar)} satır (1 bekleniyor)"
    assert satirlar[0][0] == "warning"
    assert json.loads(satirlar[0][1]).get("neden") == "stm_watchdog_timeout", satirlar[0][1]


# ── K3: döngü kollarının OLUMLU kontrolü — onaylı döngü GERÇEK HC ile gerçekten SÜRER ─────────────────────
class _SahteKamera:
    def __init__(self, *a, **k):
        pass

    def isOpened(self):  # noqa: N802
        return True

    def read(self):
        import numpy as np

        return True, np.zeros((8, 8, 3), dtype=np.uint8)

    def release(self):
        pass


@pytest.fixture
def dongu(monkeypatch, tmp_path):
    """NESLI kapısının `dongu` fikstürüyle AYNI kurulum: GERÇEK `_ai_pro_loop`, sahte kamera, GERÇEK HC."""
    from kayitci_donanim import gercek_hc
    from servers import ai_pro_hedef

    ns = ap.kur(monkeypatch, tmp_path, dongu_noop=False)
    monkeypatch.setattr(ns.air.cv2, "VideoCapture", _SahteKamera)
    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", lambda self: None)
    canli = {"n": 0}
    gercek = ns.air._ai_pro_loop

    def _sayan(*a, **k):
        canli["n"] += 1
        try:
            return gercek(*a, **k)
        finally:
            canli["n"] -= 1

    monkeypatch.setattr(ns.air, "_ai_pro_loop", _sayan)
    ns.canli = canli
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.air._ai_loop_active = False
        ap.bekle(lambda: canli["n"] == 0, 5)
        ns.geri()


def test_KARSIT_i4F17_onayli_AI_Pro_DONGUSU_GERCEK_HC_ile_SURER_olumlu_kontrol(dongu):
    """Döngü kolları (tahmin sırasında E-stop, İG-5.11) yalnız sürüşün YOKLUĞUNU ölçer. Aşırı engelleyen bir
    gerileme (döngü 'aktif', hiç sürmez — sahte aktif tedavi) onları yeşil bırakır. Bu kol: durdurma YOKKEN
    onaylı döngü bobin 1-5'e AI dozunu (D_AI) GERÇEK HC üzerinden gerçekten gönderir."""
    o = dongu
    o.tahmin.engel = None
    n = ap.paket_sayisi(o)
    _pid, r = ap.onayli_baslat(o)
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:200]

    def _ai_dozu():
        return [d for d in ap.surus_paketleri(o, n) if any(abs(x - ap.D_AI) < 1e-6 for x in d[:5])]

    surdu = ap.bekle(lambda: bool(_ai_dozu()), 8)
    tahmin_sayisi = o.tahmin.sayi
    o.c.post("/api/ai/pro/stop")
    ap.bekle(lambda: o.canli["n"] == 0, 5)
    assert tahmin_sayisi > 0, "aparat: döngü tahmine hiç ulaşmadı"
    assert surdu, f"onaylı AI Pro döngüsü {tahmin_sayisi} tahmine rağmen GERÇEK HC'ye hiç AI dozu göndermedi"
