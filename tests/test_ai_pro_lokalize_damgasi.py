# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI PRO LOKALİZASYON DAMGASI — 3. tur denetimi bulgu F2 (2026-08-24).

ÖLÇÜLEN DURUM: hazırlık akışının "ARDISIK_ONAY=2 (üst üste iki tutarlı ölçüm)" sertleştirmesi
YAPISAL BOŞTU: cat_organ lokalizasyonu en fazla 10 sn'de bir koşar, /frame 'detected'ı CACHE'ten
servis eder, hazırlık kareleri 1,5 sn'de bir gelir → aynı 10 sn penceresindeki tüm kareler TEK
ölçümün ekosu; panel sayacı tek gerçek ölçümle 2'ye ulaşıp öneriyi tetikliyordu. "tek şanslı kare
tedavi parametresi tetikleyemez" vaadi boştu.

DÜZELTME: /frame yanıtı lokalizasyon DAMGASI (localizedAt = cache 'at') taşır ve EKO karelerde
SABİT kalır (istek-başı 'now' DEĞİL). Panel ardisik sayacını yalnız YENİ damgada artırır → iki
onay gerçekten İKİ AYRI lokalizasyon. Bu dosya backend yarısını (damga + eko-kararlılık) kilitler;
panel yarısı pf jest testinde (AiProArdisikEko.test.tsx).
"""

from __future__ import annotations

import base64

import numpy as np
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def air_client(monkeypatch):
    import servers.ai_router as air
    import servers.api_server as apis

    # TUZAK #3: modül-genel cache/bayrakları snapshot+restore (test izolasyonu).
    snap_cache = dict(air._ai_organ_cache)
    snap_reloc = air._ai_relocalize
    snap_oid = air._ai_organ_id
    air._ai_organ_cache.update({"at": 0.0, "organ_id": -1, "localized": False, "kedi_var": False})
    air._ai_relocalize = False

    async def _fake_decode(*a, **k):
        return np.zeros((8, 8, 3), dtype=np.uint8)

    monkeypatch.setattr(air, "_decode_image", _fake_decode)
    # Her lokalizasyon AYNI sonucu döndürür (detected/reliability sabit) — ayırt edici SADECE damga.
    monkeypatch.setattr(air, "_localize_organ", lambda f, o: (True, 10.0, 20.0, 30.0, 0.8, None, True))
    yield air, TestClient(apis.app)
    air._ai_organ_cache.clear()
    air._ai_organ_cache.update(snap_cache)
    air._ai_relocalize = snap_reloc
    air._ai_organ_id = snap_oid


def _frame(client):
    img = base64.b64encode(b"\xff\xd8\xff\xd9").decode()  # decode monkeypatch'li → içerik önemsiz
    r = client.post("/api/ai/ai_pro/frame", data={"image_base64": img})
    assert r.status_code == 200, r.text
    return r.json()


def test_KRITIK_F2_frame_localizedAt_tasir_ve_eko_KARARLI(air_client):
    air, client = air_client
    j1 = _frame(client)
    assert "localizedAt" in j1, "frame yanıtı lokalizasyon damgası (localizedAt) TAŞIMIYOR (F2)"
    at1 = j1["localizedAt"]
    assert at1 and at1 > 0, f"ilk lokalizasyon damgası geçersiz: {at1!r}"

    # İkinci POST HEMEN (eko; now-at < 10 sn → need_localize False, yeniden lokalize YOK).
    at2 = _frame(client)["localizedAt"]
    assert at2 == at1, (
        f"eko karede localizedAt DEĞİŞTİ ({at2} != {at1}) — istek-başı 'now' kullanılmış; damga bir "
        "ÖLÇÜMÜN kimliği olmalı (cache 'at'), yoksa panel her kareyi ayrı ölçüm sanar (F2)"
    )

    # Yeniden-lokalizasyon → damga İLERLEMELİ (yeni gerçek ölçüm).
    air._ai_relocalize = True
    at3 = _frame(client)["localizedAt"]
    assert at3 != at1, f"yeniden-lokalizasyonda damga ilerlemedi ({at3} == {at1}) — yeni ölçüm sayılamaz"
