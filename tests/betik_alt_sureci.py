# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""BETİK ALT SÜRECİ — `scripts/*.py`yi conftest yolları OLMADAN, yalıtılmış ortamda koşturan yardımcı.

⚠️ BU DOSYA BİR TEST DEĞİL, YARDIMCIDIR (`topoloji.py` deseni): adı `test_*` olmadığı için pytest
onu TOPLAMAZ.

NEDEN: `tests/conftest.py` süreç yoluna depo kökü + `apps/backend` ekler; bir betiği süreç İÇİNDE
çağıran test, betiğin KENDİ yol kurulumu bozuk olsa da YEŞİL kalır. F4 artığı betikler tam böyle
haftalarca ölü kaldı (D0Ö.19/20/21). Davranış kolları ALT SÜREÇTE koşmalı.

⚠️ GÜVENLİK: ortam İZİN LİSTESİDİR — tüm `PEMF_*`/`SUPABASE_*` dışarıda; APPDATA, LOCALAPPDATA,
PROGRAMDATA, USERPROFILE, HOME, TEMP verilen sahte kökte; kasa null. Gerçek
`C:\\ProgramData\\PEMF_System\\PEMF_GUI` sırları bu süreçten OKUNAMAZ. Test bekçisi alt sürece
GEÇMEZ: bu yardımcıyla ağ gerektiren hiçbir şey koşturulmamalı.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
BETIKLER = KOK / "scripts"

#: Alt sürece taşınan ortam — yalnız işletim sistemi/yorumlayıcı için gerekenler.
TASINAN = (
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
    "PATH",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "OS",
)


def yalitik_ortam(kok: Path) -> dict:
    """İzin-listeli alt süreç ortamı; kullanıcı/makine kökleri `kok` altında sahte dizinler."""
    env = {k: os.environ[k] for k in TASINAN if k in os.environ}
    for ad in ("APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "USERPROFILE", "HOME", "TEMP", "TMP"):
        yol = kok / ad.lower()
        yol.mkdir(parents=True, exist_ok=True)
        env[ad] = str(yol)
    env.update(
        {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHON_KEYRING_BACKEND": "keyring.backends.null.Keyring",
        }
    )
    assert not [k for k in env if k.upper().startswith(("PEMF_", "SUPABASE_"))]
    return env


def kostur(arg: list[str], cwd: Path, env: dict, sure: float = 300) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *arg],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=sure,
    )


def betik_modulu(ad: str):
    """Betiği süreç İÇİNE modül olarak yükle (⚠️ conftest yolları VAR — yalnız mantık kolları için)."""
    spec = importlib.util.spec_from_file_location(f"betik_kapi_{ad}", BETIKLER / f"{ad}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m
