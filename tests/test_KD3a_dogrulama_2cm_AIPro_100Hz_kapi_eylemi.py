# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KD-3a (tezgâh 11 Kasım, sahip başında) — üç sahip kararı / bulgu:

1. SAHİP KARARI 5: "ya 2 cm olsun fark eşiği" — kabin kalibrasyonu DOĞRULA (plaka MERKEZİ) geçti / kaldı sınırı 1 cm → 2 cm.
   Ölçülen: canlı doğrulama 1,01 cm "KALDI" (cetvel köşe başına σ ≈ 5–8 mm; yeniden ölçünce 0,73 cm). Kapsam YALNIZ doğrulama sınırı.
2. SAHİP KARARI 6: "100hz olcak ai pro freq" — AI Pro bobin sürüşü 1 Hz ("eski PyQt DDS varsayılanı") yerine 100 Hz. Ölçülen: kart
   her AI Pro sürüşünde `F=1,1,1,1,1,1,1` aldı. Kapı: GERÇEK onay akışı + GERÇEK `HardwareController` (kayıtçı kuyruk); paket
   FIRMWARE AYNASIYLA çözülür (kart 100 Hz'i KABUL eder — NACK yok).
3. B-KD3a.1: sabit düzlem kipinde kapı FİZİKSEL nedenle (kamera oynamış / kör bölge / kalibrasyon …) kestiğinde AI Pro paneli nedeni
   göremiyordu — rozet ArUco metnine ("kabin işareti … kare kod … görünmüyor") düşüyordu. Sağlayıcının zaten hesapladığı kapının ilk
   FİZİKSEL eylem metni durum ucuna YALNIZ-EK `kapiEylem` alanıyla gider (kapı geçerse / neden fiziksel değilse boş).
"""

from __future__ import annotations

import ai_pro_aparati as ap
import pytest
import test_KD_kalibrasyon_uclari_ve_surus_kapisi as kdt

env = kdt.env  # fikstür (aynı düzenek: sentetik sahne, gerçek uçlar)


# ── 1. doğrulama eşiği 2 cm ────────────────────────────────────────────────────────────────────────────────────
def test_KRITIK_dogrula_MERKEZ_1_5_cm_GECER_esik_2_cm(env):
    kdt._kalibre(env)
    c = env["client"]
    k = kdt._kare(env, kdt.BASKA)
    olc = kdt._olcumler(kdt.BASKA, n=2)
    kayik = [None if q is None else dict(q, solCm=q["solCm"] + 1.5) for q in olc]  # cetvel 1,5 cm kaymış
    r = c.post("/api/ai/pro/kalibrasyon/dogrula", json={"kareKimligi": k["kareKimligi"], "olcumler": kayik})
    assert r.status_code == 200, r.text
    j = r.json()
    assert 1.2 < j["merkezFarkCm"] < 1.8, j  # vakum kapısı: fark gerçekten 1–2 cm arasında
    assert j["esikCm"] == 2.0 and j["gecti"] is True, j


def test_KARSIT_dogrula_MERKEZ_2_6_cm_KALIR(env):
    kdt._kalibre(env)
    c = env["client"]
    k = kdt._kare(env, kdt.BASKA)
    olc = kdt._olcumler(kdt.BASKA, n=2)
    kayik = [None if q is None else dict(q, solCm=q["solCm"] + 2.6) for q in olc]
    r = c.post("/api/ai/pro/kalibrasyon/dogrula", json={"kareKimligi": k["kareKimligi"], "olcumler": kayik})
    j = r.json()
    assert j["merkezFarkCm"] > 2.2 and j["gecti"] is False, j


# ── 2. AI Pro 100 Hz ───────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
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


def test_KRITIK_AI_Pro_bobinleri_100_Hz_surer_ve_KART_kabul_eder(o):
    from kayitci_donanim import paket_coz

    once = len(o.hc.core._hw_send_queue.paketler)
    _pid, r = ap.onayli_baslat(o, sure_dk=5)
    assert r.status_code == 200, r.text[:200]
    k = ap.kare(o)
    assert k.status_code == 200, k.text[:200]
    assert sorted(ap.calisan(o)) == [1, 2, 3, 4, 5, 6, 7], ap.calisan(o)
    paketler = o.hc.core._hw_send_queue.paketler[once:]
    assert paketler, "aparat: AI Pro hiç paket göndermedi"
    _duty, _faz, freq, _sure, _ref, _kip = paket_coz(paketler[-1])  # firmware aynası KABUL eder (NACK → AssertionError)
    assert [round(float(f), 3) for f in freq[:7]] == [100.0] * 7, freq
    for i in range(
        1, 8
    ):  # update_coil durumuna da 100 yazıldı (varsayılan da 100 — asıl kanıt yukarıdaki TELDEKİ paket)
        assert o.hc.coils_state[i]["freq"] == pytest.approx(100.0), o.hc.coils_state[i]


# ── 3. B-KD3a.1 durum ucunda kapının FİZİKSEL eylemi ───────────────────────────────────────────────────────────
def _meta(kod: str, surulebilir: bool = False) -> dict:
    return {
        "method": "sabit_duzlem",
        "targets": [],
        "pemf_kapisi": {
            "surulebilir": surulebilir,
            "nedenler": [kod],
            "mesajlar": [{"kod": kod, "metin": "hocanın metni"}],
            "eylem": "hocanın metni",
        },
    }


def test_KRITIK_kapi_FIZIKSEL_nedenle_kestiyse_durum_ucu_EYLEMI_tasir(monkeypatch):
    from servers import ai_pro_hedef
    from servers import ai_router as air

    monkeypatch.setattr(air, "_saglayici_meta", lambda: _meta("kamera_oynamis"))
    alan = air._saglayici_cache_alanlari()
    beklenen = ai_pro_hedef.kapi_metni("kamera_oynamis")
    assert beklenen and alan["kapi_eylem"] == beklenen, alan
    monkeypatch.setitem(air._ai_organ_cache, "kapi_eylem", alan["kapi_eylem"])
    assert air.ai_pro_status()["kapiEylem"] == beklenen


@pytest.mark.parametrize(
    "meta",
    [
        _meta("kuyu_skor_esigi"),  # fiziksel DEĞİL (hocanın kalite nedeni) → panel kendi şeridini gösterir
        _meta("kamera_oynamis", surulebilir=True),  # kapı geçti → neden yok
        {"method": "aruco_pnp", "targets": []},  # kapı hiç hesaplanmadı
    ],
)
def test_KARSIT_fiziksel_olmayan_ya_da_GECEN_kapida_kapi_eylemi_BOS(monkeypatch, meta):
    from servers import ai_router as air

    monkeypatch.setattr(air, "_saglayici_meta", lambda: meta)
    assert air._saglayici_cache_alanlari()["kapi_eylem"] == ""
