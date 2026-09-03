# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""B3 — AI PRO WEB HAZIRLIK "SİYAH EKRAN" (2026-09-03).

ÖLÇÜLEN DURUM: `/ai/pro/hazirlik/baslat` sunucu kamerasını açıp organı lokalize ediyordu ama
kareyi istemciye HİÇ göndermiyordu (`ai_vision` yalnız `_ai_pro_loop`ta yayınlanıyordu) → web
paneli hazırlıkta kapkara ("AI Pro durdu.") kalıyor, "kedi var mı"yı da öğrenemiyordu. Kamera
açılamayınca thread sessizce ölüyor, /baslat yine "success" diyor, /status hiçbir şey söylemiyordu
→ panel 120 sn "Hazırlanıyor…"da takılıp sonra YANLIŞ teşhis ("hayvan bulunamadı") gösteriyordu.

DÜZELTME: önizleme loop'u seans loop'uyla aynı `ai_vision` şemasında (`preview: true`) kare
yayınlar; /status `hazirlikActive` + `hazirlikHata` verir.
"""

import time

import numpy as np
import pytest
from fastapi.testclient import TestClient


class _FakeCap:
    def __init__(self, *a):
        pass

    def isOpened(self):
        return True

    def read(self):
        return True, np.zeros((8, 8, 3), dtype=np.uint8)

    def release(self):
        pass


class _DeadCap(_FakeCap):
    def isOpened(self):
        return False


@pytest.fixture()
def env(monkeypatch):
    import servers.ai_router as air
    import servers.api_server as apis

    snap = dict(air._ai_organ_cache)
    air._ai_organ_cache.update(
        {"at": 0.0, "organ_id": -1, "localized": False, "kedi_var": False, "overlay_bgr": None, "reliability": 0.0}
    )
    air._ai_loop_active = False
    air._ai_hazirlik_active = False
    air._ai_hazirlik_hata = ""
    monkeypatch.setattr(air, "_get_or_load_kedi", lambda: None)
    monkeypatch.setattr(air, "_get_or_load_catorgan", lambda: None)
    ov = np.full((8, 8, 3), 200, dtype=np.uint8)
    monkeypatch.setattr(air, "_localize_organ", lambda f, o: (True, 10.0, 20.0, 30.0, 0.9, ov, True))
    yayin = []
    monkeypatch.setattr(apis, "_ws_broadcast_sync", lambda m: yayin.append(m))
    yield air, apis, TestClient(apis.app), yayin
    air._ai_hazirlik_durdur_ic()
    air._ai_organ_cache.clear()
    air._ai_organ_cache.update(snap)


def _bekle(pred, timeout=3.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return True
        time.sleep(0.05)
    return False


def test_KRITIK_hazirlik_onizlemesi_ai_vision_KARE_yayinlar(env, monkeypatch):
    air, apis, client, yayin = env
    monkeypatch.setattr(air.cv2, "VideoCapture", _FakeCap)
    r = client.post("/api/ai/pro/hazirlik/baslat", json={"organ_id": 3})
    assert r.status_code == 200, r.text
    assert _bekle(lambda: any(m.get("type") == "ai_vision" for m in yayin)), (
        "hazırlık önizlemesi istemciye TEK KARE göndermedi (web paneli kapkara kalır)"
    )
    assert _bekle(lambda: air._ai_organ_cache.get("localized"))
    assert _bekle(lambda: any(m["data"].get("detected") for m in yayin if m.get("type") == "ai_vision"))
    kare = [m["data"] for m in yayin if m.get("type") == "ai_vision" and m["data"].get("detected")][-1]
    assert kare["preview"] is True
    assert kare["imageBase64"] and kare["catDetected"] is True
    assert kare["perCoil"] == [] and kare["remainingSec"] == 0  # önizleme: sürüş yok, seans yok
    st = client.get("/api/ai/pro/status").json()
    assert st["hazirlikActive"] is True and st["hazirlikHata"] == ""
    assert st["active"] is False  # seans BAŞLAMADI


def test_KRITIK_kamera_ACILAMAZSA_status_NEDENI_soyler(env, monkeypatch):
    air, apis, client, yayin = env
    monkeypatch.setattr(air.cv2, "VideoCapture", _DeadCap)
    r = client.post("/api/ai/pro/hazirlik/baslat", json={"organ_id": 3})
    assert r.status_code == 200
    assert _bekle(lambda: air._ai_hazirlik_active is False)
    st = client.get("/api/ai/pro/status").json()
    assert st["hazirlikActive"] is False
    assert "kamera" in st["hazirlikHata"].lower(), st
    # Yeni /baslat hata metnini SIFIRLAR (bayat hata bir sonraki denemeyi anında kesmesin).
    monkeypatch.setattr(air.cv2, "VideoCapture", _FakeCap)
    client.post("/api/ai/pro/hazirlik/baslat", json={"organ_id": 3})
    assert client.get("/api/ai/pro/status").json()["hazirlikHata"] == ""


def test_KRITIK_model_YUKLENEMEZSE_status_NEDENI_soyler(env, monkeypatch):
    air, apis, client, yayin = env
    monkeypatch.setattr(air.cv2, "VideoCapture", _FakeCap)

    def _patlat():
        raise RuntimeError("cat_organ paketi yok")

    monkeypatch.setattr(air, "_get_or_load_catorgan", _patlat)
    client.post("/api/ai/pro/hazirlik/baslat", json={"organ_id": 3})
    assert _bekle(lambda: air._ai_hazirlik_active is False)
    st = client.get("/api/ai/pro/status").json()
    assert "cat_organ paketi yok" in st["hazirlikHata"]
    assert not any(m.get("type") == "ai_vision" for m in yayin)


def test_KARSIT_KANIT_onizleme_yayini_HIZ_SINIRLI(env, monkeypatch):
    """Loop 50 ms'de döner; yayın ≥330 ms aralıklı olmalı (WS kuyruğu 64 — boğulmasın)."""
    air, apis, client, yayin = env
    monkeypatch.setattr(air.cv2, "VideoCapture", _FakeCap)
    client.post("/api/ai/pro/hazirlik/baslat", json={"organ_id": 0})
    time.sleep(1.5)
    n = sum(1 for m in yayin if m.get("type") == "ai_vision")
    # Alt sınır 2 (eskiden 1): `_son_yayin=0.0` ile İLK kare her zaman gider → "yalnız TEK kare atan"
    # bir regresyonu 1 alt sınırı YAKALAMAZDI (ölçüldü: aralık 1e9 yapılınca da yeşil kalıyordu).
    # Üst sınır 6: 0,33 sn aralıkta 1,5 sn'de ~4-5 kare; sel (50 ms) ~30 kare → kırmızı.
    assert 2 <= n <= 6, f"1,5 sn'de {n} kare — hız sınırı (≥330 ms) ya da yayın SÜREKLİLİĞİ bozuk"
