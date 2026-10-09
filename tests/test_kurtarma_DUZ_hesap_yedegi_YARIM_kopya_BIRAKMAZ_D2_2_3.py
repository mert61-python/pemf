# -*- coding: utf-8 -*-
"""D2-2.3 (2-D incelemesi A2) — `tools/kurtarma.py --hesap-yedegi` DÜZ yedek dalı çıktıya YARIM `auth_users.db` bırakmaz.

ÖLÇÜLEN KUSUR: şifresiz hesap yedeği `shutil.copy2(yedek, cikti)` ile DOĞRUDAN çıktıya (veri dizinindeki `auth_users.db`) kopyalanıyor.
Disk dolunca (gerçek biçim: hedefe bir kısmı yazılır, sonra ENOSPC) [ÖLÇTÜM sonda k2_kurtarma]:
  * `OSError` araçtan YAKALANMADAN kaçıyor (HATA iletisi yok, dönüş kodu yok — iz yığını),
  * çıktıda 12288 / 24576 baytlık YARIM `auth_users.db` kalıyor,
  * disk düzelip aynı komut yeniden çalıştırılınca rc 3 "çıktı zaten var — mevcut hesapların ÜSTÜNE YAZILMAZ": araç bozuk yarım
    dosyayı "mevcut hesaplar" diye KORUYOR,
  * backend o dosyayı açınca `AuthDB` → "database disk image is malformed" (kimlik DB'si okunamaz → kimlik kapıları kapalı, Y113).
Şifreli dal (`sifreli_yedegi_duze_coz`) zaten geçici ad → doğrulama → `os.replace` yapıyor; düz dal aynı sözleşmeye bağlanır.

ARIZA EN ALT KATTA: `shutil._copyfileobj_readinto` (Windows'ta copy2'nin bayt kopyalayan işlevi) hedefe yarısını yazar, sonra OSError(28).
"""

from __future__ import annotations

import logging
import shutil

import pytest

EPOSTA, PIN = "dr.d223@klinik.invalid", "112233"


@pytest.fixture
def duz_yedek(tmp_path, monkeypatch):
    from database.auth_db import AuthDB
    from database.yedek_dosyasi import duz_dbyi_yedekle
    from utils import file_acl

    monkeypatch.setattr(file_acl, "lock_down_file", lambda *a, **k: False)
    eski = tmp_path / "eski_makine"
    eski.mkdir()
    AuthDB(eski).enroll_operator(EPOSTA, "Dr. D223", PIN)
    yedek = tmp_path / "NAS" / "pemf_auth_users_20261009_020202.db"
    yedek.parent.mkdir()
    duz_dbyi_yedekle(str(eski / "auth_users.db"), str(yedek), None, "", logging.getLogger("d223"))
    assert yedek.read_bytes()[:16] == b"SQLite format 3\x00", "aparat: düz (şifresiz kurulum) hesap yedeği bekleniyordu"
    return yedek


def _kos(yedek, cikti):
    from tools import kurtarma

    try:
        return kurtarma.main(["--hesap-yedegi", str(yedek), "--cikti", str(cikti)])
    except OSError as e:
        return f"YAKALANMAYAN {type(e).__name__} errno={e.errno}"


def test_KRITIK_D2_2_3_duz_hesap_yedegi_kopyasi_disk_DOLUNCA_yarim_auth_users_db_KALMAZ_ve_yeniden_deneme_CALISIR(
    duz_yedek, tmp_path, monkeypatch
):
    from database.auth_db import AuthDB

    veri = tmp_path / "yeni_makine" / "PEMF_GUI"
    veri.mkdir(parents=True)
    cikti = veri / "auth_users.db"
    gercek = shutil._copyfileobj_readinto

    def _dolu(fsrc, fdst, length=0):
        v = fsrc.read()
        fdst.write(v[: len(v) // 2])
        fdst.flush()
        raise OSError(28, "No space left on device (aparat)")

    monkeypatch.setattr(shutil, "_copyfileobj_readinto", _dolu)
    rc = _kos(duz_yedek, cikti)
    assert isinstance(rc, int) and rc != 0, f"disk dolunca araç dönüş kodu + HATA iletisi vermedi: {rc}"
    assert not cikti.exists(), (
        f"disk dolunca çıktıda YARIM auth_users.db kaldı ({cikti.stat().st_size} bayt) — backend onu 'malformed' açar"
    )
    assert [p.name for p in veri.iterdir()] == [], f"geçici artık kaldı: {[p.name for p in veri.iterdir()]}"

    monkeypatch.setattr(shutil, "_copyfileobj_readinto", gercek)
    assert _kos(duz_yedek, cikti) == 0, "disk düzeldikten sonra aynı komut hesapları geri yükleyemedi"
    assert AuthDB(veri).verify_pin(EPOSTA, PIN)[0] is True


def test_KARSIT_D2_2_3_duz_dal_saglam_diskte_bugunku_gibi_kopyalar_ve_var_olan_ciktiya_DOKUNMAZ(duz_yedek, tmp_path):
    from database.auth_db import AuthDB

    veri = tmp_path / "y" / "PEMF_GUI"
    veri.mkdir(parents=True)
    cikti = veri / "auth_users.db"
    assert _kos(duz_yedek, cikti) == 0
    assert AuthDB(veri).verify_pin(EPOSTA, PIN)[0] is True
    once = cikti.read_bytes()
    assert _kos(duz_yedek, cikti) == 3
    assert cikti.read_bytes() == once
