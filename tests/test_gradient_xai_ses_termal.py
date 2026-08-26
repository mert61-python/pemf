# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GRADIENT-XAI: SES + TERMAL ISI HARİTALARI — Faz 2 (xai-entegrasyon-plani.md §5).

ÖLÇÜLEN DURUM: termal/ses analizleri sınıf+olasılık döner ama modelin görüntünün/melin
NERESİNE baktığı görünmez. Grad-CAM ailesi gradient ister → PT ikizleri Faz-0 karar #2
gereği release_assets tek-kaynağına kondu (GhostNetV2.pt ~21MB, EfficientNet_Lite0.pt
~15MB; download_model_sync YEREL çözer). ⚠️ grad-cam hook'ları thread-safe DEĞİL →
modül-seviyesi TEK-İŞ kilidi; XAI kendi PT instance'ını kullanır (canlı ONNX yoluna
dokunmaz); çıktı BELLEK-İÇİ base64 (karar #3: anlık gösterim, disk yok).

CI notu: torch test-ortamında yok + PT'ler gitignore'lu → gerçek-model testleri AÇIK
reason'lı skipif (CKD deseni); endpoint KABLOLAMA testleri mock'la her ortamda koşar.
"""

from __future__ import annotations

import base64
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

KOK = Path(__file__).resolve().parents[1]

_THERMAL_PT = KOK / "release_assets/ai_models/ai_hub/cat_thermal/GhostNetV2.pt"
_SOUND_PT = KOK / "release_assets/ai_models/ai_hub/inference_cat_sound/EfficientNet_Lite0.pt"


def _torch_var() -> bool:
    try:
        import torch  # noqa: F401

        return True
    except ImportError:
        return False


gercek_pt_gerekir = pytest.mark.skipif(
    not (_torch_var() and _THERMAL_PT.exists() and _SOUND_PT.exists()),
    reason="torch veya PT ikizleri yok (CI: torch test-setinde değil, PT gitignore'lu) — gerçek-model testi modelli ortamda",
)


def _b64_gorsel_cozulur(b64: str) -> np.ndarray:
    import cv2

    arr = np.frombuffer(base64.b64decode(b64), np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    assert img is not None, "xai_image_base64 geçerli bir görsel değil"
    return img


# ── 1) TERMAL — gerçek PT ile ────────────────────────────────────────────────
@gercek_pt_gerekir
def test_KRITIK_termal_isi_haritasi_URETIR_ve_DETERMINISTIK(tmp_path):
    import cv2

    from ai_hub.cat_thermal.inference_cat_thermal import xai_termal_isi_haritasi

    # Sentetik "termal" görüntü: sıcak merkezli gradyan (gerçekçi değil ama deterministik).
    yy, xx = np.mgrid[0:224, 0:224].astype(np.float32)
    sicak = np.exp(-(((yy - 112) ** 2 + (xx - 112) ** 2) / (2 * 40.0**2)))
    img = np.stack([sicak * 255, sicak * 120, (1 - sicak) * 180], axis=-1).astype(np.uint8)
    p = tmp_path / "termal.png"
    cv2.imwrite(str(p), img)

    r1 = xai_termal_isi_haritasi(str(p))
    assert set(r1) >= {"xai_image_base64", "method"}, f"eksik alanlar: {set(r1)}"
    ov = _b64_gorsel_cozulur(r1["xai_image_base64"])
    assert ov.shape[0] > 0 and ov.shape[1] > 0
    # Isı haritası DÜZ değil (uniform CAM = açıklama yok demektir):
    assert float(ov.std()) > 1.0, "overlay tekdüze — CAM anlamsız/boş"
    r2 = xai_termal_isi_haritasi(str(p))
    assert r1["xai_image_base64"] == r2["xai_image_base64"], "aynı görüntüye farklı ısı haritası (determinizm yok)"


@gercek_pt_gerekir
def test_KARSIT_KANIT_termal_PT_weights_only_TRUE():
    """Audit P3: PT yükleme pickle-RCE'ye kapalı olmalı (gelen kod False kullanıyordu)."""
    src = (KOK / "ai_hub/cat_thermal/inference_cat_thermal.py").read_text(encoding="utf-8")
    i = src.index("def _build_thermal_model_pt")
    govde = src[i : i + 1600]
    assert "weights_only=True" in govde, "_build_thermal_model_pt weights_only=True DEĞİL (P3 regresyonu)"
    assert "weights_only=False" not in govde


# ── 2) SES — gerçek PT ile ───────────────────────────────────────────────────
@gercek_pt_gerekir
def test_KRITIK_ses_isi_haritasi_URETIR(tmp_path):
    import soundfile as sf

    from ai_hub.inference_cat_sound.inference_cat_sound import xai_ses_isi_haritasi

    # 1 sn sentetik miyav-benzeri sinyal (600→900 Hz süpürme + zarf)
    sr = 22050
    t = np.linspace(0, 1.0, sr, endpoint=False)
    sinyal = (np.sin(2 * np.pi * (600 + 300 * t) * t) * np.exp(-2 * t)).astype(np.float32)
    wav = tmp_path / "miyav.wav"
    sf.write(str(wav), sinyal, sr)

    r = xai_ses_isi_haritasi(str(wav))
    assert set(r) >= {"xai_image_base64", "method"}, f"eksik alanlar: {set(r)}"
    ov = _b64_gorsel_cozulur(r["xai_image_base64"])
    assert float(ov.std()) > 1.0, "mel-CAM overlay tekdüze"


# ── 2b) PT yol çözücü (GPU-imaj smoke dersi, 2026-08-26) ─────────────────────
def test_KRITIK_pt_coz_ONCE_models_mount_sonra_downloader(tmp_path, monkeypatch):
    """ÖLÇÜLDÜ (cu128 smoke): imajda utils.model_downloader YOK (Dockerfile minimal) →
    'No module named utils.model_downloader' ile XAI zarif düşüşe takılıyordu. pt_coz
    ÖNCE PEMF_AI_MODELS_DIR mount'una bakar (ai_service yolu), yoksa downloader'a düşer."""
    from ai_hub.xai_utils.pt_yolu import pt_coz

    hedef = tmp_path / "ai_hub" / "cat_thermal"
    hedef.mkdir(parents=True)
    (hedef / "GhostNetV2.pt").write_bytes(b"x")
    monkeypatch.setenv("PEMF_AI_MODELS_DIR", str(tmp_path))
    p = pt_coz("ai_hub/cat_thermal/GhostNetV2.pt")
    assert str(p) == str(hedef / "GhostNetV2.pt"), f"mount önceliklenmedi: {p}"

    # KARŞIT: env yok → downloader yolu (yerelde release_assets'ten çözer)
    monkeypatch.delenv("PEMF_AI_MODELS_DIR", raising=False)
    p2 = pt_coz("ai_hub/cat_thermal/GhostNetV2.pt")
    assert Path(p2).name == "GhostNetV2.pt" and Path(p2).exists()


def test_YAPISAL_xai_fonksiyonlari_pt_coz_kullanir():
    """Beş gradient-XAI modülü de PT'yi TEK çözücüden almalı (imaj/klinik parite)."""
    for dosya in [
        "ai_hub/cat_thermal/inference_cat_thermal.py",
        "ai_hub/inference_cat_sound/inference_cat_sound.py",
        "ai_hub/feline_reticulocytes/inference_feline_reticulocytes.py",
        "ai_hub/inference_human_kidney_ct/inference_human_kidney_ct.py",
        "ai_hub/inference_renal_histopath_kmc/inference_renal_histopath_kmc.py",
    ]:
        src = (KOK / dosya).read_text(encoding="utf-8", errors="replace")
        assert "pt_coz(" in src, f"{dosya}: PT çözümü pt_coz'dan geçmiyor (GPU imajında kırılır)"


# ── 3) Tek-iş kilidi (yapısal — gerçek çağrıya pinli) ────────────────────────
def test_YAPISAL_xai_cagri_tek_is_kilidi_ICINDE():
    """grad-cam hook'ları thread-safe değil (plan §2): explain çağrısı modül kilidi içinde olmalı."""
    for dosya, fn_adi in [
        ("ai_hub/cat_thermal/inference_cat_thermal.py", "def xai_termal_isi_haritasi"),
        ("ai_hub/inference_cat_sound/inference_cat_sound.py", "def xai_ses_isi_haritasi"),
    ]:
        src = (KOK / dosya).read_text(encoding="utf-8", errors="replace")
        i = src.index(fn_adi)
        govde = src[i : i + 2600]
        kilit = govde.find("_XAI_KILIT")
        explain = govde.find(".explain(")
        assert kilit >= 0, f"{dosya}: XAI tek-iş kilidi (_XAI_KILIT) yok — eşzamanlı istekte bozuk heatmap"
        assert explain >= 0 and kilit < explain, f"{dosya}: explain() kilitten ÖNCE/DIŞINDA"


# ── 4) Uç kablolaması (mock — her ortamda) ───────────────────────────────────
_SENT = {"xai_image_base64": base64.b64encode(b"x").decode(), "method": "gradcam++"}


@pytest.fixture()
def istemci(monkeypatch):
    import servers.ai_router as air
    import servers.api_server as apis

    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    return TestClient(apis.app), air


def test_KRITIK_termal_endpoint_explain_kablolamasi(istemci, monkeypatch, tmp_path):
    import cv2

    client, air = istemci
    import ai_hub.cat_thermal.inference_cat_thermal as ict

    # analiz yolu: predictor mock (ONNX'siz), xai mock (PT'siz) → yalnız KABLOLAMA ölçülür
    class _P:
        def predict(self, image_path, threshold=0.5):
            return {"label": "Sick", "confidence": 0.9, "prob_sick": 0.9}

    monkeypatch.setattr(air, "_get_or_load_model", lambda ad, yukleyici: _P())
    cagri = []
    monkeypatch.setattr(ict, "xai_termal_isi_haritasi", lambda *a, **k: cagri.append(1) or _SENT)

    img = np.zeros((32, 32, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    b64 = base64.b64encode(buf.tobytes()).decode()

    r = client.post("/api/ai/vision/thermal", data={"image_base64": b64, "explain": "true"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("xai_image_base64") == _SENT["xai_image_base64"], "explain=true iken xai alanı yok"
    assert cagri, "xai fonksiyonu hiç çağrılmadı"

    # explain yokken alan SIZMAZ (mevcut sözleşme aynen)
    r2 = client.post("/api/ai/vision/thermal", data={"image_base64": b64})
    assert r2.status_code == 200 and "xai_image_base64" not in r2.json() and "xai_error" not in r2.json()


def test_KRITIK_termal_xai_hatasi_analizi_DUSURMEZ(istemci, monkeypatch):
    import cv2

    client, air = istemci
    import ai_hub.cat_thermal.inference_cat_thermal as ict

    class _P:
        def predict(self, image_path, threshold=0.5):
            return {"label": "Healthy", "confidence": 0.8, "prob_sick": 0.2}

    monkeypatch.setattr(air, "_get_or_load_model", lambda ad, yukleyici: _P())

    def _patla(*a, **k):
        raise RuntimeError("grad-cam patladı (test)")

    monkeypatch.setattr(ict, "xai_termal_isi_haritasi", _patla)
    ok, buf = cv2.imencode(".jpg", np.zeros((32, 32, 3), dtype=np.uint8))
    b64 = base64.b64encode(buf.tobytes()).decode()
    r = client.post("/api/ai/vision/thermal", data={"image_base64": b64, "explain": "true"})
    assert r.status_code == 200, f"XAI hatası analizi düşürdü: {r.text}"
    body = r.json()
    assert body.get("xai_error") and "xai_image_base64" not in body


def test_KRITIK_ses_SESSIZLIK_KAPISI_xai_den_ONCE(istemci, monkeypatch, tmp_path):
    """Saha kuralı (2026-08-15): sessiz kayda DUYGU ısı haritası üretilmez — kapı 422'si
    XAI'den ÖNCE keser (explain=true olsa bile xai fonksiyonu HİÇ çağrılmaz).
    WAV stdlib `wave` ile yazılır (soundfile CI test-setinde yok — koşu d6414c9 dersi)."""
    import wave

    client, air = istemci
    import ai_hub.inference_cat_sound.inference_cat_sound as ics

    cagri = []
    monkeypatch.setattr(ics, "xai_ses_isi_haritasi", lambda *a, **k: cagri.append(1) or _SENT)

    sr = 22050
    wav = tmp_path / "sessiz.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # 16-bit PCM
        w.setframerate(sr)
        w.writeframes(np.zeros(sr, dtype=np.int16).tobytes())  # 1 sn tam sessizlik
    b64 = base64.b64encode(wav.read_bytes()).decode()

    r = client.post("/api/ai/sound/cat", data={"audio_base64": b64, "explain": "true"})
    assert r.status_code == 422, f"sessiz kayıt kapıdan geçti: {r.status_code} {r.text[:200]}"
    assert not cagri, "sessiz kayıtta XAI ÇAĞRILDI — kapı-sırası ihlali (anlamsız duygu ısı-haritası)"


# ── 5) parite ────────────────────────────────────────────────────────────────
def test_YAPISAL_ai_service_ses_termal_XAI_paritesi():
    src = (KOK / "ai_service" / "app.py").read_text(encoding="utf-8")
    for uc, fn in [
        ('post("/infer/thermal")', "xai_termal_isi_haritasi"),
        ('post("/infer/sound")', "xai_ses_isi_haritasi"),
    ]:
        i = src.index(uc)
        govde = src[i : i + 4000]
        assert fn in govde and "explain" in govde, f":8100 {uc} XAI paritesi yok — kapı-paritesi dersi"
