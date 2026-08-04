"""Denetim 2026-08-04 (P3): STM32 protokol sabitleri ÜÇ ayrı kaynakta ELLE kopyalanmış durumda —
firmware/main.c (otorite), utils/stm32_protocol_limits.py (backend) ve tools/stm32_simulator.py
(E2E test cihazı) — ve hiçbir derleme-zamanı ya da test-zamanı kontrolü bunları karşılaştırmıyordu.

Sürüklenme GERÇEKTEN OLDU: simülatörün FREQ_MAX'ı 10 kHz'de kalmıştı, firmware ve backend ise
25 kHz. Sonuç: E2E güvenlik testleri 10–25 kHz aralığını hiç görmeyen, SEVKEDİLENDEN FARKLI bir
cihazı doğruluyordu. Bu test o sınıf sürüklenmeyi bir daha sessiz bırakmaz.

Donanımsız, saf metin/aritmetik testler — firmware kaynağı `#define`'lardan okunur.
"""

import re
from pathlib import Path

import pytest

from utils import stm32_protocol_limits as lim

_FW = Path(__file__).resolve().parent.parent / "firmware" / "main.c"


@pytest.fixture(scope="module")
def fw_src() -> str:
    if not _FW.exists():  # firmware ağacı yoksa (kod-only checkout) atla
        pytest.skip(f"firmware kaynağı yok: {_FW}")
    return _FW.read_text(encoding="utf-8", errors="replace")


def _define_float(src: str, name: str) -> float:
    """`#define <name> <sayı>[f]` değerini oku (satır-devamı `\\` toleranslı)."""
    m = re.search(rf"^#define\s+{re.escape(name)}\s*\\?\s*\n?\s*([0-9]*\.?[0-9]+)f?\b", src, re.M)
    assert m, f"firmware/main.c içinde #define {name} bulunamadı"
    return float(m.group(1))


def _define_int(src: str, name: str) -> int:
    m = re.search(rf"^#define\s+{re.escape(name)}\s*\\?\s*\n?\s*([0-9]+)U?\b", src, re.M)
    assert m, f"firmware/main.c içinde #define {name} bulunamadı"
    return int(m.group(1))


# ── firmware ↔ backend (utils/stm32_protocol_limits.py) ──────────────────────


def test_freq_max_firmware_ile_backend_ayni(fw_src):
    """FREQ_MAX firmware'de TÜRETİLİR: DDS_ISR_HZ / DDS_MIN_TICKS_PER_PERIOD."""
    isr = _define_float(fw_src, "DDS_ISR_HZ")
    min_ticks = _define_float(fw_src, "DDS_MIN_TICKS_PER_PERIOD")
    assert isr == lim.DDS_ISR_HZ
    assert min_ticks == lim.DDS_MIN_TICKS_PER_PERIOD
    assert isr / min_ticks == lim.FREQ_MAX_HZ == 25000.0


def test_freq_min_firmware_ile_backend_ayni(fw_src):
    assert _define_float(fw_src, "FREQ_MIN") == lim.FREQ_MIN_HZ == 1.0


def test_phase_max_firmware_ile_backend_ayni(fw_src):
    assert _define_float(fw_src, "PHASE_DEG_MAX") == lim.PHASE_MAX_DEG == 360.0


def test_duration_max_firmware_ile_backend_ayni(fw_src):
    assert _define_int(fw_src, "DURATION_MAX_MINUTES") == lim.DURATION_MAX_MINUTES == 9999


# ── firmware ↔ simülatör (tools/stm32_simulator.py) ──────────────────────────


@pytest.fixture(scope="module")
def sim():
    import importlib.util

    p = Path(__file__).resolve().parent.parent / "tools" / "stm32_simulator.py"
    if not p.exists():
        pytest.skip("stm32_simulator.py yok")
    spec = importlib.util.spec_from_file_location("_stm32_sim", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_simulator_sevkedilen_cihazla_ayni_limitleri_uyguluyor(sim, fw_src):
    """Simülatör GERÇEK cihazın sınırlarını uygulamazsa E2E testleri yanlış cihazı doğrular."""
    assert sim.FREQ_MAX == lim.FREQ_MAX_HZ == 25000.0, (
        "simülatör FREQ_MAX'ı firmware/backend ile AYRIŞMIŞ — E2E güvenlik testleri "
        "sevkedilenden farklı bir cihazı doğrular"
    )
    assert sim.FREQ_MIN == lim.FREQ_MIN_HZ
    assert sim.PHASE_MAX == lim.PHASE_MAX_DEG
    assert sim.DUR_MAX == lim.DURATION_MAX_MINUTES
    assert sim.NUM_COILS == _define_int(fw_src, "NUM_COILS")
    assert sim.REF_MS_MAX == _define_int(fw_src, "REF_MS_MAX")


def test_paket_boyutu_88_uc_kaynakta_da_ayni(sim, fw_src):
    """88 bayt: firmware `#pragma pack(1)` struct'ı ↔ Python struct formatı."""
    assert sim.PKT_SIZE == 88
    # firmware yorumu da 88 demeli (struct alanları: 2 + 5*4*3 + 5*4 + 2 + 4)
    assert 2 + (5 * 4) * 3 + (5 * 4) + 2 + 4 == 88
    assert "BINARY_PKT_SIZE sizeof(BinaryCmdPacket_t)" in fw_src


def test_olu_adam_watchdog_esigi_uc_kaynakta_da_1500ms(sim, fw_src):
    """Firmware'in ölü-adam eşiği; backend keep-alive'ı buna göre marj bırakır."""
    from controllers.hardware_controller import HardwareController

    assert sim.WATCHDOG_MS == 1500
    assert HardwareController._FIRMWARE_DEADMAN_MS == 1500
    assert re.search(r"last_communication_ms\s*>\s*1500", fw_src), (
        "firmware ölü-adam eşiği 1500 ms değil — backend keep-alive marjı geçersiz"
    )


def test_keep_alive_deadman_esiginden_yeterince_hizli():
    """Keep-alive periyodu ölü-adam eşiğinin en az 2 katı hızlı olmalı (tek paket kaybı
    tedaviyi kesmesin). 0.5 s vs 1500 ms → 3x marj."""
    from controllers.hardware_controller import HardwareController

    ka_ms = HardwareController.KEEP_ALIVE_INTERVAL_S * 1000
    assert ka_ms * 2 <= HardwareController._FIRMWARE_DEADMAN_MS, (
        f"keep-alive ({ka_ms} ms) ölü-adam eşiğine ({HardwareController._FIRMWARE_DEADMAN_MS} ms) "
        "çok yakın — ağ/GC gecikmesinde tedavi ortasında beklenmedik durma riski"
    )
