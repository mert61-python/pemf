"""Faz-1 (B-2.2 coil-run tracker ayrımı — refactor-ÖNCESİ DAVRANIŞ KİLİDİ).

`_begin_coil_run` / `_finish_coil_run` + `_active_coil_runs` / `_coil_run_stats` — seans sırasında
her bobinin treatment-DB'deki "coil run" yaşam-döngüsünü + dakika-ortalama akümülatörünü yönetir.
B-2.2'de `servers/coil_run_tracker.py`'ye taşınacak (treatment-DB'ye bağlı ama MQTT/hardware'e
geri-bağımlılığı YOK; db_session_id injection ile). Bu testler MEVCUT davranışı kilitler → taşıma
sonrası AYNI testler yeşil kalmalı. Testler `api_server` yüzeyinden gider (alias'lar korunur) →
extraction'dan önce ve sonra AYNI çalışır.

En kritik kilit: `_finish_coil_run`'ın per-metrik ortalaması — her metrik KENDİ dolu-örnek sayısına
bölünür (eksik sensör okuması ortalamayı aşağı çekmesin; klinik doğruluk düzeltmesi)."""
import os

os.environ.pop("PEMF_SIMULATE", None)
import pytest


class _FakeTreatmentDB:
    """Coil-run çağrılarını kaydeden sahte treatment DB (gerçek SQLite'a dokunmaz)."""

    def __init__(self):
        self.started = []    # (session_id, coil_id, kwargs)
        self.ended = []      # (run_id, epoch)
        self.summaries = []  # (run_id, kwargs)
        self._next_run_id = 100

    def start_coil_run(self, session_id, coil_id, **kw):
        rid = self._next_run_id
        self._next_run_id += 1
        self.started.append((session_id, coil_id, kw))
        return rid

    def end_coil_run(self, run_id, epoch):
        self.ended.append((run_id, epoch))

    def add_sensor_run_summary(self, run_id, **kw):
        self.summaries.append((run_id, kw))


@pytest.fixture()
def api(monkeypatch):
    """İzole api_server: sahte treatment DB + temiz coil-run/session state."""
    from servers import api_server

    fake = _FakeTreatmentDB()
    monkeypatch.setattr(api_server, "_get_treatment_db", lambda: fake)
    with api_server._active_coil_runs_lock:
        api_server._active_coil_runs.clear()
    with api_server._coil_run_stats_lock:
        api_server._coil_run_stats.clear()
    with api_server._session_lock:
        api_server._active_session.clear()
    return api_server, fake


# ── _begin_coil_run: yalnız aktif DB-seansı varken run açar ───────────────────
def test_begin_coil_run_noop_without_db_session(api):
    api_server, fake = api
    # db_session_id YOK → best-effort no-op (DB'ye yazma, run kaydetme)
    api_server._begin_coil_run(3, freq=50, duty=25, phase=0, intensity=2.0, hw_type="stm")
    assert fake.started == []
    assert 3 not in api_server._active_coil_runs


def test_begin_coil_run_starts_and_tracks_run(api):
    api_server, fake = api
    with api_server._session_lock:
        api_server._active_session["db_session_id"] = 7
    api_server._begin_coil_run(6, freq=40, duty=30, phase=0, intensity=1.5, hw_type="esp")
    # DB'de coil-run açıldı (doğru session_id + coil_id + parametreler)
    assert len(fake.started) == 1
    sid, coil_id, kw = fake.started[0]
    assert sid == 7 and coil_id == 6
    assert kw["frequency_hz"] == 40 and kw["duty_percent"] == 30 and kw["hw_type"] == "esp"
    # run-map + istatistik akümülatörü kuruldu
    assert api_server._active_coil_runs[6] == 100
    assert api_server._coil_run_stats[100]["n"] == 0


def test_begin_coil_run_closes_previous_open_run_for_same_coil(api):
    api_server, fake = api
    with api_server._session_lock:
        api_server._active_session["db_session_id"] = 7
    api_server._begin_coil_run(6, 40, 30, 0, 1.5, "esp")   # run 100 açılır
    api_server._begin_coil_run(6, 55, 20, 0, 2.0, "esp")   # aynı bobin → önce 100 kapanmalı
    # İlk run (100) end_coil_run ile kapatıldı; ikinci run (101) şimdi açık
    assert 100 in [r for r, _ in fake.ended], "aynı bobin yeniden açılınca eski run kapatılmadı (çift-açık)"
    assert api_server._active_coil_runs[6] == 101


# ── _finish_coil_run: run kapat + per-metrik ORTALAMA (her metrik kendi sayısına) ─
def test_finish_coil_run_writes_per_metric_averages(api):
    api_server, fake = api
    with api_server._session_lock:
        api_server._active_session["db_session_id"] = 7
    api_server._begin_coil_run(3, 50, 25, 0, 2.0, "stm")  # run 100
    run_id = api_server._active_coil_runs[3]
    # Akümülatörü elle doldur: her metriğin FARKLI dolu-örnek sayısı var (eksik okuma senaryosu)
    with api_server._coil_run_stats_lock:
        api_server._coil_run_stats[run_id].update({
            "n": 5,
            "t_sum": 100.0, "t_n": 4,   # sıcaklık 4 okumada → avg 25.0
            "i_sum": 20.0, "i_n": 5,    # akım 5 okumada → avg 4.0
            "b_sum": 10.0, "b_n": 2,    # alan 2 okumada → avg 5.0
            "t_min": 20.0, "t_max": 30.0,
        })

    api_server._finish_coil_run(3)

    # run kapatıldı + run-map'ten çıktı
    assert run_id in [r for r, _ in fake.ended]
    assert 3 not in api_server._active_coil_runs
    # KRİTİK: her metrik KENDİ dolu-sayısına bölünür (n=5'e DEĞİL)
    assert len(fake.summaries) == 1
    rid, kw = fake.summaries[0]
    assert rid == run_id
    assert kw["sample_count"] == 5
    assert kw["temp_avg"] == pytest.approx(25.0)      # 100/4, n=5 değil
    assert kw["current_avg"] == pytest.approx(4.0)    # 20/5
    assert kw["field_avg"] == pytest.approx(5.0)      # 10/2
    assert kw["temp_min"] == 20.0 and kw["temp_max"] == 30.0


def test_finish_coil_run_zero_fill_count_is_safe(api):
    """Bir metrik hiç okunmadıysa (fill count 0) → sıfıra-bölme YOK, avg 0.0 (eski davranış)."""
    api_server, fake = api
    with api_server._session_lock:
        api_server._active_session["db_session_id"] = 7
    api_server._begin_coil_run(4, 50, 25, 0, 2.0, "stm")
    run_id = api_server._active_coil_runs[4]
    with api_server._coil_run_stats_lock:
        api_server._coil_run_stats[run_id].update({
            "n": 3, "t_sum": 0.0, "t_n": 0,   # sıcaklık HİÇ okunmadı
            "i_sum": 9.0, "i_n": 3, "b_sum": 0.0, "b_n": 0,
        })
    api_server._finish_coil_run(4)
    rid, kw = fake.summaries[0]
    assert kw["temp_avg"] == 0.0     # 0-bölme değil
    assert kw["field_avg"] == 0.0
    assert kw["current_avg"] == pytest.approx(3.0)


def test_finish_coil_run_noop_when_no_open_run(api):
    api_server, fake = api
    # Açık run yokken finish → sessiz no-op (DB'ye dokunmaz)
    api_server._finish_coil_run(8)
    assert fake.ended == []
    assert fake.summaries == []
