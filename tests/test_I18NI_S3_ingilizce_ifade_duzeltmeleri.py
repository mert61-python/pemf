# -*- coding: utf-8 -*-
"""S-I18NI.3 [ÖNERİLEN UYGULANDI] (14-I18N-INCELEME, ajan A1 / A2 önerileri): YALNIZ İngilizce ifade düzeltmeleri — TR katalog DEĞİŞMEDİ.

- `guvenlik.mandal.oncekiOturum` (KRİTİK): "oturum" = uygulamanın açık kaldığı süre; EN "previous session" seansla (session) karışıyordu →
  "the previous app run".
- `kontrol.ekran.donanimCalisiyor_other` (KRİTİK, çoğul): "coils are energized … stop it" → "stop them".
- `seans.uyari.stopDogrulanamadi` (sunucu, KRİTİK): "for coil {{bobinler}} — they may" → "coil(s)" (arayüz eşiyle aynı).
- `kontrol.panel.sureGirilmedi`: TR "klinik gözetimsiz sınıra kadar" → "up to the clinical limit for unattended operation".
- `ai.deger.sick` (sunucu PDF): "Sick patient (at risk)" → "Sick (at risk)" — K-4 "hasta → patient" kuralı zorlamıştı (arayüz eşleri gibi istisna).
- `ai.etiket.reliable` / `ai.etiket.surulebilir` (sunucu PDF): TR soru biçimli ("… mi") etiket EN'de iddiaya dönmüştü ("Detection is reliable: No")
  → "Detection reliable?" / "Usable for coil settings?".
- `ayarlar.hakkinda.mersis`: EN "MERSİS:" (Türkçe İ) → "MERSIS:" (site EN ile aynı).
Hoca onay listesinde (DENETIM\\I18N\\CEVIRI-ONAY-LISTESI) "[İNCELE]" bölümünde.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]


def _al(rel: str, anahtar: str):
    d = json.loads((KOK / rel).read_text(encoding="utf-8"))
    for p in anahtar.split("."):
        d = d[p]
    return d


DUZELTMELER = [
    (
        "apps/ui/src/i18n/{}/guvenlik.json",
        "mandal.oncekiOturum",
        "önceki oturumda ACİL DURDUR — sıfırlanmadı ({{asil}})",
        "EMERGENCY STOP in the previous app run — not reset ({{asil}})",
    ),
    (
        "apps/ui/src/i18n/{}/kontrol.json",
        "ekran.donanimCalisiyor_other",
        "⚠️ DONANIM ÇALIŞIYOR — {{count}} bobin enerjili, seans bağlamı dışında. Aşağıdaki ACİL DURDUR ile durdurabilirsiniz.",
        "⚠️ HARDWARE IS RUNNING — {{count}} coils are energized, outside a session context. You can stop them with the EMERGENCY STOP below.",
    ),
    (
        "apps/ui/src/i18n/{}/kontrol.json",
        "panel.sureGirilmedi",
        "Süre girilmedi — bobin klinik gözetimsiz sınıra kadar çalışır (sunucu tarafında uygulanır); süre belirtmeniz önerilir.",
        "No duration entered — the coil runs up to the clinical limit for unattended operation (enforced on the server side); it is recommended"
        " to set a duration.",
    ),
    ("apps/ui/src/i18n/{}/ayarlar.json", "hakkinda.mersis", "MERSİS: ", "MERSIS: "),
    (
        "apps/backend/i18n/{}.json",
        "seans.uyari.stopDogrulanamadi",
        "Bobin {{bobinler}} için donanım STOP'u DOĞRULANAMADI — HÂLÂ ÇALIŞIYOR olabilirler. ACİL DURDUR'a basın ya da cihazın fiziksel güç"
        " düğmesini kullanın.",
        "The hardware STOP could NOT be VERIFIED for coil(s) {{bobinler}} — they may STILL BE RUNNING. Press EMERGENCY STOP or use the"
        " device's physical power button.",
    ),
    ("apps/backend/i18n/{}.json", "ai.deger.sick", "Hasta (riskli)", "Sick (at risk)"),
    ("apps/backend/i18n/{}.json", "ai.etiket.reliable", "Tespit güvenilir mi", "Detection reliable?"),
    (
        "apps/backend/i18n/{}.json",
        "ai.etiket.surulebilir",
        "Bobin ayarına esas alınabilir mi",
        "Usable for coil settings?",
    ),
]


@pytest.mark.parametrize("rel,anahtar,tr,en", DUZELTMELER, ids=[d[1] for d in DUZELTMELER])
def test_EN_ifade_duzeltildi_TR_AYNI(rel, anahtar, tr, en):
    assert _al(rel.format("tr"), anahtar) == tr, "TR değer DEĞİŞMEMELİ (göç öncesiyle birebir)"
    assert _al(rel.format("en"), anahtar) == en
