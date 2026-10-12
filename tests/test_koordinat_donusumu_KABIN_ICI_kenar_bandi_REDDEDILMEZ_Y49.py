# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.100 incelemesi (İNCELEME-2 i5-F-3 · Y49 · Ö.4-Y9) — kabin dışı reddi kabin İÇİNDEKİ kenar bandını REDDETMEZ.

ÖLÇÜLEN KÖRLÜK (`60567e4`): D1.100'ün kabin sınırı mutantla daraltıldığında (`yari = min(300, extent/2)` — fantom/petri'de
kabin içindeki x ∈ (300, 325] bandına YENİ red) mevcut 21 kapı dosyası 319/319 YEŞİL kaldı: bilinen nokta ızgarası en çok
yarı boyutun %70'ini (|x| ≤ 227,5 mm) dener, İG-5.72 taraması yalnız "dışarıda nokta yok"u ölçer. Sahip kararı Y49: kabin
içindeki bu bantta yeni red ya da kıskaç EKLENMEZ; D1.100'ün ölçütü D1.85 ile aynıdır (`|a| > cabin_extent/2` → dışarı).

ZEMİN GERÇEĞİ: ÜRÜN yapılandırması (`phantom_cv` / `petri_cv` `load_cabin_config(None)`, ürünün çağırdığı gibi) + tutarlı
fiziksel poz — kamera modeli P_cam = R_cc·(P − C); ürün dönüşümünün tanımı P_kabin = R_axis·Rᵀ(P_cam − t) + m olduğundan
R = R_cc·R_axis, t = R_cc·(m − C). Hedef → piksel (bozulmasız K) → ÜRÜN `pixel_to_cabin_mm`. İki ayrı kamera pozu.
"""

from __future__ import annotations

import importlib

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

# AI-2 C6: v1 `phantom_cv` / `petri_cv` emekli → hocanın v3 / v2'si (ürün yükleyicilerinin profili).
PROFILLER = ["inference_em_fantom.phantom_cv_v3", "inference_petri_dish.petri_cv_v2"]


def _bak(C, hedef, yukari):
    z = np.asarray(hedef, float) - np.asarray(C, float)
    z /= np.linalg.norm(z)
    x = np.cross(z, np.asarray(yukari, float))
    x /= np.linalg.norm(x)
    return np.vstack([x, np.cross(z, x), z])


def _kurulum(ct, cfg, C, hedef, yukari):
    R_axis = ct._marker_to_cabin_R(cfg)
    marker = -np.asarray(cfg.geometry.qr_to_origin_mm, float)
    m = marker + np.asarray(ct._axis_vec(cfg.aruco.normal_axis_in_cabin), float) * (cfg.aruco.plane_offset_cm * 10.0)
    R_cc = _bak(C, hedef, yukari)
    R = R_cc @ R_axis
    t = R_cc @ (m - np.asarray(C, float))
    K = np.array([[900.0, 0, 2000.0], [0, 900.0, 2000.0], [0, 0, 1.0]])
    intr = ct.CameraIntrinsics(K=K, D=np.zeros(5), image_size=(4000, 4000), rms=0.0)
    rvec, _ = cv2.Rodrigues(R)
    poz = ct.CabinPose(
        marker_id=0, rvec=rvec, tvec=t.reshape(3, 1), R=R, reproj_error_px=0.0, marker_pos_cabin_mm=marker
    )
    return R_cc, np.asarray(C, float), K, intr, poz


def _cevir(ct, cfg, kur, P):
    R_cc, C, K, intr, poz = kur
    pc = R_cc @ (np.asarray(P, float) - C)
    assert pc[2] > 0, "aparat: nokta kameranın arkasında"
    uv = K @ (pc / pc[2])
    return ct.pixel_to_cabin_mm((float(uv[0]), float(uv[1])), poz, intr, cfg)


@pytest.fixture(params=PROFILLER)
def profil(request):
    ct = importlib.import_module("ai_hub.cv_ortak.coord_transform")
    cfg = importlib.import_module(f"ai_hub.{request.param}").load_cabin_config(None)
    eksen = cfg.phantom_plate.hedef_duzlem_indeksi
    duzlem = float(cfg.phantom_plate.hedef_duzlem_mm)
    yari = [float(v) * 10.0 / 2.0 for v in cfg.geometry.cabin_extent_cm]
    assert eksen == 1 and yari == [325.0, 250.0, 250.0], f"aparat: ürün kabini beklenen değil ({eksen}, {yari})"
    hedef = [0.0, duzlem, 0.0]
    pozlar = [
        _kurulum(ct, cfg, [0.0, duzlem + 1400.0, 0.0], hedef, (0.0, 0.0, 1.0)),
        _kurulum(ct, cfg, [400.0, duzlem + 1100.0, 700.0], hedef, (0.0, 1.0, 0.0)),
    ]
    return ct, cfg, duzlem, pozlar


@pytest.mark.parametrize("x", [301.0, 310.0, 324.5, -324.5])
def test_KARSIT_Y49_kabin_ICI_x_kenar_bandi_KABUL_ve_DOGRU(profil, x):
    ct, cfg, duzlem, pozlar = profil
    for kur in pozlar:
        P = np.array([x, duzlem, 0.0])
        q = _cevir(ct, cfg, kur, P)  # KesisimGecersiz fırlatırsa: kabin İÇİ hedefe YENİ red (Y49 ihlali)
        assert float(np.linalg.norm(q - P)) < 0.05, f"kabin içi nokta yanlış çözüldü: {P} → {q}"


@pytest.mark.parametrize("z", [249.5, -249.5])
def test_KARSIT_kabin_ICI_z_kenar_bandi_KABUL(profil, z):
    ct, cfg, duzlem, pozlar = profil
    for kur in pozlar:
        P = np.array([0.0, duzlem, z])
        q = _cevir(ct, cfg, kur, P)
        assert float(np.linalg.norm(q - P)) < 0.05, f"{P} → {q}"


@pytest.mark.parametrize("P", [(325.5, 0.0, 0.0), (-325.5, 0.0, 0.0), (0.0, 0.0, 250.5)])
def test_KRITIK_kabin_HEMEN_DISI_RET_kol_bos_gecmez(profil, P):
    """Aynı aparatla kabinin 0,5 mm dışı RET — yukarıdaki KABUL kolları ölçütün kendisini (sınır 325/250) ölçüyor."""
    ct, cfg, duzlem, pozlar = profil
    for kur in pozlar:
        with pytest.raises(ct.KesisimGecersiz):
            _cevir(ct, cfg, kur, np.array([P[0], duzlem, P[2]]))
