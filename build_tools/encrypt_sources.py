# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KAYNAK ŞİFRELEME — build çıktısındaki .py dosyalarını şifreler (2026-08-06).

KULLANIM (build_backend_exe.ps1 SONRASI, base.zip ÖNCESİ):
    python build_tools/encrypt_sources.py                      # varsayılan hedef: PEMF_BUILD\\dist
    python build_tools/encrypt_sources.py --dry-run            # neyin şifreleneceğini göster, DOKUNMA
    python build_tools/encrypt_sources.py --dist <yol>         # farklı build çıktısı
    python build_tools/encrypt_sources.py --verify             # şifreleme sonrası çözülebilirliği sına

⚠️ YALNIZ BUILD ÇIKTISI ÜZERİNDE ÇALIŞIR. Kaynak ağacına (guii/ai_hub) DOKUNMAZ —
geliştirme ortamı bozulmasın. Güvenlik için hedef yolun `dist` içermesi ZORUNLU tutulur.

⚠️ Bu katmanın NE koruyup NE korumadığı: bkz. build_tools/source_crypto.py başlığı.
Anahtar üründe gider → tersine mühendisliğe karşı değildir; asıl koruma `.pyd` derlemedir.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

GUII = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GUII))

from build_tools.source_crypto import (  # noqa: E402
    ENC_SUFFIX,
    decrypt_bytes,
    encrypt_bytes,
    read_password,
)

# Şifrelenecek klasörler (build çıktısı içindeki GÖRELİ yollar).
# ÖLÇÜLDÜ 2026-08-06: yalnız `ai_hub` düz .py olarak diske kopyalanıyor; servers/database/utils
# zaten EXE'ye gömülü .pyc. Bu yüzden varsayılan kapsam ai_hub'tır (gerçek açık orası).
DEFAULT_TARGETS = ["_internal/ai_hub"]

# ŞifrelenMEyecekler: paket keşfi ve dinamik import bunlara İSİMDEN bakar; şifrelenirse
# Python paketi bulamaz ve uygulama açılmaz.
SKIP_NAMES = {"__init__.py"}
SKIP_DIRS = {"__pycache__", "PEMF_AI_Test_Girdileri"}


def toplanan(dist: Path, targets: list[str]) -> list[Path]:
    out: list[Path] = []
    for t in targets:
        base = dist / t
        if not base.exists():
            print(f"  [atla] hedef yok: {base}")
            continue
        for p in base.rglob("*.py"):
            if p.name in SKIP_NAMES:
                continue
            if any(d in p.parts for d in SKIP_DIRS):
                continue
            out.append(p)
    return sorted(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build çıktısındaki kaynakları şifrele")
    ap.add_argument("--dist", default=str(GUII / "PEMF_BUILD" / "dist" / "PEMF_Backend"))
    ap.add_argument("--dry-run", action="store_true", help="değişiklik YAPMA, yalnız listele")
    ap.add_argument("--verify", action="store_true", help="şifreleme sonrası çözülebilirliği sına")
    a = ap.parse_args()

    dist = Path(a.dist).resolve()
    # GÜVENLİK KAPISI: yanlışlıkla kaynak ağacını şifrelemeyi imkânsız kıl.
    if "dist" not in [p.lower() for p in dist.parts]:
        print(f"HATA: hedef yol 'dist' içermiyor → kaynak ağacı olabilir, DURDUM: {dist}")
        return 2
    if not dist.exists():
        print(f"HATA: build çıktısı yok: {dist}\n      Önce scripts/build_backend_exe.ps1 çalıştırın.")
        return 2

    pw = read_password()
    if not pw:
        print(
            "HATA: parola bulunamadı.\n"
            "      build_tools/_static_password.py içine SOURCE_PASSWORD = \"...\" yazın\n"
            "      (ya da PEMF_SOURCE_KEY ortam değişkenini verin)."
        )
        return 2

    dosyalar = toplanan(dist, DEFAULT_TARGETS)
    if not dosyalar:
        print("Şifrelenecek dosya bulunamadı (hedefler zaten şifreli olabilir).")
        return 0

    toplam_kaynak = sum(p.stat().st_size for p in dosyalar)
    print(f"Hedef : {dist}")
    print(f"Dosya : {len(dosyalar)} .py  ({toplam_kaynak / 1024:.1f} KB)")
    if a.dry_run:
        for p in dosyalar[:25]:
            print(f"  {p.relative_to(dist)}")
        if len(dosyalar) > 25:
            print(f"  … +{len(dosyalar) - 25} dosya")
        print("\n--dry-run: hiçbir şey değiştirilmedi.")
        return 0

    ok = 0
    for p in dosyalar:
        try:
            raw = p.read_bytes()
            blob = encrypt_bytes(raw, pw)
            if a.verify and decrypt_bytes(blob, pw) != raw:
                print(f"  HATA: doğrulama başarısız → {p}")
                return 1
            p.with_suffix(ENC_SUFFIX).write_bytes(blob)
            p.unlink()  # düz kaynağı KALDIR — asıl amaç bu
            ok += 1
        except Exception as e:
            print(f"  HATA: {p}: {e}")
            return 1

    kalan = toplanan(dist, DEFAULT_TARGETS)
    print(f"\nŞifrelendi: {ok} dosya → *{ENC_SUFFIX}")
    print(f"Kalan düz .py (yalnız __init__.py olmalı): {len(kalan)}")
    print("\n⚠️ HATIRLATMA: anahtar üründe gider — bu katman kopyalamayı zorlaştırır,")
    print("   tersine mühendisliği ENGELLEMEZ. Asıl koruma .pyd derlemedir.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
