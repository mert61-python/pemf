# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""CI: komutu UAC-SÜZGEÇLİ (yükseltilmemiş) belirteçle koşturur — YS1g (GitHub windows-latest 3bec8be9).

NEDEN: GitHub `windows-latest` koşucusu (`runneradmin`) YÜKSELTİLMİŞ çalışır. Ürünün sır / veri kökü kilidi Administrators'a tam yetki verir
(`utils/file_acl`) → yükseltilmiş süreç kilitli dosyayı YİNE okur; "okunamaz dosya / ikinci hesap" benzetimleri (ACL kapıları: D2.79, D2.80,
Y96, Y113, A14, E2-1.6 …) ölçülemedi — 24 kırmızı + 3 hata, kapsam %99,98 (`file_acl.py` / `config.py` yalnız o kollarda). Ürün sahada ve
geliştirici makinesinde YÜKSELTİLMEMİŞ koşar; testler de öyle koşmalı (atlamak yerine).
BELİRTEÇ: çağıranın belirteçinden `CreateRestrictedToken(LUA_TOKEN | DISABLE_MAX_PRIVILEGE)` — Administrators SID'i yalnız-ret, ayrıcalıklar
en aza; bütünlük düzeyi ORTA (S-1-16-8192). Yerel UAC oturumunun süzülmüş belirteciyle aynı biçim.
KULLANIM: python scripts/ci_kisitli_belirtec.py [--zorla] <komut> [arg…]   (çıkış kodu = komutun çıkış kodu)
  Süreç yükseltilmemişse komut DOĞRUDAN koşar (yerel); `--zorla` kısıtlı yolu yükseltilmemişken de kullanır (sınama).
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from ctypes import wintypes as wt

LUA_TOKEN = 0x4
DISABLE_MAX_PRIVILEGE = 0x1
TOKEN_ALL = 0x000F01FF
TOKEN_INTEGRITY_LEVEL = 25
SE_GROUP_INTEGRITY = 0x20
WIN_BUILTIN_ADMINISTRATORS_SID = 26
STARTF_USESTDHANDLES = 0x100
HANDLE_FLAG_INHERIT = 0x1
INFINITE = 0xFFFFFFFF
ORTA_BUTUNLUK = "S-1-16-8192"


class _SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wt.DWORD)]


class _STARTUPINFO(ctypes.Structure):
    _fields_ = [
        ("cb", wt.DWORD),
        ("lpReserved", wt.LPWSTR),
        ("lpDesktop", wt.LPWSTR),
        ("lpTitle", wt.LPWSTR),
        ("dwX", wt.DWORD),
        ("dwY", wt.DWORD),
        ("dwXSize", wt.DWORD),
        ("dwYSize", wt.DWORD),
        ("dwXCountChars", wt.DWORD),
        ("dwYCountChars", wt.DWORD),
        ("dwFillAttribute", wt.DWORD),
        ("dwFlags", wt.DWORD),
        ("wShowWindow", wt.WORD),
        ("cbReserved2", wt.WORD),
        ("lpReserved2", ctypes.c_void_p),
        ("hStdInput", wt.HANDLE),
        ("hStdOutput", wt.HANDLE),
        ("hStdError", wt.HANDLE),
    ]


class _PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("hProcess", wt.HANDLE), ("hThread", wt.HANDLE), ("dwProcessId", wt.DWORD), ("dwThreadId", wt.DWORD)]


def yukseltilmis_mi() -> bool:
    """Bu süreç yükseltilmiş yönetici mi (Administrators etkin)."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def _hata(ad: str) -> OSError:
    kod = ctypes.get_last_error()
    return OSError(kod, f"{ad} başarısız (Win32 {kod}): {ctypes.FormatError(kod).strip()}")


def kisitli_belirtec():
    """Çağıranın belirtecinden UAC-süzgeçli birincil belirteç (HANDLE)."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    adv.OpenProcessToken.argtypes = [wt.HANDLE, wt.DWORD, ctypes.POINTER(wt.HANDLE)]
    adv.CreateWellKnownSid.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(wt.DWORD)]
    adv.CreateRestrictedToken.argtypes = [
        wt.HANDLE,
        wt.DWORD,
        wt.DWORD,
        ctypes.POINTER(_SID_AND_ATTRIBUTES),
        wt.DWORD,
        ctypes.c_void_p,
        wt.DWORD,
        ctypes.c_void_p,
        ctypes.POINTER(wt.HANDLE),
    ]
    adv.ConvertStringSidToSidW.argtypes = [wt.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
    adv.SetTokenInformation.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD]
    adv.GetLengthSid.argtypes = [ctypes.c_void_p]
    k32.GetCurrentProcess.restype = wt.HANDLE
    asil = wt.HANDLE()
    if not adv.OpenProcessToken(k32.GetCurrentProcess(), TOKEN_ALL, ctypes.byref(asil)):
        raise _hata("OpenProcessToken")
    boyut = wt.DWORD(68)
    sid = ctypes.create_string_buffer(68)
    if not adv.CreateWellKnownSid(WIN_BUILTIN_ADMINISTRATORS_SID, None, sid, ctypes.byref(boyut)):
        raise _hata("CreateWellKnownSid")
    devre_disi = (_SID_AND_ATTRIBUTES * 1)()
    devre_disi[0].Sid = ctypes.cast(sid, ctypes.c_void_p)
    yeni = wt.HANDLE()
    if not adv.CreateRestrictedToken(
        asil, LUA_TOKEN | DISABLE_MAX_PRIVILEGE, 1, devre_disi, 0, None, 0, None, ctypes.byref(yeni)
    ):
        raise _hata("CreateRestrictedToken")
    orta = ctypes.c_void_p()
    if not adv.ConvertStringSidToSidW(ORTA_BUTUNLUK, ctypes.byref(orta)):
        raise _hata("ConvertStringSidToSidW")
    etiket = _SID_AND_ATTRIBUTES(orta, SE_GROUP_INTEGRITY)
    if not adv.SetTokenInformation(
        yeni, TOKEN_INTEGRITY_LEVEL, ctypes.byref(etiket), ctypes.sizeof(etiket) + adv.GetLengthSid(orta)
    ):
        raise _hata("SetTokenInformation(TokenIntegrityLevel)")
    k32.CloseHandle(asil)
    return yeni


def kisitli_kos(argv: list[str]) -> int:
    """`argv`ı kısıtlı belirteçle başlatır; standart akışlar devralınır; çıkış kodunu döner."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    k32.GetStdHandle.restype = wt.HANDLE
    k32.SetHandleInformation.argtypes = [wt.HANDLE, wt.DWORD, wt.DWORD]
    adv.CreateProcessAsUserW.argtypes = [
        wt.HANDLE,
        wt.LPCWSTR,
        wt.LPWSTR,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wt.BOOL,
        wt.DWORD,
        ctypes.c_void_p,
        wt.LPCWSTR,
        ctypes.POINTER(_STARTUPINFO),
        ctypes.POINTER(_PROCESS_INFORMATION),
    ]
    k32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
    k32.GetExitCodeProcess.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
    belirtec = kisitli_belirtec()
    si = _STARTUPINFO()
    si.cb = ctypes.sizeof(si)
    si.dwFlags = STARTF_USESTDHANDLES
    akislar = [k32.GetStdHandle(n) for n in (-10, -11, -12)]
    for h in akislar:
        if h:
            k32.SetHandleInformation(h, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT)
    si.hStdInput, si.hStdOutput, si.hStdError = akislar
    pi = _PROCESS_INFORMATION()
    komut = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
    if not adv.CreateProcessAsUserW(
        belirtec, None, komut, None, None, True, 0, None, os.getcwd(), ctypes.byref(si), ctypes.byref(pi)
    ):
        raise _hata("CreateProcessAsUserW")
    k32.WaitForSingleObject(pi.hProcess, INFINITE)
    kod = wt.DWORD()
    k32.GetExitCodeProcess(pi.hProcess, ctypes.byref(kod))
    for h in (pi.hThread, pi.hProcess, belirtec):
        k32.CloseHandle(h)
    return int(kod.value)


def _konsol_utf8() -> None:
    """YS1a dersi: cp1252 konsolda Türkçe ileti (ı) UnicodeEncodeError ile düşmesin."""
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        _konsol_utf8()
    argv = list(sys.argv[1:] if argv is None else argv)
    zorla = bool(argv) and argv[0] == "--zorla"
    if zorla:
        argv = argv[1:]
    if not argv:
        print("kullanım: ci_kisitli_belirtec.py [--zorla] <komut> [arg…]", file=sys.stderr)
        return 2
    if os.name != "nt" or not (zorla or yukseltilmis_mi()):
        return subprocess.call(argv)
    print(
        f"[ci_kisitli_belirtec] UAC-süzgeçli belirteç (Administrators yalnız-ret, bütünlük ORTA): {argv[0]} …",
        flush=True,
    )
    return kisitli_kos(argv)


if __name__ == "__main__":
    sys.exit(main())
