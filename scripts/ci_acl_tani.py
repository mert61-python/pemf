# -*- coding: utf-8 -*-
"""YS1l GEÇİCİ TANI (GitHub windows-latest, uç 98f524a7): kısıtlı belirteçte (Administrators yalnız-ret) bile `lock_down_file`
kilidi (SY + BA + LOCAL SERVICE) dosyayı KAPATMIYOR, `/inheritance:r /grant:r *S-1-5-19:(OI)(CI)F` dizini listelenebilir bırakıyor.
Bu betik erişimin NEREDEN geldiğini ölçer: belirteç (sahip, varsayılan DACL, gruplar, ayrıcalıklar), kilit öncesi/sonrası SDDL,
`AccessCheck` (MAXIMUM_ALLOWED) maskesi, CreateFileW (yedekleme anlamlı / anlamsız) sonucu, süzgeç sürücüleri. Yalnız okur/yazar
kendi alt dizininde; çıkış HEP 0 (tanı adımı işi durdurmaz). Kök neden düzeltilince iş akışından ve depodan KALDIRILIR.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import tempfile
import uuid
from ctypes import wintypes as wt

OWNER_GROUP_DACL = 0x1 | 0x2 | 0x4
FILE_GENERIC_READ = 0x120089
FILE_LIST_DIRECTORY = 0x1
MAXIMUM_ALLOWED = 0x02000000
GENERIC_READ = 0x80000000
FILE_SHARE_ALL = 0x7
OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
INVALID_HANDLE = ctypes.c_void_p(-1).value

adv = ctypes.WinDLL("advapi32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
adv.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
    ctypes.c_void_p,
    wt.DWORD,
    wt.DWORD,
    ctypes.POINTER(ctypes.c_void_p),
    ctypes.c_void_p,
]
adv.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
adv.GetFileSecurityW.argtypes = [wt.LPCWSTR, wt.DWORD, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD)]
adv.GetTokenInformation.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD)]
adv.OpenProcessToken.argtypes = [wt.HANDLE, wt.DWORD, ctypes.POINTER(wt.HANDLE)]
adv.DuplicateToken.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.POINTER(wt.HANDLE)]
adv.AccessCheck.argtypes = [
    ctypes.c_void_p,
    wt.HANDLE,
    wt.DWORD,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.POINTER(wt.DWORD),
    ctypes.POINTER(wt.DWORD),
    ctypes.POINTER(wt.BOOL),
]
adv.InitializeSecurityDescriptor.argtypes = [ctypes.c_void_p, wt.DWORD]
adv.SetSecurityDescriptorDacl.argtypes = [ctypes.c_void_p, wt.BOOL, ctypes.c_void_p, wt.BOOL]
adv.GetNamedSecurityInfoW.argtypes = [
    wt.LPCWSTR,
    ctypes.c_int,
    wt.DWORD,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_void_p),
]
k32.GetCurrentProcess.restype = wt.HANDLE
k32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p, wt.DWORD, wt.DWORD, wt.HANDLE]
k32.CreateFileW.restype = ctypes.c_void_p
k32.CloseHandle.argtypes = [ctypes.c_void_p]
k32.LocalFree.argtypes = [ctypes.c_void_p]


class _GENERIC_MAPPING(ctypes.Structure):
    _fields_ = [("r", wt.DWORD), ("w", wt.DWORD), ("x", wt.DWORD), ("a", wt.DWORD)]


def _sd_sddl(sd, bilgi=OWNER_GROUP_DACL) -> str:
    out = ctypes.c_void_p()
    if not adv.ConvertSecurityDescriptorToStringSecurityDescriptorW(sd, 1, bilgi, ctypes.byref(out), None):
        return f"<SDDL çevrilemedi {ctypes.get_last_error()}>"
    try:
        return ctypes.wstring_at(out.value)
    finally:
        k32.LocalFree(out)


def _dosya_sd(yol: str):
    n = wt.DWORD(0)
    adv.GetFileSecurityW(yol, OWNER_GROUP_DACL, None, 0, ctypes.byref(n))
    buf = ctypes.create_string_buffer(max(n.value, 1))
    if not adv.GetFileSecurityW(yol, OWNER_GROUP_DACL, buf, n, ctypes.byref(n)):
        return None, ctypes.get_last_error()
    return buf, 0


def _sid_metni(p) -> str:
    out = ctypes.c_void_p()
    if not adv.ConvertSidToStringSidW(p, ctypes.byref(out)):
        return "<?>"
    try:
        return ctypes.wstring_at(out.value)
    finally:
        k32.LocalFree(out)


def _belirtec(erisim=0x8 | 0x2):  # TOKEN_QUERY | TOKEN_DUPLICATE
    h = wt.HANDLE()
    adv.OpenProcessToken(k32.GetCurrentProcess(), erisim, ctypes.byref(h))
    return h


def _bilgi(h, sinif: int):
    n = wt.DWORD(0)
    adv.GetTokenInformation(h, sinif, None, 0, ctypes.byref(n))
    buf = ctypes.create_string_buffer(max(n.value, 1))
    if not adv.GetTokenInformation(h, sinif, buf, n, ctypes.byref(n)):
        return None
    return buf


def belirtec_ozeti() -> None:
    h = _belirtec()
    sahip = _bilgi(h, 4)  # TokenOwner
    if sahip is not None:
        print(f"  TokenOwner        : {_sid_metni(ctypes.c_void_p.from_buffer(sahip).value)}")
    vd = _bilgi(h, 6)  # TokenDefaultDacl
    if vd is not None:
        acl = ctypes.c_void_p.from_buffer(vd).value
        sd = ctypes.create_string_buffer(64)
        adv.InitializeSecurityDescriptor(sd, 1)
        adv.SetSecurityDescriptorDacl(sd, True, acl, False)
        print(f"  TokenDefaultDacl  : {_sd_sddl(sd, 0x4)}")
    for ad, sinif in (("TokenElevationType", 18), ("TokenElevation", 20)):
        b = _bilgi(h, sinif)
        print(f"  {ad:<18}: {None if b is None else ctypes.c_uint32.from_buffer(b).value}")
    print(f"  IsUserAnAdmin     : {bool(ctypes.windll.shell32.IsUserAnAdmin())}")
    k32.CloseHandle(h)


def erisim_denetimi(yol: str, istenen: int) -> str:
    sd, hata = _dosya_sd(yol)
    if sd is None:
        return f"GetFileSecurity hata={hata}"
    h = _belirtec()
    imp = wt.HANDLE()
    if not adv.DuplicateToken(h, 2, ctypes.byref(imp)):
        return f"DuplicateToken hata={ctypes.get_last_error()}"
    gm = _GENERIC_MAPPING(FILE_GENERIC_READ, 0x120116, 0x1200A0, 0x1F01FF)
    ps = ctypes.create_string_buffer(256)
    psn = wt.DWORD(256)
    verilen = wt.DWORD(0)
    durum = wt.BOOL(False)
    ok = adv.AccessCheck(
        sd, imp, istenen, ctypes.byref(gm), ps, ctypes.byref(psn), ctypes.byref(verilen), ctypes.byref(durum)
    )
    hata = ctypes.get_last_error()
    k32.CloseHandle(imp)
    k32.CloseHandle(h)
    if not ok:
        return f"AccessCheck çağrısı düştü hata={hata}"
    return f"verilen=0x{verilen.value:08X} durum={bool(durum.value)}"


def ac(yol: str, erisim: int, bayrak: int) -> str:
    h = k32.CreateFileW(yol, erisim, FILE_SHARE_ALL, None, OPEN_EXISTING, bayrak, None)
    if h in (None, INVALID_HANDLE):
        return f"RET (hata={ctypes.get_last_error()})"
    k32.CloseHandle(h)
    return "AÇILDI"


def python_oku(yol: str) -> str:
    try:
        with open(yol, "rb") as f:
            f.read()
        return "OKUNDU"
    except OSError as e:
        return f"RET ({type(e).__name__} {e.winerror if hasattr(e, 'winerror') else ''})"


def python_listele(yol: str) -> str:
    try:
        return f"LİSTELENDİ ({len(os.listdir(yol))} öğe)"
    except OSError as e:
        return f"RET ({type(e).__name__})"


def icacls(*a: str) -> None:
    r = subprocess.run(["icacls", *a], capture_output=True, text=True, errors="replace")
    print(
        f"  icacls {' '.join(a[1:])} → rc={r.returncode} {r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ''}"
    )


def sddl(yol: str) -> str:
    """GetNamedSecurityInfoW (ACE kalıtım bayrağı ID görünür; GetFileSecurityW onu düşürür)."""
    sd = ctypes.c_void_p()
    rc = adv.GetNamedSecurityInfoW(yol, 1, OWNER_GROUP_DACL, None, None, None, None, ctypes.byref(sd))
    if rc != 0:
        return f"<okunamadı {rc}>"
    try:
        return _sd_sddl(sd)
    finally:
        k32.LocalFree(sd)


def dosya_olc(etiket: str, f: str) -> None:
    print(f"  [{etiket}] SDDL      : {sddl(f)}")
    print(f"  [{etiket}] AccessCheck MAX : {erisim_denetimi(f, MAXIMUM_ALLOWED)}")
    print(f"  [{etiket}] AccessCheck READ: {erisim_denetimi(f, FILE_GENERIC_READ)}")
    print(f"  [{etiket}] CreateFileW GENERIC_READ         : {ac(f, GENERIC_READ, 0)}")
    print(f"  [{etiket}] CreateFileW GENERIC_READ+BACKUP  : {ac(f, GENERIC_READ, FILE_FLAG_BACKUP_SEMANTICS)}")
    print(f"  [{etiket}] python open('rb')                : {python_oku(f)}")


def kok_olc(kok: str) -> None:
    d = os.path.join(kok, f"ys_acl_tani_{os.getpid()}_{uuid.uuid4().hex[:8]}")
    os.makedirs(d)
    print(f"--- kök {kok}\n  kök SDDL   : {sddl(kok)}\n  alt dizin  : {sddl(d)}")
    f = os.path.join(d, "pemf_secrets.json")
    with open(f, "w", encoding="utf-8") as h:
        h.write("{}")
    dosya_olc("yeni", f)
    icacls(
        f,
        "/inheritance:r",
        "/remove:g",
        "*S-1-5-32-545",
        "/remove:g",
        "*S-1-5-11",
        "/grant:r",
        "*S-1-5-18:F",
        "/grant:r",
        "*S-1-5-32-544:F",
        "/grant:r",
        "*S-1-5-19:F",
    )
    dosya_olc("Y96 kilidi SY+BA+LS", f)
    g = os.path.join(d, "yalniz_ls.txt")
    with open(g, "w", encoding="utf-8") as h:
        h.write("x")
    icacls(g, "/inheritance:r", "/grant:r", "*S-1-5-19:(F)")
    dosya_olc("yalnız LS", g)
    v = os.path.join(d, "veri_koku")
    os.makedirs(v)
    with open(os.path.join(v, "auth_users.db"), "w", encoding="utf-8") as h:
        h.write("x")
    icacls(v, "/inheritance:r", "/grant:r", "*S-1-5-19:(OI)(CI)F")
    print(f"  [dizin LS] SDDL       : {sddl(v)}")
    print(f"  [dizin LS] AccessCheck LIST: {erisim_denetimi(v, FILE_LIST_DIRECTORY)}")
    print(f"  [dizin LS] CreateFileW LIST+BACKUP : {ac(v, FILE_LIST_DIRECTORY, FILE_FLAG_BACKUP_SEMANTICS)}")
    print(f"  [dizin LS] os.listdir : {python_listele(v)}")
    subprocess.run(["icacls", d, "/reset", "/T", "/C", "/Q"], capture_output=True)


def komut(*a: str) -> None:
    r = subprocess.run(list(a), capture_output=True, text=True, errors="replace")
    print(f"$ {' '.join(a)} (rc={r.returncode})")
    for satir in (r.stdout + r.stderr).strip().splitlines()[:80]:
        print(f"    {satir}")


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        try:
            akis.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if sys.platform != "win32":
        print("[ci_acl_tani] yalnız Windows")
        return 0
    print(f"===== [ci_acl_tani] pid={os.getpid()} python={sys.version.split()[0]}")
    try:
        belirtec_ozeti()
        komut("whoami", "/all", "/fo", "list")
        kokler = [tempfile.gettempdir(), os.path.realpath(tempfile.gettempdir())]
        if os.environ.get("RUNNER_TEMP"):
            kokler.append(os.environ["RUNNER_TEMP"])
        for kok in dict.fromkeys(kokler):
            try:
                kok_olc(kok)
            except Exception as e:  # noqa: BLE001 — tanı: hiçbir ölçüm öbürünü düşürmesin
                print(f"  !!! {kok}: {type(e).__name__}: {e}")
        if not ctypes.windll.shell32.IsUserAnAdmin():
            return 0
        komut("fltmc", "filters")
        komut("fsutil", "fsinfo", "volumeinfo", "C:")
        komut("reg", "query", r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System")
        komut("cmd", "/c", "ver")
    except Exception as e:  # noqa: BLE001
        print(f"!!! tanı düştü: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
