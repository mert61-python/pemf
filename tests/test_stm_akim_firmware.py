# -*- coding: utf-8 -*-
# Author: mertaygn
"""BOBİN 1-5 AKIM ÖLÇÜMÜ (ACS712-30A + ADC1) — yapısal kapı. C bu depoda DERLENMEZ.

SAHİP KARARI 2026-09-10: bobin 1-5'e ACS712 (30 A sürümü) bağlanacak, 5 ADC kanalı açıldı.
Sensör 5 V ile besleniyor ve ⚠️ **üzerinde gerilim bölücü YOK**.

Dört iddia pinli, hepsinin arkasında ölçülmüş bir arıza ya da donanım sınırı var:

1. **SEVİYE UYUŞMAZLIĞI GÖRÜNÜR OLMALI.** ACS712-30A: 0 A → 2,50 V, 66 mV/A. STM32'nin
   ADC referansı 3,30 V, pin absolute-max 3,60 V. → **+12,1 A**'da ADC kırpar, **+16,7 A**'da
   pin absolute-maximum'u aşılır. Bölücüsüz gerçek aralık −30 A … +12 A ve unipolar sürüşte
   akım TAM POZİTİF tarafta. Kırpılmış sayı sessizce doz kaydına girerse "12 A ölçüldü" der,
   gerçek 25 A olabilir → doygunluk İŞARETLENMEK zorunda.

2. **RATİOMETRİK KALİBRASYON GERÇEKTEN KULLANILMALI.** `k = offset/2.5`, `sens = 0.066·k`.
   ⚠️ ESP'de bu hesaplanıyor ama KULLANILMIYOR: `SensorManager::_deriveSensitivity()`
   `_acsSensitivity`i doldurur, `_readCurrent()` ise sabit `0.066` ile böler
   (SensorManager.cpp:508 ↔ 520-523). ESP'de k≈1 olduğu için görünmüyordu; bir bölücü
   eklendiği an akım ORAN KADAR yanlış olurdu. Aynı hata burada TEKRARLANMAMALI.

3. **BLOKLAMAMA.** Ana döngü tıkanırsa ölü-adam watchdog'u SAHTE kopuş görüp tedavi
   ortasında TÜM bobinleri keser. `HAL_Delay` ve bütçesiz `while` yasak.

4. **ADC ÇAKIŞMASI.** Derleme-kapılı NTC bloğu AYNI beş ADC1 kanalını kuruyor. İkisi
   birden derlenirse iki okuyucu aynı çevre birimini yapılandırır → tanımsız sonuç.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
SRC = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "pemf_akim.c"
HDR = KOK / "firmware" / "stm32_pemf" / "Core" / "Inc" / "pemf_akim.h"
MAIN = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "main.c"
# ⚠️ AYNA KAPISI KALDIRILDI (2026-09-11): `stm32_pemf_unipolar` projesi silindi.
# Sebep: surus kipi artik `PEMF_BOBIN_UNIPOLAR_MASKESI` ile BOBIN BASINA seciliyor,
# ikinci bir derleme gerekmiyor. TEK kaynak = firmware/stm32_pemf.

pytestmark = pytest.mark.skipif(not SRC.exists(), reason="pemf_akim.c yok")


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


def while_kosullari(kod: str) -> list[str]:
    """Her `while (...)` için DENGELİ parantezle koşulu çıkarır.

    ⚠️ NEDEN ELLE: `re.search(r"while\s*\(([^)]*)\)")` iç içe parantezde İLK `)`de durur —
    `while (((SR & EOC) == 0U) && (butce > 0U))` koşulunu `((SR & EOC` diye kırpar ve
    "bütçe yok" der. Bu kapının ilk yazımı tam bu yüzden SAHTE-KIRMIZI verdi; karşıt-kanıt
    testi yakaladı. Yapısal çıpa kırılganlığının ders kitabı örneği.
    """
    out: list[str] = []
    i = 0
    while True:
        i = kod.find("while", i)
        if i < 0:
            return out
        j = i + 5
        while j < len(kod) and kod[j] in " \t\n":
            j += 1
        if j >= len(kod) or kod[j] != "(":
            i += 5
            continue
        derinlik, k = 0, j
        while k < len(kod):
            if kod[k] == "(":
                derinlik += 1
            elif kod[k] == ")":
                derinlik -= 1
                if derinlik == 0:
                    break
            k += 1
        out.append(kod[j + 1 : k])
        i = k + 1


def _sabit(kod: str, ad: str) -> float | None:
    m = re.search(r"#define\s+" + ad + r"\s+([0-9]+(?:\.[0-9]+)?)f?", kod)
    return float(m.group(1)) if m else None


def test_KRITIK_ACS712_30A_sabitleri_DOGRU():
    """66 mV/A ve 2,50 V — 30 A sürümünün veri sayfası değerleri.

    ⚠️ 5 A sürümü 185 mV/A, 20 A sürümü 100 mV/A. Yanlış sürüm sabiti akımı 1,5-2,8 kat
    yanlış gösterir ve bu SESSİZDİR: sayı makul görünür, doz kaydına öyle girer.
    MUTASYON: 0.066 → 0.100 (20 A sürümü) yaz → KIRMIZI.
    """
    kod = _oku(SRC)
    assert _sabit(kod, "ACS712_30A_V_PER_A") == 0.066, (
        f"hassasiyet {_sabit(kod, 'ACS712_30A_V_PER_A')} V/A; ACS712-**30A** 0.066 "
        "(5A surumu 0.185, 20A surumu 0.100 — yanlis surum akimi sessizce 1.5-2.8x kaydirir)"
    )
    assert _sabit(kod, "ACS712_NOMINAL_OFFSET_V") == 2.50, "0 A cikisi VCC/2 = 2.50 V olmali"
    assert _sabit(kod, "ADC_VREF_V") == 3.30, "ADC referansi VDDA = 3.30 V"
    assert _sabit(kod, "ADC_TAM_OLCEK") == 4095.0, "12-bit ADC tam olcek 4095"


def test_KRITIK_SEVIYE_UYUSMAZLIGI_BELGELENMIS():
    """+12,1 A tavanı ve +16,7 A pin sınırı başlıkta AÇIKÇA yazılı olmalı.

    ⚠️ Bu bir "yorum testi" değil: sayı belgede yoksa bir sonraki kişi bölücüsüz kabloya
    30 A'lık yük bağlar ve pini yakar. Sınırın kaynakta durması, kablolayanın onu
    görmesinin TEK yolu (şema deposu yok).
    """
    h = _oku(HDR)
    assert "12,1 A" in h or "12.1 A" in h, "ADC tavani (+12,1 A) baslikta belgelenmemis"
    assert "16,7 A" in h or "16.7 A" in h, "pin absolute-maximum (+16,7 A) belgelenmemis"
    assert "3,60 V" in h or "3.60 V" in h, "absolute-max gerilimi belgelenmemis"
    assert "BOLUCU" in h.upper() or "BÖLÜCÜ" in h.upper(), "bolucu durumu belgelenmemis"


def test_KRITIK_DOYGUNLUK_TESPIT_EDILIYOR():
    """Ham değer tavana dayanırsa okuma `doygun` işaretlenmeli.

    MUTASYON: `if (ham >= ADC_DOYGUNLUK_HAM)` satırını sil → KIRMIZI.
    Sahadaki etki: kırpılmış akım (ör. 12,1 A) gerçek 25 A yerine doz kaydına girer.
    """
    kod = yorumsuz(_oku(SRC))
    assert "ADC_DOYGUNLUK_HAM" in kod, "doygunluk esigi sabiti YOK"
    assert re.search(r"ham\s*>=\s*ADC_DOYGUNLUK_HAM", kod), "doygunluk KARSILASTIRILMIYOR"
    assert re.search(r"doygun\s*=\s*true", kod), "doygunluk bayragi HIC set edilmiyor"
    esik = _sabit(_oku(SRC), "ADC_DOYGUNLUK_HAM")
    assert esik is not None and 4000 <= esik <= 4095, f"doygunluk esigi anlamsiz: {esik}"


def test_KRITIK_TURETILEN_HASSASIYET_GERCEKTEN_KULLANILIYOR():
    """ESP'nin hatası (hesapla-ama-kullanma) burada TEKRARLANMAMALI.

    MUTASYON: `/ g_hassasiyet[i]` yerine `/ ACS712_30A_V_PER_A` yaz → KIRMIZI.
    Sahadaki etki: bir gerilim bölücü eklendiği an akım oran kadar (ör. 1,5x) yanlış olur
    ve bu SESSİZDİR — sayı makul görünmeye devam eder.
    """
    kod = yorumsuz(_oku(SRC))
    assert re.search(r"g_hassasiyet\[i\]\s*=\s*ACS712_30A_V_PER_A\s*\*\s*k", kod), (
        "ratiometrik hassasiyet (0.066 * k) TURETILMIYOR"
    )
    # Akim hesabi TURETILEN degeri kullanmali, nominal sabiti DEGIL.
    m = re.search(r"const float akim\s*=([^;]*);", kod)
    assert m, "akim hesabi bulunamadi -> kapi BAYAT"
    ifade = m.group(1)
    assert "g_hassasiyet[i]" in ifade, (
        f"akim hesabi TURETILEN hassasiyeti kullanmiyor: {ifade!r} — ESP'deki hesapla-ama-kullanma hatasinin aynisi"
    )
    assert "ACS712_30A_V_PER_A" not in ifade, (
        f"akim hesabi NOMINAL sabiti kullaniyor: {ifade!r} — bolucu/VCC duzeltmesi kaybolur"
    )


def test_KRITIK_RMS_ve_OFFSET_KALIBRASYONU_VAR():
    """PWM'li akım tek örnekle ölçülemez → RMS; ve offset 0 A'da kalibre edilmeli."""
    kod = yorumsuz(_oku(SRC))
    assert re.search(r"sqrtf\(kareler\s*/", kod), "RMS hesaplanmiyor (tek ornek = rastgele nokta)"
    assert "KALIBRASYON_ORNEK" in kod and "RMS_ORNEK" in kod, "ornek sayilari sihirli sayi"
    assert re.search(r"g_offset_v\[i\]\s*=\s*toplam\s*/", kod), "offset ortalamasi alinmiyor"


def test_KRITIK_Init_PWM_BASLAMADAN_ONCE():
    """Offset kalibrasyonu bobinler KAPALIYKEN yapılmalı.

    ⚠️ Akım varken kalibre edilirse o bobinin offset'i yanlış olur ve TÜM ölçümleri
    kalıcı olarak kayar — hem de makul görünen bir sayıyla.
    MUTASYON: `PEMF_Akim_Init();`i `Coil_TimInit();`ten SONRAYA taşı → KIRMIZI.
    """
    kod = yorumsuz(_oku(MAIN))
    i_init = kod.find("PEMF_Akim_Init();")
    i_tim = kod.find("Coil_TimInit();")
    assert i_init > 0, "PEMF_Akim_Init() HIC cagrilmiyor -> akim hic olculmez"
    assert i_tim > 0, "Coil_TimInit() bulunamadi -> kapi BAYAT"
    assert i_init < i_tim, (
        "PEMF_Akim_Init(), Coil_TimInit()'ten SONRA cagriliyor -> offset PWM KOSARKEN "
        "olculur ve tum akim olcumleri kalici olarak kayar"
    )


def test_KRITIK_BLOKLAMAZ():
    """`HAL_Delay` yok; her `while` çevrim bütçeli."""
    kod = yorumsuz(_oku(SRC))
    assert "HAL_Delay" not in kod, (
        "pemf_akim.c icinde HAL_Delay var — ana dongu tikanir, olu-adam watchdog'u SAHTE "
        "kopus gorup TUM bobinleri keser"
    )
    for kosul in while_kosullari(kod):
        assert "butce" in kosul, f"BUTCESIZ while: while ({kosul.strip()}) — ADC arizasinda kart KILITLENIR"
    assert "ADC_SPIN_BUTCESI" in kod, "donusum beklemesi butce sabiti tasimiyor"


def test_KRITIK_NTC_ile_ADC_CAKISMASI_DERLEME_ZAMANI_YAKALANIR():
    """NTC bloğu aynı beş ADC1 kanalını kuruyor → ikisi birden derlenemez.

    MUTASYON: `#error` satırını sil → KIRMIZI. Sahadaki etki: iki modül ADC1'i ayrı ayrı
    yapılandırır, kanal sırası birbirini ezer ve akım/sıcaklık ikisi de yanlış okunur.
    """
    kod = _oku(SRC)
    assert "#error" in kod and "PEMF_NTC_TERMAL_ENABLED" in kod, (
        "NTC ile ADC catismasi icin derleme-zamani kapisi (#error) YOK"
    )


def test_KRITIK_kanal_tablosu_NUM_ile_BAGLI():
    """Kanal listesi elle yazılı (kablolamaya özgü) → uzunluğu derleme-zamanı iddiasıyla bağlı."""
    kod = _oku(SRC)
    assert "_Static_assert" in kod and "g_kanal" in kod, "kanal tablosu uzunluk iddiasi YOK"
    i = kod.find("g_kanal[PEMF_AKIM_BOBIN_SAYISI]")
    assert i > 0, "g_kanal tanimi bulunamadi -> kapi BAYAT"
    govde = kod[kod.index("{", i) + 1 : kod.index("}", i)]
    elemanlar = [x.strip() for x in govde.split(",") if x.strip()]
    assert len(elemanlar) == 5, f"g_kanal {len(elemanlar)} eleman, 5 bobin bekleniyor"
    # NTC blogunun ayirdigi kanallarla AYNI olmali (PA0=0, PA3=3, PA4=4, PC0=10, PC3=13)
    assert [e.rstrip("U") for e in elemanlar] == ["0", "3", "4", "10", "13"], (
        f"kanal listesi {elemanlar} — beklenen PA0=0 PA3=3 PA4=4 PC0=10 PC3=13 "
        "(NTC blogunun ayirdigi pinler; kablolama buna gore)"
    )


def test_KARSIT_KANIT_kapi_gercekten_olcuyor():
    """Öz-test: yorum ayıklayıcı ve desenler gerçekten ayırt ediyor mu?"""
    assert "HAL_Delay" not in yorumsuz("/* HAL_Delay kullanmayiz */ int x;")
    assert "HAL_Delay" in yorumsuz("HAL_Delay(5);")
    # ⚠️ İÇ İÇE PARANTEZ: bu kapının ilk yazımı `[^)]*` kullanıyordu ve gerçek kodun
    # koşulunu kırpıp SAHTE-KIRMIZI veriyordu. Dengeli ayrıştırıcı doğru okumalı.
    kotu = while_kosullari(yorumsuz("while (!(ADC1->SR & ADC_SR_EOC)) { }"))
    assert kotu and "butce" not in kotu[0], f"butcesiz while ayirt EDILMIYOR: {kotu}"
    iyi = while_kosullari(yorumsuz("while (((SR & EOC) == 0U) && (butce > 0U)) { butce--; }"))
    assert iyi and "butce" in iyi[0], f"IC ICE parantezli butceli kosul KIRPILDI: {iyi}"
    assert while_kosullari("int x = 1;") == [], "while olmayan kodda kosul uretildi"
