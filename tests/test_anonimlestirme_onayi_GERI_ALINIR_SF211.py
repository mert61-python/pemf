# -*- coding: utf-8 -*-
"""S-F2-1.1 (2-F incelemesi A1 · Y123 önerilen · A-06) — 5 yıl inaktif hasta anonimleştirmesinin onayı GERİ ALINABİLİR; ekran son turun
tarihini ve sayısını gösterir.

ÖLÇÜLEN: onay süresizdi ve geri alma yolu yoktu — onaydan sonra 5 yılı dolduran YENİ hastalar ekranda gösterilmeden her gün anonimleşiyor;
ekran "otomatik anonimleştirilir" diyor (dürüst) ama operatör durduramıyordu ve son turda kaç hastanın gittiğini göremiyordu.
Önerilen (a): onay geri alınır (`anonymize_revoke` — onay kaydı silinir, denetim izi `retention.anonim_onay_iptal` önceki onayı taşır) →
sonraki turlar YENİ hastaya dokunmaz; yeniden onay ekranda bekleyen sayıyla sorulur. Kanonik tarafı ZATEN anonim olanların tedavi-DB adımı
(kalıcı bekleyen liste, B-3.34) onaydan bağımsız sürer. GET `anonymization.lastRun` = son `kvkk.anonimlestirildi` izi {at, count}.
GERÇEK `PatientDatabase` + `TreatmentHistoryDB` (geçici dizin), GERÇEK uç ve GERÇEK `kvkk_anonimlestirme.tur`.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

HEKIM = "dr.sf211@klinik.vet"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database import patient_database as pmod
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB
    from fastapi.testclient import TestClient
    from servers import api_server as api
    from servers import system_router as sr

    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    pdb = PatientDatabase(str(tmp_path / "patients.db"))
    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(sr, "_pii_ayar_db", lambda: tdb)
    monkeypatch.setattr(pmod, "get_patient_database", lambda *a, **k: pdb)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: tdb)
    try:
        yield type("O", (), {"pdb": pdb, "tdb": tdb, "c": TestClient(api.app, client=("127.0.0.1", 51958))})
    finally:
        tdb.close_connections()


def _hasta(o, ad, gun=2200) -> str:
    pid = o.pdb.add_patient({"name": ad, "owner": f"Sahip {ad}"})
    with o.pdb._get_connection() as c:
        c.execute(
            "UPDATE patients SET last_treatment_at=? WHERE id=?",
            ((datetime.now() - timedelta(days=gun)).isoformat(), pid),
        )
        c.commit()
    return pid


def _anonim(o):
    return o.c.get("/api/settings/retention").json()["anonymization"]


def test_KRITIK_onay_GERI_ALININCA_yeni_hasta_ANONIMLESMEZ_ve_iz_kalir(o):
    """MUTASYON: geri alma onayı silmez / iz yazmaz → KIRMIZI."""
    from services import kvkk_anonimlestirme as kv

    assert o.c.post("/api/settings/retention", json={"anonymize_acknowledge": True}).status_code == 200
    assert _anonim(o)["acknowledged"] is True, "aparat: onay yazılmadı"
    r = o.c.post("/api/settings/retention", json={"anonymize_revoke": True})
    assert r.status_code == 200, r.text[:300]
    assert _anonim(o)["acknowledged"] is False and o.tdb.anonim_onayi_oku() is None, "onay GERİ ALINMADI"
    iz = o.tdb.denetim_oku(10, "retention.anonim_onay_iptal")
    assert iz and json.loads(iz[0]["detail"])["onceki"]["gun"] == kv.ESIK_GUN, f"geri alma denetim izinde değil: {iz}"
    pid = _hasta(o, "Yeni Inaktif SF211")
    sonuc = kv.tur(o.pdb, o.tdb)
    assert (sonuc["onay"], sonuc["anonimlestirilen"]) == (False, 0), sonuc
    assert o.pdb.get_patient(pid)["name"] == "Yeni Inaktif SF211", "onay geri alındıktan sonra hasta ANONİMLEŞTİ"
    assert _anonim(o)["pending"] == 1, "geri alma sonrası bekleyen sayı ekranda yok (yeniden onay sorulamaz)"


def test_KRITIK_ekran_SON_TURUN_tarihini_ve_sayisini_gorur(o):
    """MUTASYON: GET `lastRun` döndürmez → KIRMIZI."""
    from services import kvkk_anonimlestirme as kv

    assert _anonim(o)["lastRun"] is None, "aparat: tur yokken son tur bilgisi olmamalı"
    _hasta(o, "Eski SF211 A")
    _hasta(o, "Eski SF211 B")
    assert o.c.post("/api/settings/retention", json={"anonymize_acknowledge": True}).status_code == 200
    assert kv.tur(o.pdb, o.tdb)["anonimlestirilen"] == 2
    son = _anonim(o)["lastRun"]
    assert son and son["count"] == 2 and str(son["at"])[:10] == datetime.utcnow().strftime("%Y-%m-%d"), son


def test_KARSIT_ayni_istekte_onay_ve_geri_alma_REDDEDILIR_onay_yeniden_VERILEBILIR(o):
    r = o.c.post("/api/settings/retention", json={"anonymize_acknowledge": True, "anonymize_revoke": True})
    assert r.status_code == 400 and o.tdb.anonim_onayi_oku() is None, (r.status_code, o.tdb.anonim_onayi_oku())
    assert (
        o.c.post("/api/settings/retention", json={"anonymize_revoke": True}).status_code == 200
    )  # onaysızken de zararsız
    assert o.c.post("/api/settings/retention", json={"anonymize_acknowledge": True}).status_code == 200
    assert _anonim(o)["acknowledged"] is True
