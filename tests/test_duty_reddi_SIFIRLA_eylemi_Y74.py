# Author: mertaygn, cglrgrkn
"""Y74 (sahip, 1-G inceleme S-İG1) — seansta firmware duty reddi ACİL DURDUR yolundan durdurur ve mandal KURULU KALIR
(güvence katmanı aynen); yalnız METİN düzelir: "Duty'yi %50 ya da altına indirin (ya da bobini Unipolar yapın), sonra
'Sıfırla'ya basın." Ret sonrası başlatma 409 / engel metinleri de aynı eylemi söyler (1-G §8 #2). STOP yolu DEĞİŞMEZ.

ÖLÇÜLEN KUSURLAR (önce-kırmızı):
  * Seansta red bildirimi yalnız "Duty'yi %50 ya da altına indirin …" diyordu; mandal kurulu olduğu için operatör duty'yi
    düzeltip başlatınca "ACİL DURDURMA MANDALLI … 'Sıfırla'" 409'una çarpıyordu (1-G inceleme Kapsam 6, ölçüldü).
  * Ret sonrası dar pencerede (kart sistematik reddediyor) `/session/start` 409'u, AI Pro 409'u ve HardwareController
    başlatma engeli "firmware sürümü bu uygulamayla uyuşmuyor … kartı yeniden programlayın" diyordu — kart güncel,
    reddedilen İSTEK; operatör yanlış eyleme (yeniden programlama) yönlenir.

KAPI (D1.101 aparatı: GERÇEK `HeadlessCore._handle_stm_line` → taze EventBus + gerçek handler'lar → gerçek
`_emergency_stop_all`; NACK satırı ürünün GERÇEK paketinin firmware aynasıyla reddiyle üretilir):
  1. Seansta red → bildirim "sonra 'Sıfırla'ya basın" der; mandal KURULU; STOP donanıma gider (yol aynen).
  2. Seanssız red → mandal KURULMAZ, bildirim "Sıfırla" DEMEZ (yanlış eylem olurdu).
  3. Ret penceresi: HC başlatma engeli ve `/session/start` 409 duty eylemini söyler (firmware metni DEĞİL); mandal
     kuruluysa engel "Sıfırla" der, sıfırlandıktan sonra demez.
"""

from __future__ import annotations

import copy
import logging
import sys
import threading
import time
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from kayitci_donanim import gercek_hc  # noqa: E402

import tools.stm32_simulator as sim  # noqa: E402

_YANLIS_EYLEM = ("firmware sürümü", "yeniden programlayın", "firmware/protokol")
_SIFIRLA = "sonra 'Sıfırla'ya basın"


def _nack_satiri(bobin: int = 1, duty: float = 80.0) -> str:
    from servers import live_state as ls

    ls.stm_komut_kabulu_bildir()
    with gercek_hc() as hc:
        assert hc.update_coil(bobin, 100.0, duty, 0.0, 5, start=True) is True
        sonuc, sebep = sim.decode_packet(hc.core._hw_send_queue.paketler[-1])
    assert sonuc is None and "field=duty" in (sebep or ""), f"aparat: paket duty tavanı ile reddedilmedi: {sebep!r}"
    return f"-> STM_NACK: {sebep}"


def _estop_bekle(sure: float = 15.0) -> None:
    bitis = time.monotonic() + sure
    while time.monotonic() < bitis:
        canli = [t for t in threading.enumerate() if t.name.startswith("estop-stm")]
        if not canli:
            return
        for t in canli:
            t.join(timeout=0.2)
    raise AssertionError(f"E-stop iş parçacığı {sure} sn'de bitmedi")


class _KaydediciDonanim:
    def __init__(self):
        self.stop_all = 0

    def stop_all_coils(self):
        self.stop_all += 1
        return True

    def on_disconnect(self):
        return True


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    import event_bus as eb
    import headless_core as hcm
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import live_state as ls
    from utils import estop_mandali

    db = TreatmentHistoryDB(tmp_path)
    bildirimler: list = []
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(api, "_push_notification", lambda m, t="info": bildirimler.append((m, t)))
    yeni_bus = eb.EventBus()
    monkeypatch.setattr(eb, "_event_bus_instance", yeni_bus)
    monkeypatch.setattr(api, "_event_bus_registered", False)
    ls.stm_komut_kabulu_bildir()
    with api._stm_nack_lock:
        api._stm_nack_son.clear()
    with api._session_lock:
        eski_seans = dict(api._active_session)
    with ls._live_state_lock:
        eski_canli = copy.deepcopy(ls._live_state)
    assert not estop_mandali.mandalli_mi(), "aparat: test mandal KURULU başladı (önceki testten sızıntı)"
    core = hcm.HeadlessCore.__new__(hcm.HeadlessCore)
    core.logger = logging.getLogger("test-y74")
    core.event_bus = yeni_bus
    try:
        api._register_event_bus_handlers()
        yield api, db, core, bildirimler
    finally:
        _estop_bekle()
        ls.stm_komut_kabulu_bildir()
        with api._stm_nack_lock:
            api._stm_nack_son.clear()
        with api._session_lock:
            api._active_session.clear()
            api._active_session.update(eski_seans)
        with ls._live_state_lock:
            ls._live_state.clear()
            ls._live_state.update(eski_canli)
        yeni_bus.shutdown()


def _duty_bildirimleri(bildirimler) -> list[str]:
    return [m for m, _t in bildirimler if "duty" in m and "REDDETTİ" in m]


def test_KRITIK_seansta_duty_reddi_bildirimi_SIFIRLA_der_mandal_KURULU_STOP_gider(ortam, monkeypatch):
    from utils import estop_mandali

    api, db, core, bildirimler = ortam
    hw = _KaydediciDonanim()
    monkeypatch.setattr(api.state, "hardware", hw)
    sid = db.start_session(treatment_mode="Manuel", target_condition="test", patient_name="Pamuk")
    with api._session_lock:
        api._active_session.clear()
        api._active_session.update(
            {
                "is_active": True,
                "session_id": "y74",
                "coil_ids": [1, 2],
                "db_session_id": sid,
                "started_epoch": time.time() - 60,
                "start_mono": time.monotonic() - 60,
            }
        )
    core._handle_stm_line(_nack_satiri(bobin=1, duty=80.0), None)
    _estop_bekle()
    assert estop_mandali.mandalli_mi(), "Y74: seansta duty reddi mandalı KURMALI (güvence katmanı aynen) — kurmadı"
    assert hw.stop_all >= 1, "Y74: STOP yolu değişmemeli — donanıma STOP gitmedi"
    m = _duty_bildirimleri(bildirimler)
    assert len(m) == 1, f"tek red için {len(m)} duty bildirimi: {bildirimler!r}"
    assert _SIFIRLA in m[0], (
        f"seansta red mandalı kurdu ama bildirim ikinci adımı ('Sıfırla') söylemiyor: {m[0]!r} — operatör duty'yi düzeltip "
        "başlatınca mandal 409'una çarpar"
    )
    assert all(p in m[0] for p in ("%50", "Unipolar", "seans DURDURULDU")), m[0]


def test_KRITIK_seanssiz_duty_reddi_mandal_KURMAZ_bildirim_SIFIRLA_DEMEZ(ortam, monkeypatch):
    from utils import estop_mandali

    api, _db, core, bildirimler = ortam
    with api._session_lock:
        api._active_session.clear()
        api._active_session.update({"is_active": False})
    with gercek_hc() as hc:
        monkeypatch.setattr(api.state, "hardware", hc)
        core._handle_stm_line(_nack_satiri(bobin=1, duty=80.0), None)
    assert not estop_mandali.mandalli_mi(), "seanssız duty reddi mandal KURDU (Y74 kapsamı dışı)"
    m = _duty_bildirimleri(bildirimler)
    assert m and _SIFIRLA not in m[0], f"mandal kurulmadığı hâlde bildirim 'Sıfırla' diyor (yanlış eylem): {m!r}"


def test_KRITIK_ret_penceresinde_baslatma_engeli_ve_409_DUTY_eylemini_soyler(ortam, monkeypatch):
    from fastapi.testclient import TestClient
    from servers import live_state as ls
    from utils import estop_mandali

    api, _db, _core, _b = ortam
    nack = _nack_satiri(bobin=1, duty=80.0)
    assert ls.stm_komut_reddi_bildir(nack) is True, "aparat: duty reddi sistematik sayılmadı"
    with gercek_hc() as hc:
        estop_mandali.mandalla("y74-test")
        try:
            engel_mandalli = hc._stm_baslatma_engeli()
        finally:
            estop_mandali.sifirla()
        engel = hc._stm_baslatma_engeli()
        monkeypatch.setattr(api.state, "hardware", hc)
        r = TestClient(api.app, client=("127.0.0.1", 50074)).post(
            "/api/session/start",
            json={
                "mode": "Manuel",
                "frequency": 100,
                "duty": 40,
                "phase": 0,
                "intensity": 0,
                "duration_minutes": 5,
                "coil_ids": [1],
                "patient_name": "Y74",
            },
        )
    for ad, metin in (("HC engeli (mandallı)", engel_mandalli), ("HC engeli", engel), ("/session/start 409", r.text)):
        assert "Duty'yi" in metin and not any(y in metin for y in _YANLIS_EYLEM), (
            f"{ad}: duty reddinden sonra eylem yanlış (firmware uyuşmazlığı gibi): {metin[:300]!r}"
        )
    assert r.status_code == 409, r.text[:300]
    assert _SIFIRLA in engel_mandalli and _SIFIRLA not in engel, (
        f"'Sıfırla' yalnız mandal kuruluyken söylenmeli: mandallı={engel_mandalli!r} · sıfırlanmış={engel!r}"
    )


def test_KRITIK_ret_penceresinde_AI_Pro_409_DUTY_eylemini_soyler(monkeypatch, tmp_path):
    """AI Pro başlatma (GERÇEK onay akışı) kart sistematik reddederken 409 — metin duty eylemi, firmware DEĞİL."""
    import ai_pro_aparati as ap
    from servers import live_state as ls

    nack = _nack_satiri(bobin=1, duty=80.0)
    o = ap.kur(monkeypatch, tmp_path)
    try:
        with gercek_hc() as hc:
            o.hc = hc
            monkeypatch.setattr(o.api.state, "hardware", hc)
            assert ls.stm_komut_reddi_bildir(nack) is True, "aparat: duty reddi sistematik sayılmadı"
            _pid, r = ap.onayli_baslat(o)
    finally:
        o.geri()
    assert r.status_code == 409, r.text[:300]
    assert "Duty'yi" in r.text and not any(y in r.text for y in _YANLIS_EYLEM), (
        f"AI Pro başlatma reddi duty reddinden sonra firmware uyuşmazlığı gibi anlatıldı: {r.text[:300]!r}"
    )
