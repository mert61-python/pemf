# -*- coding: utf-8 -*-
"""E2-1.1 (2-E incelemesi, A1) — `file_acl._surec_sid` GEÇİCİ bir belirteç hatasını (None) `lru_cache` ile SÜREÇ ÖMRÜ BOYUNCA saklar.

D2.79 sürecin SID'ini belirteçten okur; okunamazsa `keep_current_user=True` kilidi UYGULANMAZ (False + uyarı). `_surec_sid`
`@functools.lru_cache(maxsize=1)` ile sarılı → None DE önbelleğe girer: tek bir geçici hata (OpenProcessToken FALSE,
ERROR_NO_SYSTEM_RESOURCES 1450) sonrasında hata kalksa bile o süreçteki HER sır dizini / sır dosyası / auth_users.db /
config.json kilidi atlanır. `secrets_manager._ensure_dir_hardened`in 60 sn geri çekilmesi "yeniden denenecek" der ama önbellekteki
None yüzünden yeniden deneme boşa döner (yalnız yeniden başlatma düzeltir).

Arıza EN ALT katta: `ctypes.WinDLL("advapi32").OpenProcessToken` bir kez FALSE döner (SetLastError 1450); sonra gerçek API.
Kilit GERÇEK `icacls` ile, kendi `tmp_path`te; `finally` `icacls /reset` + önbellek temizliği (sonraki testleri zehirlemesin).
"""

from __future__ import annotations

import ctypes
import os
import subprocess

import pytest

pytestmark = pytest.mark.skipif(os.name != "nt", reason="NTFS ACL / Win32 belirteç yalnız Windows")


def _sifirla(p) -> None:
    subprocess.run(["icacls", str(p), "/reset", "/T", "/C"], capture_output=True, timeout=60)


class _SahteOpenProcessToken:
    argtypes = None
    restype = None

    def __call__(self, *a):
        ctypes.set_last_error(1450)  # ERROR_NO_SYSTEM_RESOURCES — geçici kaynak tükenmesi
        return 0


class _Advapi32Vekili:
    """Gerçek advapi32'yi sarar; `OpenProcessToken` YALNIZ `kalan` kez başarısız döner."""

    def __init__(self, gercek, kalan):
        object.__setattr__(self, "_g", gercek)
        object.__setattr__(self, "_k", kalan)

    def __getattr__(self, ad):
        kalan = object.__getattribute__(self, "_k")
        if ad == "OpenProcessToken" and kalan["n"] > 0:
            kalan["n"] -= 1
            return _SahteOpenProcessToken()
        return getattr(object.__getattribute__(self, "_g"), ad)


def test_KRITIK_gecici_belirtec_hatasi_kilidi_SUREC_OMRU_boyunca_DUSURMEZ_E2_1_1(tmp_path, monkeypatch):
    from utils import file_acl as fa

    temizle = getattr(fa._surec_sid, "cache_clear", None)
    assert temizle is not None, "aparat: _surec_sid önbelleği temizlenemiyor (cache_clear yok)"
    temizle()
    gercek_windll = ctypes.WinDLL
    kalan = {"n": 1}

    def _windll(ad, *a, **k):
        g = gercek_windll(ad, *a, **k)
        return _Advapi32Vekili(g, kalan) if str(ad).lower().startswith("advapi32") else g

    f = tmp_path / "pemf_secrets.json"
    f.write_text("{}", encoding="utf-8")
    try:
        monkeypatch.setattr(ctypes, "WinDLL", _windll)
        assert fa._surec_sid() is None, "aparat: geçici belirteç hatası uygulanmadı"
        assert kalan["n"] == 0, "aparat: sahte OpenProcessToken çağrılmadı"
        monkeypatch.setattr(ctypes, "WinDLL", gercek_windll)  # hata KALKTI

        sid = fa._surec_sid()
        assert sid and sid.startswith("S-1-5-"), (
            f"geçici belirteç hatası KALICI oldu: hata kalktıktan sonra _surec_sid() = {sid!r} (None önbellekte) — bu süreçteki "
            "her keep_current_user kilidi (sır dizini, pemf_secrets.json, auth_users.db, config.json) yeniden başlatmaya kadar atlanır"
        )
        assert fa.lock_down_file(f, keep_current_user=True) is True, (
            "hata kalktıktan sonra da sır dosyası kilidi UYGULANMADI (önbellekteki None)"
        )
    finally:
        monkeypatch.setattr(ctypes, "WinDLL", gercek_windll)
        _sifirla(f)
        temizle()
    assert f.read_text(encoding="utf-8") == "{}", "aparat: erişim geri gelmedi"


def test_KARSIT_basarili_SID_onbellekte_kalir_ikinci_cagri_belirteci_ACMAZ_E2_1_1(monkeypatch):
    """Karşıt: başarıyla okunan SID önbellekte kalır (belirteç süreç boyunca değişmez) — ikinci çağrı API'ye inmez."""
    from utils import file_acl as fa

    fa._surec_sid.cache_clear()
    ilk = fa._surec_sid()
    assert ilk and ilk.startswith("S-1-5-")
    cagri = {"n": 0}
    gercek_windll = ctypes.WinDLL

    def _sayan(ad, *a, **k):
        cagri["n"] += 1
        return gercek_windll(ad, *a, **k)

    monkeypatch.setattr(ctypes, "WinDLL", _sayan)
    try:
        assert fa._surec_sid() == ilk
        assert cagri["n"] == 0, "başarılı SID önbelleğe alınmıyor (her kilitte belirteç yeniden açılıyor)"
    finally:
        monkeypatch.setattr(ctypes, "WinDLL", gercek_windll)
