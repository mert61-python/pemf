# -*- coding: utf-8 -*-
"""YLI-A3.9 (L2 / L3 · i18n K-5) — LN'nin eklediği kart yazılımı (firmware / yakma) uyarıları kritik anahtar listesinde olmalı.

`i18n/kritik-anahtarlar.json` türleri: `firmware` = "firmware bantları (FW-PAKET, FW-KIMLIK), STM uyumu, yakma". İkiz metin
`rust.hata.guncellemeSeansSuruyor` (seans sürerken güncelleme ertelenir) listede; yakma ikizi `rust.hata.guncellemeYakmaSuruyor` ve
kapanış / geri alma uyarıları listede DEĞİL → K-5'in "anlam birebir, iki dilde test" güvencesi bunlara uygulanmaz."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[2]
if not (KOK / "i18n").is_dir():
    KOK = Path(__file__).resolve().parents[1]

BEKLENEN = {
    "rust.hata.guncellemeYakmaSuruyor": "launcher/app/src/main.rs",
    "rust.hata.guncellemeFirmwareUyumsuz": "launcher/app/src/main.rs",
    "ui.kapanisYakmaBekleniyor": "launcher/app/ui/index.html",
    "ui.rtRollbackFirmware": "launcher/app/ui/index.html",
}


def _deger(katalog: dict, anahtar: str):
    d = katalog
    for p in anahtar.split("."):
        d = d.get(p) if isinstance(d, dict) else None
    return d


@pytest.mark.parametrize("anahtar", sorted(BEKLENEN))
def test_KRITIK_A3_9_firmware_yakma_uyarisi_kritik_listede(anahtar):
    kritik = json.loads((KOK / "i18n" / "kritik-anahtarlar.json").read_text(encoding="utf-8"))
    girdi = [x for x in kritik["anahtarlar"] if isinstance(x, dict) and x.get("anahtar") == anahtar]
    tr = json.loads((KOK / "launcher" / "i18n" / "tr.json").read_text(encoding="utf-8"))
    en = json.loads((KOK / "launcher" / "i18n" / "en.json").read_text(encoding="utf-8"))
    assert _deger(tr, anahtar) and _deger(en, anahtar), f"{anahtar} iki katalogda dolu değil"
    assert girdi, f"{anahtar} (kart yazılımı / yakma uyarısı) kritik anahtar listesinde DEĞİL"
    assert girdi[0].get("tur") == "firmware" and girdi[0].get("yuzey") == "launcher", girdi[0]
