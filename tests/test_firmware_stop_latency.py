# Author: mertaygn, cglrgrkn
"""DENETİM P0 (fw-duty-slew-stop-delay) + P1 (fw-no-iwdg-no-fault-safe) regresyonu.

MUTASYON TESTİ BULGUSU: bu iki firmware düzeltmesinin HİÇ testi yoktu. P0 olanı doğrudan
hasta güvenliğidir — canlı hayvan üzerinde STOP komutu geçerken bobin enerjili kalıyordu.

HATA
    Duty slew-rate sınırlayıcı `DDS_MAX_DUTY_SLEW = 25` sabitiyle ve PERİYOT BAŞINA
    uygulanıyordu. 100 Hz'de bir periyot 10 ms → tam ölçek ~0,2 s. Ama AI Pro 1 Hz'de
    sürer: periyot 1 s, tam ölçek 500 tick / 25 = 20 periyot = **20 saniye**; üstelik
    `g_duty_ticks` yalnız periyot başında güncellendiğinden çıkış bir periyot daha
    gecikiyordu. Yani acil durdurma / süre-bitişi / ölü-adam watchdog'u sonrası bobin
    onlarca saniye enerjili kalabiliyordu.

DÜZELTME (iki parça, ikisi de gerekli)
    1) slew = tpp / (f · DDS_SLEW_FULLSCALE_S) → rampa SÜRESİ frekanstan bağımsız.
    2) Hedef 0 ise rampa ATLANIR ve çıkış katmanı da hedefe bakar → STOP gecikmesi
       periyottan bağımsız olarak en fazla BİR ISR tick'i (20 µs).

Bu dosya firmware sabitlerini `firmware/main.c`'den OKUR (kopyalamaz) ve DDS duty
mantığını Python'da birebir modelleyerek davranışı ölçer. Böylece sabitler değişirse
test onlarla birlikte hareket eder, ama DAVRANIŞ bozulursa düşer.
"""

import re
from pathlib import Path

import pytest

FW = Path(__file__).resolve().parent.parent / "firmware" / "main.c"


@pytest.fixture(scope="module")
def src():
    assert FW.exists(), f"firmware kaynağı yok: {FW}"
    return FW.read_text(encoding="utf-8", errors="replace")


def _sabit(src, ad):
    """`#define AD <sayı>` değerini oku (satır devamı `\\` ve yorumlarla birlikte)."""
    m = re.search(rf"#define\s+{ad}\s*(?:\\\s*\n)?\s*([0-9]*\.?[0-9]+)[fFuU]?", src)
    assert m, f"{ad} firmware'de bulunamadı"
    return float(m.group(1))


# ────────────────────────── Sabitler ve formül ──────────────────────────


def test_slew_formulu_FREKANSTAN_BAGIMSIZ(src):
    """Kaynakta slew, periyoda ve frekansa göre ÖLÇEKLENMELİ — sabit kalmamalı."""
    assert "DDS_SLEW_FULLSCALE_S" in src, "frekanstan bağımsız rampa sabiti YOK → slew yine sabit tick olabilir"
    m = re.search(r"slew_f\s*=\s*tpp_f\s*/\s*\(\s*f\s*\*\s*DDS_SLEW_FULLSCALE_S\s*\)", src)
    assert m, (
        "slew hesabı `tpp / (f * DDS_SLEW_FULLSCALE_S)` biçiminde değil → "
        "rampa süresi frekansa bağımlı hale gelmiş olabilir"
    )


def test_STOP_rampayi_ATLIYOR_kaynakta(src):
    """Aşağıdaki sayısal model STOP-bypass'ı Python'da yeniden yazar; bu yüzden kaynaktaki
    bypass silinse model yine geçerdi. O boşluğu burada kapatıyoruz: İKİ bypass da main.c'de
    GERÇEKTEN duruyor mu?

    Parça-1 (rampa güncelleme): hedef ≤ 0 → duty ANINDA 0, slew uygulanmaz.
    Parça-2 (çıkış katmanı): her ISR tick'i HEDEFE bakar → periyot sonunu beklemez.
    İkisinden biri düşerse STOP yine periyoda/rampaya takılır.
    """
    parca1 = re.search(r"if\s*\(\s*g_target_duty_ticks\[i\]\s*<=\s*0\s*\)\s*\{\s*g_duty_ticks\[i\]\s*=\s*0\s*;", src)
    assert parca1, (
        "rampa güncellemesinde STOP kısayolu YOK → sıfır hedef de slew'e takılır "
        "(1 Hz'de bobin onlarca saniye enerjili kalır)"
    )

    parca2 = re.search(r"duty\s*=\s*\(\s*g_target_duty_ticks\[i\]\s*<=\s*0\s*\)\s*\?\s*0\s*:\s*g_duty_ticks\[i\]", src)
    assert parca2, (
        "çıkış katmanı hedefe BAKMIYOR → duty yalnız periyot başında güncellendiği "
        "için STOP bir periyot (1 Hz'de 1 s) gecikir"
    )


def test_100Hz_de_eski_sabitle_AYNI_kaliyor(src):
    """Geriye uyum: düzeltme 100 Hz'deki yerleşik davranışı DEĞİŞTİRMEMELİ.
    500 / (100 · 0,2) = 25 = DDS_MAX_DUTY_SLEW."""
    fullscale = _sabit(src, "DDS_SLEW_FULLSCALE_S")
    eski = _sabit(src, "DDS_MAX_DUTY_SLEW")
    isr_hz = _sabit(src, "DDS_ISR_HZ")
    tpp_100 = isr_hz / 100.0
    assert tpp_100 / (100.0 * fullscale) == pytest.approx(eski), (
        "100 Hz'de yeni formül eski sabitten farklı çıkıyor → sahada davranış değişir"
    )


# ────────────────────────── Davranış modeli ──────────────────────────


def _duty_modeli(src):
    """firmware'deki duty güncelleme + çıkış katmanını birebir modelle."""
    isr_hz = _sabit(src, "DDS_ISR_HZ")
    fullscale = _sabit(src, "DDS_SLEW_FULLSCALE_S")

    def kos(freq_hz, hedef_duty_ticks, baslangic, tick_sayisi, stop_tickinde=None):
        """Returns: çıkışın LOW olduğu ilk tick (yoksa None) ve duty izi."""
        tpp = int(isr_hz / freq_hz)
        slew = max(1, int(tpp / (freq_hz * fullscale)))
        duty = baslangic
        hedef = hedef_duty_ticks
        low_tick = None
        for t in range(tick_sayisi):
            if stop_tickinde is not None and t == stop_tickinde:
                hedef = 0  # acil durdurma / süre-bitişi / watchdog
            # ── periyot başında rampa güncellenir (firmware: period_reset) ──
            if t % tpp == 0:
                if hedef <= 0:
                    duty = 0  # DENETİM P0 parça-1: STOP rampaya tabi değil
                else:
                    err = max(-slew, min(slew, hedef - duty))
                    duty = max(0, duty + err)
            # ── çıkış katmanı HER tick'te hedefe bakar (DENETİM P0 parça-2) ──
            cikis = 0 if hedef <= 0 else duty
            if stop_tickinde is not None and t >= stop_tickinde and cikis <= 0 and low_tick is None:
                low_tick = t
        return low_tick, duty

    return kos, isr_hz


@pytest.mark.parametrize("freq", [1.0, 2.0, 10.0, 50.0, 100.0])
def test_STOP_gecikmesi_TEK_ISR_TICKI_her_frekansta(src, freq):
    """HASTA GÜVENLİĞİ: hedef sıfırlandıktan sonra çıkış en fazla 1 ISR tick'te LOW olmalı.
    Eski davranışta 1 Hz'de bu on saniyeler sürüyordu."""
    kos, isr_hz = _duty_modeli(src)
    tpp = int(isr_hz / freq)
    # Bobin tam güçte çalışıyorken periyodun ORTASINDA durdur (en kötü an: periyot sonu uzak)
    stop_at = tpp * 3 + tpp // 2
    low_tick, _ = kos(
        freq, hedef_duty_ticks=tpp // 2, baslangic=tpp // 2, tick_sayisi=stop_at + tpp * 3, stop_tickinde=stop_at
    )

    assert low_tick is not None, f"{freq} Hz: STOP sonrası çıkış hiç LOW olmadı"
    gecikme_tick = low_tick - stop_at
    gecikme_us = gecikme_tick * (1e6 / isr_hz)
    assert gecikme_tick <= 1, (
        f"{freq} Hz: STOP → çıkış-LOW {gecikme_tick} tick ({gecikme_us:.0f} µs) sürdü; "
        f"en fazla 1 tick (20 µs) olmalı — bobin canlı hayvan üzerinde enerjili kalır"
    )


@pytest.mark.parametrize("freq", [1.0, 10.0, 100.0])
def test_rampa_SURESI_frekanstan_bagimsiz(src, freq):
    """Rampanın ENERJİYİ ARTIRAN yönü hâlâ sınırlı (inrush/EMI) ama süresi sabit ~0,2 s.
    Eski davranışta 1 Hz'de tam ölçek 20 s sürüyordu."""
    kos, isr_hz = _duty_modeli(src)
    fullscale = _sabit(src, "DDS_SLEW_FULLSCALE_S")
    tpp = int(isr_hz / freq)
    hedef = tpp // 2  # %50 duty
    tam_olcek_tick = int(isr_hz * fullscale * 2)  # bolca pay

    _, duty = kos(freq, hedef_duty_ticks=hedef, baslangic=0, tick_sayisi=tam_olcek_tick)
    assert duty == hedef, (
        f"{freq} Hz: hedef duty {fullscale * 2:.1f} s içinde tutturulamadı "
        f"({duty}/{hedef}) → rampa süresi frekansa bağımlı kalmış"
    )


def test_rampa_hala_SINIRLI_ani_sicrama_yok(src):
    """Düzeltme rampayı tümden kaldırmamalı: enerjiyi ARTIRAN yön hâlâ kademeli olmalı
    (inrush/EMI koruması). Yoksa 'STOP'u hızlandıralım' derken koruma silinmiş olur."""
    kos, isr_hz = _duty_modeli(src)
    tpp = int(isr_hz / 100.0)
    hedef = tpp // 2
    _, duty = kos(100.0, hedef_duty_ticks=hedef, baslangic=0, tick_sayisi=1)
    assert duty < hedef, "duty tek tick'te hedefe fırladı → slew koruması kalkmış"


# ────────────────────────── Fault güvenliği (P1) ──────────────────────────


def test_hata_yolunda_bobinler_ONCE_kesiliyor(src):
    """DENETİM P1: Error_Handler bobinleri kesmeden kesmeleri kapatırsa (veya hiç kesmezse)
    bobinler son duty'de KİLİTLİ kalır — hata göstergesi hasta güvenliğinden önce gelemez."""
    m = re.search(r"void\s+Error_Handler\s*\(\s*void\s*\)\s*\{(.*?)\n\}", src, re.S)
    assert m, "Error_Handler bulunamadı"
    govde = m.group(1)
    assert "PEMF_ForceAllCoilOutputsLow" in govde, (
        "Error_Handler bobinleri KESMİYOR → hata anında bobinler enerjili kilitlenir"
    )
    kes = govde.index("PEMF_ForceAllCoilOutputsLow")
    irq = govde.find("__disable_irq")
    assert irq == -1 or kes < irq, "Error_Handler kesmeleri bobinleri kesmeden ÖNCE kapatıyor"


def test_bobin_kesme_fonksiyonu_DISA_ACIK(src):
    """Fault işleyicileri `stm32f4xx_it.c`'de (bu depoda YOK) tanımlı; oradan çağrılabilmesi
    için fonksiyon static OLMAMALI. static yapılırsa yama sessizce derlenmez hale gelir."""
    m = re.search(r"^\s*(static\s+)?void\s+PEMF_ForceAllCoilOutputsLow\s*\(\s*void\s*\)\s*\{", src, re.M)
    assert m, "PEMF_ForceAllCoilOutputsLow tanımı bulunamadı"
    assert not m.group(1), "PEMF_ForceAllCoilOutputsLow static → stm32f4xx_it.c'deki fault yaması bağlanamaz"
    assert re.search(r"^void\s+PEMF_ForceAllCoilOutputsLow\s*\(\s*void\s*\)\s*;", src, re.M), (
        "dışa açık bildirim (prototip) yok"
    )


def test_fault_yamasi_BELGELENMIS(src):
    """Yama elle uygulanmak zorunda (depo stm32f4xx_it.c tutmuyor) → talimatın varlığı
    testle korunmalı; yoksa kurulum sırasında sessizce atlanır."""
    readme = FW.parent / "README.md"
    assert readme.exists(), "firmware/README.md yok"
    metin = readme.read_text(encoding="utf-8", errors="replace")
    assert "stm32f4xx_it.c" in metin and "PEMF_ForceAllCoilOutputsLow" in metin, (
        "fault işleyici yama talimatı README'de yok → adım sessizce atlanır"
    )
    assert "stm32f4xx_it.c" in src, "main.c yamanın nereye uygulanacağını belirtmiyor"
