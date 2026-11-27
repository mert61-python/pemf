# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""CI: ACL benzetimlerinin ("başka hesabın kilidi") ÖLÇÜLEBİLDİĞİ bir TEMP sağlar — YS1j → YS1l (GitHub windows-latest).

NEDEN (YS1l tanısı, uç 21b5be65 · Windows Server 2025 26100): koşucunun profil TEMP'inde (C:/Users/runneradmin/AppData/Local/Temp)
doğan dosyaya `icacls /inheritance:r` kalıtımlı ACE'leri SİLMİYOR, AÇIK ACE'ye ÇEVİRİYOR (`/inheritance:d` gibi): "yalnız LOCAL SERVICE"
kilidinden sonra DACL `PAI(LS)(SY)(BA)(LA)` — süreç hesabı (LA) erişimini korur, kilit ölçülemez → 19 kırmızı + 3 hata (Y96, D2.80,
Y113, OB2B24, A14, E2-1.6 …). Aynı koşucuda D:/a/_temp'te aynı komut DOĞRU (`PAI(LS)`, okuma RET). `GetNamedSecurityInfoW` iki
yerde de dosyanın ACE'lerini `ID` gösterir (ebeveynle karşılaştırıp HESAPLAR) → ACE bayrağına bakan YS1j sondası "miras veriyor"
dedi ve yanıldı. Bu yüzden ölçüm İŞLEVSEL: dizinde (iki kat altta, pytest'in `tmp_path` zinciri gibi) doğan dosyaya kilit uygulanır,
DACL'de YALNIZ kilit ACE'i kaldı mı bakılır (belirteçten bağımsız).
DAVRANIŞ: ölçülüyorsa DOKUNMAZ. Ölçülmüyorsa dizine korumalı, kalıtımlı `(OI)(CI)F` DACL yazar (SYSTEM / Administrators / süreç
hesabı — olağan profil TEMP biçimi) ve yeniden ölçer. CI'da (yol verilmeden) yine ölçülmüyorsa YEDEK: `$RUNNER_TEMP/pemf-tmp`
olağanlaştırılır, ölçülür ve `TEMP` / `TMP` sonraki adımlar için `$GITHUB_ENV`'e yazılır. Hiçbiri olmazsa ÇIKIŞ 1 (süit 60 dk boşuna
koşmasın). Yol verilmezse YALNIZ `GITHUB_ACTIONS=true` iken TEMP hedeflenir (geliştiricinin TEMP'ine dokunmaz).
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


KILIT_ACE = "A;;FA;;;LS"  # `icacls … /grant:r *S-1-5-19:(F)` → SDDL'de tek ACE


def sonda(dizin: str) -> tuple[bool, str]:
    """`dizin`de iki kat alt dizin + dosya doğurur; dosyaya "başka hesabın kilidi" (`/inheritance:r /grant:r *S-1-5-19:(F)`) uygular.
    Dönüş: (kilit ölçülür mü = DACL'de YALNIZ kilit ACE'i kaldı mı, kilit sonrası SDDL). Sonda her durumda sıfırlanıp silinir."""
    alt = os.path.join(dizin, f"ys_acl_sonda_{os.getpid()}_{uuid.uuid4().hex[:8]}")
    os.makedirs(os.path.join(alt, "ic"))
    try:
        dosya = os.path.join(alt, "ic", "sonda.txt")
        with open(dosya, "w", encoding="utf-8") as h:
            h.write("x")
        r = subprocess.run(
            ["icacls", dosya, "/inheritance:r", "/grant:r", "*S-1-5-19:(F)"],
            capture_output=True,
            text=True,
            timeout=60,
            creationflags=CREATE_NO_WINDOW,
        )
        if r.returncode != 0:
            raise RuntimeError(f"sonda kilidi uygulanamadı (icacls rc={r.returncode}): {r.stdout}{r.stderr}")
        s = sddl(dosya)
        return aceler(s) == [KILIT_ACE], s
    finally:
        # Kilitli dosya üst dizinin FILE_DELETE_CHILD hakkıyla silinir (`/reset` YOK: kalıtımsız ebeveynde DACL'i BOŞALTIR, silme
        # düşer — yerelde artık bıraktı). Yine kalırsa: sahip olarak (WRITE_DAC) kendine erişim verip yeniden sil.
        shutil.rmtree(alt, ignore_errors=True)
        if os.path.exists(alt):
            subprocess.run(
                ["icacls", alt, "/grant", f"*{surec_sid()}:(OI)(CI)F", "/T", "/C", "/Q"],
                capture_output=True,
                timeout=60,
                creationflags=CREATE_NO_WINDOW,
            )
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
    """`dizin`e KORUMALI (`/inheritance:r` — eski tip ebeveyne bağlı kalmaz), kalıtımlı tam erişim: SYSTEM, Administrators, süreç
    hesabı `(OI)(CI)F` (`/grant:r`: aynı hesabın açık ACE'inin YERİNE). Olağan kullanıcı profili TEMP'inin biçimi."""
    return subprocess.run(
        [
            "icacls",
            dizin,
            "/inheritance:r",
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


def duzelt(dizin: str, sid: str) -> int:
    """`dizin`de kilit ölçülüyorsa 0 (dokunmaz); değilse olağanlaştırıp yeniden ölçer: 0 ölçülür · 1 hâlâ ölçülmez / icacls düştü."""
    olculur, s = sonda(dizin)
    print(f"[ci_temp_acl] {dizin}\n  dizin DACL        : {sddl(dizin)}\n  kilit sonrası DACL: {s}", flush=True)
    if olculur:
        print("[ci_temp_acl] kilit benzetimi ölçülüyor — dokunulmadı", flush=True)
        return 0
    print(
        f"[ci_temp_acl] kilit ÖLÇÜLMÜYOR — kilitten sonra kalan fazladan ACE: {[a for a in aceler(s) if a != KILIT_ACE]}",
        flush=True,
    )
    r = olaganlastir(dizin, sid)
    if r.returncode != 0:
        print(f"[ci_temp_acl] HATA: icacls rc={r.returncode}: {r.stdout}{r.stderr}", file=sys.stderr)
        return 1
    olculur, s = sonda(dizin)
    print(f"  sonra dizin DACL        : {sddl(dizin)}\n  sonra kilit sonrası DACL: {s}", flush=True)
    if not olculur:
        print(f"[ci_temp_acl] olağanlaştırma sonrası da kilit ölçülmüyor: {dizin}", file=sys.stderr)
        return 1
    print(
        "[ci_temp_acl] olağan profil biçimine getirildi (korumalı · SYSTEM / Administrators / süreç hesabı — kalıtımlı tam erişim)",
        flush=True,
    )
    return 0


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
    sid = surec_sid()
    if duzelt(dizin, sid) == 0:
        return 0
    if argv:  # --dizin: yalnız o dizin (yedek yok)
        print("[ci_temp_acl] HATA: ACL benzetimleri (başka hesabın kilidi) bu dizinde ölçülemez", file=sys.stderr)
        return 1
    rt, ge = os.environ.get("RUNNER_TEMP"), os.environ.get("GITHUB_ENV")
    if not rt or not ge:
        print(
            "[ci_temp_acl] HATA: TEMP'te kilit ölçülemiyor ve yedek için RUNNER_TEMP / GITHUB_ENV yok", file=sys.stderr
        )
        return 1
    yedek = os.path.join(rt, "pemf-tmp")
    os.makedirs(yedek, exist_ok=True)
    if duzelt(yedek, sid) != 0:
        print(
            "[ci_temp_acl] HATA: yedek TEMP'te de kilit ölçülemiyor — ACL benzetimleri bu koşucuda ölçülemez",
            file=sys.stderr,
        )
        return 1
    with open(ge, "a", encoding="utf-8") as h:
        h.write(f"TEMP={yedek}\nTMP={yedek}\n")
    print(f"[ci_temp_acl] YEDEK: sonraki adımların TEMP / TMP'si → {yedek}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
