# Author: mertaygn, cglrgrkn
"""D1.13 · B-10.123 · B-10.132 · B-10.155 — E-stop'un üç değişmezi METİN yerine DAVRANIŞLA kapılı.

Üçü de Ö.4-Y8 (E-stop hiçbir şeye kapılanmaz) / K4 değişmezidir; ürün bugün doğru, kapılar yalnız
kaynak METNİ arıyordu (`test_esp_ack_roundtrip.py`, `test_plan_a_deadman.py`,
`test_kalan_regression_gaps.py`). B-10.180 / B-6.9 düzeltmeleri `_emergency_stop_all`'ın ESP dalına
ve teyit yüklemine dokunacak → önce bunlar davranışla kilitlenir; aksi hâlde ack kaydı ya da ayna
gönderimi sessizce silinebilir.

  (a) ESP ACK kaydı: E-stop STOP'u yayınlanmadan ÖNCE onay kaydı açılır; ESP onayı (gerçek
      `_resolve_ack`) gelince ack-bekçisi ALARM ÜRETMEZ. Kayıt silinirse onay kaybolur → "onay
      gelmedi" alarmı (operatör boşuna fiziksel kontrole koşar; teyit yüklemi de bozulur).
  (b) Bulut aynası: `estop-cloud-mirror` iş parçacığı GERÇEKTEN BAŞLATILIR (buluta failover etmiş
      ESP'ye yerel yayın ulaşmaz — HG-5 Plan A-2).
  (c) `/api/v1` takma adı: auth ZORUNLU + uzak istemci + token'sız `POST /api/v1/hardware/emergency_stop`
      → 200 ve STOP gerçekten çağrılır (yeniden yazım auth'tan ÖNCE).

⚠️ A-04 (broker kimlikli olacak) ve A-63 (teyit ölçütü) bu kapıların konusu DEĞİL: kapılar
`confirmed`'ı ölçmez; yalnız kaydın, aynanın ve muafiyetin KAYBOLMASINI yakalar.
"""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient


class _DurduranDonanim:
    def __init__(self):
        self.stop_all = 0

    def stop_all_coils(self):
        self.stop_all += 1
        return True


@pytest.fixture
def estop(monkeypatch):
    from servers import api_server as api

    hw = _DurduranDonanim()
    bildirimler: list = []
    yayinlar: list = []

    def _yayin(topic, payload):
        yayinlar.append((topic, dict(payload)))
        return True  # broker KABUL etti → ack-bekçisi doğar (ölçülen şey o)

    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    monkeypatch.setattr(api.state, "hardware", hw)
    monkeypatch.setattr(api, "_mqtt_publish", _yayin)
    monkeypatch.setattr(api, "_push_notification", lambda m, t="info": bildirimler.append((m, t)))
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    with api._session_lock:
        eski = dict(api._active_session)
        api._active_session.clear()
        api._active_session.update({"is_active": False})
    try:
        yield api, hw, bildirimler, yayinlar
    finally:
        with api._session_lock:
            api._active_session.clear()
            api._active_session.update(eski)


def _ack_bekcilerini_bekle(sure: float = 6.0):
    bitis = time.monotonic() + sure
    while time.monotonic() < bitis:
        canli = [t for t in threading.enumerate() if t.name.startswith("estop-ack-")]
        if not canli:
            return
        for t in canli:
            t.join(timeout=0.2)
    raise AssertionError("E-stop ack-bekçisi süresinde bitmedi")


def test_KRITIK_a_ESP_onayi_gelince_ack_bekcisi_ALARM_URETMEZ(estop):
    from topoloji import TUM_ESP, esp_yolu_gerekir

    esp_yolu_gerekir()
    api, _hw, bildirimler, yayinlar = estop
    api._emergency_stop_all(reason="d113")
    komutlar = {
        int(t.split("/")[2]): p["command_id"]
        for t, p in yayinlar
        if t.startswith("pemf/coil/") and t.endswith("/control") and p.get("emergency")
    }
    assert set(komutlar) == set(TUM_ESP), f"acil STOP yayını her ESP bobinine gitmedi: {sorted(komutlar)}"
    for cid in komutlar.values():
        api._resolve_ack(cid, True)  # ESP onayı geldi (gerçek çözümleyici)
    _ack_bekcilerini_bekle()
    alarmlar = [m for m, _t in bildirimler if "acil durdurma" in m.lower()]
    assert alarmlar == [], f"ESP onayladığı hâlde 'onay gelmedi' alarmı üretildi: {alarmlar}"


def test_KARSIT_a_onay_GELMEZSE_alarm_URETILIR(estop, monkeypatch):
    """Kapı kör değil: onay gelmezse bekçi gerçekten alarm üretir (zaman aşımı kısaltılır)."""
    from topoloji import esp_yolu_gerekir

    esp_yolu_gerekir()
    api, _hw, bildirimler, _yayinlar = estop
    gercek_bekle = api._wait_ack
    monkeypatch.setattr(api, "_wait_ack", lambda cid, timeout: gercek_bekle(cid, 0.05))
    api._emergency_stop_all(reason="d113-karsit")
    _ack_bekcilerini_bekle()
    assert any("ONAYI GELM" in m.upper() or "onayı gelmedi" in m.lower() for m, _t in bildirimler), bildirimler


class _ThreadingVekili:
    """`api_server`'ın gördüğü `threading` modülü: `Thread` başlatmalarını kaydeder, gerisi gerçek."""

    def __init__(self):
        self.baslatilan: list[str] = []
        vekil = self

        class _KayitliThread(threading.Thread):
            def start(self):
                vekil.baslatilan.append(self.name)
                return super().start()

        self.Thread = _KayitliThread

    def __getattr__(self, ad):
        return getattr(threading, ad)


def test_KRITIK_b_bulut_aynasi_is_parcacigi_GERCEKTEN_BASLATILIR(estop, monkeypatch):
    api, _hw, _b, _y = estop
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: False)  # ack-bekçisi doğmasın
    vekil = _ThreadingVekili()
    monkeypatch.setattr(api, "threading", vekil)
    r = TestClient(api.app, client=("127.0.0.1", 51239)).post("/api/hardware/emergency_stop")
    assert r.status_code == 200, r.text[:200]
    assert "estop-cloud-mirror" in vekil.baslatilan, (
        f"E-stop bulut aynası BAŞLATILMADI (başlatılanlar: {vekil.baslatilan}) — buluta failover etmiş ESP STOP almaz"
    )
    _ack_bekcilerini_bekle()


def test_KRITIK_c_v1_takma_adi_AUTH_ZORUNLUYKEN_tokensiz_DURDURUR(estop, monkeypatch):
    from servers import auth

    api, hw, _b, _y = estop
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: False)  # ack-bekçisi doğmasın
    monkeypatch.setattr(auth, "_require", True)
    monkeypatch.setattr(auth, "_warned", True)
    monkeypatch.setattr(auth, "get_api_token", lambda: "gizli-cihaz-tokeni")
    c = TestClient(api.app)
    korumali = c.get("/api/v1/patients", headers={"cf-connecting-ip": "203.0.113.7"})
    assert korumali.status_code == 401, "senaryo: auth gerçekten zorunlu ve istek uzak sayılıyor olmalı"
    r = c.post("/api/v1/hardware/emergency_stop", headers={"cf-connecting-ip": "203.0.113.7"})
    assert r.status_code == 200, f"/api/v1 takma adında ACİL DURDUR {r.status_code} (Ö.4-Y8: kapılanamaz)"
    assert hw.stop_all >= 1, "/api/v1 ACİL DURDUR 200 döndü ama donanıma STOP denenmedi"
    _ack_bekcilerini_bekle()


# ── Bağımsız inceleme (r3) ekleri ─────────────────────────────────────────────────────────────


def test_KRITIK_a_HIZLI_ESP_onayi_YAYIN_SIRASINDA_gelirse_ALARM_YOK(estop, monkeypatch):
    """(a)'nın SIRA yarısı: kayıt yayından ÖNCE açılmalı. `_mqtt_publish` PUBACK'i senkron bekler; hızlı
    bir ESP'nin onayı yayın çağrısı DÖNMEDEN gelebilir. Kayıt yayından SONRA açılsaydı (mutant) onay
    kaybolur, her E-stop'ta sahte "onay gelmedi" alarmı çıkar — eski kol onayı E-stop DÖNDÜKTEN sonra
    verdiği için bunu göremiyordu."""
    from topoloji import esp_yolu_gerekir

    esp_yolu_gerekir()
    api, _hw, bildirimler, yayinlar = estop
    cozulen: list = []

    def _hizli_yayin(topic, payload):
        yayinlar.append((topic, dict(payload)))
        cid = payload.get("command_id")
        if cid and payload.get("emergency") and topic.endswith("/control"):
            cozulen.append(cid)
            api._resolve_ack(cid, True)  # ESP onayı yayın çağrısı dönmeden geldi
        return True

    monkeypatch.setattr(api, "_mqtt_publish", _hizli_yayin)
    gercek_bekle = api._wait_ack
    monkeypatch.setattr(api, "_wait_ack", lambda cid, timeout: gercek_bekle(cid, 0.3))
    api._emergency_stop_all(reason="d113-hizli")
    _ack_bekcilerini_bekle()
    assert cozulen, "aparat: hiç acil STOP yayını görülmedi"
    alarmlar = [m for m, _t in bildirimler if "ONAYI GELM" in m.upper() or "acil durdurma" in m.lower()]
    assert alarmlar == [], f"ESP yayın sırasında onayladı ama 'onay gelmedi' alarmı üretildi: {alarmlar}"


def test_KRITIK_b_ayna_YALNIZ_STM_seansinda_da_TUM_ESP_bobinlerini_hedefler(estop, monkeypatch):
    """(b)'nin HEDEF yarısı: ayna seans kapsamıyla sınırlanmaz — buluta failover etmiş ESP, seans onu
    içermese de STOP almalı (DENETİM P0 sınıfı). Eski kol yalnız iş parçacığının ADINI ölçüyordu."""
    from topoloji import TUM_ESP, TUM_STM, esp_yolu_gerekir

    esp_yolu_gerekir()
    api, _hw, _b, _y = estop
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: False)  # ack-bekçisi doğmasın
    aynalanan: list = []
    monkeypatch.setattr(api, "_estop_cloud_mirror", lambda bobinler, sebep: aynalanan.append(list(bobinler)))
    with api._session_lock:
        api._active_session.update({"is_active": True, "coil_ids": sorted(TUM_STM)[:3]})
    api._emergency_stop_all(reason="d113-ayna-hedef")
    bitis = time.monotonic() + 5
    while not aynalanan and time.monotonic() < bitis:
        time.sleep(0.01)
    assert aynalanan, "bulut aynası çağrılmadı"
    assert set(TUM_ESP) <= set(aynalanan[0]), (
        f"ayna yalnız {aynalanan[0]} bobinlerini hedefliyor — seans kapsamıyla SINIRLANMIŞ (TUM_ESP={sorted(TUM_ESP)})"
    )
