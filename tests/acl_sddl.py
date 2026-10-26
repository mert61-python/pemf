# -*- coding: utf-8 -*-
"""DACL izin (A) ACE'lerinin SID'leri — `Get-Acl .Sddl` (Windows PowerShell 5.1) üzerinden.

ACE ADLARI Windows GÖRÜNTÜ diline bağlıdır (`icacls`: "BUILTIN\\Users" / "BUILTIN\\Kullanıcılar"); SDDL'deki SID ve takma ad (BU, AU)
dilden BAĞIMSIZDIR. 2-F incelemesi §10 #12 → D5: A-10 karşıt kolu `icacls` METNİNDE "BUILTIN\\Users" / SID arıyordu — TR görüntü dilli
Windows'ta ikisi de basılmaz, kol Users ERİŞEBİLSE de yeşil kalırdı (kör). `PSModulePath` boş geçilir: pwsh 7 altından açılan 5.1
`Get-Acl`ı yükleyemiyordu (hafıza "pwsh7→python→PS5.1 Get-Acl düşer")."""

from __future__ import annotations

import os
import re
import subprocess

#: Yerel `Users` / `Authenticated Users` — takma ad ve SID biçimleriyle.
GENIS_GRUPLAR = frozenset({"BU", "AU", "S-1-5-32-545", "S-1-5-11"})


def dacl_sidleri(yol) -> set[str]:
    ortam = dict(os.environ)
    ortam["PSModulePath"] = ""
    r = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", f"(Get-Acl -LiteralPath '{yol}').Sddl"],
        capture_output=True,
        text=True,
        timeout=60,
        env=ortam,
    )
    assert r.returncode == 0 and "D:" in r.stdout, f"aparat: SDDL okunamadı: {r.stdout}{r.stderr}"
    dacl = r.stdout.split("D:", 1)[1].split("S:", 1)[0]
    return {m.group(1) for m in re.finditer(r"\(A;[^;()]*;[^;()]*;[^;()]*;[^;()]*;([^;()]+)\)", dacl)}
