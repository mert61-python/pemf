# -*- coding: utf-8 -*-
"""AI1.K3 — AI Pro güven dökümü kedi organ hattının KALİTE ara çıktılarını da taşır (hoca kedi organ v2 `ara_ciktilar`).

KAYNAK: hoca `inference_cat_organ_v2.py` (`ozet.csv`: poz, poz_guven, pnp_hata_px, ayna_uyarisi, anatomik_gecti, anatomik_skor; `organs.json`
"ara_ciktilar", schema v2.2 — v1 alanları aynı, ekleme); zip SHA-256 0285b1d969f8.

ÖLÇÜLEN DURUM (2026-10-11, `DUZELTME-AI1.md` K3): `_localize_organ_cpu` / `_localize_organ_gpu` güven dökümüne yalnız organın
`reliability_components`'ını (poz güveni × derinlik × maske × belirsizlik + kalibrasyon tavanı) koyuyordu; hattın poz TÜRÜ, PnP (keypoint)
uyum hatası, ayna uyarısı ve anatomik kontrol sonucu predictor sonucunda (CPU) / servis yanıtında (GPU) VARDI ama AI Pro paneline hiç
ulaşmıyordu — operatör düşük güvenin "kötü poz / ayna belirsizliği / anatomik tutarsızlık"tan geldiğini göremiyordu.
DÜZELTME: dökümün KOPYASINA yalnız-ek alanlar (`poz_turu`, `pnp_hata_px`, `ayna_uyarisi`, `anatomik_gecti`, `anatomik_skor`); iki yol
AYNI alanları üretir (parite). Güven, konum, sürüş DEĞİŞMEZ; görsel kaydedilmez (Faz 0 #3).
"""

from __future__ import annotations

import copy

import numpy as np
import pytest

DOK = {
    "pose_confidence": 0.7,
    "depth_factor": 0.95,
    "mask_factor": 1.0,
    "uncertainty_factor": 0.93,
    "calibration_cap": None,
}
HAT = {
    "poz_turu": "sphinx",
    "pnp_hata_px": 119.2,
    "ayna_uyarisi": True,
    "anatomik_gecti": False,
    "anatomik_skor": 0.667,
}


def _organlar():
    return {2: {"coord_cabin_cm": [5.0, -3.0, 2.0], "reliability": 0.62, "reliability_components": dict(DOK)}}


@pytest.fixture
def air(monkeypatch):
    from servers import ai_router

    monkeypatch.setattr(ai_router, "ai_service_enabled", lambda: False)
    return ai_router


def _cpu(air, monkeypatch, sonuc):
    class _Clf:
        def predict(self, yol, render=False, target_oid=None):
            return sonuc

    monkeypatch.setattr(air, "_get_or_load_catorgan", lambda: _Clf())
    return air._localize_organ_cpu(np.zeros((8, 8, 3), np.uint8), 2)


def _cpu_sonucu(organlar):
    return {
        "organs": organlar,
        "pose_classifier": {"type": "sphinx", "confidence": 0.7},
        "pnp_fit": {"residual_px": 119.214, "mirror_warning": True, "n_keypoints_used": 32},
        "anatomic_consistency": {"passed": False, "score": 0.667},
        "kabin_yapilandirmasi": {"yuklendi": True, "hata": None},
        "_overlay_bgr": None,
    }


def _gpu_yaniti():
    o = _organlar()[2]
    return {
        "organs": [{"id": 2, **copy.deepcopy(o)}],
        "pose_type": "sphinx",
        "pnp_residual_px": 119.2,
        "mirror_warning": True,
        "anatomic_consistency": {"passed": False, "score": 0.667},
        "kabin_uyarisi": None,
        "image_base64": None,
    }


def test_KRITIK_K3_CPU_yolu_dokume_HAT_kalitesini_ekler_organ_sozlugu_DEGISMEZ(air, monkeypatch):
    organlar = _organlar()
    r = _cpu(air, monkeypatch, _cpu_sonucu(organlar))
    assert r[7] == {**DOK, **HAT}, f"güven dökümü hattın poz/PnP/ayna/anatomik ara çıktılarını taşımıyor: {r[7]}"
    assert organlar[2]["reliability_components"] == DOK, "organın kendi dökümü YERİNDE değiştirildi (yan etki)"


def test_KRITIK_K3_GPU_yolu_CPU_ile_AYNI_dokum_PARITE(air, monkeypatch):
    cpu = _cpu(air, monkeypatch, _cpu_sonucu(_organlar()))
    monkeypatch.setattr(air, "delegate_infer_sync", lambda *a, **k: _gpu_yaniti())
    gpu = air._localize_organ_gpu(np.zeros((8, 8, 3), np.uint8), 2)
    assert gpu[7] == cpu[7], f"GPU yolu güven dökümü CPU'dan farklı (parite): GPU {gpu[7]} ↔ CPU {cpu[7]}"


def test_KARSIT_K3_guven_konum_surus_DEGISMEZ_ve_eski_yanitta_dusmez(air, monkeypatch):
    r = _cpu(air, monkeypatch, _cpu_sonucu(_organlar()))
    taban = air._extract_organ_target(_organlar(), 2, None)
    assert r[:5] == taban[:5] and r[6] == taban[6], (
        f"ek döküm lokalizasyon/güven/konumu DEĞİŞTİRDİ: {r[:5]} ↔ {taban[:5]}"
    )
    # Eski GPU servisi (alanlar YOK) → döküm bileşenleri aynen, hat alanları boş; istisna YOK.
    monkeypatch.setattr(
        air, "delegate_infer_sync", lambda *a, **k: {"organs": [{"id": 2, **_organlar()[2]}], "image_base64": None}
    )
    eski = air._localize_organ_gpu(np.zeros((8, 8, 3), np.uint8), 2)
    assert {k: eski[7][k] for k in DOK} == DOK and eski[7]["poz_turu"] is None and eski[7]["anatomik_gecti"] is None
    assert eski[:5] == taban[:5]


def test_KARSIT_K3_organ_dokumu_YOKSA_hat_eklenmez(air, monkeypatch):
    """Tüm Vücut (organ 0) ve dökümsüz organda döküm None kalır — panel satırı yine gizli (eski sözleşme)."""
    s = _cpu_sonucu({2: {"coord_cabin_cm": [5.0, -3.0, 2.0], "reliability": 0.62}})
    assert _cpu(air, monkeypatch, s)[7] is None

    class _Clf:
        def predict(self, yol, render=False, target_oid=None):
            return _cpu_sonucu(_organlar())

    monkeypatch.setattr(air, "_get_or_load_catorgan", lambda: _Clf())
    assert air._localize_organ_cpu(np.zeros((8, 8, 3), np.uint8), 0)[7] is None
