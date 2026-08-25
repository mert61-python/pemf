# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI PRO KARE SAHİPLİĞİ — 3. tur denetimi bulgu B1 (2026-08-24).

ÖLÇÜLEN DURUM: ai_pro_frame kare gönderen istemcinin KİMLİĞİNİ taşımıyor; sürüş kapısı
'if localized and session_active' yalnız GLOBAL seansı kontrol ediyor. İKİNCİ (izleyici) bir
istemci kendi kamera karelerini /frame'e akıtırsa bobinler O İSTEMCİNİN kamerasından hesaplanan
hedefe sürülür + paylaşılan _ai_organ_cache çift yönlü kirlenir. Ayrıca izleyici /organ ile
seans ortasında ONAYLANMAMIŞ organa geçebiliyor.

DÜZELTME (kayıtlı sahip-kararına UYGUN — YENİ YETKİ VERMEZ, /stop açık kalır, mühür korunur):
YABANCI kare/istek = sahip BİLİNİYOR (modern istemci start'ta client_id verdi) AND gelen kimlik
FARKLI. Yabancı: bobin SÜRMEZ + cache'e YAZMAZ + /organ ve /calibrate reddedilir. Sahip boşsa
(eski/anonim) hiç bastırma yok (geriye-uyum). Deny-only.

⚠️ Adversaryal tasarım-vetting dersi (Hole 1): `bool(frame_client)` şartı KONMAZ — yoksa kimliksiz
kare bastırmayı baypaslardı. Modern sahip kendi karesinde HER ZAMAN id taşır → yanlış-bastırma yok.
"""

import base64
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def owned(monkeypatch):
    import servers.ai_router as air
    import servers.api_server as apis

    snap = {
        "cache": dict(air._ai_organ_cache),
        "owner": air._ai_owner_client,
        "loop": air._ai_loop_active,
        "started": air._ai_started_at,
        "dur": air._ai_duration_min,
        "oid": air._ai_organ_id,
        "reloc": air._ai_relocalize,
    }
    with apis._session_lock:
        sess_snap = dict(apis._active_session)

    air._ai_organ_cache.update(
        {
            "at": 0.0,
            "organ_id": -1,
            "localized": False,
            "kedi_var": False,
            "x_mm": 0.0,
            "y_mm": 0.0,
            "z_mm": 0.0,
            "reliability": 0.0,
            "overlay_bgr": None,
        }
    )
    air._ai_owner_client = "A"  # modern sahip
    air._ai_loop_active = True
    air._ai_started_at = time.monotonic()
    air._ai_duration_min = 120
    air._ai_organ_id = 0
    air._ai_relocalize = False
    with apis._session_lock:
        apis._active_session.clear()
        apis._active_session.update({"is_active": True, "mode": "AI Pro", "coil_ids": list(range(1, 8))})

    async def _fake_decode(*a, **k):
        return np.zeros((8, 8, 3), dtype=np.uint8)

    monkeypatch.setattr(air, "_decode_image", _fake_decode)
    localize_calls = []

    def _loc(f, o):
        localize_calls.append(o)
        return (True, 10.0, 20.0, 30.0, 0.9, None, True)

    monkeypatch.setattr(air, "_localize_organ", _loc)
    driven = []
    monkeypatch.setattr(air, "_predict_and_drive", lambda x, y, z, o: ([1.0] * 7, [0.0] * 7, 0.07))
    monkeypatch.setattr(air, "_drive_coils_ai_pro", lambda D, P: driven.append((D, P)))

    yield air, apis, TestClient(apis.app), driven, localize_calls

    air._ai_organ_cache.clear()
    air._ai_organ_cache.update(snap["cache"])
    air._ai_owner_client = snap["owner"]
    air._ai_loop_active = snap["loop"]
    air._ai_started_at = snap["started"]
    air._ai_duration_min = snap["dur"]
    air._ai_organ_id = snap["oid"]
    air._ai_relocalize = snap["reloc"]
    with apis._session_lock:
        apis._active_session.clear()
        apis._active_session.update(sess_snap)


def _frame(client, cid=None):
    img = base64.b64encode(b"\xff\xd8\xff\xd9").decode()
    data = {"image_base64": img}
    if cid is not None:
        data["client_id"] = cid
    r = client.post("/api/ai/ai_pro/frame", data=data)
    assert r.status_code == 200, r.text
    return r.json()


# ── SÜRÜŞ KAPISI ───────────────────────────────────────────────────────────────────────────────
def test_KRITIK_B1_YABANCI_kare_bobin_SURMEZ_ve_cache_kirletmez(owned):
    air, apis, client, driven, localize_calls = owned
    j = _frame(client, "B")  # sahip A, gönderen B → yabancı
    assert j["driven"] is False, "yabancı kare bobin sürdü (B1 kök: yanlış kameradan hedef)"
    assert j.get("foreignViewer") is True, "yabancı yanıtı foreignViewer=true taşımıyor"
    assert driven == [], "_drive_coils_ai_pro yabancı kare için çağrıldı"
    assert localize_calls == [], "yabancı kare paylaşılan cache'i localize edip kirletti"


def test_KRITIK_B1_YABANCI_kare_ONCEDEN_lokalize_cache_ile_de_SURMEZ(owned):
    """Sahip ZATEN localize etti (cache dolu+taze) → yabancı kare need_localize=False ile cache'i
    OKUR. Drive-gate'te 'not is_foreign' OLMASAYDI, yabancı kare sahibin cache'lediği hedeften
    sürerdi. (Bu senaryo drive-gate kapısını ayrıca kilitler — need_localize gate'i TEK BAŞINA yetmez.)"""
    air, apis, client, driven, localize_calls = owned
    with air._ai_cache_lock:
        air._ai_organ_cache.update(
            {
                "localized": True,
                "organ_id": 0,
                "at": time.time(),
                "x_mm": 5.0,
                "y_mm": 5.0,
                "z_mm": 5.0,
                "reliability": 0.9,
            }
        )
    j = _frame(client, "B")  # sahip A, gönderen B, cache ÖNCEDEN localized
    assert j["driven"] is False, "yabancı kare ÖNCEDEN-lokalize cache'ten sürdü (drive-gate foreign check eksik)"
    assert driven == [], "_drive_coils_ai_pro yabancı kare için (cache'ten) çağrıldı"


def test_KRITIK_B1_SAHIP_kare_SURER(owned):
    air, apis, client, driven, localize_calls = owned
    j = _frame(client, "A")  # sahip A → sürer
    assert j["driven"] is True, "sahip kendi karesiyle sürmeli (yanlış bastırma)"
    assert len(driven) == 1
    assert localize_calls == [0]


def test_KRITIK_B1_HOLE1_kimliksiz_kare_modern_sahipte_YABANCI(owned):
    """Adversaryal vetting Hole 1: sahip modern (id='A') iken kimliksiz (client_id yok) kare de
    YABANCI sayılmalı — yoksa eski/anonim izleyici ya da alan atlayan saldırgan bastırmayı baypaslar."""
    air, apis, client, driven, localize_calls = owned
    j = _frame(client, None)  # client_id HİÇ gönderilmedi
    assert j["driven"] is False, "kimliksiz kare modern-sahipli seansta sürdü (Hole 1 baypası)"
    assert driven == []


def test_KRITIK_B1_seans_BITINCE_stale_owner_KILITLEMEZ(owned):
    """Adversaryal kod-inceleme MAJOR bulgusu: A'nın seansı /stop DIŞI bir yolla bitti (is_active=
    False) ama _ai_owner_client hâlâ "A" (stale; yalnız /stop sıfırlar). Aktif-seans kapısı olmasaydı
    B KALICI kilitlenirdi (kare localize etmez → propose 409 → owner'ı sıfırlayacak /start'a asla
    ulaşamaz). Bastırma YALNIZ aktif sahipli seansta olmalı → seans bitince B serbest."""
    air, apis, client, driven, localize_calls = owned
    with apis._session_lock:
        apis._active_session["is_active"] = False  # seans bitti (süre/acil-durdur), owner stale kaldı
    j = _frame(client, "B")
    assert j.get("foreignViewer") is False, "seans bitmişken stale owner B'yi yabancı saydı (kalıcı lockout)"
    assert localize_calls == [0], "B hazırlıkta localize edemedi (stale-owner lockout)"
    r = client.post("/api/ai/pro/organ", json={"organ_id": 2, "client_id": "B"})
    assert r.status_code == 200, "seans yokken /organ 403 verdi (stale-owner lockout)"


def test_KRITIK_B1_kimliksiz_SAHIP_bastirma_YOK_geriye_uyum(owned):
    """Sahip eski/anonim (client_id'siz start → _ai_owner_client='') → hiç bastırma yok; tek-eski
    istemci sürüşü KIRILMAZ."""
    air, apis, client, driven, localize_calls = owned
    air._ai_owner_client = ""  # eski/anonim sahip
    j = _frame(client, "B")
    assert j["driven"] is True, "sahip boşken bastırma tetiklendi — eski tek-istemci sürüşü kırıldı"
    assert len(driven) == 1


# ── /organ ve /calibrate MÜDAHALE KAPILARI (vetting Hole 2) ─────────────────────────────────────
def test_KRITIK_B1_YABANCI_organ_DEGISTIREMEZ(owned):
    air, apis, client, driven, localize_calls = owned
    r = client.post("/api/ai/pro/organ", json={"organ_id": 3, "client_id": "B"})
    assert r.status_code == 403, f"yabancı organ değiştirdi (onaylanmamış organa enerji): {r.status_code}"
    assert air._ai_organ_id == 0, "yabancı isteği organı değiştirdi"


def test_B1_SAHIP_organ_degistirebilir(owned):
    air, apis, client, driven, localize_calls = owned
    r = client.post("/api/ai/pro/organ", json={"organ_id": 3, "client_id": "A"})
    assert r.status_code == 200
    assert air._ai_organ_id == 3


def test_KRITIK_B1_YABANCI_calibrate_REDDEDILIR(owned):
    air, apis, client, driven, localize_calls = owned
    air._ai_relocalize = False
    r = client.post("/api/ai/pro/calibrate", json={"client_id": "B"})
    assert r.status_code == 403, "yabancı relocalize tetikleyebildi"
    assert air._ai_relocalize is False, "yabancı isteği relocalize'i zorladı"


def test_B1_SAHIP_calibrate_calisir(owned):
    air, apis, client, driven, localize_calls = owned
    air._ai_relocalize = False
    r = client.post("/api/ai/pro/calibrate", json={"client_id": "A"})
    assert r.status_code == 200
    assert air._ai_relocalize is True


# ── start ownerClientId (ownedRef <3sn penceresi) ────────────────────────────────────────────────
def test_B1_start_yaniti_ownerClientId_tasir(monkeypatch):
    import servers.ai_router as air
    from servers import ai_approval

    monkeypatch.setattr(air, "_ai_pro_loop", lambda: None)
    client = TestClient(__import__("servers.api_server", fromlist=["app"]).app)
    try:
        rec = ai_approval.create("ai_pro", {"organ_id": 0, "duration_minutes": 20})
        ai_approval.approve(rec["id"], operator="test@klinik.com")
        r = client.post("/api/ai/pro/start", json={"proposal_id": rec["id"], "client_id": "OWNER-1"})
        assert r.status_code == 200
        assert r.json().get("ownerClientId") == "OWNER-1", "start yanıtı ownerClientId taşımıyor (ownedRef drift)"
        # İkinci start (Already running) MEVCUT sahibi döndürmeli, çağıranı DEĞİL.
        rec2 = ai_approval.create("ai_pro", {"organ_id": 0, "duration_minutes": 20})
        ai_approval.approve(rec2["id"], operator="test@klinik.com")
        r2 = client.post("/api/ai/pro/start", json={"proposal_id": rec2["id"], "client_id": "OWNER-2"})
        assert r2.status_code == 200
        assert "running" in r2.json().get("message", "").lower()
        assert r2.json().get("ownerClientId") == "OWNER-1", "Already-running yanıtı ÇAĞIRANı sahip gösterdi"
    finally:
        client.post("/api/ai/pro/stop")
