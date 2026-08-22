# Author: mertaygn, cglrgrkn
"""ESP STATUS MQTT SÖZLEŞMESİ — 2. tur denetimi bulgu [1.2] (2026-08-20).

ÖLÇÜLEN KOPUKLUK (üç parça, tek kök neden: iki uç ayrı ayrı yazıldı, sözleşme test edilmedi):
  (a) Backend `connected`'ı `payload["status"]` DİZESİNDEN türetiyordu; ne S3 ne 8266 status
      JSON'ında `status` alanı yayınlıyor → her CANLI status mesajı connected=False yazıyordu.
  (b) Backend duty'yi yalnız `duty_cycle` anahtarından okuyordu; S3 `pwm_duty`, 8266
      `pwm_duty_cycle` yayınlıyor → ESP bobinlerinin EFEKTİF duty'si (D-2 dürüst-rapor
      düzeltmesi) live-state'e ve oradan DOZ KAYITLARINA hiç ulaşmıyordu (duty=0 yazılıyordu).
  (c) S3 `sensors` yayınını tümden kaldırdı ("UYUMSUZ-6: tümü /status içinde") ama backend
      `current`/`ambient_temp`'i yalnız sensors dalında okuyordu; `connected=True` yazan tek
      periyodik dal da sensors idi → S3 bobinleri KALICI "bağlantı yok" görünüyor, bayat-telemetri
      STOP watchdog'u (yalnız connected=True bobini durdurur) S3 için HİÇ çalışmıyordu.

⚠️ Neden hiçbir mevcut test görmedi: test payload'ları backend'in BEKLEDİĞİ biçimi
(`{"status":"online"}`) enjekte ediyordu, firmware'in ÜRETTİĞİNİ değil; PEMF_SIMULATE yolu ise
`_live_state`'i doğrudan yazar, MQTT ayrıştırmasına hiç uğramaz. Buradaki payload'lar iki
firmware'in publishStatus çıktısının birebir anahtar kümesidir ve parite kapısı o anahtarları
firmware KAYNAĞINDA kilitler — iki uç bir daha sessizce ayrışamasın.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture()
def api(monkeypatch):
    import servers.api_server as api

    # Yayın/yan-etki yolları test dışı: WS yayını, bildirim, reconcile (arka plan thread açar).
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)
    monkeypatch.setattr(api, "_reconcile_esp_calisiyor", lambda *a, **k: None)

    eski_tel = dict(api._coil_last_telemetry)
    with api._live_state_lock:
        eski_coils = {i: dict(api._live_state["coils"][i]) for i in range(8)}
        # Bilinen başlangıç: ESP bobinleri bağlı DEĞİL, ölçümler sıfır.
        for i in (5, 6, 7):
            api._live_state["coils"][i].update(
                {
                    "connected": False,
                    "running": False,
                    "dutyCycle": 0,
                    "frequencyHz": 0,
                    "objectTemp": 0.0,
                    "ambientTemp": 0.0,
                    "currentA": 0.0,
                    "magneticMt": 0.0,
                }
            )
    yield api
    api._coil_last_telemetry.clear()
    api._coil_last_telemetry.update(eski_tel)
    with api._live_state_lock:
        for i in range(8):
            api._live_state["coils"][i].clear()
            api._live_state["coils"][i].update(eski_coils[i])


def _mesaj(topic: str, payload: dict, retain: bool = False):
    class _Msg:
        pass

    m = _Msg()
    m.topic = topic
    m.retain = retain
    m.payload = json.dumps(payload).encode("utf-8")
    return m


def _s3_status(coil_id: int = 6, **degisiklik) -> dict:
    """S3 publishStatus'un GERÇEK anahtar kümesi (esps3 NetworkManager.cpp:604-672).
    ⚠️ `status` DİZESİ YOK — firmware yayınlamıyor; parite kapısı bunu kaynakta kilitler."""
    p = {
        "coil_id": coil_id,
        "fw_version": "test",
        "msg_type": "status",
        "timestamp": 1,
        "uptime": 10,
        "free_heap": 1000,
        "max_alloc_heap": 900,
        "fragmentation": 3,
        "sync_fallback_event": False,
        "wifi_connected": True,
        "wifi_ssid": "x",
        "wifi_rssi": -40,
        "wifi_ip": "10.0.0.9",
        "portal_active": False,
        "portal_ip": "",
        "portal_ssid": "",
        "mqtt_connected": True,
        "broker_type": "local",
        "pwm_active": True,
        "pwm_frequency": 2,
        "pwm_duty": 24,
        "pwm_remaining_time": 90,
        "pwm_duration": 600,
        "thermal_lock": False,
        "sync_ignored": 0,
        "sync_disabled": False,
        "pwm_start_timestamp": 1,
        "object_temp": 31.5,
        "ambient_temp": 24.0,
        "current": 0.42,
        "magnetic_field": 1.8,
        "max_magnetic_field": 2.0,
        "max_current": 0.5,
        "sensors_ok": True,
        "temp_sensor_ok": True,
        "magnetic_sensor_ok": True,
        "current_sensor_ok": True,
    }
    p.update(degisiklik)
    return p


def _e8266_status(coil_id: int = 8, **degisiklik) -> dict:
    """8266 publishStatus'un GERÇEK anahtar kümesi (esp8266 NetworkManager.cpp:210-226).
    ⚠️ Duty anahtarı S3'ten FARKLI: `pwm_duty_cycle`. Sensör okumaları AYRI sensors mesajında."""
    p = {
        "coil_id": coil_id,
        "timestamp": 1,
        "wifi_connected": True,
        "wifi_ssid": "x",
        "wifi_rssi": -40,
        "wifi_ip": "10.0.0.8",
        "portal_active": False,
        "portal_ip": "",
        "portal_ssid": "",
        "mqtt_connected": True,
        "pwm_active": False,
        "pwm_frequency": 50,
        "pwm_duty_cycle": 37,
        "pwm_remaining_time": 0,
        "pwm_start_timestamp": 0,
        "pwm_duration": 0,
        "sensors_ok": True,
        "temp_sensor_ok": True,
        "magnetic_sensor_ok": True,
        "current_sensor_ok": True,
        "free_heap": 20000,
        "max_alloc_heap": 15000,
        "fragmentation": 5,
        "uptime": 10,
    }
    p.update(degisiklik)
    return p


def _coil(api, cid: int) -> dict:
    with api._live_state_lock:
        return dict(api._live_state["coils"][cid - 1])


# ── (a) + (c): canlı status = cihaz CANLI ─────────────────────────────────────


def test_KRITIK_S3_canli_status_connected_yapar(api):
    """S3 hiç `sensors` yayınlamaz (UYUMSUZ-6) ve status'unda `status` dizesi yoktur.
    CANLI (retain=0) status mesajının kendisi cihazın yaşadığının kanıtıdır → connected=True.
    Eski davranış (`payload.get("status","") in (...)` → False) bobin 6-7'yi KALICI
    'bağlantı yok' gösteriyor, paneli kilitliyor ve watchdog'u kör ediyordu."""
    api._on_mqtt_message_api(None, None, _mesaj("pemf/coil/6/status", _s3_status(6)))
    c = _coil(api, 6)
    assert c["connected"] is True, (
        "CANLI S3 status'u connected=True yapmadı — bobin 6-7 kalıcı 'Offline' görünür, "
        "CoilParameterPanel kontrolleri kilitlenir, stale-STOP watchdog'u bu bobini ASLA durdurmaz"
    )
    assert c["running"] is True  # pwm_active'ten


def test_KRITIK_S3_status_current_ve_ambient_isler(api):
    """S3'te current/ambient yalnız status içinde gelir; okunmazsa doz kayıtlarına 0 yazılır."""
    api._on_mqtt_message_api(None, None, _mesaj("pemf/coil/6/status", _s3_status(6)))
    c = _coil(api, 6)
    assert c["currentA"] == pytest.approx(0.42), "status'taki `current` okunmadı (S3'te başka kaynağı YOK)"
    assert c["ambientTemp"] == pytest.approx(24.0), "status'taki `ambient_temp` okunmadı"
    assert c["objectTemp"] == pytest.approx(31.5)
    assert c["magneticMt"] == pytest.approx(1.8)


# ── (b): efektif duty her iki kardeş anahtarından okunur ─────────────────────


def test_KRITIK_S3_efektif_duty_pwm_duty_anahtarindan_okunur(api):
    api._on_mqtt_message_api(None, None, _mesaj("pemf/coil/6/status", _s3_status(6, pwm_duty=24)))
    assert _coil(api, 6)["dutyCycle"] == 24, (
        "S3 `pwm_duty` okunmadı — firmware'in DÜRÜST efektif duty raporu (D-2) live-state'e "
        "ulaşmıyor; dakika-akümülatörü doz kaydına duty=0 yazar"
    )


def test_KRITIK_8266_efektif_duty_pwm_duty_cycle_anahtarindan_okunur(api):
    api._on_mqtt_message_api(None, None, _mesaj("pemf/coil/8/status", _e8266_status(8, pwm_duty_cycle=37)))
    c = _coil(api, 8)
    assert c["dutyCycle"] == 37, "8266 `pwm_duty_cycle` okunmadı — doz kaydı duty=0 kalır"
    assert c["connected"] is True
    assert c["running"] is False  # pwm_active=false


def test_KRITIK_bozuk_sensor_alani_mesajin_kalanini_oldurmez(api):
    """Adversaryal review #3 (2026-08-20): S3 sıcaklık sensörü arızasında readObjectTempC NaN
    döner ve ArduinoJson NaN'i `null` yazar → eski kod `float(None)` TypeError'ıyla mesaj
    işlemeyi YARIDA kesiyordu: connected/duty uygulanmış ama current/ambient + WS yayını +
    reconcile ATLANMIŞ kalıyordu (5 Hz'de WARN spam). Bozuk TEK alan yalnız KENDİSİNİ
    düşürmeli — kalanı işlenmeli."""
    api._on_mqtt_message_api(None, None, _mesaj("pemf/coil/6/status", _s3_status(6, object_temp=None)))
    c = _coil(api, 6)
    assert c["connected"] is True
    assert c["currentA"] == pytest.approx(0.42), (
        "object_temp=null (sensör arızası) current okumasını da öldürdü — S3'te current'ın "
        "başka kaynağı YOK, doz kaydı 0 görür"
    )
    assert c["ambientTemp"] == pytest.approx(24.0)
    assert c["objectTemp"] == 0.0, "null sıcaklık bir SAYI olarak yazılmamalı (0 nöbetçisi korunur)"


def test_KRITIK_efektif_duty_komutlanan_duty_cycle_i_EZER(api):
    """Adversaryal review #4: bir firmware günün birinde HEM `duty_cycle` (komutlanan) HEM
    `pwm_duty`/`pwm_duty_cycle` (efektif) yayınlarsa DÜRÜST olan efektiftir — komutlanan değer
    efektifi gölgelememeli (D-2'nin bütün amacı gerçek çıkışı raporlamaktı)."""
    api._on_mqtt_message_api(None, None, _mesaj("pemf/coil/6/status", _s3_status(6, duty_cycle=50, pwm_duty=24)))
    assert _coil(api, 6)["dutyCycle"] == 24, "komutlanan duty_cycle=50, efektif pwm_duty=24'ü gölgeledi"


# ── güvenlik zinciri: status → connected → stale-STOP watchdog ───────────────


class _CikisSinyali(Exception):
    """`while True` watchdog'undan TEK TUR sonra çıkmak için."""


class _TekTurZaman:
    """Yalnız `sleep` yakalanır, gerisi GERÇEK `time` (test_kalan_regression_gaps deseniyle aynı)."""

    def __init__(self):
        import time as _t

        self._t = _t

    def __getattr__(self, ad):
        return getattr(self._t, ad)

    def sleep(self, _sn):
        raise _CikisSinyali


def test_KRITIK_zincir_S3_status_sonrasi_susan_bobine_stale_STOP_gider(api, monkeypatch):
    """Bulgunun asıl güvenlik sonucu: son mesajı STATUS olan (S3'te HEP öyle — sensors yok)
    bir bobin susarsa, watchdog `connected=True` şartı yüzünden STOP'u ATLIYORDU.
    Zincir uçtan uca: gerçek MQTT ayrıştırması → connected → tek tur watchdog → STOP yayını."""
    import time as _t

    api._on_mqtt_message_api(None, None, _mesaj("pemf/coil/6/status", _s3_status(6)))
    # Bobin sustu: damgayı eşikten öteye eskit.
    api._coil_last_telemetry[5] = _t.monotonic() - (float(api.ESP_STALE_SEC) + 5.0)

    yayinlar: list = []
    monkeypatch.setattr(api, "_mqtt_publish", lambda t, p=None, *a, **k: yayinlar.append((t, p)) or True)
    monkeypatch.setattr(api, "time", _TekTurZaman())
    with pytest.raises(_CikisSinyali):
        api._esp_telemetry_watchdog()

    stoplar = [(t, p) for t, p in yayinlar if t == "pemf/coil/6/control" and (p or {}).get("command") == "stop"]
    assert stoplar, (
        f"S3 status'undan sonra susan bobine stale-STOP YAYINLANMADI (yayinlar={yayinlar!r}) — "
        "1.9.16'nın 'sessizleşen ESP'ye gerçek STOP' güvenlik ağı S3 için ölü"
    )
    assert _coil(api, 6)["connected"] is False, "bayat bobin UI'da hâlâ canlı görünüyor"


# ── karşıt-kanıtlar: eski sözleşme + retained filtresi bozulmadı ─────────────


def test_KARSIT_KANIT_eski_firmware_status_dizesi_AYNEN_islenir(api):
    """Saha filosundaki ESKİ firmware `status` dizesi yayınlayabilir — açık dize sinyali
    yeni varsayılanı EZER: 'online' → True, tanınmayan/'offline' → False."""
    api._on_mqtt_message_api(None, None, _mesaj("pemf/coil/7/status", {"coil_id": 7, "status": "online"}))
    assert _coil(api, 7)["connected"] is True

    api._on_mqtt_message_api(None, None, _mesaj("pemf/coil/7/status", {"coil_id": 7, "status": "offline"}))
    assert _coil(api, 7)["connected"] is False, (
        "AÇIK 'offline' dizesi connected=False yapmalı — 'her status=canlı' aşırı-düzeltmesi "
        "eski firmware'in açık offline sinyalini yutar"
    )


def test_KARSIT_KANIT_retained_status_hicbir_sey_yazmaz(api):
    """D-4/HG-4 retained filtresi KORUNMALI: broker'da kalmış bayat status (8266 retain=true
    yayınlar) reconnect'te teslim edilir; onu canlı saymak bayat 'running' + sahte connected üretir."""
    api._on_mqtt_message_api(None, None, _mesaj("pemf/coil/8/status", _e8266_status(8, pwm_active=True), retain=True))
    c = _coil(api, 8)
    assert c["connected"] is False and c["running"] is False and c["dutyCycle"] == 0, (
        f"RETAINED status işlendi: {c!r} — bayat mesaj canlı durum sanıldı (D-4 regresyonu)"
    )


# ── parite kapısı: firmware anahtarları kaynakta kilitli ─────────────────────


def _fw_oku(*parcalar: str) -> str:
    return (REPO.joinpath(*parcalar)).read_text(encoding="utf-8", errors="replace")


def _fonksiyon_govdesi(kaynak: str, imza: str) -> str:
    """`imza` ile başlayan fonksiyonun gövdesini bir SONRAKİ fonksiyon tanımına kadar döndür."""
    i = kaynak.find(imza)
    assert i >= 0, f"parite kapısı: {imza!r} bulunamadı — firmware yapısı değişti, kapıyı güncelle"
    j = kaynak.find("\nvoid ", i + len(imza))
    return kaynak[i : j if j > 0 else len(kaynak)]


def test_PARITE_firmware_status_anahtarlari_backend_ile_ayni_dilde(api):
    """İki yönlü kilit: (1) backend'in okuduğu duty anahtarları firmware'de GERÇEKTEN var;
    (2) firmware publishStatus'ları `status` DİZESİ yayınlamıyor (yayınlamaya başlarlarsa
    buradaki sentetik payload'lar gerçeği temsil etmez olur → kapı kırmızıya döner ve
    testin kendisi güncellenir). Bu, iki ucun sessizce ayrışmasını engelleyen çapraz kapıdır."""
    s3 = _fw_oku("firmware", "esps3_pemf_coil", "NetworkManager.cpp")
    e8 = _fw_oku("firmware", "esp8266_pemf_coil", "NetworkManager.cpp")

    s3_status = _fonksiyon_govdesi(s3, "void PemfNetworkManager::publishStatus")
    e8_status = _fonksiyon_govdesi(e8, "void NetworkManager::publishStatus")

    assert 'doc["pwm_duty"]' in s3_status, "S3 artık `pwm_duty` yayınlamıyor — backend okuma listesi güncellenmeli"
    assert '\\"pwm_duty_cycle\\":' in e8_status, (
        "8266 artık `pwm_duty_cycle` yayınlamıyor — backend okuma listesi güncellenmeli"
    )
    assert 'doc["current"]' in s3_status and 'doc["ambient_temp"]' in s3_status, (
        "S3 status'u current/ambient taşımıyor — S3'te sensors mesajı OLMADIĞI için backend bu alanları başka yerden alamaz"
    )
    # `status` DİZESİ: JSON anahtarı olarak yayınlanmamalı (msg_type discriminator'ı serbest).
    assert 'doc["status"]' not in s3_status, (
        "S3 status'a `status` dizesi eklendi — sentetik payload'lar ve backend varsayımı bayatladı"
    )
    assert re.search(r'\\"status\\"\s*:', e8_status) is None, (
        "8266 status'a `status` dizesi eklendi — sentetik payload'lar ve backend varsayımı bayatladı"
    )
    # Adversaryal review kör-nokta kapatması (2026-08-20):
    # (1) `pwm_active` iki status'ta da OLMALI — backend `running`'i status-dizesi yokken yalnız
    #     ondan türetir; firmware onu çıkarırsa `running` sessizce bayatlar.
    assert 'doc["pwm_active"]' in s3_status, "S3 status'tan pwm_active düşmüş — backend `running`i türetemez"
    assert '\\"pwm_active\\":' in e8_status, "8266 status'tan pwm_active düşmüş — backend `running`i türetemez"
    # (2) 8266'nın AYRI `sensors` yayını YAŞAMALI — backend bobin 8'in current/ambient'ini oradan
    #     okur; 8266 de S3 gibi sensors'ı kaldırırsa (UYUMSUZ-6 deseni) alanlar sessizce 0'a düşer.
    #     (8266 status'u current/ambient TAŞIMAZ — kaldırma ancak status'a eklemekle birlikte yapılabilir;
    #     o gün bu iki iddiadan biri kırmızıya döner ve sözleşme bilinçli güncellenir.)
    e8_sensors = _fonksiyon_govdesi(e8, "void NetworkManager::publishSensorData")
    assert "_sensorTopic" in e8_sensors and '\\"current\\":' in e8_sensors, (
        "8266 publishSensorData sensors yayınını/current alanını kaybetmiş — bobin 8 current/ambient kaynağı yok"
    )
    e8_ino = _fw_oku("firmware", "esp8266_pemf_coil", "esp8266_pemf_coil.ino")
    assert "publishSensorData(" in e8_ino, "8266 .ino artık publishSensorData çağırmıyor — sensors yayını ölü"
