# -*- coding: utf-8 -*-
"""D2-1.1 (2-D incelemesi, A1) — sistem saati GERİ giderse (ya da bir gün İLERİ gidip düzelirse) yedekler sessizce ALINMAZ.

ÖLÇÜLEN KUSUR (HEAD a76ee0d; ebeveyn d1d10ea'da da aynı):
  1. `_rotasyon` geçerli yedekleri ADA (= yedek anındaki yerel saat damgası) göre sıralayıp `[:-N]`i siler. Saat geride iken alınan
     yedeğin damgası mevcut N yedeğin hepsinden "eski" görünür → AYNI TURDA kendi yeni yedeği silinir. Yerel rotasyon makine dışı
     kopyadan ÖNCE koştuğu için kopya da düşer ve ERROR "hedef dolu / erisilemez olabilir" der (yanlış teşhis). Saat damgayı geçene dek
     (RTC pili / BIOS sıfırlanınca aylar-yıllar) hiçbir yeni seans hiçbir yedeğe girmez. D2.51 sonrası makine dışı hedefte de aynı
     kural: hedefte N "gelecek" damgalı kopya varsa yeni kopya orada da silinir (ebeveynde makine dışında silme yoktu).
  2. Açılış kararı (`_en_yeni_gecerli_yedek_yasi`) gelecekteki mtime'ı "yaş 0 = taze" sayar → her gün kapanan klinik PC'sinde
     (süreç 24 saat yaşamaz) açılış yedeği HER GÜN atlanır; gelecek tarihli TEK bir yedek (saat bir gün ileri gidip düzeldi) yedeği
     o tarihe kadar durdurur.
DÜZELTME: rotasyon BU TURUN yedeğini silmez (saat geride iken son N + 1 kalır, ERROR "saat"); tazelik kararı gelecek tarihli yedekleri
saymaz (WARNING). Y11 (son N) normal saatte DEĞİŞMEZ (karşıt kol).
SAHTE EN ALT KATTA: yalnız saat (`datetime.now`, `time.time`, `time.monotonic`) ve dosya mtime'ı (`os.utime`, damgaya eşit — sahada mtime
da aynı saatten gelir). Yedek, kopya, rotasyon, açılış döngüsü GERÇEK.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import sqlite3
import threading
import time
import types
from datetime import datetime as _dt
from pathlib import Path

import pytest

N = 3


@pytest.fixture
def nas(tmp_path, monkeypatch):
    d = tmp_path / "NAS"
    monkeypatch.setenv("PEMF_BACKUP_DIR", str(d))
    return d


def _duz_db(app: Path, monkeypatch):
    from database import sqlcipher_util as su
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    db = TreatmentHistoryDB(app)
    assert not db.at_rest_encrypted, "aparat: düz kurulum bekleniyordu"
    return db


def _isci(app: Path, db):
    from services.headless_db_maintenance import HeadlessDBMaintenance

    w = object.__new__(HeadlessDBMaintenance)
    w.app_data_dir, w.db, w.patient_db = app, db, None
    w.backup_interval, w.backup_retention_keep = 24 * 3600, N
    w.maint_interval, w.disk_interval = 6 * 3600, 30 * 60
    w._stop, w._thread = threading.Event(), None
    return w


def _saat(monkeypatch, an: _dt, mono: float = 3600.0):
    import services.headless_db_maintenance as hdm

    class _Saat:
        @staticmethod
        def now(tz=None):
            return an

    monkeypatch.setattr(hdm, "datetime", _Saat)
    monkeypatch.setattr(
        hdm, "time", types.SimpleNamespace(monotonic=lambda: mono, time=lambda: an.timestamp(), sleep=time.sleep)
    )


def _mtime_damgaya(w, an: _dt):
    damga = an.strftime("%Y%m%d_%H%M%S")
    for d in (w.app_data_dir / "backups", Path(os.environ["PEMF_BACKUP_DIR"])):
        if d.is_dir():
            for p in d.iterdir():
                if damga in p.name:
                    os.utime(p, (an.timestamp(), an.timestamp()))


def _tur(monkeypatch, w, an: _dt):
    """Gerçek `_run_backup` turu (24/7 açık makinede döngünün periyodik yedeği)."""
    _saat(monkeypatch, an)
    w._run_backup()
    _mtime_damgaya(w, an)


class _TekTur:
    def __init__(self):
        self._kalan = 1

    def is_set(self):
        return self._kalan <= 0

    def wait(self, _sn=None):
        self._kalan -= 1
        return True


def _acilis(monkeypatch, w, an: _dt) -> int:
    """Bir açılış = gerçek `_loop`un yalnız İLK turu (klinik PC'si akşam kapanır; süreç 24 saat yaşamaz). Döndürür: yedek turu sayısı."""
    _saat(monkeypatch, an, mono=3600.0)
    sayac = {"n": 0}
    gercek = type(w)._run_backup

    def _say():
        sayac["n"] += 1
        gercek(w)
        _mtime_damgaya(w, an)

    monkeypatch.setattr(w, "_run_backup", _say)
    monkeypatch.setattr(w, "_run_maintenance", lambda: None)
    monkeypatch.setattr(w, "_check_disk", lambda: None)
    w._stop = _TekTur()
    w._loop()
    return sayac["n"]


def _yedekler(d: Path) -> list:
    """Bu testin KENDİ deseni (ürün sabitinden okunmaz)."""
    desen = re.compile(r"pemf_treatment_history_\d{8}_\d{6}\.db")
    return sorted(p for p in d.iterdir() if p.is_file() and desen.fullmatch(p.name)) if d.is_dir() else []


def _adlar(p: Path) -> set:
    c = sqlite3.connect(str(p))
    try:
        return {r[0] for r in c.execute("SELECT patient_name FROM treatment_sessions")}
    finally:
        c.close()


def _tasiyan(d: Path, ad: str) -> list:
    return [p.name for p in _yedekler(d) if ad in _adlar(p)]


# ───────────────────────── 1 · saat geride: bu turun yedeği (yerel + makine dışı) KALIR; geçmiş silinmez ─────────────────────────


def test_KRITIK_saat_GERIDE_rotasyon_bu_turun_YENI_yedegini_silmez_yerel_ve_makine_disi(
    temp_app_data, nas, monkeypatch, caplog
):
    db = _duz_db(temp_app_data, monkeypatch)
    yerel = temp_app_data / "backups"
    try:
        db.start_session(treatment_mode="Manuel", patient_name="EskiHasta")
        w = _isci(temp_app_data, db)
        for gun in range(1, 5):
            _tur(monkeypatch, w, _dt(2026, 10, gun, 3, 0, 0))
        gecmis = [p.name for p in _yedekler(yerel)]
        assert len(gecmis) == N and _tasiyan(yerel, "EskiHasta"), "ön koşul: N geçerli yedek, okuyucu hastayı görüyor"

        db.start_session(treatment_mode="Manuel", patient_name="YeniHasta")  # saat 2026-01-01'e döndü (RTC / BIOS)
        with caplog.at_level(logging.WARNING, logger="services.headless_db_maintenance"):
            for k in range(3):
                _tur(monkeypatch, w, _dt(2026, 1, 1 + k, 9, 0, 0))
                assert _tasiyan(yerel, "YeniHasta"), (
                    f"saat geride tur {k}: bu turun YENİ yedeği aynı turda SİLİNDİ — yeni seanslar hiçbir yerel yedekte yok: "
                    f"{[p.name for p in _yedekler(yerel)]}"
                )
                assert _tasiyan(nas, "YeniHasta"), (
                    f"saat geride tur {k}: yeni seanslar makine dışı hedefte de yok: {[p.name for p in _yedekler(nas)]}"
                )
                assert len(_yedekler(yerel)) <= N + 1 and len(_yedekler(nas)) <= N + 1, (
                    "saat geride iken yedekler sınırsız birikiyor"
                )
                assert set(gecmis) <= {p.name for p in _yedekler(yerel)}, (
                    "saat geride iken eski geçmiş yedekleri silindi"
                )
        assert any(r.levelno >= logging.WARNING and "saat" in r.getMessage().lower() for r in caplog.records), (
            "saat geride olduğu (bu turun yedeğinin en eski damgalı göründüğü) günlükte SÖYLENMEDİ"
        )
        assert not any("hedef dolu" in r.getMessage() for r in caplog.records), (
            "makine dışı kopya YEREL rotasyonun sildiği dosya yüzünden düştü ve 'hedef dolu / erisilemez' dendi (yanlış teşhis)"
        )

        # KARŞIT (Y11 değişmez): saat düzelince her yerde yine TAM N kalır, en yeni yedek güncel veriyi taşır.
        for gun in range(5, 8):
            _tur(monkeypatch, w, _dt(2026, 10, gun, 3, 0, 0))
        for d in (yerel, nas):
            assert len(_yedekler(d)) == N, f"{d.name}: saat düzeldikten sonra {len(_yedekler(d))} yedek (Y11: N={N})"
            assert "YeniHasta" in _adlar(_yedekler(d)[-1])
    finally:
        db.close()


def test_KRITIK_makine_disinda_N_gelecek_damgali_kopya_varken_bu_turun_kopyasi_SILINMEZ(
    temp_app_data, nas, monkeypatch
):
    """Yerel `backups/` boş (yeni kurulum / taşınmış cihaz), makine dışı hedefte N tane ileri damgalı geçerli kopya var.
    Ebeveynde makine dışında silme yoktu → yeni kopya kalıyordu; D2.51 rotasyonu onu AYNI TURDA siler."""
    db = _duz_db(temp_app_data, monkeypatch)
    try:
        db.start_session(treatment_mode="Manuel", patient_name="EskiHasta")
        w = _isci(temp_app_data, db)
        _tur(monkeypatch, w, _dt(2026, 10, 1, 3, 0, 0))
        kaynak = _yedekler(temp_app_data / "backups")[0]
        for gun in range(2, 2 + N):
            shutil.copy2(kaynak, nas / f"pemf_treatment_history_202610{gun:02d}_030000.db")
        shutil.rmtree(temp_app_data / "backups")
        (nas / "pemf_treatment_history_20261001_030000.db").unlink()
        assert len(_yedekler(nas)) == N

        db.start_session(treatment_mode="Manuel", patient_name="YeniHasta")
        _tur(monkeypatch, w, _dt(2026, 1, 5, 9, 0, 0))  # saat geride
        assert _tasiyan(temp_app_data / "backups", "YeniHasta"), "aparat: yerel yedek alınmalıydı"
        assert _tasiyan(nas, "YeniHasta"), (
            f"makine dışı rotasyon bu turun DOĞRULANMIŞ kopyasını aynı turda sildi: {[p.name for p in _yedekler(nas)]}"
        )
    finally:
        db.close()


# ───────────────────────── 2 · gelecek tarihli yedek açılış yedeğini bastırmaz (günlük kapanan PC) ─────────────────────────


def test_KRITIK_gelecek_tarihli_TEK_yedek_gunluk_acilis_yedegini_BASTIRMAZ_ve_yeniden_baslatma_korumasi_SURER(
    temp_app_data, nas, monkeypatch, caplog
):
    db = _duz_db(temp_app_data, monkeypatch)
    yerel = temp_app_data / "backups"
    try:
        db.start_session(treatment_mode="Manuel", patient_name="EskiHasta")
        w = _isci(temp_app_data, db)
        for an in (_dt(2026, 10, 1, 18, 0, 0), _dt(2026, 10, 2, 18, 0, 0), _dt(2036, 10, 3, 18, 0, 0)):
            _tur(monkeypatch, w, an)  # üçüncü gün saat 10 yıl İLERİ gitti, sonra NTP / operatör düzeltti
        db.start_session(treatment_mode="Manuel", patient_name="YeniHasta")
        with caplog.at_level(logging.WARNING, logger="services.headless_db_maintenance"):
            alinan = [
                _acilis(monkeypatch, w, _dt(2026, 10, 5, 9, 0, 0)),
                _acilis(monkeypatch, w, _dt(2026, 10, 5, 9, 5, 0)),  # aynı sabah yeniden başlatma
                _acilis(monkeypatch, w, _dt(2026, 10, 6, 9, 0, 0)),
            ]
        assert alinan[0] == 1, (
            f"gelecek tarihli (2036) tek yedek 'taze' sayıldı → günlük açılış yedeği ATLANDI {alinan}: her gün kapanan klinik PC'si "
            "o tarihe kadar HİÇ yedek almaz"
        )
        assert alinan[1] == 0, (
            f"yeniden başlatma koruması bozuldu (B-3.11/D2.63): aynı sabah ikinci açılışta yine yedek alındı {alinan}"
        )
        assert alinan[2] == 1, f"24 saat sonraki açılışta yedek alınmadı {alinan}"
        assert _tasiyan(yerel, "YeniHasta"), (
            f"yeni seans hiçbir yerel yedekte yok: {[p.name for p in _yedekler(yerel)]}"
        )
        assert any(r.levelno >= logging.WARNING and "gelecek" in r.getMessage().lower() for r in caplog.records), (
            "gelecek tarihli yedeğin tazelik kararında sayılmadığı günlükte SÖYLENMEDİ"
        )
    finally:
        db.close()


def test_KARSIT_normal_saatte_taze_yedek_varken_acilis_yedegi_YINE_ATLANIR(temp_app_data, nas, monkeypatch):
    db = _duz_db(temp_app_data, monkeypatch)
    try:
        db.start_session(treatment_mode="Manuel", patient_name="EskiHasta")
        w = _isci(temp_app_data, db)
        _tur(monkeypatch, w, _dt(2026, 10, 5, 8, 0, 0))
        assert _acilis(monkeypatch, w, _dt(2026, 10, 5, 9, 0, 0)) == 0, (
            "1 saatlik geçerli yedek varken açılışta yedek alındı"
        )
    finally:
        db.close()


def test_KRITIK_YALNIZ_gelecek_tarihli_yedekler_varken_acilis_yedegi_ALINIR(temp_app_data, nas, monkeypatch, caplog):
    """Orkestratör eki (2-D incelemesi): diskte YALNIZ gelecek tarihli yedek varken (cihazın tüm geçmişi ileri saatle yazıldı, sonra saat
    düzeltildi) açılış yedeği alınır. Bu dal yukarıdaki testte koşmuyordu: geçmiş tarihli yedekler de vardı ("yalnız gelecek varsa taze say"
    mutantı yeşil kalıyordu — ölçüldü)."""
    db = _duz_db(temp_app_data, monkeypatch)
    yerel = temp_app_data / "backups"
    try:
        db.start_session(treatment_mode="Manuel", patient_name="EskiHasta")
        w = _isci(temp_app_data, db)
        for an in (_dt(2036, 10, 1, 18, 0, 0), _dt(2036, 10, 2, 18, 0, 0)):
            _tur(monkeypatch, w, an)  # bütün geçmiş ileri saatle
        db.start_session(treatment_mode="Manuel", patient_name="YeniHasta")
        with caplog.at_level(logging.WARNING, logger="services.headless_db_maintenance"):
            alinan = _acilis(monkeypatch, w, _dt(2026, 10, 5, 9, 0, 0))
        assert alinan == 1, f"yalnız gelecek tarihli yedekler 'taze' sayıldı → açılış yedeği ATLANDI ({alinan})"
        assert _tasiyan(yerel, "YeniHasta"), (
            f"yeni seans hiçbir yerel yedekte yok: {[p.name for p in _yedekler(yerel)]}"
        )
    finally:
        db.close()
