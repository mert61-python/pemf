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
AYNA_SRC = KOK / "firmware" / "stm32_pemf_unipolar" / "Core" / "Src" / "pemf_sensor.c"

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
    """MLX90393'ün ~17 ms dönüşümü bir bekleme DEĞİL, bir zaman damgası olmalı."""
    kod = yorumsuz(_oku(SRC))
    assert "mag_hazir_ms" in kod and "S_MAG_BEKLE" in kod, (
        "donusum bekleme durumu yok — 17 ms bir yerde BLOKLAYARAK bekleniyor olabilir"
    )
    assert re.search(r"S_MAG_BEKLE[^}]*simdi_ms\s*-\s*.*mag_hazir_ms", kod, re.S), (
        "S_MAG_BEKLE durumu zaman damgasini KARSILASTIRMIYOR"
    )


def test_KRITIK_olcek_sabitleri_ADAFRUIT_TABLOSU_ile_AYNI():
    """0.150 / 0.242 µT/LSB — ESP'nin bugün ürettiği sayının kaynağı.

    Kaynak: Adafruit_MLX90393.h `mlx90393_lsb_lookup[0][7][0] = {0.150, 0.242}`
    (HALLCONF 0xC · GAIN_SEL 7 = 1x · RES_16). ESP ayarları: SensorManager.cpp:284-288.

    MUTASYON: 0.150'yi 0.161 yap → KIRMIZI. Sahadaki etki: alan sayıları geçmiş kayıtlarla
    KIYASLANAMAZ olur ve E-alanı barı/doz raporu sessizce kayar.
    """
    kod = _oku(SRC)
    xy = re.search(r"#define\s+MLX90393_LSB_XY_UT\s+([0-9.]+)f", kod)
    z = re.search(r"#define\s+MLX90393_LSB_Z_UT\s+([0-9.]+)f", kod)
    assert xy and z, "olcek sabitleri bulunamadi -> kapi BAYAT"
    assert float(xy.group(1)) == 0.150, (
        f"XY olcegi {xy.group(1)}, Adafruit tablosu 0.150 (GAIN_SEL=7, RES_16). Degistirmek "
        "ESP'nin urettigi sayiyla kiyaslanabilirligi BOZAR."
    )
    assert float(z.group(1)) == 0.242, f"Z olcegi {z.group(1)}, tablo 0.242"
    # Ayar sabitleri de ESP ile ayni olmali (olcek ancak bu ayarlarda gecerli)
    for ad, beklenen in (("MLX90393_GAIN_SEL", "7"), ("MLX90393_OSR", "3"), ("MLX90393_DIG_FILT", "1")):
        m = re.search(r"#define\s+" + ad + r"\s+(\d+)U?", kod)
        assert m and m.group(1) == beklenen, (
            f"{ad} = {m.group(1) if m else None}, ESP'de {beklenen} — olcek tablosu YALNIZ "
            "bu ayarlarda gecerlidir, ayar degisince 0.150/0.242 YANLIS olur"
        )


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


def test_ayna_senkron():
    """Unipolar projedeki kopya bayt-bayt aynı olmalı (elle düzenleme yasağı)."""
    if not AYNA_SRC.exists():
        pytest.skip("ayna projesi yok")
    assert _oku(AYNA_SRC) == _oku(SRC), "pemf_sensor.c ayna ile AYRISMIS -> python scripts/stm_unipolar_senkronla.py"


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
