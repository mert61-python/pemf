# -*- coding: utf-8 -*-
"""SG.G5 — kedi organ "kedi / organ BULUNAMADI" BİLGİDİR, hata değil (sahip gözlemi 2026-10-13, canlı kip).

Ölçülen durum [ÖLÇTÜM kurulu ürün günlüğü 2026-10-13 20:08 + `ec5e967c` sınıf taraması]: `/api/ai/vision/cat_organ` kedisiz karede
`catorgan_predictor.predict`in RuntimeError'ını ("segmentasyon: kedi tespit edilemedi", "pose: DLC kedi bulamadi (detector)",
"PnP: yetersiz keypoint (valid=2)") 500 "Kedi organ analiz hatası"na çeviriyordu → canlı kipte kare sessizce düşüyor, elle analizde
operatör "hata" görüyordu; FGS / segmentasyon aynı durumu başarılı yanıtla söyler. Gerçek arızalar (model yok, resim okunamadı,
solvePnP istisnası) hata olarak KALIR. GPU servisi aynı işlevi yalnız AI Hub'ın gönderdiği `bulunamadi_bilgi=1` ile uygular — AI Pro
GPU kolunun "kedi yok" anlamı (CPU koluyla aynı: yalnız segmentasyon) DEĞİŞMEZ.
Sahte YALNIZ en alt katta: öngörücünün `predict`i (fırlattığı ileti üretimdekiyle aynı biçim); görüntü kapısı ve uç GERÇEK.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

KOK = Path(__file__).resolve().parents[1]
KEDI = KOK / "ai_hub" / "cat_landmark" / "results" / "00000005_020.jpg"


class _Ongorucu:
    def __init__(self, hata: BaseException):
        self.hata = hata
        self.device = "cpu"

    def predict(self, *a, **k):
        raise self.hata


@pytest.fixture()
def gomulu(monkeypatch):
    from servers import ai_router as air
    from servers import api_server

    kutu = {}
    gercek = air._get_or_load_model
    monkeypatch.setattr(air, "_get_or_load_model", lambda ad, y: kutu["o"] if ad == "cat_organ" else gercek(ad, y))
    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    c = TestClient(api_server.app, client=("127.0.0.1", 51234))

    def gonder(hata):
        kutu["o"] = _Ongorucu(hata)
        return c.post("/api/ai/vision/cat_organ", files={"file": ("k.jpg", KEDI.read_bytes(), "image/jpeg")})

    return gonder


@pytest.mark.parametrize(
    "ileti,kod",
    [
        ("segmentasyon: kedi tespit edilemedi", "kedi_bulunamadi"),
        ("pose: DLC kedi bulamadi (detector)", "kedi_bulunamadi"),
        ("pose: detector conf < 0.3", "kedi_bulunamadi"),
        ("PnP: yetersiz keypoint (valid=2)", "organ_cikarilamadi"),
        ("PnP: cat_pnp_fail", "organ_cikarilamadi"),
    ],
)
def test_KRITIK_bulunamadi_BASARILI_bilgi_yaniti(gomulu, ileti, kod):
    r = gomulu(RuntimeError(ileti))
    assert r.status_code == 200, f"'{ileti}' hâlâ HATA: {r.status_code} {r.text[:160]}"
    j = r.json()
    assert j["status"] == "success" and j["n_organs"] == 0 and j["organs"] == [] and j["detected"] is False, j
    assert j["bulunamadi"] == kod
    from ai_hub.inference_cat_organ.catorgan_predictor import BULUNAMADI_METNI

    assert j["bulunamadi_mesaji"] == BULUNAMADI_METNI[kod] and j["bulunamadi_mesaji"].endswith(".")
    assert j["image_base64"] and j["image_w"] > 0 and j["image_h"] > 0, "bilgi yanıtı gösterim karesini taşımıyor"


@pytest.mark.parametrize(
    "hata",
    [
        RuntimeError("segmentasyon: YOLO model yok: x.onnx"),
        RuntimeError("pose: detector ONNX yok: y.onnx"),
        RuntimeError("PnP: opencv_solvepnp: patladi"),
        ValueError("beklenmeyen"),
    ],
)
def test_KARSIT_KANIT_gercek_ARIZA_hala_500(gomulu, hata):
    r = gomulu(hata)
    assert r.status_code == 500 and r.json()["detail"] == "Kedi organ analiz hatası", r.text[:160]


def test_KRITIK_GPU_servisi_PARITE_yalniz_AI_Hub_alaniyla(monkeypatch):
    from ai_service import app as svc

    o = _Ongorucu(RuntimeError("segmentasyon: kedi tespit edilemedi"))
    monkeypatch.setattr(svc.predictors, "get", lambda ad: o)
    c = TestClient(svc.app)
    veri = KEDI.read_bytes()
    r = c.post("/infer/cat_organ", files={"file": ("k.jpg", veri, "image/jpeg")}, data={"bulunamadi_bilgi": "1"})
    assert r.status_code == 200, r.text[:160]
    assert r.json()["bulunamadi"] == "kedi_bulunamadi" and r.json()["organs"] == []
    # AI Pro GPU kolu alanı GÖNDERMEZ → eski davranış (500) AYNEN: "kedi yok" anlamı CPU koluyla aynı kalır.
    r2 = c.post("/infer/cat_organ", files={"file": ("k.jpg", veri, "image/jpeg")})
    assert r2.status_code == 500, r2.text[:160]


def test_KRITIK_gomulu_GPU_kolu_bilgi_alanini_GONDERIR(monkeypatch):
    from servers import ai_router as air
    from servers import api_server

    giden = []

    async def _devret(name, **kw):
        giden.append((name, kw.get("data")))
        return {"status": "success", "organs": [], "n_organs": 0}

    monkeypatch.setattr(air, "ai_service_enabled", lambda: True)
    monkeypatch.setattr(air, "delegate_infer", _devret)
    c = TestClient(api_server.app, client=("127.0.0.1", 51234))
    r = c.post("/api/ai/vision/cat_organ", files={"file": ("k.jpg", KEDI.read_bytes(), "image/jpeg")})
    assert r.status_code == 200 and giden == [("cat_organ", {"bulunamadi_bilgi": "1"})], (r.status_code, giden)


def test_KARSIT_KANIT_AI_Pro_CPU_kolu_DEGISMEDI():
    """AI Pro CPU kolu kendi `predict` çağrısını yapar ve yalnız `segmentasyon:` önekini "kedi yok" sayar (E3-b) — bu oturum
    o kola dokunmadı; anlam (pose / PnP hatası yukarı fırlar) yerinde."""
    from servers import ai_router as air

    assert air._is_cat_absent_error(RuntimeError("segmentasyon: kedi tespit edilemedi"))
    assert not air._is_cat_absent_error(RuntimeError("PnP: yetersiz keypoint (valid=2)"))
