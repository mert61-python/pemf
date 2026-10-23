# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""İG-5.1 + D1.85 · B-5.11 — `/frame`'de hedef KAYBI ve lokalizasyon İSTİSNASI STOP üretir; kabin DIŞI ya da sonlu
olmayan 3B hedef REDDEDİLİR (kedi hattı ve araştırma sağlayıcıları).

ÖLÇÜLEN KUSUR (aday doğrulaması D0, ayrı süreç + tel kaydı):
  * İG-5.1: seans aktifken `/frame` hedefi kaybedince (`localized:false`) else dalı YOK — 70 sn kedisiz karede telde
    159 duty>0 paket, STOP 0; son sürüşten 65,8 sn sonra hâlâ enerjili. Fantom karesinde lokalizasyon 500'e düşüyor
    (12/12), o yolda da STOP yok. Döngüde karşılığı var (`_AI_LOST_STOP_STREAK`), `/frame`'de yok.
  * D1.85: `_extract_organ_target`'in cm→mm ±300 kıskacı kabin DIŞI hedefi (kabin yarı boyutu [325, 250, 250] mm,
    kabin yapılandırmasından) sessizce kenara çekip SÜRÜYORDU (telde 51/51 çerçeve (300,-300,-300) mm, kısılan 35/35
    hücrede iz 0); NaN koordinat `localized=True` dönüyordu; araştırma sağlayıcısında sınır denetimi hiç yok.
SIRA (D0 §5-2): İG-5.1, D1.85'ten ÖNCE ya da AYNI sette — kabin dışı hedef `localized=False` olunca STOP'suz yol uyanırdı.
Y9 temiz: bu bir HEDEF GEÇERLİLİK (lokalizasyon) denetimi, tedavi doz kıskacı değil; `normalize_*` değişmez. STOP yalnız
artar (Ö.4-Y8); kayıp STOP'u seansı bitirmez — hedef yeniden bulununca sürüş sürer (döngü kuralıyla aynı).
"""

from __future__ import annotations

import logging
import math
import threading
import time

import ai_pro_aparati as ap
import numpy as np
import pytest


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    monkeypatch.setattr(ns.air, "_ORGAN_LOCALIZE_INTERVAL_S", 0.0)  # her kare lokalize edilsin (kayıp hemen görülsün)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.geri()


def _yerellestirme(o, monkeypatch):
    """`_localize_organ`'ı denetlenebilir yap: durum["mod"] ∈ {"bulundu", "kayip", "istisna"}."""
    durum = {"mod": "bulundu"}

    def _lok(f, oid):
        if durum["mod"] == "istisna":
            raise RuntimeError("pose: fantom karesi (test)")
        bulundu = durum["mod"] == "bulundu"
        return (bulundu, 10.0, 20.0, 30.0, 0.9 if bulundu else 0.0, None, True)

    monkeypatch.setattr(o.air, "_localize_organ", _lok)
    return durum


def _son_paket_sifir_mi(o) -> bool:
    from kayitci_donanim import paket_coz

    return not any(d > 0 for d in paket_coz(o.hc.core._hw_send_queue.paketler[-1])[0])


# ── İG-5.1: hedef kaybı ve lokalizasyon istisnası ─────────────────────────────────────────────────
@pytest.mark.parametrize("kayip_modu", ["kayip", "istisna"])
def test_KRITIK_IG51_frame_hedef_kaybinda_N_karede_STOP_ve_sonra_SURUS_YOK(o, monkeypatch, kayip_modu):
    durum = _yerellestirme(o, monkeypatch)
    _pid, r = ap.onayli_baslat(o)
    assert r.status_code == 200, r.text[:200]
    assert ap.kare(o).json().get("driven") is True, "aparat: hedef bulunmuşken /frame sürmedi"
    assert ap.calisan(o), "aparat: bobinler sürülmedi"
    durum["mod"] = kayip_modu
    n = o.air._AI_LOST_STOP_STREAK
    once = ap.paket_sayisi(o)
    for _ in range(n):
        ap.kare(o)  # istisna kolunda yanıt 5xx olabilir; ölçüt donanım
    assert ap.calisan(o) == [], f"{n} ardışık '{kayip_modu}' karesinden sonra bobinler hâlâ ÇALIŞIYOR: {ap.calisan(o)}"
    assert ap.paket_sayisi(o) > once and _son_paket_sifir_mi(o), f"'{kayip_modu}': hedef kaybında telde STOP yok"
    # STOP bobin başına gider (döngüyle aynı `_stop_session_coils`): ara paketlerde henüz durdurulmamış bobinler görünür.
    # Ölçüt STOP dizisi TAMAMLANDIKTAN sonrasıdır (son paket tüm-sıfır, yukarıda).
    stop_sonrasi = ap.paket_sayisi(o)
    for _ in range(3):
        ap.kare(o)
    assert not ap.surus_paketleri(o, stop_sonrasi), f"'{kayip_modu}': kayıp STOP'undan SONRA bobin yeniden sürüldü"


def test_KARSIT_IG51_hedef_yeniden_bulununca_SURUS_SURER_seans_bitmez(o, monkeypatch):
    durum = _yerellestirme(o, monkeypatch)
    _pid, r = ap.onayli_baslat(o)
    assert r.status_code == 200, r.text[:200]
    ap.kare(o)
    durum["mod"] = "kayip"
    for _ in range(o.air._AI_LOST_STOP_STREAK):
        ap.kare(o)
    durum["mod"] = "bulundu"
    j = ap.kare(o).json()
    assert j.get("driven") is True and ap.calisan(o), (
        "hedef yeniden bulununca sürüş SÜRMEDİ (kayıp STOP'u seansı öldürdü)"
    )
    with o.api._session_lock:
        assert o.api._active_session.get("is_active") is True


# ── D1.85: kabin sınırı + sonlu olmayan hedef (`_extract_organ_target`, GERÇEK) ──────────────────────
def _kabin_yari_mm() -> tuple:
    """Beklenen sınırlar ürünün kullandığı AYNI kabin yapılandırmasından (literal değil)."""
    from ai_hub.inference_cat_organ.lib.cabin_config import load_cabin_config, varsayilan_kabin_yaml

    ext = (load_cabin_config(varsayilan_kabin_yaml()).get("geometry") or {}).get("cabin_extent_cm")
    return tuple(float(v) * 10.0 / 2.0 for v in ext)


def test_ARAC_kabin_yapilandirmasi_beklenen_yari_boyut():
    # T2B (2026-10-23 ölçüsü): iç 55,5 × 35 × 40,5 cm (Oturum 13: 57 × 34 × 32; eski 65 × 50 × 50).
    assert _kabin_yari_mm() == (277.5, 175.0, 202.5), f"paketli kabin yapılandırması değişti: {_kabin_yari_mm()}"


@pytest.mark.parametrize(
    "koord_cm",
    [
        (0.0, 25.5, 0.0),  # y: 255 mm (eski kabinde ölçülen) > 175
        (30.0, -30.0, -30.0),  # telde 51/51 sürülen nokta (kıskaç öncesi): x/y/z kabin dışı
        (0.0, 17.6, 0.0),  # y sınırın hemen dışı (175 mm — T2B kabini)
        (0.0, 0.0, 20.3),  # z sınırın hemen dışı (202,5 mm)
        (27.8, 0.0, 0.0),  # x sınırın hemen dışı (277,5 mm)
        (math.nan, 0.0, 0.0),
        (0.0, math.inf, 0.0),
        (0.0, 0.0, -math.inf),
    ],
)
def test_KRITIK_D185_kabin_DISI_ya_da_SONLU_OLMAYAN_hedef_REDDEDILIR_ve_UYARILIR(koord_cm, caplog):
    import servers.ai_router as air

    caplog.set_level(logging.WARNING)
    organlar = {2: {"coord_cabin_cm": list(koord_cm), "reliability": 0.95}}
    sonuc = air._extract_organ_target(organlar, 2, None)
    assert sonuc[0] is False, f"kabin dışı / sonlu olmayan hedef {koord_cm} cm KABUL edildi → {sonuc[1:4]} mm"
    assert any(r.levelno >= logging.WARNING and "kabin" in r.getMessage().lower() for r in caplog.records), (
        f"red SESSİZ (WARNING yok): {[r.getMessage() for r in caplog.records]}"
    )


def test_KARSIT_D185_kabin_ICI_hedef_DEGISMEDEN_kabul():
    import servers.ai_router as air

    sonuc = air._extract_organ_target({2: {"coord_cabin_cm": [10.0, -5.0, 3.0], "reliability": 0.95}}, 2, None)
    assert sonuc[0] is True and sonuc[1:4] == (100.0, -50.0, 30.0), f"kabin içi hedef değişti: {sonuc[:4]}"


def test_KRITIK_D185_sinir_KABIN_YAPILANDIRMASINI_izler_LITERAL_degil(monkeypatch):
    """Kabin farklı ölçülürse (A-17: kabin #6 yeniden ölçülecek) sınır kendiliğinden izlemeli."""
    import servers.ai_router as air

    from ai_hub.inference_cat_organ.lib import cabin_config as cc

    gercek = cc.load_cabin_config

    def _dar(yol=None, *a, **k):
        cfg = gercek(yol, *a, **k)
        cfg = dict(cfg)
        cfg["geometry"] = dict(cfg.get("geometry") or {}, cabin_extent_cm=[40.0, 30.0, 20.0])
        return cfg

    monkeypatch.setattr(cc, "load_cabin_config", _dar)
    sonuc = air._extract_organ_target({2: {"coord_cabin_cm": [0.0, 16.0, 0.0], "reliability": 0.95}}, 2, None)
    assert sonuc[0] is False, "kabin yarı-Y 15 cm iken 16 cm'lik hedef kabul edildi (sınır yapılandırmadan okunmuyor)"


def test_KRITIK_D185_arastirma_saglayicisi_kabin_disi_hedefi_REDDEDER():
    from types import SimpleNamespace

    from servers import ai_pro_hedef

    class _Sahte(ai_pro_hedef._EmCvSaglayici):
        ad = "d185_sahte"
        kapi_modeli = (
            "fantom"  # AI-2: PEMF tüketim kapısı profili (sonuç aşağıda kapıdan GEÇER → sınanan bu testin kuralı)
        )

        def _onbellek(self):
            return {}

        def _pipeline_kur(self, cache):
            sonuc = SimpleNamespace(
                success=True,
                error="",
                method="aruco_pnp",
                mm_per_px=1.0,
                # AI-2: hocanın v3 sözleşmesinde GEÇERLİ sonuç — PEMF kapısı geçer, red/kabul BU testin eşiğinden gelir.
                pemf_valid=True,
                reliable=True,
                warnings=[],
            )
            return SimpleNamespace(process_image=lambda *a, **k: (sonuc, None))

        def _adaylar(self, result):
            return [{"reliability": 0.95, "x": 0.0, "y": 300.0, "z": 0.0, "px": (4.0, 4.0), "bbox": (0, 0, 8, 8)}]

        def _overlay(self, pl, ctx, result):
            return None

        def _egitim_araligi(self):
            return None

    sonuc = _Sahte().localize(np.zeros((8, 8, 3), dtype=np.uint8), 0)
    assert sonuc[0] is False, f"araştırma hattı kabin dışı hedefi (y=300 mm) KABUL etti: {sonuc[:4]}"


# ── D1.85: aynı girdiyle /frame ve döngüde sürüş YOK (GERÇEK _localize_organ_cpu + _extract_organ_target) ──
class _SahteCatOrgan:
    def __init__(self, koord_cm):
        self.koord_cm = list(koord_cm)

    def predict(self, yol, render=True, target_oid=None):
        return {"organs": {2: {"coord_cabin_cm": list(self.koord_cm), "reliability": 0.95}}, "_overlay_bgr": None}


@pytest.mark.parametrize(("koord_cm", "surulur"), [((30.0, -30.0, -30.0), False), ((10.0, -5.0, 3.0), True)])
def test_KRITIK_D185_frame_kabin_disi_hedefi_SURMEZ_kabin_ici_SURER(o, monkeypatch, koord_cm, surulur):
    monkeypatch.setattr(o.air, "_localize_organ", o.air.ai_pro_hedef.saglayici_al("kedi").localize)
    monkeypatch.setattr(o.air, "ai_service_enabled", lambda: False)
    monkeypatch.setattr(o.air, "_get_or_load_catorgan", lambda: _SahteCatOrgan(koord_cm))
    _pid, r = ap.onayli_baslat(o, organ=2)
    assert r.status_code == 200, r.text[:200]
    n = ap.paket_sayisi(o)
    j = ap.kare(o).json()
    assert bool(j.get("driven")) is surulur, f"{koord_cm} cm: driven={j.get('driven')} (beklenen {surulur})"
    assert bool(ap.surus_paketleri(o, n)) is surulur


class _SahteKamera:
    def __init__(self, *a, **k):
        pass

    def isOpened(self):
        return True

    def read(self):
        return True, np.zeros((8, 8, 3), dtype=np.uint8)

    def release(self):
        pass


def test_KRITIK_D185_DONGU_kabin_disi_hedefi_SURMEZ(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc
    from servers import ai_pro_hedef

    ns = ap.kur(monkeypatch, tmp_path, dongu_noop=False)
    try:
        monkeypatch.setattr(ns.air.cv2, "VideoCapture", _SahteKamera)
        monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", lambda self: None)
        monkeypatch.setattr(ns.air, "_localize_organ", ai_pro_hedef.saglayici_al("kedi").localize)
        monkeypatch.setattr(ns.air, "ai_service_enabled", lambda: False)
        monkeypatch.setattr(ns.air, "_get_or_load_catorgan", lambda: _SahteCatOrgan((30.0, -30.0, -30.0)))
        tur = threading.Event()
        gercek_tahmin = ns.air._predict_and_drive
        monkeypatch.setattr(ns.air, "_predict_and_drive", lambda *a: (tur.set(), gercek_tahmin(*a))[1])
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            _pid, r = ap.onayli_baslat(ns, organ=2)
            assert r.status_code == 200, r.text[:200]
            time.sleep(2.5)  # en az iki döngü turu (tur ≈ 1 sn)
            ns.c.post("/api/ai/pro/stop")
            ap.bekle(lambda: not ns.air._ai_loop_active, 5)
            assert not tur.is_set(), "kabin dışı hedefle döngü DOZ TAHMİNİNE geçti (localized=True kaldı)"
            assert not ap.surus_paketleri(ns, 0), "kabin dışı hedefle döngü bobinleri SÜRDÜ"
    finally:
        ns.air._ai_loop_active = False
        ns.geri()
