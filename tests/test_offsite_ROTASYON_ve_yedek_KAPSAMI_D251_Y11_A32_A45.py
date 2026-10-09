# -*- coding: utf-8 -*-
"""D2.51 (B-3.22) · Y11 · A-32 · A-45 — makine dışı yedekte SON N KOPYA, yedek kapsamı hesaplar + ayarlar (SIRSIZ), yabancı dosyaya
DOKUNULMAZ.

ÖLÇÜLEN KUSUR (DENETIM-03 B-3.22, 2-D'de yeniden ölçüldü): `_copy_offsite` yalnız kopyalıyordu; rotasyon yalnız yerel `backups/`
içindi. `PEMF_BACKUP_DIR` hedefi her gün büyüyor (doldukça B-3.19'u tetikliyor) ve canlı DB'den SİLİNEN hastanın adı ilk off-site
kopyada SÜRESİZ kalıyordu — aynı dizindeki kurtarma zarfı + operatör kodu ile açılabilir (KVKK). Otomatik yedek yalnız iki klinik
DB'sini kapsıyordu: operatör hesapları (`auth_users.db`), `config.json` ve `system_settings.json` hiç yedeklenmiyordu.

SAHİP KARARLARI: Y11 — makine dışı hedefte her yedek türünden SON N kopya tutulur, eskileri silinir (N = yerel ile aynı, 14).
A-32 — kapsam genişler: hesaplar, sistem ayarları ve config da yedeklenir; SIR dosyaları HARİÇ. A-45 — tam temizlik makine dışı
yedeklere DOKUNMAZ (teardown tarafı D2.E04); buradaki karşılığı: rotasyon YALNIZ kendi adlandırdığı (`pemf_<tür>_<damga>.<uzantı>`)
ve bu kurulumun anahtarıyla AÇILAN dosyaları siler — hedef yanlışlıkla bir kullanıcı dizini seçilse de başka dosyaya dokunmaz.

Ek (aynı madde): yedekler tek dosyalık rollback-günlüğü (DELETE) kipinde yazılır — WAL başlıklı yedek her açılışta yanına `-wal`/`-shm`
açıyordu [ÖLÇTÜM 2-D sondası]; makine dışı rotasyon bu dosyaları ağ paylaşımında açar ve SQLite WAL'ı ağ dosya sistemlerinde
desteklemez.

SAHTE EN ALT KATTA: yalnız saat (`datetime.now`) ve sır deposu (bellek içi sözlük; gerçek kasa yok). Yedek, kopya, rotasyon, hesap DB'si,
kurtarma aracı GERÇEK.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sqlite3
import threading
from datetime import datetime as _dt
from datetime import timedelta
from pathlib import Path

import pytest

AYSE, PIN = "dr.ayse@klinik.com", "246810"
_KEY = "D251-test-sqlcipher-anahtari-0123456789abcdef"
PAROLA_SIRRI = "gizli-broker-parolasi-D251"
ENC_SIRRI = "enc:gAAAAABD251-sifreli-deger"
UC_SIRRI = "uc-anahtari-D251-xyz"
EPOSTA_SIRRI = "eposta-sifresi-D251"
SIR_ICERIK = "SIR-DOSYASI-ICERIGI-D251"
#: Veri dizinindeki SIR dosyaları — hiçbiri yedeğe girmez (A-32 "SIR dosyaları hariç").
SIR_DOSYALARI = ("pemf_secrets.json", ".pemf_key", ".sqlcipher_key", "api_token.txt", "admin_reset_code.txt")
SQLITE_BASLIK = b"SQLite format 3\x00"


@pytest.fixture
def sirlar(monkeypatch):
    """Sır deposu = bellek içi sözlük (gerçek `pemf_secrets.json` / DPAPI / kasa YOK)."""
    from utils import secrets_manager as sm

    depo: dict = {}
    monkeypatch.setattr(sm, "get_secret", lambda k, default="", generate=True: depo.get(k, default))
    monkeypatch.setattr(sm, "set_secret", lambda k, v: depo.__setitem__(k, v))
    monkeypatch.setattr(sm, "set_secrets", lambda d: depo.update(d))
    return depo


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


def _sifreli_db(app: Path, sirlar: dict):
    pytest.importorskip("sqlcipher3", reason="SQLCipher yoksa şifreli kol anlamsız")
    from database.treatment_history_db import TreatmentHistoryDB

    class _DB(TreatmentHistoryDB):
        def _get_sqlcipher_key(self):
            return _KEY

        def _get_sqlcipher_key_legacy(self):
            return ""

    sirlar.update({"sqlcipher_key": _KEY, "patient_fernet_key": "D251-fernet-anahtari"})
    db = _DB(app)
    assert db.at_rest_encrypted, "aparat: şifreli kurulum bekleniyordu"
    return db


def _isci(app: Path, db, keep: int):
    from services.headless_db_maintenance import HeadlessDBMaintenance

    w = object.__new__(HeadlessDBMaintenance)
    w.app_data_dir, w.db, w.patient_db = app, db, None
    w.backup_interval, w.backup_retention_keep = 24 * 3600, keep
    w._stop, w._thread = threading.Event(), None
    return w


def _tur(monkeypatch, w, gun: int):
    """Gerçek `_run_backup` turu; yalnız saat yamalı (her tur ayrı gün damgası)."""
    import services.headless_db_maintenance as hdm

    an = _dt(2026, 10, 1, 3, 0, 0) + timedelta(days=gun)

    class _Saat:
        @staticmethod
        def now(tz=None):
            return an

    monkeypatch.setattr(hdm, "datetime", _Saat)
    w._run_backup()


def _damgali(dizin: Path, tur: str, ek: str) -> list:
    """Bu testin KENDİ deseni (ürün sabitinden okunmaz): `pemf_<tür>_YYYYMMDD_HHMMSS<ek>` düzenli dosyalar, ada göre sıralı."""
    desen = re.compile(rf"pemf_{tur}_\d{{8}}_\d{{6}}{re.escape(ek)}")
    return sorted(p for p in dizin.iterdir() if p.is_file() and desen.fullmatch(p.name)) if dizin.is_dir() else []


def _adlar(yol: Path) -> set:
    c = sqlite3.connect(str(yol))
    try:
        return {r[0] for r in c.execute("SELECT patient_name FROM treatment_sessions")}
    finally:
        c.close()


def _gecerli_duz_db(yol: Path, ad: str) -> bytes:
    c = sqlite3.connect(str(yol))
    c.execute("CREATE TABLE treatment_sessions (id INTEGER PRIMARY KEY, patient_name TEXT)")
    c.execute("INSERT INTO treatment_sessions (patient_name) VALUES (?)", (ad,))
    c.commit()
    c.close()
    return yol.read_bytes()


# ─────────────────────────────── Y11 · son N kopya + silinen hastanın izi ───────────────────────────────


def test_KRITIK_Y11_offsite_SON_N_kopya_ve_silinen_hastanin_izi_N_tur_sonra_KALMAZ(
    temp_app_data, nas, monkeypatch, sirlar
):
    db = _duz_db(temp_app_data, monkeypatch)
    try:
        sid = db.start_session(treatment_mode="Manuel", patient_name="Boncuk")
        db.end_session(sid, duration_minutes=5)
        db.start_session(treatment_mode="Manuel", patient_name="Karamel")
        w = _isci(temp_app_data, db, keep=3)
        _tur(monkeypatch, w, 0)
        ilk = _damgali(nas, "treatment_history", ".db")
        assert ilk and "Boncuk" in _adlar(ilk[0]), "ön koşul: ilk off-site yedek Boncuk'u taşımalı"
        db.delete_session(sid)  # hasta kaydı canlı DB'den SİLİNDİ
        for gun in range(1, 6):
            _tur(monkeypatch, w, gun)
        kopyalar = _damgali(nas, "treatment_history", ".db")
        assert len(kopyalar) == 3, (
            f"makine dışı hedefte {len(kopyalar)} tedavi yedeği var, karar N=3 (Y11) — hedef sınırsız büyüyor: "
            f"{[p.name for p in kopyalar]}"
        )
        izli = [p.name for p in kopyalar if "Boncuk" in _adlar(p)]
        assert not izli, f"silinen hastanın adı N tur sonra makine dışı kopyada DURUYOR (KVKK): {izli}"
        assert all("Karamel" in _adlar(p) for p in kopyalar), "rotasyon yeni (sağlam) kopyalara dokundu"
        assert len(_damgali(temp_app_data / "backups", "treatment_history", ".db")) == 3, "yerel rotasyon bozuldu"
    finally:
        db.close()


def test_KRITIK_D251_yedekler_TEK_DOSYA_rollback_gunlugu_kipinde_ag_paylasiminda_WAL_acmaz(
    temp_app_data, nas, monkeypatch, sirlar
):
    db = _duz_db(temp_app_data, monkeypatch)
    try:
        db.start_session(treatment_mode="Manuel", patient_name="Zeytin")
        _tur(monkeypatch, _isci(temp_app_data, db, keep=3), 0)
        dbler = _damgali(nas, "treatment_history", ".db") + _damgali(
            temp_app_data / "backups", "treatment_history", ".db"
        )
        assert len(dbler) == 2
        for p in dbler:
            baslik = p.read_bytes()[:20]
            assert baslik[18:20] == b"\x01\x01", (
                f"{p.name} WAL başlıklı (18-19 = {baslik[18]}/{baslik[19]}): her açılış (rotasyon doğrulaması, geri yükleme) "
                "yedeğin yanına -wal/-shm açar; ağ paylaşımında SQLite WAL desteklenmez"
            )
            assert "Zeytin" in _adlar(p)
    finally:
        db.close()


# ─────────────────────────────── A-45 · yalnız kendi adlı, açılan yedekler silinir ───────────────────────────────


def test_KRITIK_A45_offsite_rotasyonu_YALNIZ_kendi_adli_ACILAN_yedekleri_siler_yabanciya_dokunmaz(
    temp_app_data, nas, monkeypatch, sirlar, caplog
):
    nas.mkdir(parents=True)
    yabanci = {}
    yabanci["pemf_treatment_history_00_elle_alinan.db"] = _gecerli_duz_db(
        nas / "pemf_treatment_history_00_elle_alinan.db", "Elle"
    )
    yabanci["pemf_treatment_history_20200101_000000.db.bak"] = _gecerli_duz_db(
        nas / "pemf_treatment_history_20200101_000000.db.bak", "Bak"
    )
    # Aparatta sır yok → bu turlar kurtarma zarfı ÜRETMEZ; hedefteki (önceki) zarf yalnız rotasyon silerse kaybolur.
    for ad, veri in (
        ("klinik_raporu_2020.pdf", b"%PDF-1.4 kullanici dosyasi"),
        ("pemf_config_20200101_000000.txt", b"pemf degil"),
        ("notlar.json", b'{"kullanici": "dosyasi"}'),
        ("kurtarma-zarfi.enc", b'{"tur": "kurtarma-zarfi", "v": 1, "aparat": "D251"}'),
    ):
        (nas / ad).write_bytes(veri)
        yabanci[ad] = veri
    acilmayan = (
        nas / "pemf_treatment_history_20200102_000000.db"
    )  # önceki bir anahtarla şifreli olabilir: kurtarılabilir veri
    acilmayan.write_bytes(os.urandom(8192))
    acilmayan_veri = acilmayan.read_bytes()
    bos = nas / "pemf_treatment_history_20200103_000000.db"  # başarısız eski kopya artığı: veri taşımaz
    bos.write_bytes(b"")
    alt = nas / "pemf_treatment_history_20200104_000000.db"
    alt.mkdir()
    (alt / "icerik.txt").write_text("kullanici", encoding="utf-8")

    db = _duz_db(temp_app_data, monkeypatch)
    try:
        db.start_session(treatment_mode="Manuel", patient_name="Pamuk")
        w = _isci(temp_app_data, db, keep=2)
        with caplog.at_level(logging.WARNING, logger="services.headless_db_maintenance"):
            for gun in range(4):
                _tur(monkeypatch, w, gun)
    finally:
        db.close()

    for ad, veri in yabanci.items():
        assert (nas / ad).is_file() and (nas / ad).read_bytes() == veri, f"rotasyon YABANCI dosyaya dokundu: {ad}"
    assert acilmayan.is_file() and acilmayan.read_bytes() == acilmayan_veri, (
        "AÇILAMAYAN (önceki anahtar?) yedek SİLİNDİ"
    )
    assert alt.is_dir() and (alt / "icerik.txt").is_file(), "aynı adlı DİZİNE dokunuldu"
    assert not bos.exists(), "0 baytlık eski kopya artığı makine dışı hedefte kaldı (veri taşımaz, yuva tutar)"
    acilan = [p for p in _damgali(nas, "treatment_history", ".db") if p.read_bytes()[:16] == SQLITE_BASLIK]
    assert len(acilan) == 2, f"makine dışı hedefte açılan yedek sayısı N=2 değil: {[p.name for p in acilan]}"
    assert any(
        r.levelno >= logging.WARNING and "ACILAMAYAN" in r.getMessage() and "makine disi" in r.getMessage()
        for r in caplog.records
    ), "açılamayan makine dışı yedek günlükte SÖYLENMEDİ"
    assert (nas / "OKU-KURTARMA.txt").is_file()


# ─────────────────────────────── A-32 · kapsam: hesaplar + ayarlar, SIRSIZ ───────────────────────────────


def _ayarlar_kur(app: Path):
    config = {
        "mqtt": {
            "user": "enc:gAAAAABkullanici",
            "pass": ENC_SIRRI,
            "local_broker": {
                "broker_url": "localhost",
                "broker_port": 1883,
                "username": "pemf",
                "password": PAROLA_SIRRI,
            },
        },
        "api": {"key": UC_SIRRI},
        "application": {"language": "tr", "theme": "koyu"},
        "treatment": {"max_duration": 60},
    }
    (app / "config.json").write_text(json.dumps(config), encoding="utf-8")
    ayar = {"clinic_name": "Klinik D251", "ble_gateway_mac": "AA:BB:CC:DD:EE:FF", "email_password": EPOSTA_SIRRI}
    (app / "system_settings.json").write_text(json.dumps(ayar), encoding="utf-8")
    for ad in SIR_DOSYALARI:
        (app / ad).write_text(f"{SIR_ICERIK}:{ad}", encoding="utf-8")


def test_KRITIK_A32_hesaplar_config_ve_sistem_ayarlari_YEDEKLENIR_SIRSIZ_ve_geri_yuklenir(
    temp_app_data, nas, tmp_path, monkeypatch, sirlar
):
    from database.auth_db import AuthDB

    AuthDB(temp_app_data).enroll_operator(AYSE, "Dr. Ayşe", PIN)
    _ayarlar_kur(temp_app_data)
    db = _duz_db(temp_app_data, monkeypatch)
    try:
        db.start_session(treatment_mode="Manuel", patient_name="Tarcin")
        w = _isci(temp_app_data, db, keep=2)
        for gun in range(3):
            _tur(monkeypatch, w, gun)
    finally:
        db.close()

    yerel = temp_app_data / "backups"
    for dizin in (yerel, nas):
        for tur, ek in (("auth_users", ".db"), ("config", ".json"), ("system_settings", ".json")):
            n = len(_damgali(dizin, tur, ek))
            assert n == 2, f"{dizin.name}: '{tur}' yedeği {n} adet (beklenen N=2 — A-32 kapsamı + Y11/yerel rotasyon)"
        sizan = []
        for p in dizin.rglob("*"):
            if p.is_file():
                veri = p.read_bytes()
                sizan += [
                    (p.name, s)
                    for s in (PAROLA_SIRRI, ENC_SIRRI, UC_SIRRI, EPOSTA_SIRRI, SIR_ICERIK)
                    if s.encode() in veri
                ]
        assert not sizan, f"SIR yedeğe girdi ({dizin.name}): {sizan}"
        assert not [p.name for p in dizin.iterdir() if p.name in SIR_DOSYALARI], "SIR dosyası yedek dizinine kopyalandı"

    cfg = json.loads(_damgali(nas, "config", ".json")[-1].read_text(encoding="utf-8"))
    assert cfg["application"] == {"language": "tr", "theme": "koyu"} and cfg["treatment"]["max_duration"] == 60
    assert cfg["mqtt"]["local_broker"]["broker_url"] == "localhost", "sır olmayan ayar da ayıklandı"
    ayar = json.loads(_damgali(nas, "system_settings", ".json")[-1].read_text(encoding="utf-8"))
    assert ayar["clinic_name"] == "Klinik D251" and ayar["ble_gateway_mac"] == "AA:BB:CC:DD:EE:FF"

    yeni = tmp_path / "yeni_makine" / "PEMF_GUI"
    yeni.mkdir(parents=True)
    shutil.copy2(_damgali(nas, "auth_users", ".db")[-1], yeni / "auth_users.db")
    assert AuthDB(yeni).verify_pin(AYSE, PIN)[0] is True, "makine dışı hesap yedeğinden operatör geri yüklenemedi"


def test_KRITIK_A32_sifreli_kurulumda_hesap_yedegi_SIFRELI_ve_kurtarma_araciyla_GERI_YUKLENIR(
    temp_app_data, nas, tmp_path, monkeypatch, sirlar
):
    from database.auth_db import AuthDB

    from tools import kurtarma

    AuthDB(temp_app_data).enroll_operator(AYSE, "Dr. Ayşe", PIN)
    db = _sifreli_db(temp_app_data, sirlar)
    try:
        db.start_session(treatment_mode="Manuel", patient_name="Findik")
        _tur(monkeypatch, _isci(temp_app_data, db, keep=14), 0)
    finally:
        db.close()

    yedek = _damgali(nas, "auth_users", ".db")
    assert len(yedek) == 1, f"hesap DB'si makine dışına yedeklenmedi: {sorted(p.name for p in nas.iterdir())}"
    veri = yedek[0].read_bytes()
    assert not veri.startswith(SQLITE_BASLIK) and AYSE.encode() not in veri, (
        "şifreli kurulumda hesap yedeği makine dışına DÜZ gitti — e-posta + 6 haneli PIN özeti çevrimdışı kaba kuvvete açık"
    )

    yeni = tmp_path / "yeni_makine" / "PEMF_GUI"
    yeni.mkdir(parents=True)
    cikti = yeni / "auth_users.db"
    assert kurtarma.main(["--hesap-yedegi", str(yedek[0]), "--cikti", str(cikti)]) == 0
    assert AuthDB(yeni).verify_pin(AYSE, PIN)[0] is True, (
        "kurtarma aracıyla çözülen hesap yedeğinden operatör doğrulanamadı"
    )

    # Karşıt: var olan çıktının ÜZERİNE YAZILMAZ; anahtar yoksa çıktı hiç oluşmaz.
    once = cikti.read_bytes()
    assert kurtarma.main(["--hesap-yedegi", str(yedek[0]), "--cikti", str(cikti)]) != 0
    assert cikti.read_bytes() == once
    sirlar.clear()
    bos_cikti = yeni / "auth_users_ikinci.db"
    assert kurtarma.main(["--hesap-yedegi", str(yedek[0]), "--cikti", str(bos_cikti)]) != 0
    assert not bos_cikti.exists()
