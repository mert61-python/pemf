# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GA (istem 53) A1 — `ai_hub/odak/alan.py` MEVCUT işlevleri SABİT (Y257 deseni: canlı alan eklenmeden ÖNCE davranışı sabitleyen test).

Canlı 3B alan görünümü için alan.py'ye YENİ işlevler eklenir (`td_dalga_faz`, `td_tepe_faz`, ortak pencere, Gram); ODAK'ın kullandığı mevcut
işlevler (`AlanModeli` kurulumu, `alan`, `genlik` / `duty`, `fazlar`, `td_tepe`, `td_turev`, `dogrusal_tepe`, `tavan`, `tavan_td`,
`rl_dalga_bicimi`, `kalibrasyon_kimligi`) DEĞİŞMEZ. Altın değerler değişiklikten ÖNCEKİ koddan üretildi (sentetik tablo + izlenen örnek
kalibrasyon — CI'da da koşar); göreli tolerans 1e-12 (platformlar arası son bit farkı için; aynı makinede bit-bit karma GA.md'de).
"""

from __future__ import annotations

import canli_alan_aparati as ap
import numpy as np
import pytest

ALTIN = {
    'kimlik': 'e6f0971a52f6d6a0',
    'kimlik107': 'e6f0971a52f6d6a0@107Hz',
    'a_tab_toplam': 234.11056366336243,
    'a_azami107': [
        0.9546101147841293,
        0.9546101147841293,
        0.9546101147841293,
        0.9546101147841293,
        0.9546101147841293,
        0.9776158307002661,
        0.9776158307002661,
    ],
    'bicim_toplam': 35425.76973624658,
    'bicim107_toplam': 36617.18335957754,
    'alan': [
        0.12152983758596264,
        0.038365244237066776,
        0.035045135171339156,
        0.044572374278075866,
        -0.0009086376386861635,
        -0.0007331709298600183,
        0.09353756206335502,
        0.16028838660887473,
        0.016933849779720678,
        0.0032304314758269475,
        -0.05225288508695426,
        -0.021422130851517368,
        0.006017323855209461,
        0.007991251980112456,
        -0.02653338685085409,
    ],
    'td_tepe': [
        [0.9034383878198203, 2.51482683447962, 0.5387676364633004, 1.0988795193578127, 0.17134119592609418],
        [0.4223365469880041, 2.602575860686112, 0.10349785979926042, 1.0088209174381597, 0.15179097712496228],
        [0.24878855296761, 2.068932910707289, 0.1255851813278783, 0.4829292856279738, 0.08673714153129929],
    ],
    'td_tepe_hizasiz': [
        0.2628263427882214,
        2.0759805983162876,
        0.09670937422279458,
        0.5386433581392508,
        0.08781156109416756,
    ],
    'td_tepe107': [0.4038496192398042, 2.4849805009849733, 0.1014631315560955, 0.9860891856364499, 0.14629918162787303],
    'td_turev_toplam': 1358301.348960574,
    'fazlar': [
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        [180.0, 0.0, 180.0, 180.0, 0.0, 0.0, 0.0],
        [125.99999999999999, 223.2, 64.8, 0.0, 0.0, 270.0, 144.0],
    ],
    'genlik': [
        0.367348557129908,
        0.8556454177231144,
        0.8182802098644529,
        0.0,
        0.9585712029298129,
        0.6341601973323993,
        0.18568452954518086,
    ],
    'duty': [
        0.0542863330870843,
        0.16111871092676525,
        0.3298974351862109,
        0.5,
        0.0,
        0.08023418609753054,
        0.233750552091375,
    ],
    'isaretli_duty': [
        -0.0542863330870843,
        0.16111871092676525,
        -0.3298974351862109,
        0.5,
        0.0,
        -0.08023418609753054,
        0.233750552091375,
    ],
    'dogrusal_tepe': [
        0.22940118375414406,
        0.8262113062353733,
        0.14855510619059228,
        0.2602938975155907,
        0.1415199572743233,
    ],
    'tavan': 0.6290136553004602,
    'tavan_td': 0.9034383878198203,
    'rl': 78.41853135502774,
}

P = np.array(
    [[0.0, -160.0, 0.0], [120.0, -100.0, -80.0], [-200.0, 0.0, 150.0], [50.0, 120.0, 60.0], [-260.0, 160.0, -190.0]]
)
SD = [np.full(7, 0.5), 0.5 * np.array([-1, 1, -1, -1, 1, 1, 1.0]), np.array([0.1, -0.33, 0.27, 0.0, 0.45, -0.2, 0.05])]


@pytest.fixture(scope="module")
def olcum():
    from ai_hub.odak import alan

    K = ap.kalibrasyon()
    T = ap.tablo()
    A = alan.AlanModeli(K, tablo=T)
    A107 = alan.AlanModeli(K, tablo=T, f_hz=107.0)
    M = A.alan(P)
    return {
        "kimlik": alan.kalibrasyon_kimligi(K),
        "kimlik107": A107.kimlik,
        "a_tab_toplam": float(A.a_tab.sum()),
        "a_azami107": list(A107.a_azami),
        "bicim_toplam": float(A.bicim.sum()),
        "bicim107_toplam": float(A107.bicim.sum()),
        "alan": list(M.ravel()[::7]),
        "td_tepe": [list(A.td_tepe(M, sd)) for sd in SD],
        "td_tepe_hizasiz": list(A.td_tepe(M, SD[2], hizala=False)),
        "td_tepe107": list(A107.td_tepe(M, SD[1])),
        "td_turev_toplam": float(np.abs(A.td_turev(SD[2])).sum()),
        "fazlar": [list(alan.AlanModeli.fazlar(sd)) for sd in SD],
        "genlik": list(A.genlik(SD[2])),
        "duty": list(A.duty(np.array([0.2, 0.5, 0.9, 1.2, 0.0, 0.33, 0.71]))),
        "isaretli_duty": list(A.isaretli_duty(np.array([-0.2, 0.5, -0.9, 1.2, 0.0, -0.33, 0.71]))),
        "dogrusal_tepe": list(A.dogrusal_tepe(M, np.array([1, -0.5, 0.3, 1, -1, 0.2, 0.7]))),
        "tavan": alan.tavan(M[:3]),
        "tavan_td": alan.tavan_td(A, M[:2]),
        "rl": float(
            np.abs(
                alan.rl_dalga_bicimi([0.1, 0.3, 0.5], True, 24.0, 8.7, 27.0, 100.0, 1.5, n_kayit=50, n_ince=500)
            ).sum()
        ),
    }


@pytest.mark.parametrize("ad", sorted(ALTIN))
def test_KRITIK_GA_A1_alan_MEVCUT_islev_SABIT(olcum, ad):
    beklenen, olan = ALTIN[ad], olcum[ad]
    if isinstance(beklenen, str):
        assert olan == beklenen
    else:
        assert np.allclose(np.asarray(olan, float), np.asarray(beklenen, float), rtol=1e-12, atol=1e-15), ad
