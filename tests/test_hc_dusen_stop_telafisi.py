# Author: mertaygn, cglrgrkn
"""D1.02 · B-1.38 — `update_coil(start=False)`'daki DÜŞEN-STOP telafisi davranışla kapılı.

Seans STOP'u bobin başına `update_coil(..., start=False)` yolundan gider. STOP paketi donanım
kuyruğuna o an VERİLEMEZSE (kuyruk/UART geçici dolu) `_force_send_left = STOP_RESEND_TICKS`
sayesinde keep-alive sonraki turlarda STOP'u yeniden gönderir — HİÇBİR bobin çalışmıyorken bile
(`need_send = any_running or _force_send_left > 0`). Bu satır 0 yapılınca mevcut süit YEŞİL
kalıyordu (kör kapı; plan: 73 test).

Kapı GERÇEK `HardwareController`'ı kullanır: ilk STOP yazımı kuyrukta düşer (`update_coil` False
döner), sonra `_tick` deterministik sürülür ve her turda kuyruğa giden paket firmware
doğrulamasının aynası olan simülatör çözücüsüyle okunur.

⚠️ Y8: bu bir E-stop/STOP gönderimini ARTIRAN mekanizmadır; kapı yalnız AZALMASINI yakalar.
"""

from __future__ import annotations

import queue
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from controllers.hardware_controller import HardwareController  # noqa: E402

# `importorskip` DEĞİL — simülatör izli; yüklenemezse kapı sessizce ATLANMAZ.
import tools.stm32_simulator as sim  # noqa: E402


class _DusurenKuyruk:
    """`_hw_send_queue` yerine: `dusur` kadar `put_nowait`'i `queue.Full` ile reddeder (UART/kuyruk
    geçici dolu), sonra kabul eder. `get_nowait` hep boş → üretim kodunun "en eskiyi at" dalı da
    yer açamaz; yani `_send_stm_manual_update`'in 3 denemesi de düşer."""

    def __init__(self):
        self.dusur = 0
        self.kabul: list[bytes] = []

    def put_nowait(self, pkt):
        if self.dusur > 0:
            self.dusur -= 1
            raise queue.Full
        self.kabul.append(pkt[0])

    def get_nowait(self):
        raise queue.Empty


class _SahteCore:
    def __init__(self):
        self._hw_send_queue = _DusurenKuyruk()


@pytest.fixture
def hc():
    from servers import live_state as _ls

    with _ls._live_state_lock:
        _eski = _ls._live_state["stm"]
        _ls._live_state["stm"] = "online"
    c = HardwareController(_SahteCore())
    c._keep_alive_stop.set()  # _tick'i test sürer (arka plan yarışı yok)
    c._keep_alive_thread.join(timeout=2)
    try:
        yield c
    finally:
        c.stop()
        with _ls._live_state_lock:
            _ls._live_state["stm"] = _eski


def _bobin_duty(paket: bytes, bobin: int) -> float:
    sonuc, sebep = sim.decode_packet(paket)
    assert sonuc is not None, f"paket firmware'ce NACK'lenir: {sebep!r}"
    return sonuc[0][bobin - 1]


def test_KRITIK_dusen_STOP_sonraki_turlarda_YENIDEN_gonderilir(hc):
    k = hc.core._hw_send_queue
    assert hc.update_coil(1, 100.0, 30.0, 0.0, duration=1) is True
    assert _bobin_duty(k.kabul[-1], 1) == pytest.approx(0.30)  # senaryo: bobin 1 gerçekten sürülüyordu

    k.dusur = 3  # STOP'un 3 kuyruk denemesi de düşer
    assert hc.update_coil(1, 100.0, 0.0, 0.0, duration=0, start=False) is False, (
        "STOP kuyruğa verilemediği hâlde True döndü — çağıran 'durdu' sanar"
    )
    assert not any(s["is_running"] for s in hc.coils_state.values()), "senaryo: başka çalışan bobin YOK"
    k.kabul.clear()

    for _ in range(hc.STOP_RESEND_TICKS):
        hc._tick()

    assert len(k.kabul) == hc.STOP_RESEND_TICKS, (
        f"düşen STOP telafisi: {hc.STOP_RESEND_TICKS} turda {len(k.kabul)} paket gitti "
        "(hiç bobin çalışmıyorken STOP yalnız _force_send_left ile yeniden gönderilir)"
    )
    assert all(_bobin_duty(p, 1) == 0.0 for p in k.kabul), "yeniden gönderilen paket STOP (duty 0) değil"


def test_KARSIT_telafi_SONLUDUR_ve_bosta_trafik_uretmez(hc):
    """Telafi penceresi bitince boştaki keep-alive paket göndermez (sonsuz UART trafiği yok).
    Bu, telafinin süresini değil yalnız BİTTİĞİNİ ölçer; süreyi uzatmak güvenli yöndür."""
    k = hc.core._hw_send_queue
    assert hc.update_coil(1, 100.0, 30.0, 0.0, duration=1) is True
    hc.update_coil(1, 100.0, 0.0, 0.0, duration=0, start=False)
    for _ in range(hc.STOP_RESEND_TICKS):
        hc._tick()
    k.kabul.clear()
    hc._tick()
    assert k.kabul == [], "telafi penceresi bittiği hâlde boştaki tur paket gönderdi"
