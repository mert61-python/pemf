# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KP-2 · apps/backend/servers/settings_router.py · sözleşmeler: bozuk `system_settings.json` varsayılana düşer · sayısal
olmayan MQTT portu kayıtlı portu korur · ayar dosyası yazılamazsa geçici dosya kalmaz ve ASIL hata yükselir (sahte "success"
YOK, 500) · arayüz dili / kabin kamerası seçimi diske yazılamazsa eylem söyleyen 503 · AI Pro kamerayı tutuyorsa (gerçek
`ai_router` bayrakları) kare 409 · `ai_router` yüklenemezse kamera "meşgul" sayılmaz.

Sahte yalnız EN ALT katta: dosya sistemi (tmp; hedef yolda DİZİN → gerçek `os.replace` hatası), `os.unlink` (silinemeyen geçici
dosya). Üretim yapılandırması `test_ayar_kismi_guncelleme.py` ile aynı bellek-içi sahte (gerçek `get/set(save=)/save` imzası).
Sunucu yalnız süreç içi (`TestClient`, router'ı taşıyan küçük uygulama) — dinleyici yok.
"""

from __future__ import annotations

import json
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


class _SahteConfig:
    """Bellek-içi üretim yapılandırması (`ProductionConfigManager.get/set/save` imzası)."""

    def __init__(self, broker="10.1.1.1", port=1884):
        self._d = {"mqtt.broker_url": broker, "mqtt.broker_port": port}
        self.kaydedildi = 0

    def get(self, anahtar, varsayilan=None):
        return self._d.get(anahtar, varsayilan)

    def set(self, anahtar, deger, save=True):
        self._d[anahtar] = deger

    def save(self):
        self.kaydedildi += 1
        return True


@pytest.fixture()
def ortam(tmp_path, monkeypatch):
    from servers import settings_router as sr

    ayar = tmp_path / "ayarlar" / "system_settings.json"
    ayar.parent.mkdir()
    monkeypatch.setattr(sr, "_settings_file", ayar)
    cfg = _SahteConfig()
    monkeypatch.setattr(sr, "get_production_config", lambda: cfg)
    monkeypatch.delenv("PEMF_KABIN_KAMERASI", raising=False)
    app = FastAPI()
    app.include_router(sr.router)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield sr, c, cfg, ayar


def _veri_koku():
    from utils.path_utils import get_app_data_directory

    return get_app_data_directory()


# ── 1. system_settings.json okuma / yazma ────────────────────────────────────────────────────────────────────────────


def test_bozuk_ayar_dosyasi_VARSAYILANA_duser_MQTT_configden_gelir(ortam):
    """Bozuk JSON → istisna YOK; klinik adı / MAC boş, MQTT değerleri config'ten (port dizge)."""
    sr, c, _cfg, ayar = ortam
    ayar.write_text("{bozuk json", encoding="utf-8")
    assert sr.load_settings() == {
        "clinic_name": "",
        "ble_gateway_mac": "",
        "mqtt_broker": "10.1.1.1",
        "mqtt_port": "1884",
    }
    r = c.get("/api/settings/")
    assert r.status_code == 200 and r.json()["clinic_name"] == "" and r.json()["mqtt_etkisiz"] is True


def test_sayisal_OLMAYAN_mqtt_portu_kayitli_portu_KORUR_digerleri_yazilir(ortam):
    """`mqtt_port: "abc"` → port config'te DEĞİŞMEZ (int'e çevrilemez), broker + klinik adı yazılır, istek başarılı."""
    sr, c, cfg, ayar = ortam
    r = c.post("/api/settings/", json={"mqtt_port": "abc", "mqtt_broker": "10.2.2.2", "clinic_name": "Pati"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "success" and r.json()["mqtt_etkisiz"] is True
    assert cfg._d["mqtt.broker_port"] == 1884, "sayısal olmayan port kayıtlı portu ezdi"
    assert cfg._d["mqtt.broker_url"] == "10.2.2.2" and cfg.kaydedildi == 1
    assert json.loads(ayar.read_text(encoding="utf-8"))["clinic_name"] == "Pati"


def test_ayar_dosyasi_YAZILAMAZSA_500_gecici_dosya_KALMAZ_success_DONMEZ(ortam):
    """Hedef yol bir DİZİN (gerçek `os.replace` hatası) → uç 500 (kayıt reddi değil → yükselir), `.tmp` artığı yok."""
    sr, c, _cfg, ayar = ortam
    ayar.mkdir()
    with pytest.raises(OSError):
        sr.save_settings({"clinic_name": "X"})
    r = c.post("/api/settings/", json={"clinic_name": "X"})
    assert r.status_code == 500, f"yazılamayan ayar 'success' döndü: {r.status_code} {r.text}"
    assert "success" not in r.text
    assert sorted(p.name for p in ayar.parent.iterdir()) == ["system_settings.json"], "geçici dosya artığı kaldı"


def test_gecici_dosya_SILINEMESE_de_ASIL_yazma_hatasi_yukselir(ortam, monkeypatch):
    """`os.replace` düştü + `os.unlink` de düştü (dosya kilitli) → yükselen hata replace'inki; unlink hatası yutulur."""
    sr, _c, _cfg, ayar = ortam
    ayar.mkdir()
    silinmek_istenen = []

    def _kilitli_unlink(yol, *a, **k):
        silinmek_istenen.append(str(yol))
        raise PermissionError(13, "kp2-sahte-unlink-kilitli", str(yol))

    monkeypatch.setattr(sr.os, "unlink", _kilitli_unlink)
    with pytest.raises(OSError) as hata:
        sr.save_settings({"clinic_name": "X"})
    assert "kp2-sahte-unlink-kilitli" not in str(hata.value), "unlink hatası asıl hatayı gölgeledi"
    assert len(silinmek_istenen) == 1 and silinmek_istenen[0].endswith(".tmp")
    assert str(ayar.parent) in silinmek_istenen[0]


# ── 2. arayüz dili / kabin kamerası seçimi diske yazılamazsa ─────────────────────────────────────────────────────────


def test_arayuz_dili_YAZILAMAZSA_503_eylem_metni_ve_ayar_degismez(ortam):
    from utils import ceviri

    _sr, c, _cfg, _ayar = ortam
    kok = _veri_koku()
    (kok / ceviri.CIHAZ_DILI_DOSYASI).mkdir(parents=True)
    r = c.post("/api/settings/arayuz-dili", json={"dil": "en"})
    assert r.status_code == 503, r.text
    assert r.json()["detail"] == ceviri.t("ayarlar.arayuzDili.yazilamadi", dil="tr", neden="PermissionError")
    assert c.get("/api/settings/arayuz-dili").json() == {"dil": None}
    assert not list(kok.glob("*.tmp")), "geçici dil dosyası artığı kaldı"


def test_kabin_kamerasi_secimi_YAZILAMAZSA_503_eylem_metni_ve_secim_yok(ortam):
    from utils import ceviri
    from utils import kabin_kamerasi as kk

    _sr, c, _cfg, _ayar = ortam
    kok = _veri_koku()
    (kok / kk.KAMERA_DOSYASI).mkdir(parents=True)
    r = c.post("/api/settings/kabin-kamerasi", json={"indeks": 1})
    assert r.status_code == 503, r.text
    assert r.json()["detail"] == ceviri.t("ayarlar.kabinKamerasi.yazilamadi", dil="tr", neden="PermissionError")
    assert kk.secili_kamera() is None
    assert not list(kok.glob("*.tmp"))


# ── 3. AI Pro kamerayı tutuyor mu (gerçek ai_router bayrakları) ──────────────────────────────────────────────────────


def test_AI_hazirlik_ya_da_dongu_aktifse_kare_ve_tarama_409(ortam, monkeypatch):
    from servers import ai_router
    from utils import ceviri

    sr, c, _cfg, _ayar = ortam
    monkeypatch.setattr(ai_router, "_ai_hazirlik_active", False)
    monkeypatch.setattr(ai_router, "_ai_loop_active", False)
    assert sr._ai_kamerasi_mesgul() is False
    monkeypatch.setattr(ai_router, "_ai_loop_active", True)
    assert sr._ai_kamerasi_mesgul() is True
    r = c.post("/api/settings/kabin-kamerasi/kare")
    assert r.status_code == 409 and r.json()["detail"] == ceviri.t("ayarlar.kabinKamerasi.kareMesgul", dil="tr")
    monkeypatch.setattr(ai_router, "_ai_loop_active", False)
    monkeypatch.setattr(ai_router, "_ai_hazirlik_active", True)
    r = c.post("/api/settings/kabin-kamerasi/tara")
    assert r.status_code == 409 and r.json()["detail"] == ceviri.t("ayarlar.kabinKamerasi.taramaMesgul", dil="tr")


def test_ai_router_YUKLENEMEZSE_kamera_mesgul_SAYILMAZ(ortam, monkeypatch):
    import servers

    sr, _c, _cfg, _ayar = ortam
    monkeypatch.delattr(servers, "ai_router", raising=False)
    monkeypatch.setitem(sys.modules, "servers.ai_router", None)
    assert sr._ai_kamerasi_mesgul() is False
