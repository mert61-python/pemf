# -*- coding: utf-8 -*-
"""F2-1.1 (2-F incelemesi · A1) — anonimleştirmenin metin temizliği (`PiiKarisimi._kimlik_deseni`) KELİME SINIRI kullanmalı.

ÖLÇÜLEN KUSUR (GERÇEK zincir: kanonik hasta → onay → `services.kvkk_anonimlestirme.tur` → `get_ai_analyses`): desen adı bir kelimenin
İÇİNDE de eşliyor. Kısa hayvan adları klinik kelimelerin parçası olduğu için anonimleştirme TIBBİ KAYDI geri dönüşsüz bozuyordu:
"Kara" → "[ANONIM]ciğer" (karaciğer), "[ANONIM]r" (karar); "Mia" → "ane[ANONIM]" (anemia); "Can" → "[ANONIM]dida" (Candida) ve
değerlendirme geçmişindeki HEKİM e-postası "candan.vet@…" → "[ANONIM]dan.vet@…" (A-27 ihlali); "Mor" → AI ayrıntısının "n_tumors"
ANAHTARI "n_tu[ANONIM]s" (takip serisi ölçütü kaybolur). Ayrıca `len(m) >= 3` süzgeci iki harfli adı ("Su") metinlerde HİÇ silmiyordu
(özet, ayrıntı, değerlendirme geçmişi, AI Pro ret gerekçesinde ad kalıyordu — KVKK).
2-F'nin iddiası: "klinik içerik kalır" (D2.54) — ölçüm çürüttü.
DÜZELTME: desen kelime sınırlı (önünde ve ardında harf/rakam yok). Alt sınır (`len(m) >= 3`) DEĞİŞMEDİ: 2'ye indirmek iki harfli adı silerdi ama aynı
yazılan Türkçe kelimeyi de ("su tüketimi" → "[ANONIM] tüketimi") geri dönüşsüz bozardı → sahip kararı, ERTELENDİ (inceleme raporu S-F2-1.6;
Y123: geri dönüşsüz yön → muhafazakâr seçenek). A1'in iki harfli kol testi inceleme arşivinde.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

import pytest

HEKIM = "dr.ayse@klinik.vet"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    pdb = PatientDatabase(str(tmp_path / "patients.db"))
    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    try:
        yield pdb, tdb
    finally:
        tdb.close_connections()


def _anonimlestir(o, ad, ozet, ayrinti, red, hekim=HEKIM, sahip="Deniz Yalçın-11", eposta="dy11@ornek.com"):
    """Ürün yazıcılarıyla 5 yıl inaktif hasta + kimlikli AI kaydı (+ iki değerlendirme → Y114 geçmişi) + AI Pro ret gerekçesi (Y119),
    sonra onay + GERÇEK tur. Dönen: (AI kaydı, karar gerekçesi)."""
    from services import kvkk_anonimlestirme as kv

    pdb, tdb = o
    pid = pdb.add_patient({"name": ad, "owner": sahip, "owner_email": eposta})
    with pdb._get_connection() as c:
        c.execute(
            "UPDATE patients SET last_treatment_at=? WHERE id=?",
            ((datetime.now() - timedelta(days=2200)).isoformat(), pid),
        )
        c.commit()
    tdb.upsert_patient({"name": ad, "patient_uuid": pid, "owner_email": eposta})
    aid = tdb.add_ai_analysis(
        module_id="em_fantom",
        patient_name=ad,
        result_summary=ozet,
        result_detail=ayrinti,
        operator_email=hekim,
        patient_uuid=pid,
    )
    tdb.set_ai_review(aid, "rejected", red, reviewed_by=hekim)
    tdb.set_ai_review(aid, "approved", "tamam", reviewed_by=hekim)
    tdb.ai_pro_karari_yaz(f"p-{ad}", "rejected", f"{red} | {ozet}", hekim, pid)
    tdb.anonim_onayi_yaz(gun=kv.ESIK_GUN, sayi=1, kim=hekim)
    assert kv.tur(pdb, tdb)["anonimlestirilen"] == 1, "aparat: hasta anonimleşmedi"
    ai = next(a for a in tdb.get_ai_analyses(10) if a["id"] == aid)
    with tdb._get_connection() as c:
        karar = c.execute("SELECT gerekce FROM ai_pro_kararlari WHERE proposal_id=?", (f"p-{ad}",)).fetchone()[0]
    return ai, karar


def test_KRITIK_ad_klinik_KELIMENIN_ICINDE_eslesmez_klinik_metin_KALIR(o):
    """MUTASYON: desenin sol ya da sağ kelime sınırı kaldırılır → KIRMIZI ("Karaciğer" → "[ANONIM]ciğer")."""
    ai, karar = _anonimlestir(
        o,
        "Kara",
        "Karaciğer enzimleri yüksek; karar: kontrol. Kara'nın iştahı iyi.",
        {"organ": "karaciğer"},
        "Kara için ikinci görüş: karaciğer USG",
    )
    assert ai["result_summary"] == "Karaciğer enzimleri yüksek; karar: kontrol. [ANONIM]'nın iştahı iyi.", ai[
        "result_summary"
    ]
    assert ai["result_detail"] == {"organ": "karaciğer"}, ai["result_detail"]
    assert ai["review_history"][0]["note"] == "[ANONIM] için ikinci görüş: karaciğer USG", ai["review_history"]
    assert "Karaciğer enzimleri" in karar and "karar: kontrol" in karar and "Kara'" not in karar, karar


def test_KRITIK_ad_kelimenin_SONUNDA_da_eslesmez(o):
    """ "Mia" → "anemia" / "hipokalemia" (sağ uç). MUTASYON: sol kelime sınırı kaldırılır → KIRMIZI."""
    ai, _ = _anonimlestir(o, "Mia", "Hafif anemia ve hipokalemia. Mia sakin.", {"lab": "anemia"}, "Mia red")
    assert ai["result_summary"] == "Hafif anemia ve hipokalemia. [ANONIM] sakin.", ai["result_summary"]
    assert ai["result_detail"] == {"lab": "anemia"}, ai["result_detail"]


def test_KRITIK_A27_hekim_atfi_DEGERLENDIRME_GECMISINDE_kalir(o):
    """Hasta "Can", hekim "candan.vet@klinik.vet": Y114 geçmişindeki `reviewed_by` hekim atfıdır (A-27) — anonimleştirme hastayı hedefler."""
    hekim = "candan.vet@klinik.vet"
    ai, _ = _anonimlestir(
        o,
        "Can",
        "Candida enfeksiyonu; canlılık iyi. Can'ın yarası kapanıyor.",
        {"bulgu": "Candida"},
        "Can için red",
        hekim=hekim,
    )
    assert [g.get("reviewed_by") for g in ai["review_history"]] == [hekim], (
        f"A-27: hekim atfı bozuldu: {ai['review_history']}"
    )
    assert ai["result_summary"] == "Candida enfeksiyonu; canlılık iyi. [ANONIM]'ın yarası kapanıyor.", ai[
        "result_summary"
    ]
    assert ai["result_detail"] == {"bulgu": "Candida"}, ai["result_detail"]


def test_KRITIK_AI_ayrintisinin_ANAHTARLARI_bozulmaz(o):
    """`result_detail` JSON metni üzerinde çalışılır: "Mor" → "n_tu[ANONIM]s" anahtarı takip serisinin (`takipSerisi.ts` em_fantom →
    `n_tumors`) ölçütünü yok ederdi."""
    ai, _ = _anonimlestir(
        o, "Mor", "Fantom ölçümü: 3 tümör. Mor sakin.", {"n_tumors": 3, "model": "em_fantom"}, "Mor red"
    )
    assert ai["result_detail"] == {"n_tumors": 3, "model": "em_fantom"}, ai["result_detail"]
    assert ai["result_summary"] == "Fantom ölçümü: 3 tümör. [ANONIM] sakin.", ai["result_summary"]


def test_KARSIT_ad_ayri_kelime_olarak_her_bicimde_SILINIR(o):
    """Araç kör değil: ad ayrı kelimeyken (büyük harf, Türkçe ek, noktalama, satır başı) yine silinir."""
    ai, karar = _anonimlestir(o, "Kara", "KARA kontrolde. kara'ya ilaç verildi. Kara.", {"hasta": "Kara"}, "(Kara) red")
    assert not re.search(
        r"(?<!\w)kara(?!\w)", ai["result_summary"] + str(ai["result_detail"]) + karar, re.IGNORECASE
    ), (
        ai["result_summary"],
        ai["result_detail"],
        karar,
    )
