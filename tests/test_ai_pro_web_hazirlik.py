# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI PRO WEB HAZIRLIK ÖNİZLEMESİ — web kapalı-döngü düzeltmesi (2026-08-25).

ÖLÇÜLEN DURUM: web/sunucu-kameralı yolda "AI Pro Başlat" DOĞRUDAN /propose çağırıyordu ve
"organ henüz konumlandırılmadı" (409) alıyordu — sunucu kamerası ancak SEANS sürerken lokalize
ediyor, seans öncesi hiçbir şey lokalize etmiyordu (telefonda 1.9.22'de çözülen kapalı-döngünün
web hâli). DÜZELTME: /ai/pro/hazirlik/baslat kamerayı ÖNİZLEMEDE ısıtır (organı lokalize eder,
BOBİN SÜRMEZ, SEANS BAŞLATMAZ) → propose artık çalışır. /start önizlemeyi durdurup kamerayı
bıraktırır (tek kamera → çakışma yok).
"""

import time

import numpy as np
import pytest
from fastapi.testclient import TestClient


class _FakeCap:
    def __init__(self, *a):
        self._open = True

    def isOpened(self):
        return True

    def read(self):
        return True, np.zeros((8, 8, 3), dtype=np.uint8)

    def release(self):
        self._open = False


@pytest.fixture()
def air_env(monkeypatch):
    import servers.ai_router as air
    import servers.api_server as apis

    snap_cache = dict(air._ai_organ_cache)
    snap_oid = air._ai_organ_id
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
    air._ai_loop_active = False
    air._ai_hazirlik_active = False
    with apis._session_lock:
        apis._active_session.clear()
        apis._active_session.update({"is_active": False, "mode": "Sistem Hazır"})

    monkeypatch.setattr(air.cv2, "VideoCapture", _FakeCap)
    monkeypatch.setattr(air, "_get_or_load_kedi", lambda: None)
    monkeypatch.setattr(air, "_get_or_load_catorgan", lambda: None)
    monkeypatch.setattr(air, "_localize_organ", lambda f, o: (True, 10.0, 20.0, 30.0, 0.9, None, True))
    driven = []
    monkeypatch.setattr(air, "_drive_coils_ai_pro", lambda D, P: driven.append((D, P)))

    yield air, apis, TestClient(apis.app), driven

    air._ai_hazirlik_durdur_ic()  # her testte preview thread'ini durdur (sızıntı yok)
    air._ai_organ_cache.clear()
    air._ai_organ_cache.update(snap_cache)
    air._ai_organ_id = snap_oid
    with apis._session_lock:
        apis._active_session.clear()
        apis._active_session.update(sess_snap)


def _lokalize_bekle(air, timeout=3.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if bool(air._ai_organ_cache.get("localized")):
            return True
        time.sleep(0.05)
    return False


def test_KRITIK_web_hazirlik_LOKALIZE_eder_bobin_SURMEZ_seans_BASLATMAZ(air_env):
    air, apis, client, driven = air_env
    r = client.post("/api/ai/pro/hazirlik/baslat", json={"organ_id": 3})
    assert r.status_code == 200, r.text
    assert _lokalize_bekle(air), "hazırlık önizlemesi organı lokalize etmedi (web kapalı-döngü hâlâ kırık)"
    assert air._ai_organ_cache.get("organ_id") == 3, "seçili organ (Karaciğer=3) için lokalize etmedi"
    # ⚠️ Önizleme SÜRMEZ + SEANS BAŞLATMAZ:
    assert driven == [], "önizleme bobin sürdü (önizleme yalnız lokalize etmeli)"
    assert air._ai_loop_active is False, "önizleme seans loop'unu başlattı"
    with apis._session_lock:
        assert not apis._active_session.get("is_active"), "önizleme _active_session'ı aktif etti"


def test_KRITIK_web_hazirlik_sonrasi_PROPOSE_calisir(air_env):
    air, apis, client, driven = air_env
    # Öneri hesabı em_kedi ister → mock'la (lokalizasyon zaten mock).
    monkeypatch_val = ([1.0] * 7, [0.0] * 7, 0.07)
    import servers.ai_router as air2

    orig = air2._predict_and_drive
    air2._predict_and_drive = lambda x, y, z, o: monkeypatch_val
    try:
        client.post("/api/ai/pro/hazirlik/baslat", json={"organ_id": 3})
        assert _lokalize_bekle(air)
        r = client.post("/api/ai/pro/propose", json={"organ_id": 3, "duration_minutes": 20})
        assert r.status_code == 200, f"hazırlık lokalize ettiği hâlde propose 409 verdi: {r.text}"
        assert r.json().get("proposalId"), "propose öneri kimliği döndürmedi"
    finally:
        air2._predict_and_drive = orig


def test_KRITIK_web_hazirlik_durdur_KAMERAYI_birakir(air_env):
    air, apis, client, driven = air_env
    client.post("/api/ai/pro/hazirlik/baslat", json={"organ_id": 0})
    assert _lokalize_bekle(air)
    assert air._ai_hazirlik_active is True
    r = client.post("/api/ai/pro/hazirlik/durdur")
    assert r.status_code == 200
    assert air._ai_hazirlik_active is False, "durdur önizlemeyi durdurmadı (kamera bırakılmaz)"


def test_KARSIT_KANIT_seans_aktifken_hazirlik_NO_OP(air_env):
    air, apis, client, driven = air_env
    air._ai_loop_active = True  # seans zaten çalışıyor (kamera seansta)
    try:
        r = client.post("/api/ai/pro/hazirlik/baslat", json={"organ_id": 0})
        assert r.status_code == 200
        # Seans aktifken önizleme BAŞLAMAZ (aynı kamerayı ikinci kez açmaz).
        assert air._ai_hazirlik_active is False, "seans aktifken önizleme başladı (çift VideoCapture riski)"
    finally:
        air._ai_loop_active = False


def test_YAPISAL_start_ONIZLEMEYI_durdurur_sonra_loop(air_env):
    """/start seans loop'unu (kamerayı açan) başlatmadan ÖNCE önizlemeyi durdurmalı — kaynakta
    `_ai_hazirlik_durdur_ic()` çağrısı `_ai_pro_loop` thread spawn'ından ÖNCE gelmeli (çift kamera yok)."""
    from pathlib import Path

    src = Path(air_env[0].__file__).read_text(encoding="utf-8")
    i = src.index("def start_ai_pro")
    j = src.index("\n@ai_router", i + 10)
    govde = src[i:j]
    durdur = govde.find("_ai_hazirlik_durdur_ic()")
    loop_spawn = govde.find("target=_ai_pro_loop")
    assert durdur >= 0, "start_ai_pro önizlemeyi durdurmuyor (_ai_hazirlik_durdur_ic çağrısı yok)"
    assert loop_spawn >= 0, "start_ai_pro seans loop'unu başlatmıyor?"
    assert durdur < loop_spawn, "önizleme-durdurma seans loop spawn'ından SONRA — çift VideoCapture riski"
