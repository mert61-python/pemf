# -*- coding: utf-8 -*-
"""KP-1 · `database/treatment_history_db.py` · sözleşmeler: açılış bütünlük denetimi BAŞARISIZ / patlarsa günlüğe yazılır (açılış sürer) ·
eski SQLCipher anahtarı sırası keyring → ortam → `.sqlcipher_key` (keyring / dosya hatası yutulur, ÜRETİLMEZ) · bağlantı havuzu: kapatma
hatası geçersiz kılmayı, ölü iş parçacığı temizliğini, bayat kuşak yenilemesini, geçici bağlantı kapanışını DURDURMAZ; hata sonrası rollback
düşse de ASIL hata yükselir · disk durumu okunamazsa hazırlık ENGELLENMEZ · açılışta açılamayan DB istek yolunda HEMEN reddedilir, arka
plan yeniden açması başarılıysa kilit KALKAR ve eski örnek kapanır (kapanamasa da) · aynı yol karşılaştırması None / samefile hatasına dayanıklı.

GERÇEK TreatmentHistoryDB (tmp). Anahtar kaynağı (`keyring` modülü), bağlantı nesneleri ve disk durumu EN ALT katta sahte; modül tekili
(`_treatment_db_instance`) ve açılış kilidi sözlüğü her testte geri konur.
"""

from __future__ import annotations

import logging
import os
import threading
from types import SimpleNamespace

import database.treatment_history_db as thm
import pytest
from database.treatment_history_db import TreatmentHistoryDB


@pytest.fixture
def db(tmp_path, monkeypatch):
    for ad in (
        "PEMF_RETAIN_PII_DAYS",
        "PEMF_MASK_HISTORY_PII",
        "PEMF_RETAIN_EVENT_DAYS",
        "PEMF_RETAIN_SENSOR_DAYS",
        "PEMF_SQLCIPHER_KEY",
    ):
        monkeypatch.delenv(ad, raising=False)
    d = TreatmentHistoryDB(tmp_path / "gecmis")
    try:
        yield d
    finally:
        d.close_connections()


class _Baglanti:
    """Kapatması / işlem denetimi / geri alması istenirse patlayan sahte bağlantı (kayıtlı)."""

    def __init__(self, kapat=False, islem=False, geri=False):
        self._k, self._i, self._g = kapat, islem, geri
        self.kapatildi = 0

    def close(self):
        self.kapatildi += 1
        if self._k:
            raise OSError("tanıtıcı zaten kapalı")

    @property
    def in_transaction(self):
        if self._i:
            raise RuntimeError("bağlantı koptu")
        return False

    def rollback(self):
        if self._g:
            raise OSError("rollback düştü")


def test_acilis_butunluk_denetimi_BASARISIZ_ya_da_PATLARSA_gunluklenir_acilis_surer(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(
        TreatmentHistoryDB, "run_integrity_check", lambda self, quick=True: {"ok": False, "details": "sayfa 7 bozuk"}
    )
    with caplog.at_level(logging.ERROR):
        a = TreatmentHistoryDB(tmp_path / "a")
    a.close_connections()
    monkeypatch.setattr(
        TreatmentHistoryDB, "run_integrity_check", lambda self, quick=True: (_ for _ in ()).throw(OSError("G/Ç"))
    )
    with caplog.at_level(logging.ERROR):
        b = TreatmentHistoryDB(tmp_path / "b")
    b.close_connections()
    mesajlar = " ".join(r.getMessage() for r in caplog.records)
    assert (
        "BUTUNLUK KONTROLU BASARISIZ" in mesajlar
        and "sayfa 7 bozuk" in mesajlar
        and "Acilis butunluk kontrolu hatasi" in mesajlar
    )


def test_eski_anahtar_SIRASI_keyring_ortam_dosya_hatalar_yutulur_URETILMEZ(db, monkeypatch, caplog):
    monkeypatch.setattr(thm, "keyring", SimpleNamespace(get_password=lambda s, a: " keyring-anahtari "))
    assert db._get_sqlcipher_key_legacy() == "keyring-anahtari"
    monkeypatch.setattr(
        thm, "keyring", SimpleNamespace(get_password=lambda s, a: (_ for _ in ()).throw(RuntimeError("kasa yok")))
    )
    monkeypatch.setenv("PEMF_SQLCIPHER_KEY", " ortam-anahtari ")
    with caplog.at_level(logging.WARNING):
        assert db._get_sqlcipher_key_legacy() == "ortam-anahtari"
    assert any("keyring okuma hatasi" in r.getMessage() for r in caplog.records)
    monkeypatch.delenv("PEMF_SQLCIPHER_KEY")
    (db.app_data_dir / ".sqlcipher_key").mkdir()  # dosya yerine DİZİN → okuma düşer
    assert db._get_sqlcipher_key_legacy() == "", "eski yol anahtar ÜRETTİ ya da istisna sızdı"
    assert not list(db.app_data_dir.glob(".sqlcipher_key*.tmp"))


def test_KRITIK_gecersiz_kilmada_kapatma_HATASI_temizligi_ve_kusagi_DURDURMAZ(db, caplog):
    patlayan, saglam = _Baglanti(kapat=True), _Baglanti()
    db._live_conns[111] = (lambda: None, patlayan)
    db._live_conns[222] = (lambda: None, saglam)
    db._local.conn = _Baglanti(kapat=True)
    kusak = db._conn_generation
    with caplog.at_level(logging.INFO):
        db._invalidate_connections("test geri alma")
    assert db._conn_generation == kusak + 1 and db._live_conns == {} and db._local.conn is None
    assert patlayan.kapatildi == 1 and saglam.kapatildi == 1, (
        "patlayan kapatma diğer bağlantıyı kapatmadı (tanıtıcı sızar)"
    )
    with db._get_connection() as c:  # geçersiz kılmadan sonra taze, çalışan bağlantı
        assert c.execute("SELECT 1").fetchone()[0] == 1


def test_kapanista_gecersiz_kilma_PATLARSA_hata_gunluklenir(db, monkeypatch, caplog):
    monkeypatch.setattr(
        db, "_invalidate_connections", lambda reason="": (_ for _ in ()).throw(RuntimeError("havuz bozuk"))
    )
    with caplog.at_level(logging.ERROR):
        db.close_connections()
    assert any("Error closing connection" in r.getMessage() for r in caplog.records)
    monkeypatch.undo()


def test_olu_is_parcacigi_baglantisi_kapatma_patlasa_da_DEFTERDEN_duser(db):
    t = threading.Thread(target=lambda: None)
    t.start()
    t.join()
    import weakref

    db._live_conns[999] = (weakref.ref(t), _Baglanti(kapat=True))
    with db._pool_lock:
        db._prune_dead_pool_entries()
    assert 999 not in db._live_conns


def test_bayat_kusak_baglantisi_kapatma_patlasa_da_YENISIYLE_degisir(db):
    with db._get_connection():
        pass
    bayat = _Baglanti(kapat=True)
    db._local.conn, db._local.conn_gen = bayat, db._conn_generation - 1
    with db._get_connection() as c:
        assert c is not bayat and c.execute("SELECT 1").fetchone()[0] == 1
    assert bayat.kapatildi == 1


def test_gecici_baglanti_ve_islem_denetimi_HATALARI_yutulur_rollback_dusse_de_ASIL_hata_yukselir(db, monkeypatch):
    monkeypatch.setattr(db, "MAX_POOLED_CONNECTIONS", 0)
    sonuc: list = []

    def _isci():
        geciciler = []
        monkeypatch.setattr(
            db, "_create_connection", lambda: geciciler.append(_Baglanti(kapat=True, geri=True)) or geciciler[-1]
        )
        try:
            with db._get_connection():
                raise ValueError("asıl hata")
        except ValueError as e:
            sonuc.append(str(e))
        sonuc.append(geciciler[0].kapatildi)

    t = threading.Thread(target=_isci)
    t.start()
    t.join(10)
    assert sonuc == ["asıl hata", 1], (
        "rollback / geçici kapatma hatası asıl hatayı yuttu ya da geçici bağlantı kapanmadı"
    )
    monkeypatch.undo()
    db._local.conn, db._local.conn_gen = _Baglanti(islem=True), db._conn_generation
    with db._get_connection():
        pass  # açık işlem denetimi patlasa da çıkış sessiz


def test_disk_durumu_OKUNAMAZSA_hazirlik_ENGELLENMEZ(db, monkeypatch, caplog):
    monkeypatch.setattr(db, "get_disk_space_status", lambda: (_ for _ in ()).throw(OSError("birim yok")))
    with caplog.at_level(logging.WARNING):
        assert db.is_ready() == (True, "")
    assert any("Disk alani okunamadi" in r.getMessage() for r in caplog.records)


@pytest.fixture
def tekil(monkeypatch):
    monkeypatch.setattr(thm, "_treatment_db_instance", None)
    monkeypatch.setattr(thm, "_acilis_kilidi", {})
    yield thm
    if thm._treatment_db_instance is not None:
        thm._treatment_db_instance.close_connections()


def test_KRITIK_acilista_acilamayan_DB_istek_yolunda_HEMEN_reddedilir_arka_plan_acinca_kilit_KALKAR(
    tekil, tmp_path, monkeypatch
):
    kok = tmp_path / "kok"
    kok.mkdir()
    tekil.acilis_hatasini_kilitle(kok, RuntimeError("anahtar çözülemez"))
    with pytest.raises(RuntimeError, match="acilista ACILAMADI"):
        tekil.get_treatment_db(kok)
    import utils.path_utils as pu

    monkeypatch.setattr(pu, "goc_engelini_yeniden_dene", lambda yol: None)
    yeni = tekil.acilista_acilamayani_yeniden_ac(kok)
    assert tekil.get_treatment_db(kok) is yeni, "arka plan açtı ama istek yolu hâlâ reddediyor (kilit kalmış)"
    baska = tmp_path / "baska"
    baska.mkdir()
    tekil.get_treatment_db(baska)  # örnek başka köke geçer (ör. veri kökü değişti) …
    geri = tekil.get_treatment_db(kok)  # … geri dönünce açılış kilidi KALMAMIŞ olmalı (kalmışsa RuntimeError)
    assert tekil.acilista_acilamayani_yeniden_ac(kok) is geri, "zaten açık DB yeniden kuruldu"


def test_yeniden_acmada_eski_ornek_KAPANAMASA_da_yenisi_kurulur(tekil, tmp_path, monkeypatch, caplog):
    import utils.path_utils as pu

    monkeypatch.setattr(pu, "goc_engelini_yeniden_dene", lambda yol: None)
    eski = SimpleNamespace(
        db_path=tmp_path / "baska" / "pemf_treatment_history.db",
        close=lambda: (_ for _ in ()).throw(OSError("kilitli")),
    )
    monkeypatch.setattr(thm, "_treatment_db_instance", eski)
    (tmp_path / "kok").mkdir()
    with caplog.at_level(logging.WARNING):
        yeni = tekil.acilista_acilamayani_yeniden_ac(tmp_path / "kok")
    assert yeni is not eski and tekil._treatment_db_instance is yeni
    assert any("eski tedavi DB ornegi kapatilamadi" in r.getMessage() for r in caplog.records)


def test_ayni_yol_karsilastirmasi_None_ve_samefile_HATASINA_dayanikli(tmp_path, monkeypatch):
    assert thm._ayni_db_yolu(None, tmp_path) is False
    a = tmp_path / "x.db"
    a.write_bytes(b"")
    monkeypatch.setattr(os.path, "samefile", lambda x, y: (_ for _ in ()).throw(OSError("ağ yolu")))
    assert thm._ayni_db_yolu(str(a), str(tmp_path / "." / "x.db")) is True, (
        "samefile düşünce normalize yol karşılaştırması yapılmadı"
    )


def test_yeniden_deneme_geri_cekilmesi_USSEL_ve_300_snde_TAVAN():
    assert [TreatmentHistoryDB._retry_backoff_seconds(n) for n in (-3, 0, 1, 2, 5, 8, 9, 30)] == [
        1,
        1,
        2,
        4,
        32,
        256,
        300,
        300,
    ]


def test_karantina_oncesi_baglanti_birakma_kapatma_patlasa_da_HAVUZDAN_duser(db):
    db._local.conn = _Baglanti(kapat=True)
    db._live_conns[threading.get_ident()] = (lambda: None, db._local.conn)
    db._baglantiyi_birak()
    assert db._local.conn is None and threading.get_ident() not in db._live_conns, (
        "dosya kilidi tutan bağlantı havuzda kaldı"
    )


def test_farkli_yol_istenince_eski_ornek_KAPANAMASA_da_yenisi_doner(tekil, tmp_path, monkeypatch, caplog):
    eski = SimpleNamespace(
        db_path=tmp_path / "eski" / "pemf_treatment_history.db", close=lambda: (_ for _ in ()).throw(OSError("kilitli"))
    )
    monkeypatch.setattr(thm, "_treatment_db_instance", eski)
    (tmp_path / "yeni").mkdir()
    with caplog.at_level(logging.WARNING):
        yeni = tekil.get_treatment_db(tmp_path / "yeni")
    assert yeni is not eski and yeni.db_path == tmp_path / "yeni" / "pemf_treatment_history.db"
    assert any("eski tedavi DB ornegi kapatilamadi" in r.getMessage() for r in caplog.records)
