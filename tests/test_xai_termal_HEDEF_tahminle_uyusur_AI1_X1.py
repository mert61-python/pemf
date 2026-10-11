# -*- coding: utf-8 -*-
"""AI1.X1 — termal ısı haritası TAHMİN EDİLEN sınıfı açıklar (hoca XAI v3: `inference_cat_thermal/xai_thermal_v2.py`).

ÖLÇÜLEN DURUM (2026-10-11, guii `97908b9b`, gerçek `GhostNetV2.pt`, CPU; `DUZELTME-AI1.md` X1): `xai_termal_isi_haritasi`
CAM'e HER ZAMAN `ClassifierOutputTarget(0)` = +Sick lojiti veriyordu → "Sağlıklı" tahmin edilen 2/2 gerçek görüntüde (03a,
hocanın 1.10'u) veteriner ekranındaki harita ("kırmızı = karara güçlü etki") "Hasta" kararının kanıtını gösteriyordu.
Ayrıca varsayılan Grad-CAM++ tek lojitli modelde sınıf-duyarsız: Sick↔Healthy hedef haritaları Spearman rho 0,83–0,95;
HiRes-CAM −0,45…−0,76 (hocanın ölçümü 0,91 / −0,66).
Düzeltme (hocanın ata → v2 farkı guii'nin sertleştirilmiş fonksiyonuna YAMA): hedef = tahmin edilen sınıf (Sick +lojit,
Healthy −lojit), varsayılan yöntem HiRes-CAM; yanıt açıklanan sınıfı (`hedef`) taşır; router ve ai_service tahmini XAI'ye
geçirir; arayüz başlığı açıklanan kararı söyler (jest: `termalIsiHaritasiHedefi.test.tsx`).
Test girdileri: `tests/xai_veri/KAYNAK.md` (03a / 03b'nin 224×224 kayıpsız PNG'si — model girdisi bayt-aynı).
"""

from __future__ import annotations

import base64
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

KOK = Path(__file__).resolve().parents[1]
VERI = KOK / "tests" / "xai_veri"
SAGLIKLI = VERI / "termal_saglikli_03a_224.png"
HASTA = VERI / "termal_hasta_03b_224.png"
_PT = "ai_hub/cat_thermal/GhostNetV2.pt"
_ONNX = "ai_hub/cat_thermal/GhostNetV2.onnx"


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    """Bağımlılıksız Spearman rho (sıra korelasyonu; eşitlikler ortalama sıra almaz — sürekli CAM değerleri için yeterli)."""
    ra = np.argsort(np.argsort(a.ravel())).astype(np.float64)
    rb = np.argsort(np.argsort(b.ravel())).astype(np.float64)
    return float(np.corrcoef(ra, rb)[0, 1])


@pytest.fixture()
def gercek_model():
    """Gerçek ağırlık (ONNX tahminci + PT ikizi). Eser yoksa atla — `PEMF_GOLDEN_REQUIRED=1`'de DÜŞ (4-A kuralı)."""
    pytest.importorskip("torch")
    pytest.importorskip("pytorch_grad_cam")
    from golden.eser import atla, eser_var_mi

    if not eser_var_mi(_PT, _ONNX):
        atla(f"termal ağırlıkları yok ({_PT}, {_ONNX})")
    from ai_hub.cat_thermal import inference_cat_thermal as ict

    return ict, ict.CatThermalPredictor(model_name="GhostNetV2")


@pytest.fixture()
def hedef_yoklayici(monkeypatch):
    """CAM kütüphanesinin EN ALT çağrısında (BaseCAM.__call__) verilen hedefi kaydeder; hesap GERÇEK koşar.
    Her hedef +2'lik tek lojitte değerlendirilir: >0 → Sick açıklanıyor, <0 → Healthy açıklanıyor."""
    import pytorch_grad_cam.base_cam as bc
    import torch

    kayit: list[list[float]] = []
    orj = bc.BaseCAM.__call__

    def _kayitci(self, input_tensor, targets=None, *a, **k):
        kayit.append([float(torch.as_tensor(t(torch.tensor([[2.0]]))).reshape(-1)[0]) for t in (targets or [])])
        return orj(self, input_tensor, targets, *a, **k)

    monkeypatch.setattr(bc.BaseCAM, "__call__", _kayitci)
    return kayit


# ── 1) gerçek ağırlık: açıklanan sınıf = tahmin edilen sınıf ─────────────────────────────────────────────────────
def test_KRITIK_saglikli_tahminde_harita_SAGLIKLI_kararini_aciklar(gercek_model, hedef_yoklayici):
    ict, tahminci = gercek_model
    tahmin = tahminci.predict(str(SAGLIKLI), threshold=0.5)
    assert tahmin["label"] == "Healthy", f"senaryo ayrışmıyor: 03a artık 'Healthy' tahmin edilmiyor ({tahmin})"

    r = ict.xai_termal_isi_haritasi(str(SAGLIKLI), hedef_sinif=tahmin["label"])
    assert r.get("hedef") == "Healthy", f"yanıt açıklanan sınıfı söylemiyor / yanlış söylüyor: {r.get('hedef')!r}"
    assert hedef_yoklayici and hedef_yoklayici[-1], "CAM hiç çağrılmadı"
    assert hedef_yoklayici[-1][0] < 0, (
        f"'Sağlıklı' tahmininde CAM hedefi +Sick lojiti ({hedef_yoklayici[-1]}) — harita YANLIŞ kararı açıklıyor (hocanın bulgusu)"
    )
    # hedef verilmezse (eski çağıran) PT'nin KENDİ tahmini kullanılır — yine Healthy, asla sabit Sick değil
    r2 = ict.xai_termal_isi_haritasi(str(SAGLIKLI))
    assert r2.get("hedef") == "Healthy" and hedef_yoklayici[-1][0] < 0, (
        f"hedefsiz çağrı sabit sınıfa düştü: {r2.get('hedef')}"
    )
    assert r2["xai_image_base64"] == r["xai_image_base64"], "aynı karar için farklı harita"


def test_KRITIK_hasta_tahminde_harita_HASTA_kararini_aciklar(gercek_model, hedef_yoklayici):
    ict, tahminci = gercek_model
    tahmin = tahminci.predict(str(HASTA), threshold=0.5)
    assert tahmin["label"] == "Sick", f"senaryo ayrışmıyor: 03b artık 'Sick' tahmin edilmiyor ({tahmin})"
    r = ict.xai_termal_isi_haritasi(str(HASTA), hedef_sinif=tahmin["label"])
    assert r.get("hedef") == "Sick"
    assert hedef_yoklayici[-1][0] > 0, f"'Hasta' tahmininde CAM hedefi −lojit ({hedef_yoklayici[-1]}) — işaret ters"


def test_KRITIK_varsayilan_yontem_SINIF_DUYARLI_haritalar_tamamlayici(gercek_model):
    """Tek lojitli modelde Grad-CAM++ sınıf-duyarsız (ölçüldü rho 0,95): iki karar için AYNI harita çıkıyordu. Varsayılan
    yöntemin iki kararın haritasını AYIRDIĞI (tamamlayıcı: rho < 0) ölçülür; aynı karar için harita deterministiktir."""
    ict, _ = gercek_model
    r = ict.xai_termal_isi_haritasi(str(SAGLIKLI))
    assert r.get("method") == "hirescam", f"varsayılan yöntem HiRes-CAM değil: {r.get('method')!r}"
    _, h_saglikli, e1 = ict.termal_cam_haritasi(str(SAGLIKLI), hedef_sinif="Healthy")
    _, h_hasta, e2 = ict.termal_cam_haritasi(str(SAGLIKLI), hedef_sinif="Sick")
    assert (e1, e2) == ("Healthy", "Sick")
    assert float(h_saglikli.std()) > 0.01 and float(h_hasta.std()) > 0.01, "harita düz/boş"
    rho = _spearman(h_saglikli, h_hasta)
    assert rho < -0.2, f"iki kararın haritası ayrışmıyor (Spearman rho {rho:.3f}) — açıklama sınıf-duyarsız"
    _, h_tekrar, _ = ict.termal_cam_haritasi(str(SAGLIKLI), hedef_sinif="Healthy")
    assert np.array_equal(h_tekrar, h_saglikli), "aynı karar için farklı harita (determinizm yok)"


def test_KRITIK_gecersiz_hedef_REDDEDILIR():
    """Yanlış yazılmış hedef sessizce 'Sick'e düşmemeli (ağırlıksız: doğrulama model yüklenmeden önce)."""
    from ai_hub.cat_thermal import inference_cat_thermal as ict

    with pytest.raises(ValueError):
        ict.xai_termal_isi_haritasi(str(SAGLIKLI), pt_path="yok.pt", hedef_sinif="sick ")


# ── 2) router: tahmin XAI'ye geçer, açıklanan sınıf yanıta girer (ağırlıksız, her ortamda) ──────────────────────────
@pytest.fixture()
def istemci(monkeypatch):
    import servers.ai_router as air
    import servers.api_server as apis

    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    return TestClient(apis.app), air


def _jpg_b64() -> str:
    import cv2

    ok, buf = cv2.imencode(".jpg", np.zeros((32, 32, 3), dtype=np.uint8))
    return base64.b64encode(buf.tobytes()).decode()


@pytest.mark.parametrize("etiket", ["Healthy", "Sick"])
def test_KRITIK_router_tahmini_XAI_ye_gecirir_ve_hedefi_dondurur(istemci, monkeypatch, etiket):
    client, air = istemci
    import ai_hub.cat_thermal.inference_cat_thermal as ict

    class _P:
        def predict(self, image_path, threshold=0.5):
            return {"label": etiket, "probability_sick": 0.9 if etiket == "Sick" else 0.1, "confidence": 0.9}

    monkeypatch.setattr(air, "_get_or_load_model", lambda ad, yukleyici: _P())
    cagri: list = []

    def _sahte_xai(image_path, pt_path=None, method="hirescam", alpha=0.5, hedef_sinif=None):
        cagri.append({"method": method, "hedef_sinif": hedef_sinif})
        return {"xai_image_base64": "WA==", "method": method, "hedef": hedef_sinif}

    monkeypatch.setattr(ict, "xai_termal_isi_haritasi", _sahte_xai)
    r = client.post("/api/ai/vision/thermal", data={"image_base64": _jpg_b64(), "explain": "true"})
    assert r.status_code == 200, r.text
    assert cagri and cagri[-1]["hedef_sinif"] == etiket, f"router tahmini XAI'ye geçirmedi: {cagri}"
    assert cagri[-1]["method"] == "hirescam", f"router varsayılan yöntemi HiRes-CAM değil: {cagri[-1]['method']}"
    assert r.json().get("xai_hedef") == etiket, f"yanıtta açıklanan sınıf yok: {sorted(r.json())}"
    # açık yöntem seçimi (izin listesi) aynen geçer
    client.post("/api/ai/vision/thermal", data={"image_base64": _jpg_b64(), "explain": "true", "xai_method": "gradcam"})
    assert cagri[-1]["method"] == "gradcam" and cagri[-1]["hedef_sinif"] == etiket


@pytest.mark.parametrize("etiket", ["Healthy", "Sick"])
def test_KRITIK_ai_service_tahmini_XAI_ye_gecirir_PARITE(monkeypatch, etiket):
    pytest.importorskip("onnxruntime")
    import ai_hub.cat_thermal.inference_cat_thermal as ict
    import ai_service.app as sapp

    class _Oturum:
        def get_providers(self):
            return ["CPUExecutionProvider"]

    class _P:
        session = _Oturum()

        def predict(self, image_path, threshold=0.5):
            return {"label": etiket, "probability_sick": 0.9 if etiket == "Sick" else 0.1, "confidence": 0.9}

    monkeypatch.setattr(sapp, "_kapi", lambda data, label: None)
    monkeypatch.setattr(sapp.predictors, "get", lambda ad: _P())
    cagri: list = []

    def _sahte_xai(image_path, pt_path=None, method="hirescam", alpha=0.5, hedef_sinif=None):
        cagri.append({"method": method, "hedef_sinif": hedef_sinif})
        return {"xai_image_base64": "WA==", "method": method, "hedef": hedef_sinif}

    monkeypatch.setattr(ict, "xai_termal_isi_haritasi", _sahte_xai)
    import cv2

    ok, buf = cv2.imencode(".jpg", np.full((64, 64, 3), 90, dtype=np.uint8))
    r = TestClient(sapp.app).post(
        "/infer/thermal", files={"file": ("t.jpg", buf.tobytes(), "image/jpeg")}, data={"explain": "true"}
    )
    assert r.status_code == 200, r.text
    assert cagri and cagri[-1]["hedef_sinif"] == etiket, f":8100 tahmini XAI'ye geçirmedi: {cagri}"
    assert cagri[-1]["method"] == "hirescam", f":8100 varsayılan yöntemi HiRes-CAM değil: {cagri[-1]['method']}"
    assert r.json().get("xai_hedef") == etiket
