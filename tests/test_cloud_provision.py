# Author: mertaygn, cglrgrkn
"""E-STOP BULUT AYNASI PROVİZYONU — sahip kararı (2026-08-19 gece): "indir-kur yeterli olsun".

Zincir: build-time `make_cloud_provision.py` (yerel Secrets.h → data/cloud_mqtt_provision.json,
GİT'E GİRMEZ) → PyInstaller datas → SecretsManager `_bundled_cloud` (env → gömülü dosya) →
ilk get_secret'te pemf_secrets.json'a taşınır (parola DPAPI). Bu kapılar: zincirin her halkası
+ sır-hijyeni (değer asla stdout'a yazılmaz) + git-sızıntı-yok.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]


def _uret(tmp_path, host="ornek123.s1.eu.hivemq.cloud", user="kullanici1", pw="parola42"):
    """Sahte Secrets.h'tan üretici betiği İZOLE yollarla çalıştır."""
    kaynak = tmp_path / "Secrets.h"
    kaynak.write_text(
        f'static const char* DEFAULT_CLOUD_MQTT_HOST = "{host}";\n'
        f"static const int   DEFAULT_CLOUD_MQTT_PORT = 8883;\n"
        f'static const char* DEFAULT_CLOUD_MQTT_USER = "{user}";\n'
        f'static const char* DEFAULT_CLOUD_MQTT_PASS = "{pw}";\n',
        encoding="utf-8",
    )
    hedef = tmp_path / "cloud_mqtt_provision.json"
    r = subprocess.run(
        [sys.executable, str(KOK / "build_tools" / "make_cloud_provision.py")],
        capture_output=True,
        text=True,
        timeout=60,
        env={
            **__import__("os").environ,
            "PEMF_CLOUD_SECRETS_H": str(kaynak),
            "PEMF_CLOUD_PROVISION_PATH": str(hedef),
        },
    )
    return r, hedef


def test_KRITIK_uretici_dosyayi_yazar_ve_DEGER_YAZDIRMAZ(tmp_path):
    r, hedef = _uret(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    d = json.loads(hedef.read_text(encoding="utf-8"))
    assert d["mqtt_cloud_host"] == "ornek123.s1.eu.hivemq.cloud"
    assert d["mqtt_cloud_port"] == "8883" and d["mqtt_cloud_user"] == "kullanici1"
    # SIR HİJYENİ: stdout'ta değerlerin HİÇBİRİ geçmez (yalnız uzunluk)
    for deger in ("ornek123", "kullanici1", "parola42"):
        assert deger not in r.stdout and deger not in r.stderr, "sır stdout'a sızdı"


def test_KRITIK_placeholder_gorunce_URETMEZ(tmp_path):
    r, hedef = _uret(tmp_path, host="<<GERCEK-DEGERI-FLASH-ONCESI-GIR>>")
    assert r.returncode == 1, "placeholder'la üretti — paket sahte sırla çıkardı"
    assert not hedef.exists()


def test_KRITIK_bundled_cloud_env_sonra_dosya(tmp_path, monkeypatch):
    """SecretsManager zinciri: env öncelikli; env yoksa gömülü dosya; ikisi de yoksa boş."""
    from utils import secrets_manager as sm

    prov = tmp_path / "p.json"
    prov.write_text(json.dumps({"mqtt_cloud_host": "dosyadan.hivemq.cloud", "mqtt_cloud_port": "8883"}), "utf-8")
    monkeypatch.setenv("PEMF_CLOUD_PROVISION_PATH", str(prov))
    monkeypatch.delenv("PEMF_MQTT_CLOUD_HOST", raising=False)
    # registry legacy lambda'sı: env yok → dosyadan
    _sec, _dp, _gen, legacy = sm._REGISTRY["mqtt_cloud_host"]
    assert legacy() == "dosyadan.hivemq.cloud"
    # env varsa env kazanır
    monkeypatch.setenv("PEMF_MQTT_CLOUD_HOST", "envden.hivemq.cloud")
    assert legacy() == "envden.hivemq.cloud"
    # dosya yoksa boş (ayna sessiz devre dışı) — exception sızdırmaz
    monkeypatch.delenv("PEMF_MQTT_CLOUD_HOST", raising=False)
    monkeypatch.setenv("PEMF_CLOUD_PROVISION_PATH", str(tmp_path / "yok.json"))
    assert legacy() == ""


def test_KRITIK_provizyon_dosyasi_GITE_GIREMEZ():
    """git-sızıntı kapısı: dosya ignore'lu VE izlenmiyor."""
    r = subprocess.run(
        ["git", "check-ignore", "data/cloud_mqtt_provision.json"],
        cwd=KOK,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode not in (0, 1):
        import pytest

        pytest.skip("git deposu değil")
    assert r.returncode == 0, "cloud_mqtt_provision.json .gitignore'da DEĞİL — public repoya sızar"
    r2 = subprocess.run(
        ["git", "ls-files", "--", "data/cloud_mqtt_provision.json"],
        cwd=KOK,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert not r2.stdout.strip(), "provizyon dosyası git'te İZLENİYOR — derhal kaldırılmalı"


def test_spec_kosullu_gomme_ICERIR():
    spec = (KOK / "build_tools" / "PEMF_Backend_onedir.spec").read_text(encoding="utf-8", errors="replace")
    assert "cloud_mqtt_provision.json" in spec
    i = spec.index("_cloud_prov")
    assert "os.path.exists" in spec[i : i + 300], "gömme koşulsuz — temiz klonda build kırılır"
    # config.json P0 kararı YERİNDE duruyor (istisna yalnız 4 bulut alanı)
    assert "if f == 'config.json':" in spec, "config.json GÖMME koruması düşmüş (P0 regresyonu)"
