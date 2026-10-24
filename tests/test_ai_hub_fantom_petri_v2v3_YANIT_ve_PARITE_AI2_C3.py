# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI-2 C3 — AI Hub fantom / petri uçları hocanın v3 / v2'siyle: mevcut alanlar KORUNUR, yeni alanlar EKLENİR, GPU servisi AYNI.

Mevcut sözleşme (eski istemci): `n_tumor`, `tumor_regions`, `n_wells`, `wells`, `centroid_cabin_mm`, `D`, `E_cancer`, `mm_per_px`.
Yeni (yalnız ek): kuyucuk / tümörde `well_id` / `tumor_id`; üst düzeyde `pemf_valid`, `reliable` (fantom), `warnings`,
`pemf_source`, `coord_frame` ve `pemf_kapisi` (hocanın ENTEGRASYON §3 tüketim kontrolü + eylem söyleyen metin + laboratuvar
VARSAYIMLARI — tek kaynak `ai_hub/cv_ortak/pemf_kapisi.py`). Petri ucuna kip / protokol parametreleri: `plate_type`
(0 = tekil petri kapları), `control_healthy`, `control_cancer`, `a1_corner` (doğrulama `petri_ayar`).

PARİTE: gömülü uç (`ai_router`) ile GPU servisi (`ai_service/app.py`) aynı görüntüde AYNI alan kümesini ve AYNI kapı kararını
döndürür (bu deponun beş kez ölçülen arıza sınıfı: `app.py`'ye eklenmeyen alan GPU dağıtımında sessizce kaybolur).
Gerçek ağırlıklı (`golden.eser`: yoksa ATLA, `PEMF_GOLDEN_REQUIRED=1`'de DÜŞ).
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

KAHIN = Path(__file__).resolve().parent / "kahin" / "hoca_cv_2026_10"
FANTOM = KAHIN / "fantom" / "WhatsApp Image 2026-10-02 at 19.40.11.jpeg"
PLAKA = KAHIN / "petri" / "WhatsApp Image 2026-10-02 at 19.40.15(2).jpeg"
TEKIL = KAHIN / "petri" / "real_petri.jpg"
_ESKI_ALANLAR_FANTOM = {"n_tumor", "tumor_regions", "mm_per_px", "method", "success", "error", "healthy_regions"}
_ESKI_ALANLAR_PETRI = {"n_wells", "wells", "mm_per_px", "method", "success", "error", "n_cancer", "plausibility"}
_YENI_ORTAK = {"pemf_valid", "warnings", "coord_frame", "pemf_source", "pemf_kapisi"}
_PETRI_EYLEM = (
    "PEMF değerleri geçersiz: plakanın kabindeki konumu bilinmiyor — kabine ArUco koyun ya da konumu ayarlayın."
)


def _b64(yol: Path) -> str:
    return base64.b64encode(yol.read_bytes()).decode()


@pytest.fixture(scope="module")
def onbellek():
    """Router'ın KENDİ yükleyicileriyle (v3 / v2) gerçek önbellek — gömülü uç ve servis aynı nesneleri kullanır."""
    from golden.eser import atla, eser_var_mi

    yollar = (
        "ai_hub/inference_em_fantom/BiLSTM_XXL_Raw.onnx",
        "ai_hub/inference_em_petri/BaggingRegressor.onnx",
        "ai_hub/inference_petri_dish/yolo11m-seg.onnx",
    )
    if not eser_var_mi(*yollar):
        atla(f"fantom / petri ağırlıkları ürün çözücüsünde yok {list(yollar)}")
    pytest.importorskip("ultralytics")
    import servers.ai_router as air

    return {"em_fantom_cv": air._yukle_em_fantom_cv(), "em_petri_cv": air._yukle_em_petri_cv()}


@pytest.fixture()
def gomulu(onbellek, monkeypatch):
    import servers.ai_router as air
    import servers.api_server as api
    from fastapi.testclient import TestClient

    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    monkeypatch.setattr(air, "_get_or_load_model", lambda ad, y: onbellek[ad])
    api.app.dependency_overrides[air.require_research] = lambda: None
    try:
        yield TestClient(api.app)
    finally:
        api.app.dependency_overrides.pop(air.require_research, None)


@pytest.fixture()
def servis(onbellek, monkeypatch):
    from fastapi.testclient import TestClient

    from ai_service import app as svc

    harita = {"em_fantom": onbellek["em_fantom_cv"], "em_petri": onbellek["em_petri_cv"]}
    monkeypatch.setattr(svc.predictors, "get", lambda ad: harita[ad])
    return TestClient(svc.app)


def test_KRITIK_fantom_ESKI_alanlar_KORUNUR_YENI_alanlar_EKLENIR(gomulu):
    r = gomulu.post("/api/ai/vision/em_fantom", data={"image_base64": _b64(FANTOM)})
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert _ESKI_ALANLAR_FANTOM <= set(j), sorted(_ESKI_ALANLAR_FANTOM - set(j))
    assert _YENI_ORTAK | {"reliable", "layout"} <= set(j), sorted((_YENI_ORTAK | {"reliable"}) - set(j))
    assert j["n_tumor"] == 5 and [t["tumor_id"] for t in j["tumor_regions"]] == ["T1", "T2", "T3", "T4", "T5"]
    for t in j["tumor_regions"]:
        assert len(t["centroid_cabin_mm"]) == 3 and len(t["D"]) == 7 and t["E_cancer"] is not None
    assert j["reliable"] is True and j["pemf_valid"] is True and j["pemf_source"] == "cst_phantom_box"
    k = j["pemf_kapisi"]
    assert k["surulebilir"] is True and k["nedenler"] == []
    # CST kutusu bir VARSAYIMDIR (laboratuvar maddesi #2) — sürüşü hocanın kuralı engellemez ama ekranda SÖYLENİR.
    assert {v["kod"] for v in k["varsayimlar"]} >= {"pemf_axis_sign_assumed", "halka_capi"}, k["varsayimlar"]


def test_KRITIK_petri_PLAKA_24_kuyucuk_pemf_GECERSIZ_eylem_soyler(gomulu):
    r = gomulu.post("/api/ai/vision/em_petri", data={"image_base64": _b64(PLAKA)})
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert _ESKI_ALANLAR_PETRI <= set(j), sorted(_ESKI_ALANLAR_PETRI - set(j))
    assert _YENI_ORTAK | {"plate", "classification"} <= set(j)
    assert j["n_wells"] == 24 and [w["well_id"] for w in j["wells"]][:3] == ["A1", "A2", "A3"]
    assert j["pemf_valid"] is False and j["coord_frame"] == "plate"
    k = j["pemf_kapisi"]
    assert k["surulebilir"] is False and k["nedenler"][0] == "pemf_gecersiz" and k["eylem"] == _PETRI_EYLEM
    assert {v["kod"] for v in k["varsayimlar"]} == {"a1_kosesi", "kanser_esikleri"}
    assert isinstance(j["plate"]["n_yolo_candidates"], int) and j["yolo_ayar"]["aday_imgsz"] == 640


def test_KRITIK_petri_TEKIL_kip_ve_KONTROL_kuyucuklari_parametreleri(gomulu):
    r = gomulu.post("/api/ai/vision/em_petri", data={"image_base64": _b64(TEKIL), "plate_type": "0"})
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert j["n_wells"] == 8 and [w["well_id"] for w in j["wells"]][0] == "W1" and j["yolo_ayar"]["plate_type"] == 0
    # Kontrol kuyucuğu verilince "eşikler yalnız yapay boyayla" VARSAYIMI düşer (protokol uygulandı).
    r2 = gomulu.post("/api/ai/vision/em_petri", data={"image_base64": _b64(PLAKA), "control_healthy": "a1, d6"})
    j2 = r2.json()
    assert r2.status_code == 200 and j2["classification"]["control_healthy"] == ["A1", "D6"]
    assert "kanser_esikleri" not in {v["kod"] for v in j2["pemf_kapisi"]["varsayimlar"]}


@pytest.mark.parametrize("alan,deger", [("plate_type", "7"), ("control_healthy", "Z9"), ("a1_corner", "orta")])
def test_KRITIK_petri_GECERSIZ_kip_parametresi_422_eylem(gomulu, alan, deger):
    r = gomulu.post("/api/ai/vision/em_petri", data={"image_base64": _b64(PLAKA), alan: deger})
    assert r.status_code == 422, r.text[:200]
    assert alan in r.json()["detail"]


def test_KRITIK_petri_fantom_fotografi_422_PLAKA_degil(gomulu):
    r = gomulu.post("/api/ai/vision/em_petri", data={"image_base64": _b64(FANTOM)})
    assert r.status_code == 422, r.text[:200]
    assert "24 kuyucuklu" in r.json()["detail"] and "Tekil petri kapları" not in r.json()["detail"]  # T3 · Y193


@pytest.mark.parametrize(
    "uc,servis_ucu,yol,alan",
    [
        ("/api/ai/vision/em_fantom", "/infer/em_fantom", FANTOM, "tumor_regions"),
        ("/api/ai/vision/em_petri", "/infer/em_petri", PLAKA, "wells"),
    ],
    ids=["fantom", "petri"],
)
def test_KRITIK_GOMULU_ve_GPU_servisi_AYNI_alanlar_AYNI_kapi(gomulu, servis, uc, servis_ucu, yol, alan):
    a = gomulu.post(uc, data={"image_base64": _b64(yol)}).json()
    b = servis.post(servis_ucu, files={"file": ("x.jpg", yol.read_bytes(), "image/jpeg")}).json()
    yeni = _YENI_ORTAK | (
        {"reliable", "layout", "ring", "phantom_frame"} if alan == "tumor_regions" else {"plate", "classification"}
    )
    assert yeni <= set(a) and yeni <= set(b), (sorted(yeni - set(a)), sorted(yeni - set(b)))
    assert a["pemf_kapisi"] == b["pemf_kapisi"], "gömülü ve GPU servisi farklı kapı kararı verdi"
    assert [r.get("tumor_id", r.get("well_id")) for r in a[alan]] == [
        r.get("tumor_id", r.get("well_id")) for r in b[alan]
    ]
    assert a["warnings"] == b["warnings"] and a["pemf_valid"] == b["pemf_valid"]


# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# MODALİTE KAPISI — hocanın laboratuvar fotoğrafları "H&E" sanılıp REDDEDİLMEZ; gerçek H&E'yi İKİNCİ KATMAN tutar
# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("klasor,etiket", [("petri", "em_petri"), ("fantom", "em_fantom")])
def test_KRITIK_hocanin_LAB_fotograflari_MODALITE_kapisindan_gecer(klasor, etiket):
    """Ölçüldü: plaka 4/6 (stain 0,169–0,229) ve fantom 2/9 (0,151 / 0,153) STAINED algılanıp 422 alıyordu."""
    import cv2
    import numpy as np
    from utils import image_domain as dom

    yollar = sorted((KAHIN / klasor).glob("WhatsApp Image *.jpeg"))
    assert len(yollar) in (6, 9)
    for p in yollar:
        dom.check(cv2.imdecode(np.fromfile(str(p), dtype=np.uint8), cv2.IMREAD_COLOR), etiket)  # fırlatmamalı


def test_KRITIK_HE_preparati_petri_ve_fantom_uclarinda_SONUC_URETMEZ(gomulu):
    """Dürüstlük + bağımlılık kilidi: STAINED bu uçlara açıldığı için H&E'yi modalite DEĞİL ikinci katman tutar —
    petri plaka makulliği (422 `not_a_petri_plate`) ve fantom v3 tümör kümesi (`tumor_cluster_not_found`, sonuç yok).
    Bu katmanlardan biri sökülürse EXPECTED['em_petri'/'em_fantom']'dan STAINED geri çıkarılmalı."""
    import capraz
    from utils import image_domain as dom

    assert dom.STAINED in dom.EXPECTED["em_petri"] and dom.STAINED in dom.EXPECTED["em_fantom"]
    assert dom.EXPECTED["histopath"] == {dom.STAINED}, "patoloji ucunun kabul kümesi değişmemeli"
    for ad in ("08a_BobrekPatoloji_grade0.jpg", "08b_BobrekPatoloji_grade2.jpg", "08c_BobrekPatoloji_grade4.jpg"):
        rel = f"ai_hub/PEMF_AI_Test_Girdileri/{ad}"
        capraz.atla_yoksa(rel)
        yol = capraz.kaynak_yolu(rel)
        rp = gomulu.post("/api/ai/vision/em_petri", data={"image_base64": _b64(yol)})
        assert rp.status_code == 422 and "24 kuyucuklu" in rp.json()["detail"], (ad, rp.status_code, rp.text[:200])
        rf = gomulu.post("/api/ai/vision/em_fantom", data={"image_base64": _b64(yol)})
        assert rf.status_code == 200 and rf.json()["success"] is False and rf.json()["n_tumor"] == 0, (
            ad,
            rf.text[:200],
        )
