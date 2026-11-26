# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""FK · K1 (istem 58, KD-3b'nin kedi karşılığı) — kedi organ hattı SABİT DÜZLEM kalibrasyonlu kabinde organın kabin konumunu üretir;
poz kırpması kedi kutusundan.

KUSUR 1 (K1 çevrimdışı ölçümü, K0 peluş kaydı 419 kare, `DENETIM\\FANTOM-KEDI.md`): kabin kamerası üstte, kabinde ArUco YOK (KD · Y258);
kedi hattının kabin koordinatı yalnız ArUco + perspektif çözümünden geliyordu → organlar HEP kalibrasyonsuz (güven tavanı 0,25 < AI Pro
eşiği 0,3): her sahnede "Tüm Vücut lokalize" %0, ODAK gövde girdisi %0 — AI Pro kediyi bulsa da hedefi hiç lokalize edemiyordu.
DÜZELTME: veri kökünde sabit düzlem kalibrasyonu varsa organ pikseli → ışın → hedef düzlemi (taban + yüzüstü organ yüksekliği × ölçülen
ölçek) → kabin mm; kamera farklı / oynamış ise konum ÜRETİLMEZ ve ipucu kalibrasyonun eylemini söyler. Dosya yoksa davranış AYNEN.

KUSUR 2 (K0 bulgusu B1'in ürün hattındaki biçimi): SuperAnimal dedektörünün EN YÜKSEK skorlu kutusu boş / dolu kabinde bütün kabini
kaplıyor (halkalar, 0,95) → poz o kutudan kırpılınca 39 nokta kabine saçılıyor, organlar kedinin dışına düşüyordu (ölçek ×1,45).
DÜZELTME: poz kırpması kedi (segmentasyon) kutusuyla örtüşen dedektör kutusundan; en yüksek skorlu kutu örtüşüyorsa davranış AYNEN.

YÖNTEM: sentetik üstten kabin kamerası (`DuzlemHaritasi.durustan`) + kanonik kedi bilinen ölçek / konumla izdüşürülür; GERÇEK
`estimate_organs_pnp` / `CatOrganPredictor.predict` / `ai_router._localize_organ_cpu` / `KediSaglayici`; yalnız ONNX koşucuları sahte.
Kamera açılmaz, ağa çıkılmaz.
"""

from __future__ import annotations

import capraz
import numpy as np
import pytest

cv2 = capraz.paket_yoksa_atla("cv2")

W, H = 1920, 1080
EXT = [55.5, 35.0, 40.5]
TABAN = -175.0
#: Kedi gerçek ölçeği (kanonik = 1) ve gövde merkezi (kabin mm; baş +Z = kabin arkası yönünde).
K_GERCEK, XC, ZC = 0.8, 60.0, 30.0


def _harita():
    from ai_hub.cv_ortak import sabit_duzlem as sd

    K = [[1400.0, 0.0, 960.0], [0.0, 1400.0, 540.0], [0.0, 0.0, 1.0]]
    R = np.array([[-1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, -1.0, 0.0]])  # üstten: görüntü sağı = −X, aşağı = ön (−Z)
    C = np.array([0.0, 205.0, 0.0])  # taban camından 380 mm yukarıda
    return sd.DuzlemHaritasi.durustan(K, [0.0] * 5, (W, H), R, -R @ C, EXT, -155.0)


def _kal(kimlik=None):
    """`kare_hazirla` için asgari kalibrasyon sözlüğü (sentetik harita ile aynı duruş)."""
    h = _harita()
    return {
        "kamera": {"genislik": W, "yukseklik": H, "indeks": 0, "kimlik": kimlik},
        "ic_parametre": {"K": h.K.tolist(), "D": h.D.tolist()},
        "R": h.R.tolist(),
        "t_mm": h.t.tolist(),
        "kabin_ext_cm": EXT,
        "duzlem_y_mm": -155.0,
        "referans": {"sahne_denetimi": False},
    }


def _dunya(p_cm, k=K_GERCEK):
    """Kanonik kedi noktası (cm; +X baş, +Y sırt, +Z sağ) → kabin mm: kedi YÜZÜSTÜ (karın tabanda), başı +Z'ye."""
    from ai_hub.inference_cat_organ.lib.duzlem_organ import KARIN_Y_CM

    x, y, z = (float(v) for v in p_cm)
    return np.array([XC - 10.0 * k * z, TABAN + 10.0 * k * (y - KARIN_Y_CM), ZC + 10.0 * k * x])


def _kp_ve_kutu(harita):
    from ai_hub.inference_cat_organ.lib.canonical import CANONICAL_CAT_3D, KEYPOINT_NAMES

    uv = np.array([harita.piksel(_dunya(CANONICAL_CAT_3D[n]), duzeltilmis=False) for n in KEYPOINT_NAMES])
    kp = np.column_stack([uv, np.full(len(uv), 0.9)])
    kutu = [
        float(uv[:, 0].min()) - 15,
        float(uv[:, 1].min()) - 15,
        float(uv[:, 0].max()) + 15,
        float(uv[:, 1].max()) + 15,
    ]
    return kp, kutu


# ── 1) saf geometri ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_KRITIK_FK_K1_duzlem_organ_olcegi_ve_konumu_GERI_bulur():
    from ai_hub.inference_cat_organ.lib import duzlem_organ as do
    from ai_hub.inference_cat_organ.lib.canonical import CANONICAL_ORGANS_3D

    h = _harita()
    merkez = h.piksel(_dunya((0.0, 0.0, 0.0)), duzeltilmis=False)
    s = K_GERCEK * do.duzlem_piksel_cm(h, merkez, TABAN + K_GERCEK * do.GOVDE_ORTA_CM * 10.0)
    org = [CANONICAL_ORGANS_3D[i] for i in sorted(CANONICAL_ORGANS_3D)]
    gercek = [_dunya(o[1:]) for o in org]
    px = [h.piksel(P, duzeltilmis=False) for P in gercek]
    r = do.organ_kabin_konumlari(h, px, [o[2] for o in org], s, merkez)
    assert r["neden"] is None and abs(r["olcek"] - K_GERCEK) < 0.02, r
    for P, Q, hh in zip(gercek, r["konumlar_mm"], r["yukseklik_mm"]):
        assert Q is not None and np.linalg.norm(np.asarray(Q) - P) < 3.0, (P, Q)
        assert abs((P[1] - TABAN) - hh) < 3.0


def test_KRITIK_FK_K1_olcek_kedi_araligi_DISINDA_konum_URETMEZ():
    from ai_hub.inference_cat_organ.lib import duzlem_organ as do

    h = _harita()
    merkez = h.piksel(_dunya((0.0, 0.0, 0.0)), duzeltilmis=False)
    r = do.organ_kabin_konumlari(h, [merkez], [0.0], 0.5, merkez)  # 0,5 px / kanonik cm → k ≈ 0,02
    assert r["neden"] == "olcek_disi" and r["konumlar_mm"] == [None] and r["olcek"] < do.OLCEK_ARALIGI[0]


def test_KRITIK_FK_K1_kabin_DISI_organ_None_hepsi_disiysa_kesisim_yok():
    from ai_hub.inference_cat_organ.lib import duzlem_organ as do

    h = _harita()
    merkez = h.piksel(_dunya((0.0, 0.0, 0.0)), duzeltilmis=False)
    s = K_GERCEK * do.duzlem_piksel_cm(h, merkez, TABAN + 44.0)
    disari = h.piksel(np.array([270.0, TABAN + 40.0, 30.0]), duzeltilmis=False) + np.array(
        [-400.0, 0.0]
    )  # sol camın ötesi
    r = do.organ_kabin_konumlari(h, [merkez, disari], [0.0, 0.0], s, merkez)
    assert (
        r["konumlar_mm"][0] is not None
        and r["konumlar_mm"][1] is None
        and r["yukseklik_mm"][1] is None
        and r["neden"] is None
    )
    r2 = do.organ_kabin_konumlari(h, [disari], [0.0], s, merkez)
    assert r2["konumlar_mm"] == [None] and r2["neden"] == "kesisim_yok"


def test_KRITIK_FK_K1_isin_kesmiyorsa_kesisim_yok():
    from ai_hub.inference_cat_organ.lib import duzlem_organ as do

    class _Kesmez:
        taban_y_mm = TABAN

        def kabin_noktasi(self, *a, **k):
            raise ValueError("isin hedef duzlemine paralel")

    r = do.organ_kabin_konumlari(_Kesmez(), [(1.0, 2.0)], [0.0], 30.0, (1.0, 2.0))
    assert r == {
        "olcek": None,
        "duzlem_px_cm": None,
        "konumlar_mm": [None],
        "yukseklik_mm": [None],
        "neden": "kesisim_yok",
    }


# ── 2) organ atlası hattı ───────────────────────────────────────────────────────────────────────────────────────────────────
def _pnp(harita):
    from ai_hub.inference_cat_organ.lib.canonical import KEYPOINT_NAMES
    from ai_hub.inference_cat_organ.lib.pipeline import estimate_organs_pnp

    kp, kutu = _kp_ve_kutu(_harita())  # noktalar her zaman sentetik kameradan; düzlem için verilen harita
    kpd = {n: kp[i, :2] for i, n in enumerate(KEYPOINT_NAMES)}
    return estimate_organs_pnp(
        kpd, kp[:, 2], np.array(kutu), {"type": "sphinx", "confidence": 0.85}, cabin_params={"duzlem_harita": harita}
    )


def test_KRITIK_FK_K1_atlas_hatti_HARITAYLA_kalibre_ve_kabin_konumu_dogru():
    from ai_hub.inference_cat_organ.lib.canonical import CANONICAL_ORGANS_3D

    r = _pnp(_harita())
    org = r["organs"]
    assert {o["calibrated"] for o in org.values()} == {True}, (
        "sabit düzlem varken organ kalibrasyonsuz kaldı (tavan 0,25)"
    )
    assert {o.get("cabin_origin") for o in org.values()} == {"sabit_duzlem"}
    assert max(o["reliability"] for o in org.values()) > 0.3, "kalibrasyonsuz tavan kalkmadı"
    d = r["pnp_fit"]["duzlem"]
    assert d["neden"] is None and abs(d["olcek"] - K_GERCEK) < 0.15, d
    for oid, o in org.items():
        P = _dunya(CANONICAL_ORGANS_3D[oid][1:])
        Q = np.array(o["coord_cabin_cm"]) * 10.0
        assert np.hypot(*(Q - P)[[0, 2]]) < 15.0, (oid, P, Q)  # yatay ≤ 1,5 cm (zayıf perspektif uydurması)
        assert o["hedef_yukseklik_cm"] == pytest.approx((Q[1] - TABAN) / 10.0, abs=0.02)


def test_KARSIT_FK_K1_atlas_hatti_HARITASIZ_aynen_kalibrasyonsuz():
    from ai_hub.inference_cat_organ.lib.canonical import KEYPOINT_NAMES
    from ai_hub.inference_cat_organ.lib.pipeline import estimate_organs_pnp

    kp, kutu = _kp_ve_kutu(_harita())
    kpd = {n: kp[i, :2] for i, n in enumerate(KEYPOINT_NAMES)}
    r = estimate_organs_pnp(kpd, kp[:, 2], np.array(kutu), {"type": "sphinx", "confidence": 0.85}, cabin_params={})
    assert {o["calibrated"] for o in r["organs"].values()} == {False}
    assert not any("coord_cabin_cm" in o for o in r["organs"].values())
    assert max(o["reliability"] for o in r["organs"].values()) <= 0.25 + 1e-9
    assert r["pnp_fit"]["duzlem"] is None


def test_KRITIK_FK_K1_atlas_hatti_kesisim_yoksa_KALIBRASYONSUZ_ve_neden():
    class _Kesmez:
        taban_y_mm = TABAN

        def kabin_noktasi(self, *a, **k):
            raise ValueError("kameranin arkasinda")

    r = _pnp(_Kesmez())
    assert {o["calibrated"] for o in r["organs"].values()} == {False}
    assert r["pnp_fit"]["duzlem"] == {"olcek": None, "duzlem_px_cm": None, "neden": "kesisim_yok"}


# ── 3) öngörücü (kalibrasyon durumu + kare denetimleri) ─────────────────────────────────────────────────────────────────────
@pytest.fixture
def ongorucu(monkeypatch, tmp_path):
    from ai_hub.inference_cat_organ import catorgan_predictor as cp
    from ai_hub.inference_cat_organ.lib import runners

    kp, kutu = _kp_ve_kutu(_harita())
    cagri: dict = {}

    def _seg(p, device="cpu"):
        return {"bbox": kutu, "n_detections": 1, **({"mask_xy": cagri["maske"]} if cagri.get("maske") else {})}

    def _poz(p, device="cpu", **k):
        cagri["kedi_kutusu"] = k.get("kedi_kutusu")
        return {"keypoints": kp, "kutu_kaynagi": "segmentasyon"}

    monkeypatch.setattr(runners, "run_yolo_segmentation", _seg)
    monkeypatch.setattr(runners, "run_pose", _poz)
    monkeypatch.setattr(cp.CatOrganPredictor, "_resolve_models", lambda self, d: None)
    img = tmp_path / "kare.png"
    ok, buf = cv2.imencode(".png", np.full((H, W, 3), 120, np.uint8))
    img.write_bytes(buf.tobytes())
    return cp.CatOrganPredictor(device="cpu"), str(img), cagri, kutu


def test_KRITIK_FK_K1_ongorucu_GECERLI_duzlemle_organlar_kalibre(ongorucu):
    p, img, cagri, kutu = ongorucu
    r = p.predict(img, render=False, duzlem=(_kal(), None), kamera_indeksi=0)
    assert r["kabin_duzlemi"]["gecerli"] is True and r["kabin_duzlemi"]["engeller"] == []
    assert {o["calibrated"] for o in r["organs"].values()} == {True}
    assert cagri["kedi_kutusu"] == kutu, "poz kırpmasına kedi (segmentasyon) kutusu verilmedi"
    assert r["pose_kutusu"] == "segmentasyon"


def test_KRITIK_FK_K1_ongorucu_KAMERA_FARKLI_konum_URETMEZ_ve_soyler(ongorucu):
    p, img, _c, _k = ongorucu
    r = p.predict(
        img,
        render=False,
        duzlem=(_kal({"ad": "FHD Camera", "vidpid": "VID_1"}), None),
        kamera_kimligi={"ad": "Baska", "vidpid": "VID_2"},
    )
    assert r["kabin_duzlemi"]["engeller"] == ["kalibrasyon_kamera_farkli"]
    assert {o["calibrated"] for o in r["organs"].values()} == {False}
    assert not any("coord_cabin_cm" in o for o in r["organs"].values())


def test_KRITIK_FK_K1_ongorucu_SAHNE_denetimi_kedi_MASKESINI_disler_ve_engel_konumu_keser(ongorucu, monkeypatch):
    from ai_hub.cv_ortak import sabit_duzlem as sd

    p, img, cagri, kutu = ongorucu
    gorulen = []

    def _sahne(kd, kare, cokgenler=(), **k):
        gorulen.append((kare.shape, [np.asarray(c) for c in cokgenler]))
        kd.engel("kamera_oynamis", "sabit sahne 20 px kaymis (esik 12)")

    monkeypatch.setattr(sd, "sahne_denetle", _sahne)
    for maske in (None, [[kutu[0], kutu[1]], [kutu[2], kutu[1]], [kutu[2], kutu[3]]]):
        cagri["maske"] = maske
        r = p.predict(img, render=False, duzlem=(_kal(), None))
        assert r["kabin_duzlemi"]["engeller"] == ["kamera_oynamis"]
        assert {o["calibrated"] for o in r["organs"].values()} == {False}
    assert [g[0] for g in gorulen] == [(H, W, 3)] * 2
    assert gorulen[0][1][0].shape == (4, 2) and gorulen[1][1][0].shape == (3, 2), (
        "dışlanan çokgen kedi kutusu / maskesi değil"
    )
    assert np.allclose(gorulen[0][1][0][0], kutu[:2], atol=1.0)  # bozulmasız kamerada çokgen = kutu


def test_KARSIT_FK_K1_ongorucu_DUZLEMSIZ_ve_DOSYASIZ_aynen(ongorucu):
    p, img, _c, _k = ongorucu
    for d in (None, (None, None)):
        r = p.predict(img, render=False, duzlem=d)
        assert r["kabin_duzlemi"] is None
        assert {o["calibrated"] for o in r["organs"].values()} == {False}


# ── 4) poz kutusu seçimi ────────────────────────────────────────────────────────────────────────────────────────────────────
KABIN = [223.0, 114.0, 1710.0, 1014.0]
KEDI = [298.0, 184.0, 719.0, 771.0]


@pytest.mark.parametrize(
    "kutular, skorlar, kedi, beklenen_kaynak, beklenen",
    [
        ([KABIN], [0.95], None, "dedektor", KABIN),  # kedi kutusu yok → eskisi gibi en yüksek skor
        (
            [[300.0, 190.0, 715.0, 760.0], KABIN],
            [0.97, 0.6],
            KEDI,
            "dedektor",
            [300.0, 190.0, 715.0, 760.0],
        ),  # örtüşüyor → AYNEN
        ([KABIN, [290.0, 180.0, 725.0, 780.0]], [0.95, 0.55], KEDI, "dedektor_ortusen", [290.0, 180.0, 725.0, 780.0]),
        ([KABIN], [0.95], KEDI, "segmentasyon", KEDI),  # yalnız bütün-kabin kutusu → kedi kutusu (K0 kaydı)
    ],
)
def test_KRITIK_FK_K1_poz_kutusu_secimi(kutular, skorlar, kedi, beklenen_kaynak, beklenen):
    from ai_hub.inference_cat_organ.lib import runners

    kutu, kaynak = runners._poz_kutusu(np.array(kutular, np.float32), np.array(skorlar, np.float32), kedi)
    assert kaynak == beklenen_kaynak and np.allclose(kutu, beklenen)


def test_FK_K1_iou_sinirlari():
    from ai_hub.inference_cat_organ.lib import runners

    assert runners._iou([0, 0, 10, 10], [0, 0, 10, 10]) == pytest.approx(1.0)
    assert runners._iou([0, 0, 10, 10], [20, 20, 30, 30]) == 0.0
    assert runners._iou([0, 0, 0, 0], [0, 0, 0, 0]) == 0.0


def test_KRITIK_FK_K1_run_pose_KEDI_kutusundan_kirpar(monkeypatch, tmp_path):
    """GERÇEK `run_pose` (kırpma + SimCC çözme + geri dönüşüm); yalnız iki ONNX oturumu sahte: dedektör bütün kabini 0,95 ile verir."""
    from ai_hub.inference_cat_organ.lib import runners

    for ad in ("det.onnx", "poz.onnx"):
        (tmp_path / ad).write_bytes(b"sahte")
    monkeypatch.setattr(runners, "DET_ONNX", tmp_path / "det.onnx")
    monkeypatch.setattr(runners, "POSE_ONNX", tmp_path / "poz.onnx")
    girdi: list = []

    class _Det:
        def run(self, _o, d):
            return np.array([KABIN], np.float32), np.array([1]), np.array([0.95], np.float32)

    class _Poz:
        def run(self, _o, d):
            girdi.append(d["input"].shape)
            return np.zeros((1, 39, 512), np.float32), np.zeros((1, 39, 512), np.float32)

    monkeypatch.setattr(runners, "_ort_session", lambda yol, cihaz: _Det() if yol.name == "det.onnx" else _Poz())
    img = tmp_path / "kare.png"
    ok, buf = cv2.imencode(".png", np.full((H, W, 3), 90, np.uint8))
    img.write_bytes(buf.tobytes())
    r = runners.run_pose(str(img), device="cpu", kedi_kutusu=KEDI)
    assert r["kutu_kaynagi"] == "segmentasyon" and np.allclose(r["bbox"], KEDI) and girdi == [(1, 3, 256, 256)]
    r0 = runners.run_pose(str(img), device="cpu")
    assert r0["kutu_kaynagi"] == "dedektor" and np.allclose(r0["bbox"], KABIN)


# ── 5) AI Pro (backend) ─────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def ai_pro(ongorucu, monkeypatch):
    from servers import ai_pro_hedef as aph
    from servers import ai_router as air

    p, _img, _c, _k = ongorucu
    monkeypatch.setattr(air, "_get_or_load_catorgan", lambda: p)
    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    monkeypatch.setattr(aph, "secili_kamera_indeksi", lambda: None)
    monkeypatch.setattr(aph, "secili_kamera_kimligi", lambda: None)
    return aph, air, np.full((H, W, 3), 120, np.uint8)


def test_KRITIK_FK_K1_AI_Pro_kedi_SABIT_DUZLEMLE_lokalize_ve_ODAK_govde_girdisi(ai_pro, monkeypatch):
    aph, air, kare = ai_pro
    monkeypatch.setattr(aph, "duzlem_durumu", lambda: (_kal(), None))
    s = aph.KediSaglayici()
    lz, x, y, z, rel, *_ = s.localize(kare, 0)
    assert lz is True and rel > 0.3, f"sabit düzlemli kabinde Tüm Vücut lokalize edilemedi (güven {rel})"
    g = s.odak_kedi_girdisi()
    assert g is not None and g["organ_sayisi"] >= 2, "ODAK kedi gövde girdisi (merkez + yön) çıkmadı"
    assert np.hypot(g["merkez_P"][0] - XC, g["merkez_P"][2] - ZC) < 40.0, g
    lz3, x3, _y3, z3, *_ = s.localize(kare, 3)  # karaciğer
    assert lz3 is True and np.hypot(x3 - XC, z3 - (ZC + 10 * K_GERCEK * 5.5)) < 20.0
    assert s._duzlem_engeli is None


def test_KRITIK_FK_K1_AI_Pro_kedi_DUZLEM_ENGELINDE_lokalize_ETMEZ_ve_EYLEM_soyler(ai_pro, monkeypatch):
    from ai_hub.cv_ortak import sabit_duzlem as sd

    aph, air, kare = ai_pro
    monkeypatch.setattr(aph, "duzlem_durumu", lambda: (_kal(), None))
    monkeypatch.setattr(sd, "sahne_denetle", lambda kd, *a, **k: kd.engel("kamera_oynamis", "20 px"))
    s = aph.KediSaglayici()
    lz, *_ = s.localize(kare, 0)
    assert lz is False and s._duzlem_engeli == "kamera_oynamis"
    assert s.ipucu(True, "Mide") == aph.kapi_metni("kamera_oynamis") and s.ipucu(True, "Mide")
    assert s.ipucu(False, "Mide") == aph.ceviri.t("ai.pro.ipucu.hayvanYok")  # özne yokken eski metin


def test_KARSIT_FK_K1_AI_Pro_kalibrasyon_DOSYASI_YOKSA_ongorucu_eski_imzayla_cagrilir(monkeypatch):
    """Dosya yoksa `predict` YENİ argümanları ALMAZ (eski sahteler / GPU servisi imzası) ve sonuç eskisi gibi."""
    from servers import ai_pro_hedef as aph
    from servers import ai_router as air

    gelen = {}

    class _Eski:
        def predict(self, yol, render=True, target_oid=None):
            gelen["cagri"] = (render, target_oid)
            return {"organs": {}, "kabin_yapilandirmasi": {"yuklendi": True}}

    monkeypatch.setattr(air, "_get_or_load_catorgan", lambda: _Eski())
    monkeypatch.setattr(aph, "duzlem_durumu", lambda: (None, None))
    lz, *_ = air._localize_organ_cpu(np.full((40, 60, 3), 100, np.uint8), 3)
    assert lz is False and gelen["cagri"] == (True, 3) and air._kedi_organ_izi.duzlem == {}
    s = aph.KediSaglayici()
    s._duzlem_engeli = None
    assert s.ipucu(True, "Mide") == aph.ceviri.t("ai.pro.ipucu.hayvanGorunuyor", ad="Mide")
