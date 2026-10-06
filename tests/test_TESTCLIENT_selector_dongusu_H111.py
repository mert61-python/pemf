# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""H-11.1 · 1-H §8 #10 (1-H incelemesi) — Windows'ta TÜM TestClient'lar SELECTOR olay döngüsüyle koşar (conftest merkezi yaması).

ÖLÇÜLEN KUSUR (1-H kapanışı `kayit/kapanis.out`; 1-C'de de): tam süit %8'de "Windows fatal exception: access violation" —
çöken iş parçacığı "Garbage-collecting" (TestClient'ın anyio portal döngüsü), ana iş parçacığı `test_ai_log_delete_scope`
POST'unda; çıkış 139, özet satırı ve junit YOK. Kök: gömülü CPython 3.10.2 ProactorEventLoop + TestClient'ın istek başına
açıp kapattığı döngüler → bekleyen G/Ç'li `Overlapped` GC'de serbest. 1-C çözümü (`loop_factory=SelectorEventLoop`)
yalnız `ai_pro_aparati.istemci()`'deydi; TestClient kuran diğer 121 dosya Proactor'daydı. Ürün etkilenmez (uvicorn tek döngü).

KAPI: (1) açık seçenek VERMEYEN bir TestClient'ın uç içinde gördüğü döngü `asyncio.SelectorEventLoop`; (2) KARŞIT — açıkça
Proactor isteyen test kendi seçimini korur (yama açık tercihi ezmez; ölçüm Proactor'u da görebiliyor).
"""

from __future__ import annotations

import asyncio
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Proactor yalnız Windows'un varsayılan döngüsü")


def _uygulama() -> FastAPI:
    app = FastAPI()

    @app.get("/dongu")
    async def dongu():
        d = asyncio.get_running_loop()
        return {"selector": isinstance(d, asyncio.SelectorEventLoop), "tur": type(d).__name__}

    return app


def test_KRITIK_H111_TestClient_varsayilan_dongusu_SELECTOR():
    with TestClient(_uygulama()) as c:
        y = c.get("/dongu").json()
    assert y["selector"] is True, (
        f"seçeneksiz TestClient {y['tur']} döngüsünde — Proactor + istek başına döngü GC'de erişim ihlaliyle süreci öldürür"
    )


def test_KARSIT_H111_acik_PROACTOR_secimi_korunur():
    with TestClient(_uygulama(), backend_options={"loop_factory": asyncio.ProactorEventLoop}) as c:
        y = c.get("/dongu").json()
    assert y["selector"] is False and "Proactor" in y["tur"], f"açık döngü seçimi ezildi / ölçüm kör: {y}"
