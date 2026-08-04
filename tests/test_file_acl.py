"""NTFS ACL kilidi — sır dosyası/dizini GERÇEKTEN Users'a kapanıyor mu?

Denetim 2026-08-04: `lock_down_file` docstring'i "Yerel `Users` grubu her iki modda da ERİŞEMEZ;
korunan şey budur" diyordu ama garanti ETMİYORDU: `icacls /inheritance:r` YALNIZCA MİRAS ALINAN
ACE'leri kaldırır. Hedefte AÇIK (explicit) bir `Users` ACE'i varsa olduğu gibi kalır ve
`/grant:r` de yalnız adı geçen SID'leri değiştirir → dosya "kilitlendi" sanılırken Users
erişmeye DEVAM eder. Bu davranış testiyle yakalandı; `/remove:g` ile kapatıldı.

Ayrıca `lock_down_dir` (yeni): sır DİZİNİ kilitlenince içinde OLUŞAN dosyalar (özellikle
`pemf_secrets.json.<pid>.tmp` — TÜM düz-metin sırları taşır) kısıtlı ACL'i MİRAS almalı.
`_save()` ACL'i bilerek `os.replace`'ten SONRA uyguladığı için (sıra zorunlu, bkz. secrets_manager)
tmp penceresini kapatmanın TEK yolu dizini kilitlemektir.

Gerçek ACL'lerle çalışır → yalnız Windows.
"""
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="NTFS ACL testi yalnız Windows")

_USERS_SID = "*S-1-5-32-545"


def _icacls(path) -> str:
    return subprocess.run(["icacls", str(path)], capture_output=True, text=True).stdout


def _users_can_access(path) -> bool:
    """Çıktıda Users / Authenticated Users için bir ACE var mı? (TR Windows: 'Kullanıcılar')"""
    low = _icacls(path).lower()
    return ("users:" in low) or ("kullan" in low) or ("authenticated" in low)


def _grant_users(path, perms: str) -> None:
    subprocess.run(["icacls", str(path), "/grant", f"{_USERS_SID}:{perms}"], capture_output=True)


def _reset(path) -> None:
    subprocess.run(["icacls", str(path), "/reset", "/t", "/q"], capture_output=True)


def test_lock_down_file_acik_users_acesini_de_kaldirir(tmp_path):
    """AÇIK Users ACE'i `/inheritance:r` ile GİTMEZ — dosya kilitli sanılıp açık kalıyordu."""
    from utils.file_acl import lock_down_file

    f = tmp_path / "pemf_secrets.json"
    f.write_text("SIR", encoding="utf-8")
    _grant_users(f, "M")
    assert _users_can_access(f), "on-kosul: Users erisebiliyor olmali"

    assert lock_down_file(f, keep_current_user=True) is True
    assert not _users_can_access(f), (
        "ACIK Users ACE'i hayatta kaldi — sir dosyasi 'kilitli' sanilirken Users okuyabilir"
    )
    _reset(tmp_path)


def test_lock_down_dir_icinde_olusan_tmp_kisitli_acl_miras_alir(tmp_path):
    """`_save()` .tmp'yi ACL'siz yazar (sıra zorunlu) → dizin kilitli DEĞİLSE düz-metin sırlar
    kısa süre Users-okunur kalır. Dizin kilidi bu pencereyi kapatmalı."""
    from utils.file_acl import lock_down_dir

    d = tmp_path / "PEMF_GUI"
    d.mkdir()
    _grant_users(d, "(OI)(CI)M")  # ProgramData mirasını taklit et
    before = d / "pemf_secrets.json.111.tmp"
    before.write_text("TUM SIRLAR", encoding="utf-8")
    assert _users_can_access(before), "on-kosul: yeni dosya Users'a acik olmali"

    assert lock_down_dir(d, keep_current_user=True) is True

    after = d / "pemf_secrets.json.222.tmp"
    after.write_text("TUM SIRLAR", encoding="utf-8")
    assert not _users_can_access(after), (
        "dizin kilitlendikten SONRA olusan .tmp hala Users'a acik — duz-metin sir penceresi kapanmadi"
    )
    _reset(tmp_path)


def test_lock_down_dir_var_olmayan_yolda_false_doner(tmp_path):
    from utils.file_acl import lock_down_dir

    assert lock_down_dir(tmp_path / "yok") is False
