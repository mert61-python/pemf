# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""VERİ KÖKÜ: KULLANICI-BAŞINA → MAKİNE-GENELİ GÖÇ (2026-08-09 denetimi, Tier 1).

ARIZA: launcher `PEMF_DATA_DIR` VERMİYORDU → backend `%APPDATA%\\PEMF_GUI`e düşüyor, yani
hasta/seans/AI verisi WINDOWS KULLANICISINA ÖZEL oluyordu. Vardiyalı bir klinikte ikinci
hesapla açan veteriner "BOŞ KLİNİK" görüyor: hasta listesi yok, geçmiş yok, AI kaydı yok.
Kullanıcı açısından bu VERİ KAYBINDAN ayırt edilemez.

Launcher artık makine-geneli kök veriyor (bkz. install.rs::cozulmus_veri_dizini). Bu dosya,
mevcut kliniklerin eski verisinin O GEÇİŞTE kaybolmadığını kilitler.

⚠️ TIBBİ VERİ KURALLARI (geri dönüşü yok):
  * hedefte aynı adlı dosya VARSA DOKUNULMAZ — üzerine yazmak yeni kliniğin kaydını siler,
  * KOPYALANIR, kaynak SİLİNMEZ,
  * göç başarısız olursa backend yine de açılır (göç bir kolaylıktır, kapı değil).
"""

import platform

import pytest

pytestmark = pytest.mark.skipif(platform.system() != "Windows", reason="göç yalnız Windows'ta anlamlı (APPDATA)")


def _duz_db(icerik: bytes) -> bytes:
    """DÜZ-METİN SQLite başlığı + içerik.

    ⚠️ 2026-08-11: göç artık YALNIZ düz-metin SQLite dosyalarını taşır. Şifreli (SQLCipher) bir
    DB'yi taşımak, onu açan anahtar `pemf_secrets.json`da kaldığı (ve o dosya cihaz kimliği
    taşıdığı için göçmediği) için hedefte KALICI OKUNAMAZ bir dosya bırakır ve cihazı sonsuz
    açılış-hatası döngüsüne sokar. Bu testler bu yüzden GERÇEK başlıkla çalışır; rastgele
    baytlar sahada hiç oluşmaz."""
    return b"SQLite format 3\x00" + icerik


def _goc(monkeypatch, eski_kok, hedef):
    from utils.path_utils import _kullanicidan_makineye_gocur

    monkeypatch.setenv("APPDATA", str(eski_kok))
    _kullanicidan_makineye_gocur(hedef)


@pytest.fixture
def ortam(tmp_path):
    eski_kok = tmp_path / "kullanici"
    eski = eski_kok / "PEMF_GUI"
    eski.mkdir(parents=True)
    hedef = tmp_path / "makine" / "PEMF_GUI"
    hedef.mkdir(parents=True)
    return eski_kok, eski, hedef


def test_KRITIK_eski_tibbi_kayit_TASINIR(ortam, monkeypatch):
    eski_kok, eski, hedef = ortam
    (eski / "pemf_treatment_history.db").write_bytes(_duz_db(b"SEANS-GECMISI"))
    (eski / "pemf_patients.db").write_bytes(_duz_db(b"HASTALAR"))

    _goc(monkeypatch, eski_kok, hedef)

    assert (hedef / "pemf_treatment_history.db").read_bytes() == _duz_db(b"SEANS-GECMISI"), (
        "seans gecmisi tasinmadi — klinik BOS gorunurdu"
    )
    assert (hedef / "pemf_patients.db").read_bytes() == _duz_db(b"HASTALAR")


def test_KRITIK_kaynak_SILINMEZ(ortam, monkeypatch):
    """Kopya bozulursa eski dosya hâlâ yerinde durmalı — tıbbi veride tek kopya kabul edilemez."""
    eski_kok, eski, hedef = ortam
    (eski / "pemf_treatment_history.db").write_bytes(_duz_db(b"X"))
    _goc(monkeypatch, eski_kok, hedef)
    assert (eski / "pemf_treatment_history.db").exists(), "kaynak silindi — geri donus yok"


def test_KRITIK_hedefteki_kayit_EZILMEZ(ortam, monkeypatch):
    """En tehlikeli senaryo: makine-geneli kökte ZATEN kayıt var (yeni klinik çalışıyor).
    Eski kullanıcı klasöründen kopyalamak, çalışan kliniğin geçmişini SİLERDİ."""
    eski_kok, eski, hedef = ortam
    (eski / "pemf_treatment_history.db").write_bytes(_duz_db(b"ESKI"))
    (hedef / "pemf_treatment_history.db").write_bytes(_duz_db(b"CALISAN-KLINIK"))

    _goc(monkeypatch, eski_kok, hedef)

    assert (hedef / "pemf_treatment_history.db").read_bytes() == _duz_db(b"CALISAN-KLINIK"), (
        "calisan klinigin gecmisi UZERINE YAZILDI"
    )


def test_cihaz_kimligi_TASINMAZ(ortam, monkeypatch):
    """`device_id.txt` makineye özgüdür; kopyalanırsa iki kurulum aynı kimliği paylaşır ve
    uzaktan eşleştirme/bulut kaydı karışır."""
    eski_kok, eski, hedef = ortam
    (eski / "device_id.txt").write_text("PEMF-ESKI")
    _goc(monkeypatch, eski_kok, hedef)
    assert not (hedef / "device_id.txt").exists(), "cihaz kimligi kopyalandi"


def test_eski_klasor_yoksa_sessizce_gecer(tmp_path, monkeypatch):
    hedef = tmp_path / "makine" / "PEMF_GUI"
    hedef.mkdir(parents=True)
    _goc(monkeypatch, tmp_path / "olmayan", hedef)  # hata atmamalı
    assert list(hedef.iterdir()) == []


def test_ayni_dizin_ise_hicbir_sey_yapmaz(tmp_path, monkeypatch):
    """`PEMF_DATA_DIR` zaten APPDATA'yı gösteriyorsa kendi üstüne kopyalama denenmemeli."""
    kok = tmp_path / "ayni"
    d = kok / "PEMF_GUI"
    d.mkdir(parents=True)
    (d / "pemf_patients.db").write_bytes(_duz_db(b"A"))
    _goc(monkeypatch, kok, d)
    assert (d / "pemf_patients.db").read_bytes() == _duz_db(b"A")


def test_KRITIK_goc_hatasi_BACKENDI_DUSURMEZ(ortam, monkeypatch):
    """Göç bir kolaylıktır. Patlarsa backend açılmaya devam etmeli — aksi hâlde tek bir dosya
    izni yüzünden klinik hiç çalışmazdı."""
    import shutil

    eski_kok, eski, hedef = ortam
    (eski / "pemf_patients.db").write_bytes(_duz_db(b"X"))
    monkeypatch.setattr(shutil, "copy2", lambda *a, **k: (_ for _ in ()).throw(OSError("izin yok")))
    _goc(monkeypatch, eski_kok, hedef)  # istisna SIZMAMALI


def test_get_app_data_directory_override_ile_goc_TETIKLER(tmp_path, monkeypatch):
    """Uçtan uca: `PEMF_DATA_DIR` verildiğinde göç gerçekten çalışıyor mu."""
    from utils.path_utils import get_app_data_directory

    eski_kok = tmp_path / "kullanici"
    (eski_kok / "PEMF_GUI").mkdir(parents=True)
    (eski_kok / "PEMF_GUI" / "pemf_patients.db").write_bytes(_duz_db(b"HASTALAR"))
    monkeypatch.setenv("APPDATA", str(eski_kok))
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path / "makine"))

    d = get_app_data_directory()
    assert d == tmp_path / "makine" / "PEMF_GUI"
    assert (d / "pemf_patients.db").read_bytes() == _duz_db(b"HASTALAR")
