# -*- coding: utf-8 -*-
"""D2.62 (B-3.71 · A-13) — şifreli yedek ANA (birincil) anahtarla; boş anahtar REDDEDİLİR; anahtar arızası artık bırakmaz.

SAHİP KARARI A-13: yedek BİRİNCİL anahtarla şifrelenmeye devam eder (bugünkü). Gerekçe: kurtarma zarfı
(`utils/backup_recovery.RECOVERY_SECRET_KEYS`) yalnız BİRİNCİL `sqlcipher_key`i taşır; yedek "DB'yi açan" (D-3 legacy) anahtarla
yazılsaydı makine dışı kurtarmada AÇILAMAZDI — denetim bu değişikliği regresyon olarak ölçtü. Bu dosya kararı KİLİTLER.

KARARDAN BAĞIMSIZ (D2.62): `_get_sqlcipher_key()` boş dönerse şifreli DB'nin yedeği için hedef bağlantısı HİÇ AÇILMAZ (yedek
reddedilir, neden günlükte). Eskiden boş anahtarla `PRAGMA key=''` deneniyordu: bugünkü sqlcipher3 bunu hata ile reddedip 0 baytlık
dosya bırakıyor [ÖLÇTÜM 2-D sondası]; boş anahtarı "şifresiz" sayan bir SQLCipher sürümünde ise şifreli klinik verisinin DÜZ-METİN
kopyası yazılırdı. Kural kitaplığın davranışına bırakılmaz.

O-A2-1.d (2-A incelemesi, [ÇIKARIM]) "legacy anahtarla açılmış DB'de göç öncesi yedek alınamaz → göç yedeksiz koşar" — 2-D'de
ÖLÇÜLDÜ ve ÇÜRÜTÜLDÜ: SQLCipher yedek API'si farklı anahtarlar arasında çalışıyor (çıktı hedef anahtarla, yani birincille); göç
öncesi yedek alınıyor ve göç düşerse geri alma veriyi koruyor. Aşağıdaki uçtan uca kol bunu kilitler.

Gerçek sqlcipher3 ister (yoksa atlanır → A-46 CI kırmızısı). Sahte en alt katta: yalnız anahtar kaynağı (birincil / legacy).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest
import sahte_sqlcipher

P = "D262-birincil-anahtar"
L = "D262-legacy-anahtar"


def _anahtarlar(monkeypatch, birincil, legacy=""):
    from database import sqlcipher_util as su
    from database import treatment_history_db as thdb

    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
    if callable(birincil):
        monkeypatch.setattr(su, "get_sqlcipher_key", birincil)
    else:
        monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: birincil)
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: legacy)
    return thdb


def _legacy_ile_acilmis_db(monkeypatch, app: Path):
    """Önce L ile şifreli DB kurulur (bir seans); sonra birincil P (≠ L), legacy L → yeni örnek LEGACY anahtarla açılır (D-3)."""
    mod = sahte_sqlcipher.baglayici_kur("gercek", monkeypatch)
    thdb = _anahtarlar(monkeypatch, L)
    ilk = thdb.TreatmentHistoryDB(app)
    sid = ilk.start_session(treatment_mode="Manuel", patient_name="D262Hasta")
    ilk.end_session(sid, duration_minutes=7)
    ilk.close()
    thdb = _anahtarlar(monkeypatch, P, legacy=L)
    db = thdb.TreatmentHistoryDB(app)
    assert getattr(db, "_cipher_key_cache", None) == L, "ön koşul: DB LEGACY anahtarla açılmış olmalı (D-3)"
    return mod, db


def _acilir_mi(mod, yol: Path, anahtar: str):
    c = mod.connect(str(yol))
    try:
        c.execute(f"PRAGMA key='{anahtar}'")
        return int(c.execute("SELECT count(*) FROM treatment_sessions").fetchone()[0])
    except Exception:
        return None
    finally:
        c.close()


def test_KRITIK_D262_bos_anahtarla_SIFRELI_yedek_REDDEDILIR_hedef_hic_ACILMAZ(temp_app_data, monkeypatch, caplog):
    mod = sahte_sqlcipher.baglayici_kur("gercek", monkeypatch)
    thdb = _anahtarlar(monkeypatch, P)
    db = thdb.TreatmentHistoryDB(temp_app_data)
    hedef = temp_app_data / "backups" / "pemf_treatment_history_20261009_030303.db"
    try:
        assert db.at_rest_encrypted is True
        # Bağlantı önbellekli anahtarla sürer; yalnız yedeğin anahtar çözümü BOŞ döner (bozuk / silinmiş sır kaydı).
        monkeypatch.setattr(thdb.TreatmentHistoryDB, "_get_sqlcipher_key", lambda self: "")
        gercek = mod.connect
        hedefe = []

        def _connect(yol, *a, **k):
            if os.path.normcase(str(yol)) == os.path.normcase(str(hedef)):
                hedefe.append(str(yol))
            return gercek(yol, *a, **k)

        monkeypatch.setattr(mod, "connect", _connect)
        with caplog.at_level(logging.ERROR):
            sonuc = db.create_backup(str(hedef))
        assert sonuc is False, "boş anahtarla şifreli yedek 'başarılı' döndü"
        assert hedefe == [], (
            "boş anahtarla yedek HEDEFİNE bağlantı açıldı — `PRAGMA key=''` kitaplığa bırakıldı (boş anahtarı 'şifresiz' sayan "
            "bir sürümde klinik verisinin DÜZ-METİN kopyası yazılır)"
        )
        assert not hedef.exists(), "boş anahtarlı yedek denemesi dosya bıraktı"
        assert any("anahtar" in r.getMessage().lower() and "bos" in r.getMessage().lower() for r in caplog.records), (
            "yedeğin neden alınmadığı (boş anahtar) günlükte söylenmiyor: "
            + repr([r.getMessage()[:120] for r in caplog.records])
        )
    finally:
        db.close()


def test_KRITIK_A13_legacy_ile_acilmis_DB_yedegi_BIRINCIL_anahtarla_acilir_legacy_ile_ACILMAZ(
    temp_app_data, monkeypatch
):
    mod, db = _legacy_ile_acilmis_db(monkeypatch, temp_app_data)
    hedef = temp_app_data / "backups" / "pemf_treatment_history_20261009_040404.db"
    try:
        assert db.create_backup(str(hedef)) is True
        assert _acilir_mi(mod, hedef, P) == 1, (
            "A-13: yedek BİRİNCİL anahtarla açılmalı (kurtarma zarfı yalnız onu taşır)"
        )
        assert _acilir_mi(mod, hedef, L) is None, (
            "A-13 ihlali: yedek DB'yi açan LEGACY anahtarla yazıldı — kurtarma zarfı bu anahtarı taşımaz, makine dışında açılamaz"
        )
    finally:
        db.close()


def test_KARSIT_D262_anahtar_COZULEMEZSE_yedek_False_artik_yok_istisna_yukselmez(temp_app_data, monkeypatch):
    sahte_sqlcipher.baglayici_kur("gercek", monkeypatch)
    thdb = _anahtarlar(monkeypatch, P)
    db = thdb.TreatmentHistoryDB(temp_app_data)
    hedef = temp_app_data / "backups" / "pemf_treatment_history_20261009_050505.db"
    try:

        def _cozulemez(self):
            raise RuntimeError("Sır çözülemedi (D2.45 fail-closed)")

        monkeypatch.setattr(thdb.TreatmentHistoryDB, "_get_sqlcipher_key", _cozulemez)
        assert db.create_backup(str(hedef)) is False
        assert not hedef.exists() and list((temp_app_data / "backups").iterdir()) == []
    finally:
        db.close()


def test_KRITIK_OA21d_legacy_ile_acilmis_DBde_goc_oncesi_yedek_ALINIR_ve_geri_alma_veriyi_KORUR(
    temp_app_data, monkeypatch
):
    """O-A2-1.d çürütmesi (uçtan uca): legacy anahtarla açık DB'de şema göçü öncesi yedek ALINIR (birincil anahtarla); göç
    düşerse geri alma o yedekten veriyi geri koyar ve DB yeniden AÇILIR (göç yedeksiz koşmaz)."""
    mod, db = _legacy_ile_acilmis_db(monkeypatch, temp_app_data)
    try:
        db._set_system_setting("db_schema_version", "2", "D262 aparat: göç zorla")

        def _goc_duser(self):
            raise RuntimeError("D262 aparat: göç adımı düştü")

        monkeypatch.setattr(type(db), "_ensure_schema_version", _goc_duser)
        with pytest.raises(RuntimeError, match="göç adımı düştü"):
            db._run_startup_migrations_with_rollback()
        yedekler = sorted((temp_app_data / "migration_backups").glob("pre_migration_v2_*.db"))
        assert len(yedekler) == 1, f"göç öncesi yedek ALINMADI (legacy açılmış DB): {yedekler}"
        assert _acilir_mi(mod, yedekler[0], P) == 1, "göç öncesi yedek birincil anahtarla açılmalı (A-13)"
    finally:
        db.close()
    monkeypatch.undo()
    _anahtarlar(monkeypatch, P, legacy=L)
    sahte_sqlcipher.baglayici_kur("gercek", monkeypatch)
    from database import treatment_history_db as thdb

    yeniden = thdb.TreatmentHistoryDB(temp_app_data)
    try:
        oturumlar = yeniden.get_session_history(limit=10)
        assert [s.get("patient_name") for s in oturumlar] == ["D262Hasta"], "geri alma sonrası seans geçmişi kayboldu"
    finally:
        yeniden.close()
