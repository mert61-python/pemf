# -*- coding: utf-8 -*-
"""4-A devri #4 (Y30) — launcher KATMANLI yayın kanalında da yayın öncesi zorunlu tam süit, manifest üretiminden ÖNCE koşar.

ARIZA: D4.10, Y30'u yalnız `publish_release.ps1`'e (exe / mobil kanalı) bağladı. Launcher katmanlı yayını (`make_manifest.py` + elle GitHub
release) betikli değildi → o hatta süit HİÇ koşmadan manifest üretilip yüklenebiliyordu (4-A §4.5 "Sınır / 4-B'ye").
DÜZELTME: `scripts/katmanli_yayin_hazirla.ps1` — (0) `yayin_oncesi_suit.ps1` (ZORUNLU kip), geçmezse DURUR (atlama anahtarı yok); (1) GERÇEK
`make_manifest.py`. BUILD.md §6 adım 0 bu betiği gösterir.

Ölçüm (gerçek betikler, ağ / yükleme YOK): Y30'a sentetik hedef (`-Hedef`) verilir — kırmızı ya da yeşil tek test. Paket dizininde önceki
manifest (`test_make_manifest.ONCEKI`) durur; GERÇEK `make_manifest.py` koşarsa `version` alanını verilen sürüme çevirir.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from test_make_manifest import ONCEKI
from test_yayin_oncesi_suit_Y30_D410 import BETIKLER, _pwsh_gerekli

SURUM = "9.9.9-y30"


def _kos(tmp_path: Path, kirmizi: bool) -> tuple[subprocess.CompletedProcess, dict]:
    pwsh = _pwsh_gerekli()
    hedef = tmp_path / "suit"
    hedef.mkdir()
    (hedef / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    govde = (
        "def test_kirmizi():\n    assert False, 'Y30-KIRMIZI'\n" if kirmizi else "def test_yesil():\n    assert True\n"
    )
    (hedef / "test_y30_katmanli.py").write_text(govde, encoding="utf-8")
    paket = tmp_path / "paket"
    paket.mkdir()
    (paket / "manifest.json").write_text(json.dumps(ONCEKI), encoding="utf-8")
    argumanlar = f"--dir,{paket},--version,{SURUM},--tag,client-app-v{SURUM},--repo,ornek/pemf-update"
    # 4B-3.4: sentetik -Hedef/-PytestOnek kancası yalnız açık denetim bayrağıyla kabul edilir.
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1", PEMF_Y30_DENETIM_KANCASI="1")
    r = subprocess.run(
        [pwsh, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(BETIKLER / "katmanli_yayin_hazirla.ps1"),
         f"-ManifestArgs:{argumanlar}", "-Python", sys.executable, "-PytestOnek", f"{sys.executable},-m,pytest", "-Hedef", str(hedef)],
        cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
    )  # fmt: skip
    return r, json.loads((paket / "manifest.json").read_text(encoding="utf-8"))


def test_KRITIK_suit_KIRMIZIYKEN_manifest_YAZILMAZ_ve_betik_DURUR(tmp_path):
    r, manifest = _kos(tmp_path, kirmizi=True)
    cikti = r.stdout + r.stderr
    assert "1 failed" in cikti, f"Y30 süiti koşmadı (vakum):\n{cikti[-1500:]}"
    assert r.returncode != 0 and "katmanli yayin DURDU (Y30)" in cikti, f"rc={r.returncode}\n{cikti[-1500:]}"
    assert manifest.get("version") != SURUM, "süit KIRMIZI iken manifest YENİ sürümle yazıldı (Y30 dışı katmanlı yayın)"
    assert "manifest uretiliyor" not in cikti


def test_KARSIT_suit_YESILKEN_GERCEK_make_manifest_kosar(tmp_path):
    r, manifest = _kos(tmp_path, kirmizi=False)
    cikti = r.stdout + r.stderr
    assert r.returncode == 0 and "1 passed" in cikti, f"rc={r.returncode}\n{cikti[-1500:]}"
    assert manifest.get("version") == SURUM, (
        f"süit yeşilken make_manifest koşmadı ya da manifesti yazmadı:\n{cikti[-1500:]}"
    )
