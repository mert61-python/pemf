# -*- coding: utf-8 -*-
# Author: mertaygn
"""KPI GRAFİĞİ — ekran, tam-sayı eksen düzeltmesini GERÇEKTEN kullanıyor mu (2026-09-12).

===============================================================================
NE İSTENDİ
===============================================================================
Sahip: "bu grafiği daha belirgin ve tasarım olarak daha güzel hale getir."

⚠️ EN GÖZE BATAN KUSUR TASARIM DEĞİL, ANLAMDI: y ekseni "11.00 · 8.25 · 5.50 · 2.75"
yazıyordu. Seans sayısı TAM SAYIDIR; "8,25 seans" diye bir birim yoktur.

===============================================================================
NEDEN BU KAPI PYTHON TARAFINDA
===============================================================================
⚠️ ÖLÇÜLDÜ (2026-09-12): aynı çıpalar önce jest tarafında düz `src.includes(...)` ile
yazıldı ve MUTASYONDA YEŞİL KALDI — çünkü aranan ifadeler (`decimalPlaces: 0`,
`fromZero`, `showValuesOnTopOfBars`) ekranın AÇIKLAMA YORUMLARINDA da geçiyordu. Kapı,
kodu değil kendi yorumumu ölçüyordu. Bu deponun "yorum kapıyı kandırdı" hatasının
ALTINCI tekrarı.

`c_soyucu.c_soy` yorumları söküp string literallerini koruduğu için çıpa burada güvenli.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

_KOK = pathlib.Path(__file__).resolve().parents[1]
_PF = _KOK / "apps" / "ui" / "src"
if str(pathlib.Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

pytestmark = pytest.mark.skipif(
    not (_PF / "screens" / "KpiDashboardScreen.tsx").exists(),
    reason="apps/ui/ kaynak ağacı yok (yalnız backend paketi) — kapı atlanır",
)


def _kod() -> str:
    """KPI ekranını YORUMLARI SÖKÜLMÜŞ döndürür."""
    from c_soyucu import c_soy

    return c_soy((_PF / "screens" / "KpiDashboardScreen.tsx").read_text(encoding="utf-8"))


def test_KRITIK_eksen_TAM_SAYI_ayari_KODDA():
    """MUTASYON: `decimalPlaces: 0` satırını sil → KIRMIZI (sahibin gördüğü "8.25" geri gelir)."""
    assert "decimalPlaces: 0" in _kod(), "grafik ondalikli eksene dondu -> '8,25 seans' gibi anlamsiz etiketler"


def test_KRITIK_bolut_hesabi_KULLANILIYOR():
    """⚠️ Saf hesap kusursuz olsa bile grafik onu ÇAĞIRMIYORSA eksen yine ondalık çıkar
    (chart-kit sabit 4 bölüte döner).

    MUTASYON: `segments={barBolumSayisi(...)}` satırını sil → KIRMIZI.
    """
    assert "segments={barBolumSayisi(barData.datasets[0].data)}" in _kod(), (
        "grafik bolut hesabini kullanmiyor -> chart-kit sabit 4 bolute doner (2.75 adimlar)"
    )


def test_KRITIK_SIFIR_TABANI_ve_deger_etiketleri():
    """⚠️ `fromZero` olmadan chart-kit ekseni en küçük değerden başlatabilir; 10 ile 11 seans
    neredeyse AYNI yükseklikte görünür — grafik yanıltır.
    ⚠️ `showValuesOnTopOfBars`, sahibin "daha belirgin" isteğinin somut karşılığıdır.
    """
    src = _kod()
    assert "fromZero" in src, "sifir tabani kaldirilmis -> kucuk farklar buyuk gorunur"
    assert "showValuesOnTopOfBars" in src, "cubuk degerleri gizlenmis -> sayi icin goz eksene gider"


def test_KRITIK_kapi_YORUMLA_kandirilamaz():
    """⚠️ KARŞIT KANIT: bu dosyanın çıpaları yorum metnini SAYMAMALI.

    `KpiDashboardScreen.tsx` kendi açıklamasında bu ifadeleri ANIYOR; yorum sökülmeseydi
    kapı kodu silinse bile YEŞİL kalırdı (bizzat ölçüldü — jest tarafındaki ilk sürüm).
    """
    ham = (_PF / "screens" / "KpiDashboardScreen.tsx").read_text(encoding="utf-8")
    assert ham.count("decimalPlaces: 0") > _kod().count("decimalPlaces: 0"), (
        "onkosul kayboldu: aciklama yorumu artik bu ifadeyi anmiyor -> karsit kanit anlamsizlasti"
    )
