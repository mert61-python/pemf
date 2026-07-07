"""Canlı-durum (live-state) çekirdeği — B-2.2 shared-state modül ayrımı.

api_server.py'nin WS/MQTT/session yollarının paylaştığı TEK gerçeklik kaynağı. Bu state + fonksiyonlar
eskiden api_server.py içindeydi (2400+ satır tek dosya); buraya taşındı → api_server yalnız HTTP/WS
yönlendirmesine odaklanır, canlı-durum mantığı bağımsız olarak sahiplenilir + test edilir
(bkz. tests/test_live_state.py — refactor-ÖNCESİ davranış kilidi, sonrası AYNI yeşil).

DAVRANIŞ BİREBİR KORUNUR. api_server.py bu isimlere aynı-nesne alias'larıyla bağlanır (dict/list/lock
in-place mutasyon → çağrı yerleri değişmez). WS broadcast event-loop'a bağımlı: api_server lifespan
`set_event_loop()` çağırır; `_event_loop` None iken broadcast erken-return no-op (thread güvenli)."""
import json
import threading
from datetime import datetime

from fastapi import WebSocket

from utils.path_utils import get_app_version

_APP_VERSION = get_app_version()

# ── WebSocket istemci kaydı + gönderim serileştirme ────────────────────────────
_ws_clients: list[WebSocket] = []
_ws_lock = threading.Lock()
# asyncio.Lock (event-loop'ta lazy olusturulur) — TUM broadcast send-donguelerini serilestirir.
# Cok sayida thread (MQTT/STM/sim/AI/bildirim) bagimsiz _send_all() coroutine'i planliyor →
# ayni WebSocket'e es-zamanli send_text = Starlette "Concurrent call to send()" / bozuk framing.
_ws_send_lock = None
_event_loop = None  # api_server lifespan'de set_event_loop() ile atanir


def set_event_loop(loop) -> None:
    """api_server lifespan STARTUP'ta çağırır → thread'lerden gelen broadcast'ler bu loop'a planlanır."""
    global _event_loop
    _event_loop = loop


def _ws_send_lock_get():
    """Event-loop'ta çalışan coroutine'lerden çağrılır → asyncio.Lock lazy-init güvenli (tek-thread)."""
    global _ws_send_lock
    if _ws_send_lock is None:
        import asyncio as _a
        _ws_send_lock = _a.Lock()
    return _ws_send_lock


def _ws_broadcast_sync(message: dict) -> None:
    """Thread-safe senkron broadcast (MQTT callback'lerinden çağrılır)."""
    import asyncio
    if not _event_loop or not _ws_clients:
        return
    data = json.dumps(message, ensure_ascii=False)
    with _ws_lock:
        clients = list(_ws_clients)

    async def _send_all():
        dead = []
        async with _ws_send_lock_get():
            for ws in clients:
                try:
                    # P-2: per-send timeout — yavaş/yarı-açık istemci tüm broadcast'i (→ tüm filoyu)
                    # bloklamasın; 5sn'de yanıtlamayan istemci DÜŞÜRÜLÜR (except Exception TimeoutError'ı
                    # da yakalar → dead). Sağlıklı istemci ms'de gönderir → davranış aynı.
                    await asyncio.wait_for(ws.send_text(data), timeout=5.0)
                except Exception:
                    dead.append(ws)
        if dead:
            with _ws_lock:
                for d in dead:
                    try:
                        _ws_clients.remove(d)
                    except ValueError:
                        pass

    try:
        _event_loop.call_soon_threadsafe(lambda: asyncio.ensure_future(_send_all(), loop=_event_loop))
    except Exception:
        pass


# ── Canlı Durum (Live State) ───────────────────────────────────────
_live_state = {
    "gateway": "offline",
    "mqtt": "warning",
    "stm": "warning",
    "coils": {
        i: {
            "id": i + 1, "connected": False, "running": False,
            "frequencyHz": 0, "dutyCycle": 0, "magneticMt": 0.0,
            "objectTemp": 0.0, "ambientTemp": 0.0, "currentA": 0.0,
            "stm32Driven": i < 5,
        } for i in range(8)
    },
    "activeTreatment": {
        "mode": "Sistem Hazır", "frequencyHz": 0, "intensityMt": 0.0,
        "remainingMin": 0, "elapsedSec": 0, "durationSec": 0, "isActive": False,
    },
    "notifications": [],
    "system": {
        "softwareVersion": _APP_VERSION,
        "hardwareVersion": "HW-2026.1",
        "deviceId": "PEMF-001",
        "startTime": datetime.now().isoformat(),
        "totalSessions": 0,
    },
}
_live_state_lock = threading.Lock()
_notif_counter = 0
STM_COIL_IDS = set(range(1, 6))
ESP_COIL_IDS = set(range(6, 9))


def _sync_stm_coils_locked() -> list[dict]:
    """Keep coils 1-5 derived from the live STM connection state."""
    stm_online = _live_state["stm"] == "online"
    snapshots = []
    for idx in range(5):
        coil = _live_state["coils"][idx]
        coil["stm32Driven"] = True
        coil["connected"] = stm_online
        if not stm_online:
            coil["running"] = False
        snapshots.append(dict(coil))
    return snapshots


def _push_notification(message: str, level: str = "info") -> None:
    global _notif_counter
    _notif_counter += 1
    notif = {"id": _notif_counter, "message": message, "level": level,
             "timestamp": datetime.now().isoformat()}
    with _live_state_lock:
        _live_state["notifications"].insert(0, notif)
        if len(_live_state["notifications"]) > 50:
            _live_state["notifications"].pop()
    _ws_broadcast_sync({"type": "notification", "data": notif})


def _build_ws_snapshot() -> dict:
    """Anlık durum özeti (WebSocket'e ilk bağlanıldığında gönderilir)."""
    with _live_state_lock:
        _sync_stm_coils_locked()
        coils_list = [dict(_live_state["coils"][i]) for i in range(8)]
        return {
            "gateway": _live_state["gateway"],
            "mqtt": _live_state["mqtt"],
            "stm": _live_state["stm"],
            "activeTreatment": _live_state["activeTreatment"],
            "coils": coils_list,
            "notifications": _live_state["notifications"][:10],
            "system": _live_state["system"],
        }


def update_live_stm_status(connected: bool) -> None:
    """STM32 bağlantı durumunu günceller."""
    with _live_state_lock:
        _live_state["stm"] = "online" if connected else "warning"
        stm_state = _live_state["stm"]
        coil_snapshots = _sync_stm_coils_locked()
    _ws_broadcast_sync({"type": "stm_status", "data": {"stm": stm_state, "connected": connected}})
    for coil in coil_snapshots:
        _ws_broadcast_sync({"type": "stm_coil_update", "coilId": coil["id"], "data": coil})


def update_live_coil_from_stm(coil_id: int, duty: float, freq: float,
                               phase: float, duration_min: int, running: bool) -> None:
    """STM32 USB verisiyle bobin durumunu günceller."""
    coil_index = coil_id - 1
    if not (0 <= coil_index < 8):
        return
    with _live_state_lock:
        _live_state["stm"] = "online"
        coil = _live_state["coils"][coil_index]
        coil.update({"connected": True, "running": running, "frequencyHz": int(freq),
                     "dutyCycle": float(duty), "phase": float(phase),
                     "durationMin": int(duration_min), "stm32Driven": True})
        snapshot = dict(coil)
    _ws_broadcast_sync({"type": "stm_status", "data": {"stm": "online", "connected": True}})
    _ws_broadcast_sync({"type": "stm_coil_update", "coilId": coil_id, "data": snapshot})


def update_live_session_state(is_active: bool, mode: str = "Sistem Hazır", freq: float = 0,
                              intensity: float = 0, remaining_min: int = 0,
                              elapsed_sec: int = 0, duration_sec: int = 0) -> None:
    """React/WebSocket tarafındaki aktif tedavi özetini günceller."""
    with _live_state_lock:
        _live_state["activeTreatment"].update({
            "isActive": bool(is_active),
            "mode": mode,
            "frequencyHz": freq,
            "intensityMt": intensity,
            "remainingMin": remaining_min,
            "elapsedSec": elapsed_sec,
            "durationSec": duration_sec,
        })
        snapshot = dict(_live_state["activeTreatment"])
    _ws_broadcast_sync({"type": "session_update", "data": snapshot})
