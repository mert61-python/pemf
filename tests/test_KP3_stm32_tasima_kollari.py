# -*- coding: utf-8 -*-
"""KP-3 C · `utils/stm32_transport.py` kapsanmayan kolları — her test bir DAVRANIŞ iddiası. ⚠️ GERÇEK COM AÇILMAZ: seri nesnesi,
port listesi (`list_ports.comports`) ve `serial_for_url` EN ALT katta sahtelenir.

- Aday yoksa açılış denenmez; el sıkışma beklenmedik istisnayla düşerse açılan port KAPATILIR ve port soğumaya alınır.
- Port kapatma hatası yutulur (kapanış yolu fırlatmaz).
- Port seçimi: ayar yoksa sabit COM10; soğumadaki port seçilmez; `auto`da bulunan ST-Link seçilir.
- ST-Link oto-algılama: yalnız ST-Link PID'i / açıklaması eşleşir (aynı VID'li kart üstü STM elenir); pyserial araçları yoksa / port
  listesi okunamazsa aday yok.
- Port açılışında DTR/RTS ayarlanamasa da port döner (bağlantı düşmez).
- El sıkışma: okuma hatası → boş; satır geri çağırımı patlasa da STM_READY yakalanır; sessiz kartta yoklama yazılamazsa → boş.
- Doğrulama yoklaması: kimlik sorgusu yazılamazsa özet hemen döner; durdurma isteği döngüyü keser; yoklama yazma / okuma hatası döngüyü
  keser; boş satır atlanır, geri çağırım hatası kimliğin okunmasını engellemez.
"""

from __future__ import annotations

import logging
import sys
import threading
import time

import pytest
from utils import stm32_transport as st


def _tasima(zaman: float = 0.5) -> st.Stm32SerialTransport:
    return st.Stm32SerialTransport(logging.getLogger("kp3.stm32"), handshake_timeout_sec=zaman)


ADAY = st.Stm32PortCandidate(device="socket://kp3-sahte-kart", description="test")


class _Seri:
    def __init__(self, satirlar=(), *, okuma_hatasi=None, yazma_hatasi=None, yazma_hatasi_sonra=0, kapanis_hatasi=None):
        self.satirlar = list(satirlar)
        self.okuma_hatasi = okuma_hatasi
        self.yazma_hatasi = yazma_hatasi
        self.yazma_hatasi_sonra = yazma_hatasi_sonra
        self.kapanis_hatasi = kapanis_hatasi
        self.yazilan: list = []
        self.is_open = True
        self.kapandi = False

    def readline(self):
        if self.okuma_hatasi:
            raise self.okuma_hatasi
        return self.satirlar.pop(0) if self.satirlar else b""

    def write(self, b):
        if self.yazma_hatasi and len(self.yazilan) >= self.yazma_hatasi_sonra:
            raise self.yazma_hatasi
        self.yazilan.append(bytes(b))

    def close(self):
        if self.kapanis_hatasi:
            raise self.kapanis_hatasi
        self.kapandi = True
        self.is_open = False


def test_aday_yoksa_acilis_denenmez_beklenmedik_hatada_port_kapatilir(monkeypatch):
    t = _tasima()
    monkeypatch.setattr(t, "_select_candidate", lambda: None)
    monkeypatch.setattr(t, "_open_serial", lambda c: pytest.fail("aday yokken port açıldı"))
    assert t.open_and_handshake(threading.Event()) is None
    seri = _Seri()
    monkeypatch.setattr(st, "VCP_SETTLE_TIME_SEC", 0.0)
    monkeypatch.setattr(t, "_select_candidate", lambda: ADAY)
    monkeypatch.setattr(t, "_open_serial", lambda c: seri)

    def _patla(*a, **k):
        raise RuntimeError("beklenmedik çerçeve")

    monkeypatch.setattr(t, "_wait_for_handshake", _patla)
    assert t.open_and_handshake(threading.Event()) is None
    assert seri.kapandi is True, "hata sonrası port açık bırakıldı"
    assert t._bad_ports_until.get(ADAY.device.upper(), 0) > time.monotonic(), "port soğumaya alınmadı"


def test_port_kapatma_hatasi_yutulur():
    _tasima().close_serial(_Seri(kapanis_hatasi=OSError("aygıt çıkarıldı")))


def test_port_secimi_varsayilan_com10_sogumadaki_secilmez_auto_st_link(monkeypatch):
    t = _tasima()
    monkeypatch.setenv("PEMF_STM_PORT", "x")
    monkeypatch.delenv("PEMF_STM_PORT")
    secilen = t._select_candidate()
    assert secilen is not None and secilen.device == st.FIXED_STM32_PORT
    t._bad_ports_until[st.FIXED_STM32_PORT.upper()] = time.monotonic() + 60
    assert t._select_candidate() is None, "soğumadaki port yeniden seçildi"
    bulunan = st.Stm32PortCandidate(device="COM7", description="oto ST-Link")
    monkeypatch.setenv("PEMF_STM_PORT", "auto")
    monkeypatch.setattr(t, "_autodetect_stlink", lambda: bulunan)
    assert t._select_candidate().device == "COM7"


class _Port:
    def __init__(self, device, vid, pid, description):
        self.device, self.vid, self.pid, self.description = device, vid, pid, description


def test_st_link_oto_algilama_kart_ustu_stm_elenir(monkeypatch):
    from serial.tools import list_ports

    kart_ustu = _Port("COM3", st.ST_LINK_USB_VID, 0x5740, "USB Seri Aygıt")
    st_link = _Port("COM10", st.ST_LINK_USB_VID, 0x374B, "STMicroelectronics STLink Virtual COM Port")
    monkeypatch.setattr(list_ports, "comports", lambda: [kart_ustu, st_link])
    aday = _tasima()._autodetect_stlink()
    assert aday is not None and aday.device == "COM10" and "STLink" in aday.description
    yalniz_aciklama = _Port("COM11", None, None, "ST-Link Virtual COM")
    monkeypatch.setattr(list_ports, "comports", lambda: [kart_ustu, yalniz_aciklama])
    assert _tasima()._autodetect_stlink().device == "COM11"

    def _okunamaz():
        raise OSError("SetupAPI reddetti")

    monkeypatch.setattr(list_ports, "comports", _okunamaz)
    assert _tasima()._autodetect_stlink() is None


def test_pyserial_araclari_yoksa_aday_yok(monkeypatch):
    import serial.tools as araclar

    monkeypatch.delattr(araclar, "list_ports", raising=False)
    monkeypatch.setitem(sys.modules, "serial.tools.list_ports", None)
    assert _tasima()._autodetect_stlink() is None


def test_dtr_rts_ayarlanamasa_da_port_doner(monkeypatch):
    import serial

    class _UrlSeri:
        @property
        def dtr(self):
            return True

        @dtr.setter
        def dtr(self, v):
            raise OSError("köprü DTR desteklemiyor")

    acilan = _UrlSeri()
    monkeypatch.setattr(serial, "serial_for_url", lambda *a, **k: acilan)
    assert _tasima()._open_serial(ADAY) is acilan


def test_el_sikisma_okuma_hatasi_geri_cagirim_hatasi_ve_yoklama_yazilamaz(monkeypatch, caplog):
    t = _tasima(zaman=2.0)
    with caplog.at_level(logging.WARNING, logger="kp3.stm32"):
        assert t._wait_for_handshake(_Seri(okuma_hatasi=OSError("port koptu")), ADAY, None, None) == ""

        def _bozuk(satir):
            raise ValueError("arayüz kuyruğu dolu")

        seri = _Seri([b"STM_READY v2.5 ch=7\r\n"])
        assert t._wait_for_handshake(seri, ADAY, None, _bozuk) == "STM_READY v2.5 ch=7"
        monkeypatch.setattr(st, "HANDSHAKE_PASSIVE_LISTEN_SEC", 0.0)
        assert t._wait_for_handshake(_Seri(yazma_hatasi=OSError("yazma zaman aşımı")), ADAY, None, None) == ""
    mesajlar = [r.getMessage() for r in caplog.records]
    assert any("Handshake okuma hatası" in m for m in mesajlar)
    assert any("Handshake callback hatası" in m for m in mesajlar)
    assert any("Handshake probe yazma hatası" in m for m in mesajlar)


def test_dogrulama_kimlik_yazilamaz_ve_durdurma_istegi(caplog):
    t = _tasima()
    with caplog.at_level(logging.WARNING, logger="kp3.stm32"):
        ozet = t._dogrulama_yoklamasi(
            _Seri(yazma_hatasi=OSError("yazılamadı")), ADAY, None, None, "STM_READY", sure_sn=5.0
        )
    assert ozet == {"kabul": False, "kimlik": None, "crc_nack": 0, "yoklama": 0}
    assert any("Kimlik sorgusu yazılamadı" in r.getMessage() for r in caplog.records)
    dur = threading.Event()
    dur.set()
    seri = _Seri()
    bas = time.monotonic()
    ozet = t._dogrulama_yoklamasi(seri, ADAY, dur, None, "STM_READY", sure_sn=5.0)
    assert time.monotonic() - bas < 2.0 and ozet["yoklama"] == 0, "durdurma isteği yoklamayı kesmedi"
    assert seri.yazilan == [st.STM_KIMLIK_SORGUSU]


def test_dogrulama_yoklama_yazma_ve_okuma_hatasi_dongu_keser(caplog):
    t = _tasima()
    with caplog.at_level(logging.WARNING, logger="kp3.stm32"):
        bas = time.monotonic()
        ozet = t._dogrulama_yoklamasi(
            _Seri(yazma_hatasi=OSError("tampon dolu"), yazma_hatasi_sonra=1), ADAY, None, None, "STM_READY", sure_sn=5.0
        )
        assert ozet["yoklama"] == 0 and time.monotonic() - bas < 2.0
        ozet = t._dogrulama_yoklamasi(
            _Seri(okuma_hatasi=OSError("port koptu")), ADAY, None, None, "STM_READY", sure_sn=5.0
        )
        assert ozet["yoklama"] == 1 and time.monotonic() - bas < 4.0
    mesajlar = [r.getMessage() for r in caplog.records]
    assert any("Doğrulama yoklaması yazılamadı" in m for m in mesajlar)
    assert any("Doğrulama okuma hatası" in m for m in mesajlar)


def test_dogrulama_bos_satir_atlanir_geri_cagirim_hatasi_kimligi_engellemez(caplog):
    t = _tasima()
    gorulen: list = []

    def _bozuk(satir):
        gorulen.append(satir)
        raise ValueError("kuyruk dolu")

    seri = _Seri([b"   \r\n", b"STM_ID: v2.5 ch=7 uid=ABC\r\n"])
    with caplog.at_level(logging.WARNING, logger="kp3.stm32"):
        ozet = t._dogrulama_yoklamasi(seri, ADAY, None, _bozuk, "STM_OK: 0", sure_sn=3.0)
    assert ozet["kabul"] is True and ozet["kimlik"] == "STM_ID: v2.5 ch=7 uid=ABC"
    assert gorulen == ["STM_ID: v2.5 ch=7 uid=ABC"], "boş satır geri çağırıma verildi"
    assert any("Doğrulama callback hatası" in r.getMessage() for r in caplog.records)
