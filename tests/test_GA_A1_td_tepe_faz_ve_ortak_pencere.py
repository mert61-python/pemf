# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GA (istem 53) A1 — Kontrol sekmesinin VERDİĞİ fazla tepe |B| + farklı frekanslarda ortak pencere + hızlı (Gram) hesap.

SÖZLEŞME:
  - `td_dalga_faz(duty, faz)`: faz = GECİKME (firmware ortak tik: `adj = (tick − faz_ofseti) mod periyot`). Çift yönlü bobinde 180° = ters
    yön, tek yönlüde yarım periyot kayması. Genlik / biçim `_td_dalga` ile AYNI (duty [0, 0,5]'e kırpılır).
  - Y280 fazlarıyla (`fazlar(sd)`) `td_tepe_faz(M, |sd|, faz)` ≡ `td_tepe(M, sd)` (ODAK'ın tanımı — iki yol aynı fiziği hesaplar).
  - Farklı frekanslar: tepe ORTAK PENCEREDE (1 / ebob(f), 0,1 Hz çözünürlük, ≤ 10 s) `ORTAK_PENCERE_ORNEK` (asal) eşit adımla aranır;
    tek frekansta periyot örnekleri AYNEN (S = Nt). İnce örneklemeye göre fark ölçüldü (GA.md "Ortak pencere").
  - `gram` / `gram_tepe` `td_tepe_dalga` ile aynı sonucu verir (float32; göreli < 1e-5).
Sentetik tablo (CI'da da koşar)."""

from __future__ import annotations

import canli_alan_aparati as ap
import numpy as np
import pytest

P = np.array(
    [
        [0.0, -160.0, 0.0],
        [120.0, -100.0, -80.0],
        [-200.0, 0.0, 150.0],
        [50.0, 120.0, 60.0],
        [-260.0, 160.0, -190.0],
        [0, 0, 0],
    ]
)


@pytest.fixture(scope="module")
def A():
    return ap.model()


@pytest.fixture(scope="module")
def A107():
    return ap.model(107.0)


@pytest.fixture(scope="module")
def M(A):
    return A.alan(P)


def test_KRITIK_GA_A1_Y280_fazlariyla_td_tepe_faz_ODAKIN_td_tepesiyle_AYNI(A, M):
    for sd in (
        np.full(7, 0.5),
        np.array([0.1, 0.33, 0.27, 0.0, 0.45, 0.2, 0.05]),
        0.5 * np.array([-1, 1, -1, -1, 1, 1, 1.0]),
    ):
        faz = A.fazlar(sd)
        beklenen = A.td_tepe(M, sd)
        olan = A.td_tepe_faz(M, np.abs(sd), faz)
        # pozitif duty'de yalnız yuvarlama farkı; ters (negatif) bipolar bobinde td_tepe işareti çevirir, td_dalga_faz yarım periyot kaydırır
        # (kararlı bipolar dalga yarım periyotta TAM ters — 12 periyot RL benzetimi: fark < 1e-3 göreli)
        assert np.allclose(olan, beklenen, rtol=1e-3, atol=1e-6), (sd, olan, beklenen)


def test_KRITIK_GA_A1_faz_GECIKME_bipolar_180_TERS_tek_yonlu_YARIM_PERIYOT(A):
    d = np.array([0.3, 0.2, 0.4, 0.1, 0.25, 0.35, 0.15])
    W0 = A.td_dalga_faz(d, np.zeros(7))
    Nt = W0.shape[1]
    W180 = A.td_dalga_faz(d, np.full(7, 180.0))
    for c in range(5):  # bobin 1–5 çift yönlü
        assert np.allclose(W180[c], -W0[c], atol=2e-3 * np.abs(W0[c]).max()), c
    for c in (5, 6):  # bobin 6–7 tek yönlü: ters işaret YOK, yarım periyot kayar
        assert np.array_equal(W180[c], np.roll(W0[c], Nt // 2))
        assert W180[c].min() >= 0.0
    # 90° = çeyrek periyot GECİKME (np.roll ileri): W90(t) = W0(t − T/4)
    W90 = A.td_dalga_faz(d, np.full(7, 90.0))
    assert np.array_equal(W90, np.stack([np.roll(W0[c], Nt // 4) for c in range(7)]))
    # faz mod 360: 360 ≡ 0, −90 ≡ 270, 450 ≡ 90
    assert np.array_equal(A.td_dalga_faz(d, np.full(7, 360.0)), W0)
    assert np.array_equal(A.td_dalga_faz(d, np.full(7, -90.0)), A.td_dalga_faz(d, np.full(7, 270.0)))
    assert np.array_equal(A.td_dalga_faz(d, np.full(7, 450.0)), W90)


def test_KRITIK_GA_A1_duty_KIRPMA_sifir_KAPALI_negatif_KAPALI_ust_0_5(A):
    W = A.td_dalga_faz(np.array([0.0, -0.2, 0.9, 0.5, 0.3, 0.0, 1.0]), np.zeros(7))
    assert not W[0].any() and not W[1].any() and not W[5].any()
    assert np.array_equal(W[2], W[3])  # 0,9 → 0,5 (model ölçülen eğrinin dışına çıkmaz)
    assert np.array_equal(W[6], A.td_dalga_faz(np.full(7, 0.5), np.zeros(7))[6])
    # genlik = ölçülen eğri (td_tepe ile aynı genlik): tepe |W| = a(d)
    assert np.isclose(np.abs(W[4]).max(), A.genlik(np.full(7, 0.3))[4], rtol=1e-9)


def test_KRITIK_GA_A1_ortak_pencere_EBOB_ve_SINIR():
    from ai_hub.odak.alan import FREKANS_COZUNURLUK_HZ, ortak_pencere_s

    assert FREKANS_COZUNURLUK_HZ == 0.1
    assert np.isclose(ortak_pencere_s([100.0]), 0.01)
    assert np.isclose(ortak_pencere_s([100.0, 107.0, 100.0]), 1.0)
    assert np.isclose(ortak_pencere_s([100.0, 100.5]), 2.0)
    assert np.isclose(ortak_pencere_s([100.0, 200.0]), 0.01)
    assert np.isclose(ortak_pencere_s([76.0, 147.0]), 1.0)
    assert np.isclose(ortak_pencere_s([100.0, 100.1]), 10.0)  # 0,1 Hz çözünürlük → üst sınır 10 s
    assert np.isclose(ortak_pencere_s([100.0, 100.01]), 0.01)  # çözünürlüğün altındaki fark AYNI frekans sayılır
    assert np.isclose(ortak_pencere_s([0.01]), 10.0)  # alt sınır: 1 adım


def test_KRITIK_GA_A1_ortak_dalga_TEK_frekans_AYNEN_farkli_frekans_ASAL_ornek(A, A107):
    from ai_hub.odak.alan import ORTAK_PENCERE_ORNEK, ortak_dalga

    assert ORTAK_PENCERE_ORNEK == 2039 and all(ORTAK_PENCERE_ORNEK % p for p in range(2, 46))  # asal
    d = np.array([0.5, 0.3, 0.4, 0.2, 0.5, 0.35, 0.45])
    faz = np.array([0, 90, 45, 180, 0, 270, 30.0])
    W = A.td_dalga_faz(d, faz)
    assert np.array_equal(ortak_dalga([(100.0, W)]), W)
    g1 = np.array([1, 1, 1, 1, 0, 0, 0.0])
    W1, W2 = A.td_dalga_faz(d * g1, faz), A107.td_dalga_faz(d * (1 - g1), faz)
    Wt = ortak_dalga([(100.0, W1), (107.0, W2)])
    assert Wt.shape == (7, ORTAK_PENCERE_ORNEK)
    t = np.arange(ORTAK_PENCERE_ORNEK) * (1.0 / ORTAK_PENCERE_ORNEK)  # pencere 1 s
    Nt = W1.shape[1]
    for c in range(4):
        assert np.array_equal(Wt[c], W1[c, np.floor(np.mod(t * 100.0, 1.0) * Nt).astype(int) % Nt])
    for c in range(4, 7):
        assert np.array_equal(Wt[c], W2[c, np.floor(np.mod(t * 107.0, 1.0) * Nt).astype(int) % Nt])


def test_KRITIK_GA_A1_farkli_frekans_tepesi_INCE_ornekleme_ile_UYUMLU(A, A107, M):
    """Ortak pencere (2039 örnek) ↔ aynı pencerede 40 000 ince örnek: en büyük fark ≤ %3 (gerçek tabloda ölçülen ≤ %2,3)."""
    from ai_hub.odak.alan import ortak_dalga, ortak_pencere_s, td_tepe_dalga

    d = np.array([0.5, 0.3, 0.5, 0.2, 0.5, 0.4, 0.5])
    faz = np.array([0, 90, 45, 180, 0, 270, 30.0])
    g1 = np.array([1, 1, 1, 1, 0, 0, 0.0])
    W1, W2 = A.td_dalga_faz(d * g1, faz), A107.td_dalga_faz(d * (1 - g1), faz)
    hizli = td_tepe_dalga(M, ortak_dalga([(100.0, W1), (107.0, W2)]))
    n = 40000
    t = np.arange(n) * (ortak_pencere_s([100.0, 107.0]) / n)
    Nt = W1.shape[1]
    Wi = (
        W1[:, np.floor(np.mod(t * 100.0, 1.0) * Nt).astype(int)]
        + W2[:, np.floor(np.mod(t * 107.0, 1.0) * Nt).astype(int)]
    )
    ince = td_tepe_dalga(M, Wi)
    assert np.max(np.abs(hizli - ince)) <= 0.03 * ince.max()


def test_KRITIK_GA_A1_td_tepe_dalga_td_tepe_ile_AYNI_hesap(A, M):
    from ai_hub.odak.alan import td_tepe_dalga

    sd = np.array([0.1, -0.33, 0.27, 0.0, 0.45, -0.2, 0.05])
    assert np.array_equal(td_tepe_dalga(M, A._td_dalga(sd)), A.td_tepe(M, sd))


def test_KRITIK_GA_A1_GRAM_tepe_dogrudan_hesapla_AYNI(A, M):
    from ai_hub.odak.alan import gram, gram_tepe, td_tepe_dalga

    G = gram(M)
    assert G.shape == (len(P), 28) and G.dtype == np.float32
    for d, faz in (
        (np.full(7, 0.5), np.zeros(7)),
        (np.array([0.2, 0.5, 0.1, 0.4, 0.3, 0.5, 0.25]), np.array([0, 180, 90, 10, 300, 45, 180.0])),
    ):
        W = A.td_dalga_faz(d, faz)
        beklenen = td_tepe_dalga(M, W)
        for parca in (1, 4, 1024):
            assert np.allclose(gram_tepe(G, W, parca=parca), beklenen, rtol=1e-5, atol=1e-7)
    # alan yok (bütün duty 0) → tepe 0 (float32 yuvarlamasıyla negatif kare kökü YOK)
    assert np.array_equal(gram_tepe(G, A.td_dalga_faz(np.zeros(7), np.zeros(7))), np.zeros(len(P)))
    assert gram_tepe(G[:0], W).shape == (0,)
    # float32 yuvarlamasıyla kare biçim NEGATİF çıkabilir → 0 (NaN ya da |kare|'nin kökü DEĞİL)
    Gn = np.zeros((1, 28), np.float32)
    Gn[0, 0] = -1.0  # G_11 < 0
    Wn = np.zeros((7, 5))
    Wn[0] = 1.0
    assert np.array_equal(gram_tepe(Gn, Wn), np.zeros(1))
