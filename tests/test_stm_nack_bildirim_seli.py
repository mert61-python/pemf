# -*- coding: utf-8 -*-
# Author: mertaygn
"""STM_NACK BİLDİRİM SELİ + EYLEM SÖYLEYEN MESAJ — DAVRANIŞSAL kapı.

===============================================================================
SAHADA ÖLÇÜLEN ARIZA (2026-09-11, sahip ekran görüntüsü)
===============================================================================
Bildirim listesi **89+** özdeş satırla dolmuştu:

    → STM_NACK: CRC      11:38:39
    → STM_NACK: CRC      11:38:39
    → STM_NACK: CRC      11:38:39   …

İki ayrı kusur:

1. **SEL.** Firmware/backend paket biçimi uyuşmazsa HER paket NACK'lenir. Keep-alive
   2 Hz olduğundan operatöre saniyede iki bildirim düşer. Liste tıkanınca GERÇEK olaylar
   (termal kesme, watchdog, doygunluk) görünmez olur — klasik alarm yorgunluğu.

2. **MESAJ EYLEM SÖYLEMİYOR.** "CRC" ham firmware metnidir; operatör ondan ne yapacağını
   çıkaramaz. Oysa CRC reddi pratikte TEK bir şeyi gösterir: karttaki firmware ile bu
   sürümün paket biçimi uyuşmuyor (5 bobinde 88, 7 bobinde 120 bayt) → kartı yeniden
   programla. Bu deponun kayıtlı kuralı: hata mesajı EYLEM söylemeli.

⚠️ İLK OLAY BASTIRILMAZ: susturma "hiç söyleme" değildir. Operatör ilk saniyede haberdar
olur; tekrarları susar.
"""

from __future__ import annotations

import time

import pytest

from servers import api_server as _api


@pytest.fixture(autouse=True)
def _temiz_kisitlayici():
    """Kısıtlayıcı durumunu testler arası SIZDIRMA (bu depoda kayıtlı sızıntı sınıfı)."""
    with _api._stm_nack_lock:
        _api._stm_nack_son.clear()
    yield
    with _api._stm_nack_lock:
        _api._stm_nack_son.clear()


def test_KRITIK_ILK_nack_BASTIRILMAZ():
    """Susturma "hiç söyleme" olmamalı — operatör arızadan haberdar olmalı."""
    assert _api._stm_nack_bastir("-> STM_NACK: CRC") is False, "ILK NACK bastirildi -> operator HIC ogrenmez"


def test_KRITIK_TEKRARLAR_bastirilir():
    """MUTASYON: `_stm_nack_bastir`ı her zaman False döndür → KIRMIZI.

    Sahadaki etki: saniyede iki bildirim, 89+ satır, gerçek olaylar görünmez.
    """
    assert _api._stm_nack_bastir("-> STM_NACK: CRC") is False
    bastirilan = sum(1 for _ in range(50) if _api._stm_nack_bastir("-> STM_NACK: CRC"))
    assert bastirilan == 50, f"50 tekrardan yalniz {bastirilan} bastirildi -> sel devam ediyor"


def test_KRITIK_FARKLI_sebep_SELE_gomulmez():
    """⚠️ Bastırma SEBEP BAZINDA olmalı.

    Tek bir küresel zamanlayıcı kullanılsaydı, CRC seli sürerken gelen FARKLI bir NACK
    (ör. parametre reddi) susturulur ve operatör onu HİÇ görmezdi.

    MUTASYON: özeti sabit bir anahtara çevir (`ozet = "X"`) → KIRMIZI.
    """
    assert _api._stm_nack_bastir("-> STM_NACK: CRC") is False
    assert _api._stm_nack_bastir("-> STM_NACK: CRC") is True, "on kosul: CRC susturulmus olmali"
    assert _api._stm_nack_bastir("-> STM_NACK: freq araligi disi") is False, (
        "FARKLI sebepli NACK, CRC seline gomuldu -> operator gercek parametre hatasini GORMEZ"
    )


def test_KRITIK_sure_dolunca_TEKRAR_bildirilir(monkeypatch):
    """Arıza sürüyorsa operatöre periyodik olarak yine hatırlatılmalı (sessiz kalmamalı)."""
    assert _api._stm_nack_bastir("-> STM_NACK: CRC") is False
    assert _api._stm_nack_bastir("-> STM_NACK: CRC") is True

    sahte = time.monotonic() + _api._STM_NACK_BILDIRIM_ARALIGI_S + 1.0
    monkeypatch.setattr(_api.time, "monotonic", lambda: sahte)
    assert _api._stm_nack_bastir("-> STM_NACK: CRC") is False, (
        "aralik dolduktan sonra da susuluyor -> suren ariza SESSIZ kalir"
    )


def test_KRITIK_CRC_mesaji_EYLEM_soyler(monkeypatch):
    """⚠️ Ham "CRC" metni operatöre ne yapacağını söylemez.

    MUTASYON: CRC dalını kaldırıp ham mesajı bas → KIRMIZI.
    """
    basilan: list[tuple[str, str]] = []
    monkeypatch.setattr(_api, "_push_notification", lambda m, s="info": basilan.append((m, s)))

    class _Olay:
        event_type = "hardware.stm.nack"
        data = {"message": "-> STM_NACK: CRC"}

    _api._handle_backend_event(_Olay())

    assert basilan, "CRC olayinda hic bildirim basilmadi"
    mesaj, seviye = basilan[0]
    assert seviye == "error"
    assert "firmware" in mesaj.lower(), f"mesaj firmware uyusmazligini SOYLEMIYOR: {mesaj}"
    assert "7-ch" in mesaj, "dogrulama olcutu (banner '7-ch') mesajda YOK"
    assert mesaj.strip() != "-> STM_NACK: CRC", "ham firmware metni oldugu gibi basildi"


def test_KRITIK_CRC_DISI_nack_metni_KORUNUR(monkeypatch):
    """Karşıt kanıt: her NACK'i CRC mesajına çevirmek teşhisi yok ederdi."""
    basilan: list[tuple[str, str]] = []
    monkeypatch.setattr(_api, "_push_notification", lambda m, s="info": basilan.append((m, s)))

    class _Olay:
        event_type = "hardware.stm.nack"
        data = {"message": "-> STM_NACK: coil=3 freq=99999 out of range"}

    _api._handle_backend_event(_Olay())
    assert basilan, "CRC disi NACK icin bildirim basilmadi"
    assert "freq=99999" in basilan[0][0], f"ozgun NACK sebebi KAYBOLDU: {basilan[0][0]}"
