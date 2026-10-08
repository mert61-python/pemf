# -*- coding: utf-8 -*-
"""C2-1.1 (2-C inceleme, A1) — AI Pro döngüsünün KENDİ süre dolumu satırı "Kesintiye Uğradı" yazdırmamalı.

KUSUR (D2.E07, `047155e`): `_ai_pro_loop` kapanışı "seans hâlâ AKTİF ve operatör durdurmuyorsa → döngü KENDİ kesildi"
der ve satırı `ai-pro-kesinti` (→ `interrupted`) ile kapatır. Döngünün KENDİ süre sayacı (`remaining <= 0` →
`_dongu_bayragini_indir`) süre bekçisinden ÖNCE dolar (`_ai_started_at` `start_mono`dan önce alınır + `int()` kırpması
≤1 sn erken) → tam süresini dolduran tedavi süre bekçisi yetişmezse "Kesintiye Uğradı" kaydedilir. Doğru: "completed"
(süre bekçisinin `sure-doldu` kapanışıyla aynı).

Kapı GERÇEK `_ai_pro_loop` (sahte kamera — gerçek kamera AÇILMAZ), GERÇEK onay akışı, GERÇEK `TreatmentHistoryDB`; süre
bekçisi bu kolda koşmaz (TestClient yaşam döngüsü başlatmaz) → döngünün kendi süre dolumu belirlenimci ölçülür.
KARŞIT: döngü süre dolmadan kesilirse (bayrak iner, seans aktif) `interrupted` kalır (D2.E07 kapısının kolu).
"""

from __future__ import annotations

import time

import numpy as np


class _Kamera:
    def __init__(self, *a, **k):
        pass

    def isOpened(self):  # noqa: N802
        return True

    def read(self):
        return True, np.zeros((8, 8, 3), dtype=np.uint8)

    def release(self):
        pass


def _kur(monkeypatch, tmp_path):
    import ai_pro_aparati as ap
    from servers import ai_pro_hedef

    gercek_tahmin = __import__("servers.ai_router", fromlist=["x"])._predict_and_drive
    ns = ap.kur(monkeypatch, tmp_path, dongu_noop=False)
    monkeypatch.setattr(ns.air, "_predict_and_drive", gercek_tahmin)
    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "predict", lambda self, *a, **k: ([0.3] * 7, [0.0] * 7, 1.0))
    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", lambda self: None)
    monkeypatch.setattr(ns.air.cv2, "VideoCapture", _Kamera)
    return ns


def _durum(ns, sid):
    with ns.db._get_connection() as c:
        return tuple(
            c.execute("SELECT session_status, end_time FROM treatment_sessions WHERE id = ?", (sid,)).fetchone()
        )


def _dongu_bitmesini_bekle(sure: float) -> bool:
    import threading

    son = time.monotonic() + sure
    while time.monotonic() < son:
        if not any(t.name == "ai-pro-dongu" and t.is_alive() for t in threading.enumerate()):
            return True
        time.sleep(0.05)
    return False


def test_KRITIK_C2_1_1_dongunun_KENDI_SURE_DOLUMU_satiri_TAMAMLANDI_yazar(monkeypatch, tmp_path):
    import ai_pro_aparati as ap
    from kayitci_donanim import gercek_hc

    ns = _kur(monkeypatch, tmp_path)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            _pid, r = ap.onayli_baslat(ns, organ=2, sure_dk=1)
            assert r.status_code == 200, r.text[:200]
            with ns.api._session_lock:
                sid = ns.api._active_session.get("db_session_id")
            assert ap.bekle(lambda: bool(ap.calisan(ns)), 5), "aparat: döngü sürmedi"
            # Tedavi süresinin SONUNA gelinmiş gibi: döngünün süre sayacı (ürünün kendi `_ai_started_at`'ı) 60 sn geri.
            ns.air._ai_started_at = time.monotonic() - 60.0
            assert _dongu_bitmesini_bekle(8.0), "döngü kendi süre dolumunda bitmedi"
            assert not ap.calisan(ns), (
                "süre dolumunda bobinler DURMADI (güvenlik — bu kapının konusu değil ama ön koşul)"
            )
        durum, bitis = _durum(ns, sid)
        assert (durum, bool(bitis)) == ("completed", True), (
            f"tam süresini dolduran AI Pro tedavisi '{durum}' yazıldı (döngünün kendi süre dolumu kesinti sayıldı)"
        )
    finally:
        ap.dongu_bitir(ns.air)
        ns.air._ai_loop_active = False
        ns.geri()


def test_KARSIT_C2_1_1_sure_DOLMADAN_kesilen_dongu_KESINTIYE_UGRADI_kalir(monkeypatch, tmp_path):
    import ai_pro_aparati as ap
    from kayitci_donanim import gercek_hc

    ns = _kur(monkeypatch, tmp_path)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            _pid, r = ap.onayli_baslat(ns, organ=2, sure_dk=1)
            assert r.status_code == 200, r.text[:200]
            with ns.api._session_lock:
                sid = ns.api._active_session.get("db_session_id")
            assert ap.bekle(lambda: bool(ap.calisan(ns)), 5), "aparat: döngü sürmedi"
            assert ap.dongu_bitir(ns.air, 8.0) == 0
        durum, bitis = _durum(ns, sid)
        assert (durum, bool(bitis)) == ("interrupted", True), f"süre dolmadan kesilen döngü: {durum!r}"
    finally:
        ns.air._ai_loop_active = False
        ns.geri()
