# Author: mertaygn, cglrgrkn
"""D1.03 · S-1.4 — STM kopuşu → `_emergency_stop_async('stm_disconnected')` → EMERGENCY_STOPPED.

`api_server._handle_backend_event` STM kopunca (`hardware.stm.disconnected`) STM bobini kullanan
aktif seansı ACİL DURDURUR. Bu satır `pass` yapılınca mevcut süit YEŞİL kalıyordu (plan: 89 test,
kör kapı); regrese olursa kopuştan sonra seans 'active' sürer ve kayıt güvenlik olayını göstermez.

Kapı GERÇEK zinciri koşar: taze bir `EventBus` + gerçek `_register_event_bus_handlers` + gerçek
`publish("hardware.stm.disconnected")` → senkron abone `_handle_backend_event` → `estop-…` thread'i →
gerçek `_emergency_stop_all` → `_finalize_session_db`. Tedavi DB'si tmp; donanım kaydedici sahte.

⚠️ Ö.4-Y8: E-stop hiçbir koşula KAPILANMAZ. Bu kapı yalnız durdurmanın KAYBOLMASINI yakalar;
"şu durumda durdurma YAPILMASIN" türünden bir şey pinlemez (güvenli yöndeki genişletmeler yeşil kalır).
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
#: Bağımsız inceleme (r1): kapı yalnız `[1, 2]` ile kuruluyordu — kopuş koşulu eski 5-bobin
#: topolojisine (`range(1, 6)`) dönse de YEŞİL kalıyordu (B-10.42 sınıfı). Kümeler topolojiden türer.
SEANS_KUMELERI = {"ilk_iki_STM": _STM[:2], "son_STM": _STM[-1:], "son_iki_STM": _STM[-2:]}


class _KaydediciDonanim:
    def __init__(self):
        self.kopus = 0
        self.stop_all = 0

    def on_disconnect(self):
        self.kopus += 1
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
    # Taze olay yolu: önceki testlerin kaydı bu kapıyı ne besler ne bozar (subscribe çiftleri ayıklamaz).
    yeni_bus = eb.EventBus()
    monkeypatch.setattr(eb, "_event_bus_instance", yeni_bus)
    monkeypatch.setattr(api, "_event_bus_registered", False)
    with api._session_lock:
        eski_seans = dict(api._active_session)
    with ls._live_state_lock:
        eski_canli = copy.deepcopy(ls._live_state)
    try:
        yield api, db, hw, bildirimler
    finally:
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
                "session_id": "d103-stm-kopus",
                "coil_ids": list(coil_ids),
                "db_session_id": sid,
                "started_epoch": time.time() - 60,
                "start_mono": time.monotonic() - 60,
            }
        )
    return sid


def _estop_threadlerini_bekle(sure: float = 15.0) -> list[str]:
    bitis = time.monotonic() + sure
    gorulen: list[str] = []
    while time.monotonic() < bitis:
        canli = [t for t in threading.enumerate() if t.name.startswith("estop-stm_disconn")]
        gorulen.extend(t.name for t in canli if t.name not in gorulen)
        if not canli:
            return gorulen
        for t in canli:
            t.join(timeout=0.2)
    raise AssertionError(f"E-stop thread'i {sure} sn'de bitmedi: {gorulen}")


def _durum(db, sid):
    with db._get_connection() as conn:
        return conn.execute("SELECT session_status FROM treatment_sessions WHERE id=?", (sid,)).fetchone()[0]


@pytest.mark.parametrize("bobinler", list(SEANS_KUMELERI.values()), ids=list(SEANS_KUMELERI))
def test_KRITIK_STM_kopusu_aktif_STM_seansini_ACIL_DURDURUR_ve_KAYDA_yazar(ortam, bobinler):
    import event_bus as eb
    from database.treatment_history_db import SEANS_DURUMU_ACIL_DURDURMA

    api, db, hw, bildirimler = ortam
    api._register_event_bus_handlers()
    sid = _aktif_seans_kur(api, db, bobinler)
    assert _durum(db, sid) == "active"  # senaryo: kayıt gerçekten açık

    assert eb.publish("hardware.stm.disconnected", {"connected": False}) is True
    _estop_threadlerini_bekle()

    assert hw.kopus == 1, "STM kopuşunda HardwareController.on_disconnect çağrılmadı (re-fire koruması)"
    assert hw.stop_all >= 1, "kopuşta E-stop yolu donanıma STOP denemedi"
    with api._session_lock:
        assert api._active_session.get("is_active") is False, "STM koptu ama seans 'aktif' kaldı"
    assert _durum(db, sid) == SEANS_DURUMU_ACIL_DURDURMA, (
        f"STM kopuşuyla biten seans kayıtta {_durum(db, sid)!r} — güvenlik olayı tıbbi kayıtta görünmüyor"
    )
    with db._get_connection() as conn:
        olaylar = conn.execute(
            "SELECT event_type, severity, payload FROM session_events WHERE session_id=?", (sid,)
        ).fetchall()
    estop = [o for o in olaylar if o[0] == "emergency_stop"]
    assert estop and estop[0][1] == "critical" and "stm_disconnected" in (estop[0][2] or ""), (
        f"denetim izi: STM kopuşu sebepli kritik emergency_stop olayı yok: {olaylar!r}"
    )
    assert any("STM32 bağlantısı koptu" in m for m, _t in bildirimler), "operatöre kopuş bildirimi gitmedi"
