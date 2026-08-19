# Author: mertaygn, cglrgrkn
"""PLAN A (HG-5/HG-6) — sahip kararı 2026-08-19: deadman YERİNE üç katman.

Sahibin "PWM ağ koparsa DURMAZ" değişmezini KORUYARAK:
  A-1  SÜRESİZ-MOD MUTLAK TAVANI (firmware, S3+8266): duration=0 modda cihaz-yerel 7200 sn
       son-tarih. Zamana bağlı, ağa DEĞİL → değişmez ihlal edilmez; süreli seans etkilenmez.
  A-2  E-STOP BULUT AYNASI (backend): acil durdurma yerel broker'a EK olarak HiveMQ cloud'a da
       yayınlanır → buluta failover etmiş ESP'ye de ulaşır. Sırlar yoksa sessiz devre dışı.
  A-3  HEDEFLİ RECONCILE (backend): ESP "çalışıyor" raporlar ama backend niyeti/aktif seans
       kapsamıyorsa hedefli STOP. Niyet, tek boğaz noktası _mqtt_publish'te kaydedilir.
       Retained-STOP bilinçli REDDEDİLDİ (meşru seansı da öldürürdü).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

import servers.api_server as api

KOK = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _temiz_intent():
    def _sifirla():
        with api._esp_intent_lock:
            api._esp_commanded_running.clear()
            api._reconcile_last_stop.clear()
            api._esp_stop_zamani.clear()
        with api._session_lock:
            api._active_session["is_active"] = False
            api._active_session["coil_ids"] = []

    _sifirla()
    yield
    _sifirla()


# ── A-1: firmware süresiz-mod tavanı (yapısal) ─────────────────────────────────


def test_KRITIK_A1_iki_firmware_de_suresiz_tavani_ICERIR():
    for klasor in ("esps3_pemf_coil", "esp8266_pemf_coil"):
        sd = (KOK / "firmware" / klasor / "SharedDefs.h").read_text(encoding="utf-8", errors="replace")
        assert "#define SURESIZ_TAVAN_SEC 7200UL" in sd, f"{klasor}: SURESIZ_TAVAN_SEC yok/değişmiş"
    s3 = (KOK / "firmware" / "esps3_pemf_coil" / "CoilController.cpp").read_text(encoding="utf-8", errors="replace")
    e8 = (KOK / "firmware" / "esp8266_pemf_coil" / "CoilController.cpp").read_text(encoding="utf-8", errors="replace")
    # S3: süresiz dal — !_hasDuration + tavan karşılaştırması + durdurma
    assert "!_hasDuration" in s3 and "SURESIZ_TAVAN_SEC" in s3, "S3 süresiz-tavan dalı yok"
    i = s3.index("SURESIZ_TAVAN_SEC * 1000UL")
    assert "_stopPWM" in s3[i : i + 300], "S3 tavanda durdurmuyor"
    # 8266: _pwmDuration == 0 dalı
    assert "_pwmDuration == 0" in e8 and "SURESIZ_TAVAN_SEC * 1000UL" in e8, "8266 süresiz-tavan dalı yok"
    j = e8.index("SURESIZ_TAVAN_SEC * 1000UL")
    assert "stop()" in e8[j : j + 300], "8266 tavanda durdurmuyor"


def test_A1_tavan_backend_STM_deadline_ile_AYNI():
    """7200 sn = 120 dk — hardware_controller.GOZETIMSIZ_VARSAYILAN_DAKIKA ile parite."""
    import controllers.hardware_controller as hc

    assert hc.GOZETIMSIZ_VARSAYILAN_DAKIKA * 60 == 7200, (
        "STM gözetimsiz varsayılanı değişmiş — firmware SURESIZ_TAVAN_SEC ile hizalayın"
    )


def test_A1_sureli_seans_yolu_wrap_GUVENLI():
    """Süreli dal (duration>0) duruyor VE wrap-güvenli (review: millis ~49,7 günde sarar;
    eski `millis() >= _endTime` hep-açık klinik makinede seansı anında kesebilirdi)."""
    s3 = (KOK / "firmware" / "esps3_pemf_coil" / "CoilController.cpp").read_text(encoding="utf-8", errors="replace")
    e8 = (KOK / "firmware" / "esp8266_pemf_coil" / "CoilController.cpp").read_text(encoding="utf-8", errors="replace")
    # S3: fark tabanlı karşılaştırma; eski mutlak-zaman formu GERİ GELMEMELİ
    assert "_active && _hasDuration && (millis() - _startTime) >= _duration" in s3
    assert "millis() >= _endTime" not in s3.replace("`millis() >= _endTime`", ""), (
        "S3 süreli dal mutlak-zaman karşılaştırmasına dönmüş (wrap'ta seans kesilir)"
    )
    # getState kalan-süre de fark tabanlı
    assert "(_duration > gecen) ? (_duration - gecen)" in s3, "S3 kalan-süre hesabı wrap-güvenli değil"
    assert "_pwmActive && _pwmDuration > 0" in e8
    # 8266'nın değişmez yorumu yerinde (ağ PWM'i etkilemez)
    assert "PWM'i ASLA ETK" in e8, "8266 ağ-bağımsızlık değişmez yorumu kaybolmuş"


def test_KRITIK_A1_tavan_KUMULATIF_crash_loop_delemez():
    """Review: <2 saatte bir çöküp dirilen cihaz (crash-loop) + otomatik resume, tavanı
    fiilen sınırsız yapıyordu. Artık geçen süre NVS/EEPROM'a kümülatif yazılır ve resume
    devralır; yalnız YENİ START komutu (operatör eylemi) pencereyi sıfırlar."""
    s3 = (KOK / "firmware" / "esps3_pemf_coil" / "CoilController.cpp").read_text(encoding="utf-8", errors="replace")
    e8 = (KOK / "firmware" / "esp8266_pemf_coil" / "CoilController.cpp").read_text(encoding="utf-8", errors="replace")
    for ad, src in (("S3", s3), ("8266", e8)):
        assert "_suresizGecenMs" in src, f"{ad}: kümülatif sayaç yok"
    # tavan kontrolü kümülatif toplamla
    assert "(_suresizGecenMs + (millis() - _startTime))" in s3, "S3 tavanı kümülatif değil"
    assert "(_suresizGecenMs + safeMillisDiff(millis(), _pwmStartTime))" in e8, "8266 tavanı kümülatif değil"
    # persist: süresiz modda elapsed kümülatif yazılır
    assert "_suresizGecenMs + (millis() - _startTime))" in s3
    assert "_suresizGecenMs + safeMillisDiff(millis(), _pwmStartTime);" in e8, "8266 savePWMState kümülatif yazmıyor"
    # resume devralır (S3 loadState / 8266 restorePWMState)
    assert "_suresizGecenMs = s.elapsedMs" in s3, "S3 resume kümülatifi devralmıyor"
    assert "_suresizGecenMs = (state.duration == 0) ? state.elapsed : 0" in e8, "8266 resume devralmıyor"
    # taze START pencereyi sıfırlar (operatör eylemi)
    assert s3.count("_suresizGecenMs = 0") >= 2, "S3 taze-start sıfırlaması yok (ctor+_beginOutput)"
    assert e8.count("_suresizGecenMs = 0") >= 2, "8266 taze-start sıfırlaması yok (ctor+start)"


def test_A1_kumulatif_tavan_MODEL():
    """Python modeli: crash-loop'ta (90dk çalış → çök → resume) tavan 2. boot'ta dolar;
    taze START ise pencereyi meşru sıfırlar."""
    TAVAN = 7200_000

    class _Cihaz:
        def __init__(self):
            self.gecen_devir = 0  # _suresizGecenMs
            self.boot_ms = 0

        def calis(self, ms):
            self.boot_ms += ms
            return (self.gecen_devir + self.boot_ms) >= TAVAN  # tavan doldu mu

        def kaydet(self):
            return self.gecen_devir + self.boot_ms  # NVS elapsedMs

        def resume(self, nvs_elapsed):
            self.gecen_devir = nvs_elapsed
            self.boot_ms = 0

        def taze_start(self):
            self.gecen_devir = 0
            self.boot_ms = 0

    c = _Cihaz()
    assert not c.calis(90 * 60_000)  # 90 dk — tavan dolmadı
    nvs = c.kaydet()
    c.resume(nvs)  # çöktü, dirildi
    assert c.calis(31 * 60_000), "crash-loop: 90+31=121 dk kümülatifte tavan DOLMALIYDI"
    c.taze_start()  # operatör yeni start verdi
    assert not c.calis(119 * 60_000), "taze start sonrası pencere sıfırlanmadı"


# ── A-3: niyet kaydı (tek boğaz noktası) ───────────────────────────────────────


def test_KRITIK_A3_niyet_ASIMETRIK_start_dogrulamali_stop_hemen():
    """F4 (review): START yalnız DOĞRULANMIŞ publish'te True; STOP hemen False + an damgası."""
    # başarısız/doğrulanmamış start niyeti True YAPMAZ (NVS-hayaleti süresiz muaf kalırdı)
    api._kaydet_esp_komut_niyeti("pemf/coil/6/control", {"command": "start", "freq": 10}, basarili=False)
    assert api._esp_commanded_running.get(6) is not True
    # doğrulanmış start → True
    api._kaydet_esp_komut_niyeti("pemf/coil/6/control", {"command": "start", "freq": 10}, basarili=True)
    assert api._esp_commanded_running.get(6) is True
    # stop HEMEN (basarili=False çağrısında) False + F5 an damgası
    api._kaydet_esp_komut_niyeti("pemf/coil/6/control", {"command": "stop"}, basarili=False)
    assert api._esp_commanded_running.get(6) is False
    assert api._esp_stop_zamani.get(6, 0) > 0, "stop anı damgalanmadı (F5 grace penceresi çalışmaz)"
    # kontrol-dışı topic ve start/stop-dışı komutlar niyeti DEĞİŞTİRMEZ; bozuk topic çökertmez
    api._kaydet_esp_komut_niyeti("pemf/coil/6/status", {"command": "start"}, basarili=True)
    api._kaydet_esp_komut_niyeti("pemf/coil/6/control", {"command": "SELFTEST"}, basarili=True)
    assert api._esp_commanded_running.get(6) is False
    api._kaydet_esp_komut_niyeti("pemf/coil/abc/control", {"command": "start"}, basarili=True)


def test_KRITIK_A3_niyet_kayit_sirasi_ve_asimetri_KODDA():
    """Yapısal: STOP kaydı probe'dan ÖNCE (broker kapalıyken bile), START kaydı yalnız
    yayinlandi=True dalında (F4)."""
    import inspect

    src = inspect.getsource(api._mqtt_publish)
    assert "_kaydet_esp_komut_niyeti(topic, payload, basarili=False)" in src
    assert src.index("basarili=False") < src.index("create_connection"), (
        "STOP niyet kaydı broker probe'undan SONRA — broker kapalıyken niyet kaybolur"
    )
    i = src.index("basarili=True")
    assert "yayinlandi" in src[i - 400 : i], "START kaydı doğrulanmış-publish dalında değil"


# ── A-3: hedefli reconcile ─────────────────────────────────────────────────────


def _reconcile_kos(coil_id, snapshot, bekle=1.5):
    """Reconcile'ı koş; arka-plan STOP thread'inin yayınını yakala."""
    yayinlar = []
    bitti = threading.Event()

    def _fake_pub(topic, payload):
        yayinlar.append((topic, payload))
        bitti.set()
        return True

    orijinal = api._mqtt_publish
    api._mqtt_publish = _fake_pub
    api_push = api._push_notification
    api._push_notification = lambda *a, **k: None
    try:
        api._reconcile_esp_calisiyor(coil_id, snapshot)
        bitti.wait(bekle)
    finally:
        api._mqtt_publish = orijinal
        api._push_notification = api_push
    return yayinlar


def test_KRITIK_A3_beklenmedik_calisan_bobine_STOP():
    yayinlar = _reconcile_kos(6, {"running": True})
    assert yayinlar, "reconcile STOP yayınlamadı — hayalet bobin enerjili kalır"
    topic, payload = yayinlar[0]
    assert topic == "pemf/coil/6/control" and payload["command"] == "stop"
    assert payload["command_id"].startswith("reconcile_")


def test_KRITIK_A3_mesru_calisma_DURDURULMAZ():
    # (a) backend start komutladıysa
    with api._esp_intent_lock:
        api._esp_commanded_running[7] = True
    assert not _reconcile_kos(7, {"running": True}, bekle=0.4), "komutlanmış bobini durdurdu (meşru seans katli)"
    # (b) aktif seans kapsıyorsa
    with api._session_lock:
        api._active_session["is_active"] = True
        api._active_session["coil_ids"] = [8]
    assert not _reconcile_kos(8, {"running": True}, bekle=0.4), "seanslı bobini durdurdu"


def test_A3_STM_ve_durmus_bobin_TETIKLEMEZ():
    assert not _reconcile_kos(1, {"running": True}, bekle=0.3), "STM bobinine MQTT reconcile gitti"
    assert not _reconcile_kos(6, {"running": False}, bekle=0.3), "durmuş bobine STOP gitti"


def test_A3_hiz_siniri_30sn():
    assert _reconcile_kos(6, {"running": True})
    assert not _reconcile_kos(6, {"running": True}, bekle=0.4), "30 sn içinde ikinci reconcile-STOP gitti (fırtına)"


def test_KRITIK_A3_F5_stop_sonrasi_grace_penceresi():
    """Normal STOP'tan hemen sonra uçuştaki 'running' status sahte reconcile TETİKLEMEMELİ
    (her normal stop'ta sahte 'güvenlik durdurması' bildirimi = alarm yorgunluğu)."""
    api._kaydet_esp_komut_niyeti("pemf/coil/6/control", {"command": "stop"}, basarili=False)
    assert not _reconcile_kos(6, {"running": True}, bekle=0.4), (
        "stop'tan hemen sonraki bayat 'running' status reconcile tetikledi (grace penceresi yok)"
    )
    # grace penceresi GEÇMİŞSE hayalet yakalanmalı (karşıt-kanıt)
    with api._esp_intent_lock:
        api._esp_stop_zamani[6] = time.monotonic() - 60.0
    assert _reconcile_kos(6, {"running": True}), "grace geçtikten sonra gerçek hayalet yakalanmadı"


def test_KRITIK_A3_F3_publish_oncesi_son_kontrol():
    """Karar ile publish arası pencerede meşru start gelirse reconcile-STOP VAZGEÇMELİ
    (yoksa yeni başlamış tedaviyi sessizce durdurur + stop niyeti start'ı ezer)."""
    yayinlar = []
    bitti = threading.Event()

    def _fake_pub(topic, payload):
        yayinlar.append((topic, payload))
        bitti.set()
        return True

    orijinal_pub = api._mqtt_publish
    orijinal_push = api._push_notification
    # thread spawn'ını yakala: karar verildi ama thread'i BİZ koşturacağız (araya start sokup)
    yakalanan = {}
    orijinal_thread = threading.Thread

    class _GecikmisThread(orijinal_thread):
        def start(self):
            yakalanan["hedef"] = self._target  # koşturma — pencereyi biz kontrol ediyoruz

    api._mqtt_publish = _fake_pub
    api._push_notification = lambda *a, **k: None
    try:
        import unittest.mock as mock

        with mock.patch.object(threading, "Thread", _GecikmisThread):
            api._reconcile_esp_calisiyor(6, {"running": True})
        assert "hedef" in yakalanan, "reconcile karar vermedi (test kurgusu bozuk)"
        # PENCERE: publish'ten önce meşru start geliyor
        with api._esp_intent_lock:
            api._esp_commanded_running[6] = True
        yakalanan["hedef"]()  # _stop_gonder şimdi koşuyor → son-kontrol vazgeçmeli
        assert not yayinlar, "F3 son-kontrol yok: reconcile-STOP meşru yeni tedaviyi durdurdu"
    finally:
        api._mqtt_publish = orijinal_pub
        api._push_notification = orijinal_push


def test_KRITIK_A3_handler_yalniz_CANLI_status_ile_tetikler():
    """Retained status (8266 retain=true yayınlar) reconcile TETİKLEMEMELİ."""
    import inspect

    src = inspect.getsource(api._on_mqtt_message_api)
    i = src.index("_reconcile_esp_calisiyor")
    onceki = src[:i].rsplit("if not is_retained", 1)
    assert len(onceki) == 2 and len(src[:i]) - len(onceki[0]) < 400, (
        "reconcile çağrısı is_retained korumasız — bayat retained 'running' sahte STOP üretir"
    )


# ── A-2: E-stop bulut aynası ───────────────────────────────────────────────────


def test_KRITIK_A2_sirlar_yoksa_ayna_SESSIZ_devre_disi(monkeypatch):
    monkeypatch.setattr("utils.secrets_manager.get_secret", lambda *a, **k: "")
    api._estop_cloud_mirror([6, 7, 8], "test")  # çökmemeli, paho'ya hiç dokunmamalı


def test_KRITIK_A2_F6_GERCEK_get_secret_ATLANDI_yolunu_izler(monkeypatch, caplog):
    """F6 (review): monkeypatch'SİZ gerçek get_secret ile — mqtt_cloud_* _REGISTRY'de TANIMLI
    olmalı ki tanımsız-değer durumunda KeyError değil 'ATLANDI' info yolu izlensin. İlk sürümde
    anahtarlar registry'de yoktu → ilk get_secret KeyError atıyor, dış except yutuyordu → ayna
    ÖLÜ DOĞMUŞTU ve testler monkeypatch yüzünden görmüyordu."""
    import logging as _logging

    from utils import secrets_manager as sm

    # kayıt kapısı: 4 anahtar registry'de
    for k in ("mqtt_cloud_host", "mqtt_cloud_port", "mqtt_cloud_user", "mqtt_cloud_pass"):
        assert k in sm._REGISTRY, f"{k} _REGISTRY'de yok → get_secret KeyError atar, ayna ölü doğar"
    # env fallback'leri temizle (makinede tanımlıysa testi kirletmesin)
    for ev in ("PEMF_MQTT_CLOUD_HOST", "PEMF_MQTT_CLOUD_PORT", "PEMF_MQTT_CLOUD_USER", "PEMF_MQTT_CLOUD_PASS"):
        monkeypatch.delenv(ev, raising=False)
    # 2026-08-19 gece: sahip kararıyla PAKETE GÖMÜLÜ provizyon dosyası eklendi (bkz.
    # test_cloud_provision.py) — build makinesinde GERÇEK değerler yerelde durur. Bu test
    # "sır TANIMSIZ" yolunu sınar → gömülü dosyayı da izole et (yoksa gerçek get_secret
    # gerçek kimliği bulur ve ayna testte GERÇEK buluta bağlanmaya kalkar!).
    monkeypatch.setenv("PEMF_CLOUD_PROVISION_PATH", r"C:\yok\boyle\bir\dosya.json")
    with caplog.at_level(_logging.INFO, logger="servers.api_server"):
        api._estop_cloud_mirror([6], "f6-test")  # GERÇEK get_secret — KeyError atmamalı
    assert any("ATLANDI" in r.message for r in caplog.records), (
        "ayna 'sırlar tanımsız → ATLANDI' info yolunu izlemedi (KeyError'a mı düştü?)"
    )
    assert not any("basarisiz" in r.message.lower() for r in caplog.records), (
        "ayna exception yoluna düştü — sırlar tanımsızken bu sessiz-atlama olmalıydı"
    )


def test_KRITIK_A2_sirlar_varsa_buluta_stop_yayinlar(monkeypatch):
    def fake_secret(key, default="", generate=True):
        assert generate is False, "generate=True → sır dosyasına rastgele değer YAZILIR (yasak)"
        return {
            "mqtt_cloud_host": "ornek.hivemq.cloud",
            "mqtt_cloud_user": "u",
            "mqtt_cloud_pass": "p",
            "mqtt_cloud_port": "8883",
        }.get(key, default)

    monkeypatch.setattr("utils.secrets_manager.get_secret", fake_secret)

    yayinlar = []

    class _Info:
        def wait_for_publish(self, timeout=None):
            pass

        def is_published(self):
            return True

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        def username_pw_set(self, u, p):
            pass

        def tls_set(self, *a, **k):
            self.tls = True

        def connect(self, host, port, keepalive=10):
            assert port == 8883 and "hivemq" in host

        def loop_start(self):
            pass

        def loop_stop(self):
            pass

        def disconnect(self):
            pass

        def publish(self, topic, payload, qos=0):
            yayinlar.append((topic, qos))
            return _Info()

    import sys
    import types

    fake_paho = types.ModuleType("paho.mqtt.client")
    fake_paho.Client = _FakeClient
    fake_paho.CallbackAPIVersion = types.SimpleNamespace(VERSION2=2)
    # `import paho.mqtt.client as _pm` üç seviyeyi de çözümler — hepsini sahtele
    fake_mqtt = types.ModuleType("paho.mqtt")
    fake_mqtt.client = fake_paho
    fake_root = types.ModuleType("paho")
    fake_root.mqtt = fake_mqtt
    monkeypatch.setitem(sys.modules, "paho", fake_root)
    monkeypatch.setitem(sys.modules, "paho.mqtt", fake_mqtt)
    monkeypatch.setitem(sys.modules, "paho.mqtt.client", fake_paho)

    api._estop_cloud_mirror([6, 7, 8], "test")
    topikler = [t for t, _ in yayinlar]
    for cid in (6, 7, 8):
        assert f"pemf/coil/{cid}/control" in topikler, f"bobin {cid} bulut STOP'u eksik"
    assert all(q == 1 for _, q in yayinlar), "bulut STOP qos=1 değil"


def test_KARSIT_KANIT_A2_estop_ayna_threadi_KODDA():
    import inspect

    src = inspect.getsource(api)
    assert 'name="estop-cloud-mirror"' in src, "E-stop bulut ayna thread'i düşmüş (HG-5 geri açıldı)"
    i = src.index('name="estop-cloud-mirror"')
    # yerel yoldan ÖNCE başlatılıyor (paralel; yerel yolu bloklamaz)
    assert "_cf.ThreadPoolExecutor" in src[i : i + 800], "ayna, yerel E-stop havuzunun yanında değil"
