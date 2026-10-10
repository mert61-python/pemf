# -*- coding: utf-8 -*-
"""E2-1.3 (2-E incelemesi, A1) — `file_acl.lock_down_file` / `lock_down_dir` hedefte AÇIK (miras DEĞİL) duran Everyone (S-1-1-0) /
Interactive (S-1-5-4) grant'ını KALDIRMAZ; kilit "uygulandı" (True) der, sır dosyası makinedeki herkese açık kalır.

`/inheritance:r` yalnız MİRAS alınan ACE'leri kaldırır, `/grant:r` yalnız adı geçen SID'lerin ACE'ini değiştirir. 2026-08-04 düzeltmesi
bu yüzden Users (S-1-5-32-545) ve Authenticated Users (S-1-5-11) için AÇIK `/remove:g` ekledi — ama Everyone ve Interactive için
eklemedi. Ürünün kendi ileti(ler)i operatöre "dosyaların izinlerini düzelttirin / elle kısıtlayın" der; bir yöneticinin bunun için
"Everyone: Tam denetim" vermesi (ya da bir kopyalama aracının açık ACE taşıması) sonrası her açılıştaki kilit bunu SİLMEZ.
`pemf_secrets.json` DPAPI LOCAL_MACHINE ile korunduğu için dosyayı okuyabilen her yerel hesap hasta DB anahtarını çözebilir.

Arıza en alt katta, GERÇEK biçimiyle: gerçek `icacls /grant *S-1-1-0:(R)` (açık ACE), gerçek `lock_down_*`, DACL SDDL'den SID düzeyinde
okunur (Türkçe Windows'ta grup ADLARI değişir). Kendi `tmp_path`'imde; `finally` `icacls /reset /T /C`.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
from ctypes import wintypes

import pytest

pytestmark = pytest.mark.skipif(os.name != "nt", reason="NTFS ACL yalnız Windows")

_adv = ctypes.WinDLL("advapi32", use_last_error=True)
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_adv.GetNamedSecurityInfoW.argtypes = [
    wintypes.LPCWSTR,
    ctypes.c_int,
    wintypes.DWORD,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_void_p),
]
_adv.GetNamedSecurityInfoW.restype = wintypes.DWORD
_adv.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.LPWSTR),
    ctypes.c_void_p,
]
_k32.LocalFree.argtypes = [ctypes.c_void_p]
_KISA = {
    "SY": "S-1-5-18",
    "BA": "S-1-5-32-544",
    "BU": "S-1-5-32-545",
    "AU": "S-1-5-11",
    "WD": "S-1-1-0",
    "IU": "S-1-5-4",
}


def _izin_veren_sidler(p) -> set:
    psd = ctypes.c_void_p()
    rc = _adv.GetNamedSecurityInfoW(str(p), 1, 4, None, None, None, None, ctypes.byref(psd))  # SE_FILE_OBJECT, DACL
    assert rc == 0, f"aparat: GetNamedSecurityInfo rc={rc}"
    s = wintypes.LPWSTR()
    _adv.ConvertSecurityDescriptorToStringSecurityDescriptorW(psd, 1, 4, ctypes.byref(s), None)
    sddl = s.value
    _k32.LocalFree(s)
    _k32.LocalFree(psd)
    out = set()
    for ace in sddl.split("D:", 1)[1].split("(")[1:]:
        al = ace.rstrip(")").split(";")
        if len(al) >= 6 and al[0] == "A":
            out.add(_KISA.get(al[5], al[5]))
    return out


def _icacls(*a):
    return subprocess.run(["icacls", *map(str, a)], capture_output=True, timeout=60)


def _kur(tmp_path, tur, sid):
    if tur == "dosya":
        hedef = tmp_path / "pemf_secrets.json"
        hedef.write_text('{"auto": {}}', encoding="utf-8")
        r = _icacls(hedef, "/grant", f"*{sid}:(F)")
    else:
        hedef = tmp_path / "PEMF_GUI"
        hedef.mkdir()
        r = _icacls(hedef, "/grant", f"*{sid}:(OI)(CI)(F)")
    assert r.returncode == 0, f"aparat: açık grant kurulamadı: {r}"
    assert sid in _izin_veren_sidler(hedef), "aparat: açık grant DACL'de görünmüyor (pozitif kontrol)"
    return hedef


@pytest.mark.parametrize("sid", ["S-1-1-0", "S-1-5-4"])
@pytest.mark.parametrize("tur", ["dosya", "dizin"])
def test_KRITIK_acik_genis_grup_grant_i_KILITTEN_SONRA_KALMAZ_E2_1_3(tmp_path, tur, sid):
    from utils import file_acl as fa

    hedef = _kur(tmp_path, tur, sid)
    try:
        kilit = fa.lock_down_file if tur == "dosya" else fa.lock_down_dir
        assert kilit(hedef, keep_current_user=True) is True, "aparat: kilit uygulanmadı"
        kalan = _izin_veren_sidler(hedef)
        assert sid not in kalan, (
            f"{tur} kilidi 'uygulandı' (True) dedi ama AÇIK {sid} grant'ı DACL'de KALDI: {sorted(kalan)} — sır dosyası makinedeki "
            "her hesaba açık (DPAPI LOCAL_MACHINE: okuyan çözer)"
        )
        # Kural 2 / Ö.4: kilit süreci kendi dosyasından dışarı atmaz
        if tur == "dosya":
            assert hedef.read_text(encoding="utf-8") == '{"auto": {}}'
            hedef.write_text('{"auto": {"x": 1}}', encoding="utf-8")
        else:
            (hedef / "yeni.json").write_text("{}", encoding="utf-8")
            assert (hedef / "yeni.json").read_text(encoding="utf-8") == "{}"
    finally:
        _icacls(hedef, "/reset", "/T", "/C", "/Q")


@pytest.mark.parametrize("sid", ["S-1-5-32-545", "S-1-5-11"])
def test_KARSIT_acik_Users_ve_AU_zaten_kaldirilir_E2_1_3(tmp_path, sid):
    """Karşıt: 2026-08-04 düzeltmesinin kapsadığı Users / AU açık ACE'leri bugün de kaldırılır (kapı doğru yeri ölçüyor)."""
    from utils import file_acl as fa

    hedef = _kur(tmp_path, "dosya", sid)
    try:
        assert fa.lock_down_file(hedef, keep_current_user=True) is True
        assert sid not in _izin_veren_sidler(hedef)
    finally:
        _icacls(hedef, "/reset", "/T", "/C", "/Q")
