# -*- coding: utf-8 -*-
"""AII-3.11 — Windows kullanıcı adı / TEMP ASCII dışıyken (ör. C:\\Users\\Müjde\\AppData\\Local\\Temp) AI uçlarının geçici görseli YAZILIR.

ÖLÇÜLEN (A3, 2026-10-12, gerçek ağırlık, taze süreç, kafes; `_inceleme/kayit/k5b_*.json`, `k5c_*.json`): router geçici kareyi
`cv2.imwrite(tmp.name, img)` ile yazıyor ve dönüşünü DENETLEMİYOR. OpenCV 4.11 Windows'ta ASCII dışı yola YAZAMAZ → False (sessiz), dosya 0 bayt
kalır; ultralytics içe aktarılınca cv2'yi Unicode-güvenli sürümle yamaladığı için sonuç İÇE AKTARMA SIRASINA bağlı:
  · `/api/ai/vision/thermal` (ultralytics hiç içe aktarılmaz) → HER çağrı 500 "Termal model hatası" (ASCII TEMP'te 200/200 — karşıt);
  · `/api/ai/vision/cat_organ` → ilk çağrı 500, ikinci 200; AI Pro CPU karesi (`_localize_organ_cpu`) → ilk kare `cv2.error … !buf.empty()`.
Kapı (ağırlıksız): ASCII dışı TEMP + OpenCV'nin ölçülen davranışı EN ALT katta (cv2.imwrite ASCII dışı yolda False) → ürünün yazdığı geçici
dosya boş olmamalı ve aynı görüntüye çözülmeli.
"""

from __future__ import annotations

import base64
import os
import tempfile

import numpy as np
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def unicode_temp(tmp_path, monkeypatch):
    import cv2

    d = tmp_path / "M\u00fcjde_Temp"
    d.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(d))
    gercek = cv2.imwrite

    def _opencv_windows_gibi(yol, img, *a, **k):
        # ölçüldü (k5b ham_once): ultralytics yamalamadan önce OpenCV 4.11 ASCII dışı yolda yazmaz ve False döner
        if any(ord(c) > 127 for c in str(yol)):
            return False
        return gercek(yol, img, *a, **k)

    monkeypatch.setattr(cv2, "imwrite", _opencv_windows_gibi)
    return d


def _kare(h=48, w=64):
    rng = np.random.default_rng(3)
    return rng.integers(0, 255, (h, w, 3), dtype=np.uint8)


def _b64(img) -> str:
    import cv2

    ok, buf = cv2.imencode(".jpg", img)
    return base64.b64encode(buf.tobytes()).decode()


def _oku(yol):
    import cv2

    ham = np.fromfile(yol, np.uint8)
    return int(ham.size), (None if ham.size == 0 else cv2.imdecode(ham, cv2.IMREAD_COLOR))


@pytest.fixture()
def istemci(monkeypatch):
    import servers.ai_router as air
    import servers.api_server as apis

    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    return TestClient(apis.app), air


def test_KRITIK_termal_ucu_ASCII_disi_TEMPte_gorseli_yazar(unicode_temp, istemci, monkeypatch):
    client, air = istemci
    goren: list = []

    class _Termal:
        def predict(self, image_path, threshold=0.5):
            from PIL import Image

            boyut, img = _oku(image_path)
            goren.append((boyut, None if img is None else img.shape))
            Image.open(image_path).convert("RGB")  # gerçek CatThermalPredictor.preprocess gibi — 0 baytta patlar
            return {"label": "Healthy", "probability_sick": 0.1, "confidence": 0.9}

    monkeypatch.setattr(air, "_get_or_load_model", lambda ad, yukleyici: _Termal())
    r = client.post("/api/ai/vision/thermal", data={"image_base64": _b64(_kare())})
    assert goren and goren[-1][0] > 0, f"geçici görsel BOŞ yazıldı (ASCII dışı TEMP): {goren} — yanıt {r.status_code}"
    assert goren[-1][1] == (48, 64, 3)
    assert r.status_code == 200, r.text[:200]


def test_KRITIK_kedi_organ_ucu_ASCII_disi_TEMPte_gorseli_yazar(unicode_temp, istemci, monkeypatch):
    client, air = istemci
    goren: list = []

    class _Organ:
        def predict(self, image_path, render=False, **k):
            goren.append(_oku(image_path)[0])
            raise RuntimeError(air._CAT_ABSENT_ERR_PREFIX + " (sahte: kedi yok)")

    monkeypatch.setattr(air, "_get_or_load_model", lambda ad, yukleyici: _Organ())
    # görüntü alanı kapısı rastgele gürültüyü "H&E" diye 422'ler (ölçüldü) → depodaki gerçek kedi fotoğrafı (küçültülmüş)
    from pathlib import Path

    import cv2

    kedi = cv2.imdecode(
        np.fromfile(
            str(
                Path(__file__).resolve().parents[1]
                / "ai_hub"
                / "inference_cat_organ"
                / "test_img"
                / "synthetic_aruco_test.jpg"
            ),
            np.uint8,
        ),
        cv2.IMREAD_COLOR,
    )
    kedi = cv2.resize(kedi, (kedi.shape[1] // 4, kedi.shape[0] // 4))
    client.post("/api/ai/vision/cat_organ", data={"image_base64": _b64(kedi)})
    assert goren and goren[-1] > 0, f"kedi organ geçici görseli BOŞ yazıldı (ASCII dışı TEMP): {goren}"


def test_KRITIK_AI_Pro_CPU_karesi_ASCII_disi_TEMPte_yazilir(unicode_temp, monkeypatch):
    import servers.ai_router as air

    goren: list = []

    class _Organ:
        def predict(self, image_path, render=False, target_oid=None, **k):
            goren.append(_oku(image_path)[0])
            raise RuntimeError(air._CAT_ABSENT_ERR_PREFIX + " (sahte: kedi yok)")

    monkeypatch.setattr(air, "_get_or_load_catorgan", lambda: _Organ())
    air._localize_organ_cpu(_kare(), 1)
    assert goren and goren[-1] > 0, f"AI Pro karesi TEMP'e BOŞ yazıldı (ASCII dışı kullanıcı adı): {goren}"
    assert not os.listdir(unicode_temp), "geçici kare silinmedi"
