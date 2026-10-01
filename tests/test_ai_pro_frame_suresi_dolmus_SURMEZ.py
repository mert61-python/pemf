# Author: mertaygn, cglrgrkn
"""D1.07 · B-10.23 — `/api/ai/ai_pro/frame`: SÜRESİ DOLMUŞ AI Pro seansında bobin SÜRÜLMEZ.

`ai_router.ai_pro_frame` sürüş kapısı, seans aktif görünse de `_ai_started_at`'tan bu yana onaylı
süre (`_ai_duration_min`) geçmişse kareyi sürmez ("watchdog henüz kapatmamış olsa da"). Bu dal
`if False:` yapılınca mevcut süit YEŞİL kalıyordu (plan: 12 dosya, kör kapı) — oysa korunan
değişmez kategori 1: onaylanan sürenin AŞILMASI.

Kapı GERÇEK `/frame` ucunu ve GERÇEK `_drive_coils_ai_pro`'yu koşar; sahte olan yalnız görüntü
çözme, organ lokalizasyonu (ağır model) ve doz tahminidir. Donanım ve ESP yayını KAYITÇIDIR:
"sürmez" = `update_coil(start=True)` 0 çağrı VE ESP'ye `start` yayını 0 VE yanıtta `driven: false`.
Karşıt kol aynı karenin süre DOLMAMIŞ seansta gerçekten sürdüğünü gösterir (aparat sürüş yoluna
ulaşıyor — "hiç sürmeyen" bir kurulum kapıyı sahte yeşil yapamaz).

İlişkili: D1.12 (B-5.19) aynı değişmezi AI Pro sürüş değişmezleri dörtlüsünün (b) kolu olarak anar.
"""

from __future__ import annotations

import base64
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient


class _KayitciDonanim:
    def __init__(self):
        self.baslat: list[int] = []

    def update_coil(self, coil_id, freq, duty, phase, duration, start=True, duration_seconds=None):
        if start:
            self.baslat.append(int(coil_id))
        return True

    def stop_all_coils(self):
        return True


@pytest.fixture
def ai_pro(monkeypatch):
    import servers.ai_router as air
    import servers.api_server as apis

    anlik = {
        "cache": dict(air._ai_organ_cache),
        "owner": air._ai_owner_client,
        "started": air._ai_started_at,
        "dur": air._ai_duration_min,
        "oid": air._ai_organ_id,
        "reloc": air._ai_relocalize,
    }
    with apis._session_lock:
        seans_anlik = dict(apis._active_session)

    hw = _KayitciDonanim()
    yayinlar: list = []

    def _yayin(topic, payload):
        yayinlar.append((topic, payload))
        return False

    async def _sahte_cozum(*a, **k):
        return np.zeros((8, 8, 3), dtype=np.uint8)

    monkeypatch.setattr(air, "_decode_image", _sahte_cozum)
    monkeypatch.setattr(air, "_localize_organ", lambda f, o: (True, 10.0, 20.0, 30.0, 0.9, None, True, None))
    monkeypatch.setattr(air, "_predict_and_drive", lambda x, y, z, o: ([0.3] * 7, [0.0] * 7, 0.05))
    monkeypatch.setattr(apis.state, "hardware", hw)
    monkeypatch.setattr(apis, "_mqtt_publish", _yayin)
    monkeypatch.setattr(apis, "_ws_broadcast_sync", lambda *a, **k: None)

    air._ai_owner_client = ""  # eski/anonim başlatım: sahiplik bastırması devre dışı (bu kapının konusu değil)
    air._ai_duration_min = 20
    air._ai_organ_id = 0
    air._ai_relocalize = True
    with apis._session_lock:
        apis._active_session.clear()
        apis._active_session.update({"is_active": True, "mode": "AI Pro", "coil_ids": list(range(1, 8))})
    try:
        yield air, TestClient(apis.app), hw, yayinlar
    finally:
        air._ai_organ_cache.clear()
        air._ai_organ_cache.update(anlik["cache"])
        air._ai_owner_client = anlik["owner"]
        air._ai_started_at = anlik["started"]
        air._ai_duration_min = anlik["dur"]
        air._ai_organ_id = anlik["oid"]
        air._ai_relocalize = anlik["reloc"]
        with apis._session_lock:
            apis._active_session.clear()
            apis._active_session.update(seans_anlik)


def _kare(istemci):
    r = istemci.post("/api/ai/ai_pro/frame", data={"image_base64": base64.b64encode(b"\xff\xd8\xff\xd9").decode()})
    assert r.status_code == 200, r.text[:300]
    return r.json()


def _esp_baslatmalari(yayinlar):
    return [t for t, p in yayinlar if isinstance(p, dict) and p.get("command") == "start"]


def test_KRITIK_suresi_DOLMUS_seansta_frame_bobin_SURMEZ(ai_pro):
    air, istemci, hw, yayinlar = ai_pro
    air._ai_started_at = time.monotonic() - (air._ai_duration_min * 60 + 1)  # onaylı süre 1 sn önce doldu
    j = _kare(istemci)
    assert j["driven"] is False, "süresi dolmuş AI Pro seansında /frame bobin SÜRDÜ (onaylı süre aşıldı)"
    assert j["sessionActive"] is False
    assert hw.baslat == [], f"süresi dolmuş seansta STM bobinlerine START gitti: {hw.baslat}"
    assert _esp_baslatmalari(yayinlar) == [], f"süresi dolmuş seansta ESP'ye START yayını: {yayinlar}"


def test_KARSIT_suresi_DOLMAMIS_seansta_ayni_kare_SURER(ai_pro):
    air, istemci, hw, yayinlar = ai_pro
    air._ai_started_at = time.monotonic()
    j = _kare(istemci)
    assert j["driven"] is True, "aparat sürüş yoluna ulaşmıyor — kapı sahte yeşil olabilir"
    assert hw.baslat, "süre dolmamış seansta STM bobinleri sürülmedi (aparat kör)"
    assert _esp_baslatmalari(yayinlar), "süre dolmamış seansta ESP 6-7 START yayını denenmedi"
