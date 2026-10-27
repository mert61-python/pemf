# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D2.10 (B-1.14) — STM takılı değilken yeniden bağlanma günlüğü DURUM DEĞİŞİMİNDE bir kez + seyrek ÖZET; her denemede DEĞİL.

Kusur [ÖLÇTÜM DENETIM-01 + önce-kırmızı]: `headless_core` kopuk hatta ~3 sn'de bir `open_and_handshake` dener; her denemede
`[STM32] Port seçimi … INFO` + `[STM32] Bağlantı başarısız … WARNING` (oto-algılamada ayrıca 15 sn'de bir "ST-Link VCP bulunamadı")
basılıyordu. Sahadaki 1.9.50 günlüğünün %75-90'ı bu gürültü: 10 MB'lık dosya 3-10 günde dönüyor, NACK / watchdog / çökme izi kayboluyor.

Ölçüm: GERÇEK `Stm32SerialTransport.open_and_handshake`, `headless_core`'un yeniden bağlanma aralığıyla (>3 sn) sahte saatle (modülün
`time`'ı) çağrılır. Port açılışı GERÇEK pyserial'de düşer: bu makinede OLMAYAN `COM239` (gerçek kart/port AÇILMAZ — varsa test atlanır);
`auto` kipinde numaralandırma en alt katta boş (`list_ports.comports`) ve geri düşüş portu `COM239`. Başarı kolu: testin kendi loopback
TCP sunucusu `STM_READY` basar (`socket://` — ürünün sanal-STM yolu).
"""

from __future__ import annotations

import logging
import socket
import threading
import time
import types
import uuid

import capraz
import pytest

_YOK_PORT = "COM239"
_TAVAN_60SN = 3  # plan: 60 sn'de (20 deneme) toplam kayıt tavanı


@pytest.fixture
def ortam(monkeypatch):
    capraz.paket_yoksa_atla("serial")
    from serial.tools import list_ports

    if any(str(p.device).upper() == _YOK_PORT for p in list_ports.comports()):
        pytest.skip(f"{_YOK_PORT} bu makinede VAR — gerçek port açılmasın diye ölçüm atlandı")
    from utils import stm32_transport as st

    # "adim": her monotonic() çağrısında ilerleme (yalnız el sıkışma kolunda > 0 — bekleme/deneme/zaman aşımı döngüsü ilerlesin).
    saat = {"t": 1000.0, "adim": 0.0}

    def _simdi():
        saat["t"] += saat["adim"]
        return saat["t"]

    def _uyu(sn):
        saat["t"] += float(sn)

    monkeypatch.setattr(st, "time", types.SimpleNamespace(monotonic=_simdi, sleep=_uyu, time=time.time))
    monkeypatch.setattr(st, "FIXED_STM32_PORT", _YOK_PORT)
    monkeypatch.setattr(list_ports, "comports", lambda *a, **k: [])
    monkeypatch.setenv("PEMF_STM_PORT", _YOK_PORT)
    kayitlar: list[logging.LogRecord] = []

    class _Toplayici(logging.Handler):
        def emit(self, record):
            kayitlar.append(record)

    log = logging.getLogger("test.d210." + uuid.uuid4().hex)
    log.propagate = False
    log.setLevel(logging.DEBUG)
    log.addHandler(_Toplayici())
    return types.SimpleNamespace(st=st, saat=saat, log=log, kayitlar=kayitlar)


def _dene(o, tasima, n: int, adim: float = 3.05):
    sonuc = None
    for _ in range(n):
        o.saat["t"] += adim
        sonuc = tasima.open_and_handshake(stop_event=threading.Event())
    return sonuc


def _metinler(o) -> list[str]:
    return [r.getMessage() for r in o.kayitlar]


def test_KRITIK_sabit_port_YOK_60_sn_20_denemede_gunluk_TAVANI_asmaz_D210(ortam):
    t = ortam.st.Stm32SerialTransport(ortam.log)
    assert _dene(ortam, t, 20) is None
    assert len(ortam.kayitlar) <= _TAVAN_60SN, (
        f"STM yokken 60 sn'de {len(ortam.kayitlar)} günlük satırı (tavan {_TAVAN_60SN}) — saha günlüğü bu gürültüyle dönüyor:\n"
        + "\n".join(_metinler(ortam)[:12])
    )


def test_KRITIK_oto_algilama_kipi_60_sn_20_denemede_gunluk_TAVANI_asmaz_D210(ortam, monkeypatch):
    """Launcher varsayılanı `PEMF_STM_PORT=auto` (install.rs) — sahadaki kip budur."""
    monkeypatch.setenv("PEMF_STM_PORT", "auto")
    t = ortam.st.Stm32SerialTransport(ortam.log)
    assert _dene(ortam, t, 20) is None
    assert len(ortam.kayitlar) <= _TAVAN_60SN, f"auto kipinde 60 sn'de {len(ortam.kayitlar)} satır:\n" + "\n".join(
        _metinler(ortam)[:12]
    )


def _acilis_hatasi(o) -> str:
    """Bu ortamda açılışın GERÇEK hata metni (pyserial ya da koşucunun seri port bekçisi) — kapı metni sabitlemez."""
    try:
        import serial

        serial.Serial(_YOK_PORT, 115200, timeout=0.3, write_timeout=1.0, dsrdtr=False, rtscts=False).close()
    except Exception as exc:  # noqa: BLE001 — ölçülen şey hata metninin kendisi
        return str(exc)
    pytest.skip(f"{_YOK_PORT} açılabildi — ölçüm anlamsız")


def test_KARSIT_ilk_basarisizlik_GERCEK_acilis_hatasiyla_GORUNUR_D210(ortam):
    beklenen = _acilis_hatasi(ortam)
    t = ortam.st.Stm32SerialTransport(ortam.log)
    _dene(ortam, t, 1)
    uyari = [m for r, m in zip(ortam.kayitlar, _metinler(ortam)) if r.levelno >= logging.WARNING]
    assert len(uyari) == 1 and "Bağlantı başarısız" in uyari[0] and _YOK_PORT in uyari[0] and beklenen in uyari[0], (
        _metinler(ortam)
    )


def test_KRITIK_uzun_kesinti_SEYREK_OZETLE_gorunur_kalir_deneme_sayisiyla_D210(ortam):
    """Susturma DEĞİL: 30 dk kesintide özet satırları ardışık deneme sayısını ve son hatayı taşır."""
    beklenen = _acilis_hatasi(ortam)
    t = ortam.st.Stm32SerialTransport(ortam.log)
    _dene(ortam, t, 590)  # ≈ 30 dk
    ozet = [m for m in _metinler(ortam) if "hâlâ kurulamıyor" in m]
    assert len(ozet) >= 2, f"uzun kesintide özet yok/az ({len(ozet)}): {_metinler(ortam)}"
    assert "ardışık deneme" in ozet[-1] and beklenen in ozet[-1], ozet[-1]
    assert len(ortam.kayitlar) <= 8, f"30 dk'da {len(ortam.kayitlar)} satır — özet seyrek değil"


def test_KRITIK_basari_sonrasi_YENI_kesinti_yeniden_bir_kez_GORUNUR_D210(ortam, monkeypatch):
    """Durum değişimi: kesinti → bağlantı (sanal STM) → yeni kesinti; her kesinti BİR KEZ yazılır, aradaki başarı da."""
    sunucu = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sunucu.bind(("127.0.0.1", 0))
    sunucu.listen(1)
    port = sunucu.getsockname()[1]
    baglantilar: list[socket.socket] = []

    def _kabul():
        # Sanal STM: bağlantıda ve aldığı HER yoklamada `STM_READY` basar (taşıma açılışta giriş tamponunu boşaltır; ilk satır
        # yarışta silinse de sıfır-duty yoklamasına verilen yanıt el sıkışmayı bitirir).
        try:
            c, _ = sunucu.accept()
            baglantilar.append(c)
            c.settimeout(20.0)
            c.sendall(b"STM_READY D210-SANAL\n")
            while c.recv(1024):
                c.sendall(b"STM_READY D210-SANAL\n")
        except OSError:
            pass

    is_parcacigi = threading.Thread(target=_kabul, daemon=True)
    is_parcacigi.start()
    t = ortam.st.Stm32SerialTransport(ortam.log)
    try:
        _dene(ortam, t, 5)
        monkeypatch.setenv("PEMF_STM_PORT", f"socket://127.0.0.1:{port}")
        ortam.saat["adim"] = (
            0.25  # el sıkışma döngüsü sahte saatte ilerlesin (dinleme → yoklama → en geç 12 sn zaman aşımı)
        )
        sonuc = _dene(ortam, t, 1)
        ortam.saat["adim"] = 0.0
        assert sonuc is not None, f"sanal STM ile el sıkışma olmadı: {_metinler(ortam)}"
        t.close_serial(sonuc.serial)
        monkeypatch.setenv("PEMF_STM_PORT", _YOK_PORT)
        _dene(ortam, t, 5)
    finally:
        for c in baglantilar:
            c.close()
        sunucu.close()
        is_parcacigi.join(timeout=5)
    m = _metinler(ortam)
    basarisiz = [x for x in m if "Bağlantı başarısız" in x]
    assert len(basarisiz) == 2, f"iki kesintinin her biri BİR KEZ yazılmalı (bulunan {len(basarisiz)}):\n" + "\n".join(
        m
    )
    assert any("Handshake OK" in x for x in m), m
