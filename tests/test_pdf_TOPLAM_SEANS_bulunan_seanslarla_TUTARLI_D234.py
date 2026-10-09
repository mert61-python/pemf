# -*- coding: utf-8 -*-
"""A3 · D2-3.4 — seçili-seans PDF'inde "Toplam Seans: N" İSTENEN kimlik sayısıdır (`generate_session_report` → `_add_report_info(story,
len(session_ids))`); bulunamayan (başka hekimin sildiği) seans rapora girmez ve PDF'te hiçbir işaret yoktur (yalnız sunucu günlüğünde ERROR);
yinelenen kimlik aynı seansı İKİ kez basar; hiçbiri bulunamazsa 200 + seanssız "Toplam Seans: 1" PDF'i iner. D2.28 planının "Neden"i tam bu
çelişkiydi ("'Toplam Seans: N' ile istatistik sayısı çelişiyor, HTTP 200"); D2.28 yalnız 50 000 penceresi nedenini kapattı.
GERÇEK: `/api/history/export_pdf` (TestClient, cihazın kendisi), PDFReportGenerator, TreatmentHistoryDB (`delete_session` ile gerçek silme);
PDF metni PyMuPDF. Depo yeri: tests/test_pdf_TOPLAM_SEANS_bulunan_seanslarla_TUTARLI_D234.py
"""

from __future__ import annotations

import re

import pytest

fitz = pytest.importorskip("fitz", reason="PyMuPDF yok")


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database import sqlcipher_util as su
    from fastapi.testclient import TestClient
    from servers import api_server as api
    from servers import history_router as hr
    from utils import pdf_report_generator as prg

    get_treatment_db = prg.get_treatment_db
    TreatmentHistoryDB = get_treatment_db.__globals__["TreatmentHistoryDB"]
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    kok = tmp_path / "pdf"
    tdb = get_treatment_db(kok)
    ids = {}
    for ad in ("Boncuk", "Pamuk", "Silinen"):
        sid = tdb.start_session(treatment_mode="Manuel", patient_name=ad)
        tdb.end_session(sid, duration_minutes=5)
        ids[ad] = sid
    tdb.delete_session(ids["Silinen"])  # liste yüklendikten sonra başka hekim sildi
    uretici = prg.PDFReportGenerator(kok)
    assert uretici.db is tdb, "aparat: üretici başka DB örneğine bakıyor"
    monkeypatch.setattr(hr, "_app_data_dir", tmp_path)
    api.app.dependency_overrides[hr.get_pdf_gen] = lambda: uretici
    try:
        yield type("O", (), {"ids": ids, "c": TestClient(api.app, client=("127.0.0.1", 53234)), "kok": tmp_path})
    finally:
        api.app.dependency_overrides.pop(hr.get_pdf_gen, None)
        tdb.close()


def _pdf(o, kimlikler, ad):
    r = o.c.get("/api/history/export_pdf", params={"session_ids": ",".join(map(str, kimlikler))})
    if r.status_code != 200 or r.content[:4] != b"%PDF":
        return r, None
    yol = o.kok / f"{ad}.pdf"
    yol.write_bytes(r.content)
    with fitz.open(str(yol)) as d:
        return r, "\n".join(s.get_text() for s in d)


def _toplam(metin):
    m = re.search(r"Toplam Seans:\s*(\d+)", metin)
    return int(m.group(1)) if m else None


def _bloklar(metin):
    return len(re.findall(r"^Seans \d+ - ", metin, re.M))


def test_KRITIK_D234_silinmis_seans_secildiyse_TOPLAM_bulunanla_tutarli_ve_PDF_eksigi_SOYLER(o):
    r, metin = _pdf(o, [o.ids["Boncuk"], o.ids["Silinen"]], "silinmis")
    assert metin is not None, f"aparat: PDF yok {r.status_code} {r.text[:120]}"
    assert _toplam(metin) == _bloklar(metin) == 1, (
        f"'Toplam Seans: {_toplam(metin)}' ama PDF'te {_bloklar(metin)} seans var — silinmiş seans sessizce düştü"
    )
    assert "bulunamad" in metin.lower(), "PDF bulunamayan (silinmiş) seansı SÖYLEMİYOR — yalnız sunucu günlüğünde"


def test_KRITIK_D234_yinelenen_kimlik_ayni_seansi_IKI_kez_basmaz(o):
    r, metin = _pdf(o, [o.ids["Boncuk"], o.ids["Boncuk"], o.ids["Pamuk"]], "yinelenen")
    assert metin is not None, f"aparat: PDF yok {r.status_code}"
    assert (_toplam(metin), _bloklar(metin), metin.count("Boncuk")) == (2, 2, 1), (
        f"yinelenen kimlik: Toplam {_toplam(metin)}, blok {_bloklar(metin)}, 'Boncuk' {metin.count('Boncuk')} kez"
    )


def test_KRITIK_D234_secilenlerin_HICBIRI_yoksa_PDF_bunu_SOYLER(o):
    """Ya rapor hiç üretilmez (4xx + neden) ya da PDF "Toplam Seans: 0" der ve bulunamayanı söyler — "Toplam Seans: 1" + seanssız DEĞİL."""
    r, metin = _pdf(o, [o.ids["Silinen"]], "hepsi_yok")
    if metin is None:
        assert 400 <= r.status_code < 500 and "bulunamad" in r.text.lower(), f"{r.status_code} {r.text[:200]}"
    else:
        assert (_toplam(metin), _bloklar(metin)) == (0, 0) and "bulunamad" in metin.lower(), (
            f"seçilenlerin hiçbiri yokken PDF 'Toplam Seans: {_toplam(metin)}' diyor, {_bloklar(metin)} seans, eksik SÖYLENMİYOR"
        )


def test_KARSIT_D234_tum_secilenler_varken_rapor_bugunku_gibi(o):
    r, metin = _pdf(o, [o.ids["Pamuk"], o.ids["Boncuk"]], "tekil")
    assert metin is not None and _toplam(metin) == _bloklar(metin) == 2
    assert "Boncuk" in metin and "Pamuk" in metin and "bulunamad" not in metin.lower()
