# Author: mertaygn, cglrgrkn
"""STM DALGA SÖZLEŞMESİ — donanım-uyum denetimi HG-2 (2026-08-19): SİMETRİK BİPOLAR.

ESKİ sözleşme `state = (adj < duty) ? A : B` idi: bir bacak HEP enerjili → net ortalama
V·(2·duty−1) → duty≠%50'de bobinden sürekli tek yönlü DC (denetim HG-2: aynı duty üç bobin
ailesinde FARKLI dalga; STM'de termal kesme de olmadığından sınırsız DC ısınması). YENİ sözleşme
ESP S3/8266 ile AYNI: A=[0,duty), B=[yarım, yarım+duty), aralarda İKİSİ DE LOW → her duty'de
net DC = 0; duty = yarım-periyot doluluk oranı; klemp = yarım − DDS_BIPOLAR_GAP_TICKS(2).

Firmware C ISR'ı doğrudan koşulamaz; bu test ISR'ın Python modelini kurup dalga fiziğini
kanıtlar + C kaynağının yeni sözleşmeyi gerçekten içerdiğini yapısal olarak kilitler.
⚠️ TEZGÂH ZORUNLU: aynı duty'de teslim edilen enerji eski dalgadan farklı — doz kalibrasyonu.
"""

from __future__ import annotations

from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
MAIN = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "main.c"
GAP = 2  # DDS_BIPOLAR_GAP_TICKS — C ile aynı


def _dalga(tpp: int, duty_t: int, faz_t: int = 0):
    """Yeni ISR durum makinesinin birebir modeli → tick başına (A, B) çıkışı."""
    yarim = tpp // 2
    out = []
    for tick in range(tpp):
        adj = tick - faz_t
        if adj < 0:
            adj += tpp
        if adj < duty_t:
            out.append((1, 0))  # A darbesi
        elif yarim <= adj < yarim + duty_t:
            out.append((0, 1))  # B darbesi (ayna)
        else:
            out.append((0, 0))  # boşluk
    return out


def _klemp(tpp: int, duty_t: int) -> int:
    """C'deki duty klempi: yarım − GAP, taban 1."""
    max_d = tpp // 2 - GAP
    if max_d < 1:
        max_d = 1
    return min(duty_t, max_d)


@pytest.mark.parametrize("duty_pct", [5, 10, 25, 40, 50, 75, 99])
@pytest.mark.parametrize("tpp", [500, 5000, 50000])  # 100 Hz, 10 Hz, 1 Hz
def test_KRITIK_net_DC_SIFIR_her_dutyde(tpp, duty_pct):
    """HG-2'nin özü: A süresi == B süresi → net DC = 0 (eski dalgada yalnız duty=%50'de sıfırdı)."""
    duty_t = _klemp(tpp, int(duty_pct / 100 * tpp))
    w = _dalga(tpp, duty_t)
    a_sure = sum(a for a, _ in w)
    b_sure = sum(b for _, b in w)
    assert a_sure == b_sure, f"A={a_sure} B={b_sure} — net DC != 0 (DC-bias geri geldi)"
    assert a_sure == duty_t, "A penceresi duty_t ile eşleşmiyor"


@pytest.mark.parametrize("duty_pct", [5, 25, 50, 99])
def test_KRITIK_asla_ikisi_birden_HIGH(duty_pct):
    """Shoot-through yapısal imkânsızlığı: hiçbir tick'te A ve B aynı anda HIGH olamaz."""
    for tpp in (500, 50000):
        duty_t = _klemp(tpp, int(duty_pct / 100 * tpp))
        for faz_t in (0, tpp // 4, tpp // 2, tpp - 1):
            for a, b in _dalga(tpp, duty_t, faz_t):
                assert not (a and b), "A ve B aynı tick'te HIGH — shoot-through"


def test_KRITIK_garantili_LOW_boslugu():
    """Maks duty'de bile A bitişi ile B başlangıcı arasında ≥GAP tick her-iki-LOW kalmalı."""
    tpp = 500
    duty_t = _klemp(tpp, tpp)  # duty=%100 istendi → klemp yarım−2 = 248
    assert duty_t == tpp // 2 - GAP
    w = _dalga(tpp, duty_t)
    # A [0,248) → boşluk [248,250) → B [250,498) → boşluk [498,500)
    assert w[duty_t] == (0, 0) and w[duty_t + 1] == (0, 0), "A→B arası LOW boşluğu yok"
    assert w[tpp // 2] == (0, 1), "B yarımda başlamıyor"
    assert w[tpp - 1] == (0, 0), "B→A (sarmal) arası LOW boşluğu yok"


def test_KRITIK_S3_ile_ayni_anlam():
    """Duty>%50 klempi S3 ile birebir: %75 isteği → yarım−GAP (S3: duty_t ≤ yarim−DEAD_TIME)."""
    tpp = 500
    assert _klemp(tpp, int(0.75 * tpp)) == 248  # S3: constrain sonrası aynı üst sınır
    assert _klemp(tpp, int(0.25 * tpp)) == 125  # %50 altı: birebir doğrusal (S3 ile aynı)


def test_KRITIK_faz_ofseti_pencereyi_KAYDIRIR():
    """Faz ofseti dalgayı döndürür; A-B simetrisi (net DC=0) korunur."""
    tpp, duty_t, faz = 500, 100, 125  # 90°
    w = _dalga(tpp, duty_t, faz)
    assert w[faz] == (1, 0), "A penceresi faz ofsetinde başlamıyor"
    assert sum(a for a, _ in w) == sum(b for _, b in w) == duty_t


def test_ESKI_sozlesme_DC_uretiyordu_capa():
    """Çapa: eski `(adj<duty)?A:B` modeli duty=%25'te net DC=−%50·V üretir — değişimin nedeni."""
    tpp, duty_t = 500, 125
    eski = [(1, 0) if t < duty_t else (0, 1) for t in range(tpp)]
    a, b = sum(x for x, _ in eski), sum(y for _, y in eski)
    assert (a - b) / tpp == pytest.approx(-0.5), "çapa bozuldu — eski dalga tanımı değişti mi?"


def test_KARSIT_KANIT_C_kaynagi_yeni_sozlesmeyi_ICERIR():
    src = MAIN.read_text(encoding="utf-8", errors="replace")
    # yeni durum makinesi + sabit
    assert "DDS_BIPOLAR_GAP_TICKS" in src
    assert "yarim + duty" in src.replace("(", " ").replace(")", " "), "B penceresi [yarım, yarım+duty) yok"
    assert 'state = 3U; /* boşluk' in src or "state = 3U" in src, "LOW-boşluk durumu (3) yok"
    # ESKİ tek satırlık tümleyen sözleşme GERİ GELMEMELİ
    assert "state = (adj < duty) ? 1U : 0U" not in src, (
        "ESKİ 'bir bacak hep enerjili' sözleşmesi geri geldi → duty!=%50'de DC-bias"
    )
    # klempler yarım-periyot tabanlı
    assert src.count("/ 2U) - DDS_BIPOLAR_GAP_TICKS") >= 2, "iki klemp de yarım-tabanlı değil"
    # sürüm izi
    assert "SYM-BIPOLAR" in src, "STM_READY sürüm dizesi dalga değişimini yansıtmıyor"


def test_KARSIT_KANIT_NTC_termal_blok_HAZIR_ve_KAPALI():
    """HG-1: NTC kesme kodu TAM ve derleme-kapılı (donanım yokken davranış birebir eski)."""
    src = MAIN.read_text(encoding="utf-8", errors="replace")
    assert "#define PEMF_NTC_TERMAL_ENABLED 0" in src, (
        "NTC ya silinmiş ya da donanımsız AÇIK bırakılmış (0 olmalı — NTC bağlanınca 1)"
    )
    for parca in ("NTC_KESME_C 48.0f", "NTC_DONUS_C 45.0f", "Coil_NtcTermalPoll", "Coil_NtcAdcInit", "g_ntc_kilit"):
        assert parca in src, f"NTC bloğu eksik: {parca}"
    # kesme, süre-bitimi kalıbını kullanmalı (shadow + pending, IRQ-korumalı)
    i = src.index("Coil_NtcTermalPoll")
    blok = src[i : i + 3000]
    assert "g_shadow.coil[i].duty = 0.0f" in blok and "__disable_irq" in blok, (
        "NTC kesmesi güvenli kanal (shadow+pending+IRQ) kullanmıyor"
    )
