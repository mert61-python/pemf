# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ODM (istem 55, 18 Kasım 2026 tezgâh ölçümü) — alan kalibrasyonunda bobin başına ÖTELEME.

SÖZLEŞME:
  - `bobin_oteleme_mm` (isteğe bağlı; gerçek bobin sırası, 7 × [dx, dy, dz] mm, ölçüm çerçevesi: x sağ, y yukarı, z ön) bobin r'nin CST
    alanını Δ_r kadar TAŞIR: M_r(P) = CST_r(P − Δ_r). Diğer bobinler değişmez; B ve E aynı ötelemeyi alır.
  - Öteleme yok / sıfır → alan ve kalibrasyon kimliği eskisiyle AYNI (yerleşik modeller bağlı kalır).
  - Sıfır olmayan öteleme kimliğe girer (0,1 mm çözünürlük) → eski ötelemeyle eğitilmiş model "modelEski" (SÜRMEZ).
  - Kalibrasyon kapısı FAIL-CLOSED: biçimi bozuk (7 × 3 değil), sonlu değil ya da bileşeni > OTELEME_AZAMI_MM olan öteleme →
    `kalibrasyonBozuk`.
Alan tablosu YAPAY ve koordinatlarda DOĞRUSAL (üç doğrusal ara değerleme ızgara içinde KESİN) — gerçek CST tablosu gerekmez.
"""

from __future__ import annotations

import copy
import json
import os

import numpy as np
import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORNEK = os.path.join(KOK, "tests", "veri", "odak_kalibrasyon_ornek.json")
N = 7


@pytest.fixture(scope="module")
def K():
    with open(ORNEK, encoding="utf-8") as fh:
        K = json.load(fh)
    K.pop("bobin_oteleme_mm", None)
    return K


def _dogrusal_tablo(ad: str = "B") -> dict:
    """CST ızgarası (−300…300 mm, 20 mm) üzerinde bileşen ve CST bobini başına FARKLI doğrusal alan."""
    eks = np.arange(-300.0, 301.0, 20.0)
    X, Y, Z = np.meshgrid(eks, eks, eks, indexing="ij")
    B = np.zeros(X.shape + (3, N), np.float64)
    for c in range(N):
        for b in range(3):
            B[..., b, c] = (c + 1) * 0.001 * X + (b + 1) * 0.002 * Y - 0.0005 * (c + 2) * Z + 0.1 * c - 0.03 * b
    return {ad: B, "kok": np.array([-300.0, -300.0, -300.0]), "adim": 20.0, "boyut": np.array(B.shape[:3])}


def _model(K, oteleme=None):
    from ai_hub.odak.alan import AlanModeli

    K2 = copy.deepcopy(K)
    if oteleme is not None:
        K2["bobin_oteleme_mm"] = np.asarray(oteleme, float).tolist()
    return AlanModeli(K2, tablo=_dogrusal_tablo())


def _kok(tmp_path, K):
    d = tmp_path / "kabin_kalibrasyonu"
    d.mkdir(parents=True, exist_ok=True)
    (d / "alan_kalibrasyonu.json").write_text(json.dumps(K), encoding="utf-8")
    return str(tmp_path)


#: kabin içi ölçüm noktaları (x sağ, y yukarı, z ön)
P = np.array([[0.0, -167.5, 0.0], [130.0, -150.0, -40.0], [-90.0, 20.0, 60.0], [200.0, 100.0, -120.0]])


def test_KRITIK_otelemesiz_ya_da_SIFIR_oteleme_ALAN_ve_KIMLIK_AYNI(K):
    from ai_hub.odak.alan import kalibrasyon_kimligi

    A0, Az = _model(K), _model(K, np.zeros((N, 3)))
    assert np.array_equal(A0.alan_olcum(P), Az.alan_olcum(P))
    assert kalibrasyon_kimligi({**K, "bobin_oteleme_mm": np.zeros((N, 3)).tolist()}) == kalibrasyon_kimligi(K)
    # 0,1 mm'nin altındaki yuvarlak sıfır da kimliği DEĞİŞTİRMEZ (−0,0 dahil)
    kucuk = np.zeros((N, 3))
    kucuk[2] = [-0.04, 0.03, -0.0]
    assert kalibrasyon_kimligi({**K, "bobin_oteleme_mm": kucuk.tolist()}) == kalibrasyon_kimligi(K)
    assert A0.kimlik == Az.kimlik == kalibrasyon_kimligi(K)
    # MUTLAK çapa: kurulu ODK12 kalibrasyonunun (13-11, ötelemesiz) kimliği yeni kodla da AYNI → yerleşik modeller bağlı kalır
    odk12 = {**K, "kazanc": [0.4692, 0.6008, 0.9481, 0.697, 0.6633, 0.5282, 0.4793]}
    assert kalibrasyon_kimligi(odk12) == "e6f0971a52f6d6a0"
    assert kalibrasyon_kimligi({**odk12, "bobin_oteleme_mm": np.zeros((N, 3)).tolist()}) == "e6f0971a52f6d6a0"


def test_KRITIK_otelenen_bobinin_ALANI_DELTA_kadar_TASINIR_digerleri_DEGISMEZ(K):
    d = np.zeros((N, 3))
    d[0] = [-2.1, 21.8, -13.8]
    A0, A1 = _model(K), _model(K, d)
    M0, M1 = A0.alan_olcum(P), A1.alan_olcum(P)
    # bobin 1: yeni modelin P + Δ'daki alanı = eski modelin P'deki alanı (bobin Δ kadar taşındı — işaret YÖNÜ dahil)
    assert np.allclose(A1.alan_olcum(P + d[0])[..., 0], M0[..., 0], atol=1e-9)
    assert not np.allclose(M1[..., 0], M0[..., 0])
    # öbür bobinler aynı noktada BİREBİR aynı (yanlış bobine uygulanmadı, sıra karışmadı)
    assert np.array_equal(M1[..., 1:], M0[..., 1:])
    # kazanç × işaret ötelenen bobine de uygulanır; backend girişi aynı dönüşümden geçer
    from ai_hub.odak.alan import backend_to_olcum

    assert np.allclose(A1.alan(backend_to_olcum(P)), M1)
    assert M1.shape == (len(P), 3, N) and A1.alan_olcum(P[0]).shape == (3, N)


def test_KRITIK_birden_COK_bobin_ayri_ayri_otelenir(K):
    d = np.zeros((N, 3))
    d[1] = [5.0, -7.0, 3.0]
    d[5] = [-12.0, 0.0, 9.0]
    A0, A2 = _model(K), _model(K, d)
    for r in range(N):
        assert np.allclose(A2.alan_olcum(P + d[r])[..., r], A0.alan_olcum(P)[..., r], atol=1e-9), r


def test_KRITIK_E_alani_AYNI_otelemeyle_tasinir(K):
    from ai_hub.odak.alan import backend_to_olcum, olcum_to_backend

    d = np.zeros((N, 3))
    d[0] = [4.0, 18.0, -9.0]
    A0, A1 = _model(K), _model(K, d)
    A0._etablo = A1._etablo = _dogrusal_tablo("E")
    Pb = olcum_to_backend(P)
    E0, E1 = A0.e_alan(Pb), A1.e_alan(Pb)
    assert np.allclose(A1.e_alan(olcum_to_backend(P + d[0]))[..., 0], E0[..., 0], atol=1e-9)
    assert np.array_equal(E1[..., 1:], E0[..., 1:])
    assert np.allclose(backend_to_olcum(Pb), P)


def test_KRITIK_KIMLIK_oteleme_ile_DEGISIR(K):
    from ai_hub.odak.alan import kalibrasyon_kimligi

    k0 = kalibrasyon_kimligi(K)
    d = np.zeros((N, 3))
    d[0] = [0.0, 21.8, 0.0]
    k1 = kalibrasyon_kimligi({**K, "bobin_oteleme_mm": d.tolist()})
    d2 = d.copy()
    d2[0, 1] = 21.9
    k2 = kalibrasyon_kimligi({**K, "bobin_oteleme_mm": d2.tolist()})
    d3 = np.zeros((N, 3))
    d3[1] = [0.0, 21.8, 0.0]  # aynı öteleme BAŞKA bobinde
    k3 = kalibrasyon_kimligi({**K, "bobin_oteleme_mm": d3.tolist()})
    assert len({k0, k1, k2, k3}) == 4
    # sürüşteki model kimliği de değişir (eski ötelemeyle eğitilmiş model "modelEski")
    assert _model(K, d).kimlik == k1 != _model(K).kimlik


@pytest.mark.parametrize(
    "ote",
    [
        np.zeros((6, 3)).tolist(),
        np.zeros((N, 2)).tolist(),
        [[0.0, 0.0, 0.0]] * 6 + [[0.0, 0.0]],
        [[float("nan"), 0.0, 0.0]] + [[0.0, 0.0, 0.0]] * 6,
        [[0.0, float("inf"), 0.0]] + [[0.0, 0.0, 0.0]] * 6,
        [[0.0, 100.5, 0.0]] + [[0.0, 0.0, 0.0]] * 6,
        [[0.0, 0.0, 0.0]] * 6 + [[-150.0, 0.0, 0.0]],
        [["a", 0.0, 0.0]] + [[0.0, 0.0, 0.0]] * 6,
        "bozuk",
    ],
)
def test_KRITIK_kalibrasyon_kapisi_BOZUK_otelemede_SURMEZ(K, tmp_path, ote):
    from ai_hub.odak.alan import KalibrasyonHatasi, kalibrasyon_oku

    with pytest.raises(KalibrasyonHatasi) as e:
        kalibrasyon_oku(_kok(tmp_path, {**K, "bobin_oteleme_mm": ote}))
    assert e.value.kod == "kalibrasyonBozuk"


def test_kalibrasyon_kapisi_GECERLI_otelemeyi_kabul_eder(K, tmp_path):
    from ai_hub.odak.alan import OTELEME_AZAMI_MM, kalibrasyon_oku

    assert OTELEME_AZAMI_MM == 100.0
    d = np.zeros((N, 3))
    d[0] = [-2.1, 21.8, -13.8]
    d[6] = [0.0, -100.0, 100.0]  # sınır dahil
    assert kalibrasyon_oku(_kok(tmp_path, {**K, "bobin_oteleme_mm": d.tolist()}))["bobin_oteleme_mm"] == d.tolist()
    assert "bobin_oteleme_mm" not in kalibrasyon_oku(_kok(tmp_path, K))
