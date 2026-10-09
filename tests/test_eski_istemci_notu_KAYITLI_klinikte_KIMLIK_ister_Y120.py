# -*- coding: utf-8 -*-
"""Y120 (S-C.2 · sahip kararı) — `session_id` GÖNDERMEYEN eski istemcinin (APK 2.3.34) gözlem notu da kayıtlı operatörlü klinikte
KİMLİK ister (428 "Operatör seçin"; Y107 / Y116 ile aynı ilke). Operatörsüz klinik (Kural 2) değişmez.

ÖLÇÜLEN (2-C inceleme A3 B5(iv) + önce-kırmızı): kayıtlı klinikte jetonsuz LAN `POST /api/session/notes {"notes": …, "patient_name": …}`
(`session_id` YOK) → 200; not, hasta adıyla bulunan son bitmiş seansın (BAŞKA hekimin) satırına kimliksiz yazılıyordu.
Bedel (sahip kabul etti): kayıtlı klinikte eski APK'lı telefon güncellenene dek not ekleyemez — ileti bunu söyler.
GERÇEK: uç (TestClient — LAN 192.168.1.96 / yerel), `operator_tokens`, `auth_db`, tedavi DB'si (geçici). Satır SQL ile, iz `denetim_oku`.
"""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
MEHMET = "dr.mehmet@klinik.com"
NOT = "Uyudu — Y120 eski istemci gozlemi"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import operator_tokens

    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: tdb)
    yerel = TestClient(api.app, client=("127.0.0.1", 52946))
    lan = TestClient(api.app, client=("192.168.1.96", 52947))

    def _sil():
        for op in yerel.get("/api/operators").json().get("data", []):
            yerel.post("/api/operators/remove", json={"email": op["email"]})

    operator_tokens.temizle_hepsi()
    _sil()
    try:
        yield type("O", (), {"tdb": tdb, "yerel": yerel, "lan": lan})
    finally:
        operator_tokens.temizle_hepsi()
        _sil()
        tdb.close_connections()


def _hekimler(o):
    j = {}
    for e in (AYSE, MEHMET):
        r = o.yerel.post("/api/operators/enroll", json={"email": e, "display_name": e, "pin": "123456"})
        assert r.status_code == 200, r.text[:200]
        j[e] = o.yerel.post("/api/operators/verify", json={"email": e, "pin": "123456"}).json()["operator_token"]
    return j


def _bitmis_seans(o, sahip=AYSE) -> int:
    sid = int(o.tdb.start_session(treatment_mode="Manuel", patient_name="Pamuk", operator_email=sahip))
    o.tdb.set_session_meta(sid, started_epoch=time.time() - 300)  # eski istemci dalı son 12 sa'te BAŞLAYANI arar
    o.tdb.end_session(sid, parameters={"frequency_hz": 50.0, "intensity_mt": 2.0}, duration_minutes=4)
    return sid


def _satir(o, sid):
    with o.tdb._get_connection() as c:
        return tuple(
            c.execute(
                "SELECT COALESCE(patient_notes,''), frequency_hz, intensity_mt, duration_minutes, session_status "
                "FROM treatment_sessions WHERE id = ?",
                (sid,),
            ).fetchone()
        )


def _iz(o):
    return [
        (s["operator_email"], s["outcome"], s["scope"], json.loads(s["detail"] or "{}"))
        for s in o.tdb.denetim_oku(50, "session.notes")
    ]


def _eski_istemci_notu(istemci, jeton=""):
    """APK 2.3.34 gövdesi: `session_id` YOK, hasta adı + (yok sayılan) doz alanları."""
    govde = {"notes": NOT, "patient_name": "Pamuk", "frequency": 999, "intensity": 9}
    return istemci.post("/api/session/notes", json=govde, headers={"X-PEMF-Operator": jeton} if jeton else {})


@pytest.mark.parametrize("yer", ["lan", "yerel"])
def test_KRITIK_kayitli_klinikte_SESSION_IDsiz_eski_istemci_notu_428_satir_DEGISMEZ_iz_REDDEDILDI_Y120(o, yer):
    _hekimler(o)
    sid = _bitmis_seans(o)
    once = _satir(o, sid)
    r = _eski_istemci_notu(getattr(o, yer))
    assert r.status_code == 428, (
        f"kayıtlı klinikte kimliksiz eski istemci notu {r.status_code} {r.text[:200]} (Y120: 428)"
    )
    detay = r.json().get("detail", "")
    assert "Operatör seçin" in detay and "güncelleyin" in detay, detay
    assert _satir(o, sid) == once, "reddedilen istek satırı DEĞİŞTİRDİ"
    assert any(oc == "reddedildi" and sc == "eski-istemci" for _e, oc, sc, _d in _iz(o)), _iz(o)
    # Kimlik kapısı güvenlik yollarını KAPATMAZ (Ö.4-Y8).
    assert o.lan.post("/api/session/stop", json={}).status_code == 200
    assert o.lan.post("/api/hardware/emergency_stop").status_code == 200


def test_KARSIT_KIMLIKLI_hekim_eski_istemci_yolundan_not_YAZAR_doz_DEGISMEZ_Y120(o):
    """Y107: kimlikli HER hekim not ekler (başkasının bitmiş seansına da); doz kaydı seansın kendisidir, istekle değişmez."""
    j = _hekimler(o)
    sid = _bitmis_seans(o)
    r = _eski_istemci_notu(o.lan, jeton=j[MEHMET])
    assert r.status_code == 200, r.text[:200]
    assert _satir(o, sid) == (NOT, 50.0, 2.0, 4, "completed")
    assert any(e == MEHMET and sc == f"id={sid}" for e, _oc, sc, _d in _iz(o)), _iz(o)


def test_KARSIT_KURAL2_operatorsuz_klinikte_eski_istemci_notu_YAZILIR_Y120(o):
    """Kural 2: kayıtlı operatör YOKSA davranış değişmez — eski istemci notu jetonsuz yazılır (doz yine değişmez)."""
    sid = _bitmis_seans(o)
    r = _eski_istemci_notu(o.lan)
    assert r.status_code == 200, r.text[:200]
    assert _satir(o, sid) == (NOT, 50.0, 2.0, 4, "completed")
