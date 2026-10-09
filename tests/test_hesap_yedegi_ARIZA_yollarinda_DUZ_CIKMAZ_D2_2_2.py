# -*- coding: utf-8 -*-
"""D2-2.2 (2-D incelemesi A2) — KÖR KAPI: şifreli kurulumda hesap yedeği (S-D.3) ARIZA yollarında da DÜZ çıkmaz, makine dışına gitmez,
geçici dosya kalmaz.

ÖLÇÜLEN KAPI BOŞLUĞU: 2-D kapısı (`test_offsite_ROTASYON_ve_yedek_KAPSAMI_D251_Y11_A32_A45.py`) yalnız anahtarın SAĞLAM olduğu yolu
ölçüyordu. Fail-OPEN mutantları YAŞADI (5/5 passed): (m1) şifreli kurulumda anahtar BOŞ dönünce `yedek_sifre_bilgisi` `(None, "")`
döndürür → hesap yedeği DÜZ; (m2) anahtar çözümü istisna atınca `_ek_kapsam_yedekle` düz yedeğe düşer; (m4) `sqlcipher_export`
yarıda kalınca geçici dosya kaldırılmaz. Ürün BUGÜN doğru [ÖLÇTÜM sonda k2 a1/a2/b1] — bu kapı onu kilitler.

ARIZA EN ALT KATTA: sır deposu (bellek içi `get_secret`) bozuk / boş; `sqlcipher_export` hedefi GERÇEK SQLITE_FULL ile dolar
(`PRAGMA yedek.max_page_count`, gerçek sqlcipher3 bağlantı alt sınıfı). Hesap DB'si, tedavi DB'si (gerçek sqlcipher3), `_run_backup`,
makine dışı kopya GERÇEK. Sır değerleri sentetik.
"""

from __future__ import annotations

import logging
import threading

import pytest

AYSE, PIN = "dr.ayse.d222@klinik.invalid", "246810"
TEST_ANAHTARI = "D2-2-2-sentetik-sqlcipher-anahtari-0123456789"
SQLITE_BASLIK = b"SQLite format 3\x00"


@pytest.fixture
def kurulum(temp_app_data, tmp_path, monkeypatch):
    pytest.importorskip("sqlcipher3", reason="SQLCipher yoksa şifreli kol anlamsız")
    from database.auth_db import AuthDB
    from database.treatment_history_db import TreatmentHistoryDB
    from services.headless_db_maintenance import HeadlessDBMaintenance
    from utils import file_acl
    from utils import secrets_manager as sm

    durum = {"kip": "normal"}

    def _get_secret(k, default="", generate=True):
        if k == "sqlcipher_key" and durum["kip"] == "bozuk":
            raise RuntimeError("sentetik: sır deposu bozuk (çözülemiyor)")
        if k == "sqlcipher_key" and durum["kip"] == "bos":
            return ""
        return {"sqlcipher_key": TEST_ANAHTARI, "patient_fernet_key": "D2-2-2-fernet"}.get(k, default)

    monkeypatch.setattr(sm, "get_secret", _get_secret)
    monkeypatch.setattr(file_acl, "lock_down_file", lambda *a, **k: False)
    monkeypatch.setattr(TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
    nas = tmp_path / "NAS"
    monkeypatch.setenv("PEMF_BACKUP_DIR", str(nas))
    AuthDB(temp_app_data).enroll_operator(AYSE, "Dr. Ayşe", PIN)
    db = TreatmentHistoryDB(temp_app_data)
    assert db.at_rest_encrypted, "aparat: şifreli kurulum bekleniyordu"
    db.start_session(treatment_mode="Manuel", patient_name="Findik")
    w = object.__new__(HeadlessDBMaintenance)
    w.app_data_dir, w.db, w.patient_db = temp_app_data, db, None
    w.backup_interval, w.backup_retention_keep = 24 * 3600, 14
    w._stop, w._thread = threading.Event(), None
    try:
        yield {"app": temp_app_data, "nas": nas, "db": db, "w": w, "durum": durum}
    finally:
        db.close()


def _duz_hesap_kopyalari(*dizinler) -> list:
    """Hesap e-postasını açık taşıyan ya da SQLite başlıklı (şifresiz) HER dosya + her hesap yedeği / geçici artığı."""
    bulunan = []
    for d in dizinler:
        if not d.is_dir():
            continue
        for p in d.rglob("*"):
            if not p.is_file():
                continue
            v = p.read_bytes()
            if p.name.startswith("pemf_auth_users_") or (v[:16] == SQLITE_BASLIK and AYSE.encode() in v):
                bulunan.append(f"{d.name}/{p.name} (duz={v[:16] == SQLITE_BASLIK}, eposta={AYSE.encode() in v})")
    return bulunan


@pytest.mark.parametrize("kip", ["bozuk", "bos"])
def test_KRITIK_D2_2_2_sifreli_kurulumda_anahtar_COZULEMEZ_ya_da_BOSKEN_hesap_yedegi_DUZ_ALINMAZ_makine_disina_GITMEZ(
    kurulum, kip, caplog
):
    kurulum["durum"]["kip"] = kip  # DB açık (önbellekli anahtar); YENİ anahtar çözümü bozuk / boş
    with caplog.at_level(logging.ERROR, logger="services.headless_db_maintenance"):
        kurulum["w"]._run_backup()
    sizan = _duz_hesap_kopyalari(kurulum["app"] / "backups", kurulum["nas"])
    assert not sizan, f"anahtar {kip} iken hesap yedeği / düz kopyası oluştu: {sizan}"
    assert any("Hesap DB yedegi BASARISIZ" in r.getMessage() for r in caplog.records), (
        "hesap yedeğinin alınamadığı günlükte SÖYLENMEDİ"
    )


def test_KRITIK_D2_2_2_sqlcipher_export_YARIDA_kalirsa_ne_son_ad_ne_gecici_dosya_KALMAZ(kurulum, caplog):
    import sqlcipher3.dbapi2 as gercek

    class _DolanHedef(gercek.Connection):
        def execute(self, sql, *a):
            if "sqlcipher_export('yedek')" in sql:
                super().execute("PRAGMA yedek.max_page_count=2")  # hedef GERÇEKTEN dolar (SQLITE_FULL)
            return super().execute(sql, *a)

    class _Mod:
        def __getattr__(self, ad):
            return getattr(gercek, ad)

        def connect(self, *a, **k):
            return gercek.connect(*a, factory=_DolanHedef, **k)

    kurulum["db"].yedek_sifre_bilgisi = lambda: (_Mod(), TEST_ANAHTARI)
    bdir = kurulum["app"] / "backups"
    bdir.mkdir(exist_ok=True)
    with caplog.at_level(logging.ERROR, logger="services.headless_db_maintenance"):
        uretilen = kurulum["w"]._ek_kapsam_yedekle(bdir, "20261009_120000")
    assert [p for p in uretilen if p.name.startswith("pemf_auth_users_")] == []
    kalan = sorted(p.name for p in bdir.iterdir() if p.name.startswith("pemf_auth_users_"))
    assert kalan == [], f"yarıda kalan hesap yedeğinden dosya kaldı: {kalan}"
    assert any("Hesap DB yedegi BASARISIZ" in r.getMessage() for r in caplog.records)
