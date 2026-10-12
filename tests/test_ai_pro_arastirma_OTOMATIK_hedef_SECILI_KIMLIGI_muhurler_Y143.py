# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Y143 (S-AII.4, sahip 2026-10-13) — araştırma AI Pro'da "otomatik" hedefle (0) onaylanan seans, onay anında SEÇİLİ hedefin
KİMLİĞİYLE mühürlenir: onay ekranında görülen = sürülen.

ÖLÇÜLEN KUSUR (AI incelemesi AII-2.4, A2 K1.10): `/propose` `organ_id=0` (otomatik) ile çağrılınca mühüre 0 yazılıyordu; onay
ekranı o anki otomatik seçimin ETİKETİNİ ("Tümör 2") gösteriyordu ama seans döngüsü / kare yolu her karede yeniden
"en yüksek öncelikli" hedefi seçiyor → öncelik değişince (odak büyüdü, ışık değişti, yeni tespit) ONAYLANMAYAN hedef sürülüyordu.

SÖZLEŞME (Y143): `/propose` hedef 0 iken o anki seçili hedefin KİMLİĞİNİ mühüre yazar (`specs.organ_id`); `/start` mühürden okur;
döngü / kare yolu yalnız o kimliği sürer (D1.60 2. katman). Seçili hedef yoksa öneri anlaşılır iletiyle REDDEDİLİR. Kimlik
kaybolunca / başka hedefe geçince sürüş durur (AII-2.1 korunur). Mühür onaydan SONRA güncellenmez. Kedi hattı (0 = Tüm Vücut)
DEĞİŞMEZ. `PEMF_ARASTIRMA_AIPRO` ürün varsayılanı KAPALI (Y145) — bu kapı bayrak AÇIK kolla sınar (kapalıyken öneri zaten 409).

KAPI: sahte EN ALT katta (`process_image` + doz modelinin `predict`'i — çağrılan koordinat kaydedilir); sağlayıcı (gerçek
`FantomSaglayici` takip / seçim), `/frame`, `/propose`, `/start`, `_predict_and_drive`, `_drive_coils_ai_pro` ve
`HardwareController` GERÇEK. ⚠️ Beklenen metin BURADA sabittir (ürün sabitinden okunmaz).
"""

from __future__ import annotations

import ai_pro_aparati as ap
import numpy as np
import pytest

P1, P2, P3 = (100.0, 100.0), (200.0, 100.0), (300.0, 100.0)
M1, M2, M3 = (-40.0, -60.0, 0.0), (-40.0, 0.0, 0.0), (-40.0, 60.0, 0.0)
SECILEMEDI = "Otomatik seçimde mühürlenecek hedef bulunamadı"


class _Bolge:
    def __init__(self, px, mm, alan, r=10):
        self.centroid_px, self.centroid_cabin_mm = px, mm
        self.organ_id, self.area_px, self.bbox_px = 1, alan, (px[0] - r, px[1] - r, 2 * r, 2 * r)
        self.E_cancer, self.E_healthy, self.tumor_id = 0.9, 0.1, ""


class _Sonuc:
    def __init__(self, bolgeler):
        self.success, self.error, self.method, self.mm_per_px = True, None, "aruco_pnp", 0.0
        self.pemf_valid, self.reliable, self.warnings = True, True, []
        self.pemf_source, self.coord_frame, self.layout = "aruco", "cabin_aruco", {}
        self.tumor_regions = [_Bolge(p, m, a) for p, m, a in bolgeler]
        self.phantom_detection = {"primary": {"solidity": 0.9, "n_blue_inside": 5}}


class _Hat:
    sonuc = None

    def __init__(self, cfg, **kw):
        self.cfg, self._predictor, self.yolo = cfg, None, None

    def process_image(self, frame, achieved_B=None, duty_sum=None):
        return _Hat.sonuc, {}

    def render_panels(self, ctx, result, lang="tr"):
        return {"07_combined": None}


class _Cfg:
    class phantom:  # noqa: N801
        achieved_B, duty_sum = 0.001, 2.4


class _Doz:
    """EN ALT doz katı: em_fantom `predictor.predict` — çağrıldığı koordinat kaydedilir (sürülen hedefin kanıtı)."""

    def __init__(self):
        self.cagri: list = []

    def predict(self, x, y, z, organ_id, achieved_B, duty_sum):
        self.cagri.append((x, y, z))
        return {**{f"D{i}": 0.3 for i in range(1, 8)}, **{f"P{i}": 0.0 for i in range(1, 8)}, "result_E_cancer": 0.5}


def _kare(bolgeler):
    _Hat.sonuc = _Sonuc(bolgeler)


_URUN: dict = {}


@pytest.fixture(autouse=True)
def _urun_sakla():
    from servers import ai_router as air

    _URUN.update(l=air._localize_organ, p=air._predict_and_drive)
    yield
    _URUN.clear()


@pytest.fixture
def o(monkeypatch, tmp_path):
    import servers.ai_pro_hedef as hedef
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    # Aparatın üst kat sahteleri kaldırılır: lokalizasyon ve doz GERÇEK sağlayıcıdan; sahte yalnız boru hattı + doz modeli.
    monkeypatch.setattr(ns.air, "_localize_organ", _URUN["l"])
    monkeypatch.setattr(ns.air, "_predict_and_drive", _URUN["p"])
    ns.doz = _Doz()
    cache = {"cls": _Hat, "cfg": _Cfg(), "predictor": ns.doz, "yolo": None, "yolo_path": "y.onnx"}
    monkeypatch.setattr(ns.air, "_get_or_load_model", lambda ad, y: cache)
    # Öneri ekranı XAI'si (hafif duyarlılık) bu kapının konusu değil ve doz modelini sarsılmış noktalarda çağırır → kapatılır.
    monkeypatch.setattr(hedef.FantomSaglayici, "xai_sensitivity", lambda self, *a, **k: None)
    monkeypatch.setattr(ns.air, "_ORGAN_LOCALIZE_INTERVAL_S", 0.0)  # her kare yeniden lokalize (kare yolu)
    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", "1")  # Y145: ürün varsayılanı KAPALI — kapı açık kolla sınar
    tekil = hedef.SAGLAYICILAR["fantom"]
    snap = {
        a: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v) for a, v in vars(tekil).items()
    }
    for a, v in vars(hedef.FantomSaglayici()).items():  # TAZE takip durumu (sıraya bağlı kalmasın — AII-2.1 R28 dersi)
        setattr(tekil, a, v)
    monkeypatch.setattr(ns.air, "_ai_hedef_modeli", "fantom")
    monkeypatch.setattr(ns.air, "_ai_organ_id", 0)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.c.post("/api/ai/pro/stop")
        if ns.hc is not None:
            ns.hc.stop_all_coils()
        ns.geri()
        for a in [a for a in vars(tekil) if a not in snap]:
            delattr(tekil, a)
        for a, v in snap.items():
            setattr(tekil, a, v)


def _oner(o, organ=0):
    return o.c.post("/api/ai/pro/propose", json={"organ_id": organ, "duration_minutes": 5, "model": "fantom"})


def _onayla_baslat(o, pid):
    from servers import ai_approval

    ai_approval.approve(pid, "arastirmaci@test.local")
    return o.c.post("/api/ai/pro/start", json={"proposal_id": pid})


def _hazirlik_karesi(o, bolgeler):
    _kare(bolgeler)
    o.air._ai_relocalize = True
    j = ap.kare(o).json()
    assert j.get("detected") is True, f"aparat: hazırlık karesi konumlanmadı: {j}"
    return j


def test_KRITIK_Y143_otomatik_oneri_SECILI_hedefin_KIMLIGINI_muhurler(o):
    _hazirlik_karesi(o, [(P1, M1, 100), (P2, M2, 300), (P3, M3, 200)])  # otomatik seçim: EN BÜYÜK odak = P2 (kimlik 2)
    r = _oner(o, 0)
    assert r.status_code == 200, r.text[:200]
    sp, me = r.json()["specs"], r.json()["meta"]
    assert sp["organ_id"] == 2, f"otomatik (0) öneri seçili hedefin kimliğini mühürlemedi: organ_id={sp['organ_id']!r}"
    assert sp["target_label"] == "Tümör 2", (
        f"onay ekranındaki etiket mühürlenen kimlikle uyuşmuyor: {sp['target_label']!r}"
    )
    assert me.get("otomatik_secim") is True, (
        f"mühür otomatik seçimden geldiğini söylemiyor: {me.get('otomatik_secim')!r}"
    )
    assert tuple(o.doz.cagri[-1]) == M2, f"öneri dozu seçili hedefin konumundan hesaplanmadı: {o.doz.cagri[-1]}"


def test_KRITIK_Y143_onaylanan_otomatik_seans_YALNIZ_muhurlu_kimligi_surer_ve_muhur_ONAYDAN_SONRA_degismez(o):
    _hazirlik_karesi(o, [(P1, M1, 100), (P2, M2, 300), (P3, M3, 200)])
    r = _oner(o, 0)
    assert r.status_code == 200, r.text[:200]
    pid = r.json()["proposalId"]
    # Öneri ile başlatma arasında otomatik seçim DEĞİŞİR (P3 büyüdü) — mühür onaylanan P2'de KALMALI.
    _hazirlik_karesi(o, [(P1, M1, 100), (P2, M2, 300), (P3, M3, 900)])
    s = _onayla_baslat(o, pid)
    assert s.status_code == 200, s.text[:200]
    with o.api._session_lock:
        assert o.api._active_session.get("onay_hedefi") == 2, (
            f"seans mührü onaylanan kimlik (2) değil: {o.api._active_session.get('onay_hedefi')!r}"
        )
    once = len(o.doz.cagri)
    # Seans: P3 hâlâ en büyük → otomatik seçim P3'ü seçerdi; mühürlü seans YALNIZ P2'yi sürer.
    _kare([(P1, M1, 100), (P2, M2, 300), (P3, M3, 900)])
    j = ap.kare(o).json()
    surulen = [tuple(c) for c in o.doz.cagri[once:]]
    assert j.get("driven") is True and surulen and all(c == M2 for c in surulen), (
        f"mühürlü otomatik seans onaylanmayan hedefi sürdü / sürmedi: driven={j.get('driven')} koordinatlar={surulen}"
    )


def test_KRITIK_Y143_muhurlu_kimlik_KAYBOLUNCA_baska_hedef_SURULMEZ(o):
    _hazirlik_karesi(o, [(P1, M1, 100), (P2, M2, 300), (P3, M3, 200)])
    pid = _oner(o, 0).json()["proposalId"]
    assert _onayla_baslat(o, pid).status_code == 200
    once = len(o.doz.cagri)
    _kare([(P1, M1, 100), (P3, M3, 900)])  # mühürlü P2 kayboldu
    j = ap.kare(o).json()
    assert j.get("driven") is not True and not o.doz.cagri[once:], (
        f"mühürlü kimlik kaybolunca başka hedef sürüldü: driven={j.get('driven')} {o.doz.cagri[once:]}"
    )


def test_KRITIK_Y143_secili_hedef_YOKKEN_otomatik_oneri_ANLASILIR_iletiyle_REDDEDILIR(o):
    import time

    # Konumlanmış görünen ama seçili hedef kimliği OKUNAMAYAN önbellek (eski biçim / kimlik düşmüş) → mühürlenecek hedef yok.
    o.air._ai_organ_cache.update(
        {
            "x_mm": -40.0,
            "y_mm": 0.0,
            "z_mm": 0.0,
            "reliability": 0.9,
            "localized": True,
            "at": time.time(),
            "organ_id": 0,
            "kedi_var": True,
            "model": "fantom",
            "target_label": "Tümör 2",
            "secili_id": None,
        }
    )
    r = _oner(o, 0)
    assert r.status_code == 409, f"seçili hedef yokken otomatik öneri verildi ({r.status_code}): {r.text[:200]}"
    assert SECILEMEDI in r.json().get("detail", ""), r.json()
    assert "elle seçin" in r.json().get("detail", ""), f"ret iletisi eylem söylemiyor: {r.json()}"


def test_KARSIT_Y143_elle_secilen_hedef_AYNEN_muhurlenir(o):
    o.air._ai_organ_id = 3
    _hazirlik_karesi(o, [(P1, M1, 100), (P2, M2, 300), (P3, M3, 200)])
    r = _oner(o, 3)
    assert r.status_code == 200 and r.json()["specs"]["organ_id"] == 3, r.text[:200]
    assert not r.json()["meta"].get("otomatik_secim")


def test_KARSIT_Y143_KEDI_tum_vucut_0_DEGISMEZ(o, monkeypatch):
    import time

    monkeypatch.setattr(o.air, "_predict_and_drive", lambda *a, **k: ([0.2] * 7, [0.0] * 7, 0.1))
    monkeypatch.setattr(o.air, "_ai_hedef_modeli", "kedi")
    o.air._ai_organ_cache.update(
        {
            "x_mm": 0.0,
            "y_mm": 0.0,
            "z_mm": 0.0,
            "reliability": 0.9,
            "localized": True,
            "at": time.time(),
            "organ_id": 0,
            "kedi_var": True,
            "model": "kedi",
        }
    )
    r = o.c.post("/api/ai/pro/propose", json={"organ_id": 0, "duration_minutes": 5})
    assert r.status_code == 200 and r.json()["specs"]["organ_id"] == 0, r.text[:200]
