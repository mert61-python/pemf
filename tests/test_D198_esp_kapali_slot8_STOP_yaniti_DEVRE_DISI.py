# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.98 · B-6.9 (+ İG-6.45) — backend yarısı: ESP BİLEREK kapalıyken slot 8 STOP yanıtı "devre_disi" der.

ÖLÇÜLEN KUSUR (06-2 g5a/g5b, aday doğrulaması İG-6.45): `PEMF_ESP_ENABLED` ayarsızken (HEAD varsayılanı) Kontrol
ekranının her başarılı "⏹ Durdur"u sahte "Durdurma onaylanamadı — bobinler HÂLÂ ÇALIŞIYOR olabilir" alarmı veriyordu:
slot 8'e giden STOP'un yanıtı `mqtt_unavailable`dı — "broker ölü" ile "ESP bilerek kapalı" AYNI dize. Alarm körlüğü
gerçek teyitsizliği değersizleştirir (K4).

SAHİP KARARLARI: slot 8 STOP kümesinde KOŞULSUZ kalır (gönderim azaltılmaz, Ö.4-Y8; plan orkestratör notu). Teyit
ölçütü A-63: ESP kapalıyken teyit STM'e göre. Bu kapı yalnız YANITIN dürüst ayrılmasını ölçer: ESP kapalı → `devre_disi`
(yine de `_mqtt_publish` DENENİR); ESP açık + yayın başarısız → `mqtt_unavailable` KALIR (gerçek arıza alarmı).

Arayüz fikstürü `apps/ui/src/screens/__tests__/__fixtures__/espSlot8Durdurma.json` GERÇEK uçlardan üretilir;
bayatlarsa `test_arayuz_fiksturu_GERCEK_yanitlarla_AYNI` KIRMIZI olur.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from topoloji import ESP_BOBIN, TUM_STM

_KOK = Path(__file__).resolve().parents[1]
_FIKSTUR = _KOK / "apps" / "ui" / "src" / "screens" / "__tests__" / "__fixtures__" / "espSlot8Durdurma.json"
_STOP = {"freq": 0, "duty": 0, "phase": 0, "duration": 0, "start": False}


@pytest.fixture()
def ortam(monkeypatch):
    from servers import api_server as api

    yayinlar: list = []

    class _SahteHC:
        def update_coil(self, coil_id, freq, duty, phase, duration, start=True, duration_seconds=None):
            return True

        def stop_all_coils(self):
            return True

    gercek = api._mqtt_publish
    monkeypatch.setattr(api.state, "hardware", _SahteHC())
    monkeypatch.setattr(
        api, "_mqtt_publish", lambda topic, payload: yayinlar.append((topic, payload)) or gercek(topic, payload)
    )
    monkeypatch.delenv("PEMF_ESP_ENABLED", raising=False)
    with api._session_lock:
        api._active_session.clear()
    return api, TestClient(api.app), yayinlar


def _durum(yanit: dict) -> dict:
    """İstemcinin okuduğu kararlı alanlar (command_id gibi rastgele alanlar atılır)."""
    tut = {k: yanit[k] for k in ("status", "transport", "coilId") if k in yanit}
    if "results" in yanit:
        tut["results"] = [_durum(r) for r in yanit["results"]]
    return tut


def test_KRITIK_esp_kapaliyken_tekil_slot8_STOP_devre_disi_der_ve_yine_DENENIR(ortam):
    api, c, yayinlar = ortam
    r = c.post(f"/api/coil/{ESP_BOBIN}/control", json=_STOP)
    assert r.status_code == 200
    assert r.json()["status"] == "devre_disi", f"ESP bilerek kapaliyken yanit 'broker olu' ile ayni: {r.json()}"
    stoplar = [p for t, p in yayinlar if t == f"pemf/coil/{ESP_BOBIN}/control" and p.get("command") == "stop"]
    assert len(stoplar) == 1, "slot 8 STOP denemesi AZALDI (O.4-Y8: durdurma gonderimi azaltilmaz)"


def test_KRITIK_esp_kapaliyken_batch_slot8_satiri_devre_disi_STM_satirlari_success(ortam):
    api, c, _ = ortam
    r = c.post("/api/coil/batch", json={"coil_ids": sorted(TUM_STM) + [ESP_BOBIN], **_STOP})
    assert r.status_code == 200
    satir = {x["coilId"]: x["status"] for x in r.json()["results"]}
    assert satir[ESP_BOBIN] == "devre_disi", f"batch slot 8 satiri: {satir[ESP_BOBIN]}"
    assert all(satir[b] == "success" for b in TUM_STM)


def test_KARSIT_esp_ACIKken_yayin_basarisiz_mqtt_unavailable_KALIR(ortam, monkeypatch):
    api, c, _ = ortam
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: False)  # broker ölü
    r = c.post(f"/api/coil/{ESP_BOBIN}/control", json=_STOP)
    assert r.json()["status"] == "mqtt_unavailable", "gercek ESP arizasi 'devre_disi' diye gizlendi"
    rb = c.post("/api/coil/batch", json={"coil_ids": [ESP_BOBIN], **_STOP})
    assert rb.json()["results"][0]["status"] == "mqtt_unavailable"


def test_KARSIT_esp_kapaliyken_slot8_START_basarili_SAYILMAZ(ortam):
    api, c, _ = ortam
    r = c.post(f"/api/coil/{ESP_BOBIN}/control", json={"freq": 50, "duty": 25, "start": True})
    assert r.json()["status"] != "success", "ESP yokken START 'success' dedi"


def test_arayuz_fiksturu_GERCEK_yanitlarla_AYNI(ortam, monkeypatch):
    api, c, _ = ortam
    beklenen = {
        "espKapali": {
            "tekil": _durum(c.post(f"/api/coil/{ESP_BOBIN}/control", json=_STOP).json()),
            "batch": _durum(c.post("/api/coil/batch", json={"coil_ids": sorted(TUM_STM), **_STOP}).json()),
        }
    }
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: False)
    beklenen["espAcikBrokerOlu"] = {"tekil": _durum(c.post(f"/api/coil/{ESP_BOBIN}/control", json=_STOP).json())}
    assert _FIKSTUR.is_file(), f"arayuz fiksturu yok: {_FIKSTUR}"
    kayitli = json.loads(_FIKSTUR.read_text(encoding="utf-8"))
    assert kayitli == beklenen, "arayuz fiksturu backend'in GERCEK yanitlarindan BAYATLADI"
