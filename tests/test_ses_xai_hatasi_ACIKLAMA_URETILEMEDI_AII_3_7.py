# -*- coding: utf-8 -*-
"""AII-3.7 — ses ucu: XAI hata verirse (ör. AI1.X7 boş harita RuntimeError'ı) analiz düşmez VE yanıt "Açıklama üretilemedi" der.

AI1.X7 boş haritayı modülde `RuntimeError`'a çevirdi ("başarılı" dönmesin); kullanıcıya görünen karşılığı router'ın `xai_error` alanı.
Termal ucunda bu sözleşme kapılı (`test_KRITIK_termal_xai_hatasi_analizi_DUSURMEZ`), ses ucunda DEĞİL: ÖLÇÜLDÜ (A3) — `xai_error`
satırını silen mutant (X7_MC) ses kapı kümesinde (54 test) 46 geçti / 8 atlandı, YEŞİL → istemci haritasız ve nedensiz kalır.
Ağırlıksız (sınıflandırıcı ve XAI en alt çağrı sınırında sahte; ffmpeg + RMS gerçek).
"""

from __future__ import annotations

import base64
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def istemci(monkeypatch):
    import servers.ai_router as air
    import servers.api_server as apis

    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    return TestClient(apis.app), air


def _ses_b64(tmp_path) -> str:
    sr = 22050
    t = np.arange(sr * 2) / sr
    x = (0.3 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)  # ~−10 dBFS, sessiz DEĞİL
    p = tmp_path / "miyav.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(x.tobytes())
    return base64.b64encode(p.read_bytes()).decode()


def test_KRITIK_ses_XAI_hatasi_analizi_DUSURMEZ_ve_ACIKLAMA_URETILEMEDI_der(istemci, monkeypatch, tmp_path):
    client, air = istemci
    import ai_hub.inference_cat_sound.inference_cat_sound as ics

    class _S:
        def predict(self, audio_path, top_k=3):
            olas = {f"c{i}": 0.1 for i in range(10)}
            olas["c0"] = 0.55
            # gerçek `CatSoundClassifier.predict` sözleşmesi (inference_cat_sound.py:301-308)
            return {
                "audio_path": str(audio_path),
                "top_1_class": "c0",
                "top_1_prob": 0.55,
                "top_k": [{"class": "c0", "prob": 0.55}],
                "probabilities": olas,
            }

    monkeypatch.setattr(air, "_get_or_load_model", lambda ad, yukleyici: _S())

    def _bos(*a, **k):
        raise RuntimeError("Ses isi haritasi BOS cikti (yontem gradcam) — aciklama gosterilmedi")

    monkeypatch.setattr(ics, "xai_ses_isi_haritasi", _bos)
    r = client.post("/api/ai/sound/cat", data={"audio_base64": _ses_b64(tmp_path), "explain": "true"})
    assert r.status_code == 200, f"XAI hatası ses analizini düşürdü: {r.status_code} {r.text[:200]}"
    govde = r.json()
    assert "xai_image_base64" not in govde
    assert govde.get("xai_error") == "Açıklama üretilemedi", (
        f"XAI başarısızken yanıt kullanıcıya nedeni söylemiyor (xai_error={govde.get('xai_error')!r}) — harita sessizce kayboluyor"
    )
