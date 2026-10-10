# -*- coding: utf-8 -*-
"""S-F2-1.2 (2-F incelemesi A1 · Y123 önerilen · C2-1.14) — AI Pro öneri reddinin yanıtı gerekçenin KAYDA GEÇİP GEÇMEDİĞİNİ söyler.

ÖLÇÜLEN: onay penceresi "Red gerekçesi (kayda geçer)" diyor; karar tablosu yazılamazsa ret yine `200 {"status": "success"}` dönüyordu
(Y119 kapısı `test_KRITIK_karar_tablosu_yazilamazsa_RET_YINE_200_ve_iz_yazilir` — ret bozulmamalı, doğru) ve arayüz yanıtı okumadığı için
hekim gerekçenin kaydedildiğini sanıyordu. Önerilen: yanıta `gerekceKaydedildi: bool`; arayüz `false`ta uyarır
(`components/domain/__tests__/AiProPanel.redGerekcesi.SF212.web.test.tsx`). Ret yine 200 — tedavi BAŞLAMAZ, karar akışı durmaz.
GERÇEK: `/api/ai/pro/propose` → `/reject`, TreatmentHistoryDB (sentetik, tmp), GERÇEK HardwareController; arıza GERÇEK SQLite hatası (tablo yok).
"""

from __future__ import annotations

from test_ai_pro_red_gerekcesi_KARAR_TABLOSUNDA_Y119 import _oner, o  # noqa: F401


def test_KRITIK_karar_tablosu_yazilamazsa_yanit_gerekceKaydedildi_FALSE(o):  # noqa: F811
    """MUTASYON: yanıt alanı hep True / hiç yok → KIRMIZI."""
    with o.db._get_connection() as c:
        c.execute("DROP TABLE ai_pro_kararlari")
        c.commit()
    pid = _oner(o)
    r = o.c.post("/api/ai/pro/reject", json={"proposal_id": pid, "reason": "gerekce SF212"})
    assert r.status_code == 200, r.text[:300]
    assert r.json().get("gerekceKaydedildi") is False, f"gerekçe yazılamadı ama yanıt bunu söylemiyor: {r.json()}"


def test_KARSIT_gerekce_yazilinca_gerekceKaydedildi_TRUE(o):  # noqa: F811
    pid = _oner(o)
    r = o.c.post("/api/ai/pro/reject", json={"proposal_id": pid, "reason": "gerekce SF212"})
    assert r.status_code == 200 and r.json().get("gerekceKaydedildi") is True, r.json()
