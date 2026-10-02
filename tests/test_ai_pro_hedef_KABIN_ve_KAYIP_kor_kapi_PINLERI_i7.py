# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""İG-5.1 · D1.85 · 1-C bağımsız inceleme i7 — kabin denetimi ve hedef-kaybı STOP'unun KÖR noktalarına pinler.

i7 ölçtü: aşağıdaki mutantlar kapı + 68 dosyalık geniş kümede (666 test) YEŞİL kalıyordu:
  F-3 kabin yapılandırması OKUNAMAZKEN fail-OPEN (kabin dışı (30, −30, −30) cm ±300'e kısılıp sürülür — B-5.11'in kendisi)
  F-4 `/frame` istisna kolunda önbellek geçersiz kılınmaz → ÜRETİM aralığında (10 sn) "yeniden konumla" + istisnadan
      sonra eko kareler ESKİ hedefle sürer (kapı aralığı 0'a çektiği için önbellek okuması hiç sınanmıyordu)
  F-5 N mutant modülden okunuyordu (`_AI_LOST_STOP_STREAK = 6` yeşil) → burada N = 3 LİTERAL pinlenir
  F-6 teyitsiz hedef-kaybı STOP'unun operatöre bildirimi kapısızdı
  F-7 kabin boyutu doğrulaması (2 eleman / NaN / inf / 0 / negatif) ve sayı-olmayan koordinat (kabin merkezine sürülür)
Ürün DÜZELTMESİ (aynı commit setinde): F-8 kabin okunamazken operatöre EYLEM söyleyen bildirim (seans başına bir kez);
F-9 kabin içi ama em_kedi eğitim aralığı DIŞI x ∈ (300, 325] mm bandı kısılınca WARNING izi (Ö.4-Y9: YENİ kıskaç YOK).
GERÇEK `_extract_organ_target` / `ai_pro_hedef.hedef_kabin_disi_nedeni` / `kabin_yari_boyut_mm` ve GERÇEK `/frame`.
"""

from __future__ import annotations

import logging
import math

import ai_pro_aparati as ap
import pytest

N_PIN = 3  # ⚠️ ürünün sabitinden OKUNMAZ (i7-F-5) — İG-5.1'in değeri


def _hedef(koord_cm, rel=0.95):
    import servers.ai_router as air

    return air._extract_organ_target({2: {"coord_cabin_cm": list(koord_cm), "reliability": rel}}, 2, None)


def _uyari_var(caplog, *anahtar):
    return any(
        r.levelno >= logging.WARNING and all(a in r.getMessage().lower() for a in anahtar) for r in caplog.records
    )


def _yukleyici_yama(monkeypatch, *, hata=None, ext=None):
    from ai_hub.inference_cat_organ.lib import cabin_config as cc

    gercek = cc.load_cabin_config

    def _yeni(yol=None, *a, **k):
        if hata is not None:
            raise hata
        cfg = dict(gercek(yol, *a, **k))
        cfg["geometry"] = dict(cfg.get("geometry") or {}, cabin_extent_cm=ext)
        return cfg

    monkeypatch.setattr(cc, "load_cabin_config", _yeni)


# ── Kabin sınırı ve eksen sırası (yarı boyut (325, 250, 250) mm; [X genişlik, Y yükseklik, Z derinlik]) ──────────────
@pytest.mark.parametrize(
    ("koord_cm", "kabul"),
    [
        ((0.0, 25.0, 0.0), True),
        ((0.0, -25.0, 0.0), True),
        ((0.0, 0.0, 25.0), True),
        ((0.0, 0.0, -25.0), True),
        ((32.5, 0.0, 0.0), True),
        ((-32.5, 0.0, 0.0), True),
        ((0.0, 25.01, 0.0), False),
        ((0.0, 0.0, -25.01), False),
        ((32.51, 0.0, 0.0), False),
        ((-32.51, 0.0, 0.0), False),
        ((25.1, 25.0, 25.0), True),
        ((0.0, 32.0, 0.0), False),
        ((0.0, 0.0, 32.0), False),
    ],
)
def test_KRITIK_kabin_SINIRI_ve_EKSEN_sirasi(koord_cm, kabul):
    sonuc = _hedef(koord_cm)
    assert bool(sonuc[0]) is kabul, f"{koord_cm} cm → localized={sonuc[0]} (beklenen {kabul}) → {sonuc[1:4]}"


@pytest.mark.parametrize("koord", [[None, 0.0, 0.0], ["abc", 0.0, 0.0], [0.0, 0.0], [1e309, 0.0, 0.0], [math.nan] * 3])
def test_KRITIK_i7F7_SAYI_DEGIL_EKSIK_SONLU_DEGIL_koordinat_REDDEDILIR_ve_UYARILIR(koord, caplog):
    caplog.set_level(logging.WARNING)
    sonuc = _hedef(koord)
    assert sonuc[0] is False, f"{koord} KABUL edildi → {sonuc[1:4]}"
    assert _uyari_var(caplog, "kabin"), [r.getMessage() for r in caplog.records]


@pytest.mark.parametrize("koord_cm", [(10.0, -5.0, 3.0), (30.0, -30.0, -30.0), (0.0, 30.0, 0.0)])
def test_KRITIK_i7F3_KABIN_OKUNAMAZ_FAIL_CLOSED_her_hedef_REDDEDILIR(monkeypatch, koord_cm, caplog):
    caplog.set_level(logging.WARNING)
    _yukleyici_yama(monkeypatch, hata=OSError("kabin yaml okunamadı (test)"))
    sonuc = _hedef(koord_cm)
    assert sonuc[0] is False, f"kabin yapılandırması OKUNAMAZKEN {koord_cm} cm KABUL edildi (fail-open) → {sonuc[1:4]}"
    assert _uyari_var(caplog, "kabin"), [r.getMessage() for r in caplog.records]


@pytest.mark.parametrize(
    ("ext", "koord_cm"),
    [
        ([65.0, 50.0], (0.0, 0.0, 30.0)),
        ([65.0, math.nan, 50.0], (0.0, 30.0, 0.0)),
        ([65.0, math.inf, 50.0], (0.0, 30.0, 0.0)),
        ([65.0, 50.0, 0.0], (0.0, 0.0, 1.0)),
        ([65.0, -50.0, 50.0], (0.0, 1.0, 0.0)),
    ],
)
def test_KRITIK_i7F7_KABIN_BOYUTU_GECERSIZ_FAIL_CLOSED(monkeypatch, ext, koord_cm):
    _yukleyici_yama(monkeypatch, ext=ext)
    sonuc = _hedef(koord_cm)
    assert sonuc[0] is False, f"geçersiz kabin boyutu {ext} ile {koord_cm} cm KABUL edildi → {sonuc[1:4]}"


@pytest.mark.parametrize("x_cm", [30.5, 31.0, 32.5, -31.0, -32.5])
def test_KRITIK_i7F9_BANT_kabin_ici_egitim_disi_x_kiskaci_IZ_BIRAKIR(x_cm, caplog, monkeypatch):
    import servers.ai_router as air

    # İz hız sınırlıdır (organ + cm değeri başına 60 sn'de bir); aynı değerleri işleyen önceki testin sınırlayıcı durumu
    # bu ölçümü bastırmasın (ürün davranışı değil, testler arası sızıntı).
    monkeypatch.setattr(air, "_kiskac_iz_son", {})
    caplog.set_level(logging.DEBUG)
    sonuc = _hedef((x_cm, 0.0, 0.0))
    assert sonuc[0] is True, "aparat: kabin içi hedef reddedildi"
    gercek_mm = x_cm * 10.0
    kisildi = sonuc[1] != gercek_mm
    assert kisildi, "aparat: bant değeri kısılmadı (em_kedi ±300 kıskacı değişti mi?)"
    assert _uyari_var(caplog, "kısıl"), (
        f"x={gercek_mm} mm (kabin İÇİ, eğitim aralığı ±300 DIŞI) SESSİZCE {sonuc[1]} mm'ye kısıldı: WARNING izi yok. "
        f"Kayıtlar: {[(r.levelname, r.getMessage()[:60]) for r in caplog.records]}"
    )


# ── /frame: kabin seans ortasında okunamaz / hedef kabin dışına çıkar / operatöre eylem ────────────────────────────
class _SahteCatOrgan:
    def __init__(self, koord_cm):
        self.koord_cm = list(koord_cm)

    def predict(self, yol, render=True, target_oid=None):
        return {"organs": {2: {"coord_cabin_cm": list(self.koord_cm), "reliability": 0.95}}, "_overlay_bgr": None}


@pytest.fixture
def o_kabin(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    monkeypatch.setattr(ns.air, "_ORGAN_LOCALIZE_INTERVAL_S", 0.0)
    monkeypatch.setattr(ns.air, "_localize_organ", ns.air.ai_pro_hedef.saglayici_al("kedi").localize)
    monkeypatch.setattr(ns.air, "ai_service_enabled", lambda: False)
    ns.catorgan = _SahteCatOrgan((10.0, -5.0, 3.0))
    monkeypatch.setattr(ns.air, "_get_or_load_catorgan", lambda: ns.catorgan)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.geri()


@pytest.mark.parametrize("deneme", range(3))
def test_KRITIK_i7F3_FRAME_kabin_seans_ortasi_OKUNAMAZ_kayip_STOPu_ENGELLENMEZ(o_kabin, monkeypatch, deneme):
    o = o_kabin
    _pid, r = ap.onayli_baslat(o, organ=2)
    assert r.status_code == 200, r.text[:200]
    assert ap.kare(o).json().get("driven") is True and ap.calisan(o), "aparat: kabin içi hedef sürülmedi"
    _yukleyici_yama(monkeypatch, hata=OSError("kabin yaml okunamadı (test)"))
    for _ in range(N_PIN):
        ap.kare(o)
    assert ap.calisan(o) == [], f"kabin okunamazken {N_PIN} karede STOP yok: {ap.calisan(o)}"


@pytest.mark.parametrize("deneme", range(3))
def test_KRITIK_FRAME_surulen_hedef_KABIN_DISINA_cikinca_N_de_STOP(o_kabin, deneme):
    o = o_kabin
    _pid, r = ap.onayli_baslat(o, organ=2)
    assert r.status_code == 200, r.text[:200]
    assert ap.kare(o).json().get("driven") is True and ap.calisan(o)
    o.catorgan.koord_cm = [30.0, -30.0, -30.0]
    for _ in range(N_PIN):
        ap.kare(o)
    assert ap.calisan(o) == [], f"hedef kabin DIŞINA çıktıktan {N_PIN} kare sonra STOP yok: {ap.calisan(o)}"


def test_KRITIK_i7F8_kabin_OKUNAMAZ_OPERATORE_EYLEM_soyleyen_BILDIRIM(o_kabin, monkeypatch):
    o = o_kabin
    monkeypatch.setattr(o.air, "_kabin_okunamaz_bildirilen", {"anahtar": None})  # seans-başı sınırlayıcı sızmasın
    _pid, r = ap.onayli_baslat(o, organ=2)
    assert r.status_code == 200, r.text[:200]
    _yukleyici_yama(monkeypatch, hata=OSError("kabin yaml okunamadı (test)"))
    for _ in range(3):
        ap.kare(o)
    kabin = [m for m, _t in o.bildirim if "kabin" in m.lower()]
    assert kabin, (
        "kabin yapılandırması okunamıyor → HER hedef reddediliyor, ama operatöre yalnız 'hedef bulunamadı' gidiyor "
        f"(yönlendirme 'açıyı değiştirin' olur): bildirimler={[m for m, _t in o.bildirim]}"
    )
    assert len(kabin) == 1, f"kabin bildirimi her karede yineleniyor (seans başına bir kez olmalı): {kabin}"


# ── ÜRETİM lokalizasyon aralığı (10 sn, YAMALANMAZ): eko kareler (i7-F-4) ─────────────────────────────────────────
@pytest.fixture
def o_uretim(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    assert ns.air._ORGAN_LOCALIZE_INTERVAL_S >= 5.0, "aparat: üretim aralığı bekleniyordu"
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.geri()


def _yerellestirme(o, monkeypatch):
    durum = {"mod": "bulundu", "cagri": 0}

    def _lok(f, oid):
        durum["cagri"] += 1
        if durum["mod"] == "istisna":
            raise RuntimeError("pose: fantom karesi (test)")
        b = durum["mod"] == "bulundu"
        return (b, 10.0, 20.0, 30.0, 0.9 if b else 0.0, None, True)

    monkeypatch.setattr(o.air, "_localize_organ", _lok)
    return durum


@pytest.mark.parametrize("deneme", range(5))
def test_KRITIK_i7F4_URETIM_ARALIGI_yeniden_konumla_ISTISNASI_sonra_eko_kareler_ESKI_hedefle_SURMEZ(
    o_uretim, monkeypatch, deneme
):
    o = o_uretim
    durum = _yerellestirme(o, monkeypatch)
    _pid, r = ap.onayli_baslat(o)
    assert r.status_code == 200, r.text[:200]
    assert ap.kare(o).json().get("driven") is True and ap.calisan(o)
    assert o.c.post("/api/ai/pro/calibrate", json={}).status_code == 200
    durum["mod"] = "istisna"
    cagri_once = durum["cagri"]
    ap.kare(o)  # zorla lokalizasyon → istisna (yanıt 5xx)
    assert durum["cagri"] == cagri_once + 1, "aparat: yeniden konumla lokalizasyonu tetiklemedi"
    tahmin_once = o.tahmin.sayi
    for _ in range(N_PIN):
        ap.kare(o)  # eko kareleri (önbellek damgası taze → lokalizasyon YOK)
    assert durum["cagri"] == cagri_once + 1, "aparat: eko kareleri lokalize etti (aralık yamalı mı?)"
    assert o.tahmin.sayi == tahmin_once and ap.calisan(o) == [], (
        f"lokalizasyon istisnasından sonra eko kareleri ESKİ 'bulundu' ile sürdü ya da STOP yok: çalışan={ap.calisan(o)} "
        f"eko karelerinde doz tahmini={o.tahmin.sayi - tahmin_once}"
    )


@pytest.mark.parametrize("deneme", range(5))
def test_KRITIK_i7F4_URETIM_ARALIGI_kayip_lokalizasyonundan_sonra_eko_kareler_N_de_STOP(o_uretim, monkeypatch, deneme):
    o = o_uretim
    durum = _yerellestirme(o, monkeypatch)
    _pid, r = ap.onayli_baslat(o)
    assert r.status_code == 200, r.text[:200]
    assert ap.kare(o).json().get("driven") is True and ap.calisan(o)
    assert o.c.post("/api/ai/pro/calibrate", json={}).status_code == 200
    durum["mod"] = "kayip"
    ap.kare(o)  # zorla lokalizasyon → kayıp (1)
    for _ in range(N_PIN - 1):
        ap.kare(o)  # eko (2, 3)
    assert ap.calisan(o) == [], f"üretim aralığında {N_PIN} kayıp karesinde STOP yok: {ap.calisan(o)}"


# ── N = 3 LİTERAL (i7-F-5) ve teyitsiz kayıp STOP'unun bildirimi (i7-F-6) ────────────────────────────────────────────
@pytest.fixture
def o_kayip(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    monkeypatch.setattr(ns.air, "_ORGAN_LOCALIZE_INTERVAL_S", 0.0)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.geri()


def test_KRITIK_i7F5_kayip_STOPu_TAM_3_karede_gelir_2_karede_GELMEZ(o_kayip, monkeypatch):
    o = o_kayip
    durum = _yerellestirme(o, monkeypatch)
    _pid, r = ap.onayli_baslat(o)
    assert r.status_code == 200, r.text[:200]
    assert ap.kare(o).json().get("driven") is True and ap.calisan(o)
    durum["mod"] = "kayip"
    for _ in range(N_PIN - 1):
        ap.kare(o)
    assert ap.calisan(o), f"{N_PIN - 1} kayıp karesinde DURDURULDU (tek kare sekmesi tedaviyi keser)"
    ap.kare(o)
    assert ap.calisan(o) == [], f"kayıp STOP'u {N_PIN}. karede GELMEDİ (eşik {N_PIN} pinli): {ap.calisan(o)}"


@pytest.mark.parametrize("kayip_modu", ["kayip", "istisna"])
def test_KRITIK_i7F6_TEYITSIZ_hedef_kaybi_STOPu_OPERATORE_BILDIRILIR(o_kayip, monkeypatch, kayip_modu):
    o = o_kayip
    durum = _yerellestirme(o, monkeypatch)
    _pid, r = ap.onayli_baslat(o)
    assert r.status_code == 200, r.text[:200]
    assert ap.kare(o).json().get("driven") is True
    gercek = o.hc.update_coil

    def _teyitsiz_stop(coil_id, *a, start=True, **k):
        sonuc = gercek(coil_id, *a, start=start, **k)
        return sonuc if start else False  # STOP paketi kuyruğa VERİLEMEDİ (teyitsiz)

    monkeypatch.setattr(o.hc, "update_coil", _teyitsiz_stop)
    durum["mod"] = kayip_modu
    o.bildirim.clear()
    for _ in range(N_PIN):
        ap.kare(o)
    hata = [m for m, t in o.bildirim if t == "error" and "DOĞRULANAMADI" in m]
    assert hata, f"teyitsiz hedef-kaybı STOP'u operatöre BİLDİRİLMEDİ (bildirimler: {o.bildirim})"
    assert any("hedef-kayb" in m for m in hata), hata
