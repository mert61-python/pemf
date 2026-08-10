# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""OPERATÖR KİMLİĞİ SUNUCU TARAFINDA (2026-08-09 denetimi, Tier 1).

ARIZA: `/api/operators/verify` PIN'i doğruluyor ama yalnız `{ok, email}` dönüyordu — doğrulama
ile sonraki YAZMALAR arasında hiçbir bağ yoktu. `operator_email` her uçta İSTEMCİ BEYANIYDI.

Sonuç: cihaza erişebilen herkes (klinik ağındaki bir cihaz, eski bir mobil kopya, elle atılan
tek bir istek) başka bir hekimin adıyla seans başlatabilir, AI analizi ve hasta kaydı
yazabilirdi. PBKDF2 + üstel kilitlenme + PIN'in tamamı, kimsenin doğrulamadığı bir dize
yüzünden anlamsız kalıyordu — üstelik özelliğin AMACI kaydın doğru hekime atfedilmesiydi.

YENİ KURAL (bkz. servers/auth.cozumlenmis_operator):
  1) Jeton varsa → e-posta JETONDAN (beyan yok sayılır)
  2) Jeton yok + cihazda kayıtlı operatör yok → beyan kabul (tek veterinerli klinik bozulmaz)
  3) Jeton yok + beyan KAYITLI bir operatöre ait → REDDEDİLİR (kayıt sahipsiz yazılır)

⚠️ Reddediş işlemi DURDURMAZ, yalnız atfı düşürür: seans başlatmayı 403'e çevirmek hasta
masadayken eski bir istemci yüzünden tedaviyi engellerdi.
"""

import os

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def api():
    from servers import api_server

    return api_server


@pytest.fixture(scope="module")
def client(api):
    return TestClient(api.app, client=("127.0.0.1", 51234))


@pytest.fixture(autouse=True)
def _temiz(client):
    from servers import operator_tokens

    operator_tokens.temizle_hepsi()
    for o in client.get("/api/operators").json().get("data", []):
        client.post("/api/operators/remove", json={"email": o["email"]})
    yield
    operator_tokens.temizle_hepsi()


def _kaydet(client, eposta, pin="123456"):
    r = client.post("/api/operators/enroll", json={"email": eposta, "display_name": eposta, "pin": pin})
    assert r.status_code == 200, r.text[:200]
    return eposta


def _jeton(client, eposta, pin="123456"):
    r = client.post("/api/operators/verify", json={"email": eposta, "pin": pin})
    assert r.status_code == 200, r.text[:200]
    return r.json()["operator_token"]


def _coz(api, beyan="", jeton=""):
    """`cozumlenmis_operator`ı sahte bir istekle çağır."""
    from servers.auth import cozumlenmis_operator

    class _Sahte:
        headers = {}
        query_params = {}

    r = _Sahte()
    r.headers = {"X-PEMF-Operator": jeton} if jeton else {}
    r.query_params = {}
    return cozumlenmis_operator(r, beyan)


# ── jeton üretimi ────────────────────────────────────────────────────────────


def test_dogrulama_JETON_uretir(client):
    e = _kaydet(client, "a@klinik.com")
    r = client.post("/api/operators/verify", json={"email": e, "pin": "123456"})
    assert r.status_code == 200
    assert r.json().get("operator_token"), "PIN dogrulandi ama jeton verilmedi"
    assert r.json().get("expires_in", 0) > 0


def test_YANLIS_pin_jeton_VERMEZ(client):
    e = _kaydet(client, "a@klinik.com")
    r = client.post("/api/operators/verify", json={"email": e, "pin": "000000"})
    assert r.status_code == 401
    assert "operator_token" not in r.text


# ── çözümleme kuralları ──────────────────────────────────────────────────────


def test_KRITIK_kanitsiz_beyan_KAYITLI_hekimi_TAKLIT_EDEMEZ(client, api):
    """Asıl açık: jeton olmadan başka bir hekimin adına yazmak."""
    _kaydet(client, "gercek@klinik.com")
    assert _coz(api, beyan="gercek@klinik.com") == "", "kanitsiz beyanla kayitli hekim taklit edildi"


def test_jetonlu_istek_JETONDAKI_kimligi_kullanir(client, api):
    _kaydet(client, "a@klinik.com")
    t = _jeton(client, "a@klinik.com")
    assert _coz(api, beyan="", jeton=t) == "a@klinik.com"


def test_KRITIK_jeton_BEYANI_EZER(client, api):
    """Jeton A'ya ait ama gövde B diyor → A yazılmalı. Beyan asla kazanamaz."""
    _kaydet(client, "a@klinik.com")
    _kaydet(client, "b@klinik.com")
    t = _jeton(client, "a@klinik.com")
    assert _coz(api, beyan="b@klinik.com", jeton=t) == "a@klinik.com"


def test_kayitli_operator_YOKKEN_beyan_kabul_edilir(api):
    """GERİYE UYUM: tek veterinerli klinik ve eski istemciler bozulmamalı; ortada taklit
    edilecek bir kimlik de yoktur."""
    assert _coz(api, beyan="tek@vet.com") == "tek@vet.com"


def test_gecersiz_jeton_beyana_DUSMEZ_kayitliysa(client, api):
    _kaydet(client, "gercek@klinik.com")
    assert _coz(api, beyan="gercek@klinik.com", jeton="UYDURMA-JETON") == ""


def test_bos_beyan_bos_doner(api):
    assert _coz(api, beyan="") == ""


def test_eposta_normalize_edilir(client, api):
    _kaydet(client, "a@klinik.com")
    t = _jeton(client, "a@klinik.com")
    assert _coz(api, jeton=t) == "a@klinik.com"
    assert _coz(api, beyan="  YENI@Klinik.COM  ") == "yeni@klinik.com"


# ── jeton yaşam döngüsü ──────────────────────────────────────────────────────


def test_KRITIK_cihazdan_CIKARILAN_operatorun_jetonu_OLUR(client, api):
    """Aksi hâlde çıkarılmış bir hekim, jeton süresi dolana kadar (12 saat) onun adına kayıt
    yazmaya devam ederdi."""
    _kaydet(client, "ayrilan@klinik.com")
    t = _jeton(client, "ayrilan@klinik.com")
    assert _coz(api, jeton=t) == "ayrilan@klinik.com"

    assert client.post("/api/operators/remove", json={"email": "ayrilan@klinik.com"}).status_code == 200
    assert _coz(api, jeton=t) == "", "cikarilan operatorun jetonu hala gecerli"


def test_suresi_dolan_jeton_GECERSIZ(client, api, monkeypatch):
    from servers import operator_tokens

    _kaydet(client, "a@klinik.com")
    t = _jeton(client, "a@klinik.com")
    import time as _t

    ileri = _t.time() + operator_tokens.TTL_SANIYE + 10
    monkeypatch.setattr(operator_tokens.time, "time", lambda: ileri)
    assert operator_tokens.cozumle(t) == "", "suresi dolan jeton kabul edildi"


def test_jeton_kullanimda_TAZELENIR(client):
    """Seans SÜRERKEN jetonun ölmesi, tedavinin kaydını sahipsiz bırakırdı."""
    import time as _t

    from servers import operator_tokens

    _kaydet(client, "a@klinik.com")
    t = _jeton(client, "a@klinik.com")
    yarim = _t.time() + operator_tokens.TTL_SANIYE - 5
    with_patch = operator_tokens.time
    eski = with_patch.time
    try:
        with_patch.time = lambda: yarim
        assert operator_tokens.cozumle(t) == "a@klinik.com"  # tazeler
        with_patch.time = lambda: yarim + operator_tokens.TTL_SANIYE - 5
        assert operator_tokens.cozumle(t) == "a@klinik.com", "tazeleme calismadi"
    finally:
        with_patch.time = eski


def test_jeton_sayisi_SINIRLI(client):
    """Erişimi olan biri sınırsız jeton üretip belleği şişirememeli."""
    from servers import operator_tokens

    operator_tokens.temizle_hepsi()
    for i in range(operator_tokens._MAX_JETON + 20):
        operator_tokens.uret(f"op{i}@klinik.com")
    assert operator_tokens.sayi() <= operator_tokens._MAX_JETON


# ── uçtan uca: seans kaydının sahibi ────────────────────────────────────────


def test_KRITIK_seans_TAKLIT_edilen_kimlikle_yazilmaz(client, api, monkeypatch):
    """Uçtan uca kapı: kayıtlı bir hekimi beyan eden kanıtsız bir seans isteği, o hekimin
    adına yazılmamalı (sahipsiz yazılır — tedavi ENGELLENMEZ)."""
    _kaydet(client, "gercek@klinik.com")
    yazilan = {}

    class _SahteDB:
        def start_session(self, **kw):
            yazilan.update(kw)
            return 1

        def __getattr__(self, ad):
            return lambda *a, **k: None

    monkeypatch.setattr(api, "_get_treatment_db", lambda: _SahteDB())
    monkeypatch.setattr(api, "_kayit_db_hazir", lambda: (True, ""))
    monkeypatch.setattr(api, "_mqtt_publish", lambda t, p: True)
    monkeypatch.setattr(api.state, "hardware", None)

    r = client.post(
        "/api/session/start",
        json={
            "mode": "Manuel",
            "frequency": 50,
            "duty": 25,
            "intensity": 2,
            "duration_minutes": 5,
            "coil_ids": [6],
            "patient_name": "Pamuk",
            "operator_email": "gercek@klinik.com",
        },
    )
    try:
        assert r.status_code == 200, r.text[:300]
        assert yazilan.get("operator_email") in (None, ""), (
            f"seans TAKLIT edilen kimlikle yazildi: {yazilan.get('operator_email')!r}"
        )
    finally:
        client.post("/api/session/stop", json={})


def test_seans_JETONLA_dogru_kimlige_yazilir(client, api, monkeypatch):
    _kaydet(client, "gercek@klinik.com")
    t = _jeton(client, "gercek@klinik.com")
    yazilan = {}

    class _SahteDB:
        def start_session(self, **kw):
            yazilan.update(kw)
            return 1

        def __getattr__(self, ad):
            return lambda *a, **k: None

    monkeypatch.setattr(api, "_get_treatment_db", lambda: _SahteDB())
    monkeypatch.setattr(api, "_kayit_db_hazir", lambda: (True, ""))
    monkeypatch.setattr(api, "_mqtt_publish", lambda t_, p: True)
    monkeypatch.setattr(api.state, "hardware", None)

    r = client.post(
        "/api/session/start",
        headers={"X-PEMF-Operator": t},
        json={
            "mode": "Manuel",
            "frequency": 50,
            "duty": 25,
            "intensity": 2,
            "duration_minutes": 5,
            "coil_ids": [6],
            "patient_name": "Pamuk",
            "operator_email": "BASKASI@klinik.com",
        },
    )
    try:
        assert r.status_code == 200, r.text[:300]
        assert yazilan.get("operator_email") == "gercek@klinik.com", (
            f"jeton yok sayildi: {yazilan.get('operator_email')!r}"
        )
    finally:
        client.post("/api/session/stop", json={})


def test_KRITIK_KAYIT_da_jeton_verir(client, api):
    """Kaydolan kişi ANINDA aktif olur (PIN yeniden sorulmaz). Jeton verilmezse şu tuzağa
    düşerdi: artık "kayıtlı operatör" olduğu için jetonsuz yazmaları reddedilir ve İLK
    operatörün TÜM kayıtları sessizce SAHİPSİZ yazılırdı."""
    r = client.post("/api/operators/enroll", json={"email": "ilk@klinik.com", "display_name": "İlk", "pin": "123456"})
    assert r.status_code == 200, r.text[:200]
    t = r.json().get("operator_token")
    assert t, "kayit jeton vermedi — ilk operatorun kayitlari sahipsiz kalirdi"
    assert _coz(api, jeton=t) == "ilk@klinik.com"


def test_PIN_degistirme_de_jeton_tazeler(client, api):
    e = _kaydet(client, "a@klinik.com", pin="111111")
    r = client.post(
        "/api/operators/enroll", json={"email": e, "display_name": "A", "pin": "222222", "eski_pin": "111111"}
    )
    assert r.status_code == 200, r.text[:200]
    assert _coz(api, jeton=r.json()["operator_token"]) == e
