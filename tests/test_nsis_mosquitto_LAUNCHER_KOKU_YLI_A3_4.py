# -*- coding: utf-8 -*-
"""YLI-A3.4 (L5 · Y71) — kaldırıcı KENDİ mosquitto'muzu, kurulum dizini değiştirilmiş olsa da bulmalı.

Launcher çalışma kökünü HER ZAMAN `install::default_install_root(home)` = `%LOCALAPPDATA%\\PEMF Vet Client`'tan alır (main.rs'de 32
çağrı, `current_exe` YOK); broker `<o kök>\\runtime\\…\\mosquitto.exe`. NSIS PREUNINSTALL kökten öldürme satırı ise YALNIZ `$INSTDIR`
altına bakar (LN L5). Kullanıcı kurulum sayfasında dizini değiştirdiyse (hooks.nsi kendi yorumu: `MUI_PAGE_DIRECTORY gösteriliyor`;
`backend.port` yedek yolu tam bu ayrışma için yazılmış) broker `$INSTDIR` altında DEĞİLDİR → L3'ten beri backend AĞAÇSIZ
öldürüldüğü için yetim kalır (1883 + dosya kilidi; hooks yorumundaki üç sonuç). L5 öncesi ADLA öldürülüyordu → gerileme.

Sonda: kopya cmd.exe süreçleri (ad sürece özgü — yalnız bu testin süreçleri hedeflenir); hooks.nsi'deki GERÇEK satır 32-bit
PowerShell ile, `PEMF_KALDIRMA_KOKU` = özel kurulum dizini, `PEMF_KALDIRMA_KOKU2` = launcher kökü (yamanın verdiği ikinci kök).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[2]
if not (KOK / "launcher").is_dir():
    KOK = Path(__file__).resolve().parents[1]
HOOKS = KOK / "launcher" / "app" / "windows" / "hooks.nsi"

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows süreç / WMI sondası")
_GIZLI = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _pre() -> list[str]:
    m = re.search(r"!macro\s+NSIS_HOOK_PREUNINSTALL\b(.*?)!macroend", HOOKS.read_text(encoding="utf-8"), re.DOTALL)
    assert m
    return [s.strip() for s in m.group(1).splitlines()]


def _komut() -> str:
    s = next(x for x in _pre() if "Win32_Process" in x and "Stop-Process" in x)
    return re.search(r"-Command \"(.*)\"'\s*$", s).group(1).replace("$$", "$")


def test_KRITIK_A3_4_kaldirici_LAUNCHER_kokunu_de_verir():
    """Yapısal: ikinci kök kullanıcı bağlamında `$LOCALAPPDATA\\PEMF Vet Client` ve aynı dalda Tauri bağlamına dönülür."""
    pre = _pre()
    i = next(
        (
            n
            for n, s in enumerate(pre)
            if re.search(
                r'SetEnvironmentVariable\(t\s+"PEMF_KALDIRMA_KOKU2",\s*t\s+"\$LOCALAPPDATA\\PEMF Vet Client"\)', s
            )
        ),
        None,
    )
    assert i is not None, (
        "kaldırıcı launcher'ın sabit çalışma kökünü (%LOCALAPPDATA%\\PEMF Vet Client) PowerShell'e vermiyor"
    )
    assert (
        pre[i - 1].startswith("SetShellVarContext current") and pre[i + 1] == "!insertmacro PEMF_BAGLAMI_GERI_YUKLE"
    ), pre[i - 1 : i + 2]


def test_KRITIK_A3_4_ozel_kurulum_dizininde_LAUNCHER_kokundeki_broker_durdurulur(tmp_path):
    sistem = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    ps = sistem / "SysWOW64" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if not ps.is_file():
        ps = sistem / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    ad = f"pemf_a34_sonda_{os.getpid()}.exe"
    taban = tmp_path.resolve()
    ozel = taban / "OzelDizin" / "PEMF Vet Client"  # NSIS $INSTDIR (kullanıcı seçti)
    launcher_koku = taban / "Local" / "PEMF Vet Client"  # default_install_root
    disari = taban / "Program Files" / "mosquitto"  # sahadaki eski servis yerine
    sondalar = []
    try:
        for d in (launcher_koku / "runtime" / "bin", disari, ozel / "runtime"):
            d.mkdir(parents=True)
            shutil.copy(sistem / "System32" / "cmd.exe", d / ad)
            sondalar.append(
                subprocess.Popen(
                    [str(d / ad), "/d", "/c", "pause"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=_GIZLI,
                )
            )  # YLI: konsolsuz üst süreçte GÖRÜNÜR pencere açmasın
        time.sleep(0.5)
        ortam = {
            **os.environ,
            "PEMF_KALDIRMA_KOKU": str(ozel),
            "PEMF_KALDIRMA_KOKU2": str(launcher_koku),
            "PEMF_KALDIRMA_AD": ad,
        }
        r = subprocess.run(
            [str(ps), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", _komut()],
            env=ortam,
            capture_output=True,
            text=True,
            timeout=120,
            creationflags=_GIZLI,
        )
        time.sleep(0.5)
        durum = [p.poll() is not None for p in sondalar]
        print(f"A3OLC|L5|olen(launcher_koku, disari, ozel)={durum}|rc={r.returncode}")
        assert durum[2], "kurulum dizinindeki süreç durdurulmadı"
        assert not durum[1], "kök DIŞINDAKİ aynı adlı süreç durduruldu (eski servis)"
        assert durum[0], (
            "launcher kökündeki broker DURDURULMADI — özel kurulum dizininde kaldırma sonrası yetim kalır (1883 + dosya kilidi)"
        )
    finally:
        for p in sondalar:
            if p.poll() is None:
                p.kill()
            p.wait(timeout=10)
