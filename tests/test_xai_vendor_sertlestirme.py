# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""XAI VENDORING SERTLEŞTİRMESİ — Faz 1.1 (xai-entegrasyon-plani.md, 2026-08-26).

ÖLÇÜLEN DURUM: `inference (1)` teslimatındaki xai_utils/xai_tabular paketleri "CLI-script"
kalitesinde: (a) overlay.heatmap_to_rgb matplotlib'in 3.11'de KALDIRILACAK `cm.get_cmap`'ini
kullanıyor (3.10.9'da deprecation ölçüldü); (b) report_html hasta adı/etiket/serbest metni
HİÇ escape etmeden HTML'e basıyor (PII/XSS) ve embed boyut tavanı yok; (c) EM sensitivity/SHAP
tek-örnekte (N=1) DEJENERE — std ve background verilen X'ten türetildiği için canlı seans
açıklaması sessizce "her şey 0" olur; (d) kernel-SHAP koalisyon örneklemesi seed'siz →
aynı girdiye farklı açıklama (klinik tekrarlanabilirlik yok).

DÜZELTME (ai_hub/xai_utils + ai_hub/xai_tabular vendored kopyasında):
  - colormaps[] API'si; report_html html.escape + max_embed_bytes tavanı;
  - sensitivity_analysis(ref_std=), shap_kernel_em(background=), run_em_xai(ref_stats=)
    + N=1 ve referans YOKSA açık ValueError (sessiz-sıfır yerine);
  - kernel-SHAP çağrıları np.random state save/seed(0)/restore ile deterministik.
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path

import numpy as np
import pytest

KOK = Path(__file__).resolve().parents[1]


# ── yardımcılar ───────────────────────────────────────────────────────────────
def _lineer_predict(X: np.ndarray) -> np.ndarray:
    """Basit deterministik (N,6)->(N,3) 'model': her çıktı girdilerin farklı ağırlıklı toplamı."""
    W = np.arange(18, dtype=np.float64).reshape(6, 3) / 10.0
    return np.asarray(X, dtype=np.float64) @ W


def _kucuk_png(tmp_path: Path, ad: str) -> Path:
    import cv2

    p = tmp_path / ad
    img = np.zeros((8, 8, 3), dtype=np.uint8)
    img[:4, :4] = 255
    cv2.imwrite(str(p), img)
    return p


# ── (a) matplotlib gelecek-koruması ───────────────────────────────────────────
def test_KRITIK_heatmap_to_rgb_deprecation_URETMEZ():
    """3.11'de kaldırılacak cm.get_cmap kullanılmamalı — deprecation'ı hataya çevirip çağır."""
    import matplotlib

    from ai_hub.xai_utils.overlay import heatmap_to_rgb

    hm = np.linspace(0, 1, 64, dtype=np.float32).reshape(8, 8)
    with warnings.catch_warnings():
        warnings.simplefilter("error", matplotlib.MatplotlibDeprecationWarning)
        rgb = heatmap_to_rgb(hm)
    assert rgb.shape == (8, 8, 3) and rgb.dtype == np.uint8
    assert rgb.max() > rgb.min(), "colormap düz çıktı — dönüşüm bozuk"


# ── (b) report_html: PII/XSS escape + boyut tavanı ────────────────────────────
def test_KRITIK_report_html_kullanici_metnini_ESCAPE_eder(tmp_path):
    from ai_hub.xai_utils.report_html import build_report

    kotu = "<script>alert('pii')</script>"
    img = _kucuk_png(tmp_path, "in.png")
    cam = _kucuk_png(tmp_path, "cam.png")
    out = build_report(
        tmp_path / "r.html",
        title=f"Hasta {kotu}",
        input_image=img,
        prediction={"top_1_class": kotu, "top_1_prob": 0.9, "top_k": [{"class": kotu, "prob": 0.9}]},
        cam_images={f"CAM {kotu}": cam},
        extra_info={"not": kotu},
    )
    html = Path(out).read_text(encoding="utf-8")
    assert "<script>" not in html, "kullanıcı metni escape edilmeden HTML'e basıldı (PII/XSS)"
    assert "&lt;script&gt;" in html, "escape edilmiş içerik raporda görünmüyor"


def test_KARSIT_KANIT_report_html_boyut_tavani(tmp_path):
    """Dev gömme şişmesine açık uç bırakma: tavan aşılırsa AÇIK hata (sessiz dev blob değil)."""
    from ai_hub.xai_utils.report_html import build_report

    img = _kucuk_png(tmp_path, "in.png")
    with pytest.raises(ValueError):
        build_report(
            tmp_path / "r.html",
            title="t",
            input_image=img,
            prediction={"top_1_class": "a", "top_1_prob": 1.0},
            cam_images={"c": img},
            max_embed_bytes=10,  # kasıtlı küçük tavan
        )


# ── (c) EM tek-örnek dejenerasyonu ────────────────────────────────────────────
def test_KRITIK_em_tek_ornek_referanssiz_ACIK_HATA():
    """N=1 + ref_std yok → sessiz ~0 raporu YERİNE açık ValueError (canlı seans güvencesi)."""
    from ai_hub.xai_tabular.em_sensitivity import sensitivity_analysis

    X = np.array([[78.0, 210.0, -57.85, 0.0, 0.001, 2.0]])
    with pytest.raises(ValueError):
        sensitivity_analysis(_lineer_predict, X)


def test_KARSIT_KANIT_em_ref_std_ile_tek_ornek_ANLAMLI():
    from ai_hub.xai_tabular.em_sensitivity import sensitivity_analysis

    X = np.array([[78.0, 210.0, -57.85, 0.0, 0.001, 2.0]])
    ref_std = np.array([10.0, 20.0, 15.0, 1.0, 0.0005, 0.5])
    sens = sensitivity_analysis(_lineer_predict, X, ref_std=ref_std)
    assert sens["delta_abs_mean"].shape == (6,)
    # Zayıf `> 0` eşiği mutasyonu KAÇIRDI (dejenere 1e-9 std bile lineer modelde >0 üretir):
    # ref_std=10 · delta=%10 · W~0-1.7 → beklenen mertebe ≥ 1e-2. Dejenere yol ~1e-10 üretir.
    assert sens["delta_abs_mean"].max() > 1e-2, (
        f"ref_std verildiği hâlde sensitivity dejenere mertebede: {sens['delta_abs_mean']!r}"
    )


def test_KARSIT_KANIT_em_batch_referanssiz_ESKISI_GIBI(tmp_path):
    """Batch (N>1) yol referanssız ÇALIŞMAYA DEVAM etmeli (Mod 2 regresyonu yok)."""
    from ai_hub.xai_tabular.em_sensitivity import sensitivity_analysis

    rng = np.random.default_rng(7)
    X = rng.normal(size=(4, 6)) * [50, 50, 30, 2, 0.001, 1.0] + [0, 100, -50, 3, 0.001, 2.0]
    sens = sensitivity_analysis(_lineer_predict, X)
    assert (sens["delta_abs_mean"] > 0).all()


def test_KRITIK_run_em_xai_ref_stats_uctan_uca(tmp_path):
    """Canlı-seans deseni: N=1 + ref_stats (std+background) → dosyalar üretilir, SHAP ~0 DEĞİL."""
    from ai_hub.xai_tabular.em_sensitivity import run_em_xai

    X = np.array([[78.0, 210.0, -57.85, 0.0, 0.001, 2.0]])
    rng = np.random.default_rng(3)
    bg = rng.normal(size=(8, 6)) * [50, 50, 30, 2, 0.001, 1.0] + [0, 100, -50, 3, 0.001, 2.0]
    ref = {"std": np.array([10.0, 20.0, 15.0, 1.0, 0.0005, 0.5]), "background": bg}

    res = run_em_xai(_lineer_predict, X, tmp_path, ref_stats=ref, shap_nsamples=40)
    assert (tmp_path / "sensitivity.csv").exists() and (tmp_path / "shap_values.csv").exists()
    assert res["sensitivity"]["delta_abs_mean"].max() > 1e-2, "ref_stats.std yok sayılmış (dejenere mertebe)"
    assert np.abs(res["shap_values"]).sum() > 1e-6, (
        "ref background verildiği hâlde SHAP ~0 — tek-örnek dejenerasyonu run_em_xai'de sürüyor"
    )


# ── (d) kernel-SHAP determinizmi ─────────────────────────────────────────────
def test_KRITIK_em_kernel_shap_DETERMINISTIK():
    from ai_hub.xai_tabular.em_sensitivity import shap_kernel_em

    rng = np.random.default_rng(11)
    X = rng.normal(size=(4, 6)) * [50, 50, 30, 2, 0.001, 1.0] + [0, 100, -50, 3, 0.001, 2.0]
    a = shap_kernel_em(_lineer_predict, X, n_kernel_samples=40)
    b = shap_kernel_em(_lineer_predict, X, n_kernel_samples=40)
    assert np.array_equal(a, b), "aynı girdiye iki çağrıda FARKLI SHAP — klinik tekrarlanabilirlik yok"


def test_KARSIT_KANIT_kernel_shap_global_rng_durumunu_BOZMAZ():
    """Seed'leme çağıran sürecin RNG durumunu değiştirmemeli (save/restore)."""
    from ai_hub.xai_tabular.em_sensitivity import shap_kernel_em

    rng = np.random.default_rng(11)
    X = rng.normal(size=(3, 6)) + [0, 100, -50, 3, 0.001, 2.0]
    np.random.seed(1234)
    beklenen = np.random.RandomState(1234).rand(3)  # aynı tohumun ilk 3 örneği
    shap_kernel_em(_lineer_predict, X, n_kernel_samples=30)
    sonra = np.random.rand(3)
    assert np.allclose(sonra, beklenen), "kernel-SHAP global np.random durumunu kalıcı değiştirdi"


# ── (e') torch'suz ortam dayanikliligi ───────────────────────────────────────
def test_KRITIK_xai_utils_TORCHSUZ_ortamda_import_edilir():
    """CI dersi (koşu 32948xxx): grad_cam.py torch'u modül-seviyesinde ister; koşulsuz paket
    import'u torch'suz ortamda (CI test seti, ağır-AI'sız kurulum) overlay/report_html'i DE
    kilitliyordu. Torch'u BLOKLAYAN alt-süreçte paket import edilmeli, overlay çalışmalı."""
    import subprocess
    import sys

    kod = (
        "import sys\n"
        "class _Blok:\n"
        "    def find_module(self, name, path=None):\n"
        "        if name == 'torch' or name.startswith('torch.'):\n"
        "            return self\n"
        "    def load_module(self, name):\n"
        "        raise ImportError('torch BLOKLANDI (test)')\n"
        "sys.meta_path.insert(0, _Blok())\n"
        f"sys.path.insert(0, {str(KOK)!r})\n"
        "import ai_hub.xai_utils as xu\n"
        "assert xu.TORCH_XAI_AVAILABLE is False, 'bayrak torch-yok durumunu soylemiyor'\n"
        "assert xu.GradCAMExplainer is None\n"
        "import numpy as np\n"
        "rgb = xu.heatmap_to_rgb(np.linspace(0, 1, 16).reshape(4, 4))\n"
        "assert rgb.shape == (4, 4, 3)\n"
        "print('TORCHSUZ-OK')\n"
    )
    r = subprocess.run([sys.executable, "-c", kod], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and "TORCHSUZ-OK" in r.stdout, f"torch'suz ortamda xai_utils kırık:\n{r.stderr[-800:]}"


# ── (e) paket hijyeni ────────────────────────────────────────────────────────
def test_YAPISAL_vendored_paketlerde_sys_path_insert_YOK():
    """ai_hub kopyaları paket-göreli çalışır; sys.path.insert kalıntısı (docstring dahil) kalmamalı."""
    for pkg in ("xai_tabular", "xai_utils"):
        for py in (KOK / "ai_hub" / pkg).glob("*.py"):
            src = py.read_text(encoding="utf-8", errors="replace")
            assert "sys.path.insert" not in src, f"{py.name} hâlâ sys.path.insert içeriyor"


def test_YAPISAL_kernel_predict_proba_dususu_LOGLANIR():
    """shap_wrapper kernel yolundaki sessiz predict_proba→predict düşüşü artık loglu olmalı."""
    src = (KOK / "ai_hub" / "xai_tabular" / "shap_wrapper.py").read_text(encoding="utf-8")
    i = src.index("def _predict(")
    govde = src[i : i + 700]
    assert "logging" in src and ("warning" in govde or "debug" in govde), (
        "kernel _predict fallback'i hâlâ sessiz (bare except, log yok)"
    )


def test_ig_internal_batch_size_parametresi():
    """Captum IG bellek zarfı: internal_batch_size passthrough (captum yoksa atla)."""
    pytest.importorskip("captum")
    import inspect

    from ai_hub.xai_tabular.ig_torch import integrated_gradients

    assert "internal_batch_size" in inspect.signature(integrated_gradients).parameters
