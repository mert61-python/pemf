# -*- coding: utf-8 -*-
# Author: mertaygn
"""SİMÜLATÖR GERÇEK PAKETİ ÇÖZÜYOR MU — DAVRANIŞSAL kapı.

===============================================================================
⚠️ PARİTE KAPISININ GÖREMEDİĞİ SINIF (2026-09-11'de bulundu)
===============================================================================
`tests/test_stm32_source_parity.py` simülatörün SABİTLERİNİ firmware'le eşliyor
(`NUM_COILS`, `PKT_SIZE`, `FREQ_MAX`…). O kapı 2026-09-10 geçişinde YEŞİL kaldı çünkü
sabitler doğru güncellenmişti — ama `decode_packet` içindeki alan dilimleri
`fields[2:7]`, `fields[7:12]`, … diye **5 bobine SABİT** bırakılmıştı:

    ref_ms = fields[22]      # 7 bobinde bu aslında freq[6]

Sonuç: simülatör her GEÇERLİ paketi yanlış çözüp reddediyordu. Yani E2E testleri ve
`headless_core`daki "sanal-STM ile smoke-test edildi" notu **sevk edilenden farklı bir
cihazı** doğruluyordu.

DERS: sabiti eşlemek davranışı eşlemez. Bu dosya, backend'in GERÇEKTEN ürettiği paketi
simülatöre verir ve çözülen değerlerin geri geldiğini ölçer.
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from utils.stm32_transport import STM_PAKET_BOBIN_SAYISI, STM_PAKET_BOYU, STM_PAKET_FMT  # noqa: E402

sim = pytest.importorskip("tools.stm32_simulator", reason="simulator yok")


def _backend_paketi(duty, phase, freq, dur, ref_ms=123) -> bytes:
    """`hardware_controller._send_stm_manual_update` ile AYNI kurulum (tek kaynak biçim)."""
    govde = struct.pack(STM_PAKET_FMT, 0xAA, 0x55, *duty, *phase, *freq, *dur, ref_ms)
    return govde + struct.pack("<I", zlib.crc32(govde) & 0xFFFFFFFF)


def test_KRITIK_simulator_BACKENDIN_paketini_KABUL_eder():
    """Geçerli bir paket reddediliyorsa simülatör hiçbir şeyi doğrulamıyor demektir."""
    n = STM_PAKET_BOBIN_SAYISI
    pkt = _backend_paketi([0.25] * n, [0.0] * n, [50.0] * n, [10] * n)
    assert len(pkt) == STM_PAKET_BOYU == sim.PKT_SIZE, "paket genisligi UCU birden AYNI olmali"

    cozum, sebep = sim.decode_packet(pkt)
    assert cozum is not None, f"simulator GECERLI paketi reddetti: {sebep}"


def test_KRITIK_cozulen_ALANLAR_dogru_yerden_okunur():
    """⚠️ ASIL KAPI: her alana AYIRT EDİCİ bir değer konur ve geri okunur.

    Hepsi aynı değerde olsaydı yanlış dilim de "doğru" görünürdü — bu testin
    5-bobinlik dilimlerle YEŞİL kalmasının sebebi tam olarak buydu.

    MUTASYON: dilimleri `fields[2:7]`/`fields[7:12]`/… diye sabitle → KIRMIZI.
    """
    n = STM_PAKET_BOBIN_SAYISI
    duty = [0.10 + 0.01 * i for i in range(n)]
    phase = [10.0 * i for i in range(n)]
    freq = [100.0 + i for i in range(n)]
    dur = [5 + i for i in range(n)]
    ref = 777

    cozum, sebep = sim.decode_packet(_backend_paketi(duty, phase, freq, dur, ref))
    assert cozum is not None, f"gecerli paket reddedildi: {sebep}"
    c_duty, c_phase, c_freq, c_dur, c_ref = cozum

    assert len(c_duty) == n and len(c_phase) == n and len(c_freq) == n and len(c_dur) == n, (
        f"alan uzunluklari {len(c_duty)}/{len(c_phase)}/{len(c_freq)}/{len(c_dur)} != {n} "
        "-> dilimler NUM_COILS'ten turemiyor"
    )
    assert c_duty == pytest.approx(duty), "duty YANLIS dilimden okundu"
    assert c_phase == pytest.approx(phase), "phase YANLIS dilimden okundu"
    assert c_freq == pytest.approx(freq), "freq YANLIS dilimden okundu"
    assert list(c_dur) == dur, "duration YANLIS dilimden okundu"
    assert c_ref == ref, f"ref_ms={c_ref} != {ref} -> ref_ms YANLIS ofsetten okundu (muhtemelen freq[n-1])"


def test_KRITIK_BOZUK_crc_hala_REDDEDILIR():
    """Karşıt kanıt: kapıyı "her şeyi kabul et" diye geçmek mümkün olmasın."""
    n = STM_PAKET_BOBIN_SAYISI
    pkt = bytearray(_backend_paketi([0.25] * n, [0.0] * n, [50.0] * n, [10] * n))
    pkt[-1] ^= 0xFF  # crc'yi boz
    cozum, sebep = sim.decode_packet(bytes(pkt))
    assert cozum is None and "CRC" in (sebep or ""), f"bozuk CRC KABUL EDILDI (sebep={sebep})"


def test_KRITIK_ESKI_88_baytlik_paket_REDDEDILIR():
    """Eski firmware/backend paketi artık geçmemeli — atomik sevk şartının kapısı."""
    eski_fmt = "<BB 5f 5f 5f 5I H"
    govde = struct.pack(eski_fmt, 0xAA, 0x55, *([0.25] * 5), *([0.0] * 5), *([50.0] * 5), *([10] * 5), 1)
    eski = govde + struct.pack("<I", zlib.crc32(govde) & 0xFFFFFFFF)
    assert len(eski) == 88
    cozum, sebep = sim.decode_packet(eski)
    assert cozum is None, "88 baytlik ESKI paket kabul edildi -> simulator eski protokolu konusuyor"
    assert "boyut" in (sebep or "").lower()


def test_KRITIK_banner_KANAL_SAYISI_ile_tutarli():
    """⚠️ Banner'daki "5-ch" elle yazılmıştı ve geçişte bayatladı.

    `scripts/stm_firmware_kimligi.py` banner'daki kanal sayısına bakıp "eski firmware"
    kararı veriyor → bayat banner o aracı YANILTIR.

    MUTASYON: banner'ı tekrar sabit "5-ch" yap → KIRMIZI.
    """
    kaynak = (KOK / "tools" / "stm32_simulator.py").read_text(encoding="utf-8", errors="replace")
    assert "{NUM_COILS}-ch" in kaynak, "banner kanal sayisi NUM_COILS'ten TURETILMIYOR (elle yazilmis)"
    assert '"-> STM_READY: DDS v2.3 (5-ch' not in kaynak, "banner hala SABIT 5-ch"
