# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""T3 · Y189 (sahip + Çağlar Hoca, 2026-10-23) — petri / fantom KOŞULSUZ kip + petri / fantom analizine KABİN KAMERASINDAN tek kare.

İSTEK (sahip): "petri analizinde koyduğun koşulları kaldır, modelin sade kendisine bırakalım … analizi hatayla kesiyor; bunu bir
butona bağla, koşullu / koşulsuz, kodda if-else" · Çağlar Hoca: "engelleri tamamen kaldırdığın bir sürüm, butonla kontrol
edilebilir; AI tek başına ne bulacak" · sahip: "AI Pro da sürebilsin" · "kamera seçilebilir olmalı, petri analizinde laptop
kamerasına attı".

ÖLÇÜLEN (önce, HEAD 78d6a0ad):
  * petri v2 hattı iki noktada analizi KESER: plaka ızgarası kurulamazsa `plate_not_found`, makullik reddi `not_a_petri_plate`
    (uç 422) — gerçek ağırlıklı kapı: fantom fotoğrafı petri ucunda 422;
  * PEMF tüketim kapısı engelleyici / yeniden-çekim / güvenilmez nedenlerinde sonucu "bobine esas alınmaz" sayar; AI Pro
    sağlayıcısı kareyi LOKALİZE SAYMAZ; ArUco dışı yöntemde tavan 0,25 < `MIN_GUVEN` 0,3;
  * petri analizinin kamerası tarayıcının / WebView'in VARSAYILAN kamerası — Ayarlar ▸ Kabin kamerası seçimi yalnız AI Pro'da.
KAPI (bu dosya): koşulsuz kipte bu engeller UYARIYA döner (listede görünür kalır), kalan koşullar fiziksel (sonuç var, konum KABİN
çerçevesinde, kabin içi / sonlu hedef); varsayılan KOŞULLU davranış AYNI (karşıt kollar); kip AI Pro'da öneri MÜHRÜNE yazılır ve
`/start` mühürden okur; kabin kamerası ucu seçili kameradan 1920×1080 tek kare verir (meşgulde / seçimsizde 409, okunamazsa 503).
"""

from __future__ import annotations

import base64
import time

import numpy as np
import pytest
from test_ai_hub_fantom_petri_v2v3_YANIT_ve_PARITE_AI2_C3 import FANTOM, _b64, gomulu, onbellek, servis  # noqa: F401
from test_ai_pro_arastirma_PEMF_KAPISI_fail_closed_AI2_C4 import _IDS, DURUMLAR, _Hat, _Sonuc, sag  # noqa: F401
from test_em_ongorucu_SONLU_OLMAYAN_girdi_PIKSEL_kipi_ve_TOPLAM_sure import (  # noqa: F401
    _KayitciDoz,
    _renkli_kare,
    petri_hatti,
)
from test_T2D2_kabin_kamerasi_SECIMI_ve_1080p import _SahteCv2, veri  # noqa: F401

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# 1. PEMF KAPISI (tek kaynak)
# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("model,boz,neden", DURUMLAR, ids=_IDS)
def test_KRITIK_kosulsuz_kapi_yalniz_FIZIKSEL_nedenle_keser_digerleri_GORUNUR_uyari(model, boz, neden):
    from ai_hub.cv_ortak import pemf_kapisi as pk

    k0 = pk.degerlendir(_Sonuc(**boz), model=model)
    assert k0["surulebilir"] is False and k0["kosulsuz"] is False and k0["atlanan"] == [], k0  # KARŞIT: koşullu AYNI
    k = pk.degerlendir(_Sonuc(**boz), model=model, kosulsuz=True)
    assert k["kosulsuz"] is True and neden in k["nedenler"], k
    assert any(m["kod"] == neden for m in k["mesajlar"]), "atlanan neden ekranda GÖRÜNMELİ (uyarı)"
    if neden == "pemf_gecersiz":
        assert k["surulebilir"] is False and neden not in k["atlanan"], "kabin konumu yokken koşulsuz da SÜRMEZ"
    else:
        assert k["surulebilir"] is True and neden in k["atlanan"], k


def test_KRITIK_kosulsuz_YALNIZ_gercek_True_ile_acilir_Form_varsayilani_ACMAZ():
    """Ölçüldü (ilgili küme, GPU servisi Y144 paritesi): uç DOĞRUDAN çağrılınca `kosulsuz: bool = Form(False)` parametresi bool değil
    FastAPI `FieldInfo`'su alır ve o nesne "doğru" sayılır → varsayılan KOŞULSUZA düşüyordu (sürülemez sonuç sürülebilir)."""
    from fastapi import Form

    from ai_hub.cv_ortak import pemf_kapisi as pk

    alan = Form(False)
    assert bool(alan) is True, "aparat: FieldInfo truthy olmalı (aksi hâlde kapı boş ölçer)"
    k = pk.degerlendir(_Sonuc(warnings=["low_resolution: x"]), model="petri", kosulsuz=alan)
    assert k["kosulsuz"] is False and k["surulebilir"] is False, k
    d = pk.yanit_alanlari(_Sonuc(warnings=["low_resolution: x"]), model="petri", kosulsuz=alan)
    assert d["kosulsuz"] is False and d["pemf_kapisi"]["surulebilir"] is False


def test_kosulsuz_kapi_BASARISIZ_sonucu_surmez_ve_yanit_alanlari_isaretler():
    from ai_hub.cv_ortak import pemf_kapisi as pk

    k = pk.degerlendir(_Sonuc(success=False, error="plate_not_found"), model="petri", kosulsuz=True)
    assert k["surulebilir"] is False and "basarisiz" in k["nedenler"] and "basarisiz" not in k["atlanan"]
    d = pk.yanit_alanlari(_Sonuc(warnings=["low_resolution: x"]), model="petri", kosulsuz=True)
    assert d["kosulsuz"] is True and d["pemf_kapisi"]["surulebilir"] is True
    d0 = pk.yanit_alanlari(_Sonuc(warnings=["low_resolution: x"]), model="petri")
    assert d0["kosulsuz"] is False and d0["pemf_kapisi"]["surulebilir"] is False


# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# 2. AI PRO SAĞLAYICISI
# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════

_ATLANABILIR = [d for d in DURUMLAR if d[2] != "pemf_gecersiz"]


@pytest.mark.parametrize("model,boz,neden", _ATLANABILIR, ids=[f"{m}-{n}" for m, _, n in _ATLANABILIR])
def test_KRITIK_saglayici_KOSULSUZ_kipte_LOKALIZE_sayar_KOSULLUDA_saymaz(sag, model, boz, neden):
    hedef, fantom, petri, _ong = sag
    s = fantom if model == "fantom" else petri
    _Hat.kuyruk = [_Sonuc(**boz)]
    assert hedef.kosulsuz_ayarla(s, True) is True
    lz, x, y, z, _g, _ov, ozne, dokum = s.localize(np.zeros((8, 8, 3), np.uint8), 0)
    assert lz is True and (x, y, z) == (-40.0, 0.0, 0.0) and dokum["kosulsuz"] is True, (lz, dokum)
    assert hedef.kosulsuz_ayarla(s, False) is False
    lz2, *_ = s.localize(np.zeros((8, 8, 3), np.uint8), 0)
    assert lz2 is False, "KARŞIT: koşullu kipte aynı kare lokalize SAYILMAZ"


def test_KRITIK_saglayici_KOSULSUZ_yontem_tavanini_ve_esigi_ATLAR_konum_YOKSA_atlamaz(sag):
    hedef, _fantom, petri, _ong = sag
    _Hat.kuyruk = [_Sonuc(method="plate_grid", coord_frame="cabin_placement")]  # tavan 0,25 → güven 0,2 < 0,3
    lz0, *_ = petri.localize(np.zeros((8, 8, 3), np.uint8), 0)
    assert lz0 is False, "KARŞIT: koşulluda ArUco dışı yöntem sürülmez (karar #4)"
    hedef.kosulsuz_ayarla(petri, True)
    lz, _x, _y, _z, guven, *_ = petri.localize(np.zeros((8, 8, 3), np.uint8), 0)
    assert lz is True and guven < hedef.MIN_GUVEN
    _Hat.kuyruk = [_Sonuc(pemf_valid=False)]
    lz2, *_ = petri.localize(np.zeros((8, 8, 3), np.uint8), 0)
    assert lz2 is False, "kabin çerçevesinde konum yokken koşulsuz da lokalize sayılmaz"


def test_kosulsuz_ayarla_KEDIDE_yok_sayilir_ve_petri_hattina_GECER(sag, monkeypatch):
    hedef, _fantom, petri, _ong = sag
    kedi = hedef.saglayici_al("kedi")
    assert hedef.kosulsuz_ayarla(kedi, True) is False and not getattr(kedi, "kosulsuz", False)
    gelen = {}

    class _Yakala(_Hat):
        def __init__(self, cfg, **kw):
            gelen.update(kw)
            super().__init__(cfg, **kw)

    import servers.ai_router as air

    monkeypatch.setattr(
        air,
        "_get_or_load_model",
        lambda ad, y: {"cls": _Yakala, "cfg": None, "predictor": None, "yolo": None, "yolo_path": "y"},
    )
    hedef.kosulsuz_ayarla(petri, True)
    petri._pipeline_kur(air._get_or_load_model("em_petri_cv", None))
    assert gelen.get("kosulsuz") is True, gelen


# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# 3. PETRİ v2 HATTI (GERÇEK `process_image`, sahte YOLO)
# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_petri_hatti_kosulsuz_YALNIZ_gercek_True(petri_hatti):
    from fastapi import Form

    pp, _kos, _Yolo = petri_hatti
    assert pp.PetriCvPipeline(None, yolo_device="cpu", kosulsuz=Form(False)).kosulsuz is False
    assert pp.PetriCvPipeline(None, yolo_device="cpu", kosulsuz=True).kosulsuz is True


def _petri_kos(pp, yolo_sinifi, plate_type, kosulsuz):
    hat = pp.PetriCvPipeline(None, yolo_device="cpu", plate_type=plate_type, kosulsuz=kosulsuz)
    hat.yolo = yolo_sinifi()
    hat._predictor = _KayitciDoz()
    return hat.process_image(_renkli_kare())[0]


def test_KRITIK_petri_hatti_MAKULLIK_reddi_KOSULSUZDA_analizi_kesmez(petri_hatti, monkeypatch):
    pp, _kos, _Yolo = petri_hatti
    monkeypatch.setattr(pp._plaus, "evaluate", lambda *a, **k: (False, {"message": "olcum"}))
    r0 = _petri_kos(pp, _Yolo, 0, False)
    assert r0.success is False and r0.error == pp._plaus.PETRI_REJECT and r0.kosulsuz is False  # KARŞIT
    r1 = _petri_kos(pp, _Yolo, 0, True)
    assert r1.success is True and r1.kosulsuz is True and r1.n_wells == 1, (r1.error, r1.warnings)
    assert any(w.startswith("kosulsuz_makullik:") for w in r1.warnings), r1.warnings
    assert r1.to_dict()["kosulsuz"] is True


def test_KRITIK_petri_hatti_PLAKA_bulunamazsa_KOSULSUZDA_ham_YOLO_tespiti(petri_hatti, monkeypatch):
    pp, _kos, _Yolo = petri_hatti
    from ai_hub.inference_petri_dish.petri_cv_v2.plate_grid import PlateGridResult

    monkeypatch.setattr(pp, "detect_plate_wells", lambda *a, **k: PlateGridResult(False, error="plate_not_found"))
    r0 = _petri_kos(pp, _Yolo, 24, False)
    assert r0.success is False and r0.error == "plate_not_found"  # KARŞIT
    r1 = _petri_kos(pp, _Yolo, 24, True)
    assert r1.success is True and r1.n_wells == 1 and r1.wells[0].source == "yolo", (r1.error, r1.warnings)
    assert any(w.startswith("kosulsuz_plaka_yok: plate_not_found") for w in r1.warnings), r1.warnings


# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# 4. AI HUB UÇLARI — GERÇEK AĞIRLIKLAR (golden; yoksa atlanır) + GPU servisi paritesi
# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_petri_ucu_FANTOM_fotografi_KOSULLU_422_KOSULSUZ_sonuc_doner(gomulu):
    r0 = gomulu.post("/api/ai/vision/em_petri", data={"image_base64": _b64(FANTOM)})
    assert r0.status_code == 422, r0.text[:200]  # KARŞIT: bugünkü davranış
    r = gomulu.post("/api/ai/vision/em_petri", data={"image_base64": _b64(FANTOM), "kosulsuz": "true"})
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert j["kosulsuz"] is True and j["pemf_kapisi"]["kosulsuz"] is True
    assert any(str(w).startswith(("kosulsuz_makullik", "kosulsuz_plaka_yok")) for w in j["warnings"]), j["warnings"]


def test_KRITIK_fantom_ucu_KOSULSUZ_isareti_ve_GPU_servisi_AYNI_kapi(gomulu, servis):
    a = gomulu.post("/api/ai/vision/em_fantom", data={"image_base64": _b64(FANTOM), "kosulsuz": "true"}).json()
    b = servis.post(
        "/infer/em_fantom", files={"file": ("x.jpg", FANTOM.read_bytes(), "image/jpeg")}, data={"kosulsuz": "true"}
    ).json()
    assert a["kosulsuz"] is True and b["kosulsuz"] is True
    assert a["pemf_kapisi"] == b["pemf_kapisi"], "gömülü ve GPU servisi farklı kapı kararı verdi"
    p = servis.post(
        "/infer/em_petri", files={"file": ("x.jpg", FANTOM.read_bytes(), "image/jpeg")}, data={"kosulsuz": "true"}
    ).json()
    assert p.get("kosulsuz") is True and p.get("error") != "not_a_petri_plate", str(p)[:300]


# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# 5. KABİN KAMERASI — tek kare (en alt kat sahte cv2) + uç
# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_kare_al_SECILI_kameradan_1080p_ve_HER_durumda_birakir(veri):
    kk, _ = veri
    cv = _SahteCv2()
    with pytest.raises(kk.KameraSecilmedi):
        kk.kare_al(cv)
    assert cv.acilan == [], "seçim yokken kamera açıldı"
    kk.kamera_sec(1)
    k = kk.kare_al(cv)
    cap = cv.capler[-1]
    assert cv.acilan == [1] and cap.sira[:2] == [("set", 3, 1920.0), ("set", 4, 1080.0)], cap.sira
    assert (k["indeks"], k["genislik"], k["yukseklik"]) == (1, 1920, 1080) and base64.b64decode(k["image_base64"])
    assert cap.sira[-1] == ("release",) and cap.sira.count(("read",)) == kk.KARE_ISINMA + 1
    cv2 = _SahteCv2(acik=())
    kk.kamera_sec(0)
    assert kk.kare_al(cv2) is None and cv2.capler[-1].sira[-1] == ("release",)


@pytest.fixture()
def istemci():
    from fastapi.testclient import TestClient
    from servers import api_server

    return TestClient(api_server.app)


def test_KRITIK_kare_ucu_mesgulde_409_secimsizde_409_okunamazsa_503_basarida_kare(istemci, monkeypatch):
    from servers import settings_router as sr
    from utils import kabin_kamerasi as kk

    monkeypatch.setattr(sr, "_ai_kamerasi_mesgul", lambda: True)
    r = istemci.post("/api/settings/kabin-kamerasi/kare")
    assert r.status_code == 409 and "AI Pro" in r.json()["detail"], r.text[:200]
    monkeypatch.setattr(sr, "_ai_kamerasi_mesgul", lambda: False)

    def _secilmedi(*a, **k):
        raise kk.KameraSecilmedi()

    monkeypatch.setattr(kk, "kare_al", _secilmedi)
    r = istemci.post("/api/settings/kabin-kamerasi/kare")
    assert r.status_code == 409 and "Kabin kamerası" in r.json()["detail"], r.text[:200]
    monkeypatch.setattr(kk, "kare_al", lambda *a, **k: None)
    monkeypatch.setattr(kk, "secili_kamera", lambda: {"indeks": 1, "kaynak": "ayar"})
    r = istemci.post("/api/settings/kabin-kamerasi/kare")
    assert r.status_code == 503 and "(kamera 1)" in r.json()["detail"], r.text[:200]
    monkeypatch.setattr(
        kk, "kare_al", lambda *a, **k: {"indeks": 1, "genislik": 1920, "yukseklik": 1080, "image_base64": "QQ=="}
    )
    r = istemci.post("/api/settings/kabin-kamerasi/kare")
    assert r.status_code == 200 and r.json()["genislik"] == 1920 and r.json()["image_base64"] == "QQ=="


# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# 6. AI PRO — öneri mührü + /start mühürden + durdurma
# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════


@pytest.fixture()
def aipro(istemci, monkeypatch):
    from servers import ai_approval as ap
    from servers import ai_pro_hedef as hedef
    from servers import ai_router as air

    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", "1")
    monkeypatch.setattr(air, "_ai_pro_loop", lambda *a, **k: None)
    monkeypatch.setattr(air, "_predict_and_drive", lambda x, y, z, o: ([0.3] * 7, [0.0] * 7, 0.5))
    monkeypatch.setattr(hedef.PetriSaglayici, "xai_sensitivity", lambda self, *a: {})
    ap.clear()
    istemci.post("/api/ai/pro/stop")
    yield istemci, air, ap
    istemci.post("/api/ai/pro/stop")
    ap.clear()


def _taze(air, monkeypatch, kosulsuz):
    monkeypatch.setattr(
        air,
        "_ai_organ_cache",
        {
            "localized": True,
            "organ_id": 3,
            "model": "petri",
            "at": time.time(),
            "x_mm": -40.0,
            "y_mm": 0.0,
            "z_mm": 0.0,
            "reliability": 0.2,
            "kosulsuz": kosulsuz,
            "secili_id": None,
            "target_label": "A3",
        },
    )


def test_KRITIK_oneri_KIP_uyusmazsa_409_uyusursa_MUHURE_yazar(aipro, monkeypatch):
    istemci, air, _ap = aipro
    _taze(air, monkeypatch, True)
    r = istemci.post("/api/ai/pro/propose", json={"organ_id": 3, "model": "petri", "kosulsuz": False})
    assert r.status_code == 409 and "Koşullu / Koşulsuz" in r.json()["detail"], r.text[:200]
    r = istemci.post("/api/ai/pro/propose", json={"organ_id": 3, "model": "petri", "kosulsuz": True})
    assert r.status_code == 200 and r.json()["specs"].get("kosulsuz") is True, r.text[:300]
    _taze(air, monkeypatch, False)
    r = istemci.post("/api/ai/pro/propose", json={"organ_id": 3, "model": "petri"})
    assert r.status_code == 200 and "kosulsuz" not in r.json()["specs"], "KARŞIT: koşullu mühür ESKİ biçim"


def test_KRITIK_start_KIPI_MUHURDEN_okur_govdeyi_yok_sayar_stop_sifirlar(aipro):
    istemci, _air, ap = aipro
    rec = ap.create("ai_pro", {"organ_id": 2, "duration_minutes": 5, "model": "petri", "kosulsuz": True})
    istemci.post("/api/ai/pro/approve", json={"proposal_id": rec["id"], "operator_email": "dr@k.com"})
    r = istemci.post("/api/ai/pro/start", json={"proposal_id": rec["id"], "kosulsuz": False})
    assert r.status_code == 200, r.text[:300]
    st = istemci.get("/api/ai/pro/status").json()
    assert st["model"] == "petri" and st["kosulsuz"] is True, st
    istemci.post("/api/ai/pro/stop")
    assert istemci.get("/api/ai/pro/status").json()["kosulsuz"] is False
    rec2 = ap.create("ai_pro", {"organ_id": 2, "duration_minutes": 5, "model": "petri"})
    istemci.post("/api/ai/pro/approve", json={"proposal_id": rec2["id"], "operator_email": "dr@k.com"})
    assert istemci.post("/api/ai/pro/start", json={"proposal_id": rec2["id"], "kosulsuz": True}).status_code == 200
    assert istemci.get("/api/ai/pro/status").json()["kosulsuz"] is False, "gövdedeki kip mührü EZDİ"
