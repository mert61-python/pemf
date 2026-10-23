# Author: mertaygn, cglrgrkn
# SGI-3.3 (A3 · K3 · TD3) — KÖR KAPI: E-stop teyidi yalnız TÜM-SIFIR `STM_OK`'tan "kabul" olur.
# TD3 kapısı (tests/test_TD3_estop_kartin_STOP_NACKi_teyit_DEGILDIR.py, 6 test) "herhangi bir STM_OK = kabul" mutantında YEŞİL kaldı
# (ölçüldü: _inceleme/kayit/K3a_herhangi_OK_kabul_mutasyon.txt — 6 passed). Gerçek akış: E-stop'un STOP'u porta yazıldığı anda
# kartın RX'inde bir önceki RUN paketi işleniyor olabilir (121 B @115200 ≈ 10,5 ms); o RUN'ın duty>0 ACK'i STOP yazımından SONRA gelir.
# STOP'un kendisi NACK'lenirse teyit "red" olmalı — RUN'ın ACK'i bobinlerin DURDUĞUNUN kanıtı değildir.
# GERÇEK `HeadlessCore._handle_stm_line` (gerçek `_parse_stm_ok` sınıflaması) + GERÇEK yazım izi + GERÇEK `hw_stop_yaniti_bekle`.
from __future__ import annotations

import logging
import threading

import pytest

RUN_ACK = (
    "-> STM_OK: D=50,0,0,0,0,0,0 P=0,0,0,0,0,0,0 F=100,100,100,100,100,100,100 T=0,0,0,0,0,0,0 K=96 E=50,0,0,0,0,0,0"
)
STOP_ACK = (
    "-> STM_OK: D=0,0,0,0,0,0,0 P=0,0,0,0,0,0,0 F=100,100,100,100,100,100,100 T=0,0,0,0,0,0,0 K=96 E=0,0,0,0,0,0,0"
)
CRC_NACK = "-> STM_NACK: CRC"


@pytest.fixture
def cekirdek():
    import headless_core as hcm

    c = hcm.HeadlessCore.__new__(hcm.HeadlessCore)
    c.logger = logging.getLogger("sgi-3-3")
    c._stm_state_lock = threading.RLock()
    c.stm_kimlik = None
    c.stm_uyumlu = None
    c.stm_uyumsuzluk_sebebi = ""
    c.stm_is_connected = True
    c.olaylar = []
    c._set_stm_connected = lambda v: setattr(c, "stm_is_connected", v)
    c._publish_event = lambda tur, veri=None, **k: c.olaylar.append((tur, veri))
    c._hw_izlemeyi_kur()
    return c


def _stop_yazildi(c, sira: int) -> None:
    from utils.stm32_transport import build_stm32_zero_duty_packet

    c._hw_yazimi_kaydet(build_stm32_zero_duty_packet(), sira=sira)


def test_KRITIK_STOP_yaziminda_ucustaki_RUN_ACKi_kabul_SAYILMAZ_STOP_NACKi_RED(cekirdek):
    _stop_yazildi(cekirdek, 7)
    cekirdek._handle_stm_line(RUN_ACK, retry_last_payload=lambda: None)  # STOP'tan ÖNCE yazılmış RUN'ın ACK'i
    cekirdek._handle_stm_line(CRC_NACK, retry_last_payload=lambda: None)  # STOP reddedildi
    assert cekirdek.hw_stop_yaniti_bekle(7, 0.05) == "red"


def test_KRITIK_yalniz_RUN_ACKi_gelirse_kabul_DEGIL(cekirdek):
    # T2D-1: STOP'un kendisine yanıt yok (yalnız uçuştaki RUN'ın ACK'i) → "yanitsiz" (teyit YOK); eskiden None = "porta yazıldı" teyidi.
    _stop_yazildi(cekirdek, 3)
    cekirdek._handle_stm_line(RUN_ACK, retry_last_payload=lambda: None)
    assert cekirdek.hw_stop_yaniti_bekle(3, 0.05) == "yanitsiz"


def test_KRITIK_T2D1_STOPa_hic_yanit_yoksa_YANITSIZ(cekirdek):
    _stop_yazildi(cekirdek, 5)
    assert cekirdek.hw_stop_yaniti_bekle(5, 0.05) == "yanitsiz"


def test_KARSIT_T2D1_STOP_yazim_izi_YOKSA_None(cekirdek):
    """İz yok (bu sırada STOP hiç yazılmadı) → None: karar `stmStopped`a (porta yazım beklemesi) kalır."""
    _stop_yazildi(cekirdek, 2)
    assert cekirdek.hw_stop_yaniti_bekle(9, 0.05) is None


def test_KARSIT_tum_sifir_ACK_kabul(cekirdek):
    _stop_yazildi(cekirdek, 4)
    cekirdek._handle_stm_line(RUN_ACK, retry_last_payload=lambda: None)
    cekirdek._handle_stm_line(STOP_ACK, retry_last_payload=lambda: None)
    assert cekirdek.hw_stop_yaniti_bekle(4, 0.05) == "kabul"
