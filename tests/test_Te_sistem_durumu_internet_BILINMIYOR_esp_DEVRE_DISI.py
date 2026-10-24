# Author: mertaygn, cglrgrkn
"""T-e (Tezgâh-2 #8, Y195) — `/api/gateway/status` ölçülmemiş interneti "kapalı" diye vermez; ESP'nin bilinçli kapalı olduğunu söyler.

ÖLÇÜLEN KUSUR (Tezgâh-2, 2026-10-23): Sistem Durumu "İnternet Bağlantısı" ağ izleme servisi yokken "Kapalı" (kırmızı) — uç
`networkOnline: bool(network_status.get("internet_connected"))` servis yokken / ilk ölçümden önce `False` veriyordu; ESP bilinçli
kapalıyken "Cihaz Köprüsü" kırmızı.
SÖZLEŞME (yalnız-ek alanlar): `internetBilinmiyor` = servis durumu yok ya da henüz ölçmedi (`gateway_mode` "unknown"); `espEtkin` =
`live_state.esp_etkin()`. `networkOnline` eski istemciler için bool KALIR. Çekirdek sahte (yalnız `get_service_status` sözleşmesi).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest


@pytest.fixture
def uc(monkeypatch):
    from servers import api_server as api
    from servers import system_router as sr

    def _kur(servis: dict, esp: bool = False):
        monkeypatch.setattr(api.state, "core", SimpleNamespace(get_service_status=lambda: servis))
        monkeypatch.setattr(api.live_state, "esp_etkin", lambda: esp)
        return asyncio.run(sr.gateway_status())

    return _kur


def test_KRITIK_ag_servisi_YOKKEN_internet_BILINMIYOR(uc):
    d = uc({"mosquitto": {}})
    assert d["internetBilinmiyor"] is True, d
    assert d["networkOnline"] is False and isinstance(d["networkOnline"], bool), "eski istemci sözleşmesi bozuldu"


def test_KRITIK_ilk_olcumden_ONCE_internet_BILINMIYOR(uc):
    d = uc({"network": {"internet_connected": False, "gateway_mode": "unknown"}})
    assert d["internetBilinmiyor"] is True, d


@pytest.mark.parametrize(("var", "online"), [(True, True), (False, False)])
def test_KARSIT_olculmus_internet_BILINIR(uc, var, online):
    d = uc({"network": {"internet_connected": var, "gateway_mode": "online" if var else "offline"}})
    assert d["internetBilinmiyor"] is False and d["networkOnline"] is online, d


@pytest.mark.parametrize("esp", [False, True])
def test_KRITIK_esp_etkinligi_bildirilir(uc, esp):
    assert uc({}, esp=esp)["espEtkin"] is esp
