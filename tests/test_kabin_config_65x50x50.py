# Author: mertaygn, cglrgrkn
"""Kabin geometrisi + basılı ArUco marker + cat_organ yaml'ı GERÇEKTEN okur (2026-09-08; ölçüler TD4 2026-10-14).

⚠️ Dosya adı TARİHÇEDİR (65×50×50). Güncel kabin (TEZGÂH-2B 2026-10-23, sahip şerit metre + ArUco): iç 55,5 × 35 × 40,5 cm;
işaret TABAN camının üstünde, merkez (-8.25, -17.5, -0.75), 10 cm, siyah yüz yukarı, üst kenarı arka duvara; kamera (Pusat FHD)
tavan camının üstünde tepeden → lens (2.75, 19.5, -12.25). (Oturum 13 2026-10-14: 57 × 34 × 32, arka duvar işareti — eski.)
Eksen kuralı: +X = ÖNDEN BAKANIN SOLU (eski açıklamalar "sağ = +X" diyordu — aynaydı). Bu dosya ÖLÇER:
  (a) üç yaml parse edilir, aynı geometriyi taşır, mesafeler vektörlerden hesaplananla ±0.2 cm uyuşur,
      marker sözlüğü/kenarı basılı sayfa üreticisinin sabitleriyle aynıdır;
  (b) cat_organ `CatOrganPredictor` paketli yaml'ı yükler → kamera-sabitli + perspektif verisi VAR
      (2026-09-08'e kadar `load_cabin_config(None)` DEFAULT döndürüyordu: yaml güncellemeleri etkisizdi);
  (c) basılı marker sayfası üretildiğinde cv2.aruco onu ID 0 ve `real_cm` kenarıyla (300 DPI) bulur;
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
    # AI-2 C6: v1 `phantom_cv` / `petri_cv` emekli → hocanın v3 / v2 profil YAML'ları (aynı saha kabin çekirdeği).
    "em_fantom": KOK / "ai_hub" / "inference_em_fantom" / "phantom_cv_v3" / "cabin_config_v3.yaml",
    "petri": KOK / "ai_hub" / "inference_petri_dish" / "petri_cv_v2" / "cabin_config_v2.yaml",
}
# T2B (2026-10-23 olcusu; TEZGAH-2B.md §7). Sessiz bolge kurali kenardan TURETILIR (asagida).
EXTENT = [55.5, 35.0, 40.5]
KAMERA = [2.75, 19.5, -12.25]
MARKER = [-8.25, -17.5, -0.75]
ISARET_KENAR_CM = 10.0
SESSIZ_CM = 2.0


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
    # ⚠️ Isaret + sessiz bolge duvar/tavana SIGMALI: merkez >= kenar/2 + sessiz kadar iceride.
    # Sabit "7" idi ve 10 cm isarete gore hesaplanmisti; 15 cm'de 9,5 cm gerekir -> kenardan TURET.
    # Taban işareti: sessiz bölge X (sol / sağ cam) ve Z (ön / arka cam) yönünde sığmalı.
    ic = float(a["real_cm"]) / 2 + SESSIZ_CM
    for i, eksen in ((0, "sol / sağ cam"), (2, "ön / arka cam")):
        assert -EXTENT[i] / 2 + ic <= marker[i] <= EXTENT[i] / 2 - ic, (
            f"{ad}: marker {eksen} yönünde kenara {EXTENT[i] / 2 - abs(marker[i]):.1f} cm — sessiz bölge taşar (asgari {ic})"
        )
    assert marker[1] == -EXTENT[1] / 2, f"{ad}: marker taban camının üstünde değil (Y={marker[1]})"
    to_o = math.dist(KAMERA, [0, 0, 0])
    to_m = math.dist(KAMERA, marker)
    assert abs(to_o - float(c["to_origin_cm"])) <= 0.2, f"{ad}: to_origin {c['to_origin_cm']} ≠ {to_o:.2f}"
    assert abs(to_m - float(c["to_marker_cm"])) <= 0.2, f"{ad}: to_marker {c['to_marker_cm']} ≠ {to_m:.2f}"
    assert a["dict"] == "DICT_5X5_50" and float(a["real_cm"]) == ISARET_KENAR_CM
    assert str(a["normal_axis_in_cabin"]).upper() == "+Y", "marker tabanda yukarı (tavandaki kameraya) bakar"
    assert [float(x) for x in c["up_cabin"]] == [0.0, 0.0, 1.0], f"{ad}: işaretin üst kenarı arka duvara (+Z)"


def test_KRITIK_petri_deney_yeri_YAZILMAZ_isaretsiz_foto_kabinde_SAYILMAZ_B7():
    """T3 (2026-10-23) ölçtü: `multiwell.placement.a1_cabin_mm` dolu iken İŞARETSİZ her plaka fotoğrafı (telefon, başka kabin, hocanın
    WhatsApp kareleri) bu kabinin deney yerinde sayılıp `pemf_valid: true` ve AI Pro'da sürülebilir oluyordu (T2B B7). Konum yalnız
    kabin işaretinden (ArUco); T2B deney yeri ölçüsü YAML yorumunda kalır."""
    d = _yukle(YAMLLAR["petri"])
    assert d["multiwell"]["placement"]["a1_cabin_mm"] is None, d["multiwell"]["placement"]


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
    assert _qr.ARUCO_DICT == "DICT_5X5_50" and float(_qr.ARUCO_REAL_CM) == ISARET_KENAR_CM


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
    assert re.search(rf"^KENAR_CM = {ISARET_KENAR_CM:g}\.0", src, re.M)
    # sayfadaki talimat kabin sayılarını yaml ile aynı söyler
    assert "[-8.25, -17.5, -0.75]" in src and "[2.75, 19.5, -12.25]" in src and "[8.25, 17.5, 0.75]" in src


def test_marker_sayfasi_cv2_ile_ID0_ve_KENAR_bulunur():
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
    for s in (
        "[55.5, 35, 40.5]",
        "[2.75, 19.5, -12.25]",
        "[-8.25, -17.5, -0.75]",
        "[8.25, 17.5, 0.75]",
        "23.2",
        "40.3",
    ):
        assert s in k, f"kılavuzda {s} yok"
    sayfa = f"PEMF_ArUco_Marker_5X5_50_ID0_{ISARET_KENAR_CM:g}cm_A4"
    assert f"{sayfa}.pdf" in k and "kabin_marker_a4.py" in k
    assert (KOK / "ai_hub" / f"{sayfa}.png").exists()


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
    pdf = tmp_path / f"PEMF_ArUco_Marker_5X5_50_ID0_{ISARET_KENAR_CM:g}cm_A4.pdf"
    m = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]", pdf.read_bytes())
    assert m, "PDF MediaBox yok"
    w, h = float(m.group(1)), float(m.group(2))
    assert abs(w - 595.3) < 1.0 and abs(h - 841.9) < 1.0, f"A4 değil: {w}x{h} pt"
