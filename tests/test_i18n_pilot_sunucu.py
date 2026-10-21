# -*- coding: utf-8 -*-
"""I18N-0 · SUNUCU PİLOTU — yönlendirici hata iletisi (patient_router), PDF başlık / bilgi / altbilgi, AI sonuç metni (ai_router) istek
dilinde. Başlıksız istek = BUGÜNKÜ Türkçe (eski APK / eski arayüz aynen); `X-PEMF-Dil: en` → İngilizce; `Accept-Language` YOK SAYILIR.

GERÇEK: uçlar (TestClient — LAN), hasta DB'si (geçici), PDF üreticisi (reportlab hikâye öğeleri), `ceviri` ara katmanı ve ContextVar.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

OLMAYAN = "00000000-0000-0000-0000-000000000000"
TR_404 = "Hasta bulunamadı — zaten silinmiş olabilir; listeyi yenileyin."


@pytest.fixture
def lan(tmp_path, monkeypatch):
    from database.patient_database import PatientDatabase
    from servers import api_server as api
    from servers import operator_tokens, patient_router

    hdb = PatientDatabase(str(tmp_path / "patients.db"))
    monkeypatch.setattr(patient_router, "get_patient_database", lambda: hdb)
    operator_tokens.temizle_hepsi()
    try:
        yield TestClient(api.app, client=("192.168.1.96", 53135))
    finally:
        operator_tokens.temizle_hepsi()


@pytest.mark.parametrize(
    "baslik,beklenen",
    [
        ({}, TR_404),
        ({"X-PEMF-Dil": "tr"}, TR_404),
        ({"Accept-Language": "en-US,en;q=0.9"}, TR_404),
        # I18NI-A3.1: tam "en" değeri — geçerli bir dil kodu; ara katman Accept-Language'ı X-PEMF-Dil gibi okursa EN döner (mutant).
        ({"Accept-Language": "en"}, TR_404),
        ({"X-PEMF-Dil": "en"}, "Patient not found — it may already have been deleted; refresh the list."),
    ],
    ids=["basliksiz", "tr", "accept-language-YOK-SAYILIR", "accept-language-tam-en-YOK-SAYILIR", "en"],
)
def test_yonlendirici_hata_iletisi_istek_dilinde(lan, baslik, beklenen):
    r = lan.delete(f"/api/patients/{OLMAYAN}", headers=baslik)
    assert r.status_code == 404, r.text[:200]
    assert r.json()["detail"] == beklenen


@pytest.fixture
def pdf(tmp_path):
    from utils.pdf_report_generator import PDFReportGenerator

    return PDFReportGenerator(app_data_dir=tmp_path)


def _metinler(story) -> list[str]:
    from reportlab.platypus import Paragraph, Table

    out = []
    for o in story:
        if isinstance(o, Paragraph):
            out.append(o.getPlainText())
        elif isinstance(o, Table):
            out += [str(h) for satir in o._cellvalues for h in satir]
    return out


def _dilde(dil: str):
    from utils import ceviri

    return ceviri.istek_dili_var.set(dil)


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_pdf_baslik_bilgi_altbilgi_rapor_dilinde_iki_dil_KARISMAZ(pdf, dil):
    from utils import ceviri

    jeton = _dilde(dil)
    try:
        story: list = []
        pdf._add_header(story)
        pdf._add_report_info(story, 3)
        pdf._add_footer(story)
        pdf._add_footer(story, "Hasta: Pamuk.")
    finally:
        ceviri.istek_dili_var.reset(jeton)
    m = "\n".join(_metinler(story))
    if dil == "tr":
        for parca in (
            "PEMF TEDAVİ RAPORU",
            "Rapor Tarihi:",
            "Toplam Seans:",
            "Tedavi Geçmişi Raporu",
            "Veteriner PEMF Tedavi Sistemi v1.0",
            "Hasta: Pamuk. Rapor tarihi:",
        ):
            assert parca in m, parca
    else:
        for parca in (
            "PEMF SESSION REPORT",
            "Report Date:",
            "Total Sessions:",
            "Session History Report",
            "Veterinary PEMF Session System v1.0",
            "Hasta: Pamuk. Report date:",
        ):
            assert parca in m, parca
        for tr in ("Rapor", "Tedavi", "Seans", "Veteriner Uygulaması"):
            assert tr not in m.replace("Hasta: Pamuk.", ""), f"İngilizce raporda Türkçe kaldı: {tr!r}"


def test_pdf_bos_baslik_hala_YAZILMAZ(pdf):
    story: list = []
    pdf._add_header(story, "", "")
    assert not [s for s in _metinler(story) if s.strip()], "boş başlık / alt başlık verildiğinde başlık yazılmamalı"


@pytest.mark.parametrize(
    "dil,beklenen", [("tr", "PEMF geçerliliği hesaplanamadı"), ("en", "PEMF validity could not be calculated")]
)
def test_ai_sonuc_metni_istek_dilinde_KOD_degismez(monkeypatch, dil, beklenen):
    from servers import ai_router
    from utils import ceviri

    from ai_hub.cv_ortak import pemf_kapisi

    def bozuk(*_a, **_k):
        raise RuntimeError("deneme")

    monkeypatch.setattr(pemf_kapisi, "yanit_alanlari", bozuk)
    jeton = _dilde(dil)
    try:
        y = ai_router._pemf_alanlari({}, "petri")
    finally:
        ceviri.istek_dili_var.reset(jeton)
    assert y["pemf_kapisi"]["eylem"].startswith(beklenen)
    assert y["pemf_kapisi"]["mesajlar"][0]["kod"] == "kapi_hesaplanamadi", "makine-okur kod dilden bağımsız"
