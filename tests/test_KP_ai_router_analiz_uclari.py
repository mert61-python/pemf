# -*- coding: utf-8 -*-
"""KP-1 · apps/backend/servers/ai_router.py · sözleşmeler: AI Hub analiz uçları (gömülü + GPU mikroservis devri).

Uçlar: disease, vision/landmark, vision/segmentation, vision/thermal, vision/reticulocytes, rna/kidney, disease/kidney,
sound/cat, vision/kidney_ct, vision/histopath, vision/scratch, vision/cat_organ, vision/em_fantom ve model yükleyicileri
(`_get_or_load_kedi`, `_yukle_em_fantom_cv`, `_yukle_em_petri_cv`).

İddialar: mikroservis kipinde istek GPU servisine (doğru `/infer/<ad>` + aynı baytlar) gider ve yanıt AYNEN döner; ilk istekte
model İNDİRİCİDEN doğru göreli yolla istenir ve önbelleğe alınır; indirici bütünlük DIŞI hata verirse modül-yanı yola düşülür,
bütünlük reddi YUTULMAZ (503 + dosya adı); geçici dosya silinemese de analiz döner; çıkarım hatası ham iletisini SIZDIRMADAN
500 + uç etiketi; açıklama (XAI) başarısı / hatası analizi düşürmez; boyut / boş / bozuk CSV-ses girdileri reddedilir.
RNA: gerçek öngörücüyü kullanan test git-ignored eser yoksa `capraz` deseniyle atlar; yan dosyası eksik öngörücü için sözleşme
(500 + `ai.hata.rnaAnaliz`, SystemExit sızmaz) — KP1-IB.2, KP-2 A1 (Y240) ile düzeltildi (`_require` → `FileNotFoundError`).

Sahte EN ALT katta: ağ (`ai_client.httpx` → gerçek httpx + `MockTransport`), çıkarım motoru (`ultralytics.YOLO`, model sınıfları
— ağırlıklar klonda YOK), model indirici, süreç (`subprocess.run` = ffmpeg), WAV okuyucu (`wave.open`). Geçici dosyalar tmp
(`tempfile.tempdir`). Sunucu süreç içi `TestClient` (port YOK).
"""

from __future__ import annotations

import base64
import io
import os
import subprocess
import sys
import tempfile
import types
import wave

import capraz
import cv2
import httpx
import numpy as np
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from servers import ai_client
from servers import ai_router as air
from starlette.datastructures import UploadFile
from utils import ceviri

# ───────────────────────────── aparat ─────────────────────────────


@pytest.fixture(scope="module")
def istemci():
    from servers import api_server as api

    c = TestClient(api.app, client=("127.0.0.1", 50991), raise_server_exceptions=False)
    try:
        yield c
    finally:
        c.close()


@pytest.fixture(autouse=True)
def _yalitim(monkeypatch, tmp_path):
    """Her test: boş model önbelleği, gömülü kip, modalite kapısı kapalı (konu değil), geçici dosyalar tmp'de."""
    monkeypatch.setattr(air, "_models", {})
    monkeypatch.setattr(ai_client, "AI_SERVICE_URL", "")
    monkeypatch.setenv("PEMF_AI_DOMAIN_GUARD", "0")
    gecici = tmp_path / "gecici"
    gecici.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(gecici))
    yield gecici


def _jpg(h=48, w=64, renk=(100, 100, 100)) -> bytes:
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = renk
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 100])
    assert ok
    return buf.tobytes()


def _b64(veri: bytes) -> str:
    return base64.b64encode(veri).decode("ascii")


def _gecici_kalan(klasor) -> list:
    return sorted(p.name for p in klasor.iterdir() if p.is_file())


def _servis(monkeypatch, yanit_uret):
    """GPU mikroservis kipi: `ai_client` gerçek httpx'i `MockTransport` ile kullanır (ağ YOK). İstekler kaydedilir."""
    istekler = []

    def _isle(req: httpx.Request) -> httpx.Response:
        istekler.append({"yol": req.url.path, "govde": req.read(), "tur": req.headers.get("content-type", "")})
        return yanit_uret(req)

    tasima = httpx.MockTransport(_isle)
    monkeypatch.setattr(ai_client, "AI_SERVICE_URL", "http://ai-servisi.invalid")
    monkeypatch.setattr(
        ai_client,
        "httpx",
        types.SimpleNamespace(
            AsyncClient=lambda **kw: httpx.AsyncClient(transport=tasima, **kw),
            Client=lambda **kw: httpx.Client(transport=tasima, **kw),
            ReadTimeout=httpx.ReadTimeout,
            HTTPStatusError=httpx.HTTPStatusError,
        ),
    )
    return istekler


def _indirici(monkeypatch, hata=None):
    """Model indiricisi: istenen göreli yolları kaydeder; `hata` verilirse onu fırlatır (modül-yanı düşüşü / bütünlük)."""
    from utils import model_downloader as md

    istenen = []

    def _indir(goreli, *a, **k):
        istenen.append(goreli)
        if hata is not None:
            raise hata
        return os.path.join("C:\\kp_modeller", *goreli.split("/"))

    monkeypatch.setattr(md, "download_model_sync", _indir)
    monkeypatch.setattr(air, "download_model_sync", _indir)
    return istenen


class _T:
    """torch tensörü benzeri: `.cpu().numpy()` ve indeks."""

    def __init__(self, a):
        self.a = np.asarray(a)

    def cpu(self):
        return self

    def numpy(self):
        return self.a

    def __getitem__(self, i):
        return self.a[i]

    def __len__(self):
        return len(self.a)


def _sahte_ultralytics(monkeypatch, tahmin):
    """`ultralytics.YOLO` (çıkarım motoru) sahtesi: kurulumu (yol, görev) ve `predict` argümanlarını kaydeder."""
    kayit = {"kurulum": [], "predict": []}

    class YOLO:
        def __init__(self, yol, task=None):
            kayit["kurulum"].append((yol, task))

        def predict(self, *a, **k):
            kayit["predict"].append((a, k))
            return tahmin(*a, **k)

    monkeypatch.setitem(sys.modules, "ultralytics", types.SimpleNamespace(YOLO=YOLO))
    return kayit


def _kaynak(a, k):
    return k.get("source") or (a[0] if a else None)


# ───────────────────────────── disease ─────────────────────────────

_VITAL = {"age": 4, "weight": 4.2, "hr": 180, "temp": 38.6, "duration": 3, "symptom_indices": [2, 3]}


def test_disease_MIKROSERVIS_kipinde_govde_GPU_servisine_gider_yanit_AYNEN_doner(istemci, monkeypatch):
    """PEMF_AI_SERVICE_URL dolu → POST /infer/disease (vital JSON aynen) ve servis yanıtı değişmeden döner."""
    import json

    istekler = _servis(
        monkeypatch, lambda r: httpx.Response(200, json={"status": "success", "kaynak": "gpu", "results": []})
    )
    r = istemci.post("/api/ai/disease", json=_VITAL)
    assert r.status_code == 200, r.text[:300]
    assert r.json() == {"status": "success", "kaynak": "gpu", "results": []}
    assert [i["yol"] for i in istekler] == ["/infer/disease"]
    govde = json.loads(istekler[0]["govde"])
    assert govde["weight"] == 4.2 and govde["hr"] == 180 and govde["symptom_indices"] == [2, 3]


def test_disease_ilk_istekte_XGBoost_INDIRICIDEN_istenir_gercek_ongorucu_onbellege_alinir(istemci, monkeypatch):
    """Önbellek boş → indirici 'ai_hub/cat_disease/XGBoost.pkl' ister, CatDiseasePredictor kurulur, 3 sonuç + olasılık döner."""
    istenen = _indirici(monkeypatch)
    r = istemci.post("/api/ai/disease", json=_VITAL)
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert istenen == ["ai_hub/cat_disease/XGBoost.pkl"]
    assert len(j["results"]) == 3 and all(0.0 <= x["probability"] <= 1.0 for x in j["results"])
    assert type(air._models["disease"]).__name__ == "CatDiseasePredictor"


def test_disease_cikarim_HATASI_ham_iletiyi_sizdirmadan_500(istemci, monkeypatch):
    """Öngörücü RuntimeError → 500 + `ai.hata.hastalikAnalizi`; istisna metni yanıtta YOK."""

    class _Bozuk:
        def predict(self, *a, **k):
            raise RuntimeError("xgboost booster bozuk GIZLI-AYRINTI")

    air._models["disease"] = _Bozuk()
    r = istemci.post("/api/ai/disease", json=_VITAL)
    assert r.status_code == 500
    assert r.json()["detail"] == ceviri.t("ai.hata.hastalikAnalizi")
    assert "GIZLI-AYRINTI" not in r.text


# ───────────────────────────── landmark ─────────────────────────────


def test_landmark_MIKROSERVIS_kipinde_ayni_baytlar_devredilir(istemci, monkeypatch):
    """Gömülü kapıdan geçen görüntü baytları /infer/landmark'a multipart gider; servis yanıtı aynen döner."""
    jpg = _jpg()
    istekler = _servis(monkeypatch, lambda r: httpx.Response(200, json={"status": "success", "fgs_total": 2}))
    r = istemci.post("/api/ai/vision/landmark", data={"image_base64": _b64(jpg)})
    assert r.status_code == 200, r.text[:300]
    assert r.json() == {"status": "success", "fgs_total": 2}
    assert [i["yol"] for i in istekler] == ["/infer/landmark"] and jpg in istekler[0]["govde"]


def test_landmark_ilk_istekte_POZ_modeli_yuklenir_tespit_YOKSA_skor_null(istemci, monkeypatch, _yalitim):
    """Model yolu indiriciden (yolo26m-pose.onnx, task=pose); tespit yok → fgs_total None + 'Kedi yüzü tespit edilemedi';
    geçici dosya çıkarımda silinmiş olsa da (FileNotFoundError) yanıt 200 ve tmp'de artık kalmaz."""
    istenen = _indirici(monkeypatch)

    def _tahmin(*a, **k):
        os.unlink(a[0])  # motor geçici dosyayı tüketti → ürünün silmesi FileNotFoundError alır
        return []

    kayit = _sahte_ultralytics(monkeypatch, _tahmin)
    r = istemci.post("/api/ai/vision/landmark", data={"image_base64": _b64(_jpg())})
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert istenen == ["ai_hub/cat_landmark/yolo26m-pose.onnx"]
    assert kayit["kurulum"] == [
        (os.path.join("C:\\kp_modeller", "ai_hub", "cat_landmark", "yolo26m-pose.onnx"), "pose")
    ]
    assert j["detected"] is False and j["fgs_total"] is None and j["pain_level"] == "Kedi yüzü tespit edilemedi"
    assert j["raw_fgs"] is None and j["action_units"] is None
    assert _gecici_kalan(_yalitim) == []


def test_landmark_nokta_GUVENI_okunamazsa_skor_verilir_ama_DOGRULANMADI_isareti_konur(istemci, monkeypatch):
    """`keypoints.conf` erişimi hata verir → güven yok sayılır; 48 nokta + kutu ile skor üretilir, nokta_gorunurlugu_dogrulanmadi=True."""
    rng = np.random.default_rng(3)
    xy = np.column_stack([rng.uniform(12, 52, 48), rng.uniform(8, 40, 48)])

    class _Nokta:
        def __init__(self):
            self.xy = [_T(xy)]

        @property
        def conf(self):
            raise RuntimeError("model nokta güveni üretmiyor")

    sonuc = types.SimpleNamespace(keypoints=_Nokta(), boxes=[types.SimpleNamespace(xyxy=[_T([10.0, 6.0, 54.0, 42.0])])])
    air._models["landmark"] = types.SimpleNamespace(predict=lambda *a, **k: [sonuc])
    r = istemci.post("/api/ai/vision/landmark", data={"image_base64": _b64(_jpg())})
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert j["detected"] is True and isinstance(j["fgs_total"], int) and 0 <= j["fgs_total"] <= 10
    assert j["nokta_gorunurlugu_dogrulanmadi"] is True


def test_landmark_cikarim_HATASI_500_uc_etiketiyle(istemci, monkeypatch):
    """Motor RuntimeError → 500 + `ai.hata.landmark` (ham ileti yok)."""

    def _patla(*a, **k):
        raise RuntimeError("onnx oturumu GIZLI")

    air._models["landmark"] = types.SimpleNamespace(predict=_patla)
    r = istemci.post("/api/ai/vision/landmark", data={"image_base64": _b64(_jpg())})
    assert r.status_code == 500 and r.json()["detail"] == ceviri.t("ai.hata.landmark")
    assert "GIZLI" not in r.text


# ───────────────────────────── segmentation ─────────────────────────────


def test_segmentation_MIKROSERVIS_kipinde_devredilir(istemci, monkeypatch):
    """Mikroservis kipi → /infer/segmentation; yanıt aynen."""
    istekler = _servis(monkeypatch, lambda r: httpx.Response(200, json={"status": "success", "cat_count": 3}))
    r = istemci.post("/api/ai/vision/segmentation", data={"image_base64": _b64(_jpg())})
    assert r.status_code == 200 and r.json() == {"status": "success", "cat_count": 3}
    assert [i["yol"] for i in istekler] == ["/infer/segmentation"]


def test_segmentation_MASKE_bolgesi_yesille_boyanir_kedi_sayisi_kutu_sayisidir(istemci, monkeypatch, _yalitim):
    """Model ilk istekte yüklenir (yolov8m-seg.onnx, task=segment); 2 kutu → cat_count 2; maske (sol yarı) yeşile karışır,
    sağ yarı değişmez; geçici dosya motorca silinmiş olsa da yanıt 200."""
    istenen = _indirici(monkeypatch)
    maske = np.zeros((24, 32), dtype=np.float32)
    maske[:, :16] = 1.0

    class _Maskeler:
        def __init__(self, data):
            self.data = data

        def __len__(self):
            return len(self.data)

    def _tahmin(*a, **k):
        os.unlink(_kaynak(a, k))
        return [types.SimpleNamespace(boxes=[1, 2], masks=_Maskeler([_T(maske)]))]

    kayit = _sahte_ultralytics(monkeypatch, _tahmin)
    r = istemci.post("/api/ai/vision/segmentation", data={"image_base64": _b64(_jpg(48, 64, (100, 100, 100)))})
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert istenen == ["ai_hub/cat_segmentation/yolov8m-seg.onnx"]
    assert kayit["kurulum"][0][1] == "segment"
    assert j["cat_count"] == 2 and (j["image_w"], j["image_h"]) == (64, 48)
    img = cv2.imdecode(np.frombuffer(base64.b64decode(j["image_base64"]), np.uint8), cv2.IMREAD_COLOR)
    sol, sag = img[:, 4:28].reshape(-1, 3).mean(0), img[:, 36:60].reshape(-1, 3).mean(0)
    assert sol[1] > sag[1] + 15 and sol[0] < sag[0] - 25, (sol, sag)
    assert abs(sag[1] - 100) < 8
    assert _gecici_kalan(_yalitim) == []


def test_segmentation_cikarim_HATASI_500(istemci, monkeypatch):
    """Motor hata → 500 + `ai.hata.segmentasyon`."""

    def _patla(*a, **k):
        raise RuntimeError("seg motoru")

    air._models["seg"] = types.SimpleNamespace(predict=_patla)
    r = istemci.post("/api/ai/vision/segmentation", data={"image_base64": _b64(_jpg())})
    assert r.status_code == 500 and r.json()["detail"] == ceviri.t("ai.hata.segmentasyon")


# ───────────────────────────── thermal ─────────────────────────────


def test_thermal_ilk_istekte_GhostNetV2_ongorucu_kurulur_tahmin_yanita_konur(istemci, monkeypatch, _yalitim):
    """Önbellek boş → CatThermalPredictor(model_name='GhostNetV2'); tahmin `prediction` alanında aynen; tmp silinmiş olsa da 200."""
    from ai_hub.cat_thermal import inference_cat_thermal as ict

    kurulan = []

    class _Termal:
        def __init__(self, model_name=None, **k):
            kurulan.append(model_name)

        def predict(self, yol, threshold=None):
            os.unlink(yol)
            return {"label": "Saglikli", "prob": 0.81, "threshold": threshold}

    monkeypatch.setattr(ict, "CatThermalPredictor", _Termal)
    r = istemci.post("/api/ai/vision/thermal", data={"image_base64": _b64(_jpg())})
    assert r.status_code == 200, r.text[:300]
    assert kurulan == ["GhostNetV2"]
    assert r.json()["prediction"] == {"label": "Saglikli", "prob": 0.81, "threshold": 0.5}
    assert _gecici_kalan(_yalitim) == []


# ───────────────────────────── reticulocytes ─────────────────────────────


def test_reticulocytes_MIKROSERVIS_kipinde_explain_bayragi_iletilir(istemci, monkeypatch):
    """explain=true → /infer/reticulocytes form alanı explain=true; yanıt aynen."""
    istekler = _servis(monkeypatch, lambda r: httpx.Response(200, json={"status": "success", "counts": {}}))
    r = istemci.post("/api/ai/vision/reticulocytes", data={"image_base64": _b64(_jpg()), "explain": "true"})
    assert r.status_code == 200 and r.json() == {"status": "success", "counts": {}}
    assert istekler[0]["yol"] == "/infer/reticulocytes" and b'name="explain"' in istekler[0]["govde"]


def test_reticulocytes_kutular_SINIF_basina_sayilir_motorun_kaydettigi_gorsel_doner(istemci, monkeypatch, _yalitim):
    """yolov8s.onnx (task=detect) yüklenir; kutular [0,2,2] → eritrosit 1 / agregat 2; motorun kaydettiği 40×30 görsel yanıt
    boyutunu belirler; XAI hatası analizi düşürmez (xai_error); geçici girdi silinemese de 200."""
    from ai_hub.feline_reticulocytes import inference_feline_reticulocytes as ifr

    istenen = _indirici(monkeypatch)

    def _tahmin(*a, **k):
        kaynak = _kaynak(a, k)
        hedef = os.path.join(k["project"], k["name"])
        os.makedirs(hedef, exist_ok=True)
        cv2.imwrite(os.path.join(hedef, os.path.basename(kaynak)), np.full((30, 40, 3), 90, np.uint8))
        os.unlink(kaynak)
        kutular = [types.SimpleNamespace(cls=[c]) for c in (0, 2, 2)]
        return [types.SimpleNamespace(boxes=kutular), types.SimpleNamespace(boxes=None)]

    def _xai(yol):
        raise RuntimeError("cam hesaplanamadı")

    kayit = _sahte_ultralytics(monkeypatch, _tahmin)
    monkeypatch.setattr(ifr, "xai_retikulosit_isi_haritasi", _xai)
    r = istemci.post("/api/ai/vision/reticulocytes", data={"image_base64": _b64(_jpg()), "explain": "true"})
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert istenen == ["ai_hub/feline_reticulocytes/yolov8s.onnx"] and kayit["kurulum"][0][1] == "detect"
    assert j["counts"] == {"erythrocyte": 1, "punctate reticulocyte": 0, "aggregate reticulocyte": 2}
    assert (j["image_w"], j["image_h"]) == (40, 30)
    assert j["xai_error"] == ceviri.t("ai.sonuc.aciklamaUretilemedi") and "xai_image_base64" not in j
    assert _gecici_kalan(_yalitim) == []


def test_reticulocytes_cikarim_HATASINDA_500_ve_gecici_dosya_SILINIR(istemci, monkeypatch, _yalitim):
    """Motor hata → 500 + `ai.hata.retikulosit`; finally geçici girdiyi siler (tmp boş)."""

    def _patla(*a, **k):
        raise RuntimeError("retik motoru")

    air._models["retic"] = types.SimpleNamespace(predict=_patla)
    r = istemci.post("/api/ai/vision/reticulocytes", data={"image_base64": _b64(_jpg())})
    assert r.status_code == 500 and r.json()["detail"] == ceviri.t("ai.hata.retikulosit")
    assert _gecici_kalan(_yalitim) == []


# ───────────────────────────── rna ─────────────────────────────


def test_rna_MIKROSERVIS_kipinde_CSV_devredilir(istemci, monkeypatch):
    """Mikroservis → /infer/rna, CSV baytları gövdede; yanıt aynen."""
    csv = b"id,g1\nh1,1.0\n"
    istekler = _servis(monkeypatch, lambda r: httpx.Response(200, json={"status": "success", "n_patients": 1}))
    r = istemci.post("/api/ai/rna/kidney", data={"csv_base64": _b64(csv)})
    assert r.status_code == 200 and r.json() == {"status": "success", "n_patients": 1}
    assert istekler[0]["yol"] == "/infer/rna" and csv in istekler[0]["govde"]


#: Gerçek `KidneyRnaPredictor`ın açtığı İZLENMEYEN (.gitignore `*.pkl` / `*.onnx`) eserler — temiz checkout / CI'da YOK.
_RNA_IZLENMEYEN = (
    "ai_hub/inference_human_kidney_rna/scaler.pkl",
    "ai_hub/inference_human_kidney_rna/mlp_medium_kirc.onnx",
)


def test_rna_DOSYA_yuklemesi_okunur_gen_sutunu_UYUSMAZSA_400_beklenen_ve_gelen(istemci):
    """CSV dosya olarak gelir (3 gen sütunu) → gerçek KidneyRnaPredictor 20531 bekler → 400 + `ai.hata.genSutunSayisi`.

    TUR 2 · KP1-IB.1: gerçek öngörücü git-ignored eserlere dayanır → eser / paket yoksa `capraz` deseniyle ATLA (ZORUNLU kipte
    DÜŞ). Atlamasız koşu ağırlıksız ortamda kırmızı değil ASILI kalıyordu (`_require` → `sys.exit` TestClient portalını öldürüyordu;
    KP1-IB.2, KP-2 A1 ile düzeldi → `test_rna_YAN_DOSYA_eksikse_500_ve_backend_AYAKTA`)."""
    capraz.paket_yoksa_atla("onnxruntime")
    capraz.paket_yoksa_atla("joblib")
    for rel in _RNA_IZLENMEYEN:
        capraz.atla_yoksa(rel)
    csv = b"id,g1,g2,g3\nh1,1,2,3\nh2,4,5,6\n"
    r = istemci.post("/api/ai/rna/kidney", files={"file": ("rna.csv", csv, "text/csv")})
    assert r.status_code == 400, r.text[:300]
    beklenen = air._models["kidney_rna"].expected_cols
    assert r.json()["detail"] == ceviri.t("ai.hata.genSutunSayisi", beklenen=beklenen, gelen=3)


def _dongu_kapat(dongu) -> None:
    """Kendi olay döngüsünü HER durumda kapatır: bekleyen görevler iptal (SystemExit yeniden kaçsa da turlarla), varsayılan
    yürütücü (`asyncio.to_thread` işçisi) kapanır, döngü kapanır — test süreci asılı kalmaz."""
    import asyncio

    for _tur in range(6):
        bekleyen = [t for t in asyncio.all_tasks(dongu) if not t.done()]
        if not bekleyen:
            break
        for t in bekleyen:
            t.cancel()
        try:
            dongu.run_until_complete(asyncio.gather(*bekleyen, return_exceptions=True))
        except BaseException:  # noqa: BLE001 — iptal turunda yeniden kaçan SystemExit; temizlik sürer
            pass
    try:
        dongu.run_until_complete(dongu.shutdown_default_executor())
    finally:
        dongu.close()


def test_rna_YAN_DOSYA_eksikse_500_ve_backend_AYAKTA(monkeypatch, tmp_path):
    """RNA öngörücüsünün yan dosyası (best_model_meta.json — ilk `_require`; git-ignored eserlerden BAĞIMSIZ) yok → uç, öteki
    çıkarım hatalarıyla AYNI sözleşmeyle 500 + `ai.hata.rnaAnaliz` döner (SystemExit SIZMAZ), öngörücü önbelleğe girmez ve AYNI
    olay döngüsündeki komşu iş (backend'in öteki istekleri — ACİL DURDUR uçları dahil) tamamlanır.

    KP1-IB.2 GERÇEK ÜRÜN HATASIYDI (gerçek `api.app` yığını + uvicorn 0.48 `run_asgi` sarmalı → SystemExit `starlette/middleware/
    base.py:144` alt görevinden döngüye kaçıyor, komşu iş 9/30 adımda kalıyor, yanıt gitmiyordu). KP-2 A1 (Y240): `_require` →
    `FileNotFoundError`. Gerçek ASGI yığını + ardından ACİL DURDUR kanıtı: `test_KP2_A1_rna_yan_dosya_eksik_backend_AYAKTA.py`."""
    import asyncio

    from ai_hub.inference_human_kidney_rna import inference_human_kidney_rna as ihr

    monkeypatch.setattr(ihr, "META_PATH", tmp_path / "kurulum_eksik" / "best_model_meta.json")
    komsu = []

    async def _komsu():
        for i in range(5):
            await asyncio.sleep(0.01)
            komsu.append(i)

    async def _senaryo():
        komsu_gorev = asyncio.ensure_future(_komsu())
        try:
            await air.analyze_kidney_rna(file=None, csv_base64=_b64(b"id,g1,g2\nh1,1,2\n"), explain=False, _res=None)
        except HTTPException as e:
            yakalanan = e
        else:
            yakalanan = None
        await komsu_gorev
        return yakalanan

    dongu = asyncio.SelectorEventLoop()
    try:
        hata = dongu.run_until_complete(_senaryo())
    finally:
        _dongu_kapat(dongu)
    assert hata is not None and hata.status_code == 500
    assert hata.detail == ceviri.t("ai.hata.rnaAnaliz")
    assert komsu == [0, 1, 2, 3, 4]
    assert "kidney_rna" not in air._models


def test_rna_60MB_ustu_dosya_MODEL_yuklenmeden_reddedilir():
    """60 MB + 1 baytlık yükleme → 500 + `ai.hata.rnaAnaliz`; öngörücü önbelleğe girmez."""
    dosya = UploadFile(file=io.BytesIO(b"0" * (60 * 1024 * 1024 + 1)), filename="dev.csv")
    import asyncio

    dongu = asyncio.SelectorEventLoop()
    try:
        with pytest.raises(HTTPException) as ex:
            dongu.run_until_complete(air.analyze_kidney_rna(file=dosya, csv_base64=None, explain=False, _res=None))
    finally:
        dongu.run_until_complete(dongu.shutdown_default_executor())
        dongu.close()
    assert ex.value.status_code == 500 and ex.value.detail == ceviri.t("ai.hata.rnaAnaliz")
    assert "kidney_rna" not in air._models


@pytest.mark.parametrize(
    "veri",
    [None, b"", b"id,g1,g2\n"],
    ids=["girdi-yok", "okunamaz-csv", "hasta-satiri-yok"],
)
def test_rna_GIRDI_yok_okunamaz_ya_da_BOS_csv_500_model_yuklenmez(istemci, veri):
    """CSV yok / pandas okuyamaz / yalnız başlık → 500 + `ai.hata.rnaAnaliz`; öngörücü yüklenmez."""
    if veri is None:
        r = istemci.post("/api/ai/rna/kidney", data={"explain": "false"})
    else:
        r = istemci.post("/api/ai/rna/kidney", files={"file": ("r.csv", veri, "text/csv")})
    assert r.status_code == 500, r.text[:300]
    assert r.json()["detail"] == ceviri.t("ai.hata.rnaAnaliz")
    assert "kidney_rna" not in air._models


# ───────────────────────────── kidney disease (CKD) ─────────────────────────────

_CKD = {"age": 61, "bp": 80, "sg": 1.015, "al": 2, "su": 0, "bgr": 140, "bu": 60, "sc": 2.4, "hemo": 10.1, "htn": "yes"}


def test_ckd_MIKROSERVIS_kipinde_explain_bayragiyla_devredilir(istemci, monkeypatch):
    """Asgari kapıdan geçen form → /infer/kidney_disease, gövdede explain=True + alanlar; yanıt aynen."""
    import json

    istekler = _servis(monkeypatch, lambda r: httpx.Response(200, json={"status": "success", "prob_ckd": 0.9}))
    r = istemci.post("/api/ai/disease/kidney", json={**_CKD, "explain": True})
    assert r.status_code == 200 and r.json() == {"status": "success", "prob_ckd": 0.9}
    govde = json.loads(istekler[0]["govde"])
    assert istekler[0]["yol"] == "/infer/kidney_disease" and govde["explain"] is True and govde["sc"] == 2.4


def test_ckd_cikarim_HATASI_eylem_soyleyen_500(istemci, monkeypatch):
    """`predict_one` hata → 500 + `ai.hata.bobrekHastalik` (ham ileti yok)."""
    import ai_hub.inference_human_kidney_disease as ihd

    def _patla(f):
        raise RuntimeError("onnx GIZLI")

    monkeypatch.setattr(ihd, "predict_one", _patla)
    r = istemci.post("/api/ai/disease/kidney", json=_CKD)
    assert r.status_code == 500 and r.json()["detail"] == ceviri.t("ai.hata.bobrekHastalik")
    assert "GIZLI" not in r.text


# ───────────────────────────── sound/cat ─────────────────────────────


def _wav(sn=1.0, genlik=12000) -> bytes:
    b = io.BytesIO()
    n = int(22050 * sn)
    t = np.arange(n)
    ornek = (genlik * np.sin(t / 7.0)).astype("<i2")
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(ornek.tobytes())
    return b.getvalue()


def _sahte_ffmpeg(monkeypatch, rc=0):
    """ffmpeg süreci (subprocess.run) sahtesi: başarıda çıktı WAV'ını (son argüman) yazar."""
    cagri = []

    def _run(args, **k):
        cagri.append(list(args))
        if rc == 0:
            with open(args[-1], "wb") as f:
                f.write(_wav())
        return subprocess.CompletedProcess(args, rc, b"", b"")

    monkeypatch.setattr(subprocess, "run", _run)
    return cagri


class _SesSiniflandirici:
    def __init__(self, model_path=None, runtime=None, device=None, kilitle=False):
        self.kurulum = (model_path, runtime, device)
        self.kilitle = kilitle
        self.acik = None

    def predict(self, yol, top_k=3):
        if self.kilitle:  # Windows: paylaşımsız açık tutamaç → os.unlink PermissionError
            self.acik = open(yol, "rb")
        p = {"Angry": 0.1, "Happy": 0.7, "Resting": 0.2}
        return {
            "top_1_class": "Happy",
            "top_1_prob": 0.7,
            "top_k": [{"class": "Happy", "prob": 0.7}],
            "probabilities": p,
        }


def test_ses_25MB_ustu_dosya_reddedilir():
    """25 MB + 1 bayt ses → 500 + `ai.hata.sesAnaliz` (ffmpeg'e gitmez)."""
    import asyncio

    dosya = UploadFile(file=io.BytesIO(b"\x00" * (25 * 1024 * 1024 + 1)), filename="dev.wav")
    dongu = asyncio.SelectorEventLoop()
    try:
        with pytest.raises(HTTPException) as ex:
            dongu.run_until_complete(
                air.analyze_cat_sound(file=dosya, audio_base64=None, explain=False, xai_method="gradcam")
            )
    finally:
        dongu.run_until_complete(dongu.shutdown_default_executor())
        dongu.close()
    assert ex.value.status_code == 500 and ex.value.detail == ceviri.t("ai.hata.sesAnaliz")


def test_ses_COZUMLENEMEZSE_500_model_yuklenmez_gecici_dosyalar_silinir(istemci, monkeypatch, _yalitim):
    """ffmpeg rc=1 → 500 + `ai.hata.sesAnaliz`; model yüklenmez; tmp boş kalır."""
    cagri = _sahte_ffmpeg(monkeypatch, rc=1)
    r = istemci.post("/api/ai/sound/cat", files={"file": ("k.m4a", b"\x01" * 400, "audio/mp4")})
    assert r.status_code == 500 and r.json()["detail"] == ceviri.t("ai.hata.sesAnaliz")
    assert len(cagri) == 1 and "-protocol_whitelist" in cagri[0] and cagri[0][cagri[0].index("-ar") + 1] == "22050"
    assert "cat_sound" not in air._models
    assert _gecici_kalan(_yalitim) == []


def test_ses_RMS_OLCULEMEZSE_kapi_zorlanmaz_analiz_surer_rms_null(istemci, monkeypatch):
    """WAV okunamaz (wave.Error) → sessizlik kapısı atlanır, sınıflandırma döner, rms_dbfs None."""
    from utils import ses_kalitesi

    _sahte_ffmpeg(monkeypatch)

    def _okunamaz(*a, **k):
        raise wave.Error("file does not start with RIFF id")

    monkeypatch.setattr(ses_kalitesi, "wave", types.SimpleNamespace(open=_okunamaz, Error=wave.Error))
    air._models["cat_sound"] = _SesSiniflandirici()
    r = istemci.post("/api/ai/sound/cat", data={"audio_base64": _b64(_wav())})
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert j["top_1_class"] == "Happy" and j["rms_dbfs"] is None


def test_ses_indirici_HATASINDA_modul_yani_yola_duser_XAI_alanlari_yanita_konur(istemci, monkeypatch):
    """İndirici bütünlük DIŞI hata → model yolu project_root/ai_hub/inference_cat_sound/EfficientNet_Lite0.onnx (onnx, cpu);
    explain=true ve ısı haritası üretildi → xai_image_base64 + xai_method yanıtta."""
    import ai_hub.inference_cat_sound as ics_paket
    from ai_hub.inference_cat_sound import inference_cat_sound as ics

    _sahte_ffmpeg(monkeypatch)
    istenen = _indirici(monkeypatch, hata=RuntimeError("HF erişilemedi"))
    kurulan = []

    def _sinif(**k):
        s = _SesSiniflandirici(**k)
        kurulan.append(s.kurulum)
        return s

    monkeypatch.setattr(ics_paket, "CatSoundClassifier", _sinif)
    monkeypatch.setattr(
        ics, "xai_ses_isi_haritasi", lambda yol, _m, yontem: {"xai_image_base64": "QUJD", "method": yontem}
    )
    r = istemci.post(
        "/api/ai/sound/cat", data={"audio_base64": _b64(_wav()), "explain": "true", "xai_method": "eigencam"}
    )
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert istenen == ["ai_hub/inference_cat_sound/EfficientNet_Lite0.onnx"]
    assert kurulan == [
        (os.path.join(air.project_root, "ai_hub", "inference_cat_sound", "EfficientNet_Lite0.onnx"), "onnx", "cpu")
    ]
    assert j["xai_image_base64"] == "QUJD" and j["xai_method"] == "eigencam"


@pytest.mark.skipif(os.name != "nt", reason="paylaşımsız açık tutamaç silmeyi yalnız Windows'ta engeller")
def test_ses_gecici_WAV_kilitli_SILINEMESE_de_yanit_200(istemci, monkeypatch, _yalitim):
    """Sınıflandırıcı WAV'ı açık tutar (Windows'ta silme PermissionError) → finally hatayı yutar, yanıt 200."""
    _sahte_ffmpeg(monkeypatch)
    s = _SesSiniflandirici(kilitle=True)
    air._models["cat_sound"] = s
    try:
        r = istemci.post("/api/ai/sound/cat", data={"audio_base64": _b64(_wav())})
        assert r.status_code == 200, r.text[:300]
        assert r.json()["top_1_class"] == "Happy"
        assert any(ad.endswith(".wav") for ad in _gecici_kalan(_yalitim)), "aparat: kilitli WAV silinmiş olmamalı"
    finally:
        if s.acik is not None:
            s.acik.close()


# ───────────────────────────── kidney_ct / histopath (indirici düşüşü + bütünlük) ─────────────────────────────


class _CTDedektor:
    def __init__(self, model_path=None, backend=None, device=None, silinsin=True, patlasin=False):
        self.kurulum = (model_path, backend, device)
        self.silinsin, self.patlasin = silinsin, patlasin

    def predict(self, yol):
        if self.patlasin:
            raise RuntimeError("ct motoru GIZLI")
        return {"n_detections": 1, "class_counts": {"Kidney Stone": 1}, "detections": [{"cls": "Kidney Stone"}]}

    def draw_overlay(self, yol, sonuc):
        if self.silinsin:
            os.unlink(yol)
        return np.full((20, 30, 3), 50, np.uint8)


def test_ct_indirici_HATASINDA_modul_yani_yola_duser_XAI_haritasi_doner(istemci, monkeypatch, _yalitim):
    """İndirici RuntimeError → KidneyCTDetector(model_path=<kök>/ai_hub/inference_human_kidney_ct/yolov8s.onnx, onnx, cpu);
    explain=true → xai alanları; overlay boyutu yanıt boyutu; geçici dosya silinmiş olsa da 200."""
    import ai_hub.inference_human_kidney_ct as ct_paket
    from ai_hub.inference_human_kidney_ct import inference_human_kidney_ct as ikt

    _indirici(monkeypatch, hata=RuntimeError("HF erişilemedi"))
    kurulan = []

    def _sinif(**k):
        d = _CTDedektor(**k)
        kurulan.append(d.kurulum)
        return d

    monkeypatch.setattr(ct_paket, "KidneyCTDetector", _sinif)
    monkeypatch.setattr(ikt, "xai_ct_isi_haritasi", lambda yol: {"xai_image_base64": "WFla", "method": "hirescam"})
    r = istemci.post("/api/ai/vision/kidney_ct", data={"image_base64": _b64(_jpg()), "explain": "true"})
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert kurulan == [
        (os.path.join(air.project_root, "ai_hub", "inference_human_kidney_ct", "yolov8s.onnx"), "onnx", "cpu")
    ]
    assert j["n_detections"] == 1 and j["class_counts"] == {"Kidney Stone": 1}
    assert (j["image_w"], j["image_h"]) == (30, 20)
    assert j["xai_image_base64"] == "WFla" and j["xai_method"] == "hirescam"
    assert _gecici_kalan(_yalitim) == []


def test_ct_XAI_hatasi_analizi_DUSURMEZ(istemci, monkeypatch):
    """explain=true, ısı haritası hata → 200 + xai_error (aciklamaUretilemedi), tespit alanları dolu."""
    from ai_hub.inference_human_kidney_ct import inference_human_kidney_ct as ikt

    air._models["kidney_ct"] = _CTDedektor(silinsin=False)

    def _xai(yol):
        raise RuntimeError("cam")

    monkeypatch.setattr(ikt, "xai_ct_isi_haritasi", _xai)
    r = istemci.post("/api/ai/vision/kidney_ct", data={"image_base64": _b64(_jpg()), "explain": "true"})
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert j["xai_error"] == ceviri.t("ai.sonuc.aciklamaUretilemedi") and j["n_detections"] == 1


def test_ct_cikarim_HATASI_500(istemci):
    """Dedektör hata → 500 + `ai.hata.bobrekCt`."""
    air._models["kidney_ct"] = _CTDedektor(patlasin=True)
    r = istemci.post("/api/ai/vision/kidney_ct", data={"image_base64": _b64(_jpg())})
    assert r.status_code == 500 and r.json()["detail"] == ceviri.t("ai.hata.bobrekCt")
    assert "GIZLI" not in r.text


@pytest.mark.parametrize(
    "uc, goreli",
    [
        ("/api/ai/vision/kidney_ct", "ai_hub/inference_human_kidney_ct/yolov8s.onnx"),
        ("/api/ai/vision/histopath", "ai_hub/inference_renal_histopath_kmc/v22_kmc_classictrio_kmc.onnx"),
        ("/api/ai/sound/cat", "ai_hub/inference_cat_sound/EfficientNet_Lite0.onnx"),
    ],
)
def test_BUTUNLUK_reddi_YUTULMAZ_503_dosya_adiyla(istemci, monkeypatch, uc, goreli):
    """İndirici ModelButunlukHatasi → modül-yanı yola DÜŞÜLMEZ; 503 + `ai.hata.modelButunluk` (dosya adı)."""
    from utils.model_downloader import ModelButunlukHatasi

    _sahte_ffmpeg(monkeypatch)
    _indirici(monkeypatch, hata=ModelButunlukHatasi("C:\\kp\\" + goreli.split("/")[-1], "özet tutmadı"))
    if uc.endswith("/cat"):
        r = istemci.post(uc, data={"audio_base64": _b64(_wav())})
    else:
        r = istemci.post(uc, data={"image_base64": _b64(_jpg())})
    assert r.status_code == 503, r.text[:300]
    assert r.json()["detail"] == ceviri.t("ai.hata.modelButunluk", dosya=goreli.split("/")[-1])


def test_histopath_indirici_HATASINDA_modul_yani_yola_duser_gecici_dosya_silinmis_olsa_da_200(
    istemci, monkeypatch, _yalitim
):
    """İndirici RuntimeError → RenalHistopathClassifier(model_path=<kök>/…/v22_kmc_classictrio_kmc.onnx, onnx, cpu); top_k=5 ile
    tahmin; sonuç alanları aynen."""
    import ai_hub.inference_renal_histopath_kmc as rh_paket

    _indirici(monkeypatch, hata=RuntimeError("HF erişilemedi"))
    kurulan, cagri = [], []

    class _Sinif:
        def __init__(self, **k):
            kurulan.append((k["model_path"], k["backend"], k["device"]))

        def predict(self, yol, top_k=None):
            cagri.append(top_k)
            os.unlink(yol)
            return {
                "top_1_class": "grade2",
                "top_1_prob": 0.6,
                "top_k": [["grade2", 0.6]],
                "probabilities": {"grade2": 0.6},
            }

    monkeypatch.setattr(rh_paket, "RenalHistopathClassifier", _Sinif)
    r = istemci.post("/api/ai/vision/histopath", data={"image_base64": _b64(_jpg())})
    assert r.status_code == 200, r.text[:300]
    hedef = os.path.join(air.project_root, "ai_hub", "inference_renal_histopath_kmc", "v22_kmc_classictrio_kmc.onnx")
    assert kurulan == [(hedef, "onnx", "cpu")] and cagri == [5]
    assert r.json()["top_1_class"] == "grade2" and r.json()["probabilities"] == {"grade2": 0.6}
    assert _gecici_kalan(_yalitim) == []


# ───────────────────────────── scratch ─────────────────────────────


def test_scratch_servis_422_JSON_hata_metni_AYNEN_iletilir(istemci, monkeypatch):
    """GPU servisi 422 {'error': …} → uç 422 + aynı metin (jenerik 500 değil)."""
    istekler = _servis(monkeypatch, lambda r: httpx.Response(422, json={"error": "pixel_mm aralık dışı"}))
    r = istemci.post("/api/ai/vision/scratch", data={"image_base64": _b64(_jpg())})
    assert r.status_code == 422 and r.json()["detail"] == "pixel_mm aralık dışı"
    assert istekler[0]["yol"] == "/infer/scratch"


def test_scratch_servis_422_govdesi_JSON_DEGILSE_gecersiz_parametre_metni(istemci, monkeypatch):
    """GPU servisi 422 + düz metin gövde → uç 422 + `ai.hata.gecersizParametre`."""
    _servis(monkeypatch, lambda r: httpx.Response(422, text="<html>bad</html>"))
    r = istemci.post("/api/ai/vision/scratch", data={"image_base64": _b64(_jpg())})
    assert r.status_code == 422 and r.json()["detail"] == ceviri.t("ai.hata.gecersizParametre")


def test_scratch_gomulu_analiz_KAYIPSIZ_PNG_ile_yapilir_gecici_dosya_silinmis_olsa_da_200(
    istemci, monkeypatch, _yalitim
):
    """Gömülü yol: analiz .png geçici dosyayla, yön / piksel ölçeği aynen geçer; sonuç alanları yanıta eklenir."""
    from ai_hub.inference_paper_dilek_hoca import inference_paper_dilek_hoca as ipd

    cagri = []

    def _analiz(yol, **k):
        cagri.append((os.path.splitext(yol)[1], k["scratch_yonu"], k["pixel_mm"]))
        os.unlink(yol)
        return {"kapanma_yuzdesi": 42.5}

    monkeypatch.setattr(ipd, "scratch_analiz", _analiz)
    r = istemci.post(
        "/api/ai/vision/scratch", data={"image_base64": _b64(_jpg()), "scratch_yonu": "yatay", "pixel_mm": "0.002"}
    )
    assert r.status_code == 200, r.text[:300]
    assert r.json() == {"status": "success", "kapanma_yuzdesi": 42.5}
    assert cagri == [(".png", "yatay", 0.002)]
    assert _gecici_kalan(_yalitim) == []


# ───────────────────────────── cat_organ ─────────────────────────────


def test_kedi_organ_ilk_istekte_CPU_ongorucu_kurulur_organlar_sirali_doner(istemci, monkeypatch, _yalitim):
    """CatOrganPredictor(device='cpu') kurulur; organlar kimliğe göre sıralı; geçici dosya silinmiş olsa da 200."""
    from ai_hub.inference_cat_organ import catorgan_predictor as cp

    kurulan = []

    class _Organ:
        def __init__(self, device=None):
            kurulan.append(device)

        def predict(self, yol, render=False):
            os.unlink(yol)
            return {
                "organs": {"3": {"name": "karaciğer", "reliability": 0.7}, 1: {"name": "mide", "reliability": 0.9}},
                "pnp_fit": {"residual_px": 3.14159, "scale_px_per_cm": 12.0},
                "pose_classifier": {"type": "yan"},
            }

    monkeypatch.setattr(cp, "CatOrganPredictor", _Organ)
    r = istemci.post("/api/ai/vision/cat_organ", data={"image_base64": _b64(_jpg())})
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert kurulan == ["cpu"]
    assert [o["id"] for o in j["organs"]] == [1, 3] and j["n_organs"] == 2
    assert j["pnp_residual_px"] == 3.1 and j["pose_type"] == "yan" and j["image_base64"] is None
    assert _gecici_kalan(_yalitim) == []


# ───────────────────────────── em_fantom ─────────────────────────────


def test_fantom_boru_hatti_HATASI_500_uc_etiketiyle(istemci, monkeypatch):
    """Boru hattı RuntimeError (sonlu-olmayan girdi DEĞİL) → 500 + `ai.hata.fantomAnaliz`."""

    class _Hat:
        def __init__(self, cfg, **k):
            self._predictor = None

        def process_image(self, img, **k):
            raise RuntimeError("halka kalibrasyonu GIZLI")

    air._models["em_fantom_cv"] = {"cfg": object(), "predictor": object(), "cls": _Hat}
    r = istemci.post("/api/ai/vision/em_fantom", data={"image_base64": _b64(_jpg())})
    assert r.status_code == 500 and r.json()["detail"] == ceviri.t("ai.hata.fantomAnaliz")
    assert "GIZLI" not in r.text


def test_fantom_TESPIT_YOK_ve_canli_E_baglami_KURULAMASA_da_yanit_doner(istemci, monkeypatch):
    """Boru hattı tespit edemedi (piksel kipi) → status 'no_detection', orijinal kare boyutu; canlı E bağlamı temizliği hata
    verse de yanıt 200 ve PEMF alanları (geçersiz) taşır."""
    from servers import efield_live as ef

    class _Sonuc:
        success, method, error = False, "pixel", "tumor_cluster_not_found"
        n_tumor = n_healthy = 0
        mm_per_px, timing_ms = 0.5, {"toplam": 3}

        def to_dict(self):
            return {"tumor_regions": [], "healthy_regions": [], "pemf_valid": False}

    class _Hat:
        def __init__(self, cfg, **k):
            self._predictor = None

        def process_image(self, img, **k):
            return _Sonuc(), None

    baglam = []

    def _set(bolgeler, *a, **k):
        baglam.append(list(bolgeler))
        raise RuntimeError("E bağlam kilidi")

    monkeypatch.setattr(ef, "set_context", _set)
    air._models["em_fantom_cv"] = {"cfg": object(), "predictor": None, "cls": _Hat}
    r = istemci.post("/api/ai/vision/em_fantom", data={"image_base64": _b64(_jpg(48, 64))})
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert j["status"] == "no_detection" and j["n_tumor"] == 0 and j["paneller"] == []
    assert (j["image_w"], j["image_h"]) == (64, 48)
    assert j["pemf_valid"] is False and j["pemf_kapisi"]["surulebilir"] is False
    assert baglam == [[]]


# ───────────────────────────── yükleyiciler ─────────────────────────────


def test_kedi_yukleyici_indirici_UYARISINDA_yine_CPU_ongorucu_kurar(monkeypatch):
    """em_kedi indirici hata verir → uyarı; KediPredictor(providers=['CPUExecutionProvider']) yine kurulur ve önbelleğe girer."""
    from ai_hub.em_kedi import inference_em_kedi as iek

    istenen = _indirici(monkeypatch, hata=RuntimeError("HF erişilemedi"))
    kurulan = []

    class _Kedi:
        def __init__(self, providers=None):
            kurulan.append(providers)

    monkeypatch.setattr(iek, "KediPredictor", _Kedi)
    m = air._get_or_load_kedi()
    assert isinstance(m, _Kedi) and air._models["em_kedi"] is m
    assert istenen == ["ai_hub/em_kedi/BiLSTM_XXL_Raw.onnx"] and kurulan == [["CPUExecutionProvider"]]


def test_fantom_yukleyici_indirici_UYARISINDA_boru_hatti_kurulur(monkeypatch):
    """em_fantom indirici hata → uyarı; PhantomCvPipeline(cfg, manual_fallback=False) kurulur, {cfg, predictor, cls} döner."""
    from ai_hub.inference_em_fantom import phantom_cv_v3 as pc3

    _indirici(monkeypatch, hata=RuntimeError("HF erişilemedi"))
    kurulan = []

    class _Hat:
        def __init__(self, cfg, manual_fallback=None):
            kurulan.append((cfg, manual_fallback))
            self._predictor = "ONGORUCU"

        @property
        def predictor(self):
            return self._predictor

    monkeypatch.setattr(pc3, "PhantomCvPipeline", _Hat)
    monkeypatch.setattr(pc3, "load_cabin_config", lambda yol: "CFG")
    d = air._yukle_em_fantom_cv()
    assert d == {"cfg": "CFG", "predictor": "ONGORUCU", "cls": _Hat} and kurulan == [("CFG", False)]


def _petri_hatti(monkeypatch, isit_hatasi=None):
    from ai_hub.inference_petri_dish import petri_cv_v2 as pv2

    kurulan = []

    class _Hat:
        def __init__(self, cfg, yolo_model_path=None, yolo_device=None):
            kurulan.append((cfg, yolo_model_path, yolo_device))
            self._predictor, self.yolo = "BAGGING", "YOLO"

        @property
        def predictor(self):
            return self._predictor

        def process_image(self, img):
            if isit_hatasi is not None:
                raise isit_hatasi
            return None

    monkeypatch.setattr(pv2, "PetriCvPipeline", _Hat)
    monkeypatch.setattr(pv2, "load_cabin_config", lambda yol: "CFG")
    return kurulan, _Hat


def test_petri_yukleyici_indirici_HATASINDA_modul_yani_YOLO_isitma_hatasi_yuklemeyi_DUSURMEZ(monkeypatch):
    """İndirici RuntimeError → yolo_path = <kök>/ai_hub/inference_petri_dish/yolo11m-seg.onnx (cpu); ısıtma karesi hata verse de
    sözlük {cfg, cls, yolo, predictor, yolo_path} döner."""
    _indirici(monkeypatch, hata=RuntimeError("HF erişilemedi"))
    kurulan, hat = _petri_hatti(monkeypatch, isit_hatasi=RuntimeError("ısıtma"))
    d = air._yukle_em_petri_cv()
    yol = os.path.join(air.project_root, "ai_hub", "inference_petri_dish", "yolo11m-seg.onnx")
    assert kurulan == [("CFG", yol, "cpu")]
    assert d == {"cfg": "CFG", "cls": hat, "yolo": "YOLO", "predictor": "BAGGING", "yolo_path": yol}


def test_petri_yukleyici_BUTUNLUK_reddini_YUTMAZ(monkeypatch):
    """İndirici ModelButunlukHatasi → aynı istisna yükselir, boru hattı KURULMAZ (başka köke düşüş yok)."""
    from utils.model_downloader import ModelButunlukHatasi

    _indirici(monkeypatch, hata=ModelButunlukHatasi("yolo11m-seg.onnx", "özet"))
    kurulan, _ = _petri_hatti(monkeypatch)
    with pytest.raises(ModelButunlukHatasi):
        air._yukle_em_petri_cv()
    assert kurulan == []
