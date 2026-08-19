# Author: mertaygn, cglrgrkn
"""ESP komut TOPİĞİ — donanım-uyum denetimi D-1 (2026-08-19).

NEDEN VAR: selftest ve reset_pwm eskiden ÖLÜ bir topiğe (`pemf/esp32_{id}/command`) yayınlıyordu;
S3/8266 firmware'i `pemf/coil/{id}/control`'e abone, o topiğe DEĞİL. Sonuç: selftest ESP 6-8'de
HİÇ çalışmıyor (arızalı ESP sessizce geçer = yanlış tanısal güvence); reset sonrası seans-dışı
ESP bobini enerjili kalıyordu. Bu kapı, komutların ESP'nin GERÇEKTEN dinlediği topiğe gittiğini
+ ölü esp32_ topiğinin (E-stop legacy hariç) geri gelmediğini kilitler.
"""

from __future__ import annotations

import inspect

import servers.api_server as api


def _yakala(monkeypatch):
    """_mqtt_publish çağrılarını (topic, payload) olarak topla."""
    cagrilar = []
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: cagrilar.append((topic, payload)) or True)
    return cagrilar


def test_KRITIK_broadcast_ESP_bobinlerine_DOGRU_topige(monkeypatch):
    cagrilar = _yakala(monkeypatch)
    api._esp_control_broadcast("SELFTEST", "selftest")
    topikler = [t for t, _ in cagrilar]

    # yalnız ESP bobinleri (6,7,8), yalnız coil/control
    assert set(topikler) == {f"pemf/coil/{i}/control" for i in (6, 7, 8)}, (
        f"beklenen ESP control topikleri değil: {topikler}"
    )
    # ölü esp32_ topiği KULLANILMAMALI
    assert not any("esp32_" in t for t in topikler), "ölü pemf/esp32_ topiği geri geldi"
    # STM bobinleri (1-5) MQTT'ye çıkmamalı (seri protokol)
    assert not any(f"pemf/coil/{i}/" in t for t in topikler for i in range(1, 6)), (
        "STM bobinine MQTT komutu gitti (STM seri dinler)"
    )


def test_KRITIK_broadcast_komut_ve_command_id(monkeypatch):
    cagrilar = _yakala(monkeypatch)
    api._esp_control_broadcast("stop", "reset", extra={"emergency": False})
    for topic, payload in cagrilar:
        assert payload["command"] == "stop"
        assert payload["command_id"].startswith("reset_")
        assert payload["emergency"] is False  # extra birleşti


def test_KRITIK_selftest_reset_endpointleri_broadcast_KULLANIR():
    """Regresyon: iki endpoint de ölü esp32_ değil, _esp_control_broadcast çağırıyor."""
    src = inspect.getsource(api)
    # selftest + reset gövdelerinde broadcast çağrısı var
    assert src.count("_esp_control_broadcast(") >= 3, (
        "selftest/reset _esp_control_broadcast kullanmıyor (tanım + 2 çağrı beklenir)"
    )
    # ölü esp32_ topiği selftest/reset'te YOK — yalnız E-stop legacy (bilinçli) + docstring
    esp32_satirlar = [ln for ln in src.splitlines() if 'f"pemf/esp32_' in ln]
    assert len(esp32_satirlar) == 1, (
        f"pemf/esp32_ yayını beklenenden fazla ({len(esp32_satirlar)}) — selftest/reset'te geri gelmiş olabilir; "
        "yalnız E-stop legacy çift-yayını kalmalı"
    )
