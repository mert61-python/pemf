# -*- coding: utf-8 -*-
"""KP-1 · `utils/telemetry.py` · sözleşmeler (KVKK): uzaktan hata izleme VARSAYILAN KAPALI (DSN yoksa ve SDK yoksa no-op) · açılınca
yalnız hata (performans izleme yok), PII gönderilmez, iz kırıntıları (log satırları) TAMAMEN düşer · giden olayda istek / kullanıcı / iz
kırıntısı / ek alanlar silinir, ileti ve istisna değeri maskelenir, yığın çerçevesi yerelleri atılır · bozuk olay temizlikte çökmez ·
başlatma hatası açılışı durdurmaz · ikinci çağrı yeniden başlatmaz.

Ağa ÇIKILMAZ: `sentry_sdk` modülü EN ALT katta sahte (sys.modules; gerçek SDK / DSN yok). Modül durumu (`_initialized`) geri konur.
"""

from __future__ import annotations

import logging
import sys
import types

import pytest
from utils import telemetry as tm


@pytest.fixture
def sdk(monkeypatch):
    monkeypatch.setattr(tm, "_initialized", False)
    for ad in ("PEMF_SENTRY_DSN", "PEMF_DEVICE_NAME", "PEMF_VERSION"):
        monkeypatch.delenv(ad, raising=False)
    sahte = types.ModuleType("sentry_sdk")
    sahte.cagrilar = []
    sahte.patla = False

    def _init(**kw):
        if sahte.patla:
            raise ValueError("geçersiz DSN")
        sahte.cagrilar.append(kw)

    sahte.init = _init
    monkeypatch.setitem(sys.modules, "sentry_sdk", sahte)
    return sahte


def test_KRITIK_giden_olayda_PII_tasiyan_her_blok_silinir_ya_da_maskelenir():
    olay = {
        "request": {"url": "/api/patients/42"},
        "user": {"ip_address": "10.0.0.5"},
        "extra": {"hasta": "Pamuk"},
        "breadcrumbs": {"values": [{"message": "Hasta Pamuk (tel 0555…) kaydedildi"}]},
        "logentry": {"message": "Hasta %s", "params": ["Pamuk"]},
        "message": "Pamuk için seans",
        "exception": {
            "values": [
                {
                    "type": "ValueError",
                    "value": "Pamuk bulunamadı",
                    "stacktrace": {"frames": [{"function": "f", "vars": {"hasta_adi": "Pamuk"}}]},
                }
            ]
        },
        "level": "error",
    }
    sonuc = tm._scrub_event(olay, None)
    assert not {"request", "user", "extra", "breadcrumbs"} & set(sonuc)
    assert sonuc["logentry"] == {"message": "[scrubbed]"} and sonuc["message"] == "[scrubbed]"
    istisna = sonuc["exception"]["values"][0]
    assert istisna["value"] == "[scrubbed]" and istisna["type"] == "ValueError", "istisna türü (PII değil) kayboldu"
    assert "vars" not in istisna["stacktrace"]["frames"][0] and istisna["stacktrace"]["frames"][0]["function"] == "f"
    assert "Pamuk" not in repr(sonuc), "olayda hasta adı kaldı"


def test_bozuk_olay_temizlikte_COKMEZ_olduğu_gibi_doner():
    bozuk = ["olay", "değil"]
    assert tm._scrub_event(bozuk, None) is bozuk


def test_KRITIK_DSN_yoksa_KAPALI_SDK_hic_cagrilmaz(sdk):
    assert tm.init_telemetry() is False and sdk.cagrilar == []


def test_DSN_var_SDK_YOKSA_kapali_ve_uyari(sdk, monkeypatch, caplog):
    monkeypatch.setenv("PEMF_SENTRY_DSN", "https://anahtar@ornek.invalid/1")
    monkeypatch.setitem(sys.modules, "sentry_sdk", None)
    with caplog.at_level(logging.WARNING, logger=tm.logger.name):
        assert tm.init_telemetry() is False
    assert any("sentry-sdk kurulu değil" in r.getMessage() for r in caplog.records)


def test_KRITIK_acilinca_yalniz_HATA_PII_yok_iz_kirintisi_DUSER_ikinci_cagri_yeniden_baslatmaz(sdk, monkeypatch):
    monkeypatch.setenv("PEMF_SENTRY_DSN", " https://anahtar@ornek.invalid/1 ")
    monkeypatch.setenv("PEMF_DEVICE_NAME", "klinik-3")
    monkeypatch.setenv("PEMF_VERSION", "1.9.52")
    assert tm.init_telemetry() is True and tm.init_telemetry() is True
    assert len(sdk.cagrilar) == 1, "telemetri iki kez başlatıldı"
    kw = sdk.cagrilar[0]
    assert kw["dsn"] == "https://anahtar@ornek.invalid/1" and kw["traces_sample_rate"] == 0.0
    assert kw["send_default_pii"] is False and kw["before_send"] is tm._scrub_event
    assert kw["before_breadcrumb"]({"message": "Hasta Pamuk"}, None) is None, (
        "log satırı iz kırıntısı olarak buluta gider"
    )
    assert (kw["environment"], kw["release"]) == ("klinik-3", "1.9.52")


def test_surum_yoksa_release_None_baslatma_PATLARSA_acilis_surer(sdk, monkeypatch, caplog):
    monkeypatch.setenv("PEMF_SENTRY_DSN", "https://anahtar@ornek.invalid/1")
    monkeypatch.setenv("PEMF_VERSION", "  ")
    sdk.patla = True
    with caplog.at_level(logging.ERROR, logger=tm.logger.name):
        assert tm.init_telemetry() is False
    assert tm._initialized is False and any("Sentry init başarısız" in r.getMessage() for r in caplog.records)
    sdk.patla = False
    assert (
        tm.init_telemetry() is True
        and sdk.cagrilar[0]["release"] is None
        and sdk.cagrilar[0]["environment"] == "pemf-device"
    )
