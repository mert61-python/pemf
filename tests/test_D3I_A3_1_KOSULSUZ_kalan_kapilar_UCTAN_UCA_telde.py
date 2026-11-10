# -*- coding: utf-8 -*-
"""D3I-A3.1 KAPI ADAYI (kalıcı) — Koşulsuz kip (Y189b) + AI Pro sürüşü: kalan kapılar GERÇEKTEN kesiyor mu?

Sahte olan YALNIZ: CV boru hattı sonucu (sağlayıcının `_pipeline_kur` / `_adaylar` / `_onbellek`), doz modeli (ap: duty 0,30),
görüntü çözümü, DB / yayın. GERÇEK: `/api/ai/pro/{propose,approve,start}`, `/api/ai/ai_pro/frame`, sağlayıcının `localize`
(PEMF kapısı + koşulsuz kolu + yöntem tavanı + kabin içi denetimi), `_muhur_surulebilir_mi`, `_drive_coils_ai_pro`,
`HardwareController` paket kurucusu (EN ALT kat: `core._hw_send_queue`, firmware aynasıyla çözülür).
Ölçüt: telde AI dozu (bobin 1-5 duty 0,30) gitti mi.
"""

from __future__ import annotations

import math
import types

import ai_pro_aparati as ap
import pytest
from kd_kalibrasyon_yardimci import (
    kd_gecerli_kalibrasyon,  # noqa: F401,E402  KD · Y259: kalibrasyon ön koşulu sağlanmış (bu dosya başka kuralı ölçer)
)


def _sonuc(*, pemf_valid=True, warnings=(), method="scale", success=True, reliable=False):
    return types.SimpleNamespace(
        success=success,
        error="" if success else "plate_not_found",
        method=method,
        mm_per_px=0.5,
        warnings=list(warnings),
        pemf_valid=pemf_valid,
        reliable=reliable,
        coord_frame="cabin_aruco" if pemf_valid else "",
        layout={},
    )


class _Hat:
    def __init__(self, sag):
        self.sag = sag

    def process_image(self, frame, **k):
        self.sag.hat_kosulsuz.append(getattr(self.sag, "kosulsuz", None))
        return self.sag.sonuc_fn(), {}


def _sahte_sinif(taban):
    class _S(taban):
        def __init__(self):
            super().__init__()
            self.sonuc_fn = lambda: _sonuc()
            self.hedef = (10.0, 20.0, 30.0)
            self.hat_kosulsuz = []

        def _onbellek(self):
            return {"cfg": None}

        def _pipeline_kur(self, cache):
            return _Hat(self)

        def _overlay(self, pl, ctx, result):
            return None

        def _egitim_araligi(self):
            raise RuntimeError("sonda: aralık yok")

        def _adaylar(self, result):
            x, y, z = self.hedef
            return [
                {
                    "px": (4.0, 4.0),
                    "bbox": (2, 2, 4, 4),
                    "x": x,
                    "y": y,
                    "z": z,
                    "organ_id": 1,
                    "reliability": 0.9,
                    "oncelik": 1.0,
                    "label": "",
                    "id": 0,
                }
            ]

    return _S


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc
    from servers import ai_pro_hedef as hedef
    from servers import ai_router as air

    gercek_lokalize = air._localize_organ
    ns = ap.kur(monkeypatch, tmp_path)
    # Lokalizasyon GERÇEK sağlayıcıya gider (ap kedi sahtesini kurmuştu).
    monkeypatch.setattr(air, "_localize_organ", gercek_lokalize)
    petri = _sahte_sinif(hedef.PetriSaglayici)()
    fantom = _sahte_sinif(hedef.FantomSaglayici)()
    monkeypatch.setitem(hedef.SAGLAYICILAR, "petri", petri)
    monkeypatch.setitem(hedef.SAGLAYICILAR, "fantom", fantom)
    monkeypatch.delenv("PEMF_ARASTIRMA_AIPRO", raising=False)
    monkeypatch.delenv("PEMF_ARASTIRMA_AIPRO_FANTOM", raising=False)
    ns.petri, ns.fantom = petri, fantom
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        for s in hedef.SAGLAYICILAR.values():
            hedef.kosulsuz_ayarla(s, False)
        ns.geri()


def _ai_dozu(o, once: int) -> list:
    return [d for d in ap.surus_paketleri(o, once) if any(abs(x - ap.D_AI) < 1e-6 for x in d[:5])]


def _muhurlu_baslat(o, model, *, kosulsuz, organ=1):
    """GERÇEK onay kaydı (öneri ucunu atlayarak — öneri kapısından bağımsız ölçmek için) + GERÇEK `/start`."""
    from servers import ai_approval

    spec = {"organ_id": organ, "duration_minutes": 5, "model": model}
    if kosulsuz:
        spec["kosulsuz"] = True
    rec = ai_approval.create("ai_pro", spec)
    ai_approval.approve(rec["id"], "hekim@test.local")
    return o.c.post("/api/ai/pro/start", json={"proposal_id": rec["id"], "client_id": ""})


def _kare_surdu_mu(o):
    o.air._ai_relocalize = True
    n = ap.paket_sayisi(o)
    j = ap.kare(o).json()
    return bool(_ai_dozu(o, n)), j


ENGELLI = ("control_cancer_missed: x", "oblique_view: y", "kuyu_skor_esigi: z")


# ── KARŞIT: aparat sürebiliyor (Y189b: koşulsuz + bayrak + pemf_valid + kabin içi → SÜRER) ─────────────────────────────


def test_KARSIT_kosulsuz_petri_bayrak_ACIK_engelli_sonuc_SURER(o, monkeypatch):
    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", "1")
    o.petri.sonuc_fn = lambda: _sonuc(warnings=ENGELLI, method="scale")  # yöntem tavanı 0,25 < MIN_GUVEN
    r = _muhurlu_baslat(o, "petri", kosulsuz=True)
    assert r.status_code == 200, r.text[:300]
    assert o.petri.kosulsuz is True
    surdu, j = _kare_surdu_mu(o)
    assert surdu and j.get("driven") is True, j


def test_kosullu_muhur_ayni_sonuc_SURMEZ(o, monkeypatch):
    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", "1")
    o.petri.sonuc_fn = lambda: _sonuc(warnings=ENGELLI, method="scale")
    r = _muhurlu_baslat(o, "petri", kosulsuz=False)
    assert r.status_code == 200, r.text[:300]
    assert o.petri.kosulsuz is False
    surdu, j = _kare_surdu_mu(o)
    assert not surdu and j.get("driven") is not True


def test_start_GOVDEDEKI_kosulsuz_YOK_SAYILIR(o, monkeypatch):
    from servers import ai_approval

    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", "1")
    o.petri.sonuc_fn = lambda: _sonuc(warnings=ENGELLI, method="scale")
    rec = ai_approval.create("ai_pro", {"organ_id": 1, "duration_minutes": 5, "model": "petri"})
    ai_approval.approve(rec["id"], "hekim@test.local")
    r = o.c.post("/api/ai/pro/start", json={"proposal_id": rec["id"], "kosulsuz": True})
    assert r.status_code == 200, r.text[:300]
    assert o.petri.kosulsuz is False, "gövdedeki kosulsuz mühürden ÖNCE geldi"
    surdu, _ = _kare_surdu_mu(o)
    assert not surdu


# ── KALAN kapılar koşulsuzda da KESER ──────────────────────────────────────────────────────────────────────────────────


def test_kosulsuz_pemf_valid_YOK_SURMEZ(o, monkeypatch):
    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", "1")
    o.petri.sonuc_fn = lambda: _sonuc(pemf_valid=False, warnings=ENGELLI)
    assert _muhurlu_baslat(o, "petri", kosulsuz=True).status_code == 200
    surdu, j = _kare_surdu_mu(o)
    assert not surdu and j.get("driven") is not True


def test_kosulsuz_basarisiz_sonuc_SURMEZ(o, monkeypatch):
    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", "1")
    o.petri.sonuc_fn = lambda: _sonuc(success=False)
    assert _muhurlu_baslat(o, "petri", kosulsuz=True).status_code == 200
    surdu, _ = _kare_surdu_mu(o)
    assert not surdu


@pytest.mark.parametrize(
    "hedef", [(1.0e5, 0.0, 0.0), (float("nan"), 0.0, 0.0), (0.0, float("inf"), 0.0), (0.0, 0.0, -9000.0)]
)
def test_kosulsuz_kabin_DISI_ya_da_sonsuz_hedef_SURMEZ(o, monkeypatch, hedef):
    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", "1")
    o.petri.hedef = hedef
    assert _muhurlu_baslat(o, "petri", kosulsuz=True).status_code == 200
    surdu, _ = _kare_surdu_mu(o)
    assert not surdu, f"kabin dışı / sonlu olmayan hedef {hedef} koşulsuzda SÜRÜLDÜ"


def test_kosulsuz_petri_BAYRAK_KAPALI_baslatma_409_ve_muhurlu_karede_SURMEZ(o, monkeypatch):
    o.petri.sonuc_fn = lambda: _sonuc(warnings=ENGELLI)
    r = _muhurlu_baslat(o, "petri", kosulsuz=True)
    assert r.status_code == 409, r.text[:200]
    # Mühür başka yoldan yazılmış olsa bile (sürüş-anı kapısı):
    from servers import ai_pro_hedef as hedef

    o.air._ai_hedef_modeli = "petri"
    o.air._ai_organ_id = 1
    hedef.kosulsuz_ayarla(o.petri, True)
    ap.muhurlu_seans_yaz(o.api, model="petri", onay_hedefi=1)
    surdu, _ = _kare_surdu_mu(o)
    assert not surdu


def test_kosulsuz_FANTOM_genel_bayrak_ACIK_fantom_bayragi_KAPALI_UCTAN_UCA_SURMEZ(o, monkeypatch):
    from servers import ai_pro_hedef as hedef

    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", "1")
    o.fantom.sonuc_fn = lambda: _sonuc(warnings=("layout_mismatch: x",), reliable=False)
    # (a) öneri: önizleme koşulsuz kipte taze konum bulmuş olsun
    o.air._ai_hedef_modeli = "fantom"
    o.air._ai_organ_id = 1
    hedef.kosulsuz_ayarla(o.fantom, True)
    o.air._ai_relocalize = True
    ap.kare(o)  # mühürsüz kare: önbelleği koşulsuz damgasıyla doldurur (sürmez)
    rp = o.c.post(
        "/api/ai/pro/propose", json={"organ_id": 1, "duration_minutes": 5, "model": "fantom", "kosulsuz": True}
    )
    assert rp.status_code == 409, rp.text[:200]
    # (b) başlatma (mühür doğrudan yazılmış onay)
    assert _muhurlu_baslat(o, "fantom", kosulsuz=True).status_code == 409
    # (c) sürüş anı (mühürlü seans başka yoldan)
    hedef.kosulsuz_ayarla(o.fantom, True)
    ap.muhurlu_seans_yaz(o.api, model="fantom", onay_hedefi=1)
    surdu, _ = _kare_surdu_mu(o)
    assert not surdu
    # (d) takma ad: model adı büyük harf / boşluklu
    rp2 = o.c.post(
        "/api/ai/pro/propose", json={"organ_id": 1, "duration_minutes": 5, "model": " FANTOM ", "kosulsuz": True}
    )
    assert rp2.status_code in (409, 422), rp2.text[:200]


def test_kosulsuz_ACIL_DURDUR_mandali_SURUSU_ENGELLER(o, monkeypatch):
    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", "1")
    o.petri.sonuc_fn = lambda: _sonuc(warnings=ENGELLI)
    assert _muhurlu_baslat(o, "petri", kosulsuz=True).status_code == 200
    surdu, _ = _kare_surdu_mu(o)
    assert surdu, "aparat: önce sürmeliydi"
    re = o.c.post("/api/hardware/emergency_stop")
    assert re.status_code == 200, re.text[:200]
    surdu2, _ = _kare_surdu_mu(o)
    assert not surdu2, "ACİL DURDUR sonrası koşulsuz seans yeniden enerjiledi"
    # mandal varken yeni koşulsuz başlatma da 409
    assert _muhurlu_baslat(o, "petri", kosulsuz=True).status_code == 409


def test_kosulsuz_HEDEF_KAYBINDA_STOP(o, monkeypatch):
    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", "1")
    durum = {"gecerli": True}
    o.petri.sonuc_fn = lambda: _sonuc(warnings=ENGELLI, pemf_valid=durum["gecerli"])
    assert _muhurlu_baslat(o, "petri", kosulsuz=True).status_code == 200
    surdu, _ = _kare_surdu_mu(o)
    assert surdu
    assert ap.calisan(o), "aparat: sürülen bobin çalışır görünmeli"
    durum["gecerli"] = False
    for _ in range(o.air._AI_LOST_STOP_STREAK):
        _kare_surdu_mu(o)
    assert not ap.calisan(o), (
        f"koşulsuzda hedef {o.air._AI_LOST_STOP_STREAK} kare kayıp — bobinler DURMADI: {ap.calisan(o)}"
    )


def test_oneri_KIP_UYUSMAZLIGI_409_iki_yonde(o, monkeypatch):
    from servers import ai_pro_hedef as hedef

    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", "1")
    o.petri.sonuc_fn = lambda: _sonuc(warnings=())
    o.air._ai_hedef_modeli = "petri"
    o.air._ai_organ_id = 1
    for onizleme, istek in ((True, False), (False, True)):
        hedef.kosulsuz_ayarla(o.petri, onizleme)
        o.air._ai_relocalize = True
        ap.kare(o)
        r = o.c.post(
            "/api/ai/pro/propose", json={"organ_id": 1, "duration_minutes": 5, "model": "petri", "kosulsuz": istek}
        )
        assert r.status_code == 409, (onizleme, istek, r.status_code, r.text[:200])
    hedef.kosulsuz_ayarla(o.petri, True)
    o.air._ai_relocalize = True
    ap.kare(o)
    r = o.c.post("/api/ai/pro/propose", json={"organ_id": 1, "duration_minutes": 5, "model": "petri", "kosulsuz": True})
    assert r.status_code == 200 and r.json()["specs"].get("kosulsuz") is True, r.text[:300]


def test_kosulsuz_NORMALIZASYON_dogrudan_cagri_FieldInfo_ve_dogruluk_nesneleri_ACMAZ(o):
    from fastapi import Form
    from servers import ai_pro_hedef as hedef

    from ai_hub.cv_ortak import pemf_kapisi

    for deger in (Form(False), Form(None), 1, "true", [1], object()):
        assert hedef.kosulsuz_ayarla(o.petri, deger) is False, repr(deger)
        k = pemf_kapisi.degerlendir(_sonuc(warnings=ENGELLI), model="petri", kosulsuz=deger)
        assert k["surulebilir"] is False and k["kosulsuz"] is False, repr(deger)
    assert hedef.kosulsuz_ayarla(o.petri, True) is True


def _hazirlik_409_SEANS_nedeniyle(r):
    """409 SEANS kapısından gelmeli — kamera seçimi (T2D-2) gibi daha önceki bir 409 kipi hiç sınamadan geçirir.
    (Seçili kamera conftest `_kabin_kamerasi_bugunku` ile; o fikstür kalkarsa bu satır KIRMIZI olur, kapı körleşmez.)"""
    from utils import ceviri

    anahtar = "ai.pro.hata.seansSurerkenHedef"
    assert r.status_code == 409, r.text[:200]
    assert r.json().get("detail") in {ceviri.t(anahtar, dil="tr"), ceviri.t(anahtar, dil="en")}, r.text[:200]


def test_hazirlik_SEANS_SURERKEN_kipi_DEGISTIREMEZ(o, monkeypatch):
    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", "1")
    o.petri.sonuc_fn = lambda: _sonuc(warnings=ENGELLI)
    assert _muhurlu_baslat(o, "petri", kosulsuz=False).status_code == 200
    r = o.c.post("/api/ai/pro/hazirlik/baslat", json={"organ_id": 1, "model": "petri", "kosulsuz": True})
    _hazirlik_409_SEANS_nedeniyle(r)
    # Ölçüt TELDE: KOŞULLU mühürlü seans engelli kareyi hazırlık isteğinden sonra da SÜRMEZ (bayrak durumu ikincil).
    surdu, _ = _kare_surdu_mu(o)
    assert not surdu, "seans sürerken hazırlık isteği KOŞULLU seansı koşulsuza çevirdi — engelli kare SÜRÜLDÜ"
    assert o.petri.kosulsuz is False
    # hazırlık durdur seans sürerken kipi sıfırlamaz / değiştirmez (koşullu kalır)
    o.c.post("/api/ai/pro/hazirlik/durdur")
    assert o.petri.kosulsuz is False


def test_hazirlik_KOSULSUZ_seans_surerken_kip_MUHURDEN_kalir_ve_durdur_SIFIRLAMAZ(o, monkeypatch):
    """Ters yön (Y189: kip MÜHÜRDEN): koşulsuz mühürlü seans sürerken hazırlık isteği (kosulsuz=False) ve hazırlık durdurma
    kipi DEĞİŞTİRMEZ — önceki testteki 'durdur sıfırlamaz' denetimi koşullu seansta False→False olduğu için boş kalıyordu."""
    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", "1")
    o.petri.sonuc_fn = lambda: _sonuc(warnings=ENGELLI)
    assert _muhurlu_baslat(o, "petri", kosulsuz=True).status_code == 200
    r = o.c.post("/api/ai/pro/hazirlik/baslat", json={"organ_id": 1, "model": "petri", "kosulsuz": False})
    _hazirlik_409_SEANS_nedeniyle(r)
    assert o.petri.kosulsuz is True, "seans sürerken hazırlık isteği mühürlü kipi DEĞİŞTİRDİ"
    o.c.post("/api/ai/pro/hazirlik/durdur")
    assert o.petri.kosulsuz is True, "seans sürerken hazırlık durdurma mühürlü kipi SIFIRLADI"
    surdu, _ = _kare_surdu_mu(o)
    assert surdu, "aparat: koşulsuz mühürlü seans (bayrak açık, kabin içi) sürmeliydi (Y189b)"
