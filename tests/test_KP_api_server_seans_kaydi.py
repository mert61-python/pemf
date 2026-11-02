# Author: mertaygn, cglrgrkn
"""KP-1 · apps/backend/servers/api_server.py · sözleşmeler: seans DURDURMA ve KAYIT kapanışı — `/api/session/stop` (STM STOP
istisnası teyitsiz sayılır → 409 + bildirim hatası yutulur; DB yazım hataları yanıtı bozmaz; seans DB'ye bağlı değilse
tampon kaybı uyarısı; kalıcı kayıt genel hatası yutulur; seanssız durdurmada STM hatası teyitsiz), `_finalize_session_db`
(dakika ortalaması / tampon yazımı / koşu kapatma / DB erişimi hataları — örnekler tampona GERİ konur, mühür sebebe göre),
ertelenmiş VACUUM (iş hatası ve iş parçacığı açılamaması), kapanış kaydı, başlatma geri alma ve iptal satırı, yardımcılar
(`_get_treatment_db`, `_kayit_db_hazir`, `_lookup_owner_email`, `_bobin_suresi_doldu`, `_bildir_teyitsiz_stop`).

Sahte EN ALT katta: tedavi DB'si (`_get_treatment_db` → kayıtçı, arıza biçimi `sqlite3.OperationalError`), hasta DB'si
(`get_patient_database`), donanım (`state.hardware`, G/Ç `OSError`), kayıt kuyruğu (`utils.dongu_disi_yazim.calistir`, yürütücü
kapalı `RuntimeError`), iş parçacığı açılışı (`threading.Thread.start`, adla), bildirim / WS kaydı.
"""

from __future__ import annotations

import copy
import logging
import sqlite3
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from topoloji import STM_BOBIN, TUM_STM


@pytest.fixture
def ortam(monkeypatch):
    from servers import api_server as a
    from servers import live_state as ls

    yayin: list = []
    bildirim: list = []
    engelli: list = []
    acilamayan: list = []
    gercek = threading.Thread

    class _Secici(gercek):
        def start(self):
            if any(str(self.name).startswith(on) for on in engelli):
                acilamayan.append(self.name)
                raise RuntimeError("can't start new thread")
            return super().start()

    monkeypatch.setattr(threading, "Thread", _Secici)
    monkeypatch.setattr(a, "_ws_broadcast_sync", lambda m: yayin.append(m))
    monkeypatch.setattr(ls, "_ws_broadcast_sync", lambda m: yayin.append(m))
    monkeypatch.setattr(a, "_push_notification", lambda m, s="info", mesajlar=None: bildirim.append((m, s)))
    monkeypatch.setattr(a, "_mqtt_publish", lambda t, p: False)
    monkeypatch.setattr(a.state, "hardware", None)
    with a._live_state_lock:
        canli_once = {k: copy.deepcopy(v) for k, v in a._live_state.items()}
    with a._session_lock:
        seans_once = dict(a._active_session)
    with a._sensor_sample_buffer_lock:
        tampon_once = list(a._sensor_sample_buffer)
    with a._minute_acc_lock:
        dakika_once = copy.deepcopy(a._minute_acc)
    try:
        yield SimpleNamespace(a=a, yayin=yayin, bildirim=bildirim, engelli=engelli, acilamayan=acilamayan)
    finally:
        for t in [t for t in threading.enumerate() if t.name == "kvkk-vacuum"]:
            t.join(5)
        with a._session_lock:
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


def _patlayan(hata):
    def _f(*_a, **_k):
        raise hata

    return _f


def _log(caplog):
    return [r.getMessage() for r in caplog.records]


class _Db:
    """Tedavi DB'si yerine: istenen yöntemler `sqlite3.OperationalError` verir, tüm çağrılar kaydedilir."""

    def __init__(self, *bozuk):
        self.bozuk = set(bozuk)
        self.cagri: list = []

    def _kaydet(self, ad, *a):
        self.cagri.append((ad, *a))
        if ad in self.bozuk:
            raise sqlite3.OperationalError("disk I/O error")

    def add_sensor_samples_batch(self, sid, rows):
        self._kaydet("add_sensor_samples_batch", sid, len(rows))
        return len(rows)

    def end_session(self, sid, duration_minutes=0, session_status="completed"):
        self._kaydet("end_session", sid, session_status)

    def set_session_meta(self, sid, **k):
        self._kaydet("set_session_meta", sid)

    def record_session_event(self, sid, tur, **k):
        self._kaydet("record_session_event", sid, tur)

    def bekleyen_vacuum_calistir(self):
        self._kaydet("bekleyen_vacuum_calistir")

    def is_ready(self):
        self._kaydet("is_ready")
        return True, ""


def _kosu_kapatma_bozuk(monkeypatch):
    from utils import dongu_disi_yazim

    gercek = dongu_disi_yazim.calistir

    def _kuyruk(fn, *x, ad="kayit", **k):
        if str(ad).startswith("bobin kosu kaydi bitir"):
            raise RuntimeError("cannot schedule new futures after shutdown")
        return gercek(fn, *x, ad=ad, **k)

    monkeypatch.setattr(dongu_disi_yazim, "calistir", _kuyruk)


def _seans(a, **ek):
    with a._session_lock:
        a._active_session.update(
            is_active=True,
            session_id="kp-seans",
            coil_ids=[STM_BOBIN],
            started_epoch=time.time() - 120,
            start_mono=time.monotonic() - 120,
            **ek,
        )


class _BozukDurum:
    def items(self):
        raise RuntimeError("durum sözlüğü değişti")


def _vakum_bekle():
    for t in [t for t in threading.enumerate() if t.name == "kvkk-vacuum"]:
        t.join(5)


def test_STOP_STM_istisnasi_TEYITSIZ_409_ve_yan_hatalar_yutulur(ortam, monkeypatch, caplog):
    """Aktif seans (db 55) + HC `update_coil` OSError + HC durum okunamıyor + koşu kapatma kuyruğu kapalı + bozuk dakika
    akümülatörü + tampon yazımı ve `end_session` OperationalError + bildirim kanalı patlıyor + ertelenmiş VACUUM patlıyor →
    409 {status: hardware_stop_unconfirmed, hardware_stop_unconfirmed: [STM], session_closed: True, sensor_samples: 0}; her
    arıza günlüğe yazılır, seans pasif."""
    from utils import ceviri

    a = ortam.a
    db = _Db("add_sensor_samples_batch", "end_session", "bekleyen_vacuum_calistir")
    monkeypatch.setattr(a, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(
        a.state,
        "hardware",
        SimpleNamespace(coils_state=_BozukDurum(), core=None, update_coil=_patlayan(OSError("seri port yok"))),
    )
    monkeypatch.setattr(a, "_push_notification", _patlayan(ConnectionResetError("bildirim kanalı kapandı")))
    _kosu_kapatma_bozuk(monkeypatch)
    with a._minute_acc_lock:
        a._minute_acc[STM_BOBIN] = None
    with a._sensor_sample_buffer_lock:
        a._sensor_sample_buffer[:] = [{"coil_id": STM_BOBIN, "t": 1}]
    _seans(a, db_session_id=55)
    caplog.set_level(logging.DEBUG)
    with TestClient(a.app, client=("127.0.0.1", 50300)) as c:
        r = c.post("/api/session/stop")
    _vakum_bekle()
    j = r.json()
    assert r.status_code == 409
    assert (j["status"], j["hardware_stop_unconfirmed"], j["session_closed"], j["sensor_samples"]) == (
        "hardware_stop_unconfirmed",
        [STM_BOBIN],
        True,
        0,
    )
    assert j["detail"] == ceviri.t("seans.uyari.stopDogrulanamadi", dil="tr", bobinler=str(STM_BOBIN))
    assert a._active_session["is_active"] is False
    log = _log(caplog)
    for parca in (
        "stop: minute emit hatasi",
        "Y63: HC bobin durumu okunamadi (o kaynak atlandi)",
        f"_stop_session_coils: STM stop hatasi (bobin {STM_BOBIN})",
        "_stop_session_coils _finish_coil_run hatasi",
        "stop: sensor flush hatasi",
        "stop: end_session hatasi",
        "stop: teyitsiz-durdurma bildirimi gonderilemedi",
        "Ertelenmis KVKK VACUUM'u calistirilamadi",
    ):
        assert parca in log, parca


def _saglam_hc(a, monkeypatch):
    """STOP'u kabul eden HC (yazım izi bildirmeyen çekirdek → "kuyruğa verildi" = teyit)."""
    monkeypatch.setattr(
        a.state, "hardware", SimpleNamespace(core=None, coils_state={}, update_coil=lambda *x, **k: True)
    )


def test_STOP_seans_DB_ye_BAGLI_DEGILSE_tampon_kaybi_uyarisi(ortam, monkeypatch, caplog):
    """Aktif seans db kimliksiz + tamponda 2 örnek → 200 success, tampon boşaltılır, "stop: db_session_id YOK → 2 sensor
    satiri KALICI DEGIL" uyarısı yazılır."""
    a = ortam.a
    _saglam_hc(a, monkeypatch)
    with a._sensor_sample_buffer_lock:
        a._sensor_sample_buffer[:] = [{"t": 1}, {"t": 2}]
    _seans(a, db_session_id=None)
    caplog.set_level(logging.WARNING)
    with TestClient(a.app, client=("127.0.0.1", 50301)) as c:
        r = c.post("/api/session/stop")
    assert r.status_code == 200 and r.json()["status"] == "success"
    assert a._sensor_sample_buffer == []
    assert any("db_session_id YOK → 2 sensor satiri KALICI DEGIL" in m for m in _log(caplog))


def test_STOP_kalici_kayit_GENEL_hatasi_yaniti_bozmaz(ortam, monkeypatch, caplog):
    """Aktif seans (db 56) + tedavi DB erişimi istisna → yanıt 200 success (sensor_samples 0), "stop: kalici kayit genel hatasi"."""
    a = ortam.a
    _saglam_hc(a, monkeypatch)
    monkeypatch.setattr(a, "_get_treatment_db", _patlayan(sqlite3.OperationalError("database is malformed")))
    _seans(a, db_session_id=56)
    caplog.set_level(logging.ERROR)
    with TestClient(a.app, client=("127.0.0.1", 50302)) as c:
        r = c.post("/api/session/stop")
    assert r.status_code == 200 and r.json()["sensor_samples"] == 0
    assert "stop: kalici kayit genel hatasi" in _log(caplog)


def test_STOP_SEANSSIZ_STM_hatasi_tum_STM_teyitsiz_kosu_hatasi_yutulur(ortam, monkeypatch, caplog):
    """Seans yok + `stop_all_coils` OSError + koşu kapatma kuyruğu kapalı → {status: ok, hardware_stop_unconfirmed: tüm STM}."""
    a = ortam.a
    monkeypatch.setattr(a.state, "hardware", SimpleNamespace(core=None, stop_all_coils=_patlayan(OSError("port yok"))))
    _kosu_kapatma_bozuk(monkeypatch)
    with a._session_lock:
        a._active_session["is_active"] = False
    caplog.set_level(logging.DEBUG)
    with TestClient(a.app, client=("127.0.0.1", 50303)) as c:
        r = c.post("/api/session/stop")
    j = r.json()
    assert j["status"] == "ok" and j["hardware_stop_unconfirmed"] == sorted(TUM_STM)
    log = _log(caplog)
    assert "seanssiz stop: STM stop_all hatasi" in log and "seanssiz stop: _finish_coil_run hatasi" in log


def test_FINALIZE_tampon_yazimi_PATLARSA_ornekler_tampona_GERI_konur(ortam, monkeypatch, caplog):
    """Bozuk dakika akümülatörü + 3 örnek + `add_sensor_samples_batch` OperationalError → 0 döner; 3 örnek tamponun BAŞINA geri
    konur; seans yine "completed" kapanır; "finalize: dakika-ortalamasi hatasi" ve "…buffer'a geri konuldu" yazılır."""
    a = ortam.a
    db = _Db("add_sensor_samples_batch")
    monkeypatch.setattr(a, "_get_treatment_db", lambda: db)
    ornek = [{"i": 1}, {"i": 2}, {"i": 3}]
    with a._minute_acc_lock:
        a._minute_acc[STM_BOBIN] = None
    with a._sensor_sample_buffer_lock:
        a._sensor_sample_buffer[:] = list(ornek)
    caplog.set_level(logging.WARNING)
    assert (
        a._finalize_session_db(60, time.time() - 30, coil_ids=[], reason="auto", start_mono=time.monotonic() - 30) == 0
    )
    _vakum_bekle()
    assert a._sensor_sample_buffer[:3] == ornek
    assert ("end_session", 60, "completed") in db.cagri
    log = _log(caplog)
    assert "finalize: dakika-ortalamasi hatasi" in log
    assert "finalize: 3 sensor ornegi yazilamadi → buffer'a geri konuldu." in log


def test_FINALIZE_DB_erisimi_ve_kosu_ve_VACUUM_is_parcacigi_hatasi_yutulur(ortam, monkeypatch, caplog):
    """Koşu kapatma kuyruğu kapalı + tedavi DB erişimi istisna + VACUUM iş parçacığı açılamıyor → `_finalize_session_db` 0 döner;
    "finalize: _finish_coil_run(N) hatasi", "finalize: kalici kayit hatasi" ve "KVKK VACUUM is parcacigi acilamadi" yazılır."""
    a = ortam.a
    _kosu_kapatma_bozuk(monkeypatch)
    monkeypatch.setattr(a, "_get_treatment_db", _patlayan(sqlite3.OperationalError("database is locked")))
    ortam.engelli.append("kvkk-vacuum")
    caplog.set_level(logging.DEBUG)
    assert a._finalize_session_db(61, time.time(), coil_ids=[STM_BOBIN]) == 0
    log = _log(caplog)
    assert f"finalize: _finish_coil_run({STM_BOBIN}) hatasi" in log
    assert "finalize: kalici kayit hatasi" in log
    assert "KVKK VACUUM is parcacigi acilamadi (bakimda denenecek)" in log
    assert ortam.acilamayan == ["kvkk-vacuum"]


def test_KAPANIS_kaydi_bos_goruntu_DB_ye_dokunmaz_olay_hatasi_yutulur_KESINTI(ortam, monkeypatch, caplog):
    """Görüntü None / db kimliksiz → DB çağrısı yok; db 62 + olay yazımı OperationalError → uyarı "kapanis: session_event
    yazilamadi" ve satır "interrupted" mühürlenir."""
    a = ortam.a
    db = _Db("record_session_event")
    monkeypatch.setattr(a, "_get_treatment_db", lambda: db)
    a.kapanis_seans_kaydini_kapat(None)
    a.kapanis_seans_kaydini_kapat({"db_session_id": None})
    assert db.cagri == []
    caplog.set_level(logging.WARNING)
    a.kapanis_seans_kaydini_kapat({"db_session_id": 62, "started_epoch": time.time() - 10, "coil_ids": [], "mode": "m"})
    _vakum_bekle()
    assert ("end_session", 62, "interrupted") in db.cagri
    assert "kapanis: session_event yazilamadi" in _log(caplog)


def test_GERI_ALMA_canli_durum_hatasi_yutulur_DONANIM_REDDI_muhru(ortam, monkeypatch, caplog):
    """Aktif seans (db 63) geri alınıyor + canlı durum güncellemesi istisna → seans pasif, satır `SEANS_DURUMU_DONANIM_REDDI`."""
    from database.treatment_history_db import SEANS_DURUMU_DONANIM_REDDI
    from servers import live_state as ls

    a = ortam.a
    db = _Db()
    monkeypatch.setattr(a, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(ls, "update_live_session_state", _patlayan(RuntimeError("canlı durum kilitli")))
    _seans(a, db_session_id=63)
    caplog.set_level(logging.DEBUG)
    a._seansi_geri_al("donanim-reddi:hicbir-bobin-surulmedi", "kp-seans")  # çağrı yerindeki gerçek sebep
    _vakum_bekle()
    assert a._active_session["is_active"] is False
    assert ("end_session", 63, SEANS_DURUMU_DONANIM_REDDI) in db.cagri
    assert "geri-al: canli durum guncellenemedi" in _log(caplog)


def test_GERI_ALMA_kimlik_KARSILASTIRILAMAZSA_istisnasiz_seans_DOKUNULMAZ(ortam, caplog):
    """Seans kimliği karşılaştırması istisna atıyor → geri alma istisna sızdırmaz, aktif seans AKTİF kalır, hata yazılır."""

    class _Kimlik:
        def __eq__(self, o):
            raise TypeError("karşılaştırılamaz")

        __hash__ = object.__hash__

    a = ortam.a
    _seans(a, db_session_id=None)
    caplog.set_level(logging.ERROR)
    a._seansi_geri_al("kp-red", _Kimlik())
    assert a._active_session["is_active"] is True
    assert "Seans geri alma basarisiz (kp-red)" in _log(caplog)


def test_IPTAL_satiri_kimliksiz_DBsiz_ve_yazim_hatasi(ortam, monkeypatch, caplog):
    """`_iptal_seans_satirini_kapat`: kimlik yok → DB'ye gidilmez; DB yok → sessiz; `end_session` OperationalError → uyarı."""
    a = ortam.a
    cagri: list = []
    monkeypatch.setattr(a, "_get_treatment_db", lambda: cagri.append(1))
    a._iptal_seans_satirini_kapat(None)
    assert cagri == []
    a._iptal_seans_satirini_kapat(64)
    assert cagri == [1]
    db = _Db("end_session")
    monkeypatch.setattr(a, "_get_treatment_db", lambda: db)
    caplog.set_level(logging.WARNING)
    a._iptal_seans_satirini_kapat(65)
    assert db.cagri == [("end_session", 65, "cancelled")]
    assert "Iptal edilen seansin DB satiri kapatilamadi (db_id=65)." in _log(caplog)


def test_tedavi_DB_getirici_PATLARSA_None_ve_hazirlik_sebebi(ortam, monkeypatch):
    """`get_treatment_db` istisna → `_get_treatment_db` None; `is_ready` istisna → `_kayit_db_hazir` (False, ilk 200 karakter)."""
    import database.treatment_history_db as thdb

    a = ortam.a
    monkeypatch.setattr(thdb, "get_treatment_db", _patlayan(sqlite3.OperationalError("unable to open database file")))
    assert a._get_treatment_db() is None

    class _Hazir:
        def is_ready(self):
            raise sqlite3.DatabaseError("x" * 300)

    monkeypatch.setattr(a.state, "core", None)
    monkeypatch.setattr(a, "_get_treatment_db", lambda: _Hazir())
    assert a._kayit_db_hazir() == (False, "x" * 200)


def test_sahip_epostasi_HASTA_DB_yok_ya_da_patlarsa_bos(ortam, monkeypatch):
    """Hasta DB yok → ""; `get_patient` istisna → ""; kayıt var → kırpılmış e-posta."""
    a = ortam.a
    monkeypatch.setattr(a, "get_patient_database", lambda *x, **k: None)
    assert a._lookup_owner_email("u-1") == ""
    monkeypatch.setattr(
        a,
        "get_patient_database",
        lambda *x, **k: SimpleNamespace(get_patient=_patlayan(sqlite3.OperationalError("kilitli"))),
    )
    assert a._lookup_owner_email("u-1") == ""
    monkeypatch.setattr(
        a,
        "get_patient_database",
        lambda *x, **k: SimpleNamespace(get_patient=lambda u: {"owner_email": "  s@ornek.com "}),
    )
    assert a._lookup_owner_email("u-1") == "s@ornek.com"


def test_SURE_KAPAGI_kosu_kapatma_ve_is_parcacigi_hatasi(ortam, monkeypatch, caplog):
    """Açık koşulu bobinin süre kapağı doldu: koşu kapatma kuyruğu kapalı → "sure kapagi: kosu kaydi kapatilamadi (bobin N)";
    iş parçacığı açılamazsa → "sure kapagi: kayit is parcacigi acilamadi"."""
    a = ortam.a
    _kosu_kapatma_bozuk(monkeypatch)
    with a._active_coil_runs_lock:
        a._active_coil_runs[STM_BOBIN] = 7001
    caplog.set_level(logging.WARNING)
    a._bobin_suresi_doldu([STM_BOBIN])
    for t in [t for t in threading.enumerate() if t.name == "sure-kapagi-kayit"]:
        t.join(5)
    assert f"sure kapagi: kosu kaydi kapatilamadi (bobin {STM_BOBIN})" in _log(caplog)
    ortam.engelli.append("sure-kapagi-kayit")
    a._bobin_suresi_doldu([STM_BOBIN])
    assert "sure kapagi: kayit is parcacigi acilamadi (kosu kaydi acik kalabilir)" in _log(caplog)


def test_TEYITSIZ_stop_bildirimi_patlarsa_uyari_yazilir(ortam, monkeypatch, caplog):
    """Teyitsiz bobin listesi + bildirim kanalı patlıyor → istisna sızmaz, "teyitsiz-stop bildirimi gonderilemedi (kaynak)"."""
    a = ortam.a
    monkeypatch.setattr(a, "_push_notification", _patlayan(ConnectionResetError("kanal kapalı")))
    caplog.set_level(logging.WARNING)
    a._bildir_teyitsiz_stop([STM_BOBIN], lambda d: "kp-kaynak")
    assert "teyitsiz-stop bildirimi gonderilemedi (kp-kaynak)" in _log(caplog)
