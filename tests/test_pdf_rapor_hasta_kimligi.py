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


def test_parameters_yolu_DA_calisir():
    """`parameters` yolu da desteklenir (savunma amaçlı zincir).

    ⚠️ DÜZELTME (2026-08-15): bu test önce "parameters ÖNCELİKLİDİR, seans satırı yedektir"
    diye yazılmıştı — ÜRETİMDE GEÇERSİZ bir değişmez. `_fetch_sessions` satırları
    `get_session_history`ten gelir ve o SQL zaten `COALESCE(sp_name.parameter_value,
    ts.patient_name)` yapar (treatment_history_db.py:2079); yani iki kaynağın ÇELİŞMESİ üretimde
    imkânsızdır ve testin kurduğu durum hiçbir zaman oluşamaz. Uydurma bir değişmezi kilitlemek,
    ileride onu "koruma" adına yanlış kararlar aldırır. Test artık yalnız gerçek olanı söylüyor:
    ad `parameters`tan geliyorsa da okunur."""
    g = _uretici()
    parameters = {"patient_name": {"value": "Parametre"}, "patient_surname": {"value": "Adi"}}
    rows = g._session_info_rows({}, parameters=parameters, include_patient_info=True)
    assert _satir(rows, "Hasta Adı") == "Parametre Adi"


def test_KRITIK_HASTA_RAPORU_basligi_ile_tablosu_CELISMEZ(tmp_path):
    """`/api/history/export_patient_pdf` yolundaki `_add_patient_header`.

    ⚠️ Belge KENDİ İÇİNDE çelişiyordu: başlıkta "HASTA RAPORU: PAMUK" (ad sorgu parametresinden
    gelir), tablosunda "Hasta Adı: Belirtilmemiş". Aynı sayfada iki farklı beyan taşıyan bir
    tıbbi rapor, hangisinin doğru olduğu bilinmediği için kullanılamaz."""
    # ⚠️ MANTIĞI KOPYALAMA — GERÇEK fonksiyonu çağır. (İlk yazımda tabloyu teste yeniden
    # hesaplamıştım; o desen, üretim kodu bozulsa bile yeşil kalır — aynı hatayı KPI testinde
    # mutasyon yakalamıştı.)
    from utils.pdf_report_generator import PDFReportGenerator

    # ⚠️ `tmp_path` ŞART: buraya depo kökünü vermiştim ve üretici köke `pemf_treatment_history.db`
    # + `migration_backups/` yaratıp bunları commit'e sokmuştu. Test, koştuğu ağaca YAZMAMALI.
    g = PDFReportGenerator(app_data_dir=tmp_path)

    class _DB:
        def get_session_details(self, _sid):
            return {"parameters": {}}  # ÜRETİMDE ad `session_parameters`ta YOKTUR

    g.db = _DB()
    story = []
    g._add_patient_header(story, {"id": 1, "patient_name": "Pamuk", "session_date": "2026-08-14"}, "Pamuk")

    tablolar = [x for x in story if hasattr(x, "_cellvalues")]
    assert tablolar, "hasta bilgisi tablosu uretilmedi"
    hucreler = {str(r[0]): r[1] for r in tablolar[0]._cellvalues if r and len(r) > 1}
    assert hucreler.get("Hasta Adı:") == "Pamuk", (
        f"tablo adi kaybetti: {hucreler.get('Hasta Adı:')!r} — baslik 'HASTA RAPORU: PAMUK' derken "
        "tablo 'Belirtilmemis' diyor; belge KENDI ICINDE celisiyor"
    )


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
