#!/usr/bin/env python3
"""manifest.json üretici — elle düzenlemeyi bitirir.

NEDEN: manifest bugüne kadar elle güncelleniyordu ve `publish.ps1` yorumunda kayda
geçtiği üzere bir kez `base_linux` eksik kalıp Linux istemcisi sessizce Windows
paketini indirmişti. Digest/boyut da elle yazılıyordu → yanlış sha256 = kullanıcıda
"doğrulama başarısız". Bu betik ikisini de dosyalardan ÜRETİR.

Şema v2 yazar, v1 alanlarını da GERİYE UYUM için korur (sahadaki v1.8.0 istemcileri
`base`/`base_linux`/`base_mac` okur; yeni launcher `runtimes`/`models` okur).

Kullanım:
  python scripts/make_manifest.py \
      --dir pemf-app-packages \
      --version 1.8.0 \
      --tag client-app-v1.8.0 \
      --repo mert61-python/pemf-update
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

# dosya adı -> (v2 bölümü, v2 anahtarı, v1 anahtarı)
ASSETS = {
    "base.zip": ("runtimes", "win-x64", "base"),
    "base-linux.zip": ("runtimes", "linux-x64", "base_linux"),
    "base-mac.zip": ("runtimes", "mac-arm64", "base_mac"),
    "home.zip": ("models", "home", None),
    "vet.zip": ("models", "vet", None),
    "research.zip": ("models", "research", None),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, type=Path, help="paketlerin bulunduğu klasör")
    ap.add_argument("--version", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--repo", required=True, help="örn. mert61-python/pemf-update")
    ap.add_argument("--out", type=Path, default=None, help="varsayılan: <dir>/manifest.json")
    ap.add_argument(
        "--drop-missing",
        action="store_true",
        help="Yerelde olmayan paketleri manifest'ten DÜŞÜR (varsayılan: mevcut manifest'ten taşı)",
    )
    args = ap.parse_args()

    base_url = f"https://github.com/{args.repo}/releases/download/{args.tag}"
    out_path = args.out or (args.dir / "manifest.json")

    manifest: dict = {
        "schema": 2,
        "version": args.version,
        "tag": args.tag,
        "runtimes": {},
        "models": {},
        # v1 geriye uyum: profiles + base/base_linux/base_mac aşağıda doldurulur.
        "profiles": {},
    }

    found, missing = [], []
    for name, (section, key, v1_key) in ASSETS.items():
        path = args.dir / name
        if not path.exists():
            missing.append(name)
            continue
        entry = {
            "url": f"{base_url}/{name}",
            "sha256": sha256(path),
            "size": path.stat().st_size,
            "kind": "zip",
        }
        manifest[section][key] = entry
        # v1 alanları
        if section == "models":
            manifest["profiles"][key] = entry
        elif v1_key:
            manifest[v1_key] = entry
        found.append(f"{name} -> {section}.{key}")

    # --- Eksikleri mevcut manifest'ten TAŞI (varsayılan davranış) ----------------
    # Paketler farklı runner'larda üretilip doğrudan release'e yüklenir (ör. base-linux.zip
    # Linux CI'da üretilir, bu makinede HİÇ bulunmaz). Yerelde yok diye düşürülürse o
    # platformun istemcisi kurulum yapamaz hale gelir — sessiz regresyon. Bu yüzden
    # varsayılan MERGE'dir; kasten silmek için --drop-missing gerekir.
    carried = []
    if missing and not args.drop_missing:
        prev_path = out_path if out_path.exists() else (args.dir / "manifest.json")
        if prev_path.exists():
            try:
                prev = json.loads(prev_path.read_text(encoding="utf-8"))
            except Exception as e:  # bozuk önceki manifest sessizce yutulmamalı
                print(f"[HATA] mevcut manifest okunamadı ({prev_path}): {e}", file=sys.stderr)
                return 1
            for name in list(missing):
                section, key, v1_key = ASSETS[name]
                # v2'den, yoksa v1 alanından al.
                entry = (prev.get(section) or {}).get(key)
                if entry is None and v1_key:
                    entry = prev.get(v1_key)
                if entry is None and section == "models":
                    entry = (prev.get("profiles") or {}).get(key)
                if entry is not None:
                    manifest[section][key] = entry
                    if section == "models":
                        manifest["profiles"][key] = entry
                    elif v1_key:
                        manifest[v1_key] = entry
                    missing.remove(name)
                    carried.append(f"{name} -> {section}.{key} (mevcut manifest'ten)")

    if not manifest["runtimes"]:
        print("[HATA] hiçbir base paketi bulunamadı — manifest yazılmadı.", file=sys.stderr)
        return 1

    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Yazıldı: {out_path}")
    for line in found:
        print(f"  + {line}")
    for line in carried:
        print(f"  = {line}")
    if missing:
        # SESSİZ ATLAMA YOK: eksik base = o platformun istemcisi kurulum yapamaz.
        # Yeni launcher sert hata verir (sessizce yanlış paketi İNDİRMEZ), ama
        # yayıncının bunu bilerek yapması gerekir.
        print("\n[UYARI] Bu paketler bulunamadı, manifest'e GİRMEDİ:", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        print("  Eksik platformun istemcisi 'paket yayınlanmamış' hatası verecek.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
