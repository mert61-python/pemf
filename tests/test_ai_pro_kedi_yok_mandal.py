# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI PRO TEK-YÖNLÜ KEDI_VAR MANDALI — 3. tur denetimi bulgu E3-b (2026-08-24).

ÖLÇÜLEN DURUM: kedi kadrajdan çıkınca cat_organ pipeline SEGMENTASYON aşamasında başarısız olup
`RuntimeError("segmentasyon: ...")` atar (catorgan_predictor.py:80). Bu istisna `_extract_organ_target`
çağrısına ULAŞMADAN yukarı fırlar → `kedi_var` bir kez True olduysa bir daha False'a DÖNEMEZ (loop
hata dalı yalnız localized=False yapar; /frame 500 döner). Sonuç: ws/status/propose-409 ipucu BAYAT
kalır ve hedef kaybolunca operatöre YANLIŞ yönlendirme ("açıyı değiştirin" — kedi kabinde sanılır —
oysa "hayvan aranıyor" demeli). E3-a (loop cache kedi_var yazımı) bu turda düzeltildi; E3-b (istisnayla
mandal) açık kaldı.

DÜZELTME: kedi-yok (SEGMENTASYON hatası) İSTİSNA yerine temiz (localized=False, kedi_var=False) tuple'a
çevrilir → mevcut başarılı cache.update kedi_var=False yazar, mandal hata dallarına DOKUNMADAN kırılır.
pose/PnP hatası (kedi VAR ama organ okluzyon/açı) İSTİSNA olarak YUKARI fırlamaya devam eder → kedi_var
son değerde (True) KORUNUR (karşıt-kanıt).
"""

from __future__ import annotations

import numpy as np
import pytest


def test_KRITIK_E3b_kedi_yok_istisna_yerine_temiz_False_doner(monkeypatch):
    """🔴 Segmentasyon hatası (kedi yok) İSTİSNA ATMAMALI; localized=False + kedi_var=False DÖNMELİ."""
    import servers.ai_router as air

    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)

    class _Clf:
        def predict(self, *a, **k):
            raise RuntimeError("segmentasyon: kedi tespit edilemedi")

    monkeypatch.setattr(air, "_get_or_load_catorgan", lambda: _Clf())
    frame = np.zeros((8, 8, 3), dtype=np.uint8)
    # organ_id 0 (Tüm Vücut) ve 3 (tekil organ) — _extract_organ_target dalları farklı.
    for oid in (0, 3):
        r = air._localize_organ(frame, oid)  # ATMAMALI (mevcut kodda RuntimeError propagate eder)
        assert r[0] is False, f"localized True (oid={oid}) — kedi-yokta sürüş kapısı açık kalır"
        assert r[6] is False, f"kedi_var True (oid={oid}) — kedi yokken bayat True; mandal kırılmadı (E3-b)"


def test_KARSIT_KANIT_E3b_organ_okluzyon_kedi_var_KORUNUR(monkeypatch):
    """Karşıt-kanıt: pose/PnP hatası = kedi VAR ama organ görünmüyor → İSTİSNA YUKARI fırlamalı
    (çağıran cache'teki kedi_var=True'yu korur). Aşırı-düzeltme (tüm istisnaları yut) bunu bozar."""
    import servers.ai_router as air

    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)

    class _Clf:
        def predict(self, *a, **k):
            raise RuntimeError("PnP: organ atlasi cozulemedi (occlusion)")

    monkeypatch.setattr(air, "_get_or_load_catorgan", lambda: _Clf())
    frame = np.zeros((8, 8, 3), dtype=np.uint8)
    with pytest.raises(RuntimeError):
        air._localize_organ(frame, 3)
