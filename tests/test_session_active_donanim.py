# Author: mertaygn, cglrgrkn
"""`/api/session/active` DONANIM alanları — 2. tur denetimi bulgu [2.1] (2026-08-20).

ÖLÇÜLEN DURUM: APK kurulumunun tıbbi-güvenlik kapısı (`useApkGuncelleme.seansSuruyorMu`) cihaza
YALNIZ `/api/session/active`in `is_active`ini soruyordu. Oysa bobinler SEANSSIZ da çalışır
(CoilParameterPanel → `/api/coil/{id}/control` `_active_session`a hiç dokunmaz; kod tabanı bu
durumu `hardwareRunningOutOfSession` banner'ıyla ayrı bir gerçek durum olarak zaten tanıyor).
Sonuç: bobinler hayvanın üzerinde enerjiliyken Android paket yükleyicisi kontrol ekranının
üstüne açılabiliyordu — 1. turun 1 numaralı düzeltmesinin "seanssız bobin" varyantı.

DÜZELTME SÖZLEŞMESİ: uç, canlı-durumdan türetilen `hardware_running` (+ `running_coil_ids`)
alanlarını HER yanıtta taşır; istemci kapısı `is_active || hardware_running`a bakar.
GET SALT-OKUNUR KALIR (dosyanın kendi kuralı: watchdog STOP'unu bastırma riski yok).
Eski istemci alanları yok sayar; eski backend'e karşı istemci fail-open kalır (pf testleri kilitler).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(scope="module")
def api():
    from servers import api_server

    return api_server


@pytest.fixture(scope="module")
def client(api):
    return TestClient(api.app)


@pytest.fixture()
def temiz_durum(api):
    """Seans kapalı + tüm bobinler durmuş bilinen başlangıç; test sonrası eski hâle döner."""
    with api._session_lock:
        eski_sess = dict(api._active_session)
        api._active_session["is_active"] = False
    with api._live_state_lock:
        eski_coils = {i: dict(api._live_state["coils"][i]) for i in range(8)}
        for i in range(8):
            api._live_state["coils"][i]["running"] = False
    yield
    with api._session_lock:
        api._active_session.clear()
        api._active_session.update(eski_sess)
    with api._live_state_lock:
        for i in range(8):
            api._live_state["coils"][i].clear()
            api._live_state["coils"][i].update(eski_coils[i])


def test_KRITIK_seanssiz_calisan_bobin_yanita_yansir(api, client, temiz_durum):
    """Seans YOK ama bobin 6 çalışıyor → `hardware_running: true` + bobin listesi.
    APK kapısının 'seanssız bobin' körlüğünü kapatan sunucu yarısı."""
    with api._live_state_lock:
        api._live_state["coils"][5]["running"] = True  # bobin 6, seans dışı sürüş

    gövde = client.get("/api/session/active").json()
    assert gövde.get("is_active") in (False, None)
    assert gövde.get("hardware_running") is True, (
        f"seanssız çalışan bobin yanıtta görünmüyor: {gövde!r} — APK kapısı bobinler "
        "hayvanın üzerindeyken kurulum ekranını açmaya devam eder (bulgu [2.1])"
    )
    assert gövde.get("running_coil_ids") == [6], f"hangi bobinler olduğu söylenmiyor: {gövde!r}"


def test_KARSIT_KANIT_hicbir_sey_calismiyorsa_false(api, client, temiz_durum):
    """Yanlış-pozitif üretme: seans yok + bobin yok → false + boş liste (kapı kurulumu ertelemez)."""
    gövde = client.get("/api/session/active").json()
    assert gövde.get("hardware_running") is False, f"boşta cihaz 'çalışıyor' raporlandı: {gövde!r}"
    assert gövde.get("running_coil_ids") == []


def test_KARSIT_KANIT_GET_salt_okunur_kalir(api, client, temiz_durum):
    """Dosyanın kendi kuralı: GET global durumu MUTATE ETMEZ (watchdog STOP'u bastırılmasın).
    Yeni alanlar da bu kuralı bozmamalı."""
    with api._live_state_lock:
        api._live_state["coils"][6]["running"] = True  # bobin 7

    client.get("/api/session/active")
    client.get("/api/session/active")

    with api._live_state_lock:
        hala = api._live_state["coils"][6]["running"]
    assert hala is True, "GET canlı-durumu değiştirdi (salt-okunur kuralı ihlal)"
    with api._session_lock:
        assert api._active_session.get("is_active") is False


def test_seans_aktifken_alanlar_yine_dolu(api, client, temiz_durum):
    """Aktif seans yolunda da alanlar tutarlı (istemci tek yüklemle ikisine bakar)."""
    import time as _t

    with api._session_lock:
        api._active_session.update(
            {"is_active": True, "session_id": "t", "duration_minutes": 10, "start_time": _t.time()}
        )
    with api._live_state_lock:
        api._live_state["coils"][0]["running"] = True  # bobin 1

    gövde = client.get("/api/session/active").json()
    assert gövde.get("is_active") is True
    assert gövde.get("hardware_running") is True
    assert gövde.get("running_coil_ids") == [1]
