# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.61 · B-5.7 + İG-5.83 · D1.76 · B-1.24 · B-1.25 · B-1.26 — canlı E-alanı ve ölçülen alan gösterimi DÜRÜST.

Plan C1-45: iki madde AYNI `efield_live.set_context` bağlamını düzeltir → TEK değişiklik.

KUSURLAR (plan / D0 ölçümleri):
  * B-5.7 / B-1.25 — fantom analizinin kurduğu canlı E bağlamı (tümör konumu) yalnız AI Pro durdurmada temizleniyordu;
    sonraki ELLE ya da KEDİ seansında E barı başka hedefin E'sini "● canlı" gösteriyordu.
  * B-1.24 — vekil modele giden `achieved_B`, çalışan TÜM bobinlerin `magneticMt` ortalamasıydı; ölçülmeyen bobinlerin
    0.0 başlangıç değeri ortalamayı düşürüyordu (7 bobin çalışıyor, yalnız bobin 6 ölçüyor 1,842 mT → 0,263 mT).
  * İG-5.83 — model `achieved_B` için dar bir aralıkta eğitildi (fantom 0,984–1,029 mT, referans örneklemden OKUNUR);
    aralık dışında anlamsız E üretiyordu ve bar onu sayı olarak gösteriyordu. Artık '—' (Y6: ölçülmeyen/geçersiz sayı yok).
  * B-1.26 — seans alan kaydının son/zirve değeri seans bitince sıfırlanmıyordu: CSV'siz (AI) ya da CSV'si açılamayan
    sonraki seansta önceki seansın 7,5 mT tepesi o seansın "ölçülen yoğunluğu" gibi görünüyordu.
  * (D1.67 açık-2) — alan sensörü susunca seans kartındaki ANLIK ölçülen yoğunluk son değerde kalıyordu.

⚠️ YALNIZ GÖSTERİM: hiçbir kol sürüşü/dozu değiştirmez; yeni kıskaç/tavan/red YOK (Ö.4-Y9).
"""

from __future__ import annotations

import time as _gercek_zaman

import ai_pro_aparati as ap
import pytest


class _ModulSaati:
    def __init__(self):
        self.ek = 0.0

    def monotonic(self):
        return _gercek_zaman.monotonic() + self.ek

    def __getattr__(self, ad):
        return getattr(_gercek_zaman, ad)


class _Olay:
    def __init__(self, govde: dict):
        self.event_type = "hardware.stm.telemetry"
        self.data = govde


def _baglam(ef, model=None):
    ef.set_context([{"centroid_cabin_mm": [-43.6, 0.0, 0.0], "organ_id": 1}], model=model)
    assert ef.get_context() is not None, "aparat: bağlam kurulamadı"


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc
    from servers import efield_live as ef

    ns = ap.kur(monkeypatch, tmp_path)
    ef.set_context([])
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            ns.ef = ef
            yield ns
    finally:
        ef.set_context([])
        ns.air._ai_loop_active = False
        ns.geri()


_ELLE = {"coil_ids": [1, 2], "frequency": 100, "duty": 40, "phase": 0, "duration_minutes": 5, "mode": "Manuel"}


# ── D1.61 / B-1.25: bağlam seansa bağlı ──────────────────────────────────────────────────────────────────────────────


def test_KRITIK_D161_elle_seans_BASLAYINCA_fantom_baglami_TEMIZLENIR(o):
    _baglam(o.ef)
    r = o.c.post("/api/session/start", json=_ELLE)
    assert r.status_code == 200, r.text[:200]
    assert o.ef.get_context() is None, (
        "elle seansta fantom tümörünün E bağlamı duruyor — bar başka hedefin E'sini gösterir"
    )
    assert o.c.get("/api/dashboard-snapshot").json().get("eField") is None


def test_KRITIK_D161_kedi_AI_Pro_BASLAYINCA_fantom_baglami_TEMIZLENIR(o):
    _baglam(o.ef)
    _pid, r = ap.onayli_baslat(o, organ=2)
    assert r.status_code == 200, r.text[:200]
    assert o.ef.get_context() is None, "kedi AI Pro seansında fantom tümörünün E bağlamı duruyor"


def test_KRITIK_D161_seans_DURDURUNCA_baglam_TEMIZLENIR(o):
    assert o.c.post("/api/session/start", json=_ELLE).status_code == 200
    _baglam(o.ef)  # seans sürerken yapılan bir analiz
    assert o.c.post("/api/session/stop").status_code == 200
    assert o.ef.get_context() is None and o.ef.get_live() is None


def test_KRITIK_D161_ACIL_DURDUR_baglami_TEMIZLER(o):
    _baglam(o.ef)
    assert o.c.post("/api/hardware/emergency_stop", json={}).status_code == 200
    assert o.ef.get_context() is None and o.ef.get_live() is None


@pytest.mark.parametrize(
    ("baglam_modeli", "seans_modeli", "kalir"),
    [(None, "fantom", True), ("petri", "petri", True), ("fantom", "petri", False), (None, "kedi", False)],
)
def test_KARSIT_D161_arastirma_seansi_KENDI_modelinin_baglamini_KORUR(o, baglam_modeli, seans_modeli, kalir):
    """KARŞIT: aynı modelin araştırma AI Pro seansı bağlamı korur (bar orada meşru); farklı model/kedi temizler.
    Analiz ucu bağlamı modelsiz kurar → fantom vekili (efield_live varsayılanı)."""
    _baglam(o.ef, baglam_modeli)
    o.api.start_ai_session(
        0.0,
        0.0,
        5,
        range(1, 8),
        f"AI Pro · {seans_modeli}",
        tur="ai_pro",
        onay_kimligi="t",
        surus_nesli=0,
        model=seans_modeli,
        onay_hedefi=0,
    )
    assert (o.ef.get_context() is not None) is kalir, (baglam_modeli, seans_modeli, o.ef.get_context())


# ── D1.76 a / B-1.24: achieved_B yalnız alanı ÖLÇÜLEN bobinlerden ─────────────────────────────────────────────────────


def test_KRITIK_D176a_achieved_B_YALNIZ_alani_OLCULEN_bobinlerden(o):
    api = o.api
    api._handle_backend_event(_Olay({"coil_id": 6, "magnetic_field": 1.842}))
    with api._live_state_lock:
        for i in range(7):
            api._live_state["coils"][i]["running"] = True
            api._live_state["coils"][i]["dutyCycle"] = 30
    try:
        b, duty, n = o.ef.telemetry_inputs(api._build_ws_snapshot()["coils"])
    finally:
        with api._live_state_lock:
            for i in range(7):
                api._live_state["coils"][i]["running"] = False
    assert n == 7 and duty == pytest.approx(2.1)
    assert b == pytest.approx(1.842e-3), (
        f"achieved_B {b} T — ölçülmeyen 6 bobinin 0.0'ı ortalamaya girdi (beklenen yalnız bobin 6: 1,842 mT)"
    )


def test_KRITIK_D176a_alan_HIC_olculmuyorsa_E_HESAPLANMAZ(o, monkeypatch):
    _baglam(o.ef)
    cagri = []
    monkeypatch.setattr(o.ef, "_predictor", lambda model=None: _SahteVekil(cagri))
    v = o.ef.compute([{"running": True, "magneticMt": 0.0, "dutyCycle": 30, "measuredFields": []}])
    assert v is not None and v["cancer"] is None and v["healthy"] is None, v
    assert cagri == [], "ölçülmeyen alanla vekil model çağrıldı (0.0 'ölçüldü' sayıldı)"
    # Ayırt edici etki (katman maskesi: B=0,0 eğitim aralığı dışı olduğundan E yine '—' olurdu): B ÖLÇÜLMEDİ — arayüz
    # "B=0,00 mT" (ölçüldü, sıfır) değil "alan ölçülmüyor" demeli.
    assert v["achievedB_T"] is None and v.get("bOlculmuyor") is True and not v.get("egitimAraligiDisi"), v


# ── İG-5.83: eğitim B aralığı dışında E '—' ───────────────────────────────────────────────────────────────────────────


class _SahteVekil:
    def __init__(self, kayit):
        self.kayit = kayit

    def predict(self, x, y, z, organ_id, achieved_B, duty_sum):
        self.kayit.append(achieved_B)
        return {"result_E_healthy": 0.021, "result_E_cancer": 0.055, "result_E_avg": 0.038}


@pytest.mark.parametrize("b_mt", [0.0, 0.5, 2.0, 24.6])
def test_KRITIK_IG583_egitim_B_araligi_DISINDA_E_GOSTERILMEZ(o, monkeypatch, b_mt):
    _baglam(o.ef)
    cagri = []
    monkeypatch.setattr(o.ef, "_predictor", lambda model=None: _SahteVekil(cagri))
    v = o.ef.compute([{"running": True, "magneticMt": b_mt, "dutyCycle": 30, "measuredFields": ["magneticMt"]}])
    assert v is not None, "aparat: compute None döndü"
    assert v["cancer"] is None and v["healthy"] is None and v["avg"] is None, (
        f"B={b_mt} mT eğitim aralığı dışında ama E sayı olarak üretildi: {v}"
    )
    assert v.get("egitimAraligiDisi") is True, v
    assert v["achievedB_T"] == pytest.approx(b_mt / 1000.0), "B şeffaflık alanı korunmalı"


def test_KARSIT_IG583_egitim_araliginda_E_URETILIR(o, monkeypatch):
    _baglam(o.ef)
    cagri = []
    monkeypatch.setattr(o.ef, "_predictor", lambda model=None: _SahteVekil(cagri))
    v = o.ef.compute([{"running": True, "magneticMt": 1.0, "dutyCycle": 30, "measuredFields": ["magneticMt"]}])
    assert v["cancer"] == pytest.approx(0.055) and v["healthy"] == pytest.approx(0.021), v
    assert not v.get("egitimAraligiDisi"), v


@pytest.mark.parametrize(
    "model, sutun_mod",
    [
        ("fantom", "ai_hub.inference_em_fantom.inference_em_fantom"),
        ("petri", "ai_hub.inference_em_petri.inference_em_petri"),
    ],
)
def test_KRITIK_IG583_aralik_MODELIN_referans_orneklemiNDEN_okunur(model, sutun_mod):
    """Aralık sabit değil: modelin XAI referans örnekleminin `achieved_B` sütunu (yeniden eğitimde kendiliğinden güncellenir)."""
    import importlib

    from servers import efield_live as ef

    bg = importlib.import_module(sutun_mod).xai_ref_stats()["background"]
    alt, ust = ef.egitim_b_araligi_T(model)
    assert (alt, ust) == (pytest.approx(float(bg[:, 4].min())), pytest.approx(float(bg[:, 4].max())))


# ── D1.76 c / B-1.26: seans alan kaydının son/zirve değeri seansa aittir ──────────────────────────────────────────────


@pytest.fixture
def kayit(monkeypatch, tmp_path):
    from servers import api_server as api
    from servers import live_state
    from servers import seans_alan_kaydi as sak

    k = sak.SeansAlanKaydi()
    monkeypatch.setattr(sak, "masaustu_dizini", lambda: (tmp_path, "test"))
    monkeypatch.setattr(api, "_seans_alan", k)
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda m: None)
    monkeypatch.setattr(live_state, "_ws_broadcast_sync", lambda m: None)
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)
    with api._live_state_lock:
        eski = dict(api._live_state["activeTreatment"])
    yield api, live_state, k, sak
    k.seans_bitti("test sonu")
    with api._live_state_lock:
        api._live_state["activeTreatment"].clear()
        api._live_state["activeTreatment"].update(eski)
    api._coil_olculen_alanlar.pop(5, None)


def _at(api):
    with api._live_state_lock:
        return dict(api._live_state["activeTreatment"])


def _seans_A_zirve_7_5(api, live_state, k):
    assert k.seans_basladi("A") is not None
    live_state.update_live_session_state(is_active=True, mode="Manuel")
    api._handle_backend_event(_Olay({"coil_id": 6, "magnetic_field": 7.5}))
    assert _at(api)["measuredPeakMt"] == 7.5, "aparat: A seansının zirvesi yazılmadı"
    api.update_live_session_state(is_active=False)  # sarmalayıcı: CSV kapanır


def test_KRITIK_D176c_AI_seansinda_ONCEKI_seansin_zirvesi_GORUNMEZ(kayit):
    api, live_state, k, _ = kayit
    _seans_A_zirve_7_5(api, live_state, k)
    live_state.update_live_session_state(is_active=True, mode="AI Pro · Kedi Organ")  # AI: CSV açılmaz
    api._handle_backend_event(_Olay({"coil_id": 6, "magnetic_field": 1.0}))
    at = _at(api)
    assert at["measuredPeakMt"] is None and at["measuredIntensityMt"] is None, (
        f"AI seansında ÖNCEKİ seansın tepesi/son değeri gösteriliyor: tepe={at['measuredPeakMt']} anlık={at['measuredIntensityMt']}"
    )


def test_KRITIK_D176c_CSV_ACILAMAYAN_seansta_onceki_zirve_GORUNMEZ(kayit, monkeypatch):
    api, live_state, k, sak = kayit
    _seans_A_zirve_7_5(api, live_state, k)

    def _patla():
        raise PermissionError("masaüstü yazılamaz")

    monkeypatch.setattr(sak, "masaustu_dizini", _patla)
    assert k.seans_basladi("B") is None, "aparat: CSV açılmamalıydı"
    live_state.update_live_session_state(is_active=True, mode="Manuel")
    api._handle_backend_event(_Olay({"coil_id": 6, "magnetic_field": 1.0}))
    assert _at(api)["measuredPeakMt"] is None, f"CSV açılamayan B seansında A'nın tepesi: {_at(api)['measuredPeakMt']}"


def test_KARSIT_D176c_CSV_li_seansta_olculen_yogunluk_GORUNUR(kayit):
    api, live_state, k, _ = kayit
    _seans_A_zirve_7_5(api, live_state, k)
    assert k.seans_basladi("C") is not None
    live_state.update_live_session_state(is_active=True, mode="Manuel")
    api._handle_backend_event(_Olay({"coil_id": 6, "magnetic_field": 1.2}))
    at = _at(api)
    assert at["measuredIntensityMt"] == 1.2 and at["measuredPeakMt"] == 1.2, at


def test_KRITIK_alan_sensoru_SUSUNCA_anlik_olculen_yogunluk_DUSER_zirve_KALIR(kayit, monkeypatch):
    """D1.67 açık-2: susan alan sensörünün son değeri seans kartında 'anlık' gibi kalmaz; seans tepesi kayıttır, kalır."""
    from dongu_tek_tur import bir_tur_kos

    api, live_state, k, _ = kayit
    saat = _ModulSaati()
    monkeypatch.setattr(api, "time", saat)
    assert k.seans_basladi("D") is not None
    live_state.update_live_session_state(is_active=True, mode="Manuel")
    api._handle_backend_event(_Olay({"coil_id": 6, "magnetic_field": 1.8}))
    assert _at(api)["measuredIntensityMt"] == 1.8
    saat.ek += 30.0
    with api._session_lock:
        eski = api._active_session.get("is_active")
        api._active_session["is_active"] = False  # akümülatör bu kolun konusu değil
    try:
        assert bir_tur_kos(api._sensor_persistence_loop) == (1, [])
    finally:
        with api._session_lock:
            api._active_session["is_active"] = eski
    at = _at(api)
    assert at["measuredIntensityMt"] is None, (
        f"30 sn'dir gelmeyen alan seans kartında ANLIK gösteriliyor: {at['measuredIntensityMt']}"
    )
    assert at["measuredPeakMt"] == 1.8, "seans tepesi (kayıt) silinmemeli"
