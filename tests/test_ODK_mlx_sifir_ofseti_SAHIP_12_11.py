# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ODK · sahip kararı 12 Kasım 2026 (tezgâh): MLX90393'ün ~0,34 mT SIFIR OFSETİ backend'de çıkarılır — bobinler KAPALIYKEN (kartın STM_OK
yankısında bütün duty 0, son sürüşten ≥ 2 sn sonra) ölçülen eksen merkezleri ofsettir; sürüşte |B| ofsetsiz eksen uçlarından. Firmware DEĞİŞMEZ.
Ölçüldü (ODK 0. adım): bobinler kapalıyken firmware `B=` ~0,38 mT; faz 0 tavanında B satırı 1,04, ofsetsiz 0,75 mT (+%37).
SÖZLEŞME: en az 3 boşta pencereden önce DEĞER DEĞİŞMEZ · sürüş penceresi / son sürüşe < 2 sn / doygun pencere ofsete KATILMAZ · ham değer
`magnetic_field_ham`da · `_handle_stm_line` iki yolu (STM_OK yankısı, STM_TELE) bağlar; ofset hatası satırı DÜŞÜRMEZ (ham kalır).
"""

from __future__ import annotations

import math

import pytest
from test_KP_headless_core_satir_ve_yasam_dongusu import _cekirdek, _Veriyolu
from utils import mlx_ofset as mo

OFS = (-0.04, 0.18, -0.28)
SIFIR = "-> STM_OK: D=0,0,0,0,0,0,0 P=0,0,0,0,0,0,0 F=100,100,100,100,100,100,100 T=0,0,0,0,0,0,0 K=96 E=0,0,0,0,0,0,0"
AKTIF = (
    "-> STM_OK: D=250,0,0,0,0,0,0 P=0,0,0,0,0,0,0 F=100,100,100,100,100,100,100 T=1,0,0,0,0,0,0 K=96 E=0,0,0,0,0,0,0"
)


class _Saat:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def _govde(b=(0.0, 0.0, 0.0), gurultu=0.03, B=None, ofs=OFS, **ek):
    g = {"coil_id": 6}
    for (a, z), o, bi in zip(mo.EKSENLER, ofs, b):
        g[a], g[z] = o - abs(bi) - gurultu / 2, o + abs(bi) + gurultu / 2
    g["magnetic_field"] = B if B is not None else round(math.dist((0, 0, 0), ofs) + math.hypot(*b), 3)
    g.update(ek)
    return g


def test_KRITIK_bosta_3_pencereden_SONRA_ofset_cikarilir_ve_SURUSTE_ofsetsiz_B():
    s = _Saat()
    m = mo.MlxOfset(saat=s)
    m.duty_yankisi(SIFIR)
    for i in range(2):
        g = _govde()
        m.pencere(g)
        assert "magnetic_ofset_duzeltildi" not in g and g["magnetic_field"] == pytest.approx(0.337, abs=0.01), (
            "3 pencereden önce değer değişti"
        )
    g = _govde()
    m.pencere(g)
    assert g["magnetic_ofset_duzeltildi"] is True and g["magnetic_field"] < 0.05 and g["magnetic_field_ham"] > 0.3
    assert m.ofset == pytest.approx(list(OFS), abs=1e-9)
    # sürüş: bipolar salınım (0,5 · 0,6 · 0,3 mT) → ofsetsiz |B| = tepe vektörü (+ gürültü yarısı)
    m.duty_yankisi(AKTIF)
    s.t += 0.5
    g = _govde(b=(0.5, 0.6, 0.3), gurultu=0.0, B=1.2)
    m.pencere(g)
    assert g["magnetic_field"] == pytest.approx(math.hypot(0.5, 0.6, 0.3), abs=1e-3) and g["magnetic_field_ham"] == 1.2
    assert m.ofset == pytest.approx(list(OFS), abs=1e-9), "sürüş penceresi ofsete katıldı"


def test_KRITIK_son_surusten_2_SN_ICINDE_bosta_pencere_ofsete_KATILMAZ_sonra_katilir():
    s = _Saat()
    m = mo.MlxOfset(saat=s)
    m.duty_yankisi(AKTIF)
    s.t += 0.5
    m.duty_yankisi(SIFIR)
    for _ in range(3):
        m.pencere(_govde(ofs=(0.5, 0.5, 0.5)))  # söndürme süresinde yanlış merkez
    assert m.ofset is None
    s.t += mo.BOSTA_BEKLEME_S
    for _ in range(3):
        m.pencere(_govde())
    assert m.ofset == pytest.approx(list(OFS), abs=1e-9)


def test_KARSIT_doygun_eksik_eksen_ve_bozuk_yanki_YOK_SAYILIR():
    m = mo.MlxOfset(saat=_Saat())
    m.duty_yankisi("-> STM_OK: D=a,b")
    m.duty_yankisi("-> STM_OK: D=,")
    m.duty_yankisi("-> STM_OK: D=-,1")
    m.duty_yankisi("-> STM_OK: P=0")
    assert m._bosta is False
    m.duty_yankisi(SIFIR)
    for _ in range(5):
        m.pencere(_govde(magnetic_saturated=True))
    assert m.ofset is None, "doygun pencere ofsete katıldı"
    g = {"coil_id": 6, "magnetic_field": 0.4, "mag_x_min": 0.0}
    m.pencere(g)
    assert g == {"coil_id": 6, "magnetic_field": 0.4, "mag_x_min": 0.0}
    g = {"coil_id": 6, "object_temp": 30.0}
    m.pencere(g)
    assert g == {"coil_id": 6, "object_temp": 30.0}


def test_KRITIK_handle_stm_line_STM_OK_ve_TELE_yollari_BAGLI_yayinda_ofsetsiz_B(tmp_path):
    bus = _Veriyolu()
    c = _cekirdek(bus, tmp_path)
    c._handle_stm_line(SIFIR)
    tele = "-> STM_TELE: C=6,T=30.00,A=25.00,B=0.381,N=360,XN=-0.070,XP=-0.010,YN=0.150,YP=0.210,ZN=-0.310,ZP=-0.250,GS=0,RS=0"
    for _ in range(3):
        c._handle_stm_line(tele)
    son = bus.hepsi("hardware.stm.telemetry")[-1][1]
    assert (
        son["magnetic_ofset_duzeltildi"] is True
        and son["magnetic_field"] < 0.06
        and son["magnetic_field_ham"] == pytest.approx(0.381)
    )
    c._handle_stm_line(AKTIF)
    c._handle_stm_line(
        "-> STM_TELE: C=6,B=1.200,N=360,XN=-0.540,XP=0.460,YN=-0.420,YP=0.780,ZN=-0.580,ZP=0.020,GS=0,RS=0"
    )
    son = bus.hepsi("hardware.stm.telemetry")[-1][1]
    assert (
        son["magnetic_field"] == pytest.approx(math.hypot(0.5, 0.6, 0.3), abs=0.01) and son["magnetic_field_ham"] == 1.2
    )


def test_KARSIT_ofset_HATASI_satiri_dusurmez_HAM_kalir(tmp_path, monkeypatch, caplog):
    bus = _Veriyolu()
    c = _cekirdek(bus, tmp_path)

    def patla(self, *a, **k):
        raise RuntimeError("test: ofset patladı")

    monkeypatch.setattr(mo.MlxOfset, "pencere", patla)
    monkeypatch.setattr(mo.MlxOfset, "duty_yankisi", patla)
    c._handle_stm_line(SIFIR)
    c._handle_stm_line(
        "-> STM_TELE: C=6,B=0.381,N=360,XN=-0.070,XP=-0.010,YN=0.150,YP=0.210,ZN=-0.310,ZP=-0.250,GS=0,RS=0"
    )
    son = bus.hepsi("hardware.stm.telemetry")[-1][1]
    assert son["magnetic_field"] == pytest.approx(0.381) and "magnetic_ofset_duzeltildi" not in son
