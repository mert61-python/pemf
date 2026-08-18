# Author: mertaygn, cglrgrkn
"""versions.json'daki sürümler CHANGELOG.md'de geçmeden COMMIT EDİLEMEZ (pre-commit kancası).

NEDEN VAR: Bu kapı CI'da zaten vardı (`tests/test_version_visibility.py::
test_KRITIK_CHANGELOG_guncel_surumleri_ICERIR`) ama İLK yakalayışı push'tan SONRAYDI —
2026-08-14'te `mobile=2.3.14` CHANGELOG'suz push edildi, `critical-path-tests` kırmızı döndü
ve sahibe bir "Run failed" e-postası daha gitti (kosu 31809975681). Cihazlar sessiz otomatik
güncellendiği için "ne değişti" sorusunun cevapsız kalmaması ürün kararıdır; bu betik aynı
denetimi commit ANINA taşır. CI testi yedek kapı olarak DURUR (bu betiği atlayan yollar için).

Mantık test ile BİREBİR aynı tutulur — iki kapı ayrışırsa "yerelde geçti, CI'da kırmızı"
sınıfı geri gelir (bkz. tests/test_lint_muafiyet_tutarliligi.py'nin hikâyesi).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]


def main() -> int:
    ch = KOK / "CHANGELOG.md"
    if not ch.exists():
        print("HATA: CHANGELOG.md yok")
        return 1
    metin = ch.read_text(encoding="utf-8")
    v = json.loads((KOK / "versions.json").read_text(encoding="utf-8"))
    eksik = [
        f"{ad}={s}"
        for ad, s in (
            ("launcher", v["launcher"]),
            ("mobile", v["mobile"]["name"]),
            ("backend", v["backend"]),
        )
        if s not in metin
    ]
    if eksik:
        print(
            f"versions.json'daki surum(ler) CHANGELOG'da gecmiyor: {eksik}\n"
            "Surum yukseltildiyse degisiklik kaydi da yazilmali — CHANGELOG.md'ye\n"
            "yeni surumun bolumunu ekleyip tekrar commit edin.\n"
            "(Ayni kural CI'da da var: tests/test_version_visibility.py)"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
