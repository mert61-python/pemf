# Author: mertaygn, cglrgrkn
"""D1.31 · B-10.56 (+ 1-A açık madde 7) — STM sistematik NACK ve STM watchdog → aktif STM seansı DURUR.

ÖLÇÜLEN KÖRLÜK: `test_sahte_basarili_seans::test_KRITIK_NACK_dali_aktif_seansi_DURDURUR` NACK dalının
2000 karakterlik METİN diliminde yalnız çağrı ADLARINI arıyordu — çağrı `if False:` altına alınsa da,
`stm_komut_reddi_bildir` dönüş anlamı bozulup durdurma hiç tetiklenmese de YEŞİL (plan C1b-63: B-1.1
"sistematik red" kararını değiştirecek; bu kapı o zincirin önüne gelir). Sonuç kategori 2: bobin
çalışmadan seans "Tamamlandı" yazılır (sahte-başarılı seans).

1-A açık madde 7 (D1.03 kapı ailesi): `hardware.stm.watchdog_timeout` dalı da aynı topoloji koşuluyla
(`any(c in STM_COIL_IDS …)`) seansı durduruyor ve kapısızdı; koşul eski 5-bobin kümesine dönse bobin 6-7
seansı firmware watchdog'undan sonra "aktif" sürerdi.

Kapı GERÇEK zinciri koşar (D1.03 düzeni): taze `EventBus` + gerçek `_register_event_bus_handlers` +
gerçek `publish(...)` → `_handle_backend_event` → `estop-…` iş parçacığı → gerçek `_emergency_stop_all`
→ `_finalize_session_db`. Tedavi DB'si tmp; donanım kaydedici sahte. Bobin kümeleri TOPOLOJİDEN türer.

⚠️ Ö.4-Y8: kapı yalnız durdurmanın KAYBOLMASINI yakalar; "şu durumda durdurma" yasağı pinlenmez.
"""

from __future__ import annotations

import copy
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from topoloji import TUM_STM  # noqa: E402  (literal bobin numarası YAZILMAZ)

_STM = sorted(TUM_STM)
SEANS_KUMELERI = {"ilk_STM": _STM[:1], "son_STM": _STM[-1:], "tum_STM": _STM}


class _KaydediciDonanim:
    def __init__(self):
        self.stop_all = 0

    def on_disconnect(self):
        return True

    def stop_all_coils(self):
        self.stop_all += 1
        return True


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    import event_bus as eb
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import live_state as ls

    db = TreatmentHistoryDB(tmp_path)
    hw = _KaydediciDonanim()
    bildirimler: list = []
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(api.state, "hardware", hw)
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(api, "_push_notification", lambda m, t="info": bildirimler.append((m, t)))
    yeni_bus = eb.EventBus()
    monkeypatch.setattr(eb, "_event_bus_instance", yeni_bus)
    monkeypatch.setattr(api, "_event_bus_registered", False)
    ls.stm_komut_kabulu_bildir()  # süreç-geneli red sayacı önceki testten sızmasın
    with api._session_lock:
        eski_seans = dict(api._active_session)
    with ls._live_state_lock:
        eski_canli = copy.deepcopy(ls._live_state)
    try:
        api._register_event_bus_handlers()
        yield api, db, hw, bildirimler
    finally:
        ls.stm_komut_kabulu_bildir()
        with api._session_lock:
            api._active_session.clear()
            api._active_session.update(eski_seans)
        with ls._live_state_lock:
            ls._live_state.clear()
            ls._live_state.update(eski_canli)
        yeni_bus.shutdown()


def _aktif_seans_kur(api, db, coil_ids):
    sid = db.start_session(treatment_mode="Manuel", target_condition="test", patient_name="Pamuk")
    with api._session_lock:
        api._active_session.clear()
        api._active_session.update(
            {
                "is_active": True,
                "session_id": "d131-stm-red",
                "coil_ids": list(coil_ids),
                "db_session_id": sid,
                "started_epoch": time.time() - 60,
                "start_mono": time.monotonic() - 60,
            }
        )
    return sid


def _estop_bekle(sure: float = 15.0) -> list[str]:
    """`estop-…` iş parçacıkları bitene kadar bekle; görülen adları döndür."""
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


def _durum(db, sid):
    with db._get_connection() as conn:
        return conn.execute("SELECT session_status FROM treatment_sessions WHERE id=?", (sid,)).fetchone()[0]


def _estop_olayi(db, sid, sebep):
    with db._get_connection() as conn:
        olaylar = conn.execute(
            "SELECT event_type, severity, payload FROM session_events WHERE session_id=?", (sid,)
        ).fetchall()
    return [o for o in olaylar if o[0] == "emergency_stop" and sebep in (o[2] or "")], olaylar


@pytest.mark.parametrize("bobinler", list(SEANS_KUMELERI.values()), ids=list(SEANS_KUMELERI))
def test_KRITIK_sistematik_NACK_aktif_STM_seansini_DURDURUR_kayit_tamamlandi_DEGIL(ortam, bobinler):
    import event_bus as eb
    from database.treatment_history_db import SEANS_DURUMU_ACIL_DURDURMA
    from servers import live_state as ls

    api, db, hw, bildirimler = ortam
    sid = _aktif_seans_kur(api, db, bobinler)
    assert _durum(db, sid) == "active"  # senaryo: kayıt gerçekten açık

    # Eşiğin BİR altı: tek tük gürültü NACK'i seansı DURDURMAZ (her şeyi durduran mutanta karşı).
    for _ in range(ls.STM_RED_ESIGI - 1):
        assert eb.publish("hardware.stm.nack", {"message": "STM_NACK: CRC"}) is True
    assert _estop_bekle() == [], "eşiğin altındaki NACK seansı durdurdu (gürültüde klinik durur)"
    with api._session_lock:
        assert api._active_session.get("is_active") is True

    assert eb.publish("hardware.stm.nack", {"message": "STM_NACK: CRC"}) is True  # eşik
    gorulen = _estop_bekle()
    assert gorulen, "sistematik NACK'te E-stop yolu HİÇ başlatılmadı"
    with api._session_lock:
        assert api._active_session.get("is_active") is False, "kart sistematik reddediyor ama seans 'aktif' kaldı"
    durum = _durum(db, sid)
    assert durum not in ("active", "completed"), f"sahte-başarılı seans: kayıt {durum!r}"
    assert durum == SEANS_DURUMU_ACIL_DURDURMA, f"kayıt {durum!r} (beklenen {SEANS_DURUMU_ACIL_DURDURMA})"
    estop, olaylar = _estop_olayi(db, sid, "stm_komut_reddi")
    assert estop, f"denetim izinde stm_komut_reddi sebepli emergency_stop yok: {olaylar!r}"
    assert hw.stop_all >= 1, "donanıma STOP denenmedi"
    assert any("Seans DURDURULDU" in m for m, _t in bildirimler), "operatöre durdurma bildirimi gitmedi"


@pytest.mark.parametrize("bobinler", list(SEANS_KUMELERI.values()), ids=list(SEANS_KUMELERI))
def test_KRITIK_STM_watchdog_aktif_STM_seansini_DURDURUR(ortam, bobinler):
    """1-A açık madde 7: watchdog dalının topoloji koşulu — bobin 6-7 seansı da durmalı."""
    import event_bus as eb
    from database.treatment_history_db import SEANS_DURUMU_ACIL_DURDURMA

    api, db, hw, _b = ortam
    sid = _aktif_seans_kur(api, db, bobinler)
    assert eb.publish("hardware.stm.watchdog_timeout", {"message": "Watchdog Timeout"}) is True
    assert _estop_bekle(), "STM watchdog'unda E-stop yolu HİÇ başlatılmadı"
    with api._session_lock:
        assert api._active_session.get("is_active") is False, f"STM watchdog sonrası {bobinler} seansı 'aktif' kaldı"
    assert _durum(db, sid) == SEANS_DURUMU_ACIL_DURDURMA, f"kayıt {_durum(db, sid)!r}"
    estop, olaylar = _estop_olayi(db, sid, "stm_watchdog_timeout")
    assert estop, f"denetim izinde stm_watchdog_timeout sebepli emergency_stop yok: {olaylar!r}"
    assert hw.stop_all >= 1, "donanıma STOP denenmedi"
