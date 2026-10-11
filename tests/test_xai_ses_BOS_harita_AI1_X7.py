# -*- coding: utf-8 -*-
"""AI1.X7 — kedi sesi mel ısı haritası BOŞ çıkmaz; boş harita "başarılı" dönmez (hoca XAI v3: `explain_cat_sound_v2.py`).

ÖLÇÜLEN DURUM (2026-10-11, gerçek EfficientNet_Lite0.pt, CPU, hocanın doğrulama 20 örneği + PEMF 10a/b/c; `DUZELTME-AI1.md` X7):
varsayılan Grad-CAM++ 2/23 örnekte TAMAMEN BOŞ harita (maks 0, std 0) üretip "başarılı" dönüyordu — biri PEMF test girdisi 10c
"Kedi sesi — ağrı" (= hocanın Paining/Cat_YoutubeLLT42369, bayt-aynı); Grad-CAM ve HiRes-CAM 0/23 boş. Varsayılan Grad-CAM;
boş harita RuntimeError → router / :8100 "Açıklama üretilemedi". Sessizlik kapısı XAI'den ÖNCE kalır
(`test_gradient_xai_ses_termal.py::test_KRITIK_ses_SESSIZLIK_KAPISI_xai_den_ONCE`).
"""

from __future__ import annotations

import ast
import base64
from pathlib import Path

import numpy as np
import pytest

KOK = Path(__file__).resolve().parents[1]
AGRI = KOK / "tests" / "xai_veri" / "ses_agri_10c.mp3"
_PT = "ai_hub/inference_cat_sound/EfficientNet_Lite0.pt"


@pytest.fixture(scope="module")
def ses():
    pytest.importorskip("torch")
    pytest.importorskip("pytorch_grad_cam")
    pytest.importorskip("librosa")
    from golden.eser import atla, eser_var_mi

    if not eser_var_mi(_PT):
        atla(f"ses PT ağırlığı yok ({_PT})")
    from ai_hub.inference_cat_sound import inference_cat_sound as ics

    return ics


def test_KRITIK_agri_sesinde_varsayilan_harita_BOS_DEGIL(ses):
    import cv2

    r = ses.xai_ses_isi_haritasi(str(AGRI))
    assert r["method"] == "gradcam", f"varsayılan yöntem {r['method']!r}"
    ov = cv2.imdecode(np.frombuffer(base64.b64decode(r["xai_image_base64"]), np.uint8), cv2.IMREAD_COLOR)
    mel = cv2.cvtColor(np.asarray(ses.audio_to_mel_image(str(AGRI)), np.uint8), cv2.COLOR_RGB2BGR)
    assert ov is not None and ov.shape == mel.shape
    assert float(np.abs(ov.astype(int) - mel.astype(int)).mean()) > 2.0, "overlay mel ile aynı — harita boş"


def test_KRITIK_BOS_harita_BASARILI_donmez(ses):
    """Bu örnekte Grad-CAM++ boş harita üretir (ölçüldü): eskiden düz bir overlay 'başarılı' dönüyordu; artık açık hata."""
    with pytest.raises(RuntimeError, match="BOS"):
        ses.xai_ses_isi_haritasi(str(AGRI), None, "gradcam++")


def _form_varsayilani(kaynak: Path, fonksiyon: str, arg: str):
    agac = ast.parse(kaynak.read_text(encoding="utf-8"))
    fn = next(
        d for d in ast.walk(agac) if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)) and d.name == fonksiyon
    )
    adlar = [a.arg for a in fn.args.args]
    varsayilan = fn.args.defaults[adlar.index(arg) - (len(adlar) - len(fn.args.defaults))]
    return varsayilan.args[0].value if isinstance(varsayilan, ast.Call) else getattr(varsayilan, "value", None)


def test_KRITIK_router_ve_modul_varsayilani_GRADCAM():
    assert _form_varsayilani(KOK / "apps/backend/servers/ai_router.py", "analyze_cat_sound", "xai_method") == "gradcam"
    assert (
        _form_varsayilani(KOK / "ai_hub/inference_cat_sound/inference_cat_sound.py", "xai_ses_isi_haritasi", "method")
        == "gradcam"
    )
    src = (KOK / "ai_service/app.py").read_text(encoding="utf-8")
    govde = src[src.index('post("/infer/sound")') :]
    govde = govde[: govde.index("\n@app.")]
    assert 'xai_ses_isi_haritasi(tmp_wav, None, xai_method or "gradcam")' in govde, (
        ":8100 ses varsayılanı Grad-CAM değil"
    )
