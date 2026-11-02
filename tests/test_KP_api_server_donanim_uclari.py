# Author: mertaygn, cglrgrkn
"""KP-1 · apps/backend/servers/api_server.py · sözleşmeler: donanım uçları — `/api/hardware/auto_preset` (çekirdek yok 503,
önerici bağımlılığı yok 501, hesap hatası 500 — ham hata sızmaz), `/api/hardware/command` (çekirdek/donanım yok 503, bilinmeyen
komut "error" + katalog metni, donanım istisnası 500, AI Pro plan dışı kaydı patlasa da bobin STOP'u gider),
`/api/hardware/selftest` ve `/reset_pwm` (donanım yok 503; STM sıfırlaması patlasa da ESP STOP yayını denenir),
`/api/hardware/cleanup_esp`, kart yanıtı yardımcıları (sayaç / yanıt okuma istisnası, bozuk ACK satırı sonraki NACK'i
engellemez), `/api/coil/{id}/control` ve `/api/coil/batch` (STM bobini donanımsız 503 / `stm_unavailable`, geçersiz kimlik
`invalid`, ESP başlatmada bobin 1'in yüksek frekansı → faz senkron uyarısı; bobin 1 frekansı bozuksa uyarısız).

Sahte EN ALT katta: donanım (`state.hardware` / `state.core`; seri G/Ç arıza biçimi `OSError`), önerici iç bağımlılığı
(`ai.hybrid_recommender.create_recommender`), MQTT yayını (`_mqtt_publish` — ağa çıkmaz), WS yayını ve bildirim kaydı.
Metinler ürün kataloğundan (`ceviri.t`, TR varsayılan).
"""

from __future__ import annotations

import asyncio
import copy
import logging
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from topoloji import ESP_BOBIN, STM_BOBIN, esp_yolu_gerekir

DUTY_NACK_1 = "-> STM_NACK: RANGE coil=1 field=duty value_milli=800000 max_milli=500000 kip=bipolar"


@pytest.fixture
def ortam(monkeypatch):
    from servers import api_server as a
    from servers import live_state as ls

    yayin: list = []
    bildirim: list = []
    mqtt: list = []
    monkeypatch.setattr(a, "_ws_broadcast_sync", lambda m: yayin.append(m))
    monkeypatch.setattr(ls, "_ws_broadcast_sync", lambda m: yayin.append(m))
    monkeypatch.setattr(a, "_push_notification", lambda m, s="info", mesajlar=None: bildirim.append((m, s)))
    monkeypatch.setattr(a, "_mqtt_publish", lambda t, p: mqtt.append((t, p.get("command"))) or False)
    with a._live_state_lock:
        canli_once = {k: copy.deepcopy(v) for k, v in a._live_state.items()}
    with a._pending_acks_lock:
        bekleyen_once = dict(a._pending_acks)
    try:
        with TestClient(a.app, client=("127.0.0.1", 50100)) as c:
            yield SimpleNamespace(a=a, c=c, yayin=yayin, bildirim=bildirim, mqtt=mqtt)
    finally:
        with a._live_state_lock:
            for k, v in canli_once.items():
                a._live_state[k] = v
        with a._pending_acks_lock:
            a._pending_acks.clear()
            a._pending_acks.update(bekleyen_once)


def _t(anahtar, **k):
    from utils import ceviri

    return ceviri.t(anahtar, dil="tr", **k)


class _Hc:
    def __init__(self, update_hata=None, stop_hata=None):
        self.cagri: list = []
        self._uh, self._sh = update_hata, stop_hata
        self.coils_state = {}

    def update_coil(self, *a, **k):
        self.cagri.append(("update_coil", a, k.get("start")))
        if self._uh:
            raise self._uh
        return True

    def stop_all_coils(self):
        self.cagri.append(("stop_all_coils",))
        if self._sh:
            raise self._sh
        return True


def test_auto_preset_CEKIRDEK_yoksa_503(ortam, monkeypatch):
    """`state.core` yok → 503, ayrıntı `donanim.hata.cekirdekHazirDegil`."""
    monkeypatch.setattr(ortam.a.state, "core", None)
    r = ortam.c.post("/api/hardware/auto_preset", json={"target_condition": "kirik"})
    assert r.status_code == 503 and r.json()["detail"] == _t("donanim.hata.cekirdekHazirDegil")


@pytest.mark.parametrize(
    ("hata", "kod", "anahtar"),
    [
        (ImportError("No module named 'numpy'"), 501, "ai.hata.onericiYok"),
        (ValueError("bozuk tablo"), 500, "ai.hata.oneriHatasi"),
    ],
)
def test_auto_preset_ONERICI_hatasi_kod_ve_katalog_metni_ham_hata_SIZMAZ(ortam, monkeypatch, hata, kod, anahtar):
    """Önericinin iç bağımlılığı ImportError → 501 `ai.hata.onericiYok`; başka istisna → 500 `ai.hata.oneriHatasi`; gövdede
    ham istisna metni YOK."""
    import ai.hybrid_recommender as hr

    def _patlayan(*_a, **_k):
        raise hata

    monkeypatch.setattr(ortam.a.state, "core", object())
    monkeypatch.setattr(hr, "create_recommender", _patlayan)
    r = ortam.c.post("/api/hardware/auto_preset", json={"target_condition": "kirik"})
    assert r.status_code == kod and r.json()["detail"] == _t(anahtar)
    assert str(hata) not in r.text


def test_komut_CEKIRDEK_ya_da_DONANIM_yoksa_503(ortam, monkeypatch):
    """`state.core` var ama `state.hardware` yok → 503 `donanim.hata.cekirdekDonanimHazirDegil`."""
    monkeypatch.setattr(ortam.a.state, "core", object())
    monkeypatch.setattr(ortam.a.state, "hardware", None)
    r = ortam.c.post("/api/hardware/command", json={"command": "stop_all_coils"})
    assert r.status_code == 503 and r.json()["detail"] == _t("donanim.hata.cekirdekDonanimHazirDegil")


def test_komut_BILINMEYEN_error_ve_katalog_metni(ortam, monkeypatch):
    """Tanımsız komut → 200, {"status": "error", "message": `donanim.hata.bilinmeyenKomut` (cmd küçük harfli)}; donanım çağrılmaz."""
    hc = _Hc()
    monkeypatch.setattr(ortam.a.state, "core", object())
    monkeypatch.setattr(ortam.a.state, "hardware", hc)
    r = ortam.c.post("/api/hardware/command", json={"command": "Dans_Et"})
    assert r.status_code == 200
    assert r.json() == {"status": "error", "message": _t("donanim.hata.bilinmeyenKomut", cmd="dans_et")}
    assert hc.cagri == []


def test_komut_DONANIM_istisnasi_500_ham_hata_SIZMAZ(ortam, monkeypatch):
    """`stop_coil` + `update_coil` OSError → 500 `donanim.hata.komutBasarisiz`; gövdede ham istisna metni yok."""
    hc = _Hc(update_hata=OSError("COM7 erişim reddedildi"))
    monkeypatch.setattr(ortam.a.state, "core", object())
    monkeypatch.setattr(ortam.a.state, "hardware", hc)
    r = ortam.c.post("/api/hardware/command", json={"command": "stop_coil", "params": {"coil_id": STM_BOBIN}})
    assert r.status_code == 500 and r.json()["detail"] == _t("donanim.hata.komutBasarisiz")
    assert "COM7" not in r.text


def test_komut_STOP_AI_Pro_plan_kaydi_patlasa_da_bobin_durdurulur(ortam, monkeypatch, caplog):
    """`stop_coil` + AI Pro plan dışı kaydı istisna atıyor → bobin STOP'u (`update_coil(..., start=False)`) YİNE gider, yanıt
    success; "Y54: AI Pro plan disi kaydi yapilamadi" yazılır."""
    from servers import ai_router

    def _patlayan(_b):
        raise RuntimeError("plan kilidi bozuk")

    monkeypatch.setattr(ai_router, "ai_pro_bobinlerini_plandan_cikar", _patlayan)
    hc = _Hc()
    monkeypatch.setattr(ortam.a.state, "core", object())
    monkeypatch.setattr(ortam.a.state, "hardware", hc)
    caplog.set_level(logging.ERROR)
    r = ortam.c.post("/api/hardware/command", json={"command": "stop_coil", "params": {"coil_id": STM_BOBIN}})
    assert r.json() == {"status": "success", "command": "stop_coil", "coil_id": STM_BOBIN}
    assert hc.cagri == [("update_coil", (STM_BOBIN, 0, 0, 0, 0), False)]
    assert any("Y54: AI Pro plan disi kaydi yapilamadi" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("yol", ["/api/hardware/selftest", "/api/hardware/reset_pwm"])
def test_selftest_ve_reset_DONANIM_yoksa_503(ortam, monkeypatch, yol):
    """`state.hardware` yok → 503 `donanim.hata.hazirDegil`; ESP yayını yapılmaz."""
    monkeypatch.setattr(ortam.a.state, "hardware", None)
    r = ortam.c.post(yol)
    assert r.status_code == 503 and r.json()["detail"] == _t("donanim.hata.hazirDegil")
    assert ortam.mqtt == []


def test_reset_STM_sifirlamasi_PATLASA_da_ESP_STOP_yayini_denenir(ortam, monkeypatch):
    """reset_pwm + `stop_all_coils` OSError → yanıt hemen success; arka plan işi STM'i dener, ardından TÜM ESP bobinlerine "stop"
    yayınlar."""
    from topoloji import TUM_ESP

    hc = _Hc(stop_hata=OSError("seri port yok"))
    monkeypatch.setattr(ortam.a.state, "hardware", hc)
    r = ortam.c.post("/api/hardware/reset_pwm")
    assert r.json()["status"] == "success"
    for t in [t for t in threading.enumerate() if t.name == "hw-reset-pwm"]:
        t.join(5)
    assert hc.cagri == [("stop_all_coils",)]
    assert ortam.mqtt == [(f"pemf/coil/{i}/control", "stop") for i in sorted(TUM_ESP)]


def test_cleanup_esp_BAGLANTISIZ_slotlarin_calisiyor_bayragi_dusurulur(ortam):
    """Slot 6-8 (indeks 5-7): bağlantısız + "running" → running False; bağlı olan dokunulmaz; yanıt success."""
    a = ortam.a
    with a._live_state_lock:
        a._live_state["coils"][5].update(connected=False, running=True)
        a._live_state["coils"][6].update(connected=True, running=True)
        a._live_state["coils"][7].update(connected=False, running=True)
    r = ortam.c.post("/api/hardware/cleanup_esp")
    assert r.json() == {"status": "success", "message": "Stale ESP state cleaned."}
    assert [a._live_state["coils"][i]["running"] for i in (5, 6, 7)] == [False, True, False]


def test_kart_yanit_SAYACI_patlarsa_None(ortam, monkeypatch):
    """`core.stm_yanit_sayaci` istisna atıyor → `_stm_yanit_tabani` None (bekleme yapılmaz)."""

    def _patlayan():
        raise OSError("sayaç okunamadı")

    monkeypatch.setattr(ortam.a.state, "hardware", SimpleNamespace(core=SimpleNamespace(stm_yanit_sayaci=_patlayan)))
    assert ortam.a._stm_yanit_tabani() is None


def test_kart_yaniti_OKUMA_yolu_yok_ya_da_patlarsa_bos(ortam, monkeypatch):
    """Çekirdek `stm_yanitlari_sonra` bildirmiyor → ""; bildiriyor ama istisna atıyor → "" (red metni uydurulmaz)."""
    a = ortam.a
    monkeypatch.setattr(a.state, "hardware", SimpleNamespace(core=SimpleNamespace()))
    assert asyncio.run(a._stm_baslatma_kart_yaniti(1, 80.0, 5)) == ""

    def _patlayan(_taban):
        raise OSError("tampon kilitli")

    monkeypatch.setattr(a.state, "hardware", SimpleNamespace(core=SimpleNamespace(stm_yanitlari_sonra=_patlayan)))
    assert asyncio.run(a._stm_baslatma_kart_yaniti(1, 80.0, 5)) == ""


def test_kart_yaniti_BOZUK_ack_satiri_sonraki_NACKi_engellemez(ortam, monkeypatch):
    """Yanıtlar: ayrıştırılamayan ACK satırı (ayrıştırıcı istisna) + bu bobinin duty NACK'i → `stm_duty_reddi_metni(NACK)`."""
    from servers import live_state as ls

    def _coz(_satir):
        raise ValueError("bozuk STM_OK")

    core = SimpleNamespace(
        stm_yanitlari_sonra=lambda _t: [("ok", "-> STM_OK: ???"), ("nack", DUTY_NACK_1)], _parse_stm_ok=_coz
    )
    monkeypatch.setattr(ortam.a.state, "hardware", SimpleNamespace(core=core))
    assert asyncio.run(ortam.a._stm_baslatma_kart_yaniti(1, 80.0, 0)) == ls.stm_duty_reddi_metni(DUTY_NACK_1)


def test_tekil_STM_bobini_DONANIM_yoksa_503(ortam, monkeypatch):
    """STM bobinine start + `state.hardware` yok → 503 `donanim.hata.stmHazirDegil`."""
    monkeypatch.setattr(ortam.a.state, "hardware", None)
    r = ortam.c.post(f"/api/coil/{STM_BOBIN}/control", json={"freq": 10, "duty": 20, "start": True})
    assert r.status_code == 503 and r.json()["detail"] == _t("donanim.hata.stmHazirDegil")


def _bobin1(a, frekans):
    with a._live_state_lock:
        a._live_state["coils"][0].update(running=True, frequencyHz=frekans)


def test_tekil_ESP_baslatma_FAZ_SENKRON_uyarisi_yanitta_ve_bildirimde(ortam):
    """ESP bobinine 10 Hz start + bobin 1 1000 Hz'de çalışıyor (≥ 50×) → yanıtta `sync_warning` = `donanim.uyari.fazSenkron`,
    "warning" bildirimi "⚠️ " + aynı metin; ESP kapalı → status `devre_disi`."""
    esp_yolu_gerekir()
    a = ortam.a
    _bobin1(a, 1000)
    r = ortam.c.post(f"/api/coil/{ESP_BOBIN}/control", json={"freq": 10, "duty": 20, "start": True})
    beklenen = _t("donanim.uyari.fazSenkron", hz=1000, coil=ESP_BOBIN, esp_freq=10.0)
    j = r.json()
    assert j["status"] == "devre_disi" and j["sync_warning"] == beklenen
    assert ("⚠️ " + beklenen, "warning") in ortam.bildirim


def test_tekil_ESP_baslatma_bobin1_frekansi_BOZUKSA_uyarisiz(ortam):
    """Bobin 1 frekansı sayı değil → faz denetimi yutulur, yanıtta `sync_warning` YOK, istek yine işlenir."""
    esp_yolu_gerekir()
    a = ortam.a
    _bobin1(a, "bozuk")
    r = ortam.c.post(f"/api/coil/{ESP_BOBIN}/control", json={"freq": 10, "duty": 20, "start": True})
    assert r.status_code == 200 and "sync_warning" not in r.json()
    assert ortam.bildirim == []


def test_toplu_GECERSIZ_kimlik_STM_donanimsiz_ESP_faz_uyarisi_satir_satir(ortam, monkeypatch):
    """Toplu start [9, STM, ESP] + donanım yok + bobin 1 1000 Hz → satırlar: 9 `invalid`, STM `stm_unavailable`, ESP `devre_disi`
    + `sync_warning` = `donanim.uyari.fazSenkronKisa`."""
    esp_yolu_gerekir()
    a = ortam.a
    monkeypatch.setattr(a.state, "hardware", None)
    _bobin1(a, 1000)
    r = ortam.c.post(
        "/api/coil/batch", json={"coil_ids": [9, STM_BOBIN, ESP_BOBIN], "freq": 10, "duty": 20, "start": True}
    )
    sonuc = {s["coilId"]: s for s in r.json()["results"]}
    assert sonuc[9]["status"] == "invalid"
    assert sonuc[STM_BOBIN]["status"] == "stm_unavailable"
    assert sonuc[ESP_BOBIN]["status"] == "devre_disi"
    assert sonuc[ESP_BOBIN]["sync_warning"] == _t(
        "donanim.uyari.fazSenkronKisa", hz=1000, coil=ESP_BOBIN, esp_freq=10.0
    )


def test_toplu_ESP_bobin1_frekansi_BOZUKSA_uyarisiz(ortam):
    """Toplu ESP start + bobin 1 frekansı bozuk → satırda `sync_warning` yok, bildirim yok."""
    esp_yolu_gerekir()
    a = ortam.a
    _bobin1(a, "bozuk")
    r = ortam.c.post("/api/coil/batch", json={"coil_ids": [ESP_BOBIN], "freq": 10, "duty": 20, "start": True})
    satir = r.json()["results"][0]
    assert satir["coilId"] == ESP_BOBIN and "sync_warning" not in satir
    assert ortam.bildirim == []
