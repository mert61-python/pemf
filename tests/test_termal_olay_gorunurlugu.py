# Author: mertaygn, cglrgrkn
"""YEREL TERMAL KESME GÖRÜNÜRLÜĞÜ — 2. tur denetimi bulgu [4.2] (2026-08-20).

ÖLÇÜLEN DURUM: iki ESP firmware'i de yerel termal korumada `pemf/coil/{id}/events`e olay
yayınlıyor (S3 `.ino:80-82` thermal_stop; 8266 `.ino:361/368/493` thermal_stop + thermal_unlock +
thermal_lock) ama backend'in events dalı yalnız `selftest_*`/`wifi_*` tanıyordu → cihazın EN
ÖNEMLİ yerel güvenlik eylemi operatöre HİÇ görünmüyordu: bobin "sebepsiz durdu" sanılır, termal
kilit sürerken start redleri açıklamasız kalır (HG-1/HG-2 bağlamında termal olayların görünürlüğü
klinik olarak önemli — D-1 selftest düzeltmesinin zincirin öbür ucundaki ikizi).

SÖZLEŞME: üç olay tipi de bildirilir (stop=error, lock=warning, unlock=success) + WS yayını;
RETAINED events filtresi aynen korunur (bayat termal olay yeniden-bağlanmada alarm üretmez).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]


@pytest.fixture()
def api(monkeypatch):
    import servers.api_server as api

    bildirimler: list = []
    ws: list = []
    monkeypatch.setattr(api, "_push_notification", lambda msg, sev="info": bildirimler.append((msg, sev)))
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda m: ws.append(m))
    monkeypatch.setattr(api, "_reconcile_esp_calisiyor", lambda *a, **k: None)
    return api, bildirimler, ws


def _olay(api, coil_id: int, event_type: str, message: str = "", retain: bool = False):
    class _Msg:
        pass

    m = _Msg()
    m.topic = f"pemf/coil/{coil_id}/events"
    m.retain = retain
    # İki firmware'in publishEvent şeması: {coil_id, event_type, message, timestamp}
    m.payload = json.dumps({"coil_id": coil_id, "event_type": event_type, "message": message, "timestamp": 1}).encode(
        "utf-8"
    )
    api._on_mqtt_message_api(None, None, m)


def test_KRITIK_thermal_stop_operatore_ERROR_bildirilir(api):
    api, bildirimler, ws = api
    _olay(api, 6, "thermal_stop", "Yerel termal kesme: 49.2C >= 48.0C")

    assert bildirimler, (
        "thermal_stop olayı operatöre HİÇ bildirilmedi — cihazın en önemli yerel güvenlik "
        "eylemi görünmez, bobin 'sebepsiz durdu' sanılır (bulgu [4.2])"
    )
    mesaj, sev = bildirimler[0]
    assert "6" in mesaj and ("ERMAL" in mesaj or "ermal" in mesaj), f"teşhis eksik: {mesaj!r}"
    assert "49.2" in mesaj, f"firmware'in ölçtüğü sıcaklık operatöre taşınmadı: {mesaj!r}"
    assert sev == "error"
    assert any(m.get("type") == "thermal_event" for m in ws), "WS'e termal olay yayınlanmadı"


def test_KRITIK_thermal_lock_ve_unlock_da_bildirilir(api):
    """8266 start reddini (lock) ve soğuma serbestliğini (unlock) ayrıca yayınlar — operatör
    'start neden çalışmıyor'u ve 'ne zaman serbest'i görmeli."""
    api, bildirimler, _ws = api
    _olay(api, 8, "thermal_lock", "Start reddedildi: bobin sicak")
    _olay(api, 8, "thermal_unlock", "Sicaklik dustu")

    turler = {sev for _m, sev in bildirimler}
    assert len(bildirimler) == 2, f"lock+unlock bildirilmedi: {bildirimler!r}"
    assert "warning" in turler and "success" in turler, f"ciddiyet eşlemesi yanlış: {bildirimler!r}"
    assert "8" in bildirimler[0][0]


def test_KARSIT_KANIT_RETAINED_termal_olay_alarm_URETMEZ(api):
    """D-4 filtresi korunur: broker'da kalmış bayat thermal_stop, backend yeniden-bağlanınca
    teslim edilir — onu canlı sanmak her reconnect'te sahte termal alarm demek olurdu."""
    api, bildirimler, ws = api
    _olay(api, 6, "thermal_stop", "bayat", retain=True)

    assert not bildirimler and not ws, f"RETAINED termal olay işlendi: {bildirimler!r} {ws!r}"


def test_PARITE_firmware_termal_olay_adlari_kaynakta_kilitli():
    """Backend'in tanıdığı üç ad, firmware'lerin GERÇEKTEN yayınladığı adlardır — biri adı
    değiştirirse bu kapı kırmızıya döner (sözleşme sessizce ayrışamaz)."""
    s3_ino = (KOK / "firmware" / "esps3_pemf_coil" / "esps3_pemf_coil.ino").read_text(
        encoding="utf-8", errors="replace"
    )
    e8_ino = (KOK / "firmware" / "esp8266_pemf_coil" / "esp8266_pemf_coil.ino").read_text(
        encoding="utf-8", errors="replace"
    )

    assert 'publishEvent("thermal_stop"' in s3_ino, "S3 thermal_stop yayınlamıyor — backend dalı bayatladı"
    for ad in ("thermal_stop", "thermal_unlock", "thermal_lock"):
        assert f'publishEvent("{ad}"' in e8_ino, f"8266 {ad} yayınlamıyor — backend dalı bayatladı"
