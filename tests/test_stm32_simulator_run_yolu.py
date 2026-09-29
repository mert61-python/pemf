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
(STOP/boşta biçimli paket + sürüş) ve ürünün GERÇEK el sıkışma yoklaması
(`stm32_transport.build_stm32_zero_duty_packet`) verilir. İddia: her birine 3 sn içinde `-> STM_OK:`
gelir ve bağlantı AÇIK kalır. D0Ö.12 ek: bekçi/süre işçileri GERÇEKTEN koşar (sürüşten sonra
suskunlukta `STM_ERR: Watchdog`) ve bağlantı bitince SONLANIR (eskiden `while True` — her bağlantı iki
kalıcı thread sızdırıyordu).
MUTASYON: `run()` paket dalına `raise RuntimeError` (M2) ya da 6'lı açımı 5'liye geri almak → KIRMIZI;
işçi döngüsünü `while True`ya döndürmek ya da `finally`'deki durdurmayı silmek → KIRMIZI.
"""

from __future__ import annotations

import queue
import socket
import threading
import time

import pytest

# ⚠️ importorskip DEĞİL: simülatör depoda izli; yüklenemezse bu kapı SESSİZCE atlanmamalı (Ö.7).
import tools.stm32_simulator as sim


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
    from utils.stm32_transport import build_stm32_zero_duty_packet

    monkeypatch.setattr(sim, "READY_DELAY_S", 0.0)  # banner beklemesi ölçümü geciktirmesin
    # Bu kapı PAKET yolunu ölçer → işçiler boş (işçi davranışı aşağıdaki ayrı kapıda).
    monkeypatch.setattr(sim.Stm32SimClient, "_watchdog_worker", lambda self: None)
    monkeypatch.setattr(sim.Stm32SimClient, "_duration_worker", lambda self: None)
    istemci, sunucu_tarafi = socket.socketpair()
    try:
        sim_istemci = sim.Stm32SimClient(sunucu_tarafi, ("socketpair", 0))
        t = threading.Thread(target=sim_istemci.run, name="d0o12-sim", daemon=True)
        t.start()

        # (1) HC'nin STOP/boşta biçimli paketi (tüm duty 0) — keep-alive/STOP/E-stop aynı baytı üretir
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

        # (3) ürünün GERÇEK el sıkışma yoklaması (headless_core → stm32_transport; ping_packet verilmez)
        istemci.sendall(bytes(build_stm32_zero_duty_packet()))
        ok3 = _satir_bekle(istemci, "-> STM_OK:", 3.0)
        assert ok3, "ürünün el sıkışma yoklamasına STM_OK gelmedi"
        assert t.is_alive(), "simülatör istemci thread'i öldü (bağlantı kapandı)"
    finally:
        istemci.close()
        sunucu_tarafi.close()


def _istemcinin_iscileri(sim_istemci) -> list[threading.Thread]:
    """`sim_istemci`nin bağlı yöntemlerini koşturan CANLI thread'ler (bekçi, süre, hazır)."""
    return [x for x in threading.enumerate() if getattr(getattr(x, "_target", None), "__self__", None) is sim_istemci]


def test_KRITIK_bekci_suskunlukta_ERR_basar_ve_isciler_baglantiyla_BITER(hw, monkeypatch):
    """D0Ö.12 ek: işçiler GERÇEKTEN koşar (firmware ölü-adam davranışı) ve bağlantıyla birlikte biter."""
    monkeypatch.setattr(sim, "READY_DELAY_S", 0.0)
    istemci, sunucu_tarafi = socket.socketpair()
    sim_istemci = sim.Stm32SimClient(sunucu_tarafi, ("socketpair", 0))
    t = threading.Thread(target=sim_istemci.run, name="d0o12-sim-bekci", daemon=True)
    t.start()
    try:
        assert hw.update_coil(1, 100.0, 25.0, 0.0, 5)
        istemci.sendall(_kuyruktan_paket(hw))
        assert _satir_bekle(istemci, "-> STM_OK:", 3.0), "sürüş paketine STM_OK gelmedi"
        # Sürüşten sonra SUSKUNLUK (keep-alive fixture'da durduruldu): firmware 1,5 sn'de bobinleri 0'lar.
        err = _satir_bekle(istemci, "-> STM_ERR: Watchdog", sim.WATCHDOG_MS / 1000 + 2.0)
        assert err, "bekçi suskunlukta bobinleri 0'lamadı / STM_ERR basmadı (ölü-adam davranışı yok)"
        isciler = _istemcinin_iscileri(sim_istemci)
        assert len(isciler) >= 2, f"kurulum: bekçi/süre işçileri bulunamadı ({[x.name for x in isciler]})"
    finally:
        istemci.close()
    t.join(timeout=3)
    sunucu_tarafi.close()
    bitis = time.monotonic() + 3.0
    while time.monotonic() < bitis and any(x.is_alive() for x in isciler):
        time.sleep(0.05)
    yasayan = [x.name for x in isciler if x.is_alive()]
    assert not yasayan, f"bağlantı bittiği hâlde simülatör işçileri YAŞIYOR (thread sızıntısı): {yasayan}"
