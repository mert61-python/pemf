# Author: mertaygn, cglrgrkn
"""SGI-2.4 (bağımsız inceleme) — SG.G4-5 "jeton yalnız TESLİM edilen analizde": istemcisi KOPAN analiz jeton düşürmez.

Sahte yalnız EN ALT katta: ASGI `receive` (gövde bir kez, sonra `http.disconnect` = istemci koptu / hiç dönmeyen bekleme = istemci
bağlı), Supabase taşıması, termal model. `Request.is_disconnected` YAMALANMAZ (SG kapısı onu yamalıyordu → ürünün kopma sorusu hiç
koşmuyordu; `api_server`daki üç `@app.middleware("http")` arkasında o yoklama hep "bağlı" döner — ölçüldü).
KARŞIT: aynı `jeton_tuketimi`, ara katmansız küçük uygulamada da, tek boş `@app.middleware("http")` arkasında da kopmayı görür;
bağlı istemci TAM BİR jeton öder. (SGI-2.5 eşzamanlılık ölçümü sahip kararına kadar raporda — `DUZELTME-SG-INCELEME.md`.)
"""

from __future__ import annotations

import asyncio
import base64
import importlib
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, Depends, FastAPI, File, Request, UploadFile

KOK = Path(__file__).resolve().parents[1]
TERMAL = KOK / "tests" / "xai_veri" / "termal_hasta_03b_224.png"


def _jwt(sub: str) -> str:
    b = base64.urlsafe_b64encode(json.dumps({"sub": sub}).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJIUzI1NiJ9.{b}.sahte-imza"


class _Termal:
    def predict(self, yol, threshold=0.5):
        return {"label": "Healthy", "probability_sick": 0.1, "confidence": 0.9}


@pytest.fixture()
def ortam(tmp_path, monkeypatch):
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))
    j = importlib.import_module("servers.jeton")
    from servers import ai_router as air
    from servers import api_server

    monkeypatch.setattr(j, "JETON_ENFORCED", True)
    monkeypatch.setattr(j, "_son_uzlastirma", None, raising=False)
    monkeypatch.setattr(j, "_canli_oturumlar", {})
    sunucu = {"bakiye": 1000, "defter": set(), "dusulen": []}
    rpc_kilit = threading.Lock()

    def _oku(token):
        return {"aylik_hak": 0, "satin_alinan": sunucu["bakiye"], "odeme_modeli": "on_odemeli", "kullandikca_borc": 0}

    def _rpc(token, **k):
        # supabase_jetonlar.sql::jeton_tuket — satır kilidi + (user_id, istek_id) idempotansı + 'yetersiz' reddi
        with rpc_kilit:
            iid = str(k.get("istek_id") or "")
            if iid in sunucu["defter"]:
                return True
            m = int(k.get("miktar") or 0)
            if sunucu["bakiye"] < m:
                return False
            sunucu["bakiye"] -= m
            sunucu["defter"].add(iid)
            sunucu["dusulen"].append(dict(k))
            return True

    monkeypatch.setattr(j, "_bakiye_satiri_oku", _oku)
    monkeypatch.setattr(j, "_tuketim_gonder_canli", _rpc)
    model = _Termal()
    gercek = air._get_or_load_model
    monkeypatch.setattr(air, "_get_or_load_model", lambda ad, y: model if ad == "thermal" else gercek(ad, y))
    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    monkeypatch.delenv("PEMF_AI_DOMAIN_GUARD", raising=False)
    yield SimpleNamespace(app=api_server.app, j=j, sunucu=sunucu, model=model, tmp=tmp_path, monkeypatch=monkeypatch)
    t = getattr(j, "_son_uzlastirma", None)
    if t is not None:
        t.join(timeout=10)


def _scope(yol: str, govde_uzunlugu: int, ctype: str, port: int) -> dict:
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": yol,
        "raw_path": yol.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"127.0.0.1"),
            (b"content-type", ctype.encode()),
            (b"content-length", str(govde_uzunlugu).encode()),
            (b"authorization", f"Bearer {_jwt('hekim-a')}".encode()),
        ],
        "client": ("127.0.0.1", port),
        "server": ("127.0.0.1", 80),
    }


async def _asgi_bir(app, kopuk: bool, port: int = 51240, yol: str = "/api/ai/vision/thermal") -> int:
    from urllib3 import encode_multipart_formdata

    govde, ctype = encode_multipart_formdata({"file": ("k.png", TERMAL.read_bytes(), "image/png")})
    gonderildi = {"n": 0}
    giden = []

    async def receive():
        if gonderildi["n"] == 0:
            gonderildi["n"] = 1
            return {"type": "http.request", "body": govde, "more_body": False}
        if kopuk:
            return {"type": "http.disconnect"}  # uvicorn: bağlantı koptuysa receive() beklemeden http.disconnect döner
        await asyncio.Event().wait()  # istemci bağlı: yanıt bitene dek mesaj yok

    async def send(m):
        giden.append(m)

    await app(_scope(yol, len(govde), ctype, port), receive, send)
    return [m for m in giden if m["type"] == "http.response.start"][0]["status"]


def _kucuk_uygulama(j, ara_katman: bool):
    """`jeton_tuketimi` GERÇEK; karar kapısı yerine sayaç tüketicisi bırakan küçük bağımlılık."""
    sayac = {"n": 0}

    async def _kapi(request: Request):
        def _tuketici():
            sayac["n"] += 1

        setattr(request.state, j._BEKLEYEN_TUKETIM, _tuketici)

    r = APIRouter(dependencies=[Depends(_kapi), Depends(j.jeton_tuketimi, scope="function")])

    @r.post("/api/ai/vision/thermal")
    async def _uc(file: UploadFile = File(None)):
        await file.read()
        return {"status": "success"}

    app = FastAPI()
    if ara_katman:

        @app.middleware("http")
        async def _bos(request, call_next):
            return await call_next(request)

    app.include_router(r)
    return app, sayac


# ── SGI-2.4 ──────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_SGI_2_4_GERCEK_uygulama_istemcisi_KOPAN_analiz_JETON_dusurmez(ortam):
    o = ortam
    assert asyncio.run(_asgi_bir(o.app, kopuk=True)) == 200
    assert o.sunucu["dusulen"] == [], f"istemcisi kopan analiz için jeton DÜŞTÜ: {o.sunucu['dusulen']}"


def test_SGI_2_4_KARSIT_GERCEK_uygulama_bagli_istemci_TAM_BIR_jeton(ortam):
    o = ortam
    assert asyncio.run(_asgi_bir(o.app, kopuk=False)) == 200
    assert [k["detay"] for k in o.sunucu["dusulen"]] == ["goruntu"], o.sunucu["dusulen"]


def test_SGI_2_4_KARSIT_ara_katmansiz_uygulamada_kopma_GORULUR():
    j = importlib.import_module("servers.jeton")
    app, sayac = _kucuk_uygulama(j, ara_katman=False)
    assert asyncio.run(_asgi_bir(app, kopuk=True)) == 200
    assert sayac["n"] == 0, "ara katmansız uygulamada da kopma görülmedi (sonda kör)"
    assert asyncio.run(_asgi_bir(app, kopuk=False)) == 200
    assert sayac["n"] == 1


def test_SGI_2_4_NEDEN_tek_bos_http_ara_katmani_kopmayi_gizler():
    j = importlib.import_module("servers.jeton")
    app, sayac = _kucuk_uygulama(j, ara_katman=True)
    assert asyncio.run(_asgi_bir(app, kopuk=True)) == 200
    assert sayac["n"] == 0, "boş @app.middleware('http') arkasında istemci kopması GÖRÜLMEDİ → jeton düştü"
    assert asyncio.run(_asgi_bir(app, kopuk=False)) == 200
    assert sayac["n"] == 1
