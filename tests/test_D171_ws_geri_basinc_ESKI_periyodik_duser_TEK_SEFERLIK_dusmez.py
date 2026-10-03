# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.71 · B-1.11 + B-1.27 — WS geri-basınç sınırında GELEN YENİ ileti değil EN ESKİ PERİYODİK anlık görüntü düşer; tek
seferlik geçişler (STM kopması, seans bitişi, E-stop) ASLA düşmez; bekleyen sayacı serileştirmeden SONRA artar.

ÖLÇÜLEN KUSUR (DENETIM-01 tv-F7_2, v-A25): gönderimi tıkanan tek bir istemci kuyruğu 64'e doldurunca sınırdaki dal YENİ
iletiyi `return` ile atıyordu (yorumu "ESKİSİNİ düşür" derken) → sağlıklı masaüstü de STM kopmasını, E-stop'u, seans
bitişini HİÇ görmüyordu (11/11 kayıp) ve durum kendiliğinden düzelmiyordu. B-1.27: `_ws_pending += 1` `json.dumps`tan
ÖNCE → 64 serileştirilemeyen yayından sonra sayaç kalıcı 64, bütün canlı akış ölür (hata çağırana da sızar).

GERÇEK: `live_state._ws_broadcast_sync`, `update_live_stm_status`, asyncio gönderim kilidi. Sahte: iki WS istemcisi
(biri gönderimde tıkanır, biri kaydeder). Olay döngüsü test iş parçacığında adım adım koşturulur.
"""

from __future__ import annotations

import asyncio
import json

import pytest


class _Tikanan:
    """İlk gönderimde `serbest` olayı kurulana dek bekler (yarı-açık istemci); sonra hemen gönderir."""

    def __init__(self):
        self.serbest = asyncio.Event()
        self.gonderim = 0

    async def send_text(self, data):
        await self.serbest.wait()
        self.gonderim += 1

    async def close(self, code=None):
        pass


class _Saglikli:
    def __init__(self):
        self.alinan: list[dict] = []

    async def send_text(self, data):
        self.alinan.append(json.loads(data))

    async def close(self, code=None):
        pass


@pytest.fixture
def ortam(monkeypatch):
    from servers import live_state as ls

    dongu = asyncio.new_event_loop()
    tikanan, saglikli = _Tikanan(), _Saglikli()
    # STM önce ÇEVRİMİÇİ (istemci yokken yayın erken döner) — kopuş bir GEÇİŞ olsun.
    monkeypatch.setattr(ls, "_ws_clients", [])
    ls.update_live_stm_status(True)
    monkeypatch.setattr(ls, "_event_loop", dongu)
    monkeypatch.setattr(ls, "_ws_clients", [tikanan, saglikli])
    monkeypatch.setattr(ls, "_ws_send_lock", None)
    monkeypatch.setattr(ls, "_ws_pending", 0)
    # raising=False: kapı D1.71 ÖNCESİ kodda da (alan yokken) davranışı ölçebilsin (önce-kırmızı).
    monkeypatch.setattr(ls, "_ws_bekleyenler", __import__("collections").deque(), raising=False)
    monkeypatch.setattr(ls, "_ws_dropped_total", 0)
    try:
        yield ls, dongu, tikanan, saglikli
    finally:
        tikanan.serbest.set()
        for _ in range(100):
            if ls._ws_pending <= 0:
                break
            dongu.run_until_complete(asyncio.sleep(0.005))
        dongu.close()
        monkeypatch.setattr(ls, "_ws_clients", [])
        ls.update_live_stm_status(False)


def _adim(dongu, n: int = 3) -> None:
    for _ in range(n):
        dongu.run_until_complete(asyncio.sleep(0.005))


def _bosalt(ls, dongu, tikanan) -> None:
    tikanan.serbest.set()
    for _ in range(400):
        if ls._ws_pending == 0:
            return
        dongu.run_until_complete(asyncio.sleep(0.005))


def _sensor(n: int) -> dict:
    return {"type": "sensor_data", "coilId": 6, "timestamp": n, "data": {"magneticMt": 1.0, "n": n}}


def test_KRITIK_kuyruk_doluyken_STM_kopmasi_saglikli_istemciye_ULASIR(ortam):
    ls, dongu, tikanan, saglikli = ortam
    ls._ws_broadcast_sync(_sensor(0))
    _adim(dongu)  # ilk gönderim tıkanan istemcide asılı → kilit tutuluyor
    for n in range(1, 80):
        ls._ws_broadcast_sync(_sensor(n))
    assert ls._ws_pending >= ls._WS_MAX_PENDING_BROADCASTS, f"aparat: kuyruk dolmadi ({ls._ws_pending})"
    ls.update_live_stm_status(False)  # GERÇEK kopuş yayını (tek seferlik geçiş)
    for n in range(80, 90):
        ls._ws_broadcast_sync(_sensor(n))
    _bosalt(ls, dongu, tikanan)
    assert ls._ws_pending == 0, f"bekleyen sayaci sizdi: {ls._ws_pending}"
    stm = [m for m in saglikli.alinan if m.get("type") == "stm_status"]
    assert stm, "STM KOPMASI saglikli istemciye HIC ulasmadi (kuyruk doluyken yeni ileti atildi)"
    assert stm[-1]["data"]["connected"] is False, stm[-1]
    sensor_n = [m["data"]["n"] for m in saglikli.alinan if m.get("type") == "sensor_data"]
    assert sensor_n[-1] == 89, f"EN YENI periyodik ileti dusuruldu (son gorulen {sensor_n[-1]})"
    assert sensor_n == sorted(sensor_n), "yayin sirasi bozuldu"
    # n=0 uçuşta (düşürülemez); sınırda ilk düşen KUYRUKTAKİ EN ESKİ (n=1) olmalı — en yeniyi düşürmek de "kopuşu
    # iletir" ama güncel olmayan anlık görüntüleri saklayıp yenileri atar.
    assert 0 in sensor_n and 1 not in sensor_n, f"en eski periyodik ileti dusmedi: ilk gorulenler {sensor_n[:5]}"
    assert ls._ws_dropped_total > 0, "aparat: hic dusurme olmadi, kapi anlamsiz"


def test_KRITIK_serilestirilemeyen_64_yayin_akisi_OLDURMEZ_ve_cagirana_SIZMAZ(ortam):
    ls, dongu, tikanan, saglikli = ortam
    tikanan.serbest.set()
    sizan = []
    for _ in range(ls._WS_MAX_PENDING_BROADCASTS + 1):
        try:
            ls._ws_broadcast_sync({"type": "session_update", "data": {"x": object()}})
        except Exception as e:  # noqa: BLE001 — kapı: çağırana hata sızmamalı
            sizan.append(type(e).__name__)
    assert ls._ws_pending == 0, f"serilestirilemeyen yayin sayaci SIZDIRDI: {ls._ws_pending}"
    ls._ws_broadcast_sync({"type": "session_update", "data": {"isActive": False, "mode": "Sistem Hazır"}})
    _bosalt(ls, dongu, tikanan)
    assert any(m.get("type") == "session_update" for m in saglikli.alinan), "gecerli yayin teslim edilmedi"
    assert not sizan, f"serilestirme hatasi cagirana sizdi ({len(sizan)}x {set(sizan)}) — ör. acil durdurma yolu"


def test_KARSIT_tek_seferlik_iletiler_sinir_ASILSA_da_hicbiri_dusmez(ortam):
    ls, dongu, tikanan, saglikli = ortam
    ls._ws_broadcast_sync({"type": "notification", "data": {"n": -1}})
    _adim(dongu)
    toplam = ls._WS_MAX_PENDING_BROADCASTS + 10
    for n in range(toplam):
        ls._ws_broadcast_sync({"type": "notification", "data": {"n": n}})
    _bosalt(ls, dongu, tikanan)
    alinan = [m["data"]["n"] for m in saglikli.alinan if m.get("type") == "notification"]
    assert alinan == [-1, *range(toplam)], f"tek seferlik ileti DUSTU ya da sira bozuldu ({len(alinan)} / {toplam + 1})"
    assert ls._ws_dropped_total == 0


def test_KARSIT_yalniz_periyodik_dolulukta_sinir_KORUNUR(ortam):
    ls, dongu, tikanan, saglikli = ortam
    ls._ws_broadcast_sync(_sensor(0))
    _adim(dongu)
    for n in range(1, 200):
        ls._ws_broadcast_sync(_sensor(n))
        assert ls._ws_pending <= ls._WS_MAX_PENDING_BROADCASTS, f"periyodik akista sinir asildi: {ls._ws_pending}"
    _bosalt(ls, dongu, tikanan)
    assert ls._ws_pending == 0
