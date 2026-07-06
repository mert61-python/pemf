"""Session state — B-2.2 shared-state modül ayrımı (son kademe).

Aktif tedavi seansının in-memory TEK gerçeklik kaynağı (`_active_session` + `_session_lock`). Eskiden
api_server.py'deydi ve `start_session`/`start_ai_session` dict'i **REBIND** ediyordu → önce in-place
mutasyona (`.clear()+.update()`) normalize edildi (kimlik sabit), sonra buraya taşındı. api_server
aynı-nesne alias'larıyla bağlanır (dict/lock in-place → endpoint/watchdog/emergency gövdesi DEĞİŞMEDİ);
davranış birebir (bkz. tests/test_session_lifecycle.py refactor-öncesi kilit).

Session LOGIC (start/stop/emergency endpoint'leri + süre-watchdog) BİLİNÇLİ olarak api_server'da kalır
(web/orkestrasyon katmanı; donanım/MQTT/live-state'e örülü). Burada yalnız STATE + saf erişim."""
import threading

_session_lock = threading.Lock()
_active_session: dict = {}  # boş = aktif seans yok


def snapshot() -> dict:
    """Aktif seansın kilit-altında sığ kopyası (okuyucular global dict'i mutate etmesin)."""
    with _session_lock:
        return dict(_active_session)


def is_active() -> bool:
    """Şu an aktif bir seans var mı (kilitli okuma)."""
    with _session_lock:
        return bool(_active_session.get("is_active"))


def current_db_session_id():
    """Aktif seansın gerçek DB satır-id'si (`db_session_id`) veya None — kilitli okuma.
    coil_run_tracker'a enjekte edilir; in-place normalizasyon sayesinde çağrı-anında günceldir."""
    with _session_lock:
        return _active_session.get("db_session_id")
