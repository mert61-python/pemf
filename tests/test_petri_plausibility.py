# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Petri MAKULLİK denetimi — yanlış modülün fotoğrafına sessizce sonuç üretilmesini engeller.

SAHİP BİLDİRİMİ (2026-08-06): `05_FantomTumor.jpeg` Petri Kuyu ucuna verilince boru hattı
itirazsız `success=True, n_wells=2, n_cancer=1` döndürüyor, iki SAHTE kuyucuk için
PetriPredictor'ı çalıştırıp E_cancer/D/P üretiyordu. `apps/backend/utils/image_domain.py` bunu yakalayamaz
(ölçüldü: petri achromatic=0.391, fantom 0.179 → İKİSİ DE `color`).

İki katman test edilir:
  (a) SAF BİRİM — sentetik konturla, MODEL YÜKLEMEDEN kuralı kilitler (hızlı, CI-dostu).
  (b) ENTEGRASYON — gerçek test girdileriyle çapraz yükleme (yalnız YOLO ONNX varsa).
"""

import os
from pathlib import Path

import capraz
import cv2
import numpy as np
import pytest

from ai_hub.inference_petri_dish import plausibility as pl

KOK = Path(__file__).resolve().parent.parent
GIRDI = KOK / "ai_hub" / "PEMF_AI_Test_Girdileri"

PETRI = GIRDI / "06_PetriKuyu.jpg"
PETRI_ARUCO = GIRDI / "06b_PetriKuyu_aruco.jpg"
FANTOM = GIRDI / "05_FantomTumor.jpeg"
KEDI_SEG = GIRDI / "02_Segmentasyon_kedi.jpeg"
CT_KIST = GIRDI / "07b_BobrekCT_kist.jpg"
CT_NORMAL = GIRDI / "07c_BobrekCT_normal.jpg"
CT_TAS = GIRDI / "07a_BobrekCT_tas.jpg"


# ══════════════════════════════════════════════════════════════════════════════
# (a) SAF BİRİM — sentetik kontur, model yok
# ══════════════════════════════════════════════════════════════════════════════
def _kontur(maske: np.ndarray) -> np.ndarray:
    cnts, _ = cv2.findContours(maske, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    assert cnts, "sentetik maskeden kontur çıkmadı"
    return max(cnts, key=cv2.contourArea)


def _daire(r: int = 40, boy: int = 640) -> np.ndarray:
    m = np.zeros((boy, boy), np.uint8)
    cv2.circle(m, (boy // 2, boy // 2), r, 255, -1)
    return _kontur(m)


def _elips(a: int = 180, b: int = 25, boy: int = 640) -> np.ndarray:
    """Uzun/düzensiz leke — ölçülen fantom "kuyucuk"larının imzası (dairesellik 0.34)."""
    m = np.zeros((boy, boy), np.uint8)
    cv2.ellipse(m, (boy // 2, boy // 2), (a, b), 0, 0, 360, 255, -1)
    return _kontur(m)


def _dev_blob(boy: int = 640) -> np.ndarray:
    """Karenin ~%28'ini kaplayan büyük leke — ölçülen sahte girdilerin imzası (0.262-0.545).
    Gerçek petri kuyucuğu bu kadar yer kaplamaz (ölçülen en yüksek 0.166)."""
    m = np.zeros((boy, boy), np.uint8)
    cv2.ellipse(m, (boy // 2, boy // 2), (330, 110), 0, 0, 360, 255, -1)
    return _kontur(m)


def test_dairesellik_olcusu_dogru():
    assert pl.circularity(_daire()) > 0.85  # disk ≈ 1 (diskretizasyon payı)
    assert pl.circularity(_elips()) < 0.40  # uzun leke belirgin düşük
    assert pl.circularity(np.zeros((0, 1, 2), np.int32)) == 0.0  # bozuk girdi çökertmez


def test_gercek_petri_imzasi_KABUL_edilir():
    """8 küçük, yuvarlak, yüksek-güvenli disk = ölçülen gerçek petri imzası."""
    cnts = [_daire(40) for _ in range(8)]
    ok, m = pl.evaluate(cnts, [0.92] * 8, 640.0 * 640.0)
    assert ok, m
    assert m["votes"] == 3, m


def test_fantom_imzasi_REDDEDILIR():
    """Ölçülen fantom imzası: 2 tespit, dairesellik ~0.34, conf ~0.69, kareyi %51 kaplıyor."""
    ok, m = pl.evaluate([_elips(), _dev_blob()], [0.66, 0.72], 640.0 * 640.0)
    assert not ok, m
    assert m["votes"] == 0, m
    assert "message" in m and "petri" in m["message"].lower()


def test_TEK_sinyal_TEK_BASINA_reddettirmez():
    """MUHAFAZAKÂRLIK SÖZLEŞMESİ: kararsızsa GEÇİR. Meşru bir araştırma görüntüsünde tek bir
    sinyal (ör. bulanık fotoğrafta düşen conf) bozulduğunda analiz engellenmemeli."""
    cnts = [_daire(40) for _ in range(6)]
    ok, m = pl.evaluate(cnts, [0.50] * 6, 640.0 * 640.0)  # conf DÜŞÜK, diğer ikisi sağlam
    assert ok, m
    assert m["votes"] == 2, m


def test_iki_sinyal_bozulunca_reddeder():
    ok, m = pl.evaluate([_elips()], [0.50], 640.0 * 640.0)  # dairesellik + conf düştü
    assert not ok, m


def test_ALAN_sinyali_VETO_dur():
    """DENETİM 2026-08-06 (REGRESYON KİLİDİ): böbrek CT kesitinin ÖLÇÜLEN imzası — YUVARLAK
    (circ 0.79) ve YOLO ondan EMİN (conf 0.90), yani iki oyu da KAZANIYOR; ayıran tek sinyal
    kareyi %35 kaplaması. Saf 2-of-3 oyla 07b/07c CT'leri em_petri ucundan HTTP 200 +
    n_wells=1 ile geçiyordu. Alan sinyali VETO olmazsa bu test düşer."""
    r = 640 // 2 - 20  # kareyi ~%68 kaplayan tek büyük disk
    ok, m = pl.evaluate([_daire(r)], [0.90], 640.0 * 640.0)
    assert m["circularity_med"] >= 0.55, m  # dairesellik oyu GEÇİYOR
    assert m["conf_med"] >= 0.85, m  # güven oyu GEÇİYOR
    assert m["votes"] == 2, m  # yani 2-of-3 saf oyla KABUL edilirdi
    assert m["area_ok"] is False, m
    assert not ok, "alan VETO'su çalışmadı — tek dev tespit petri kuyucuğu sayıldı"


def test_veto_MESRU_kucuk_kuyucuklari_ETKILEMEZ():
    """Yanlış-pozitif kontrolü: gerçek petri imzasında (küçük kuyucuklar) veto hiç tetiklenmez."""
    ok, m = pl.evaluate([_daire(40) for _ in range(8)], [0.92] * 8, 640.0 * 640.0)
    assert ok and m["area_ok"] is True, m


def test_kacis_kapagi_env_ile_kapatilir(monkeypatch):
    monkeypatch.setenv("PEMF_AI_PLAUSIBILITY_GUARD", "0")
    ok, m = pl.evaluate([_elips(), _dev_blob()], [0.66, 0.72], 640.0 * 640.0)
    assert ok, "kaçış kapağı açıkken analiz bloklanmamalı"
    assert m.get("guard") == "off"


def test_varsayilan_ACIK(monkeypatch):
    monkeypatch.delenv("PEMF_AI_PLAUSIBILITY_GUARD", raising=False)
    assert pl.guard_enabled() is True


def test_bozuk_girdi_FAIL_OPEN():
    """Denetim ÖLÇEMEZSE meşru analizi ASLA engellememeli (tıbbi cihazda kilit > koruma zararı).

    Somut senaryo: detector bir gün kontur formatını değiştirirse her ölçüm 0'a düşer; fail-open
    olmasa denetim TÜM petri fotoğraflarını reddetmeye başlar ve modül sessizce kullanılamaz olur.
    """
    ok, m = pl.evaluate(["kontur-degil"], ["conf-degil"], 0.0)
    assert ok is True
    assert m["measurable"] is False
    ok2, m2 = pl.evaluate([_elips()], [], 640.0 * 640.0)  # conf listesi boş → karar verme
    assert ok2 is True and m2["measurable"] is False


def test_tel_sozlesmesi_ai_router_ile_ESLESIYOR():
    """`not_a_petri_plate` iki tarafta ayrı yazılı (ai_router ağır ai_hub import'u yapmasın diye).
    Sessizce ayrışırsa mikroservis yolunda 422 çevirimi ÇALIŞMAZ → burada kilitleniyor."""
    from servers import ai_router

    assert ai_router._PETRI_NOT_PLATE == pl.PETRI_REJECT


# ══════════════════════════════════════════════════════════════════════════════
# (b) ENTEGRASYON — GERÇEK test girdileri + gerçek YOLO (model yoksa atlanır)
# ══════════════════════════════════════════════════════════════════════════════
def _yolo_yolu():
    # AI-2 C6: gerçek ağırlık dizini (PEMF_AI_MODELS_DIR — kurulu düzen / koşucu) da aranır; yoksa eskisi gibi atlanır.
    _md = os.environ.get("PEMF_AI_MODELS_DIR")
    if _md and (Path(_md) / "ai_hub" / "inference_petri_dish" / "yolo11m-seg.onnx").exists():
        return Path(_md) / "ai_hub" / "inference_petri_dish" / "yolo11m-seg.onnx"
    for aday in (
        KOK / "release_assets" / "ai_models" / "ai_hub" / "inference_petri_dish" / "yolo11m-seg.onnx",
        KOK / "ai_hub" / "inference_petri_dish" / "yolo11m-seg.onnx",
        KOK / "ai_hub" / "inference_petri_dish" / "yolo11m-seg.pt",
    ):
        if aday.exists():
            return aday
    return None


_MODEL = _yolo_yolu()


@pytest.fixture(scope="module")
def _yolo_ve_petri_girdisi():
    """D5-F (K5-F P4): gerçek YOLO ağırlığı (çözümlenir) ve petri girdisi İZLENMEZ — yoksa atla, `PEMF_CAPRAZ_KAYNAK_ZORUNLU=1`de
    DÜŞ. Eskiden düz `skipif(_MODEL is None or not PETRI.exists())`: zorunlu kipte de sessizce atlıyordu. Modül kapsamlı:
    `usefixtures` adları modül kapsamlı `boru_hatti`dan ÖNCE kurulur (model yokken boru hattı hiç kurulmaz)."""
    if _MODEL is None:
        capraz.atla(
            "YOLO petri modeli (yolo11m-seg) bulunamadı — PEMF_AI_MODELS_DIR / release_assets/ai_models / ai_hub"
        )
    capraz.atla_yoksa("ai_hub/PEMF_AI_Test_Girdileri/06_PetriKuyu.jpg")


entegrasyon = pytest.mark.usefixtures("_yolo_ve_petri_girdisi")


@pytest.fixture(scope="module")
def boru_hatti():
    """AI-2 C6: v1 `petri_cv` emekli → hocanın v2'si TEKİL kap kipinde (`plate_type=0`): bu bölümün denetimi (dairesellik /
    güven / alan) v2'de tekil kipin kuralıdır. Plaka kipi (ürün varsayılanı) `plaka_hatti` ile ayrıca ölçülür."""
    from ai_hub.inference_petri_dish.petri_cv_v2 import PetriCvPipeline, load_cabin_config

    return PetriCvPipeline(load_cabin_config(None), yolo_model_path=_MODEL, yolo_device="cpu", plate_type=0)


@pytest.fixture(scope="module")
def plaka_hatti(boru_hatti):
    """Ürün varsayılanı: hocanın 24 kuyucuklu plaka kipi (YAML `multiwell.plate_type`). Ağır modeller tekil hattan paylaşılır."""
    from ai_hub.inference_petri_dish.petri_cv_v2 import PetriCvPipeline

    h = PetriCvPipeline(boru_hatti.cfg, yolo_model_path=_MODEL, yolo_device="cpu")
    h.yolo, h._predictor = boru_hatti.yolo, boru_hatti._predictor
    return h


@pytest.fixture(params=["tekil", "plaka"])
def iki_kip(request):
    return request.param, request.getfixturevalue("boru_hatti" if request.param == "tekil" else "plaka_hatti")


@entegrasyon
@pytest.mark.parametrize("yol", [PETRI, PETRI_ARUCO])
def test_gercek_petri_GECER(boru_hatti, yol):
    """YANLIŞ-POZİTİF OLMAMALI — meşru görüntüyü bloklamak da bir başarısızlıktır."""
    capraz.atla_yoksa(yol.relative_to(capraz.KOK).as_posix())  # D5-F: eski düz pytest.skip — ZORUNLU kipte DÜŞER
    r, _ = boru_hatti.process_image(cv2.imread(str(yol)))
    assert r.error != pl.PETRI_REJECT, f"gerçek petri reddedildi: {r.plausibility}"
    assert r.success, r.error
    assert r.n_wells > 0


def _reddetti(kip, r):
    """Tekil kip: makullik REDDİ (v1 sözleşmesi). Plaka kipi: plaka bulunamaz ya da ızgara doğrulanamaz — iki yolda da
    kuyucuk YOK (ölçüldü: fantom / kedi / CT → plate_not_found)."""
    if kip == "tekil":
        return r.error == pl.PETRI_REJECT
    return r.error in (pl.PETRI_REJECT, "plate_not_found")


@entegrasyon
@pytest.mark.parametrize("yol", [FANTOM, KEDI_SEG])
def test_capraz_yukleme_REDDEDILIR(iki_kip, yol):
    """ASIL BULGU: fantom/kedi fotoğrafı sessizce 'kuyucuk' üretmemeli — AI-2: iki kipte de."""
    capraz.atla_yoksa(yol.relative_to(capraz.KOK).as_posix())  # D5-F: eski düz pytest.skip — ZORUNLU kipte DÜŞER
    kip, boru_hatti = iki_kip
    r, _ = boru_hatti.process_image(cv2.imread(str(yol)))
    assert _reddetti(kip, r), f"{kip}: reddedilmedi: success={r.success} hata={r.error} {r.plausibility}"
    assert r.success is False
    assert r.wells == [], "reddedilen görüntüde kuyucuk tahmini üretilmemeli"


@entegrasyon
@pytest.mark.parametrize("yol", [CT_KIST, CT_NORMAL, CT_TAS])
def test_bobrek_CT_kesiti_REDDEDILIR(iki_kip, yol):
    """DENETİM 2026-08-06 (ASIL REGRESYON): `apps/backend/utils/image_domain.py` em_petri'ye GRAYSCALE'i
    açtığı gün CT kesitlerini bu uçta tutan modalite katmanı kalktı ve o anki geometri katmanı
    07b/07c'yi GEÇİRİYORDU (HTTP 200, success=True, n_wells=1, PetriPredictor çalıştı).
    Böbrek CT'sinden "petri kuyucuğu" raporlamak, düzeltilmeye çalışılan sessiz-yanlış-sonucun
    kendisidir. İki katman da yerinde olmalı: modalite {COLOR,GRAYSCALE} ise alan VETO'su ŞART."""
    capraz.atla_yoksa(yol.relative_to(capraz.KOK).as_posix())  # D5-F: eski düz pytest.skip — ZORUNLU kipte DÜŞER
    kip, boru_hatti = iki_kip
    r, _ = boru_hatti.process_image(cv2.imread(str(yol)))
    assert _reddetti(kip, r), f"{kip}: CT kabul edildi: success={r.success} {r.plausibility}"
    assert r.success is False and r.wells == []


@entegrasyon
def test_kacis_kapagi_boru_hattinda_da_calisir(boru_hatti, monkeypatch):
    capraz.atla_yoksa("ai_hub/PEMF_AI_Test_Girdileri/05_FantomTumor.jpeg")  # D5-F: eski düz pytest.skip
    monkeypatch.setenv("PEMF_AI_PLAUSIBILITY_GUARD", "0")
    r, _ = boru_hatti.process_image(cv2.imread(str(FANTOM)))
    assert r.error != pl.PETRI_REJECT, "kaçış kapağı açıkken boru hattı yine de reddetti"


# ══════════════════════════════════════════════════════════════════════════════
# (c) UÇ SEVİYESİ — 422 + anlaşılır Türkçe (jenerik 500 "Petri analiz hatası" DEĞİL)
# ══════════════════════════════════════════════════════════════════════════════
@entegrasyon
def test_uc_fantom_fotografina_422_doner():
    from fastapi.testclient import TestClient
    from servers import api_server

    c = TestClient(api_server.app)
    with open(FANTOM, "rb") as f:  # AI-2: tekil kip (v1 sözleşmesi: 422 + neden); plaka kipi aşağıda
        r = c.post(
            "/api/ai/vision/em_petri", files={"file": ("fantom.jpeg", f, "image/jpeg")}, data={"plate_type": "0"}
        )
    assert r.status_code == 422, f"HTTP {r.status_code}: {r.text[:300]}"
    detail = r.json().get("detail", "")
    assert "petri" in detail.lower(), detail
    assert "yanıltıcı" in detail.lower(), detail  # NEDEN reddedildiğini söylemeli
    assert "Petri analiz hatası" not in detail  # jenerik 500'e düşmemeli


@entegrasyon
def test_uc_bobrek_CT_sine_422_doner():
    """UÇ SEVİYESİ regresyon kilidi: ölçülen hâli HTTP 200 + status='success' + n_wells=1 idi."""
    from fastapi.testclient import TestClient
    from servers import api_server

    capraz.atla_yoksa("ai_hub/PEMF_AI_Test_Girdileri/07b_BobrekCT_kist.jpg")  # D5-F: eski düz pytest.skip
    c = TestClient(api_server.app)
    with open(CT_KIST, "rb") as f:
        r = c.post("/api/ai/vision/em_petri", files={"file": ("ct.jpg", f, "image/jpeg")}, data={"plate_type": "0"})
    assert r.status_code == 422, f"HTTP {r.status_code}: {r.text[:300]}"
    assert "petri" in r.json().get("detail", "").lower()


@entegrasyon
def test_uc_gercek_petriyi_KABUL_eder():
    from fastapi.testclient import TestClient
    from servers import api_server

    c = TestClient(api_server.app)
    with open(PETRI, "rb") as f:  # AI-2: 06 tekil kaplar (8) — plaka kipinde 24'lük ızgara doğrulanamaz (aşağıda)
        r = c.post("/api/ai/vision/em_petri", files={"file": ("petri.jpg", f, "image/jpeg")}, data={"plate_type": "0"})
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:300]}"
    assert r.json().get("status") == "success", r.json().get("error")


@entegrasyon
def test_uc_PLAKA_kipinde_fantom_KUYUCUK_URETMEZ_ve_tekil_kap_YONLENDIRILIR():
    """AI-2 (ürün varsayılanı plaka kipi): fantom → plaka yok (200 no_detection, kuyucuk 0); tekil kap fotoğrafı (06) →
    422 + ızgaranın oturmadığını ve çekimi anlatan metin (T3 · Y193: tekil kip arayüzden kalktı → o kipe YÖNLENDİRMEZ). Uydurulmuş kuyucuk YOK."""
    from fastapi.testclient import TestClient
    from servers import api_server

    c = TestClient(api_server.app)
    with open(FANTOM, "rb") as f:
        r = c.post("/api/ai/vision/em_petri", files={"file": ("fantom.jpeg", f, "image/jpeg")})
    assert r.status_code in (200, 422), f"HTTP {r.status_code}: {r.text[:300]}"
    if r.status_code == 200:
        j = r.json()
        assert j.get("status") == "no_detection" and j.get("n_wells") == 0 and j.get("wells") == [], str(j)[:300]
    with open(PETRI, "rb") as f:
        r = c.post("/api/ai/vision/em_petri", files={"file": ("petri.jpg", f, "image/jpeg")})
    assert r.status_code == 422, f"HTTP {r.status_code}: {r.text[:300]}"
    d = r.json().get("detail", "")
    assert "ızgarası oturmadı" in d and "Tekil petri kapları" not in d, d
