# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""H-5.2 (1-H incelemesi) — META KAPI: canlı durumun `activeTreatment`'ı testler arası SIZMAZ (conftest
`_canli_tedavi_durumu_sizmaz`).

ÖLÇÜLEN (inceleme, klon r1x, HEAD conftest): `test_nack_gorunurlugu.py` ardından D1.112 → 3 KIRMIZI, D1.115 → 2 KIRMIZI
("[4] AKTİF TEDAVİ / SÜRÜLEN BOBİN VAR (süreç içi canlı durum) — yakılmaz"); tek başlarına yeşil. Sonda: nack testlerinden
sonra `_active_session.is_active=False` ama `_live_state["activeTreatment"]["isActive"]=True`.

KAPI (dosya içi SIRA — pytest dosyayı yukarıdan aşağı koşar): 1. kol alanı GERÇEK canlı duruma yazar (sızan test taklidi);
2. kol temiz başlamalı. Bu dosya tek başına koşulduğunda da anlamlıdır.
"""

from __future__ import annotations

_BASTA: dict = {}


def test_1_SIZDIRAN_kol_activeTreatment_AKTIF_birakir():
    from servers import api_server  # noqa: F401 — canlı durum modülü süreçte yüklü olsun
    from servers import live_state as ls

    with ls._live_state_lock:
        _BASTA["isActive"] = bool(ls._live_state["activeTreatment"].get("isActive"))
        ls._live_state["activeTreatment"]["isActive"] = True  # temizlemeden çıkar (nack testi deseni)
    assert _BASTA["isActive"] is False, f"aparat: test zaten aktif tedaviyle başladı: {_BASTA}"


def test_2_SONRAKI_test_TEMIZ_baslar():
    from servers import live_state as ls

    with ls._live_state_lock:
        aktif = bool(ls._live_state["activeTreatment"].get("isActive"))
    assert aktif is False, (
        "önceki testin bıraktığı activeTreatment.isActive=True bu teste SIZDI — firmware kapıları '[4] AKTİF TEDAVİ' ile "
        "sıraya bağlı kırmızı (ya da maskeli yeşil) olur"
    )
