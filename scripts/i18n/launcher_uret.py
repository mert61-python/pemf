# -*- coding: utf-8 -*-
"""LAUNCHER KATALOĞUNDAN ÜRETİLEN DOSYALAR (I18N-0 · A4) — elle DÜZENLENMEZ, `launcher/i18n/{tr,en}.json` tek kaynaktır.

1. `launcher/app/ui/i18n_katalog.js` — arayüzün (index.html) `ui.*` alt ağacı; `<script src="i18n_katalog.js">` ile EŞZAMANLI yüklenir
   (pencere JS'ten bağımsız 250 ms sonra gösterilir → katalog zaman uyumsuz bir komutla gelseydi ilk karede metin eksik kalabilirdi).
2. `launcher/app/windows/hooks.nsi` içindeki `; >>> I18N-DIL` … `; <<< I18N-DIL` bloğu — `nsis.*` alt ağacından `LangString PEMF_<ad>`
   satırları. YALNIZ `tauri.conf.json` `bundle.windows.nsis.languages` listesindeki diller yazılır: yüklenmemiş bir dil için `LangString`
   o dile YARIM tablo açar (ölçüldü: 6 uyarı, `-WX`'te kırmızı). Dil listesi bayrağa bağlıdır (`scripts/i18n/bayrak.py`).

Kullanım:  ..\\python.exe scripts\\i18n\\launcher_uret.py [--denetle]   (denetle: yazmaz, fark varsa çıkış 1)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.i18n import ortak  # noqa: E402

JS_YOLU = "launcher/app/ui/i18n_katalog.js"
HOOKS_YOLU = "launcher/app/windows/hooks.nsi"
TAURI_CONF = "launcher/app/tauri.conf.json"
NSIS_DIL_KIMLIGI = {"Turkish": ("tr", 1055), "English": ("en", 1033)}
BLOK_BAS = "; >>> I18N-DIL"
BLOK_SON = "; <<< I18N-DIL"


def _katalog(kok: Path, dil: str) -> dict:
    return ortak.json_oku(kok / "launcher" / "i18n" / f"{dil}.json")


def js_metni(kok: Path) -> str:
    ui = {d: _katalog(kok, d).get("ui", {}) for d in ortak.DILLER}
    govde = json.dumps(ui, ensure_ascii=False, indent=1, sort_keys=True)
    return (
        "// ÜRETİLMİŞ DOSYA — ELLE DÜZENLEMEYİN. Kaynak: launcher/i18n/{tr,en}.json → ui.* · Üreteç: scripts/i18n/launcher_uret.py\n"
        "// (K-6: katalog ile bu dosya ayrışırsa tests/test_i18n_launcher_altyapi.py kırmızı.)\n"
        f"window.PEMF_I18N_KATALOG = {govde};\n"
    )


def nsis_dilleri(kok: Path) -> list[str]:
    conf = ortak.json_oku(kok / TAURI_CONF)
    return list(((conf.get("bundle") or {}).get("windows") or {}).get("nsis", {}).get("languages") or ["English"])


def langstring_adi(anahtar: str) -> str:
    return "PEMF_" + anahtar.replace(".", "_")


def _nsis_dizgi(s: str) -> str:
    # Katalogda NSIS kaçışları ($\r$\n, $\") zaten yazılıdır; ham çift tırnak kaçışlanır.
    return re.sub(r'(?<!\$\\)"', '$\\\\"', s)


def nsis_blogu(kok: Path, sonu: str = "\r\n") -> str:
    satirlar = [
        f"{BLOK_BAS} — ÜRETİLMİŞ (scripts/i18n/launcher_uret.py): ELLE DÜZENLEMEYİN. Kaynak launcher/i18n/{{tr,en}}.json → nsis.*",
        "; Yalnız tauri.conf.json bundle.windows.nsis.languages dilleri yazılır (yüklenmemiş dil = yarım tablo, -WX kırmızı).",
    ]
    for dil_adi in nsis_dilleri(kok):
        kod, kimlik = NSIS_DIL_KIMLIGI[dil_adi]
        duz = ortak.duzlestir(_katalog(kok, kod).get("nsis", {}))
        for k in sorted(duz):
            satirlar.append(f'LangString {langstring_adi(k)} {kimlik} "{_nsis_dizgi(duz[k])}"')
    satirlar.append(BLOK_SON)
    return sonu.join(satirlar)


def hooks_metni(kok: Path) -> str:
    ham = (kok / HOOKS_YOLU).read_bytes().decode("utf-8")
    blok = nsis_blogu(kok, "\r\n" if "\r\n" in ham else "\n")
    desen = re.compile(re.escape(BLOK_BAS) + r".*?" + re.escape(BLOK_SON), re.S)
    if desen.search(ham):
        return desen.sub(lambda _m: blok, ham, count=1)
    raise SystemExit(
        f"{HOOKS_YOLU} içinde '{BLOK_BAS}' … '{BLOK_SON}' bloğu yok — bir kez elle yerleştirin (dosyanın başı)"
    )


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--denetle", action="store_true")
    ap.add_argument("--kok")
    a = ap.parse_args(argv)
    kok = Path(a.kok).resolve() if a.kok else ortak.KOK
    hedefler = {JS_YOLU: js_metni(kok), HOOKS_YOLU: hooks_metni(kok)}
    fark = []
    for yol, yeni in hedefler.items():
        p = kok / yol
        eski = p.read_bytes().decode("utf-8") if p.exists() else None
        if eski is None or eski.replace("\r\n", "\n") != yeni.replace(
            "\r\n", "\n"
        ):  # satır sonu (autocrlf) fark sayılmaz
            fark.append(yol)
            if not a.denetle:
                p.write_bytes(yeni.encode("utf-8"))
    if a.denetle:
        print(
            "[OK] üretilmiş launcher dosyaları katalogla aynı"
            if not fark
            else f"[FARK] {fark} → scripts/i18n/launcher_uret.py"
        )
        return 1 if fark else 0
    print(f"yazıldı: {fark or 'değişiklik yok'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
