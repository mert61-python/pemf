# Author: mertaygn, cglrgrkn
"""GÖZETİMSİZ ENERJİLENDİRME SINIRI — ESP TARAFI (bobin 6-8).

DENETİM BULGUSU (2026-08-17). 1.9.14'te eklenen klinik kapak (`GOZETIMSIZ_VARSAYILAN_DAKIKA = 120`)
yalnız `controllers/hardware_controller.py` içinde, yani **8 bobinin 5'inde** yaşıyordu. ESP dalı
(`/api/coil/{id}/control` ve `/api/coil/batch`) `payload.duration`'ı HAM iletiyordu.

Neden bu bir kusur:
  * `duration = 0` bu projenin KENDİ protokol sözleşmesinde **"süresiz"** demektir —
    `firmware/main.c:195` (`uint32_t dur_min; /**< Süre (dakika): 0 = süresiz */`) ve
    `controllers/hardware_controller.py` ("duration=0 → sinirsiz").
  * STM yolu bu nöbetçiyi bilerek 120 dakikaya çevirir; ESP yolu onu olduğu gibi iletiyordu.
  * ESP bobinlerinde sunucu tarafında hiçbir son-tarih/watchdog yok: `_coil_deadline` yalnız
    `range(1, 6)`, seans açılmadığı için `_session_duration_watchdog` kapsam dışı,
    `_esp_telemetry_watchdog` yalnız telemetri SUSARSA devreye girer.
  * Arayüz operatöre "bobin donanım üst-sınırına kadar çalışır" diye güvence veriyordu; ESP
    firmware'i (`CoilController.cpp`) bu depoda DEĞİL, yani o güvencenin dayanağı yoktu.

⚠️ Bu sınır yalnız SÜREdir. freq/duty/48°C safety-limit'leri sahip kararıyla kaldırıldı ve GERİ
EKLENMEZ (bkz. `tests/test_gozetimsiz_enerjilendirme.py` başlığı).

⚠️ `duration = 0` GEÇERLİ bir girdi olarak KALIR (aşağıda karşı-kanıt var) — reddedilmez, yalnız
sonsuz sürmez. Reddetmek Kontrol Paneli'ni bozardı.
"""

import os

os.environ.pop("PEMF_SIMULATE", None)

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from controllers.hardware_controller import GOZETIMSIZ_VARSAYILAN_DAKIKA  # noqa: E402

BEKLENEN_KAPAK_SN = GOZETIMSIZ_VARSAYILAN_DAKIKA * 60


@pytest.fixture(scope="module")
def api():
    from servers import api_server

    return api_server


@pytest.fixture(scope="module")
def client(api):
    return TestClient(api.app)


@pytest.fixture()
def yayinlar(api, monkeypatch):
    """ESP'ye giden MQTT payload'larını yakalar (topic + gövde)."""
    kayit = []

    def _fake_publish(topic, payload):
        kayit.append({"topic": topic, "payload": payload})
        return True

    monkeypatch.setattr(api, "_mqtt_publish", _fake_publish)
    # Bu testler süre kapağını sınıyor; coil-run DB yan etkisi konu dışı.
    monkeypatch.setattr(api, "_begin_coil_run", lambda *a, **k: None)
    monkeypatch.setattr(api, "_finish_coil_run", lambda *a, **k: None)
    with api._session_lock:
        api._active_session.clear()
    return kayit


def _start_yayini(kayit):
    """Kayıttaki tek `start` komutunu döndürür."""
    startlar = [k for k in kayit if k["payload"].get("command") == "start"]
    assert len(startlar) == 1, f"tam bir start yayini beklendi, gelen: {kayit}"
    return startlar[0]["payload"]


def test_KRITIK_ESP_sure_verilmeden_baslatilan_bobin_KAPAKLANIR(client, yayinlar):
    """`duration=0` ile başlatılan ESP bobini SONSUZ sürmemeli — klinik kapak uygulanmalı."""
    r = client.post("/api/coil/6/control", json={"freq": 50, "duty": 25, "start": True})
    assert r.status_code == 200
    assert r.json()["transport"] == "mqtt"

    gonderilen = _start_yayini(yayinlar)["duration"]
    assert gonderilen == BEKLENEN_KAPAK_SN, (
        f"ESP bobini {gonderilen} sn ile baslatildi. `0` bu projenin sozlesmesinde SURESIZ demektir "
        f"(firmware/main.c: '0 = süresiz') ve ESP tarafinda sunucu-yanli hicbir watchdog yok → "
        f"gozetimsiz enerjilendirme. Beklenen klinik kapak: {BEKLENEN_KAPAK_SN} sn."
    )


def test_KRITIK_ESP_batch_yolunda_da_KAPAKLANIR(client, yayinlar):
    """Toplu yol (`/api/coil/batch`) tek-bobin yoluyla AYNI kapağı uygulamalı.

    Bu ayrı bir test çünkü depo bu sınıfta bir kez yandı: 2026-08-12'de AI zaman aşımı düzeltmesi
    `apiPost` yolunda yapılıp ham `fetch` kullanan 10 modül atlanmıştı ("kısmi düzeltme,
    düzeltilmemiş demektir")."""
    r = client.post("/api/coil/batch", json={"coil_ids": [7], "freq": 50, "duty": 25, "start": True})
    assert r.status_code == 200

    gonderilen = _start_yayini(yayinlar)["duration"]
    assert gonderilen == BEKLENEN_KAPAK_SN, (
        f"batch yolu {gonderilen} sn gonderdi — tek-bobin yolu kapakli ama batch kapaksiz kalmis."
    )


def test_ACIK_verilen_sure_DEGISTIRILMEZ_karsit_kanit(client, yayinlar):
    """Karşı-kanıt: operatör AÇIKÇA bir süre verdiyse ona dokunulmaz.

    Kapak yalnız "süre belirtilmedi" nöbetçisini (0) değiştirir; bu yeni bir üst-sınır DEĞİLDİR."""
    r = client.post("/api/coil/6/control", json={"freq": 50, "duty": 25, "duration": 300, "start": True})
    assert r.status_code == 200
    assert _start_yayini(yayinlar)["duration"] == 300


def test_sifir_sure_hala_KABUL_edilir_karsit_kanit(client, yayinlar):
    """Karşı-kanıt: `duration=0` REDDEDİLMEZ (422 dönmez) — yalnız sonsuz sürmez.

    `tests/test_gozetimsiz_enerjilendirme.py::test_sifir_sure_hala_KABUL_edilir_karsit_kanit` ile
    aynı değişmezin ESP karşılığı."""
    r = client.post("/api/coil/6/control", json={"freq": 20, "duty": 30, "duration": 0, "start": True})
    assert r.status_code == 200


def test_STOP_komutunda_sure_alani_HIC_gonderilmez_karsit_kanit(client, yayinlar):
    """Karşı-kanıt: kapak yalnız `start` yolunda. STOP payload'ı süre taşımaz ve taşımamalı."""
    r = client.post("/api/coil/6/control", json={"freq": 0, "duty": 0, "duration": 0, "start": False})
    assert r.status_code == 200
    stoplar = [k for k in yayinlar if k["payload"].get("command") == "stop"]
    assert len(stoplar) == 1
    assert "duration" not in stoplar[0]["payload"]


def test_kapak_STM_ile_AYNI_KAYNAKTAN_gelir():
    """Yapısal kapı: ESP kapağı kendi sabitini TAŞIMAMALI.

    İki transport ayrı sabit kullanırsa klinik sınır bir gün yalnız birinde güncellenir — bu
    bulgunun kök nedeni tam olarak buydu. `servers/api_server.py` kapağı
    `controllers.hardware_controller.GOZETIMSIZ_VARSAYILAN_DAKIKA`'dan türetmelidir."""
    kaynak = (Path(__file__).resolve().parent.parent / "servers" / "api_server.py").read_text(encoding="utf-8")
    assert "GOZETIMSIZ_VARSAYILAN_DAKIKA" in kaynak, (
        "ESP kapagi klinik sabiti TEK KAYNAKTAN okumuyor — ayri bir sayi yazilmis olabilir."
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
