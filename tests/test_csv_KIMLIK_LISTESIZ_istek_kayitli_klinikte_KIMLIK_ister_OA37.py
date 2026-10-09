# -*- coding: utf-8 -*-
"""O-A3.7 (2-B incelemesi) · S-D.1 [ÖNERİLEN UYGULANDI, Y123] — `/api/history/export_csv` kimlik LİSTESİZ ("Tümünü") istekte kayıtlı
operatörlü klinikte KİMLİK ister.

ÖLÇÜLEN KUSUR: uç `session_ids` boşken ("Boş = tümü") kliniğin TÜM seans geçmişini (hasta adı, notlar — PII) kimliksiz isteğe veriyordu.
Arayüz kapısı B2-3.4 ile kapandı (kimliksizken id listesi gönderilir), uç kendisi kapsamsızdı: jetonsuz bir LAN istemcisi ya da kilit
sonrası bir sekme tek istekle tüm klinik dökümünü alabiliyordu. Y103 (sahip): kayıtlı operatörlü klinikte kimse seçili değilse listeler
kayıt GÖSTERMEZ — bu uç onun dışa aktarma yüzüdür.
UYGULANAN (önerilen, geri alınabilir): kayıtlı operatörlü klinikte kimlik listesiz istek jetonsuz 428 "Operatör seçin"; kimlikli hekim
bugünkü gibi tümünü alır (rol modeli yok, A-28); operatörsüz klinik (Kural 2) ve kimlik listeli istek DEĞİŞMEZ.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database import sqlcipher_util as su
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import history_router as hr
    from servers import operator_tokens

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    for ad in ("Mia", "Pamuk", "Tarcin"):
        sid = tdb.start_session(treatment_mode="Manuel", patient_name=ad)
        tdb.end_session(sid, duration_minutes=5)
    api.app.dependency_overrides[hr.get_db] = lambda: tdb
    c = TestClient(api.app, client=("127.0.0.1", 53370))

    def _sil():
        for op in c.get("/api/operators").json().get("data", []):
            c.post("/api/operators/remove", json={"email": op["email"]})

    operator_tokens.temizle_hepsi()
    _sil()
    try:
        yield type("O", (), {"tdb": tdb, "c": c})
    finally:
        operator_tokens.temizle_hepsi()
        _sil()
        api.app.dependency_overrides.pop(hr.get_db, None)
        tdb.close()


def _kayitli(o) -> str:
    r = o.c.post("/api/operators/enroll", json={"email": AYSE, "display_name": "Dr. Ayşe", "pin": "123456"})
    assert r.status_code == 200, r.text[:200]
    return o.c.post("/api/operators/verify", json={"email": AYSE, "pin": "123456"}).json()["operator_token"]


def test_KRITIK_OA37_kayitli_klinikte_KIMLIKSIZ_TUMU_csv_428_ve_PII_vermez(o):
    _kayitli(o)
    r = o.c.get("/api/history/export_csv")
    assert r.status_code == 428, f"kimliksiz 'Tümünü' CSV kliniğin TÜM seans geçmişini verdi: {r.status_code}"
    assert "Mia" not in r.text and "Pamuk" not in r.text


def test_KARSIT_OA37_kayitli_klinikte_KIMLIKLI_hekim_TUMUNU_alir(o):
    jeton = _kayitli(o)
    r = o.c.get("/api/history/export_csv", headers={"X-PEMF-Operator": jeton})
    assert r.status_code == 200 and all(ad in r.content.decode("utf-8-sig") for ad in ("Mia", "Pamuk", "Tarcin"))


def test_KARSIT_OA37_OPERATORSUZ_klinik_Kural2_bugunku_gibi_tumu(o):
    r = o.c.get("/api/history/export_csv")
    assert r.status_code == 200 and "Tarcin" in r.content.decode("utf-8-sig")


def test_KARSIT_OA37_kimlik_LISTELI_istek_DEGISMEZ(o):
    _kayitli(o)
    with o.tdb._get_connection() as c:
        ilk = c.execute("SELECT id FROM treatment_sessions ORDER BY id LIMIT 1").fetchone()[0]
    r = o.c.get("/api/history/export_csv", params={"session_ids": str(ilk)})
    assert r.status_code == 200 and "Mia" in r.content.decode("utf-8-sig")
