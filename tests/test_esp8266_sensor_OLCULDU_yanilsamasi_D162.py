# Author: mertaygn, cglrgrkn
"""D1.62 · B-8.12 — ESP8266 sensör katmanında "ölçüldü" yanılsaması: akım bayrağı DONANIMA göre, türetilen ACS712
hassasiyeti kullanılır, geçici okuma arızasında SON SAĞLIKLI değer (hiç yoksa NaN) döner — yapıcı sabiti değil.

ÖLÇÜLEN KUSUR (DENETIM-08 §B-8.12; 08-2 grup e — aynı senaryolar bu aparatla 1-G'de yeniden üretildi):
  * sensör yokken `current_sensor_ok = 1` (koşulsuz `true`): toprak 0,000 A · YÜZEN pin 2,27 A · 3,3 V 0,000 A;
  * `_acsSensitivity` (0,066·k) hesaplanıyor ama okumada sabit `/ 0.066` → bölücülü kartta (k = 0,716) 5 A → 3,57 A;
  * geçici sıcaklık arızasında `getData()` 30,00 °C (yapıcı sabiti) döner — son iyi değer 36,50 dururken; alan 0,000 mT
    (eksenler bayat kalır); sıcaklık hiç okunamadıysa da 30,00 / 25,00 "fallback" olarak yayınlanır.
Başlık (`SensorManager.h`) "Geçici okuma arızasında son sağlıklı değer döner" diyordu — kod yapmıyordu.

ZİNCİRİN DEVAMI (düzeltme NaN'ı yaygınlaştırdığı için ŞART): `publishSensorData` NaN'ı `%.2f` ile `nan` yazıyordu = GEÇERSİZ
JSON → backend iletinin TAMAMINI atar (sıcaklık dahil); backend'in `sensors` dalı da `null` alanda `float(None)` ile iletinin
geri kalanını düşürüyordu. Artık sonlu olmayan alan `null` (`JsonSayi.h`, ana makinede ölçülür; NetworkManager.cpp Secrets.h
içerdiği için DERLENMEZ — kullanım yorumsuz kaynakta pinli) ve backend `null` alanı yalnız kendisi için atlar.

ARAÇ: GERÇEK `SensorManager.cpp` ana makinede (`tests/esp8266_sensor_aparat.py`; bayt bayt kopya + sha256), `.ino` çağrı
düzeni (`beginWithoutCalibration` → `calibrate` → `update` döngüsü), A0 modelleri ve MLX taklitleri. ESP kodu SİLİNMEZ
(Ö.4-Y7); termal kesme (Y40, 100 °C — `temp_sensor_ok`'a bakar) bu maddede DEĞİŞMEZ. TEZGÂH: gerçek ACS712 kablolaması
BİLİNMİYOR (isteğe bağlı Oturum 13 teyidi).
"""

from __future__ import annotations

import math

import pytest
from akim_olcumu_aparati import akim_olcumu_acik  # noqa: F401  (CH4 · Y154: akım sensörü AÇIKKEN yolu)


@pytest.fixture(scope="module")
def exe(tmp_path_factory):
    import esp8266_sensor_aparat as ea

    return ea.derle(tmp_path_factory.mktemp("esp8266_sensor"))


def _oku(exe, senaryo: str, tmp_path) -> list[dict]:
    import esp8266_sensor_aparat as ea

    return ea.kos(exe, senaryo, tmp_path)["okumalar"]


@pytest.mark.parametrize("model", ["toprak", "yuzen", "3v3"])
def test_KRITIK_D162_akim_sensoru_YOKKEN_bayrak_0_ve_deger_NaN(exe, tmp_path, model):
    d = _oku(exe, f"A0 {model}\nBASLAT\nGUNCELLE 3000\nOKU\n", tmp_path)[-1]
    assert d["cur_ok"] is False, f"A0 {model} (ACS712 yok): current_sensor_ok=1, akım {d['akim']} A ÖLÇÜLMÜŞ gibi"
    assert math.isnan(d["akim"]), f"A0 {model}: sensör yokken akım {d['akim']} A yayınlanıyor (NaN beklenir)"


@pytest.mark.parametrize("k", [1.0, 0.716, 0.5])
def test_KRITIK_D162_turetilmis_ACS712_hassasiyeti_KULLANILIR_5A_okunur(exe, tmp_path, k):
    d = _oku(exe, f"A0 acs {k}\nBASLAT\nAKIM 5\nGUNCELLE 3000\nOKU\n", tmp_path)[-1]
    assert d["cur_ok"] is True, f"k={k}: ACS712 TAKILIYKEN akım bayrağı 0"
    assert 4.85 <= d["akim"] <= 5.15, f"k={k}: 5 A → {d['akim']:.3f} A (sabit 0,066 V/A bölücüyü yok sayıyor)"


_IYI = "A0 acs 1.0\nMLX614 1\nSICAKLIK 36.5 25.0\nMLX393 1\nMAG 100 200 300\nBASLAT\nGUNCELLE 3000\nOKU\n"


def test_KRITIK_D162_gecici_arizada_SON_SAGLIKLI_deger_doner(exe, tmp_path):
    iyi, ariza = _oku(exe, _IYI + "SICAKLIK_HATA 1\nMAG_HATA 1\nGUNCELLE 1100\nOKU\n", tmp_path)[-2:]
    assert iyi["temp_ok"] and iyi["nesne"] == pytest.approx(36.5), f"aparat: iyi okuma yok {iyi}"
    assert ariza["temp_ok"] is False, f"aparat: arıza oluşmadı {ariza}"
    assert ariza["nesne"] == pytest.approx(36.5) and ariza["ortam"] == pytest.approx(25.0), (
        f"geçici sıcaklık arızasında {ariza['nesne']} / {ariza['ortam']} — son sağlıklı değer 36,50 / 25,00 değil "
        "(yapıcı sabiti ölçülmüş gibi yayınlanıyor)"
    )
    assert ariza["mag_ok"] is False and ariza["mag"] == pytest.approx(iyi["mag"], rel=1e-3), (
        f"geçici alan arızasında {ariza['mag']} mT — son sağlıklı değer {iyi['mag']}"
    )
    assert ariza["eksen"] == pytest.approx(iyi["eksen"], rel=1e-3), "eksenler alanla tutarsız"


def test_KRITIK_D162_hic_saglikli_okuma_YOKSA_NaN_sabit_DEGIL(exe, tmp_path):
    d = _oku(exe, "A0 acs 1.0\nMLX614 0\nMLX393 0\nBASLAT\nGUNCELLE 3000\nOKU\n", tmp_path)[-1]
    assert d["temp_ok"] is False and d["mag_ok"] is False
    assert math.isnan(d["nesne"]) and math.isnan(d["ortam"]), (
        f"sıcaklık sensörü hiç okunmadı ama {d['nesne']} / {d['ortam']} °C yayınlanıyor (NaN beklenir)"
    )
    assert math.isnan(d["mag"]), f"alan sensörü hiç okunmadı ama {d['mag']} mT yayınlanıyor (NaN beklenir)"


def test_KARSIT_D162_saglikli_sensorler_OLCULEN_degeri_ve_ok_1_verir(exe, tmp_path):
    d = _oku(exe, _IYI, tmp_path)[-1]
    assert d["temp_ok"] and d["mag_ok"] and d["cur_ok"], d
    assert d["nesne"] == pytest.approx(36.5) and d["mag"] == pytest.approx(
        math.sqrt(100**2 + 200**2 + 300**2) / 1000, rel=1e-3
    )
    assert abs(d["akim"]) < 0.2, f"akımsız ACS712'de {d['akim']} A"


# ── yayın zinciri: NaN JSON'da `null` (8266 JsonSayi.h) ve backend `sensors` dalı `null` alanı yalnız KENDİSİ için atlar ──


def test_KRITIK_D162_JsonSayi_sonlu_olmayani_null_sonluyu_ESKI_basamakla_yazar(tmp_path):
    import json

    import esp8266_sensor_aparat as ea

    if not (ea.FW / "JsonSayi.h").is_file():
        pytest.fail(
            "firmware/esp8266_pemf_coil/JsonSayi.h YOK — NaN alanlar `nan` (geçersiz JSON) yazılır", pytrace=False
        )
    s = ea.json_sayi(tmp_path)
    assert s[("nan", 2)] == "null" and s[("inf", 2)] == "null" and s[("-inf", 3)] == "null", s
    assert s[("36.5", 2)] == "36.50" and s[("0.37416", 3)] == "0.374" and s[("0", 2)] == "0.00", s
    assert s[("-1.25", 2)] == "-1.25", s
    for cikti in s.values():
        json.loads(f'{{"x":{cikti}}}')  # her çıktı GEÇERLİ JSON değeri


def test_KRITIK_D162_publishSensorData_dort_olcum_alanini_JsonSayi_ile_yazar():
    """NetworkManager.cpp `Secrets.h` içerdiği için ana makinede DERLENMEZ (Ö.4-Y6) — kullanım yorumsuz kaynakta pinlenir:
    dört ölçüm alanının biçimi `%s` ve argümanı `jsonSayi(...)`; ham `%.2f`/`%.3f` ölçüm alanı KALMAZ."""
    import re

    import esp8266_sensor_aparat as ea
    from c_soyucu import c_soy

    kod = c_soy((ea.FW / "NetworkManager.cpp").read_text(encoding="utf-8", errors="replace"))
    bas = kod.index("void NetworkManager::publishSensorData(")
    govde = kod[bas : kod.index("\n}\n", bas)]
    duz = re.sub(r"\s+", " ", govde)
    assert '#include "JsonSayi.h"' in kod, "NetworkManager.cpp JsonSayi.h'yi içermiyor"
    for alan in ("object_temp", "ambient_temp", "magnetic_field", "current"):
        assert re.search(rf'\\"{alan}\\":%s', duz), f"{alan} alanı `%s` (jsonSayi) ile basılmıyor"
    for veri, basamak in (("tempObject", 2), ("tempAmbient", 2), ("magneticField", 3), ("current", 2)):
        assert re.search(rf"jsonSayi\(\s*\w+,\s*sizeof\(\w+\),\s*data\.{veri},\s*{basamak}\s*\)", duz), (
            f"data.{veri} jsonSayi(..., {basamak}) ile biçimlenmiyor"
        )
    assert not re.search(r"%\.\d+f", duz), "publishSensorData'da ham %.Nf ölçüm biçimi kaldı (NaN → `nan`)"


@pytest.fixture()
def api(monkeypatch):
    import servers.api_server as api
    from topoloji import ESP_BOBIN

    yayin: list = []
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda m, *a, **k: yayin.append(m))
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)
    monkeypatch.setattr(api, "_reconcile_esp_calisiyor", lambda *a, **k: None)
    monkeypatch.setattr(api._sensor_kaydedici, "kaydet", lambda *a, **k: False)
    i = ESP_BOBIN - 1
    eski_tel = dict(api._coil_last_telemetry)
    with api._live_state_lock:
        eski = dict(api._live_state["coils"][i])
        api._live_state["coils"][i].update(
            {"connected": False, "objectTemp": 11.1, "ambientTemp": 22.2, "currentA": 3.333, "magneticMt": 4.44}
        )
    yield api, i, yayin
    with api._live_state_lock:
        api._live_state["coils"][i].clear()
        api._live_state["coils"][i].update(eski)
    api._coil_last_telemetry.clear()
    api._coil_last_telemetry.update(eski_tel)


def _sensor_iletisi(bobin: int, govde: str):
    class _Msg:
        pass

    m = _Msg()
    m.topic = f"pemf/coil/{bobin}/sensors"
    m.retain = False
    m.payload = govde.encode("utf-8")
    return m


def test_KRITIK_D162_backend_sensors_null_alani_ATLAR_digerlerini_YAZAR_ve_YAYINLAR(api):
    """8266'nın GERÇEK biçimi (`publishSensorData`): akım sensörü yok → `"current":null`, `current_sensor_ok:false`."""
    api_mod, i, yayin = api
    from topoloji import ESP_BOBIN

    govde = (
        f'{{"coil_id":{ESP_BOBIN},"timestamp":1,"object_temp":36.50,"ambient_temp":25.00,"magnetic_field":0.374,'
        '"current":null,"temp_sensor_ok":true,"magnetic_sensor_ok":true,"current_sensor_ok":false,"sensors_ok":true}'
    )
    api_mod._on_mqtt_message_api(None, None, _sensor_iletisi(ESP_BOBIN, govde))
    with api_mod._live_state_lock:
        b = dict(api_mod._live_state["coils"][i])
    assert b["objectTemp"] == 36.5 and b["magneticMt"] == pytest.approx(0.37), f"sonlu alanlar yazılmadı: {b}"
    assert b["currentA"] == 3.333, f"`null` akım {b['currentA']} yazdı (ölçülmemiş değer ölçülmüş gibi / 0 nöbetçisi)"
    assert b["connected"] is True, "null alan iletinin geri kalanını düşürdü (bağlantı yazılmadı)"
    assert any(m.get("type") == "sensor_data" for m in yayin), "null alan WS yayınını düşürdü"


def test_KARSIT_D162_backend_sensors_tum_alanlar_sayiyken_HEPSINI_yazar(api):
    api_mod, i, _y = api
    from topoloji import ESP_BOBIN

    govde = f'{{"coil_id":{ESP_BOBIN},"object_temp":30.25,"ambient_temp":24.5,"magnetic_field":1.234,"current":0.5}}'
    api_mod._on_mqtt_message_api(None, None, _sensor_iletisi(ESP_BOBIN, govde))
    with api_mod._live_state_lock:
        b = dict(api_mod._live_state["coils"][i])
    assert (b["objectTemp"], b["ambientTemp"], b["magneticMt"], b["currentA"]) == (30.2, 24.5, 1.23, 0.5), b
