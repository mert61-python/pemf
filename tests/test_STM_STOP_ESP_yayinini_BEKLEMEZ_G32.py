# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""1-G inceleme G-3.2 (Ö.4-Y8) — seans / AI Pro durdurmasında STM STOP'u ESP yayınını BEKLEMEZ.

ÖLÇÜLEN KUSUR (`b733a79`; önceden var, D1.104 ağırlaştırdı): `_stop_session_coils` önce ESP bobinlerine `_mqtt_publish`
yapıp SONRA STM bobinlerine STOP veriyordu. GERÇEK mosquitto 2.0.18 ile ölçüldü (ESP açık, seans bobin [1, 8]):
sağlıklı broker'da tek yayın ~1,02 sn → "Seansı Durdur"un ilk STM STOP'u 1,04 sn; yerel broker kimliği uyuşmazken
(D1.104 `--yenile` penceresi: broker eski parolaları tutar) yayın 2,08 sn'de başarısız → ilk STM STOP 3,09 sn.
ACİL DURDUR, seanssız durdurma ve kapanış STM'i ÖNCE durduruyordu — yalnız bu yol tersti.

SÖZLEŞME: ESP yayını yavaşken (1,5 sn) "Seansı Durdur" (bobin 1 + 8) ve AI Pro durdurma (1–8) STM STOP'unu
< 0,5 sn'de PORTA yazar; ESP STOP'u YİNE yayınlanır (STOP azaltılmaz). Ölçüt PORTA YAZILAN BAYTLAR (O-1.1 aparatı:
GERÇEK HeadlessCore + HWSender + HardwareController; tek olay döngüsü)."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest
from test_O11_STOP_yollari_ORTAK_HAVUZA_bagli_DEGIL import (  # noqa: F401 — fikstür
    _bobin1_sur,
    _ilk_stop_stm,
    aparat,
)

ESP_YAYIN_S = 1.5  # sağlıklı broker ~1 sn, kimlik uyuşmazlığı ~2 sn (ölçüldü)
SINIR_S = 0.5


def _aktif_seans_1_8(o, ad: str) -> None:
    with o.api._session_lock:
        o.api._active_session.clear()
        o.api._active_session.update(
            {
                "is_active": True,
                "session_id": ad,
                "coil_ids": [1, 8],
                "db_session_id": None,
                "started_epoch": time.time(),
                "start_mono": time.monotonic(),
                "mode": "Manuel",
            }
        )


@pytest.mark.parametrize(
    "yol",
    [
        ("seans_durdur", "/api/session/stop", _aktif_seans_1_8),
        ("ai_pro_stop", "/api/ai/pro/stop", lambda o, ad: o.api._active_session.clear()),
    ],
    ids=lambda y: y[0],
)
def test_KRITIK_G32_STM_STOPu_YAVAS_ESP_yayinini_BEKLEMEZ_ve_ESP_STOPu_yine_gider(aparat, monkeypatch, yol):
    import httpx
    from servers import live_state as _ls

    o = aparat
    ad, uc, hazirla = yol
    kilit = threading.Lock()
    yayin: list = []

    def _yavas_yayin(topic, payload):
        t = time.perf_counter()
        time.sleep(ESP_YAYIN_S)
        with kilit:
            yayin.append((t, topic, dict(payload)))
        return True

    monkeypatch.setattr(o.api, "_mqtt_publish", _yavas_yayin)
    monkeypatch.setattr(_ls, "esp_etkin", lambda: True)
    sonuc = []
    for i in range(5):
        _bobin1_sur(o)
        hazirla(o, f"g32-{ad}-{i}")
        with kilit:
            yayin.clear()

        async def _kos():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=o.api.app), base_url="http://cihaz") as c:
                t0 = time.perf_counter()
                gorev = asyncio.ensure_future(c.post(uc))
                while time.perf_counter() < t0 + SINIR_S and _ilk_stop_stm(o, t0) is None:
                    await asyncio.sleep(0.01)
                ts = _ilk_stop_stm(o, t0)
                await asyncio.wait_for(gorev, 15)
                return None if ts is None else round(ts - t0, 3)

        stm_s = asyncio.run(_kos())
        with kilit:
            esp_stop = [p for _t, tp, p in yayin if tp == "pemf/coil/8/control" and p.get("command") == "stop"]
        sonuc.append((stm_s, len(esp_stop)))
    print(f"G32 yol={ad} (stm_stop_s, esp_stop_sayisi)={sonuc}")
    assert all(n >= 1 for _s, n in sonuc), f"{ad}: ESP bobini 8'e STOP yayınlanmadı (STOP azaldı — Ö.4-Y8): {sonuc}"
    kotu = [s for s, _n in sonuc if s is None or s >= SINIR_S]
    assert not kotu, (
        f"{ad}: ESP yayını {ESP_YAYIN_S} sn sürerken STM STOP'u {SINIR_S} sn içinde PORTA gitmedi — STM durdurması ESP "
        f"yayınını BEKLİYOR (Ö.4-Y8). (stm_stop_s, esp_stop) = {sonuc}"
    )
