# Author: mertaygn
"""ESP FIRMWARE — `IRAM_ATTR` VERİYE KONMAZ (Exception 3 / LoadStoreError crashloop kapısı).

ÖLÇÜLEN DURUM (2026-09-09, sahibin tezgâhı): ESP8266 kartı açılışta sürekli restart atıyordu.
Seri çıktı, çökmenin sensör başlatmadan HEMEN SONRA olduğunu gösteriyordu:

    Adım 1: Sensörler başlatıldı (Kalibrasyon Bekliyor)
    Exception (3):
    epc1=0x402010a0 epc2=0x00000000 epc3=0x00000000 excvaddr=0x40106d23
    ets Jan  8 2013,rst cause:2, boot mode:(3,6)        <- yeniden boot → döngü

`excvaddr = 0x40106d23` IRAM aralığındadır (0x40100000–0x40108000) ve Exception (3)
LoadStoreError'dur. `CoilController.cpp` DDS durum değişkenlerinin ALTISINA da `IRAM_ATTR`
koyuyordu:

    static volatile bool    IRAM_ATTR s_dds_active = false;   // 1 bayt
    static volatile uint8_t IRAM_ATTR s_pin_a      = 0;       // 1 bayt

`IRAM_ATTR` = `__attribute__((section(".iram.text")))`, yani KOD bölümü. ESP8266'da IRAM
YALNIZ 32-bit erişilebilir; oraya konmuş bir `bool`/`uint8_t`a bayt erişimi LoadStoreError
fırlatır. `s_pin_a`, `CoilController::begin()` içinde yazılıyor — çökmenin "Adım 1"
satırından hemen sonra olmasının sebebi tam olarak bu (`sensors.beginWithoutCalibration()`
→ `coil->begin()`). `s_dds_active` ise 50 kHz DDS ISR'ının İLK satırında okunuyor.

DOĞRU ÇÖZÜM VERİYİ DRAM'DE BIRAKMAKTIR: ESP8266'da ISR'dan erişim kısıtı yalnız KOD içindir
(ISR'lar bu yüzden `ICACHE_RAM_ATTR`). Global/statik veri zaten DRAM'de (0x3FFExxxx) ve
kesmeden serbestçe erişilir. ESP32-S3 varyantı bunu baştan doğru yapıyordu (düz
`static volatile`) — 8266 tek istisnaydı, yani bu bir kopya-sürüklenmesiydi.

⚠️ ARDUINO AYARI ÇÖZÜM DEĞİLDİR: "Non-32-Bit Access: Byte/Word access to IRAM/PROGMEM"
seçeneği çökmeyi susturur (çekirdek bir LoadStoreError işleyicisi kurar) ama her bayt
erişimi kesmeye girer. `s_dds_active`/`s_pin_a` 50 kHz ISR'da okunduğundan bu saniyede
~150 bin ek kesme demektir → DDS zamanlaması bozulur. Bu yüzden kapı KODA bakar, ayara değil.

C bu makinede DERLENEMEZ → doğrulanabilir = YAPISAL. Yapısal kapı + mutasyon BU makinede tam
koşar; ESP derleme + REFLASH + güç çevrimi (restart döngüsünün bittiği, DDS'in 50 kHz'de
çalıştığı) tezgâh-ONLY.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from c_soyucu import c_soy

KOK = Path(__file__).resolve().parents[1]
FIRMWARE = KOK / "firmware"
KLASORLER = ["esp8266_pemf_coil", "esps3_pemf_coil"]

#: `IRAM_ATTR`/`ICACHE_RAM_ATTR`den SONRAKİ ilk sözcük ve onu izleyen karakterler.
_ATTR = re.compile(r"\b(?:IRAM_ATTR|ICACHE_RAM_ATTR|IRAM_ATTR_ISR)\b(?P<kalan>[^\n;{]*)")


def _kaynaklar() -> list[Path]:
    yollar: list[Path] = []
    for k in KLASORLER:
        d = FIRMWARE / k
        if d.is_dir():
            yollar += sorted(list(d.glob("*.cpp")) + list(d.glob("*.h")) + list(d.glob("*.ino")))
    return yollar


pytestmark = pytest.mark.skipif(not _kaynaklar(), reason="firmware/ kaynak agaci yok")


def _veri_bildirimi_mi(kalan: str) -> bool:
    """Attribute'tan sonrası FONKSİYON imzası mı, VERİ bildirimi mi?

    Ölçüt: ilk `(` ile ilk `=` hangisi önce geliyor.
      · `static void IRAM_ATTR ddsTimerISR() {`  → `(` önce  → FONKSİYON
      · `static volatile uint8_t IRAM_ATTR s_pin_a = 0;` → `(` YOK, `=` var → VERİ
      · `static volatile uint32_t IRAM_ATTR s_x = (A/B);` → `=` önce → VERİ
    Parantez de eşittir de yoksa (ör. `extern int IRAM_ATTR x`) VERİ sayılır — o da yasak.
    """
    p = kalan.find("(")
    e = kalan.find("=")
    if p >= 0 and (e < 0 or p < e):
        return False
    return True


def test_KRITIK_IRAM_ATTR_VERIYE_konmamis():
    """Hiçbir ESP kaynağında `IRAM_ATTR` bir DEĞİŞKEN bildiriminde geçmemeli.

    ⚠️ Yorumlar `c_soy` ile SÖKÜLÜR: `CoilController.cpp` bu tuzağı anlatan uzun bir uyarı
    bloğu taşıyor ve içinde `IRAM_ATTR s_dds_active` metni GEÇİYOR. Ham metin araması bu
    yüzden kalıcı YANLIŞ-KIRMIZI verirdi; kapı yalnız gerçek kodu ölçer.
    """
    ihlaller: list[str] = []
    for yol in _kaynaklar():
        soy = c_soy(yol.read_text(encoding="utf-8", errors="replace"))
        for satir_no, satir in enumerate(soy.splitlines(), 1):
            for m in _ATTR.finditer(satir):
                if _veri_bildirimi_mi(m.group("kalan")):
                    ihlaller.append(f"{yol.parent.name}/{yol.name}:{satir_no}: {satir.strip()[:100]}")
    assert not ihlaller, (
        "IRAM_ATTR bir VERI bildiriminde: ESP8266'da IRAM yalniz 32-bit erisilebilir, "
        "bayt/word erisimi Exception (3) LoadStoreError -> boot crashloop. Veriyi DRAM'de "
        "birakin (attribute'u KALDIRIN); IRAM_ATTR yalniz ISR'dan cagrilan KOD icindir.\n  " + "\n  ".join(ihlaller)
    )


def test_KARSIT_KANIT_ISR_kodu_IRAM_ATTR_TASIYOR():
    """Karşıt kanıt: kapı attribute'u topluca yasaklamıyor — ISR KODU onu TAŞIMAK ZORUNDA.

    ⚠️ Bu test olmadan "bütün IRAM_ATTR'ları sil" mutasyonu birinci kapıyı YEŞİL yapardı;
    oysa ISR'dan çağrılan kod flash'ta kalırsa kesme sırasında flash cache-miss olur ve cihaz
    çöker (8266'nın klasik ISR kuralı).

    ⚠️ HER TANIM AYRI AYRI ÖLÇÜLÜR. İlk yazımda tek bir `search` vardı ve MUTASYON KAÇTI:
    dosyada `ddsTimerISR`ın İKİ tanımı var (`#ifdef ESP32` dalı + `#else` 8266 dalı); 8266
    tanımından attribute silindiğinde arama ESP32 dalını bulup YEŞİL kalıyordu — yani asıl
    derlenen daldaki regresyonu göremiyordu.
    """
    yol = FIRMWARE / "esp8266_pemf_coil" / "CoilController.cpp"
    soy = c_soy(yol.read_text(encoding="utf-8", errors="replace"))
    tanimlar = list(re.finditer(r"\bddsTimerISR\s*\(\s*\)\s*\{", soy))
    assert tanimlar, "ddsTimerISR tanimi bulunamadi -> kapi BAYAT (isim degismis olabilir)"
    ciplak = [
        soy.count("\n", 0, m.start()) + 1
        for m in tanimlar
        if not re.search(
            r"(?:IRAM_ATTR|ICACHE_RAM_ATTR)\s+ddsTimerISR\s*\(\s*\)\s*\{\Z", soy[max(0, m.start() - 60) : m.end()]
        )
    ]
    assert not ciplak, (
        f"ddsTimerISR tanimi IRAM'de DEGIL (satir {ciplak}) -> kesme aninda flash "
        "cache-miss riski; ISR KODU IRAM_ATTR/ICACHE_RAM_ATTR tasimak ZORUNDA"
    )


def test_KRITIK_8266_DDS_durumu_DRAM_de():
    """8266 DDS durum değişkenleri düz `static volatile` olmalı (çökmenin doğrudan pini).

    Kapıyı gerçek bildirime pinler: birinci test deseni yakalar, bu test tam bu altı
    değişkenin bugünkü doğru biçimini kilitler (yeniden `IRAM_ATTR` eklenirse ikisi de kırmızı).
    """
    yol = FIRMWARE / "esp8266_pemf_coil" / "CoilController.cpp"
    soy = c_soy(yol.read_text(encoding="utf-8", errors="replace"))
    for tip, ad in [
        ("uint32_t", "s_tick_counter"),
        ("uint32_t", "s_ticks_per_period"),
        ("uint32_t", "s_duty_ticks"),
        ("bool", "s_dds_active"),
        ("uint8_t", "s_pin_a"),
    ]:
        kalip = rf"static\s+volatile\s+{tip}\s+{ad}\s*="
        assert re.search(kalip, soy), f"{ad} duz 'static volatile {tip}' olarak bildirilmemis"
