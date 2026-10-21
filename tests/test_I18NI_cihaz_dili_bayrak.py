# -*- coding: utf-8 -*-
"""I18NI-A3.4 — İSTEK DIŞI üretimler (cihaz dili) İngilizce bayrağına uymuyor.

KURAL (T4, KURALLAR §0.4): bayrak (`I18N_EN_ACIK`, tek kaynak `i18n/bayrak.json`) KAPALIYKEN etkin dil HER yüzeyde tr. Arayüz
(`dil.etkinDil`), site, DEMA ve launcher (`dil::baslangic_dili`, `ayarla`) bayrak kapalıyken kayıtlı `en` seçimini YOK SAYAR; sunucunun istek
DIŞI dili (`ceviri.cihaz_dili` ← `<veri kökü>/arayuz_dili.json`) bayrak bilmez: dosyada `en` kalmışsa (bayrak açık bir inceleme / deneme
kurulumundan, ya da `POST /api/settings/arayuz-dili` — uç bayrak kapalıyken de `en` yazar) arka plan üretimleri İngilizce olur, Türkçe arayüz
ve launcher Türkçe kalır.

Ölçülen (bulgusuz kısımlar YEŞİL): dosya yok → tr · bozuk dosya → tr (çökme yok) · `_bildir` her durumda `message` TR + `mesajlar` {tr, en}.
KIRMIZI (bugün): bayrak kapalı + dosya `en` → `cihaz_dili()` / istek dışı `ceviri.t` İngilizce.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from utils import ceviri

KOK = Path(__file__).resolve().parents[1]


def _bayrak() -> bool:
    return bool(json.loads((KOK / "i18n" / "bayrak.json").read_text(encoding="utf-8"))["I18N_EN_ACIK"])


@pytest.fixture
def kok(tmp_path, monkeypatch):
    monkeypatch.setattr(ceviri, "_veri_koku", lambda: tmp_path)
    assert ceviri.istek_dili_var.get() is None  # istek DIŞI
    return tmp_path


def test_dosya_yok_tr(kok):
    assert ceviri.cihaz_dili() == "tr"
    assert ceviri.t("hata.beklenmeyen") == ceviri.t("hata.beklenmeyen", dil="tr")


@pytest.mark.parametrize("icerik", ["{bozuk", "", '{"dil": 5}', '["en"]', '{"dil": "de"}'])
def test_bozuk_dosya_sessiz_tr(kok, icerik):
    (kok / "arayuz_dili.json").write_text(icerik, encoding="utf-8")
    assert ceviri.cihaz_dili() == "tr"


def test_bildirim_message_her_zaman_TR_mesajlar_iki_dil(kok):
    from servers import live_state

    (kok / "arayuz_dili.json").write_text('{"dil": "en"}', encoding="utf-8")
    yakalanan = []
    live_state._bildir(
        lambda d: ceviri.t("hata.beklenmeyen", dil=d),
        "info",
        gonder=lambda m, lv: yakalanan.append((m, live_state._BILDIRIM_MESAJLARI.get())),
    )
    m, mesajlar = yakalanan[0]
    assert m == ceviri.t("hata.beklenmeyen", dil="tr")
    assert mesajlar == {"tr": ceviri.t("hata.beklenmeyen", dil="tr"), "en": ceviri.t("hata.beklenmeyen", dil="en")}


@pytest.mark.parametrize("acik,beklenen", [(False, "tr"), (True, "en")], ids=["bayrak-kapali", "bayrak-acik"])
def test_cihaz_dili_BAYRAGA_uyar(kok, monkeypatch, acik, beklenen):
    """Orkestratör (14): ajan sondası bayrak açılınca ATLIYORDU (bayrağı açan commit'ten sonra kör) → iki durum sabit yamayla ayrı ölçülür."""
    monkeypatch.setattr(ceviri, "I18N_EN_ACIK", acik)
    (kok / "arayuz_dili.json").write_text('{"dil": "en"}', encoding="utf-8")
    assert ceviri.cihaz_dili() == beklenen
    assert ceviri.t("hata.beklenmeyen") == ceviri.t("hata.beklenmeyen", dil=beklenen)


def test_sunucu_sabiti_ANA_KAYNAKLA_esles():
    """`ceviri.I18N_EN_ACIK` `i18n/bayrak.json`la aynı (bayrak.py yazar; `--denetle` de denetler)."""
    assert ceviri.I18N_EN_ACIK is _bayrak()
