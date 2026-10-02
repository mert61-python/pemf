# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.59 · B-5.4 — doz modeline giden ORGAN, kullanılan KOORDİNATIN organıdır (döngü ve `/frame`).

KUSUR (plan, 05-2 l1): lokalizasyon önbelleği organ kimliğiyle damgalanıyordu (`"organ_id": _oid`), ama tahmin
`_predict_and_drive(x, y, z, _ai_organ_id)` GLOBALİ okuyordu. Lokalizasyon 1–4 sn sürerken organ değişirse ESKİ
organın koordinatı YENİ organın kimliğiyle em_kedi'ye gidiyordu: yeni organın duty/faz deseni eski organın konumuna
odaklanır, ekran yeni organı gösterir (gösterilen ≠ uygulanan).

YÖNTEM (olay sıralı, zamana bağlı değil): sahte lokalizasyon organı KOORDİNATA kodlar — organ k → (10k+1, 10k+2,
10k+3) mm — ve ilk çağrıda bir Event'te BEKLER. O sırada organ değiştirilir, sonra serbest bırakılır. Doz modeli
(tahmin) çağrısı kaydedilir: organ argümanı koordinattan çözülen organa EŞİT olmalı.

İKİ YAZICI: (a) GERÇEK `POST /api/ai/pro/organ` (bugünkü seans-içi tetik; D1.60/A-16 sonrası mühür dışı organa
409 — o zaman küresel değişmez ve kol yine tutarlılığı ölçer) · (b) `_ai_organ_id` küresel yazımı (hazırlık / yeni
seans gibi başka yazıcılar; A-16'dan bağımsız kalıcı kol).

Bu dosya `test_ai_pro_safety::test_organ_switch_race_snapshots_id_and_consumes_flag_first` METİN çapasının
davranış karşılığıdır (plan: "metin çapası, davranış testine çevrilecek"); "yeniden konumla" isteğinin lokalizasyon
uçarken YUTULMAMASI da burada davranışla ölçülür.
"""

from __future__ import annotations

import threading
import time

import ai_pro_aparati as ap
import numpy as np
import pytest


def _koord(oid: int):
    return 10.0 * oid + 1, 10.0 * oid + 2, 10.0 * oid + 3


def _organ_coz(x: float) -> int:
    return int(round((x - 1.0) / 10.0))


class _Lokalizasyon:
    """Organı koordinata kodlayan sahte lokalizasyon; `bekle` kuruluysa İLK çağrıda serbest bırakılana dek bekler."""

    def __init__(self):
        self.cagrilar: list[int] = []
        self.girdi = threading.Event()
        self.bekle: threading.Event | None = None

    def __call__(self, frame, oid):
        self.cagrilar.append(int(oid))
        if self.bekle is not None and len(self.cagrilar) == 1:
            self.girdi.set()
            assert self.bekle.wait(10), "aparat: lokalizasyon engeli 10 sn'de kalkmadı"
        x, y, z = _koord(int(oid))
        return True, x, y, z, 0.9, None, True


class _Tahmin:
    def __init__(self):
        self.cagrilar: list[tuple] = []
        self.ilk = threading.Event()

    def __call__(self, x, y, z, oid):
        self.cagrilar.append((x, y, z, int(oid)))
        self.ilk.set()
        return [ap.D_AI] * 7, [0.0] * 7, 1.0


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            ns.lok = _Lokalizasyon()
            ns.tah = _Tahmin()
            monkeypatch.setattr(ns.air, "_localize_organ", ns.lok)
            monkeypatch.setattr(ns.air, "_predict_and_drive", ns.tah)
            yield ns
    finally:
        ns.air._ai_loop_active = False
        ns.geri()


def _organ_degistir(o, yazici: str, yeni: int):
    if yazici == "organ_ucu":
        r = o.c.post("/api/ai/pro/organ", json={"organ_id": yeni})
        assert r.status_code in (200, 409), r.text[:200]  # 409 = A-16 (D1.60) mühür dışı organ
    else:
        o.air._ai_organ_id = yeni


@pytest.mark.parametrize("yazici", ["organ_ucu", "kuresel"])
def test_KRITIK_frame_tahmine_KOORDINATIN_organi_gider(o, yazici):
    _pid, r = ap.onayli_baslat(o, organ=2)
    assert r.status_code == 200, r.text[:200]
    o.lok.bekle = threading.Event()
    t, kutu = ap.kare_arka_planda(o)
    assert o.lok.girdi.wait(5), "aparat: /frame lokalizasyona girmedi"
    _organ_degistir(o, yazici, 5)
    o.lok.bekle.set()
    t.join(10)
    assert "yanit" in kutu and kutu["yanit"].status_code == 200, kutu
    assert o.tah.cagrilar, "aparat: /frame tahmine geçmedi (sürülebilir seans kurulmadı)"
    x, _y, _z, oid = o.tah.cagrilar[0]
    assert oid == _organ_coz(x), (
        f"/frame: em_kedi'ye organ {oid} gitti ama koordinat organ {_organ_coz(x)}'nin ({x} mm) — yeni organın deseni "
        "eski organın konumuna odaklanıyor"
    )
    j = kutu["yanit"].json()
    assert j["organId"] == oid, (
        f"/frame yanıtı organ {j['organId']} gösteriyor, sürülen organ {oid} (gösterilen ≠ uygulanan)"
    )


def test_KARSIT_frame_organ_degisimi_SONRAKI_karede_yeni_organi_surer(o):
    """KARŞIT: düzeltme organ değişimini YUTMAZ — sonraki kare yeni organı lokalize eder.

    ⚠️ D1.60 (A-16) ile netleşti: organ-2 mühürlü seansta organ 5 lokalize edilir ama SÜRÜLMEZ (mühür dışı = onaysız
    tedavi; o kol `test_ai_pro_organ_MUHUR_DISI_yeni_onay_ister_A16.py`). Mühürdeki organa dönülünce sonraki kare onu
    lokalize edip SÜRER — değişimler hiçbir yönde yutulmaz."""
    _pid, r = ap.onayli_baslat(o, organ=2)
    assert r.status_code == 200, r.text[:200]
    o.lok.bekle = threading.Event()
    t, _kutu = ap.kare_arka_planda(o)
    assert o.lok.girdi.wait(5)
    o.air._ai_organ_id = 5
    o.lok.bekle.set()
    t.join(10)
    n_tahmin = len(o.tah.cagrilar)
    j2 = ap.kare(o).json()
    assert o.lok.cagrilar[-1] == 5, f"organ değişimi sonraki karede lokalize edilmedi: {o.lok.cagrilar}"
    assert j2["organId"] == 5 and j2.get("driven") is not True, j2
    assert len(o.tah.cagrilar) == n_tahmin, f"mühür dışı organ 5 tahmine/sürüşe gitti: {o.tah.cagrilar}"
    o.air._ai_organ_id = 2
    j3 = ap.kare(o).json()
    assert o.lok.cagrilar[-1] == 2, f"mühürdeki organa dönüş lokalize edilmedi: {o.lok.cagrilar}"
    assert o.tah.cagrilar[-1] == (*_koord(2), 2), o.tah.cagrilar
    assert j3["organId"] == 2 and j3.get("driven") is True, j3


def test_KRITIK_frame_yeniden_konumla_istegi_lokalizasyon_UCARKEN_YUTULMAZ(o):
    """Lokalizasyon sürerken basılan "yeniden konumla" (`/calibrate`) sonraki karede YENİ lokalizasyon tetikler.

    (Eski metin çapasının ikinci iddiası: bayrak lokalizasyondan ÖNCE tüketilir.)"""
    _pid, r = ap.onayli_baslat(o, organ=2)
    assert r.status_code == 200, r.text[:200]
    o.lok.bekle = threading.Event()
    t, _kutu = ap.kare_arka_planda(o)
    assert o.lok.girdi.wait(5)
    assert o.c.post("/api/ai/pro/calibrate", json={}).status_code == 200
    o.lok.bekle.set()
    t.join(10)
    n = len(o.lok.cagrilar)
    ap.kare(o)
    assert len(o.lok.cagrilar) == n + 1, "lokalizasyon uçarken gelen 'yeniden konumla' isteği YUTULDU"


class _SahteKamera:
    def __init__(self, *a, **k):
        pass

    def isOpened(self):  # noqa: N802
        return True

    def read(self):
        return True, np.zeros((8, 8, 3), dtype=np.uint8)

    def release(self):
        pass


def test_KRITIK_DONGU_yeniden_konumla_istegi_lokalizasyon_UCARKEN_YUTULMAZ(monkeypatch, tmp_path):
    """GERÇEK döngü: lokalizasyon sürerken gelen `/calibrate` bir SONRAKİ turda yeni lokalizasyon tetikler.

    Bayrak lokalizasyondan SONRA tüketilseydi istek yutulur, yeniden konum ancak periyodik aralıkta
    (`_ORGAN_LOCALIZE_INTERVAL_S`) gelirdi."""
    from kayitci_donanim import gercek_hc
    from servers import ai_pro_hedef

    ns = ap.kur(monkeypatch, tmp_path, dongu_noop=False)
    try:
        monkeypatch.setattr(ns.air.cv2, "VideoCapture", _SahteKamera)
        monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", lambda self: None)
        assert ns.air._ORGAN_LOCALIZE_INTERVAL_S >= 5.0, "aparat: periyodik aralık ölçümü ayırt edemez"
        lok, tah = _Lokalizasyon(), _Tahmin()
        lok.bekle = threading.Event()
        monkeypatch.setattr(ns.air, "_localize_organ", lok)
        monkeypatch.setattr(ns.air, "_predict_and_drive", tah)
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            _pid, r = ap.onayli_baslat(ns, organ=2)
            assert r.status_code == 200, r.text[:200]
            assert lok.girdi.wait(5), "aparat: döngü lokalizasyona girmedi"
            assert ns.c.post("/api/ai/pro/calibrate", json={}).status_code == 200
            lok.bekle.set()
            yeniden = ap.bekle(lambda: len(lok.cagrilar) >= 2, 3.5)
            ns.c.post("/api/ai/pro/stop")
            ap.bekle(lambda: not ns.air._ai_loop_active, 5)
        assert yeniden, f"lokalizasyon uçarken gelen 'yeniden konumla' YUTULDU (çağrılar: {lok.cagrilar})"
    finally:
        ns.air._ai_loop_active = False
        ns.geri()


@pytest.mark.parametrize("yazici", ["organ_ucu", "kuresel"])
def test_KRITIK_DONGU_tahmine_KOORDINATIN_organi_gider(monkeypatch, tmp_path, yazici):
    """GERÇEK `_ai_pro_loop` (sahte kamera; gerçek kamera AÇILMAZ)."""
    from kayitci_donanim import gercek_hc
    from servers import ai_pro_hedef

    ns = ap.kur(monkeypatch, tmp_path, dongu_noop=False)
    try:
        monkeypatch.setattr(ns.air.cv2, "VideoCapture", _SahteKamera)
        monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", lambda self: None)
        lok, tah = _Lokalizasyon(), _Tahmin()
        lok.bekle = threading.Event()
        monkeypatch.setattr(ns.air, "_localize_organ", lok)
        monkeypatch.setattr(ns.air, "_predict_and_drive", tah)
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            _pid, r = ap.onayli_baslat(ns, organ=2)
            assert r.status_code == 200, r.text[:200]
            assert lok.girdi.wait(5), "aparat: döngü lokalizasyona girmedi"
            _organ_degistir(ns, yazici, 5)
            lok.bekle.set()
            assert tah.ilk.wait(5), "aparat: döngü tahmine geçmedi"
            ns.c.post("/api/ai/pro/stop")
            ap.bekle(lambda: not ns.air._ai_loop_active, 5)
            time.sleep(0.2)
        x, _y, _z, oid = tah.cagrilar[0]
        assert oid == _organ_coz(x), (
            f"döngü: em_kedi'ye organ {oid} gitti ama koordinat organ {_organ_coz(x)}'nin ({x} mm)"
        )
        vision = [m["data"] for m in ns.ws if m.get("type") == "ai_vision"]
        assert vision, "aparat: döngü ai_vision yayını üretmedi"
        assert vision[0]["organId"] == oid, (
            f"döngü WS organ {vision[0]['organId']} gösteriyor, sürülen organ {oid} (gösterilen ≠ uygulanan)"
        )
    finally:
        ns.air._ai_loop_active = False
        ns.geri()
