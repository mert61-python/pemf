# -*- coding: utf-8 -*-
"""GERÇEK gitleaks ikilisini bulur — özel kuralları ölçen testlerin TEK bulucusu (D3.02 · B-10.48 · A-69, 2026-10-10).

🔴 ÖLÇÜLEN DURUM: özel kuralları (`.gitleaks.toml` [2.2]) gerçek gitleaks'le ölçen testler yalnız `shutil.which("gitleaks")`
ya da `Path.home()/.cache/pre-commit` arıyordu. Geliştirme makinesinde ikili pre-commit önbelleğinde (`…/golangenv-*/bin/`)
duruyor ama PATH'te değil; CI'ın pytest işi hiç kurmuyordu; yalıtılmış koşucularda HOME sahte → üç ortamda da SKIP. Bu yüzden
`.gitleaks.toml`'daki config.json kuralının `path`ini bozan mutant (`data`→`veri`: gerçek gitleaks'te yakalama 2 → 0) hiçbir
kapıyı kırmızı yapmıyordu.

Arama sırası (İNDİRME YOK): `PEMF_GITLEAKS` (açık yol — bozuksa bulunamadı sayılır, sessizce başka ikiliye düşülmez) → PATH →
pre-commit önbellekleri (`PRE_COMMIT_HOME`, `XDG_CACHE_HOME/pre-commit`, `~/.cache/pre-commit`). Sürüm: `.pre-commit-config.yaml`
`rev` (CI aynı rev'i `pre-commit install-hooks` ile kaynaktan kurar). İkili yoksa varsayılan kipte ATLA; `PEMF_CAPRAZ_KAYNAK_ZORUNLU=1`
ya da `PEMF_GITLEAKS_ZORUNLU=1` (CI) ise DÜŞ.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import capraz
import pytest

ZORUNLU_ORTAM = "PEMF_GITLEAKS_ZORUNLU"
_ADLAR = ("gitleaks.exe", "gitleaks")


def _onbellek_kokleri() -> list[Path]:
    kokler: list[Path] = []
    if os.environ.get("PRE_COMMIT_HOME"):
        kokler.append(Path(os.environ["PRE_COMMIT_HOME"]))
    if os.environ.get("XDG_CACHE_HOME"):
        kokler.append(Path(os.environ["XDG_CACHE_HOME"]) / "pre-commit")
    kokler.append(Path.home() / ".cache" / "pre-commit")
    return kokler


def bul() -> str | None:
    acik = os.environ.get("PEMF_GITLEAKS", "").strip()
    if acik:
        return acik if Path(acik).is_file() else None
    yol = shutil.which("gitleaks")
    if yol:
        return yol
    for kok in _onbellek_kokleri():
        if not kok.is_dir():
            continue
        adaylar = [p for ad in _ADLAR for p in kok.glob(f"*/golangenv-*/bin/{ad}") if p.is_file()]
        if adaylar:
            return str(max(adaylar, key=lambda p: p.stat().st_mtime))
    return None


def zorunlu_mu() -> bool:
    return capraz.ZORUNLU or os.environ.get(ZORUNLU_ORTAM) == "1"


def gerekli() -> str:
    """İkili yolu; yoksa ATLA (varsayılan) ya da DÜŞ (zorunlu kip)."""
    ikili = bul()
    if ikili:
        return ikili
    neden = "gitleaks ikilisi bulunamadi (PEMF_GITLEAKS / PATH / pre-commit onbellegi) — indirme YAPILMAZ"
    if zorunlu_mu():
        pytest.fail(f"zorunlu kip ({ZORUNLU_ORTAM} / PEMF_CAPRAZ_KAYNAK_ZORUNLU) ama {neden}")
    pytest.skip(neden)
