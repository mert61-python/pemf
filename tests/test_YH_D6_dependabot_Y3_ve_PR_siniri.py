# -*- coding: utf-8 -*-
"""YH D6 (A-42 kalanı, Y3) — Dependabot torch / torchvision / onnx için HİÇ PR açmaz; PR sınırları ilk açılışta dalga yaratmaz.

ÖLÇÜLEN (YH, 2026-10-22; `.github/dependabot.yml` HEAD): Y3 (sahip kararı: onnx 1.15.0 / torch 2.1.2+cpu pinleri AYNEN, yükseltme YASAK)
dosyada karşılıksızdı — torch / torchvision yalnız major / minor SÜRÜM güncellemesinde dışlanıyor (yama ve güvenlik PR'ı açılabilir), onnx
HİÇ dışlanmıyordu; `/docker` ve `/ai_service` pip ekosistemleri (ikisi de onnx, docker torch da sabitliyor) hiç dışlamasızdı. PR sınırları
toplamı ~50 (github-actions sınırsız varsayılan) — Dependabot bu depoda hiç koşmadığı için açıldığında bir kerede PR dalgası (her biri CI +
Vercel önizlemesi) açardı. Sahip kararı 2026-10-13: dışlama + PR sınırları yayın push'undan önce dosyada (push bu oturumda YOK).

Kapı (yalnız dosya): her pip ekosisteminde üç paket `update-types`SIZ (= her güncelleme türü) dışlı; her ekosistemin AÇIK sınırı ≤ 3, toplam
≤ 15; mevcut koordinasyon dışlamaları (expo / react / react-native major, numpy / ultralytics major) korunur.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="pyyaml yok")

KOK = Path(__file__).resolve().parents[1]
GUNCELLEMELER = yaml.safe_load((KOK / ".github" / "dependabot.yml").read_text(encoding="utf-8"))["updates"]
Y3 = ("torch", "torchvision", "onnx")


def _dislamalar(u: dict) -> dict[str, list | None]:
    return {i["dependency-name"]: i.get("update-types") for i in u.get("ignore") or []}


def test_KRITIK_Y3_her_pip_ekosisteminde_torch_torchvision_onnx_TAMAMEN_disli():
    pipler = [u for u in GUNCELLEMELER if u["package-ecosystem"] == "pip"]
    assert {u["directory"] for u in pipler} >= {"/", "/docker", "/ai_service"}, [u["directory"] for u in pipler]
    eksik = []
    for u in pipler:
        d = _dislamalar(u)
        for paket in Y3:
            if paket not in d:
                eksik.append(f"{u['directory']}:{paket} dışlanmamış")
            elif d[paket]:
                eksik.append(f"{u['directory']}:{paket} yalnız {d[paket]} türünde dışlı (yama / güvenlik PR'ı açılır)")
    assert not eksik, f"Y3 (onnx / torch pinleri AYNEN) Dependabot'ta karşılıksız: {eksik}"


def test_KRITIK_PR_sinirlari_ACIK_ve_kucuk():
    sinirlar = {f"{u['package-ecosystem']}:{u['directory']}": u.get("open-pull-requests-limit") for u in GUNCELLEMELER}
    acik_degil = [k for k, v in sinirlar.items() if v is None]
    assert not acik_degil, f"sınırı yazılmamış ekosistem (Dependabot varsayılanı 5): {acik_degil}"
    buyuk = {k: v for k, v in sinirlar.items() if v > 3}
    assert not buyuk, f"ekosistem başına sınır > 3 (ilk açılışta PR dalgası): {buyuk}"
    assert sum(sinirlar.values()) <= 15, f"toplam PR sınırı {sum(sinirlar.values())} > 15: {sinirlar}"


def test_koordinasyon_dislamalari_KORUNUR():
    kok = next(u for u in GUNCELLEMELER if u["package-ecosystem"] == "pip" and u["directory"] == "/")
    ui = next(u for u in GUNCELLEMELER if u["package-ecosystem"] == "npm" and u["directory"] == "/apps/ui")
    major = ["version-update:semver-major"]
    assert _dislamalar(kok).get("numpy") == major and _dislamalar(kok).get("ultralytics") == major
    assert all(_dislamalar(ui).get(p) == major for p in ("expo", "react", "react-native")), _dislamalar(ui)
