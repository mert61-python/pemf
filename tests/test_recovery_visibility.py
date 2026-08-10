# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KURTARMA KODU GÖRÜNÜRLÜĞÜ (2026-08-09 denetimi, ENGEL'in ikinci yarısı).

ARIZA: `utils/backup_recovery` kurtarma kodunu `<veri-dizini>\\KURTARMA-KODU.txt` dosyasına
yazıp YALNIZCA log'a bir uyarı düşüyordu. Veteriner log okumaz.

Sonuç: kod, şifreli veritabanıyla AYNI diskte duruyor. Disk ölürse ikisi de gider ve off-site
yedekler — zarf orada olsa bile — SONSUZA DEK açılamaz. Yani kurtarma mekanizması, operatör
kodu makine dışına kopyalamadıkça hiçbir şey korumuyordu; operatöre ise varlığı hiç söylenmiyordu.

Bu dosya iki şeyi kilitler: (1) durum arayüze ULAŞIR ve onaylanana kadar UYARI ister,
(2) kodun KENDİSİ yalnız cihazın kendi ekranından okunur — LAN/tünelden ASLA.
"""

import os

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def api():
    from servers import api_server

    return api_server


@pytest.fixture(scope="module")
def loopback(api):
    return TestClient(api.app, client=("127.0.0.1", 51234))


@pytest.fixture(scope="module")
def lan(api):
    return TestClient(api.app, client=("192.168.1.77", 51234))


@pytest.fixture
def kod_dosyasi(api, tmp_path, monkeypatch):
    """Kurtarma kodu üretilmiş bir cihaz modeli."""
    from utils.backup_recovery import CODE_FILE_NAME

    monkeypatch.setattr(api, "_app_data_dir", lambda: tmp_path)
    p = tmp_path / CODE_FILE_NAME
    p.write_text("KURTARMA KODU: ABCDE-FGHIJ-KLMNO-PQRST-UVWXY-Z2345\n", encoding="utf-8")
    return p


# ── kodun kendisi: YALNIZ loopback ───────────────────────────────────────────


def test_KRITIK_kurtarma_kodu_LANdan_OKUNAMAZ(lan, kod_dosyasi):
    """Kod, tüm hasta verisinin ana anahtarıdır; zarfla birleşince at-rest şifrelemeyi tamamen
    geçersiz kılar. LAN'a sızması, şifrelemenin hiç olmamasıyla aynı şeydir."""
    r = lan.get("/api/system/recovery-code")
    assert r.status_code == 403, f"kurtarma kodu LAN'dan okundu ({r.status_code})"
    assert "ABCDE" not in r.text, "kod govdede SIZDI"


def test_KRITIK_kurtarma_kodu_TUNELDEN_OKUNAMAZ(loopback, kod_dosyasi):
    """cloudflared 127.0.0.1'DEN bağlanır → proxy başlığı varsa UZAK sayılmalı."""
    r = loopback.get("/api/system/recovery-code", headers={"CF-Connecting-IP": "8.8.8.8"})
    assert r.status_code == 403, "tunelden gelen istek loopback sayildi — kod internete acildi"
    assert "ABCDE" not in r.text


def test_KRITIK_LAN_gecerli_TOKENLA_da_OKUYAMAZ(lan, kod_dosyasi, monkeypatch):
    """Eşleştirilmiş mobil uygulama bile bu kodu görmemeli: telefon kaybolursa tüm klinik
    verisinin ana anahtarı da kaybolur. Kapı `enforce_privileged` DEĞİL, katı loopback."""
    from servers import auth

    monkeypatch.setattr(auth, "check_token", lambda t: True)
    r = lan.get("/api/system/recovery-code", headers={"X-API-Key": "GECERLI"})
    assert r.status_code == 403, "gecerli token kurtarma kodunu acti"


def test_kod_cihazin_kendi_ekranindan_OKUNUR(loopback, kod_dosyasi):
    r = loopback.get("/api/system/recovery-code")
    assert r.status_code == 200, r.text[:300]
    assert "ABCDE-FGHIJ" in r.json()["content"]


def test_kod_yoksa_404(loopback, api, tmp_path, monkeypatch):
    monkeypatch.setattr(api, "_app_data_dir", lambda: tmp_path)
    assert loopback.get("/api/system/recovery-code").status_code == 404


# ── durum ucu: uyarı ne zaman çıkar ──────────────────────────────────────────


def test_durum_ucu_KODU_SIZDIRMAZ(loopback, kod_dosyasi):
    """Durum ucu ayrıcalıklıdır (mobil de okuyabilir) → kodun kendisi ASLA burada dönmemeli."""
    r = loopback.get("/api/system/recovery-status")
    assert r.status_code == 200, r.text[:300]
    assert "ABCDE" not in r.text, "kod durum ucundan SIZDI"
    assert r.json()["codeExists"] is True


def test_KRITIK_onaylanmadikca_UYARI_ister(loopback, kod_dosyasi, monkeypatch):
    """`warn=true` → arayüz kalıcı uyarı gösterir. Bu olmadan operatör kodun varlığını
    ÖĞRENEMİYORDU ve makine dışına kopyalamıyordu."""
    from servers import system_router as sr

    monkeypatch.setattr(sr, "_kurtarma_durumu", lambda: (True, True, None, str(kod_dosyasi)))
    assert loopback.get("/api/system/recovery-status").json()["warn"] is True


def test_onaylandiktan_sonra_UYARI_SUSAR(loopback, kod_dosyasi, monkeypatch):
    from servers import system_router as sr

    monkeypatch.setattr(sr, "_kurtarma_durumu", lambda: (True, True, "2026-08-09T12:00:00", str(kod_dosyasi)))
    g = loopback.get("/api/system/recovery-status").json()
    assert g["warn"] is False and g["acknowledged"] is True


def test_sifreleme_KAPALIYKEN_uyari_YOK(loopback, kod_dosyasi, monkeypatch):
    """Düz-metin DB'de kurtarma zarfı anlamsızdır → gereksiz uyarı alarm körlüğü yaratır."""
    from servers import system_router as sr

    monkeypatch.setattr(sr, "_kurtarma_durumu", lambda: (False, True, None, "x"))
    assert loopback.get("/api/system/recovery-status").json()["warn"] is False


def test_kod_dosyasi_YOKSA_uyari_YOK(loopback, monkeypatch):
    from servers import system_router as sr

    monkeypatch.setattr(sr, "_kurtarma_durumu", lambda: (True, False, None, "x"))
    assert loopback.get("/api/system/recovery-status").json()["warn"] is False


# ── onay ─────────────────────────────────────────────────────────────────────


def test_onay_KALICI_yazilir(loopback, api, tmp_path, monkeypatch):
    monkeypatch.setattr(api, "_app_data_dir", lambda: tmp_path)
    from utils.backup_recovery import CODE_FILE_NAME

    (tmp_path / CODE_FILE_NAME).write_text("KOD", encoding="utf-8")

    assert loopback.get("/api/system/recovery-status").json()["acknowledged"] is False
    assert loopback.post("/api/system/recovery-ack", json={}).status_code == 200
    g = loopback.get("/api/system/recovery-status").json()
    assert g["acknowledged"] is True and g["acknowledgedAt"], "onay kalici degil"


def test_KRITIK_onay_ucu_LANdan_kimliksiz_REDDEDILIR(lan):
    """Onay 'uyarıyı sustur' demektir; klinik ağındaki rastgele bir cihaz bunu yapamamalı."""
    assert lan.post("/api/system/recovery-ack", json={}).status_code == 403


def test_durum_ucu_LANdan_kimliksiz_REDDEDILIR(lan):
    assert lan.get("/api/system/recovery-status").status_code == 403


def test_durum_ucu_gecerli_TOKENLA_okunur(lan, kod_dosyasi, monkeypatch):
    """Meşru mobil kullanım kırılmamalı: durum (kod DEĞİL) token'la okunabilir."""
    from servers import auth

    monkeypatch.setattr(auth, "check_token", lambda t: t == "T")
    r = lan.get("/api/system/recovery-status", headers={"X-API-Key": "T"})
    assert r.status_code == 200 and "ABCDE" not in r.text
