# -*- coding: utf-8 -*-
"""I18NI-A1.9 — sunucu seans / hasta PDF'i (ve CSV) AI Pro seans modunu ("AI Pro · Kedi Organ · Böbrek") İngilizce raporda Türkçe basıyor.

`utils/seans_durum.mod_etiketi` (EN1; PDF + CSV) yalnız "Manuel" / "Otomatik"u çevirir, AI Pro mod VERİSİNİ ham döndürür (arayüz eşi I18NI-A1.5).
GERÇEK: TreatmentHistoryDB + PDFReportGenerator + PyMuPDF metni; `mod_etiketi` doğrudan. Bugün KIRMIZI; TR çıktısı ham değerle AYNI kalmalı.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

TR_HARF = re.compile(r"[çğıöşüÇĞİÖŞÜ]")
MODLAR = [
    "AI Pro · Kedi Organ · Böbrek",
    "AI Pro · Kedi Organ · Akciğer (sağ)",
    "AI Pro · Kedi Organ",
    "AI Pro · Fantom Tümör · Tümör 2",
    "AI Pro · Petri Kuyu · Kuyu (otomatik)",
]


@pytest.fixture(params=["tr", "en"])
def dil(request):
    from utils import ceviri

    jeton = ceviri.istek_dili_var.set(request.param)
    try:
        yield request.param
    finally:
        ceviri.istek_dili_var.reset(jeton)


@pytest.mark.parametrize("mod", MODLAR)
def test_mod_etiketi_TR_ham_EN_ingilizce(dil, mod):
    from utils.seans_durum import mod_etiketi

    g = mod_etiketi(mod)
    if dil == "tr":
        assert g == mod
    else:
        assert g.startswith("AI Pro") and not TR_HARF.search(g) and not re.search(r"Kedi|Kuyu|Fantom|otomatik", g), g


def test_EN_seans_PDF_AI_Pro_modu_ingilizce(tmp_path):
    fitz = pytest.importorskip("fitz")
    from database.treatment_history_db import TreatmentHistoryDB
    from utils import ceviri
    from utils.pdf_report_generator import PDFReportGenerator

    db = TreatmentHistoryDB(tmp_path)
    sid = db.start_session(treatment_mode="AI Pro · Kedi Organ · Böbrek", patient_name="Mia")
    db.end_session(sid, session_status="completed")
    yol = str(tmp_path / "s.pdf")
    jeton = ceviri.istek_dili_var.set("en")
    try:
        PDFReportGenerator(tmp_path).generate_session_report(session_ids=[sid], output_path=yol)
    finally:
        ceviri.istek_dili_var.reset(jeton)
    with fitz.open(yol) as d:
        metin = "\n".join(s.get_text() for s in d)
    kalan = sorted({ln for ln in metin.splitlines() if TR_HARF.search(ln) or "Kedi" in ln})
    assert not kalan, kalan
