# -*- coding: utf-8 -*-
"""KD-2b · Y264 (sahip 2026-11-10 gece) — petri KUYU YARIÇAPI eşiği (`plate_grid._quality_warnings`: `well_radius_px < 25` →
`low_resolution`) KALDIRILDI.

ÖLÇÜLDÜ (KD-2 uçtan uca, `DENETIM/KAMERA-DUZLEM.md` 4.1): kabin kamerası üst kapağa sabit (~37 cm) → 24'lük plakada kuyu yarıçapı
24 px; eşik HER karede `low_resolution` verip PEMF kapısını (YENIDEN_CEKIM) düşürüyordu → koşullu kipte petri hiç sürülmüyordu.
Kuyu konumunun doğruluğu yarıçaptan değil ızgara uyumundan gelir (aday sayısı, ECC, kuyu skoru, kırpık plaka, kamera / aralık
denetimi, kör bölge) — o nedenler AYNEN keser.

Kapsam YALNIZ petri eşiği: fantom TÜMÖR eşiği (`tumor_detect`: `r_typ < 6` → `low_resolution`) ve kapının `low_resolution`
nedeni (fantom yolu) KALIR.

Sahte EN ALT katta (AII-1.1 düzeni): YOLO ipucu kapalı (Hough + ECC), doz modeli çağrı sınırında sahte. 24 px kare = kâhinin tek
uyarısız plakası ölçeklenerek; ölçek hocanın `mm_per_px`inden hesaplanır, sonuçtaki yarıçap AYRICA doğrulanır (vakum kapısı: kare
eski eşiğin altında değilse test hiçbir şey kanıtlamaz). Sabitler testin kendisinde — mutasyon hedefinden OKUNMAZ.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

KAHIN = Path(__file__).resolve().parent / "kahin" / "hoca_cv_2026_10"
#: 24'lük plaka kuyu çapı (SBS/ANSI; hocanın PLATE_SPECS) — test kendi sabitini taşır.
_KUYU_CAP_MM = 15.6
#: Kâhinde tek uyarısız plaka (AII-1.1 karşıtı); hocanın ölçeği `beklenen_petri/summary.csv` `mm_per_px`.
_TAM_TEMIZ = "WhatsApp Image 2026-10-02 at 19.40.15(2).jpeg"
#: Fantom kâhin karesi — ÖLÇÜLDÜ (KD-2b): tam boyda 5 tümör, yarıçap 34–47 px, uyarısız; ×0,08'de 2 tümör, ~4 px → eşik altı.
_FANTOM = "WhatsApp Image 2026-10-02 at 19.40.11.jpeg"
_FANTOM_OLCEK = 0.08


class _SahteEM:
    """PetriPredictor.predict sözleşmesi (D1–D7, P1–P7, result_E_*) — model çağrı sınırında sahte."""

    def predict(self, x, y, z, organ_id, achieved_B, duty_sum):
        d = {f"D{k}": 0.5 for k in range(1, 8)}
        d.update({f"P{k}": 100.0 for k in range(1, 8)})
        d.update(result_E_healthy=0.1, result_E_cancer=0.1, result_E_avg=0.1)
        return d


def _oku(alt, ad):
    import cv2

    img = cv2.imdecode(np.fromfile(str(KAHIN / alt / ad), dtype=np.uint8), cv2.IMREAD_COLOR)
    assert img is not None, ad
    return img


def _hoca_mm_per_px(ad):
    satir = next(
        s for s in csv.DictReader(open(KAHIN / "beklenen_petri" / "summary.csv", encoding="utf-8")) if s["image"] == ad
    )
    return float(satir["mm_per_px"])


def _kare(hedef_yaricap_px):
    """Kâhin plakası, kuyu yarıçapı ≈ `hedef_yaricap_px` olacak ölçekte (INTER_AREA: gerçek kameradaki gibi alt örnekleme)."""
    import cv2

    olcek = hedef_yaricap_px * _hoca_mm_per_px(_TAM_TEMIZ) / (_KUYU_CAP_MM / 2.0)
    return cv2.resize(_oku("petri", _TAM_TEMIZ), None, fx=olcek, fy=olcek, interpolation=cv2.INTER_AREA)


def _hough_boru_hatti(tmp_path):
    from ai_hub.inference_petri_dish.petri_cv_v2 import PetriCvPipeline, load_cabin_config

    sahte_yol = tmp_path / "yolo_ipucu_yok.onnx"
    sahte_yol.write_bytes(b"")  # dedektör yalnız varlık denetler (tembel yükleme); aşağıda kapatılır
    pl = PetriCvPipeline(
        load_cabin_config(None), yolo_model_path=sahte_yol, yolo_device="cpu", a1_cabin_mm=[0.0, 0.0, 0.0]
    )
    pl.yolo = None  # plate_grid._yolo_candidates(yolo=None) -> [] : Hough + ECC
    pl._predictor = _SahteEM()
    return pl


def _kodlar(uyarilar):
    return {str(u).split(":", 1)[0].strip() for u in uyarilar}


# ── 1. Önce-kırmızı: eski eşiğin altındaki kuyulu karede `low_resolution` YOK, kapı bu nedenle DÜŞMEZ ───────────────────────────
@pytest.mark.parametrize("hedef", [24.0, 18.0], ids=["24px_kabin_kamerasi", "18px"])
def test_KRITIK_kuyu_yaricapi_25px_ALTINDA_low_resolution_YOK_ve_kapi_SURULEBILIR(tmp_path, hedef):
    from ai_hub.cv_ortak import pemf_kapisi

    r, _ = _hough_boru_hatti(tmp_path).process_image(_kare(hedef))
    assert r.success and r.n_wells == 24 and r.pemf_valid is True, (r.error, r.n_wells, r.pemf_valid, r.warnings)
    yaricap = (_KUYU_CAP_MM / 2.0) / r.mm_per_px
    # Vakum kapısı: kare gerçekten ESKİ eşiğin (25 px) altında ve hedefe yakın — değilse test bir şey kanıtlamaz.
    assert abs(yaricap - hedef) < 1.5 and yaricap < 25.0, f"kuyu yarıçapı {yaricap:.2f} px (hedef {hedef})"
    assert "low_resolution" not in _kodlar(r.warnings), r.warnings
    k = pemf_kapisi.degerlendir(r, model="petri")
    assert "low_resolution" not in k["nedenler"], k["nedenler"]
    assert k["surulebilir"] is True, (k["nedenler"], r.warnings)


# ── 2. Karşıt: aynı 24 px karede ÖTEKİ nedenler hâlâ keser ────────────────────────────────────────────────────────────────────
def test_karsit_24px_kirpik_karede_IZGARA_nedenleri_HALA_KESER(tmp_path):
    from ai_hub.cv_ortak import pemf_kapisi

    img = _kare(24.0)
    yarim = img[:, img.shape[1] // 2 :].copy()  # plakanın sağ yarısı kadrajda (AII-1.1 sınıfı)
    r, _ = _hough_boru_hatti(tmp_path).process_image(yarim)
    k = pemf_kapisi.degerlendir(r, model="petri")
    assert k["surulebilir"] is False, (k["nedenler"], r.warnings)
    assert {"plate_cropped", "kuyu_skor_esigi", "few_candidates", "basarisiz"} & set(k["nedenler"]), k["nedenler"]
    assert "low_resolution" not in k["nedenler"], k["nedenler"]


@pytest.mark.parametrize(
    "uyari",
    [
        "oblique_view: olcek degisimi x1.34",
        "plate_cropped: plaka goruntu kenarina degiyor",
        "few_candidates: 2 aday dogrulandi",
        "ecc_failed: pembe maske ile ince hizalama yapilamadi",
        "kuyu_skor_esigi: 3 hucrenin skoru 0.6 altinda",
        "kamera_oynamis: kuyu araligi %4 farkli",
        "kor_bolge_on: numune on camin dibinde",
    ],
)
def test_karsit_petride_OTEKI_kapi_nedenleri_AYNEN_KESER(uyari):
    from ai_hub.cv_ortak import pemf_kapisi

    k = pemf_kapisi.degerlendir({"success": True, "pemf_valid": True, "warnings": [uyari]}, model="petri")
    kod = uyari.split(":", 1)[0]
    assert k["surulebilir"] is False and kod in k["nedenler"], k


# ── 3. Karşıt: FANTOM tümör eşiği KALIR (Y264 yalnız petri) ─────────────────────────────────────────────────────────────────
def test_karsit_FANTOM_kapisi_low_resolution_ile_HALA_KESER():
    from ai_hub.cv_ortak import pemf_kapisi

    sonuc = {
        "success": True,
        "pemf_valid": True,
        "reliable": True,
        "warnings": ["low_resolution: tumor yaricapi ~4px - yaklas"],
    }
    k = pemf_kapisi.degerlendir(sonuc, model="fantom")
    assert k["surulebilir"] is False and "low_resolution" in k["yeniden_cekim"], k
    assert any(m["kod"] == "low_resolution" and "yeniden çekin" in m["metin"] for m in k["mesajlar"]), k["mesajlar"]


def test_karsit_FANTOM_tumor_yaricapi_6px_ALTINDA_hat_low_resolution_VERIR():
    """Gerçek fantom tespiti (saf CV, model yok): kâhin karesi küçültülünce tümör yarıçapı 6 px'in altına iner → uyarı gelir."""
    import cv2

    from ai_hub.inference_em_fantom.phantom_cv_v3.tumor_detect import TumorDetectCfg, detect_phantom_tumors

    img = _oku("fantom", _FANTOM)
    tam = detect_phantom_tumors(img, TumorDetectCfg())
    assert tam.success and "low_resolution" not in _kodlar(tam.warnings), (tam.error, tam.warnings)
    kucuk = cv2.resize(img, None, fx=_FANTOM_OLCEK, fy=_FANTOM_OLCEK, interpolation=cv2.INTER_AREA)
    r = detect_phantom_tumors(kucuk, TumorDetectCfg())
    assert r.success, (r.error, r.warnings)
    assert "low_resolution" in _kodlar(r.warnings), r.warnings
