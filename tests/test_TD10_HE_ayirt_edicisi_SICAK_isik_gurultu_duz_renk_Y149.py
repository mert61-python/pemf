# -*- coding: utf-8 -*-
"""TD10 (Y149, sahip 2026-10-14) — H&E ayırt edicisi: sıcak ışıktaki doğal kare, RGB gürültü ve düz renk STAINED SAYILMAZ; gerçek
patoloji geçer.

ÖLÇÜLEN KUSUR (SG S-SG.3 · G5): canlı segmentasyon karelerinin 63'ü sıcak oda ışığında (ten, pembe-bej perde) `stain_ratio` 0,16–0,51
ile "boyalı patoloji (H&E) gibi" 422 aldı; RGB gürültü (0,29) histopath'ta "grade2 %63" üretti. Gerçek patoloji 0,352–0,882 → eşikle
ayrılmaz. Düzeltme `utils/image_domain._he_yapisi`: iki boya + doku + bulanıkta korunma (ölçüm tablosu modül yorumunda ve raporda).
Sahibin fotoğrafları depoya GİRMEZ: sıcak ışık sahneleri ölçülen dağılımı üreten SENTETİK kurgulardır (pembe-bej perde + kıvrım
gölgesi + ten + ahşap + sıcak beyaz dengesi + sensör gürültüsü). Gerçek patoloji (`ai_hub/PEMF_AI_Test_Girdileri/08*.jpg`, izlenmez)
varsa ölçülür; depoda izlenen sentetik H&E (pembe eozin zemin + mor çekirdekler + lif dokusu) mutasyon kapısını her makinede tutar.
AI-2'nin em_fantom / em_petri istisnaları (STAINED kabul) ve ikinci katmanları KORUNUR.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

GIRDI = Path(__file__).resolve().parents[1] / "ai_hub" / "PEMF_AI_Test_Girdileri"
PATOLOJI = ["08a_BobrekPatoloji_grade0.jpg", "08b_BobrekPatoloji_grade2.jpg", "08c_BobrekPatoloji_grade4.jpg"]


def _dom():
    from utils import image_domain as dom

    return dom


def sicak_sahne(tohum: int, perde=(200, 180, 225), sicaklik=1.05, perde_oran=0.7) -> np.ndarray:
    rng = np.random.default_rng(tohum)
    h, w = 360, 480
    img = np.zeros((h, w, 3), np.float32)
    img[:] = (170, 185, 200)
    pw = int(w * perde_oran)
    img[:, :pw] = perde
    for x in range(0, pw, 24):
        img[:, x : x + 8] *= 0.82
    cv2.ellipse(img, (int(w * 0.68), int(h * 0.45)), (70, 95), 0, 0, 360, (150, 175, 215), -1)
    cv2.rectangle(img, (0, int(h * 0.82)), (w, h), (60, 95, 140), -1)
    img[:, :, 2] *= sicaklik
    img[:, :, 0] /= sicaklik
    return np.clip(img + rng.normal(0, 5, img.shape), 0, 255).astype(np.uint8)


def sentetik_he(tohum: int = 3) -> np.ndarray:
    """Pembe eozin zemin + lif dokusu + mor-lacivert hematoksilen çekirdekleri + boşluklar (BGR)."""
    rng = np.random.default_rng(tohum)
    h, w = 400, 520
    lif = cv2.GaussianBlur(rng.normal(0, 1, (h, w)).astype(np.float32), (0, 0), 3)
    lif = (lif - lif.min()) / (lif.max() - lif.min())
    img = np.zeros((h, w, 3), np.float32)
    img[:] = (190, 140, 225)
    img *= (0.75 + 0.45 * lif)[:, :, None]
    for _ in range(14):
        cv2.ellipse(
            img,
            (int(rng.integers(0, w)), int(rng.integers(0, h))),
            (int(rng.integers(12, 30)), int(rng.integers(8, 20))),
            float(rng.integers(0, 180)),
            0,
            360,
            (235, 230, 240),
            -1,
        )
    for _ in range(420):
        cv2.ellipse(
            img,
            (int(rng.integers(0, w)), int(rng.integers(0, h))),
            (int(rng.integers(3, 7)), int(rng.integers(3, 6))),
            float(rng.integers(0, 180)),
            0,
            360,
            (150, 55, 95),
            -1,
        )
    return np.clip(img + rng.normal(0, 6, img.shape), 0, 255).astype(np.uint8)


SICAK = [
    dict(perde=(200, 180, 225), sicaklik=1.05, perde_oran=0.4),
    dict(perde=(200, 180, 225), sicaklik=1.05, perde_oran=0.7),
    dict(perde=(190, 170, 215), sicaklik=1.05, perde_oran=0.7),
    dict(perde=(205, 185, 235), sicaklik=1.05, perde_oran=0.7),
    dict(perde=(185, 165, 210), sicaklik=1.05, perde_oran=0.4),
    dict(perde=(210, 175, 230), sicaklik=1.05, perde_oran=0.7),
    dict(perde=(210, 175, 230), sicaklik=1.15, perde_oran=0.7),
]


@pytest.mark.parametrize("i", range(len(SICAK)))
def test_KRITIK_sicak_isikli_dogal_kare_HE_SAYILMAZ_canli_uclar_GECER(i):
    dom = _dom()
    img = sicak_sahne(10 + i, **SICAK[i])
    kip, m = dom.analyze(img)
    assert m["stain_ratio"] >= dom._STAIN_RATIO, f"aparat: sahne boya eşiğini geçmeli (tezgâh 0,16–0,51): {m}"
    assert kip != dom.STAINED, f"sıcak ışıklı doğal kare H&E sayıldı: {m}"
    for uc in ("segmentation", "landmark", "cat_organ"):
        dom.check(img, uc)  # 422 (DomainMismatch) FIRLATMAMALI


def test_KRITIK_RGB_gurultu_HE_SAYILMAZ_histopath_REDDEDER():
    dom = _dom()
    img = np.random.default_rng(1).integers(0, 256, (360, 480, 3), dtype=np.uint8)
    kip, m = dom.analyze(img)
    assert m["stain_ratio"] >= dom._STAIN_RATIO and kip != dom.STAINED, m
    with pytest.raises(dom.DomainMismatch):
        dom.check(img, "histopath")


@pytest.mark.parametrize("renk", [(180, 105, 255), (160, 60, 120), (200, 80, 200)])
def test_KRITIK_duz_renk_HE_SAYILMAZ(renk):
    dom = _dom()
    kip, m = dom.analyze(np.full((240, 320, 3), renk, np.uint8))
    assert kip != dom.STAINED, m


def test_KRITIK_iki_blok_duz_pembe_mor_HE_SAYILMAZ():
    dom = _dom()
    img = np.zeros((240, 320, 3), np.uint8)
    img[:, :160] = (180, 105, 255)
    img[:, 160:] = (160, 60, 120)
    kip, m = dom.analyze(img)
    assert kip != dom.STAINED, m


def tek_boya_kumas(renk, tohum: int = 4, genlik: float = 0.35) -> np.ndarray:
    """Tek tonlu DOKULU yüzey (pembe havlu / eflatun kumaş yakın çekimi): örgü + lif, boyalı ama tek boya."""
    rng = np.random.default_rng(tohum)
    h, w = 360, 480
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    orgu = 0.5 * (np.sin(xx * 0.9) + np.sin(yy * 0.9))
    lif = cv2.GaussianBlur(rng.normal(0, 1, (h, w)).astype(np.float32), (0, 0), 1.5)
    lif = lif / (np.abs(lif).max() + 1e-6)
    img = np.zeros((h, w, 3), np.float32)
    img[:] = renk
    img *= (1.0 + genlik * (0.6 * orgu + 0.4 * lif))[:, :, None]
    return np.clip(img + rng.normal(0, 4, img.shape), 0, 255).astype(np.uint8)


@pytest.mark.parametrize("renk", [(190, 140, 225), (200, 80, 200)])
def test_KRITIK_tek_boya_dokulu_yuzey_HE_SAYILMAZ(renk):
    """Doku + bulanıkta korunma VAR, iki boya YOK → yalnız `iki_boya` ölçütü ayırır (H&E iki boyadır)."""
    dom = _dom()
    kip, m = dom.analyze(tek_boya_kumas(renk))
    assert m["doku"] >= dom._HE_DOKU_ASGARI and m["bulanik_oran"] >= dom._HE_BULANIK_ORAN_ASGARI, (
        f"aparat: yalnız iki boya eksik olmalı: {m}"
    )
    assert kip != dom.STAINED, m


def test_KARSIT_sentetik_HE_GECER_histopath_kabul():
    dom = _dom()
    img = sentetik_he()
    kip, m = dom.analyze(img)
    assert kip == dom.STAINED, m
    dom.check(img, "histopath")


@pytest.mark.parametrize("ad", PATOLOJI)
def test_KARSIT_gercek_patoloji_GECER(ad):
    p = GIRDI / ad
    if not p.is_file():
        pytest.skip("test girdisi yok (izlenmez; ai_hub/PEMF_AI_Test_Girdileri)")
    dom = _dom()
    img = cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)
    kip, m = dom.analyze(img)
    assert kip == dom.STAINED, f"{ad}: gerçek patoloji H&E sayılmadı: {m}"
    dom.check(img, "histopath")


def test_AI2_istisnalari_KORUNUR():
    dom = _dom()
    assert dom.STAINED in dom.EXPECTED["em_fantom"] and dom.STAINED in dom.EXPECTED["em_petri"]
    assert dom.GRAYSCALE in dom.EXPECTED["em_petri"] and dom.EXPECTED["histopath"] == {dom.STAINED}
    assert dom._STAIN_RATIO == 0.15, "boya eşiği DEĞİŞMEZ (yapı ölçütü eşiğe EK)"
