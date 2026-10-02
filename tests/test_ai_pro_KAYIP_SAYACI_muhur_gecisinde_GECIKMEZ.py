# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""İG-5.1 · 1-C bağımsız inceleme i7-F-2 — eski seansın mührüyle girmiş uçuştaki kare YENİ seansın kayıp sayacını
sıfırlamaz (kayıp STOP'u gecikmez).

ÖLÇÜLEN KUSUR (i7, 30/30): `_frame_kayip` sayacı TEK globaldir ve "onay" değişince sıfırlanır. Eski seansın (S1)
mührüyle girmiş, lokalizasyonda bekleyen (uçuştaki) bir kare, YENİ seans (S2) kayıp sayarken tamamlanınca sayacı S1'e
çevirip sıfırlıyor; S2'nin sonraki karesi onu tekrar S2'ye çevirip sıfırlıyordu → S2'nin kayıp STOP'u 3. yerine 5. kayıp
karesinde geliyordu. DÜZELTME: mührü GÜNCEL aktif seansın onayı olmayan kare sayaca DOKUNMAZ.
KAPI (zorlanmış zamanlama, ×30): S1'de A lokalizasyonda bekler → S1 durdurulur → S2 başlar, sürer → 2 kayıp karesi → A
bırakılır → kayıp kareleri bobin durana dek sayılır: en geç N (= 3) karede STOP.
"""

from __future__ import annotations

import threading

import ai_pro_aparati as ap
import pytest

N_PIN = 3


@pytest.fixture
def o(monkeypatch, tmp_path):
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


@pytest.mark.parametrize("deneme", range(30))
def test_KRITIK_i7F2_MUHUR_GECISI_eski_seansin_ucustaki_karesi_YENI_seansin_kayip_sayacini_GECIKTIRMEZ(
    o, monkeypatch, deneme
):
    durum = {"mod": "bulundu", "blok": None, "icerde": threading.Event()}

    def _lok(f, oid):
        blok = durum["blok"]
        if blok is not None:
            durum["blok"] = None
            durum["icerde"].set()
            assert blok.wait(10), "aparat: lokalizasyon engeli kalkmadı"
        b = durum["mod"] == "bulundu"
        return (b, 10.0, 20.0, 30.0, 0.9 if b else 0.0, None, True)

    monkeypatch.setattr(o.air, "_localize_organ", _lok)
    _pid1, r = ap.onayli_baslat(o)
    assert r.status_code == 200, r.text[:200]
    assert ap.kare(o).json().get("driven") is True
    # S1 mühürlü kare A lokalizasyonda bekler
    durum["blok"] = threading.Event()
    engel = durum["blok"]
    t, kutu = ap.kare_arka_planda(o)
    assert durum["icerde"].wait(5), "aparat: A lokalizasyona girmedi"
    assert o.c.post("/api/ai/pro/stop").status_code == 200
    _pid2, r2 = ap.onayli_baslat(o)
    assert r2.status_code == 200 and r2.json().get("message") != "Already running", r2.text[:200]
    assert ap.kare(o).json().get("driven") is True and ap.calisan(o), "aparat: S2 sürmedi"
    durum["mod"] = "kayip"
    kayip = 0
    for _ in range(N_PIN - 1):
        ap.kare(o)
        kayip += 1
    engel.set()  # S1'in uçuştaki karesi şimdi tamamlanır (kayıp okur)
    t.join(10)
    while ap.calisan(o) and kayip < 10:
        ap.kare(o)
        kayip += 1
    assert kayip <= N_PIN, (
        f"S2'de hedef kaybından sonra STOP {kayip}. kayıp karesinde geldi (beklenen ≤{N_PIN}); S1 mühürlü uçuştaki kare "
        f"sayacı sıfırladı (A yanıtı: {getattr(kutu.get('yanit'), 'status_code', kutu.get('hata'))})"
    )
