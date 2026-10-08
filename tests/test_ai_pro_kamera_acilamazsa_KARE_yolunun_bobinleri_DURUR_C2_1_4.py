# -*- coding: utf-8 -*-
"""C2-1.4 (2-C inceleme, A1) — AI Pro döngüsü kamera AÇILAMADAN ölünce, kare yolunun (`/frame`) sürdüğü bobinler DURUR ve
satır "İptal Edildi" (bobin sürülmedi) yazılmaz.

KUSUR: `/ai/pro/start` sunucu kamerası döngüsünü açar; kamera açılamazsa döngü 5×0,5 sn dener ve `_ai_seansi_pasife_al` ile
oturumu pasife alır. Bu pencerede istemci kare yolu (`/api/ai/ai_pro/frame`, mühürlü seans) bobinleri SÜRMÜŞ olabilir.
`_ai_seansi_pasife_al` STOP GÖNDERMEZ (2026-09-09'dan beri; 2-C öncesi) → 7 bobin keep-alive ile ENERJİLİ kalır; oturum pasif
olduğu için süre bekçisi de onları görmez (ölçüldü: döngü öldükten sonra çalışan [1..7], ikinci kare de durdurmadı). D2.E07
(`047155e`) aynı yola satır kapanışını ekledi ve "bobin SÜRMEDEN öldü" varsayımıyla `iptal-ai-pro` → **cancelled** yazar —
uygulanmış tedavi geçmişte "İptal Edildi" görünür ve kapanış DB yazımı STOP'suz koşar (§9 Grup 1 (iii)).
Kapı GERÇEK `_ai_pro_loop` (kamera AÇILAMAZ — gerçek kamera açılmaz), GERÇEK onay akışı, GERÇEK `/frame`, GERÇEK
`HardwareController` (`gercek_hc`), GERÇEK `TreatmentHistoryDB`.
KARŞIT: hiçbir bobin sürülmeden kamera açılamazsa satır "cancelled" kalır (D2.E07 davranışı).
"""

from __future__ import annotations

import time

import pytest


class _KameraYok:
    def __init__(self, *a, **k):
        pass

    def isOpened(self):  # noqa: N802
        return False

    def read(self):
        return False, None

    def release(self):
        pass


@pytest.fixture
def ns(monkeypatch, tmp_path):
    import ai_pro_aparati as ap
    from kayitci_donanim import gercek_hc
    from servers import ai_pro_hedef

    ns = ap.kur(monkeypatch, tmp_path, dongu_noop=False)
    try:
        monkeypatch.setattr(ns.air.cv2, "VideoCapture", _KameraYok)
        monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", lambda self: None)
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
            ap.dongu_bitir(ns.air)
            ns.c.post("/api/ai/pro/stop")
    finally:
        ap.dongu_bitir(ns.air)
        ns.air._ai_loop_active = False
        ns.geri()


def _baslat(ns):
    import ai_pro_aparati as ap

    _pid, r = ap.onayli_baslat(ns, organ=0)
    assert r.status_code == 200, r.text[:200]
    with ns.api._session_lock:
        return ns.api._active_session.get("db_session_id")


def _dongu_olsun(ns):
    import ai_pro_aparati as ap

    assert ap.bekle(lambda: ap.dongu_bitir(ns.air, 0.01) == 0 and not ns.air._ai_loop_active, 8.0)
    time.sleep(0.3)


def _durum(ns, sid):
    with ns.db._get_connection() as c:
        return c.execute("SELECT session_status FROM treatment_sessions WHERE id=?", (sid,)).fetchone()[0]


def test_KRITIK_C2_1_4_kamera_acilamazsa_KARE_yolunun_surdugu_bobinler_DURUR(ns):
    import ai_pro_aparati as ap

    sid = _baslat(ns)
    assert ap.kare(ns).status_code == 200
    assert ap.bekle(lambda: bool(ap.calisan(ns)), 2), "aparat: kare yolu bobinleri sürmedi"
    _dongu_olsun(ns)
    with ns.api._session_lock:
        assert not ns.api._active_session.get("is_active"), "ön koşul: döngü oturumu pasife almalı"
    assert ap.calisan(ns) == [], (
        f"döngü (kamera açılamadı) oturumu pasife aldı ama kare yolunun sürdüğü bobinler {ap.calisan(ns)} ENERJİLİ kaldı — "
        "oturum pasif olduğu için süre bekçisi de durdurmaz"
    )
    assert _durum(ns, sid) != "cancelled", "bobin sürülmüş tedavi 'İptal Edildi' (bobin sürülmedi) kaydedildi"


def test_KARSIT_C2_1_4_hic_surulmeden_kamera_acilamazsa_IPTAL_EDILDI(ns):
    import ai_pro_aparati as ap

    sid = _baslat(ns)
    _dongu_olsun(ns)
    assert ap.calisan(ns) == []
    assert _durum(ns, sid) == "cancelled"


def test_KRITIK_C2_1_4_STOP_satir_kapanisindan_ONCE_gider(ns, monkeypatch):
    """Orkestratör eki (2-C incelemesi): kamera açılamadan ölen döngünün STOP'u, satır kapanışından (tedavi DB yazımı) ÖNCE
    gider — kilitli tedavi DB'sinde kapanış STOP'u bekletmesin (Ö.4-Y8; E07 "kapanış STOP'TAN SONRA" ilkesi)."""
    import ai_pro_aparati as ap

    sira: list = []
    orj_stop = ns.api._stop_session_coils
    orj_kapat = ns.air._ai_pro_satirini_kapat

    def _stop(*a, **k):
        sira.append("stop")
        return orj_stop(*a, **k)

    def _kapat(*a, **k):
        sira.append("kapat")
        return orj_kapat(*a, **k)

    monkeypatch.setattr(ns.api, "_stop_session_coils", _stop)
    monkeypatch.setattr(ns.air, "_ai_pro_satirini_kapat", _kapat)
    _baslat(ns)
    assert ap.kare(ns).status_code == 200
    assert ap.bekle(lambda: bool(ap.calisan(ns)), 2), "aparat: kare yolu bobinleri sürmedi"
    _dongu_olsun(ns)
    assert "kapat" in sira, f"aparat: satır kapanışı çağrılmadı: {sira}"
    assert "stop" in sira and sira.index("stop") < sira.index("kapat"), (
        f"STOP satır kapanışından SONRA ya da hiç: {sira}"
    )
