# Author: mertaygn, cglrgrkn
"""MAKİNE-ÖZEL SIR YEDEĞİ — build_tools/secrets_backup.py yuvarlak-tur + güvenlik kapıları.

"Her makinede build" için sırlar git'e girmeden taşınabilir olmalı. Bu araç scrypt+Fernet ile
şifreli tek arşiv üretir. Kapılar: (a) backup→restore içerik BİREBİR korunur, (b) yanlış parola
ÇÖZEMEZ, (c) list/hata çıktısı DEĞER SIZDIRMAZ, (d) .pemfsec git'e giremez.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "build_tools" / "secrets_backup.py"


def _kos(args, parola=None, extra_env=None):
    import os

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    if parola is not None:
        env["PEMF_SECBAK_PASSPHRASE"] = parola
    if extra_env:
        env.update(extra_env)
    return subprocess.run([sys.executable, str(BETIK), *args], capture_output=True, text=True, env=env, timeout=120)


@pytest.fixture()
def sahte_repo(tmp_path, monkeypatch):
    """secrets_backup'ı izole yollarla koşmak için GUII/HOME'u geçici dizine bağla."""
    # betiği alt-süreç yerine IN-PROCESS koştur ki GUII/HOME'u monkeypatch edebilelim
    import importlib

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
    # sahte sır içerikleri (gerçek sır DEĞİL)
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
    # _KALEMLER GUII/HOME'a bağlı olduğundan yeniden kur
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


def test_KRITIK_backup_restore_YUVARLAK_TUR_bire_bir(sahte_repo, monkeypatch):
    mod, gui, home, tmp_path, icerik = sahte_repo
    ark = tmp_path / "yedek.pemfsec"
    monkeypatch.setenv("PEMF_SECBAK_PASSPHRASE", "dogru-parola-99")

    class _A:
        out = str(ark)

    assert mod.cmd_backup(_A()) == 0
    assert ark.exists()

    # tüm sır dosyalarını SİL → restore geri getirmeli
    for rel in icerik:
        (gui / rel).unlink()
    (home / ".pemf-keys/pemf-release.jks").unlink()

    class _R:
        inp = str(ark)
        force = True

    assert mod.cmd_restore(_R()) == 0
    for rel, beklenen in icerik.items():
        assert (gui / rel).read_bytes() == beklenen, f"{rel} birebir gelmedi"
    assert (home / ".pemf-keys/pemf-release.jks").read_bytes() == b"SAHTE-JKS-BINARY-ICERIK"


def test_KRITIK_YANLIS_parola_COZEMEZ(sahte_repo, monkeypatch):
    mod, gui, home, tmp_path, icerik = sahte_repo
    ark = tmp_path / "y.pemfsec"
    monkeypatch.setenv("PEMF_SECBAK_PASSPHRASE", "dogru-parola-99")

    class _A:
        out = str(ark)

    mod.cmd_backup(_A())
    (gui / "data/cloud_mqtt_provision.json").unlink()
    monkeypatch.setenv("PEMF_SECBAK_PASSPHRASE", "YANLIS-parola-00")

    class _R:
        inp = str(ark)
        force = True

    with pytest.raises(SystemExit):
        mod.cmd_restore(_R())


def test_KRITIK_arsiv_ve_list_DEGER_SIZDIRMAZ(sahte_repo, monkeypatch, capsys):
    mod, gui, home, tmp_path, icerik = sahte_repo
    ark = tmp_path / "y.pemfsec"
    monkeypatch.setenv("PEMF_SECBAK_PASSPHRASE", "dogru-parola-99")

    class _A:
        out = str(ark)

    mod.cmd_backup(_A())
    # arşivin HAM içeriğinde hiçbir sahte-sır DÜZ METİN geçmemeli (Fernet şifreli)
    ham = ark.read_text(encoding="utf-8")
    for gizli in ("sahte-8266-parola", "sahte-bulut", "sahte-keystore-pw", "SAHTE-JKS"):
        assert gizli not in ham, f"sır arşivde DÜZ METİN: {gizli}"
    # list de değer basmaz
    capsys.readouterr()

    class _L:
        inp = str(ark)

    mod.cmd_list(_L())
    cikti = capsys.readouterr().out
    for gizli in ("sahte-8266-parola", "sahte-bulut", "sahte-keystore-pw"):
        assert gizli not in cikti


def test_KRITIK_pemfsec_GITE_GIREMEZ():
    r = subprocess.run(["git", "check-ignore", "ornek.pemfsec"], cwd=KOK, capture_output=True, text=True, timeout=60)
    if r.returncode not in (0, 1):
        pytest.skip("git deposu değil")
    assert r.returncode == 0, "*.pemfsec .gitignore'da DEĞİL — şifreli sır yedeği repoya sızabilir"
    # betiğin kendisi de sır DEĞERİ içermez (kaynak public repoda)
    src = BETIK.read_text(encoding="utf-8", errors="replace")
    assert "hivemq" not in src.lower() and ".cloud" not in src, "betikte gerçek sır izi"
