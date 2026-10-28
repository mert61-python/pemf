# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""İG-5.57 · :8100 modalite kapısı, kapının çözücüsünün (cv2) OKUYAMADIĞI girdide REDDEDER (A-24) — D67, 2026-10-28.

🔴 ÖLÇÜLEN DURUM (HEAD ebf1c3fe, sonda `_inceleme/IG-5.57`): A-24 / D4.09 `analyze` iç hatasını üç profilde de kapatmıştı; ama
`ai_service/app.py::_kapi` girdiyi `_read_bgr` (cv2.imdecode) ile çözemezse `except Exception: return None` ile isteği MODELE
geçiriyordu ("uç kendi except'iyle 500 döner" varsayımı). Modeller görüntüyü PIL ile açar (`RenalHistopathClassifier`
`Image.open(...).convert("RGB")`); cv2 4.11'in okuyamadığı GIF / ICO / PCX / TGA'yı PIL okur → CT kesiti (07a) GIF'e
çevrilince `/infer/histopath` → **200 "grade4" 0,99995** (gerçek sınıflandırıcı, cpu), kapı hiç çalışmadan ve TEK SATIR günlük
yazılmadan. Gömülü ve mikroservis profili aynı girdiyi zaten reddediyor (backend `_decode_image` cv2 ile çözer; çözemezse
modele / mikroservise gitmez).
KAPI: kuralı olan etikette cv2'nin okuyamadığı (PIL'in okuduğu) girdi → 422 `domain_check_error` + WARNING günlüğü, model
ÇAĞRILMAZ; app.py'deki HER `_kapi(data, "<etiket>")` çağrı yeri aynı reddi verir; karşıt-kanıt: kapı kapalıyken
(`PEMF_AI_DOMAIN_GUARD=0`) ve kuralsız etikette eski yol (None), cv2'nin okuduğu aynı görüntü modaliteyle (domain_mismatch) reddedilir.
Fikstürsüz (sentetik gri "kesit"): her ortamda koşar.
"""

from __future__ import annotations

import io
import logging
import re
from pathlib import Path

import capraz
import numpy as np
import pytest

KOK = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def app_modulu():
    capraz.paket_yoksa_atla("onnxruntime", sebep="ai_service :8100 calisma zamani paketi yok (CI)")
    from ai_service import app as _app

    return _app


def _gri_kesit():
    """CT benzeri AKROMATİK görüntü (gri tonlamalı daire + gürültü) — histopath ucu için yanlış modalite."""
    y, x = np.mgrid[0:256, 0:256]
    g = (np.hypot(x - 128, y - 128) < 90) * 160 + 40
    g = np.clip(g + np.random.default_rng(3).normal(0, 6, g.shape), 0, 255).astype(np.uint8)
    return np.dstack([g, g, g])


def _kodla(rgb: np.ndarray, bicim: str) -> bytes:
    from PIL import Image

    bio = io.BytesIO()
    Image.fromarray(rgb).save(bio, bicim)
    return bio.getvalue()


def _cv2_okur_mu(veri: bytes) -> bool:
    import cv2

    return cv2.imdecode(np.frombuffer(veri, np.uint8), cv2.IMREAD_COLOR) is not None


def _pil_okur_mu(veri: bytes) -> bool:
    from PIL import Image

    try:
        with Image.open(io.BytesIO(veri)) as im:
            im.convert("RGB").load()
        return True
    except Exception:  # noqa: BLE001 — yalnız "PIL okuyor mu" sorusu
        return False


@pytest.fixture()
def sv(app_modulu, monkeypatch):
    """`:8100` gerçek TestClient'ı; sınıflandırıcı CASUS — ürünün sınıflandırıcısı gibi görüntüyü PIL ile AÇAR."""
    from fastapi.testclient import TestClient

    monkeypatch.delenv("PEMF_AI_DOMAIN_GUARD", raising=False)
    cagrilar: list[str] = []

    class _Casus:
        device = "sahte"

        def predict(self, yol, *a, **k):
            from PIL import Image

            with Image.open(yol) as im:  # RenalHistopathClassifier ile AYNI çözücü
                im.convert("RGB").load()
            cagrilar.append(str(yol))
            return {
                "top_1_class": "grade4",
                "top_1_prob": 0.9999,
                "top_k": [("grade4", 0.9999)],
                "probabilities": {"grade4": 0.9999},
            }

        def draw_overlay(self, *a, **k):
            return np.zeros((8, 8, 3), dtype=np.uint8)

    monkeypatch.setattr(app_modulu.predictors, "get", lambda ad: _Casus())
    return TestClient(app_modulu.app, raise_server_exceptions=False), cagrilar


def test_kurulum_PCX_cv2_OKUMAZ_PIL_OKUR():
    """Ölçülen kolun ön-koşulu: bu biçimi kapının çözücüsü okumaz, modelin çözücüsü okur (aksi hâlde kol ölçülmez)."""
    veri = _kodla(_gri_kesit(), "PCX")
    assert _pil_okur_mu(veri), "kurulum: PIL PCX okuyamıyor — modelin çözücüsü bu girdiyi açamaz, kol ölçülmez"
    assert not _cv2_okur_mu(veri), (
        "kurulum: cv2 artık PCX okuyor — kapının çözemediği kol ölçülmüyor; testi cv2'nin OKUYAMADIĞI (PIL'in okuduğu) "
        "başka bir biçimle yeniden kurun"
    )


@pytest.mark.parametrize("bicim", ["PCX", "GIF", "TGA", "ICO"])
def test_KRITIK_8100_histopath_COZULEMEYEN_CT_modele_GITMEZ(sv, bicim, caplog):
    client, cagrilar = sv
    veri = _kodla(_gri_kesit(), bicim)
    assert _pil_okur_mu(veri), f"kurulum: PIL {bicim} okuyamıyor"
    with caplog.at_level(logging.WARNING):
        r = client.post(
            "/infer/histopath", files={"file": (f"kesit.{bicim.lower()}", veri, "application/octet-stream")}
        )
    assert not cagrilar, (
        f"{bicim}: kapı girdiyi çözemedi ama istek MODELE gitti (fail-open) → HTTP {r.status_code} {r.text[:160]}"
    )
    assert r.status_code == 422, f"{bicim}: beklenen 422 ret, alınan HTTP {r.status_code}: {r.text[:200]}"
    j = r.json()
    assert j.get("domain_check_error") is True or j.get("domain_mismatch") is True, f"ret nedeni işaretlenmedi: {j}"
    if not _cv2_okur_mu(veri):
        assert j.get("domain_check_error") is True, (
            f"{bicim}: cv2 okuyamadığı girdide ret `domain_check_error` olmalı: {j}"
        )
        assert "analiz YAPILMADI" in j.get("error", ""), f"ret iletisi nedeni söylemiyor (A-24): {j}"
        uyarilar = [
            k
            for k in caplog.records
            if k.levelno >= logging.WARNING and "ÇALIŞTIRILAMADI [histopath]" in k.getMessage()
        ]
        assert uyarilar, f"{bicim}: ret WARNING günlüğüne yazılmadı (iz yalnız DEBUG / hiç yok)"


def test_KRITIK_8100_HER_kapi_cagri_yeri_COZULEMEYEN_girdiyi_REDDEDER(app_modulu, monkeypatch):
    """app.py'deki her `_kapi(data, "<etiket>")` çağrı yerinin etiketi: cv2'nin okuyamadığı girdi → 422."""
    monkeypatch.delenv("PEMF_AI_DOMAIN_GUARD", raising=False)
    kaynak = (KOK / "ai_service" / "app.py").read_text(encoding="utf-8")
    etiketler = sorted(set(re.findall(r'_kapi\(data, "([a-z_]+)"\)', kaynak)))
    assert len(etiketler) >= 10, f"kurulum: _kapi çağrı yerleri bulunamadı ({etiketler})"
    veri = _kodla(_gri_kesit(), "PCX")
    gecen = []
    for et in etiketler:
        red = app_modulu._kapi(veri, et)
        if red is None or red.status_code != 422:
            gecen.append(et)
    assert not gecen, f"cv2'nin okuyamadığı girdi şu uçlarda kapıdan GEÇİYOR (fail-open): {gecen}"


def test_KARSIT_KANIT_kapi_KAPALI_ve_KURALSIZ_etikette_eski_yol(app_modulu, monkeypatch):
    veri = _kodla(_gri_kesit(), "PCX")
    monkeypatch.delenv("PEMF_AI_DOMAIN_GUARD", raising=False)
    assert app_modulu._kapi(veri, "kurali_olmayan_etiket") is None, (
        "kuralsız etiket artık reddediliyor (kapsam genişledi)"
    )
    monkeypatch.setenv("PEMF_AI_DOMAIN_GUARD", "0")
    assert app_modulu._kapi(veri, "histopath") is None, "kapı kapalıyken (PEMF_AI_DOMAIN_GUARD=0) ret sürüyor"


def test_KARSIT_KANIT_cv2_OKUDUGU_ayni_gorsel_MODALITEYLE_reddedilir(sv):
    """Aynı gri kesit PNG (cv2 okur) → ret `domain_mismatch` (kapı gerçekten modaliteyi ölçüyor, her şeyi reddetmiyor)."""
    client, cagrilar = sv
    veri = _kodla(_gri_kesit(), "PNG")
    assert _cv2_okur_mu(veri)
    r = client.post("/infer/histopath", files={"file": ("kesit.png", veri, "image/png")})
    assert r.status_code == 422 and r.json().get("domain_mismatch") is True, f"{r.status_code} {r.text[:200]}"
    assert not cagrilar
