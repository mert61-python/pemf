# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.100 · B-5.16 (+ İG-5.72) — ArUco piksel→kabin dönüşümü DOĞRU ve geçersiz kesişimi REDDEDER.

ÖLÇÜLEN KUSUR (05 · B-5.16; D0 İG-5.72): `cv_ortak.coord_transform.pixel_to_cabin_mm`
  * kamera orijinini marker→kabin DÖNDÜRMEDEN kabine taşıyor (`cam_origin_cabin` döndürmesiz; döndürme bir satır sonra
    ÖLÜ bir değişkene yazılıyor) → fiziksel tutarlı pozda hata ~1,5 m (plan: 1472 mm);
  * kesişim kameranın ARKASINDAysa (`s ≤ 0`) ya da ışın düzleme (neredeyse) paralelse sayı döndürüyor (`s = 1e6`);
  * kabin DIŞI nokta reddedilmiyor (D0: gerçek ArUco pozunda pikselin %9'u > 5 m).
Mevcut karakterizasyon golden'ı bunu göremiyordu: pozu R = I (kamera marker'ın ARKASINDA — fiziksel değil).

KAPI (sentetik zemin gerçeği, ağırlık/fotoğraf gerekmez): ÜRÜN YAML'ından fiziksel tutarlı poz — kamera
`camera.fixed_position_cm`de, `look_at_cm`e bakıyor, `up_cabin` yukarı; marker `-qr_to_origin`da, arka duvarda (normal
`-Z`). Hedef düzlemdeki bilinen kabin noktaları piksele izdüşürülür ve geri dönüştürülür: hata < 5 mm. Kameranın
arkasında kesişen piksel ve kabin dışına düşen her ızgara pikseli REDDEDİLİR (`KesisimGecersiz`, `ValueError`).
⚠️ Bu yazılım kapısıdır; VERIFICATION §15'in ±2 cm kabulü ve A-17 gerçek kabin/ArUco ölçümü Oturum 13 (tezgâh) — burada
ölçüm UYDURULMAZ.
"""

from __future__ import annotations

import numpy as np
import pytest
from kabin_fiziksel_poz import fiziksel_poz as _fiziksel_poz
from kabin_fiziksel_poz import genis_aci_ic_parametre
from kabin_fiziksel_poz import izdusur as _izdusur

HATA_MM = 5.0


def _ct():
    from ai_hub.cv_ortak import coord_transform as ct

    return ct


# AI-2 C6: v1 `phantom_cv` / `petri_cv` emekli → hocanın v3 / v2'si (ürün yükleyicilerinin profili).
@pytest.fixture(params=["inference_em_fantom.phantom_cv_v3", "inference_petri_dish.petri_cv_v2"])
def kurulum(request):
    import importlib

    ct = _ct()
    cfg = importlib.import_module(f"ai_hub.{request.param}.cabin_config").load_cabin_config(None)
    return ct, cfg, genis_aci_ic_parametre(ct)  # geniş açı: aşağı bakan ışın da olsun (sentetik)


def _duzlem_noktalari(cfg):
    """Hedef düzlemde, kabin içinde bilinen noktalar (düzlemin iki serbest ekseninde ızgara)."""
    eksen = cfg.phantom_plate.hedef_duzlem_indeksi
    deger = cfg.phantom_plate.hedef_duzlem_mm
    yari = [float(v) * 10.0 / 2 for v in cfg.geometry.cabin_extent_cm]
    serbest = [i for i in range(3) if i != eksen]
    out = []
    for a in np.linspace(-0.7, 0.7, 5):
        for b in np.linspace(-0.7, 0.7, 5):
            P = [0.0, 0.0, 0.0]
            P[eksen] = deger
            P[serbest[0]] = a * yari[serbest[0]]
            P[serbest[1]] = b * yari[serbest[1]]
            out.append(np.array(P))
    return out


@pytest.mark.parametrize("duzlem", ["yaml", "Z0"])
def test_KRITIK_D1100_fiziksel_pozda_bilinen_noktalar_5mm_icinde_GERI_DONER(kurulum, duzlem):
    ct, cfg, intr = kurulum
    if duzlem == "Z0":
        cfg.phantom_plate.hedef_duzlem_eksen = "Z"
        cfg.phantom_plate.hedef_duzlem_cm = 0.0
    poz, R_kk, C = _fiziksel_poz(ct, cfg)
    w, h = intr.image_size
    sinanan, hatalar = 0, []
    for P in _duzlem_noktalari(cfg):
        px = _izdusur(intr.K, R_kk, C, P)
        if px is None or not (0 <= px[0] < w and 0 <= px[1] < h):
            continue
        sinanan += 1
        try:
            p = ct.pixel_to_cabin_mm(px, poz, intr, cfg)
        except ValueError as e:
            hatalar.append((P.tolist(), f"REDDEDİLDİ: {e}"))
            continue
        hata = float(np.linalg.norm(np.asarray(p) - P))
        if hata >= HATA_MM:
            hatalar.append((P.tolist(), round(hata, 1)))
    assert sinanan >= 6, f"aparat: görüntüye düşen bilinen nokta çok az ({sinanan})"
    assert not hatalar, f"{len(hatalar)}/{sinanan} noktada hata ≥ {HATA_MM} mm (ilk 3: {hatalar[:3]})"


def test_KRITIK_D1100_kameranin_ARKASINDA_kesisen_isin_REDDEDILIR(kurulum):
    """Hedef düzlem (YAML: Y = -20 cm) kameranın (Y = -25 cm) ÜSTÜNDE: aşağı bakan ışın düzlemi ARKADA keser."""
    ct, cfg, intr = kurulum
    poz, R_kk, C = _fiziksel_poz(ct, cfg)
    eksen = cfg.phantom_plate.hedef_duzlem_indeksi
    w, h = intr.image_size
    px = None
    for v in range(h - 1, 0, -20):  # alttan yukarı: ilk "arkada" kesişen pikseli ara (aparat ön koşulu)
        ray = R_kk.T @ np.linalg.inv(intr.K) @ np.array([w / 2, v, 1.0])
        s = (cfg.phantom_plate.hedef_duzlem_mm - C[eksen]) / ray[eksen] if abs(ray[eksen]) > 1e-12 else 0
        if s < 0:
            px = (w / 2, float(v))
            break
    assert px is not None, "aparat: kameranın arkasında kesişen piksel bulunamadı (poz/düzlem değişmiş olabilir)"
    with pytest.raises(ValueError) as e:
        p = ct.pixel_to_cabin_mm(px, poz, intr, cfg)
        pytest.fail(f"arkadaki kesişim sayı olarak döndü: {np.round(p, 1).tolist()}")
    assert "arka" in str(e.value).lower(), f"ret nedeni söylenmiyor: {e.value}"


def test_KRITIK_IG572_izgara_taramasinda_KABIN_DISI_nokta_YOK(kurulum):
    """İG-5.72: 16 px ızgara (80 × 45 piksel) — her piksel ya REDDEDİLİR ya kabin İÇİNDE bir nokta döner."""
    ct, cfg, intr = kurulum
    poz, _R, _C = _fiziksel_poz(ct, cfg)
    yari = [float(v) * 10.0 / 2 for v in cfg.geometry.cabin_extent_cm]
    w, h = intr.image_size
    disarida, red, ic = [], 0, 0
    for u in range(8, w, 16):
        for v in range(8, h, 16):
            try:
                p = ct.pixel_to_cabin_mm((float(u), float(v)), poz, intr, cfg)
            except ValueError:
                red += 1
                continue
            if not np.all(np.isfinite(p)) or any(abs(float(p[i])) > yari[i] + 1e-6 for i in range(3)):
                disarida.append(((u, v), np.round(p, 0).tolist()))
            else:
                ic += 1
    assert not disarida, f"{len(disarida)} piksel kabin DIŞI nokta üretti (ilk 3: {disarida[:3]}); red={red}, iç={ic}"
    assert ic > 0, "aparat: hiçbir piksel kabin içine düşmedi (karşıt kol boş)"


def test_KARSIT_D1100_kabin_ici_hedef_KABUL_ve_dusuk_hata(kurulum):
    ct, cfg, intr = kurulum
    poz, R_kk, C = _fiziksel_poz(ct, cfg)
    eksen = cfg.phantom_plate.hedef_duzlem_indeksi
    P = np.zeros(3)
    P[eksen] = cfg.phantom_plate.hedef_duzlem_mm
    px = _izdusur(intr.K, R_kk, C, P)
    assert px is not None
    p = ct.pixel_to_cabin_mm(px, poz, intr, cfg)
    assert float(np.linalg.norm(np.asarray(p) - P)) < HATA_MM


def test_KRITIK_D1100_ret_turu_ValueError_ALT_SINIFI_ve_ADLANDIRILMIS():
    ct = _ct()
    assert issubclass(ct.KesisimGecersiz, ValueError), "ret türü ValueError değil (çağıranlar ValueError yakalar)"


# ── Tüketiciler: geçersiz kesişim → bölge "konum çözülemedi" (sayı UYDURULMAZ, doz yok, çizim/aday/XAI/bağlam dürüst) ──
from test_em_ongorucu_SONLU_OLMAYAN_girdi_PIKSEL_kipi_ve_TOPLAM_sure import (  # noqa: E402,F401 — aparat
    _KayitciDoz,
    fantom_hatti,
    fantom_ucu,
    petri_hatti,
)


def _red_sinifi():
    ct = _ct()
    return getattr(ct, "KesisimGecersiz", ValueError)  # düzeltme öncesi ağaçta sınıf yok


def _aruco_yamala(mod, monkeypatch, cozulemeyen, yalniz_kabul=None):
    """ArUco kipini aç: poz var; `cozulemeyen` piksellerde dönüşüm REDDEDER, diğerlerinde kabin içi nokta döner."""

    class _Poz:
        marker_id = 0
        tvec = np.zeros((3, 1))
        R = np.eye(3)
        rvec = np.zeros((3, 1))
        reproj_error_px = 0.5
        marker_pos_cabin_mm = np.zeros(3)

    Red = _red_sinifi()

    def _p2c(px, *a, **k):
        # yalniz_kabul verilirse YALNIZ o piksel cozulur (kuyu merkezi), diger HER piksel (kontur) reddedilir.
        if yalniz_kabul is not None and not (abs(px[0] - yalniz_kabul[0]) < 0.5 and abs(px[1] - yalniz_kabul[1]) < 0.5):
            raise Red('kesisim kabin DISINDA (test)')
        if any(abs(px[0] - c[0]) < 0.5 and abs(px[1] - c[1]) < 0.5 for c in cozulemeyen):
            raise Red("isin hedef duzlemini kameranin ARKASINDA kesiyor (test)")
        return np.array([-40.0 + 0.01 * px[0], 1.0, -10.0])

    monkeypatch.setattr(mod, "detect_aruco_marker", lambda *a, **k: type("M", (), {"corners_px": np.zeros((4, 2))})())
    monkeypatch.setattr(mod, "solve_cabin_pose", lambda *a, **k: _Poz())
    monkeypatch.setattr(mod, "pixel_to_cabin_mm", _p2c)


def test_KRITIK_D1100_fantom_ArUco_COZULEMEYEN_bolge_konumsuz_dozsuz_ve_CIZILIR(fantom_hatti, monkeypatch):
    pl, _kos = fantom_hatti
    _aruco_yamala(pl, monkeypatch, [(330.0, 230.0)])
    hat = pl.PhantomCvPipeline(None, manual_fallback=False)
    hat._predictor = _KayitciDoz()
    sonuc, ctx = hat.process_image(np.zeros((480, 640, 3), np.uint8))
    assert sonuc.success and sonuc.method == "aruco_pnp", sonuc.error
    t = sonuc.tumor_regions[0]
    assert t.centroid_cabin_mm is None and t.centroid_cabin_cm is None, (
        f"geçersiz kesişim sayı oldu: {t.centroid_cabin_mm}"
    )
    assert "ARKA" in (t.konum_hatasi or ""), f"neden taşınmıyor: {t.konum_hatasi!r}"
    assert hat._predictor.cagri == [] and t.D == [] and t.E_cancer is None, "konumsuz bölgeye doz hesaplandı"
    hat.render_panels(ctx, sonuc, lang="tr")  # GERÇEK çizim None konumla çökmemeli

    from servers import ai_pro_hedef

    assert ai_pro_hedef.FantomSaglayici()._adaylar(sonuc) == [], "konumsuz bölge AI Pro hedefi oldu"


def test_KRITIK_D1100_petri_ArUco_COZULEMEYEN_kuyu_konumsuz_alansiz_dozsuz(petri_hatti, monkeypatch):
    pp, kos, _Yolo = petri_hatti
    _aruco_yamala(pp, monkeypatch, [(320.0, 240.0)])
    hat, sonuc, ctx = kos()
    assert sonuc.method == "aruco_pnp", sonuc.method
    w = sonuc.wells[0]
    assert w.centroid_cabin_mm is None and w.area_mm2 is None, (w.centroid_cabin_mm, w.area_mm2)
    assert "ARKA" in (w.konum_hatasi or "") and hat._predictor.cagri == [] and w.D == []
    hat.render_panels(ctx, sonuc, lang="tr")

    from servers import ai_pro_hedef

    assert ai_pro_hedef.PetriSaglayici()._adaylar(sonuc) == [], "konumsuz kuyu AI Pro hedefi oldu"


def test_KARSIT_D1100_petri_ArUco_COZULEN_kuyu_konumlu_ve_dozlu(petri_hatti, monkeypatch):
    pp, kos, _Yolo = petri_hatti
    _aruco_yamala(pp, monkeypatch, [])
    hat, sonuc, _ctx = kos()
    w = sonuc.wells[0]
    assert w.centroid_cabin_mm is not None and len(hat._predictor.cagri) == 1 and w.konum_hatasi is None


def test_KRITIK_D1100_em_fantom_XAI_ve_canli_E_KONUMSUZ_ilk_bolgeden_KURULMAZ(fantom_ucu, fantom_hatti, monkeypatch):
    """İlk bölge çözülemiyor, ikinci çözülüyor: XAI ve canlı E bağlamı İKİNCİDEN; eski bağlam BAYAT kalmaz."""
    from ai_hub.inference_em_fantom.phantom_cv_v3.color_segment import Region

    c, ef, kutu, govde = fantom_ucu
    pl, _kos = fantom_hatti
    maske = np.zeros((480, 640), np.uint8)
    t1 = Region(
        organ_id=1,
        label="tumor",
        centroid_px=(330.0, 230.0),
        area_px=167,
        bbox_px=(320, 220, 20, 20),
        contour_px=np.zeros((4, 1, 2), np.int32),
        mask=maske,
    )
    t2 = Region(
        organ_id=1,
        label="tumor",
        centroid_px=(300.0, 250.0),
        area_px=120,
        bbox_px=(290, 240, 20, 20),
        contour_px=np.zeros((4, 1, 2), np.int32),
        mask=maske,
    )
    monkeypatch.setattr(pl, "segment_phantom", lambda *a, **k: {"tumor": [t1, t2], "healthy": []})
    _aruco_yamala(pl, monkeypatch, [(330.0, 230.0)])
    kutu["ong"] = _KayitciDoz()
    ef.set_context([{"centroid_cabin_mm": [99.0, 99.0, 99.0], "organ_id": 1}])  # önceki analizden kalan bağlam
    r = c.post("/api/ai/vision/em_fantom", data={"image_base64": govde})
    assert r.status_code == 200, r.text[:200]
    bolgeler = r.json()["tumor_regions"]
    assert bolgeler[0]["centroid_cabin_mm"] is None and bolgeler[1]["centroid_cabin_mm"] is not None
    x2 = bolgeler[1]["centroid_cabin_mm"][0]
    assert kutu["xai"] and abs(kutu["xai"][0][1] - x2) < 1e-9, (
        f"XAI konumsuz bölgeden ya da (0,0,0)'dan: {kutu['xai'][:1]}"
    )
    bag = ef.get_context()
    assert bag is not None and abs(bag["x"] - x2) < 1e-9, f"canlı E bağlamı yanlış/bayat: {bag}"


def test_KRITIK_D1100_em_fantom_HIC_konum_yoksa_bayat_baglam_TEMIZLENIR(fantom_ucu, fantom_hatti, monkeypatch):
    c, ef, kutu, govde = fantom_ucu
    pl, _kos = fantom_hatti
    _aruco_yamala(pl, monkeypatch, [(330.0, 230.0)])
    kutu["ong"] = _KayitciDoz()
    ef.set_context([{"centroid_cabin_mm": [99.0, 99.0, 99.0], "organ_id": 1}])
    r = c.post("/api/ai/vision/em_fantom", data={"image_base64": govde})
    assert r.status_code == 200, r.text[:200]
    assert ef.get_context() is None, f"konumu çözülemeyen analizden sonra ÖNCEKİ bağlam kaldı: {ef.get_context()}"
    assert kutu["xai"] == [] and "xaiSensitivity" not in r.json(), "konumsuz bölgede XAI üretildi"


def test_KRITIK_D1100_petri_kontur_noktasi_REDDEDILINCE_alan_mm2_YAZILMAZ(petri_hatti, monkeypatch):
    """Merkez çözülür, kontur noktaları çözülemez: konum ve doz var, ALAN bilinmiyor (None) — kısmi konturla alan uydurulmaz."""
    pp, kos, _Yolo = petri_hatti
    _aruco_yamala(pp, monkeypatch, [], yalniz_kabul=(320.0, 240.0))
    hat, sonuc, _ctx = kos()
    w = sonuc.wells[0]
    assert w.centroid_cabin_mm is not None and len(hat._predictor.cagri) == 1, "aparat: merkez çözülmeliydi"
    assert w.area_mm2 is None, f"kontur noktaları kabin dışıyken alan yazıldı: {w.area_mm2}"


@pytest.fixture
def petri_ucu_d100(petri_hatti, monkeypatch):
    import base64

    from fastapi.testclient import TestClient
    from servers import ai_router as air
    from servers import api_server as api
    from test_em_ongorucu_SONLU_OLMAYAN_girdi_PIKSEL_kipi_ve_TOPLAM_sure import _kabin_petri_tekil, _renkli_jpg

    from ai_hub.inference_em_petri import inference_em_petri as iep

    pp, _kos, _Yolo = petri_hatti
    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    api.app.dependency_overrides[air.require_research] = lambda: None
    xai = []
    monkeypatch.setattr(iep, "xai_hizli_sensitivity", lambda *a, **k: xai.append(a) or {"sahte": 1})

    def _yukle(ad, yukleyici):
        return {
            "cls": pp.PetriCvPipeline,
            "cfg": _kabin_petri_tekil(),
            "yolo_path": None,
            "yolo": _Yolo(),
            "predictor": _KayitciDoz(),
        }

    monkeypatch.setattr(air, "_get_or_load_model", _yukle)
    try:
        yield TestClient(api.app), base64.b64encode(_renkli_jpg()).decode(), xai, pp
    finally:
        api.app.dependency_overrides.pop(air.require_research, None)


def test_KRITIK_D1100_em_petri_KONUMSUZ_kuyuda_XAI_000da_URETILMEZ(petri_ucu_d100, monkeypatch):
    c, govde, xai, pp = petri_ucu_d100
    _aruco_yamala(pp, monkeypatch, [(320.0, 240.0)])
    r = c.post("/api/ai/vision/em_petri", data={"image_base64": govde})
    assert r.status_code == 200, r.text[:200]
    assert r.json()["wells"][0]["centroid_cabin_mm"] is None
    assert xai == [] and "xaiSensitivity" not in r.json(), f"konumsuz kuyuda XAI üretildi: {xai[:1]}"


@pytest.mark.parametrize("uc", ["em_fantom", "em_petri"])
def test_KRITIK_D1100_servis_KONUMSUZ_bolgede_XAI_000da_URETILMEZ(fantom_hatti, petri_hatti, monkeypatch, uc):
    from test_em_ongorucu_SONLU_OLMAYAN_girdi_PIKSEL_kipi_ve_TOPLAM_sure import (
        _govde,
        _kabin,
        _kabin_petri_tekil,
        _servis_cagir,
    )

    import ai_service.app as a
    from ai_hub.inference_em_fantom import inference_em_fantom as ief
    from ai_hub.inference_em_petri import inference_em_petri as iep

    pl, _fk = fantom_hatti
    pp, _pk, _Yolo = petri_hatti
    xai = []
    monkeypatch.setattr(ief, "xai_hizli_sensitivity", lambda *a, **k: xai.append("fantom") or {"sahte": 1})
    monkeypatch.setattr(iep, "xai_hizli_sensitivity", lambda *a, **k: xai.append("petri") or {"sahte": 1})
    monkeypatch.setattr(a, "_prov_dev", lambda s: "cpu")

    def _al(ad):
        if ad == "em_fantom":
            return {
                "cls": pl.PhantomCvPipeline,
                "cfg": _kabin("inference_em_fantom.phantom_cv_v3"),
                "predictor": _KayitciDoz(),
            }
        return {
            "cls": pp.PetriCvPipeline,
            "cfg": _kabin_petri_tekil(),
            "yolo_path": None,
            "yolo": _Yolo(),
            "predictor": _KayitciDoz(),
        }

    monkeypatch.setattr(a.predictors, "get", _al)
    if uc == "em_fantom":
        _aruco_yamala(pl, monkeypatch, [(330.0, 230.0)])
    else:
        _aruco_yamala(pp, monkeypatch, [(320.0, 240.0)])
    kod, j = _govde(_servis_cagir(a, uc))
    assert kod == 200, (kod, str(j)[:200])
    assert xai == [] and "xaiSensitivity" not in j, f"servis ({uc}) konumsuz bölgede XAI üretti"
