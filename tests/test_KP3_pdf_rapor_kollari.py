# -*- coding: utf-8 -*-
"""KP-3 C · `utils/pdf_report_generator.py` kapsanmayan kolları — her test bir DAVRANIŞ iddiası:

- Biçimleyiciler: geçersiz / taşan zaman → "-", sayıya çevrilemeyen değer AYNEN (rapor hücresi boş kalmaz, PDF düşmez).
- Veri dizini çözülemezse ev dizinindeki `.pemf_gui`a düşülür (uyarıyla); ReportLab yoksa üreteç AÇIKÇA reddeder; modül, depo kökü
  `sys.path`te değilse onu ekler.
- Yazı tipi: aile dosyası yok / bozuk → sonraki aile; hiçbiri yoksa Helvetica + "siyah kutu" uyarısı; bozuk yüz → yedek yüz; Unicode yüz
  yoksa stiller Type1'de BIRAKILIR (yarım dönüşüm yok).
- Rapor üretimi hatası günlüğe yazılır ve YUKARI fırlar (uç 500'e çevirir — sessiz boş PDF yok); hasta seansı yoksa ValueError; geçmiş
  sınırda kırpıldıysa "rapor eksik olabilir" uyarısı; boş kimlik listesi DB'ye gitmez; ad ipucusuz çıktı adı.
- Tek seans: bobin çalışmaları tablosu patlarsa seans yine yazılır (uyarıyla); seans kimliği yoksa tablo eklenmez.

Sahte EN ALT katta: tedavi DB nesnesi (`get_treatment_db` dönüşü), veri dizini çözücüsü, `sys.modules['reportlab']`, yazı tipi dosyaları (tmp).
"""

from __future__ import annotations

import importlib.util
import logging
import sqlite3
import sys
from pathlib import Path

import pytest
from utils import path_utils
from utils import pdf_report_generator as prg

KOK = Path(__file__).resolve().parents[1]
MODUL = KOK / "apps/backend/utils/pdf_report_generator.py"


class _Db:
    def __init__(self, gecmis=None, *, gecmis_hatasi: Exception | None = None, bobin_hatasi: Exception | None = None):
        self.gecmis = list(gecmis or [])
        self.gecmis_hatasi = gecmis_hatasi
        self.bobin_hatasi = bobin_hatasi
        self.gecmis_cagri = 0

    def get_session_history(self, **k):
        self.gecmis_cagri += 1
        if self.gecmis_hatasi:
            raise self.gecmis_hatasi
        return list(self.gecmis)

    def get_session_details(self, sid):
        return {}

    def get_session_coil_runs(self, sid):
        if self.bobin_hatasi:
            raise self.bobin_hatasi
        return []


@pytest.fixture
def uretec(monkeypatch, tmp_path):
    db = _Db()
    monkeypatch.setattr(prg, "get_treatment_db", lambda d: db)
    g = prg.PDFReportGenerator(app_data_dir=tmp_path)
    assert g.db is db
    return g


def test_bicimleyiciler_gecersiz_degerde_tire_ya_da_ham():
    assert prg._fmt_hms(None) == "-"
    assert prg._fmt_hms("saat-degil") == "-"
    assert prg._fmt_hms(1e20) == "-", "taşan zaman damgası raporu düşürdü"
    assert prg._fmt_num(None) == "-"
    assert prg._fmt_num("olculmedi") == "olculmedi"
    assert prg._fmt_num(2) == "2.0"


def test_veri_dizini_cozulemezse_ev_dizinine_duser(monkeypatch, caplog):
    def _patla():
        raise OSError("ProgramData erişilemez")

    monkeypatch.setattr(path_utils, "get_app_data_directory", _patla)
    monkeypatch.setattr(prg, "get_treatment_db", lambda d: _Db())
    with caplog.at_level(logging.WARNING, logger=prg.__name__):
        g = prg.PDFReportGenerator()
    assert g.app_data_dir == Path.home() / ".pemf_gui"
    assert any("app_data_dir alınamadı" in r.getMessage() for r in caplog.records)


def test_reportlab_yoksa_uretec_reddeder_ve_kok_sys_path_e_eklenir(monkeypatch, tmp_path):
    kok = str(path_utils.kaynak_kokunu_bul(MODUL))
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p != kok])
    monkeypatch.setitem(sys.modules, "reportlab", None)
    spec = importlib.util.spec_from_file_location("kp3_pdf_kopya", MODUL)
    kopya = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kopya)
    assert sys.path[0] == kok, "depo kökü sys.path'e eklenmedi"
    assert kopya.REPORTLAB_AVAILABLE is False
    kopya.get_treatment_db = lambda d: _Db()
    with pytest.raises(ImportError, match="ReportLab"):
        kopya.PDFReportGenerator(app_data_dir=tmp_path)


def test_yazi_tipi_ailesi_yok_ya_da_bozuksa_helvetica_ve_uyari(uretec, tmp_path, caplog):
    bozuk = tmp_path / "bozuk.ttf"
    bozuk.write_bytes(b"bu bir TrueType dosyasi degil")
    yok = str(tmp_path / "yok.ttf")
    uretec.FONT_AILELERI = (
        ("KP3-Yok", yok, yok, yok, yok),
        ("KP3-Bozuk", str(bozuk), str(bozuk), str(bozuk), str(bozuk)),
    )
    with caplog.at_level(logging.WARNING, logger=prg.__name__):
        uretec._register_fonts()
    assert uretec.unicode_font == "Helvetica"
    mesajlar = [r.getMessage() for r in caplog.records]
    assert any("KP3-Bozuk" in m and "kaydedilemedi" in m for m in mesajlar)
    assert any("BULUNAMADI" in m for m in mesajlar), "siyah kutu uyarısı yazılmadı"
    assert uretec._yuz_kaydet("KP3-BozukYuz", str(bozuk), "KP3-Yedek") == "KP3-Yedek"


def test_unicode_yuz_yoksa_stiller_type1_de_birakilir(uretec):
    uretec.unicode_font = "Helvetica"
    stil = uretec.styles["Heading3"]
    stil.fontName = "Helvetica-BoldOblique"
    uretec._stilleri_unicode_yap()
    assert stil.fontName == "Helvetica-BoldOblique"


def test_rapor_hatasi_gunluge_yazilir_ve_yukari_firlar(uretec, caplog):
    uretec.db = _Db(gecmis_hatasi=sqlite3.OperationalError("database is locked"))
    with caplog.at_level(logging.ERROR, logger=prg.__name__):
        with pytest.raises(sqlite3.OperationalError):
            uretec.generate_session_report([3], output_path="kullanilmaz.pdf")
        with pytest.raises(sqlite3.OperationalError):
            uretec.generate_patient_report("Pamuk", output_path="kullanilmaz.pdf")
    mesajlar = [r.getMessage() for r in caplog.records]
    assert any("PDF raporu oluşturma hatası" in m for m in mesajlar)
    assert any("Hasta raporu oluşturma hatası" in m for m in mesajlar)


def test_hasta_seansi_yoksa_hata_ve_kirpilmis_gecmis_uyarisi(uretec, monkeypatch, caplog):
    uretec.db = _Db([{"id": 1, "patient_name": "Boncuk", "patient_surname": None}])
    with pytest.raises(ValueError, match="Pamuk"):
        uretec._get_patient_sessions("Pamuk", None, None)
    monkeypatch.setattr(prg, "_HISTORY_FETCH_LIMIT", 2)
    uretec.db = _Db([{"id": i, "patient_name": "Pamuk", "patient_surname": ""} for i in (1, 2)])
    with caplog.at_level(logging.WARNING, logger=prg.__name__):
        assert len(uretec._get_patient_sessions("Pamuk", None, None)) == 2
    assert any("KIRPILDI" in r.getMessage() for r in caplog.records)


def test_bos_kimlik_listesi_db_ye_gitmez_ve_ipucusuz_cikti_adi(uretec):
    db = uretec.db
    assert uretec._fetch_sessions([]) == []
    assert db.gecmis_cagri == 0, "boş seçim için DB sorgulandı"
    yol = Path(uretec._default_output_path("PEMF_Tedavi_Raporu"))
    assert (
        yol.is_absolute()
    )  # dizin: conftest masaüstünü test başına sahte dizine yönlendirir (test_masaustu_sizintisi)
    assert yol.name.startswith("PEMF_Tedavi_Raporu_") and yol.suffix == ".pdf" and yol.name.count("_") == 4


def test_bobin_tablosu_patlarsa_seans_yine_yazilir(uretec, caplog):
    uretec.db = _Db(bobin_hatasi=sqlite3.DatabaseError("bobin tablosu bozuk"))
    hikaye: list = []
    with caplog.at_level(logging.WARNING, logger=prg.__name__):
        uretec._add_single_session(hikaye, {"id": 7, "session_date": "2026-11-07"}, 1, True)
    assert len(hikaye) == 2, "seans başlığı + bilgi tablosu yazılmadı"
    assert any("Bobin calismalari tablosu atlandi (session 7)" in r.getMessage() for r in caplog.records)
    sonraki: list = []
    uretec._add_coil_runs_table(sonraki, None)
    assert sonraki == []
