# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D6.16 (B-3.97 · sahip kararı Y15) — `/api/settings` MQTT broker adresi / portunun bağlantıya ETKİSİZ olduğunu söyler.

Kusur: `POST /api/settings/` `mqtt_broker` / `mqtt_port`u `config.json`a (`mqtt.broker_url` / `mqtt.broker_port`) yazıp
`{"status": "success"}` diyordu; ama üretimde bu değerleri OKUYAN bağlantı kodu YOK — yerel broker istemcisi sabit
`127.0.0.1:1883`e bağlanır (`api_server._YEREL_BROKER`), ESP yolu kapalı (Y7). Operatör adresi değiştirip bağlantının değiştiğini
sanıyordu. Y15: ayar "KULLANILMIYOR" diye işaretlenir; kod SİLİNMEZ; değerlerin okunup yazılması (fail-closed kayıt) DEĞİŞMEZ.

Kapı:
  (1) ölçüm — üretim kodunda (`tests/` hariç, AST) `mqtt.broker_url` / `mqtt.broker_port`u okuyan yer yalnız ayar ucu ve
      yapılandırma yöneticisi; bağlantı hedefi sabit (`_YEREL_BROKER` = 127.0.0.1). Biri bağlantıya bağlanırsa bu kol KIRMIZI
      olur ve "etkisiz" yanıtı yeniden düşünülmelidir;
  (2) GERÇEK uç (TestClient, yapılandırma bellekte) — MQTT alanı gönderilen POST: değer YAZILIR, yanıt `mqtt_etkisiz: true` +
      istek dilinde not (TR / EN bayt bayt); MQTT alanı gönderilmeyen POST notsuz; GET de işaretli.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

KOK = Path(__file__).resolve().parents[1]

#: Katalog değerleri BAYT BAYT (i18n kuralı: kataloğa giren metnin TR'si pinlenir).
TR_NOT = (
    "MQTT broker adresi ve portu kaydedildi ama bağlantıya ETKİSİZ: cihaz bu ayarı okumuyor, yerel broker'a sabit adresten "
    "bağlanır (ESP yolu kapalı)."
)
EN_NOT = (
    "MQTT broker address and port were saved but have NO EFFECT on the connection: the device does not read this setting and "
    "connects to the local broker at a fixed address (ESP path disabled)."
)
_IZINLI = {"apps/backend/servers/settings_router.py", "apps/backend/utils/production_config_manager.py"}


# ── (1) ölçüm ─────────────────────────────────────────────────────────────────
def _uretim_py() -> list[str]:
    r = subprocess.run(["git", "ls-files", "-z", "--", "*.py"], cwd=KOK, capture_output=True, timeout=60)
    assert r.returncode == 0, f"aparat: git ls-files düştü (rc={r.returncode})"
    return [p for p in r.stdout.decode("utf-8").split("\0") if p and not p.startswith("tests/")]


def test_KRITIK_uretimde_broker_AYARINI_okuyan_baglanti_YOK_D6_16():
    okuyan = []
    for rel in _uretim_py():
        try:
            agac = ast.parse((KOK / rel).read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for d in ast.walk(agac):
            # Tur 2 (çürütücü): iç içe erişim (`cfg.get("mqtt")["broker_url"]`) de okuma sayılır — eskiden yalnız noktalı
            # anahtar aranıyordu, bağlantıyı iç içe okumayla ayara bağlayan kod KAÇIYORDU.
            if isinstance(d, ast.Constant) and d.value in (
                "mqtt.broker_url",
                "mqtt.broker_port",
                "broker_url",
                "broker_port",
            ):
                if rel not in _IZINLI:
                    okuyan.append(f"{rel}:{d.lineno} {d.value}")
    assert not okuyan, (
        "broker ayarını okuyan yeni kod var — ayar bağlantıya bağlanmış olabilir; `/api/settings` 'etkisiz' yanıtını "
        f"(D6.16 / Y15) yeniden değerlendirin: {okuyan}"
    )
    from servers import api_server

    assert api_server._YEREL_BROKER[0] == "127.0.0.1", (
        f"aparat: yerel broker hedefi değişti: {api_server._YEREL_BROKER}"
    )


# ── (2) gerçek uç ─────────────────────────────────────────────────────────────
class _SahteConfig:
    """Bellek-içi üretim yapılandırması — GERÇEK `config.json`a dokunulmaz (bkz. test_ayar_kismi_guncelleme.py)."""

    def __init__(self):
        self._d = {"mqtt.broker_url": "localhost", "mqtt.broker_port": 1883}

    def get(self, anahtar, varsayilan=None):
        return self._d.get(anahtar, varsayilan)

    def set(self, anahtar, deger, save=True):
        self._d[anahtar] = deger

    def save(self):
        return True


@pytest.fixture()
def uc(tmp_path, monkeypatch):
    from servers import settings_router

    monkeypatch.setattr(settings_router, "_settings_file", tmp_path / "system_settings.json")
    sahte = _SahteConfig()
    monkeypatch.setattr(settings_router, "get_production_config", lambda: sahte)
    from servers import api_server

    assert settings_router.get_production_config() is sahte  # SERT KAPI: gerçek yapılandırmaya dokunulmaz
    return TestClient(api_server.app, client=("127.0.0.1", 51235)), sahte


def test_KRITIK_katalog_metni_TR_ve_EN_BAYT_BAYT_D6_16():
    from utils import ceviri

    k = ceviri.kataloglar()
    tr, en = k["tr"].get("ayarlar.mqtt.etkisiz"), k["en"].get("ayarlar.mqtt.etkisiz")
    assert tr == TR_NOT, f"TR katalog metni farklı / yok: {tr!r}"
    assert en == EN_NOT, f"EN katalog metni farklı / yok: {en!r}"


@pytest.mark.parametrize("dil, beklenen", [("tr", TR_NOT), ("en", EN_NOT)], ids=["tr", "en"])
def test_KRITIK_MQTT_alani_gonderilen_POST_ETKISIZ_der_deger_YINE_yazilir_D6_16(uc, dil, beklenen):
    c, sahte = uc
    r = c.post("/api/settings/", json={"mqtt_broker": "10.0.0.9", "mqtt_port": "1884"}, headers={"X-PEMF-Dil": dil})
    assert r.status_code == 200, r.text
    govde = r.json()
    assert govde.get("status") == "success", govde
    assert govde.get("mqtt_etkisiz") is True, f"yanıt MQTT ayarının bağlantıya ETKİSİZ olduğunu söylemiyor: {govde}"
    assert govde.get("mqtt_notu") == beklenen, f"etkisiz notu istek dilinde değil ({dil}): {govde.get('mqtt_notu')!r}"
    assert sahte.get("mqtt.broker_url") == "10.0.0.9" and sahte.get("mqtt.broker_port") == 1884, (
        "değer YAZILMADI — Y15 yalnız işaretler, kaydı değiştirmez"
    )


@pytest.mark.parametrize(
    "gonderilen", [{"mqtt_port": "1885"}, {"mqtt_broker": "10.0.0.7"}], ids=["yalniz_port", "yalniz_adres"]
)
def test_KRITIK_TEK_MQTT_alani_gonderilen_POST_de_ETKISIZ_der_D6_16(uc, gonderilen):
    """Tur 2 (çürütücü): yukarıdaki kol iki alanı BİRLİKTE gönderiyordu — MQTT alan kümesinden biri düşse (yalnız port değişen
    kayıt) not çıkmaz, kapı yeşil kalırdı."""
    c, _ = uc
    govde = c.post("/api/settings/", json=gonderilen, headers={"X-PEMF-Dil": "tr"}).json()
    assert govde.get("mqtt_etkisiz") is True and govde.get("mqtt_notu") == TR_NOT, (
        f"yalnız {sorted(gonderilen)} gönderilen kayıtta etkisiz notu YOK: {govde}"
    )


def test_MQTT_alani_GONDERILMEYEN_POST_notsuz_D6_16(uc):
    c, _ = uc
    govde = c.post("/api/settings/", json={"clinic_name": "Minnos"}).json()
    assert govde == {"status": "success"}, f"MQTT alanı gönderilmeyen kayıtta etkisiz notu çıktı: {govde}"


def test_KRITIK_GET_ayarlar_MQTT_ETKISIZ_isaretli_D6_16(uc):
    c, _ = uc
    govde = c.get("/api/settings/", headers={"X-PEMF-Dil": "en"}).json()
    assert govde.get("mqtt_broker") == "localhost", f"aparat: değer okunmadı: {govde}"
    assert govde.get("mqtt_etkisiz") is True and govde.get("mqtt_notu") == EN_NOT, govde
