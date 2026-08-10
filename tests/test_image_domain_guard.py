# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI girdi-ALAN denetimi — yanlış modalitedeki görüntüye güvenle teşhis üretilmesini engeller.

SAHİP BİLDİRİMİ (2026-08-06): Böbrek Patoloji modülüne CT kesiti yüklendi → "Grade 4 · güven %100".
Sınıflandırıcı softmax'ı, girdi eğitim dağılımının dışında olsa bile 1'e toplar; model YANILDIĞINI
bilmez. Bu testler gerçek test görüntüleriyle (ai_hub/PEMF_AI_Test_Girdileri) korumayı kilitler.
"""

import os
from pathlib import Path

import cv2
import pytest

os.environ.pop("PEMF_SIMULATE", None)

from utils import image_domain as dom

GIRDI = Path(__file__).resolve().parent.parent / "ai_hub" / "PEMF_AI_Test_Girdileri"

CT = GIRDI / "07a_BobrekCT_tas.jpg"
CT_KIST = GIRDI / "07b_BobrekCT_kist.jpg"
PATOLOJI = GIRDI / "08a_BobrekPatoloji_grade0.jpg"
PATOLOJI4 = GIRDI / "08c_BobrekPatoloji_grade4.jpg"
KEDI = GIRDI / "01_YuzAgrisi_FGS_kedi.jpeg"
PETRI = GIRDI / "06_PetriKuyu.jpg"
PETRI_ARUCO = GIRDI / "06b_PetriKuyu_aruco.jpg"
FANTOM = GIRDI / "05_FantomTumor.jpeg"

pytestmark = pytest.mark.skipif(not CT.exists(), reason="test girdileri yok")


def oku(p):
    img = cv2.imread(str(p))
    assert img is not None, f"okunamadi: {p}"
    return img


# ── modalite tespiti doğru mu ────────────────────────────────────────────────
@pytest.mark.parametrize(
    "yol,beklenen",
    [
        (CT, dom.GRAYSCALE),
        (CT_KIST, dom.GRAYSCALE),
        (PATOLOJI, dom.STAINED),
        (PATOLOJI4, dom.STAINED),
        (KEDI, dom.COLOR),
        (PETRI, dom.COLOR),
        (FANTOM, dom.COLOR),
    ],
)
def test_modalite_tespiti(yol, beklenen):
    algilanan, olcum = dom.analyze(oku(yol))
    assert algilanan == beklenen, f"{yol.name}: {algilanan} != {beklenen} ({olcum})"


# ── ASIL BULGU: CT görüntüsü patoloji modülünde REDDEDİLMELİ ────────────────
def test_ct_goruntusu_patoloji_modulunde_reddedilir():
    with pytest.raises(dom.DomainMismatch) as ex:
        dom.check(oku(CT), "histopath")
    msg = ex.value.user_message()
    assert "patoloji" in msg.lower()
    assert "gri tonlamalı" in msg.lower()  # NEYIN yüklendiğini söylemeli
    assert "yanıltıcı" in msg.lower()  # NEDEN reddedildiğini söylemeli


# DENETİM 2026-08-06 (BAĞIMSIZ ÇAPRAZ MATRİS ile bulundu): histopath `{STAINED, COLOR}` iken
# HER renkli fotoğrafı kabul ediyordu → kedi fotoğrafına da "Grade 4 · %100" verilebilirdi.
# Sahibin bildirdiği CT vakasıyla AYNI sınıf hata. Bu testler o boşluğu kilitler.
@pytest.mark.parametrize("yol", [KEDI, PETRI, FANTOM, PETRI_ARUCO])
def test_patoloji_OLMAYAN_goruntuler_histopath_te_reddedilir(yol):
    if not yol.exists():
        pytest.skip(f"girdi yok: {yol.name}")
    with pytest.raises(dom.DomainMismatch):
        dom.check(oku(yol), "histopath")


def test_gercek_patoloji_STAINED_marji_korunur():
    """Eşik (0.15) ile gerçek patoloji arasında en az 2 kat pay olmalı — solgun boyanmış bir
    preparat yanlışlıkla reddedilmesin. En düşük gerçek örnek 08b (ölçülen stain_ratio 0.352)."""
    for p in [PATOLOJI, PATOLOJI4, GIRDI / "08b_BobrekPatoloji_grade2.jpg"]:
        if not p.exists():
            continue
        modalite, olcum = dom.analyze(oku(p))
        assert modalite == dom.STAINED, f"{p.name}: {modalite} ({olcum})"
        assert olcum["stain_ratio"] >= dom._STAIN_RATIO * 2, (
            f"{p.name} eşiğe çok yakın: {olcum['stain_ratio']} (eşik {dom._STAIN_RATIO})"
        )


def test_patoloji_olmayanlar_esigin_COK_altinda():
    """Ters yön: patoloji-dışı görüntüler eşiğin en az yarısı kadar altında kalmalı."""
    for p in [KEDI, PETRI, FANTOM]:
        _m, olcum = dom.analyze(oku(p))
        assert olcum["stain_ratio"] <= dom._STAIN_RATIO * 0.5, f"{p.name} eşiğe çok yakın: {olcum['stain_ratio']}"


def test_renkli_fotograf_ct_modulunde_reddedilir():
    with pytest.raises(dom.DomainMismatch):
        dom.check(oku(KEDI), "kidney_ct")


def test_patoloji_goruntusu_ct_modulunde_reddedilir():
    with pytest.raises(dom.DomainMismatch):
        dom.check(oku(PATOLOJI), "kidney_ct")


# ── YANLIŞ-POZİTİF OLMAMALI: doğru görüntüler sorunsuz geçmeli ──────────────
@pytest.mark.parametrize(
    "yol,etiket",
    [
        (CT, "kidney_ct"),
        (CT_KIST, "kidney_ct"),
        (PATOLOJI, "histopath"),
        (PATOLOJI4, "histopath"),
        (KEDI, "landmark"),
        (KEDI, "segmentation"),
        (KEDI, "cat_organ"),
        (PETRI, "em_petri"),
        (FANTOM, "em_fantom"),
        # DENETİM 2026-08-06: 06b GERÇEK bir petri girdisi ama achromatic_ratio=0.9937 ile
        # `grayscale` algılanıyor → EXPECTED["em_petri"] yalnız {COLOR} iken 422 ile REDDEDİLİYORDU
        # (canlı yanlış-pozitif: "petri modülü petri fotoğrafını kabul etmiyor").
        (PETRI_ARUCO, "em_petri"),
    ],
)
def test_dogru_goruntu_gecer(yol, etiket):
    if not yol.exists():
        pytest.skip(f"girdi yok: {yol.name}")
    dom.check(oku(yol), etiket)  # fırlatmamalı


def test_modalite_denetimi_FANTOMU_petriden_AYIRAMAZ():
    """DÜRÜSTLÜK TESTİ (sınırı belgeler): fantom fotoğrafı `em_petri` modalite denetiminden
    GEÇER — ikisi de `color`. Bu boşluğu kapatan şey geometri katmanıdır
    (ai_hub/inference_petri_dish/plausibility.py, bkz. tests/test_petri_plausibility.py).
    Modalite denetimi bir gün "yakalıyor" sanılıp geometri katmanı sökülmesin."""
    dom.check(oku(FANTOM), "em_petri")  # fırlatmıyor — KASITLI, tek katman yetmez
    assert dom.analyze(oku(FANTOM))[0] == dom.COLOR
    assert dom.analyze(oku(PETRI))[0] == dom.COLOR


def test_em_petri_GRAYSCALE_i_kabul_eder_CT_yi_GEOMETRI_tutar():
    """DENETİM 2026-08-06 (DÜRÜSTLÜK + BAĞIMLILIK KİLİDİ): `em_petri` gerçek kabin fotoğrafı
    için GRAYSCALE'e açıldı (06b achromatic=0.9937). BEDELİ: CT kesiti de bu uçta modalite
    denetiminden GEÇER — yani em_petri'de CT'yi tutan tek şey `plausibility.py` ALAN VETO'sudur
    (bkz. tests/test_petri_plausibility.py::test_bobrek_CT_kesiti_REDDEDILIR).
    Bu testin adı bir uyarıdır: EXPECTED['em_petri'] GRAYSCALE içerdiği sürece veto SÖKÜLEMEZ."""
    assert dom.analyze(oku(CT))[0] == dom.GRAYSCALE
    assert dom.GRAYSCALE in dom.EXPECTED["em_petri"]
    dom.check(oku(CT), "em_petri")  # fırlatmıyor — geometri katmanı ŞART
    from ai_hub.inference_petri_dish import plausibility as pl

    assert pl.is_plausible({"measurable": True, "votes": 2, "area_ok": False}) is False


# ── kapsam dışı uçlar denetlenmemeli (geriye uyumluluk) ─────────────────────
@pytest.mark.parametrize("etiket", ["thermal", "ai_pro_frame", "yeni_model_2027"])
def test_kapsam_disi_uclar_serbest(etiket):
    dom.check(oku(CT), etiket)
    dom.check(oku(KEDI), etiket)


# ── araştırma kaçış kapağı ──────────────────────────────────────────────────
def test_env_ile_kapatilabilir(monkeypatch):
    monkeypatch.setenv("PEMF_AI_DOMAIN_GUARD", "0")
    dom.check(oku(CT), "histopath")  # kapalıyken fırlatmamalı


def test_varsayilan_ACIK(monkeypatch):
    monkeypatch.delenv("PEMF_AI_DOMAIN_GUARD", raising=False)
    assert dom.guard_enabled() is True


# ── bozuk girdi denetimi ÇÖKERTMEMELİ ───────────────────────────────────────
def test_bos_goruntu_cokertmez():
    import numpy as np

    dom.check(np.zeros((0, 0, 3), dtype=np.uint8), "histopath")
    dom.check(None, "histopath")


# ── UÇ SEVİYESİ: 422 + anlaşılır mesaj (500 "Analiz hatası" DEĞİL) ──────────
def test_uc_422_ve_anlasilir_mesaj_dondurur():
    from fastapi.testclient import TestClient

    from servers import api_server

    c = TestClient(api_server.app)
    with open(CT, "rb") as f:
        r = c.post("/api/ai/vision/histopath", files={"file": ("ct.jpg", f, "image/jpeg")})
    assert r.status_code == 422, f"HTTP {r.status_code}: {r.text[:200]}"
    detail = r.json().get("detail", "")
    assert "patoloji" in detail.lower(), detail
    assert "Histopatoloji analiz hatası" not in detail  # jenerik 500'e düşmemeli


def test_uc_dogru_goruntuyu_KABUL_eder():
    from fastapi.testclient import TestClient

    from servers import api_server

    c = TestClient(api_server.app)
    with open(CT, "rb") as f:
        r = c.post("/api/ai/vision/kidney_ct", files={"file": ("ct.jpg", f, "image/jpeg")})
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}"
    assert r.json().get("status") == "success"
