# -*- coding: utf-8 -*-
"""YH D3 — THIRD_PARTY_LICENSES.md npm bölümü TAM (her kilit dosyasının bütün çalışma-zamanı girdileri) ve kopyleft içermez.

ÖLÇÜLEN (YH, 2026-10-22): npm envanteri yalnız çok dillilik kütüphanelerini (5 satır) listeliyordu; react, expo, react-native, vite …
dahil arayüzün 626, sitenin 92, DEMA'nın 206 çalışma-zamanı girdisi atıfsızdı (S-I18N kaydı: "react, expo … HİÇ YOK"). Üretici artık
dört kilit dosyasının bütün geliştirme-dışı girdilerini kullanan yüzeyle yazar (782 tekil ad + sürüm). Kopyleft kararı SPDX İFADESİYLE
verilir: `node-forge` `(BSD-3-Clause OR GPL-2.0)` seçim hakkı tanır → kopyleft DEĞİL (eski alt-dize bakışı onu GPL sayardı).

Kapı kilit dosyalarını okur (her yerde izlenir) → CI'da da koşar, `base-deps.zip` GEREKMEZ, atlama YOK:
  · dosyadaki npm bölümü üreticinin çıktısıyla BİREBİR (kilit değişip envanter unutulursa kırmızı);
  · üreticiden BAĞIMSIZ sayım: her kilitteki her çalışma-zamanı (ad, sürüm) satırda ve "Kullanan" sütunu o yüzeyi anıyor;
  · npm kopyleft kümesi BOŞ; lisansı boş girdi yok; SPDX önceliği (WITH > AND > OR) birim sınaması.
Hukuki değerlendirme (MPL-2.0 dosya düzeyi, CC-BY-4.0 / OFL-1.1 atıf koşulları) [SAHİBE] — kapı yalnız eksiksizliği ve kopylefti ölçer.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
NOTICE = KOK / "THIRD_PARTY_LICENSES.md"
KILITLER = {
    "arayüz": KOK / "apps" / "ui" / "package-lock.json",
    "site": KOK / "apps" / "web" / "package-lock.json",
    "DEMA": KOK / "dema-terapi-simülatörü" / "package-lock.json",
    "launcher": KOK / "launcher" / "app" / "package-lock.json",
}


def _uretec():
    sys.path.insert(0, str(KOK / "scripts"))
    import lisans_envanteri_uret as l

    return l


def _npm_bolumu_dosyada() -> str:
    metin = NOTICE.read_text(encoding="utf-8")
    m = re.search(r"^### [^\n]*\(npm\)[^\n]*$", metin, re.M)
    assert m, "THIRD_PARTY_LICENSES.md'de npm bölümü YOK"
    return metin[m.start() :].strip()


def test_KRITIK_npm_bolumu_URETECIN_ciktisiyla_BIREBIR():
    beklenen = _uretec()._npm_bolumu().strip()
    assert beklenen, "üretici npm bölümü üretmedi (kilit dosyaları okunamadı)"
    assert _npm_bolumu_dosyada() == beklenen, (
        "THIRD_PARTY_LICENSES.md npm bölümü kilit dosyalarıyla güncel DEĞİL → `python scripts/lisans_envanteri_uret.py` "
        "(base-deps.zip gerekir; yalnız npm bölümü değişiyorsa üretici çıktısı birebir yapıştırılabilir)"
    )


def test_KRITIK_her_kilitteki_calisma_zamani_girdisi_KULLANAN_yuzeyiyle_listede():
    """Üreticiden bağımsız sayım (üretici bir kilidi / girdiyi düşürürse birebir karşılaştırma kör kalırdı)."""
    satirlar = {}
    for s in _npm_bolumu_dosyada().splitlines():
        m = re.match(r"^\| `([^`]+)` \| ([^|]+?) \| ([^|]+?) \| ([^|]+?) \|$", s)
        if m:
            satirlar[(m.group(1), m.group(2))] = {x.strip() for x in m.group(4).split(",")}
    eksik, toplam = [], 0
    for yuzey, kilit in KILITLER.items():
        assert kilit.exists(), f"kilit dosyası yok: {kilit}"
        for yol, p in (json.loads(kilit.read_text(encoding="utf-8")).get("packages") or {}).items():
            if not yol or p.get("dev") or p.get("devOptional") or p.get("link"):
                continue
            toplam += 1
            anahtar = (yol.rsplit("node_modules/", 1)[-1], str(p.get("version")))
            if yuzey not in satirlar.get(anahtar, set()):
                eksik.append(f"{yuzey}:{anahtar[0]}@{anahtar[1]}")
    assert toplam > 800, f"kilitlerden okunan çalışma-zamanı girdisi şüpheli az: {toplam}"
    assert not eksik, f"NOTICE'ta olmayan (ya da yüzeyi yazılmamış) npm girdileri ({len(eksik)}): {eksik[:15]}"
    for zorunlu in ("react", "expo", "react-native", "i18next", "react-router-dom"):
        assert any(a == zorunlu for a, _ in satirlar), f"`{zorunlu}` npm envanterinde yok"


def test_KRITIK_npm_envanterinde_KOPYLEFT_yok_ve_lisanssiz_girdi_yok():
    l = _uretec()
    assert l.npm_kopyleft() == [], (
        f"npm'de kopyleft bileşen (kaynak açma yükümlülüğü) — bilinçli karar gerekir [SAHİBE]: {l.npm_kopyleft()}"
    )
    bos = [(a, s) for a, s, li in l.npm_envanteri() if "doğrulanmadı" in li]
    assert not bos, f"kilitte lisansı BOŞ npm girdileri: {bos}"


@pytest.mark.parametrize(
    "ifade, beklenen",
    [
        ("MIT", False),
        ("(BSD-3-Clause OR GPL-2.0)", False),  # node-forge: seçim hakkı
        ("GPL-2.0 AND MIT", True),
        ("GPL-2.0 AND (MIT OR BSD-3-Clause)", True),  # öncelik: parantezsiz OR'a bölmek bunu YANLIŞ "temiz" sayardı
        ("(MIT AND GPL-3.0) OR BSD-2-Clause", False),
        ("MIT AND GPL-3.0 OR BSD-2-Clause", False),  # AND, OR'dan önce bağlar
        ("GPL-2.0-only WITH Classpath-exception-2.0", True),
        ("LGPL-3.0-or-later", False),
        ("AGPL-3.0 OR GPL-3.0", True),
        ("MPL-2.0", False),
        ("MIT OR (GPL-2.0", True),  # ayrıştırılamaz → metnin tamamı → güvenli taraf
    ],
)
def test_spdx_ifadesi_ONCELIK_ve_secim_hakki(ifade, beklenen):
    assert _uretec().spdx_kopyleft_mu(ifade) is beklenen, ifade
