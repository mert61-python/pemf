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
import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]


def _eksik_kanallar(metin: str, v: dict) -> list[str]:
    """CHANGELOG'da KENDİ KANALININ başlığıyla geçmeyen sürümler.

    ⚠️ CI (`tests/test_version_visibility.py::test_KRITIK_CHANGELOG_guncel_surumleri_ICERIR`) ile
    BİREBİR aynı olmalı (F7/BLD-3, denetim 2026-08-24). Eski hâl ham `s not in metin` idi ve
    YANLIŞ-YEŞİL üretiyordu: sürüm numaraları kanallar arası tekrar ettiğinden (app 1.9.x ↔
    launcher 1.9.x) backend'i mevcut bir launcher numarasına çekmek kapıyı geçiriyordu — hata
    push'tan SONRA CI'da çıkıyordu. versions.json anahtarı → CHANGELOG başlığındaki kanal adı
    (backend → 'app'). Birleşik başlıklar da geçerli (`## app 1.9.9 · launcher 1.9.20 — …`)."""
    kanallar = (
        ("launcher", "launcher", v["launcher"]),
        ("mobile", "mobile", v["mobile"]["name"]),
        ("backend", "app", v["backend"]),
    )
    return [
        f"{ad}={surum}"
        for ad, kanal, surum in kanallar
        if not re.search(rf"^##[^\n]*\b{re.escape(kanal)}\s+{re.escape(surum)}\b", metin, re.M)
    ]


def main() -> int:
    ch = KOK / "CHANGELOG.md"
    if not ch.exists():
        print("HATA: CHANGELOG.md yok")
        return 1
    metin = ch.read_text(encoding="utf-8")
    v = json.loads((KOK / "versions.json").read_text(encoding="utf-8"))
    eksik = _eksik_kanallar(metin, v)
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
