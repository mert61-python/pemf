# -*- coding: utf-8 -*-
"""KP-3 C · `database/thdb_bakim.py` (tedavi DB'si bakım / taşıma karışımı) kapsanmayan kolları — gerçek `TreatmentHistoryDB` (tmp), her
test bir DAVRANIŞ iddiası (ürün kodu DEĞİŞMEDİ):

- Saat tavanı: cihaz saati son görülenin biraz GERİSİNDEYSE (tolerans içinde) adım koşar ama tavan GERİ ALINMAZ.
- Ayar okunamazsa None; bütünlük denetimi patlarsa `ok=False` + hata metni; sağlık özetinde sayaç sorgusu patlarsa bütünlük `ok=False`
  + "health snapshot error"; bakımda checkpoint / optimize ayrı ayrı başarısız olabilir (rapor söyler), bağlantı yoksa bütünlük raporu hata.
- Şifreli DB'de birincil anahtar çözülemezse yedek doğrulaması uyarıyla anahtarsız yapılır (şifreli yedek AÇILAMAZ sayılır).
- Dışa aktarma: hedef sürümde olmayan tablo boş geçilir; okuma hatası günlüğe yazılır ve YUKARI fırlar (eksik paket sessizce oluşmaz).
- İçe aktarma: geçerli kolonu olmayan satır atlanır; zorunlu alanı eksik satır (bütünlük hatası, doğal anahtar yok) uyarıyla atlanır;
  doğal anahtar araması patlarsa satır bağlanmaz, uyarıyla atlanır.

Sahte EN ALT katta: bağlantı / imleç sarmalayıcısı (belirli SQL desenlerinde OperationalError), anahtar çözücü.
"""

from __future__ import annotations

import contextlib
import logging
import sqlite3
from datetime import datetime, timedelta

import pytest
from database.treatment_history_db import TreatmentHistoryDB


class _SecenekliImlec:
    def __init__(self, imlec, desenler):
        self._i = imlec
        self._d = desenler

    def execute(self, sql, *a):
        for desen in self._d:
            if desen in sql:
                raise sqlite3.OperationalError(f"{desen} reddedildi")
        return self._i.execute(sql, *a)

    def __getattr__(self, ad):
        return getattr(self._i, ad)


class _SecenekliBaglanti:
    def __init__(self, baglanti, desenler):
        self._b = baglanti
        self._d = desenler

    def cursor(self):
        return _SecenekliImlec(self._b.cursor(), self._d)

    def execute(self, sql, *a):
        return self.cursor().execute(sql, *a)

    def __getattr__(self, ad):
        return getattr(self._b, ad)


def _patlat(db, monkeypatch, *desenler):
    gercek = db._get_connection

    @contextlib.contextmanager
    def _gc():
        with gercek() as c:
            yield _SecenekliBaglanti(c, desenler)

    monkeypatch.setattr(db, "_get_connection", _gc)


def _baglantisiz(db, monkeypatch):
    def _patla():
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(db, "_get_connection", _patla)


@pytest.fixture
def db(tmp_path):
    d = TreatmentHistoryDB(tmp_path / "gecmis")
    yield d
    with contextlib.suppress(Exception):
        d.close()


def test_saat_kisa_geri_sapmada_adim_kosar_tavan_geri_alinmaz(db):
    ileri = (datetime.now() + timedelta(minutes=10)).isoformat(timespec="seconds")
    db._set_system_setting(db.SAAT_TAVANI_ANAHTARI, ileri, "test")
    assert db.saat_akla_yatkin_mi() is True
    assert db._get_system_setting(db.SAAT_TAVANI_ANAHTARI) == ileri, "saat tavanı geri alındı"


def test_ayar_butunluk_saglik_ve_bakim_hata_kollari(db, monkeypatch):
    gercek = db._get_connection
    _patlat(db, monkeypatch, "PRAGMA quick_check")
    b = db.run_integrity_check(quick=True)
    assert b["ok"] is False and b["details"] == ["PRAGMA quick_check reddedildi"]
    monkeypatch.setattr(db, "_get_connection", gercek)
    _patlat(db, monkeypatch, "FROM treatment_sessions")
    s = db.get_database_health_snapshot()
    assert s["integrity"]["ok"] is False, "sayaç sorgusu patladığı hâlde bütünlük sağlam göründü"
    assert s["integrity"]["details"] == ["ok", "health snapshot error: FROM treatment_sessions reddedildi"]
    monkeypatch.setattr(db, "_get_connection", gercek)
    _patlat(db, monkeypatch, "wal_checkpoint", "PRAGMA optimize")
    r = db.run_maintenance()
    assert r["checkpoint"] is None and r["optimize"] is False, "başarısız checkpoint / optimize başarılı sayıldı"
    assert r["integrity"]["ok"] is True
    _baglantisiz(db, monkeypatch)
    assert db._get_system_setting("herhangi") is None
    r = db.run_maintenance()
    assert r["integrity"] == {"ok": False, "check": "quick_check", "details": ["unable to open database file"]}


def test_sifreli_dbde_anahtar_cozulemezse_yedek_anahtarsiz_dogrulanir(db, monkeypatch, tmp_path, caplog):
    yedek = tmp_path / "duz_yedek.db"
    c = sqlite3.connect(str(yedek))
    c.execute("CREATE TABLE t (x)")
    c.commit()
    c.close()

    def _anahtar_patla():
        raise RuntimeError("kasa kilitli")

    monkeypatch.setattr(db, "at_rest_encrypted", True)
    monkeypatch.setattr(db, "_get_sqlcipher_key", _anahtar_patla)
    with caplog.at_level(logging.WARNING, logger=db.logger.name):
        assert db.yedek_acilir_mi(yedek) is True
        sifreli = tmp_path / "sifreli.db"
        sifreli.write_bytes(b"\x8f" * 4096)
        assert db.yedek_acilir_mi(sifreli) is False, "anahtarsız doğrulamada şifreli yedek açılır sayıldı"
    assert any("birincil anahtar cozulemedi" in r.getMessage() for r in caplog.records)


def test_disa_aktarma_eksik_tablo_bos_okuma_hatasi_firlar(db, monkeypatch, caplog):
    with db._get_connection() as c:
        c.execute("ALTER TABLE sensor_samples RENAME TO kp3_eski_sensor")
        c.commit()
    out = db.export_rows()
    assert out["sensor_samples"] == [] and "treatment_sessions" in out
    _baglantisiz(db, monkeypatch)
    with caplog.at_level(logging.ERROR, logger=db.logger.name), pytest.raises(sqlite3.OperationalError):
        db.export_rows()
    assert any("Dışa aktarma için satırlar okunamadı" in r.getMessage() for r in caplog.records)


def test_ice_aktarma_kolonsuz_zorunlu_alan_eksik_ve_dogal_anahtar_hatasi(db, monkeypatch, caplog):
    with caplog.at_level(logging.WARNING, logger=db.logger.name):
        sonuc = db.import_rows({"patients": [{"bilinmeyen_kolon": 1}, {"id": 5, "species": "kedi"}]})
    assert sonuc["patients"] == 0
    assert any("patients satırı eklenemedi, atlandı" in r.getMessage() for r in caplog.records)
    assert db.import_rows({"patients": [{"id": 1, "patient_uuid": "u-1", "name": "Pamuk"}]})["patients"] == 1
    caplog.clear()
    _patlat(db, monkeypatch, "SELECT id FROM patients WHERE patient_uuid")
    with caplog.at_level(logging.WARNING, logger=db.logger.name):
        sonuc = db.import_rows(
            {
                "patients": [{"id": 9, "patient_uuid": "u-1", "name": "Pamuk"}],
                "treatment_sessions": [{"id": 3, "patient_id": 9, "session_date": "2026-11-07"}],
            }
        )
    assert sonuc["patients"] == 0 and sonuc["treatment_sessions"] == 0, (
        "bağlanamayan hastanın seansı başka kayda eklendi"
    )
    mesajlar = [r.getMessage() for r in caplog.records]
    assert any("patients satırı eklenemedi, atlandı" in m for m in mesajlar)
    assert any("ebeveyni bulunamadığı için atlandı" in m for m in mesajlar)
