# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""CANLI E-ALANI (2026-08-06, hoca isteği: 'E alanı gerçek zamanlı, bar gibi').

Kilitlenen sözleşme:
  * Telemetri → model girdisi dönüşümü (mT→Tesla, %→duty toplamı) DOĞRU ölçekte olmalı;
    üretim varsayılanlarıyla (1 mT / duty_sum 1.5) tutarlı kalmalı.
  * YALNIZ çalışan bobinler sayılır (duran bobin ortalamayı düşürüp E'yi yanlış göstermesin).
  * Bağlam yoksa canlı değer ÜRETİLMEZ (eski değeri canlıymış gibi göstermek yanıltıcıdır).
"""

import os

os.environ.pop("PEMF_SIMULATE", None)

import pytest

from servers import efield_live as ef


@pytest.fixture(autouse=True)
def _temiz():
    ef.set_context([])  # her testte bağlamı sıfırla
    yield
    ef.set_context([])


# ── telemetri → model girdisi ölçeği ────────────────────────────────────────
def test_olcek_uretim_varsayilanlariyla_tutar():
    """5 bobin × %30 duty, 1 mT  →  achieved_B=0.001 T, duty_sum=1.5.
    Bu tam olarak ai_router._AI_ACHIEVED_B / _AI_DUTY_SUM varsayılanlarıdır."""
    coils = [{"running": True, "magneticMt": 1.0, "dutyCycle": 30.0} for _ in range(5)]
    b, duty, n = ef.telemetry_inputs(coils)
    assert n == 5
    assert b == pytest.approx(0.001), f"achieved_B Tesla olmalı: {b}"
    assert duty == pytest.approx(1.5), f"duty_sum duty toplamı olmalı: {duty}"


def test_yalniz_CALISAN_bobinler_sayilir():
    """Duran bobin alan üretmez; ortalamaya katılırsa B yapay olarak düşer."""
    coils = [
        {"running": True, "magneticMt": 2.0, "dutyCycle": 40.0},
        {"running": False, "magneticMt": 0.0, "dutyCycle": 0.0},
        {"running": False, "magneticMt": 0.0, "dutyCycle": 0.0},
    ]
    b, duty, n = ef.telemetry_inputs(coils)
    assert n == 1
    assert b == pytest.approx(0.002), "duran bobinler ortalamayı düşürmüş"
    assert duty == pytest.approx(0.4)


def test_calisan_bobin_yoksa_sifir():
    b, duty, n = ef.telemetry_inputs([{"running": False, "magneticMt": 5.0, "dutyCycle": 90.0}])
    assert (b, duty, n) == (0.0, 0.0, 0)


def test_bos_liste_cokertmez():
    assert ef.telemetry_inputs([]) == (0.0, 0.0, 0)
    assert ef.telemetry_inputs(None) == (0.0, 0.0, 0)


# ── bağlam yönetimi ─────────────────────────────────────────────────────────
def test_baglam_kurulur_ve_okunur():
    ef.set_context([{"centroid_cabin_mm": [10.0, -5.0, 3.0], "organ_id": 2}])
    c = ef.get_context()
    assert c and (c["x"], c["y"], c["z"], c["organ_id"]) == (10.0, -5.0, 3.0, 2)


def test_baglam_YOKSA_canli_deger_URETILMEZ():
    """Analiz yapılmadan bar gösterilemez — uydurma değer YOK."""
    assert ef.get_context() is None
    assert ef.compute([{"running": True, "magneticMt": 2.0, "dutyCycle": 30.0}]) is None


def test_bos_liste_baglami_TEMIZLER():
    ef.set_context([{"centroid_cabin_mm": [1.0, 2.0, 3.0], "organ_id": 1}])
    assert ef.get_context() is not None
    ef.set_context([])
    assert ef.get_context() is None
    assert ef.get_live() is None


def test_centroid_eksikse_baglam_kurulmaz():
    ef.set_context([{"area_mm2": 12.0}])  # centroid YOK
    assert ef.get_context() is None


# ── gerçek modelle uçtan uca ────────────────────────────────────────────────
def test_gercek_model_ile_E_uretir_ve_duty_ile_DEGISIR():
    """Vekil model gerçekten çağrılıyor mu ve canlı girdiye TEPKİ veriyor mu?
    (Sabit bir sayı döndüren sahte bir 'canlı' bar işe yaramaz.)"""
    if ef._predictor() is None:
        pytest.skip("vekil model yok (ai_models kurulu değil)")
    ef.set_context([{"centroid_cabin_mm": [0.0, 0.0, 0.0], "organ_id": 1}])

    dusuk = ef.compute([{"running": True, "magneticMt": 1.0, "dutyCycle": 10.0}])
    yuksek = ef.compute([{"running": True, "magneticMt": 4.0, "dutyCycle": 80.0}])
    assert dusuk and yuksek
    for v in (dusuk, yuksek):
        assert set(["healthy", "cancer", "avg", "activeCoils", "achievedB_T", "dutySum"]) <= set(v)
    assert dusuk["cancer"] != yuksek["cancer"], "E canlı girdiye tepki vermiyor — bar sabit kalırdı"
    assert yuksek["achievedB_T"] == pytest.approx(0.004)
    assert yuksek["dutySum"] == pytest.approx(0.8)


def test_bobin_durunca_E_sifirlanir():
    """Bobinler durduğunda bar SIFIRA inmeli — son değeri tutmak 'hâlâ alan var' der."""
    ef.set_context([{"centroid_cabin_mm": [0.0, 0.0, 0.0], "organ_id": 1}])
    v = ef.compute([{"running": False, "magneticMt": 0.0, "dutyCycle": 0.0}])
    assert v is not None
    assert v["cancer"] == 0.0 and v["healthy"] == 0.0 and v["activeCoils"] == 0
