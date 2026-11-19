# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GA (istem 53) A1 — `ai_hub/odak/alan.py` MEVCUT işlevleri SABİT (Y257 deseni: canlı alan eklenmeden ÖNCE davranışı sabitleyen test).

Canlı 3B alan görünümü için alan.py'ye YENİ işlevler eklenir (`td_dalga_faz`, `td_tepe_faz`, ortak pencere, Gram); ODAK'ın kullandığı mevcut
işlevler (`AlanModeli` kurulumu, `alan`, `genlik` / `duty`, `fazlar`, `td_tepe`, `td_turev`, `dogrusal_tepe`, `tavan`, `tavan_td`,
`rl_dalga_bicimi`, `kalibrasyon_kimligi`) DEĞİŞMEZ. Altın değerler değişiklikten ÖNCEKİ koddan üretildi (sentetik tablo + izlenen örnek
kalibrasyon — CI'da da koşar); göreli tolerans 1e-12 (platformlar arası son bit farkı için; aynı makinede bit-bit karma GA.md'de).
OYZ (istem 56 AŞAMA 3, 19-11 birleştirme): ODM örnek kalibrasyonu `5a248f7d` (bobin 1 ötelemesi + kazanç) ile değiştiği için altın
değerler GA'dan ÖNCEKİ ODM kodundan (`duzeltme/odk-b` @ `47cdc817`) YENİDEN üretildi; birleşik kodla BİT BİT aynı (GA'nın alan.py farkı
yalnız ekleme). Eski değerler (`e6f0971a`) GA'nın kendi tabanının (`d2d5179b`) kalibrasyonundandı.
"""

from __future__ import annotations

import canli_alan_aparati as ap
import numpy as np
import pytest

ALTIN = {
    'kimlik': '5a248f7d6cc34afb',
    'kimlik107': '5a248f7d6cc34afb@107Hz',
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
        0.0939754819502228,
        0.041008178931068166,
        0.0415633404168654,
        0.040409058435181736,
        0.002911502923903396,
        0.0025131828687960157,
        0.25790982404816465,
        0.21067265495950438,
        -0.05136415527074242,
        0.010999634056179399,
        -0.05248727370250632,
        -0.02515280027954439,
        0.008848226351285455,
        0.007342921057179073,
        -0.024784467020582016,
    ],
    'td_tepe': [
        [0.8816617393603075, 2.5115875682098547, 0.6738164760851301, 1.0915191038201009, 0.17176756485150937],
        [0.41671318744461505, 2.600038118429679, 0.2821169063831033, 1.015448320010513, 0.1518273449921453],
        [0.2517040017508979, 2.0680192950331664, 0.14105321326867484, 0.4846048588968873, 0.08707738387884624],
    ],
    'td_tepe_hizasiz': [
        0.26403181790927166,
        2.0755859351487373,
        0.11545016044766404,
        0.5397335416705407,
        0.08790929158960431,
    ],
    'td_tepe107': [
        0.39851089028434916,
        2.482559077617442,
        0.27160715539234215,
        0.9924181120748055,
        0.14636476353205935,
    ],
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
        0.206278749180389,
        0.8230893520236386,
        0.2617354044633987,
        0.25291655638383836,
        0.13900423846167975,
    ],
    'tavan': 0.7514565083405568,
    'tavan_td': 0.8816617393603075,
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
