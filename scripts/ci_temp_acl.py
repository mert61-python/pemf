# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""CI: koşucunun TEMP'ini OLAĞAN kullanıcı profili ACL'ine getirir — YS1j (GitHub windows-latest 4c3c10ee).

NEDEN: koşucunun TEMP'i alt öğelerine ACE MİRAS VERMİYOR. Orada doğan dosya ACE'lerini belirtecin VARSAYILAN DACL'inden AÇIK (miras
değil) olarak alır (kullanıcı:F, Administrators:F, SYSTEM:F). ACL benzetimleri ("başka hesabın kilidi": `icacls /inheritance:r /grant:r
*S-1-5-19:(F)`) yalnız MİRAS ACE'lerini kaldırır → kullanıcının açık ACE'i kalır, dosya OKUNUR: 22 kırmızı + 3 hata (D2.80, Y96, Y113,
A14, E2-1.6 …) ve kapsam %99,98 (`file_acl` / `config` yalnız o kollarda). Olağan profil TEMP'inde (SYSTEM / Administrators / kullanıcı
`(OI)(CI)F`) aynı testler yeşil; miras vermeyen dizinde aynı belirti yerelde birebir üretildi. Testleri atlamak yerine ortam düzeltilir.
DAVRANIŞ: TEMP'te bir sonda dosyası doğurur; ACE'lerinin HEPSİ miras mı ölçer. Öyleyse DOKUNMAZ. Değilse TEMP'e SYSTEM, Administrators
ve süreç hesabı için kalıtımlı `(OI)(CI)F` verir (aynı hesabın açık ACE'inin yerine) ve yeniden ölçer; hâlâ miras yoksa ÇIKIŞ 1 (süit
boşuna koşmasın). Hedef: `--dizin <yol>`; yol verilmezse YALNIZ `GITHUB_ACTIONS=true` iken TEMP (geliştiricinin TEMP'ine dokunmaz).
KULLANIM: python scripts/ci_temp_acl.py [--dizin <yol>]
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid

SID_SYSTEM = "S-1-5-18"
SID_ADMINS = "S-1-5-32-544"
SE_FILE_OBJECT = 1
DACL_SECURITY_INFORMATION = 0x4
SDDL_REVISION_1 = 1
CREATE_NO_WINDOW = 0x08000000


def sddl(yol: str) -> str:
    """`yol`un DACL'i SDDL metni olarak (Windows API — dil bağımsız)."""
    import ctypes
    from ctypes import wintypes as wt

    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    adv.GetNamedSecurityInfoW.argtypes = [
        wt.LPCWSTR,
        ctypes.c_int,
        wt.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    adv.GetNamedSecurityInfoW.restype = wt.DWORD
    adv.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
        ctypes.c_void_p,
        wt.DWORD,
        wt.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
    ]
    k32.LocalFree.argtypes = [ctypes.c_void_p]
    dacl, sd = ctypes.c_void_p(), ctypes.c_void_p()
    kod = adv.GetNamedSecurityInfoW(
        yol, SE_FILE_OBJECT, DACL_SECURITY_INFORMATION, None, None, ctypes.byref(dacl), None, ctypes.byref(sd)
    )
    if kod:
        raise OSError(kod, f"GetNamedSecurityInfoW başarısız (Win32 {kod}): {yol}")
    try:
        metin = ctypes.c_void_p()
        if not adv.ConvertSecurityDescriptorToStringSecurityDescriptorW(
            sd, SDDL_REVISION_1, DACL_SECURITY_INFORMATION, ctypes.byref(metin), None
        ):
            raise OSError(ctypes.get_last_error(), "ConvertSecurityDescriptorToStringSecurityDescriptorW başarısız")
        try:
            return ctypes.wstring_at(metin)
        finally:
            k32.LocalFree(metin)
    finally:
        k32.LocalFree(sd)


def aceler(sddl_metni: str) -> list[str]:
    """SDDL'deki DACL ACE'leri (parantezsiz)."""
    dacl = sddl_metni.split("D:", 1)[1].split("S:", 1)[0] if "D:" in sddl_metni else ""
    return re.findall(r"\(([^()]*)\)", dacl)


def acik_aceler(sddl_metni: str) -> list[str]:
    """DACL'deki MİRAS OLMAYAN ACE'ler (bayrak alanında `ID` yok — bayraklar iki harfli: OI CI NP IO ID …)."""
    sonuc = []
    for ace in aceler(sddl_metni):
        alanlar = ace.split(";")
        bayrak = alanlar[1] if len(alanlar) > 1 else ""
        if "ID" not in [bayrak[i : i + 2] for i in range(0, len(bayrak), 2)]:
            sonuc.append(ace)
    return sonuc


def sonda(dizin: str) -> tuple[bool, str]:
    """`dizin`de yeni bir alt dizin + dosya doğurur (pytest'in `tmp_path` zinciri gibi); dosyanın ACE'lerinin HEPSİ miras mı?
    Dönüş: (miras_mi, dosyanın SDDL'i). Sonda her durumda silinir."""
    alt = os.path.join(dizin, f"ys_acl_sonda_{os.getpid()}_{uuid.uuid4().hex[:8]}")
    os.mkdir(alt)
    try:
        dosya = os.path.join(alt, "sonda.txt")
        with open(dosya, "w", encoding="utf-8") as h:
            h.write("x")
        s = sddl(dosya)
        return bool(aceler(s)) and not acik_aceler(s), s
    finally:
        shutil.rmtree(alt, ignore_errors=True)


def surec_sid() -> str:
    """Süreç hesabının SID'i (`whoami /user` — dil bağımsız CSV)."""
    r = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        capture_output=True,
        text=True,
        timeout=60,
        creationflags=CREATE_NO_WINDOW,
    )
    sid = r.stdout.strip().split(",")[-1].strip().strip('"')
    if not sid.startswith("S-1-"):
        raise RuntimeError(f"süreç SID'i okunamadı: {r.stdout!r} {r.stderr!r}")
    return sid


def olaganlastir(dizin: str, sid: str) -> subprocess.CompletedProcess:
    """`dizin`e SYSTEM, Administrators ve süreç hesabı için kalıtımlı tam erişim (`/grant:r`: aynı hesabın açık ACE'inin YERİNE)."""
    return subprocess.run(
        [
            "icacls",
            dizin,
            "/grant:r",
            f"*{SID_SYSTEM}:(OI)(CI)F",
            "/grant:r",
            f"*{SID_ADMINS}:(OI)(CI)F",
            "/grant:r",
            f"*{sid}:(OI)(CI)F",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        creationflags=CREATE_NO_WINDOW,
    )


def _konsol_utf8() -> None:
    """YS1a dersi: cp1252 konsolda Türkçe ileti UnicodeEncodeError ile düşmesin."""
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        _konsol_utf8()
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) == 2 and argv[0] == "--dizin":
        dizin = argv[1]
    elif not argv and os.environ.get("GITHUB_ACTIONS") == "true":
        dizin = tempfile.gettempdir()
    else:
        print(
            "kullanım: ci_temp_acl.py [--dizin <yol>]  (yol verilmezse YALNIZ GITHUB_ACTIONS=true iken TEMP)",
            file=sys.stderr,
        )
        return 2
    miras, s = sonda(dizin)
    print(f"[ci_temp_acl] {dizin}\n  dizin DACL : {sddl(dizin)}\n  sonda DACL : {s}", flush=True)
    if miras:
        print("[ci_temp_acl] alt öğelere miras veriyor — dokunulmadı", flush=True)
        return 0
    r = olaganlastir(dizin, surec_sid())
    if r.returncode != 0:
        print(f"[ci_temp_acl] HATA: icacls rc={r.returncode}: {r.stdout}{r.stderr}", file=sys.stderr)
        return 1
    miras, s = sonda(dizin)
    print(f"  sonra dizin DACL : {sddl(dizin)}\n  sonra sonda DACL : {s}", flush=True)
    if not miras:
        print(
            "[ci_temp_acl] HATA: olağanlaştırma sonrası da yeni dosyada AÇIK ACE var — ACL benzetimleri (başka hesabın kilidi) "
            "bu koşucuda ölçülemez",
            file=sys.stderr,
        )
        return 1
    print(
        "[ci_temp_acl] olağan profil biçimine getirildi (SYSTEM / Administrators / süreç hesabı — kalıtımlı tam erişim)",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
