# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""TEST YARDIMCISI — GERÇEK `HardwareController` + kayıtçı donanım kuyruğu. ⚠️ pytest TOPLAMAZ.

(`test_` ön eki yok; `topoloji.py` / `stm_baglanti.py` ile aynı desen.)

NEDEN VAR (Dalga 1, D1.04–D1.06): E-stop / seans / clamp kapıları `FakeHW` ya da
`state.hardware = None` ile yalnız HTTP 200'e bakıyordu; STOP'un ya da duty'nin DONANIMA ne
olarak gittiğini görmüyorlardı (kör kapı). Bu yardımcı ürünün GERÇEK paket kurucusunu koşar ve
`core._hw_send_queue`'ya verilen her paketi KAYDEDER; paket, firmware doğrulamasının aynası olan
simülatör çözücüsüyle (`tools/stm32_simulator.decode_packet`) okunur — firmware'in NACK'leyeceği
paket "geçerli" sayılmaz.

⚠️ KAPSAM SINIRI: kayıt, HC → donanım KUYRUĞU sınırındadır. HeadlessCore'un HWSender
iş parçacığı ve seri yazımı (kuyruk → port) bu aparatta YOKTUR — o adımın arızası (B-1.23:
gönderici ölüyken STOP "kuyruğa verildi" sayılır) burada GÖRÜNMEZ; ayrı maddede (D1.55) ölçülür.
"""

from __future__ import annotations

import contextlib
import queue
import sys
from pathlib import Path

_KOK = Path(__file__).resolve().parents[1]
if str(_KOK) not in sys.path:
    sys.path.insert(0, str(_KOK))


class KayitciKuyruk:
    """`_hw_send_queue` yerine: her paketi kabul eder ve STM baytlarını sırayla saklar."""

    def __init__(self):
        self.paketler: list[bytes] = []

    def put_nowait(self, pkt):
        self.paketler.append(pkt[0])

    def get_nowait(self):
        raise queue.Empty


class _KayitciCore:
    def __init__(self):
        self._hw_send_queue = KayitciKuyruk()


@contextlib.contextmanager
def gercek_hc(stm_cevrimici: bool = True):
    """Blok boyunca GERÇEK bir `HardwareController` verir (keep-alive durdurulmuş: paketler yalnız
    test edilen çağrılardan gelir). `hc.stop_all_cagri` `stop_all_coils` çağrılarını sayar.
    `stm_cevrimici`: başlatma kapısının ön koşulu (STOP için gerekmez); çıkışta eski değer döner."""
    from controllers.hardware_controller import HardwareController
    from servers import live_state as _ls

    with _ls._live_state_lock:
        eski = _ls._live_state["stm"]
        if stm_cevrimici:
            _ls._live_state["stm"] = "online"
    hc = HardwareController(_KayitciCore())
    hc._keep_alive_stop.set()
    hc._keep_alive_thread.join(timeout=2)
    hc.stop_all_cagri = 0
    _orj = hc.stop_all_coils

    def _sayan_stop_all():
        hc.stop_all_cagri += 1
        return _orj()

    hc.stop_all_coils = _sayan_stop_all
    try:
        yield hc
    finally:
        hc.stop()
        with _ls._live_state_lock:
            _ls._live_state["stm"] = eski


def paket_coz(paket: bytes):
    """Firmware aynasıyla çöz → (duty, faz, freq, süre, ref_ms, kip). NACK'lenecek paket → AssertionError."""
    import tools.stm32_simulator as sim

    sonuc, sebep = sim.decode_packet(paket)
    assert sonuc is not None, f"paket firmware'ce NACK'lenir: {sebep!r}"
    return sonuc
