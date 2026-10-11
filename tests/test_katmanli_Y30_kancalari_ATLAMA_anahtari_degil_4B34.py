# -*- coding: utf-8 -*-
"""4B-3.4 (A3 inceleme, 4-A devri #4 `394a24a0`) — `katmanli_yayin_hazirla.ps1`'in `-PytestOnek` / `-Hedef` geçişi Y30'u ATLAMA anahtarıdır.

Betik başlığı "Atlama anahtarı YOK" der; aynı başlık `-PytestOnek` / `-Hedef`'i "denetim / sandbox kancası (yayın makinesinde KULLANILMAZ)"
diye listeler ama hiçbir şey bunu ZORLAMAZ. Ölçüldü (HEAD `0ef16a1e`, `kayit/k2_devir4_sonda.txt`): `-PytestOnek "<python>,-c,import sys;
sys.exit(0)"` → HİÇ test koşmadan "[YAYIN-ONCESI] tam suit GECTI" + manifest YENİ sürümle yazıldı (çıkış 0); `-Hedef <tek yeşil test>` →
aynı. `publish_release.ps1` (D4.10) Y30'u parametresiz çağırır — o kanalda bu kanca YOK → katmanlı kanal asimetrik.

Kapı GERÇEK betik + GERÇEK `yayin_oncesi_suit.ps1` + GERÇEK `make_manifest.py` (çıktı tmp_path; ağ/yükleme YOK).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from test_make_manifest import ONCEKI
from test_yayin_oncesi_suit_Y30_D410 import BETIKLER, _pwsh_gerekli

SURUM = "9.9.9-4b34"
BAYRAK = "PEMF_Y30_DENETIM_KANCASI"


def _kos(tmp_path: Path, ek: list[str], bayrak: bool) -> tuple[subprocess.CompletedProcess, dict]:
    pwsh = _pwsh_gerekli()
    hedef = tmp_path / "suit"
    hedef.mkdir()
    (hedef / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (hedef / "test_tek_yesil.py").write_text("def test_y():\n    assert True\n", encoding="utf-8")
    paket = tmp_path / "paket"
    paket.mkdir()
    (paket / "manifest.json").write_text(json.dumps(ONCEKI), encoding="utf-8")
    argumanlar = f"--dir,{paket},--version,{SURUM},--tag,client-app-v{SURUM},--repo,ornek/pemf-update"
    env = {k: v for k, v in os.environ.items() if k != BAYRAK}
    env.update(PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    if bayrak:
        env[BAYRAK] = "1"
    ek = [x.replace("{HEDEF}", str(hedef)).replace("{PY}", sys.executable) for x in ek]
    r = subprocess.run(
        [pwsh, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(BETIKLER / "katmanli_yayin_hazirla.ps1"),
         f"-ManifestArgs:{argumanlar}", "-Python", sys.executable, *ek],
        cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
    )  # fmt: skip
    return r, json.loads((paket / "manifest.json").read_text(encoding="utf-8"))


def test_KRITIK_PytestOnek_ile_HIC_test_kosmadan_manifest_YAZILMAZ(tmp_path):
    r, manifest = _kos(tmp_path, ["-PytestOnek", "{PY},-c,import sys; sys.exit(0)"], bayrak=False)
    assert manifest.get("version") != SURUM and r.returncode != 0, (
        f"Y30 süiti HİÇ koşmadan (-PytestOnek no-op) manifest yeni sürümle yazıldı (rc={r.returncode}):\n{(r.stdout + r.stderr)[-1200:]}"
    )


def test_KRITIK_Hedef_ile_DARALTILMIS_suitle_manifest_YAZILMAZ(tmp_path):
    r, manifest = _kos(tmp_path, ["-PytestOnek", "{PY},-m,pytest", "-Hedef", "{HEDEF}"], bayrak=False)
    assert manifest.get("version") != SURUM and r.returncode != 0, (
        f"Y30 tek teste daraltıldı ve manifest yazıldı (rc={r.returncode}):\n{(r.stdout + r.stderr)[-1200:]}"
    )


def test_KARSIT_denetim_bayragiyla_kanca_calisir_ve_DAR_SUIT_damgasi_basilir(tmp_path):
    r, manifest = _kos(tmp_path, ["-PytestOnek", "{PY},-m,pytest", "-Hedef", "{HEDEF}"], bayrak=True)
    cikti = r.stdout + r.stderr
    assert r.returncode == 0 and manifest.get("version") == SURUM and "1 passed" in cikti, (
        f"rc={r.returncode}\n{cikti[-1200:]}"
    )
    assert "DAR SUIT" in cikti, "denetim kancası kullanıldı ama çıktı bunu damgalamıyor"
