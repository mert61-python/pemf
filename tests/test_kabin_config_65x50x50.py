# Author: mertaygn, cglrgrkn
"""Kabin geometrisi 65×50×50 + basılı ArUco marker + cat_organ yaml'ı GERÇEKTEN okur (2026-09-08).

Sahip ölçüsü: genişlik 65 · derinlik 50 · yükseklik 50 cm. Üç pipeline'ın örnek yaml'ı aynı kabini
tanımlar (kamera sağ-alt-ön köşe, marker arka duvar sol-üst). Bu dosya ÖLÇER:
  (a) üç yaml parse edilir, aynı geometriyi taşır, mesafeler vektörlerden hesaplananla ±0.2 cm uyuşur,
      marker sözlüğü/kenarı basılı sayfa üreticisinin sabitleriyle aynıdır;
  (b) cat_organ `CatOrganPredictor` paketli yaml'ı yükler → kamera-sabitli + perspektif verisi VAR
      (2026-09-08'e kadar `load_cabin_config(None)` DEFAULT döndürüyordu: yaml güncellemeleri etkisizdi);
  (c) basılı marker sayfası üretildiğinde cv2.aruco onu ID 0 ve 10,0 cm (300 DPI) olarak bulur;
  (d) kılavuz aynı sayıları söyler.
Mutasyonla KIRMIZI: predictor `load_cabin_config(None)`'a döndürülünce (b) düşer; yaml'da to_marker
değiştirilince (a) düşer.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
YAMLLAR = {
    "cat_organ": KOK / "ai_hub" / "inference_cat_organ" / "cabin_config_example.yaml",
    "em_fantom": KOK / "ai_hub" / "inference_em_fantom" / "phantom_cv" / "cabin_config_example.yaml",
    "petri": KOK / "ai_hub" / "inference_petri_dish" / "petri_cv" / "cabin_config_example.yaml",
}
EXTENT = [65.0, 50.0, 50.0]
KAMERA = [32.5, -25.0, -25.0]
MARKER = [-24.5, 17.0, 25.0]


def _yukle(p: Path) -> dict:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(p.read_text(encoding="utf-8"))


@pytest.mark.parametrize("ad", sorted(YAMLLAR))
def test_KRITIK_yaml_geometri_65x50x50_ve_mesafeler_tutarli(ad):
    d = _yukle(YAMLLAR[ad])
    g, c, a = d["geometry"], d["camera"], d["aruco"]
    assert [float(x) for x in g["cabin_extent_cm"]] == EXTENT, f"{ad}: cabin_extent {g['cabin_extent_cm']}"
    assert [float(x) for x in c["fixed_position_cm"]] == KAMERA, f"{ad}: kamera {c['fixed_position_cm']}"
    marker = [-float(x) for x in g["qr_to_origin_cm"]]
    assert marker == MARKER, f"{ad}: marker merkezi {marker} (qr_to_origin={g['qr_to_origin_cm']})"
    # marker 10 cm + 2 cm sessiz bölge duvar/tavana sığmalı (merkez ≥ 7 cm içeride)
    assert -EXTENT[0] / 2 + 7 <= marker[0] and marker[1] <= EXTENT[1] / 2 - 7 and marker[2] == EXTENT[2] / 2
    to_o = math.dist(KAMERA, [0, 0, 0])
    to_m = math.dist(KAMERA, marker)
    assert abs(to_o - float(c["to_origin_cm"])) <= 0.2, f"{ad}: to_origin {c['to_origin_cm']} ≠ {to_o:.2f}"
    assert abs(to_m - float(c["to_marker_cm"])) <= 0.2, f"{ad}: to_marker {c['to_marker_cm']} ≠ {to_m:.2f}"
    assert a["dict"] == "DICT_5X5_50" and float(a["real_cm"]) == 10.0
    assert str(a["normal_axis_in_cabin"]).upper() == "-Z", "marker arka duvarda öne (kameraya) bakar"


def test_uc_pipeline_AYNI_kabini_tanimlar():
    ds = {ad: _yukle(p) for ad, p in YAMLLAR.items()}
    ref = ds["cat_organ"]
    for ad, d in ds.items():
        for k in ("qr_to_origin_cm", "cabin_extent_cm"):
            assert d["geometry"][k] == ref["geometry"][k], f"{ad}.geometry.{k} cat_organ'dan farklı"
        for k in ("fixed_position_cm", "to_marker_cm", "to_origin_cm", "look_at_cm", "up_cabin"):
            assert d["camera"][k] == ref["camera"][k], f"{ad}.camera.{k} cat_organ'dan farklı"


def test_KRITIK_cat_organ_predictor_paketli_yamli_YUKLER(monkeypatch):
    """2026-09-08 öncesi: DEFAULT config → has_perspective_data False → ArUco yolu hiç çalışmıyordu."""
    pytest.importorskip("cv2")
    from ai_hub.inference_cat_organ import catorgan_predictor as cp
    from ai_hub.inference_cat_organ.lib import qr as _qr
    from ai_hub.inference_cat_organ.lib.cabin_config import has_perspective_data, is_camera_anchored

    monkeypatch.setattr(cp.CatOrganPredictor, "_resolve_models", lambda self, models_dir: None)
    p = cp.CatOrganPredictor(device="cpu")
    cfg = p.cabin_cfg
    assert [float(x) for x in cfg["camera"]["fixed_position_cm"]] == KAMERA, cfg["camera"]
    assert is_camera_anchored(cfg) and has_perspective_data(cfg), "perspektif/ArUco yolu yine kapalı"
    assert cfg.get("_yaml_path", "").endswith("cabin_config_example.yaml")
    assert _qr.ARUCO_DICT == "DICT_5X5_50" and float(_qr.ARUCO_REAL_CM) == 10.0


def test_cat_organ_yaml_yoksa_DEFAULT_a_duser(monkeypatch, tmp_path):
    """Bozuk/eksik yaml analizi düşürmez (kalibrasyonsuz eski davranış)."""
    pytest.importorskip("cv2")
    from ai_hub.inference_cat_organ import catorgan_predictor as cp

    monkeypatch.setattr(cp.CatOrganPredictor, "_resolve_models", lambda self, models_dir: None)
    monkeypatch.setattr(cp, "varsayilan_kabin_yaml", lambda: str(tmp_path / "yok.yaml"))
    p = cp.CatOrganPredictor(device="cpu")
    assert p.cabin_cfg["camera"]["fixed_position_cm"] is None


def test_marker_sayfasi_uretici_sabitleri_yaml_ile_AYNI():
    src = (KOK / "scripts" / "kabin_marker_a4.py").read_text(encoding="utf-8")
    assert re.search(r'^DICT_ADI = "DICT_5X5_50"$', src, re.M) and re.search(r"^MARKER_ID = 0$", src, re.M)
    assert re.search(r"^KENAR_CM = 10\.0", src, re.M)
    # sayfadaki talimat kabin sayılarını yaml ile aynı söyler
    assert "[-24.5, +17.0, +25.0]" in src and "[32.5, -25.0, -25.0]" in src and "[24.5, -17.0, -25.0]" in src


def test_marker_sayfasi_cv2_ile_ID0_ve_10cm_bulunur():
    cv2 = pytest.importorskip("cv2")
    pytest.importorskip("PIL")
    if not hasattr(cv2, "aruco"):
        pytest.skip("cv2.aruco yok")
    import sys

    sys.path.insert(0, str(KOK / "scripts"))
    import kabin_marker_a4 as km

    ok, mesaj = km.dogrula(km.sayfa_uret())
    assert ok, mesaj


def test_kilavuz_ayni_sayilari_soyler_ve_marker_png_depoda():
    k = (KOK / "ai_hub" / "KABIN_KURULUM_KILAVUZU.md").read_text(encoding="utf-8")
    for s in ("[65, 50, 50]", "[32.5, -25, -25]", "[-24.5, +17, +25]", "[24.5, -17, -25]", "48.0", "86.7"):
        assert s in k, f"kılavuzda {s} yok"
    assert "PEMF_ArUco_Marker_5X5_50_ID0_10cm_A4.pdf" in k and "kabin_marker_a4.py" in k
    assert (KOK / "ai_hub" / "PEMF_ArUco_Marker_5X5_50_ID0_10cm_A4.png").exists()


def test_marker_pdf_A4_sayfa_boyutunda_uretilir(tmp_path):
    """*.pdf depoda izlenmez (gitignore) → sayfa üretilip A4 MediaBox (595×842 pt) ölçülür;
    yanlış DPI/sayfa boyutu basılı marker'ı 10 cm'den saptırır."""
    cv2 = pytest.importorskip("cv2")
    pytest.importorskip("PIL")
    if not hasattr(cv2, "aruco"):
        pytest.skip("cv2.aruco yok")
    import sys

    sys.path.insert(0, str(KOK / "scripts"))
    import kabin_marker_a4 as km

    assert km.main(["--cikti", str(tmp_path)]) == 0
    pdf = tmp_path / "PEMF_ArUco_Marker_5X5_50_ID0_10cm_A4.pdf"
    m = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]", pdf.read_bytes())
    assert m, "PDF MediaBox yok"
    w, h = float(m.group(1)), float(m.group(2))
    assert abs(w - 595.3) < 1.0 and abs(h - 841.9) < 1.0, f"A4 değil: {w}x{h} pt"
