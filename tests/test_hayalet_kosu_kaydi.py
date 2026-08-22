# Author: mertaygn, cglrgrkn
"""HAYALET KOŞU KAYDI — 2. tur denetimi bulgu [4.5] (2026-08-20).

ÖLÇÜLEN DURUM: `_begin_coil_run` (doz/tedavi geçmişindeki per-bobin koşu satırı) teslim/kabul
sonucundan BAĞIMSIZ açılıyordu: ESP yolunda `_mqtt_publish` False dönse (broker ölü — komut
KESİN gitmedi) bile, STM yolunda `update_coil` False dönse (parametre reddedildi — bobin
sürülmedi) bile tedavi geçmişine "bobin koştu" yazılıyordu. Doz kaydının bütün amacı NE
UYGULANDIĞINI belgelemekti (4. tur "doz kaydı" kararının ruhu); hiç koşmamış bobinin satırı
yanlış klinik kayıttır.

SÖZLEŞME: koşu kaydı yalnız SONUCU BİLİNEN ve BAŞARILI yollarda açılır (tek-bobin + batch;
STM=update_coil dönüşü, ESP=publish doğrulaması). STOP'ta `_finish_coil_run` publish düşse bile
ÇAĞRILMAYA DEVAM EDER (açık koşuyu kapatmak güvenli taraftır; fiziksel-durmama uyarısı [1.1]'in
işi). Seans yolunun ESP yayını BİLEREK arka planda (snappy start) — orada sonuç bilinemez,
davranış değişmedi (kayıtlı bilinçli karar).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(scope="module")
def api():
    from servers import api_server

    return api_server


@pytest.fixture(scope="module")
def client(api):
    return TestClient(api.app)


class _SahteStm:
    def __init__(self, sonuc: bool):
        self.sonuc = sonuc
        self.cagrilar: list = []

    def update_coil(self, coil_id, freq, duty, phase, dur_min, start=True, **kw):
        self.cagrilar.append((coil_id, start))
        return self.sonuc


@pytest.fixture()
def izleyiciler(api, monkeypatch):
    """begin/finish çağrılarını yakala; yan-etkili kanalları sustur."""
    beginler: list = []
    finisler: list = []
    monkeypatch.setattr(api, "_begin_coil_run", lambda cid, f, d, p, i, t: beginler.append((cid, t)))
    monkeypatch.setattr(api, "_finish_coil_run", lambda cid: finisler.append(cid))
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)
    return beginler, finisler


def test_KRITIK_esp_publish_dusunce_kosu_kaydi_ACILMAZ(api, client, izleyiciler, monkeypatch):
    beginler, _f = izleyiciler
    monkeypatch.setattr(api, "_mqtt_publish", lambda t, p: False)  # broker ölü — komut KESİN gitmedi

    r = client.post("/api/coil/6/control", json={"freq": 50, "duty": 25, "phase": 0, "duration": 60, "start": True})
    assert r.json().get("status") == "mqtt_unavailable"
    assert beginler == [], f"komut hiçbir yere gitmedi ama tedavi geçmişine koşu yazıldı: {beginler!r} (bulgu [4.5])"


def test_KARSIT_KANIT_esp_publish_dogrulaninca_kosu_ACILIR(api, client, izleyiciler, monkeypatch):
    beginler, _f = izleyiciler
    monkeypatch.setattr(api, "_mqtt_publish", lambda t, p: True)

    r = client.post("/api/coil/6/control", json={"freq": 50, "duty": 25, "phase": 0, "duration": 60, "start": True})
    assert r.json().get("status") == "success"
    assert beginler == [(6, "esp")], f"başarılı start koşu kaydı açmadı: {beginler!r}"


def test_KRITIK_stm_reddi_kosu_kaydi_ACMAZ_ve_success_DEMEZ(api, client, izleyiciler, monkeypatch):
    beginler, _f = izleyiciler
    monkeypatch.setattr(api.state, "hardware", _SahteStm(sonuc=False))  # parametre reddi

    r = client.post("/api/coil/2/control", json={"freq": 50, "duty": 25, "phase": 0, "duration": 60, "start": True})
    assert beginler == [], f"STM start REDDEDİLDİ ama koşu kaydı açıldı: {beginler!r}"
    assert r.json().get("status") != "success", (
        f"STM start reddi 'success' olarak bildirildi — operatör bobin sürülüyor sanır: {r.json()!r}"
    )


def test_KARSIT_KANIT_stm_kabulu_kosu_ACILIR_success(api, client, izleyiciler, monkeypatch):
    beginler, _f = izleyiciler
    monkeypatch.setattr(api.state, "hardware", _SahteStm(sonuc=True))

    r = client.post("/api/coil/2/control", json={"freq": 50, "duty": 25, "phase": 0, "duration": 60, "start": True})
    assert r.json().get("status") == "success"
    assert beginler == [(2, "stm")]


def test_KRITIK_batch_yalniz_BASARILI_bobinlere_kosu_yazar(api, client, izleyiciler, monkeypatch):
    beginler, _f = izleyiciler
    monkeypatch.setattr(api.state, "hardware", _SahteStm(sonuc=False))  # STM reddediyor
    monkeypatch.setattr(api, "_mqtt_publish", lambda t, p: True)  # ESP teslim ediliyor

    r = client.post(
        "/api/coil/batch",
        json={"coil_ids": [2, 6], "freq": 50, "duty": 25, "phase": 0, "duration": 60, "start": True},
    )
    satirlar = {s["coilId"]: s["status"] for s in r.json()["results"]}
    assert beginler == [(6, "esp")], f"batch'te koşu kaydı yanlış küme: {beginler!r}"
    assert satirlar[6] == "success"
    assert satirlar[2] != "success", f"STM reddi batch satırında 'success' görünüyor: {satirlar!r}"


def test_KARSIT_KANIT_stop_publish_dusse_de_kosu_KAPATILIR(api, client, izleyiciler, monkeypatch):
    """Açık koşuyu KAPATMAK güvenli taraftır (kayıt sızdırmaz); fiziksel-durmama uyarısı [1.1]'de.
    STOP'ta finish, publish sonucundan bağımsız çağrılmaya devam etmeli."""
    _b, finisler = izleyiciler
    monkeypatch.setattr(api, "_mqtt_publish", lambda t, p: False)

    client.post("/api/coil/6/control", json={"freq": 0, "duty": 0, "phase": 0, "duration": 0, "start": False})
    assert finisler == [6], f"STOP'ta koşu kapatılmadı (kayıt açık sızar): {finisler!r}"
