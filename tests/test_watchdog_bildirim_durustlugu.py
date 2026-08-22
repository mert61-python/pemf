# Author: mertaygn, cglrgrkn
"""[5.8] Watchdog bildirim DÜRÜSTLÜĞÜ (2. tur denetimi, sahip onayı 2026-08-20).

`_esp_telemetry_watchdog` bayat bobine STOP yayınlar ama publish SONUCUNU okumuyordu:
broker çökükken bildirim yine "STOP gönderildi" diyordu — STOP gitmemiştir, bobin ESP'de
kendi süresi bitene dek enerjili kalabilir; operatöre YANLIŞ GÜVENCE (bu deponun 1. tur
ciddiyet-1 bulgusuyla aynı sınıf: sahte "durduruldu" onayı). Yorumdaki "log'a düşülür"
vaadi de gerçekleşmiyordu (probe False döner, istisna atmaz → except hiç koşmaz).

DÜZELTME: publish sonucu okunur; False/istisna → bildirim "STOP GÖNDERİLEMEDİ … HÂLÂ
ENERJİLİ olabilir" (error) + uyarı logu; True → mevcut "STOP gönderildi" (warning) AYNEN
(karşıt-kanıt: dürüstlük düzeltmesi başarılı yolda alarm yorgunluğu üretmemeli).

Watchdog tek-tur sürme deseni test_kalan_davranissal.py'den (sleep try-dışında → istisnayla çık).
"""

import time

import pytest


class _Dur(Exception):
    pass


def _tek_tur_watchdog(api, monkeypatch, publish, coil_idx=5):
    """Bobin (idx) bayat+connected kur, watchdog'u TEK tur koştur, bildirimleri döndür."""
    bildirimler = []
    monkeypatch.setattr(api, "_mqtt_publish", publish)
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(api, "_push_notification", lambda msg, sev="info": bildirimler.append((msg, sev)))
    with api._live_state_lock:
        api._live_state["coils"][coil_idx]["connected"] = True
        api._live_state["coils"][coil_idx]["running"] = True
    api._coil_last_telemetry[coil_idx] = time.monotonic() - (api.ESP_STALE_SEC + 10)

    def _sleep(_s):
        raise _Dur()

    monkeypatch.setattr(api.time, "sleep", _sleep)
    with pytest.raises(_Dur):
        api._esp_telemetry_watchdog()
    return bildirimler


def test_KRITIK_publish_False_iken_STOP_gonderildi_DENMEZ(monkeypatch, caplog):
    """Broker çökük (probe False): bildirim 'STOP gönderildi' DİYEMEZ; gönderilemediğini
    söylemeli (error) ve log'a düşmeli — bobin fiziksel olarak enerjili olabilir."""
    from servers import api_server as api

    with caplog.at_level("WARNING"):
        bildirimler = _tek_tur_watchdog(api, monkeypatch, lambda t, p: False)

    assert bildirimler, "bayat bobin için hiç bildirim çıkmadı"
    metinler = " | ".join(m for m, _ in bildirimler)
    assert "STOP gönderildi" not in metinler, (
        f"publish False iken bildirim hâlâ 'STOP gönderildi' diyor — yanlış güvence (bulgu [5.8]): {metinler!r}"
    )
    assert "GÖNDERİLEMEDİ" in metinler, f"gönderilemediği söylenmiyor: {metinler!r}"
    assert any(sev == "error" for _, sev in bildirimler), "teslim edilemeyen STOP 'error' ciddiyetinde olmalı"
    assert any("STOP" in r.getMessage() for r in caplog.records), (
        "yorumdaki 'log'a düşülür' vaadi hâlâ gerçekleşmiyor (uyarı logu yok)"
    )


def test_KRITIK_publish_istisnasi_da_ayni_durust_yolda(monkeypatch):
    """Publish istisna atarsa da (False'la aynı sınıf) 'STOP gönderildi' denmez."""
    from servers import api_server as api

    def _patla(t, p):
        raise RuntimeError("broker socket error")

    bildirimler = _tek_tur_watchdog(api, monkeypatch, _patla)
    metinler = " | ".join(m for m, _ in bildirimler)
    assert bildirimler and "STOP gönderildi" not in metinler and "GÖNDERİLEMEDİ" in metinler, (
        f"istisna yolunda dürüst bildirim yok: {metinler!r}"
    )


def test_KARSIT_KANIT_publish_True_iken_mevcut_bildirim_AYNEN(monkeypatch):
    """Başarılı publish'te davranış DEĞİŞMEZ: 'STOP gönderildi' (warning) — alarm yorgunluğu
    üretme; dürüstlük düzeltmesi aşırı-genişleyip başarılı yolu error'a çeviremez."""
    from servers import api_server as api

    bildirimler = _tek_tur_watchdog(api, monkeypatch, lambda t, p: True)
    assert bildirimler, "başarılı yolda bildirim kayboldu (aşırı-düzeltme)"
    metinler = " | ".join(m for m, _ in bildirimler)
    assert "STOP gönderildi" in metinler, f"başarılı yolun bildirimi değişmiş: {metinler!r}"
    assert all(sev == "warning" for _, sev in bildirimler), "başarılı yol 'warning' kalmalı"
