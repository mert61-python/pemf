# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI PRO GÜVEN DÖKÜMÜ — sunum-katmanı XAI, Faz 1 kalem 2 (docs/xai-entegrasyon-plani.md §4/1.5).

ÖLÇÜLEN DURUM: cat_organ pipeline'ı reliability'yi 4 bileşenden (poz güveni × derinlik ×
maske-cezası × belirsizlik) + kalibrasyonsuz 0.25 tavanından hesaplıyor ama TEK skalara
indirgeyip bileşenleri ATIYOR; AI Pro panelinde "Güven %62" NEDENSİZ görünüyor (operatör
düşük güvenin poz mu, maske-dışı mı, kalibrasyonsuzluk mu olduğunu ayırt edemiyor).

DÜZELTME: pipeline'da tek-formül-kaynağı `guven_dokumu_hesapla` helper'ı (reliability +
bileşen sözlüğü) → entry'ye `reliability_components`; `_extract_organ_target` 8. eleman
olarak dökümü taşır (ESKİ 7'li tuple mock'ları KIRILMAZ — tüketiciler *ekstra ile açar);
cache + /status + /frame yanıtına `guvenDokumu`.
"""

import time

import numpy as np
import pytest
from fastapi.testclient import TestClient


# ── 1) Formül tek-kaynağı: helper ────────────────────────────────────────────
def test_KRITIK_guven_dokumu_formulu_reliability_ile_TUTARLI():
    from ai_hub.inference_cat_organ.lib.pipeline import guven_dokumu_hesapla

    # maske İÇİ + kalibreli: rel = poz × derinlik × 1.0 × belirsizlik (tavan yok)
    rel, dok = guven_dokumu_hesapla(0.9, 0.8, True, 2.0, True)
    beklenen = 0.9 * 0.8 * 1.0 * (1.0 - 2.0 / 10.0)
    assert abs(rel - beklenen) < 1e-9, f"formül bileşen çarpımıyla uyuşmuyor: {rel} != {beklenen}"
    carpim = dok["pose_confidence"] * dok["depth_factor"] * dok["mask_factor"] * dok["uncertainty_factor"]
    assert abs(rel - carpim) < 5e-3, "döküm bileşenlerinin çarpımı reliability'yi YENİDEN ÜRETMİYOR"
    assert dok["calibration_cap"] is None

    # maske DIŞI cezası ×0.6
    rel2, dok2 = guven_dokumu_hesapla(0.9, 0.8, False, 2.0, True)
    assert abs(rel2 - beklenen * 0.6) < 1e-9
    assert dok2["mask_factor"] == 0.6

    # belirsizlik clip alt sınırı 0.4 (cm_sd=9 → 0.1 DEĞİL 0.4... hayır: 1-9/10=0.1 → clip 0.4)
    _, dok3 = guven_dokumu_hesapla(0.9, 0.8, True, 9.0, True)
    assert dok3["uncertainty_factor"] == pytest.approx(0.4)


def test_KRITIK_kalibresiz_tavan_UYGULANIR_ve_dokumde_GORUNUR():
    """Audit P2 tavanı: kalibresizken rel ≤ 0.25 VE operatör tavanı dökümde görür."""
    from ai_hub.inference_cat_organ.lib.pipeline import guven_dokumu_hesapla

    rel, dok = guven_dokumu_hesapla(0.95, 1.0, True, 0.5, False)
    assert rel <= 0.25 + 1e-9, "kalibrasyonsuz tavan (Audit P2) helper'da uygulanmıyor"
    assert dok["calibration_cap"] == 0.25, "tavan dökümde raporlanmıyor — düşük güvenin nedeni gizli"


def test_KARSIT_KANIT_kalibreli_tavan_YOK():
    from ai_hub.inference_cat_organ.lib.pipeline import guven_dokumu_hesapla

    rel, dok = guven_dokumu_hesapla(0.95, 1.0, True, 0.5, True)
    assert rel > 0.25, "kalibreliyken tavan uygulanmamalı"
    assert dok["calibration_cap"] is None


# ── 2) _extract_organ_target 8. eleman ───────────────────────────────────────
def _organ(rel, dok=None):
    o = {"coord_3d_cm": [1.0, 2.0, 3.0], "reliability": rel}
    if dok is not None:
        o["reliability_components"] = dok
    return o


def test_KRITIK_extract_organ_target_dokumu_TASIR():
    import servers.ai_router as air

    dok = {
        "pose_confidence": 0.9,
        "depth_factor": 0.8,
        "mask_factor": 1.0,
        "uncertainty_factor": 0.9,
        "calibration_cap": None,
    }
    sonuc = air._extract_organ_target({3: _organ(0.65, dok)}, 3, None)
    assert len(sonuc) == 8, "tuple 8'e genişletilmedi (guven_dokumu eksik)"
    assert sonuc[7] == dok, "seçili organın reliability_components'ı taşınmadı"


def test_KARSIT_KANIT_extract_dokumsuz_organ_None():
    """Eski pipeline çıktısı (components'sız) veya organ_id=0 → döküm None; akış kırılmaz."""
    import servers.ai_router as air

    assert air._extract_organ_target({3: _organ(0.65)}, 3, None)[7] is None
    assert air._extract_organ_target({3: _organ(0.9, {"x": 1})}, 0, None)[7] is None  # Tüm Vücut
    assert air._extract_organ_target({}, 3, None)[7] is None


# ── 3) uçtan uca: cache → /status ────────────────────────────────────────────
@pytest.fixture()
def air_env(monkeypatch):
    import servers.ai_router as air
    import servers.api_server as apis

    snap = dict(air._ai_organ_cache)
    air._ai_organ_cache.update(
        {
            "at": 0.0,
            "organ_id": -1,
            "localized": False,
            "kedi_var": False,
            "x_mm": 0.0,
            "y_mm": 0.0,
            "z_mm": 0.0,
            "reliability": 0.0,
            "overlay_bgr": None,
            "guven_dokumu": None,
        }
    )
    air._ai_loop_active = False
    air._ai_hazirlik_active = False
    monkeypatch.setattr(air.cv2, "VideoCapture", _FakeCap)
    monkeypatch.setattr(air, "_get_or_load_kedi", lambda: None)
    monkeypatch.setattr(air, "_get_or_load_catorgan", lambda: None)
    monkeypatch.setattr(air, "_drive_coils_ai_pro", lambda D, P: None)
    yield air, TestClient(apis.app)
    air._ai_hazirlik_durdur_ic()
    air._ai_organ_cache.clear()
    air._ai_organ_cache.update(snap)


class _FakeCap:
    def __init__(self, *a):
        pass

    def isOpened(self):
        return True

    def read(self):
        return True, np.zeros((8, 8, 3), dtype=np.uint8)

    def release(self):
        pass


def _lokalize_bekle(air, timeout=3.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if bool(air._ai_organ_cache.get("localized")):
            return True
        time.sleep(0.05)
    return False


_DOK = {
    "pose_confidence": 0.74,
    "depth_factor": 0.9,
    "mask_factor": 0.6,
    "uncertainty_factor": 0.85,
    "calibration_cap": None,
}


def test_KRITIK_status_guven_dokumu_DONER(air_env, monkeypatch):
    air, client = air_env
    monkeypatch.setattr(air, "_localize_organ", lambda f, o: (True, 10.0, 20.0, 30.0, 0.34, None, True, _DOK))
    client.post("/api/ai/pro/hazirlik/baslat", json={"organ_id": 3})
    assert _lokalize_bekle(air)
    r = client.get("/api/ai/pro/status")
    assert r.status_code == 200
    assert r.json().get("guvenDokumu") == _DOK, (
        "lokalizasyon dökümü /status'a taşınmadı — panel 'Güven %X'in NEDENİNİ gösteremez"
    )


def test_KARSIT_KANIT_eski_7li_tuple_mock_KIRILMAZ(air_env, monkeypatch):
    """Geriye uyumluluk: 7'li tuple (eski imza) hâlâ çalışır, döküm None kalır."""
    air, client = air_env
    monkeypatch.setattr(air, "_localize_organ", lambda f, o: (True, 10.0, 20.0, 30.0, 0.9, None, True))
    client.post("/api/ai/pro/hazirlik/baslat", json={"organ_id": 3})
    assert _lokalize_bekle(air), "7'li tuple ile lokalizasyon KIRILDI (geriye uyumluluk yok)"
    r = client.get("/api/ai/pro/status")
    assert r.json().get("guvenDokumu") is None


# ── 4) yapısal: pipeline entry + frame yanıtı ────────────────────────────────
def test_YAPISAL_pipeline_entry_dokumu_yazar():
    from pathlib import Path

    import ai_hub.inference_cat_organ.lib.pipeline as plp

    src = Path(plp.__file__).read_text(encoding="utf-8", errors="replace")
    i = src.index("def estimate_organs_pnp")
    govde = src[i:]
    assert "guven_dokumu_hesapla(" in govde, "pipeline reliability'yi helper'dan HESAPLAMIYOR (çift formül riski)"
    assert '"reliability_components"' in govde, "entry'ye reliability_components yazılmıyor"


def test_YAPISAL_frame_yaniti_dokumu_tasir():
    from pathlib import Path

    import servers.ai_router as air

    src = Path(air.__file__).read_text(encoding="utf-8", errors="replace")
    i = src.index('post("/api/ai/ai_pro/frame")')
    govde = src[i : i + 12000]
    assert '"guvenDokumu"' in govde, "mobil /frame yanıtı güven dökümünü taşımıyor (web/mobil paritesi)"
