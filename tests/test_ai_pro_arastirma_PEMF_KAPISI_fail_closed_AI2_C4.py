# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI-2 C4 — hocanın tüketim kapıları AI Pro'da UÇTAN UCA ve FAIL-CLOSED (plan §3.9; hoca ENTEGRASYON §3).

Bobine (ya da `_predict_and_drive` zarfına) giden yolda: `success=false`, `pemf_valid=false`, fantomda `reliable=false`,
`layout_mismatch`, `control_cancer_missed`, `control_healthy_flagged` → sonuç KULLANILMAZ; `oblique_view`, `low_resolution`,
`ring_partial` → çekim TEKRARLANIR. Kapı sağlayıcının `localize`ındadır: kare lokalize SAYILMAZ → `/propose` taze hedef
bulamaz (409 + EYLEM metni), seans döngüsü `_predict_and_drive`ı ÇAĞIRMAZ. `PEMF_ARASTIRMA_AIPRO=1` iken BİLE (bayrak
araştırma sürüşünü AÇAR; bu kapı geçersiz sonucu yine KESER). Her kapıya iki kol: bayrak AÇIK ve KAPALI.

AĞIRLIK GEREKMEZ: `ai_router._get_or_load_model` sahte boru hattı / öngörücüyle doldurulur (sağlayıcı testleriyle aynı
desen); seans döngüsü GERÇEK `_ai_pro_loop`tur (kamera, donanım ve uyku sahtelenir).
"""

from __future__ import annotations

import time

import numpy as np
import pytest
from kd_kalibrasyon_yardimci import (
    kd_gecerli_kalibrasyon,  # noqa: F401,E402  KD · Y259: kalibrasyon ön koşulu sağlanmış (bu dosya başka kuralı ölçer)
)

_EYLEM_PETRI = (
    "PEMF değerleri geçersiz: plakanın kabindeki konumu bilinmiyor — kabine ArUco koyun ya da konumu ayarlayın."
)


# ── Sahte v2 / v3 boru hattı ────────────────────────────────────────────────────────────────────────────────────
class _Bolge:
    def __init__(self, px, mm, organ_id=1, tid="T1", wid="A1"):
        self.centroid_px, self.centroid_cabin_mm = px, mm
        self.centroid_cabin_cm = tuple(v / 10.0 for v in mm)
        self.organ_id, self.area_px, self.bbox_px = organ_id, 100, (0, 0, 20, 20)
        self.E_cancer, self.E_healthy = 0.9, 0.1
        self.tumor_id, self.well_id = tid, wid
        self.reliability, self.conf = 0.8, 0.9


class _Sonuc:
    """GEÇERLİ bir v2 / v3 sonucu (ArUco kipi); testler tek alanı bozar."""

    def __init__(self, **k):
        self.success, self.error, self.method, self.mm_per_px = True, None, "aruco_pnp", 0.0
        self.pemf_valid, self.reliable, self.warnings = True, True, []
        self.pemf_source, self.coord_frame, self.layout = "aruco", "cabin_aruco", {}
        self.tumor_regions = [_Bolge((10, 10), (-40.0, 0.0, 0.0))]
        self.healthy_regions = []
        self.wells = [_Bolge((10, 10), (-40.0, 0.0, 0.0), wid="B2")]
        self.phantom_detection = {"primary": {"solidity": 0.9, "n_blue_inside": 5}}
        self.plate, self.classification = {"plate_type": 24}, {"control_healthy": ["A1"], "control_cancer": ["B2"]}
        for a, v in k.items():
            setattr(self, a, v)


class _Hat:
    kuyruk: list = []

    def __init__(self, cfg, **kw):
        self.cfg, self._predictor, self.yolo = cfg, None, None

    def process_image(self, frame, achieved_B=None, duty_sum=None):
        return (_Hat.kuyruk[0] if _Hat.kuyruk else _Sonuc()), {}

    def render_panels(self, ctx, result, lang="tr"):
        return {"07_combined": None}


class _Ongorucu:
    def __init__(self):
        self.cagri = []

    def predict(self, **k):
        self.cagri.append(k)
        return {
            **{f"D{i}": 0.3 for i in range(1, 8)},
            **{f"P{i}": 0.0 for i in range(1, 8)},
            "result_E_cancer": 0.5,
            "result_E_healthy": 0.1,
            "result_E_avg": 0.3,
        }


class _Cfg:
    class phantom:  # noqa: N801
        achieved_B, duty_sum = 0.001, 2.4


@pytest.fixture()
def sag(monkeypatch):
    import servers.ai_pro_hedef as hedef
    import servers.ai_router as air

    ong = _Ongorucu()
    cache = {"cls": _Hat, "cfg": _Cfg(), "predictor": ong, "yolo": None, "yolo_path": "y.onnx"}
    monkeypatch.setattr(air, "_get_or_load_model", lambda ad, y: cache)
    monkeypatch.setattr(hedef, "hedef_kabin_disi_nedeni", lambda *a: "")  # kabin geometrisi bu kapının konusu değil
    _Hat.kuyruk = []
    return hedef, hedef.FantomSaglayici(), hedef.PetriSaglayici(), ong


#: (model, bozulan alanlar, beklenen neden kodu)
DURUMLAR = [
    ("petri", {"pemf_valid": False}, "pemf_gecersiz"),
    ("fantom", {"pemf_valid": False}, "pemf_gecersiz"),
    ("fantom", {"reliable": False}, "guvenilir_degil"),
    ("fantom", {"warnings": ["layout_mismatch: referans yerlesime kayit hatasi 9.1 mm"]}, "layout_mismatch"),
    ("petri", {"warnings": ["control_cancer_missed: B2 (blue=0.001)"]}, "control_cancer_missed"),
    ("petri", {"warnings": ["control_healthy_flagged: A1 (frac)"]}, "control_healthy_flagged"),
    ("petri", {"warnings": ["oblique_view: olcek degisimi x1.34"]}, "oblique_view"),
    # KD-2b · Y264: petri hattı `low_resolution` üretmez (kuyu yarıçapı eşiği kaldırıldı); kod fantom tümör eşiğinde KALIR.
    ("fantom", {"warnings": ["low_resolution: tumor yaricapi ~4px - yaklas"]}, "low_resolution"),
    ("fantom", {"warnings": ["ring_unavailable: ring_partial: halkanin %31'i gorunur (<%35)"]}, "ring_partial"),
]
_IDS = [f"{m}-{n}" for m, _, n in DURUMLAR]


# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# 1. SAF KAPI (tek kaynak)
# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("model,boz,neden", DURUMLAR, ids=_IDS)
def test_KRITIK_kapi_her_kosulda_SURULEMEZ_ve_EYLEM_soyler(model, boz, neden):
    from ai_hub.cv_ortak import pemf_kapisi as pk

    k = pk.degerlendir(_Sonuc(**boz), model=model)
    assert k["surulebilir"] is False and neden in k["nedenler"], k
    assert k["eylem"] and any(m["kod"] == neden for m in k["mesajlar"])


def test_KRITIK_kapi_EKSIK_alanda_FAIL_CLOSED_ve_gecerli_sonucta_ACIK():
    from ai_hub.cv_ortak import pemf_kapisi as pk

    # v1 sonucu (pemf_valid / reliable alanı YOK) sürülebilir SAYILMAZ.
    eski = type("V1", (), {"success": True, "warnings": [], "method": "aruco_pnp"})()
    assert pk.degerlendir(eski, model="fantom")["nedenler"] == ["pemf_gecersiz", "guvenilir_degil"]
    assert pk.degerlendir({"success": True}, model="petri")["surulebilir"] is False
    assert pk.degerlendir(_Sonuc(), model="fantom")["surulebilir"] is True
    assert pk.degerlendir(_Sonuc(), model="petri")["surulebilir"] is True
    assert pk.degerlendir(_Sonuc(pemf_valid=False), model="petri")["eylem"] == _EYLEM_PETRI
    with pytest.raises(ValueError):
        pk.degerlendir(_Sonuc(), model="kedi")


def test_ic_ice_uyari_kodu_COZULUR():
    from ai_hub.cv_ortak import pemf_kapisi as pk

    assert pk.uyari_kodlari(["ring_unavailable: ring_partial: halkanin %31'i", "pemf_axis_sign_assumed: x"]) == [
        "ring_unavailable",
        "ring_partial",
        "pemf_axis_sign_assumed",
    ]


# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# 2. SAĞLAYICI — kare LOKALİZE SAYILMAZ, ipucu EYLEMİ söyler
# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("bayrak", ["1", None], ids=["bayrak_ACIK", "bayrak_KAPALI"])
@pytest.mark.parametrize("model,boz,neden", DURUMLAR, ids=_IDS)
def test_KRITIK_saglayici_GECERSIZ_sonucu_LOKALIZE_saymaz(sag, monkeypatch, bayrak, model, boz, neden):
    hedef, fantom, petri, ong = sag
    if bayrak:
        monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", bayrak)
    else:
        monkeypatch.delenv("PEMF_ARASTIRMA_AIPRO", raising=False)
    s = fantom if model == "fantom" else petri
    _Hat.kuyruk = [_Sonuc(**boz)]
    lz, x, y, z, guven, _ov, ozne, dokum = s.localize(np.zeros((8, 8, 3), np.uint8), 0)
    assert lz is False and (x, y, z, guven) == (0.0, 0.0, 0.0, 0.0) and dokum is None
    assert ozne is True, "özne kadrajda — sorun açı / konum / kalite; 'özne yok' ipucu yanlış yönlendirir"
    meta = s.son_lokalizasyon_meta()
    assert meta["pemf_kapisi"]["surulebilir"] is False and neden in meta["pemf_kapisi"]["nedenler"]
    assert s.ipucu(True, "Hedef") == meta["pemf_kapisi"]["eylem"]
    assert ong.cagri == [], "kapı geçmeyen karede doz modeli çağrıldı"


def test_KARSIT_saglayici_GECERLI_sonucu_lokalize_eder(sag):
    hedef, fantom, petri, ong = sag
    for s in (fantom, petri):
        _Hat.kuyruk = [_Sonuc()]
        assert s.localize(np.zeros((8, 8, 3), np.uint8), 0)[0] is True


# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# 3. GERÇEK SEANS DÖNGÜSÜ — `_predict_and_drive` ÇAĞRILMAZ, bobin SÜRÜLMEZ (bayrak açık / kapalı)
# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════


class _Cv2:
    INTER_AREA, IMWRITE_JPEG_QUALITY = 3, 1

    class _Cap:
        def isOpened(self):  # noqa: N802
            return True

        def read(self):
            return True, np.zeros((8, 8, 3), np.uint8)

        def release(self):
            return None

    def VideoCapture(self, *a, **k):  # noqa: N802
        return self._Cap()

    def imencode(self, *a, **k):
        return True, bytearray(b"jpeg")

    def resize(self, img, *a, **k):
        return img


class _Saat:
    def __init__(self, air, tur):
        import time as _t

        self._t, self._air, self.kalan = _t, air, tur

    def __getattr__(self, ad):
        return getattr(self._t, ad)

    def time(self):
        return 1_800_000_000.0

    def sleep(self, _sn):
        self.kalan -= 1
        if self.kalan <= 0:
            self._air._ai_loop_active = False


@pytest.fixture()
def dongu(sag, monkeypatch):
    import servers.ai_router as air
    import servers.api_server as apis

    snap = (dict(air._ai_organ_cache), air._ai_organ_id, air._ai_hedef_modeli)
    with apis._session_lock:
        sess = dict(apis._active_session)
    iz = {"tahmin": [], "surus": []}
    monkeypatch.setattr(air, "cv2", _Cv2())
    monkeypatch.setattr(
        air, "_predict_and_drive", lambda *a, **k: iz["tahmin"].append(a) or ([0.5] * 7, [0.0] * 7, 1.0)
    )
    monkeypatch.setattr(air, "_drive_coils_ai_pro", lambda D, P: iz["surus"].append(D))
    monkeypatch.setattr(apis, "_stop_session_coils", lambda c=None: None)
    monkeypatch.setattr(apis, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(apis, "update_live_session_state", lambda *a, **k: None)
    monkeypatch.setattr(apis, "_mqtt_publish", lambda *a, **k: True)
    monkeypatch.setattr(apis, "state", None)
    monkeypatch.setattr(air, "_ai_started_at", 0.0)
    monkeypatch.setattr(air, "_ai_relocalize", True)
    monkeypatch.setattr(air, "_ai_organ_id", 0)
    air._ai_organ_cache.update({"at": 0.0, "organ_id": -1, "localized": False, "guven_dokumu": None})
    with apis._session_lock:
        apis._active_session.clear()
        apis._active_session.update({"is_active": True, "session_id": "ai_1", "mode": "AI Pro · Fantom Tümör"})

    def kos(model, sonuc, tur=2):
        monkeypatch.setattr(air, "_ai_hedef_modeli", model)
        _Hat.kuyruk = [sonuc]
        saat = _Saat(air, tur)
        monkeypatch.setattr(air, "time", saat)
        air._ai_loop_active = True
        air._ai_pro_loop()
        assert saat.kalan <= 0, "döngü dönmedi — kapı bir şey ölçmedi"

    yield air, iz, kos
    air._ai_loop_active = False
    air._ai_organ_cache.clear()
    air._ai_organ_cache.update(snap[0])
    air._ai_organ_id, air._ai_hedef_modeli = snap[1], snap[2]
    with apis._session_lock:
        apis._active_session.clear()
        apis._active_session.update(sess)


@pytest.mark.parametrize("bayrak", ["1", None], ids=["bayrak_ACIK", "bayrak_KAPALI"])
@pytest.mark.parametrize("model,boz,neden", DURUMLAR, ids=_IDS)
def test_KRITIK_seans_dongusu_GECERSIZ_sonucla_TAHMIN_ve_SURUS_YOK(dongu, monkeypatch, bayrak, model, boz, neden):
    air, iz, kos = dongu
    if bayrak:
        monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", bayrak)
    else:
        monkeypatch.delenv("PEMF_ARASTIRMA_AIPRO", raising=False)
    kos(model, _Sonuc(**boz))
    assert iz["tahmin"] == [] and iz["surus"] == [], f"{neden}: _predict_and_drive / bobin çağrıldı ({iz})"
    assert air._ai_organ_cache["localized"] is False


def test_KARSIT_seans_dongusu_GECERLI_sonucla_TAHMIN_cagrilir(dongu, monkeypatch):
    """Kapı "her zaman reddet"e dönüşmedi: geçerli ArUco sonucunda döngü tahmin ister (bayrak açık)."""
    air, iz, kos = dongu
    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", "1")
    kos("fantom", _Sonuc())
    assert iz["tahmin"], "geçerli sonuçta tahmin çağrılmadı — düzenek kör"


# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# 4. /propose — taze hedef yok → 409 + EYLEM (bayrak açık); bayrak kapalıyken bayrak reddi
# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("bayrak", ["1", None], ids=["bayrak_ACIK", "bayrak_KAPALI"])
def test_KRITIK_propose_GECERSIZ_petri_karesinde_409(sag, monkeypatch, bayrak):
    import servers.ai_router as air
    import servers.api_server as apis
    from fastapi.testclient import TestClient

    hedef, fantom, petri, ong = sag
    if bayrak:
        monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", bayrak)
    else:
        monkeypatch.delenv("PEMF_ARASTIRMA_AIPRO", raising=False)
    tahmin = []
    monkeypatch.setattr(air, "_predict_and_drive", lambda *a, **k: tahmin.append(a) or ([0.3] * 7, [0.0] * 7, 0.5))
    monkeypatch.setattr(air, "_ai_hedef_modeli", "petri")
    snap = dict(air._ai_organ_cache)
    try:
        _Hat.kuyruk = [_Sonuc(pemf_valid=False)]
        lz, x, y, z, rel, ov, ozne, *ek = air._localize_organ(np.zeros((8, 8, 3), np.uint8), 0)  # hazırlık turu
        with air._ai_cache_lock:
            air._ai_organ_cache.update(
                {
                    "x_mm": x,
                    "y_mm": y,
                    "z_mm": z,
                    "reliability": rel,
                    "localized": lz,
                    "at": time.time(),
                    "organ_id": 0,
                    "kedi_var": ozne,
                    "model": "petri",
                    **air._saglayici_cache_alanlari(),
                }
            )
        r = TestClient(apis.app).post(
            "/api/ai/pro/propose", json={"organ_id": 0, "duration_minutes": 5, "model": "petri"}
        )
        assert r.status_code == 409, r.text[:300]
        if bayrak:
            assert _EYLEM_PETRI in r.json()["detail"], r.json()["detail"]
        else:
            assert "tezgâh" in r.json()["detail"].lower()
        assert tahmin == [], "geçersiz karede öneri dozu hesaplandı"
    finally:
        air._ai_organ_cache.clear()
        air._ai_organ_cache.update(snap)


def test_KRITIK_petri_24_kuyucugun_HEPSI_hedef_secilebilir(sag):
    """v2 plaka kipi 24 (96'lık plakada 96) kuyucuk verir; eski 8'lik tavan kuyu 9–24'ü `/propose` / `/start` / organ /
    hazırlık doğrulamasında 422 ile REDDEDERDİ. Fantomun tavanı değişmez (5 tümör + eski fantom)."""
    hedef, fantom, petri, ong = sag
    assert set(range(0, 25)) <= petri.hedef_idleri() and 96 in petri.hedef_idleri()
    assert fantom.hedef_idleri() == frozenset(range(0, 9))
