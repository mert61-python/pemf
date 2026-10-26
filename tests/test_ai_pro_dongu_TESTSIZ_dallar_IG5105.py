# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""İG-5.105 KAPISI — AI Pro döngüsünün TESTSİZ kalan iki dalı (B-5.19 paketi).

ÖLÇÜLDÜ (HEAD 5bc99be1, dal mutantları → AI Pro döngü kümesi, 57 dosya / 633 test):
  (1) `_ai_pro_loop` modeli YÜKLEYEMEZSE `_ai_seansi_pasife_al("model yüklenemedi", …)` çağrısı SİLİNSE de küme YEŞİL kalıyordu —
      `/ai/pro/start` seansı döngü thread'inden ÖNCE AKTİF açar; pasife alınmazsa panel / geçmiş bobin sürülmediği hâlde
      tedaviyi "sürüyor" gösterir, süre bekçisi dolana kadar kapanmaz (2026-09-09 düzeltmesinin kendisi kapısızdı).
  (2) Döngü kendi bitince (süre dolumu / hedef kaybı / dış durdurma) canlı E-alanı bağlamını TEMİZLER (`efield_live.set_context([])`
      ya da `temizle_degismediyse`) — bu temizlik silinse de küme YEŞİLDİ: sonraki (kedi) seansta E barı ESKİ hedefin değerini
      "canlı" gösterir. (OAK1 / C2-1.15 kapıları yalnız ters yönü — GEÇ kurulan bağlamın SİLİNMEDİĞİNİ — ölçüyordu.)
  (Döngünün kendi süre dolumu — `_sure_doldu` / `_dongu_bayragini_indir` — bugün `test_ai_pro_SURE_DOLUMU_kesinti_SAYILMAZ_C2_1_1`
   ve `test_ai_pro_dongu_TEARDOWN_STOPU` ile KIRMIZI olur; `test_target_lost` 6'lı demet iddiası D1.39'da kapanmış: 8'li sözleşme.)
GERÇEK `/ai/pro/start` onay akışı + GERÇEK `_ai_pro_loop` + `HardwareController` (kayıtçı donanım); kamera SAHTE (gerçek kamera
AÇILMAZ), sağlayıcı yüklemesi / tahmini yamalı.
"""

from __future__ import annotations

import threading
import time

import numpy as np


class _Kamera:
    acilan = 0

    def __init__(self, *a, **k):
        type(self).acilan += 1

    def isOpened(self):  # noqa: N802
        return True

    def read(self):
        return True, np.zeros((8, 8, 3), dtype=np.uint8)

    def release(self):
        pass


def _kur(monkeypatch, tmp_path, *, yukle):
    import ai_pro_aparati as ap
    from servers import ai_pro_hedef

    gercek_tahmin = __import__("servers.ai_router", fromlist=["x"])._predict_and_drive
    ns = ap.kur(monkeypatch, tmp_path, dongu_noop=False)
    monkeypatch.setattr(ns.air, "_predict_and_drive", gercek_tahmin)
    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "predict", lambda self, *a, **k: ([0.3] * 7, [0.0] * 7, 1.0))
    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", yukle)
    _Kamera.acilan = 0
    monkeypatch.setattr(ns.air.cv2, "VideoCapture", _Kamera)
    return ns


def _dongu_yok(sure: float) -> bool:
    son = time.monotonic() + sure
    while time.monotonic() < son:
        if not any(t.name == "ai-pro-dongu" and t.is_alive() for t in threading.enumerate()):
            return True
        time.sleep(0.05)
    return False


def test_KRITIK_IG5105_model_YUKLENEMEZSE_kendi_seansi_PASIFE_alinir_kamera_ACILMAZ(monkeypatch, tmp_path):
    """MUTASYON: `_ai_pro_loop`taki `_ai_seansi_pasife_al("model yüklenemedi", dongu_muhru)` satırını silmek → KIRMIZI."""
    import ai_pro_aparati as ap
    from kayitci_donanim import gercek_hc

    def _yuklenemez(self):
        raise RuntimeError("IG5105 model paketi yüklenemedi (zorlanmış)")

    ns = _kur(monkeypatch, tmp_path, yukle=_yuklenemez)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            pid, r = ap.onayli_baslat(ns, organ=2, sure_dk=5)
            assert r.status_code == 200, f"aparat: /start {r.status_code} {r.text[:200]}"
            assert _dongu_yok(8.0), "aparat: döngü model hatasından sonra bitmedi"
            with ns.api._session_lock:
                s = dict(ns.api._active_session)
            assert s.get("onay_kimligi") == pid, f"aparat: seans bu onayın değil: {s.get('onay_kimligi')!r}"
            assert not s.get("is_active"), (
                "model YÜKLENEMEDİ, döngü hiç sürmedi ama oturum AI modunda AKTİF kaldı — panel ve seans geçmişi tedavi "
                "sürüyormuş gibi gösterir (süre bekçisi dolana kadar)"
            )
            assert _Kamera.acilan == 0, (
                "model yüklenemediği hâlde kabin kamerası AÇILDI (kamera modelden SONRA açılmalı)"
            )
            assert not ap.calisan(ns), f"model hatasında bobin sürüldü: {ap.calisan(ns)}"
    finally:
        ap.dongu_bitir(ns.air)
        ns.air._ai_loop_active = False
        ns.geri()


def test_KRITIK_IG5105_dongu_KENDI_bitince_canli_E_baglamini_TEMIZLER(monkeypatch, tmp_path):
    """Seans sırasında kurulmuş canlı E bağlamı, döngü kendi süre dolumuyla bitince temizlenir (sonraki seansa sızmaz).
    ⚠️ Bu yolda temizliği İKİ yer yapar (teardown bloğu + `update_live_session_state(is_active=False, e_baglam_nesli=…)`) —
    teardown bloğu etkisizken bu test YEŞİL kalır (ölçüldü); teardown'ın TEK başına taşıdığı yol bir sonraki testte."""
    import ai_pro_aparati as ap
    from kayitci_donanim import gercek_hc
    from servers import efield_live as ef

    ns = _kur(monkeypatch, tmp_path, yukle=lambda self: None)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            _pid, r = ap.onayli_baslat(ns, organ=2, sure_dk=1)
            assert r.status_code == 200, r.text[:200]
            assert ap.bekle(lambda: bool(ap.calisan(ns)), 5), "aparat: döngü sürmedi"
            ef.set_context(
                [{"centroid_cabin_mm": [10.0, 20.0, 30.0], "organ_id": 1}], model="fantom"
            )  # seans içi analiz
            assert ef.get_context() is not None, "aparat: bağlam kurulamadı"
            ns.air._ai_started_at = time.monotonic() - 60.0  # döngünün KENDİ süre dolumu
            assert _dongu_yok(8.0), "aparat: döngü kendi süre dolumunda bitmedi"
            assert ef.get_context() is None, (
                f"AI Pro döngüsü bitti ama canlı E bağlamı KALDI ({ef.get_context()}) — sonraki seansta E barı eski hedefin "
                "değerini 'canlı' gösterir"
            )
    finally:
        ap.dongu_bitir(ns.air)
        ns.air._ai_loop_active = False
        ef.set_context([])
        ns.geri()


def test_KRITIK_IG5105_BASKA_seans_aktifken_biten_dongu_de_E_baglamini_TEMIZLER(monkeypatch, tmp_path):
    """Döngü bittiğinde O AN başka bir seans (yeni onay) aktifse teardown canlı durumu ezmez (`_baskasi_aktif`) — bu yolda
    `update_live_session_state` ÇAĞRILMAZ ve biten AI Pro seansının E bağlamını yalnız teardown bloğu temizler. Temizlenmezse
    yeni seansın E barı ESKİ hedefin değerini "canlı" gösterir.
    MUTASYON: teardown'daki `_ef2.set_context([])` / `temizle_degismediyse` dalını etkisiz kılmak → KIRMIZI."""
    import ai_pro_aparati as ap
    from kayitci_donanim import gercek_hc
    from servers import efield_live as ef

    ns = _kur(monkeypatch, tmp_path, yukle=lambda self: None)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            _pid, r = ap.onayli_baslat(ns, organ=2, sure_dk=1)
            assert r.status_code == 200, r.text[:200]
            assert ap.bekle(lambda: bool(ap.calisan(ns)), 5), "aparat: döngü sürmedi"
            ef.set_context([{"centroid_cabin_mm": [10.0, 20.0, 30.0], "organ_id": 1}], model="fantom")
            with ns.api._session_lock:  # o arada başka bir onaylı seans açılmış (aktif, onay kimliği FARKLI)
                ns.api._active_session["onay_kimligi"] = "IG5105-baska-onay"
            ns.air._ai_started_at = time.monotonic() - 60.0
            assert _dongu_yok(8.0), "aparat: döngü kendi süre dolumunda bitmedi"
            with ns.api._session_lock:
                assert ns.api._active_session.get("is_active"), (
                    "aparat: 'başka seans' teardown'da kapatıldı (yol yanlış)"
                )
            assert ef.get_context() is None, (
                f"biten AI Pro döngüsünün canlı E bağlamı KALDI ({ef.get_context()}) — o an aktif olan başka seansın E barı "
                "eski hedefin değerini 'canlı' gösterir"
            )
    finally:
        ap.dongu_bitir(ns.air)
        ns.air._ai_loop_active = False
        ef.set_context([])
        with ns.api._session_lock:
            ns.api._active_session["is_active"] = False
        ns.geri()
