# Author: mertaygn, cglrgrkn
"""KP-1 · apps/backend/servers/api_server.py · sözleşmeler: `start_ai_session` kenar yolları (hasta ayna satırı yazılamazsa seans
SAHİPSİZ başlar; anlık görüntüde "devam" sanılan seans kilitte bitmişse satırsız seans AÇILMAZ — Y65 `KayitAcilamadi`, oturuma
dokunulmaz; DB çağrısı sürerken eşzamanlı AI (Auto) seansı başladıysa açılan satır "cancelled" mühürlenir ve süren seans
korunur; canlı E bağlamı temizlenemese de seans başlar; devralınan elle seansın koşu kapatması düşse de seans "interrupted"
kapanır; başlangıç damgası yazılamasa da kimlik döner), süre bekçisi TOCTOU mührü (süre dolan seans STOP'tan hemen önce
DEVRALINMIŞSA yeni seansın bobinlerine STOP gitmez), simülasyon döngüsü (bozuk seans verisi döngüyü öldürmez, o tur yayın
yok), mDNS başlatıcı (gerçek API portu ve "PEMF-Vet" adı; hata yutulur ve günlüğe yazılır), `OnbellekPolitikaliStatik`
(giriş belgesi `no-store`, içerik-hash'li varlık `immutable`, öteki dosya ve 304 yanıtı `no-cache`).

Sahte EN ALT katta: tedavi DB'si (kayıtçı; arıza `sqlite3.OperationalError`), hasta defteri (`get_patient_database` → None),
koşu kaydı kuyruğu (`utils.dongu_disi_yazim.calistir` → yürütücü kapalı `RuntimeError`), canlı E alanı modülü
(`efield_live.seans_basladi`), donanım (`state.hardware.update_coil` kayıtçı), oturum kilidi (iki kritik bölge ARASINDA öteki
iş parçacığının işi: `__enter__` kancası), uyku (`time.sleep` — yalnız döngü iş parçacığında turu bitirir), mDNS yayıncısı
(`servers.auto_discovery.start_mdns`), statik dizin (tmp).
"""

from __future__ import annotations

import copy
import logging
import sqlite3
import threading
import time as _time
from types import SimpleNamespace

import pytest
from topoloji import STM_BOBIN


def _log(caplog):
    return [r.getMessage() for r in caplog.records]


@pytest.fixture
def ortam(monkeypatch):
    from servers import api_server as a
    from servers import efield_live
    from servers import live_state as ls

    yayin: list = []
    ef: list = []
    monkeypatch.setattr(a, "_ws_broadcast_sync", lambda m: yayin.append(m))
    monkeypatch.setattr(ls, "_ws_broadcast_sync", lambda m: yayin.append(m))
    monkeypatch.setattr(a, "_push_notification", lambda m, s="info", mesajlar=None: None)
    monkeypatch.setattr(a, "_mqtt_publish", lambda t, p: False)
    monkeypatch.setattr(a, "get_patient_database", lambda *x, **k: None)
    monkeypatch.setattr(efield_live, "seans_basladi", lambda tur="", model=None: ef.append((tur, model)))
    monkeypatch.setattr(a.state, "hardware", None)
    seans_kilidi = a._session_lock
    with a._live_state_lock:
        canli_once = {k: copy.deepcopy(v) for k, v in a._live_state.items()}
    with seans_kilidi:
        seans_once = dict(a._active_session)
    with a._sensor_sample_buffer_lock:
        tampon_once = list(a._sensor_sample_buffer)
    with a._minute_acc_lock:
        dakika_once = copy.deepcopy(a._minute_acc)
    try:
        yield SimpleNamespace(a=a, yayin=yayin, ef=ef)
    finally:
        for t in [t for t in threading.enumerate() if t.name == "kvkk-vacuum"]:
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


class _Db:
    """Tedavi DB'si yerine: `bozuk` yöntemler `sqlite3.OperationalError` verir; `kanca` `start_session` SIRASINDA koşar."""

    def __init__(self, *bozuk, sid=501, kanca=None):
        self.bozuk, self.sid, self.kanca = set(bozuk), sid, kanca
        self.cagri: list = []

    def _kaydet(self, ad, *x):
        self.cagri.append((ad, *x))
        if ad in self.bozuk:
            raise sqlite3.OperationalError("database is locked")

    def upsert_patient(self, d):
        self._kaydet("upsert_patient", d.get("name"))
        return 77

    def start_session(self, **k):
        self._kaydet("start_session", k.get("treatment_mode"), k.get("patient_name"))
        if self.kanca:
            self.kanca()
        return self.sid

    def end_session(self, sid, duration_minutes=0, session_status="completed"):
        self._kaydet("end_session", sid, session_status)

    def set_session_meta(self, sid, **k):
        self._kaydet("set_session_meta", sid, k.get("patient_id"))

    def set_session_parameter(self, sid, ad, deger, birim=""):
        self._kaydet("set_session_parameter", sid, ad, deger)

    def add_sensor_samples_batch(self, sid, rows):
        return len(rows)

    def bekleyen_vacuum_calistir(self):
        self._kaydet("bekleyen_vacuum_calistir")


class _KancaliKilit:
    """Gerçek kilide yönlendirir; `kanca_sira`ncı girişte kilit alınmadan HEMEN önce `kanca` koşar (iki kritik bölge arasında
    öteki iş parçacığının işi)."""

    def __init__(self, gercek, kanca_sira, kanca):
        self.gercek, self.sira, self.kanca, self.giris = gercek, kanca_sira, kanca, 0

    def __enter__(self):
        self.giris += 1
        if self.giris == self.sira:
            self.kanca()
        return self.gercek.__enter__()

    def __exit__(self, *e):
        return self.gercek.__exit__(*e)

    def acquire(self, *x, **k):
        return self.gercek.acquire(*x, **k)

    def release(self):
        return self.gercek.release()


def _ai_baslat(a, **k):
    arg = dict(freq=40, duty=30, duration_minutes=10, coil_ids=[STM_BOBIN], mode="AI Pro", tur="ai_pro")
    arg.update(k)
    return a.start_ai_session(**arg)


# ── start_ai_session ───────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_AI_SEANS_hasta_ayna_satiri_YAZILAMAZSA_seans_SAHIPSIZ_baslar(ortam, monkeypatch, caplog):
    """Hasta {Mia, u-1} + `upsert_patient` OperationalError → seans yine başlar (satır 501, hasta adıyla), `db_patient_id` None,
    uyarı "AI seansi: hasta ayna satiri yazilamadi (seans sahipsiz)"."""
    a = ortam.a
    db = _Db("upsert_patient")
    monkeypatch.setattr(a, "_get_treatment_db", lambda: db)
    with a._session_lock:
        a._active_session["is_active"] = False
    caplog.set_level(logging.WARNING)
    sid = _ai_baslat(a, hasta={"name": "Mia", "id": "u-1"})
    assert sid.startswith("ai_") and a._active_session["session_id"] == sid
    assert (a._active_session["db_session_id"], a._active_session["db_patient_id"]) == (501, None)
    assert ("start_session", "AI Pro", "Mia") in db.cagri
    assert ("set_session_meta", 501, None) in db.cagri
    assert "AI seansi: hasta ayna satiri yazilamadi (seans sahipsiz)" in _log(caplog)


def test_AI_SEANS_devam_sanilan_seans_KILITTE_bitmisse_SATIRSIZ_acilmaz_Y65(ortam, monkeypatch):
    """Anlık görüntüde AI (Auto) seansı sürüyor (devam → satır açılmaz); kilit alınmadan hemen önce o seans durduruldu → Y65
    `KayitAcilamadi` (ürün metni), DB'ye gidilmez, oturum DEĞİŞMEZ (bitmiş seans olduğu gibi kalır)."""
    from utils import ceviri

    a = ortam.a
    db = _Db()
    monkeypatch.setattr(a, "_get_treatment_db", lambda: db)
    with a._session_lock:
        a._active_session.clear()
        a._active_session.update(
            is_active=True, mode="AI", tur="ai_auto", session_id="ai_onceki", db_session_id=300, coil_ids=[STM_BOBIN]
        )
    kilit = _KancaliKilit(a._session_lock, 2, lambda: a._active_session.update(is_active=False))
    monkeypatch.setattr(a, "_session_lock", kilit)
    with pytest.raises(a.KayitAcilamadi) as e:
        _ai_baslat(a, mode="AI", tur="ai_auto")
    assert str(e.value) == ceviri.t("seans.hata.kayitAcilamadi", dil="tr")
    assert db.cagri == [] and kilit.giris == 2
    assert (a._active_session["is_active"], a._active_session["session_id"], a._active_session["db_session_id"]) == (
        False,
        "ai_onceki",
        300,
    )


def test_AI_SEANS_DB_cagrisi_SURERKEN_esZamanli_AI_Auto_basladiysa_satir_IPTAL(ortam, monkeypatch):
    """Seans yokken AI (Auto) başlatılıyor; satır (501) açılırken eşzamanlı bir AI (Auto) seansı (`ai_eszamanli`, satır 400)
    başladı → kilitte "devam": süren seansın kimliği döner, satırı 400 kalır, açılan 501 `cancelled` mühürlenir; canlı E
    bağlamı yeniden kurulmaz."""
    a = ortam.a

    def _eszamanli():
        with a._session_lock:
            a._active_session.clear()
            a._active_session.update(
                is_active=True,
                mode="AI",
                tur="ai_auto",
                session_id="ai_eszamanli",
                db_session_id=400,
                coil_ids=[STM_BOBIN],
                start_time=_time.time(),
            )

    db = _Db(kanca=_eszamanli)
    monkeypatch.setattr(a, "_get_treatment_db", lambda: db)
    with a._session_lock:
        a._active_session["is_active"] = False
    sid = _ai_baslat(a, mode="AI", tur="ai_auto")
    assert sid == "ai_eszamanli"
    assert (a._active_session["session_id"], a._active_session["db_session_id"]) == ("ai_eszamanli", 400)
    assert ("end_session", 501, "cancelled") in db.cagri
    assert not [c for c in db.cagri if c[0] == "set_session_meta"]
    assert ortam.ef == []


def test_AI_SEANS_canli_E_baglami_TEMIZLENEMESE_de_seans_baslar(ortam, monkeypatch, caplog):
    """`efield_live.seans_basladi` RuntimeError → seans aktif (satır 501), günlükte "canlı E bağlamı temizlenemedi"."""
    from servers import efield_live

    a = ortam.a
    db = _Db()
    monkeypatch.setattr(a, "_get_treatment_db", lambda: db)

    def _patla(tur="", model=None):
        raise RuntimeError("bağlam kilitli")

    monkeypatch.setattr(efield_live, "seans_basladi", _patla)
    with a._session_lock:
        a._active_session["is_active"] = False
    caplog.set_level(logging.ERROR)
    sid = _ai_baslat(a)
    assert a._active_session["is_active"] is True and a._active_session["session_id"] == sid
    assert a._active_session["db_session_id"] == 501
    assert "canlı E bağlamı temizlenemedi (seans akışı etkilenmez)" in _log(caplog)


def test_AI_SEANS_DEVRALMA_kosu_kapatma_DUSSE_de_eski_seans_INTERRUPTED_kapanir(ortam, monkeypatch, caplog):
    """Aktif ELLE seans (satır 301, bobin STM) + koşu kaydı kuyruğu kapalı (`_finish_coil_run` RuntimeError) → AI Pro devralır:
    eski satır `interrupted` kapanır (+ bitiş damgası), uyarı "aktif MANUEL seansi devraldi … (db_id=301)"; "eski manuel seans
    kapatma hatasi" YAZILMAZ; yeni seans satırı 501."""
    from utils import dongu_disi_yazim

    a = ortam.a
    db = _Db()
    monkeypatch.setattr(a, "_get_treatment_db", lambda: db)
    gercek = dongu_disi_yazim.calistir

    def _kuyruk(fn, *x, ad="kayit", **k):
        if str(ad).startswith("bobin kosu kaydi bitir"):
            raise RuntimeError("cannot schedule new futures after shutdown")
        return gercek(fn, *x, ad=ad, **k)

    monkeypatch.setattr(dongu_disi_yazim, "calistir", _kuyruk)
    with a._session_lock:
        a._active_session.clear()
        a._active_session.update(
            is_active=True,
            mode="Manuel",
            session_id="elle-1",
            db_session_id=301,
            coil_ids=[STM_BOBIN],
            started_epoch=_time.time() - 60,
            start_mono=_time.monotonic() - 60,
        )
    caplog.set_level(logging.WARNING)
    sid = _ai_baslat(a)
    assert sid != "elle-1" and a._active_session["db_session_id"] == 501
    assert ("end_session", 301, "interrupted") in db.cagri
    assert ("set_session_meta", 301, None) in db.cagri
    log = _log(caplog)
    assert (
        "AI seansi (AI Pro) aktif MANUEL seansi devraldi → eski seans (db_id=301) duzgun kapatildi (orphan onlendi)."
        in log
    )
    assert "AI gecisinde eski manuel seans kapatma hatasi" not in log


def test_AI_SEANS_baslangic_DAMGASI_yazilamasa_da_kimlik_doner(ortam, monkeypatch, caplog):
    """`set_session_meta` OperationalError → kimlik yine döner, seans aktif (satır 501), DEBUG "AI set_session_meta hatasi"."""
    a = ortam.a
    db = _Db("set_session_meta")
    monkeypatch.setattr(a, "_get_treatment_db", lambda: db)
    with a._session_lock:
        a._active_session["is_active"] = False
    caplog.set_level(logging.DEBUG)
    sid = _ai_baslat(a)
    assert a._active_session["session_id"] == sid and a._active_session["db_session_id"] == 501
    assert ("set_session_meta", 501, None) in db.cagri
    assert "AI set_session_meta hatasi" in _log(caplog)


# ── döngüler: tek tur ──────────────────────────────────────────────────────────────────────────────────────────────────────────


class _TurBitti(BaseException):
    pass


def _tur(fonk, sure: float = 20.0):
    """`fonk`u ayrı iş parçacığında koştur; o iş parçacığındaki ilk uyku turu bitirir. → (uyku sayısı, hatalar)."""
    orj_sleep = _time.sleep
    d = {"id": None, "uyku": 0}

    def _sleep(s):
        if threading.get_ident() == d["id"]:
            d["uyku"] += 1
            raise _TurBitti()
        return orj_sleep(s)

    hatalar: list = []

    def _kos():
        d["id"] = threading.get_ident()
        try:
            fonk()
        except _TurBitti:
            pass
        except BaseException as e:  # noqa: BLE001
            hatalar.append(e)

    _time.sleep = _sleep
    try:
        th = threading.Thread(target=_kos, daemon=True, name="kp-tek-tur")
        th.start()
        th.join(sure)
    finally:
        _time.sleep = orj_sleep
    assert not th.is_alive(), "döngü bir turda uykuya varmadı"
    return d["uyku"], hatalar


def test_SURE_BEKCISI_STOP_oncesi_seans_DEVRALINMISSA_yeni_seansa_STOP_gitmez(ortam, monkeypatch):
    """Seans A'nın süresi doldu; STOP'tan hemen önceki mühür denetiminden önce A durdurulup aynı bobinde B başladı → bayat tur
    atlanır: donanıma STOP GİTMEZ, B aktif kalır, döngü ölmez (tek uyku, hata yok)."""
    a = ortam.a
    stop: list = []
    monkeypatch.setattr(
        a.state,
        "hardware",
        SimpleNamespace(core=None, coils_state={}, update_coil=lambda c, *x, **k: stop.append(c) or True),
    )
    with a._session_lock:
        a._active_session.clear()
        a._active_session.update(
            is_active=True,
            session_id="kp-A",
            coil_ids=[STM_BOBIN],
            db_session_id=None,
            start_mono=_time.monotonic() - 100,
            bitis_mono=_time.monotonic() - 1,
        )

    def _devral():
        a._active_session.clear()
        a._active_session.update(
            is_active=True,
            session_id="kp-B",
            coil_ids=[STM_BOBIN],
            db_session_id=None,
            duration_minutes=30,
            start_mono=_time.monotonic(),
        )

    kilit = _KancaliKilit(a._session_lock, 2, _devral)
    monkeypatch.setattr(a, "_session_lock", kilit)
    uyku, hatalar = _tur(a._session_duration_watchdog)
    assert (uyku, hatalar) == (1, [])
    assert stop == []
    assert (a._active_session["is_active"], a._active_session["session_id"]) == (True, "kp-B")
    assert kilit.giris == 3  # A anlık görüntü · mühür (devralındı) · B anlık görüntü


def test_SIMULASYON_bozuk_seans_frekansi_donguyu_OLDURMEZ_o_tur_yayin_yok(ortam, caplog):
    """Aktif seansın frekansı sayı değil → tur "hardware sim loop error" ile biter (yığın izli), döngü uykuya varır; o turda
    bobin durumu YAYINLANMAZ."""
    a = ortam.a
    with a._session_lock:
        a._active_session.clear()
        a._active_session.update(is_active=True, session_id="kp-sim", frequency="yok", duty=25, coil_ids=[STM_BOBIN])
    caplog.set_level(logging.ERROR)
    uyku, hatalar = _tur(a._hardware_simulation_loop)
    assert (uyku, hatalar) == (1, [])
    kayit = [r for r in caplog.records if r.getMessage() == "hardware sim loop error"]
    assert kayit and kayit[0].exc_info and kayit[0].exc_info[0] is ValueError
    assert not [m for m in ortam.yayin if m.get("type") == "coil_status"]


# ── mDNS · statik önbellek ─────────────────────────────────────────────────────────────────────────────────────────────────────


def _gercek_mdns_baslatici(a):
    """conftest'in OTURUM koruması (`_lifespan_yan_etkilerini_engelle`) `api_server._start_mdns_service`'i kaydeden boş işlemle
    değiştirir (gerçek LAN ilanı olmasın). Gerçek gövde: modülün KENDİ kaynağından derlenen kod nesnesi, modülün KENDİ
    globalleriyle (yayıncı bu testte sahte → ilan yok; koruma bozulmaz)."""
    import types
    from pathlib import Path

    kod = compile(Path(a.__file__).read_text(encoding="utf-8"), a.__file__, "exec", dont_inherit=True)
    for c in kod.co_consts:
        if isinstance(c, types.CodeType) and c.co_name == "_start_mdns_service":
            return types.FunctionType(c, vars(a), "_start_mdns_service")
    raise AssertionError("api_server kaynağında _start_mdns_service yok")


def test_MDNS_gercek_API_portu_ve_cihaz_adi_ile_baslar_hatasi_yutulur(ortam, monkeypatch, caplog):
    """`PEMF_API_PORT=8131` → `start_mdns(port=8131, device_name="PEMF-Vet")`; yayıncı OSError verirse istisna sızmaz, uyarı
    "mDNS başlatılamadı: …" yazılır."""
    from servers import auto_discovery

    baslat = _gercek_mdns_baslatici(ortam.a)
    cagri: list = []
    monkeypatch.setenv("PEMF_API_PORT", "8131")
    monkeypatch.setattr(auto_discovery, "start_mdns", lambda **k: cagri.append(k))
    baslat()
    assert cagri == [{"port": 8131, "device_name": "PEMF-Vet"}]

    def _patla(**k):
        raise OSError(10049, "istenen adres bu bağlamda geçerli değil")

    monkeypatch.setattr(auto_discovery, "start_mdns", _patla)
    caplog.set_level(logging.WARNING)
    baslat()
    assert any(m.startswith("mDNS başlatılamadı: ") and "geçerli değil" in m for m in _log(caplog))


def test_STATIK_onbellek_politikasi_giris_varlik_oteki_ve_304(ortam, tmp_path):
    """`/` → `no-store, must-revalidate`; hash'li varlık → `public, max-age=31536000, immutable`; hash'siz dosya → `no-cache`;
    ETag'li koşullu istek 304 ve YİNE `no-cache` (politika 304 yolunda düşmez)."""
    from fastapi.testclient import TestClient
    from starlette.applications import Starlette
    from starlette.routing import Mount

    d = tmp_path / "dist"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text("<!doctype html><title>kp</title>", encoding="utf-8")
    (d / "assets" / "app-0123456789abcdef.js").write_text("console.log(1)", encoding="utf-8")
    (d / "logo.txt").write_text("logo", encoding="utf-8")
    uyg = Starlette(routes=[Mount("/", app=ortam.a.OnbellekPolitikaliStatik(directory=str(d), html=True))])
    with TestClient(uyg) as c:
        giris = c.get("/")
        varlik = c.get("/assets/app-0123456789abcdef.js")
        oteki = c.get("/logo.txt")
        kosullu = c.get("/logo.txt", headers={"If-None-Match": oteki.headers["etag"]})
    assert (giris.status_code, giris.headers["cache-control"]) == (200, "no-store, must-revalidate")
    assert (varlik.status_code, varlik.headers["cache-control"]) == (200, "public, max-age=31536000, immutable")
    assert (oteki.status_code, oteki.headers["cache-control"]) == (200, "no-cache")
    assert (kosullu.status_code, kosullu.headers["cache-control"]) == (304, "no-cache")
