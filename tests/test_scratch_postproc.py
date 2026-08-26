# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Yara Kapanma (Scratch) modülü — cell'siz koşan davranış kilitleri.

Plan: guii/scratch-entegrasyon-plani.md §6. Kapsam:
  * compute_closure_metrics KESİN değerler (sentetik dikey-yara maskesi)
  * draw_analysis ROI YÖN doğrulaması (yatay/dikey kırmızı çizgi pikselleri)
  * torch.load patch'inin GLOBAL OLMADIĞI (sahte-torch stub — CI'da torch yok)
  * top-level importların yalnız stdlib+numpy/cv2 olduğu (AST — bekçi kör noktası)
  * scratch_analiz sözleşmesi mock predictor'la: küçültme, n_cells==0 uyarısı,
    yatay closure_uyari, kilit yapısı, geçersiz yön ValueError
"""

from __future__ import annotations

import ast
import base64
import importlib
import sys
import types
from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

KOK = Path(__file__).resolve().parents[1]
MODUL_YOLU = KOK / "ai_hub" / "inference_paper_dilek_hoca" / "inference_paper_dilek_hoca.py"


def _modul():
    import ai_hub.inference_paper_dilek_hoca.inference_paper_dilek_hoca as m

    return m


# ── 1) Closure matematiği — KESİN değerler ───────────────────────────────────
def _dikey_yara_maskesi(w=400, h=200, yara_sol=180, yara_gen=40):
    """Tam beyaz hücre tabakası + ortada tam-yükseklik dikey siyah yara."""
    m = np.full((h, w), 255, dtype=np.uint8)
    m[:, yara_sol : yara_sol + yara_gen] = 0
    return m


def test_KRITIK_closure_metrikleri_KESIN_degerler():
    """W=400: band=max(40,120)=120 → ROI [140,260). Yara 40 kolon tam yükseklik.
    cell=80*200, total=120*200 → closure %66.67; gap kolonları 200px → mean
    (40*200)/120=66.67px*1.6=106.7µm, max 320µm; bg=8000px*0.0016² = 0.0205mm²."""
    m = _modul()
    r = m.compute_closure_metrics(_dikey_yara_maskesi(), pixel_mm=0.0016)
    assert r["roi_left"] == 140 and r["roi_right"] == 260
    assert r["closure_pct"] == 66.67
    assert r["mean_gap_um"] == 106.7
    assert r["max_gap_um"] == 320.0
    assert r["gap_area_mm2"] == 0.0205
    assert r["max_gap_col"] == 180  # ilk yara kolonu (mutlak x)
    assert r["mean_gap_col"] == 140  # 0-genişlikli ilk ROI kolonu ortalamaya en yakın


def test_KARSIT_pixel_mm_metrikleri_olcekler():
    """Objektif kalibrasyonu: 10× (0.00065) → µm değerleri 0.65/1.6 oranında."""
    m = _modul()
    r = m.compute_closure_metrics(_dikey_yara_maskesi(), pixel_mm=0.00065)
    assert r["mean_gap_um"] == round(66.6666 * 0.65, 1) == 43.3
    assert r["max_gap_um"] == 130.0
    assert r["closure_pct"] == 66.67  # oran kalibrasyondan BAĞIMSIZ


# ── 2) draw_analysis ROI yönü ────────────────────────────────────────────────
def _kirmizi(satir_veya_sutun: np.ndarray) -> int:
    """RGB dizide saf-kırmızı piksel sayısı (çizgi rengi BGR(0,0,255)→RGB kırmızı)."""
    r = satir_veya_sutun.reshape(-1, 3)
    return int(np.sum((r[:, 0] > 200) & (r[:, 1] < 80) & (r[:, 2] < 80)))


def test_KRITIK_analysis_ROI_yonu_yatay_ve_dikey():
    """vertical_box=False → YATAY kırmızı kuşak çizgileri (satır top=50);
    vertical_box=True → DİKEY çizgiler (kolon left=150). Ters mod o çizgiyi çizmez."""
    m = _modul()
    maske = _dikey_yara_maskesi()  # H=200, W=400
    yatay = m.draw_analysis(maske, vertical_box=False)
    dikey = m.draw_analysis(maske, vertical_box=True)
    # yatay mod: cy=100, half_band_h=max(50,20)=50 → top=50 satırı kırmızı şerit
    assert _kirmizi(yatay[50, :, :]) > 300, "yatay modda üst ROI çizgisi yok"
    # dikey mod: cx=200, half_band_v=max(50,40)=50 → left=150 kolonu kırmızı
    assert _kirmizi(dikey[:, 150, :]) > 150, "dikey modda sol ROI çizgisi yok"
    # KARŞIT: yatay modda kolon 150'de DİKEY çizgi OLMAMALI. Sondaj bölgesi
    # kırmızı ÇİZGİLERİN (satır ~49-51 ve ~148-150) ve kırmızı METİN gliflerinin
    # (putText satır ~10-75) dışında: satır 90-140.
    assert _kirmizi(yatay[90:140, 150, :]) == 0
    assert _kirmizi(dikey[50, 300:, :]) == 0


# ── 3) torch.load patch'i GLOBAL DEĞİL (sahte-stub — CI'da torch yok) ────────
def test_KRITIK_torch_load_patch_kapsamli_GLOBAL_degil(monkeypatch):
    m = _modul()

    def orijinal_load(*a, **k):
        return ("ORIJINAL", k.get("weights_only", "VERILMEDI"))

    sahte = types.ModuleType("torch")
    sahte.load = orijinal_load
    sahte.serialization = types.SimpleNamespace(add_safe_globals=lambda *_: None)
    monkeypatch.setitem(sys.modules, "torch", sahte)
    monkeypatch.delitem(sys.modules, "celldetection.util.schedule", raising=False)

    # Modül importu torch'a DOKUNMAMIŞ olmalı (import zaten yapıldı; top-level'da
    # torch yok — AST testi de kilitler). Kapsam öncesi:
    assert sahte.load is orijinal_load
    with m._cpn_yukleme_kapsami():
        assert sahte.load is not orijinal_load, "kapsam içinde patch yok"
        assert sahte.load("x")[1] is False, "kapsam içinde weights_only=False değil"
        assert sahte.load("x", weights_only=True)[1] is True, "açık argüman ezildi"
    assert sahte.load is orijinal_load, "kapsam sonrası torch.load GERİ GELMEDİ"

    # Hata durumunda da geri gelmeli
    with pytest.raises(RuntimeError):
        with m._cpn_yukleme_kapsami():
            raise RuntimeError("yükleme patladı")
    assert sahte.load is orijinal_load


# ── 4) Top-level importlar (bağımlılık-bekçisi ai_hub'ı TARAMAZ — kör nokta) ─
def test_YAPISAL_top_level_import_yalniz_stdlib_numpy_cv2():
    izinli = {"__future__", "base64", "contextlib", "logging", "os", "threading", "pathlib", "numpy", "cv2"}
    agac = ast.parse(MODUL_YOLU.read_text(encoding="utf-8"))
    for dugum in agac.body:  # yalnız modül gövdesi
        adlar = []
        if isinstance(dugum, ast.Import):
            adlar = [a.name.split(".")[0] for a in dugum.names]
        elif isinstance(dugum, ast.ImportFrom):
            adlar = [(dugum.module or "").split(".")[0]]
        for ad in adlar:
            assert ad in izinli, (
                f"top-level'a ağır import girmiş: {ad!r} — celldetection/torch "
                "fonksiyon-içi kalmalı (frozen EXE + CI güvenliği)"
            )


# ── 5) scratch_analiz sözleşmesi (mock predictor — cell'siz) ─────────────────
class _SahtePred:
    device = "cpu"

    def __init__(self, n_cells=1500, w=3000, h=1000):
        self.n_cells = n_cells
        self.w, self.h = w, h

    def predict(self, image_path, *, compute_closure=True, pixel_mm=0.0016):
        binary = np.full((self.h, self.w), 255, dtype=np.uint8)
        binary[:, self.w // 2 - 50 : self.w // 2 + 50] = 0
        r = {
            "image_path": str(image_path),
            "image_shape": [self.h, self.w],
            "n_cells": self.n_cells,
            "cell_area_mean": 100.0,
            "cell_area_median": 90.0,
            "coverage_ratio": 0.5,
            "score_mean": 0.6,
            "score_min": 0.3,
            "boxes": [],
            "labels_max": self.n_cells,
            "_labels": None,
            "_binary": binary,
        }
        if compute_closure:
            import ai_hub.inference_paper_dilek_hoca.inference_paper_dilek_hoca as m

            cm = m.compute_closure_metrics(binary, pixel_mm=pixel_mm)
            cm["pixel_mm"] = pixel_mm
            r["closure"] = cm
        return r

    def seg_gorselleri(self, image_path, result):
        seg = np.zeros((self.h, self.w, 3), dtype=np.uint8)
        return seg, seg.copy()


@pytest.fixture()
def girdi_png(tmp_path):
    yol = tmp_path / "ornek girdi.png"  # boşluklu ad — gerçek TIF adları gibi
    img = np.random.default_rng(42).integers(0, 255, (60, 80, 3), dtype=np.uint8)
    assert cv2.imwrite(str(yol), img)
    return str(yol)


def _b64_gorsel(b64: str) -> np.ndarray:
    arr = np.frombuffer(base64.b64decode(b64), np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    assert img is not None
    return img


def test_KRITIK_scratch_analiz_coklu_gorsel_ve_KUCULTME(monkeypatch, girdi_png):
    """Tek girdi → 5 base64 görsel + metrikler; 3000px kaynak 1280px'e KÜÇÜLÜR
    (ölçülen 15-20MB yanıt riskine karşı bekçi)."""
    m = _modul()
    monkeypatch.setitem(m._PREDICTOR_CACHE, "cpn", _SahtePred())
    y = m.scratch_analiz(girdi_png, scratch_yonu="dikey", pixel_mm=0.0016)
    for alan in (
        "input_image_base64",
        "seg_image_base64",
        "overlay_image_base64",
        "analysis_image_base64",
        "closure_image_base64",
    ):
        assert y.get(alan), f"eksik görsel alanı: {alan}"
    assert y["n_cells"] == 1500 and y["closure"]["closure_pct"] > 0
    assert "closure_uyari" not in y and "uyari" not in y
    # KÜÇÜLTME: 3000px kaynak → ≤1280. LİTERAL pinli (modül sabitine karşı assert
    # mutasyonla birlikte kayar — ölçüldü: sabit 99999 yapılınca test yeşil kalmıştı)
    assert _b64_gorsel(y["analysis_image_base64"]).shape[1] <= 1280
    assert _b64_gorsel(y["closure_image_base64"]).shape[1] <= 1280
    # input orijinal küçük (80px) → küçültülmemiş
    assert _b64_gorsel(y["input_image_base64"]).shape[1] == 80
    # toplam yanıt boyutu bekçisi (plan §6): ~<1.5 MB
    toplam = sum(len(v) for k, v in y.items() if k.endswith("_base64"))
    assert toplam < 1_500_000, f"6-görselli yanıt çok büyük: {toplam} B"


def test_KRITIK_yatay_yara_closure_uyarisi_DONER(monkeypatch, girdi_png):
    m = _modul()
    monkeypatch.setitem(m._PREDICTOR_CACHE, "cpn", _SahtePred())
    y = m.scratch_analiz(girdi_png, scratch_yonu="yatay")
    assert "dikey yara varsayimiyla" in y["closure_uyari"]
    assert y["scratch_yonu"] == "yatay"


def test_KRITIK_hucre_yoksa_yapilandirilmis_uyari(monkeypatch, girdi_png):
    """Karar 0.3: modalite kapısı YOK — boş görüntü bu uyarıyla yakalanır;
    dejenere çizimler ÜRETİLMEZ ama orijinal önizleme DÖNER."""
    m = _modul()
    monkeypatch.setitem(m._PREDICTOR_CACHE, "cpn", _SahtePred(n_cells=0))
    y = m.scratch_analiz(girdi_png)
    assert y["n_cells"] == 0 and y["closure"] is None
    assert "kontrol edin" in y["uyari"]
    assert y.get("input_image_base64")
    for alan in ("seg_image_base64", "analysis_image_base64", "closure_image_base64"):
        assert alan not in y, f"n_cells==0'da dejenere görsel üretildi: {alan}"


def test_KRITIK_xai_hatasi_analizi_DUSURMEZ(monkeypatch, girdi_png):
    """Zarif düşüş TEK-KAYNAK scratch_analiz'te: XAI patlasa da metrikler +
    görseller döner, yanıtta xai_error olur (router ve :8100 aynı davranışı alır)."""
    m = _modul()
    monkeypatch.setitem(m._PREDICTOR_CACHE, "cpn", _SahtePred())

    def patla(*a, **k):
        raise RuntimeError("eigencam patladı (test)")

    monkeypatch.setattr(m, "_xai_cpn_bellekte", patla)
    y = m.scratch_analiz(girdi_png, explain=True)
    assert y["xai_error"] == "Açıklama üretilemedi"
    assert y["closure"]["closure_pct"] > 0 and y.get("closure_image_base64")
    assert "xai_image_base64" not in y


def test_KRITIK_hucre_yok_uyarisi_XAI_den_ONCE(monkeypatch, girdi_png):
    """XAI kuralı (ses sessizlik-kapısı muadili): kapı/uyarı XAI'den ÖNCE gelir.
    n_cells==0 iken explain=true bile olsa XAI ÇALIŞTIRILMAZ."""
    m = _modul()
    monkeypatch.setitem(m._PREDICTOR_CACHE, "cpn", _SahtePred(n_cells=0))

    def patlat(*a, **k):
        raise AssertionError("n_cells==0 iken XAI çağrıldı — kapı sırası bozuk")

    monkeypatch.setattr(m, "_xai_cpn_bellekte", patlat)
    y = m.scratch_analiz(girdi_png, explain=True)
    assert "uyari" in y and "xai_image_base64" not in y


def test_KARSIT_gecersiz_yon_ValueError(girdi_png):
    m = _modul()
    with pytest.raises(ValueError, match="dikey"):
        m.scratch_analiz(girdi_png, scratch_yonu="capraz")


# ── 6) Yapısal: kilit + pt_coz ───────────────────────────────────────────────
def test_YAPISAL_analiz_kilit_TIMEOUT_lu_ve_pt_coz_kullanilir():
    """Düşman-doğrulama YÜKSEK bulgusu: kilit süresiz beklerse to_thread thread'leri
    default executor'u doldurur (E-stop bile gecikir) → timeout'lu acquire + 429
    (ScratchMesgul) + finally'de release ZORUNLU."""
    src = MODUL_YOLU.read_text(encoding="utf-8")
    i = src.index("def scratch_analiz")
    govde = src[i : src.index("GECERLI_XAI_YONTEMLERI")]  # fonksiyon-sonu çıpası (sabit uzunluk kayar)
    assert "_KILIT.acquire(timeout=" in govde, "kilit süresiz bekliyor (executor tükenmesi)"
    assert "raise ScratchMesgul" in govde, "meşgul durumu 429 sınıfına eşlenmiyor"
    assert govde.index("_KILIT.acquire") < govde.index("predict("), "predict kilit DIŞINDA"
    assert "_KILIT.release()" in govde, "finally release yok — kilit sızar"
    assert 'pt_coz(_PT_REL)' in src and '_PT_REL = "ai_hub/inference_paper_dilek_hoca/' in src


def test_KRITIK_mesgulken_ScratchMesgul(monkeypatch, girdi_png):
    """Kilit doluyken istek dakikalarca BEKLEMEZ — kısa timeout sonrası ScratchMesgul."""
    m = _modul()
    monkeypatch.setattr(m, "_KILIT_BEKLEME_SN", 0.05)
    monkeypatch.setitem(m._PREDICTOR_CACHE, "cpn", _SahtePred())
    assert m._KILIT.acquire(timeout=1), "test kilidi alamadı"
    try:
        with pytest.raises(m.ScratchMesgul):
            m.scratch_analiz(girdi_png)
    finally:
        m._KILIT.release()
    # kilit boşalınca normal akış çalışır (release sızıntısı yok)
    assert m.scratch_analiz(girdi_png)["n_cells"] == 1500


def test_YAPISAL_xai_requires_grad_RESTORE_edilir():
    """Hakem-onaylı bulgu: cache'li predictor'da bayraklar geri alınmazsa ilk
    explain'den sonraki HER analiz grad-etkin koşar (VRAM şişmesi)."""
    src = MODUL_YOLU.read_text(encoding="utf-8")
    i = src.index("def _xai_cpn_bellekte")
    govde = src[i : src.index("def scratch_analiz")]
    assert "_eski_bayraklar" in govde and "finally:" in govde
    assert "p.requires_grad_(eski)" in govde, "bayrak restorasyonu yok"
    assert "p.grad = None" in govde, "backward artığı .grad temizlenmiyor"
