# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.105 · B-10.180 + İG-5.10 + 1-C §9 #2 — TEYİT EKSENİ (sahip kararı A-63): ESP kapalıyken teyit STM onayına göre;
E-stop DIŞI STOP yolları da "porta YAZILDI"yı teyit sayar. Gönderimler AZALTILMAZ (Ö.4-Y8) — yalnız RAPOR değişir.

ÖLÇÜLEN KUSURLAR:
  * B-10.180: `PEMF_ESP_ENABLED` ayarsızken (HEAD varsayılanı) her E-stop `partial` / `confirmed:false` — STM STOP porta
    yazılmış olsa bile; operatör her basışta "fiziksel güç düğmesinden kapatın" alarmı görüyordu (alarm körlüğü, K4).
  * İG-5.10: ESP kapalıyken bobin 8'i içeren seansın `/session/stop`'u her seferinde 409 "HÂLÂ ÇALIŞIYOR olabilirler".
  * 1-C §9 #2: seans durdurma (`_stop_session_coils`: `/session/stop`, AI Pro durdurma, süre bekçisi), seanssız
    `/session/stop` ve `/hardware/command stop_all_coils` "kuyruğa verildi"yi teyit sayıyordu; kablo çıkıkken (porta
    0 bayt) "teyitsiz" demiyorlardı.
ZİNCİR C1-11 (plan §13): teyit STM'e bağlanınca ÖLÜ / yazamayan göndericide yalan "teyitli" olmamalı (B-1.23 = D1.55
önce yapıldı) → KARŞIT kol.

Aparat: D1.55'in GERÇEK `HeadlessCore` (HWSender GERÇEK) + GERÇEK `HardwareController` + tek erişimli sahte seri taşıma
(porta yazılan her paket kaydedilir; `yazim_patlat` = WriteFile başarısız / USB yarı kopuk). Ölçüt HTTP 200 değil
PORTA YAZILAN BAYT ve yanıttaki teyit alanları.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from test_hwsender_olurse_STOP_teyidi_YALAN_SOYLEMEZ import _bekle, _stop_mu, _surulen_bobin, aparat  # noqa: F401
from topoloji import ESP_BOBIN, TUM_STM


@pytest.fixture
def api_ortami(aparat, monkeypatch):  # noqa: F811
    from servers import api_server as api

    core, hc, d = aparat
    yayinlar: list = []
    monkeypatch.setattr(api.state, "hardware", hc)
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: yayinlar.append((topic, payload)) or False)
    monkeypatch.setattr(api, "_estop_cloud_mirror", lambda *a, **k: None)
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.delenv("PEMF_ESP_ENABLED", raising=False)
    with api._session_lock:
        api._active_session.clear()
    return api, core, hc, d, yayinlar


def _esp_stop_denendi(yayinlar) -> bool:
    return any(t == f"pemf/coil/{ESP_BOBIN}/control" and p.get("command") == "stop" for t, p in yayinlar)


def test_KRITIK_D1105_esp_kapali_STM_STOP_porta_yazildiysa_estop_TEYITLI_ve_ESP_STOP_yine_denenir(api_ortami):
    # T2D-1: teyit "porta yazıldı" + kartın tüm-sıfır ACK'i (uyumlu kart). Sessiz kart kolu: TD3 dosyası (`saha_sessiz` → teyitsiz).
    api, core, hc, d, yayinlar = api_ortami
    d.ack_ver = True
    _surulen_bobin(hc, d)
    once = len(d.yazilan)
    r = TestClient(api.app).post("/api/hardware/emergency_stop").json()
    assert _bekle(lambda: any(_stop_mu(b) for _, _, b in d.yazilan[once:]), 3.0), "aparat: STOP porta yazilmadi"
    assert r["stmStopped"] is True
    assert _esp_stop_denendi(yayinlar), "ESP kapali diye ESP STOP denemesi AZALDI (O.4-Y8)"
    assert r["confirmed"] is True, f"ESP bilerek kapaliyken STM teyitli E-stop 'teyitsiz' raporlandi (A-63): {r}"
    assert r["status"] == "success"


def test_KARSIT_C111_esp_kapali_ama_STOP_porta_YAZILAMADI_estop_TEYITSIZ(api_ortami):
    api, core, hc, d, yayinlar = api_ortami
    _surulen_bobin(hc, d)
    d.yazim_patlat = True  # USB yarı kopuk: WriteFile başarısız → porta 0 bayt
    r = TestClient(api.app).post("/api/hardware/emergency_stop").json()
    assert r["stmStopped"] is False
    assert r["confirmed"] is False, f"porta yazilamayan STOP 'teyitli' raporlandi (C1-11): {r}"


def test_KARSIT_esp_ACIK_ve_yayin_basarisiz_estop_TEYITSIZ(api_ortami, monkeypatch):
    api, core, hc, d, yayinlar = api_ortami
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    r = TestClient(api.app).post("/api/hardware/emergency_stop").json()
    assert r["stmStopped"] is True
    assert r["confirmed"] is False, "ESP acikken ESP STOP'u dogrulanamadi ama E-stop 'teyitli' dedi"


def test_KRITIK_1C9_2_seans_STOPu_porta_yazilamazsa_STM_bobinleri_TEYITSIZ(api_ortami):
    api, core, hc, d, yayinlar = api_ortami
    _surulen_bobin(hc, d)
    d.yazim_patlat = True
    hedef = sorted(TUM_STM)[:2]
    teyitsiz = api._stop_session_coils(hedef, True)
    assert set(hedef) <= set(teyitsiz), f"porta 0 bayt ama seans STOP'u 'teyitli' sayildi: {teyitsiz}"


def test_KRITIK_1C9_2_seanssiz_session_stop_porta_yazilamazsa_TEYITSIZ_bildirir(api_ortami):
    api, core, hc, d, yayinlar = api_ortami
    _surulen_bobin(hc, d)
    d.yazim_patlat = True
    r = TestClient(api.app).post("/api/session/stop").json()
    assert set(TUM_STM) <= set(r.get("hardware_stop_unconfirmed") or []), f"seanssiz STOP teyitsizligi gizlendi: {r}"


def test_KRITIK_1C9_2_hardware_command_stop_all_porta_yazilamazsa_success_DEMEZ(api_ortami, monkeypatch):
    api, core, hc, d, yayinlar = api_ortami
    monkeypatch.setattr(api.state, "core", core)
    _surulen_bobin(hc, d)
    d.yazim_patlat = True
    r = TestClient(api.app).post("/api/hardware/command", json={"command": "stop_all_coils"}).json()
    assert r.get("stmStopped") is False and r.get("status") != "success", f"porta 0 bayt ama {r}"


def test_KARSIT_saglam_portta_seans_ve_seanssiz_STOP_teyitli(api_ortami):
    api, core, hc, d, yayinlar = api_ortami
    _surulen_bobin(hc, d)
    assert api._stop_session_coils(sorted(TUM_STM)[:2], True) == []
    r = TestClient(api.app).post("/api/session/stop").json()
    assert not r.get("hardware_stop_unconfirmed"), r


def test_KRITIK_IG510_esp_kapali_bobin8li_seans_durdurma_409_DEGIL_ve_ESP_STOP_denenir(api_ortami):
    api, core, hc, d, yayinlar = api_ortami
    with api._session_lock:
        api._active_session.update(
            {
                "is_active": True,
                "session_id": "d1105-ig510",
                "coil_ids": sorted(TUM_STM) + [ESP_BOBIN],
                "db_session_id": None,
                "started_epoch": time.time(),
                "start_mono": time.monotonic(),
            }
        )
    r = TestClient(api.app).post("/api/session/stop")
    assert r.status_code == 200, f"ESP bilerek kapaliyken bobin 8'li seans durdurma {r.status_code}: {r.text}"
    assert _esp_stop_denendi(yayinlar), "slot 8 STOP denemesi AZALDI"
