# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.80 · B-5.1 · B-5.10 (+ İG-5.2) — `/api/ai/ai_pro/frame` YALNIZ onayı tüketilmiş AI Pro seansında sürer.

SAHİP KARARI (ai_approval.py:5, 2026-08-06): "onaysız tedavi başlamaz". ÖLÇÜLEN KUSUR: `/frame`'in sürüş kapısı
`mode.startswith("AI")` idi; `mode` `/api/session/start`'ta SERBEST METİN. "AI…" önekli herhangi bir elle seans
(`"AI (Auto)"`, `"ai…"` değil ama `"AI Pro · x"` dahil) onaysız AI dozunu açıyordu (İG-5.2: 17/17, önek daraltılınca
bile 1/17 — önek tabanlı her kapı delinir). Araştırma modelleri (bayrak kapalıyken) `/frame`'de denetlenmiyordu;
hazırlık ucu seans sürerken modeli değiştirebiliyordu (B-5.10).

Kapı GERÇEK uçlarla: elle seans `POST /api/session/start`, onaylı seans GERÇEK `öner→onayla→/api/ai/pro/start`
(`ai_pro_aparati`), sürüş GERÇEK `_drive_coils_ai_pro` → GERÇEK `HardwareController` paketleri. HTTP 200'e değil
donanıma giden AI dozuna (bobin 1-5'te duty 0,30) bakılır.
"""

from __future__ import annotations

import random

import ai_pro_aparati as ap
import pytest
from kd_kalibrasyon_yardimci import (
    kd_gecerli_kalibrasyon,  # noqa: F401,E402  KD · Y259: kalibrasyon ön koşulu sağlanmış (bu dosya başka kuralı ölçer)
)

_ONEKLI = ["AI (Auto)", "AI Pro · x", "AI Pro · Kedi Organ · Tüm Vücut", "AI", "AIx", "AI ", "AI Pro", "AI-otomatik"]
_ONEKSIZ = ["Manuel", "Otomatik", "ai (auto)", " AI (Auto)", "Ai Pro", "manual", "Test"]


def _rastgele_modlar(n: int = 35) -> list:
    """İG-5.2 yöntemi: tohumlu üreteçle önekli/öneksiz, büyük/küçük harf, Unicode ve boşluk çeşitlemeleri."""
    rnd = random.Random(52)
    kuyruk = ["", " · x", " (Auto)", "Pro", " ğüşİ", "\t1", " Pro · Fantom"]
    modlar = list(_ONEKLI) + list(_ONEKSIZ)
    while len(modlar) < n:
        modlar.append(rnd.choice(["AI", "AI Pro", "Ai", "ai", "A I", "AI​"]) + rnd.choice(kuyruk))
    return modlar[:n]


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.geri()


def _ai_dozu(o, once: int) -> list:
    return [d for d in ap.surus_paketleri(o, once) if any(abs(x - ap.D_AI) < 1e-6 for x in d[:5])]


def test_KRITIK_IG52_SERBEST_mode_ile_elle_seans_frame_SURMEZ_N35(o):
    ihlal = []
    for mod in _rastgele_modlar():
        r = o.c.post(
            "/api/session/start",
            json={"coil_ids": [1, 2], "frequency": 10, "duty": 5, "phase": 0, "duration_minutes": 5, "mode": mod},
        )
        assert r.status_code == 200, f"aparat: elle seans açılmadı ({mod!r}): {r.text[:200]}"
        n = ap.paket_sayisi(o)
        j = ap.kare(o).json()
        if _ai_dozu(o, n) or j.get("driven"):
            ihlal.append(mod)
        o.c.post("/api/session/stop")
    assert not ihlal, f"onaysız ELLE seansta /frame AI dozu sürdü ({len(ihlal)}/35): {ihlal[:6]}"


def test_KARSIT_onayi_tuketilmis_AI_Pro_seansinda_frame_SURER(o):
    _pid, r = ap.onayli_baslat(o)
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:200]
    n = ap.paket_sayisi(o)
    j = ap.kare(o).json()
    assert j.get("driven") is True and _ai_dozu(o, n), f"onaylı AI Pro seansında /frame sürmedi: {j.get('driven')}"


def test_KRITIK_B510_bayrak_KAPALIYKEN_arastirma_modeli_muhurlu_seansta_frame_SURMEZ(o, monkeypatch):
    """Onay bayrak AÇIKKEN alınmış, sonra bayrak kapatılmış: `/frame` sürüş anında bayrağı denetler."""
    from servers import ai_pro_hedef

    monkeypatch.setenv(o.air.ARASTIRMA_AIPRO_BAYRAGI, "1")
    _pid, r = ap.onayli_baslat(o, model="petri", organ=ai_pro_hedef.saglayici_al("petri").varsayilan_hedef)
    assert r.status_code == 200 and r.json().get("status") == "success", f"aparat: petri seansı açılmadı {r.text[:200]}"
    monkeypatch.delenv(o.air.ARASTIRMA_AIPRO_BAYRAGI)
    n = ap.paket_sayisi(o)
    j = ap.kare(o).json()
    assert not _ai_dozu(o, n) and j.get("driven") is not True, "bayrak kapalıyken araştırma modeli /frame'de SÜRDÜ"


def test_KRITIK_B510_seans_surerken_HAZIRLIK_modeli_DEGISTIREMEZ_ve_muhur_disi_model_SURMEZ(o, monkeypatch):
    _pid, r = ap.onayli_baslat(o)
    assert r.status_code == 200, r.text[:200]
    o.air._ai_loop_active = False  # mobil kol: sunucu kamerası döngüsü yok (yalnız /frame)
    h = o.c.post("/api/ai/pro/hazirlik/baslat", json={"model": "petri", "organ_id": 0})
    assert h.status_code == 409, f"onaylı seans sürerken hazırlık modeli değiştirildi ({h.status_code})"
    assert o.air._ai_hedef_modeli == "kedi", f"seans modeli değişti: {o.air._ai_hedef_modeli}"
    # Başka bir yoldan ezildiğini varsay (mühür dışı model). Bayrak AÇIK: araştırma bayrağı kapısı bunu ÖRTMESİN —
    # tek engel mühürdeki modelle karşılaştırma olsun.
    monkeypatch.setenv(o.air.ARASTIRMA_AIPRO_BAYRAGI, "1")
    o.air._ai_hedef_modeli = "petri"
    n = ap.paket_sayisi(o)
    j = ap.kare(o).json()
    assert not _ai_dozu(o, n) and j.get("driven") is not True, "mühürdeki model dışı sağlayıcıyla /frame SÜRDÜ"
