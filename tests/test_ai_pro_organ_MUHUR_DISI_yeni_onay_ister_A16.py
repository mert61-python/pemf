# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.60 · B-5.5 · İG-6.10 — SAHİP KARARI A-16: seans sürerken MÜHÜRDE OLMAYAN organa geçiş YENİ ONAY ister (409).

Onay mührü bir organa verilir; mühürde olmayan organa sürüş onaysız tedavidir ("onaysız tedavi başlamaz" sert
kapısı). KUSUR (D0 İG-6.10, ölçüldü): onaylı seans (organ 0) sürerken SAHİP istemci `POST /api/ai/pro/organ
{organ_id: 2}` gönderdi → 200, yeni onay istenmedi, teldeki duty/faz yeni organın desenine geçti.

İKİ KATMAN (her biri kendi gözlenebilir etkisiyle ölçülür):
  1. `/api/ai/pro/organ` mühürlü seansta mühürdeki organdan FARKLI organa 409 döner; küresel hedef DEĞİŞMEZ.
  2. Sürüş (`/frame` ve döngü) yalnız MÜHÜRDEKİ organı sürer — küresel hedef BAŞKA bir yolla değişse bile
     (hazırlık, ileride eklenecek bir uç). Mühür dışı organın koordinatı sürülmez.

Ölçüt HTTP değil TELDEKİ PAKET: sahte doz modeli organa bağlı duty üretir (organ k → 0,10 + 0,02·k).
"""

from __future__ import annotations

import threading
import time

import ai_pro_aparati as ap
import numpy as np
import pytest


def _duty(oid: int) -> float:
    return round(0.10 + 0.02 * oid, 4)


class _Tahmin:
    def __init__(self):
        self.organlar: list[int] = []

    def __call__(self, x, y, z, oid):
        self.organlar.append(int(oid))
        return [_duty(int(oid))] * 7, [10.0 * int(oid)] * 7, 1.0


def _lokalize(frame, oid):
    return True, 10.0 * oid + 1, 10.0 * oid + 2, 10.0 * oid + 3, 0.9, None, True


def _duty_kumesi(o, once: int) -> set:
    return {round(d, 4) for paket in ap.surus_paketleri(o, once) for d in paket if d > 0}


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            ns.tah = _Tahmin()
            monkeypatch.setattr(ns.air, "_localize_organ", _lokalize)
            monkeypatch.setattr(ns.air, "_predict_and_drive", ns.tah)
            yield ns
    finally:
        ns.air._ai_loop_active = False
        ns.geri()


def _baslat(o, organ=2, istemci="A"):
    _pid, r = ap.onayli_baslat(o, organ=organ, istemci=istemci)
    assert r.status_code == 200, r.text[:200]
    j = ap.kare(o, istemci).json()
    assert j.get("driven") is True, f"aparat: onaylı organ {organ} sürülmedi: {j}"
    assert ap.surus_paketleri(o, 0), "aparat: telde sürüş paketi yok"


def test_KRITIK_A16_seans_icinde_MUHUR_DISI_organa_gecis_409_ve_tel_DEGISMEZ(o):
    _baslat(o, organ=2)
    n = ap.paket_sayisi(o)
    r = o.c.post("/api/ai/pro/organ", json={"organ_id": 5, "client_id": "A"})
    assert r.status_code == 409, (
        f"mühürde OLMAYAN organa (5) geçiş {r.status_code} ile kabul edildi — onaysız tedavi (A-16 yeni onay ister)"
    )
    assert o.air._ai_organ_id == 2, f"409'a rağmen küresel hedef değişti: {o.air._ai_organ_id}"
    for _ in range(2):
        ap.kare(o, "A")
    assert _duty_kumesi(o, n) <= {_duty(2)}, (
        f"409'dan sonra telde mühür dışı desen: {_duty_kumesi(o, n)} (beklenen yalnız {_duty(2)})"
    )
    assert 5 not in o.tah.organlar, f"mühür dışı organ doz modeline gitti: {o.tah.organlar}"


def test_KRITIK_A16_409_metni_EYLEM_soyler(o):
    _baslat(o, organ=2)
    r = o.c.post("/api/ai/pro/organ", json={"organ_id": 5, "client_id": "A"})
    assert r.status_code == 409, r.status_code
    d = r.json().get("detail", "")
    ad2 = o.air._aktif_saglayici().hedef_adi(2)
    assert ad2 in d, f"409 metni onaylı hedefi ({ad2}) söylemiyor: {d!r}"
    assert "yeni onay" in d.lower() and "durdur" in d.lower(), f"409 metni operatöre eylemi söylemiyor: {d!r}"


def test_KARSIT_ayni_organ_seans_icinde_200(o):
    _baslat(o, organ=2)
    r = o.c.post("/api/ai/pro/organ", json={"organ_id": 2, "client_id": "A"})
    assert r.status_code == 200, r.text[:200]


def test_KARSIT_seans_YOKKEN_organ_secimi_serbest(o):
    """A-16 yalnız SÜREN seansı kapsar: hazırlıkta hedef seçimi (öneri öncesi) serbest kalır."""
    r = o.c.post("/api/ai/pro/organ", json={"organ_id": 5, "client_id": "A"})
    assert r.status_code == 200, r.text[:200]
    assert o.air._ai_organ_id == 5


def test_KRITIK_A16_ikinci_katman_kuresel_hedef_BASKA_yoldan_degisse_de_frame_MUHUR_DISINI_SURMEZ(o):
    """Katman 2: küresel hedef `/organ` dışında bir yazıcıyla değişirse `/frame` yeni organı lokalize eder ama SÜRMEZ."""
    _baslat(o, organ=2)
    n = ap.paket_sayisi(o)
    o.air._ai_organ_id = 5  # başka bir yazıcı (ör. ileride eklenecek bir uç)
    j = ap.kare(o, "A").json()
    assert j.get("driven") is not True, f"mühür dışı organ (5) /frame'de SÜRÜLDÜ: {j.get('driven')}"
    assert _duty(5) not in _duty_kumesi(o, n), f"telde mühür dışı organın deseni: {_duty_kumesi(o, n)}"


def test_KARSIT_ikinci_katman_mühurdeki_organa_donunce_surus_SURER(o):
    _baslat(o, organ=2)
    o.air._ai_organ_id = 5
    ap.kare(o, "A")
    o.air._ai_organ_id = 2
    n = ap.paket_sayisi(o)
    j = ap.kare(o, "A").json()
    assert j.get("driven") is True, j
    assert _duty(2) in _duty_kumesi(o, n)


class _SahteKamera:
    def __init__(self, *a, **k):
        pass

    def isOpened(self):  # noqa: N802
        return True

    def read(self):
        return True, np.zeros((8, 8, 3), dtype=np.uint8)

    def release(self):
        pass


def test_KRITIK_A16_ikinci_katman_DONGU_mühur_disi_organi_SURMEZ(monkeypatch, tmp_path):
    """GERÇEK `_ai_pro_loop` (sahte kamera): küresel hedef değişince döngü yeni organı lokalize eder ama SÜRMEZ."""
    from kayitci_donanim import gercek_hc
    from servers import ai_pro_hedef

    ns = ap.kur(monkeypatch, tmp_path, dongu_noop=False)
    try:
        monkeypatch.setattr(ns.air.cv2, "VideoCapture", _SahteKamera)
        monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", lambda self: None)
        tah = _Tahmin()
        ilk = threading.Event()
        lok_organlar: list[int] = []

        def _lok(frame, oid):
            lok_organlar.append(int(oid))
            ilk.set()
            return _lokalize(frame, oid)

        monkeypatch.setattr(ns.air, "_localize_organ", _lok)
        monkeypatch.setattr(ns.air, "_predict_and_drive", tah)
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            _pid, r = ap.onayli_baslat(ns, organ=2)
            assert r.status_code == 200, r.text[:200]
            assert ap.bekle(lambda: _duty(2) in _duty_kumesi(ns, 0), 5), "aparat: döngü onaylı organı sürmedi"
            n = ap.paket_sayisi(ns)
            ns.air._ai_organ_id = 5
            ap.bekle(lambda: 5 in lok_organlar, 5)
            time.sleep(2.5)  # en az iki tur
            ns.c.post("/api/ai/pro/stop")
            ap.bekle(lambda: not ns.air._ai_loop_active, 5)
        assert 5 in lok_organlar, "aparat: döngü yeni hedefi lokalize etmedi"
        assert _duty(5) not in _duty_kumesi(ns, n), f"döngü mühür dışı organı SÜRDÜ: {_duty_kumesi(ns, n)}"
    finally:
        ns.air._ai_loop_active = False
        ns.geri()
