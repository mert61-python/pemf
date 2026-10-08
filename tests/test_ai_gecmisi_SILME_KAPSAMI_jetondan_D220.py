# -*- coding: utf-8 -*-
"""D2.20 · B-3.38 (+ aday İG-6.19) · A-10 · A-56 · Y83 — AI geçmişi silme KAPSAMI jetondan; sahipsizlere dokunulmaz.

ÖLÇÜLEN KUSUR (DENETIM-03 B-3.38; ADAY-DOGRULAMA-D2 İG-6.19, A4 + orkestratör bağımsız): `/api/ai/log/delete_all` ve
`/api/ai/log/delete` kapsamı GÖVDEDEKİ `operator_email` beyanından alıyordu ve "kendi" kapsamına sahipsiz kayıtları da
katıyordu (`operator_email IS NULL OR = '' OR = ?`) → B'nin jetonuyla A beyan edilince A'nın geçmişi VACUUM'lu silindi;
her "kendi geçmişimi sil" kliniğin TÜM sahipsiz AI kayıtlarını da götürdü (K1–K5: sahipsiz 3/3); tekil sil sahipsiz kaydı sildi.

KURAL (sahip kararları A-10 · A-56 · Y83 — plandan üstün):
  * Kapsam OTURUM KİMLİĞİNDEN (`cozumlenmis_operator`: jeton; kayıtlı operatör yoksa — Kural 2 — beyan). Beyan jetonu ezemez.
  * "Kendi" kapsamı YALNIZ kimliğin kayıtları — sahipsizlere (`NULL`/`''`) dokunulmaz.
  * Sahipsizler yalnız "Tüm Klinik" kapsamından (`all_operators: true`, beyansız) silinir; tekil "Kaydı sil" sahipsizi SİLEMEZ (404).
  * Kayıtlı operatörlü cihazda kimliksiz silme (kendi ya da tüm klinik) → 428 "Operatör seçin"; iz `reddedildi`.
Karşıt: Kural 2 — kayıtlı operatörü olmayan tek hekimli klinik kilitlenmez (beyan = oturum kimliği; tüm klinik silinebilir).
GERÇEK: uçlar (TestClient — yerel istemci: silme uçları ayrıcalıklı, `_enforce_privileged`), `operator_tokens`, `auth_db`, tedavi DB'si (geçici). Ölçüt ham SQL sayımı.
"""

import json

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
MEHMET = "dr.mehmet@klinik.com"
TEK = "tek@klinik.com"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import operator_tokens

    db = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    yerel = TestClient(api.app, client=("127.0.0.1", 51634))
    lan = TestClient(api.app, client=("192.168.1.90", 51635))

    def _sil():
        for op in yerel.get("/api/operators").json().get("data", []):
            yerel.post("/api/operators/remove", json={"email": op["email"]})

    operator_tokens.temizle_hepsi()
    _sil()
    try:
        yield type("O", (), {"db": db, "yerel": yerel, "lan": lan})
    finally:
        operator_tokens.temizle_hepsi()
        _sil()
        db.close_connections()


def _iki_hekim(o):
    j = {}
    for e in (AYSE, MEHMET):
        assert (
            o.yerel.post("/api/operators/enroll", json={"email": e, "display_name": e, "pin": "123456"}).status_code
            == 200
        )
        j[e] = o.yerel.post("/api/operators/verify", json={"email": e, "pin": "123456"}).json()["operator_token"]
    return j


def _tohum(o, a=AYSE, b=MEHMET):
    """İG-6.19 tohumu: A 3, B 2, sahipsiz 3 (2×'' + 1×NULL). Kimlikleri sahibe göre döndürür."""
    kim = {"A": [], "B": [], "S": []}
    for _ in range(3):
        kim["A"].append(o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="a", operator_email=a))
    for _ in range(2):
        kim["B"].append(o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="b", operator_email=b))
    for _ in range(3):
        kim["S"].append(o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="s", operator_email=""))
    with o.db._get_connection() as c:
        c.execute("UPDATE ai_analyses SET operator_email = NULL WHERE id = ?", (kim["S"][-1],))
        c.commit()
    return kim


def _kalan(o, kim):
    with o.db._get_connection() as c:
        return {
            k: c.execute(
                f"SELECT COUNT(*) FROM ai_analyses WHERE id IN ({','.join('?' for _ in v)})", list(v)
            ).fetchone()[0]
            for k, v in kim.items()
        }


def _b(jeton):
    return {"X-PEMF-Operator": jeton} if jeton else {}


def _toplu(o, beyan="", jeton="", tum=False):
    govde = {"confirm": "DELETE_ALL", "operator_email": beyan}
    if tum:
        govde["all_operators"] = True
    return o.yerel.post("/api/ai/log/delete_all", json=govde, headers=_b(jeton))


def _tekil(o, kimlik, beyan="", jeton=""):
    return o.yerel.post("/api/ai/log/delete", json={"id": kimlik, "operator_email": beyan}, headers=_b(jeton))


# ─────────────────────────── toplu ("Geçmişi sil") ───────────────────────────


def test_KRITIK_K1_kendi_kapsami_SAHIPSIZLERE_dokunmaz(o):
    """A-56. MUTASYON: WHERE'e `IS NULL OR = ''` geri koymak → KIRMIZI."""
    j = _iki_hekim(o)
    kim = _tohum(o)
    r = _toplu(o, AYSE, j[AYSE])
    assert r.status_code == 200, r.text[:200]
    assert _kalan(o, kim) == {"A": 0, "B": 2, "S": 3}, "kendi geçmişini silmek sahipsiz kayıtları da götürdü"


def test_KRITIK_K4_baska_hekimin_JETONU_beyani_EZER(o):
    """A-10 (planın kapısı: A'nın jetonu + `operator_email=B` → B'nin kayıtları durur). MUTASYON: kapsamı
    `payload.operator_email`den okumak → KIRMIZI."""
    j = _iki_hekim(o)
    kim = _tohum(o)
    r = _toplu(o, MEHMET, j[AYSE])
    assert r.status_code == 200, r.text[:200]
    assert _kalan(o, kim) == {"A": 0, "B": 2, "S": 3}, "beyan edilen hekimin geçmişi başka hekimin jetonuyla silindi"


def test_KRITIK_K3_kimliksiz_kendi_kapsami_428_hicbir_sey_silinmez(o):
    _iki_hekim(o)
    kim = _tohum(o)
    r = _toplu(o, MEHMET)
    assert r.status_code == 428 and "Operatör seçin" in r.json().get("detail", ""), r.text[:200]
    assert _kalan(o, kim) == {"A": 3, "B": 2, "S": 3}


def test_KRITIK_kimliksiz_TUM_KLINIK_silme_de_428(o):
    _iki_hekim(o)
    kim = _tohum(o)
    r = _toplu(o, "", "", tum=True)
    assert r.status_code == 428, r.text[:200]
    assert _kalan(o, kim) == {"A": 3, "B": 2, "S": 3}
    iz = o.db.denetim_oku(50, "ai_log.delete_all")
    assert [(s["operator_email"], s["outcome"]) for s in iz] == [("", "reddedildi")], iz


def test_KARSIT_Y83_TUM_KLINIK_kapsami_sahipsizleri_de_siler_iz_jeton_sahibine(o):
    j = _iki_hekim(o)
    kim = _tohum(o)
    r = _toplu(o, "", j[AYSE], tum=True)
    assert r.status_code == 200 and r.json()["deleted"] == 8, r.text[:200]
    assert _kalan(o, kim) == {"A": 0, "B": 0, "S": 0}
    iz = o.db.denetim_oku(50, "ai_log.delete_all")
    assert [(s["operator_email"], s["outcome"]) for s in iz] == [(AYSE, "ok")], iz
    assert json.loads(iz[0]["detail"] or "{}").get("all_operators") is True


def test_KARSIT_beyan_ve_bayrak_birlikte_ise_DAR_kapsam_kazanir(o):
    j = _iki_hekim(o)
    kim = _tohum(o)
    r = _toplu(o, AYSE, j[AYSE], tum=True)
    assert r.status_code == 200, r.text[:200]
    assert _kalan(o, kim) == {"A": 0, "B": 2, "S": 3}


# ─────────────────────────── tekil ("Kaydı sil") ───────────────────────────


@pytest.mark.parametrize("sira", [0, 2], ids=["bos_dize", "NULL"])
def test_KRITIK_K6_K7_tekil_SAHIPSIZ_kayit_404_ve_durur(o, sira):
    """Y83. MUTASYON: tekil WHERE'e sahipsiz dalını geri koymak → KIRMIZI."""
    j = _iki_hekim(o)
    kim = _tohum(o)
    hedef = kim["S"][sira]
    r = _tekil(o, hedef, AYSE, j[AYSE])
    assert r.status_code == 404, r.text[:200]
    assert _kalan(o, {"x": [hedef]}) == {"x": 1}


def test_KRITIK_tekil_BASKA_hekimin_kaydi_beyanla_silinemez(o):
    j = _iki_hekim(o)
    kim = _tohum(o)
    r = _tekil(o, kim["B"][0], MEHMET, j[AYSE])
    assert r.status_code == 404 and _kalan(o, {"x": [kim["B"][0]]}) == {"x": 1}, r.text[:200]


def test_KRITIK_tekil_kimliksiz_428(o):
    _iki_hekim(o)
    kim = _tohum(o)
    r = _tekil(o, kim["A"][0], AYSE)
    assert r.status_code == 428 and _kalan(o, {"x": [kim["A"][0]]}) == {"x": 1}, r.text[:200]


def test_KARSIT_tekil_KENDI_kaydi_silinir_jeton_kimligiyle(o):
    j = _iki_hekim(o)
    kim = _tohum(o)
    r = _tekil(o, kim["A"][0], "", j[AYSE])
    assert r.status_code == 200 and _kalan(o, {"x": [kim["A"][0]]}) == {"x": 0}, r.text[:200]


# ─────────────────────────── Kural 2 ───────────────────────────


def test_KARSIT_KURAL2_operatorsuz_klinik_KILITLENMEZ(o):
    """Kayıtlı operatör yok: kimlik = beyan (oturum e-postası). Kendi kapsamı kendi + SAHİPSİZ (Y105 — 2-B2; önce A-56 gereği
    yalnız kendi idi); başka e-postalı kayıt durur; tüm klinik siler."""
    kim = _tohum(o, a=TEK, b="eski@klinik.com")
    r = _tekil(o, kim["A"][0], TEK)
    assert r.status_code == 200, r.text[:200]
    r = _toplu(o, TEK)
    assert r.status_code == 200, r.text[:200]
    assert _kalan(o, kim) == {"A": 0, "B": 2, "S": 0}  # Y105: operatörsüz cihazda sahipsizler "kendi"nindir
    r = _toplu(o, "", "", tum=True)
    assert r.status_code == 200 and _kalan(o, kim) == {"A": 0, "B": 0, "S": 0}, f"Kural 2 kilitlendi: {r.text[:200]}"
