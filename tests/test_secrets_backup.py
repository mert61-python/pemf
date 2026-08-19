# Author: mertaygn, cglrgrkn
"""MAKİNE-ÖZEL SIR YEDEĞİ — build_tools/secrets_backup.py yuvarlak-tur + güvenlik kapıları.

"Her makinede build" için sırlar git'e girmeden taşınabilir olmalı. Bu araç (parolasız, sahip
kararı 2026-08-19) sırları TEK base64 arşive toplar. Kapılar: (a) backup→restore içerik BİREBİR
korunur, (b) `.pemfsec` git'e giremez, (c) çıktı değer sızdırmaz, (d) eski parola-korumalı arşiv
(PEMFSEC1) açıkça REDDEDİLİR (sessiz veri kaybı olmasın).
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "build_tools" / "secrets_backup.py"


@pytest.fixture()
def sahte_repo(tmp_path, monkeypatch):
    """secrets_backup'ı izole yollarla koşmak için GUII/HOME'u geçici dizine bağla."""
    monkeypatch.syspath_prepend(str(KOK / "build_tools"))
    mod = importlib.import_module("secrets_backup")
    importlib.reload(mod)
    gui = tmp_path / "guii"
    home = tmp_path / "home"
    (gui / "firmware/esp8266_pemf_coil/data").mkdir(parents=True)
    (gui / "firmware/esps3_pemf_coil/data").mkdir(parents=True)
    (gui / "data").mkdir(parents=True)
    (gui / "pf/android").mkdir(parents=True)
    (home / ".pemf-keys").mkdir(parents=True)
    icerik = {
        "firmware/esp8266_pemf_coil/Secrets.h": b'#define WIFI_PASS "sahte-8266-parola-123"\n',
        "firmware/esps3_pemf_coil/Secrets.h": b'#define WIFI_PASS "sahte-s3-parola-456"\n',
        "firmware/esp8266_pemf_coil/data/config.json": b'{"mqtt_pass":"sahte-cfg-8266"}',
        "firmware/esps3_pemf_coil/data/config.json": b'{"mqtt_pass":"sahte-cfg-s3"}',
        "data/cloud_mqtt_provision.json": b'{"mqtt_cloud_pass":"sahte-bulut"}',
        "pf/android/keystore.properties": b"storePassword=sahte-keystore-pw\n",
    }
    for rel, veri in icerik.items():
        (gui / rel).write_bytes(veri)
    (home / ".pemf-keys/pemf-release.jks").write_bytes(b"SAHTE-JKS-BINARY-ICERIK")
    monkeypatch.setattr(mod, "GUII", gui)
    monkeypatch.setattr(mod, "HOME", home)
    mod._KALEMLER = [
        ("esp8266/Secrets.h", gui / "firmware/esp8266_pemf_coil/Secrets.h", True),
        ("esps3/Secrets.h", gui / "firmware/esps3_pemf_coil/Secrets.h", True),
        ("esp8266/data/config.json", gui / "firmware/esp8266_pemf_coil/data/config.json", True),
        ("esps3/data/config.json", gui / "firmware/esps3_pemf_coil/data/config.json", True),
        ("data/cloud_mqtt_provision.json", gui / "data/cloud_mqtt_provision.json", False),
        ("pf/android/keystore.properties", gui / "pf/android/keystore.properties", False),
        ("release-keystore/pemf-release.jks", home / ".pemf-keys/pemf-release.jks", False),
    ]
    return mod, gui, home, tmp_path, icerik


class _Out:
    def __init__(self, out):
        self.out = out


class _Restore:
    def __init__(self, inp, force=True):
        self.inp = inp
        self.force = force


def test_KRITIK_backup_restore_YUVARLAK_TUR_bire_bir(sahte_repo):
    mod, gui, home, tmp_path, icerik = sahte_repo
    ark = tmp_path / "yedek.pemfsec"
    assert mod.cmd_backup(_Out(str(ark))) == 0
    assert ark.exists()
    for rel in icerik:
        (gui / rel).unlink()
    (home / ".pemf-keys/pemf-release.jks").unlink()
    assert mod.cmd_restore(_Restore(str(ark))) == 0
    for rel, beklenen in icerik.items():
        assert (gui / rel).read_bytes() == beklenen, f"{rel} birebir gelmedi"
    assert (home / ".pemf-keys/pemf-release.jks").read_bytes() == b"SAHTE-JKS-BINARY-ICERIK"


def test_backup_PAROLASIZ_calisir_env_gerekmez(sahte_repo, monkeypatch):
    """Sahip kararı: parola kaldırıldı — hiçbir parola/env olmadan backup+list çalışır."""
    mod, gui, home, tmp_path, icerik = sahte_repo
    monkeypatch.delenv("PEMF_SECBAK_PASSPHRASE", raising=False)
    ark = tmp_path / "y.pemfsec"
    assert mod.cmd_backup(_Out(str(ark))) == 0

    class _L:
        inp = str(ark)

    assert mod.cmd_list(_L()) == 0


def test_KRITIK_ESKI_sifreli_arsiv_ACIKCA_REDDEDILIR(sahte_repo, tmp_path):
    """PEMFSEC1 (eski parola-korumalı) arşiv parolasız sürümde SESSİZCE bozulmamalı — açık hata."""
    import json

    mod, *_ = sahte_repo
    eski = tmp_path / "eski.pemfsec"
    eski.write_text(json.dumps({"_magic": "PEMFSEC1", "kdf": {}, "kalemler": []}), encoding="utf-8")

    class _L:
        inp = str(eski)

    with pytest.raises(SystemExit):
        mod.cmd_list(_L())


def test_KRITIK_cikti_DEGER_SIZDIRMAZ(sahte_repo, capsys):
    mod, gui, home, tmp_path, icerik = sahte_repo
    ark = tmp_path / "y.pemfsec"
    mod.cmd_backup(_Out(str(ark)))
    capsys.readouterr()

    class _L:
        inp = str(ark)

    mod.cmd_list(_L())
    cikti = capsys.readouterr().out
    # base64 olsa da list KOMUTU düz değerleri BASMAMALI (yalnız ad + boyut)
    for gizli in ("sahte-8266-parola", "sahte-bulut", "sahte-keystore-pw", "SAHTE-JKS"):
        assert gizli not in cikti


def test_KRITIK_pemfsec_GITE_GIREMEZ():
    r = subprocess.run(["git", "check-ignore", "ornek.pemfsec"], cwd=KOK, capture_output=True, text=True, timeout=60)
    if r.returncode not in (0, 1):
        pytest.skip("git deposu değil")
    assert r.returncode == 0, "*.pemfsec .gitignore'da DEĞİL — sır yedeği repoya sızabilir"
    src = BETIK.read_text(encoding="utf-8", errors="replace")
    assert "hivemq" not in src.lower() and ".cloud" not in src, "betikte gerçek sır izi"


def test_restore_mevcut_dosyayi_FORCE_olmadan_KORUR(sahte_repo):
    mod, gui, home, tmp_path, icerik = sahte_repo
    ark = tmp_path / "y.pemfsec"
    mod.cmd_backup(_Out(str(ark)))
    # bir dosyayı DEĞİŞTİR; force'suz restore üzerine YAZMAMALI
    hedef = gui / "data/cloud_mqtt_provision.json"
    hedef.write_bytes(b"YENI-YEREL-ICERIK-DOKUNMA")
    assert mod.cmd_restore(_Restore(str(ark), force=False)) == 0
    assert hedef.read_bytes() == b"YENI-YEREL-ICERIK-DOKUNMA", "force'suz restore mevcut dosyayı ezdi"
    # sys import gerektirmiyor; alt-süreç yok
    assert sys.executable  # noop, lint için
