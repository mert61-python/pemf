# -*- coding: utf-8 -*-
"""D2-2.6 (2-D incelemesi A2) — KÖR KAPI: O-A3.7 / Y111 / E01 kapılarının ölçmediği kollar. Ürün BUGÜN doğru [ÖLÇTÜM sonda k4/k5/k6];
bu kapı onu kilitler (HEAD'de YEŞİL, aşağıdaki mutantlarda KIRMIZI).

YAŞAYAN MUTANTLAR (2-D kapılarında): k4_m1 CSV 428'i Y113 arıza iletisini kaybeder ("Operatör seçin" der) · k4_m2 CSV kimlik kararı katı
olmayan okumayla (kimlik DB arızasında FAIL-OPEN → tüm geçmiş) · k5_m1 / k5_m2 REPLACE_ALL için aynı ikisi · k5_m3 `cihazin_kendisinden_mi`
`X-Forwarded-For`'u yok sayar (yerel ters vekil arkasındaki LAN istemcisi "cihazın kendisi" sayılır — REPLACE_ALL / tümünü sil / kaydet) ·
k6_m1 aynı dakikadaki ikinci yedek ilkinin ÜZERİNE yazar.
Arıza EN ALT katta: Y113 kapısının `_Ariza`sı (gerçek SQLite kilidi `locking_mode=EXCLUSIVE`, SQLite olmayan dosya).
"""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient
from veri_tasima_aparati import PAROLA, cihaz_kur, disa_aktar, doldur, istekler, kapat, sayimlar, uclari_bagla

AYSE = "dr.ayse.d226@klinik.invalid"
ARIZA_BASI = "Cihazın kimlik veritabanı okunamıyor"


@pytest.fixture
def gecmis(tmp_path, monkeypatch):
    from database import sqlcipher_util as su
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import history_router as hr
    from servers import operator_tokens

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    for ad in ("Mia", "Pamuk"):
        tdb.end_session(tdb.start_session(treatment_mode="Manuel", patient_name=ad), duration_minutes=5)
    api.app.dependency_overrides[hr.get_db] = lambda: tdb
    c = TestClient(api.app, client=("127.0.0.1", 53260))

    def _sil():
        for op in c.get("/api/operators").json().get("data", []):
            c.post("/api/operators/remove", json={"email": op["email"]})

    operator_tokens.temizle_hepsi()
    _sil()
    try:
        yield type("G", (), {"c": c, "tmp": tmp_path})
    finally:
        operator_tokens.temizle_hepsi()
        _sil()
        api.app.dependency_overrides.pop(hr.get_db, None)
        tdb.close()


@pytest.mark.parametrize("kip", ["kilit", "bozuk_dosya"])
def test_KAPI_D2_2_6_kimlik_DB_arizasinda_TUMU_csv_FAIL_CLOSED_ve_ARIZAYI_soyler(gecmis, monkeypatch, kip):
    from test_kimlik_DB_okunamazken_ileti_ARIZA_ve_CARE_Y113 import _Ariza

    assert (
        gecmis.c.post(
            "/api/operators/enroll", json={"email": AYSE, "display_name": "D226", "pin": "123456"}
        ).status_code
        == 200
    )
    with _Ariza(monkeypatch, gecmis.tmp, kip):
        r = gecmis.c.get("/api/history/export_csv")
    govde = r.content.decode("utf-8-sig", "replace")
    assert r.status_code == 428 and "Mia" not in govde, f"kimlik DB arızasında kimliksiz 'Tümü' CSV: {r.status_code}"
    d = r.json().get("detail", "")
    assert d.startswith(ARIZA_BASI) and "Operatör seçin" not in d, f"428 iletisi arızayı söylemiyor (Y113): {d[:80]!r}"


@pytest.fixture
def dolu(tmp_path, monkeypatch):
    from servers import api_server as api
    from servers import auth, operator_tokens

    monkeypatch.setattr(auth, "check_token", lambda t: t == "CIHAZ-TOKEN")
    ta, ha = cihaz_kur(monkeypatch, tmp_path / "A")
    uclari_bagla(monkeypatch, ta, ha)
    doldur(ta, ha, ["Mia"], seans_basi=1)
    paket = disa_aktar(api.app)
    tb, hb = cihaz_kur(monkeypatch, tmp_path / "B")
    uclari_bagla(monkeypatch, tb, hb)
    doldur(tb, hb, ["Zeytin"], seans_basi=1)
    operator_tokens.temizle_hepsi()
    try:
        yield type("D", (), {"app": api.app, "paket": paket, "tb": tb, "hb": hb, "tmp": tmp_path})
    finally:
        for op in istekler(api.app, [("GET", "/api/operators", None, None)])[0].json().get("data", []):
            istekler(api.app, [("POST", "/api/operators/remove", {"email": op["email"]}, None)])
        operator_tokens.temizle_hepsi()
        kapat(ta, ha, tb, hb)


@pytest.mark.parametrize("kip", ["kilit", "bozuk_dosya"])
def test_KAPI_D2_2_6_kimlik_DB_arizasinda_dolu_cihaza_REPLACE_ALL_FAIL_CLOSED_kayitlar_DEGISMEZ(dolu, monkeypatch, kip):
    from test_kimlik_DB_okunamazken_ileti_ARIZA_ve_CARE_Y113 import _Ariza

    r = istekler(
        dolu.app, [("POST", "/api/operators/enroll", {"email": AYSE, "display_name": "D226", "pin": "123456"}, None)]
    )
    assert r[0].status_code == 200
    once = sayimlar(dolu.tb, dolu.hb)
    govde = {"passphrase": PAROLA, "blob_b64": dolu.paket["data_b64"], "confirm": "REPLACE_ALL"}
    with _Ariza(monkeypatch, dolu.tmp, kip):
        (r1,) = istekler(dolu.app, [("POST", "/api/data/import", govde, None)])
    assert r1.status_code == 428 and sayimlar(dolu.tb, dolu.hb) == once, (
        f"kimlik DB arızasında REPLACE_ALL: {r1.status_code}"
    )
    d = r1.json().get("detail", "")
    assert d.startswith(ARIZA_BASI) and "Operatör seçin" not in d, f"428 iletisi arızayı söylemiyor (Y113): {d[:80]!r}"


def test_KAPI_D2_2_6_yerel_TERS_VEKIL_XFF_ile_gelen_LAN_istemcisi_cihazin_kendisi_SAYILMAZ(dolu, _masaustunu_koru):
    """Cihazda yerel ters vekil (XFF ekler — 2-C incelemesi `eb0cfc9` belgesi) arkasındaki eşleşmiş LAN istemcisi: soket 127.0.0.1."""
    once = sayimlar(dolu.tb, dolu.hb)
    bas = {"X-API-Key": "CIHAZ-TOKEN", "X-Forwarded-For": "192.168.1.50"}
    govde = {"passphrase": PAROLA, "blob_b64": dolu.paket["data_b64"], "confirm": "REPLACE_ALL"}
    (r1,) = istekler(dolu.app, [("POST", "/api/data/import", govde, bas)], client=("127.0.0.1", 53261))
    (r2,) = istekler(
        dolu.app,
        [("POST", "/api/data/export", {"passphrase": PAROLA, "kaydet": True}, bas)],
        client=("127.0.0.1", 53262),
    )
    assert r1.status_code == 403 and sayimlar(dolu.tb, dolu.hb) == once, (
        f"vekil arkasından REPLACE_ALL: {r1.status_code}"
    )
    assert r2.status_code == 400 and list(_masaustunu_koru.iterdir()) == [], (
        f"vekil arkasından kaydet: {r2.status_code}"
    )


def test_KAPI_D2_2_6_ayni_dakikada_IKINCI_yedek_ilkinin_UZERINE_yazmaz(dolu, _masaustunu_koru):
    from utils.data_export import decrypt_bundle

    (r1,) = istekler(
        dolu.app, [("POST", "/api/data/export", {"passphrase": "birinci-parola-d226", "kaydet": True}, None)]
    )
    (r2,) = istekler(
        dolu.app, [("POST", "/api/data/export", {"passphrase": "ikinci-parola-d226", "kaydet": True}, None)]
    )
    assert r1.status_code == r2.status_code == 200
    y1, y2 = r1.json()["yol"], r2.json()["yol"]
    assert y1 != y2, f"ikinci yedek AYNI ada yazıldı: {y1}"
    from pathlib import Path

    assert decrypt_bundle(Path(y1).read_bytes(), "birinci-parola-d226")["treatment_sessions"], (
        "ilk yedek bozuldu / ezildi"
    )
    _ = base64
