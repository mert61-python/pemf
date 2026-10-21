# -*- coding: utf-8 -*-
"""YH A6 · Y168 (çeviri onay listesi §7, sahip 2026-10-21): AI modül adlarının İngilizcesi terminolojiye uydurulur — Phantom Tumor → Tumor
Phantom · Petri Well → Well Plate · Cat Organ → Feline Organ; arayüz, sunucu (ileti + PDF), site — HER YERDE AYNI. Türkçe DEĞİŞMEZ.

Kural (uygulanan): modülün ADINI anan her İngilizce metin yeni adı taşır — kısaltma dahil ("the Petri module", "Petri card", "Start Petri
Analysis", "AI Pro — Phantom / Petri …"); modülün nesnesi olan çok kuyucuklu plaka "well plate" ("petri plate / photo / target" → "well
plate …"). Tekil kap ve fantom nesnesi aynen kalır ("Petri diameter", "Single petri dishes", "Not a petri dish", "phantom photo").
"""

from __future__ import annotations

import json
import re
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent

#: Bütün İngilizce kataloglar (arayüz, site, sunucu, launcher, DEMA).
EN_KATALOGLAR = [
    *sorted((KOK / "apps/ui/src/i18n/en").glob("*.json")),
    *sorted((KOK / "apps/web/src/i18n/en").glob("*.json")),
    KOK / "apps/backend/i18n/en.json",
    KOK / "launcher/i18n/en.json",
    KOK / "dema-terapi-simülatörü/src/i18n/en.json",
]
ESKI = re.compile(
    r"(?i)phantom tumou?r|petri well|cat organ|\bPetri (?:module|card|analysis|photo|plate|target)\b|Phantom ?/ ?Petri|Phantom or Petri"
)


def _duz(o, onek=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _duz(v, f"{onek}.{k}" if onek else k)
    else:
        yield onek, o


def _yaprak(yol: Path) -> dict:
    return dict(_duz(json.loads(yol.read_text(encoding="utf-8"))))


def test_eski_ingilizce_modul_adi_HICBIR_EN_katalogda_yok():
    assert len(EN_KATALOGLAR) > 20 and all(p.is_file() for p in EN_KATALOGLAR)
    kalan = [
        f"{p.relative_to(KOK).as_posix()}:{k}: {v[:90]!r}"
        for p in EN_KATALOGLAR
        for k, v in _yaprak(p).items()
        if isinstance(v, str) and ESKI.search(v)
    ]
    assert not kalan, "Y168 öncesi İngilizce AI modül adı kaldı:\n" + "\n".join(kalan)


def test_yeni_adlar_arayuz_ve_sunucuda_AYNI_turkce_DEGISMEDI():
    ui_en = _yaprak(KOK / "apps/ui/src/i18n/en/ai.json")
    ui_tr = _yaprak(KOK / "apps/ui/src/i18n/tr/ai.json")
    sv_en = _yaprak(KOK / "apps/backend/i18n/en.json")
    sv_tr = _yaprak(KOK / "apps/backend/i18n/tr.json")
    beklenen = {  # (arayüz anahtarı, sunucu anahtarı): (EN, TR)
        ("modul.fantomTumor.ad", "ai.model.fantom"): ("Tumor Phantom", "Fantom Tümör"),
        ("modul.petriKuyu.ad", "ai.model.petri"): ("Well Plate", "Petri Kuyu"),
        ("modul.kediOrgan.ad", "ai.model.kedi"): ("Feline Organ", "Kedi Organ"),
    }
    for (ui, sv), (en, tr) in beklenen.items():
        assert ui_en[ui] == sv_en[sv] == en, (ui, sv, ui_en[ui], sv_en[sv])
        assert ui_tr[ui] == sv_tr[sv] == tr, (ui, sv, ui_tr[ui], sv_tr[sv])
    assert ui_en["fantom.baslik"] == "Tumor Phantom Analysis"
    assert ui_en["petri.baslik"] == "Well Plate Analysis"
    assert ui_en["organ.baslik"] == "Feline Organ Localization"
    # sunucunun petri reddi iletisi kullanıcıyı doğru modüle yollar (modül adı ekranda göründüğü gibi)
    assert "'Tumor Phantom' module" in sv_en["ai.hata.petriPlakaDegil"]
    assert "'Tumor Phantom' module" in sv_en["ai.hata.petriGeometriYok"]
    assert "Well Plate module" in sv_en["ai.hata.petriGeometriYok"]


def test_site_arastirma_profili_yeni_adlar():
    site = _yaprak(KOK / "apps/web/src/i18n/en/icerik.json")
    assert site["profil.arastirma.ic1"].startswith("Tumor phantom")
    assert site["profil.arastirma.ic2"].startswith("Well plate")
    assert "tumor phantom" in site["sss.arastirma.a"] and "well plate analysis" in site["sss.arastirma.a"]
