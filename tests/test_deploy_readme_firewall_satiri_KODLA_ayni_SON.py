# -*- coding: utf-8 -*-
"""SON-A2.54 (22 · A2b) — `deploy/README.md` kurulum adımındaki güvenlik duvarı satırı `scripts/setup_services.ps1`'in GERÇEKTEN kurduğu
kuralları söyler: API (TCP, varsayılan 8000 — `PEMF_API_PORT`), keşif (UDP 5051) ve broker (TCP 1883) — 1883 kuralı YALNIZ hotspot alt
ağından (`$Hotspot`) açılır ve ESP kapalıyken de kurulur (`Ensure-PemfMosquittoFirewallRule`: oluşturma dalı `$EspEtkin`'e bağlı değil).
Eski satır "Firewall: TCP 8000, TCP 1883, UDP 5051." 1883'ün kaynak kısıtını söylemiyordu; D67 §5 SONRAKİ öncülü ("ESP kapalıyken 1883 kuralı
kurulmaz") ise kodla çelişiyor — satır o öncülle "1883'ü sil" diye düzeltilirse YANLIŞ olur. Kapı iki yönü de tutar."""

from __future__ import annotations

import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]


def _kod() -> str:
    return (KOK / "scripts" / "setup_services.ps1").read_text(encoding="utf-8")


def _hotspot_alt_agi() -> str:
    m = re.search(r'^\s*\$Hotspot\s*=\s*"([0-9./]+)"', _kod(), re.M)
    assert m, "aparat: setup_services.ps1'de $Hotspot tanımı bulunamadı"
    return m.group(1)


def _firewall_satiri() -> str:
    satirlar = [
        s
        for s in (KOK / "deploy" / "README.md").read_text(encoding="utf-8").splitlines()
        if re.match(r"\s*-\s*Firewall:", s)
    ]
    assert len(satirlar) == 1, f"aparat: deploy/README.md'de tek 'Firewall:' satırı bekleniyordu ({len(satirlar)})"
    return satirlar[0]


def test_kod_1883_kuralini_ESP_kapaliyken_de_YALNIZ_hotspot_alt_agindan_kurar():
    kod = _kod()
    govde = kod[kod.index("function Ensure-PemfMosquittoFirewallRule") :]
    govde = govde[: govde.index("\nfunction ", 10)] if "\nfunction " in govde[10:] else govde
    olustur = re.findall(r"New-NetFirewallRule[^\n]*-LocalPort 1883[^\n]*", govde)
    gercek = [s for s in olustur if "-ErrorAction Stop" in s]  # elle-kur ipucu dizgesi değil, gerçek çağrı
    assert gercek, "aparat: 1883 kuralını oluşturan gerçek çağrı bulunamadı"
    assert all(_hotspot_alt_agi() in s for s in gercek), f"1883 kuralı hotspot alt ağı dışına açılıyor: {gercek}"
    # oluşturma dalının koşulu ESP bayrağına bağlı değil (ESP kapalıyken de kurulur)
    kosul = re.search(r"if \((\$Mevcut\.Count[^\n]*)\)\s*\{\s*\n\s*try \{\s*\n\s*New-NetFirewallRule[^\n]*1883", govde)
    assert kosul and "EspEtkin" not in kosul.group(1), (
        "1883 kuralının oluşturma koşulu değişti — README satırını yeniden ölç"
    )


def test_README_firewall_satiri_1883_kaynak_kisitini_ve_uc_kurali_SOYLER():
    satir = _firewall_satiri()
    for parca in ("8000", "1883", "5051"):
        assert parca in satir, f"README güvenlik duvarı satırında {parca} yok: {satir!r}"
    assert _hotspot_alt_agi() in satir, (
        f"README 1883 kuralının kaynak kısıtını ({_hotspot_alt_agi()}) söylemiyor — kod 1883'ü YALNIZ hotspot alt ağından açar: {satir!r}"
    )
