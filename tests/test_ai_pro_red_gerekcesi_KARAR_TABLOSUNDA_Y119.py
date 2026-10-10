# -*- coding: utf-8 -*-
"""Y119 (S-C.1 · O-A2.2) — AI Pro öneri reddinin gerekçe METNİ tedavi DB'sinin kendi AI Pro karar tablosunda saklanır; `session_events`
izi METİNSİZ kalır (Y114 deseni). Saklama / anonimleştirme kurallarına (A-06, A-27) tabidir.

ÖLÇÜLEN KUSUR: O-A2.2'den (`3fbdd6e`) beri ret gerekçesi yalnız süreç belleğindeki öneri kaydında duruyordu (yeniden başlatmada
kayboluyor); onay penceresi ise "Red gerekçesi (kayda geçer)" diyor (C2-1.14 — kapısı aynı oturumda arşivden alındı).
GERÇEK: `/api/ai/pro/propose` → `/reject` / `/approve` uçları, TreatmentHistoryDB (sentetik, tmp), GERÇEK HardwareController, D2.54
anonimleştirme turu (`services.kvkk_anonimlestirme.tur`) ve PatientDatabase. Arıza (yazım düşmesi) GERÇEK SQLite hatası (tablo yok).
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta

import ai_pro_aparati as ap
import pytest


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            yield ns
    finally:
        ns.geri()


def _oner(o, hasta_id: str = "", hasta_adi: str = "") -> str:
    o.air._ai_organ_id = 2
    with o.air._ai_cache_lock:
        o.air._ai_organ_cache.update(
            {
                "x_mm": 1.0,
                "y_mm": 2.0,
                "z_mm": 3.0,
                "reliability": 0.9,
                "localized": True,
                "overlay_bgr": None,
                "at": time.time(),
                "organ_id": 2,
                "kedi_var": True,
                "guven_dokumu": None,
                "model": "kedi",
            }
        )
    r = o.c.post(
        "/api/ai/pro/propose",
        json={"organ_id": 2, "duration_minutes": 5, "patient_id": hasta_id, "patient_name": hasta_adi},
    )
    assert r.status_code == 200, r.text[:300]
    return r.json()["proposalId"]


def _kararlar(db):
    with db._get_connection() as c:
        c.row_factory = None
        return c.execute(
            "SELECT proposal_id, karar, gerekce, operator_email, patient_uuid FROM ai_pro_kararlari ORDER BY id"
        ).fetchall()


def _iz(db, olay):
    with db._get_connection() as c:
        c.row_factory = None
        return [json.loads(r[0]) for r in c.execute("SELECT payload FROM session_events WHERE event_type=?", (olay,))]


def test_KRITIK_Y119_red_gerekcesi_KARAR_TABLOSUNDA_iz_METINSIZ(o):
    """MUTASYON: karar tablosuna yazım kaldırılır → KIRMIZI; ize metin geri eklenir (O-A2.2 öncesi) → KIRMIZI."""
    pid = _oner(o, "uuid-y119", "Pamuk")
    gerekce = "Pamuk kilo yüksek, doz düşürülsün BENZ-Y119"
    r = o.c.post("/api/ai/pro/reject", json={"proposal_id": pid, "operator_email": "h@k.com", "reason": gerekce})
    assert r.status_code == 200, r.text[:300]
    iz = _iz(o.db, "ai_proposal_rejected")
    assert len(iz) == 1 and iz[0]["gerekce_var"] is True, f"aparat/iz: {iz}"
    assert "BENZ-Y119" not in json.dumps(iz, ensure_ascii=False), (
        "ret gerekçe METNİ denetim izine (session_events) girdi (O-A2.2)"
    )
    kararlar = _kararlar(o.db)
    assert kararlar == [(pid, "reddedildi", gerekce, iz[0]["operator"], "uuid-y119")], (
        f"ret gerekçe metni AI Pro karar tablosunda yok / eksik (Y119): {kararlar}"
    )


def test_KRITIK_Y119_anonimlestirme_karar_metnine_ULASIR_hekim_atfi_KALIR(o, tmp_path):
    """A-06 / Y125: hasta anonimleşince karar metnindeki hasta ve sahip adı `[ANONIM]`; klinik içerik ve hekim atfı (A-27) kalır.
    Başka hastanın kararı dokunulmaz."""
    from database.patient_database import PatientDatabase
    from services import kvkk_anonimlestirme as kv

    pdb = PatientDatabase(str(tmp_path / "patients.db"))
    hid = pdb.add_patient({"name": "Pamuk Yüzondokuz", "owner": "Ayşe Sahibe"})
    with pdb._get_connection() as c:
        c.execute(
            "UPDATE patients SET last_treatment_at=? WHERE id=?",
            ((datetime.now() - timedelta(days=2200)).isoformat(), hid),
        )
        c.commit()
    diger = pdb.add_patient({"name": "Boncuk Aktif", "owner": "Veli"})
    p1 = _oner(o, hid, "Pamuk Yüzondokuz")
    assert (
        o.c.post(
            "/api/ai/pro/reject",
            json={
                "proposal_id": p1,
                "operator_email": "h@k.com",
                "reason": "PAMUK YÜZONDOKUZ kilo yüksek; sahibi Ayşe Sahibe aradı",
            },
        ).status_code
        == 200
    )
    p2 = _oner(o, diger, "Boncuk Aktif")
    assert (
        o.c.post(
            "/api/ai/pro/reject",
            json={"proposal_id": p2, "operator_email": "h@k.com", "reason": "Boncuk Aktif sakin değil"},
        ).status_code
        == 200
    )
    o.db.anonim_onayi_yaz(gun=kv.ESIK_GUN, sayi=1, kim="")
    assert kv.tur(pdb, o.db)["anonimlestirilen"] == 1
    k = {r[0]: r for r in _kararlar(o.db)}
    assert "Yüzondokuz".lower() not in k[p1][2].lower() and "Ayşe" not in k[p1][2], (
        f"anonimleştirme AI Pro karar metnindeki hasta/sahip adına ulaşmadı (Y119 · A-06): {k[p1][2]!r}"
    )
    assert "kilo yüksek" in k[p1][2] and "[ANONIM]" in k[p1][2], k[p1][2]
    assert k[p1][3] == "h@k.com", "hekim atfı silindi (A-27)"
    assert k[p2][2] == "Boncuk Aktif sakin değil", "başka (aktif) hastanın kararı değişti"


def test_KRITIK_Y119_kimliksiz_karar_ad_TEK_hastaya_cozulurse_anonim(o, tmp_path):
    """Hastasız (kimliksiz) öneri reddinin metninde hastanın adı geçiyorsa ve ad kanonik DB'de başka AKTİF hastaya çözülmüyorsa (Y125
    kuralı) karar metni de anonimleşir."""
    from database.patient_database import PatientDatabase
    from services import kvkk_anonimlestirme as kv

    pdb = PatientDatabase(str(tmp_path / "patients.db"))
    hid = pdb.add_patient({"name": "Minnoş Eskikayıt", "owner": "S"})
    with pdb._get_connection() as c:
        c.execute(
            "UPDATE patients SET last_treatment_at=? WHERE id=?",
            ((datetime.now() - timedelta(days=2200)).isoformat(), hid),
        )
        c.commit()
    p = _oner(o)
    assert (
        o.c.post(
            "/api/ai/pro/reject", json={"proposal_id": p, "reason": "minnoş eskikayıt için uygun değil"}
        ).status_code
        == 200
    )
    o.db.anonim_onayi_yaz(gun=kv.ESIK_GUN, sayi=1, kim="")
    kv.tur(pdb, o.db)
    gerekce = _kararlar(o.db)[0][2]
    assert "eskikayıt" not in gerekce.lower() and "uygun değil" in gerekce, gerekce


def test_KARSIT_onay_kararı_METINSIZ_kayda_gecer(o):
    pid = _oner(o, "uuid-onay", "Pamuk")
    assert o.c.post("/api/ai/pro/approve", json={"proposal_id": pid, "operator_email": "h@k.com"}).status_code == 200
    assert [(k[0], k[1], k[2], k[4]) for k in _kararlar(o.db)] == [(pid, "onaylandi", "", "uuid-onay")]


def test_KRITIK_karar_tablosu_yazilamazsa_RET_YINE_200_ve_iz_yazilir(o, caplog):
    """Karar tablosu yazımı best-effort: GERÇEK SQLite hatası (tablo yok) reddi bozmaz, metinsiz iz yazılır, WARNING düşer."""
    import logging

    with o.db._get_connection() as c:
        c.execute("DROP TABLE ai_pro_kararlari")
        c.commit()
    caplog.set_level(logging.WARNING)
    pid = _oner(o)
    r = o.c.post("/api/ai/pro/reject", json={"proposal_id": pid, "reason": "gerekce"})
    assert r.status_code == 200 and len(_iz(o.db, "ai_proposal_rejected")) == 1
    assert any("karar" in x.getMessage().lower() for x in caplog.records if x.levelno >= logging.WARNING)
