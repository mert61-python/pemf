# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.E07 incelemesi (İNCELEME-2 i4-F-1 · İG-5.15 · Ö.4-Y9) — "doz modeli hatası" yalnız HİÇBİR bobinin dozu olmayan zarftır;
bazı bobinleri sıfır olan MEŞRU plan hata sayılmaz, SÜRÜLÜR.

ÖLÇÜLEN KÖRLÜK (`60567e4`): D1.E07 seans ortası model hatasını `not any(D)` (zarf `[0]*7`) ile tanır. Ölçüt `not all(D)`a
kaysa — tek bir bobini sıfır olan her plan "model hatası" sayılır: kare/tur SÜRÜLMEZ, N'de STOP, operatöre "AI Pro'yu durdurup
yeniden başlatın" bildirimi — mevcut 35 kapı dosyası (D1.86'nın 66 kolu dahil) `/frame` ve döngü mutantında 507/507 YEŞİL kaldı
(tüm kapılar yedi bobini de sıfırdan büyük planla sürüyor). Bu, onaylı tedavide meşru dozun YENİ bir reddi olurdu (Ö.4-Y9).

KAPI: GERÇEK onay akışı + GERÇEK `/frame` / döngü + GERÇEK HC (kayıtçı kuyruk, firmware aynası). Doz modeli sahte: 7 bobinden
dördü sıfır (D = [0,30; 0; 0,32; 0; 0; 0; 0,36]).
"""

from __future__ import annotations

import ai_pro_aparati as ap
import numpy as np
import pytest

D_KISMI = [0.30, 0.0, 0.32, 0.0, 0.0, 0.0, 0.36]
P7 = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0]


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    monkeypatch.setattr(ns.air, "_predict_and_drive", lambda *a, **k: (list(D_KISMI), list(P7), 0.5))
    monkeypatch.setattr(ns.air, "_doz_hatasi_bildirilen", {"anahtar": "<test-öncesi>"})
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


def _doz_hatasi_bildirimi(o) -> list:
    return [m for m, _t in o.bildirim if "doz modeli" in m]


def _teldeki_duty(o) -> tuple:
    """Donanıma giden SON paketin bobin 1-7 duty'leri (firmware aynasıyla çözülür)."""
    from kayitci_donanim import paket_coz

    return tuple(round(float(x), 4) for x in paket_coz(o.hc.core._hw_send_queue.paketler[-1])[0][:7])


def test_KARSIT_frame_KISMI_sifir_plan_SURULUR_hata_bildirimi_ve_STOP_YOK(o):
    _pid, r = ap.onayli_baslat(o, organ=2)
    assert r.status_code == 200, r.text[:200]
    for _ in range(4):  # N=3'ü aşan ardışık kare: "hata" sayılsaydı STOP gelirdi
        j = ap.kare(o).json()
        assert j.get("driven") is True, f"kısmi sıfır plan 'sürülmedi': driven={j.get('driven')}"
    assert _teldeki_duty(o) == tuple(D_KISMI), (
        f"telde duty {_teldeki_duty(o)} ≠ plan {tuple(D_KISMI)} (STOP ya da red?)"
    )
    assert not _doz_hatasi_bildirimi(o), f"meşru plan 'doz modeli hatası' sayıldı: {_doz_hatasi_bildirimi(o)}"


def test_KRITIK_frame_TUM_sifir_zarf_HATA_sayilir_ve_SURULMEZ_karsit_kol_bos_gecmez(o, monkeypatch):
    """Ölçütün diğer yüzü: zarf `[0]*7` (model hatası) sürülmez ve bildirilir — yukarıdaki KARŞIT boş geçmesin."""
    monkeypatch.setattr(o.air, "_predict_and_drive", lambda *a, **k: ([0.0] * 7, [0.0] * 7, 0.0))
    _pid, r = ap.onayli_baslat(o, organ=2)
    assert r.status_code == 200, r.text[:200]
    j = ap.kare(o).json()
    assert j.get("driven") is not True and ap.calisan(o) == [] and _doz_hatasi_bildirimi(o), (
        j.get("driven"),
        ap.calisan(o),
        o.bildirim,
    )


def test_KARSIT_DONGU_KISMI_sifir_plan_SURULUR_hata_bildirimi_YOK(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc
    from servers import ai_pro_hedef

    ns = ap.kur(monkeypatch, tmp_path, dongu_noop=False)
    monkeypatch.setattr(ns.air, "_predict_and_drive", lambda *a, **k: (list(D_KISMI), list(P7), 0.5))
    monkeypatch.setattr(ns.air, "_doz_hatasi_bildirilen", {"anahtar": "<test-öncesi>"})
    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", lambda self: None)  # em_kedi ağırlığı depoda yok

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
    hc_ctx = gercek_hc()
    ns.hc = hc_ctx.__enter__()
    monkeypatch.setattr(ns.api.state, "hardware", ns.hc)
    try:
        _pid, r = ap.onayli_baslat(ns, organ=2)
        assert r.status_code == 200, r.text[:200]
        assert ap.bekle(lambda: ap.paket_sayisi(ns) > 0 and _teldeki_duty(ns) == tuple(D_KISMI), 6), (
            "döngü planı sürmedi"
        )
        ap.bekle(lambda: False, 4.0)  # ≥ N=3 tur: "hata" sayılsaydı STOP gelirdi
        assert _teldeki_duty(ns) == tuple(D_KISMI), f"döngü kısmi sıfır planı durdurdu: telde {_teldeki_duty(ns)}"
        assert not [m for m, _t in ns.bildirim if "doz modeli" in m], ns.bildirim
    finally:
        ns.air._ai_loop_active = False
        ap.bekle(lambda: False, 1.5)
        ns.hc.stop_all_coils()
        hc_ctx.__exit__(None, None, None)
        ns.geri()
