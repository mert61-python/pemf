# Author: mertaygn, cglrgrkn
"""ESP8266 EEPROM HARİTA ÇAKIŞMASI — 3. tur denetimi bulgu D4 (2026-08-24). 8266-ONLY.

ÖLÇÜLEN DURUM: non-WiFi EEPROM adresleri WiFi kimlik bölgesiyle ÇAKIŞIYOR. WiFi bölgesi manuel
stride'lı (sizeof(bool)1 + ssid[33] + password[65] = 99 bayt) × MAX_WIFI_CREDENTIALS(5) = [0, 495).
Ama EEPROM_PWM_STATE_ADDR=256 (slot2.password 232-296 içinde), EEPROM_BROKER_STATE_ADDR=300 ve
EEPROM_CONFIG_VER_ADDR=304 (slot3.ssid 297-330 içinde). SharedDefs.h:155 "0-255 WiFi için" yorumu
YANLIŞ. Sonuç: (a) 30 sn'lik savePWMState kayıtlı WiFi parolasını BOZAR; (b) portal WiFi yazımı
CONFIG_VER'i örter → boot'ta sürüm-uyuşmazlığı → wipe → tekrarlayan migrasyon.

DÜZELTME: non-WiFi bloğu WiFi bölgesinin GERÇEK sonrasına (≥495) taşı (5-slot kapasitesini KORU;
slot daraltma DEĞİL). Boot version-mismatch wipe'ı tüm WiFi bölgesini (0..494) silsin (yalnız 256
değil → bayat slot3-4 valid=true kalmasın). clearAllWiFiCredentials yalnız WiFi bölgesini silsin
(relocated CONFIG_VER/PWM'i ezmesin).

C bu makinede DERLENEMEZ → dogrulanabilir=YAPISAL_MODEL. Python adres-modeli + c_soy yapısal kapı +
iki-yönlü mutasyon BU makinede TAM koşar; ESP derleme + REFLASH + güç-çevrimi (tek-seferlik wipe
sonra stabil / savePWMState artık WiFi bozmuyor / yeni adreste PWM-resume çalışıyor) tezgâh-ONLY.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from c_soyucu import c_soy

KOK = Path(__file__).resolve().parents[1]
ESP = KOK / "firmware" / "esp8266_pemf_coil"
SHARED = ESP / "SharedDefs.h"
NMH = ESP / "NetworkManager.h"
NMC = ESP / "NetworkManager.cpp"
INO = ESP / "esp8266_pemf_coil.ino"

#: ESP8266 (xtensa-lx106, GCC) C ABI: tür → (boyut, hizalama). `enum` = int. Tabloda olmayan tür → kapı KIRMIZI.
XTENSA_ABI: dict[str, tuple[int, int]] = {
    "uint8_t": (1, 1),
    "int8_t": (1, 1),
    "char": (1, 1),
    "bool": (1, 1),
    "uint16_t": (2, 2),
    "int16_t": (2, 2),
    "short": (2, 2),
    "int": (4, 4),
    "unsigned": (4, 4),
    "unsigned int": (4, 4),
    "uint32_t": (4, 4),
    "int32_t": (4, 4),
    "long": (4, 4),
    "unsigned long": (4, 4),
    "float": (4, 4),
    "double": (8, 8),
    "uint64_t": (8, 8),
    "int64_t": (8, 8),
}


def c_struct_boyutu(soy: str, ad: str, abi: dict[str, tuple[int, int]] = XTENSA_ABI) -> int:
    """`struct AD { … };` (YORUMU SOYULMUŞ) → sizeof: alan sırası, hizalama dolgusu ve sondaki dolgu dahil.

    ⚠️ D1.49 (B-10.231): sizeof eskiden ELLE (`PWM_SIZE = 24`) yazılıydı — struct'a 4 baytlık bir alan
    eklenince PWM span'i [512,540) BROKER'ı (536) örterken bu dosya YEŞİL kalıyordu."""
    m = re.search(rf"\bstruct\s+{re.escape(ad)}\s*\{{(.*?)\}}\s*;", soy, re.S)
    assert m, f"struct {ad} (yorum dışı) bulunamadı"
    ofset, en_hizali = 0, 1
    for bildirim in (b.strip() for b in m.group(1).split(";")):
        if not bildirim:
            continue
        a = re.fullmatch(r"((?:unsigned\s+|signed\s+)?[A-Za-z_]\w*)\s+([A-Za-z_]\w*)\s*(?:\[\s*(\d+)\s*\])?", bildirim)
        assert a, f"struct {ad}: ayrıştırılamayan alan {bildirim!r} — kapıyı güncelle"
        tur = " ".join(a.group(1).split())
        assert tur in abi, f"struct {ad}: ABI tablosunda olmayan tür {tur!r}"
        boyut, hiza = abi[tur]
        ofset = (ofset + hiza - 1) // hiza * hiza + boyut * int(a.group(3) or 1)
        en_hizali = max(en_hizali, hiza)
    return (ofset + en_hizali - 1) // en_hizali * en_hizali


PWM_SIZE = c_struct_boyutu(c_soy(SHARED.read_text(encoding="utf-8", errors="replace")), "PWMStateEEPROM")
BROKER_SIZE = 4  # BrokerType enum (int) — xtensa ABI'de 4 bayt


def _define(soy: str, ad: str) -> int:
    m = re.search(rf"#define\s+{re.escape(ad)}\s+(\d+)", soy)
    assert m, f"{ad} tanımı bulunamadı"
    return int(m.group(1))


def _shared() -> str:
    return c_soy(SHARED.read_text(encoding="utf-8", errors="replace"))


def _wifi_bolge() -> tuple[int, int]:
    h = c_soy(NMH.read_text(encoding="utf-8", errors="replace"))
    mx = int(re.search(r"MAX_WIFI_CREDENTIALS\s*=\s*(\d+)", h).group(1))
    start = int(re.search(r"EEPROM_WIFI_START\s*=\s*(\d+)", h).group(1))
    ssid = int(re.search(r"char\s+ssid\[(\d+)\]", h).group(1))
    pw = int(re.search(r"char\s+password\[(\d+)\]", h).group(1))
    stride = 1 + ssid + pw  # sizeof(bool) + ssid + password (save/load MANUEL stride)
    return start, start + mx * stride


def _eeprom_size() -> int:
    h = c_soy(NMH.read_text(encoding="utf-8", errors="replace"))
    return int(re.search(r"EEPROM_SIZE\s*=\s*(\d+)", h).group(1))


def _nonwifi_spanlar() -> dict[str, tuple[int, int]]:
    soy = _shared()
    return {
        "PWM": (_define(soy, "EEPROM_PWM_STATE_ADDR"), PWM_SIZE),
        "BROKER": (_define(soy, "EEPROM_BROKER_STATE_ADDR"), BROKER_SIZE),
        "CONFIG_VER": (_define(soy, "EEPROM_CONFIG_VER_ADDR"), 1),
    }


def _cakisir(a: tuple[int, int], b: tuple[int, int]) -> bool:
    (a0, an), (b0, bn) = a, b
    return a0 < b0 + bn and b0 < a0 + an


# ═══════════════════════ DAVRANIŞSAL ADRES MODELİ ═════════════════════════════════════════════
def test_KRITIK_D4_nonwifi_adresler_wifi_bolgesiyle_cakismiyor():
    w0, w1 = _wifi_bolge()
    size = _eeprom_size()
    for ad, (addr, n) in _nonwifi_spanlar().items():
        assert not _cakisir((addr, n), (w0, w1 - w0)), (
            f"{ad} EEPROM span'i [{addr},{addr + n}) WiFi bölgesi [{w0},{w1}) ile ÇAKIŞIYOR — "
            f"WiFi yazımı ile birbirini bozar (D4 kök neden)"
        )
        assert 0 <= addr and addr + n <= size, f"{ad} span'i [{addr},{addr + n}) EEPROM_SIZE={size} DIŞINDA"


def test_KRITIK_D4_nonwifi_spanlar_birbiriyle_cakismiyor():
    spanlar = list(_nonwifi_spanlar().items())
    for i in range(len(spanlar)):
        for j in range(i + 1, len(spanlar)):
            (a, sa), (b, sb) = spanlar[i], spanlar[j]
            assert not _cakisir(sa, sb), f"{a} ve {b} span'leri çakışıyor: {sa} vs {sb}"


def _yinelenir(config_ver_addr: int) -> bool:
    """config_ver WiFi bölgesindeyse portal WiFi yazımı onu örter → boot mismatch → wipe → yineleme."""
    w0, w1 = _wifi_bolge()
    return w0 <= config_ver_addr < w1


def test_KRITIK_D4_migrasyon_yinelenme_yok():
    cfg = _define(_shared(), "EEPROM_CONFIG_VER_ADDR")
    assert not _yinelenir(cfg), (
        f"CONFIG_VER adresi {cfg} WiFi bölgesinde — portal WiFi yazımı onu ezer, her boot'ta "
        "sürüm-uyuşmazlığı wipe'ı tetiklenir (tekrarlayan migrasyon, D4)"
    )


def test_MODEL_AYIRT_EDIYOR_bilinen_ici_adres_yinelenme_raporlar():
    """Ayrıştırıcı öz-kontrol: bilinen-İÇERİDE bir adres (304, eski değer) yineleme=True vermeli;
    aksi hâlde model off-by-one ve asıl kapı anlamsız."""
    assert _yinelenir(304), "model bilinen-içeride adresi (304) yineleme saymıyor — off-by-one"


def test_KARSIT_KANIT_D4_reverse_pwm_wifi_bolgesini_bozmuyor():
    """Ters kol: PWM span'i WiFi bölgesindeyse 30 sn'lik savePWMState slot parolasını bozar."""
    w0, w1 = _wifi_bolge()
    pwm_addr = _define(_shared(), "EEPROM_PWM_STATE_ADDR")
    assert not _cakisir((pwm_addr, PWM_SIZE), (w0, w1 - w0)), (
        f"PWM span [{pwm_addr},{pwm_addr + PWM_SIZE}) WiFi bölgesinde — periyodik savePWMState "
        "kayıtlı WiFi'yi bozar (D4 ters kol)"
    )


# ═══════════════════════ YAPISAL KAPILAR (c_soy) ══════════════════════════════════════════════
def test_YAPISAL_D4_boot_wipe_tum_wifi_bolgesini_siliyor():
    ino = c_soy(INO.read_text(encoding="utf-8", errors="replace"))
    i = ino.index("if (storedVersion != EEPROM_CONFIG_VERSION)")
    govde = ino[i : ino.index("EEPROM.commit()", i)]
    assert "for (int i = 0; i < 256;" not in govde, (
        "boot wipe hâlâ literal 256'ya sınırlı — slot3-4 (297-494) bayat valid=true kalır, migrasyon "
        "iki boot'a uzar (D4)"
    )
    assert "EEPROM_WIFI_REGION_END" in govde, (
        "boot wipe WiFi bölge-sonu (EEPROM_WIFI_REGION_END) isimli sabitini kullanmıyor"
    )


def test_YAPISAL_D4_nonwifi_adresler_bolge_sonu_uzerinde():
    soy = _shared()
    region_end = _define(soy, "EEPROM_WIFI_REGION_END")
    for ad in ("EEPROM_PWM_STATE_ADDR", "EEPROM_BROKER_STATE_ADDR", "EEPROM_CONFIG_VER_ADDR"):
        assert _define(soy, ad) >= region_end, (
            f"{ad} EEPROM_WIFI_REGION_END={region_end} ALTINDA — WiFi bölgesiyle çakışır (D4)"
        )


def test_KARSIT_KANIT_D4_wifi_slot_stride_degismedi():
    """Çakışmayı slot daraltarak 'çözme' regresyonunu yakalar: 5-slot kapasitesi + 99-bayt manuel
    stride korunmalı."""
    h = NMH.read_text(encoding="utf-8", errors="replace")
    assert "MAX_WIFI_CREDENTIALS = 5" in h, "kayıtlı-ağ kapasitesi 5'ten düşürüldü"
    assert "char ssid[33]" in h and "char password[65]" in h, "WiFi slot alan boyları değişti"
    save = c_soy(NMC.read_text(encoding="utf-8", errors="replace"))
    i = save.index("void NetworkManager::_saveWiFiCredentials()")
    govde = save[i : save.index("void NetworkManager::", i + 10)]
    assert "sizeof(bool)" in govde and "address += 33" in govde and "address += 65" in govde, (
        "WiFi save manuel stride'ı (1+33+65) değişti — bölge matematiği kayar"
    )


def test_KARSIT_KANIT_D4_PWMStateEEPROM_layout_degismedi():
    """PWM struct küçültüp çakışmayı 'çözme' regresyonunu yakalar: [1.3] magic/checksum + 24-bayt
    ikili düzen korunmalı."""
    s = _shared()  # D1.49: yorumu soyulmuş — yoruma alınmış alan "var" sayılmaz
    i = s.index("struct PWMStateEEPROM")
    govde = s[i : s.index("};", i)]
    for alan in ("magic", "active", "frequency", "dutyCycle", "duration", "elapsed", "checksum"):
        assert alan in govde, f"PWMStateEEPROM alanı '{alan}' kayboldu — 24-bayt/[1.3] sözleşmesi bozuldu"


def test_KARSIT_KANIT_D4_wifi_clear_bolge_sonuyla_sinirli():
    """clearAllWiFiCredentials tüm EEPROM'u değil yalnız WiFi bölgesini silmeli; yoksa relocated
    CONFIG_VER/PWM'i ezip her WiFi-temizlemede migrasyonu yeniden tetikler."""
    soy = c_soy(NMC.read_text(encoding="utf-8", errors="replace"))
    i = soy.index("void NetworkManager::clearAllWiFiCredentials()")
    govde = soy[i : soy.index("void NetworkManager::", i + 10)]
    assert "i < EEPROM_SIZE" not in govde, (
        "clearAllWiFiCredentials hâlâ tüm EEPROM'u (< EEPROM_SIZE) siliyor — relocated non-WiFi bloğu "
        "ezilir, WiFi-temizleme migrasyonu yeniden tetikler (D4)"
    )
    assert "EEPROM_WIFI_REGION_END" in govde, "clearAll WiFi bölge-sonuyla sınırlanmamış"


# ═══════════════════════ D1.49 · sizeof KAYNAKTAN ═════════════════════════════════════════════
def test_D149_PWMStateEEPROM_boyutu_KAYNAKTAN_ve_bilincli_PIN():
    """Bugünkü düzen 24 bayt [512,536). Değişirse EEPROM düzeni değişmiştir: CONFIG_VERSION ve adres haritası
    BİLİNÇLİ güncellenmeli (sahadaki kayıtlı PWM durumu yeni struct'la yanlış okunur)."""
    assert PWM_SIZE == 24, f"sizeof(PWMStateEEPROM) kaynaktan {PWM_SIZE} — EEPROM düzeni değişti"


def test_ARAC_D149_struct_boyutu_hizalama_ve_dolgu():
    assert c_struct_boyutu("struct A { uint8_t a; int b; };", "A") == 8
    assert c_struct_boyutu("struct A { uint8_t a; uint8_t b; };", "A") == 2
    assert c_struct_boyutu("struct A { int a; uint8_t b; };", "A") == 8
    assert c_struct_boyutu("struct A { char s[33]; bool v; };", "A") == 34
    assert (
        c_struct_boyutu(
            "struct A { uint8_t m; bool a; int f; int d; unsigned long u; unsigned long e; uint8_t c; };", "A"
        )
        == 24
    )
    with pytest.raises(AssertionError, match="ABI"):
        c_struct_boyutu("struct A { Foo x; };", "A")


def test_ARAC_D149_struct_a_4_baytlik_alan_eklenince_harita_KIRMIZI():
    """Plan mutantı: PWMStateEEPROM'a 4 baytlık alan → sizeof 28 → PWM span [512,540) BROKER'ı (536) örter."""
    soy = _shared()
    capa = "uint8_t checksum;"
    assert soy.count(capa) == 1
    mutant = soy.replace(capa, "uint32_t ekAlan; " + capa)
    boyut = c_struct_boyutu(mutant, "PWMStateEEPROM")
    assert boyut == 28
    pwm = (_define(mutant, "EEPROM_PWM_STATE_ADDR"), boyut)
    broker = (_define(mutant, "EEPROM_BROKER_STATE_ADDR"), BROKER_SIZE)
    assert _cakisir(pwm, broker), "4 baytlık alan eklenince PWM span'i BROKER ile çakışmalıydı — model kör"
