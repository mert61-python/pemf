# -*- coding: utf-8 -*-
"""E2-3.9 (2-E incelemesi A3) — Y120 kapısının KÖR kolları: ret izi (`scope=eski-istemci`) not METNİ / hasta ADI taşımaz (D2.43);
tünelden (cf-ray, cihaz anahtarıyla) gelen session_id'siz eski istemci notu da kayıtlı klinikte 428.

Ürün HEAD'de doğru (2-E incelemesi A3 K3 matrisi: tünel-anahtarlı × ad / bellek dalı → 428; iz ve günlükte not / ad YOK). Ama 2-E'nin
Y120 + Y116 kapıları ve not kümesi (9 dosya, 53 test) şu mutantlarda YEŞİL kaldı (2-E incelemesi kaydı):
  k3a  ret izine `detail={"hasta": <ad>, "not": <metin>}` eklenir (D2.43 ihlali — kişisel veri / klinik not denetim izine)
  k3d  tünelden gelen session_id'siz istek kimlik kapısından MUAF tutulur (uzak eski istemci kimliksiz yazar)
Kapı: GERÇEK uç (TestClient), `operator_tokens`, `auth_db`, geçici tedavi DB'si; iz `denetim_oku` ile, AYRIŞTIRILMIŞ tüm değerlerde aranır.
"""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse.e239@klinik.com"
NOT = "E239-gozlem-notu-metni"
HASTA = "E239Pamuk"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import auth, operator_tokens

    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: tdb)
    monkeypatch.setattr(auth, "check_token", lambda t: t == "CIHAZ-TOKEN-E239")
    monkeypatch.setattr(auth, "get_api_token", lambda: "CIHAZ-TOKEN-E239")
    monkeypatch.setattr(auth, "_require", True, raising=False)
    yerel = TestClient(api.app, client=("127.0.0.1", 52960))
    lan = TestClient(api.app, client=("192.168.1.96", 52961))

    def _sil():
        for op in yerel.get("/api/operators").json().get("data", []):
            yerel.post("/api/operators/remove", json={"email": op["email"]})

    operator_tokens.temizle_hepsi()
    _sil()
    r = yerel.post("/api/operators/enroll", json={"email": AYSE, "display_name": AYSE, "pin": "123456"})
    assert r.status_code == 200, r.text[:200]
    sid = int(tdb.start_session(treatment_mode="Manuel", patient_name=HASTA, operator_email=AYSE))
    tdb.set_session_meta(sid, started_epoch=time.time() - 300)
    tdb.end_session(sid, parameters={"frequency_hz": 50.0, "intensity_mt": 2.0}, duration_minutes=4)
    try:
        yield type("O", (), {"tdb": tdb, "yerel": yerel, "lan": lan, "sid": sid})
    finally:
        operator_tokens.temizle_hepsi()
        _sil()
        tdb.close_connections()


def _not(o, sid):
    with o.tdb._get_connection() as c:
        return c.execute("SELECT COALESCE(patient_notes,'') FROM treatment_sessions WHERE id=?", (sid,)).fetchone()[0]


@pytest.mark.parametrize("yer", ["lan", "yerel"])
def test_KRITIK_eski_istemci_RET_izi_not_metni_ve_hasta_adi_TASIMAZ_E239(o, yer):
    r = getattr(o, yer).post("/api/session/notes", json={"notes": NOT, "patient_name": HASTA})
    assert r.status_code == 428, r.text[:200]
    izler = [dict(s) for s in o.tdb.denetim_oku(50, "session.notes")]
    assert any(s.get("outcome") == "reddedildi" and s.get("scope") == "eski-istemci" for s in izler), (
        f"aparat: ret izi bulunamadı (okuyucu izi görmüyor): {izler}"
    )
    metin = json.dumps(izler, ensure_ascii=False, default=str)
    assert NOT not in metin and HASTA not in metin, "ret izi not METNİNİ / hasta ADINI taşıyor (D2.43)"


def test_KRITIK_TUNELDEN_session_idsiz_eski_istemci_notu_kayitli_klinikte_428_E239(o):
    bas = {"X-API-Key": "CIHAZ-TOKEN-E239", "cf-ray": "e239", "cf-connecting-ip": "203.0.113.9"}
    r = o.yerel.post("/api/session/notes", json={"notes": NOT, "patient_name": HASTA}, headers=bas)
    assert r.status_code == 428, f"tünelden kimliksiz eski istemci notu {r.status_code} {r.text[:200]} (Y120: 428)"
    assert _not(o, o.sid) == "", "tünelden kimliksiz not satıra YAZILDI"
