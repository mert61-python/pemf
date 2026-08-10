# Author: mertaygn, cglrgrkn
"""Coil-run tracker — B-2.2 shared-state modül ayrımı.

Seans sırasında her bobinin treatment-DB'deki "coil run" yaşam-döngüsünü + per-run sensör istatistik
akümülatörünü yönetir (dakika-ortalama → run özeti). Eskiden api_server.py içindeydi.

Treatment-DB'ye bağlı ama **MQTT/hardware'e GERİ-BAĞIMLI DEĞİL**: aktif seansın DB satır-id'si +
treatment-DB erişimi api_server'dan INJECTION ile gelir (`set_db_session_id_getter` /
`set_treatment_db_getter`) → döngüsel import yok, `_active_session`'ın rebind'i doğal olarak
karşılanır (getter çağrı-anında okur). Davranış BİREBİR (bkz. tests/test_coil_run_tracker.py —
refactor-öncesi kilit). api_server state'e aynı-nesne alias'larıyla bağlanır (`_active_coil_runs` /
`_coil_run_stats` yalnız in-place mutasyon: start_session `.clear()`, sensör-loop akümülasyonu)."""

import logging
import threading
import time

# ── Coil-run state (yalnız in-place mutasyon → api_server alias'ları aynı nesneye işaret eder) ──
_active_coil_runs = {}  # coil_id(int) -> run_id(int)
_active_coil_runs_lock = threading.Lock()
_coil_run_stats = {}  # run_id -> {n,t_min,t_max,t_sum,i_sum,b_sum,t_n,i_n,b_n}
_coil_run_stats_lock = threading.Lock()
# Audit P3: tüm _begin_coil_run dizisini (kontrol→kapat→aç→kaydet) serileştir → eş-zamanlı iki begin
# çift DB-satırı + orphan üretmesin. _active_coil_runs_lock'tan AYRI → _finish_coil_run ile deadlock yok.
_begin_coil_run_lock = threading.Lock()


# ── Injection: api_server bağlar (döngüsel import yok). Varsayılanlar güvenli no-op. ──
def _default_session_id():
    return None


def _default_treatment_db():
    return None


_db_session_id_getter = _default_session_id
_treatment_db_getter = _default_treatment_db


def set_db_session_id_getter(fn) -> None:
    """api_server enjekte eder: aktif seansın gerçek DB satır-id'si (`db_session_id`) veya None."""
    global _db_session_id_getter
    _db_session_id_getter = fn


def set_treatment_db_getter(fn) -> None:
    """api_server enjekte eder: TreatmentHistoryDB singleton'ı veya None (best-effort)."""
    global _treatment_db_getter
    _treatment_db_getter = fn


def _begin_coil_run(coil_id, freq, duty, phase, intensity, hw_type):
    """Aktif seans (db_session_id) varsa bir bobin calismasini DB'de baslat ve run-map'e koy.
    Ayni coil zaten acik run'daysa once eskisini _finish_coil_run ile kapatir. Hepsi best-effort."""
    try:
        coil_id = int(coil_id)
    except Exception:
        return
    try:
        sid = _db_session_id_getter()
        if not sid:
            return
        # Audit P3 (TOCTOU): kontrol→kapat→aç→kaydet dizisini begin-kilidiyle SERİLEŞTİR (eş-zamanlı iki
        # _begin_coil_run çift DB-satırı + orphan üretmesin). _active_coil_runs_lock'tan AYRI kilit →
        # içerideki _finish_coil_run/store'un kısa acquisition'ları deadlock yapmaz.
        with _begin_coil_run_lock:
            with _active_coil_runs_lock:
                already_open = coil_id in _active_coil_runs
            if already_open:
                _finish_coil_run(coil_id)
            db = _treatment_db_getter()
            if db is None:
                return
            run_id = db.start_coil_run(
                sid,
                coil_id,
                frequency_hz=freq,
                duty_percent=duty,
                phase=phase,
                intensity_mt=intensity,
                hw_type=hw_type,
                started_epoch=time.time(),
            )
            if run_id is not None:
                with _active_coil_runs_lock:
                    _active_coil_runs[coil_id] = run_id
                with _coil_run_stats_lock:
                    _coil_run_stats[run_id] = {
                        "n": 0,
                        "t_min": None,
                        "t_max": None,
                        "t_sum": 0.0,
                        "i_sum": 0.0,
                        "b_sum": 0.0,
                        "t_n": 0,
                        "i_n": 0,
                        "b_n": 0,
                    }
    except Exception:
        logging.getLogger(__name__).debug("_begin_coil_run hatasi (coil=%s)", coil_id, exc_info=True)


def _finish_coil_run(coil_id):
    """Acik bobin calismasini kapat: end_coil_run + run-ozetini (add_sensor_run_summary) yaz.
    Run-map ve istatistik akumulatorundan siler. Best-effort (hata seansi durdurmaz)."""
    try:
        coil_id = int(coil_id)
    except Exception:
        return
    try:
        with _active_coil_runs_lock:
            run_id = _active_coil_runs.pop(coil_id, None)
        if run_id is None:
            return
        db = _treatment_db_getter()
        if db is not None:
            try:
                db.end_coil_run(run_id, time.time())
            except Exception:
                logging.getLogger(__name__).debug("end_coil_run hatasi", exc_info=True)
        with _coil_run_stats_lock:
            st = _coil_run_stats.pop(run_id, None)
        if db is not None and st and st.get("n", 0) > 0:
            n = st["n"]
            # Her metrik KENDI dolu-ornek sayisina bolunur (eksik sensor okumalari
            # ortalamayi asagi cekmesin); metrik hic okunmadiysa None.
            _tn = st.get("t_n", 0)
            _in = st.get("i_n", 0)
            _bn = st.get("b_n", 0)
            try:
                db.add_sensor_run_summary(
                    run_id,
                    sample_count=n,
                    temp_min=st.get("t_min"),
                    temp_max=st.get("t_max"),
                    temp_avg=(st["t_sum"] / _tn) if _tn else 0.0,
                    current_avg=(st["i_sum"] / _in) if _in else 0.0,
                    field_avg=(st["b_sum"] / _bn) if _bn else 0.0,
                )
            except Exception:
                logging.getLogger(__name__).debug("add_sensor_run_summary hatasi", exc_info=True)
    except Exception:
        logging.getLogger(__name__).debug("_finish_coil_run hatasi (coil=%s)", coil_id, exc_info=True)
