# Author: mertaygn, cglrgrkn
"""TD4 (tezgâh Oturum 13 · A16, F2, K7) — kabin geometrisi: ters takılmış işaret, tavan / taban işaretinde `up_cabin`,
`intrinsics_npz` çözünürlüğü.

ÖLÇÜLEN KUSURLAR:
  * Saha kabininde ArUco kâğıdı 180° TERS yapıştırılmıştı (tezgâh 2026-10-14 buldu, elle çevrildi). Kod işaretin "üst" kenarının
    tavana baktığını VARSAYAR (`_marker_to_cabin_R`); ters işaretle kabin X ve Y AYNALANIR — her hedef yanlış yerde, uyarı YOK.
  * Tavan / taban işaretinde (normal ±Y) `up_cabin` verilmezse (varsayılan +Y, normale PARALEL) dönüşüm TEKİL çıkar (det 0) ve
    yükleme sessizce kabul ediyordu.
  * `intrinsics_npz` kalibrasyonu farklı çözünürlükteyse fantom v3 hattı K'yı ÖLÇEKLEMİYOR (petri v2 ölçekliyor —
    2026-09-09 kuralı) → solvePnP mesafeyi çözünürlük oranı kadar yanlış verir.
DÜZENEK: TD4 DUVAR DÜZENİ (Oturum 13 ölçüsü, `kabin_test_geometrisi.td4_duvar_kabini`) ile ürün YAML'ından fiziksel tutarlı poz
(tests/kabin_fiziksel_poz.py) + GERÇEK ArUco görüntüsü sentezlenir (cv2.aruco işareti + sessiz bölge, homografiyle kameranın gördüğü
yere) → GERÇEK `detect_aruco_marker` + `solve_cabin_pose` + hat. T3 (2026-10-23): ürün kabini T2B'den beri TABAN işareti; ters
işaret kararı yalnız duvar işaretinde verilir (`isaret_ters_mi` taban / tavanda False — T2B B3, yayından sonra) → mekanizma kapısı
duvar düzeninde ölçülür.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import capraz
import cv2
import numpy as np
import pytest
from kabin_fiziksel_poz import fiziksel_poz, genis_aci_ic_parametre, izdusur

KOK = Path(__file__).resolve().parents[1]
FANTOM_YAML = KOK / "ai_hub" / "inference_em_fantom" / "phantom_cv_v3" / "cabin_config_v3.yaml"
TERS_METNI = "Kabin işareti ters takılmış görünüyor — üst kenar tavana bakacak şekilde çevirin"


def _ct():
    from ai_hub.cv_ortak import coord_transform as ct

    return ct


def _cfg(p=FANTOM_YAML):
    from kabin_test_geometrisi import td4_duvar_kabini

    from ai_hub.cv_ortak.cabin_config import load_cabin_config

    return td4_duvar_kabini(load_cabin_config(p))


def _sentetik(cfg, *, ters: bool, boyut=(1280, 720)):
    """Kameranın göreceği kare: arka duvardaki ArUco (ID 0, `real_cm`) + %30 sessiz bölge; `ters` = kâğıt 180° döndürülmüş."""
    ct = _ct()
    intr = genis_aci_ic_parametre(ct)
    poz, R_kk, C = fiziksel_poz(ct, cfg)
    R_mk = ct._marker_to_cabin_R(cfg)
    M = poz.marker_pos_cabin_mm
    piksel, pay = 200, 60
    isaret = cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_50), 0, piksel)
    if ters:
        isaret = np.ascontiguousarray(np.rot90(isaret, 2))
    tam = cv2.copyMakeBorder(isaret, pay, pay, pay, pay, cv2.BORDER_CONSTANT, value=255)
    s = cfg.aruco.real_mm / 2.0 * (piksel + 2 * pay) / piksel
    x, y = R_mk[:, 0], R_mk[:, 1]
    koseler = [M - s * x + s * y, M + s * x + s * y, M + s * x - s * y, M - s * x - s * y]  # görüntü TL, TR, BR, BL
    dst = np.float32([izdusur(intr.K, R_kk, C, P) for P in koseler])
    n = tam.shape[0] - 1
    H = cv2.getPerspectiveTransform(np.float32([[0, 0], [n, 0], [n, n], [0, n]]), dst)
    kare = cv2.warpPerspective(cv2.cvtColor(tam, cv2.COLOR_GRAY2BGR), H, boyut, borderValue=(150, 150, 150))
    return kare, intr, poz


@pytest.mark.parametrize("ters", [False, True])
def test_KRITIK_ters_takilmis_isaret_rvecten_ALGILANIR(ters):
    ct = _ct()
    cfg = _cfg()
    kare, intr, gercek = _sentetik(cfg, ters=ters)
    poz = ct.solve_cabin_pose(kare, intr, cfg.aruco, cfg.geometry, cfg.pnp)
    assert poz is not None, "aparat: sentetik işaret algılanmadı"
    if not ters:
        assert np.allclose(poz.R, gercek.R, atol=0.05), "aparat: düz işaretin pozu fiziksel pozla uyuşmuyor"
    assert ct.isaret_ters_mi(poz, cfg) is ters, f"ters={ters} ama karar {ct.isaret_ters_mi(poz, cfg)}"


def test_KRITIK_fantom_hatti_ters_isarette_UYARIR_ve_PEMF_kapisi_SURMEZ():
    from ai_hub.cv_ortak import pemf_kapisi
    from ai_hub.inference_em_fantom.phantom_cv_v3.pipeline import PhantomCvPipeline

    cfg = _cfg()
    kare, _intr, _poz = _sentetik(cfg, ters=True)
    sonuc, _ctx = PhantomCvPipeline(cfg).process_image(kare, image_name="td4_ters")
    uyari = [w for w in sonuc.warnings if str(w).startswith("marker_upside_down")]
    assert uyari and TERS_METNI in uyari[0], sonuc.warnings
    karar = pemf_kapisi.degerlendir(
        {**vars(sonuc), "success": True, "pemf_valid": True, "reliable": True}, model="fantom"
    )
    assert karar["surulebilir"] is False and "marker_upside_down" in karar["engelleyici"], karar
    assert karar["eylem"] == TERS_METNI + ".", karar["eylem"]


def test_KARSIT_fantom_hatti_duz_isarette_UYARMAZ():
    from ai_hub.inference_em_fantom.phantom_cv_v3.pipeline import PhantomCvPipeline

    cfg = _cfg()
    kare, _intr, _poz = _sentetik(cfg, ters=False)
    sonuc, _ctx = PhantomCvPipeline(cfg).process_image(kare, image_name="td4_duz")
    assert sonuc.cabin_pose, "aparat: düz işaretle kabin pozu çözülmedi"
    assert not [w for w in sonuc.warnings if str(w).startswith("marker_upside_down")], sonuc.warnings


def _yaml_kopya(tmp_path, degistir):
    yaml = capraz.paket_yoksa_atla("yaml")
    d = yaml.safe_load(FANTOM_YAML.read_text(encoding="utf-8"))
    degistir(d)
    p = tmp_path / "cabin_td4.yaml"
    p.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    return p


@pytest.mark.parametrize("normal", ["+Y", "-Y"])
def test_KRITIK_tavan_taban_isaretinde_up_cabin_ZORUNLU(tmp_path, normal):
    def _d(d):
        d["aruco"]["normal_axis_in_cabin"] = normal
        d["camera"].pop("up_cabin", None)

    with pytest.raises(ValueError, match="up_cabin"):
        _cfg(_yaml_kopya(tmp_path, _d))


def test_KRITIK_up_cabin_normale_PARALEL_ise_reddedilir(tmp_path):
    def _d(d):
        d["aruco"]["normal_axis_in_cabin"] = "-Y"
        d["camera"]["up_cabin"] = [0.0, 1.0, 0.0]

    with pytest.raises(ValueError, match="up_cabin"):
        _cfg(_yaml_kopya(tmp_path, _d))


def test_KARSIT_tavan_isareti_DOGRU_up_cabin_ile_ortonormal(tmp_path):
    def _d(d):
        d["aruco"]["normal_axis_in_cabin"] = "-Y"
        d["camera"]["up_cabin"] = [0.0, 0.0, -1.0]

    cfg = _cfg(_yaml_kopya(tmp_path, _d))
    R = _ct()._marker_to_cabin_R(cfg)
    assert np.allclose(R.T @ R, np.eye(3), atol=1e-9) and abs(np.linalg.det(R) - 1.0) < 1e-9, R


def test_KRITIK_marker_to_cabin_R_TEKIL_donusumu_SESSIZCE_kabul_etmez():
    from types import SimpleNamespace

    cfg = SimpleNamespace(
        aruco=SimpleNamespace(normal_axis_in_cabin="+Y"), camera=SimpleNamespace(up_cabin=[0.0, 1.0, 0.0])
    )
    with pytest.raises(ValueError, match="up_cabin"):
        _ct()._marker_to_cabin_R(cfg)


def test_KRITIK_intrinsics_npz_FARKLI_cozunurlukte_fantom_K_OLCEKLER(tmp_path):
    """Kalibrasyon 2560×1440'ta (K 2×), kare 1280×720: hat K'yı kareye ölçeklemeli; ölçeklemezse mesafe 2× çıkar."""
    from ai_hub.inference_em_fantom.phantom_cv_v3.pipeline import PhantomCvPipeline

    ct = _ct()
    intr = genis_aci_ic_parametre(ct)
    np.savez(
        tmp_path / "kalib_td4.npz",
        K=intr.K * np.array([[2.0, 1, 2.0], [1, 2.0, 2.0], [1, 1, 1]]),
        D=np.zeros(5),
        image_size=np.array([2560, 1440], dtype=np.int32),
        rms=0.2,
    )
    shutil.copy(FANTOM_YAML, tmp_path / "cabin.yaml")
    yaml = capraz.paket_yoksa_atla("yaml")
    d = yaml.safe_load((tmp_path / "cabin.yaml").read_text(encoding="utf-8"))
    d["camera"]["intrinsics_npz"] = "kalib_td4.npz"  # YAML'a GÖRELİ yol (calibrate_camera.py çıktısı yanına konur)
    (tmp_path / "cabin.yaml").write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    cfg = _cfg(tmp_path / "cabin.yaml")
    assert cfg.has_intrinsics(), "aparat: göreli intrinsics_npz bulunamadı"
    kare, _i, gercek = _sentetik(cfg, ters=False)
    sonuc, ctx = PhantomCvPipeline(cfg).process_image(kare, image_name="td4_npz")
    assert sonuc.camera_calib["approx"] is False, "kalibrasyon dosyası kullanılmadı (yaklaşık K)"
    K = np.array(sonuc.camera_calib["K"])
    assert abs(K[0, 0] - 500.0) < 1.0 and abs(K[0, 2] - 640.0) < 1.0, f"K kare çözünürlüğüne ölçeklenmedi: {K.tolist()}"
    poz = ctx.get("cabin_pose")
    assert poz is not None, "aparat: kalibrasyonlu hatta işaret pozu yok"
    hata = float(np.linalg.norm(poz.tvec.flatten() - gercek.tvec.flatten()))
    assert hata < 10.0, f"işaret mesafesi {hata:.0f} mm yanlış (gerçek {np.linalg.norm(gercek.tvec):.0f} mm)"


from test_em_ongorucu_SONLU_OLMAYAN_girdi_PIKSEL_kipi_ve_TOPLAM_sure import petri_hatti  # noqa: E402,F401 — aparat
from test_koordinat_donusumu_FIZIKSEL_poz_DOGRULUK_ve_RED import _aruco_yamala  # noqa: E402


@pytest.mark.parametrize("ters", [False, True])
def test_KRITIK_petri_hatti_ters_isarette_UYARIR(petri_hatti, monkeypatch, ters):
    """Petri v2 hattı da (GERÇEK `process_image`, sahte YOLO + ArUco aparatı) ters işareti söyler; düz işarette söylemez."""
    from kabin_test_geometrisi import td4_duvar_kabini

    pp, kos, _Yolo = petri_hatti
    _gercek_yukle = pp.load_cabin_config
    monkeypatch.setattr(pp, "load_cabin_config", lambda *a, **k: td4_duvar_kabini(_gercek_yukle(*a, **k)))
    _aruco_yamala(pp, monkeypatch, [])
    if ters:  # kâğıt 180°: işaretin +Y'si kamerada AŞAĞI
        asil = pp.solve_cabin_pose

        def _ters_poz(*a, **k):
            p = asil(*a, **k)
            p.R = np.diag([-1.0, 1.0, -1.0])
            return p

        monkeypatch.setattr(pp, "solve_cabin_pose", _ters_poz)
    _hat, sonuc, _ctx = kos()
    uyari = [w for w in sonuc.warnings if str(w).startswith("marker_upside_down")]
    assert sonuc.method == "aruco_pnp", sonuc.method
    assert bool(uyari) is ters and (not uyari or TERS_METNI in uyari[0]), sonuc.warnings
