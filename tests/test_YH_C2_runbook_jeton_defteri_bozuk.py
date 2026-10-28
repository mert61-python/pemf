# -*- coding: utf-8 -*-
"""YH C2 — `jeton_bekleyen.json` (yolda kalan ödeme defteri) okunamaz bulunursa içerik karantina dosyasına (`<defter>` + `DEFTER_KARANTINA_EKI`)
eklenir; bu yol 10-19 kararından (K8: çevrimdışı analiz / eksi bakiye KALDIRILDI) SONRA da canlıdır (defter yalnız "yolda kalan ödeme" için durur —
davranış kapısı `test_jeton_defteri_YAZIM_ORTASINDA_olumde_KAYIP_YOK_4B14.py`). Sahada dosyayı gören teknik kişi için elle inceleme yolu RUNBOOK'ta
TEK satırdır: dosya adı (kaynaktaki sabitle AYNI), SİLMEYİN, teknik destek, veriyi silmeyen uzlaştırma; çevrimdışı analiz / eksi bakiye vaadi YOK."""

from __future__ import annotations

import re
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
RUNBOOK = KOK / "docs" / "RUNBOOK.md"
JETON = KOK / "apps" / "backend" / "servers" / "jeton.py"


def _karantina_adi() -> str:
    kaynak = JETON.read_text(encoding="utf-8")
    ek = re.search(r'^DEFTER_KARANTINA_EKI = "([^"]+)"', kaynak, re.M).group(1)
    # Y202: ad sabitte (yol `<kök>/PEMF_GUI/<ad>`)
    defter = re.search(r'^DEFTER_ADI = "([^"]+)"', kaynak, re.M).group(1)
    return defter + ek


def test_runbook_karantina_dosyasini_ADIYLA_anar_ve_SILMEYIN_der():
    satirlar = [x for x in RUNBOOK.read_text(encoding="utf-8").splitlines() if _karantina_adi() in x]
    assert len(satirlar) == 1, f"RUNBOOK'ta `{_karantina_adi()}` satırı yok / birden çok"
    s = satirlar[0]
    # başlık (belirti) hücresi dosyayı ADIYLA anar — sahada aranan şey budur
    assert _karantina_adi() in s.split("|")[1], s.split("|")[1]
    assert "SİLMEYİN" in s and "teknik" in s.lower()
    assert "ACİL DURDUR" in s and "ETKİLENMEZ" in s
    assert "yolda kalan" in s.lower()


def test_runbook_satiri_10_19_kararini_bozmaz():
    s = next(x for x in RUNBOOK.read_text(encoding="utf-8").splitlines() if _karantina_adi() in x)
    assert "eksi bakiye YOK" in s and "çevrimdışı analiz" in s
    assert not re.search(r"(?i)internetsiz analiz yapılabilir|çevrimdışı analiz (yapılır|devam)|bakiye eksiye", s)
