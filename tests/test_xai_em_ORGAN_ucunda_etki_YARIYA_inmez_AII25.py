# -*- coding: utf-8 -*-
"""AII-2.5 (AI incelemesi, A2) — EM canlı açıklaması: `organ_id` eğitim aralığının UCUNDA etkisi YARIYA İNMEZ (onay ekranı ilk-3).

KUSUR [ÖLÇTÜM `kayit/K3_x6.json`, gerçek em_kedi / em_fantom]: `em_runtime.merkezi_duyarlilik` organ_id'yi ±1 komşu kategoriye
kaydırıp eğitim aralığına KIRPAR ve farkı HER ZAMAN 2'ye böler. İç değerde |f(o+1) − f(o−1)| / 2 = adım başına etki; UÇTA (kedi 0 =
Tüm Vücut, 6 = Bağırsak; fantomda aralık [0, 1] → HER nokta uç) kırpma bir tarafı sıfırlar → |f(o±1) − f(o)| / 2 = adım etkisinin
YARISI. Onay ekranının "Dozu en çok belirleyen" ilk-3'ü uç noktaların kedi 12/26'sında, fantom 47/120'sinde değişiyor (ör. kedi organ 0:
gösterilen "konum Y · güç bütçesi · konum X", doğru adım etkisiyle organ 1. sırada). Hocanın `em_sensitivity_v2.sensitivity_v2`'si de
aynı (guii sadık uyarlama) → hocaya not. Sürüşü etkilemez (yalnız açıklama).
Kapı: doğrusal sentetik model (organ başına sabit etki) — organ etkisi iç değerde ve uçlarda AYNI; uçtaki baskın organ ilk sırada.
Yol: tests/test_xai_em_ORGAN_ucunda_etki_YARIYA_inmez_AII25.py"""

from __future__ import annotations

import numpy as np
import pytest

ADIM = 0.06  # organ başına duty değişimi (sentetik)


def _ref(org_hi):
    return {
        "std": np.array([140.0, 176.0, 110.0, 1.5, 6e-5, 0.32]),
        "min": np.array([-212.0, -330.0, -287.0, 0.0, 9e-4, 1.06]),
        "max": np.array([298.0, 330.0, 142.0, float(org_hi), 1.1e-3, 3.19]),
    }


def _fn(X):
    X = np.asarray(X, dtype=np.float64)
    duty = ADIM * X[:, 3] + 0.002 * X[:, 1] + 0.5 * X[:, 5]
    return np.repeat(duty[:, None], 14, axis=1)


@pytest.mark.parametrize("org_hi", [6, 1], ids=["kedi_0_6", "fantom_0_1"])
def test_KRITIK_organ_etkisi_UCTA_ve_ICTE_ayni(org_hi):
    from ai_hub.xai_tabular import em_runtime as er

    organlar = list(range(0, org_hi + 1))
    X = np.array([[10.0, 20.0, -30.0, float(o), 1e-3, 2.0] for o in organlar])
    S = er.merkezi_duyarlilik(_fn, X, _ref(org_hi))
    j = list(er.EM_FEATURES).index("organ_id")
    for o, s in zip(organlar, S[:, j]):
        assert s == pytest.approx(ADIM, rel=1e-6), (
            f"organ {o} (aralık 0..{org_hi}): etki {s:.4f} ≠ adım etkisi {ADIM} — uçta kırpılan taraf farkı YARIYA indiriyor"
        )


def test_KRITIK_onay_ekrani_UC_organda_baskin_organi_ILK_sirada_gosterir(monkeypatch):
    """Uç organ (0) + organ adım etkisi 0,06 > konum Y etkisi (0,002 × 17,6 = 0,035) > duty (0,5 × 0,032 = 0,016):
    "Dozu en çok belirleyen" listesi organ_id ile BAŞLAMALI (bugün y başlıyor — organ 0,03'e iniyor)."""
    from ai_hub.xai_tabular import em_runtime as er

    monkeypatch.setattr(er, "predict_raw_fn", lambda pred: _fn)
    liste = er.hizli_sensitivity(None, _ref(6), 10.0, 20.0, -30.0, 0.0, 1e-3, 2.0)
    belirleyen = [d["feature"] for d in liste if not d.get("ogrenilmemis") and d.get("surukleyen") is not False]
    assert belirleyen[:1] == ["organ_id"], f"uç organda baskın organ ilk sırada değil: {belirleyen}"


@pytest.mark.parametrize("org_hi", [6, 1], ids=["kedi_0_6", "fantom_0_1"])
def test_KRITIK_TOPLU_yol_organ_etkisi_UCTA_ve_ICTE_ayni_ve_CANLI_ile_esit(org_hi):
    """Orkestratör (AI inceleme): toplu XAI CLI'nin `em_sensitivity.sensitivity_egitim_ref`'i (AI-1 X10) AYNI /2 kusurunu ikinci kez
    uyguluyordu — ajanın yaması yalnız canlı yolu düzeltmişti. Toplu yol uçta adım etkisi verir ve canlı yolla satır satır eşittir."""
    from ai_hub.xai_tabular import em_runtime as er
    from ai_hub.xai_tabular import em_sensitivity as es

    organlar = list(range(0, org_hi + 1))
    X = np.array([[10.0, 20.0, -30.0, float(o), 1e-3, 2.0] for o in organlar])
    toplu = es.sensitivity_egitim_ref(_fn, X, _ref(org_hi))["per_sample_duty"]
    canli = er.merkezi_duyarlilik(_fn, X, _ref(org_hi))
    j = list(es.EM_FEATURES).index("organ_id")
    assert np.allclose(toplu[:, j], ADIM, rtol=1e-6), f"toplu yol uç organ etkisi {toplu[:, j]} ≠ {ADIM}"
    assert np.allclose(toplu, canli, rtol=1e-9, equal_nan=True), "toplu ve canlı duyarlılık AYRIŞTI"


def test_KARSIT_surekli_ozellik_ve_ic_organ_DEGISMEZ():
    from ai_hub.xai_tabular import em_runtime as er

    X = np.array([[10.0, 20.0, -30.0, 3.0, 1e-3, 2.0]])
    S = er.merkezi_duyarlilik(_fn, X, _ref(6))[0]
    F = list(er.EM_FEATURES)
    assert S[F.index("y")] == pytest.approx(0.002 * 0.1 * 176.0, rel=1e-6)
    assert S[F.index("duty_sum")] == pytest.approx(0.5 * 0.1 * 0.32, rel=1e-6)
    assert S[F.index("organ_id")] == pytest.approx(ADIM, rel=1e-6)
    assert S[F.index("x")] == 0.0
