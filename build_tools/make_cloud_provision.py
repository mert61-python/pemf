# Author: mertaygn, cglrgrkn
"""E-stop BULUT AYNASI sır provizyon dosyası üreticisi (SAHİP KARARI, 2026-08-19 gece).

`data/cloud_mqtt_provision.json` dosyasını yerel ESP Secrets.h'tan üretir. Bu dosya:
  * GİT'E GİRMEZ (.gitignore) — gitleaks/public-repo sızıntısı yok.
  * PyInstaller paketine GÖMÜLÜR (spec, varsa) → klinik makine "web sitesinden indir-kur"
    ile bulut E-stop aynasına otomatik kavuşur; ilk get_secret çağrısında değerler
    pemf_secrets.json'a taşınır (parola DPAPI ile makineye bağlı şifrelenir).

⚠️ GÜVENLİK KAYDI — bu, 2026-06-28 P0 "data/config.json'ı GÖMME" kararının 4 alan için
BİLİNÇLİ SAHİP KARARIYLA tersine çevrilmesidir ("sırları da tanımla, klinik makineye sadece
web sitesinden indirip kurması yeterli olsun" — 2026-08-19). Maruziyet sınıfı YENİ DEĞİL:
aynı HiveMQ kimliği zaten (a) sahadaki her ESP'nin flash'ında, (b) public repo'nun `esp`
dalında (rotasyon sahip tarafından reddedildi, kayıtta). wifi_pass gibi DİĞER alanlar
GÖMÜLMEZ — yalnız mqtt_cloud_host/port/user/pass.

Kullanım:  python build_tools/make_cloud_provision.py
Değer YAZDIRMAZ (yalnız uzunluk); placeholder görürse ÜRETMEZ (çıkış 1).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

GUII = Path(__file__).resolve().parent.parent
KAYNAK = Path(os.environ.get("PEMF_CLOUD_SECRETS_H") or (GUII / "firmware" / "esp8266_pemf_coil" / "Secrets.h"))
HEDEF = Path(os.environ.get("PEMF_CLOUD_PROVISION_PATH") or (GUII / "data" / "cloud_mqtt_provision.json"))

_ALANLAR = {
    "mqtt_cloud_host": r'DEFAULT_CLOUD_MQTT_HOST\s*=\s*"([^"]*)"',
    "mqtt_cloud_user": r'DEFAULT_CLOUD_MQTT_USER\s*=\s*"([^"]*)"',
    "mqtt_cloud_pass": r'DEFAULT_CLOUD_MQTT_PASS\s*=\s*"([^"]*)"',
}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if not KAYNAK.exists():
        print(f"[cloud-provision] kaynak yok: {KAYNAK} -> uretilmedi (paket sirsiz cikar, ayna devre disi)")
        return 1
    s = KAYNAK.read_text(encoding="utf-8", errors="replace")
    doc: dict = {
        "_comment": "E-stop bulut aynasi provizyonu — build-time uretilir, git'e girmez. "
        "Ilk calismada pemf_secrets.json'a tasinir (parola DPAPI).",
    }
    for anahtar, desen in _ALANLAR.items():
        m = re.search(desen, s)
        deger = (m.group(1) if m else "").strip()
        if not deger or "<<" in deger or "GERCEK" in deger:
            print(f"[cloud-provision] {anahtar}: placeholder/bos -> uretilmedi")
            return 1
        doc[anahtar] = deger
    mp = re.search(r"DEFAULT_CLOUD_MQTT_PORT\s*=?\s*(\d+)", s)
    doc["mqtt_cloud_port"] = mp.group(1) if mp else "8883"

    HEDEF.parent.mkdir(parents=True, exist_ok=True)
    HEDEF.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Deger YAZDIRMA — yalniz uzunluklar (sir hijyeni)
    ozet = ", ".join(f"{k}=<{len(v)} kr>" for k, v in doc.items() if not k.startswith("_"))
    print(f"[cloud-provision] yazildi: {HEDEF.name} ({ozet})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
