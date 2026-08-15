# Author: mertaygn, cglrgrkn
"""PDF TIBBİ RAPORDA HASTA KİMLİĞİ KAYBOLMAMALI.

KAMPANYA BULGUSU (2026-08-14, S18-EK). Aynı seans üç uçtan çekildiğinde hasta adı CSV ve
JSON'da doğru ("Pamuk"), **PDF raporunda "Bilinmiyor"** çıkıyordu.

NEDEN. `_session_info_rows` hasta adını YALNIZCA `parameters` sözlüğünden okuyordu
(`parameters['patient_name']['value']`). Oysa seans satırında `patient_name` ÜST DÜZEYDE durur —
CSV/JSON oradan okuduğu için doğruydu. `parameters` yalnız seansa özel ek alanları taşır ve
çoğu kayıtta hasta adını İÇERMEZ.

⚠️ NEDEN ÖNEMLİ: bu bir TIBBİ RAPORDUR ve hasta sahibine / başka bir kliniğe gider. Üzerinde
"Hasta Adı: Bilinmiyor" yazan bir belge, kime ait olduğu belirsiz bir tedavi kaydıdır: hukuken
ve tıbben kullanılamaz. Aynı dosyadaki `patient_vet_contact` satırı DOĞRU deseni zaten
kullanıyordu (`parameters` → yoksa `session`); hasta adına uygulanmamıştı.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _uretici():
    from utils.pdf_report_generator import PDFReportGenerator

    return PDFReportGenerator.__new__(PDFReportGenerator)  # __init__ (reportlab styles) GEREKMEZ


def _satir(rows, etiket):
    for r in rows:
        if r and str(r[0]) == etiket:
            return str(r[1])
    return None


def test_KRITIK_hasta_adi_SEANS_SATIRINDAN_okunur():
    """Asıl arıza: `parameters` hasta adını taşımıyorsa seans satırına DÜŞÜLMELİ."""
    g = _uretici()
    session = {"patient_name": "Pamuk", "patient_surname": "Yılmaz", "session_date": "2026-08-14"}
    rows = g._session_info_rows(session, parameters={}, include_patient_info=True)
    assert _satir(rows, "Hasta Adı") == "Pamuk Yılmaz", (
        f"PDF hasta adini kaybetti: {_satir(rows, 'Hasta Adı')!r} — tibbi rapor kime ait belirsiz kalir"
    )


def test_parameters_ONCELIKLIDIR_karsit_kanit():
    """Karşı-kanıt: düzeltme, `parameters`taki değeri EZMEMELİ. Seansa özel olarak girilmiş bir
    ad varsa o kullanılır; seans satırı yalnız YEDEKtir."""
    g = _uretici()
    session = {"patient_name": "SeansSatiri", "patient_surname": ""}
    parameters = {"patient_name": {"value": "Parametre"}, "patient_surname": {"value": "Adi"}}
    rows = g._session_info_rows(session, parameters=parameters, include_patient_info=True)
    assert _satir(rows, "Hasta Adı") == "Parametre Adi"


def test_hicbir_kaynak_YOKSA_Bilinmiyor_kalir():
    """Karşı-kanıt: gerçekten hiçbir yerde ad yoksa 'Bilinmiyor' DOĞRU cevaptır — uydurma yapma."""
    g = _uretici()
    rows = g._session_info_rows({}, parameters={}, include_patient_info=True)
    assert _satir(rows, "Hasta Adı") == "Bilinmiyor"


def test_yalniz_ad_varken_soyad_bosluk_birakmaz():
    """Soyad yoksa "Pamuk " gibi sondan boşluklu bir ad üretilmemeli (belgede göze çarpar)."""
    g = _uretici()
    rows = g._session_info_rows({"patient_name": "Pamuk"}, parameters={}, include_patient_info=True)
    assert _satir(rows, "Hasta Adı") == "Pamuk"


def test_hasta_bilgisi_KAPALIYKEN_satir_hic_eklenmez():
    """Karşı-kanıt: `include_patient_info=False` iken hasta satırı HİÇ çıkmamalı (anonim rapor)."""
    g = _uretici()
    rows = g._session_info_rows({"patient_name": "Pamuk"}, parameters={}, include_patient_info=False)
    assert _satir(rows, "Hasta Adı") is None


if __name__ == "__main__":
    import os

    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
