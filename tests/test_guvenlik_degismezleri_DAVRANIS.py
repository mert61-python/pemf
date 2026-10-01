# Author: mertaygn, cglrgrkn
"""D1.11 · B-2.24 — yedi KÖR güvenlik değişmezine DAVRANIŞ kapısı.

DENETİM-02 (02-2 tablosu): aşağıdaki mutantların her biri tek tek enjekte edildiğinde tam süit
YEŞİL kalıyordu. Hepsi Dalga 3'ün auth/middleware düzeltmelerinin (B-2.1, B-2.2, B-2.8) ve E-stop
yolu düzeltmelerinin dokunacağı değişmezler → önce bunlar kapılanır.

  M03  auth middleware FAIL-CLOSED: auth katmanı patlarsa korumalı uç 503 (ama ACİL DURDUR geçer — Ö.4-Y8)
  M04  boş beklenen token: auth zorunluyken cihaz token'ı BOŞSA herkes reddedilir (fail-open değil)
  M14  WS köken (CSWSH): proxy'siz LAN'da başka kökenli tarayıcı sayfası WS açamaz
  M27  WS token FAIL-CLOSED: token denetimi patlarsa bağlantı REDDEDİLİR (1008)
  M29  `/api/ai/` önekinin TAMAMI muaf DEĞİL — yalnız 6 bilinçli yol (sahip kararı; hafıza
       `pemf-auth-exemptions`): uzaktan token'sız `/api/ai/hazirlik` → 401
  M31  operatör jetonu HİÇBİR günlüğe yazılmaz (üretim ve çözümleme)
  M32  TEDAVİ uçları (AI Pro, /frame, landmark) AI kuyruğuna GİRMEZ — dolu kuyrukta beklemeden geçer

Kapılar GERÇEK middleware'i, GERÇEK WS ucunu, GERÇEK `ai_queue_gate`'i ve gerçek günlük kaydını
kullanır. M17 (durdurmaya kapı) planda KISMEN çürütüldü ve buraya alınmadı; M35 → B-2.5.

⚠️ Ö.4-Y8: M03 kolu ACİL DURDUR'un auth katmanı çökükken de geçtiğini AYRICA ölçer.
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


@pytest.fixture
def api(monkeypatch):
    from servers import api_server

    # E-stop'un yan işleri bu dosyanın konusu değil: ağ yok, bildirim yok, ack-bekçisi doğmaz.
    monkeypatch.setattr(api_server, "_mqtt_publish", lambda topic, payload: False)
    monkeypatch.setattr(api_server, "_push_notification", lambda *a, **k: None)
    monkeypatch.setattr(api_server, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(api_server.state, "hardware", None)
    return api_server


@pytest.fixture
def auth_zorunlu(monkeypatch):
    """Auth ZORUNLU + bilinen cihaz token'ı. TestClient'ın varsayılan istemci adı ('testclient') IP
    değildir → `is_local_request` fail-closed UZAK sayar (tünel benzetimi)."""
    from servers import auth

    monkeypatch.setattr(auth, "_require", True)
    monkeypatch.setattr(auth, "_warned", True)
    monkeypatch.setattr(auth, "get_api_token", lambda: "gizli-cihaz-tokeni")
    return auth


# ── M03 ───────────────────────────────────────────────────────────────────────


def test_KRITIK_M03_auth_katmani_PATLARSA_korumali_uc_503_ACIL_DURDUR_gecer(api, monkeypatch):
    from servers import auth

    def _patla():
        raise RuntimeError("auth katmanı bozuk (benzetim)")

    monkeypatch.setattr(auth, "require_auth", _patla)
    c = TestClient(api.app)
    r = c.get("/api/patients")
    assert r.status_code == 503, f"auth katmanı çökükken korumalı uç {r.status_code} döndü (fail-OPEN)"
    e = c.post("/api/hardware/emergency_stop")
    assert e.status_code == 200, f"auth katmanı çökükken ACİL DURDUR {e.status_code} (Ö.4-Y8: kapılanamaz)"


# ── M04 ───────────────────────────────────────────────────────────────────────


def test_KRITIK_M04_cihaz_tokeni_BOSKEN_herkes_REDDEDILIR(api, auth_zorunlu, monkeypatch):
    monkeypatch.setattr(auth_zorunlu, "get_api_token", lambda: "")
    c = TestClient(api.app)
    assert c.get("/api/patients").status_code == 401, "boş cihaz token'ı + boş istek token'ı KABUL edildi"
    assert c.get("/api/patients", headers={"X-API-Key": ""}).status_code == 401
    assert c.get("/api/patients", headers={"X-API-Key": "herhangi"}).status_code == 401


def test_KARSIT_M04_dogru_token_GECER(api, auth_zorunlu):
    c = TestClient(api.app)
    assert c.get("/api/patients", headers={"X-API-Key": "gizli-cihaz-tokeni"}).status_code != 401


# ── M14 ───────────────────────────────────────────────────────────────────────


def test_KRITIK_M14_capraz_kokenli_WS_REDDEDILIR(api, monkeypatch):
    from servers import auth

    monkeypatch.setattr(auth, "_require", False)
    monkeypatch.setattr(auth, "_warned", True)
    c = TestClient(api.app)
    with pytest.raises(WebSocketDisconnect) as kapanis:
        with c.websocket_connect("/ws", headers={"origin": "http://kotu-site.example"}) as ws:
            ws.receive_text()
    assert kapanis.value.code == 1008, f"çapraz kökenli WS kapanış kodu {kapanis.value.code}"


def test_KARSIT_M14_ayni_kokenli_WS_KABUL_edilir(api, monkeypatch):
    from servers import auth

    monkeypatch.setattr(auth, "_require", False)
    monkeypatch.setattr(auth, "_warned", True)
    c = TestClient(api.app)
    with c.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
        assert '"snapshot"' in ws.receive_text()


# ── M27 ───────────────────────────────────────────────────────────────────────


def test_KRITIK_M27_WS_token_denetimi_PATLARSA_REDDEDER(api, auth_zorunlu, monkeypatch):
    def _patla(_tok):
        raise RuntimeError("token denetimi bozuk (benzetim)")

    monkeypatch.setattr(auth_zorunlu, "check_token", _patla)
    c = TestClient(api.app)
    with pytest.raises(WebSocketDisconnect) as kapanis:
        with c.websocket_connect("/ws?token=herhangi", headers={"cf-connecting-ip": "203.0.113.9"}) as ws:
            ws.receive_text()
    assert kapanis.value.code == 1008, f"token denetimi çökükken WS kapanışı {kapanis.value.code} (fail-OPEN?)"


def test_KARSIT_M27_dogru_tokenli_uzak_WS_KABUL(api, auth_zorunlu):
    c = TestClient(api.app)
    with c.websocket_connect("/ws?token=gizli-cihaz-tokeni", headers={"cf-connecting-ip": "203.0.113.9"}) as ws:
        assert '"snapshot"' in ws.receive_text()


# ── M29 ───────────────────────────────────────────────────────────────────────


def test_KRITIK_M29_ai_oneki_TOPTAN_muaf_DEGIL(api, auth_zorunlu):
    c = TestClient(api.app)
    r = c.get("/api/ai/hazirlik")
    assert r.status_code == 401, f"uzaktan token'sız /api/ai/hazirlik {r.status_code} — /api/ai toptan muaf olmuş"
    assert not auth_zorunlu.is_exempt("/api/ai/log"), "/api/ai/log AYRICALIKLI sınıfta — muaf olamaz"


def test_KARSIT_M29_bilincli_muaf_ai_yollari_MUAF_kalir(api, auth_zorunlu):
    """Sahip kararı (2026-07-01): 6 AI yolu bilerek muaf — bu kapı onları 'kapatma' diye OKUNMAZ."""
    for yol in ("/api/ai/vision/x", "/api/ai/disease/x", "/api/ai/rna/x", "/api/ai/sound/x", "/api/ai/pro/x"):
        assert auth_zorunlu.is_exempt(yol), yol
    assert auth_zorunlu.is_exempt("/api/ai/ai_pro/frame")


# ── M31 ───────────────────────────────────────────────────────────────────────


def test_KRITIK_M31_operator_jetonu_HICBIR_gunluge_YAZILMAZ(api, caplog, monkeypatch):
    from servers import operator_tokens

    operator_tokens.temizle_hepsi()
    caplog.set_level(logging.DEBUG)
    c = TestClient(api.app, client=("127.0.0.1", 51238))
    try:
        for o in c.get("/api/operators").json().get("data", []):
            c.post("/api/operators/remove", json={"email": o["email"]})
        assert (
            c.post(
                "/api/operators/enroll", json={"email": "m31@klinik.test", "display_name": "M31", "pin": "482913"}
            ).status_code
            == 200
        )
        r = c.post("/api/operators/verify", json={"email": "m31@klinik.test", "pin": "482913"})
        assert r.status_code == 200, r.text[:200]
        jeton = r.json()["operator_token"]
        assert operator_tokens.cozumle(jeton) == "m31@klinik.test"  # çözümleme yolu da koşsun
        sizan = [rec.name for rec in caplog.records if jeton in rec.getMessage()]
        assert jeton and not sizan, f"operatör jetonu günlüğe yazıldı: {sizan}"
        assert jeton not in caplog.text
    finally:
        c.post("/api/operators/remove", json={"email": "m31@klinik.test"})
        operator_tokens.temizle_hepsi()


# ── M32 ───────────────────────────────────────────────────────────────────────


def _sahte_istek(yol: str):
    return SimpleNamespace(
        url=SimpleNamespace(path=yol),
        headers={"x-pemf-tier": "baslangic"},  # gerçek-zamanlı DEĞİL → kuyruk adayı
        state=SimpleNamespace(),
    )


def test_KRITIK_M32_tedavi_uclari_DOLU_kuyrukta_BEKLEMEDEN_gecer(monkeypatch):
    from servers import entitlement as ent

    async def _senaryo():
        sem = asyncio.Semaphore(1)
        await sem.acquire()  # kuyruk DOLU: ağır bir analiz tutuyor
        monkeypatch.setattr(ent, "_ai_semaphore", sem)
        monkeypatch.setattr(ent, "TIER_ENFORCED", True)
        monkeypatch.setattr(ent, "AI_QUEUE_MAX_WAIT", 5.0)
        for yol in ("/api/ai/pro/stop", "/api/ai/ai_pro/frame", "/api/ai/landmark/auto"):
            gen = ent.ai_queue_gate(_sahte_istek(yol))
            try:
                await asyncio.wait_for(gen.__anext__(), 0.5)
            except asyncio.TimeoutError:
                raise AssertionError(f"TEDAVİ ucu {yol} AI kuyruğunda BEKLEDİ (durdurma/sürüş ağır analizin arkasında)")
            finally:
                await gen.aclose()
        # KARŞIT: analiz ucu aynı dolu kuyrukta GERÇEKTEN bekler (kapı kör değil)
        gen = ent.ai_queue_gate(_sahte_istek("/api/ai/vision/fgs"))
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(gen.__anext__(), 0.3)
        await gen.aclose()

    asyncio.run(_senaryo())
