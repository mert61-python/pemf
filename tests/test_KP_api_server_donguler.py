# Author: mertaygn, cglrgrkn
"""KP-1 · apps/backend/servers/api_server.py · sözleşmeler: arka plan döngüleri ve yaşam döngüsü — süre bekçisi (süre dolunca
STOP + seans pasif; canlı durum hatası yutulur; bozuk seans verisi döngüyü öldürmez), sensör kalıcılık döngüsü (kimliği bozuk /
telemetrisiz bobin atlanır, ortam sıcaklığı ortalamaya girer, dakika sınırında satır üretilir; tazelik ve ölçüm hataları
döngüyü öldürmez), ESP telemetri bekçisi (bayat bobin bağlantısız + STOP; yayın hatası döngüyü öldürmez), dakika
ortalaması (boş akümülatör atlanır, koşu min/maks güncellenir, tampon 20 000 tavanı), periyodik tampon yazımı, günlük bakım
(KVKK / retention / VACUUM / checkpoint hataları; seans durumu okunamazsa VACUUM YOK), arka plan başlatıcı (tek sefer; canlı E
döngüsü başlatılamazsa uyarı), broker kimlik sondası (durdurulunca sessiz), MQTT dinleyici başlatma hatası, lifespan
kapanışı (MQTT / mDNS kapatma hataları yutulur), olay veriyolu kaydı hatası, Y53 tek bobin STOP hatası, seans kapanış
sarmalayıcısı (alan kaydı / canlı E bağlamı hataları yutulur).

Döngüler TEK TUR koşar: `time.sleep` yalnız döngü iş parçacığında BaseException ile keser (`dongu_tek_tur` deseni; bakım
döngüsü için ilk N uyku geçirilir). Sahte EN ALT katta: tedavi / hasta DB'si (`sqlite3.OperationalError`), MQTT yayını, WS
yayını, kasa / broker sondası (`utils.mqtt_kimlik`), paho istemcisi, olay veriyolu `subscribe`, iş parçacığı sınıfı.
"""

from __future__ import annotations

import copy
import logging
import sqlite3
import sys
import threading
import time as _time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from topoloji import ESP_BOBIN, STM_BOBIN, esp_yolu_gerekir


class _TurBitti(BaseException):
    pass


def _tur(fonk, atla: int = 0, dakika_atla: bool = False, sure: float = 20.0):
    """`fonk`u ayrı iş parçacığında koştur: o iş parçacığındaki ilk `atla` uyku hemen döner, sonraki uyku turu bitirir.
    `dakika_atla`: o iş parçacığında her `time.time()` 61 sn ileri gider. → (uyku sayısı, hatalar)."""
    orj_sleep, orj_time = _time.sleep, _time.time
    d = {"id": None, "uyku": 0, "zaman": 0}

    def _sleep(s):
        if threading.get_ident() == d["id"]:
            d["uyku"] += 1
            if d["uyku"] > atla:
                raise _TurBitti()
            return None
        return orj_sleep(s)

    def _zaman():
        if threading.get_ident() == d["id"] and dakika_atla:
            d["zaman"] += 1
            return orj_time() + 61.0 * (d["zaman"] - 1)
        return orj_time()

    hatalar: list = []

    def _kos():
        d["id"] = threading.get_ident()
        try:
            fonk()
        except _TurBitti:
            pass
        except BaseException as e:  # noqa: BLE001
            hatalar.append(e)

    _time.sleep, _time.time = _sleep, _zaman
    try:
        th = threading.Thread(target=_kos, daemon=True, name="kp-tek-tur")
        th.start()
        th.join(sure)
    finally:
        _time.sleep, _time.time = orj_sleep, orj_time
    assert not th.is_alive(), "döngü bir turda uykuya varmadı"
    return d["uyku"], hatalar


@pytest.fixture
def ortam(monkeypatch):
    from servers import api_server as a
    from servers import live_state as ls

    yayin: list = []
    bildirim: list = []
    mqtt: list = []
    monkeypatch.setattr(a, "_ws_broadcast_sync", lambda m: yayin.append(m))
    monkeypatch.setattr(ls, "_ws_broadcast_sync", lambda m: yayin.append(m))
    monkeypatch.setattr(a, "_push_notification", lambda m, s="info", mesajlar=None: bildirim.append((m, s)))
    monkeypatch.setattr(a, "_mqtt_publish", lambda t, p: mqtt.append((t, p.get("command"), p.get("reason"))) or False)
    monkeypatch.setattr(a.state, "hardware", None)
    with a._live_state_lock:
        canli_once = {k: copy.deepcopy(v) for k, v in a._live_state.items()}
    with a._session_lock:
        seans_once = dict(a._active_session)
    with a._sensor_sample_buffer_lock:
        tampon_once = list(a._sensor_sample_buffer)
    with a._minute_acc_lock:
        dakika_once = copy.deepcopy(a._minute_acc)
    tel_once = dict(a._coil_last_telemetry)
    olculen_once = copy.deepcopy(a._coil_olculen_alanlar)
    seans_kilidi = a._session_lock  # bir test kilidi bozuk nesneyle değiştirir; geri alma gerçek kilitle
    try:
        yield SimpleNamespace(a=a, ls=ls, yayin=yayin, bildirim=bildirim, mqtt=mqtt)
    finally:
        for t in [t for t in threading.enumerate() if t.name in ("kvkk-vacuum", "BrokerKimlikSondasi")]:
            t.join(5)
        with seans_kilidi:
            a._active_session.clear()
            a._active_session.update(seans_once)
        with a._live_state_lock:
            for k, v in canli_once.items():
                a._live_state[k] = v
        with a._sensor_sample_buffer_lock:
            a._sensor_sample_buffer[:] = tampon_once
        with a._minute_acc_lock:
            a._minute_acc.clear()
            a._minute_acc.update(dakika_once)
        a._coil_last_telemetry.clear()
        a._coil_last_telemetry.update(tel_once)
        a._coil_olculen_alanlar.clear()
        a._coil_olculen_alanlar.update(olculen_once)


def _patlayan(hata):
    def _f(*_a, **_k):
        raise hata

    return _f


def _log(caplog):
    return [r.getMessage() for r in caplog.records]


class _Db:
    def __init__(self, *bozuk, baglanti=None):
        self.bozuk = set(bozuk)
        self.cagri: list = []
        if baglanti is not None:
            self._get_connection = baglanti

    def _k(self, ad, *a):
        self.cagri.append((ad, *a))
        if ad in self.bozuk:
            raise sqlite3.OperationalError("disk I/O error")

    def add_sensor_samples_batch(self, sid, rows):
        self._k("add_sensor_samples_batch", sid, len(rows))
        return len(rows)

    def end_session(self, sid, duration_minutes=0, session_status="completed"):
        self._k("end_session", sid, session_status)

    def set_session_meta(self, sid, **k):
        self._k("set_session_meta", sid)

    def purge_old_session_events(self, gun):
        self._k("purge_old_session_events", gun)
        return 0

    def bekleyen_vacuum_calistir(self):
        self._k("bekleyen_vacuum_calistir")

    def run_maintenance(self):
        self._k("run_maintenance")


# ── süre bekçisi ─────────────────────────────────────────────────────────────────────────────


def test_SURE_BEKCISI_doldu_STOP_ve_pasif_canli_durum_hatasi_yutulur(ortam, monkeypatch, caplog):
    """Aktif seansın bitiş işareti geçmişte + canlı durum güncellemesi istisna → STM bobinine STOP (`update_coil(..., start=False)`),
    seans pasif; `session_completed` yayını atlanır, döngü bir turda uykuya varır (hata yok). İstisna İÇ kolda yutulur: INFO
    "Süre doldu → seans otomatik durduruldu (watchdog): kp-sb" YAZILIR, genel döngü hatası "session_duration_watchdog hata"
    YAZILMAZ (TUR 2 · KP1-IA.5: iç `except` daraltılınca istisna genel yakalayıcıya düşüp tamamlanma günlüğünü atlıyordu)."""
    a = ortam.a
    stop: list = []
    monkeypatch.setattr(
        a.state,
        "hardware",
        SimpleNamespace(
            core=None, coils_state={}, update_coil=lambda *x, **k: stop.append((x[0], k.get("start"))) or True
        ),
    )
    monkeypatch.setattr(ortam.ls, "update_live_session_state", _patlayan(RuntimeError("canlı durum kilitli")))
    with a._session_lock:
        a._active_session.update(
            is_active=True,
            session_id="kp-sb",
            coil_ids=[STM_BOBIN],
            bitis_mono=_time.monotonic() - 1,
            start_mono=_time.monotonic() - 100,
            db_session_id=None,
        )
    caplog.set_level(logging.INFO)
    uyku, hatalar = _tur(a._session_duration_watchdog)
    assert (uyku, hatalar) == (1, [])
    assert stop == [(STM_BOBIN, False)]
    assert a._active_session["is_active"] is False
    assert not [m for m in ortam.yayin if m.get("type") == "session_completed"]
    log = _log(caplog)
    assert "Süre doldu → seans otomatik durduruldu (watchdog): kp-sb" in log
    assert "session_duration_watchdog hata" not in log


def test_SURE_BEKCISI_bozuk_seans_verisi_dongu_SURER(ortam, caplog):
    """Aktif seansın süresi sayı değil → istisna döngüde yakalanır ("session_duration_watchdog hata"), tur uykuya varır."""
    a = ortam.a
    with a._session_lock:
        a._active_session.update(is_active=True, session_id="kp-sb2", duration_minutes="abc")
    caplog.set_level(logging.ERROR)
    uyku, hatalar = _tur(a._session_duration_watchdog)
    assert (uyku, hatalar) == (1, [])
    assert "session_duration_watchdog hata" in _log(caplog)


# ── sensör kalıcılık döngüsü ─────────────────────────────────────────────────────────────────


def _bobin(a, idx, **alan):
    with a._live_state_lock:
        a._live_state["coils"][idx].update(**alan)


def test_KALICILIK_bozuk_kimlik_ve_telemetrisiz_atlanir_ORTAM_sicakligi_dakika_satirinda(ortam):
    """Aktif seans + bobin(0) kimliği sayı değil + bobin(1) telemetrisiz + bobin(2) taze objectTemp/ambientTemp → dakika
    sınırında TAMPONA tek satır: coil_id "3", temperature_c 30.0, ambient_temp_c 22.5, sample_count 1; diğerleri atlanır."""
    a = ortam.a
    with a._session_lock:
        a._active_session.update(is_active=True, db_session_id=None)
    simdi = _time.monotonic()
    _bobin(a, 0, id="x", running=True)
    _bobin(a, 1, running=True)
    _bobin(a, 2, running=True, objectTemp=30.0, ambientTemp=22.5, frequencyHz=10, dutyCycle=20)
    a._coil_last_telemetry.pop(1, None)
    a._coil_last_telemetry[2] = simdi
    a._coil_olculen_alanlar[2] = {"objectTemp": simdi + 3600, "ambientTemp": simdi + 3600}
    for i in range(3, 8):
        _bobin(a, i, running=False)
    with a._minute_acc_lock:
        a._minute_acc.clear()
    with a._sensor_sample_buffer_lock:
        a._sensor_sample_buffer.clear()
    uyku, hatalar = _tur(a._sensor_persistence_loop, dakika_atla=True)
    assert (uyku, hatalar) == (1, [])
    satirlar = list(a._sensor_sample_buffer)
    assert [(s["coil_id"], s["temperature_c"], s["ambient_temp_c"], s["sample_count"]) for s in satirlar] == [
        ("3", 30.0, 22.5, 1)
    ]


def test_KALICILIK_tazelik_ve_olcum_hatasi_donguyu_OLDURMEZ(ortam, monkeypatch, caplog):
    """Tazelik yayını istisna + aktif seansta ölçülen sıcaklık sayı değil → iki hata da döngüde yakalanır ("olculen alan tazelik
    denetimi hatasi", "sensor persistence loop error"), tur uykuya varır."""
    a = ortam.a

    def _yayin(m):
        if m.get("type") == "coil_status":
            raise ConnectionResetError("WS kapandı")

    monkeypatch.setattr(a, "_ws_broadcast_sync", _yayin)
    simdi = _time.monotonic()
    a._coil_olculen_alanlar[2] = {"objectTemp": simdi + 3600}
    _bobin(a, 2, running=True, objectTemp="abc", measuredFields=[])
    a._coil_last_telemetry[2] = simdi
    with a._session_lock:
        a._active_session.update(is_active=True, db_session_id=None)
    caplog.set_level(logging.ERROR)
    uyku, hatalar = _tur(a._sensor_persistence_loop)
    assert (uyku, hatalar) == (1, [])
    log = _log(caplog)
    assert "olculen alan tazelik denetimi hatasi" in log and "sensor persistence loop error" in log


# ── ESP telemetri bekçisi ────────────────────────────────────────────────────────────────────


def test_ESP_BEKCISI_bayat_bobin_STOP_yayin_hatasi_donguyu_OLDURMEZ(ortam, monkeypatch, caplog):
    """ESP bobini bağlı ama telemetrisi 100 sn bayat + WS yayını istisna → bobin bağlantısız/çalışmıyor, "telemetry_stale"
    STOP'u yayınlanır, hata "esp telemetry watchdog error" ile yakalanır, tur uykuya varır."""
    esp_yolu_gerekir()
    a = ortam.a
    monkeypatch.setattr(a, "_ws_broadcast_sync", _patlayan(ConnectionResetError("WS kapandı")))
    _bobin(a, ESP_BOBIN - 1, connected=True, running=True)
    a._coil_last_telemetry[ESP_BOBIN - 1] = _time.monotonic() - 100
    caplog.set_level(logging.ERROR)
    uyku, hatalar = _tur(a._esp_telemetry_watchdog)
    assert (uyku, hatalar) == (1, [])
    assert ortam.mqtt == [(f"pemf/coil/{ESP_BOBIN}/control", "stop", "telemetry_stale")]
    c = a._live_state["coils"][ESP_BOBIN - 1]
    assert (c["connected"], c["running"]) == (False, False)
    assert "esp telemetry watchdog error" in _log(caplog)


def test_ESP_BEKCISI_aralik_disi_bobin_kimligi_atlanir(ortam, monkeypatch, caplog):
    """ESP bobin listesinde ÖNCE aralık dışı kimlik (9), SONRA sınırdaki geçerli kimlik (8, indeks 7) bağlı ve telemetrisi 100 sn
    bayat → 9 ATLANIR ve 8'in denetimini engellemez: yalnız 8'e "telemetry_stale" STOP'u yayınlanır, 8 bağlantısız/çalışmıyor,
    genel döngü hatası "esp telemetry watchdog error" YAZILMAZ, tur uykuya varır (TUR 2 · KP1-IA.1: aralık koruması silinince
    9'un IndexError'ı genel yakalayıcıda yutulup eski iddiayı (yalnız "yayın yok") aynen sağlıyordu)."""
    a = ortam.a
    monkeypatch.setattr(a, "ESP_COIL_IDS", [9, 8])
    _bobin(a, 7, connected=True, running=True)
    a._coil_last_telemetry[7] = _time.monotonic() - 100
    caplog.set_level(logging.ERROR)
    uyku, hatalar = _tur(a._esp_telemetry_watchdog)
    assert (uyku, hatalar) == (1, [])
    assert ortam.mqtt == [("pemf/coil/8/control", "stop", "telemetry_stale")]
    c = a._live_state["coils"][7]
    assert (c["connected"], c["running"]) == (False, False)
    assert "esp telemetry watchdog error" not in _log(caplog)


# ── dakika ortalaması ve tampon ──────────────────────────────────────────────────────────────


def test_DAKIKA_bos_akumulator_atlanir_kosu_MIN_MAKS_guncellenir(ortam):
    """n=0 akümülatör satır üretmez; açık koşulu bobinin akümülatörü t_min/t_max → koşu istatistiği min/maks'ı genişler, n artar."""
    a = ortam.a
    with a._active_coil_runs_lock:
        a._active_coil_runs[3] = 501
    with a._coil_run_stats_lock:
        a._coil_run_stats[501] = {"n": 0, "t_sum": 0.0, "i_sum": 0.0, "b_sum": 0.0, "t_min": 30.0, "t_max": 30.5}
    with a._minute_acc_lock:
        a._minute_acc.clear()
        a._minute_acc[2] = {"n": 0}
        a._minute_acc[3] = {"n": 2, "t_sum": 60.0, "t_n": 2, "t_min": 29.0, "t_max": 31.0, "i_sum": 0.0, "b_sum": 0.0}
    with a._sensor_sample_buffer_lock:
        a._sensor_sample_buffer.clear()
    a._emit_minute_averages(1000.0)
    assert [s["coil_id"] for s in a._sensor_sample_buffer] == ["3"]
    st = a._coil_run_stats[501]
    assert (st["t_min"], st["t_max"], st["n"]) == (29.0, 31.0, 2)


def test_DAKIKA_tampon_20000_TAVANI_en_eskiyi_atar(ortam):
    """Tampon 20 000 doluyken yeni dakika satırı → uzunluk 20 000, en eski satır düşer, yeni satır sonda."""
    a = ortam.a
    with a._sensor_sample_buffer_lock:
        a._sensor_sample_buffer[:] = [{"i": i} for i in range(20000)]
    with a._minute_acc_lock:
        a._minute_acc.clear()
        a._minute_acc[4] = {"n": 1, "t_sum": 0.0, "i_sum": 0.0, "b_sum": 0.0}
    a._emit_minute_averages(2000.0)
    assert len(a._sensor_sample_buffer) == 20000
    assert a._sensor_sample_buffer[0] == {"i": 1} and a._sensor_sample_buffer[-1]["coil_id"] == "4"


def test_PERIYODIK_yazim_seanssizsa_DOKUNMAZ_hatada_GERI_koyar_basarida_bosaltir(ortam, monkeypatch):
    """db kimliği yok → tampon aynen; DB yazımı OperationalError → örnekler tampona geri; başarı → tampon boş, DB'ye 2 satır."""
    a = ortam.a
    ornek = [{"i": 1}, {"i": 2}]
    with a._sensor_sample_buffer_lock:
        a._sensor_sample_buffer[:] = list(ornek)
    with a._session_lock:
        a._active_session["db_session_id"] = None
    a._flush_sensor_buffer_if_active()
    assert a._sensor_sample_buffer == ornek
    with a._session_lock:
        a._active_session["db_session_id"] = 70
    bozuk = _Db("add_sensor_samples_batch")
    monkeypatch.setattr(a, "_get_treatment_db", lambda: bozuk)
    a._flush_sensor_buffer_if_active()
    assert a._sensor_sample_buffer == ornek
    saglam = _Db()
    monkeypatch.setattr(a, "_get_treatment_db", lambda: saglam)
    a._flush_sensor_buffer_if_active()
    assert a._sensor_sample_buffer == [] and saglam.cagri == [("add_sensor_samples_batch", 70, 2)]


# ── günlük bakım ─────────────────────────────────────────────────────────────────────────────


def test_BAKIM_KVKK_ve_vacuum_hatalari_yutulur(ortam, monkeypatch, caplog):
    """Seans yok + KVKK anonimleştirme turu istisna + tedavi ve hasta DB ertelenmiş VACUUM'u OperationalError → üç uyarı yazılır,
    retention (365 gün) çalışır, tur uykuya varır."""
    from services import kvkk_anonimlestirme

    a = ortam.a
    db = _Db("bekleyen_vacuum_calistir")
    hdb = _Db("bekleyen_vacuum_calistir")
    monkeypatch.setattr(a, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(a, "get_patient_database", lambda *x, **k: hdb)
    monkeypatch.setattr(kvkk_anonimlestirme, "tur", _patlayan(RuntimeError("onay tablosu okunamadı")))
    monkeypatch.delenv("PEMF_RETAIN_EVENT_DAYS", raising=False)
    with a._session_lock:
        a._active_session["is_active"] = False
    caplog.set_level(logging.WARNING)
    uyku, hatalar = _tur(a._daily_maintenance_loop, atla=1)
    assert (uyku, hatalar) == (2, [])
    assert ("purge_old_session_events", 365) in db.cagri
    log = _log(caplog)
    for parca in (
        "Hasta retention (anonimlestirme) hatasi",
        "Ertelenmis KVKK VACUUM'u (bakim) hatasi",
        "Hasta DB ertelenmis KVKK VACUUM'u (bakim) hatasi",
    ):
        assert parca in log, parca


def test_BAKIM_retention_hatasi_ve_seans_durumu_OKUNAMAZSA_VACUUM_YOK(ortam, monkeypatch, caplog):
    """Retention silmesi OperationalError → "Retention temizleme hatasi"; seans kilidi okunamıyor → seans VAR sayılır: tedavi ve
    hasta DB'sinde ertelenmiş VACUUM ÇAĞRILMAZ (fail-safe)."""
    a = ortam.a
    db = _Db("purge_old_session_events")
    hdb = _Db()
    monkeypatch.setattr(a, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(a, "get_patient_database", lambda *x, **k: hdb)

    class _BozukKilit:
        def __enter__(self):
            raise RuntimeError("kilit bozuk")

        def __exit__(self, *e):
            return False

    monkeypatch.setattr(a, "_session_lock", _BozukKilit())
    caplog.set_level(logging.WARNING)
    uyku, hatalar = _tur(a._daily_maintenance_loop, atla=1)
    assert (uyku, hatalar) == (2, [])
    assert "Retention temizleme hatasi" in _log(caplog)
    assert ("bekleyen_vacuum_calistir",) not in db.cagri and hdb.cagri == []


class _Imlec:
    def __init__(self, kayit, pragma_hata):
        self.kayit, self.pragma_hata = kayit, pragma_hata

    def execute(self, sql):
        self.kayit.append(sql)
        if sql.startswith("PRAGMA") and self.pragma_hata:
            raise sqlite3.OperationalError("database is locked")


class _Baglanti:
    def __init__(self, kayit, pragma_hata):
        self.kayit, self.pragma_hata = kayit, pragma_hata
        self.isolation_level = "DEFERRED"

    def cursor(self):
        return _Imlec(self.kayit, self.pragma_hata)

    def __enter__(self):
        return self

    def __exit__(self, *e):
        return False


def test_BAKIM_HAFTALIK_checkpoint_hatasi_yutulur_VACUUM_yine_yapilir(ortam, monkeypatch):
    """8. turda (run_count 7) seans yok → `run_maintenance` + PRAGMA wal_checkpoint (OperationalError, yutulur) + VACUUM; bağlantının
    yalıtım kipi eski hâline döner."""
    a = ortam.a
    sql: list = []
    baglanti = _Baglanti(sql, pragma_hata=True)
    db = _Db(baglanti=lambda: baglanti)
    monkeypatch.setattr(a, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(a, "get_patient_database", lambda *x, **k: None)
    with a._session_lock:
        a._active_session["is_active"] = False
    uyku, hatalar = _tur(a._daily_maintenance_loop, atla=8)
    assert (uyku, hatalar) == (9, [])
    assert ("run_maintenance",) in db.cagri
    assert sql == ["PRAGMA wal_checkpoint(TRUNCATE)", "VACUUM"]
    assert baglanti.isolation_level == "DEFERRED"


def test_BAKIM_HAFTALIK_bakim_hatasi_ve_GENEL_hata_donguyu_OLDURMEZ(ortam, monkeypatch, caplog):
    """Haftalık `run_maintenance` OperationalError → "Haftalik VACUUM/checkpoint hatasi"; tedavi DB erişimi istisna → "daily
    maintenance loop genel hatasi" (uyarı); döngü uykuya varır."""
    a = ortam.a
    db = _Db("run_maintenance")
    monkeypatch.setattr(a, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(a, "get_patient_database", lambda *x, **k: None)
    with a._session_lock:
        a._active_session["is_active"] = False
    caplog.set_level(logging.WARNING)
    uyku, hatalar = _tur(a._daily_maintenance_loop, atla=8)
    assert (uyku, hatalar) == (9, [])
    assert "Haftalik VACUUM/checkpoint hatasi" in _log(caplog)
    monkeypatch.setattr(a, "_get_treatment_db", _patlayan(sqlite3.OperationalError("database is malformed")))
    uyku, hatalar = _tur(a._daily_maintenance_loop, atla=1)
    assert (uyku, hatalar) == (2, [])
    assert "daily maintenance loop genel hatasi" in _log(caplog)


# ── başlatıcılar / yaşam döngüsü ─────────────────────────────────────────────────────────────


def test_ARKA_PLAN_baslatici_TEK_sefer_canli_E_hatasi_uyari(ortam, monkeypatch, caplog):
    """Gerçek başlatıcı (iş parçacıkları kaydedici sınıfla, açılmaz) + `efield_live.start_loop` istisna → dört döngü kaydedilir,
    "Canlı E-alanı döngüsü başlatılamadı" yazılır; ikinci çağrı HİÇBİR şey başlatmaz."""
    from servers import efield_live

    c = sys.modules.get("conftest")
    assert c is not None and Path(c.__file__).resolve() == (Path(__file__).parent / "conftest.py").resolve()
    gercek = c._GERCEK_ARKA_PLAN_BASLATICI
    a = ortam.a
    baslatilan: list = []

    class _Kayit(threading.Thread):
        def start(self):
            baslatilan.append(self.name)

    monkeypatch.setattr(a, "_threading", SimpleNamespace(Thread=_Kayit))
    monkeypatch.setattr(a, "_bg_threads_started", False)
    monkeypatch.setattr(efield_live, "start_loop", _patlayan(RuntimeError("E döngüsü kurulamadı")))
    monkeypatch.delenv("PEMF_SIMULATE", raising=False)
    caplog.set_level(logging.WARNING)
    gercek()
    assert baslatilan == ["session-watchdog", "sensor-persist", "daily-maintenance", "esp-telemetry-watchdog"]
    assert "Canlı E-alanı döngüsü başlatılamadı" in _log(caplog)
    gercek()
    assert len(baslatilan) == 4


def test_BROKER_sondasi_DURDURULUNCA_tek_deneme_sessiz_doner(ortam, monkeypatch, caplog):
    """Sonda durdurma olayı kurulu + broker yanıtsız (None) → tek deneme, None döner, "OLCULEMEDI" uyarısı BASILMAZ."""
    from utils import mqtt_kimlik

    a = ortam.a
    deneme: list = []
    monkeypatch.setattr(mqtt_kimlik, "broker_anonim_kabul_ediyor_mu", lambda h, p: deneme.append((h, p)))
    a._sonda_dur.set()
    try:
        caplog.set_level(logging.WARNING)
        assert a._broker_kimlik_sondasi() is None
    finally:
        a._sonda_dur.clear()
    assert deneme == [a._YEREL_BROKER]
    assert not [m for m in _log(caplog) if "OLCULEMEDI" in m]


def test_MQTT_dinleyici_istemci_KURULAMAZSA_uyari_istemci_degismez(ortam, monkeypatch, caplog):
    """ESP etkin + paho istemcisi kurulamıyor → "MQTT dinleyici başlatılamadı: …" uyarısı, `_mqtt_client_api` değişmez."""
    import paho.mqtt.client as pm

    a = ortam.a
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    monkeypatch.setattr(a, "_broker_kimlik_sondasi", lambda: None)
    monkeypatch.setattr(a, "_mqtt_client_api", None)
    monkeypatch.setattr(pm, "Client", _patlayan(OSError("soket açılamadı")))
    caplog.set_level(logging.WARNING)
    a._start_mqtt_for_api()
    assert a._mqtt_client_api is None
    assert "MQTT dinleyici başlatılamadı: soket açılamadı" in _log(caplog)


def test_LIFESPAN_kapanisi_MQTT_ve_mDNS_hatalarini_yutar(ortam, monkeypatch):
    """Lifespan kapanışında MQTT istemcisi `loop_stop` tamam, `disconnect` istisna + `stop_mdns` istisna → TestClient kapanışı
    istisnasız; MQTT hatasından SONRA mDNS kapatması da DENENİR: sıra loop_stop · disconnect · stop_mdns (TUR 2 · KP1-IA.2:
    `stop_mdns` çağrısı kaydedilmiyordu — LAN ilanı kapanışta hiç kapatılmasa da yeşildi)."""
    from servers import auto_discovery

    a = ortam.a
    kayit: list = []

    class _Istemci:
        def loop_stop(self):
            kayit.append("loop_stop")

        def disconnect(self):
            kayit.append("disconnect")
            raise RuntimeError("soket zaten kapalı")

    def _stop_mdns():
        kayit.append("stop_mdns")
        raise OSError("zeroconf kapalı")

    monkeypatch.setattr(a, "_mqtt_client_api", _Istemci())
    monkeypatch.setattr(auto_discovery, "stop_mdns", _stop_mdns)
    with TestClient(a.app, client=("127.0.0.1", 50400)) as c:
        assert c.get("/api/health").status_code == 200
    assert kayit == ["loop_stop", "disconnect", "stop_mdns"]


def test_OLAY_VERIYOLU_kaydi_PATLARSA_uyari_kayitli_sayilmaz(ortam, monkeypatch, caplog):
    """`event_bus.subscribe` istisna → "EventBus handler registration failed" uyarısı, `_event_bus_registered` False kalır."""
    import event_bus

    a = ortam.a
    monkeypatch.setattr(a, "_event_bus_registered", False)
    monkeypatch.setattr(event_bus, "subscribe", _patlayan(RuntimeError("veriyolu kapalı")))
    caplog.set_level(logging.WARNING)
    a._register_event_bus_handlers()
    assert a._event_bus_registered is False
    assert "EventBus handler registration failed: veriyolu kapalı" in _log(caplog)


def test_Y53_tek_bobin_STOP_PATLARSA_teyitsiz_ek_metni(ortam, monkeypatch, caplog):
    """Aşırı sıcaklık alarmı + bobin STOP yayını istisna → bobin "çalışmıyor" yayınlanır, uyarı bildirimi
    `bildirim.asiriSicaklik` + `bildirim.stopDogrulanamadiEk`, "Y53: bobin N STOP basarisiz" yazılır."""
    esp_yolu_gerekir()
    from utils import ceviri

    a = ortam.a
    monkeypatch.setattr(a, "_mqtt_publish", _patlayan(OSError("broker yok")))
    _bobin(a, ESP_BOBIN - 1, running=True)
    caplog.set_level(logging.ERROR)
    a._y53_yalniz_kendi_bobinini_durdur(ESP_BOBIN, "overtemp")
    assert a._live_state["coils"][ESP_BOBIN - 1]["running"] is False
    beklenen = ceviri.t("bildirim.asiriSicaklik", dil="tr", coil=ESP_BOBIN, atype="overtemp") + ceviri.t(
        "bildirim.stopDogrulanamadiEk", dil="tr"
    )
    assert (beklenen, "warning") in ortam.bildirim
    assert f"Y53: bobin {ESP_BOBIN} STOP basarisiz" in _log(caplog)


def test_SEANS_KAPANIS_sarmalayicisi_alan_kaydi_ve_E_baglami_hatasini_yutar(ortam, monkeypatch, caplog):
    """Seans pasife alınırken alan kaydı kapanışı ve canlı E bağlamı temizliği istisna → ikisi de yazılır, canlı durum yine
    "pasif" güncellenir (`activeTreatment.isActive` False)."""
    from servers import efield_live

    a = ortam.a
    monkeypatch.setattr(a._seans_alan, "seans_bitti", _patlayan(OSError("CSV kilitli")))
    monkeypatch.setattr(efield_live, "seans_bitti", _patlayan(RuntimeError("E bağlamı kilitli")))
    with a._live_state_lock:
        a._live_state["activeTreatment"]["isActive"] = True
    caplog.set_level(logging.ERROR)
    a.update_live_session_state(is_active=False, mode="Sistem Hazır")
    assert a._live_state["activeTreatment"]["isActive"] is False
    log = _log(caplog)
    assert "seans alan kaydı kapatılamadı (seans akışı etkilenmez)" in log
    assert "canlı E bağlamı temizlenemedi (seans akışı etkilenmez)" in log
