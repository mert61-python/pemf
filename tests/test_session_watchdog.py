# Author: mertaygn, cglrgrkn
"""Kritik GÜVENLİK yolu (audit B-3.1 #1): seans süre-watchdog'u — süresi dolan seansı DONANIM
düzeyinde otomatik durdurur (firmware keep-alive tek başına auto-stop OLMAZ).

⚠️ D0Ö.10 (B-10.104): bu testler eskiden `with TestClient` lifespan'ıyla GERÇEK `session-watchdog`
daemon'ını başlatıyordu; o daemon süreç sonuna dek yaşayıp SONRAKİ testlerin seanslarını
durdurabiliyordu. Artık conftest lifespan'ın arka plan başlatıcısını engelliyor. Watchdog MANTIĞI
döngünün kendisi TEST THREAD'İNDE TEK TUR koşturularak sınanır; lifespan → başlatıcı → watchdog
bağlantısı ayrı bir kablolama testiyle (gerçek başlatıcı, Thread kaydedici) kilitlenir."""

import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


class _TurBitti(BaseException):
    """Döngüyü tek tur sonra durdurur (BaseException: döngünün `except Exception`ı yakalamaz)."""


@pytest.fixture()
def tek_tur(monkeypatch):
    """`_session_duration_watchdog`u test thread'inde SINIRLI TUR (varsayılan 1) koşturan ortam. `sleep`
    yalnız bu thread'de kesilir (başka thread'lerin uykusuna dokunulmaz) ve argümanı KAYDEDİLİR
    (`_kos.uykular`); `arada` verilirse turlar arasında (uykuda) koşar. Seans durumu test sonunda geri gelir."""
    from servers import api_server

    ana = threading.current_thread()
    gercek_uyku = time.sleep
    uykular: list = []
    durum = {"kalan": 1, "arada": None}

    def _uyku(sn):
        if threading.current_thread() is not ana:
            return gercek_uyku(sn)
        uykular.append(sn)
        durum["kalan"] -= 1
        if durum["kalan"] <= 0:
            raise _TurBitti
        if durum["arada"]:
            durum["arada"]()

    # ESP publish'i mock'la (broker yok); STM yok → yalnız watchdog mantığı sınanır.
    monkeypatch.setattr(api_server, "_mqtt_publish", lambda *a, **k: True)
    monkeypatch.setattr(time, "sleep", _uyku)  # watchdog `import time as _t` → `_t.sleep` buraya düşer
    with api_server._session_lock:
        eski = dict(api_server._active_session)

    def _kos(seans: dict, turlar: int = 1, arada=None):
        uykular.clear()
        durum.update(kalan=turlar, arada=arada)
        with api_server._session_lock:
            api_server._active_session.clear()
            api_server._active_session.update(seans)
        with pytest.raises(_TurBitti):
            api_server._session_duration_watchdog()
        with api_server._session_lock:
            return dict(api_server._active_session)

    _kos.uykular = uykular
    yield _kos
    with api_server._session_lock:
        api_server._active_session.clear()
        api_server._active_session.update(eski)


def test_watchdog_auto_stops_expired_session(tek_tur):
    # Süresi DOLMUŞ seans: start_time 2 dk önce, süre 1 dk → total 60s < geçen 120s.
    sonra = tek_tur(
        {
            "is_active": True,
            "session_id": "wd_test",
            "coil_ids": [6, 7, 8],
            "duration_minutes": 1,
            "start_time": time.time() - 120,
        }
    )
    assert not sonra.get("is_active"), "süre-watchdog süresi dolan seansı durdurmadı (GÜVENLİK regresyonu)"


def test_watchdog_keeps_active_unexpired_session(tek_tur):
    sonra = tek_tur(
        {
            "is_active": True,
            "session_id": "wd_active",
            "coil_ids": [6, 7, 8],
            "duration_minutes": 60,  # 1 saat
            "start_time": time.time(),  # yeni başladı → süre DOLMADI
        }
    )
    assert sonra.get("is_active"), "watchdog süresi dolmamış seansı erken durdurdu"


def test_KRITIK_watchdog_DONGUSU_surer_ve_PERIYODU_1_sn(tek_tur):
    """Tek-tur testleri döngünün DEVAMINA ve PERİYODUNA kördü (bağımsız inceleme, tur 3): `while True` →
    `for _ in range(1)` (watchdog ilk turdan sonra ÖLÜR; süre dolunca hiçbir seans durmaz) ya da
    `sleep(1)` → `sleep(60)` (seanslar 60 sn'ye kadar planlanandan UZUN sürer) YEŞİL kalırdı.
    1. turda süresi DOLMAMIŞ seans; uykuda süresi doldurulur; 2. tur onu durdurmalı, her uyku 1 sn."""
    from servers import api_server

    def _sureyi_doldur():
        with api_server._session_lock:
            api_server._active_session["start_time"] = time.time() - 120
            api_server._active_session["start_mono"] = time.monotonic() - 120

    sonra = tek_tur(
        {
            "is_active": True,
            "session_id": "wd_dongu",
            "coil_ids": [6, 7, 8],
            "duration_minutes": 1,
            "start_time": time.time(),
            "start_mono": time.monotonic(),
        },
        turlar=2,
        arada=_sureyi_doldur,
    )
    assert not sonra.get("is_active"), "watchdog 2. tura GEÇMEDİ ya da süresi dolan seansı durdurmadı (GÜVENLİK)"
    assert tek_tur.uykular == [1, 1], f"süre-watchdog periyodu 1 sn değil: uykular={tek_tur.uykular}"


def test_KRITIK_watchdog_MONOTONIC_isarete_bakar(tek_tur):
    """Üretim seansları `start_mono` taşır (api_server start_session/start_ai_session). Tek-tur testleri
    yalnız duvar saati yedek dalını koşuyordu; `... and _sm is None` gibi bir gerileme üretimde HİÇBİR
    seansı durdurmazdı. Duvar saati TAZE ama monotonic 2 dk önce → DURMALI."""
    sonra = tek_tur(
        {
            "is_active": True,
            "session_id": "wd_mono",
            "coil_ids": [6, 7, 8],
            "duration_minutes": 1,
            "start_time": time.time(),
            "start_mono": time.monotonic() - 120,
        }
    )
    assert not sonra.get("is_active"), "monotonic işarete göre süresi dolan seans DURMADI (GÜVENLİK regresyonu)"


def test_KARSIT_KANIT_duvar_saati_eski_monotonic_taze_DURMAZ(tek_tur):
    """Karşıt-kanıt: duvar saati ileri atlamış (NTP/DST) ama monotonic taze → seans ERKEN kesilmez."""
    sonra = tek_tur(
        {
            "is_active": True,
            "session_id": "wd_mono_taze",
            "coil_ids": [6, 7, 8],
            "duration_minutes": 1,
            "start_time": time.time() - 3600,
            "start_mono": time.monotonic(),
        }
    )
    assert sonra.get("is_active"), "duvar saati sıçraması seansı ERKEN kesti — monotonic işaret öncelikli değil"


def test_KRITIK_arka_plan_baslaticisi_SURE_WATCHDOG_unu_baslatir(monkeypatch):
    """Lifespan'ın çağırdığı GERÇEK `_start_background_threads` süre-watchdog'unu başlatıyor mu —
    gerçek daemon AÇILMADAN: Thread kaydediciyle. (Lifespan'ın bu başlatıcıyı çağırdığını
    `test_lifespan_mdns_kaydi.py` conftest kaydıyla doğrular.)"""
    from servers import api_server, efield_live

    c = sys.modules.get("conftest")
    assert c is not None and Path(c.__file__).resolve() == (Path(__file__).parent / "conftest.py").resolve()
    gercek = c._GERCEK_ARKA_PLAN_BASLATICI
    baslatilan = []

    class _KayitThread(threading.Thread):
        """GERÇEK Thread kurucusu (imza doğrulanır: konumsal/yanlış anahtar sözcük üretimde lifespan'ı
        düşürür, burada da düşer); `start` yalnız KAYDEDER — daemon AÇILMAZ."""

        def start(self):
            baslatilan.append((self.name, self._target, self.daemon))

    monkeypatch.setattr(api_server, "_threading", SimpleNamespace(Thread=_KayitThread))
    monkeypatch.setattr(api_server, "_bg_threads_started", False)
    monkeypatch.setattr(efield_live, "start_loop", lambda **k: baslatilan.append(("efield-live", None, True)))
    monkeypatch.delenv("PEMF_SIMULATE", raising=False)
    once = set(threading.enumerate())
    gercek()
    yeni = sorted(t.name for t in set(threading.enumerate()) - once if t.is_alive())
    assert not yeni, f"kablolama testi GERÇEK thread başlattı (sızıntı; başka bir Thread yolu eklenmiş): {yeni}"
    assert ("session-watchdog", api_server._session_duration_watchdog, True) in baslatilan, (
        f"arka plan başlatıcısı süre-watchdog'unu BAŞLATMIYOR (GÜVENLİK regresyonu): {baslatilan}"
    )


def test_watchdog_uses_monotonic_not_wallclock(monkeypatch):
    """DENETIM P2 regresyonu: süre-watchdog DUVAR SAATİ farkıyla çalışmamalı.

    Hata: `_t.time() - start_time`. NTP düzeltmesi / DST / elle saat değişimi İLERİ giderse seans
    ERKEN kesilir, GERİ giderse planlanandan UZUN sürer (maruziyet artar). start_time istemciye
    gösterim için gittiğinden epoch olarak korundu; güvenlik kararı ayrı monotonic işaretle verilir.
    """
    import inspect

    from servers import api_server as api

    src = inspect.getsource(api._session_duration_watchdog)
    assert "_planlanan_sure_doldu(sess)" in src, "watchdog süre ölçütünü TEK yardımcıdan almalı (Y306)"
    # Y306: ölçüt `_planlanan_sure_doldu`da (durdurma ucunun durum ayrımı da onu kullanır)
    yardimci = inspect.getsource(api._planlanan_sure_doldu)
    assert "start_mono" in yardimci, "watchdog monotonic işareti kullanmalı"
    assert "_t.monotonic()" in yardimci, "geçen süre monotonic saatten hesaplanmalı"

    # Her iki seans kurucusu da işareti dikmeli (yoksa watchdog eski yola düşer)
    assert '"start_mono"' in inspect.getsource(api.start_session)
    assert '"start_mono"' in inspect.getsource(api.start_ai_session)
