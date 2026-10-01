# Author: mertaygn, cglrgrkn
"""D1.01 · B-1.34 — `update_coil` ÇAĞRI YERİNDEKİ protokol sınırı TAŞIYICIDIR (Ö.4-Y9).

`controllers/README.md` "Python-tarafı satürasyon yok" diyordu; çağrı yerindeki
`normalize_frequency_hz` / `normalize_phase_deg` ham `float()` ile değiştirilince mevcut süit
YEŞİL kalıyordu (kör kapı). Oysa bu sınır bir TEDAVİ clamp'i DEĞİL, protokol-geçerlilik
sınırıdır: firmware aralık dışı freq/fazı NACK'ler (`main.c` `Coil_DecodeAndValidatePacket`:
`RANGE coil=… field=phase` / `field=freq`) → paket reddedilir, bobin SESSİZCE sürülmez.

Kapı GERÇEK `HardwareController.update_coil` / `start_all_coils`'u çağırır ve kuyruğa giden
paketi firmware doğrulamasının aynası olan simülatör `decode_packet` ile çözer: istenen bobinde
freq=25000.0 / faz=360.0 ve paket firmware'ce KABUL edilir.

⚠️ Bu bir tedavi güvenlik-sınırı kapısı DEĞİLDİR (Ö.4-Y9: o sınır geri eklenmez; duty tavanı
yoktur — D1.06). 0 Hz bilerek ölçülmez (A-05: 0 Hz = STOP, D1.53'te değişecek).
"""

from __future__ import annotations

import queue
import struct
import sys
import zlib
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from controllers.hardware_controller import STM_BOBIN_SAYISI, HardwareController  # noqa: E402
from utils.stm32_protocol_limits import FREQ_MAX_HZ, FREQ_MIN_HZ, PHASE_MAX_DEG, PHASE_MIN_DEG  # noqa: E402

# `importorskip` DEĞİL — simülatör izli; yüklenemezse kapı sessizce ATLANMAZ (D0Ö.12 ek-2 dersi).
import tools.stm32_simulator as sim  # noqa: E402


class _SahteCore:
    def __init__(self):
        self._hw_send_queue = queue.Queue(maxsize=100)


@pytest.fixture
def hc():
    # STM "online" ön koşulu: başlatma kapısı (`_stm_surus_hazir`) kopuk STM'de START'ı reddeder.
    from servers import live_state as _ls

    with _ls._live_state_lock:
        _eski = _ls._live_state["stm"]
        _ls._live_state["stm"] = "online"
    c = HardwareController(_SahteCore())
    # keep-alive thread'i durur → kuyruktaki paketler yalnız test edilen çağrıdan gelir.
    c._keep_alive_stop.set()
    c._keep_alive_thread.join(timeout=2)
    try:
        yield c
    finally:
        c.stop()
        with _ls._live_state_lock:
            _ls._live_state["stm"] = _eski


def _son_paket(c: HardwareController) -> bytes:
    son = None
    while True:
        try:
            son = c.core._hw_send_queue.get_nowait()
        except queue.Empty:
            break
    assert son is not None, "çağrı donanım kuyruğuna HİÇ paket vermedi"
    return son[0]


def _firmware_cozer(paket: bytes):
    """Firmware doğrulamasının aynası: (alanlar, None) ya da (None, NACK sebebi)."""
    return sim.decode_packet(paket)


def test_ARAC_firmware_aynasi_ARALIK_DISINI_reddeder(hc):
    """Ölçüm aracının KÖR olmadığının kanıtı (Ö.6): geçerli bir ürün paketinde yalnız bobin 1'in
    frekansı 99999'a çevrilip CRC yeniden hesaplanınca çözücü NACK sebebi döndürmeli."""
    assert hc.update_coil(1, 100.0, 30.0, 0.0, duration=1) is True
    ham = _son_paket(hc)
    alanlar = list(struct.unpack(sim.PKT_FMT, ham))
    n = sim.NUM_COILS
    alanlar[2 + 2 * n] = 99999.0  # bobin 1 freq
    govde = struct.pack(sim.PKT_FMT, *alanlar)[:-4]
    bozuk = govde + struct.pack("<I", zlib.crc32(govde) & 0xFFFFFFFF)
    sonuc, sebep = _firmware_cozer(bozuk)
    assert sonuc is None and sebep and "freq" in sebep, f"firmware aynası aralık dışını görmedi: {sebep!r}"


@pytest.mark.parametrize("bobin", [1, STM_BOBIN_SAYISI])
@pytest.mark.parametrize(
    ("istek_freq", "istek_faz", "beklenen_freq", "beklenen_faz"),
    [
        (99999.0, 720.0, FREQ_MAX_HZ, PHASE_MAX_DEG),  # üst sınır
        (50.0, -90.0, 50.0, PHASE_MIN_DEG),  # negatif faz
    ],
)
def test_KRITIK_update_coil_PROTOKOL_SINIRINA_ceker_ve_firmware_KABUL_eder(
    hc, bobin, istek_freq, istek_faz, beklenen_freq, beklenen_faz
):
    assert hc.update_coil(bobin, istek_freq, 30.0, istek_faz, duration=1) is True
    sonuc, sebep = _firmware_cozer(_son_paket(hc))
    assert sonuc is not None, (
        f"firmware paketi NACK'ler: {sebep!r} — çağrı yerindeki protokol sınırı (normalize_*) "
        "kaldırılmış; bobin SESSİZCE sürülmez (Ö.4-Y9 taşıyıcı sınır)"
    )
    duty, faz, freq, _sure, _ref, _kip = sonuc
    assert freq[bobin - 1] == pytest.approx(beklenen_freq)
    assert faz[bobin - 1] == pytest.approx(beklenen_faz)
    assert duty[bobin - 1] == pytest.approx(0.30)


def test_KRITIK_start_all_coils_AYNI_sinira_ceker(hc):
    assert hc.start_all_coils(freq=99999.0, duty=30.0, phase=720.0, duration=1) is True
    sonuc, sebep = _firmware_cozer(_son_paket(hc))
    assert sonuc is not None, f"start_all_coils paketi firmware'ce NACK'lenir: {sebep!r}"
    _duty, faz, freq, *_ = sonuc
    for i in range(STM_BOBIN_SAYISI):
        assert freq[i] == pytest.approx(FREQ_MAX_HZ), f"bobin {i + 1} freq={freq[i]}"
        assert faz[i] == pytest.approx(PHASE_MAX_DEG), f"bobin {i + 1} faz={faz[i]}"


@pytest.mark.parametrize("bobin", [1, STM_BOBIN_SAYISI])
def test_KRITIK_update_coil_ALT_UCLAR_da_TASIYICI_frekans_ve_duty(hc, bobin):
    """Bağımsız inceleme (r1): kapı yalnız ÜST uçları ölçüyordu — `_freq = min(float(freq), 25000.0)`
    (1 Hz tabanı kalkar) yeşil kalıyordu. Firmware alt uçları da NACK'ler (`freq < FREQ_MIN`,
    `duty < DUTY_MIN`). 0 < f < 1 Hz → `FREQ_MIN_HZ`; negatif duty → 0. 0 Hz bilerek ölçülmez
    (A-05 → D1.53: o uç orada değişecek; bu kol 0,5 Hz ile o maddeyi kilitlemez)."""
    assert hc.update_coil(bobin, 0.5, 30.0, 0.0, duration=1) is True
    sonuc, sebep = _firmware_cozer(_son_paket(hc))
    assert sonuc is not None, f"0,5 Hz paketi firmware'ce NACK'lenir: {sebep!r} — frekans ALT sınırı kaldırılmış"
    _duty, _faz, freq, *_ = sonuc
    assert freq[bobin - 1] == pytest.approx(FREQ_MIN_HZ)

    assert hc.update_coil(bobin, 100.0, -10.0, 0.0, duration=1) is True
    sonuc, sebep = _firmware_cozer(_son_paket(hc))
    assert sonuc is not None, f"negatif duty paketi firmware'ce NACK'lenir: {sebep!r} — duty ALT sınırı kaldırılmış"
    assert sonuc[0][bobin - 1] == 0.0


def test_KRITIK_start_all_coils_ALT_frekans_ucunu_da_ceker(hc):
    assert hc.start_all_coils(freq=0.5, duty=30.0, phase=0.0, duration=1) is True
    sonuc, sebep = _firmware_cozer(_son_paket(hc))
    assert sonuc is not None, f"start_all_coils 0,5 Hz paketi firmware'ce NACK'lenir: {sebep!r}"
    _duty, _faz, freq, *_ = sonuc
    for i in range(STM_BOBIN_SAYISI):
        assert freq[i] == pytest.approx(FREQ_MIN_HZ), f"bobin {i + 1} freq={freq[i]}"


def test_KARSIT_aralik_ICINDEKI_deger_DEGISMEDEN_gider(hc):
    """Sınır yalnız aralık DIŞINI çeker; aralık içi değer pakete aynen gider (her şeyi sabite
    çeken bir mutant bu düzeltme sanılmasın). Değerler float32'de tam temsil edilir."""
    assert hc.update_coil(2, 1234.5, 30.0, 45.0, duration=1) is True
    sonuc, sebep = _firmware_cozer(_son_paket(hc))
    assert sonuc is not None, sebep
    _duty, faz, freq, *_ = sonuc
    assert freq[1] == 1234.5
    assert faz[1] == 45.0
