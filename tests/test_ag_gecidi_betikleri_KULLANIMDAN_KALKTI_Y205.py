# -*- coding: utf-8 -*-
"""Y205 · S-D5.15 (sahip, 2026-10-28) — eski "ağ geçidi" betikleri (`scripts/install_mosquitto.ps1`, `scripts/setup_gateway.ps1`)
emekliye ayrıldı: SİLİNMEZ (sahada eskiden koşturulmuş izlerin temizliği sahibin işi), başlıkta ve `scripts/README.md`'de
"KULLANIMDAN KALKTI" yazar, desteklenen hiçbir yol onları çağırmaz / pakete koymaz. `install_mosquitto.ps1` için çağrı / paket
kapısı D5 H-2'dedir; burada aynı ölçüt `setup_gateway.ps1` için koşar. Başlık eklenirken BOM + CRLF korunur (PS 5.1 BOM'suz UTF-8'i
ANSI okur — Türkçe yorum bozulurdu).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from test_install_mosquitto_KULLANIMDAN_KALKMIS_desteklenen_yola_BAGLANMAZ_D5H2 import _add_scripts, _kod_satirlari

KOK = Path(__file__).resolve().parents[1]
EMEKLI = ("install_mosquitto.ps1", "setup_gateway.ps1")


@pytest.mark.parametrize("ad", EMEKLI)
def test_KULLANIMDAN_KALKAN_betik_SILINMEDI_basligi_ve_kodlamasi_KORUNUR(ad):
    yol = KOK / "scripts" / ad
    assert yol.is_file(), f"{ad} SİLİNMİŞ — Y205: emekliye ayrılır, silinmez"
    ham = yol.read_bytes()
    assert ham.startswith(b"\xef\xbb\xbf"), f"{ad}: UTF-8 BOM kayboldu (PS 5.1 Türkçe yorumu bozar)"
    assert b"\n" not in ham.replace(b"\r\n", b""), f"{ad}: CRLF bozuldu (çıplak LF var)"
    bas = "\n".join(ham[3:].decode("utf-8").split("\r\n")[:12])
    assert "KULLANIMDAN KALKTI" in bas and "Y205" in bas, f"{ad}: başlıkta KULLANIMDAN KALKTI (Y205) notu yok:\n{bas}"


def _readme_satiri(ad: str) -> str:
    satirlar = [
        s
        for s in (KOK / "scripts" / "README.md").read_text(encoding="utf-8").splitlines()
        if s.startswith(f"| `{ad}` |")
    ]
    assert len(satirlar) == 1, f"aparat: scripts/README.md'de `{ad}` için tek tablo satırı bekleniyordu: {satirlar}"
    return satirlar[0]


def test_README_iki_betigi_KULLANIMDAN_KALKTI_diye_isaretler_servis_betigi_DESTEKLENIR_kalir():
    for ad in EMEKLI:
        assert "KULLANIMDAN KALKTI" in _readme_satiri(ad), (
            f"README `{ad}` satırı emekliliği söylemiyor: {_readme_satiri(ad)!r}"
        )
    # aynı satırı paylaştığı servis betiği desteklenir — emeklilik notu ona taşmamalı
    assert "KULLANIMDAN" not in _readme_satiri("install_mosquitto_service.ps1")


def test_setup_gateway_desteklenen_yola_BAGLANMAZ():
    assert not [s for s in _add_scripts() if re.search(r"setup_gateway\.ps1", s, re.I)], (
        "launcher paketi setup_gateway.ps1 taşıyor"
    )
    kumeler = [
        (KOK / "build_tools", ("*.iss", "*.py", "*.ps1")),
        (KOK / "scripts", ("*.ps1", "*.psm1", "*.py")),
        (KOK / "launcher" / "core" / "src", ("*.rs",)),
        (KOK / "launcher" / "app" / "src", ("*.rs",)),
        (KOK / "launcher" / "app" / "windows", ("*.nsi", "*.nsh")),
        (KOK / "apps" / "backend", ("*.py",)),
        (KOK / ".github" / "workflows", ("*.yml", "*.yaml")),
    ]
    dosyalar = sorted(
        {
            p
            for kok, desenler in kumeler
            for d in desenler
            for p in kok.rglob(d)
            if "node_modules" not in p.parts and p.name != "setup_gateway.ps1"
        }
    )
    assert any(p.suffix == ".iss" for p in dosyalar) and any(p.suffix == ".rs" for p in dosyalar), (
        "aparat: kaynaklar bulunamadı"
    )
    bulgu = [
        f"{p.relative_to(KOK)}:{i}: {s.strip()[:140]}"
        for p in dosyalar
        for i, s in _kod_satirlari(p)
        if re.search(r"setup_gateway\.ps1", s, re.I)
    ]
    assert not bulgu, "KULLANIMDAN KALKMIŞ setup_gateway.ps1 desteklenen bir yoldan çağrılıyor:\n  " + "\n  ".join(
        bulgu
    )
