# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""TEK GÜNCELLEME KANALI — split-brain hasta DB'si olamaz (2026-08-09 denetimi, Tier 3).

ARIZA: cihazda AYNI ANDA iki güncelleme kanalı canlıydı.
  • YENİ: PEMF Vet Client (launcher) — katmanlı paket, atomik takas, sağlık kapılı geri alma,
    `rollout` + `min_supported_version`. Kurulumu O yönetir.
  • ESKİ: bu modül — `pemf-update` deposunun `exe` dalındaki `latest.json` + Inno `/VERYSILENT`.

Eski kanal iki yüzden kaldırılmalı:
  1) ÖLÜ — `exe/latest.json` 404 (ölçüldü 2026-08-10). Denetleyici 6 saatte bir boşuna ağa
     çıkıyor; `previousStable` hiç dolmadığı için `/api/update/rollback` ÇALIŞAMIYOR. Buna
     rağmen RUNBOOK "kötü güncelleme"de tam o komutu gösteriyordu.
  2) TEHLİKELİ — dosya bir gün yeniden yayınlanırsa Inno installer, launcher'ın yönettiği
     kurulumun YANINA ikinci bir backend + ikinci veri kökü kurar. Seanslar iki ayrı hasta
     veritabanına bölünür ve HER İKİSİ de eksiksiz görünür.

Kural: kanal VARSAYILAN KAPALI; `PEMF_LEGACY_EXE_UPDATE=1` ile (launcher'sız kurulum için)
bilinçli açılabilir. Kapalıyken `is_update_in_progress()` False kalmalı — seans/AI Pro
başlatmadaki TOCTOU korumaları bu bayrağa DEĞİL, gerçek kurulum penceresine bakar.
"""

import os

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def um(monkeypatch):
    from servers import update_manager

    monkeypatch.delenv("PEMF_LEGACY_EXE_UPDATE", raising=False)
    return update_manager


@pytest.fixture
def client():
    from servers import api_server

    return TestClient(api_server.app, client=("127.0.0.1", 51234))


# ── varsayılan: KAPALI ──────────────────────────────────────────────────────


def test_KRITIK_eski_kanal_VARSAYILAN_KAPALI(um):
    assert um.eski_kanal_acik_mi() is False, "eski Inno/exe kanali varsayilan ACIK — split-brain hasta DB riski"


def test_KRITIK_kapaliyken_apply_INSTALLER_CALISTIRMAZ(um, monkeypatch):
    """En ağır kapı: apply hiçbir koşulda indirme/kurulum yoluna GİRMEMELİ."""
    patladi = []
    monkeypatch.setattr(um, "get_status", lambda: patladi.append("get_status") or {})
    monkeypatch.setattr(um, "_has_active_treatment", lambda: patladi.append("treat") or False)
    r = um.apply_update()
    assert r["ok"] is False
    assert not patladi, f"kapali kanalda kurulum yoluna GIRILDI: {patladi}"


def test_KRITIK_kapaliyken_rollback_calismaz(um, monkeypatch):
    monkeypatch.setattr(um, "get_status", lambda: pytest.fail("kapali kanalda rollback yoluna girildi"))
    r = um.rollback()
    assert r["ok"] is False


def test_kapaliyken_denetleyici_AG_A_CIKMAZ(um, monkeypatch):
    monkeypatch.setattr(um, "check_for_update", lambda *a, **k: pytest.fail("kapali kanalda ag kontrolu yapildi"))
    um.start_update_checker(interval_sec=1)
    assert um._check_thread is None or not um._check_thread.is_alive(), "kapali kanalda denetleyici thread'i basladi"


def test_kapaliyken_TOCTOU_korumasi_BOZULMAZ(um):
    """`is_update_in_progress()` seans/AI-Pro başlatmayı kapatan güvenlik guard'ıdır.
    Kanal kapandı diye True'ya sıkışırsa cihaz HİÇ seans açamaz; False'a sıkışırsa koruma
    kaybolur. Kapalı kanalda doğru cevap False'tur (kurulum penceresi yoktur)."""
    assert um.is_update_in_progress() is False


# ── uç noktalar: sözleşme korunur, gerçek söylenir ─────────────────────────


def test_status_ucu_KANALI_bildirir(client, um):
    r = client.get("/api/update/status")
    assert r.status_code == 200, r.text[:200]
    g = r.json()
    assert g["available"] is False
    assert g.get("channel") == "launcher", f"kanal bildirilmiyor: {g}"
    assert g.get("legacyChannelEnabled") is False
    assert g.get("message"), "operatore aciklama verilmiyor"


def test_status_ucu_ESKI_ISTEMCI_sozlesmesini_KORUR(client):
    """Sahadaki eski mobil sürümler `available` / `currentVersion` alanlarını okur; alan tipi
    değişirse o istemciler çöker. Kapalı kanal kırılma sebebi olmamalı."""
    g = client.get("/api/update/status").json()
    assert isinstance(g.get("available"), bool)
    assert isinstance(g.get("currentVersion", ""), str) and g.get("currentVersion")
    assert isinstance(g.get("applying"), bool)


def test_KRITIK_kapali_kanal_HATA_gibi_gorunmez(client):
    """`error` doluysa arayüz "güncelleme sunucusuna ulaşılamıyor" der ve klinik ağ arızası
    arar. Kapalı bir kanal arıza DEĞİLDİR."""
    assert client.get("/api/update/status").json().get("error", "") == ""


def test_apply_ucu_ACIKLAYICI_yanit_dondurur(client):
    r = client.post("/api/update/apply")
    assert r.status_code == 200, r.text[:200]
    g = r.json()
    assert g["ok"] is False
    assert "launcher" in g.get("error", "").lower() or "client" in g.get("error", "").lower(), (
        f"operatore hangi kanalin yonettigi soylenmiyor: {g}"
    )


# ── bilinçli açma yolu ─────────────────────────────────────────────────────


def test_bayrakla_ACILABILIR(um, monkeypatch):
    """Launcher'sız (yalnız backend kurulu) bir dağıtım için kaçış kapağı korunmalı —
    yoksa bu değişiklik o kurulumları güncellemesiz bırakır."""
    monkeypatch.setenv("PEMF_LEGACY_EXE_UPDATE", "1")
    assert um.eski_kanal_acik_mi() is True
    from servers.update_manager import get_status

    assert get_status().get("channel") == "legacy-exe"
