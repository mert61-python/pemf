# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Petri MAKULLİK denetimi — yanlış modülün fotoğrafına sessizce sonuç üretilmesini engeller.

SAHİP BİLDİRİMİ (2026-08-06): `05_FantomTumor.jpeg` Petri Kuyu ucuna verilince boru hattı
itirazsız `success=True, n_wells=2, n_cancer=1` döndürüyor, iki SAHTE kuyucuk için
PetriPredictor'ı çalıştırıp E_cancer/D/P üretiyordu. `utils/image_domain.py` bunu yakalayamaz
(ölçüldü: petri achromatic=0.391, fantom 0.179 → İKİSİ DE `color`).

İki katman test edilir:
  (a) SAF BİRİM — sentetik konturla, MODEL YÜKLEMEDEN kuralı kilitler (hızlı, CI-dostu).
  (b) ENTEGRASYON — gerçek test girdileriyle çapraz yükleme (yalnız YOLO ONNX varsa).
"""

import os
from pathlib import Path

import cv2
import numpy as np
import pytest

os.environ.pop("PEMF_SIMULATE", None)

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
    for aday in (
        KOK / "release_assets" / "ai_models" / "ai_hub" / "inference_petri_dish" / "yolo11m-seg.onnx",
        KOK / "ai_hub" / "inference_petri_dish" / "yolo11m-seg.onnx",
        KOK / "ai_hub" / "inference_petri_dish" / "yolo11m-seg.pt",
    ):
        if aday.exists():
            return aday
    return None


_MODEL = _yolo_yolu()
entegrasyon = pytest.mark.skipif(
    _MODEL is None or not PETRI.exists(), reason="YOLO petri modeli veya test girdileri yok"
)


@pytest.fixture(scope="module")
def boru_hatti():
    from ai_hub.inference_petri_dish.petri_cv import PetriCvPipeline, load_cabin_config

    return PetriCvPipeline(load_cabin_config(None), yolo_model_path=_MODEL, yolo_device="cpu")


@entegrasyon
@pytest.mark.parametrize("yol", [PETRI, PETRI_ARUCO])
def test_gercek_petri_GECER(boru_hatti, yol):
    """YANLIŞ-POZİTİF OLMAMALI — meşru görüntüyü bloklamak da bir başarısızlıktır."""
    if not yol.exists():
        pytest.skip(f"girdi yok: {yol.name}")
    r, _ = boru_hatti.process_image(cv2.imread(str(yol)))
    assert r.error != pl.PETRI_REJECT, f"gerçek petri reddedildi: {r.plausibility}"
    assert r.success, r.error
    assert r.n_wells > 0


@entegrasyon
@pytest.mark.parametrize("yol", [FANTOM, KEDI_SEG])
def test_capraz_yukleme_REDDEDILIR(boru_hatti, yol):
    """ASIL BULGU: fantom/kedi fotoğrafı sessizce 'kuyucuk' üretmemeli."""
    if not yol.exists():
        pytest.skip(f"girdi yok: {yol.name}")
    r, _ = boru_hatti.process_image(cv2.imread(str(yol)))
    assert r.error == pl.PETRI_REJECT, f"reddedilmedi: success={r.success} hata={r.error} {r.plausibility}"
    assert r.success is False
    assert r.wells == [], "reddedilen görüntüde kuyucuk tahmini üretilmemeli"


@entegrasyon
@pytest.mark.parametrize("yol", [CT_KIST, CT_NORMAL, CT_TAS])
def test_bobrek_CT_kesiti_REDDEDILIR(boru_hatti, yol):
    """DENETİM 2026-08-06 (ASIL REGRESYON): `utils/image_domain.py` em_petri'ye GRAYSCALE'i
    açtığı gün CT kesitlerini bu uçta tutan modalite katmanı kalktı ve o anki geometri katmanı
    07b/07c'yi GEÇİRİYORDU (HTTP 200, success=True, n_wells=1, PetriPredictor çalıştı).
    Böbrek CT'sinden "petri kuyucuğu" raporlamak, düzeltilmeye çalışılan sessiz-yanlış-sonucun
    kendisidir. İki katman da yerinde olmalı: modalite {COLOR,GRAYSCALE} ise alan VETO'su ŞART."""
    if not yol.exists():
        pytest.skip(f"girdi yok: {yol.name}")
    r, _ = boru_hatti.process_image(cv2.imread(str(yol)))
    assert r.error == pl.PETRI_REJECT, f"CT kabul edildi: success={r.success} {r.plausibility}"
    assert r.success is False and r.wells == []


@entegrasyon
def test_kacis_kapagi_boru_hattinda_da_calisir(boru_hatti, monkeypatch):
    if not FANTOM.exists():
        pytest.skip("girdi yok")
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
    with open(FANTOM, "rb") as f:
        r = c.post("/api/ai/vision/em_petri", files={"file": ("fantom.jpeg", f, "image/jpeg")})
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

    if not CT_KIST.exists():
        pytest.skip("girdi yok")
    c = TestClient(api_server.app)
    with open(CT_KIST, "rb") as f:
        r = c.post("/api/ai/vision/em_petri", files={"file": ("ct.jpg", f, "image/jpeg")})
    assert r.status_code == 422, f"HTTP {r.status_code}: {r.text[:300]}"
    assert "petri" in r.json().get("detail", "").lower()


@entegrasyon
def test_uc_gercek_petriyi_KABUL_eder():
    from fastapi.testclient import TestClient

    from servers import api_server

    c = TestClient(api_server.app)
    with open(PETRI, "rb") as f:
        r = c.post("/api/ai/vision/em_petri", files={"file": ("petri.jpg", f, "image/jpeg")})
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:300]}"
    assert r.json().get("status") == "success", r.json().get("error")
