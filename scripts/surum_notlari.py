# -*- coding: utf-8 -*-
"""Kullanıcıya görünen sürüm notları — iki dil, TEK KAYNAK `docs/surum_notlari.json` (YH D1).

NEDEN VAR: telefon uygulaması güncelleme notunu manifest'in `mobile.android` bloğundan okur ve İngilizce arayüzde Türkçe `notes`u
GÖSTERMEZ (`apps/ui/src/services/mobileUpdate.ts` — `notes_en` yoksa katalog metnine düşer, I18NI-A3.5). Blok yayında ELLE yazıldığı
için `notes_en`in bir kaynağı yoktu; ayrıca `publish_release.ps1` yalnız Türkçe not taşıyordu. İki metin artık tek dosyada durur:

    python scripts/surum_notlari.py goster <app|launcher|mobile> <sürüm> <tr|en>   # metni yazdırır (publish_release.ps1 -Notes / -NotesEn)
    python scripts/surum_notlari.py mobil <manifest.json>                           # mobile.android.notes + notes_en'i yazar
    python scripts/surum_notlari.py baslatici <manifest.json>                       # launcher.notes + notes_en'i yazar (GK · Y254 a)

`mobil` komutu bloğun KENDİ sürümünün notunu yazar (APK dosyası yüklenip blok elle güncellendikten SONRA çalıştırılır); o sürümün
notu yoksa hiçbir şey yazmadan durur — eski sürümün notu yeni APK'nın üstüne yazılmaz. Ağ yok; yalnız verilen dosyaya dokunur.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
NOTLAR = KOK / "docs" / "surum_notlari.json"
KANALLAR = ("app", "launcher", "mobile")
DILLER = {"tr": "notes", "en": "notes_en"}


class NotYok(LookupError):
    """İstenen kanal / sürüm için iki dilli not yok (ya da biri boş)."""


def notlari_oku(kanal: str, surum: str, yol: Path = NOTLAR) -> dict[str, str]:
    """`{"notes": <tr>, "notes_en": <en>}` — ikisi de dolu olmak zorunda."""
    if kanal not in KANALLAR:
        raise NotYok(f"bilinmeyen kanal: {kanal!r} (geçerli: {', '.join(KANALLAR)})")
    kayit = (json.loads(yol.read_text(encoding="utf-8")).get(kanal) or {}).get(surum)
    if not isinstance(kayit, dict):
        raise NotYok(f"{yol.name}: {kanal} {surum} için not yok")
    notlar = {alan: str(kayit.get(alan) or "").strip() for alan in DILLER.values()}
    bos = [alan for alan, metin in notlar.items() if not metin]
    if bos:
        raise NotYok(f"{yol.name}: {kanal} {surum} notu eksik: {', '.join(bos)}")
    return notlar


def mobil_notlarini_yaz(manifest_yolu: Path, yol: Path = NOTLAR) -> str:
    """Manifest'in `mobile.android` bloğuna kendi sürümünün iki notunu yazar; yazılan sürümü döndürür."""
    manifest = json.loads(manifest_yolu.read_text(encoding="utf-8"))
    android = (manifest.get("mobile") or {}).get("android")
    if not isinstance(android, dict) or not android.get("version"):
        raise NotYok(f"{manifest_yolu.name}: mobile.android.version yok")
    surum = str(android["version"])
    android.update(notlari_oku("mobile", surum, yol))
    # make_manifest.py ile AYNI biçim (girinti 2, Türkçe karakter kaçışsız, sonda satır sonu).
    manifest_yolu.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return surum


def baslatici_notlarini_yaz(manifest_yolu: Path, yol: Path = NOTLAR) -> str:
    """GK (istem 41 · Y254 a): başlatıcının onay penceresi kısa sürüm notunu manifest'in `launcher` bloğundan okur
    (`launcher/core/src/manifest.rs` `LauncherInfo.notes` / `notes_en`). Bloğun KENDİ sürümünün iki notunu yazar; not yoksa
    hiçbir şey yazmadan durur (eski sürümün notu yeni başlatıcının üstüne yazılmaz). Yazılan sürümü döndürür."""
    manifest = json.loads(manifest_yolu.read_text(encoding="utf-8"))
    blok = manifest.get("launcher")
    if not isinstance(blok, dict) or not blok.get("version"):
        raise NotYok(f"{manifest_yolu.name}: launcher.version yok")
    surum = str(blok["version"])
    blok.update(notlari_oku("launcher", surum, yol))
    manifest_yolu.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return surum


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # gömülü Python'un cp1254 konsolu Türkçe karakterde düşmesin
    except (AttributeError, ValueError):
        pass
    try:
        if len(argv) == 4 and argv[0] == "goster" and argv[3] in DILLER:
            print(notlari_oku(argv[1], argv[2])[DILLER[argv[3]]])
            return 0
        if len(argv) == 2 and argv[0] == "mobil":
            surum = mobil_notlarini_yaz(Path(argv[1]))
            print(f"[surum_notlari] mobile.android {surum}: notes + notes_en yazıldı → {argv[1]}")
            return 0
        if len(argv) == 2 and argv[0] == "baslatici":
            surum = baslatici_notlarini_yaz(Path(argv[1]))
            print(f"[surum_notlari] launcher {surum}: notes + notes_en yazıldı → {argv[1]}")
            return 0
    except NotYok as e:
        print(f"[surum_notlari] HATA: {e}", file=sys.stderr)
        return 1
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
