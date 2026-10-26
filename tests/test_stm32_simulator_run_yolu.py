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
        # D0Ö.12 ek-2 (tur 5): `run()` thread'i de `sim_istemci`nin bağlı yöntemi — "≥2" tek işçiyle de
        # geçiyordu. İki işçi ADLARIYLA istenir.
        adlar = {getattr(x._target, "__name__", "") for x in isciler}
        assert {"_watchdog_worker", "_duration_worker"} <= adlar, f"kurulum: bekçi/süre işçileri yok ({sorted(adlar)})"
    finally:
        istemci.close()
    t.join(timeout=3)
    sunucu_tarafi.close()
    bitis = time.monotonic() + 3.0
    while time.monotonic() < bitis and any(x.is_alive() for x in isciler):
        time.sleep(0.05)
    yasayan = [x.name for x in isciler if x.is_alive()]
    assert not yasayan, f"bağlantı bittiği hâlde simülatör işçileri YAŞIYOR (thread sızıntısı): {yasayan}"


class _SahteBaglanti:
    """`recv` parçaları SIRAYLA verir (sonra b'' = karşı taraf kapattı), `sendall` yakalanır — soket YOK, zamanlama YOK."""

    def __init__(self, parcalar: list[bytes]):
        self._parcalar = list(parcalar)
        self.giden: list[bytes] = []

    def recv(self, _n: int) -> bytes:
        return self._parcalar.pop(0) if self._parcalar else b""

    def sendall(self, veri: bytes) -> None:
        self.giden.append(bytes(veri))

    def close(self) -> None:
        pass


def test_KRITIK_bitisik_ve_parcali_URUN_paketlerinin_HER_BIRINE_STM_OK(hw, monkeypatch, caplog):
    """D5.15 / İG-5.39 (D5 ek kol): TCP akışı paket sınırını KORUMAZ — ürünün iki paketi TEK `recv`te (bitişik), üçüncüsü
    üç parçaya bölünmüş ve önünde Y68 kimlik sorgusu gelir. Her GEÇERLİ paket kendi `STM_OK`'unu almalı (3 adet), kimlik
    yanıtı (`STM_ID`) basılmalı ve `run()` hata kaydı olmadan bitmeli. Socketpair kapısı paketleri tek tek yolladığı için
    tamponu bir paketten sonra SIFIRLAYAN mutant (`buf = buf[PKT_SIZE:]` → `buf = b""`) orada YEŞİL kalıyordu (ölçüldü)."""
    import logging

    monkeypatch.setattr(sim, "READY_DELAY_S", 0.0)
    monkeypatch.setattr(sim.Stm32SimClient, "_send_ready", lambda self: None)
    monkeypatch.setattr(sim.Stm32SimClient, "_watchdog_worker", lambda self: None)
    monkeypatch.setattr(sim.Stm32SimClient, "_duration_worker", lambda self: None)

    assert hw._send_stm_manual_update() is True
    p1 = _kuyruktan_paket(hw)
    assert hw.update_coil(1, 100.0, 25.0, 0.0, 5)
    p2 = _kuyruktan_paket(hw)
    assert hw.update_coil(2, 50.0, 10.0, 0.0, 3)
    p3 = _kuyruktan_paket(hw)
    assert len(p1) == len(p2) == len(p3) == sim.PKT_SIZE

    baglanti = _SahteBaglanti([p1 + p2, sim.KIMLIK_SORGUSU + p3[:10], p3[10:70], p3[70:]])
    with caplog.at_level(logging.WARNING, logger=sim.log.name):
        sim.Stm32SimClient(baglanti, ("sahte", 0)).run()  # son recv b'' → normal çıkış (thread YOK)
    satirlar = b"".join(baglanti.giden).decode("utf-8", "replace").splitlines()
    ok = [s for s in satirlar if s.startswith("-> STM_OK:")]
    assert len(ok) == 3, (
        f"3 geçerli paket için 3 STM_OK beklenirdi, {len(ok)} geldi (bitişik/parçalı paket kayboldu): {satirlar}"
    )
    assert ok[1].startswith("-> STM_OK: D=25,0,"), f"bitişik İKİNCİ paket (bobin 1 %25) yanlış çözüldü: {ok[1]!r}"
    assert ok[2].startswith("-> STM_OK: D=25,10,"), f"parçalı ÜÇÜNCÜ paket (bobin 2 %10) yanlış çözüldü: {ok[2]!r}"
    assert any(s.startswith("-> STM_ID:") for s in satirlar), (
        f"paketler arasındaki kimlik sorgusu yanıtlanmadı: {satirlar}"
    )
    hatalar = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert not hatalar, f"run() geçerli akışta uyarı/hata kaydetti: {hatalar}"
