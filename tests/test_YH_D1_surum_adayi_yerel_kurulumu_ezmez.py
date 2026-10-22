# -*- coding: utf-8 -*-
"""YH D1 — yayın adayı sürüm numaraları bu makinedeki kurulumu yayındakiyle EZDİRMEZ.

Soru (istem D1): versions.json yükseltilince (aday: app 1.9.51 · launcher 1.9.52 · mobil 2.3.35 / 42) bu makinedeki launcher (1.9.51)
ve yerel kurulum (`installed_packages.json`, app 1.9.50) açılışta yayındakini indirip yerel kurulumu ezer mi?

ÖLÇÜLEN (kod okuması + yayındaki manifest kopyası `pemf-app-packages/manifest.json`):
  · launcher kendini yalnız `is_newer(manifest.launcher.version, kendi)` iken günceller (`launcher/core/src/manifest.rs::is_newer`);
  · runtime katmanları SÜRÜMLE değil SHA ile karşılaştırılır (`flow.rs::pending_updates`: `installed_packages.json` ↔ manifest) —
    sürüm numarası bu karara GİRMEZ; zorunlu güncelleme yalnız `min_supported_version` kurulu sürümden yeniyse (yayında: YOK);
  · backend EXE kanalı yalnız `update_manager._is_newer(yayindaki, kurulu)` iken güncelleme önerir;
  · telefon yalnız manifest `versionCode` kendisininkinden BÜYÜKSE APK indirir.
Yani aday numaralar yayındakinden KÜÇÜK olmadıkça (ve `min_supported_version` adayın üstüne çıkmadıkça) hiçbir kanal yayındakini
"daha yeni" saymaz. Kapı bu iki koşulu kalıcı tutar; ölçü fonksiyonu ürünün KENDİ karşılaştırıcısıdır (`_is_newer`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]


def _oku(yol: str) -> dict:
    return json.loads((KOK / yol).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def is_newer():
    from servers.update_manager import _is_newer

    return _is_newer


def _ciftler() -> list[tuple[str, str, str]]:
    v, m = _oku("versions.json"), _oku("pemf-app-packages/manifest.json")
    android = (m.get("mobile") or {}).get("android") or {}
    return [
        ("app (backend)", str(m["version"]), v["backend"]),
        ("launcher", str(m["launcher"]["version"]), v["launcher"]),
        ("mobil", str(android.get("version", "0.0.0")), v["mobile"]["name"]),
    ]


def test_KRITIK_aday_surumler_YAYINDAKINDEN_kucuk_degil(is_newer):
    geride = [f"{ad}: yayındaki {yay} > aday {aday}" for ad, yay, aday in _ciftler() if is_newer(yay, aday)]
    assert not geride, (
        f"aday sürüm yayındakinden ESKİ → o kanal yayındakini 'daha yeni' sayıp indirir, yerel kurulumu EZER: {geride}"
    )


def test_KRITIK_android_versionCode_yayindakinden_kucuk_degil():
    v, m = _oku("versions.json"), _oku("pemf-app-packages/manifest.json")
    yay = int(((m.get("mobile") or {}).get("android") or {}).get("versionCode", 0))
    assert int(v["mobile"]["androidVersionCode"]) >= yay, (
        "versionCode geriledi: telefon yayındaki APK'yı yeni sayar (Play de reddeder)"
    )


def test_KRITIK_min_supported_version_adayi_ZORLAMAZ(is_newer):
    v, m = _oku("versions.json"), _oku("pemf-app-packages/manifest.json")
    asgari = m.get("min_supported_version")
    assert not asgari or not is_newer(str(asgari), v["backend"]), (
        f"yayındaki min_supported_version ({asgari}) aday app sürümünden ({v['backend']}) yeni → launcher yerel kurulumu ZORLA günceller"
    )


def test_KARSIT_KANIT_olcu_GERIDE_kalan_adayi_yakalar(is_newer):
    """Ölçücü kör değil: aday yayındakinden bir yama eski olsaydı kapı kırmızı verirdi."""
    assert is_newer("1.9.50", "1.9.49") and not is_newer("1.9.50", "1.9.51") and not is_newer("1.9.51", "1.9.51")
