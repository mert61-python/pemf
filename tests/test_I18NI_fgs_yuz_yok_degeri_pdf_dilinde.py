# -*- coding: utf-8 -*-
"""I18NI-A1.7: FGS yüz analizi kedi yüzü BULUNAMAYINCA sunucu `pain_level` VERİSİ Türkçe sabittir ("Kedi yüzü tespit edilemedi",
`ai_router`). Göç kapsam defteri bunu [İNCELE] notuyla muaf bırakmıştı → İngilizce AI PDF'inde (ve arayüz ayrıntısında) Türkçe cümle.
Güvenlik BİLGİSİ: yüz yok → ağrı skoru yok ("ağrı yok" güvencesi VERİLMEZ); okuyucu veteriner + hayvan sahibi, rapor seçilen dilde olmalı.
Gösterim değer → anahtar (`DEGERLER` / arayüz `VALUE_LABELS`, K-7 eşliği); VERİ ve TR çıktı göç öncesiyle bayt bayt aynı.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
for _p in (KOK, KOK / "apps" / "backend"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from utils import ai_rapor_ogeleri as aro  # noqa: E402
from utils import ceviri  # noqa: E402

VERI = "Kedi yüzü tespit edilemedi"
TR_HARF = re.compile(r"[çğıöşüÇĞİÖŞÜ]")


@pytest.fixture
def dil():
    jetonlar = []

    def kur(d):
        jetonlar.append(ceviri.istek_dili_var.set(d))

    yield kur
    for j in reversed(jetonlar):
        ceviri.istek_dili_var.reset(j)


def test_yonlendirici_VERI_degeri_hala_ayni():
    """Eşleme tablosunun anahtarı sunucunun gerçek VERİ değeridir — biri değişirse öteki de değişmeli."""
    src = (KOK / "apps/backend/servers/ai_router.py").read_text(encoding="utf-8")
    assert f'pain_level = "{VERI}"' in src
    assert aro.DEGERLER.get(VERI.lower()) == "ai.deger.kediYuzuYok"


def test_TR_deger_gocten_onceki_gibi(dil):
    dil("tr")
    assert aro.turkce_deger(VERI) == VERI


def test_EN_deger_ve_AI_PDF_ogeleri_ingilizce(dil):
    dil("en")
    assert aro.turkce_deger(VERI) == "Cat face not detected"
    ogeler = aro.analiz_pdf_ogeleri(
        {"module_id": "fgs", "result_detail": {"detected": False, "fgs_total": None, "pain_level": VERI}}
    )
    metin = " | ".join(f"{o.get('etiket')}: {o.get('aciklama', '')} {' '.join(o.get('satirlar', []))}" for o in ogeler)
    assert "Cat face not detected" in metin, metin
    assert VERI not in metin, metin
