# -*- coding: utf-8 -*-
"""D5 devri (DUZELTME-D4A §6 #6 · A-69 kalanı) — kimlik bilgisi DOSYASI sınıfı gitleaks'te YAKALANIR.

A-69 ölçümü (4-A): `credentials.json` / `hivemq_users.json` / `mosquitto_passwords.txt` içindeki düşük entropili düz parola ve mosquitto
`$7$` özet satırı varsayılan kurallarla 0 bulgu veriyordu. `.gitleaks.toml`'a iki DAR (path'li) kural eklendi. Bu kapı GERÇEK gitleaks
ikilisiyle (`tests/gitleaks_ikili.py` — yoksa varsayılan kipte atlar, `PEMF_GITLEAKS_ZORUNLU=1` / `PEMF_CAPRAZ_KAYNAK_ZORUNLU=1`'de düşer)
ölçer. Sahte değerler bu dosyada düz yazılmaz (kendi sır taramamızı tetiklemesin) — çalışma anında kurulur.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import gitleaks_ikili

KOK = Path(__file__).resolve().parent.parent
_CONFIG = KOK / ".gitleaks.toml"
_JSON_KURAL = "pemf-kimlik-dosyasi-json-deger"
_MOSQ_KURAL = "pemf-mosquitto-parola-dosyasi"


def _parola() -> str:
    return "Kl" + "nk" + "9-" + "x7Q" + "r2"


def _ozet() -> str:
    return "$" + "7" + "$101$" + "A" * 16 + "$" + "B" * 40


def _tara(kok: Path) -> list[tuple[str, str]]:
    ikili = gitleaks_ikili.gerekli()
    rapor = kok.parent / (kok.name + "_rapor.json")
    r = subprocess.run(
        [ikili, "detect", "--config", str(_CONFIG), "--no-git", "--no-banner", "--redact", "-s", str(kok)]
        + ["--report-format", "json", "--report-path", str(rapor)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert r.returncode in (0, 1) and rapor.is_file(), (
        f"gitleaks taramayı tamamlamadı (rc={r.returncode}): {r.stderr[:800]}"
    )
    return [(Path(b["File"]).name, b["RuleID"]) for b in json.loads(rapor.read_text(encoding="utf-8") or "[]")]


def _yaz(kok: Path, ad: str, icerik: str) -> None:
    p = kok / "config" / "credentials" / ad
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(icerik, encoding="utf-8")


def test_KRITIK_kimlik_dosyasi_sinifi_YAKALANIR(tmp_path):
    kok = tmp_path / "gercek"
    _yaz(kok, "credentials.json", json.dumps({"service": "pemf", "password": _parola()}))
    _yaz(kok, "hivemq_users.json", json.dumps({"users": [{"username": "esp8", "password": _parola()}]}))
    _yaz(kok, "mosquitto_passwords.txt", "# yorum\npemf_esp:" + _ozet() + "\n")
    (kok / "mosquitto").mkdir()
    (kok / "mosquitto" / "mosquitto_passwd").write_text(
        "pemf_esp:" + _ozet() + "\n", encoding="utf-8"
    )  # mosquitto'nun varsayılan adı
    (kok / "mosquitto" / "mosquitto_passwd.bak").write_text(
        "pemf_esp:" + _ozet() + "\n", encoding="utf-8"
    )  # yedek = aynı sızıntı
    bulgular = _tara(kok)
    assert ("credentials.json", _JSON_KURAL) in bulgular, bulgular
    assert ("hivemq_users.json", _JSON_KURAL) in bulgular, bulgular
    assert ("mosquitto_passwords.txt", _MOSQ_KURAL) in bulgular, bulgular
    assert ("mosquitto_passwd", _MOSQ_KURAL) in bulgular, bulgular
    assert ("mosquitto_passwd.bak", _MOSQ_KURAL) in bulgular, bulgular


def test_KARSIT_yer_tutucu_ve_baska_dosya_adi_YAKALANMAZ(tmp_path):
    """Dar kapsam: yer tutucu değer ve aynı içeriğin başka adlı dosyası bu iki kuralı TETİKLEMEZ (yanlış alarm commit'i durdurur)."""
    kok = tmp_path / "karsit"
    _yaz(kok, "credentials.json", json.dumps({"password": "<parola>", "token": "{sahte}", "secret": ""}))
    _yaz(kok, "hivemq_users.json", json.dumps({"users": [{"username": "esp8", "password": "<buraya>"}]}))
    _yaz(kok, "notlar.json", json.dumps({"password": _parola()}))
    _yaz(kok, "mosquitto_ornek.txt", "pemf_esp:" + _ozet() + "\n")
    # Yapılandırma dosyası parola DOSYASINA atıf yapar, özet taşımaz — kural yalnız parola dosyasının içeriğinde koşmalı.
    # (k5: `.exe` adlı karşıt örnek VAKUMDU — gitleaks ikili uzantıyı hiç taramıyor; çıta kaldırıldı.)
    _yaz(kok, "mosquitto.conf", "password_file C:/ProgramData/PEMF_System/mosquitto/mosquitto_passwd\n")
    bizimkiler = [b for b in _tara(kok) if b[1] in (_JSON_KURAL, _MOSQ_KURAL)]
    assert bizimkiler == [], bizimkiler
