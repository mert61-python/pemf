# -*- coding: utf-8 -*-
"""TD11 (Y150, sahip 2026-10-14) — Scratch (yara kapanma) MİKROSKOPİ MAKULLİK KAPISI: mikroskopi olmayan görüntü analiz edilmez.

ÖLÇÜLEN KUSUR (SG ölçtü): araştırma Scratch ucu "karar 0.3: modalite kapısı YOK" ile her görüntüyü CPN hücre segmentasyonuna
veriyordu — nesne fotoğrafına "488 hücre, kapanma %29,5" döndü ve 3 jeton (ağır araştırma) düştü. Düzeltme
`utils/image_domain.scratch_analizi` (termal kapı SG G4 ilkesi: model-bağımsız, deterministik, ölçülmüş eşik, iki yönlü marj; iki ölçek
512 / 256) + `check(img, "scratch")` (yönlendiricinin gömülü ve GPU kolları `_decode_image` üzerinden) + `:8100 /infer/scratch` `_kapi`.
Sahte YALNIZ en alt katta: `scratch_analiz` (CPN), GPU devri ve jeton taşıması; kapı ve uçlar GERÇEK. Eşikler testte LİTERAL (kapı
sabiti mutasyon hedefinden okunmaz). Gerçek 12a / 12b ve H&E 08* izlenmez (`ai_hub/PEMF_AI_Test_Girdileri`) — yoksa atlanır; izlenen
kesit (`tests/xai_veri/yara_0H_kesit_640x600.png`, 12a'dan bayt-kaynaklı) her makinede kapıyı tutar.
"""

from __future__ import annotations

import base64
import importlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

KOK = Path(__file__).resolve().parents[1]
KESIT = KOK / "tests" / "xai_veri" / "yara_0H_kesit_640x600.png"
GIRDI = KOK / "ai_hub" / "PEMF_AI_Test_Girdileri"
KAHIN = KOK / "tests" / "kahin" / "hoca_cv_2026_10"
IZLENEN_OLUMSUZ = [
    "tests/xai_veri/bt_tas_07a.jpg",
    "tests/xai_veri/retikulosit_04a.jpg",
    "tests/xai_veri/termal_saglikli_03a_224.png",
    "tests/xai_veri/termal_hasta_03b_224.png",
    "ai_hub/cat_landmark/results/00000005_020.jpg",
    "ai_hub/cat_segmentation/results/group0032_jpeg_jpg.rf.66f4458aa732ee0e274b7afd6a766b24.jpg",
    "ai_hub/inference_cat_organ/test_img/synthetic_aruco_test.jpg",
    "ai_hub/PEMF_ArUco_Marker_5X5_50_ID0_10cm_A4.png",
]
EYLEM = "mikroskop"


def _dom():
    from utils import image_domain as dom

    return dom


def _oku(p: Path) -> np.ndarray:
    img = cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)
    assert img is not None, p
    return img


def _png(img: np.ndarray) -> bytes:
    ok, b = cv2.imencode(".png", img)
    assert ok
    return b.tobytes()


def _buyut(img: np.ndarray, z: int) -> np.ndarray:
    h, w = img.shape[:2]
    c = img[h // 2 - h // (2 * z) : h // 2 + h // (2 * z), w // 2 - w // (2 * z) : w // 2 + w // (2 * z)]
    return cv2.resize(c, (w, h), interpolation=cv2.INTER_CUBIC)


def _vinyet(img: np.ndarray, guc: float) -> np.ndarray:
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r2 = (((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2) / 2.0
    return np.clip(img.astype(np.float32) * (1.0 - guc * r2)[:, :, None], 0, 255).astype(np.uint8)


def _oda(tohum: int = 2) -> np.ndarray:
    rng = np.random.default_rng(tohum)
    img = np.zeros((360, 480, 3), np.float32)
    img[:] = (170, 185, 200)
    cv2.rectangle(img, (40, 60), (200, 300), (60, 95, 140), -1)
    cv2.ellipse(img, (330, 170), (70, 95), 0, 0, 360, (150, 175, 215), -1)
    cv2.rectangle(img, (0, 300), (480, 360), (90, 110, 130), -1)
    return np.clip(img + rng.normal(0, 5, img.shape), 0, 255).astype(np.uint8)


def _iliskili_gurultu(sigma: float, tohum: int = 9) -> np.ndarray:
    """Piksel ölçeğinde İLİŞKİLİ gürültü (JPEG / gürültü azaltma sonrası gibi): bulanıkta korunur, enerjisi σ < 2'de."""
    g = cv2.GaussianBlur(np.random.default_rng(tohum).normal(128, 50, (400, 520)).astype(np.float32), (0, 0), sigma)
    g = np.clip((g - g.mean()) / (g.std() + 1e-6) * 40 + 128, 0, 255).astype(np.uint8)
    return cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)


def _gurultulu(img: np.ndarray, sigma: float, tohum: int = 9) -> np.ndarray:
    return np.clip(img.astype(np.float32) + np.random.default_rng(tohum).normal(0, sigma, img.shape), 0, 255).astype(
        np.uint8
    )


def _kontrast(img: np.ndarray, c: float) -> np.ndarray:
    f = img.astype(np.float32)
    return np.clip(f.mean() + (f - f.mean()) * c, 0, 255).astype(np.uint8)


def _golgeli_granuler(golge: float = 0.9) -> np.ndarray:
    """Hücre ölçeğinde granüler yüzey (kum / kumaş yakın çekimi) + güçlü yan ışık gölgesi."""
    d = _iliskili_gurultu(1.5).astype(np.float32)
    m = np.linspace(1.0 - golge, 1.0 + golge, d.shape[1], dtype=np.float32)[None, :, None]
    return np.clip((d - 128) * 0.6 + 128 * m, 0, 255).astype(np.uint8)


SENTETIK_OLUMSUZ = {
    "oda": _oda,
    "duz_gri": lambda: np.full((300, 400, 3), 128, np.uint8),
    "duz_bej": lambda: np.full((300, 400, 3), (170, 185, 200), np.uint8),
    "duz_siyah": lambda: np.zeros((300, 400, 3), np.uint8),
    "rgb_gurultu": lambda: np.random.default_rng(2).integers(0, 256, (400, 520, 3), dtype=np.uint8),
    "gri_gurultu": lambda: cv2.cvtColor(
        np.random.default_rng(3).integers(0, 256, (400, 520), dtype=np.uint8), cv2.COLOR_GRAY2BGR
    ),
    "kucuk_1x1": lambda: np.full((1, 1, 3), 90, np.uint8),
}


# ── 1) Saf kapı: gerçek scratch mikroskopisi GEÇER ────────────────────────────────────────────────────────────────────────
KESIT_VARYANT = {
    "ham": lambda i: i,
    "2x_buyutme": lambda i: _buyut(i, 2),
    "odak_sigma2": lambda i: cv2.GaussianBlur(i, (0, 0), 2.0),
    "odak_sigma3": lambda i: cv2.GaussianBlur(i, (0, 0), 3.0),
    "vinyet_0.7": lambda i: _vinyet(i, 0.7),
    "kontrast_0.5": lambda i: np.clip(128 + (i.astype(np.float32) - 128) * 0.5, 0, 255).astype(np.uint8),
    "jpeg_q70": lambda i: cv2.imdecode(cv2.imencode(".jpg", i, [cv2.IMWRITE_JPEG_QUALITY, 70])[1], cv2.IMREAD_COLOR),
    "yatay_90": lambda i: cv2.rotate(i, cv2.ROTATE_90_CLOCKWISE),
    "gri_tek_kanal": lambda i: cv2.cvtColor(i, cv2.COLOR_BGR2GRAY),
    "gurultulu_sigma30": lambda i: _gurultulu(i, 30),
    "kontrast_0.3": lambda i: _kontrast(i, 0.3),
}


@pytest.mark.parametrize("varyant", list(KESIT_VARYANT))
def test_KARSIT_izlenen_gercek_kesit_ve_cekim_varyantlari_GECER(varyant):
    dom = _dom()
    img = KESIT_VARYANT[varyant](_oku(KESIT))
    durum, m = dom.scratch_analizi(img)
    assert durum == "mikroskopi", f"gerçek scratch kesiti ({varyant}) REDDEDİLDİ: {m}"
    dom.check(img, "scratch")


@pytest.mark.parametrize("ad", ["12a_YaraKapanma_0H.tif", "12b_YaraKapanma_24H.tif"])
@pytest.mark.parametrize("z", [1, 2, 3])
def test_KARSIT_gercek_12a_12b_ve_buyutmeleri_GECER(ad, z):
    p = GIRDI / ad
    if not p.is_file():
        pytest.skip("test girdisi yok (izlenmez; ai_hub/PEMF_AI_Test_Girdileri)")
    dom = _dom()
    img = _oku(p) if z == 1 else _buyut(_oku(p), z)
    durum, m = dom.scratch_analizi(img)
    assert durum == "mikroskopi", f"{ad} ×{z} REDDEDİLDİ: {m}"


# ── 2) Saf kapı: nesne / oda / düz renk / gürültü / başka modalite 422 + EYLEM ───────────────────────────────────────────
def _reddedilir(img: np.ndarray, ad: str):
    dom = _dom()
    durum, m = dom.scratch_analizi(img)
    assert durum == "uyumsuz", f"{ad}: mikroskopi olmayan görüntü scratch'e GEÇTİ: {m}"
    with pytest.raises(dom.DomainMismatch) as e:
        dom.check(img, "scratch")
    metin = e.value.user_message()
    assert EYLEM in metin.lower() and "yükleyin" in metin, f"{ad}: ret metni eylem söylemiyor: {metin}"
    return m, metin


@pytest.mark.parametrize("ad", list(SENTETIK_OLUMSUZ))
def test_KRITIK_oda_duz_renk_gurultu_REDDEDILIR_eylem_metniyle(ad):
    m, metin = _reddedilir(SENTETIK_OLUMSUZ[ad](), ad)
    if ad.startswith("duz") or ad == "kucuk_1x1":
        assert m["neden"] == "duz" and "düz" in metin, (m, metin)
    if ad.endswith("gurultu"):
        assert m["neden"] == "gurultu" and "gürültü" in metin, (m, metin)
    if ad == "oda":
        assert m["neden"] == "yapi_yok" and "gürültü" not in metin and "fotoğraf" in metin, (m, metin)


#: Her ölçütü TEK BAŞINA reddeden karşıt örnek (diğer üçü geçer) — dört ölçütün de görevi var (mutasyon kapısı).
YALITIM = {
    "iliskili_gurultu_sigma1": (lambda: _iliskili_gurultu(1.0), "gurultu", "orta_ust"),
    "gurultu_baskin_kesit_sigma55": (lambda: _gurultulu(_oku(KESIT), 55), "gurultu", "korunma"),
    "asiri_dusuk_kontrast_kesit_0.15": (lambda: _kontrast(_oku(KESIT), 0.15), "duz", "doku"),
    "golgeli_granuler_yuzey": (_golgeli_granuler, "yapi_yok", "ince_oran"),
}
_SINIR = {
    "doku": 2.0,
    "korunma": 0.55,
    "orta_alt": 1.9,
    "orta_ust": 6.5,
    "ince_oran": 0.28,
}  # LİTERAL (modülden okunmaz)


def _kalan(m: dict) -> set:
    k = set()
    if m["doku"] < _SINIR["doku"]:
        k.add("doku")
    if m["korunma"] < _SINIR["korunma"]:
        k.add("korunma")
    if m["orta"] < _SINIR["orta_alt"]:
        k.add("orta_alt")
    if m["orta"] > _SINIR["orta_ust"]:
        k.add("orta_ust")
    if m["ince_oran"] < _SINIR["ince_oran"]:
        k.add("ince_oran")
    return k


@pytest.mark.parametrize("ad", list(YALITIM))
def test_KRITIK_her_olcut_TEK_BASINA_reddeder(ad):
    uretici, neden, olcut = YALITIM[ad]
    m, _ = _reddedilir(uretici(), ad)
    assert m["neden"] == neden, m
    kalanlar = [_kalan(m[o]) for o in ("512", "256")]
    assert any(k == {olcut} for k in kalanlar), (
        f"aparat: {ad} en az bir ölçekte YALNIZ {olcut} ile kalmalı: {kalanlar} {m}"
    )


@pytest.mark.parametrize("yol", IZLENEN_OLUMSUZ + sorted(p.relative_to(KOK).as_posix() for p in KAHIN.rglob("*.jp*g")))
def test_KRITIK_izlenen_nesne_fantom_petri_kedi_CT_termal_REDDEDILIR(yol):
    _reddedilir(_oku(KOK / yol), yol)


@pytest.mark.parametrize(
    "ad", ["08a_BobrekPatoloji_grade0.jpg", "08b_BobrekPatoloji_grade2.jpg", "08c_BobrekPatoloji_grade4.jpg"]
)
def test_KRITIK_HE_patoloji_scratch_e_GECMEZ(ad):
    p = GIRDI / ad
    if not p.is_file():
        pytest.skip("test girdisi yok (izlenmez)")
    _reddedilir(_oku(p), ad)


def test_olcum_dagilimi_IKI_YONDE_marj():
    """Eşikler ölçümden (modül yorumu); aparat girdilerinde marj korunur mu — LİTERAL sınırlar (kapı sabiti okunmaz)."""
    dom = _dom()
    _, m = dom.scratch_analizi(_oku(KESIT))
    gecen = m[str(m["olcek"])]
    assert gecen["orta"] >= 2.0 and gecen["ince_oran"] >= 0.30 and gecen["korunma"] >= 0.6, m
    for ad in ("rgb_gurultu", "gri_gurultu"):
        _, g = dom.scratch_analizi(SENTETIK_OLUMSUZ[ad]())
        assert all(g[o]["korunma"] <= 0.50 and g[o]["orta"] >= 7.0 for o in ("512", "256")), g
    for p in sorted(KAHIN.rglob("*.jp*g")):
        _, f = dom.scratch_analizi(_oku(p))
        assert all(f[o]["orta"] <= 1.6 for o in ("512", "256")), (p.name, f)


# ── 3) A-24: kapı ÇÖKERSE ret ────────────────────────────────────────────────────────────────────────────────────────────
def test_KRITIK_A24_scratch_kapisi_COKERSE_REDDEDER(monkeypatch):
    dom = _dom()

    def _bozuk(img):
        raise RuntimeError("sentetik iç hata (TD11 kapısı)")

    monkeypatch.setattr(dom, "scratch_analizi", _bozuk)
    monkeypatch.delenv("PEMF_AI_DOMAIN_GUARD", raising=False)
    with pytest.raises(dom.DomainCheckError):
        dom.check(_oku(KESIT), "scratch")


# ── 4) Uçlar: gömülü + GPU kolu + :8100 — ret 422, model ÇAĞRILMAZ, geçen girdi DEĞİŞMEDEN analize gider ───────────────────
@pytest.fixture()
def uc(monkeypatch):
    from servers import ai_router as air
    from servers import api_server

    import ai_hub.inference_paper_dilek_hoca.inference_paper_dilek_hoca as ipd

    cagri = []

    def _sahte(image_path, *, scratch_yonu, pixel_mm, explain, xai_method):
        cagri.append(cv2.imread(image_path, cv2.IMREAD_COLOR))
        return {"n_cells": 488, "closure": {"closure_pct": 29.5}, "uyari": None}

    monkeypatch.setattr(ipd, "scratch_analiz", _sahte)
    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    monkeypatch.delenv("PEMF_AI_DOMAIN_GUARD", raising=False)
    api_server.app.dependency_overrides[air.require_research] = lambda: True
    try:
        yield TestClient(api_server.app, client=("127.0.0.1", 51234)), cagri, air
    finally:
        api_server.app.dependency_overrides.pop(air.require_research, None)


def _gonder(client, veri: bytes, ad: str = "k.png", basliklar: dict | None = None):
    return client.post(
        "/api/ai/vision/scratch",
        files={"file": (ad, veri, "image/png")},
        data={"scratch_yonu": "dikey", "pixel_mm": "0.0016"},
        headers=basliklar or {},
    )


@pytest.mark.parametrize("ad", ["oda", "duz_bej", "rgb_gurultu"])
def test_KRITIK_gomulu_uc_mikroskopi_OLMAYANI_422_ve_CPN_CAGRILMAZ(uc, ad):
    client, cagri, _ = uc
    r = _gonder(client, _png(SENTETIK_OLUMSUZ[ad]()))
    assert r.status_code == 422, (
        f"{ad}: mikroskopi olmayan görüntü analiz edildi (HTTP {r.status_code}): {r.text[:200]}"
    )
    assert EYLEM in r.json()["detail"].lower(), r.text[:200]
    assert cagri == [], "kapı reddetmesine rağmen CPN çalıştı"


def test_KRITIK_gomulu_uc_nesne_fotografi_422(uc):
    client, cagri, _ = uc
    p = sorted((KAHIN / "fantom").glob("*.jpeg"))[0]
    r = client.post("/api/ai/vision/scratch", files={"file": (p.name, p.read_bytes(), "image/jpeg")})
    assert r.status_code == 422 and EYLEM in r.json()["detail"].lower(), r.text[:200]
    assert cagri == []


@pytest.mark.parametrize("kaynak", ["kesit", "12a", "12b"])
def test_KRITIK_gercek_mikroskopi_GECER_ve_analize_DEGISMEDEN_gider(uc, kaynak):
    """Kapı salt okur: CPN'e giden kayıpsız PNG = gönderilen görüntü (piksel piksel) → kâhin (`test_scratch_gercek_model`)
    sonuçları bu uçta da BİREBİR."""
    p = {"kesit": KESIT, "12a": GIRDI / "12a_YaraKapanma_0H.tif", "12b": GIRDI / "12b_YaraKapanma_24H.tif"}[kaynak]
    if not p.is_file():
        pytest.skip("test girdisi yok (izlenmez)")
    client, cagri, _ = uc
    r = _gonder(client, p.read_bytes(), ad=p.name)
    assert r.status_code == 200, r.text[:200]
    assert len(cagri) == 1 and np.array_equal(cagri[0], _oku(p)), "analize giden görüntü gönderilenden FARKLI"


def test_KRITIK_A24_uc_kapisi_COKERSE_422_ve_CPN_CAGRILMAZ(uc, monkeypatch):
    client, cagri, _ = uc
    dom = _dom()

    def _bozuk(img):
        raise RuntimeError("sentetik iç hata")

    monkeypatch.setattr(dom, "scratch_analizi", _bozuk)
    r = _gonder(client, KESIT.read_bytes())
    assert r.status_code == 422 and r.json()["detail"] == dom.DENETIM_CALISMADI_MESAJI, r.text[:200]
    assert cagri == []


def test_KRITIK_GPU_kolunda_kapi_DEVRETMEDEN_once(uc, monkeypatch):
    client, cagri, air = uc
    devredilen = []

    async def _devret(name, **kw):
        devredilen.append(name)
        return {"status": "success", "n_cells": 488}

    monkeypatch.setattr(air, "ai_service_enabled", lambda: True)
    monkeypatch.setattr(air, "delegate_infer", _devret)
    r = _gonder(client, _png(_oda()))
    assert r.status_code == 422 and EYLEM in r.json()["detail"].lower(), r.text[:200]
    assert devredilen == []
    r2 = _gonder(client, KESIT.read_bytes())
    assert r2.status_code == 200 and devredilen == ["scratch"], r2.text[:200]


def test_KRITIK_GPU_servisi_8100_PARITE(monkeypatch):
    """`ai_service/app.py /infer/scratch` aynı kapıyı (aynı nesne) uygular: ret 422 + `domain_mismatch`, CPN çağrılmaz."""
    import ai_hub.inference_paper_dilek_hoca.inference_paper_dilek_hoca as ipd
    from ai_service import app as svc

    cagri = []
    monkeypatch.setattr(ipd, "scratch_analiz", lambda yol, **k: cagri.append(yol) or {"n_cells": 1, "closure": None})
    monkeypatch.delenv("PEMF_AI_DOMAIN_GUARD", raising=False)
    c = TestClient(svc.app)
    r = c.post("/infer/scratch", files={"file": ("o.png", _png(_oda()), "image/png")})
    assert r.status_code == 422 and r.json().get("domain_mismatch") is True and EYLEM in r.json()["error"].lower(), (
        r.text[:200]
    )
    assert cagri == []
    r2 = c.post("/infer/scratch", files={"file": ("k.png", KESIT.read_bytes(), "image/png")})
    assert r2.status_code == 200 and len(cagri) == 1, r2.text[:200]


def test_KARSIT_KANIT_kacis_kapagi_PEMF_AI_DOMAIN_GUARD_0(uc, monkeypatch):
    client, cagri, _ = uc
    monkeypatch.setenv("PEMF_AI_DOMAIN_GUARD", "0")
    r = _gonder(client, _png(_oda()))
    assert r.status_code == 200 and len(cagri) == 1, r.text[:200]


# ── 5) Jeton: ret DÜŞMEZ, geçen analiz 3 (ağır araştırma) ─────────────────────────────────────────────────────────────────
def _jwt(sub: str) -> str:
    b = base64.urlsafe_b64encode(json.dumps({"sub": sub}).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJIUzI1NiJ9.{b}.imza"


@pytest.fixture()
def jetonlu(uc, tmp_path, monkeypatch):
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))
    j = importlib.import_module("servers.jeton")
    monkeypatch.setattr(j, "JETON_ENFORCED", True)
    monkeypatch.setattr(j, "_son_uzlastirma", None, raising=False)
    okunan, giden = [], []
    bakiye = {"aylik_hak": 0, "satin_alinan": 100, "odeme_modeli": "on_odemeli", "kullandikca_borc": 0}
    monkeypatch.setattr(j, "_bakiye_satiri_oku", lambda token: okunan.append(token) or dict(bakiye))
    monkeypatch.setattr(j, "_tuketim_gonder_canli", lambda token, **k: giden.append(k) or True)
    yield uc[0], okunan, giden
    t = getattr(j, "_son_uzlastirma", None)
    if t is not None:
        t.join(timeout=10)


def test_KRITIK_reddedilen_scratch_JETON_DUSURMEZ_gecen_UC_jeton(jetonlu):
    client, okunan, giden = jetonlu
    yetki = {"Authorization": f"Bearer {_jwt('arastirmaci-a')}"}
    r = _gonder(client, _png(_oda()), basliklar=yetki)
    assert r.status_code == 422, r.text[:200]
    assert okunan, "KARŞIT: jeton kapısı bakiyeyi okumadı — ölçüm kör"
    assert giden == [], f"reddedilen scratch için jeton DÜŞTÜ: {giden}"
    r2 = _gonder(client, KESIT.read_bytes(), basliklar=yetki)
    assert r2.status_code == 200, r2.text[:200]
    assert len(giden) == 1 and giden[0]["miktar"] == 3, giden
