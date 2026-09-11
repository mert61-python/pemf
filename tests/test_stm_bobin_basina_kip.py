# -*- coding: utf-8 -*-
# Author: mertaygn
"""BOBİN BAŞINA SÜRÜŞ KİPİ — shoot-through ve kip karışması kapısı.

===============================================================================
SAHİP DONANIM BİLGİSİ 2026-09-11
===============================================================================
  bobin 1-5 : TAM KÖPRÜ sürücü  → bipolar DA unipolar DA sürülebilir
  bobin 6-7 : TEK YÖNLÜ sürücü  → YALNIZ unipolar (sağ/sol duvar)
Amaç: **maksimum dB/dt** (tepe alan DEĞİL). Gerçek bipolar sürüşte alan `−B → +B`
salınır → kenar başına ΔB iki katı, periyot başına 4 kenar (unipolarda 2).

Tek bir derleme-zamanı `PEMF_SURUS_UNIPOLAR` bayrağı "5 bipolar + 2 unipolar"ı ifade
edemediği için kip `PEMF_BOBIN_UNIPOLAR_MASKESI`ne taşındı.

===============================================================================
⚠️⚠️ KAPININ KORUDUĞU ASIL TEHLİKE: SHOOT-THROUGH
===============================================================================
Bipolar bir bobinde pencereler A=[0,duty) ve B=[yarım, yarım+duty)'dir. `duty` yarım
periyodu aşarsa pencereler ÇAKIŞIR → iki bacak AYNI ANDA HIGH → tam köprüde kaynak ile
toprak arasında kısa devre → SÜRÜCÜ YANAR.

Buna karşı tek koruma duty klempidir. Klemp ile çıkış aşaması **AYNI** kip kaynağını
(`g_unipolar[i]`) okumak ZORUNDA. Ayrışırlarsa (ör. klemp bobini unipolar sanıp tavanı
`tpp−1` verir ama çıkış aşaması bipolar dalga üretir) doğrudan shoot-through olur.
Bu dosya o eşleşmeyi hem YAPISAL hem MODEL üzerinden ölçer.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
MAIN = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "main.c"
SURUS = KOK / "firmware" / "stm32_pemf" / "Core" / "Inc" / "pemf_surus.h"
SURUS_UNI = KOK / "firmware" / "stm32_pemf_unipolar" / "Core" / "Inc" / "pemf_surus.h"

pytestmark = pytest.mark.skipif(not MAIN.exists(), reason="firmware kaynagi yok")


def _oku(p: Path) -> str:
    return io.open(p, encoding="utf-8", errors="replace").read()


def _maske(p: Path) -> int:
    m = re.search(r"#define\s+PEMF_BOBIN_UNIPOLAR_MASKESI\s+0x([0-9A-Fa-f]+)U?", _oku(p))
    assert m, f"{p.name}: PEMF_BOBIN_UNIPOLAR_MASKESI YOK"
    return int(m.group(1), 16)


def _num_coils() -> int:
    m = re.search(r"#define\s+NUM_COILS\s+(\d+)", _oku(MAIN))
    assert m
    return int(m.group(1))


# ============================================================================
# 1. YAPILANDIRMA — donanımın dayattığı kip
# ============================================================================


def test_KRITIK_saha_projesinde_bobin_6_7_UNIPOLAR_digerleri_BIPOLAR():
    """Sürücü donanımı böyle: 6-7 tek yönlü, 1-5 tam köprü.

    MUTASYON: maskeyi 0x00 yap → KIRMIZI (bobin 6-7 bipolar sürülmeye çalışılır;
    sürücüleri bunu yapamaz).
    """
    n = _num_coils()
    m = _maske(SURUS)
    uni = [bool((m >> i) & 1) for i in range(n)]
    assert uni == [False, False, False, False, False, True, True], (
        f"saha maskesi 0x{m:02X} yanlis -> bobin kipleri {uni}; "
        "beklenen: 1-5 BIPOLAR (tam kopru), 6-7 UNIPOLAR (tek yonlu surucu)"
    )


def test_KRITIK_karsilastirma_projesi_HEPSI_unipolar():
    """`stm32_pemf_unipolar` geri-dönüş/karşılaştırma yapısı olarak kalır."""
    n = _num_coils()
    m = _maske(SURUS_UNI)
    assert m == (1 << n) - 1, f"karsilastirma projesi maskesi 0x{m:02X} != hepsi-unipolar"


# ============================================================================
# 2. ⚠️ SHOOT-THROUGH — klemp ile çıkış AYNI kaynağı okumalı
# ============================================================================


def test_KRITIK_duty_klempi_ve_CIKIS_asamasi_AYNI_kaynagi_okur():
    """⚠️ Ayrışırlarsa bipolar bobin yarım-periyottan uzun duty alır → İKİ BACAK AYNI ANDA HIGH.

    MUTASYON: klemplerden birini `g_unipolar[i]` yerine sabit `1` yap → KIRMIZI.
    """
    kod = _oku(MAIN)
    # iki klemp + cikis asamasi: ucu de g_unipolar[i] okumali
    klempler = re.findall(r"int32_t\s+max_d(?:_now)?\s*=\s*([^;]+);", kod, re.S)
    assert len(klempler) == 2, f"beklenen 2 duty klempi, bulunan {len(klempler)} -> kapi BAYAT"
    for k in klempler:
        assert "g_unipolar[i]" in k, (
            f"duty klempi kip dizisini OKUMUYOR: {k.strip()[:80]!r} -> "
            "bipolar bobinde tavan yanlis olur ve SHOOT-THROUGH riski dogar"
        )

    m = re.search(r"uint8_t state;\s*\n\s*if \(g_unipolar\[i\]\)", kod)
    assert m, "cikis asamasi kipi `g_unipolar[i]` ile secmiyor"


def test_KRITIK_kip_DERLEME_ZAMANI_dallanmasi_KALMADI():
    """`#if PEMF_SURUS_UNIPOLAR` sürüş yolunda kalırsa maske ETKİSİZ olur."""
    kod = _oku(MAIN)
    kalan = [ln for ln in kod.splitlines() if "#if PEMF_SURUS_UNIPOLAR" in ln]
    assert not kalan, f"surus yolunda hala derleme-zamani dal var ({len(kalan)}) -> maske ETKISIZ"


def test_KRITIK_kip_dizisi_MASKEDEN_turetilir():
    """Dizi elle doldurulursa maske yalan söyler."""
    kod = _oku(MAIN)
    m = re.search(r"g_unipolar\[i\]\s*=\s*([^;]+);", kod)
    assert m, "g_unipolar dizisi HIC doldurulmuyor"
    assert "PEMF_BOBIN_UNIPOLAR_MASKESI" in m.group(1), f"kip dizisi maskeden TURETILMIYOR: {m.group(1).strip()!r}"


# ============================================================================
# 3. DALGA MODELİ — çakışma fiziksel olarak imkânsız mı
# ============================================================================


def _dalga(unipolar: bool, tpp: int, duty_istenen: int, gap: int = 2):
    """ISR çıkış aşamasının birebir modeli. @return (A_tick, B_tick) listeleri."""
    max_d = (tpp - 1) if unipolar else (tpp // 2 - gap)
    if max_d < 1:
        max_d = 1
    duty = min(duty_istenen, max_d)
    a, b = [], []
    yarim = tpp // 2
    for adj in range(tpp):
        if unipolar:
            st = 1 if adj < duty else 3
        else:
            if adj < duty:
                st = 1
            elif yarim <= adj < (yarim + duty):
                st = 0
            else:
                st = 3
        a.append(st == 1)
        b.append(st == 0)
    return a, b


def test_KRITIK_BIPOLAR_bobinde_iki_bacak_ASLA_ayni_anda_HIGH():
    """⚠️ Klemp doğru uygulanırsa çakışma YAPISAL OLARAK imkânsızdır.

    MUTASYON: modeldeki `max_d` hesabında bipolar dalını `tpp - 1` yap → KIRMIZI
    (gerçek kodda bu, sürücünün yanması demektir).
    """
    for tpp in (10, 50, 500, 5000):
        for istenen in (1, tpp // 4, tpp // 2, tpp - 1, tpp * 2):
            a, b = _dalga(False, tpp, istenen)
            cakisma = [i for i, (x, y) in enumerate(zip(a, b)) if x and y]
            assert not cakisma, (
                f"tpp={tpp} duty={istenen}: A ve B {len(cakisma)} tick boyunca AYNI ANDA HIGH "
                "-> SHOOT-THROUGH (surucu yanar)"
            )


def test_KRITIK_UNIPOLAR_bobinde_B_bacagi_HIC_HIGH_olmaz():
    """Bobin 6-7'nin sürücüsü tek yönlü — B'yi sürmek tanımsız davranıştır."""
    for tpp in (10, 500, 5000):
        for istenen in (1, tpp // 2, tpp - 1, tpp * 2):
            _a, b = _dalga(True, tpp, istenen)
            assert not any(b), f"tpp={tpp} duty={istenen}: UNIPOLAR bobinde B bacagi HIGH oldu"


def test_KRITIK_BIPOLAR_periyot_basina_4_KENAR_uretir():
    """dB/dt kazancının kaynağı: bipolar 4 kenar, unipolar 2.

    ⚠️ Bu, sahibin amacının (maks dB/dt) sayısal karşılığıdır. Bipolar dalga
    `−B → +B` salındığı için kenar başına ΔB de iki katıdır.
    """
    tpp = 500
    duty = tpp // 4  # %25 — klempin altinda, iki kipte de uygulanir

    def kenar_sayisi(seri):
        return sum(1 for i in range(len(seri)) if seri[i] != seri[i - 1])

    a_uni, b_uni = _dalga(True, tpp, duty)
    a_bi, b_bi = _dalga(False, tpp, duty)

    uni_kenar = kenar_sayisi(a_uni) + kenar_sayisi(b_uni)
    bi_kenar = kenar_sayisi(a_bi) + kenar_sayisi(b_bi)

    assert uni_kenar == 2, f"unipolar periyot basina {uni_kenar} kenar (2 bekleniyordu)"
    assert bi_kenar == 4, f"bipolar periyot basina {bi_kenar} kenar (4 bekleniyordu)"


def test_KRITIK_IN_A_penceresi_IKI_KIPTE_de_AYNI():
    """⚠️ IN_B kablosu ÇEKİLMEDEN bipolara geçmek alanı DEĞİŞTİRMEZ (zararsız ama etkisiz).

    Bu, sahibe "önce kabloyu çek" diyebilmemizin dayanağı: IN_A penceresi özdeş
    olduğu için, IN_B bağlanana kadar bipolar kip bugünküyle aynı alanı üretir.
    Duty klempin altında kaldığı sürece (sahip zaten ≤%50 veriyor) fark YOKTUR.
    """
    tpp = 500
    duty = tpp // 4  # %25 — bipolar klempi (tpp/2-2 = 248) BAGLAYICI DEGIL
    a_uni, _ = _dalga(True, tpp, duty)
    a_bi, _ = _dalga(False, tpp, duty)
    assert a_uni == a_bi, "IN_A penceresi iki kipte AYRISTI -> 'kablo cekilene kadar ayni' iddiasi YANLIS"
