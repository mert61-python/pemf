# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""1-C bağımsız inceleme i2-F6 — ESKİ AI Pro döngüsünün BAŞLANGIÇ hatası YENİ onaylı seansı pasife ÇEKMEZ.

ÖLÇÜLEN KUSUR (c5b3c04, i2 30/30): `_ai_pro_loop` başlarken modeli yükler (gerçek sağlayıcıda saniyeler) ve kamerayı
5 × 0,5 sn dener. Bu sırada operatör eski seansı (A) durdurup yeni onaylı seans (B) açabilir. A sonra başarısız olunca
`_ai_seansi_pasife_al` yalnız `_ai_seansi_mi(_active_session)`e bakıyordu (onay kimliğine BAKMIYORDU) → O AN aktif olan
B'yi pasife çekiyor, canlı durumu "Sistem Hazır" yapıyordu; B'nin döngüsü bir sonraki turda çıkıyor, onayı tüketilmiş
tedavi operatör bir şey yapmadan bitiyordu. Teardown'ın "yalnız KENDİ seansı" kuralı (onay kimliği) bu yolda yoktu.

KAPI: A'nın model yüklemesi ya da İLK kamera açılışı bir Event'te tutulur, B GERÇEK onay akışıyla açılıp sürdükten
sonra A hata ile döner (kamera kolunda A'nın iş parçacığı kapalı kamera görür; B'ninki açık). GERÇEK: `/ai/pro/start`,
`/ai/pro/stop`, `_ai_pro_loop`, `HardwareController`. 2 kol × 30 deneme + KARŞIT (A hatasız biterse B yaşar).
"""

from __future__ import annotations

import threading
import time

import ai_pro_aparati as ap
import pytest

DENEME = 30


class _AcikKamera:
    def isOpened(self):
        return True

    def read(self):
        import numpy as np

        return True, np.zeros((8, 8, 3), dtype=np.uint8)

    def release(self):
        pass


class _KapaliKamera(_AcikKamera):
    def isOpened(self):
        return False


@pytest.fixture
def d(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc
    from servers import ai_pro_hedef

    ns = ap.kur(monkeypatch, tmp_path, dongu_noop=False)
    kanca = {"tur": None, "ev": None, "girdi": threading.Event(), "a_iplik": None}

    def _yukle(self):
        if kanca["tur"] == "model" and kanca["ev"] is not None:
            ev, kanca["ev"] = kanca["ev"], None
            kanca["girdi"].set()
            assert ev.wait(10), "aparat: yükleme engeli kalkmadı"
            raise RuntimeError("model paketi yüklenemedi (zorlanmış)")
        return None

    def _kamera(*a, **k):
        if kanca["tur"] == "kamera" and kanca["ev"] is not None:
            ev, kanca["ev"] = kanca["ev"], None
            kanca["a_iplik"] = threading.get_ident()  # A'nın döngü iş parçacığı
            kanca["girdi"].set()
            assert ev.wait(10), "aparat: kamera engeli kalkmadı"
        if kanca["a_iplik"] == threading.get_ident():
            return _KapaliKamera()
        return _AcikKamera()

    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", _yukle)
    monkeypatch.setattr(ns.air.cv2, "VideoCapture", _kamera)
    canli = {"n": 0}
    gercek = ns.air._ai_pro_loop

    def _sayan(*a, **k):
        canli["n"] += 1
        try:
            return gercek(*a, **k)
        finally:
            canli["n"] -= 1

    monkeypatch.setattr(ns.air, "_ai_pro_loop", _sayan)
    ns.canli = canli
    ns.kanca = kanca
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.air._ai_loop_active = False
        ap.bekle(lambda: canli["n"] == 0, 8)
        ns.geri()


def _tur(d, tur: str, yaris: bool = True) -> dict:
    d.tahmin.engel = None
    ap.mandali_sifirla(d.c)
    d.air.stop_ai_pro()
    assert ap.bekle(lambda: d.canli["n"] == 0, 15), "aparat: önceki döngü bitmedi"
    ap.mandali_sifirla(d.c)
    ev = threading.Event()
    k = d.kanca
    k.update(tur=tur, ev=ev if yaris else None, a_iplik=None)
    k["girdi"].clear()
    _pa, ra = ap.onayli_baslat(d)  # A
    assert ra.status_code == 200, ra.text[:200]
    if yaris:
        assert k["girdi"].wait(8), f"aparat: A {tur} adımına ulaşmadı"
    assert d.c.post("/api/ai/pro/stop").status_code == 200  # operatör A'yı durdurur
    pid_b, rb = ap.onayli_baslat(d)  # ... ve hemen yeni onaylı seans B
    assert rb.status_code == 200 and rb.json().get("status") == "success", f"aparat: B açılmadı {rb.text[:200]}"
    n1 = d.tahmin.sayi
    assert ap.bekle(lambda: d.tahmin.sayi > n1, 5), "aparat: B sürmedi"
    ev.set()  # A'nın yüklemesi / kamerası ŞİMDİ hata ile döner
    if yaris:
        # A'nın döngüsü bitene kadar (kamera kolunda 5 × 0,5 sn yeniden deneme) + B'nin bir tur daha dönmesi.
        assert ap.bekle(lambda: d.canli["n"] <= 1, 8), "aparat: A'nın döngüsü bitmedi"
    time.sleep(1.5)
    with d.api._session_lock:
        s = dict(d.api._active_session)
    return {
        "b_seans_aktif": bool(s.get("is_active")) and s.get("onay_kimligi") == pid_b,
        "b_dongu_canli": d.canli["n"] >= 1 and bool(d.air._ai_loop_active),
        "calisan": ap.calisan(d),
    }


@pytest.mark.parametrize("tur", ["model", "kamera"])
def test_KRITIK_ESKI_dongu_baslangic_hatasi_YENI_seansi_OLDURMEZ_N30(d, tur):
    ihlal = 0
    ornek = None
    for _ in range(DENEME):
        s = _tur(d, tur)
        if not (s["b_seans_aktif"] and s["b_dongu_canli"] and s["calisan"]):
            ihlal += 1
            ornek = ornek or s
    assert ihlal == 0, (
        f"{tur}: {DENEME} denemenin {ihlal}'inde ESKİ döngünün başlangıç hatası (`_ai_seansi_pasife_al`) YENİ onaylı "
        f"seansı pasife çekti; B'nin döngüsü çıktı / bobinleri durdu. Örnek: {ornek}"
    )


def test_KARSIT_eski_dongu_hatasiz_biterse_yeni_seans_YASAR(d):
    for _ in range(3):
        s = _tur(d, "model", yaris=False)
        assert s["b_seans_aktif"] and s["b_dongu_canli"] and s["calisan"], s
