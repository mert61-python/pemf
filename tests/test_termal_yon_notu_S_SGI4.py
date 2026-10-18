# -*- coding: utf-8 -*-
"""S-SGI.4 — TERMAL PALET YÖNÜ NOTU (sahip kararı 2026-10-18: "Uyarı + tezgâh ölçümü", seçenek a).

Ölçülen boşluk (SGI-2.6, gerçek GhostNetV2): SG.G4 kapısı palet ÜYELİĞİNİ ölçer, YÖNÜNÜ ölçmez — aynı sıcaklık alanının palet × iki yön
boyamasının HEPSİ "doğrulandı"; TERS palette model teşhisi tersine çevirir (hasta 03b inferno TERS → "Sağlıklı %1,8", yanlış negatif).
SÖZLEŞME: kapı kararı DEĞİŞMEZ (ters palet yine geçer, "doğrulandı" kalır); yanıt, eşleşen paletin KAMERA yönünü söyleyen `yon_notu`
taşır — "doğrulandı" sonucunda da. Renksiz (akromatik) girdide not YOK (beyaz-sıcak / siyah-sıcak yönü ölçülmedi). Kapı kapalıyken
genel not. Yön SEZGİSİ (seçenek c) T2-SGI.4 tezgâh ölçümünden sonra — burada YOK.
Beklenen metinler BURADA sabit (kapı sabiti mutasyon hedefinden okunmaz).
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

KOK = Path(__file__).resolve().parents[1]
SAGLIKLI = KOK / "tests" / "xai_veri" / "termal_saglikli_03a_224.png"
HASTA = KOK / "tests" / "xai_veri" / "termal_hasta_03b_224.png"

ON = "Paletin kamera yönünde olduğundan emin olun ("
SON = ") — ters palette sonuç tersine dönebilir."
BEKLENEN_IPUCU = {
    "INFERNO": "soğuk = siyah / mor, sıcak = sarı",
    "MAGMA": "soğuk = siyah / mor, sıcak = açık sarı / beyaz",
    "PLASMA": "soğuk = lacivert / mor, sıcak = sarı",
    "HOT": "soğuk = siyah, sıcak = sarı / beyaz",
    "JET": "soğuk = mavi, sıcak = kırmızı",
    "TURBO": "soğuk = mavi / mor, sıcak = kırmızı",
    "RAINBOW": "soğuk = mavi / mor, sıcak = kırmızı",
}
GENEL_IPUCU = "soğuk = koyu / mor, sıcak = sarı / beyaz"


def _oku(p: Path) -> np.ndarray:
    img = cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)
    assert img is not None, p
    return img


def _inferno_skaleri(img: np.ndarray) -> np.ndarray:
    """Inferno boyalı termal görüntüden sıcaklık skaleri (LUT'a en yakın indeks)."""
    lut = cv2.applyColorMap(np.arange(256, dtype=np.uint8).reshape(-1, 1), cv2.COLORMAP_INFERNO).reshape(256, 3)
    p = img.reshape(-1, 3).astype(np.float32)
    lut = lut.astype(np.float32)
    out = np.empty(len(p), np.uint8)
    for i in range(0, len(p), 8192):
        out[i : i + 8192] = np.argmin(((p[i : i + 8192, None, :] - lut[None]) ** 2).sum(-1), 1)
    return out.reshape(img.shape[:2])


def _boya_jpg(skaler: np.ndarray, palet: str) -> np.ndarray:
    ok, b = cv2.imencode(
        ".jpg", cv2.applyColorMap(skaler, getattr(cv2, f"COLORMAP_{palet}")), [cv2.IMWRITE_JPEG_QUALITY, 60]
    )
    assert ok
    return cv2.imdecode(b, cv2.IMREAD_COLOR)


def test_KRITIK_DOGRULANDI_sonucunda_da_kamera_YONU_notu():
    from utils import image_domain as dom

    for p in (SAGLIKLI, HASTA):
        g = dom.termal_girdi_dogrulamasi(_oku(p))
        assert g["durum"] == "termal_paleti" and g["dogrulandi"] is True and g["uyari"] is None, (p.name, g)
        assert g["yon_notu"] == ON + BEKLENEN_IPUCU["INFERNO"] + SON, (p.name, g)


def test_KRITIK_TERS_palet_KAPI_KARARI_AYNI_ve_NOT_yine_VAR():
    """Ölçülen yanlış negatifin girdisi (hasta 03b inferno TERS): kapı kararı DEĞİŞMEDİ (geçer, doğrulandı) — azaltım NOT'tur."""
    from utils import image_domain as dom

    ters = _boya_jpg(255 - _inferno_skaleri(_oku(HASTA)), "INFERNO")
    g = dom.termal_girdi_dogrulamasi(ters)
    assert g["dogrulandi"] is True, g
    assert g["yon_notu"] == ON + BEKLENEN_IPUCU["INFERNO"] + SON, g
    dom.check(ters, "thermal")  # kapı ters paleti REDDETMEZ (yön sezgisi T2-SGI.4 ölçümünden sonra)


@pytest.mark.parametrize("palet", sorted(BEKLENEN_IPUCU))
@pytest.mark.parametrize("yon", ["dogru", "TERS"])
def test_KRITIK_not_ESLESEN_paletin_kamera_yonunu_soyler(palet, yon):
    from utils import image_domain as dom

    sk = _inferno_skaleri(_oku(SAGLIKLI))
    g = dom.termal_girdi_dogrulamasi(_boya_jpg(sk if yon == "dogru" else 255 - sk, palet))
    assert g["olcum"]["palet"] == palet.lower() and g["dogrulandi"] is True, g
    assert g["yon_notu"] == ON + BEKLENEN_IPUCU[palet] + SON, g


def test_KARSIT_renksiz_girdide_YON_NOTU_YOK_kapi_kapaliyken_GENEL_not(monkeypatch):
    from utils import image_domain as dom

    gri = cv2.cvtColor(_oku(HASTA), cv2.COLOR_BGR2GRAY)
    g = dom.termal_girdi_dogrulamasi(cv2.cvtColor(gri, cv2.COLOR_GRAY2BGR))
    assert g["durum"] == "akromatik" and g["yon_notu"] is None, g
    monkeypatch.setenv("PEMF_AI_DOMAIN_GUARD", "0")
    g = dom.termal_girdi_dogrulamasi(gri)
    assert g["durum"] == "kapali" and g["yon_notu"] == ON + GENEL_IPUCU + SON, g


def test_KARSIT_palet_bilinmiyorsa_GENEL_not():
    from utils import image_domain as dom

    assert dom.termal_yon_notu("kararsiz", {}) == ON + GENEL_IPUCU + SON
    assert dom.termal_yon_notu("bilinmiyor", {"palet": "yeni_palet"}) == ON + GENEL_IPUCU + SON
