# -*- coding: utf-8 -*-
# Author: mertaygn
"""STM KOPUKKEN BAŞLATMA REDDEDİLİR — DAVRANIŞSAL kapı.

===============================================================================
SAHADA ÖLÇÜLEN ARIZA (2026-09-11)
===============================================================================
Sahip "bobinler başlamıyor" dedi. Çalışan backend'e soruldu: STM **kopuk**
(`stmConnected: false`, hiç COM portu yok). Ama kontrol ucu şunu döndürüyordu:

    POST /api/coil/1/control  →  {"status":"success","transport":"stm32"}

Donanım bağlı değilken, hiçbir şey çalışmayacakken **"başarılı"**. Sebep:
`stm_is_connected` backend'in HİÇBİR yerinde kontrol edilmiyordu — ne bobin
kontrolünde, ne seans başlatmada. Tek kapı istemci tarafındaydı
(`CoilParameterPanel: isDisabled = ... || (stm32Driven && !stmConnected)`).

Tek katmanlı kapı yetmez: arayüz dışından gelen her çağrı (mobil uygulama,
AI yönlendirici, doğrudan API) donanım yokken "başarılı" cevabı alır ve
operatör tedavinin uygulandığını sanır. Bu, bu deponun tekrarlayan
"SESSİZ BAŞARISIZLIK" sınıfıdır.

===============================================================================
KAPININ ÖLÇTÜĞÜ ÜÇ DEĞİŞMEZ
===============================================================================
1. **BAŞLATMA reddedilir** — ve bobin durumu DEĞİŞMEZ, kuyruğa paket GİTMEZ.
   (Sadece `False` dönmek yetmez: state kirlenirse keep-alive onu sürmeye çalışır.)
2. **DURDURMA ASLA kapılanmaz** — karşıt kanıt. STOP/E-stop her koşulda geçmeli;
   kayıtlı sahip kararı: "seans/E-stop ASLA kapılanmaz". Kopuk bağlantıda STOP'u
   reddetmek, yeniden bağlanınca bobinlerin ESKİ duty ile canlanmasına yol açar.
3. **İKİ GİRİŞ NOKTASI DA** kapanır: `update_coil` VE `start_all_coils`.
   ⚠️ `start_all_coils`, `update_coil`'i ÇAĞIRMAZ — paralel bir uygulamadır ve bu
   dosyanın kaynağındaki yorum önceki bir düzeltmenin "BURAYA TAŞINMAMIŞTI"
   olduğunu söylüyor. Yalnız birini kapatmak "kısmi düzeltme = düzeltilmemiş"tir.

⚠️ DEMO YOLU KIRILMAMALI: aynı EXE sunucuda `PEMF_SIMULATE=1` ile demo koşuyor ve
simülasyon `core.stm_is_connected`'i AYARLAMAZ — `_live_state["stm"]`i "online"
yapar. Bu yüzden kapı arayüzün okuduğu AYNI kaynağa bağlıdır. Yan fayda: backend
artık ekranda görünenle aynı şeyi söyler.
"""

from __future__ import annotations

import queue

import pytest

from controllers.hardware_controller import HardwareController
from servers import live_state


class _FakeCore:
    def __init__(self):
        self._hw_send_queue = queue.Queue(maxsize=100)


@pytest.fixture
def hw():
    c = HardwareController(_FakeCore())
    # keep-alive thread'i DURDURULUR → kuyruk sayımı deterministik olur.
    c._keep_alive_stop.set()
    c._keep_alive_thread.join(timeout=2)
    yield c
    c.stop()


@pytest.fixture
def stm_durumu():
    """`_live_state["stm"]`i testin sonunda ESKİ değerine döndürür (sızıntı yok)."""
    with live_state._live_state_lock:
        eski = live_state._live_state["stm"]

    def ayarla(deger: str) -> None:
        with live_state._live_state_lock:
            live_state._live_state["stm"] = deger

    yield ayarla
    ayarla(eski)


def _kuyrugu_bosalt(hw) -> int:
    n = 0
    while True:
        try:
            hw.core._hw_send_queue.get_nowait()
            n += 1
        except queue.Empty:
            return n


# ============================================================================
# 1. BAŞLATMA REDDİ
# ============================================================================


def test_KRITIK_STM_kopukken_update_coil_BASLATMAYI_REDDEDER(hw, stm_durumu):
    """MUTASYON: `update_coil`deki STM kapısını sil → KIRMIZI.

    Sahadaki etki: operatör "başarılı" görür, hiçbir bobin çalışmaz.
    """
    stm_durumu("warning")  # kopuk
    _kuyrugu_bosalt(hw)

    sonuc = hw.update_coil(1, 50.0, 25.0, 0.0, 10, start=True)

    assert sonuc is False, "STM KOPUK ama baslatma 'basarili' dondu -> sessiz basarisizlik"
    assert hw.coils_state[1]["is_running"] is False, (
        "reddedilen komut bobin durumunu KIRLETTI -> keep-alive onu surmeye calisir"
    )
    assert _kuyrugu_bosalt(hw) == 0, "reddedilen komut icin paket KUYRUGA KONDU"


def test_KRITIK_STM_kopukken_start_all_coils_de_REDDEDER(hw, stm_durumu):
    """⚠️ `start_all_coils` `update_coil`i ÇAĞIRMAZ — ayrı kapı gerekir.

    MUTASYON: `start_all_coils`daki STM kapısını sil → KIRMIZI.
    Bu iddia olmadan "yalnız update_coil kapatıldı" hâli yeşil görünürdü ve
    seans/AI yolları hâlâ sessizce başarılı dönerdi.
    """
    stm_durumu("warning")
    _kuyrugu_bosalt(hw)

    sonuc = hw.start_all_coils(50.0, 25.0, 0.0, 10)

    assert sonuc is False, "STM KOPUK ama start_all_coils 'basarili' dondu"
    for i in range(1, 8):
        assert hw.coils_state[i]["is_running"] is False, f"bobin {i} durumu KIRLENDI"
    assert _kuyrugu_bosalt(hw) == 0, "reddedilen toplu komut icin paket KUYRUGA KONDU"


# ============================================================================
# 2. KARŞIT KANIT — DURDURMA ASLA KAPILANMAZ
# ============================================================================


def test_KRITIK_STM_kopukken_DURDURMA_YINE_GECER(hw, stm_durumu):
    """⚠️ Kapıyı `if not hazir: return False` diye BAŞA koymak bunu kırar.

    Kayıtlı sahip kararı: seans/E-stop ASLA kapılanmaz. Ayrıca kopuk bağlantıda
    STOP'u reddetmek, yeniden bağlanınca bobinlerin ESKİ duty ile canlanmasına
    yol açar (keep-alive eski state'i sürer).

    MUTASYON: kapıyı `start` kontrolü OLMADAN koy → KIRMIZI.
    """
    stm_durumu("online")
    hw.update_coil(1, 50.0, 25.0, 0.0, 10, start=True)
    assert hw.coils_state[1]["is_running"] is True, "on kosul kurulamadi"

    stm_durumu("warning")  # kablo cikti
    _kuyrugu_bosalt(hw)

    hw.update_coil(1, 0, 0, 0, 0, start=False)

    assert hw.coils_state[1]["is_running"] is False, "STM kopukken DURDURMA kapilandi -> bobin 'calisiyor' kaldi"
    assert hw.coils_state[1]["duty"] == 0.0, "durdurmada duty sifirlanmadi"


def test_KRITIK_STM_kopukken_stop_all_coils_YINE_GECER(hw, stm_durumu):
    stm_durumu("online")
    hw.start_all_coils(50.0, 25.0, 0.0, 10)
    stm_durumu("warning")
    hw.stop_all_coils()
    for i in range(1, 8):
        assert hw.coils_state[i]["is_running"] is False, f"bobin {i} STOP kapilandi"


# ============================================================================
# 3. BAĞLIYKEN / DEMO'DA ÇALIŞMAYA DEVAM
# ============================================================================


def test_KRITIK_STM_BAGLIYKEN_baslatma_GECER(hw, stm_durumu):
    """Kapı yalnız KOPUKKEN durdurmalı; aksi halde cihaz hiç çalışmaz."""
    stm_durumu("online")
    _kuyrugu_bosalt(hw)
    assert hw.update_coil(1, 50.0, 25.0, 0.0, 10, start=True), "STM BAGLI ama baslatma reddedildi"
    assert hw.coils_state[1]["is_running"] is True
    assert _kuyrugu_bosalt(hw) >= 1, "kabul edilen komut icin paket KUYRUGA KONMADI"


def test_KRITIK_SIMULASYON_demo_yolu_KIRILMAZ(hw, stm_durumu):
    """⚠️ Aynı EXE sunucuda `PEMF_SIMULATE=1` demo olarak koşuyor.

    Simülasyon `core.stm_is_connected`i AYARLAMAZ; `_live_state["stm"]`i "online"
    yapar. Kapı `core.stm_is_connected`e bağlanırsa demo'da HİÇBİR bobin
    başlatılamaz — sunucu dağıtımı sessizce ölür.

    MUTASYON: kapıyı `self.core.stm_is_connected`e bağla → KIRMIZI
    (fake core'da o alan YOK, tıpkı simülasyonda olmadığı gibi).
    """
    assert not hasattr(hw.core, "stm_is_connected"), "on kosul: fake core simulasyon gibi bu alani TASIMAZ"
    stm_durumu("online")
    assert hw.update_coil(3, 40.0, 30.0, 0.0, 5, start=True), (
        "simulasyon/demo yolunda baslatma reddedildi -> sunucu dagitimi coker"
    )


def test_KRITIK_durum_OKUNAMAZSA_tedavi_ENGELLENMEZ(hw, stm_durumu, monkeypatch):
    """Beklenmeyen bir hata tüm tedaviyi durdurmamalı (fail-open, bilinçli).

    Firmware'in 1500 ms ölü-adam devresi ve arayüz kapısı yerinde kalır. Kapının
    amacı SAHTE BAŞARIYI kesmek; kendi arızasıyla cihazı kilitlemek değil.
    """

    def patla():
        raise RuntimeError("canli durum okunamadi")

    monkeypatch.setattr(live_state, "stm_surus_hazir", patla)
    assert hw.update_coil(2, 50.0, 25.0, 0.0, 10, start=True), (
        "durum okunamayinca tedavi ENGELLENDI -> kapinin kendi arizasi cihazi kilitliyor"
    )
