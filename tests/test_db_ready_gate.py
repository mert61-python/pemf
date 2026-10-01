# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KAYITSIZ TEDAVİ KAPISI — DB hazır değilse seans başlamaz (2026-08-09 denetimi, ENGEL).

ARIZA: seans başlatma yolundaki TÜM DB yazımları bilinçli olarak "best-effort"tu (DB hatası
bobinleri durdurmasın). Ama BAŞLANGIÇTA bunun sonucu şuydu:

    DB hiç açılamıyor → `db_session_id=None` → seans satırı YOK, coil-run YOK, sensör YOK
                      → ama bobinler ENERJİLENİYOR ve tedavi UYGULANIYOR, üstelik SESSİZCE.

Hastanın aldığı doz geriye dönük olarak BİLİNEMEZ hâle geliyordu: doz takibi, yan etki
soruşturması ve yasal saklama yükümlülüğünün tamamı bu kayda dayanır.

⚠️ KAPI YALNIZ BAŞLATMADADIR. Durdurma yolları (session/stop, emergency_stop) BU KONTROLDEN
GEÇMEZ — DB çökükken tedaviyi durduramamak asıl tehlike olurdu. Bu dosya iki yönü de kilitler.
"""

import pytest
from fastapi.testclient import TestClient
from topoloji import ESP_BOBIN, TUM_ESP, TUM_STM  # faz 4: literal bobin numarasi YASAK


@pytest.fixture(autouse=True)
def _esp_acik(monkeypatch):
    """⚠️ ESP ALT SİSTEMİ AÇIK (2026-09-12).

    Bu dosya ESP bobinleriyle (6-8) seans açıyor — STM donanımı gerektirmesin diye. ESP
    kapalıyken `/session/start` artık o bobinleri kapsamdan ÇIKARIYOR ve "hiçbir bobin
    sürülmedi" diye reddediyor (hayalet bobin-8 kaydını önleyen düzeltme; sahip bildirimi:
    "bobin 8 görünüyor ama aslında çalışmıyor").

    Kural: ESP kodu SİLİNMEZ, testler `PEMF_ESP_ENABLED=1` ile KOŞMAYA DEVAM EDER
    (bkz. test_internetsiz_ve_esp_kapali.py::test_KRITIK_bayrakla_ESP_GERI_GELIR).
    ⚠️ `monkeypatch` ile: modül seviyesinde `os.environ` yazmak sonraki test modüllerine
    SIZAR ve "ESP kapalı" kapılarını sessizce yeşile boyardı.
    """
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")


@pytest.fixture(scope="module")
def api():
    from servers import api_server

    return api_server


@pytest.fixture(scope="module")
def client(api):
    return TestClient(api.app, client=("127.0.0.1", 51234))


def _seans_govdesi():
    return {
        "mode": "Manuel",
        "frequency": 50,
        "duty": 25,
        "intensity": 2,
        "duration_minutes": 5,
        "coil_ids": [ESP_BOBIN],
        "patient_name": "Pamuk",
    }


@pytest.fixture(autouse=True)
def _seans_temiz(client):
    """Uçlar süreç-geneli durumu paylaşır: sızan bir aktif seans SONRAKİ testi 409'a düşürür
    ve gerçek arıza gibi görünürdü (mutasyon turunda bu yanlış sinyali verdi)."""
    yield
    client.post("/api/session/stop", json={})


@pytest.fixture
def db_bozuk(api, monkeypatch):
    """Tıbbi kayıt DB'si açılamıyor durumunu modelle."""
    monkeypatch.setattr(api, "_get_treatment_db", lambda: None)


# ── başlatma kapısı ──────────────────────────────────────────────────────────


def test_KRITIK_DB_hazir_degilse_seans_BASLAMAZ(client, db_bozuk):
    r = client.post("/api/session/start", json=_seans_govdesi())
    assert r.status_code == 503, f"kayitsiz tedavi basladi ({r.status_code})"
    assert "kayıt" in r.json()["detail"].lower()


def test_KRITIK_reddedilen_seans_BOBINLERI_ENERJILEMEZ(client, api, db_bozuk, monkeypatch):
    """Kapı, donanıma tek komut gitmeden ÖNCE olmalı — yoksa bobin açılır ama seans 'yok'
    sayılır: süre-watchdog'u olmayan gözetimsiz sürüş (setin en zararlı hatası)."""
    gidilen = []
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: gidilen.append(topic) or True)

    class _HW:
        def __init__(self):
            self.cagrildi = []

        def update_coil(self, *a, **k):
            self.cagrildi.append(a)
            return True

        def stop_all_coils(self):
            return True

    hw = _HW()
    monkeypatch.setattr(api.state, "hardware", hw)

    assert client.post("/api/session/start", json=_seans_govdesi()).status_code == 503
    assert gidilen == [], f"reddedilen seansta ESP'ye komut gitti: {gidilen}"
    assert hw.cagrildi == [], "reddedilen seansta STM bobini surulmeye calisildi"


def test_KRITIK_reddedilen_seans_AKTIF_SAYILMAZ(client, api, db_bozuk):
    """Yarım-açık durum bırakılmamalı: reddedilen seans `is_active` bırakırsa sonraki
    gerçek seans 409 ile reddedilir ve cihaz kilitlenir."""
    client.post("/api/session/start", json=_seans_govdesi())
    with api._session_lock:
        assert api._active_session.get("is_active") is not True


def test_DB_hazirsa_seans_NORMAL_baslar(client, api, monkeypatch):
    """Regresyon kapısı: kapı sağlıklı kurulumda tedaviyi ENGELLEMEMELİ."""
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: True)
    monkeypatch.setattr(api.state, "hardware", None)
    r = client.post("/api/session/start", json=_seans_govdesi())
    assert r.status_code == 200, r.text[:300]
    client.post("/api/session/stop", json={})


# ── durdurma yolları ASLA kapıya takılmaz ────────────────────────────────────


def test_KRITIK_DB_bozukken_ACIL_DURDURMA_CALISIR(client, api, db_bozuk, monkeypatch):
    """DB arızası acil durdurmayı engellerse hasta bobinlerin altında kalır.

    ⚠️ D1.04 (B-10.36): bu test eskiden yalnız HTTP 200'e bakıyordu ve `state.hardware=None`
    kuruyordu — "DB yoksa erken 200 dön" mutantında YEŞİL kalıyordu (kör). Artık GERÇEK
    `HardwareController`'ın STOP'u verdiği, paketin donanım kuyruğuna gittiği (firmware aynasıyla
    çözülür, 7 STM bobininde duty 0) ve her ESP bobinine STOP yayınının DENENDİĞİ ölçülür.
    Teyit (`confirmed`) BİLEREK ölçülmez: ölçütü A-63 belirler (D1.105, B-1.23'ten sonra)."""
    from kayitci_donanim import gercek_hc, paket_coz

    yayinlar = []

    # Kayıtçı False döner: iddia "yayın DENENDİ mi" (Y8), başarı değil. True dönseydi her ESP bobini
    # için 2 sn'lik ack-bekçisi iş parçacığı doğar ve test bittikten sonra bildirim yazardı (sızıntı).
    def _kaydet(topic, payload):
        yayinlar.append((topic, payload))
        return False

    monkeypatch.setattr(api, "_mqtt_publish", _kaydet)
    with gercek_hc() as hc:
        monkeypatch.setattr(api.state, "hardware", hc)
        # Bağımsız inceleme (r1): E-stop'tan ÖNCE bobinler GERÇEKTEN sürülüyor olmalı — yoksa "son paket
        # duty 0" her pakette zaten doğrudur ve `stop_all_coils` bobin durumunu sıfırlamasa da kapı
        # yeşil kalırdı (eski duty ile giden E-stop paketi).
        surulen = sorted({1, max(TUM_STM)})
        for b in surulen:
            assert hc.update_coil(b, 100.0, 30.0, 0.0, duration=1) is True
        once = paket_coz(hc.core._hw_send_queue.paketler[-1])[0]
        assert all(once[b - 1] == pytest.approx(0.30) for b in surulen), f"senaryo: bobinler sürülmüyor {once}"
        r = client.post("/api/hardware/emergency_stop")
        assert r.status_code == 200, f"DB bozukken acil durdurma reddedildi: {r.status_code}"
        assert hc.stop_all_cagri >= 1, "DB bozukken acil durdurma donanıma STOP VERMEDİ (yalnız 200 döndü)"
        assert r.json().get("stmStopped") is True, f"yanıt STM STOP'unu bildirmiyor: {r.json()!r}"
        assert hc.core._hw_send_queue.paketler, "STOP paketi donanım kuyruğuna HİÇ gitmedi"
        duty = paket_coz(hc.core._hw_send_queue.paketler[-1])[0]
        assert all(d == 0.0 for d in duty), f"son paket STOP değil (duty): {duty}"
    for cid in TUM_ESP:
        assert any(
            t == f"pemf/coil/{cid}/control" and p.get("command") == "stop" and p.get("emergency") is True
            for t, p in yayinlar
        ), f"ESP bobin {cid}'e acil STOP yayını DENENMEDİ (Y8: gönderim azaltılamaz)"


def test_KRITIK_DB_bozukken_SEANS_DURDURMA_CALISIR(client, api, db_bozuk, monkeypatch):
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: True)
    monkeypatch.setattr(api.state, "hardware", None)
    r = client.post("/api/session/stop", json={})
    assert r.status_code == 200, f"DB bozukken seans durdurma reddedildi: {r.status_code}"


def test_KRITIK_seans_ORTASINDA_DB_duserse_tedavi_KESILMEZ(client, api, monkeypatch):
    """Kapı yalnız başlatmada. Süren tedaviyi DB yüzünden kesmek hastaya zarar verir."""
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: True)
    monkeypatch.setattr(api.state, "hardware", None)
    assert client.post("/api/session/start", json=_seans_govdesi()).status_code == 200
    try:
        monkeypatch.setattr(api, "_get_treatment_db", lambda: None)  # DB seans ortasında düştü
        with api._session_lock:
            assert api._active_session.get("is_active") is True, "DB dusunce tedavi kesildi"
        assert client.get("/api/session/active").status_code == 200
    finally:
        client.post("/api/session/stop", json={})


# ── görünürlük: /api/health dbReady ──────────────────────────────────────────


def test_health_dbReady_TRUE_saglikli_kurulumda(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["dbReady"] is True


def test_KRITIK_health_dbReady_FALSE_DB_bozukken(client, db_bozuk):
    """Bu alan olmadan DB arızası ancak veteriner seans başlatmayı DENEYİNCE — yani hasta
    masadayken — görülüyordu."""
    r = client.get("/api/health")
    assert r.status_code == 200, "DB arizasi health'i DUSURMEMELI (backend ve E-stop ayakta)"
    assert r.json()["dbReady"] is False


def test_dbReady_ile_seans_kapisi_AYNI_kaynaktan(client, api, monkeypatch):
    """Tutarsızlık teşhis edilemez bir arıza sınıfıdır: 'sağlık yeşil ama seans 503'."""
    cagri = {"n": 0}

    def _sahte():
        cagri["n"] += 1
        return False, "test"

    monkeypatch.setattr(api, "_kayit_db_hazir", _sahte)

    assert client.get("/api/health").json()["dbReady"] is False
    assert client.post("/api/session/start", json=_seans_govdesi()).status_code == 503
    assert cagri["n"] == 2, "iki yol ayni yardimciyi kullanmiyor"


# ── veri katmanı sağlaması ───────────────────────────────────────────────────


def test_is_ready_saglam_dbde_True(temp_app_data):
    from database.treatment_history_db import TreatmentHistoryDB

    db = TreatmentHistoryDB(temp_app_data)
    try:
        assert db.is_ready() == (True, "")
    finally:
        db.close_connections()


def test_KRITIK_is_ready_BOZUK_dosyada_False(temp_app_data):
    """SQLCipher anahtarı yanlış / dosya bozuk → şema okunamaz. Bu, gerçek arızanın modeli."""
    from database.treatment_history_db import TreatmentHistoryDB

    db = TreatmentHistoryDB(temp_app_data)
    try:
        db.close_connections()
        (temp_app_data / "pemf_treatment_history.db").write_bytes(b"BU BIR SQLITE DOSYASI DEGIL" * 64)
        db._conn_generation += 1  # havuz bayat tanıtıcıyı yeniden açsın
        hazir, sebep = db.is_ready()
        assert hazir is False, "bozuk DB 'hazir' bildirildi"
        assert sebep, "sebep bos — teshis imkansiz"
    finally:
        db.close_connections()
