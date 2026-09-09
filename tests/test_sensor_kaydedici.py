# -*- coding: utf-8 -*-
# Author: mertaygn
"""SENSÖR TELEMETRİSİ YEREL KAYIT — sahip kararı: "bilgisayar tarafı" + "her zaman açık".

⚠️ TEST YÜKLERİ UYDURMA DEĞİL: aşağıdaki `S3_STATUS` gövdesi 2026-09-09'da yerel broker'dan
`mosquitto_sub -t pemf/coil/6/status` ile YAKALANDI. Uydurma bir yük, S3'ün gerçek şemasını
(sensör değerlerinin `sensors` DEĞİL `status` içinde gelmesi) gizlerdi — kaydedici testte
yeşil, sahada boş dosya üretirdi.

ÖLÇÜLEN ŞEMA GERÇEĞİ: S3 hiç `sensors` yayınlamaz (UYUMSUZ-6); sensör alanları `status`
içindedir. 8266 ise ayrıca `sensors` yayınlar ve duty'yi `pwm_duty_cycle` adıyla verir.
Kaydedici ikisini de aynı sütunlara indirmek zorunda.

⚠️ `mag_x/mag_y/mag_z`: bobin YÖNÜ (polarite) ölçümünün tek taşıyıcısı. Yakalanan gerçek yükte
`mag_x` SIFIR kez geçiyordu → yön verisi MQTT'ye hiç çıkmıyordu; S3 firmware'ine bu alanlar
eklendi ve aşağıdaki parite testi bunu kilitler. Skaler `magnetic_field` yön TAŞIMAZ.
"""

from __future__ import annotations

import importlib
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]

#: 2026-09-09, `mosquitto_sub -h 127.0.0.1 -t 'pemf/coil/6/status' -v` ile YAKALANDI.
S3_STATUS = json.loads(
    '{"coil_id":6,"fw_version":"3.1.0","msg_type":"status","timestamp":1788956665732,'
    '"uptime":2060001,"wifi_connected":true,"wifi_ssid":"PEMF-Gateway","wifi_rssi":-49,'
    '"wifi_ip":"192.168.137.146","portal_active":false,"portal_ip":"","portal_ssid":"",'
    '"mqtt_connected":true,"broker_type":"local","pwm_active":false,"pwm_frequency":1000,'
    '"pwm_duty":50,"pwm_remaining_time":0,"pwm_start_timestamp":0,"pwm_duration":0,'
    '"object_temp":23.41,"ambient_temp":24.13,"magnetic_field":0.030,"current":0.56,'
    '"max_magnetic_field":0.000,"max_current":0.00,"sensors_ok":true,"temp_sensor_ok":true,'
    '"magnetic_sensor_ok":true,"current_sensor_ok":true,"sync_fallback_event":false,'
    '"free_heap":21648,"max_alloc_heap":20056,"fragmentation":8}'
)

#: 8266'nın `sensors` yükü (kaynaktaki biçim dizesinden birebir).
ESP8266_SENSORS = {
    "coil_id": 8,
    "timestamp": 123456,
    "object_temp": 23.51,
    "ambient_temp": 23.55,
    "magnetic_field": 0.047,
    "current": 0.03,
    "temp_sensor_ok": True,
    "magnetic_sensor_ok": True,
    "current_sensor_ok": False,
    "sensors_ok": True,
}


@pytest.fixture()
def mod(tmp_path, monkeypatch):
    """Kaydediciyi İZOLE dizinde taze yükle (gerçek veri köküne ASLA yazma)."""
    monkeypatch.setenv("PEMF_SENSOR_LOG_DIR", str(tmp_path / "sensor_log"))
    monkeypatch.setenv("PEMF_SENSOR_LOG", "1")
    monkeypatch.delenv("PEMF_SENSOR_LOG_DAYS", raising=False)
    monkeypatch.delenv("PEMF_SENSOR_LOG_MB", raising=False)
    import servers.sensor_kaydedici as sk

    importlib.reload(sk)
    yield sk
    try:
        sk.kaydedici().kapat()
    except Exception:
        pass


def _satirlar(dizin: Path, sk=None) -> list[list[str]]:
    """Dosyayı oku. ⚠️ ÖNCE flush: yazımlar tamponlu (bkz. `flush` docstring'i) — flush'sız
    okuma son saniyelerin satırlarını GÖRMEZ ve test sahte kırmızı verir."""
    if sk is not None:
        sk.kaydedici().flush()
    dosyalar = sorted(dizin.glob("sensor_*.csv"))
    assert dosyalar, f"CSV uretilmemis: {dizin}"
    metin = dosyalar[-1].read_text(encoding="utf-8").strip().splitlines()
    return [s.split(",") for s in metin]


# ══ 1) GERÇEK YÜKLER KAYDA GEÇİYOR ═════════════════════════════════════════════════════════
def test_KRITIK_S3_STATUS_yuku_kayda_geciyor(mod, tmp_path):
    """S3'ün GERÇEK `status` yükü satır üretmeli.

    ⚠️ Bu testin var olma sebebi: kaydedici yalnız `sensors` dinlerse S3 bobinleri için
    (dolaptaki bobin 6-7) BOŞ dosya üretir ve kimse fark etmez — panel canlı çalışmaya devam
    ettiği için "kayıt da çalışıyor" sanılır.
    """
    assert mod.kaydet(6, "status", S3_STATUS) is True
    satirlar = _satirlar(tmp_path / "sensor_log", mod)
    assert satirlar[0] == list(mod.SUTUNLAR), "basli satir sutun listesiyle uyusmuyor"
    assert len(satirlar) == 2, satirlar
    kayit = dict(zip(mod.SUTUNLAR, satirlar[1]))
    assert kayit["bobin"] == "6"
    assert kayit["msg_type"] == "status"
    assert kayit["fw"] == "3.1.0"
    assert kayit["temp_object"] == "23.41"
    assert kayit["magnetic_field"] == "0.03"
    assert kayit["current"] == "0.56"
    assert kayit["pwm_duty"] == "50", "S3 `pwm_duty` adini kullanir"
    assert kayit["sensors_ok"] == "1" and kayit["current_sensor_ok"] == "1"
    assert kayit["cihaz_ts_ms"] == "1788956665732", "cihazin kendi damgasi kaybolmus"
    assert kayit["ts_epoch_ms"].isdigit() and len(kayit["ts_epoch_ms"]) >= 13


def test_KRITIK_8266_SENSORS_yuku_AYNI_sutunlara_dusuyor(mod, tmp_path):
    """İki firmware ailesi farklı ad kullanıyor; kayıt tek şemaya indirmeli.

    8266 duty'yi `pwm_duty_cycle`, S3 `pwm_duty` diye yayınlar. Ayrı sütunlara düşerlerse
    analiz iki yarım kolonla uğraşır (ve kimse fark etmez).
    """
    mod.kaydet(8, "sensors", ESP8266_SENSORS)
    mod.kaydet(8, "status", {"pwm_duty_cycle": 30, "pwm_active": True, "uptime": 999})
    satirlar = _satirlar(tmp_path / "sensor_log", mod)
    assert len(satirlar) == 3
    ilk = dict(zip(mod.SUTUNLAR, satirlar[1]))
    ikinci = dict(zip(mod.SUTUNLAR, satirlar[2]))
    assert ilk["msg_type"] == "sensors" and ilk["temp_object"] == "23.51"
    assert ilk["current_sensor_ok"] == "0", "bool False '0' olarak yazilmali"
    assert ikinci["pwm_duty"] == "30", "8266 `pwm_duty_cycle` -> `pwm_duty` sutununa dusmeli"


def test_KRITIK_mag_EKSENLERI_sutun_olarak_VAR(mod, tmp_path):
    """Eksen bileşenleri kayda geçmeli — yönün tek taşıyıcısı.

    ⚠️ Skaler `magnetic_field` yön TAŞIMAZ (|B| her zaman pozitif). Eksenler sütun olarak
    yoksa iki günlük polarite çalışması kayda hiç girmez.
    """
    for s in ("mag_x", "mag_y", "mag_z"):
        assert s in mod.SUTUNLAR, f"{s} sutun listesinde YOK"
    mod.kaydet(6, "status", {**S3_STATUS, "mag_x": -0.038, "mag_y": 0.084, "mag_z": -2.267})
    kayit = dict(zip(mod.SUTUNLAR, _satirlar(tmp_path / "sensor_log", mod)[1]))
    assert kayit["mag_z"] == "-2.267", kayit["mag_z"]
    assert kayit["mag_x"] == "-0.038"


def test_olculmeyen_alan_BOS_kalir_sifir_DEGIL(mod, tmp_path):
    """Firmware bir alanı yayınlamıyorsa sütun BOŞ kalmalı, `0` OLMAMALI.

    ⚠️ `0` yazmak "ölçüldü ve sıfır" demektir; eksen sıfırı polarite analizinde GERÇEK bir
    sonuçtur. "ölçülmedi" ile "sıfır ölçüldü" karışırsa yanlış karar verilir.
    """
    mod.kaydet(6, "status", S3_STATUS)  # bu yukte mag_x YOK
    kayit = dict(zip(mod.SUTUNLAR, _satirlar(tmp_path / "sensor_log", mod)[1]))
    assert kayit["mag_x"] == "", f"olculmeyen eksen '{kayit['mag_x']}' olarak yazilmis"


# ══ 2) DAYANIKLILIK — canlı akışı ASLA bozmamalı ═══════════════════════════════════════════
def test_KRITIK_HATA_MQTT_yoluna_SIZMAZ(mod, monkeypatch):
    """Dosya yazımı patlasa bile `kaydet` False döner, FIRLATMAZ.

    ⚠️ Bu fonksiyon MQTT işleyicisinden çağrılıyor; bir istisna canlı durum güncellemesini,
    paneli ve E-stop görünürlüğünü bozardı. Telemetri kaydı bir kolaylıktır, koşul değil.
    """
    k = mod.kaydedici()

    def _patla(*a, **kw):
        raise OSError("disk dolu (sentetik)")

    monkeypatch.setattr(k, "_dosyayi_hazirla", _patla)
    assert mod.kaydet(6, "status", S3_STATUS) is False
    assert k.atilan >= 1, "atilan sayaci artmadi -> sessiz kayip olcusuz kalir"


def test_kapatma_anahtari(mod, monkeypatch, tmp_path):
    """`PEMF_SENSOR_LOG=0` kaydı tamamen durdurmalı (kaçış kapağı)."""
    monkeypatch.setenv("PEMF_SENSOR_LOG", "0")
    assert mod.kaydet(6, "status", S3_STATUS) is False
    assert not list((tmp_path / "sensor_log").glob("sensor_*.csv"))


def test_ilgisiz_mesaj_tipi_KAYDEDILMEZ(mod, tmp_path):
    """`ack`/`events` gibi tipler sensör satırı üretmemeli (dosya kirlenmesin)."""
    assert mod.kaydet(6, "ack", {"success": True}) is False
    assert mod.kaydet(6, "events", {"event_type": "offline"}) is False
    assert not list((tmp_path / "sensor_log").glob("sensor_*.csv"))


# ══ 3) DİSK DOLMASI YAPISAL OLARAK ENGELLİ ═════════════════════════════════════════════════
def test_KRITIK_GUN_SINIRI_eski_dosyalari_siliyor(mod, tmp_path, monkeypatch):
    """Retention: gün sınırından eski dosyalar silinmeli.

    "Her zaman açık" kaydın en gerçek riski diskin sessizce dolmasıdır.
    """
    dizin = tmp_path / "sensor_log"
    dizin.mkdir(parents=True)
    eski = datetime.now() - timedelta(days=40)
    (dizin / f"sensor_{eski.strftime('%Y-%m-%d')}.csv").write_text("x\n", encoding="utf-8")
    yeni = datetime.now() - timedelta(days=1)
    (dizin / f"sensor_{yeni.strftime('%Y-%m-%d')}.csv").write_text("x\n", encoding="utf-8")

    mod.kaydet(6, "status", S3_STATUS)  # ilk yazim retention'i tetikler
    kalanlar = {p.name for p in dizin.glob("sensor_*.csv")}
    assert f"sensor_{eski.strftime('%Y-%m-%d')}.csv" not in kalanlar, "40 gunluk dosya SILINMEDI"
    assert f"sensor_{yeni.strftime('%Y-%m-%d')}.csv" in kalanlar, "1 gunluk dosya silinmis (fazla agresif)"


def test_KRITIK_BOYUT_TAVANI_uygulaniyor(mod, tmp_path, monkeypatch):
    """Toplam boyut tavanı: tavan aşılırsa en ESKİ dosyalar silinmeli.

    ⚠️ Yalnız gün sınırı yetmez: 3 bobin × 1 Hz ≈ 16 MB/gün ölçüldü; yoğun bir tezgâh günü
    ya da daha hızlı yayın tavanı gün sınırından ÖNCE aşar.
    """
    monkeypatch.setenv("PEMF_SENSOR_LOG_MB", "1")
    importlib.reload(mod)
    dizin = tmp_path / "sensor_log"
    dizin.mkdir(parents=True, exist_ok=True)
    for gun_geri in (5, 4, 3):
        d = datetime.now() - timedelta(days=gun_geri)
        (dizin / f"sensor_{d.strftime('%Y-%m-%d')}.csv").write_bytes(b"a" * 700_000)
    onceki = sum(p.stat().st_size for p in dizin.glob("sensor_*.csv"))
    assert onceki > 1024 * 1024, "sentetik kurulum tavanin altinda -> test anlamsiz"

    mod.kaydet(6, "status", S3_STATUS)
    sonraki = sum(p.stat().st_size for p in dizin.glob("sensor_*.csv"))
    assert sonraki <= 1024 * 1024 + 4096, f"boyut tavani UYGULANMADI: {sonraki} bayt"


def test_HASTA_VERITABANINA_yazmiyor(mod, tmp_path):
    """Telemetri hasta/seans DB'sine GİRMEMELİ.

    ⚠️ `headless_db_maintenance` o DB'ye retention + PII-maskeleme + YEDEKLEME uyguluyor;
    16 MB/gün telemetri her yedeği şişirir ve tıbbi kaydın geri-yükleme süresini bozar.
    """
    kaynak = (KOK / "servers" / "sensor_kaydedici.py").read_text(encoding="utf-8")
    for yasak in ("treatment_history", "patients.db", "sqlite3", "session_manager"):
        assert yasak not in kaynak, f"kaydedici hasta DB yoluna dokunuyor: {yasak}"


# ══ 4) BAĞLANTI GERÇEKTEN KURULU MU (sessiz ölüm kapısı) ═══════════════════════════════════
def test_KRITIK_MQTT_isleyicisi_kaydediciyi_CAGIRIYOR():
    """Modül var olup çağrılmazsa hiçbir şey kaydedilmez ve hata da görünmez.

    Kapı çağrının VARLIĞINI ve `is_retained` kapısının İÇİNDE olmasını ölçer: retained
    mesajlar her reconnect'te yeniden teslim edilir ve geçmişe SAHTE tekrar satırları yazardı.
    """
    kaynak = (KOK / "servers" / "api_server.py").read_text(encoding="utf-8")
    assert "sensor_kaydedici" in kaynak, "kaydedici api_server'a import EDILMEMIS"
    assert "_sensor_kaydedici.kaydet(" in kaynak, "kaydedici CAGRILMIYOR -> sessiz olu modul"
    i = kaynak.index("_sensor_kaydedici.kaydet(")
    onceki = kaynak[max(0, i - 400) : i]
    assert "if not is_retained:" in onceki, "cagri retained kapisinin ICINDE degil"


def test_KRITIK_S3_firmware_mag_eksenlerini_YAYINLIYOR():
    """S3 status JSON'u `mag_x/mag_y/mag_z` taşımalı — yoksa kayıtta yön sütunları boş kalır.

    Yakalanan gerçek yükte `mag_x` SIFIR kez geçiyordu; bu kapı o eksiğin geri gelmesini
    engeller.
    """
    nm = KOK / "firmware" / "esps3_pemf_coil" / "NetworkManager.cpp"
    if not nm.exists():
        pytest.skip("firmware/ agaci yok")
    kaynak = nm.read_text(encoding="utf-8", errors="replace")
    for alan, ic in (("mag_x", "magX"), ("mag_y", "magY"), ("mag_z", "magZ")):
        assert f'doc["{alan}"]' in kaynak, f"S3 status JSON'unda {alan} YOK"
        i = kaynak.index(f'doc["{alan}"]')
        assert ic in kaynak[i : i + 80], f"{alan} sensors.{ic}'den turemiyor"
