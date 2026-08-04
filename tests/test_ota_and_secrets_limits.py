"""MUTASYON TESTİ BULGUSU — üç düzeltme uygulanmıştı ama HİÇBİR test onları korumuyordu:
sınırları etkisizleştiren mutasyonlar tüm takımdan geçti.

  1) OTA installer indirme boyut tavanı (`_MAX_INSTALLER_BYTES`)
  2) OTA manifest boyut tavanı (`_MAX_MANIFEST_BYTES`)
  3) `pemf_secrets.json` yazıldıktan sonra NTFS ACL kilidi

Neden önemli: (1)+(2) ele geçirilmiş/hatalı bir güncelleme kaynağının diski doldurup cihazı
(canlı hayvan üzerinde tedavi eden bir tıbbi cihazı) hizmet dışı bırakmasını engeller; (3)
TÜM sırları — SQLCipher anahtarı dahil — taşıyan dosyanın yerel `Users`'a okunur kalmasını
engeller (`os.chmod` Windows'ta no-op'tur, tek koruma budur).
"""

import io
import os
import sys

import pytest


# ────────────────────────── OTA boyut tavanları ──────────────────────────

class _SonsuzYanit:
    """Hiç bitmeyen bir HTTP gövdesi (kötü niyetli/bozuk sunucu)."""

    def __init__(self, chunk=b"A" * (1 << 20)):
        self._chunk = chunk
        self.okunan = 0

    def read(self, n=-1):
        self.okunan += len(self._chunk)
        if self.okunan > 4 * 1024 * 1024 * 1024:      # test güvenlik supabı: 4 GB
            raise AssertionError("sınır hiç uygulanmadı — 4 GB okundu")
        return self._chunk


def test_installer_indirme_boyut_tavani_UYGULANIR():
    """Tavan aşılınca indirme İPTAL edilmeli; aksi halde disk dolana kadar yazılır."""
    from servers import update_manager as um

    hedef = io.BytesIO()
    with pytest.raises(ValueError, match="boyut siniri asildi"):
        um._download_to(_SonsuzYanit(), hedef, 3 * 1024 * 1024, "Installer")
    # Tavanı bir miktar aşınca durmalı — GB'larca yazmamalı
    assert hedef.tell() <= 4 * 1024 * 1024, "tavan aşıldıktan sonra yazmaya devam etti"


def test_installer_tavani_GERCEK_degeriyle_makul():
    """Tavan tanımlı ve makul olmalı — devasa bir değer korumayı etkisizleştirir."""
    from servers import update_manager as um

    assert 16 * 1024 * 1024 <= um._MAX_INSTALLER_BYTES <= 2 * 1024 * 1024 * 1024, (
        f"_MAX_INSTALLER_BYTES makul aralıkta değil: {um._MAX_INSTALLER_BYTES}")
    assert 4 * 1024 <= um._MAX_MANIFEST_BYTES <= 16 * 1024 * 1024, (
        f"_MAX_MANIFEST_BYTES makul aralıkta değil: {um._MAX_MANIFEST_BYTES}")


def test_sinir_altindaki_indirme_SORUNSUZ_tamamlanir():
    """Koruma meşru güncellemeyi engellememeli (fail-closed ≠ hep-reddet)."""
    from servers import update_manager as um

    class _Sonlu:
        def __init__(self):
            self.kalan = 3

        def read(self, n=-1):
            if self.kalan <= 0:
                return b""
            self.kalan -= 1
            return b"B" * 1024

    hedef = io.BytesIO()
    n = um._download_to(_Sonlu(), hedef, 1 * 1024 * 1024, "Installer")
    assert n == 3 * 1024 and hedef.getvalue() == b"B" * 3072


def test_manifest_boyut_tavani_UYGULANIR(monkeypatch):
    """DENETİM 2026-08-04'te `_MAX_MANIFEST_BYTES` TANIMLI ama HİÇ UYGULANMIYORDU.
    Uygulama geri gitmesin diye kaynak sözleşmesi kilitlenir: okuma tavan+1 ile
    sınırlanmalı ve aşımda reddedilmeli."""
    import ast
    import inspect

    from servers import update_manager as um

    src = inspect.getsource(um)
    assert "_MAX_MANIFEST_BYTES + 1" in src, (
        "manifest okuması tavanla sınırlanmıyor → tüm gövde belleğe alınır")
    assert "len(raw) > _MAX_MANIFEST_BYTES" in src, (
        "manifest boyut kontrolü YOK → tavan tanımlı ama etkisiz (2026-08-04 hatasının aynısı)")
    # Sabitler gerçekten bu adla ve modül seviyesinde mi (yeniden adlandırma sessizce
    # korumayı düşürmesin)
    tree = ast.parse(src)
    isimler = {t.id for n in ast.walk(tree) if isinstance(n, ast.Assign)
               for t in n.targets if isinstance(t, ast.Name)}
    assert {"_MAX_INSTALLER_BYTES", "_MAX_MANIFEST_BYTES"} <= isimler


# ────────────────────────── Sır dosyası ACL kilidi ──────────────────────────

@pytest.mark.skipif(os.name != "nt", reason="NTFS ACL yalnız Windows")
def test_sirlar_dosyasi_yazildiktan_sonra_ACL_KILITLENIR(tmp_path, monkeypatch):
    """`pemf_secrets.json` TÜM sırları taşır (SQLCipher anahtarı dahil). Windows'ta
    `os.chmod` no-op olduğundan tek koruma `lock_down_file`'dır — çağrı düşerse dosya
    yerel `Users`'a okunur kalır ve kimse fark etmez."""
    from utils import secrets_manager as sm

    veri = tmp_path / "PEMF_GUI"
    veri.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sm, "_data_dir", lambda: veri)
    monkeypatch.setattr(sm, "_cache", None, raising=False)

    cagrilar = []
    import utils.file_acl as fa
    gercek = fa.lock_down_file

    def _izle(p, **kw):
        cagrilar.append((str(p), kw))
        return gercek(p, **kw)

    monkeypatch.setattr(fa, "lock_down_file", _izle)

    sm._save({"version": 1, "auto": {"deneme": "x"}, "operator": {}, "embedded": {}})

    yol = veri / "pemf_secrets.json"
    assert yol.exists(), "sır dosyası yazılmadı"
    assert cagrilar, "sır dosyası yazıldı ama ACL KİLİTLENMEDİ → Users'a okunur kalır"
    kilitlenen = os.path.normcase(cagrilar[-1][0])
    assert kilitlenen == os.path.normcase(str(yol)), (
        f"ACL yanlış yola uygulandı: {kilitlenen}")
    assert cagrilar[-1][1].get("keep_current_user") is True, (
        "keep_current_user=False → süreç kendi sır dosyasını AÇAMAZ hale gelir "
        "(daha önce gerçek makinede yaşandı: backend başlamıyordu)")


@pytest.mark.skipif(os.name != "nt", reason="NTFS ACL yalnız Windows")
def test_sirlar_dosyasi_Users_a_ACIK_DEGIL(tmp_path, monkeypatch):
    """Uçtan uca: gerçek icacls çıktısında yerel `Users` ACE'si kalmamalı."""
    import subprocess

    from utils import secrets_manager as sm

    veri = tmp_path / "PEMF_GUI"
    veri.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sm, "_data_dir", lambda: veri)
    monkeypatch.setattr(sm, "_cache", None, raising=False)

    sm._save({"version": 1, "auto": {"k": "v"}, "operator": {}, "embedded": {}})
    yol = veri / "pemf_secrets.json"

    out = subprocess.run(["icacls", str(yol)], capture_output=True, text=True).stdout
    if "BUILTIN" not in out and "NT AUTHORITY" not in out and "S-1-5" not in out:
        pytest.skip(f"icacls beklenen biçimde çıktı vermedi: {out[:200]}")
    dusuk = out.lower()
    # S-1-5-32-545 = BUILTIN\Users. Yerelleştirmeden bağımsız olması için SID de kabul edilir.
    assert "s-1-5-32-545" not in dusuk and "\\users:" not in dusuk and "\\kullanıcılar:" not in dusuk, (
        f"sır dosyasında yerel Users ACE'si DURUYOR → tüm sırlar okunabilir:\n{out}")
