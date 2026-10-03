# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.86 · B-5.9 + D1.E07 · İG-5.80 · İG-5.15 · İG-5.76 · İG-5.29 — EM doz hattının girdi/çıktı dürüstlüğü.

KUSURLAR (D0 ölçümleri, bu dosya yeniden ölçer):
  * İG-5.80 / İG-5.15 — öngörücüler (fantom, petri, kedi `em_kedi`) NaN/None girdiyi REDDETMİYORDU: "makul görünen"
    sonlu bir D dönüyor, bobin bildirimsiz sürülüyordu. Bozuk ölçekleyici (ortalama NaN) de aynı sonucu veriyordu.
  * B-5.9 — GPU servisinin `/infer/em_kedi` ucu eksik girdiyi VARSAYILANLA dolduruyordu (`duty_sum` 2,0 — çekirdeğin
    1,5'i değil; `{}` → konum (0,0,0)) ve 200 dönüyordu: doz ölçeği sessizce 2×.
  * İG-5.15 (seans ortası) — doz modeli hata verince `_predict_and_drive` `[0]*7` döndürüyor, döngü/`/frame` bunu
    SÜRÜŞ olarak gönderiyordu (bildirimsiz; panel "sürüldü"). Artık sürülmez, operatöre söylenir, kayıp sayılır.
  * İG-5.76 — fantom CV PİKSEL kipinde (ölçek yok) piksel farkı mm sanılıp doz modeline veriliyor (+6,8σ) ve px² "mm²"
    etiketiyle gösteriliyordu. ArUco kipinde fiziksel alan bilinmezken `area_mm2 = 0.0` (sahte sıfır) yazılıyordu.
  * İG-5.29 — AI servisi yanıtında zaman aşımı OKUMA BAŞINA idi: her 2 sn'de 1 bayt gönderen servis isteği sınırsız
    uzatıyordu (ölçüldü: 20 sn'de tek istek bitmedi). Artık TOPLAM süre sınırı var (≤ 2T).

⚠️ Ö.4-Y9: hiçbiri doz kıskacı/tavanı değildir — geçersiz GİRDİ reddedilir, geçersiz sonuç sürülmez.
"""

from __future__ import annotations

import importlib
import json
import math
import socket
import threading
import time
from pathlib import Path

import numpy as np
import pytest

KOK = Path(__file__).resolve().parents[1]


def _sonlu_degil_mi(e: BaseException) -> bool:
    return type(e).__name__ == "SonluOlmayanGirdi" and isinstance(e, ValueError)


# ── İG-5.80 / İG-5.15: öngörücü sonlu olmayan girdiyi REDDEDER ─────────────────────────────────────────────────────


def _ongorucu(ad: str):
    """Gerçek öngörücü sınıfı + gerçek paketli ölçekleyiciler (ONNX yüklenmeden: `__new__`)."""
    import joblib

    if ad == "fantom":
        mod = importlib.import_module("ai_hub.inference_em_fantom.inference_em_fantom")
        cls, kok = mod.PhantomPredictor, KOK / "ai_hub" / "inference_em_fantom"
    elif ad == "kedi":
        mod = importlib.import_module("ai_hub.em_kedi.inference_em_kedi")
        cls, kok = mod.KediPredictor, KOK / "ai_hub" / "em_kedi"
    else:  # petri ölçekleyicileri depoda yok → aynı boyutlu (3 + 2 özellik) fantom ölçekleyicileri; kural ölçekten bağımsız
        mod = importlib.import_module("ai_hub.inference_em_petri.inference_em_petri")
        cls, kok = mod.PetriPredictor, KOK / "ai_hub" / "inference_em_fantom"
    p = cls.__new__(cls)
    p.sx = joblib.load(kok / "scaler_X.pkl")
    p.se = joblib.load(kok / "scaler_extra.pkl")
    p.sy = joblib.load(kok / "scaler_y.pkl")
    return p


_GECERLI = {"x": -43.6, "y": 0.0, "z": 0.0, "organ_id": 1, "achieved_B": 0.001, "duty_sum": 2.4}


@pytest.mark.parametrize("ad", ["fantom", "petri", "kedi"])
@pytest.mark.parametrize(
    ("alan", "deger"), [("x", math.nan), ("achieved_B", None), ("duty_sum", math.inf), ("z", None)]
)
def test_KRITIK_E07_ongorucu_SONLU_OLMAYAN_girdiyi_REDDEDER(ad, alan, deger):
    p = _ongorucu(ad)
    g = dict(_GECERLI, **{alan: deger})
    with pytest.raises(ValueError) as e:
        p._build_input(**g)
    assert _sonlu_degil_mi(e.value), (
        f"{ad}: {alan}={deger!r} için uç 422'ye eşleyemez (genel {type(e.value).__name__}: {e.value})"
    )


@pytest.mark.parametrize("ad", ["fantom", "petri", "kedi"])
def test_KRITIK_IG515_BOZUK_olcekleyici_NaN_doz_uretmez(ad):
    """Ölçekleyicinin ortalaması NaN (bozuk dosya) → ölçeklenmiş girdi NaN → REDDEDİLİR (eskiden "makul" D)."""
    import copy

    p = _ongorucu(ad)
    p.sx = copy.deepcopy(p.sx)
    p.sx.mean_ = np.full_like(p.sx.mean_, np.nan)
    with pytest.raises(ValueError) as e:
        p._build_input(**_GECERLI)
    assert _sonlu_degil_mi(e.value), e.value


@pytest.mark.parametrize(("ad", "n_cikti"), [("fantom", 23), ("petri", 23), ("kedi", 22)])
def test_KRITIK_IG515_model_CIKTISI_sonlu_degilse_REDDEDILIR(ad, n_cikti):
    p = _ongorucu(ad)

    class _NaNOturum:
        def run(self, *_a, **_k):
            return [np.full((1, n_cikti), np.nan, dtype=np.float32)]

    p.session, p.input_name = _NaNOturum(), "x"
    with pytest.raises(ValueError) as e:
        p.predict(**_GECERLI)
    assert _sonlu_degil_mi(e.value), e.value


def test_KARSIT_E07_gecerli_girdi_KABUL_edilir():
    for ad in ("fantom", "petri", "kedi"):
        X = _ongorucu(ad)._build_input(**_GECERLI)
        assert X.shape == (1, 6) and np.isfinite(X).all(), ad


# ── B-5.9: GPU servisi /infer/em_kedi eksik/sonlu olmayan girdiye 422 ───────────────────────────────────────────────


class _SahteKedi:
    session = None  # uç `_prov_dev(pred.session)` okur

    def __init__(self):
        self.cagri: list = []

    def predict(self, **k):
        self.cagri.append(k)
        return {**{f"D{i}": 0.2 for i in range(1, 8)}, **{f"P{i}": 0.0 for i in range(1, 8)}, "result_E": 0.01}


@pytest.fixture
def servis(monkeypatch):
    import ai_service.app as a

    sahte = _SahteKedi()
    monkeypatch.setattr(a.predictors, "get", lambda ad: sahte)
    monkeypatch.setattr(a, "_prov_dev", lambda s: "cpu")
    return a, sahte


@pytest.mark.parametrize(
    "govde",
    [
        {},
        {"x": 1.0, "y": 2.0, "z": 3.0, "organ_id": 1, "achieved_B": 0.001},  # duty_sum yok → eskiden 2,0 (1,5 değil)
        {"x": 1.0, "y": 2.0, "z": 3.0, "organ_id": 1, "duty_sum": 1.5},  # achieved_B yok
        {"x": "nan", "y": 2.0, "z": 3.0, "organ_id": 1, "achieved_B": 0.001, "duty_sum": 1.5},
        {"x": 1.0, "y": 2.0, "z": None, "organ_id": 1, "achieved_B": 0.001, "duty_sum": 1.5},
    ],
)
def test_KRITIK_D186_em_kedi_EKSIK_ya_da_sonlu_olmayan_girdiye_422(servis, govde):
    a, sahte = servis
    r = a.infer_em_kedi(dict(govde))
    assert getattr(r, "status_code", 200) == 422, (
        f"{govde} → {getattr(r, 'status_code', 200)} (varsayılanla doz üretildi)"
    )
    assert sahte.cagri == [], f"eksik/geçersiz girdiyle model çağrıldı: {sahte.cagri}"
    _eksik = [k for k in ("x", "y", "z", "organ_id", "achieved_B", "duty_sum") if k not in govde]
    if _eksik:  # eksik alan "eksik" diye söylenir (sonlu-değer denetimi de 422 verir ama nedeni yanlış adlandırır)
        hata = json.loads(r.body).get("error", "")
        assert "eksik girdi" in hata and _eksik[0] in hata, f"eksik alan doğru adlandırılmadı: {hata!r}"


def test_KARSIT_D186_em_kedi_TAM_girdiyle_calisir(servis):
    a, sahte = servis
    r = a.infer_em_kedi({"x": 1.0, "y": 2.0, "z": 3.0, "organ_id": 1, "achieved_B": 0.001, "duty_sum": 1.5})
    assert isinstance(r, dict) and r["status"] == "success", r
    assert sahte.cagri and sahte.cagri[0]["duty_sum"] == 1.5


# ── İG-5.76: fantom CV piksel kipinde doz YOK, alan px² ────────────────────────────────────────────────────────────


@pytest.fixture
def fantom_hatti(monkeypatch):
    """GERÇEK `PhantomCvPipeline.process_image` (6. adım: piksel→mm, alan, öngörücü çağrısı); algılama/segmentasyon
    sentetik bölgelerle (fantom test görüntüleri depoda izlenmiyor)."""
    from ai_hub.inference_em_fantom.phantom_cv import pipeline as pl
    from ai_hub.inference_em_fantom.phantom_cv.color_segment import PhantomDetection, Region

    maske = np.zeros((480, 640), np.uint8)
    fantom = PhantomDetection(
        centroid_px=(320.0, 240.0),
        area_px=40000,
        bbox_px=(220, 140, 200, 200),
        contour_px=np.zeros((4, 1, 2), np.int32),
        mask=maske,
        solidity=0.95,
        aspect_ratio=1.0,
        n_blue_inside=1,
        score=0.9,
    )
    tumor = Region(
        organ_id=1,
        label="tumor",
        centroid_px=(330.0, 230.0),
        area_px=167,
        bbox_px=(320, 220, 20, 20),
        contour_px=np.zeros((4, 1, 2), np.int32),
        mask=maske,
    )
    monkeypatch.setattr(pl, "find_phantoms", lambda *a, **k: [fantom])
    monkeypatch.setattr(pl, "segment_phantom", lambda *a, **k: {"tumor": [tumor], "healthy": []})
    monkeypatch.setattr(pl, "detect_aruco_marker", lambda *a, **k: None)

    class _KayitciOngorucu:
        def __init__(self):
            self.cagri = []

        def predict(self, **k):
            self.cagri.append(k)
            return {
                **{f"D{i}": 0.3 for i in range(1, 8)},
                **{f"P{i}": 0.0 for i in range(1, 8)},
                "result_E_healthy": 0.02,
                "result_E_cancer": 0.05,
                "result_E_avg": 0.035,
            }

    def _kos(**pkw):
        hat = pl.PhantomCvPipeline(None, manual_fallback=False, **pkw)
        hat._predictor = _KayitciOngorucu()
        sonuc, _ctx = hat.process_image(np.zeros((480, 640, 3), np.uint8))
        assert sonuc.success, sonuc.error
        return sonuc, hat._predictor

    return pl, _kos


def test_KRITIK_IG576_PIKSEL_kipinde_DOZ_hesaplanmaz_alan_mm2_SAYILMAZ(fantom_hatti):
    _pl, kos = fantom_hatti
    sonuc, ong = kos()
    assert sonuc.method == "pixel"
    assert ong.cagri == [], f"piksel kipinde piksel farkı mm sanılıp doz modeline verildi: {ong.cagri}"
    t = sonuc.tumor_regions[0]
    assert t.D == [] and t.E_cancer is None and t.E_healthy is None, (t.D, t.E_cancer, t.E_healthy)
    assert t.area_mm2 is None and t.area_px == 167, f"piksel alanı mm² diye etiketlendi: {t.area_mm2}"


def test_KARSIT_IG576_fantom_boyu_VERILINCE_doz_ve_mm2_hesaplanir(fantom_hatti):
    _pl, kos = fantom_hatti
    sonuc, ong = kos(phantom_length_cm=10.0)
    assert sonuc.method == "phantom_length" and ong.cagri, "ölçekli kipte doz hesaplanmalı"
    t = sonuc.tumor_regions[0]
    assert t.area_mm2 == pytest.approx(167 * sonuc.mm_per_px**2) and t.E_cancer == pytest.approx(0.05)


def test_KRITIK_IG576_ArUco_kipinde_bilinmeyen_alan_SIFIR_yazilmaz(fantom_hatti, monkeypatch):
    pl, kos = fantom_hatti

    class _Poz:
        marker_id = 0
        tvec = np.zeros((3, 1))
        reproj_error_px = 0.5

    monkeypatch.setattr(pl, "detect_aruco_marker", lambda *a, **k: type("M", (), {"corners_px": np.zeros((4, 2))})())
    monkeypatch.setattr(pl, "solve_cabin_pose", lambda *a, **k: _Poz())
    monkeypatch.setattr(pl, "pixel_to_cabin_mm", lambda px, *a, **k: np.array([-40.0, 1.0, 0.0]))
    sonuc, ong = kos()
    assert sonuc.method == "aruco_pnp" and ong.cagri, "aparat: ArUco kipinde doz hesaplanmalı"
    assert sonuc.tumor_regions[0].area_mm2 is None, (
        f"bilinmeyen fiziksel alan {sonuc.tumor_regions[0].area_mm2} yazıldı"
    )


# ── AI Pro: model hatası (sıfır doz) SÜRÜLMEZ ve bildirilir (İG-5.15 seans ortası) ──────────────────────────────────


def _sinif_yamasi_etkin(ai_pro_hedef):
    """Aparat bekçisi: sağlayıcı ÖRNEĞİNDE `predict` özniteliği olmamalı — varsa sınıf yaması gölgelenir ve kol gerçek
    modele gider (1-D'de ölçüldü: `test_ai_pro_model_muhru` örneğe bağlı metot sızdırıyordu; geniş kümede bu kollar
    yanlış nedenle kırmızı / yeşil oldu)."""
    for ad, sag in ai_pro_hedef.SAGLAYICILAR.items():
        assert "predict" not in vars(sag), f"aparat: '{ad}' sağlayıcı örneğine `predict` sızmış (önceki test)"


@pytest.fixture
def ap_ortam(monkeypatch, tmp_path):
    import ai_pro_aparati as ap
    from kayitci_donanim import gercek_hc
    from servers import ai_pro_hedef
    from servers import ai_router as air

    gercek_tahmin = air._predict_and_drive
    ns = ap.kur(monkeypatch, tmp_path)
    monkeypatch.setattr(ns.air, "_predict_and_drive", gercek_tahmin)  # GERÇEK zarf (hata → sıfır doz)

    def _patla(self, *a, **k):
        raise RuntimeError("doz modeli bozuk (test)")

    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "predict", _patla)
    _sinif_yamasi_etkin(ai_pro_hedef)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            ns.ap = ap
            yield ns
    finally:
        ns.air._ai_loop_active = False
        ns.geri()


def test_KRITIK_IG515_doz_modeli_HATA_verince_frame_SURMEZ_ve_BILDIRIR(ap_ortam):
    o, ap = ap_ortam, ap_ortam.ap
    _pid, r = ap.onayli_baslat(o, organ=2)
    assert r.status_code == 200, r.text[:200]
    n = ap.paket_sayisi(o)
    j = ap.kare(o).json()
    assert j.get("driven") is not True, f"doz modeli hata verdi ama kare 'sürüldü' dedi: {j.get('driven')}"
    yeni = o.hc.core._hw_send_queue.paketler[n:]
    from kayitci_donanim import paket_coz

    calisan = [i for p in yeni for i, d in enumerate(paket_coz(p)[0]) if d > 0]
    assert not o.ap.calisan(o), f"model hatasında bobin ÇALIŞIR durumda: {o.ap.calisan(o)} (paket {calisan})"
    assert any("doz modeli" in m for m, _t in o.bildirim), f"operatöre bildirim yok: {o.bildirim[-3:]}"


# ── İG-5.29: AI servisi yanıtında TOPLAM süre sınırı ───────────────────────────────────────────────────────────────


@pytest.fixture
def damla_sunucu():
    """Loopback (bekçi izinli) sahte AI servisi; kip istek yolunun ilk parçasından seçilir:
    /govde → 200 başlığı + her 0,2 sn'de 1 GÖVDE baytı · /baslik → BAŞLIK baytları 0,2 sn'de bir ·
    /hizli → anında 200 JSON · /red → anında 422 JSON. Damla kipleri okuma-başı zaman aşımını hep sıfırlar."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    port = srv.getsockname()[1]
    dur = threading.Event()

    def _damla(c, veri):
        for b in veri:
            if dur.is_set():
                return
            c.sendall(bytes([b]))
            time.sleep(0.2)

    def _hizmet(c):
        try:
            ilk = c.recv(65536).split(b" ", 2)[1]
            if ilk.startswith(b"/hizli"):
                g = b'{"tamam": 1}'
                c.sendall(
                    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n%s" % (len(g), g)
                )
            elif ilk.startswith(b"/red"):
                g = b'{"error": "gecersiz parametre"}'
                c.sendall(
                    b"HTTP/1.1 422 Unprocessable\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n%s"
                    % (len(g), g)
                )
            elif ilk.startswith(b"/baslik"):
                _damla(c, b"HTTP/1.1 200 OK\r\nX-Dolgu: " + b"a" * 400 + b"\r\n\r\n")
            else:
                c.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 100000\r\n\r\n")
                _damla(c, b" " * 100000)
            time.sleep(0.3)
        except OSError:
            pass
        finally:
            c.close()

    def _kabul():
        srv.settimeout(0.2)
        while not dur.is_set():
            try:
                c, _ = srv.accept()
            except OSError:
                continue
            threading.Thread(target=_hizmet, args=(c,), daemon=True).start()

    t = threading.Thread(target=_kabul, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    dur.set()
    srv.close()


def _ai_cagir(ac, cagri):
    import asyncio

    if cagri == "json_sync":
        return ac.delegate_json_sync("em_kedi", {"x": 1})
    if cagri == "infer_sync":
        return ac.delegate_infer_sync("cat_organ", bytes([0xFF, 0xD8, 0xFF, 0xD9]))
    if cagri == "json_async":
        return asyncio.run(ac.delegate_json("em_kedi", {"x": 1}))
    return asyncio.run(ac.delegate_infer("cat_organ", image_base64="/9j/2Q=="))


_CAGRILAR = ["json_sync", "infer_sync", "json_async", "infer_async"]


def _sureli_kos(fn, emniyet=8.0):
    kutu: dict = {}

    def _calis():
        t0 = time.monotonic()
        try:
            kutu["sonuc"] = fn()
        except Exception as e:  # noqa: BLE001 — beklenen: toplam süre aşımı
            kutu["hata"] = e
        kutu["gecen"] = time.monotonic() - t0

    t = threading.Thread(target=_calis, daemon=True)
    t.start()
    t.join(emniyet)  # test emniyeti: düzeltmesiz ürün damla serviste sonsuza dek bekler
    return t.is_alive(), kutu


@pytest.mark.parametrize("kip", ["govde", "baslik"])
@pytest.mark.parametrize("cagri", _CAGRILAR)
def test_KRITIK_IG529_damla_servis_TOPLAM_sureyi_ASAMAZ(damla_sunucu, monkeypatch, cagri, kip):
    import httpx
    from servers import ai_client as ac

    T = 1.0
    monkeypatch.setattr(ac, "AI_SERVICE_URL", f"{damla_sunucu}/{kip}")
    monkeypatch.setattr(ac, "_TIMEOUT", T)
    asili, kutu = _sureli_kos(lambda: _ai_cagir(ac, cagri))
    assert not asili, f"{cagri}/{kip}: damla serviste istek 8 sn'de BİTMEDİ (toplam süre sınırı yok)"
    assert "hata" in kutu, f"{cagri}/{kip}: istek hata vermeden bitti: {kutu}"
    assert kutu["gecen"] <= T + 0.8, f"{cagri}/{kip}: istek {kutu['gecen']:.1f} sn sürdü (toplam sınır T={T} sn)"
    assert isinstance(kutu["hata"], httpx.TimeoutException), (
        f"{cagri}/{kip}: süre aşımı {type(kutu['hata']).__name__} olarak yükseldi (çağıranlar zaman aşımı türünü bekler)"
    )
    assert "toplam süre" in str(kutu["hata"]), f"{cagri}/{kip}: hata nedeni söylemiyor: {kutu['hata']}"


@pytest.mark.parametrize("cagri", _CAGRILAR)
def test_KARSIT_IG529_hizli_servis_SONUC_doner_ve_422_GOVDESI_korunur(damla_sunucu, monkeypatch, cagri):
    import httpx
    from servers import ai_client as ac

    monkeypatch.setattr(ac, "_TIMEOUT", 1.0)
    monkeypatch.setattr(ac, "AI_SERVICE_URL", f"{damla_sunucu}/hizli")
    asili, kutu = _sureli_kos(lambda: _ai_cagir(ac, cagri))
    assert not asili and kutu.get("sonuc") == {"tamam": 1}, f"{cagri}: hızlı servis sonucu dönmedi: {kutu}"
    # Zamanlayıcı İPTAL edilmeli: edilmezse her çağrı T sn (varsayılan 180) yaşayan bir iş parçacığı bırakır — AI Pro
    # döngüsünde ~1 Hz çağrıyla yüzlerce uyuyan iş parçacığı birikir.
    # İNCELEME-2 i4-F-2: `cancel()` yalnız olayı kurar; zamanlayıcı iş parçacığı birkaç ms SONRA çıkar — ölçüldü: 300 hızlı
    # çağrının 8'inde dönüşten HEMEN sonra canlıydı (tam süitte yalancı kırmızı), 0,2 sn sonra 0. Kısa bekleme kolu
    # körleştirmez: İPTAL EDİLMEYEN zamanlayıcı T = 1 sn yaşar (yukarıda `_TIMEOUT` 1,0), 0,2 sn sonra hâlâ canlıdır.
    for _t in [t for t in threading.enumerate() if isinstance(t, threading.Timer)]:
        _t.join(0.2)
    _canli = [t for t in threading.enumerate() if isinstance(t, threading.Timer) and t.is_alive()]
    assert not _canli, f"{cagri}: başarılı çağrıdan sonra toplam-süre zamanlayıcısı hâlâ canlı: {_canli}"
    # Zamanlayıcı iptal edilmezse T sonra istemciyi kapatır; sonraki çağrının etkilenmediğini de göster.
    time.sleep(1.2)
    monkeypatch.setattr(ac, "AI_SERVICE_URL", f"{damla_sunucu}/red")
    asili, kutu = _sureli_kos(lambda: _ai_cagir(ac, cagri))
    hata = kutu.get("hata")
    assert isinstance(hata, httpx.HTTPStatusError), f"{cagri}: 422 HTTPStatusError olarak gelmedi: {kutu}"
    assert hata.response.json() == {"error": "gecersiz parametre"}, (
        "422 gövdesi okunamıyor (scratch 422 geçişi bozulur)"
    )


class _BozulanKedi:
    """İlk çağrı geçerli doz, sonrakiler model hatası (seans ORTASINDA bozulan model)."""

    def __init__(self):
        self.n = 0

    def __call__(self, saglayici, *a, **k):
        self.n += 1
        if self.n == 1:
            return [0.3] * 7, [0.0] * 7, 1.0
        raise RuntimeError("doz modeli seans ortasında bozuldu (test)")


def test_KRITIK_IG515_frame_seans_ORTASINDA_bozulan_model_N_karede_STOP(ap_ortam, monkeypatch):
    """Önceki geçerli doz keep-alive ile SÜRMEZ: model bozulunca hatalı kareler kayıp sayılır, N=3'te STOP."""
    from servers import ai_pro_hedef

    o, ap = ap_ortam, ap_ortam.ap
    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "predict", _BozulanKedi())
    _sinif_yamasi_etkin(ai_pro_hedef)
    _pid, r = ap.onayli_baslat(o, organ=2)
    assert r.status_code == 200, r.text[:200]
    assert ap.kare(o).json().get("driven") is True, "aparat: ilk kare geçerli dozla sürülmeliydi"
    assert ap.calisan(o), "aparat: ilk kareden sonra bobinler çalışmalı"
    for _ in range(3):
        ap.kare(o)
    assert not ap.calisan(o), (
        f"model 3 karedir hata veriyor ama önceki doz SÜRÜYOR: {ap.calisan(o)} (kayıp sayacı sıfırlanıyor)"
    )


def test_KRITIK_IG515_DONGU_seans_ORTASINDA_bozulan_model_N_turda_STOP(monkeypatch, tmp_path):
    """GERÇEK `_ai_pro_loop` (sahte kamera): aynı kural döngüde."""
    import ai_pro_aparati as ap
    from kayitci_donanim import gercek_hc
    from servers import ai_pro_hedef
    from servers import ai_router as air

    gercek_tahmin = air._predict_and_drive
    ns = ap.kur(monkeypatch, tmp_path, dongu_noop=False)
    try:
        monkeypatch.setattr(ns.air, "_predict_and_drive", gercek_tahmin)
        monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "predict", _BozulanKedi())
        monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", lambda self: None)
        _sinif_yamasi_etkin(ai_pro_hedef)

        class _Kamera:
            def __init__(self, *a, **k):
                pass

            def isOpened(self):  # noqa: N802
                return True

            def read(self):
                return True, np.zeros((8, 8, 3), dtype=np.uint8)

            def release(self):
                pass

        monkeypatch.setattr(ns.air.cv2, "VideoCapture", _Kamera)
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            _pid, r = ap.onayli_baslat(ns, organ=2)
            assert r.status_code == 200, r.text[:200]
            assert ap.bekle(lambda: bool(ap.calisan(ns)), 5), "aparat: döngü ilk geçerli dozla sürmedi"
            durdu = ap.bekle(lambda: not ap.calisan(ns), 6.0)
            ns.c.post("/api/ai/pro/stop")
            ap.bekle(lambda: not ns.air._ai_loop_active, 5)
        assert durdu, "döngü: model hata verirken önceki doz SÜRDÜ (N turda STOP gelmedi)"
        assert any("doz modeli" in m for m, _t in ns.bildirim), "döngü: operatöre doz hatası bildirilmedi"
    finally:
        ns.air._ai_loop_active = False
        ns.geri()


@pytest.fixture
def fantom_ucu(fantom_hatti, monkeypatch):
    from fastapi.testclient import TestClient
    from servers import ai_router as air
    from servers import api_server as api
    from servers import efield_live as ef

    from ai_hub.inference_em_fantom import inference_em_fantom as ief

    # ⚠️ render_panels GERÇEK: hesaplanmamış (None) E ile biçimlendirme çökmesi de bu uçta ölçülür.
    pl, _kos = fantom_hatti
    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    api.app.dependency_overrides[air.require_research] = lambda: None
    kutu = {"ong": None, "xai": []}
    monkeypatch.setattr(ief, "xai_hizli_sensitivity", lambda *a, **k: kutu["xai"].append(a) or {"sahte": 1})

    def _yukle(ad, yukleyici):
        return {"cls": pl.PhantomCvPipeline, "cfg": _kabin("inference_em_fantom.phantom_cv"), "predictor": kutu["ong"]}

    monkeypatch.setattr(air, "_get_or_load_model", _yukle)
    ef.set_context([])
    import base64

    govde = base64.b64encode(_renkli_jpg()).decode()
    try:
        yield TestClient(api.app), ef, kutu, govde
    finally:
        api.app.dependency_overrides.pop(air.require_research, None)
        ef.set_context([])


class _KayitciFantom:
    def __init__(self, hata=None):
        self.cagri, self.hata = [], hata

    def predict(self, **k):
        self.cagri.append(k)
        if self.hata is not None:
            raise self.hata
        return {
            **{f"D{i}": 0.3 for i in range(1, 8)},
            **{f"P{i}": 0.0 for i in range(1, 8)},
            "result_E_healthy": 0.02,
            "result_E_cancer": 0.05,
            "result_E_avg": 0.035,
        }


def test_KRITIK_IG576_em_fantom_PIKSEL_kipinde_canli_E_baglami_KURULMAZ(fantom_ucu):
    c, ef, kutu, govde = fantom_ucu
    kutu["ong"] = _KayitciFantom()
    r = c.post("/api/ai/vision/em_fantom", data={"image_base64": govde})
    assert r.status_code == 200, r.text[:200]
    assert r.json()["method"] == "pixel"
    assert ef.get_context() is None, f"piksel koordinatıyla canlı E bağlamı kuruldu: {ef.get_context()}"
    assert kutu["xai"] == [] and "xaiSensitivity" not in r.json(), "piksel kipinde XAI piksel koordinatıyla üretildi"
    t = r.json()["tumor_regions"][0]
    assert t["E_cancer"] is None and t["area_mm2"] is None, f"uç hesaplanmamış değeri sayı gibi döndü: {t}"


def test_KRITIK_E07_em_fantom_SONLU_OLMAYAN_girdiye_422(fantom_ucu):
    try:
        from ai_hub.em_girdi import SonluOlmayanGirdi
    except ImportError:  # düzeltme öncesi ağaç: modül yok; öngörücü hatası genel ValueError'dı

        class SonluOlmayanGirdi(ValueError):
            pass

    c, ef, kutu, govde = fantom_ucu
    kutu["ong"] = _KayitciFantom(hata=SonluOlmayanGirdi("sonlu olmayan girdi: achieved_B"))
    r = c.post("/api/ai/vision/em_fantom", data={"image_base64": govde, "phantom_length_cm": "10", "achieved_B": "nan"})
    assert r.status_code == 422, (
        f"sonlu olmayan girdi {r.status_code} döndü (istemci girdisi 422 olmalı): {r.text[:160]}"
    )


def test_KARSIT_E07_em_fantom_OLCEKLI_kipte_baglam_KURULUR(fantom_ucu):
    c, ef, kutu, govde = fantom_ucu
    kutu["ong"] = _KayitciFantom()
    r = c.post("/api/ai/vision/em_fantom", data={"image_base64": govde, "phantom_length_cm": "10"})
    assert r.status_code == 200 and r.json()["method"] == "phantom_length", r.text[:200]
    assert ef.get_context() is not None, "ölçekli kipte canlı E bağlamı kurulmalı (bar meşru)"
    assert kutu["xai"] and "xaiSensitivity" in r.json(), "ölçekli kipte XAI üretilmeli"


# ── D1.E07 ek: kabin YAML'ında sonlu olmayan değer YÜKLEMEDE reddedilir (İG-5.80 BİLİNMİYOR kolu) ──────────────────

_PROFILLER = ["inference_em_fantom.phantom_cv", "inference_petri_dish.petri_cv"]


@pytest.mark.parametrize("profil", _PROFILLER)
@pytest.mark.parametrize(
    "anahtar,deger,ad",
    [
        ("achieved_B", ".nan", "phantom.achieved_B"),
        ("duty_sum", ".inf", "phantom.duty_sum"),
        ("real_cm", ".nan", "aruco.real_cm"),
    ],
)
def test_KRITIK_E07_kabin_YAML_sonlu_olmayan_deger_YUKLEMEDE_reddedilir(tmp_path, profil, anahtar, deger, ad):
    mod = importlib.import_module(f"ai_hub.{profil}.cabin_config")
    satirlar = Path(mod.DEFAULT_CONFIG_YAML).read_text(encoding="utf-8").splitlines(keepends=True)
    hedef = [i for i, s in enumerate(satirlar) if s.lstrip().startswith(anahtar + ":")]
    assert len(hedef) == 1, f"aparat: '{anahtar}:' örnek YAML'da {len(hedef)} kez"
    i = hedef[0]
    girinti = satirlar[i][: len(satirlar[i]) - len(satirlar[i].lstrip())]
    satirlar[i] = f"{girinti}{anahtar}: {deger}" + chr(10)
    yol = tmp_path / "kabin.yaml"
    yol.write_text("".join(satirlar), encoding="utf-8")
    try:
        cfg = mod.load_cabin_config(yol)
    except ValueError as e:
        assert ad in str(e), f"hata bozuk anahtarı söylemiyor: {e}"
        return
    pytest.fail(f"{anahtar}: {deger} YÜKLENDİ (phantom={cfg.phantom}, aruco.real_cm={cfg.aruco.real_cm})")


@pytest.mark.parametrize("profil", _PROFILLER)
def test_KARSIT_E07_ornek_kabin_YAML_yuklenir(profil):
    mod = importlib.import_module(f"ai_hub.{profil}.cabin_config")
    cfg = mod.load_cabin_config(None)
    assert math.isfinite(cfg.phantom.achieved_B) and math.isfinite(cfg.phantom.duty_sum)


# ── D1.E07 ek: petri hattı PİKSEL kipinde doz hesaplamaz, alanı mm² saymaz (İG-5.76'nın petri kardeşi) ──────────────


def _renkli_kare():
    rng = np.random.default_rng(7)
    taban = np.dstack([np.full((480, 640), 40), np.full((480, 640), 140), np.full((480, 640), 210)])
    return np.clip(taban + rng.integers(-25, 25, taban.shape), 0, 255).astype(np.uint8)


def _renkli_jpg() -> bytes:
    import cv2 as _cv2

    ok, buf = _cv2.imencode(".jpg", _renkli_kare())
    assert ok
    return buf.tobytes()


class _KayitciDoz:
    session = None  # servis `_prov_dev(predictor.session)` okur

    def __init__(self, hata=None):
        self.cagri, self.hata = [], hata

    def predict(self, **k):
        self.cagri.append(k)
        if self.hata is not None:
            raise self.hata
        return {
            **{f"D{i}": 0.3 for i in range(1, 8)},
            **{f"P{i}": 0.0 for i in range(1, 8)},
            "result_E_healthy": 0.02,
            "result_E_cancer": 0.05,
            "result_E_avg": 0.035,
        }


@pytest.fixture
def petri_hatti(monkeypatch):
    """GERÇEK `PetriCvPipeline.process_image` (+ gerçek render); YOLO sahte (tek dairesel kuyu), ArUco yok."""
    import cv2 as _cv2

    from ai_hub.inference_petri_dish.petri_cv import pipeline as pp
    from ai_hub.inference_petri_dish.petri_cv.petri_detector import PetriDetection

    maske = np.zeros((480, 640), np.uint8)
    _cv2.circle(maske, (320, 240), 100, 255, -1)
    kont, _ = _cv2.findContours(maske, _cv2.RETR_EXTERNAL, _cv2.CHAIN_APPROX_NONE)
    kuyu = PetriDetection(
        bbox_xyxy=(220.0, 140.0, 420.0, 340.0),
        conf=0.9,
        mask=maske,
        contour=kont[0],
        centroid_px=(320.0, 240.0),
        area_px=int((maske > 0).sum()),
        radius_px=100.0,
    )

    class _Yolo:
        imgsz = 640

        def detect(self, img, conf=None, iou=None):
            return [kuyu]

    monkeypatch.setattr(pp, "PetriYoloDetector", lambda *a, **k: _Yolo())  # .pt ağırlığı depoda yok
    monkeypatch.setattr(pp, "detect_aruco_marker", lambda *a, **k: None)
    monkeypatch.setattr(pp._plaus, "evaluate", lambda *a, **k: (True, {}))

    def _kos(ong=None, **pkw):
        hat = pp.PetriCvPipeline(None, yolo_device="cpu", **pkw)
        hat.yolo = _Yolo()
        hat._predictor = ong or _KayitciDoz()
        sonuc, ctx = hat.process_image(_renkli_kare())
        assert sonuc.success, sonuc.error
        return hat, sonuc, ctx

    return pp, _kos, _Yolo


def test_KRITIK_IG576_petri_PIKSEL_kipinde_DOZ_hesaplanmaz_alan_mm2_SAYILMAZ(petri_hatti):
    _pp, kos, _y = petri_hatti
    hat, sonuc, ctx = kos()
    assert sonuc.method == "pixel"
    assert hat._predictor.cagri == [], f"piksel farkı mm sanılıp petri doz modeline verildi: {hat._predictor.cagri}"
    w = sonuc.wells[0]
    assert w.D == [] and w.E_cancer is None and w.E_healthy is None, (w.D, w.E_cancer, w.E_healthy)
    assert w.area_mm2 is None and w.area_px > 0, f"piksel alanı mm² diye etiketlendi: {w.area_mm2}"
    paneller = hat.render_panels(ctx, sonuc, lang="tr")  # GERÇEK render: None değerle çökmemeli
    assert "06_predictions" in paneller


def test_KARSIT_IG576_petri_capi_VERILINCE_doz_ve_mm2_hesaplanir(petri_hatti):
    _pp, kos, _y = petri_hatti
    hat, sonuc, ctx = kos(petri_diameter_cm=9.0)
    assert sonuc.method == "petri_diameter" and len(hat._predictor.cagri) == 1
    w = sonuc.wells[0]
    assert len(w.D) == 7 and w.E_cancer == 0.05 and w.area_mm2 and w.area_mm2 > 0
    hat.render_panels(ctx, sonuc, lang="tr")


def test_KRITIK_IG576_AI_Pro_petri_adayi_hesaplanmamis_E_SIFIR_yazmaz(petri_hatti):
    from servers import ai_pro_hedef

    _pp, kos, _y = petri_hatti
    _hat, sonuc, _ctx = kos()
    ad = ai_pro_hedef.PetriSaglayici()._adaylar(sonuc)
    assert ad and ad[0]["E_cancer"] is None and ad[0]["E_healthy"] is None, (
        f"hesaplanmamış E ölçülmüş 0 gibi aktarıldı: {ad[:1]}"
    )


@pytest.fixture
def petri_ucu(petri_hatti, monkeypatch):
    import base64

    from fastapi.testclient import TestClient
    from servers import ai_router as air
    from servers import api_server as api

    from ai_hub.inference_em_petri import inference_em_petri as iep

    pp, _kos, _Yolo = petri_hatti
    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    api.app.dependency_overrides[air.require_research] = lambda: None
    xai = []
    monkeypatch.setattr(iep, "xai_hizli_sensitivity", lambda *a, **k: xai.append(a) or {"sahte": 1})
    kutu = {"ong": _KayitciDoz()}

    def _yukle(ad, yukleyici):
        return {
            "cls": pp.PetriCvPipeline,
            "cfg": _kabin("inference_petri_dish.petri_cv"),
            "yolo_path": None,
            "yolo": _Yolo(),
            "predictor": kutu["ong"],
        }

    monkeypatch.setattr(air, "_get_or_load_model", _yukle)
    govde = base64.b64encode(_renkli_jpg()).decode()
    try:
        yield TestClient(api.app), kutu, govde, xai
    finally:
        api.app.dependency_overrides.pop(air.require_research, None)


def test_KRITIK_IG576_em_petri_PIKSEL_kipinde_XAI_URETILMEZ(petri_ucu):
    c, kutu, govde, xai = petri_ucu
    r = c.post("/api/ai/vision/em_petri", data={"image_base64": govde})
    assert r.status_code == 200, r.text[:200]
    j = r.json()
    assert j["method"] == "pixel" and j["wells"][0]["area_mm2"] is None and j["wells"][0]["E_cancer"] is None
    assert xai == [] and "xaiSensitivity" not in j, "piksel kipinde XAI piksel koordinatıyla üretildi"


def test_KARSIT_IG576_em_petri_OLCEKLI_kipte_XAI_uretilir(petri_ucu):
    c, kutu, govde, xai = petri_ucu
    r = c.post("/api/ai/vision/em_petri", data={"image_base64": govde, "petri_diameter_cm": "9"})
    assert r.status_code == 200, r.text[:200]
    assert r.json()["method"] == "petri_diameter" and xai, "ölçekli kipte XAI üretilmeli"


def test_KRITIK_E07_em_petri_SONLU_OLMAYAN_girdiye_422(petri_ucu):
    try:
        from ai_hub.em_girdi import SonluOlmayanGirdi
    except ImportError:  # düzeltme öncesi ağaç

        class SonluOlmayanGirdi(ValueError):
            pass

    c, kutu, govde, _xai = petri_ucu
    kutu["ong"] = _KayitciDoz(hata=SonluOlmayanGirdi("sonlu olmayan girdi: achieved_B"))
    r = c.post("/api/ai/vision/em_petri", data={"image_base64": govde, "petri_diameter_cm": "9", "achieved_B": "nan"})
    assert r.status_code == 422, f"sonlu olmayan girdi {r.status_code} döndü: {r.text[:160]}"


# ── GPU servisi paritesi (fantom + petri): piksel kipinde XAI yok, sonlu olmayan girdi 422 ─────────────────────────


class _Dosya:
    def __init__(self, b: bytes):
        import io

        self.file = io.BytesIO(b)
        self.filename = "kare.jpg"


@pytest.fixture
def servis_cv(fantom_hatti, petri_hatti, monkeypatch):
    import ai_service.app as a
    from ai_hub.inference_em_fantom import inference_em_fantom as ief
    from ai_hub.inference_em_petri import inference_em_petri as iep

    pl, _fk = fantom_hatti
    pp, _pk, _Yolo = petri_hatti
    xai = []
    monkeypatch.setattr(ief, "xai_hizli_sensitivity", lambda *a, **k: xai.append("fantom") or {"sahte": 1})
    monkeypatch.setattr(iep, "xai_hizli_sensitivity", lambda *a, **k: xai.append("petri") or {"sahte": 1})
    monkeypatch.setattr(a, "_prov_dev", lambda s: "cpu")
    kutu = {"ong": _KayitciDoz()}

    def _al(ad):
        if ad == "em_fantom":
            return {
                "cls": pl.PhantomCvPipeline,
                "cfg": _kabin("inference_em_fantom.phantom_cv"),
                "predictor": kutu["ong"],
            }
        return {
            "cls": pp.PetriCvPipeline,
            "cfg": _kabin("inference_petri_dish.petri_cv"),
            "yolo_path": None,
            "yolo": _Yolo(),
            "predictor": kutu["ong"],
        }

    monkeypatch.setattr(a.predictors, "get", _al)
    return a, kutu, xai


def _servis_cagir(a, uc, olcek=None, **k):
    if uc == "em_fantom":
        return a.infer_em_fantom(file=_Dosya(_renkli_jpg()), phantom_length_cm=olcek, achieved_B=None, duty_sum=None)
    bos = dict.fromkeys(
        ["yolo_conf", "yolo_iou", "resize_max", "plaus_circularity", "plaus_conf", "plaus_area_frac", "plaus_guard"]
    )
    return a.infer_em_petri(file=_Dosya(_renkli_jpg()), petri_diameter_cm=olcek, achieved_B=None, duty_sum=None, **bos)


def _govde(r):
    import json as _json

    return (getattr(r, "status_code", 200), r if isinstance(r, dict) else _json.loads(r.body))


@pytest.mark.parametrize("uc", ["em_fantom", "em_petri"])
def test_KRITIK_IG576_servis_PIKSEL_kipinde_XAI_URETILMEZ(servis_cv, uc):
    a, _kutu, xai = servis_cv
    kod, j = _govde(_servis_cagir(a, uc))
    assert kod == 200 and j.get("method") == "pixel", (kod, str(j)[:200])
    assert xai == [] and "xaiSensitivity" not in j, f"servis ({uc}) piksel kipinde XAI üretti"


@pytest.mark.parametrize("uc,olcek", [("em_fantom", 10.0), ("em_petri", 9.0)])
def test_KRITIK_E07_servis_SONLU_OLMAYAN_girdiye_422(servis_cv, uc, olcek):
    try:
        from ai_hub.em_girdi import SonluOlmayanGirdi
    except ImportError:  # düzeltme öncesi ağaç

        class SonluOlmayanGirdi(ValueError):
            pass

    a, kutu, _xai = servis_cv
    kutu["ong"] = _KayitciDoz(hata=SonluOlmayanGirdi("sonlu olmayan girdi: achieved_B"))
    kod, j = _govde(_servis_cagir(a, uc, olcek))
    assert kod == 422, f"servis ({uc}) sonlu olmayan girdiye {kod} döndü: {str(j)[:160]}"


@pytest.mark.parametrize("uc,olcek", [("em_fantom", 10.0), ("em_petri", 9.0)])
def test_KARSIT_E07_servis_OLCEKLI_kipte_XAI_uretilir(servis_cv, uc, olcek):
    a, _kutu, xai = servis_cv
    kod, j = _govde(_servis_cagir(a, uc, olcek))
    assert kod == 200 and xai, (kod, str(j)[:200])


def _kabin(profil):
    """Örnek kabin yapılandırması (uçlar XAI taban noktasını `cfg.phantom`dan okur)."""
    return importlib.import_module(f"ai_hub.{profil}.cabin_config").load_cabin_config(None)
