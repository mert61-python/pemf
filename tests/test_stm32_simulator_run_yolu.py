# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D0Ö.12 (B-10.176) KAPISI — simülatörün `run()` yolu ürünün GERÇEK paketine `STM_OK` döner.

ARIZA (DENETIM-10 B-10.176): `decode_packet` 2026-09-11'den beri 6'lı döndürüyor (kip maskesi
eklendi) ama `Stm32SimClient.run()` sonucu 5'e açıyordu → ilk GEÇERLİ pakette `ValueError`,
`except Exception` yakalıyor ve bağlantı KAPANIYOR. Yani sanal-STM, ürünün gönderdiği ilk
gerçek pakette ölüyordu; `decode_packet`i doğrudan çağıran kapı (`test_stm32_simulator_cozumleme`)
bunu göremedi — `run()`ı kimse koşmuyordu. Dalga-0 sanal-STM ölçümlerinin (İG-5.3, İG-6.1)
önkoşulu.

KAPI: `socket.socketpair` üzerinde `Stm32SimClient.run()` thread'de koşar; ürünün GERÇEK
`HardwareController._send_stm_manual_update` / `update_coil` yolunun ürettiği 121 baytlık paketler
(sıfır-duty yoklama + sürüş) verilir. İddia: her birine 3 sn içinde `-> STM_OK:` gelir ve
bağlantı AÇIK kalır (ikinci paket de cevaplanır).
MUTASYON: `run()` paket dalına `raise RuntimeError` (M2) ya da 6'lı açımı 5'liye geri almak → KIRMIZI.
"""

from __future__ import annotations

import queue
import socket
import threading
import time

import pytest

sim = pytest.importorskip("tools.stm32_simulator", reason="simulator yok")


class _SahteCore:
    """HardwareController'ın paketi bıraktığı kuyruk — donanım YOK."""

    def __init__(self):
        self._hw_send_queue = queue.Queue(maxsize=100)


@pytest.fixture
def hw():
    from controllers.hardware_controller import HardwareController
    from servers import live_state as _ls

    with _ls._live_state_lock:
        _eski = _ls._live_state["stm"]
        _ls._live_state["stm"] = "online"  # sürüş kapısının "STM bağlı" ön koşulu (paket ÜRETİMİ için)
    c = HardwareController(_SahteCore())
    c._keep_alive_stop.set()
    c._keep_alive_thread.join(timeout=2)
    try:
        yield c
    finally:
        c.stop()
        with _ls._live_state_lock:
            _ls._live_state["stm"] = _eski


def _kuyruktan_paket(hw) -> bytes:
    paket = None
    while not hw.core._hw_send_queue.empty():
        paket = hw.core._hw_send_queue.get_nowait()[0]  # (stm_msg, udp, ip, port) — en SON paket
    assert paket is not None, "ürün paket üretmedi"
    return bytes(paket)


def _satir_bekle(sok: socket.socket, onek: str, sure: float) -> str:
    """`onek` ile başlayan ilk satırı döndür; süre dolarsa ya da bağlantı kapanırsa ''."""
    tampon = b""
    bitis = time.monotonic() + sure
    while time.monotonic() < bitis:
        sok.settimeout(max(0.05, bitis - time.monotonic()))
        try:
            parca = sok.recv(4096)
        except socket.timeout:
            break
        if not parca:
            return ""  # karşı taraf kapattı
        tampon += parca
        for satir in tampon.decode("utf-8", "replace").splitlines():
            if satir.startswith(onek):
                return satir
    return ""


def test_KRITIK_simulator_run_URUN_paketine_STM_OK_doner_ve_ACIK_kalir(hw, monkeypatch):
    monkeypatch.setattr(sim, "READY_DELAY_S", 0.0)  # banner beklemesi ölçümü geciktirmesin
    # Bekçi/süre işçileri `while True` döngüsüdür ve durdurulamaz: test bitince oturum boyunca
    # yaşarlardı (D0Ö.10 sınıfı daemon sızıntısı). Bu kapı PAKET yolunu ölçer → işçiler boş.
    monkeypatch.setattr(sim.Stm32SimClient, "_watchdog_worker", lambda self: None)
    monkeypatch.setattr(sim.Stm32SimClient, "_duration_worker", lambda self: None)
    istemci, sunucu_tarafi = socket.socketpair()
    try:
        sim_istemci = sim.Stm32SimClient(sunucu_tarafi, ("socketpair", 0))
        t = threading.Thread(target=sim_istemci.run, name="d0o12-sim", daemon=True)
        t.start()

        # (1) sıfır-duty YOKLAMA — ürünün boşta gönderdiği paket
        assert hw._send_stm_manual_update() is True
        yoklama = _kuyruktan_paket(hw)
        assert len(yoklama) == sim.PKT_SIZE == 121, f"paket boyu {len(yoklama)}"
        istemci.sendall(yoklama)
        ok1 = _satir_bekle(istemci, "-> STM_OK:", 3.0)
        assert ok1, "simülatör ürünün sıfır-duty paketine 3 sn içinde STM_OK DÖNMEDİ (run() yolu ölü)"

        # (2) SÜRÜŞ paketi — bağlantı hâlâ açık mı, ikinci paket de cevaplanıyor mu
        assert hw.update_coil(1, 100.0, 25.0, 0.0, 5)
        surus = _kuyruktan_paket(hw)
        istemci.sendall(surus)
        ok2 = _satir_bekle(istemci, "-> STM_OK:", 3.0)
        assert ok2, "ikinci pakete STM_OK gelmedi — simülatör ilk paketten sonra bağlantıyı kapattı"
        assert t.is_alive(), "simülatör istemci thread'i öldü (bağlantı kapandı)"
    finally:
        istemci.close()
        sunucu_tarafi.close()
