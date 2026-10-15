# Author: mertaygn, cglrgrkn
"""D1.101 · B-8.13 · Y20 (sahip) — backend kolu: kartın duty TAVANI reddi operatöre NEDEN ve EYLEM olarak söylenir,
seans durur, reddedilen istek STOP'ları bekletmez.

Firmware tavan üstü duty'yi NACK'ler (`main.c`; kapı `test_firmware_DUTY_TAVANI_NACK_D1101.py`). Sahip Y20: "Backend'e ve
arayüze duty sınırı EKLENMEZ. Sistematik NACK seansı durdurur; operatör nedenini açıkça görmeli."

ÖLÇÜLEN KUSURLAR (önce-kırmızı, D1.101 backend değişikliği olmadan):
  1. Bildirim/durdurma metni "STM32 kartı komutları REDDEDİYOR (firmware sürümü bu uygulamayla uyuşmuyor) … kartı yeniden
     programlayın" diyordu — kart güncel; reddedilen İSTEKTİR. Operatör yanlış eyleme (yeniden programlama) yönlenir.
  2. Firmware paketi BÜTÜN reddeder. Reddedilen istek `HardwareController` durumunda kaldıkça HER paket (keep-alive,
     başka bobinin STOP'u) yine reddedilir: seanssız sürüşte çalışan bobinin STOP'u karta UYGULANMAZ, bobin ancak
     firmware ölü-adamıyla (1,5 sn) durur — Ö.4-Y8 ihlali. Seansta durdurma 3. NACK'i (~1-1,5 sn) bekliyordu.

KAPI GERÇEK zinciri koşar: GERÇEK `HeadlessCore._handle_stm_line` (firmware'in ham NACK satırı) → taze `EventBus` +
gerçek `_register_event_bus_handlers` → `_handle_backend_event` → (seansta) `estop-…` iş parçacığı → gerçek
`_emergency_stop_all`. NACK metni elle YAZILMAZ: ürünün GERÇEK paketi simülatör aynasıyla (`decode_packet`; firmware'e
Windows kapısıyla pinli) reddettirilerek üretilir. Seanssız kolda donanım GERÇEK `HardwareController` (kayıtçı kuyruk).
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

_YANLIS_EYLEM = ("firmware sürümü", "yeniden programlayın", "Project → Clean")


def _nack_satiri(bobin: int = 1, duty: float = 80.0, kip: int = 0x00, diger=()) -> str:
    """Ürünün GERÇEK paketini firmware aynasıyla reddettir → kartın ham NACK satırı."""
    from servers import live_state as ls

    ls.stm_komut_kabulu_bildir()  # HC başlatma kapısı süreç-geneli red kararına takılmasın
    with gercek_hc() as hc:
        hc.surus_kipi_ayarla(kip)
        for b, d in diger:
            assert hc.update_coil(b, 100.0, d, 0.0, 5, start=True) is True
        assert hc.update_coil(bobin, 100.0, duty, 0.0, 5, start=True) is True
        sonuc, sebep = sim.decode_packet(hc.core._hw_send_queue.paketler[-1])
    assert sonuc is None and "field=duty" in (sebep or ""), f"aparat: paket duty tavanı ile reddedilmedi: {sebep!r}"
    return f"-> STM_NACK: {sebep}"


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    import event_bus as eb
    import headless_core as hcm
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import live_state as ls

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
        api._stm_nack_son.clear()  # bildirim bastırma penceresi önceki testten sızmasın
    with api._session_lock:
        eski_seans = dict(api._active_session)
    with ls._live_state_lock:
        eski_canli = copy.deepcopy(ls._live_state)
    core = hcm.HeadlessCore.__new__(hcm.HeadlessCore)
    core.logger = logging.getLogger("test-d1101")
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


def _estop_bekle(sure: float = 15.0) -> list[str]:
    bitis = time.monotonic() + sure
    gorulen: list[str] = []
    while time.monotonic() < bitis:
        canli = [t for t in threading.enumerate() if t.name.startswith("estop-stm")]
        gorulen.extend(t.name for t in canli if t.name not in gorulen)
        if not canli:
            return gorulen
        for t in canli:
            t.join(timeout=0.2)
    raise AssertionError(f"E-stop iş parçacığı {sure} sn'de bitmedi: {gorulen}")


class _KaydediciDonanim:
    def __init__(self):
        self.stop_all = 0

    def stop_all_coils(self):
        self.stop_all += 1
        return True

    def on_disconnect(self):
        return True


def _aktif_seans_kur(api, db, coil_ids):
    sid = db.start_session(treatment_mode="Manuel", target_condition="test", patient_name="Pamuk")
    with api._session_lock:
        api._active_session.clear()
        api._active_session.update(
            {
                "is_active": True,
                "session_id": "d1101-duty-reddi",
                "coil_ids": list(coil_ids),
                "db_session_id": sid,
                "started_epoch": time.time() - 60,
                "start_mono": time.monotonic() - 60,
            }
        )
    return sid


def _duty_bildirimleri(bildirimler) -> list[str]:
    # TD6 · K3: sade metin ("Bobin N çift yönlü kipte en fazla %… çalışabilir; %… kabul edilmedi. Duty'yi …") — eski
    # "UYGULANAMAZ — kart komutu REDDETTİ" jargonu kalktı.
    return [m for m, _t in bildirimler if "Duty'yi" in m and "kabul edilmedi" in m]


# ── sayaç: duty reddi gürültü değil — TEK NACK sistematik karardır; CRC eşiği DEĞİŞMEDİ ──────────────────────────


def test_KRITIK_duty_reddi_TEK_NACK_ta_sistematik_CRC_ve_diger_RANGE_esigi_DEGISMEDI():
    from servers import live_state as ls

    duty = _nack_satiri()
    ls.stm_komut_kabulu_bildir()
    try:
        assert [ls.stm_komut_reddi_bildir(duty) for _ in range(3)] == [True, False, False], (
            "duty tavanı reddi ilk NACK'te sistematik sayılmadı (reddedilen paket keep-alive'da kalır, STOP'lar bekler)"
        )
        ls.stm_komut_kabulu_bildir()
        assert [ls.stm_komut_reddi_bildir("-> STM_NACK: CRC") for _ in range(3)] == [False, False, True]
        ls.stm_komut_kabulu_bildir()
        freq = "-> STM_NACK: RANGE coil=1 field=freq value_milli=0 min_milli=1000 max_milli=25000000"
        assert [ls.stm_komut_reddi_bildir(freq) for _ in range(3)] == [False, False, True], (
            "duty DIŞI aralık NACK'i de tek NACK'te sistematik sayıldı (gürültü eşiği yalnız duty tavanı için kalkar)"
        )
    finally:
        ls.stm_komut_kabulu_bildir()


# ── seansta: ilk duty reddinde seans DURUR, bildirim NEDENİ ve EYLEMİ söyler ───────────────────────────────────────


def test_KRITIK_seansta_ILK_duty_reddi_seansi_DURDURUR_neden_ve_eylem_SOYLER(ortam, monkeypatch):
    from database.treatment_history_db import SEANS_DURUMU_ACIL_DURDURMA

    api, db, core, bildirimler = ortam
    hw = _KaydediciDonanim()
    monkeypatch.setattr(api.state, "hardware", hw)
    sid = _aktif_seans_kur(api, db, [1, 2])
    satir = _nack_satiri(bobin=1, duty=80.0)
    core._handle_stm_line(satir, None)  # TEK NACK
    assert _estop_bekle(), "ilk duty reddinde seans durdurma (E-stop yolu) HİÇ başlamadı"
    with api._session_lock:
        assert api._active_session.get("is_active") is False, "kart duty'yi reddetti ama seans 'aktif' kaldı"
    with db._get_connection() as conn:
        durum = conn.execute("SELECT session_status FROM treatment_sessions WHERE id=?", (sid,)).fetchone()[0]
        olaylar = conn.execute("SELECT event_type, payload FROM session_events WHERE session_id=?", (sid,)).fetchall()
    assert durum == SEANS_DURUMU_ACIL_DURDURMA, f"kayıt {durum!r}"
    estop = [p for e, p in olaylar if e == "emergency_stop" and "stm_komut_reddi" in (p or "")]
    assert estop and "Duty Reddedildi" in estop[0], f"denetim izinde duty reddi sebepli acil durdurma yok: {olaylar!r}"
    metinler = _duty_bildirimleri(bildirimler)
    assert len(metinler) == 1, f"tek red için {len(metinler)} duty bildirimi: {bildirimler!r}"
    m = metinler[0]
    for parca in ("Bobin 1", "%80", "çift yönlü", "%50", "seans DURDURULDU", "Sürüş Kipi", "Unipolar"):
        assert parca in m, f"bildirimde {parca!r} yok: {m!r}"
    assert not any(y in m for y in _YANLIS_EYLEM), f"duty reddi firmware uyuşmazlığı gibi anlatıldı: {m!r}"
    assert not any("firmware sürümü" in b for b, _t in bildirimler), (
        f"yanlış eylem bildirimi de basıldı: {bildirimler!r}"
    )


def test_KRITIK_tek_bacak_tavani_reddi_UNIPOLAR_eylemi_soyler(ortam, monkeypatch):
    api, db, core, bildirimler = ortam
    monkeypatch.setattr(api.state, "hardware", _KaydediciDonanim())
    _aktif_seans_kur(api, db, [6])
    core._handle_stm_line(_nack_satiri(bobin=6, duty=120.0), None)
    assert _estop_bekle()
    m = _duty_bildirimleri(bildirimler)
    assert m and all(p in m[0] for p in ("Bobin 6", "%120", "tek yönlü", "%100")), f"{bildirimler!r}"
    assert "Sürüş Kipi" not in m[0], f"tek-bacak tavanında kip önerisi anlamsız: {m[0]!r}"


# ── seanssız: reddedilen istek düşürülür → STOP'lar karta GEÇERLİ paketle gider (Ö.4-Y8) ──────────────────────────


def test_KRITIK_seanssiz_duty_reddi_STOP_paketlerini_BEKLETMEZ(ortam, monkeypatch):
    """Bobin 2 çalışırken bobin 1'e 80 (bipolar) → kart reddeder. Reddedilen istek HC'de kalırsa sonraki HER paket — bobin
    2'nin STOP'u dahil — reddedilir; STOP ancak firmware ölü-adamıyla (1,5 sn) uygulanır. Kapı: ilk NACK'ten SONRA kuyruğa
    giren paketler firmware aynasınca KABUL edilir ve bobin 2'nin STOP'u karta gider."""
    from servers import live_state as ls

    api, _db, core, bildirimler = ortam
    with api._session_lock:
        api._active_session.clear()
        api._active_session.update({"is_active": False})
    ls.stm_komut_kabulu_bildir()
    with gercek_hc() as hc:
        monkeypatch.setattr(api.state, "hardware", hc)
        assert hc.update_coil(2, 100.0, 30.0, 0.0, 5, start=True) is True
        assert hc.update_coil(1, 100.0, 80.0, 0.0, 5, start=True) is True
        paketler = hc.core._hw_send_queue.paketler
        _s, sebep = sim.decode_packet(paketler[-1])
        assert sebep and "kip=bipolar" in sebep, f"aparat: reddedilecek paket kurulamadı: {sebep!r}"
        ilk = len(paketler)
        core._handle_stm_line(f"-> STM_NACK: {sebep}", None)
        hc.update_coil(2, 0.0, 0.0, 0.0, 0, start=False)  # operatör bobin 2'yi durdurur
        sonra = paketler[ilk:]
        assert sonra, "NACK'ten sonra hiç paket yok"
        reddedilen = [s for _p, (r, s) in ((p, sim.decode_packet(p)) for p in sonra) if r is None]
        assert reddedilen == [], (
            f"NACK'ten sonraki {len(sonra)} paketin {len(reddedilen)}'i yine REDDEDİLİR ({reddedilen[0]!r}) — "
            "bobin 2'nin STOP'u karta uygulanmaz, firmware ölü-adamına (1,5 sn) kalır (Ö.4-Y8)"
        )
        son, _ = sim.decode_packet(sonra[-1])
        assert son[0][1] == 0.0, "bobin 2 STOP'u son pakette yok"
    m = _duty_bildirimleri(bildirimler)
    assert m and "durduruldu" in m[0] and not any(y in m[0] for y in _YANLIS_EYLEM), f"{bildirimler!r}"


def test_KARSIT_kenar_DISI_tekrar_NACK_ikinci_DURDURMA_ve_bildirim_URETMEZ(ortam, monkeypatch):
    """Kart aynı paketi yeniden deneme / keep-alive ile tekrar reddeder: taze kararda yeni kenar YOK (bildirim/E-stop seli)."""
    api, db, core, bildirimler = ortam
    hw = _KaydediciDonanim()
    monkeypatch.setattr(api.state, "hardware", hw)
    satir = _nack_satiri()
    with api._session_lock:
        api._active_session.clear()
        api._active_session.update({"is_active": False})
    core._handle_stm_line(satir, None)
    core._handle_stm_line(satir, None)
    core._handle_stm_line(satir, None)
    assert hw.stop_all == 1, f"tekrar NACK'ler sürüşü {hw.stop_all} kez durdurdu (1 bekleniyordu)"
    assert len(_duty_bildirimleri(bildirimler)) == 1, f"bildirim seli: {bildirimler!r}"


def test_KARSIT_duty_DISI_NACK_eski_yolda_kalir_ham_metin_ve_esik(ortam, monkeypatch):
    """Kapsam: yalnız duty TAVANI reddi yeni yoldan gider. Freq aralık NACK'i ilk NACK'te sürüşü DURDURMAZ, ham metin basılır."""
    api, _db, core, bildirimler = ortam
    hw = _KaydediciDonanim()
    monkeypatch.setattr(api.state, "hardware", hw)
    with api._session_lock:
        api._active_session.clear()
        api._active_session.update({"is_active": False})
    satir = "-> STM_NACK: RANGE coil=1 field=freq value_milli=0 min_milli=1000 max_milli=25000000"
    core._handle_stm_line(satir, None)
    assert hw.stop_all == 0, "duty DIŞI NACK ilk seferde sürüşü durdurdu"
    assert any("field=freq" in m for m, _t in bildirimler), f"ham NACK metni basılmadı: {bildirimler!r}"
