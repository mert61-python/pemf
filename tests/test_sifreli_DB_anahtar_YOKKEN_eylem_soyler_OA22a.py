# -*- coding: utf-8 -*-
"""O-A2-2.a (2-A incelemesi gözlemi — D3 devri → D5): at-rest anahtarı YOKKEN (sır dosyası kayıp / yenilenmiş) ŞİFRELİ bir veritabanı
dosyasıyla karşılaşan açılış yalnız "file is not a database" diyordu — operatör "dosya bozuk" sanıp silebilir (hafıza "Hata mesajı EYLEM
söylesin"). Artık ERROR satırı dosyanın ŞİFRELİ göründüğünü, DOKUNULMADIĞINI ve YAPILACAĞI (kurtarma zarfı + kurtarma kodu) söyler.
Davranış AYNI: dosya karantinaya alınmaz, silinmez, istisna yine yükselir (fail-closed, kısıtlı kip). Gerçek sqlcipher3 ile anahtarlı GERÇEK
şifreli dosya (sahte bağlayıcı değil) — sqlcipher3 yoksa A-46 kanalı atlamaya izin vermez (conftest sayacı)."""

from __future__ import annotations

import logging

import pytest

sqlcipher3 = pytest.importorskip("sqlcipher3")


def _sifreli_dosya(yol, tablo):
    c = sqlcipher3.connect(str(yol))
    c.execute("PRAGMA key='OA22a-baska-anahtar'")
    c.execute(f"CREATE TABLE {tablo} (id INTEGER PRIMARY KEY, x TEXT)")
    c.execute(f"INSERT INTO {tablo} (x) VALUES ('kayit')")
    c.commit()
    c.close()
    with open(yol, "rb") as f:
        assert f.read(16) != b"SQLite format 3\x00", "aparat: dosya şifreli değil"


def _eylem_satiri(caplog):
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno >= logging.ERROR and "anahtari YOK" in r.getMessage() and "--kurtarma" in r.getMessage()
    ]


@pytest.fixture
def anahtarsiz(monkeypatch):
    from database import patient_database as pdb
    from database import sqlcipher_util as su
    from database import treatment_history_db as thdb

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    return pdb, thdb


def test_KRITIK_hasta_DB_sifreli_anahtar_YOK_EYLEM_soyler_dosyaya_DOKUNMAZ(tmp_path, anahtarsiz, caplog):
    pdb, _ = anahtarsiz
    yol = tmp_path / "patients.db"
    _sifreli_dosya(yol, "patients")
    once = yol.read_bytes()
    caplog.set_level(logging.ERROR)
    with pytest.raises(RuntimeError):
        pdb.PatientDatabase(str(yol))
    assert _eylem_satiri(caplog), (
        "anahtar YOKKEN şifreli hasta DB'si: ERROR satırı eylem söylemiyor (yalnız 'file is not a database')"
    )
    assert yol.read_bytes() == once and not list(tmp_path.glob("patients.db.acilamadi-*")), (
        "dosyaya DOKUNULDU / karantina"
    )


def test_KRITIK_tedavi_DB_sifreli_anahtar_YOK_EYLEM_soyler_dosyaya_DOKUNMAZ(tmp_path, anahtarsiz, caplog):
    _, thdb = anahtarsiz
    kok = tmp_path / "gecmis"
    kok.mkdir()
    yol = kok / "pemf_treatment_history.db"
    _sifreli_dosya(yol, "treatment_sessions")
    once = yol.read_bytes()
    caplog.set_level(logging.ERROR)
    try:
        db = thdb.TreatmentHistoryDB(kok)
        db.close()
    except Exception:
        pass  # davranış (kısıtlı kip / istisna) bu kapının konusu değil — ileti ve dosya
    assert _eylem_satiri(caplog), "anahtar YOKKEN şifreli tedavi DB'si: ERROR satırı eylem söylemiyor"
    assert yol.read_bytes() == once and not list(kok.glob("pemf_treatment_history.db.acilamadi-*")), (
        "dosyaya DOKUNULDU / karantina"
    )


def test_KARSIT_duz_sqlite_dosyada_SIFRELI_iletisi_YOK(tmp_path, anahtarsiz, caplog):
    import sqlite3

    pdb, _ = anahtarsiz
    yol = tmp_path / "patients.db"
    c = sqlite3.connect(str(yol))
    c.execute("CREATE TABLE eski (id INTEGER)")
    c.commit()
    c.close()
    caplog.set_level(logging.ERROR)
    pdb.PatientDatabase(str(yol))
    assert not _eylem_satiri(caplog), "düz SQLite dosyada 'şifreli görünüyor' iletisi YANLIŞ alarm"


def test_KARSIT_sifreli_gorunur_mu_YALNIZ_basliksiz_dolu_dosyada(tmp_path):
    """Yardımcının kendisi: SQLite başlıklı dosya / boş dosya / başlıktan kısa dosya / olmayan yol → False; başlıksız dolu dosya → True
    (yukarıdaki düz-dosya karşıtı hata dalına hiç girmediği için ileti seçimini tek başına ölçmez)."""
    from database.sqlcipher_util import sifreli_gorunur_mu

    baslikli = tmp_path / "a.db"
    baslikli.write_bytes(b"SQLite format 3\x00" + b"\x00" * 100)
    bos = tmp_path / "b.db"
    bos.write_bytes(b"")
    kisa = tmp_path / "c.db"
    kisa.write_bytes(b"SQLite")
    sifreli = tmp_path / "d.db"
    sifreli.write_bytes(bytes(range(200)))
    assert not sifreli_gorunur_mu(baslikli)
    assert not sifreli_gorunur_mu(bos)
    assert not sifreli_gorunur_mu(kisa)
    assert not sifreli_gorunur_mu(tmp_path / "yok.db")
    assert sifreli_gorunur_mu(sifreli)
