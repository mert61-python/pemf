# -*- coding: utf-8 -*-
"""YS1g (GitHub windows-latest ilk tam koşu, 0cf83c06): ALT SÜREÇ AĞ BEKÇİSİ (`tests/alt_surec_ag_bekcisi.py`) `subprocess.Popen`
denetim olayından yalnız `executable`ı kaydediyordu. Python 3.10.10+ (gh-101283) `shell=True`da `executable`a cmd.exe'nin TAM yolunu
koyar, komut satırı (`…\\cmd.exe /c "ver"`) `args`ta kalır → kayıt argümansız `C:\\WINDOWS\\system32\\cmd.exe` oldu; izin listeleri
(`cmd.exe /c "ver"` — platform sürüm sorgusu) eşleşmedi, 22 test "izin listesi dışı alt süreç" ile KIRMIZI. Yerelde (gömülü 3.10.2:
`executable` None) görünmedi.

KAPI (bekçi süreç geneli kanca kurduğu için ALT SÜREÇTE): (1) bu Python'da GERÇEK `subprocess.run("ver", shell=True)` → kayıt tam komut
satırı (`/c "ver"` dahil) ve iki aparatın izin deseni (`cmd.exe /c "?ver"?`) eşleşir; (2) 3.10.10+ biçimi (executable + dize args) yapay
olayla → tam komut satırı; (3) liste args (executable yok) → eskisi gibi yalnız program adı.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

TESTLER = Path(__file__).resolve().parent

_COCUK = r"""
import json, subprocess, sys
sys.path.insert(0, sys.argv[1])
import alt_surec_ag_bekcisi as b
subprocess.run("ver", shell=True, capture_output=True, check=False)
gercek = list(b.ALT_SURECLER)
b.ALT_SURECLER.clear()
b._kanca("subprocess.Popen", ("C:\\WINDOWS\\system32\\cmd.exe", 'C:\\WINDOWS\\system32\\cmd.exe /c "ver"', None, None))
b._kanca("subprocess.Popen", (None, ["icacls", "C:\\x", "/inheritance:r"], None, None))
print("SONUC " + json.dumps({"gercek": gercek, "yapay": list(b.ALT_SURECLER)}))
"""

#: İki aparatın (test_bozuk_sayisal_bayrak_ESTOP_OLDURMEZ / test_acilis_DB_acilamasa_ACIL_DURDUR_yasar) `cmd.exe` kolu.
_CMD_VER = re.compile(r'subprocess\.Popen:(?:[A-Za-z]:\\(?:[^"\\]+\\)*)?cmd\.exe /c "?ver"?', re.IGNORECASE)


def _kos() -> dict:
    c = subprocess.run([sys.executable, "-c", _COCUK, str(TESTLER)], capture_output=True, text=True, timeout=120)
    satir = [s for s in c.stdout.splitlines() if s.startswith("SONUC ")]
    assert c.returncode == 0 and satir, f"çocuk düştü rc={c.returncode}: {c.stderr[-800:]}"
    return json.loads(satir[-1][len("SONUC ") :])


def test_KRITIK_gercek_shell_ver_TAM_komut_satiriyla_kaydedilir_izin_deseni_eslesir():
    s = _kos()
    popen = [k for k in s["gercek"] if k.startswith("subprocess.Popen:")]
    assert len(popen) == 1, s["gercek"]
    assert '/c "ver"' in popen[0], f"komut satırı kayboldu (yalnız executable kaydedildi): {popen[0]}"
    assert _CMD_VER.fullmatch(popen[0]), f"izin deseni eşleşmiyor: {popen[0]}"


def test_KRITIK_executable_ve_dize_args_TAM_komut_KARSIT_liste_args_yalniz_program():
    s = _kos()
    assert s["yapay"] == ['subprocess.Popen:C:\\WINDOWS\\system32\\cmd.exe /c "ver"', "subprocess.Popen:icacls"], s[
        "yapay"
    ]
