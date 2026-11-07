# -*- coding: utf-8 -*-
"""KP-3 C · destek paketi (`utils/support_bundle.py` + `tools/destek_paketi.py`) kapsanmayan kolları — her test bir DAVRANIŞ iddiası:

- PII listesi: eski DB'de olmayan tablonun sorgusu atlanır, okunabilen değerler yine maskelemeye girer.
- Günlük kuyruğu okunamazsa pakete "[okunamadi: …]" yazılır (paket düşmez).
- Sağlık özeti: sürüm / platform / firmware durumu okunamasa da özet üretilir (firmware için hata TÜRÜ yazılır).
- Paket: günlük dizinindeki alt dizin atlanır (yalnız dosyalar).
- CLI veri kökü: açık `--veri-dizini` > `PEMF_DATA_DIR` > makine kökü (`%PROGRAMDATA%\\PEMF_System\\PEMF_GUI` — varsa) > uygulama verisi;
  makine kökü seçilince `PEMF_DATA_DIR` YALNIZ bu süreç için üst dizine kurulur.
- Depo kökü: donmuş EXE'de aranmaz (None); işaret yoksa açık hata; kök `sys.path`te değilse eklenir; betik doğrudan koşulunca paketi
  yazar ve `main()`in kodu süreç kodu olur.

Sahte EN ALT katta: tedavi DB nesnesi (in-memory SQLite), sürüm / platform / firmware okuyucuları, ortam değişkenleri, `sys.frozen`.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sqlite3
import sys
import types
import zipfile
from pathlib import Path

import pytest
from utils import support_bundle as sb

KOK = Path(__file__).resolve().parents[1]
ARAC = KOK / "tools" / "destek_paketi.py"


def _arac_kopyasi(ad="kp3_destek_paketi"):
    spec = importlib.util.spec_from_file_location(ad, ARAC)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_pii_listesi_eksik_tablo_atlanir_okunan_maskelenir(monkeypatch, tmp_path):
    from database import treatment_history_db as thdb

    c = sqlite3.connect(":memory:")
    # eski şema: `operator_name` sütunu YOK → ortadaki sorgu patlar; sonraki sorgular (e-posta, hasta / sahip adı) yine okunmalı
    c.execute("CREATE TABLE treatment_sessions (patient_name TEXT, operator_email TEXT)")
    c.execute("INSERT INTO treatment_sessions VALUES ('Pamuk', 'ayse@klinik.test')")
    c.execute("CREATE TABLE patients (name TEXT, owner_name TEXT)")
    c.execute("INSERT INTO patients VALUES ('Boncuk', 'Ali Veli')")
    db = types.SimpleNamespace(_get_connection=lambda: contextlib.nullcontext(c))
    monkeypatch.setattr(thdb, "get_treatment_db", lambda d: db)
    degerler = sb._pii_degerleri(tmp_path)
    assert {"Pamuk", "ayse@klinik.test", "Boncuk", "Ali Veli"} <= set(degerler), (
        "patlayan sorgu sonraki okumaları da düşürdü"
    )


def test_gunluk_kuyrugu_okunamazsa_isaret(tmp_path):
    assert sb._kuyruk(tmp_path).startswith("[okunamadi: ")


def test_saglik_ozeti_okuyucular_patlasa_da_uretilir(monkeypatch, tmp_path):
    import platform

    from servers import firmware_manager
    from utils import path_utils

    def _patla(*a, **k):
        raise OSError("okunamadı")

    monkeypatch.setattr(path_utils, "get_app_version", _patla)
    monkeypatch.setattr(platform, "system", _patla)

    def _fw_patla():
        raise RuntimeError("firmware durumu kilitli")

    monkeypatch.setattr(firmware_manager, "durum", _fw_patla)
    ozet = sb._saglik_ozeti(tmp_path)
    assert "olusturuldu_utc" in ozet and "app_version" not in ozet and "os" not in ozet
    assert ozet["firmware_guncelleme"] == {"okunamadi": "RuntimeError"}


def test_paket_gunluk_alt_dizinini_atlar(monkeypatch, tmp_path):
    loglar = tmp_path / "logs"
    (loglar / "eski").mkdir(parents=True)
    (loglar / "backend.log").write_text("satir\n", encoding="utf-8")
    monkeypatch.setattr(sb, "_log_dizini", lambda d: loglar)
    monkeypatch.setattr(sb, "_pii_degerleri", lambda d: [])
    bayt, ozet = sb.olustur(tmp_path)
    adlar = zipfile.ZipFile(io.BytesIO(bayt)).namelist()
    assert any(a.endswith("backend.log") for a in adlar) and not any("eski" in a for a in adlar)


def _ortam(monkeypatch, **degerler):
    for ad in ("PEMF_DATA_DIR", "PROGRAMDATA"):
        monkeypatch.setenv(ad, "x")
        monkeypatch.delenv(ad)
    for ad, deger in degerler.items():
        monkeypatch.setenv(ad, deger)


def test_cli_veri_koku_secim_sirasi(monkeypatch, tmp_path):
    arac = _arac_kopyasi()
    from utils import path_utils

    monkeypatch.setattr(path_utils, "get_app_data_directory", lambda: tmp_path / "uygulama")
    makine = tmp_path / "pd" / "PEMF_System" / "PEMF_GUI"
    makine.mkdir(parents=True)
    _ortam(monkeypatch, PEMF_DATA_DIR=str(tmp_path / "veri"), PROGRAMDATA=str(tmp_path / "pd"))
    assert arac._veri_koku_sec(None) == tmp_path / "uygulama", "PEMF_DATA_DIR makine kökünden önce gelmedi"
    _ortam(monkeypatch, PROGRAMDATA=str(tmp_path / "pd_yok"))
    assert arac._veri_koku_sec(None) == tmp_path / "uygulama"
    _ortam(monkeypatch, PROGRAMDATA=str(tmp_path / "pd"))
    assert arac._veri_koku_sec(None) == makine
    assert os.environ["PEMF_DATA_DIR"] == str(makine.parent), "makine kökü seçilince PEMF_DATA_DIR üst dizine kurulmadı"
    _ortam(monkeypatch)
    assert arac._veri_koku_sec(None) == tmp_path / "uygulama"


def test_depo_koku_donmus_ve_isaretsiz_ve_sys_path(monkeypatch, tmp_path):
    arac = _arac_kopyasi()
    with pytest.raises(RuntimeError, match="depo kökü bulunamadı"):
        arac._depo_koku(tmp_path)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert arac._depo_koku(tmp_path) is None
    monkeypatch.delattr(sys, "frozen")
    arka = str(KOK / "apps" / "backend")
    monkeypatch.setattr(sys, "path", [p for p in sys.path if Path(p) not in (KOK, Path(arka))])
    _arac_kopyasi("kp3_destek_paketi_2")
    assert str(KOK) in sys.path and arka in sys.path, "depo kökü / backend sys.path'e eklenmedi"


def test_arac_dogrudan_kosu_paketi_yazar(monkeypatch, tmp_path, capsys):
    hedef = tmp_path / "paket.zip"
    monkeypatch.setattr(
        sys, "argv", ["destek_paketi.py", "--veri-dizini", str(tmp_path / "veri"), "--cikti", str(hedef)]
    )
    (tmp_path / "veri").mkdir()
    with pytest.raises(SystemExit) as e:
        _arac_kopyasi("__main__")
    assert e.value.code == 0 and hedef.is_file()
    assert "Destek paketi yazildi" in capsys.readouterr().out
