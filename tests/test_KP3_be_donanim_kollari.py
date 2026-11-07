# -*- coding: utf-8 -*-
"""KP-3 C · `controllers/hardware_controller.py` kapsanmayan kolları — her test bir DAVRANIŞ iddiası. ⚠️ Ürün kodu (bobin sürüşü /
STOP / ACİL DURDUR yolu) DEĞİŞMEDİ; yalnız test. Gerçek kart / COM YOK: denetleyici `__new__` ile kurulur (tests/test_son16_gaps.py
deseni), gönderim kuyruğu bellek içi.

- Süre kapağı bobini durdurur; koşu kaydı kancası patlasa da tik sürer (döngü düşmez, bobin DURMUŞ kalır).
- Sürüş kipi: sayıya çevrilemeyen maske DEĞİŞTİRMEZ (mevcut maske döner); çalışan bobin varken yeni kip HEMEN gönderilir ve STOP
  tazeleme sayacı kurulur.
- Başlatma kapısı: `_stm_surus_hazir` engelin tersidir; durum modülü / red sorgusu okunamazsa başlatma ENGELLENMEZ (bilinçli fail-open —
  firmware ölü-adam devresi ve arayüz kilidi ayrı katmanlar).
- Gönderici canlılık denetimi patlarsa gönderici ÖLÜ sayılır (başlatma reddedilir).
- Paket: topolojide olmayan bobin (paket genişliği 7, topoloji 5) SIFIR duty / faz, 100 Hz, 0 süre gider; init'siz denetleyicide paket
  sayacı kurulur; hepsi sıfırsa STOP sırası işaretlenir.
"""

from __future__ import annotations

import logging
import queue
import struct
import sys
import threading
import time
import types

import pytest
from controllers import hardware_controller as hcm
from controllers.hardware_controller import HardwareController


def _hc(bobin_sayisi: int = hcm.STM_BOBIN_SAYISI) -> HardwareController:
    hw = HardwareController.__new__(HardwareController)
    hw._state_lock = threading.RLock()
    hw.logger = logging.getLogger("kp3.hc")
    hw.coils_state = {
        i: {"is_running": False, "freq": 10.0, "duty": 0.0, "phase": 0.0, "duration": 5}
        for i in range(1, bobin_sayisi + 1)
    }
    hw._coil_deadline = {i: None for i in range(1, bobin_sayisi + 1)}
    hw._force_send_left = 0
    hw._unipolar_maskesi = 0x60
    hw.core = None
    return hw


def test_sure_kapagi_kancasi_patlasa_da_bobin_durur_tik_surer(monkeypatch, caplog):
    hw = _hc()
    hw.coils_state[2].update(is_running=True, duty=0.3)
    hw._coil_deadline[2] = time.monotonic() - 1
    gonderilen: list = []
    monkeypatch.setattr(hw, "_send_stm_manual_update", lambda: gonderilen.append(1) or True)

    def _kanca(bobinler):
        raise RuntimeError("koşu kaydı DB'si kilitli")

    monkeypatch.setattr(hcm, "_sure_doldu_kancasi", _kanca)
    with caplog.at_level(logging.ERROR, logger="kp3.hc"):
        hw._tick()
    assert hw.coils_state[2]["is_running"] is False and hw.coils_state[2]["duty"] == 0.0
    assert gonderilen, "süre dolan bobin için STOP paketi gönderilmedi"
    assert any("sure kapagi kancasi hata verdi" in r.getMessage() for r in caplog.records)


def test_surus_kipi_gecersiz_maske_degistirmez_calisan_bobinde_hemen_gonderir(monkeypatch, caplog):
    hw = _hc()
    with caplog.at_level(logging.WARNING, logger="kp3.hc"):
        assert hw.surus_kipi_ayarla("bipolar") == 0x60
    assert hw._unipolar_maskesi == 0x60
    assert any("Gecersiz surus kipi maskesi" in r.getMessage() for r in caplog.records)
    gonderilen: list = []
    monkeypatch.setattr(hw, "_send_stm_manual_update", lambda: gonderilen.append(hw._unipolar_maskesi) or True)
    hw.coils_state[1]["is_running"] = True
    assert hw.surus_kipi_ayarla(0x1FF) == 0xFF
    assert gonderilen == [0xFF] and hw._force_send_left == hw.STOP_RESEND_TICKS


def test_baslatma_kapisi_fail_open_ve_hazirlik_tersi(monkeypatch, caplog):
    hw = _hc()
    monkeypatch.setattr(hw, "_stm_baslatma_engeli", lambda: "")
    assert hw._stm_surus_hazir() is True
    monkeypatch.setattr(hw, "_stm_baslatma_engeli", lambda: "STM bağlı değil")
    assert hw._stm_surus_hazir() is False
    monkeypatch.undo()
    hw = _hc()
    import servers

    monkeypatch.delattr(servers, "live_state", raising=False)
    monkeypatch.setitem(sys.modules, "servers.live_state", None)
    with caplog.at_level(logging.DEBUG, logger="kp3.hc"):
        assert hw._stm_baslatma_engeli() == ""
    assert any("STM surus durumu okunamadi" in r.getMessage() for r in caplog.records)


def test_red_sorgusu_okunamazsa_baslatma_engellenmez(monkeypatch, caplog):
    from servers import live_state

    hw = _hc()
    monkeypatch.setattr(live_state, "stm_surus_hazir", lambda: True)

    def _patla():
        raise RuntimeError("red penceresi kilitli")

    monkeypatch.setattr(live_state, "stm_komutlari_reddediyor", _patla)
    with caplog.at_level(logging.DEBUG, logger="kp3.hc"):
        assert hw._stm_baslatma_engeli() == ""
    assert any("STM red durumu okunamadi" in r.getMessage() for r in caplog.records)


def test_gonderici_canlilik_denetimi_patlarsa_olu_sayilir(caplog):
    def _patla():
        raise RuntimeError("iş parçacığı tablosu okunamadı")

    hw = _hc()
    hw.core = types.SimpleNamespace(hw_gonderici_canli=_patla)
    with caplog.at_level(logging.ERROR, logger="kp3.hc"):
        assert hw._gonderici_baslatmaya_hazir() is False
        assert hw._gonderici_canli() is False
    assert sum("HWSender canlilik denetimi basarisiz" in r.getMessage() for r in caplog.records) == 2


def test_topolojide_olmayan_bobin_sifir_gider_paket_sayaci_kurulur():
    from utils.stm32_transport import STM_PAKET_FMT

    hw = _hc(bobin_sayisi=5)
    hw.coils_state[1].update(is_running=True, duty=0.25, phase=90.0, freq=50.0, duration=30)
    hw.core = types.SimpleNamespace(_hw_send_queue=queue.Queue(maxsize=8))
    assert not hasattr(hw, "_paket_sayaci")
    assert hw._send_stm_manual_update() is True
    pkt = hw.core._hw_send_queue.get_nowait()
    msg = pkt[0]  # _SiraliPaket = (stm_msg, udp_pkt, ip, port) + .sira
    alanlar = struct.unpack(STM_PAKET_FMT, msg[:-4])
    n = hcm.STM_PAKET_BOBIN_SAYISI
    duty, faz, frek, sure = (
        alanlar[2 : 2 + n],
        alanlar[2 + n : 2 + 2 * n],
        alanlar[2 + 2 * n : 2 + 3 * n],
        alanlar[2 + 3 * n : 2 + 4 * n],
    )
    assert duty[0] == pytest.approx(0.25) and frek[0] == pytest.approx(50.0) and sure[0] == 30
    assert list(duty[5:]) == [0.0] * (n - 5) and list(faz[5:]) == [0.0] * (n - 5)
    assert list(frek[5:]) == [100.0] * (n - 5) and list(sure[5:]) == [0] * (n - 5)
    assert hw._paket_sayaci is not None
    hw.coils_state[1].update(is_running=False, duty=0.0)
    assert hw._send_stm_manual_update() is True
    assert hw._son_stop_sirasi == 2, "tümü sıfır paket STOP sırası olarak işaretlenmedi"
