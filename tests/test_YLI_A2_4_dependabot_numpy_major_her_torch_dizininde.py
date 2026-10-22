# -*- coding: utf-8 -*-
"""YLI-A2.4 — Dependabot `numpy` / `ultralytics` MAJOR dışlaması yalnız `pip:/`te; aynı pinleri taşıyan `/docker` (torch 2.1.2+cpu · numpy
1.26.4 · onnx 1.15.0 · ultralytics 8.4.47) ve `/ai_service` (numpy 1.26.4 · onnx 1.15.0 · ultralytics 8.4.47) numpy 2.x / ultralytics major
PR'ı alır.

ÖLÇÜLEN (A2, HEAD 957ba225): `.github/dependabot.yml` `pip:/` → `numpy` + `ultralytics` `version-update:semver-major` dışlı, gerekçe
"KRİTİK: torch 2.1.2 numpy<2 ister" (requirements.txt aynı notu taşır: ">=2.0 KIRAR"). `pip:/docker` ve `pip:/ai_service` blokları yalnız
torch / torchvision / onnx'i dışlıyor (YH D6). YH D6 kapısı numpy / ultralytics'i YALNIZ `/` için denetliyor.

Kapı (yalnız dosya): her pip ekosisteminin dizinindeki requirements dosyası numpy ya da ultralytics SABİTLİYORSA o ekosistemde ilgili paket en az
major'da dışlı; Y3 üçlüsü ve PR sınırları YH D6 kapısında kalır.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="pyyaml yok")

KOK = next(p for p in Path(__file__).resolve().parents if (p / "versions.json").exists())
GUNCELLEMELER = yaml.safe_load((KOK / ".github" / "dependabot.yml").read_text(encoding="utf-8"))["updates"]
KOORDINELI = ("numpy", "ultralytics")  # torch 2.1.2 numpy<2 ister; ultralytics major torch / numpy tabanını taşır
_SATIR = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*==", re.M)


def _sabitli_paketler(dizin: str) -> set[str]:
    d = KOK / dizin.strip("/")
    adlar: set[str] = set()
    for f in d.glob("requirements*.txt"):
        adlar |= {m.group(1).lower() for m in _SATIR.finditer(f.read_text(encoding="utf-8"))}
    return adlar


def test_KRITIK_numpy_ultralytics_sabitleyen_HER_pip_dizininde_major_disli():
    eksik = []
    for u in (u for u in GUNCELLEMELER if u["package-ecosystem"] == "pip"):
        sabitli = _sabitli_paketler(u["directory"])
        dislama = {i["dependency-name"]: i.get("update-types") for i in u.get("ignore") or []}
        for paket in KOORDINELI:
            if paket not in sabitli:
                continue
            tur = dislama.get(paket, "YOK")
            if tur == "YOK" or (tur and "version-update:semver-major" not in tur):
                eksik.append(f"{u['directory']}:{paket} (dışlama: {tur})")
    assert not eksik, f"numpy<2 / ultralytics koordinasyonu bu pip dizinlerinde karşılıksız — major PR açılır: {eksik}"


def test_KARSIT_olcu_KOR_degil_dizinlerde_sabitler_gercekten_var():
    assert {"numpy", "ultralytics", "torch"} <= _sabitli_paketler("/docker")
    assert {"numpy", "ultralytics"} <= _sabitli_paketler("/ai_service")
    assert {"numpy", "ultralytics"} <= _sabitli_paketler("/")
