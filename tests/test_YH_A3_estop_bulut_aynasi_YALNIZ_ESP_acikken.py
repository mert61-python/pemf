# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""YH · A3 (istem 50, Y289 · P0-2 kod tarafı): ACİL DURDUR'un BULUT AYNASI (`_estop_cloud_mirror`, HiveMQ) YALNIZ ESP AÇIKKEN
(`live_state.esp_etkin()`) çalışır. ESP söküldü (Y230): aynanın tüketicisi (buluta failover etmiş ESP) yok; ayna sızmış eski HiveMQ
kimliğiyle her ACİL DURDUR'da bulut bağlantısı deneyip zaman aşımına düşüyordu (AP B9, 13-11 tezgâh).

  1) ESP KAPALI → ayna iş parçacığı AÇILMAZ, ayna HİÇ çağrılmaz; yerel yol (STM STOP + yerel ESP STOP denemesi) AYNEN;
  2) ESP AÇIK (karşıt) → ayna eskisi gibi TÜM ESP bobinleriyle, ACİL DURDUR sebebiyle çağrılır;
  3) bayrak ACİL DURDUR anında okunur (önbelleğe alınmaz): aynı süreçte kapalı → açık → kapalı.
Yerel STOP'un aynayı HİÇBİR koşulda beklemediğinin kanıtı ayrı dosyada KORUNUR (`test_AP_B9_...`, ESP açık fikstür; Ö.4-Y8).
Ağa çıkılmaz: ayna sahtelenir, `_mqtt_publish` sahte.
"""

from __future__ import annotations

import threading

import pytest


@pytest.fixture
def api(monkeypatch):
    from servers import api_server as _api

    olaylar: list[str] = []
    yayinlar: list[str] = []
    aynalanan: list[tuple[list, str]] = []
    acilan: list[str] = []

    class _HW:
        def stop_all_coils(self):
            olaylar.append("stm_stop")
            return True

    monkeypatch.setattr(_api.state, "hardware", _HW())

    def _yayin(topic, payload):
        yayinlar.append(topic)
        return False  # ack-bekçisi doğmasın (yayın DENEMESİ yine kaydedilir)

    monkeypatch.setattr(_api, "_mqtt_publish", _yayin)

    def _ayna(coil_ids, reason):
        aynalanan.append((list(coil_ids), reason))

    monkeypatch.setattr(_api, "_estop_cloud_mirror", _ayna)

    gercek = threading.Thread
    ayna_parcaciklari: list = []

    class _Thread(gercek):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            if self.name == "estop-cloud-mirror":
                acilan.append(self.name)
                ayna_parcaciklari.append(self)

    monkeypatch.setattr(threading, "Thread", _Thread)

    def _ayna_bitsin():
        for t in ayna_parcaciklari:
            t.join(5)

    return _api, {
        "olaylar": olaylar,
        "yayinlar": yayinlar,
        "aynalanan": aynalanan,
        "acilan": acilan,
        "bitsin": _ayna_bitsin,
    }


def _estop(api, kayit, sebep):
    sonuc = api._emergency_stop_all(reason=sebep, kalici=False)
    kayit["bitsin"]()
    return sonuc


def test_KRITIK_ESP_KAPALI_bulut_aynasi_HIC_calismaz_yerel_STOP_aynen(api, monkeypatch):
    _api, k = api
    monkeypatch.delenv("PEMF_ESP_ENABLED", raising=False)
    assert _api.live_state.esp_etkin() is False, "öncül: ESP kapalı olmalı"
    sonuc = _estop(_api, k, "yh-a3-esp-kapali")
    assert k["acilan"] == [], f"ESP kapalıyken bulut aynası iş parçacığı AÇILDI: {k['acilan']}"
    assert k["aynalanan"] == [], (
        f"ESP kapalıyken bulut aynası ÇAĞRILDI (sızmış HiveMQ kimliği, AP B9): {k['aynalanan']}"
    )
    # yerel yol AYNEN: STM STOP gider, yerel ESP STOP yayını DENENİR (sonucu `_esp_yanit_durumu` söyler)
    assert k["olaylar"] == ["stm_stop"], f"STM STOP gitmedi / beklenmeyen olay: {k['olaylar']}"
    assert any(t.startswith("pemf/coil/") for t in k["yayinlar"]), (
        "yerel ESP STOP denemesi kayboldu (yerel yol DEĞİŞMEMELİ)"
    )
    assert sonuc is not None


def test_KRITIK_ESP_ACIK_bulut_aynasi_ESKISI_GIBI_tum_ESP_bobinleri(api, monkeypatch):
    from topoloji import TUM_ESP, esp_yolu_gerekir

    esp_yolu_gerekir()
    _api, k = api
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    _estop(_api, k, "yh-a3-esp-acik")
    assert k["acilan"] == ["estop-cloud-mirror"], f"ESP açıkken ayna iş parçacığı açılmadı: {k['acilan']}"
    assert len(k["aynalanan"]) == 1, f"ESP açıkken bulut aynası çağrılmadı / iki kez çağrıldı: {k['aynalanan']}"
    bobinler, sebep = k["aynalanan"][0]
    assert bobinler == sorted(_api.ESP_COIL_IDS) and set(TUM_ESP) <= set(bobinler), bobinler
    assert sebep == "yh-a3-esp-acik"
    assert k["olaylar"][0] == "stm_stop", "STM STOP her durumda gider"


def test_bayrak_ACIL_DURDUR_aninda_okunur_onbellege_alinmaz(api, monkeypatch):
    _api, k = api
    for acik, beklenen in (("0", 0), ("1", 1), ("0", 1)):
        monkeypatch.setenv("PEMF_ESP_ENABLED", acik)
        _estop(_api, k, f"yh-a3-{acik}")
        assert len(k["aynalanan"]) == beklenen, (acik, k["aynalanan"])
