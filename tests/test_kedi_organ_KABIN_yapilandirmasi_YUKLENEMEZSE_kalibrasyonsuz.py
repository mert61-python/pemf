# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.E08 · İG-5.27 — kabin yapılandırması (YAML) yüklenemezse kedi-organ sonucu KALİBRASYONSUZDUR ve bunu söyler.

KUSUR (D0 İG-5.27, bu oturumda yeniden ölçüldü): paketli kabin YAML'ı yok ya da bozuksa `CatOrganPredictor` sessizce
DEFAULT yapılandırmaya düşüyordu (yalnız konsola bir satır). `cabin_active` YAML'ın yüklenmesine değil yalnız ArUco
bulunmasına bağlıydı → çıktı `calibrated=True`, güven tavansız (0,536), organ 2'nin kabin koordinatı ~84 cm kayık
(-11,3; 28,6; 5,5 → -26,4; -53,7; -3,2 cm). Operatöre hiçbir şey söylenmiyordu.

DÜZELTME BEKLENTİSİ: YAML yüklenemezse `calibrated=False`, kalibrasyonsuz güven TAVANI (0,25 — mevcut tek formül
`guven_dokumu_hesapla`), DEFAULT geometriden kabin koordinatı ÜRETİLMEZ ve sonuç/yanıt bunu açıkça bildirir. 1-C'nin
kabin sınırı (fail-closed) ile tutarlı: AI Pro hedefi doğrulanamaz → sürülmez, operatöre EYLEM söyleyen bildirim.

YÖNTEM: GERÇEK öngörücü + GERÇEK `estimate_organs_pnp` + GERÇEK ArUco algılama (paketli sentetik ArUco görüntüsü);
yalnız iki ONNX koşucusu (segmentasyon, poz) kanonik iskeletten türetilmiş anahtar noktalarla sahtedir (modeller bu
yalıtılmış ortamda yok). Kamera açılmaz, ağa çıkılmaz.
"""

from __future__ import annotations

import base64
import os

import capraz
import numpy as np
import pytest

cv2 = capraz.paket_yoksa_atla("cv2")

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG = os.path.join(KOK, "ai_hub", "inference_cat_organ", "test_img", "synthetic_aruco_test.jpg")


@pytest.fixture
def ongorucu(monkeypatch, tmp_path):
    """kol ∈ {"var", "yok", "bozuk", "gercek_yok"} → GERÇEK CatOrganPredictor (yalnız ONNX koşucuları sahte).

    ⚠️ İNCELEME-2 i5-F-1: "yok" kolu `varsayilan_kabin_yaml`ı var OLMAYAN BİR YOLA yamalar (istisna dalı); üründe paketli
    dosya gerçekten yoksa işlev None döner ve istisna HİÇ oluşmaz → "gercek_yok" modülün KENDİ varsayılan yolunu yok eder."""
    from ai_hub.inference_cat_organ import catorgan_predictor as cp
    from ai_hub.inference_cat_organ.lib import cabin_config as lcc
    from ai_hub.inference_cat_organ.lib import runners
    from ai_hub.inference_cat_organ.lib.canonical import KEYPOINT_NAMES
    from ai_hub.inference_cat_organ.lib.geometry import CANONICAL_CAT_3D

    h, w = cv2.imread(IMG).shape[:2]
    xs = np.array([CANONICAL_CAT_3D[n][0] for n in KEYPOINT_NAMES])
    ys = np.array([CANONICAL_CAT_3D[n][1] for n in KEYPOINT_NAMES])
    s = 0.5 * w / (xs.max() - xs.min())
    u = (xs - xs.min()) * s + 0.25 * w
    v = (-(ys - ys.max())) * s + 0.30 * h
    kp = np.column_stack([u, v, np.full(len(u), 0.9)])
    bbox = [float(u.min()) - 10, float(v.min()) - 10, float(u.max()) + 10, float(v.max()) + 10]
    monkeypatch.setattr(runners, "run_yolo_segmentation", lambda p, device="cpu": {"bbox": bbox, "n_detections": 1})
    # FK · K1: `run_pose` kedi (segmentasyon) kutusunu da alır (`kedi_kutusu=`) — sahte imza onu kabul eder.
    monkeypatch.setattr(runners, "run_pose", lambda p, device="cpu", **_k: {"keypoints": kp})
    monkeypatch.setattr(cp.CatOrganPredictor, "_resolve_models", lambda self, d: None)
    gercek_yaml = cp.varsayilan_kabin_yaml()

    def _kur(kol: str):
        if kol == "gercek_yok":
            monkeypatch.setattr(lcc, "DEFAULT_CONFIG_YAML", tmp_path / "paketli_yok" / "cabin_config_example.yaml")
            assert cp.varsayilan_kabin_yaml() is None, "aparat: paketli kabin YAML yolu hâlâ çözülüyor"
        elif kol == "yok":
            monkeypatch.setattr(cp, "varsayilan_kabin_yaml", lambda: str(tmp_path / "yok_kabin.yaml"))
        elif kol == "bozuk":
            bozuk = tmp_path / "bozuk_kabin.yaml"
            bozuk.write_text("geometry: [kapanmayan\n  : :", encoding="utf-8")
            monkeypatch.setattr(cp, "varsayilan_kabin_yaml", lambda: str(bozuk))
        else:
            monkeypatch.setattr(cp, "varsayilan_kabin_yaml", lambda: gercek_yaml)
        return cp.CatOrganPredictor(device="cpu")

    return _kur


@pytest.mark.parametrize("kol", ["yok", "bozuk", "gercek_yok"])
def test_KRITIK_DE08_yaml_YUKLENEMEZSE_kalibrasyonsuz_tavanli_ve_bildirir(ongorucu, kol):
    p = ongorucu(kol)
    r = p.predict(IMG, render=False)
    org = r.get("organs") or {}
    assert org, "aparat: öngörücü organ üretmedi"
    kalibre = {o.get("calibrated") for o in org.values()}
    assert kalibre == {False}, f"kabin YAML'ı {kol} ama sonuç 'kalibre' diyor: {kalibre}"
    rels = [float(o.get("reliability") or 0.0) for o in org.values()]
    assert max(rels) <= 0.25 + 1e-9, f"kalibrasyonsuz güven tavanı uygulanmadı: max {max(rels):.3f}"
    sahte = {oid: o.get("coord_cabin_cm") for oid, o in org.items() if o.get("coord_cabin_cm") is not None}
    assert not sahte, f"DEFAULT geometriden kabin koordinatı üretildi (kayık hedef): {sahte}"
    ky = r.get("kabin_yapilandirmasi") or {}
    assert ky.get("yuklendi") is False and ky.get("hata"), f"sonuç yüklenemeyen yapılandırmayı bildirmiyor: {ky}"


def test_KARSIT_DE08_yaml_VARSA_kalibre_ve_kabin_koordinati_var(ongorucu):
    p = ongorucu("var")
    r = p.predict(IMG, render=False)
    org = r.get("organs") or {}
    assert {o.get("calibrated") for o in org.values()} == {True}, "aparat: ArUco'lu görüntü kalibre olmalı"
    assert all(o.get("coord_cabin_cm") is not None for o in org.values())
    assert (r.get("kabin_yapilandirmasi") or {}).get("yuklendi") is True


@pytest.mark.parametrize("kol", ["yok", "bozuk", "gercek_yok"])
def test_KRITIK_DE08_AI_Pro_hedefi_DOGRULANAMAZ_ve_operatore_EYLEM_soylenir(ongorucu, monkeypatch, kol):
    """AI Pro lokalizasyonu: hedef SÜRÜLEMEZ (localized False) ve 1-C'nin kabin bildirimi (eylem söyler) çıkar."""
    from servers import ai_router as air
    from servers import api_server as api

    p = ongorucu(kol)
    monkeypatch.setattr(air, "_get_or_load_catorgan", lambda: p)
    bildirim: list = []
    monkeypatch.setattr(api, "_push_notification", lambda m, t="info": bildirim.append((m, t)))
    monkeypatch.setattr(air, "_kabin_okunamaz_bildirilen", {"anahtar": "<test-öncesi>"})
    lz, *_ = air._localize_organ_cpu(cv2.imread(IMG), 2)
    assert lz is False, "kabin yapılandırması yüklenemezken AI Pro hedefi 'bulundu' sayıldı (kayık hedefe sürüş)"
    assert any("kabin yapılandırması" in m for m, _t in bildirim), f"operatöre bildirim yok: {bildirim}"


@pytest.mark.parametrize("kol", ["yok", "bozuk", "gercek_yok"])
def test_KRITIK_DE08_AI_Hub_yaniti_KALIBRASYONSUZ_oldugunu_soyler(ongorucu, monkeypatch, kol):
    from fastapi.testclient import TestClient
    from servers import ai_router as air
    from servers import api_server as api

    p = ongorucu(kol)
    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    monkeypatch.setattr(air, "_get_or_load_model", lambda ad, yukle: p)
    ok, buf = cv2.imencode(".jpg", cv2.imread(IMG))
    assert ok
    r = TestClient(api.app).post("/api/ai/vision/cat_organ", data={"image_base64": base64.b64encode(buf).decode()})
    assert r.status_code == 200, r.text[:200]
    j = r.json()
    assert j.get("kabin_uyarisi"), f"AI Hub yanıtı kalibrasyonsuz olduğunu SÖYLEMİYOR: {sorted(j)[:20]}"
    assert {o.get("calibrated") for o in j.get("organs") or []} == {False}


def test_KARSIT_DE08_AI_Hub_yaniti_YAML_varken_uyari_TASIMAZ(ongorucu, monkeypatch):
    from fastapi.testclient import TestClient
    from servers import ai_router as air
    from servers import api_server as api

    p = ongorucu("var")
    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    monkeypatch.setattr(air, "_get_or_load_model", lambda ad, yukle: p)
    ok, buf = cv2.imencode(".jpg", cv2.imread(IMG))
    r = TestClient(api.app).post("/api/ai/vision/cat_organ", data={"image_base64": base64.b64encode(buf).decode()})
    assert r.status_code == 200, r.text[:200]
    assert not r.json().get("kabin_uyarisi")


def test_KRITIK_DE08_GPU_yolu_da_DOGRULANAMAZ_ve_bildirir(monkeypatch):
    """GPU profili (`_localize_organ_gpu`): servis aynı öngörücüyü koşar ve `kabin_uyarisi` döner → CPU yoluyla aynı."""
    from servers import ai_router as air
    from servers import api_server as api

    yanit = {
        "status": "success",
        "organs": [{"id": 2, "coord_3d_cm": [1.0, 2.0, 3.0], "reliability": 0.9, "calibrated": False}],
        "kabin_uyarisi": "Kabin yapılandırması yüklenemedi — test",
    }
    monkeypatch.setattr(air, "delegate_infer_sync", lambda *a, **k: yanit)
    bildirim: list = []
    monkeypatch.setattr(api, "_push_notification", lambda m, t="info": bildirim.append((m, t)))
    monkeypatch.setattr(air, "_kabin_okunamaz_bildirilen", {"anahtar": "<test-öncesi>"})
    lz, *_ = air._localize_organ_gpu(cv2.imread(IMG), 2)
    assert lz is False, "GPU yolunda kalibrasyonsuz (güveni yüksek bildirilmiş) hedef 'bulundu' sayıldı"
    assert any("kabin yapılandırması" in m for m, _t in bildirim), bildirim
