# -*- coding: utf-8 -*-
# Author: mertaygn
"""STM32 SENSÖR KATMANI — yapısal kapı (C bu depoda DERLENMEZ).

`firmware/stm32_pemf/Core/Src/pemf_sensor.c` bobin 6-7'nin MLX90614 + MLX90393 okumasını
registre seviyesinde yapar. Tezgâh doğrulaması ZORUNLU; burada doğrulanabilir olan **yapısal**
şeyler pinlenir. Dört ayrı iddia var, hepsinin arkasında ölçülmüş bir arıza sınıfı duruyor:

1. **BLOKLAMAMA.** Ana döngü 1500 ms sessizlikte ölü-adam watchdog'unu tetikler ve firmware
   TÜM bobinleri durdurur. Sensör kodu ana döngüyü tutarsa watchdog SAHTE bir kopuş görür →
   **tedavi ortasında bobinler kesilir**. `HAL_Delay` ve bütçesiz `while` yasak.

2. **ÖLÇEK SABİTLERİ.** `0.150` / `0.242` µT/LSB değerleri Adafruit_MLX90393'ün
   `mlx90393_lsb_lookup[HALLCONF=0xC][GAIN_SEL=7][RES_16]` satırından geliyor — yani
   **ESP'nin bugün ürettiği sayının kaynağı**. Değiştirmek geçmiş kayıtlarla
   kıyaslanabilirliği bozar (1.9.45'te µm gap değişiminin aynısı: eski kayıtlarla
   kıyaslanamaz hale gelmişti).

3. **TERMAL KESME EKLENMEMİŞ.** Sahip 2026-09-10'da bobin 6-7 için termal kesme İSTEMEDİ.
   Bu dosya sıcaklığı okur ve bildirir; PWM'i durdurmaz. Buraya sessizce bir kesme eklenmesi
   sahip kararını iptal eder (ters yönde de tehlikeli: eşiği kimse ölçmemiş olur).

4. **HAT KURTARMA.** Uzun kabloda takılı I2C bus'ı sahada 8266'da GERÇEKTEN yaşandı
   (`SensorManager::_clearI2CBus/_isI2CBusStuck/_hardResetI2C`). Kurtarma olmadan sensör bir
   daha geri gelmez ve **sıcaklık sessizce donar** — arayüz son değeri göstermeye devam eder.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
SRC = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "pemf_sensor.c"
HDR = KOK / "firmware" / "stm32_pemf" / "Core" / "Inc" / "pemf_sensor.h"
MAIN = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "main.c"
# ⚠️ AYNA KAPISI KALDIRILDI (2026-09-11): `stm32_pemf_unipolar` projesi silindi.
# Sebep: surus kipi artik `PEMF_BOBIN_UNIPOLAR_MASKESI` ile BOBIN BASINA seciliyor,
# ikinci bir derleme gerekmiyor. TEK kaynak = firmware/stm32_pemf.

pytestmark = pytest.mark.skipif(not SRC.exists(), reason="pemf_sensor.c yok")


def _oku(p: Path) -> str:
    return io.open(p, encoding="utf-8", errors="replace").read()


def yorumsuz(kod: str) -> str:
    """C yorumlarını ve string literallerini boşlukla değiştirir (satır sayısı korunur)."""
    out: list[str] = []
    i, n, durum = 0, len(kod), "kod"
    while i < n:
        ch = kod[i]
        if durum == "kod":
            if kod[i : i + 2] == "//":
                durum, i = "satir", i + 2
                out.append("  ")
                continue
            if kod[i : i + 2] == "/*":
                durum, i = "blok", i + 2
                out.append("  ")
                continue
            if ch in '"' + chr(39):
                durum = "str" if ch == '"' else "chr"
                out.append(" ")
                i += 1
                continue
            out.append(ch)
        elif durum == "satir":
            out.append("\n" if ch == "\n" else " ")
            if ch == "\n":
                durum = "kod"
        elif durum == "blok":
            out.append("\n" if ch == "\n" else " ")
            if kod[i : i + 2] == "*/":
                out.append(" ")
                durum, i = "kod", i + 2
                continue
        else:
            if ch == chr(92):
                out.append("  ")
                i += 2
                continue
            kapanis = '"' if durum == "str" else chr(39)
            out.append("\n" if ch == "\n" else " ")
            if ch == kapanis:
                durum = "kod"
        i += 1
    return "".join(out)


def test_KRITIK_BLOKLAMAZ_HAL_Delay_ve_butcesiz_while_YOK():
    """Sensör kodu ana döngüyü ms'ler boyunca TUTMAMALI.

    MUTASYON: `PEMF_Sensor_Poll` içine `HAL_Delay(17);` koy → KIRMIZI.
    Sahadaki etki: ana döngü tıkanır → ölü-adam watchdog'u SAHTE kopuş görür → tedavi
    ortasında tüm bobinler kesilir.
    """
    kod = yorumsuz(_oku(SRC))
    assert "HAL_Delay" not in kod, (
        "pemf_sensor.c icinde HAL_Delay var — ana dongu tikanir ve olu-adam watchdog'u "
        "SAHTE kopus gorup TUM bobinleri keser. Beklemeler HAL_GetTick DAMGASI ile yapilir."
    )
    # Her `while` bir bütçe azaltmasi TASIMALI (`butce--` gibi) ya da `for` olmalı.
    for m in re.finditer(r"\bwhile\s*\(([^)]*)\)", kod):
        kosul = m.group(1)
        assert "butce" in kosul, (
            f"BUTCESIZ while bulundu: while ({kosul.strip()}) — kopuk SDA hattinda kart "
            "KILITLENIR. Her bayrak beklemesi cevrim butceli olmali (i2c_bekle)."
        )


def test_KRITIK_donusum_suresi_DAMGA_ile_beklenir():
    """MLX90393 dönüşümü bir BEKLEME değil, bir zaman DAMGASI olmalı.

    ⚠️ 2026-09-11'de damga kaynağı DEĞİŞTİ: dönüşüm 6,84 ms'ten 1,27 ms'e indi (DIG_FILT=0,
    OSR=0) ve `HAL_GetTick()` 1 ms çözünürlüklü olduğu için artık DWT çevrim sayacı
    kullanılıyor (`mag_hazir_cyc`), tick yolu YEDEK. Kapı ikisini de tanır; ASIL iddia
    değişmedi: **beklemek için ana döngü BLOKLANMAZ**.

    MUTASYON: `S_MAG_BEKLE` gövdesini `HAL_Delay(2); h->durum = S_MAG_OKU;` yap → KIRMIZI.
    Sahadaki etki: ana döngü ~400 Hz'de 2 ms bloklanır, ölü-adam watchdog'u sahte kopuş
    görüp tedavi ortasında bobinleri keser.
    """
    kod = yorumsuz(_oku(SRC))
    assert "S_MAG_BEKLE" in kod, "donusum bekleme durumu yok -> sure BLOKLAYARAK bekleniyor olabilir"
    assert "mag_hazir_cyc" in kod or "mag_hazir_ms" in kod, "donusum damgasi YOK"
    # Bekleme kararı ayrı bir yardımcıya taşındı; damga karşılaştırması ORADA olabilir.
    _pencere = kod
    assert re.search(r"(DWT->CYCCNT\s*-\s*[^;]*mag_hazir_cyc)|(simdi_ms\s*-\s*[^;]*mag_hazir_ms)", _pencere), (
        "donusum beklemesi damga KARSILASTIRMIYOR"
    )
    # ⚠️ KARSIT-KANIT: bloklayici bekleme SIZMASIN. Bu dosyada `HAL_Delay` HIC olmamali.
    assert "HAL_Delay" not in kod, (
        "sensor katmaninda HAL_Delay VAR -> ana dongu bloklanir, olu-adam watchdog'u sahte kopus gorur"
    )


def test_KRITIK_DWT_sayaci_OLCULEREK_dogrulanir():
    """DWT çevrim sayacı VARSAYILMAZ, açılışta gerçekten ilerlediği ÖLÇÜLÜR.

    ⚠️ NEDEN KAPI: 1,27 ms'lik dönüşüm beklemesi bu sayaca dayanıyor. Sayaç ilerlemezse
    (bazı kartlarda TRCENA açılmaz) hedef çevrim ASLA gelmez ve manyetik durum makinesi
    `S_MAG_BEKLE`de SONSUZA KADAR takılır. Ana döngü dönmeye devam ettiği için ölü-adam
    watchdog'u bunu YAKALAMAZ — alan telemetrisi sessizce kesilir ve kimse fark etmez.

    MUTASYON: `g_dwt_var = (DWT->CYCCNT != t0);` → `g_dwt_var = true;` yap → KIRMIZI.
    """
    kod = yorumsuz(_oku(SRC))
    assert "g_dwt_var" in kod, "DWT kullanilabilirlik bayragi YOK"
    # ⚠️ TUM atamalar taranir: ilki `static bool g_dwt_var = false;` BASLANGIC degeridir,
    # onu okuyup "CYCCNT yok" demek kapiyi HER ZAMAN kirmizi yapardi (sahte kirmizi da
    # sahte yesil kadar zararlidir — kimse kapiya bakmaz olur).
    atamalar = re.findall(r"g_dwt_var\s*=\s*([^;]+);", kod)
    assert atamalar, "g_dwt_var atamasi bulunamadi -> kapi BAYAT"
    olcenler = [a for a in atamalar if "CYCCNT" in a]
    assert olcenler, (
        f"g_dwt_var atamalari {atamalar!r} — hicbiri sayacin GERCEKTEN ilerledigini OLCMUYOR. "
        "Ilerlemeyen sayacta manyetik okuma sessizce sonsuza kadar durur."
    )
    # Baslangic degeri GUVENSIZ olmali: olcum yapilmadan once true varsayilirsa,
    # `dwt_baslat()` cagrilmayi unutuldugunda kilitlenme geri gelir.
    ilk = re.search(r"static bool g_dwt_var\s*=\s*([^;]+);", kod)
    assert ilk and ilk.group(1).strip() == "false", (
        f"g_dwt_var baslangici {ilk.group(1) if ilk else None} — 'false' olmali (olculene kadar YOK say)"
    )
    # Yedek yol da bulunmali: DWT yoksa tick'e dusulur, kilitlenilmez.
    assert "MLX90393_DONUSUM_MS_YEDEK" in kod, "DWT yoksa YEDEK bekleme yolu YOK -> kilitlenme"


#: Adafruit_MLX90393.h `mlx90393_lsb_lookup[HALLCONF=0xC][GAIN_SEL][RES_16]` — (XY, Z) µT/LSB.
#: Kütüphane dosyasından BİREBİR kopyalandı (satır 105-125).
ADAFRUIT_LSB_RES16 = {
    0: (0.751, 1.210),
    1: (0.601, 0.968),
    2: (0.451, 0.726),
    3: (0.376, 0.605),
    4: (0.300, 0.484),
    5: (0.250, 0.403),
    6: (0.200, 0.323),
    7: (0.150, 0.242),
}

#: Sahip 2026-09-11: "1-10 mT arası genelde, 0-5 arası aşırı fazla".
#: Tam ölçek bu bandın ÜSTÜNDE olmalı — pay olmadan anahtarlama aşımı sarar.
SAHIP_AZAMI_ALAN_MT = 10.0
GEREKLI_TAM_OLCEK_MT = 15.0  # sahibin bandına en az %50 pay


def _mlx_sabiti(kod, ad):
    m = re.search(r"#define\s+" + ad + r"\s+([0-9.]+)f?U?", kod)
    assert m, f"{ad} bulunamadi -> kapi BAYAT"
    return m.group(1)


def test_KRITIK_olcek_sabitleri_ADAFRUIT_TABLOSU_ile_AYNI():
    """LSB sabitleri, kaynakta SEÇİLİ olan GAIN_SEL'in Adafruit satırıyla AYNI olmalı.

    ⚠️ KAPI 2026-09-11'DE YENİDEN ÇIPALANDI. Eskiden `GAIN_SEL == 7` ve `0.150/0.242`
    SABİT olarak pinlenmişti; sahip ölçüm bandını verince (1-10 mT) o ayarın tam ölçeği
    (XY 4,92 mT) YETERSİZ çıktı ve GAIN_SEL 0'a alındı. Sayıyı sabit pinlemek, kapının
    KENDİSİNİ doğru değişimin önünde engel yapıyordu.

    Yeni iddia DAHA GÜÇLÜ ve ayardan bağımsız: **kaynaktaki LSB çifti, kaynaktaki
    GAIN_SEL'in tablo satırıyla tutarlı olmalı**. Böylece asıl arıza sınıfı yakalanır:
    gain değişip ölçek sabitinin unutulması (ya da tersi) — o hâlde her mT %500'e kadar
    yanlış olur ve hiçbir şey uyarı vermez.

    MUTASYON A: `MLX90393_GAIN_SEL 0` → `4` (LSB'lere dokunmadan) → KIRMIZI.
    MUTASYON B: `MLX90393_LSB_XY_UT 0.751f` → `0.161f` → KIRMIZI.
    """
    kod = _oku(SRC)
    gain = int(_mlx_sabiti(kod, "MLX90393_GAIN_SEL"))
    assert gain in ADAFRUIT_LSB_RES16, f"GAIN_SEL={gain} Adafruit tablosunda YOK (0-7 olmali)"
    bek_xy, bek_z = ADAFRUIT_LSB_RES16[gain]
    xy = float(_mlx_sabiti(kod, "MLX90393_LSB_XY_UT"))
    z = float(_mlx_sabiti(kod, "MLX90393_LSB_Z_UT"))
    assert xy == bek_xy, (
        f"GAIN_SEL={gain} icin XY olcegi {bek_xy} olmali, kaynakta {xy}. Ayar ile olcek "
        "AYRISMIS -> uretilen her mT sessizce YANLIS."
    )
    assert z == bek_z, f"GAIN_SEL={gain} icin Z olcegi {bek_z} olmali, kaynakta {z}"


def test_KRITIK_olcum_araligi_SAHIBIN_BANDINI_KAPSAR():
    """Tam ölçek, sahibin ölçüm bandını (1-10 mT) PAYLA kapsamalı — HER EKSENDE.

    ⚠️ NEDEN AYRI VE KRİTİK BİR KAPI (2026-09-11): RES_16'da MLX90393, 19-bit sonucun ALT
    16 BİTİNİ döndürür. Taşan değer KIRPILMAZ, **SARAR** — 15 mT'lik gerçek bir alan küçük
    ya da NEGATİF bir sayı olarak okunur. Sarma yazılımdan tespit EDİLEMEZ (doygunluk
    bayrağı bile yakalayamaz, çünkü sarmış ham değer küçüktür). TEK savunma yeterli
    aralıktır — yani bu kapı, bir bayrağın değil, FİZİĞİN kapısıdır.

    İlk sürüm GAIN_SEL=7 ile geldi: XY tam ölçek 4,92 mT → sahibin bandının ÜST YARISI
    ölçülemiyordu ve kimse fark etmezdi.

    MUTASYON: `MLX90393_GAIN_SEL 0` → `7` (LSB'leri de 0.150/0.242 yaparak, yani yukarıdaki
    tutarlılık kapısını MEMNUN EDEREK) → bu kapı KIRMIZI. İki kapı birlikte, "tutarlı ama
    yetersiz" ayarı da yakalar.
    """
    kod = _oku(SRC)
    xy = float(_mlx_sabiti(kod, "MLX90393_LSB_XY_UT"))
    z = float(_mlx_sabiti(kod, "MLX90393_LSB_Z_UT"))
    tam_xy_mt = 32767 * xy / 1000.0
    tam_z_mt = 32767 * z / 1000.0
    assert tam_xy_mt >= GEREKLI_TAM_OLCEK_MT, (
        f"XY tam olcek {tam_xy_mt:.2f} mT < {GEREKLI_TAM_OLCEK_MT} mT. Sahip bandi "
        f"{SAHIP_AZAMI_ALAN_MT} mT'ye kadar; RES_16'da tasma KIRPILMAZ, SARAR -> buyuk alan "
        "KUCUK okunur ve zirve mantigi o yanlis sayiyi 'maksimum' diye kilitler."
    )
    assert tam_z_mt >= GEREKLI_TAM_OLCEK_MT, f"Z tam olcek {tam_z_mt:.2f} mT < {GEREKLI_TAM_OLCEK_MT} mT"


def test_KRITIK_okuma_hizi_DARBEYI_yakalayacak_kadar():
    """Dönüşüm süresi, 100 Hz'lik bobin darbesinde birden çok örnek düşürecek kadar kısa olmalı.

    ⚠️ NEDEN: bobinler birlikte anahtarlanıyor. Darbe periyodunda tek örnek düşerse zirve
    tesadüfe kalır — sahip tam olarak bunu bildirdi ("hepsi aynı anda açıkken kaç mT").
    tconv tablosu (Adafruit_MLX90393.h `mlx90393_tconv[DIG_FILT][OSR]`) DIG_FILT=0/OSR=0'da
    1,27 ms verir; eski ayar (DIG_FILT=1/OSR=3) 6,84 ms idi ve 100 Hz'de tek örnek bile
    garanti değildi.

    MUTASYON: `MLX90393_OSR 0` → `3` yap → KIRMIZI.
    """
    kod = _oku(SRC)
    tconv = {
        0: (1.27, 1.84, 3.00, 5.30),
        1: (1.46, 2.23, 3.76, 6.84),
        2: (1.84, 3.00, 5.30, 9.91),
        3: (2.61, 4.53, 8.37, 16.05),
    }
    df = int(_mlx_sabiti(kod, "MLX90393_DIG_FILT"))
    osr = int(_mlx_sabiti(kod, "MLX90393_OSR"))
    assert df in tconv and osr < 4, f"DIG_FILT={df} OSR={osr} tconv tablosunda YOK"
    sure_ms = tconv[df][osr]
    assert sure_ms <= 2.0, (
        f"tconv {sure_ms} ms — 100 Hz'lik darbe periyodunda (10 ms) yeterli ornek dusmez; "
        "zirve darbenin neresine denk geldigine gore RASTGELE olur."
    )
    # Kaynaktaki bekleme, tconv'den KISA olamaz: donusum bitmeden okumak cop veri verir.
    us = int(_mlx_sabiti(kod, "MLX90393_DONUSUM_US"))
    assert us >= sure_ms * 1000, f"bekleme {us} us < tconv {sure_ms} ms — donusum BITMEDEN okunuyor"


def test_KRITIK_buyukluk_mT_ve_ESP_ile_AYNI_TANIM():
    """`magneticMt` = sqrt(x²+y²+z²)/1000. ESP: SensorManager.cpp:418-419 ile birebir."""
    kod = yorumsuz(_oku(SRC))
    assert re.search(r"sqrtf\(.*\)\s*/\s*1000\.0f", kod, re.S), (
        "|B| buyuklugu mT'ye cevrilmiyor (sqrtf(...)/1000.0f yok) -> ESP ile AYRI birim: "
        "`magneticMt` alaninin anlami sessizce degisir"
    )


def test_KRITIK_TERMAL_KESME_EKLENMEMIS():
    """Sahip kararı: bobin 6-7 için termal kesme YOK. Sensör katmanı PWM'e DOKUNMAZ.

    MUTASYON: `if (sv.nesne_c > 60.0f) { g_shadow.coil[5].duty = 0.0f; }` ekle → KIRMIZI.
    Ters yön de tehlikeli: eşik kimse tarafından ölçülmemiş olur ve sahip kararı sessizce
    iptal edilir.
    """
    kod = yorumsuz(_oku(SRC))
    for yasak in ("g_shadow", "g_active", "coil_gpio", "duty", "TERMAL_KESME", "NTC_KESME_C"):
        assert yasak not in kod, (
            f"pemf_sensor.c '{yasak}' gecuyor — sensor katmani SURUS durumuna DOKUNMAMALI. "
            "Sahip 2026-09-10'da bobin 6-7 icin termal kesme ISTEMEDI; kesme eklemek bilincli "
            "bir SAHIP KARARI gerektirir (ve esik olculmelidir)."
        )
    # ⚠️ BSRR yasaklanamaz: I2C hat kurtarma PB8-PB11'i elle darbeler (mesru). Asil degismez
    # olan su: sensor katmani BOBIN PORTLARINA HIC dokunmaz. Bobin pinleri GPIOA/C/D/E'de;
    # bu dosya YALNIZ GPIOB kullanir. Bir bobin portu gecerse, bir bobin pinini surme
    # ihtimali dogar (or. PE13 = bobin 6 IN_A, PA8 = bobin 5 IN_A).
    for port in ("GPIOA", "GPIOC", "GPIOD", "GPIOE", "GPIOF", "GPIOG"):
        assert port not in kod, (
            f"pemf_sensor.c {port}'ya dokunuyor — bobin pinleri o portlarda (PA8 PC6 PC8 PC9 "
            "PD10 PD12 PE13 PE15...). Sensor katmani YALNIZ GPIOB (I2C1/I2C2) kullanmali."
        )


def test_KRITIK_I2C_HAT_KURTARMA_VAR():
    """Takılı bus kurtarılmazsa sıcaklık SESSİZCE DONAR (8266'da sahada yaşandı)."""
    kod = yorumsuz(_oku(SRC))
    assert "i2c_hat_kurtar" in kod, "hat kurtarma fonksiyonu YOK"
    assert "I2C_CR1_SWRST" in kod, "cevre birimi SWRST ile sifirlanmiyor"
    assert re.search(r"for\s*\([^)]*<\s*9U", kod), (
        "9 saat darbesi (stuck-slave birakma) yok — SDA LOW takili kalirsa bus geri gelmez"
    )
    assert "I2C_KURTARMA_ESIGI" in kod, "kurtarma esigi sabiti yok (sihirli sayi?)"


def test_KRITIK_SENSOR_satiri_AKIM_alani_TASIMAZ():
    """⚠️ KAPI BİLİNÇLİ ÇEVRİLDİ (2026-09-10): eskiden `STM_TELE`de `I=` TAMAMEN yasaktı
    ("ACS712 taşınmıyor"). Sahip kararını değiştirdi → bobin 1-5'te akım var.

    Yeni ve DAHA KESKİN iddia: **bobin 6-7'nin sensör satırı akım taşımaz** (o bobinlerde
    ACS712 yok) ve alanlar `*_ok` ile kapılanır. Yani "akım hiç yok" değil, "ölçülmeyen
    yerde yok". Ölçülmeyen alanı göndermek (özellikle 0.0) aşağı akışta "ölçüldü" olarak
    kaydedilir — PDF'e "0.0 °C ölçüldü" yazdıran desen.
    """
    ana = _oku(MAIN)
    i = ana.find("BOBIN 6-7 SENSOR TELEMETRISI")
    assert i > 0, "main.c'de sensor telemetri blogu yok -> telemetri hic gonderilmiyor"
    j = ana.find("BOBIN 1-5 AKIM TELEMETRISI", i)
    assert j > i, "akim telemetri blogu yok -> bobin 1-5 akimi hic gonderilmiyor"
    sensor_blogu = ana[i:j]
    assert re.search(r'"[^"]*\bI=', sensor_blogu) is None, (
        "bobin 6-7 SENSOR satiri akim alani (I=) tasiyor — o bobinlerde ACS712 YOK"
    )
    assert "sicaklik_ok" in sensor_blogu and "alan_ok" in sensor_blogu, (
        "alanlar `*_ok` ile KAPILANMIYOR -> arizada sahte 0.0 gonderilir"
    )


def test_KRITIK_AKIM_satiri_SICAKLIK_ALAN_tasimaz():
    """Bobin 1-5'te MLX sensörü YOK → akım satırı `T=`/`A=`/`B=` TAŞIMAMALI.

    MUTASYON: akım satırına `,T=%.2f` ekle → KIRMIZI. Sahadaki etki: bobin 1-5 için DB'ye
    ve PDF'e "0.0 °C ölçüldü" satırı girer (deponun tekrar eden sahte-ölçüm sınıfı).
    """
    ana = _oku(MAIN)
    i = ana.find("BOBIN 1-5 AKIM TELEMETRISI")
    assert i > 0, "akim telemetri blogu yok"
    blok = ana[i : i + 2200]
    for yasak in ("T=", "A=", "B="):
        assert re.search(r'"[^"]*\b' + yasak, blok) is None, (
            f"akim satiri '{yasak}' alani tasiyor — bobin 1-5'te o sensor YOK, "
            "olculmeyen alan gondermek 'olculdu' gibi kaydedilir"
        )
    assert "av.ok" in blok, "akim alani `ok` ile KAPILANMIYOR -> kalibrasyon arizasinda sahte 0.0"
    assert "av.doygun" in blok and "X=1" in blok, (
        "ADC doygunlugu (X=1) bildirilmiyor -> kirpilmis akim SESSIZCE doz kaydina girer"
    )


def test_KRITIK_Init_ISR_BASLAMADAN_ONCE_cagriliyor():
    """`PEMF_Sensor_Init()` adres taraması yapar (ms'ler) → 50 kHz ISR başlamadan ÖNCE."""
    kod = yorumsuz(_oku(MAIN))
    i_init = kod.find("PEMF_Sensor_Init();")
    i_tim = kod.find("Coil_TimInit();")
    assert i_init > 0, "PEMF_Sensor_Init() HIC cagrilmiyor -> sensorler kurulmaz"
    assert i_tim > 0, "Coil_TimInit() bulunamadi -> kapi BAYAT"
    assert i_init < i_tim, (
        "PEMF_Sensor_Init(), Coil_TimInit()'ten SONRA cagriliyor -> adres taramasi 50 kHz ISR "
        "kosarken yapilir ve acilista DDS jitter'i uretir"
    )


def test_KARSIT_KANIT_kapi_gercekten_olcuyor():
    """Öz-test: yorum ayıklayıcı ve desenler gerçekten ayırt ediyor mu?"""
    # Yorum icindeki yasak kelime kapiyi ALDATMAMALI
    assert "g_shadow" not in yorumsuz("/* g_shadow'a dokunmayiz */ int x;")
    assert "GPIOE" not in yorumsuz("/* GPIOE bobin 6 portu */ int x;")
    assert "GPIOE" in yorumsuz("GPIOE->BSRR = 1;"), "port deseni KODDA yakalamiyor -> kapi sahte"
    # Ama KODDAKI yasak kelime GORULMELI
    assert "g_shadow" in yorumsuz("g_shadow.coil[5].duty = 0.0f;")
    # String icindeki de gizlenmeli
    assert "HAL_Delay" not in yorumsuz('const char *s = "HAL_Delay";')
    # Butcesiz while GERCEKTEN yakalaniyor mu
    kotu = yorumsuz("while (!(SR1 & X)) { }")
    assert re.search(r"\bwhile\s*\(([^)]*)\)", kotu), "while deseni eslesmiyor -> kapi sahte"


def test_KRITIK_CIHAZ_BAZINDA_VARLIK_TESPITI():
    """Bir bus'ta YALNIZ manyetik (ya da yalnız sıcaklık) sensör olabilir.

    ⚠️ SAHİP KABLOLAMASI 2026-09-10: PB10/PB11'e (I2C2) yalnız manyetik sensör bağlanıyor.
    Bu dosyanın ilk hâli her bus'ta İKİ cihazı da varsayıyordu.

    ⚠️ İLK ANLATIMIMIN DÜZELTMESİ: "yok olan sensör her ~5 saniyede hat kurtarma tetikler ve
    çalışan sensörü sakatlar" demiştim — **YANLIŞTI**. `ardisik_hata` HAT BAŞINA tutulur ve
    BAŞARILI her işlem onu sıfırlar; manyetik okuma çalışırken sayaç 1→0 salınır ve 5'e asla
    ulaşmaz. O kablolama düzeltmeden ÖNCE de çalışıyordu (ölçüldü:
    `test_stm_sensor_kablolama_modeli.py`). Gerçek maliyet üç kalem, hepsi hijyen/teşhis:
    (1) her turda boşa giden bir I2C işlemi, (2) `i2c_hata` teşhis sayacı takılı olmayan
    cihaz için sonsuza kadar artar → gerçek arıza göstergesi olmaktan çıkar (tezgâh kabul
    kriteri "sayaç 0" idi), (3) TAMAMEN BOŞ hatta hiç başarı olmadığı için sayaç 5'e ULAŞIR
    ve boşuna kurtarma koşar.

    MUTASYON: `S_TOBJ`taki `if (h->sicaklik_adres == 0U)` erken-çıkışını sil → KIRMIZI.
    """
    kod = yorumsuz(_oku(SRC))
    assert "sicaklik_adres" in kod, "sicaklik cihazi icin VARLIK alani YOK"
    assert "cihaz_var" in kod, "adres yoklama yardimcisi YOK"
    # ⚠️ ZAYIF ÇIPA DÜZELTMESİ: bu kapının ilk hâli yalnız erken-çıkışın VAR OLDUĞUNU
    # ölçüyordu. `sicaklik_adres = MLX90614_ADRES` (yoklamasız, hep "var") mutasyonu kapıyı
    # YEŞİL bıraktı — erken-çıkış kodda duruyor ama hiç tetiklenmiyordu, yani arıza geri
    # gelmişti. Artık varlığın GERÇEKTEN yoklandığı pinli.
    # ⚠️ `=(?!=)`: `==` KARŞILAŞTIRMASINI atamadan ayır. İlk yazımda bu lookahead yoktu ve
    # desen `sicaklik_adres == 0U` koşulunu da "atama" sanıp temiz kaynakta SAHTE-KIRMIZI
    # verdi (aynı gün ADC kapısında iç-içe parantezle yaşananın kardeşi).
    # `(?:->|\.)` : YALNIZ hat yapısının alanına yapılan atamalar. `*sicaklik_adres = ...`
    # (rapor fonksiyonunun ÇIKTI parametresi) bir varlık ataması DEĞİL; ilk hâlde o da
    # yakalanıp temiz kaynakta sahte-kırmızı verdi.
    for m in re.finditer(r"(?:->|\.)sicaklik_adres\s*=(?!=)([^;]+);", kod):
        atama = m.group(1)
        if "0U" == atama.strip():
            continue  # sifirlama (kurulum) mesru
        assert "cihaz_var" in atama, (
            f"`sicaklik_adres` YOKLAMASIZ atanmis: {atama.strip()!r} — cihaz hep 'var' "
            "sayilir, erken-cikis hic tetiklenmez ve yok olan sensorun NACK'i 5 turda bir "
            "hat kurtarma tetikleyip AYNI bus'taki manyetik sensoru sakatlar"
        )
    # Yok olan cihaz her iki sicaklik durumunda da ERKEN CIKMALI (hata sayilmadan)
    for durum in ("S_TOBJ", "S_TA"):
        i = kod.find("case " + durum + ":")
        assert i > 0, f"{durum} durumu bulunamadi -> kapi BAYAT"
        pencere = kod[i : i + 400]
        assert "sicaklik_adres == 0U" in pencere, (
            f"{durum} yok olan sicaklik sensorunu ATLAMIYOR -> her turda hata sayilir -> "
            "5 turda bir hat kurtarma AYNI bus'taki manyetik sensoru sakatlar"
        )
        # Erken cikis, hata isletmeden ONCE olmali
        atla = pencere.find("sicaklik_adres == 0U")
        hata = pencere.find("i2c_hata_islet")
        assert (hata < 0) or (atla < hata), f"{durum}: atlama hata sayimindan SONRA geliyor"
    # Sonradan takilan cihaz bulunmali, ama HER TURDA aranmamali (bos START = butce israfi)
    assert "SENSOR_YENIDEN_ARAMA_TUR" in kod, "periyodik yeniden arama YOK (sonradan takilan cihaz)"
    assert re.search(r"tur_sayaci\s*%\s*SENSOR_YENIDEN_ARAMA_TUR", kod), (
        "yeniden arama periyodik DEGIL -> her turda eksik adrese bosa START atilir"
    )


def test_KRITIK_iki_sensor_TEK_BUSTA_cakismaz():
    """MLX90614 (0x5A) ve MLX90393 (0x18) farklı adresler → aynı bus'ta yaşayabilirler.

    ⚠️ İKİ BUS'IN GERÇEK SEBEBİ BU DEĞİL: iki MLX90614'ün İKİSİ DE 0x5A'da sabit olduğu
    için aynı hatta konamaz. Adresler eşitlenirse (biri yanlış yazılırsa) iki cihaz aynı
    adreste yanıt verir ve okumalar birbirine karışır — sessiz ve teşhisi zor bir arıza.
    """
    kod = _oku(SRC)
    m614 = re.search(r"#define\s+MLX90614_ADRES\s+0x([0-9A-Fa-f]+)U", kod)
    m393 = re.search(r"#define\s+MLX90393_ADRES_VARSAYILAN\s+0x([0-9A-Fa-f]+)U", kod)
    assert m614 and m393, "adres sabitleri bulunamadi -> kapi BAYAT"
    a614, a393 = int(m614.group(1), 16), int(m393.group(1), 16)
    assert a614 == 0x5A, f"MLX90614 adresi 0x{a614:02X}; fabrikada SABIT 0x5A"
    assert a393 != a614, f"iki sensor AYNI adreste (0x{a614:02X}) -> tek bus'ta cakisirlar ve okumalar karisir"
