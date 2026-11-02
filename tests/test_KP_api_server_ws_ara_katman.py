# Author: mertaygn, cglrgrkn
"""KP-1 · apps/backend/servers/api_server.py · sözleşmeler: `/ws` uç noktası (kimlik katmanı yüklenemezse 1011, bozuk Origin
bağlantıyı düşürmez, LAN istemcisine token istenmez, geçersiz token'da accept hatası olsa da 1008, ping→pong, bozuk ileti
yok sayılır, kapanışta istemci listeden düşer — zaten düşmüşse de), HTTP ara katmanları (`X-Build-Id`, OPTIONS kimliksiz
geçer, token denetimi patlarsa 401, `/api/v1/` savunma yeniden yazımı), DNS-rebinding katmanı (http/websocket dışı kapsam
geçer, yabancı Host'lu websocket 4400 ile kapanır, tünel adı kasadan), `_app_data_dir` yedeği.

Sahte EN ALT katta: WebSocket taşıması (ASGI uç nesnesi: başlıklar, istemci, accept/close/send/receive kaydı), kasa
(`utils.secrets_manager.get_secret`), API token'ı (`servers.auth._token`), yol yardımcısı (`utils.path_utils`).
Sunucu yalnız süreç içi (`TestClient` `with` içinde) — dinleyici yok.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient


@pytest.fixture
def api(monkeypatch):
    from servers import api_server as a
    from servers import auth

    monkeypatch.setattr(auth, "_require", False)
    with a._ws_lock:
        istemciler_once = list(a._ws_clients)
    a._rl_hits.clear()
    try:
        yield a
    finally:
        a._rl_hits.clear()
        with a._ws_lock:
            a._ws_clients[:] = istemciler_once


class _SahteWS:
    """ASGI WebSocket yerine — yalnız taşıma katmanı."""

    def __init__(
        self, api, *, headers=None, host="127.0.0.1", query=None, gelen=(), accept_hata=False, kendini_dusur=False
    ):
        self._api = api
        self.headers = dict(headers or {})
        self.client = SimpleNamespace(host=host)
        self.query_params = dict(query or {})
        self._gelen = list(gelen)
        self._accept_hata = accept_hata
        self._kendini_dusur = kendini_dusur
        self.kabul = False
        self.kapanis = None
        self.giden: list = []

    async def accept(self):
        if self._accept_hata:
            raise RuntimeError("Unexpected ASGI message 'websocket.accept'")
        self.kabul = True

    async def close(self, code=1000):
        self.kapanis = code

    async def send_text(self, metin):
        self.giden.append(json.loads(metin))

    async def receive_text(self):
        if self._gelen:
            return self._gelen.pop(0)
        if self._kendini_dusur:
            with self._api._ws_lock:
                self._api._ws_clients.remove(self)
        raise WebSocketDisconnect(1000)


def _kos(api, ws):
    asyncio.run(api.websocket_endpoint(ws))
    return ws


def test_WS_kimlik_katmani_YUKLENEMEZSE_1011_ile_kapanir_kabul_YOK(api, monkeypatch):
    """`require_auth` istisna atıyor → bağlantı KABUL EDİLMEZ, 1011 ile kapanır, istemci listesine girmez (fail-closed)."""
    from servers import auth

    def _patlayan():
        raise RuntimeError("auth modülü bozuk")

    monkeypatch.setattr(auth, "require_auth", _patlayan)
    ws = _kos(api, _SahteWS(api))
    assert (ws.kabul, ws.kapanis) == (False, 1011)
    assert ws not in api._ws_clients


def test_WS_BOZUK_origin_baglantiyi_dusurmez_anlik_goruntu_gider(api):
    """Origin ayrıştırılamıyor ("http://[bozuk") → köken denetimi atlanır, bağlantı kabul edilir, ilk ileti `snapshot`."""
    ws = _kos(api, _SahteWS(api, headers={"origin": "http://[bozuk", "host": "pemf.local:8000"}))
    assert ws.kabul is True and ws.kapanis is None
    assert ws.giden and ws.giden[0]["type"] == "snapshot"


def test_WS_kimlik_ZORUNLU_ama_LAN_istemcisi_tokensiz_kabul(api, monkeypatch):
    """Kimlik zorunlu + istemci LAN (192.168.x) + token yok → yerel sayılır, bağlantı kabul edilir ve anlık görüntü gider."""
    from servers import auth

    monkeypatch.setattr(auth, "_require", True)
    ws = _kos(api, _SahteWS(api, host="192.168.1.20"))
    assert ws.kabul is True and ws.kapanis is None
    assert ws.giden[0]["type"] == "snapshot"


def test_WS_UZAK_gecersiz_token_accept_patlasa_da_1008(api, monkeypatch):
    """Kimlik zorunlu + uzak istemci + yanlış token + `accept` istisna atıyor → yine 1008 (politika) ile kapanır, listeye girmez."""
    from servers import auth

    monkeypatch.setattr(auth, "_require", True)
    monkeypatch.setattr(auth, "_token", "dogru-jeton")
    ws = _kos(api, _SahteWS(api, host="203.0.113.9", query={"token": "yanlis"}, accept_hata=True))
    assert ws.kapanis == 1008
    assert ws not in api._ws_clients and ws.giden == []


def test_WS_ping_PONG_bozuk_ileti_yok_sayilir_kapanista_listeden_duser(api):
    """Gelen: ping, bozuk JSON, bilinmeyen tür → giden: snapshot, pong (yalnız bir kez); kopuşta istemci listeden çıkar."""
    ws = _kos(api, _SahteWS(api, gelen=['{"type":"ping"}', "{bozuk", '{"type":"baska"}']))
    assert [m["type"] for m in ws.giden] == ["snapshot", "pong"]
    assert ws not in api._ws_clients


def test_WS_listeden_ZATEN_dusmusse_kapanis_istisnasiz(api):
    """İstemci (ör. ölü yayın temizliğiyle) listeden zaten çıkarılmışken kopuş → uç istisna sızdırmadan döner, liste tutarlı."""
    ws = _kos(api, _SahteWS(api, kendini_dusur=True))
    assert ws.kabul is True
    assert ws not in api._ws_clients


def test_paket_kimligi_VARSA_X_Build_Id_basligi(api, monkeypatch):
    """`_BUILD_ID` dolu → her yanıtta `X-Build-Id` başlığı aynı değerle."""
    monkeypatch.setattr(api, "_BUILD_ID", "kp1-sha-abc")
    with TestClient(api.app, client=("127.0.0.1", 50001)) as c:
        r = c.get("/api/health")
    assert r.headers.get("X-Build-Id") == "kp1-sha-abc"


def test_OPTIONS_kimlik_zorunlu_uzakta_bile_401_ALMAZ(api, monkeypatch):
    """Kimlik zorunlu + uzak istemci + korumalı yola OPTIONS (preflight değil) → kimlik denetimi atlanır: 401 DEĞİL (yol OPTIONS
    tanımlamadığı için 405)."""
    from servers import auth

    monkeypatch.setattr(auth, "_require", True)
    with TestClient(api.app, client=("203.0.113.10", 50002)) as c:
        r = c.options("/api/system/info")
    assert r.status_code == 405


def test_token_denetimi_PATLARSA_401_api_anahtari_metni(api, monkeypatch):
    """Kimlik zorunlu + uzak istemci + `check_token` istisna atıyor → 401, gövde `hata.apiAnahtari` (fail-closed)."""
    from servers import auth
    from utils import ceviri

    monkeypatch.setattr(auth, "_require", True)

    def _patlayan(_t):
        raise RuntimeError("token deposu okunamadı")

    monkeypatch.setattr(auth, "check_token", _patlayan)
    with TestClient(api.app, client=("203.0.113.11", 50003)) as c:
        r = c.get("/api/system/info", headers={"X-API-Key": "x"})
    assert r.status_code == 401
    assert r.json() == {"detail": ceviri.t("hata.apiAnahtari", dil="tr")}


def test_auth_katmani_V1_yolunu_savunma_amacli_yeniden_yazar(api):
    """Dış takma ad katmanı atlanmış olsa da `_auth_middleware` `/api/v1/x` yolunu `/api/x` olarak alt katmana verir."""
    from starlette.requests import Request
    from starlette.responses import Response

    kapsam = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/health",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 50004),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    gorulen: list = []

    async def _sonraki(istek):
        gorulen.append(istek.scope["path"])
        return Response("ok")

    yanit = asyncio.run(api._auth_middleware(Request(kapsam), _sonraki))
    assert gorulen == ["/api/health"] and yanit.status_code == 200


def test_rebind_katmani_HTTP_WS_DISI_kapsami_aynen_gecirir(api):
    """`lifespan` kapsamı → iç uygulama aynı (scope, receive, send) ile çağrılır, Host denetimi yapılmaz."""
    cagri: list = []

    async def _ic(scope, receive, send):
        cagri.append(scope["type"])

    katman = api._RebindKorumaMiddleware(_ic)
    asyncio.run(katman({"type": "lifespan"}, None, None))
    assert cagri == ["lifespan"]


def test_rebind_katmani_YABANCI_hostlu_WEBSOCKET_4400_ile_kapanir(api, monkeypatch):
    """websocket kapsamı + yabancı DNS adı Host → iç uygulama ÇAĞRILMAZ, `websocket.close` kod 4400 gönderilir."""
    from utils import secrets_manager

    monkeypatch.setattr(secrets_manager, "get_secret", lambda *a, **k: "")
    giden: list = []
    cagri: list = []

    async def _ic(scope, receive, send):
        cagri.append(scope)

    async def _gonder(m):
        giden.append(m)

    katman = api._RebindKorumaMiddleware(_ic)
    asyncio.run(katman({"type": "websocket", "headers": [(b"host", b"saldirgan.example.com:8000")]}, None, _gonder))
    assert cagri == [] and giden == [{"type": "websocket.close", "code": 4400}]


def test_host_izni_TUNEL_adi_kasadan_eslesirse_izinli_kasa_patlarsa_RED(api, monkeypatch):
    """Host kasadaki `tunnel_hostname` ile aynı → izinli; kasa okuması istisna atarsa → izinsiz (fail-closed)."""
    from utils import secrets_manager

    monkeypatch.setattr(
        secrets_manager, "get_secret", lambda ad, **k: "Klinik.Ornek.Com" if ad == "tunnel_hostname" else ""
    )
    assert api._host_izinli("klinik.ornek.com", ()) is True
    assert api._host_izinli("baska.ornek.com", ()) is False

    def _patlayan(*a, **k):
        raise OSError("kasa kilitli")

    monkeypatch.setattr(secrets_manager, "get_secret", _patlayan)
    assert api._host_izinli("klinik.ornek.com", ()) is False


@pytest.mark.parametrize("appdata_var", [True, False])
def test_app_data_dizini_YARDIMCI_patlarsa_APPDATA_yedegi(api, monkeypatch, tmp_path, appdata_var):
    """`get_app_data_directory` istisna atıyor → `APPDATA/PEMF_GUI` (APPDATA yoksa `~/AppData/Roaming/PEMF_GUI`)."""
    from utils import path_utils

    def _patlayan():
        raise OSError("ProgramData okunamadı")

    monkeypatch.setattr(path_utils, "get_app_data_directory", _patlayan)
    if appdata_var:
        monkeypatch.setenv("APPDATA", str(tmp_path))
        assert api._app_data_dir() == tmp_path / "PEMF_GUI"
    else:
        monkeypatch.delenv("APPDATA", raising=False)
        assert api._app_data_dir() == Path.home() / "AppData" / "Roaming" / "PEMF_GUI"
