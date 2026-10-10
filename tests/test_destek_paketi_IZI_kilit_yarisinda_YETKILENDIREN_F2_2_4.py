# -*- coding: utf-8 -*-
"""F2-2.4 (2-F incelemesi A2 · O-A2.3 kalıbı, 2-F açık #11) — `POST /api/support/bundle` izi, paket üretilirken gelen "Kilitle"de
YETKİLENDİREN hekimin adına kalır.

ÖLÇÜLEN: uç kimliği HİÇ çözmeden uzun işleme (`support_bundle.olustur` — günlükler + DB'den maske listesi, saniyeler) giriyor; başarı izi
(`kimlikli_yaz`) sonda kimliği İLK KEZ çözüyor → işlem sürerken aynı hekimin "Kilitle"si (`operator_tokens.iptal` — POST /api/operators/lock'un
yaptığı) izi SAHİPSİZ bırakıyor. Destek paketi PII-maskeli bir DIŞA AKTARMADIR; izi "kim aldı" sorusunun tek cevabıdır.
KARŞIT: `/api/hardware/estop_mandali/sifirla` kimliği ilk satırda çözüyor (`api_server.py:7330`); istekten ÖNCE iptal edilmiş jeton sahipsiz.
GERÇEK: uç, `olustur` (sarılır: önce Kilitle, sonra GERÇEK olustur), operatör kaydı/jetonu, `TreatmentHistoryDB` (tmp) denetim izi.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import operator_tokens

    kok = tmp_path / "veri"
    kok.mkdir()
    db = TreatmentHistoryDB(kok)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(api, "_app_data_dir", lambda: kok)
    yerel = TestClient(api.app, client=("127.0.0.1", 51436))

    def _sil():
        for op in yerel.get("/api/operators").json().get("data", []):
            yerel.post("/api/operators/remove", json={"email": op["email"]})

    operator_tokens.temizle_hepsi()
    _sil()
    try:
        yield type("O", (), {"db": db, "yerel": yerel})
    finally:
        operator_tokens.temizle_hepsi()
        _sil()
        db.close_connections()


def _jeton(o):
    assert (
        o.yerel.post("/api/operators/enroll", json={"email": AYSE, "display_name": "Ayse", "pin": "123456"}).status_code
        == 200
    )
    return o.yerel.post("/api/operators/verify", json={"email": AYSE, "pin": "123456"}).json()["operator_token"]


def test_KRITIK_destek_paketi_URETILIRKEN_Kilitle_iz_YETKILENDIREN_hekimin_adina(o, monkeypatch):
    """MUTASYON / HEAD: kimlik işlemden önce çözülmez → iz SAHİPSİZ → KIRMIZI."""
    from servers import operator_tokens
    from utils import support_bundle

    j = _jeton(o)
    orj = support_bundle.olustur

    def _sar(*a, **k):
        operator_tokens.iptal(j)  # paket üretilirken "Kilitle"
        return orj(*a, **k)

    monkeypatch.setattr(support_bundle, "olustur", _sar)
    r = o.yerel.post("/api/support/bundle", headers={"X-PEMF-Operator": j})
    assert r.status_code == 200, r.text[:300]
    izler = o.db.denetim_oku(20, "support.bundle")
    assert izler, "aparat: destek paketi izi yok"
    assert izler[0]["operator_email"] == AYSE, (
        f"paket üretilirken 'Kilitle' → iz SAHİPSİZ ({izler[0]['operator_email']!r}) — kimlik işlemden SONRA çözülüyor (O-A2.3 kalıbı)"
    )


def test_KARSIT_istekten_ONCE_iptal_edilmis_jetonla_iz_SAHIPSIZ(o):
    from servers import operator_tokens

    j = _jeton(o)
    operator_tokens.iptal(j)
    r = o.yerel.post("/api/support/bundle", headers={"X-PEMF-Operator": j})
    assert r.status_code == 200, r.text[:300]
    izler = o.db.denetim_oku(20, "support.bundle")
    assert izler and not izler[0]["operator_email"], izler[:1]


def test_KARSIT_kilitsiz_iz_hekimin_adina(o):
    j = _jeton(o)
    r = o.yerel.post("/api/support/bundle", headers={"X-PEMF-Operator": j})
    assert r.status_code == 200, r.text[:300]
    izler = o.db.denetim_oku(20, "support.bundle")
    assert izler and izler[0]["operator_email"] == AYSE, izler[:1]
