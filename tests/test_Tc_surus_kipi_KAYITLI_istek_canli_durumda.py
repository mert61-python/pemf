# Author: mertaygn, cglrgrkn
"""T-c (Tezgâh-2 #6, Y195) — backend'in KAYITLI sürüş kipi isteği canlı durumda (`coils[i].unipolarIstek`, yalnız-ek alan) ve yayında.

ÖLÇÜLEN KUSUR (Tezgâh-2, 2026-10-23): "All Unipolar" sonrası kart K=127 uyguladı ama yeniden açılan Sürüş Kipi ekranı kutuları 1–5 "BİP"
gösterdi — istek yalnız `HardwareController._unipolar_maskesi`ndeydi, istemciye hiç ulaşmıyordu; bileşen sabit varsayılandan başlıyordu.
SÖZLEŞME: `/api/coil/surus_kipi` kayıtlı isteği (yetenekle OR'lanmış: bir sonraki sürüşte karta giden kip) canlı duruma yazar ve DEĞİŞEN
bobini `coil_status` ile yayınlar; kartın bildirdiği ETKİN kip (`unipolar`) DEĞİŞMEZ. Donanım denetleyicisi sahte (yalnız
`surus_kipi_ayarla` sözleşmesi: istenen maskeyi döner) — canlı durum ve yayın gerçek modül.
"""

from __future__ import annotations

import asyncio
import copy

import pytest


class _HC:
    """`HardwareController.surus_kipi_ayarla` sözleşmesi: istek maskesini kaydeder ve döner (0xFF ile)."""

    def __init__(self):
        self.maskeler: list[int] = []

    def surus_kipi_ayarla(self, maske: int) -> int:
        self.maskeler.append(int(maske))
        return int(maske) & 0xFF


@pytest.fixture
def ortam(monkeypatch):
    from servers import api_server as api
    from servers import live_state as ls

    yayin: list[dict] = []
    monkeypatch.setattr(ls, "_ws_broadcast_sync", lambda m: yayin.append(m))
    hc = _HC()
    monkeypatch.setattr(api.state, "hardware", hc)
    with ls._live_state_lock:
        eski = copy.deepcopy(ls._live_state["coils"])
    try:
        yield api, ls, hc, yayin
    finally:
        with ls._live_state_lock:
            ls._live_state["coils"].clear()
            ls._live_state["coils"].update(eski)


def _gonder(api, unipolar: list[bool]) -> dict:
    return asyncio.run(api.set_surus_kipi(api.SurusKipiPayload(unipolar=unipolar)))


def test_KRITIK_kayitli_istek_CANLI_duruma_yazilir_ve_YAYINLANIR(ortam):
    api, ls, hc, yayin = ortam
    with ls._live_state_lock:
        for i in range(7):
            ls._live_state["coils"][i]["unipolarIstek"] = None
            ls._live_state["coils"][i]["unipolar"] = False  # kartın bildirdiği (eski) kip
    yanit = _gonder(api, [True] * 7)
    assert yanit["status"] == "success" and hc.maskeler == [0x7F]
    with ls._live_state_lock:
        istek = [ls._live_state["coils"][i].get("unipolarIstek") for i in range(7)]
        kart = [ls._live_state["coils"][i].get("unipolar") for i in range(7)]
    assert istek == [True] * 7, f"kayıtlı istek canlı durumda yok: {istek}"
    assert kart == [False] * 7, "kartın BİLDİRDİĞİ kip istekle ezildi (ETKİN ≠ İSTEK)"
    yayinlanan = sorted(
        m["coilId"] for m in yayin if m.get("type") == "coil_status" and m["data"].get("unipolarIstek") is True
    )
    assert yayinlanan == [1, 2, 3, 4, 5, 6, 7], f"değişen bobinler yayınlanmadı: {yayin}"


def test_KRITIK_yeteneksiz_bobin_istegi_DAIMA_unipolar_degismeyen_YAYINLANMAZ(ortam):
    api, ls, _hc, yayin = ortam
    _gonder(api, [True] * 7)
    yayin.clear()
    _gonder(api, [False] * 7)  # "Hepsi Bipolar" (6-7 yeteneksiz: istek ne olursa olsun tek yönlü)
    with ls._live_state_lock:
        istek = [ls._live_state["coils"][i].get("unipolarIstek") for i in range(7)]
    assert istek == [False] * 5 + [True, True], istek
    assert sorted(m["coilId"] for m in yayin if m.get("type") == "coil_status") == [1, 2, 3, 4, 5], yayin
    yayin.clear()
    _gonder(api, [False] * 7)
    assert not [m for m in yayin if m.get("type") == "coil_status"], "değişmeyen istek yeniden yayınlandı"


def test_canli_bobin_durumunda_alan_VAR():
    from servers import live_state as ls

    with ls._live_state_lock:
        assert all("unipolarIstek" in ls._live_state["coils"][i] for i in range(8))
