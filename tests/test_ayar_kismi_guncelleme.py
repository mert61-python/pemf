# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KISMİ AYAR POST'U GÖNDERİLMEYEN ALANLARI SİLİYORDU (denetim 2026-08-17).

`SettingsModel` tüm alanlara varsayılan verdiği ve `payload.dict()` DAİMA 4 anahtar taşıdığı için
`/api/settings/` POST'u, gönderilmeyen her alanı MODEL VARSAYILANINA döndürüyordu:

  · **CANLI KAYIP:** `clinic_name`i hiç göndermeyen arayüz (pf `SettingsScreen`in "Kaydet" düğmesi)
    onu HER kayıtta `system_settings.json`dan siliyordu.
  · Yalnız `clinic_name` gönderen bir istemci MQTT broker ayarını sessizce `localhost:1883`e
    döndürüyordu — ESP bobinleri (6-8) broker'ı bu ayardan buluyor.

⚠️ DENETİM RAPORUM BURADA YANILIYORDU: "frontend'de bu POST'un çağrıldığı yer bulunamadı" demiştim.
Çağıran VAR — `apiClient` `/api` önekini kendisi eklediği ve çağrı `"/settings/"` yazdığı için
`api/settings` araması onu kaçırmış.

⚠️ `save_settings` ZATEN kısmi sözlüğe göre yazılmış (`if "mqtt_broker" in data` gibi kapıları var);
eksik olan tek şey ona kısmi sözlüğü VERMEKTİ.
"""

import json
import os

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.testclient import TestClient


class _SahteConfig:
    """Bellek-içi üretim yapılandırması.

    ⚠️ ZORUNLU — ACI DERS (2026-08-17): ilk yazımda bu mock YOKTU ve test GERÇEK
    `%APPDATA%\PEMF_GUI\config.json`i EZDİ. Mekanizma sinsi: dosya ACL ile SYSTEM+Admin'e
    kilitli olduğu için `load` "Permission denied" ile DÜŞÜYOR ve yönetici sessizce
    VARSAYILANLARA dönüyor; ama `save` `tmp + os.replace` kullandığı ve DİZİN yazılabilir olduğu
    için BAŞARILI oluyor → kullanıcının override'ları (MQTT broker/port) siliniyor.
    Yani "okuyamıyorum" hatası "yazamıyorum" anlamına GELMİYOR."""

    def __init__(self):
        self._d = {"mqtt.broker_url": "localhost", "mqtt.broker_port": 1883}
        self.kaydedildi = 0

    def get(self, anahtar, varsayilan=None):
        return self._d.get(anahtar, varsayilan)

    def set(self, anahtar, deger, save=True):
        self._d[anahtar] = deger

    def save(self):
        self.kaydedildi += 1
        return True


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Ayar dosyasını VE üretim yapılandırmasını tmp'ye/belleğe yönlendir."""
    from servers import settings_router

    monkeypatch.setattr(settings_router, "_settings_file", tmp_path / "system_settings.json")
    sahte = _SahteConfig()
    monkeypatch.setattr(settings_router, "get_production_config", lambda: sahte)

    from servers import api_server

    # SERT KAPI: gerçek yapılandırmaya dokunma ihtimali sıfırlanmadan devam etme.
    assert settings_router.get_production_config() is sahte
    assert str(tmp_path) in str(settings_router._settings_file)

    return TestClient(api_server.app, client=("127.0.0.1", 51234)), settings_router


def test_KRITIK_gonderilmeyen_alan_KORUNUR(client):
    """Yalnız `clinic_name` gönderen bir istek MQTT ayarını DEĞİŞTİRMEMELİ."""
    c, sr = client

    sr.save_settings({"clinic_name": "Eski Klinik", "mqtt_broker": "192.168.137.1", "mqtt_port": "1884"})
    assert c.post("/api/settings/", json={"clinic_name": "Yeni Klinik"}).status_code == 200

    son = sr.load_settings()
    assert son.get("clinic_name") == "Yeni Klinik", f"gonderilen alan yazilmadi: {son}"
    assert son.get("mqtt_broker") == "192.168.137.1", (
        f"MQTT broker sessizce localhost'a dondu -> ESP bobinleri (6-8) broker'i bulamaz: {son}"
    )
    assert son.get("mqtt_port") == "1884", f"MQTT portu sessizce degisti: {son}"


def test_KRITIK_clinic_name_HER_KAYITTA_silinmez(client):
    """Arayüzün "Kaydet"i `clinic_name` göndermiyor; onu silmemeli (canlı kayıp)."""
    c, sr = client

    sr.save_settings({"clinic_name": "Minnos Veteriner", "mqtt_broker": "10.0.0.5", "mqtt_port": "1883"})
    assert c.post("/api/settings/", json={"mqtt_broker": "10.0.0.9"}).status_code == 200

    son = sr.load_settings()
    assert son.get("clinic_name") == "Minnos Veteriner", (
        f"clinic_name HER kayitta siliniyor (arayuz onu hic gondermiyor): {son}"
    )
    assert son.get("mqtt_broker") == "10.0.0.9", "gonderilen alan yazilmadi"


def test_KARSIT_KANIT_gonderilen_alan_BOSALTILABILIR(client):
    """Karşıt-kanıt: yama "hiç değiştirme"ye dönüşmemeli — AÇIKÇA gönderilen boş değer yazılmalı."""
    c, sr = client

    sr.save_settings({"clinic_name": "Dolu", "mqtt_broker": "10.0.0.5", "mqtt_port": "1883"})
    assert c.post("/api/settings/", json={"clinic_name": ""}).status_code == 200

    assert sr.load_settings().get("clinic_name") == "", "acikca gonderilen bos deger yazilmadi"


def test_KARSIT_KANIT_TAM_govde_hala_hepsini_yazar(client):
    """Karşıt-kanıt: dört alanı da gönderen eski bir istemci aynen çalışmaya devam etmeli."""
    c, sr = client

    sr.save_settings({"clinic_name": "Eski", "mqtt_broker": "10.0.0.5", "mqtt_port": "1883"})
    r = c.post(
        "/api/settings/",
        json={"clinic_name": "Tam", "mqtt_broker": "10.0.0.7", "mqtt_port": "1885"},
    )
    assert r.status_code == 200

    son = sr.load_settings()
    assert son.get("clinic_name") == "Tam"
    assert son.get("mqtt_broker") == "10.0.0.7"
    assert son.get("mqtt_port") == "1885"


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
