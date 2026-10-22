# -*- coding: utf-8 -*-
"""YLI-A1.1 (YLI bağımsız inceleme) · Y168 "her yerde aynı": İngilizce kataloglarda AI modülü eski kısa adıyla ("Petri" = eski "Petri Well")
ANILMAZ — launcher (PEMF Vet Client) profil kartları dahil.

YH A6'nın kapısı (`test_YH_A6_ai_modul_adlari_EN_Y168.py`) yalnız "petri well / Petri module|card|analysis|photo|plate|target" biçimlerini
arıyor; launcher'daki liste biçimi ("Petri, histopathology, kidney and phantom AI models" · "Research models — petri, histopathology, kidney,
phantom") kapıdan geçiyor. Kural (YH A6'nın kendi kuralı): modülün ADINI anan her EN metin yeni adı taşır, kısaltma dahil; tekil kap
("petri dish(es)", "petri diameter") nesnedir, aynen kalır.

Kalıcı kapı adayı: `tests/` altına taşınabilir (kök, `launcher/i18n/en.json`'u bulana dek yukarı aranır).
"""

from __future__ import annotations

import json
import re
from pathlib import Path


def _kok() -> Path:
    for p in Path(__file__).resolve().parents:
        if (p / "launcher" / "i18n" / "en.json").is_file() and (p / "apps" / "ui").is_dir():
            return p
    raise AssertionError("depo kökü bulunamadı")


KOK = _kok()
EN_KATALOGLAR = [
    *sorted((KOK / "apps/ui/src/i18n/en").glob("*.json")),
    *sorted((KOK / "apps/web/src/i18n/en").glob("*.json")),
    KOK / "apps/backend/i18n/en.json",
    KOK / "launcher/i18n/en.json",
    KOK / "dema-terapi-simülatörü/src/i18n/en.json",
]
#: "petri" sözcüğü modül kısa adı olarak (ardından tekil kap / çap gelmiyorsa).
PETRI_KISA = re.compile(r"(?i)\bpetri\b(?!\s+(?:dish|dishes|diameter)\b)")


def _duz(o, onek=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _duz(v, f"{onek}.{k}" if onek else k)
    else:
        yield onek, o


def _yaprak(yol: Path) -> dict:
    return dict(_duz(json.loads(yol.read_text(encoding="utf-8"))))


def test_EN_kataloglarda_modul_eski_kisa_adiyla_PETRI_anilmaz():
    assert len(EN_KATALOGLAR) > 20 and all(p.is_file() for p in EN_KATALOGLAR)
    kalan = [
        f"{p.relative_to(KOK).as_posix()}:{k}: {v[:100]!r}"
        for p in EN_KATALOGLAR
        for k, v in _yaprak(p).items()
        if isinstance(v, str) and PETRI_KISA.search(v)
    ]
    assert not kalan, "Y168: modül eski kısa adıyla anılıyor (yeni ad 'Well Plate'):\n" + "\n".join(kalan)


def test_launcher_arastirma_profili_yeni_adlarla_TR_DEGISMEDI():
    en = _yaprak(KOK / "launcher/i18n/en.json")
    tr = _yaprak(KOK / "launcher/i18n/tr.json")
    for k in ("ui.kilavuz.profiles.p03.does", "ui.profilMeta.research.aciklama"):
        assert "well plate" in en[k].lower() and "tumor phantom" in en[k].lower(), (k, en[k])
    # Türkçe DEĞİŞMEZ (Y168 yalnız İngilizce)
    assert tr["ui.kilavuz.profiles.p03.does"] == (
        "Petri, histopatoloji, böbrek ve fantom yapay zekâ modelleri; örnek/veri kaydı ve geçmiş. Cihaz İÇERMEZ."
    )
    assert tr["ui.profilMeta.research.aciklama"] == "Araştırma modelleri — petri, histopatoloji, böbrek, fantom"
