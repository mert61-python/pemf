# -*- coding: utf-8 -*-
"""KP-1 · apps/backend/backend_service.py · sözleşmeler: güvenli durdurma (STM / ESP adımı düşerse diğeri sürer),
açılış mutabakatı (aktif seans → atlanır; yayın hatası düşürmez), erken kapanış durdurması, sinyal işleyicileri (kapanış
bayrağı + TEK erken STOP + uvicorn işleyicisinin sarılması), `_shutdown` (her adım best-effort, sıra), `main()` (bozuk
ortam portu → 8000 + uyarı, açılış sırası, çökme → 1, her yolda `_shutdown`), doğrudan çalıştırma alt komutu.

Sahteler EN ALT katta: sinyal kaydı (modülün `signal` adı), MQTT yayını (`api_server._mqtt_publish` kaydedici), seri
gönderim (HC sahtesi), süreç (`file_acl.subprocess`), `time.sleep(3.0)` mutabakat beklemesi. `main()` için ağır alt
sistemler (HeadlessCore, API bağlantısı, uvicorn sunucusu, açılış yardımcıları) gerçek imzalarına uyan kaydedicilerdir:
gerçekleri seri port / MQTT / dinleyici port / ağ açar (YASAK).
"""

from __future__ import annotations

import logging
import os
import runpy
import subprocess
import sys
import threading
import time
import types

import backend_service as bs
import pytest

# ── ortak aparat ──────────────────────────────────────────────────────────────────────────────────────────────────────


class _Toplayici(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.kayitlar: list[logging.LogRecord] = []

    def emit(self, record):
        self.kayitlar.append(record)

    def metinler(self, duzey: int | None = None) -> list[str]:
        return [r.getMessage() for r in self.kayitlar if duzey is None or r.levelno == duzey]


_SAYAC = {"n": 0}


def _gunlukcu(ad: str):
    _SAYAC["n"] += 1
    lg = logging.getLogger(f"kp_bs_kapanis.{ad}.{_SAYAC['n']}")
    lg.handlers[:] = []
    h = _Toplayici()
    lg.addHandler(h)
    lg.setLevel(logging.DEBUG)
    lg.propagate = False
    return lg, h


def _env_gecici(monkeypatch, ad: str) -> None:
    monkeypatch.setenv(ad, "kp-gecici")
    monkeypatch.delenv(ad)


class _SatirIciThread(threading.Thread):
    def start(self):
        self.run()


@pytest.fixture
def kayitli_thread(monkeypatch):
    """Gerçek iş parçacıkları (gerçek start/join) — oluşturulan her biri kaydedilir; test sonunda hepsi join edilir."""
    olusan: list[threading.Thread] = []

    class _KayitliThread(threading.Thread):
        def start(self):
            olusan.append(self)
            super().start()

    monkeypatch.setattr(threading, "Thread", _KayitliThread)
    yield olusan
    for t in olusan:
        t.join(timeout=5)
    assert not any(t.is_alive() for t in olusan), "aparat: iş parçacığı test sonunda yaşıyor"


class _HC:
    def __init__(self, sira: list, stop_patla: bool = False):
        self.sira = sira
        self.stop_patla = stop_patla

    def stop_all_coils(self):
        self.sira.append("stop_all")
        if self.stop_patla:
            raise OSError("seri port yazılamadı")
        return True

    def stop(self):
        self.sira.append("hw_stop")


def _sahte_api(sira: list, **ek):
    yayin: list = []

    def _yayin(konu, yuk):
        yayin.append((konu, yuk))
        return True

    api = types.SimpleNamespace(
        state=types.SimpleNamespace(hardware=_HC(sira)),
        _mqtt_publish=_yayin,
        _session_lock=threading.Lock(),
        _active_session={"is_active": False},
        yayin=yayin,
    )
    api.__dict__.update(ek)
    return api


# ── güvenli durdurma ──────────────────────────────────────────────────────────────────────────────────────────────────


def test_STM_STOP_PATLARSA_ESP_STOPlari_yine_yayinlanir(kayitli_thread, caplog):
    """`stop_all_coils` istisna atarsa → 'STM safe stop failed' ERROR; ESP bobinlerinin İKİ konusuna da acil STOP yine
    yayınlanır (komut, kaynak, benzersiz kimlik)."""
    from servers.live_state import ESP_COIL_IDS

    sira: list = []
    api = _sahte_api(sira)
    api.state.hardware = _HC(sira, stop_patla=True)
    with caplog.at_level(logging.ERROR, logger="backend_service"):
        bs._safe_stop_outputs(api)
    assert any(r.getMessage() == "STM safe stop failed" and r.exc_info for r in caplog.records)
    assert ESP_COIL_IDS, "aparat: ESP bobin kümesi boş — aşağıdaki döngüler boşa düşerdi"
    assert api.yayin, "STM STOP patlayınca ESP acil STOP yayını hiç gitmedi"
    for c in sorted(ESP_COIL_IDS):
        konular = [k for k, _ in api.yayin if k in (f"pemf/coil/{c}/control", f"pemf/esp32_{c}/command")]
        assert sorted(konular) == sorted([f"pemf/coil/{c}/control", f"pemf/esp32_{c}/command"])
    for _, yuk in api.yayin:
        assert yuk["command"] == "stop" and yuk["emergency"] is True and yuk["source"] == "backend_service_shutdown"
        assert yuk["command_id"].startswith("service_stop_")


def test_ESP_is_parcacigi_ACILAMAZSA_MQTT_hatasi_loglanir_kapanis_surer(monkeypatch, caplog):
    """ESP STOP iş parçacığı başlatılamazsa (kaynak tükenmesi) → 'MQTT safe stop failed' ERROR + iz; istisna kaçmaz,
    STM STOP'u ondan ÖNCE verilmiştir."""

    class _AcilamayanThread(threading.Thread):
        def start(self):
            raise RuntimeError("can't start new thread")

    monkeypatch.setattr(threading, "Thread", _AcilamayanThread)
    sira: list = []
    api = _sahte_api(sira)
    with caplog.at_level(logging.ERROR, logger="backend_service"):
        bs._safe_stop_outputs(api)
    assert sira == ["stop_all"] and api.yayin == []
    assert any(r.getMessage() == "MQTT safe stop failed" and r.exc_info for r in caplog.records)


# ── açılış mutabakatı ─────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mutabakat(monkeypatch):
    gercek_uyku = time.sleep
    uyku: list = []
    test_is_parcacigi = threading.current_thread()

    def _uyku(s):
        if threading.current_thread() is not test_is_parcacigi:
            return gercek_uyku(s)  # başka (arka plan) iş parçacıklarının uykusu kaydedilmez, aynen uyur
        uyku.append(s)
        if s != 3.0:
            gercek_uyku(s)

    monkeypatch.setattr(time, "sleep", _uyku)
    monkeypatch.setattr(threading, "Thread", _SatirIciThread)
    return uyku


def test_mutabakat_AKTIF_seans_varken_ATLANIR_STOP_gitmez(mutabakat):
    """3 sn bekleme sonrası aktif seans varsa → 'Başlangıç mutabakatı atlandı' INFO; STM STOP ve MQTT STOP YOK."""
    sira: list = []
    api = _sahte_api(sira, _active_session={"is_active": True, "coil_ids": [1]})
    lg, h = _gunlukcu("mut_aktif")
    bs._start_startup_reconcile(api, lg)
    assert mutabakat == [3.0]
    assert sira == [] and api.yayin == []
    assert h.metinler(logging.INFO) == ["Başlangıç mutabakatı atlandı: bu arada aktif seans başlatılmış."]


def test_mutabakat_YAYIN_PATLARSA_uyari_STM_STOP_once_verilmis(mutabakat):
    """MQTT yayını istisna atarsa → 'Başlangıç mutabakatı başarısız' WARNING + iz; STM STOP ondan önce verilmiştir,
    'tüm bobinlere STOP' INFO'su yazılmaz."""
    sira: list = []

    def _patla(konu, yuk):
        raise ConnectionRefusedError("broker yok")

    api = _sahte_api(sira, _mqtt_publish=_patla)
    lg, h = _gunlukcu("mut_hata")
    bs._start_startup_reconcile(api, lg)
    assert sira == ["stop_all"]
    uyari = [r for r in h.kayitlar if r.levelno == logging.WARNING]
    assert (
        len(uyari) == 1 and uyari[0].getMessage() == "Başlangıç mutabakatı başarısız (non-fatal)." and uyari[0].exc_info
    )
    assert not h.metinler(logging.INFO)


# ── erken kapanış durdurması ──────────────────────────────────────────────────────────────────────────────────────────


def test_erken_durdurma_MANDAL_kurulamazsa_STOP_yine_verilir(monkeypatch, kayitli_thread):
    """Kapanış mandalı kurulamazsa → 'Kapanis (erken) mandali kurulamadi (durdurma SURUYOR)' ERROR ve STM STOP yine verilir."""
    from utils import estop_mandali

    def _patla():
        raise RuntimeError("mandal kilidi bozuk")

    monkeypatch.setattr(estop_mandali, "kapanis_kur", _patla)
    sira: list = []
    lg, h = _gunlukcu("erken_mandal")
    bs._kapanis_erken_durdurma(_sahte_api(sira), lg)
    assert h.metinler(logging.ERROR) == ["Kapanis (erken) mandali kurulamadi (durdurma SURUYOR)"]
    assert sira == ["stop_all"]


def test_erken_durdurma_STOP_adimi_PATLARSA_loglanir_kacmaz(monkeypatch):
    """Donanım STOP adımı istisna atarsa → 'Kapanis (erken) donanim STOP'u basarisiz' ERROR; kapanış mandalı KURULUR."""
    from utils import estop_mandali

    def _patla(api):
        raise RuntimeError("STOP yolu çöktü")

    monkeypatch.setattr(bs, "_safe_stop_outputs", _patla)
    lg, h = _gunlukcu("erken_stop")
    bs._kapanis_erken_durdurma(_sahte_api([]), lg)
    assert h.metinler(logging.ERROR) == ["Kapanis (erken) donanim STOP'u basarisiz"]
    assert estop_mandali.baslatma_engeli() == estop_mandali.kapanis_mesaji()


# ── sinyal işleyicileri ───────────────────────────────────────────────────────────────────────────────────────────────


class _SinyalKaydi:
    SIGINT, SIGTERM, SIGBREAK = 2, 15, 21

    def __init__(self, patlayan=()):
        self.kayit: dict = {}
        self.patlayan = set(patlayan)

    def signal(self, sig, isleyici):
        if sig in self.patlayan:
            raise ValueError("signal only works in main thread of the main interpreter")
        self.kayit[sig] = isleyici


class _Sunucu:
    def __init__(self):
        self.should_exit = False
        self.ozgun: list = []

    def handle_exit(self, sig, frame):
        self.ozgun.append(sig)


def test_sinyal_KAPANIS_bayragi_ve_TEK_erken_STOP(monkeypatch, kayitli_thread):
    """SIGINT/SIGTERM/SIGBREAK kaydedilir; sinyal → server.should_exit=True ve AYRI iş parçacığında TEK erken durdurma
    (kapanış mandalı + STM STOP); ikinci sinyal yeni durdurma başlatmaz; sarılmış uvicorn işleyicisi özgünü de çağırır."""
    from utils import estop_mandali

    sk = _SinyalKaydi()
    monkeypatch.setattr(bs, "signal", sk)
    sunucu = _Sunucu()
    sira: list = []
    lg, h = _gunlukcu("sinyal")
    bs._install_signal_handlers(sunucu, lg, _sahte_api(sira))
    assert set(sk.kayit) == {2, 15, 21}
    sk.kayit[15](15, None)
    assert sunucu.should_exit is True
    erken = [t for t in kayitli_thread if t.name == "kapanis-erken-stop"]
    assert len(erken) == 1 and erken[0].daemon is True
    erken[0].join(timeout=5)
    assert sira == ["stop_all"]
    assert estop_mandali.baslatma_engeli() == estop_mandali.kapanis_mesaji()
    assert "Shutdown requested by signal 15" in h.metinler(logging.INFO)
    sk.kayit[2](2, None)
    sunucu.handle_exit(2, None)
    assert len([t for t in kayitli_thread if t.name == "kapanis-erken-stop"]) == 1
    assert sunucu.ozgun == [2]


def test_sinyal_API_YOKSA_erken_STOP_yok_yalniz_bayrak(monkeypatch, kayitli_thread):
    """api_server verilmezse → sinyal yalnız should_exit'i kurar; erken durdurma iş parçacığı AÇILMAZ."""
    sk = _SinyalKaydi()
    monkeypatch.setattr(bs, "signal", sk)
    sunucu = _Sunucu()
    lg, h = _gunlukcu("sinyal_apisiz")
    bs._install_signal_handlers(sunucu, lg, None)
    sk.kayit[2]()
    assert sunucu.should_exit is True and kayitli_thread == []
    assert "Shutdown requested" in h.metinler(logging.INFO)


def test_sinyal_erken_STOP_is_parcacigi_ACILAMAZSA_hata_bayrak_yine_kurulur(monkeypatch):
    """Erken durdurma iş parçacığı açılamazsa → 'STOP _shutdown'a kaldi' ERROR; should_exit yine True."""

    class _AcilamayanThread(threading.Thread):
        def start(self):
            raise RuntimeError("can't start new thread")

    monkeypatch.setattr(threading, "Thread", _AcilamayanThread)
    sk = _SinyalKaydi()
    monkeypatch.setattr(bs, "signal", sk)
    sunucu = _Sunucu()
    lg, h = _gunlukcu("sinyal_threadsiz")
    bs._install_signal_handlers(sunucu, lg, _sahte_api([]))
    sk.kayit[15](15, None)
    assert sunucu.should_exit is True
    hatalar = h.metinler(logging.ERROR)
    assert hatalar == ["Kapanis (erken) STOP is parcacigi acilamadi — STOP _shutdown'a kaldi"]


def test_sinyal_uvicorn_isleyicisi_SARILAMAZSA_uyari_sinyaller_yine_kurulur(monkeypatch):
    """`handle_exit` salt okunursa → 'uvicorn kapanis isleyicisi sarilamadi' WARNING; sinyal işleyicileri yine kurulur."""

    class _SaltOkuSunucu:
        should_exit = False

        @property
        def handle_exit(self):
            return lambda sig, frame: None

    sk = _SinyalKaydi()
    monkeypatch.setattr(bs, "signal", sk)
    lg, h = _gunlukcu("sinyal_saltoku")
    bs._install_signal_handlers(_SaltOkuSunucu(), lg, None)
    assert any("sarilamadi" in m for m in h.metinler(logging.WARNING))
    assert set(sk.kayit) == {2, 15, 21}


def test_sinyal_KAYDI_PATLAYAN_sinyal_atlanir_digerleri_kurulur(monkeypatch):
    """`signal.signal` bir sinyalde istisna atarsa → kurulum düşmez; öbür sinyaller kurulur."""
    sk = _SinyalKaydi(patlayan={21})
    monkeypatch.setattr(bs, "signal", sk)
    bs._install_signal_handlers(_Sunucu(), _gunlukcu("sinyal_patla")[0], None)
    assert set(sk.kayit) == {2, 15}


# ── _shutdown ─────────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def kapanis(monkeypatch):
    """Kapanış alt sistemleri: bulut / tünel / bakım / zeroconf kaydedicileri (gerçekleri ağ ve iş parçacığı kapatır)."""
    import servers.sync_worker as sw
    import servers.tunnel_manager as tm
    import services.headless_db_maintenance as hm
    import utils.zeroconf_singleton as zs

    sira: list = []
    ns = types.SimpleNamespace(sira=sira, patla=set())

    def _adim(ad):
        def _f(*a, **k):
            sira.append(ad)
            if ad in ns.patla:
                raise RuntimeError(f"{ad} patladı")

        return _f

    bulut = types.SimpleNamespace(stop=_adim("bulut_stop"))
    monkeypatch.setattr(sw, "get_cloud_sync", lambda: bulut)
    monkeypatch.setattr(tm, "stop_tunnel", _adim("tunel_stop"))
    monkeypatch.setattr(hm, "stop_headless_db_maintenance", _adim("bakim_stop"))
    monkeypatch.setattr(zs, "close_shared_zeroconf", _adim("zeroconf"))
    ns.cekirdek = types.SimpleNamespace(quit=_adim("quit"))
    ns.veriyolu = types.SimpleNamespace(shutdown=_adim("bus_shutdown"))
    ns.adim = _adim
    return ns


def test_shutdown_SIRA_mandal_pasif_STOP_kayit_sonra_alt_sistemler(kapanis, kayitli_thread):
    """Normal kapanış → kapanış mandalı kurulur; sıra: seans pasife → STM STOP → seans KAYDI (pasife alınan anlıkla) →
    HC durdur → bulut → tünel → bakım → çekirdek → zeroconf → olay veriyolu; 'stopped' INFO."""
    from utils import estop_mandali

    seans = {"session_id": "kp-s1"}
    kayit_anlik: list = []

    def _pasife_al():
        kapanis.sira.append("pasife_al")
        return seans

    def _kaydi_kapat(anlik):
        kapanis.sira.append("kayit_kapat")
        kayit_anlik.append(anlik)

    api = _sahte_api(kapanis.sira, kapanis_seansi_pasife_al=_pasife_al, kapanis_seans_kaydini_kapat=_kaydi_kapat)
    lg, h = _gunlukcu("kapanis_sira")
    bs._shutdown(lg, api, kapanis.cekirdek, kapanis.veriyolu)
    assert kapanis.sira == [
        "pasife_al",
        "stop_all",
        "kayit_kapat",
        "hw_stop",
        "bulut_stop",
        "tunel_stop",
        "bakim_stop",
        "quit",
        "zeroconf",
        "bus_shutdown",
    ]
    assert kayit_anlik == [seans]
    assert estop_mandali.baslatma_engeli() == estop_mandali.kapanis_mesaji()
    assert h.metinler(logging.INFO) == ["PEMF backend service stopping", "PEMF backend service stopped"]
    assert not h.metinler(logging.ERROR)


def test_shutdown_HER_adim_PATLASA_da_hepsi_denenir_ve_loglanir(kapanis, monkeypatch):
    """Mandal, STOP, seans kaydı, HC, bulut, tünel, bakım, çekirdek, zeroconf ve veriyolu adımlarının HER biri istisna
    atsa → hepsi denenir, her biri kendi ERROR iletisiyle loglanır, 'stopped' yine yazılır."""
    from utils import estop_mandali

    def _mandal_patla():
        kapanis.sira.append("mandal")
        raise RuntimeError("mandal")

    def _stop_patla(api):
        kapanis.sira.append("safe_stop")
        raise RuntimeError("stop")

    monkeypatch.setattr(estop_mandali, "kapanis_kur", _mandal_patla)
    monkeypatch.setattr(bs, "_safe_stop_outputs", _stop_patla)
    kapanis.patla.update(
        {"kayit_kapat", "hw_stop", "bulut_stop", "tunel_stop", "bakim_stop", "quit", "zeroconf", "bus_shutdown"}
    )
    hc = types.SimpleNamespace(stop=kapanis.adim("hw_stop"))
    api = types.SimpleNamespace(
        state=types.SimpleNamespace(hardware=hc),
        kapanis_seansi_pasife_al=lambda: {"session_id": "kp-s2"},
        kapanis_seans_kaydini_kapat=kapanis.adim("kayit_kapat"),
    )
    lg, h = _gunlukcu("kapanis_hepsi")
    bs._shutdown(lg, api, kapanis.cekirdek, kapanis.veriyolu)
    assert kapanis.sira == [
        "mandal",
        "safe_stop",
        "kayit_kapat",
        "hw_stop",
        "bulut_stop",
        "tunel_stop",
        "bakim_stop",
        "quit",
        "zeroconf",
        "bus_shutdown",
    ]
    assert h.metinler(logging.ERROR) == [
        "Kapanis mandali kurulamadi (durdurma SURUYOR)",
        "Safe output shutdown failed",
        "Kapanista seans kaydi kapatilamadi",
        "HardwareController shutdown failed",
        "Cloud sync shutdown failed",
        "Tunnel shutdown failed",
        "DB maintenance shutdown failed",
        "HeadlessCore shutdown failed",
        "Zeroconf shutdown failed",
        "EventBus shutdown failed",
    ]
    assert h.metinler(logging.INFO)[-1] == "PEMF backend service stopped"


def test_shutdown_seans_PASIFE_ALINAMAZSA_kayit_kapatilmaz_STOP_yine_verilir(kapanis, kayitli_thread):
    """Seans pasife alma istisna atarsa → ERROR; seans kaydı kapatma ÇAĞRILMAZ (anlık yok), STM STOP yine verilir."""

    def _patla():
        raise RuntimeError("seans kilidi")

    api = _sahte_api(
        kapanis.sira, kapanis_seansi_pasife_al=_patla, kapanis_seans_kaydini_kapat=kapanis.adim("kayit_kapat")
    )
    lg, h = _gunlukcu("kapanis_pasif")
    bs._shutdown(lg, api, kapanis.cekirdek, kapanis.veriyolu)
    assert "kayit_kapat" not in kapanis.sira and kapanis.sira[0] == "stop_all"
    assert h.metinler(logging.ERROR) == ["Kapanista aktif seans pasife alinamadi (durdurma SURUYOR)"]


# ── main() ────────────────────────────────────────────────────────────────────────────────────────────────────────────


class _SahteCekirdek:
    olusan: list = []

    def __init__(
        self, app_data_dir, api_port=8000, start_headless_services=True, ensure_mosquitto=True, event_bus=None
    ):
        self.app_data_dir = app_data_dir
        self.kw = {
            "api_port": api_port,
            "start_headless_services": start_headless_services,
            "ensure_mosquitto": ensure_mosquitto,
            "event_bus": event_bus,
        }
        self.stm_is_connected = False
        self.cikti = 0
        _SahteCekirdek.olusan.append(self)

    def quit(self):
        self.cikti += 1


class _SahteSunucu:
    def __init__(self, app, args, hata=None):
        self.app, self.args, self.hata = app, args, hata
        self.should_exit = False
        self.kosuldu = 0

    def handle_exit(self, sig, frame):
        pass

    def run(self):
        self.kosuldu += 1
        if self.hata is not None:
            raise self.hata


@pytest.fixture
def ana(monkeypatch, tmp_path, kapanis):
    """main() aparatı: kök günlükçü değişmez (basicConfig kaydedilir), kancalar / ortam geri gelir, alt sistemler kayıtlı."""
    import utils.agir_import as ai
    import utils.file_acl as fa

    for ad in ("PEMF_API_HOST", "PEMF_API_PORT", "PEMF_HEADLESS", "PEMF_LOG_JSON", "PEMF_SENTRY_DSN"):
        _env_gecici(monkeypatch, ad)
    monkeypatch.setenv("PEMF_LOG_DIR", str(tmp_path / "lg"))
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    yakalanan: dict = {}
    monkeypatch.setattr(logging, "basicConfig", lambda **k: yakalanan.update(k))
    monkeypatch.setattr(
        fa,
        "subprocess",
        types.SimpleNamespace(
            run=lambda args, **k: subprocess.CompletedProcess(args, 0, b"", b""),
            CREATE_NO_WINDOW=0x08000000,
            CalledProcessError=subprocess.CalledProcessError,
        ),
    )
    _SahteCekirdek.olusan = []
    monkeypatch.setattr(bs, "HeadlessCore", _SahteCekirdek)
    veriyolu = types.SimpleNamespace(shutdown=kapanis.adim("bus_shutdown"), subscribe=lambda *a, **k: True)
    monkeypatch.setattr(bs, "get_event_bus", lambda: veriyolu)
    acilis: list = []
    ns = types.SimpleNamespace(acilis=acilis, veriyolu=veriyolu, sunucular=[], hata=None, kapanis=kapanis)
    api = _sahte_api(kapanis.sira, app=object())
    ns.api = api

    def _bagla(core):
        acilis.append(("bagla", core))
        return api

    monkeypatch.setattr(bs, "_wire_api_server", _bagla)
    monkeypatch.setattr(bs, "_start_startup_reconcile", lambda a, lg: acilis.append(("mutabakat", a)))
    monkeypatch.setattr(bs, "_start_cloud_sync", lambda lg: acilis.append("bulut"))
    monkeypatch.setattr(bs, "_start_db_maintenance", lambda core, lg: acilis.append("bakim"))
    monkeypatch.setattr(bs, "_maybe_start_tunnel", lambda port, lg: acilis.append(("tunel", port)))
    monkeypatch.setattr(bs, "_start_update_checker_safe", lambda lg: acilis.append("guncelleme"))
    monkeypatch.setattr(bs, "_donanim_guncellemesi_kur", lambda core, lg, bus=None: acilis.append(("donanim", bus)))
    monkeypatch.setattr(bs, "_start_hotspot_safe", lambda lg: acilis.append("hotspot"))
    monkeypatch.setattr(ai, "torch_isit", lambda *a, **k: acilis.append("torch"))
    monkeypatch.setattr(bs, "_start_ai_warmup_safe", lambda lg: acilis.append("isitma"))

    def _sunucu_kur(app, args):
        s = _SahteSunucu(app, args, ns.hata)
        ns.sunucular.append(s)
        return s

    monkeypatch.setattr(bs, "_build_server", _sunucu_kur)
    ns.sinyal = _SinyalKaydi()
    monkeypatch.setattr(bs, "signal", ns.sinyal)
    yield ns
    for h in yakalanan.get("handlers") or []:
        h.close()


def _adlar(acilis):
    return [a[0] if isinstance(a, tuple) else a for a in acilis]


def test_main_BOZUK_ortam_portu_8000_ve_UYARI_acilis_SIRASI_kapanis(ana, monkeypatch, caplog):
    """`--port` yok + PEMF_API_PORT='80O0' → port 8000 (dinlenen + yayınlanan), adıyla uyarı; çekirdek ortam bayraklarıyla
    kurulur; açılış sırası (mutabakat → bulut → bakım → tünel → güncelleme → donanım → hotspot → torch → ısıtma); sinyaller
    kurulur; sunucu koşar → 0 ve `_shutdown` (çekirdek quit + veriyolu kapanışı) koşar."""
    monkeypatch.setenv("PEMF_API_PORT", "80O0")
    with caplog.at_level(logging.INFO, logger="backend_service"):
        rc = bs.main([])
    assert rc == 0
    s = ana.sunucular[0]
    assert s.kosuldu == 1 and s.app is ana.api.app and s.args.port == 8000 and s.args.host == "0.0.0.0"
    assert os.environ["PEMF_API_PORT"] == "8000" and os.environ["PEMF_API_HOST"] == "0.0.0.0"
    assert os.environ["PEMF_HEADLESS"] == "1"
    uyari = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING and r.name == "backend_service"]
    assert any("PEMF_API_PORT='80O0' gecersiz" in m and "varsayilan 8000" in m for m in uyari)
    cekirdek = _SahteCekirdek.olusan[0]
    assert cekirdek.kw == {
        "api_port": 8000,
        "start_headless_services": True,
        "ensure_mosquitto": True,
        "event_bus": ana.veriyolu,
    }
    assert _adlar(ana.acilis) == [
        "bagla",
        "mutabakat",
        "bulut",
        "bakim",
        "tunel",
        "guncelleme",
        "donanim",
        "hotspot",
        "torch",
        "isitma",
    ]
    assert ("tunel", 8000) in ana.acilis and ("donanim", ana.veriyolu) in ana.acilis
    assert set(ana.sinyal.kayit) == {2, 15, 21}
    assert cekirdek.cikti == 1 and "bus_shutdown" in ana.kapanis.sira
    assert any(r.getMessage() == "PEMF backend service starting: host=0.0.0.0 port=8000" for r in caplog.records)


def test_main_ACIK_port_ve_bayraklar_ORTAMI_ezer_uyari_YOK(ana, monkeypatch, caplog):
    """`--port 8123 --host 127.0.0.1 --no-headless-services --no-mosquitto-ensure` → bozuk ortam portu OKUNMAZ (uyarı yok);
    dinlenen/yayınlanan 8123 + 127.0.0.1; çekirdek destek servissiz ve broker'ı başlatmadan; tünel 8123 ile."""
    monkeypatch.setenv("PEMF_API_PORT", "sekizbin")
    monkeypatch.setenv("PEMF_HEADLESS", "0")
    with caplog.at_level(logging.INFO, logger="backend_service"):
        rc = bs.main(["--port", "8123", "--host", "127.0.0.1", "--no-headless-services", "--no-mosquitto-ensure"])
    assert rc == 0
    assert ana.sunucular[0].args.port == 8123 and os.environ["PEMF_API_PORT"] == "8123"
    assert os.environ["PEMF_API_HOST"] == "127.0.0.1" and os.environ["PEMF_HEADLESS"] == "0"
    kw = _SahteCekirdek.olusan[0].kw
    assert (kw["api_port"], kw["start_headless_services"], kw["ensure_mosquitto"]) == (8123, False, False)
    assert ("tunel", 8123) in ana.acilis
    assert not any("gecersiz" in r.getMessage() for r in caplog.records)


def test_main_sunucu_COKERSE_1_doner_kapanis_YINE_kosar(ana, caplog):
    """`server.run()` istisna atarsa → main 1 döner, 'Backend service crashed' ERROR + iz; `_shutdown` yine koşar."""
    ana.hata = RuntimeError("olay döngüsü çöktü")
    with caplog.at_level(logging.INFO, logger="backend_service"):
        rc = bs.main(["--port", "8124"])
    assert rc == 1
    assert any(r.getMessage() == "Backend service crashed" and r.exc_info for r in caplog.records)
    assert _SahteCekirdek.olusan[0].cikti == 1
    assert any(r.getMessage() == "PEMF backend service stopped" for r in caplog.records)


def test_main_TELEMETRI_kurulamazsa_DEBUG_acilis_surer(ana, monkeypatch, caplog):
    """Uzaktan hata izleme kurulumu istisna atarsa → 'Telemetri init atlandı' DEBUG; açılış sürer, sunucu koşar, 0 döner."""
    import utils.telemetry as tel

    def _patla():
        raise ImportError("sentry_sdk bozuk")

    monkeypatch.setattr(tel, "init_telemetry", _patla)
    with caplog.at_level(logging.DEBUG, logger="backend_service"):
        rc = bs.main(["--port", "8125"])
    assert rc == 0 and ana.sunucular[0].kosuldu == 1
    assert any(
        r.levelno == logging.DEBUG and r.getMessage() == "Telemetri init atlandı" and r.exc_info for r in caplog.records
    )


def test_main_SINYAL_isleyicileri_API_ile_BAGLANIR_serve_SURERKEN_SIGTERM_erken_STOP_run_DONMEDEN(
    ana, kayitli_thread, monkeypatch
):
    """G-1.1 (Ö.4-Y8) · main() kablolaması: `server.run()` sürerken SIGTERM gelir (uvicorn `capture_signals` sinyali sunucunun
    SARILMIŞ `handle_exit`'ine verir) → `run()` DÖNMEDEN, AYRI "kapanis-erken-stop" iş parçacığında kapanış mandalı kurulur, STM STOP
    verilir ve ESP bobinlerine acil STOP yayınlanır; uvicorn'un özgün işleyicisi de çağrılır (kapanış bayrağı). Serve dışı yoldan
    (signal modülü) ikinci istek yeni erken STOP açmaz. `run()` dönünce `_shutdown` STOP'u yineler (idempotent) ve alt sistemleri
    kapatır. main() işleyicilere api_server BAĞLAMAZSA serve sürerken erken STOP hiç başlamaz (bobinler `run()` dönene dek sürülür)."""
    from servers.live_state import ESP_COIL_IDS
    from utils import estop_mandali

    anlik: dict = {}

    class _SinyalAlanSunucu(_SahteSunucu):
        def __init__(self, app, args):
            super().__init__(app, args)
            self.ozgun: list = []

        def handle_exit(self, sig, frame):  # uvicorn'un özgün işleyicisi: kapanış bayrağı
            self.ozgun.append(sig)
            self.should_exit = True

        def run(self):
            # ⚠️ burada assert YOK: main() `run()` istisnasını yutar (→ 1); ölçüm anlık görüntüyle testte yapılır
            self.kosuldu += 1
            anlik["engel_once"] = estop_mandali.baslatma_engeli()
            anlik["sira_once"] = list(ana.kapanis.sira)
            self.handle_exit(15, None)  # serve sürerken: uvicorn capture_signals → örnek özniteliği (sarılmış işleyici)
            erken = [t for t in kayitli_thread if t.name == "kapanis-erken-stop"]
            anlik["erken"] = [(t.name, t.daemon) for t in erken]
            for t in erken:
                t.join(timeout=5)
            anlik["sira"] = list(ana.kapanis.sira)
            anlik["yayin"] = list(ana.api.yayin)
            anlik["engel"] = estop_mandali.baslatma_engeli()
            ana.sinyal.kayit[2](2, None)  # serve dışı yol (signal modülü işleyicisi): ikinci kapanış isteği
            anlik["erken_2"] = len([t for t in kayitli_thread if t.name == "kapanis-erken-stop"])

    def _sunucu_kur(app, args):
        s = _SinyalAlanSunucu(app, args)
        ana.sunucular.append(s)
        return s

    monkeypatch.setattr(bs, "_build_server", _sunucu_kur)
    assert bs.main(["--port", "8127"]) == 0
    s = ana.sunucular[0]
    assert s.kosuldu == 1 and anlik["engel_once"] == "" and anlik["sira_once"] == []
    assert anlik["erken"] == [("kapanis-erken-stop", True)], (
        "main() sinyal işleyicilerine api_server bağlamadı → erken STOP yok"
    )
    assert anlik["sira"] == ["stop_all"], "STM STOP `server.run()` dönmeden verilmedi"
    assert anlik["engel"] == estop_mandali.kapanis_mesaji(), "kapanış mandalı `server.run()` dönmeden kurulmadı"
    assert ESP_COIL_IDS, "aparat: ESP bobin kümesi boş — ESP iddiası boşa düşerdi"
    beklenen_konular = [f"pemf/coil/{c}/control" for c in ESP_COIL_IDS] + [
        f"pemf/esp32_{c}/command" for c in ESP_COIL_IDS
    ]
    assert sorted(k for k, _ in anlik["yayin"]) == sorted(beklenen_konular)
    assert all(y["command"] == "stop" and y["emergency"] is True for _, y in anlik["yayin"])
    assert s.ozgun == [15] and s.should_exit is True
    assert anlik["erken_2"] == 1, "ikinci kapanış isteği yeni erken STOP açtı"
    assert ana.kapanis.sira == [
        "stop_all",
        "stop_all",
        "hw_stop",
        "bulut_stop",
        "tunel_stop",
        "bakim_stop",
        "zeroconf",
        "bus_shutdown",
    ]


def test_dogrudan_calistirma_KURTARMA_alt_komutu_sunucu_ACMADAN_cikis(monkeypatch, capsys):
    """`python backend_service.py --kurtarma` (zarfsız) → sunucu kurulmadan kurtarma aracı '--zarf gerekli' ile çıkış 2."""
    import utils.encrypted_import as ei
    import utils.runtime_guards as rg

    monkeypatch.setattr(ei, "install", lambda: False)
    monkeypatch.setattr(rg, "pip_kurulumunu_yasakla", lambda: None)
    monkeypatch.setattr(rg, "dis_ag_cagrilarini_kapat", lambda: None)
    import uvicorn

    monkeypatch.setattr(uvicorn.Server, "run", lambda self, *a, **k: pytest.fail("sunucu açılmamalıydı"))
    monkeypatch.setattr(sys, "argv", [bs.__file__, "--kurtarma"])
    with pytest.raises(SystemExit) as cikis:
        runpy.run_path(bs.__file__, run_name="__main__")
    assert cikis.value.code == 2
    assert "--zarf gerekli" in capsys.readouterr().err
