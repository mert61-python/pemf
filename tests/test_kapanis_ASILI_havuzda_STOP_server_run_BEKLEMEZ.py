# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""1-G inceleme G-1.1 (Ö.4-Y8) — servis/Ctrl+C kapanışında donanım STOP'u `server.run()`'ın dönmesini BEKLEMEZ.

ÖLÇÜLEN KUSUR (`b733a79`, önceden var — O-1.1 çürütme sorusu "asılı diskte kapanış yolu"): `main()` STOP'u
`try: server.run() … finally: _shutdown(...)` ile verir. uvicorn 0.48'in `asyncio_run`'ı (py3.10) kapanışta
`loop.shutdown_default_executor()` ile olay döngüsünün ORTAK havuzundaki işleri BEKLER; bitmeyen bir `to_thread` işi
(asılı disk: DB yazımı) varken `server.run()` 20 sn'de DÖNMEDİ (`timeout_graceful_shutdown=8` istek görevini iptal etti,
iş parçacığı sürdü) → `_shutdown` hiç koşmuyor, bobinler NSSM'in sert sonlandırmasına (15 sn) + firmware ölü-adamına
dek sürülüyordu. (Sahadaki launcher modelinde backend sinyalsiz öldürülür, STOP'u ACİL DURDUR ucu verir — O-1.1.)

SÖZLEŞME: kapanış İSTENİR İSTENMEZ (uvicorn'un yakaladığı sinyal → `server.handle_exit`) kapanış durumu kurulur
(START reddi — D1.75 sırası: kapanış STOP'tan ÖNCE) ve STOP < 1 sn'de PORTA gider; `server.run()` o an hâlâ
dönmemiş olsa da. Ölçüt PORTA YAZILAN BAYTLAR (O-1.1 aparatı: GERÇEK HeadlessCore + HWSender + HardwareController).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import socket
import threading
import time

from test_O11_STOP_yollari_ORTAK_HAVUZA_bagli_DEGIL import (  # noqa: F401 — fikstür
    _bobin1_sur,
    _ilk_stop_stm,
    aparat,
)


def _bos_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_KRITIK_kapanis_istenince_STOP_PORTA_gider_asili_havuz_server_run_u_bekletse_de(aparat):
    import backend_service as bs
    import httpx
    from fastapi import FastAPI

    o = aparat
    olay, basladi = threading.Event(), threading.Event()
    app = FastAPI()

    @app.post("/asili")
    async def _asili():
        basladi.set()
        await asyncio.to_thread(olay.wait, 60)  # asılı disk benzeri: ortak havuzda BİTMEYEN iş
        return {"ok": True}

    port = _bos_port()
    server = bs._build_server(app, argparse.Namespace(host="127.0.0.1", port=port, log_level="WARNING"))
    isleyiciler = {
        s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM, getattr(signal, "SIGBREAK", None)) if s
    }
    calisma = threading.Thread(target=server.run, name="test-uvicorn", daemon=True)
    try:
        bs._install_signal_handlers(server, logging.getLogger("test_kapanis"), o.api)
        # Aparat: uvicorn serve SÜRERKEN sinyali `server.handle_exit`'e verir (capture_signals) — sarılmış işleyici o.
        with server.capture_signals():
            assert signal.getsignal(signal.SIGINT) == server.handle_exit, "aparat: uvicorn sinyal işleyicisi değişti"
        calisma.start()
        son = time.monotonic() + 15
        while time.monotonic() < son and not server.started:
            time.sleep(0.05)
        assert server.started, "aparat: uvicorn başlamadı"

        def _istek() -> None:
            try:
                httpx.post(f"http://127.0.0.1:{port}/asili", timeout=90)
            except Exception:
                pass  # kapanışta bağlantı kesilebilir — ölçüt bu değil

        threading.Thread(target=_istek, name="test-asili-istek", daemon=True).start()
        assert basladi.wait(10), "aparat: asılı iş başlamadı"
        _bobin1_sur(o)  # telde gerçek sürüş (duty>0 paket porta yazıldı)
        t0 = time.perf_counter()
        server.handle_exit(signal.SIGINT, None)  # uvicorn'un yakaladığı kapanış sinyali
        while time.perf_counter() < t0 + 1.0 and _ilk_stop_stm(o, t0) is None:
            time.sleep(0.01)
        stop_s = _ilk_stop_stm(o, t0)
        hala_calisiyor = calisma.is_alive()
        engel = o.mandal.baslatma_engeli()
        assert stop_s is not None, (
            "kapanış istendi, ortak havuzda asılı bir iş var: STOP 1 sn içinde PORTA GİTMEDİ — donanım STOP'u "
            f"`server.run()`'ın dönmesine bağlı (server.run hâlâ çalışıyor={hala_calisiyor}) (Ö.4-Y8)"
        )
        assert hala_calisiyor, "aparat: server.run() döndü — asılı iş senaryosu kurulamadı (ölçüm anlamsız)"
        assert engel, "kapanış istendikten sonra START engeli YOK — kapanış durumu STOP'tan önce kurulmadı (D1.75)"
    finally:
        olay.set()
        calisma.join(timeout=30)
        for s, h in isleyiciler.items():
            signal.signal(s, h)
        o.mandal.kapanis_kaldir()  # süreç geneli kapanış durumu sonraki testlere sızmasın
    assert not calisma.is_alive(), "aparat: asılı iş bırakılınca server.run() dönmedi"
