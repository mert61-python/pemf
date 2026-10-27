# -*- coding: utf-8 -*-
"""AII-1.1 (AI incelemesi, A1) — KIRPIK gerçek plaka fotoğrafında uydurulan 24 kuyucuk PEMF tüketim kapısından "sürülebilir" geçiyordu.

ÖLÇÜLDÜ (`_inceleme/sonda/k1d_petri_kirpik_plaka_kapi.py`, gerçek ONNX): hocanın kâhin plakası 17(2) / 15(3) sağ yarısı kadrajda
→ petri v2 PLAKA kipi + makullik AÇIK: `success=True`, 24 kuyucuk, doğrulanmış aday 2–4, ECC ✔ (kapı geçer); görünen 12 gerçek
kuyucuğun 0'ı doğru kimlik+konumda, sapma ≈ 3,1 aralık (~60 mm). Uyarılar yalnız `few_candidates` + `plate_cropped` — ikisi de
`pemf_kapisi`nin listelerinde YOK → PEMF çerçevesi kurulunca (laboratuvar maddesi #1 `a1_cabin_mm` ya da kabin ArUco'su — AI Pro'da
ZORUNLU) `surulebilir=True`. Hocanın kendi README'si (`petri_cv_v2/README.md` "Çekim kalitesi uyarıları") bu uyarıları çekim
protokolü ihlali sayıyor: `plate_cropped` → "kadrajı genişlet", `few_candidates` → "sonucu gözle kontrol et" (kapalı döngüde göz
yok), `ecc_failed` → "ışık / odak kontrol". `ENTEGRASYON.md` §3 listesi bunları atlamıştı; guii kapısı §3'ü harfiyen aldı.
Aynı kök: denetim KAPALI + ArUco → fantom fotoğrafına uydurulan ızgara (`ecc_failed` + `few_candidates`) da "sürülebilir".

Sahte EN ALT katta: YOLO yalnız ipucu → kapatılır (bu plakalarda ONNX@640 = YOLO'suz, ölçüldü `k1b`); doz modeli çağrı sınırında
sözleşmeye uyan sahte (alanlar dolu). Gerçek ONNX kolu `golden.eser` düzeninde (ağırlık yoksa atla, PEMF_GOLDEN_REQUIRED=1'de düş).
"""

from __future__ import annotations

import csv
from pathlib import Path

import capraz
import numpy as np
import pytest

KAHIN = Path(__file__).resolve().parent / "kahin" / "hoca_cv_2026_10"
_YOLO = "ai_hub/inference_petri_dish/yolo11m-seg.onnx"
_EM = "ai_hub/inference_em_petri/BaggingRegressor.onnx"


class _SahteEM:
    """PetriPredictor.predict sözleşmesi (D1–D7, P1–P7, result_E_*) — model çağrı sınırında sahte."""

    def predict(self, x, y, z, organ_id, achieved_B, duty_sum):
        d = {f"D{k}": 0.5 for k in range(1, 8)}
        d.update({f"P{k}": 100.0 for k in range(1, 8)})
        d.update(result_E_healthy=0.1, result_E_cancer=0.1, result_E_avg=0.1)
        return d


def _oku(ad):
    import cv2

    img = cv2.imdecode(np.fromfile(str(KAHIN / "petri" / ad), dtype=np.uint8), cv2.IMREAD_COLOR)
    assert img is not None, ad
    return img


def _sag_yarim(ad):
    """Plakanın sağ yarısı kadrajda: kesim, hocanın beklenen kuyucuk merkezlerinin ORTASINDAN (sütun 3 ile 4 arası)."""
    xs = [
        float(s["cx_px"])
        for s in csv.DictReader(open(KAHIN / "beklenen_petri" / "wells.csv", encoding="utf-8"))
        if s["image"] == ad
    ]
    img = _oku(ad)
    return img[:, int((min(xs) + max(xs)) / 2) :].copy()


def _hough_boru_hatti(tmp_path, **kw):
    from ai_hub.inference_petri_dish.petri_cv_v2 import PetriCvPipeline, load_cabin_config

    sahte_yol = tmp_path / "yolo_ipucu_yok.onnx"
    sahte_yol.write_bytes(b"")  # dedektör yalnız varlık denetler (tembel yükleme); aşağıda kapatılır
    pl = PetriCvPipeline(load_cabin_config(None), yolo_model_path=sahte_yol, yolo_device="cpu", **kw)
    pl.yolo = None  # plate_grid._yolo_candidates(yolo=None) -> [] : Hough + ECC
    pl._predictor = _SahteEM()
    return pl


_KIRPIK = ["WhatsApp Image 2026-10-02 at 19.40.17(2).jpeg", "WhatsApp Image 2026-10-02 at 19.40.15(3).jpeg"]
_TAM_TEMIZ = "WhatsApp Image 2026-10-02 at 19.40.15(2).jpeg"  # kâhinde tek uyarısız plaka (karşıt)


# ── 1. Saf kural: hocanın README'sindeki çekim protokolü uyarıları kapalı döngüde sürüşü KESER ─────────────────────────────
@pytest.mark.parametrize(
    "uyari",
    [
        "plate_cropped: plaka goruntu kenarina degiyor",
        "few_candidates: 2 aday dogrulandi - konum agirlikla geometri+ECC'den",
        "ecc_failed: pembe maske ile ince hizalama yapilamadi",
    ],
)
def test_KRITIK_cekim_protokolu_uyarisi_SURULEMEZ_ve_EYLEM_soyler(uyari):
    from ai_hub.cv_ortak import pemf_kapisi

    sonuc = {"success": True, "pemf_valid": True, "warnings": [uyari], "plate": {"plate_type": 24}}
    k = pemf_kapisi.degerlendir(sonuc, model="petri")
    kod = uyari.split(":", 1)[0]
    assert k["surulebilir"] is False, f"{kod} varken sonuç sürülebilir sayıldı: {k}"
    assert kod in k["nedenler"] and kod in k["yeniden_cekim"], k
    metin = next(m["metin"] for m in k["mesajlar"] if m["kod"] == kod)
    assert "yeniden çekin" in metin, metin  # hata mesajı EYLEM söylesin


def test_karsit_uyarisiz_gecerli_plaka_SURULEBILIR_kalir():
    from ai_hub.cv_ortak import pemf_kapisi

    k = pemf_kapisi.degerlendir({"success": True, "pemf_valid": True, "warnings": [], "plate": {}}, model="petri")
    assert k["surulebilir"] is True and k["nedenler"] == [], k


# ── 2. Davranış: gerçek kâhin plakasının kırpık hâli (Hough + ECC, sahte doz modeli) ─────────────────────────────────────────
@pytest.mark.parametrize("ad", _KIRPIK)
def test_KRITIK_kirpik_plaka_UYDURULAN_izgara_SURULEMEZ(tmp_path, ad):
    from ai_hub.cv_ortak import pemf_kapisi

    # T3 · Y191b hücre skoru eşiği KAPALI (0): hocanın ızgarasının karakterizasyonu — kapı eşikten BAĞIMSIZ da sürmemeli
    pl = _hough_boru_hatti(
        tmp_path, a1_cabin_mm=[0.0, 0.0, 0.0], kuyu_skor_esigi=0.0
    )  # laboratuvar maddesi #1'in hedef yapılandırması
    r, _ = pl.process_image(_sag_yarim(ad))
    # Karakterizasyon (hocanın ızgarası): yarım plakaya 24 kuyucuk + kabin konumu + doz üretiliyor
    assert r.success and r.n_wells == 24 and r.pemf_valid is True, (r.error, r.n_wells, r.pemf_valid)
    kodlar = {str(u).split(":", 1)[0] for u in r.warnings}
    assert "plate_cropped" in kodlar, r.warnings
    k = pemf_kapisi.degerlendir(r, model="petri")
    assert k["surulebilir"] is False, (
        f"{ad}: kırpık plakadaki uydurulmuş ızgara sürülebilir sayıldı — {k['nedenler']} / {r.warnings}"
    )
    # Varsayılan eşik (0,6): kadraj dışına düşen uydurma hücreler kuyu SAYILMAZ ve yeniden çekim nedeni eklenir
    r2, _ = _hough_boru_hatti(tmp_path, a1_cabin_mm=[0.0, 0.0, 0.0]).process_image(_sag_yarim(ad))
    k2 = pemf_kapisi.degerlendir(r2, model="petri")
    assert r2.n_wells < 24 and "kuyu_skor_esigi" in k2["nedenler"] and k2["surulebilir"] is False, (
        r2.n_wells,
        k2["nedenler"],
    )


def test_karsit_tam_kadraj_kahin_plakasi_SURULEBILIR(tmp_path):
    from ai_hub.cv_ortak import pemf_kapisi

    pl = _hough_boru_hatti(tmp_path, a1_cabin_mm=[0.0, 0.0, 0.0])
    r, _ = pl.process_image(_oku(_TAM_TEMIZ))
    assert r.success and r.n_wells == 24 and r.pemf_valid is True
    k = pemf_kapisi.degerlendir(r, model="petri")
    assert k["surulebilir"] is True, (k["nedenler"], r.warnings)


# ── 3. Gerçek ONNX kolu (ürün çözücüsü) — golden.eser düzeni ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("ad", _KIRPIK)
def test_KRITIK_kirpik_plaka_GERCEK_ONNX_SURULEMEZ(ad):
    capraz.paket_yoksa_atla("ultralytics")
    from golden.eser import atla, eser_var_mi

    if not eser_var_mi(_YOLO, _EM):
        atla(f"petri ağırlıkları ürün çözücüsünde yok ({_YOLO}, {_EM})")
    from utils.model_downloader import download_model_sync

    from ai_hub.cv_ortak import pemf_kapisi
    from ai_hub.inference_petri_dish.petri_cv_v2 import PetriCvPipeline, load_cabin_config

    yolo = download_model_sync(_YOLO)
    pl = PetriCvPipeline(
        load_cabin_config(None),
        yolo_model_path=yolo,
        yolo_device="cpu",
        a1_cabin_mm=[0.0, 0.0, 0.0],
        kuyu_skor_esigi=0.0,  # T3 · Y191b eşiği KAPALI: hocanın 24'lük ızgarasının karakterizasyonu
    )
    r, _ = pl.process_image(_sag_yarim(ad))
    assert r.success and r.n_wells == 24 and r.pemf_valid is True, (r.error, r.n_wells)
    assert all(w.E_cancer is not None for w in r.wells), "doz hesaplanmadı — karakterizasyon değişti"
    k = pemf_kapisi.degerlendir(r, model="petri")
    assert k["surulebilir"] is False, f"{ad}: {k['nedenler']} / {r.warnings}"
    pl2 = PetriCvPipeline(load_cabin_config(None), yolo_model_path=yolo, yolo_device="cpu", a1_cabin_mm=[0.0, 0.0, 0.0])
    r2, _ = pl2.process_image(_sag_yarim(ad))
    k2 = pemf_kapisi.degerlendir(r2, model="petri")
    assert r2.n_wells < 24 and "kuyu_skor_esigi" in k2["nedenler"] and k2["surulebilir"] is False, (
        r2.n_wells,
        k2["nedenler"],
    )
