# -*- coding: utf-8 -*-
"""İNGİLİZCE BAYRAĞI — TEK KAYNAK `i18n/bayrak.json`, TEK KOMUT (Y158).

Göç bitip `14-I18N-INCELEME` onaylayana dek KAPALI: dil seçeneği her yüzeyde gizli, etkin dil tr, kurulum sihirbazı yalnız Türkçe.
Bayrağı YALNIZ inceleme oturumu açar:
    ..\\python.exe scripts\\i18n\\bayrak.py --ac        # bütün yüzeyler + NSIS dil listesi + hooks LangString bloğu
    ..\\python.exe scripts\\i18n\\bayrak.py --kapat
    ..\\python.exe scripts\\i18n\\bayrak.py --denetle   # yazmaz; ana kaynakla ayrışan yüzey → çıkış 1 (K-5 de bunu çağırır)

Yüzey sabitleri (elle DEĞİŞTİRİLMEZ): arayüz / site / DEMA `src/i18n/bayrak.ts` (`I18N_EN_ACIK: boolean = …`), launcher
`core/src/dil.rs` (`pub const I18N_EN_ACIK: bool = …;`), `launcher/app/tauri.conf.json` `bundle.windows.nsis.languages`
(kapalı: ["Turkish"] · açık: ["Turkish", "English"] — Windows Türkçe ise Türkçe, değilse İngilizce sihirbaz);
`apps/ui/auth-pages/i18n_katalog.js` (auth sayfaları: kapalıyken HER ZAMAN Türkçe — `scripts/i18n/auth_uret.py` üretir).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.i18n import auth_uret, launcher_uret, ortak  # noqa: E402

ANA = "i18n/bayrak.json"
TS_SABITLERI = (
    "apps/ui/src/i18n/bayrak.ts",
    "apps/web/src/i18n/bayrak.ts",
    "dema-terapi-simülatörü/src/i18n/bayrak.ts",
)
RS_SABITI = "launcher/core/src/dil.rs"
TS_DESEN = re.compile(r"(export const I18N_EN_ACIK: boolean = )(true|false)")
RS_DESEN = re.compile(r"(pub const I18N_EN_ACIK: bool = )(true|false)(;)")
NSIS_DILLERI = {False: ["Turkish"], True: ["Turkish", "English"]}


def ana_deger(kok: Path) -> bool:
    return bool(json.loads((kok / ANA).read_text(encoding="utf-8"))["I18N_EN_ACIK"])


def yuzey_degerleri(kok: Path) -> dict[str, object]:
    d: dict[str, object] = {}
    for y in TS_SABITLERI:
        m = TS_DESEN.findall((kok / y).read_text(encoding="utf-8"))
        d[y] = (m[0][1] == "true") if len(m) == 1 else f"!!! {len(m)} eşleşme"
    m = RS_DESEN.findall((kok / RS_SABITI).read_text(encoding="utf-8"))
    d[RS_SABITI] = (m[0][1] == "true") if len(m) == 1 else f"!!! {len(m)} eşleşme"
    d[launcher_uret.TAURI_CONF] = launcher_uret.nsis_dilleri(kok)
    return d


def denetle(kok: Path) -> list[str]:
    acik = ana_deger(kok)
    sorun = []
    for yol, v in yuzey_degerleri(kok).items():
        beklenen = NSIS_DILLERI[acik] if yol == launcher_uret.TAURI_CONF else acik
        if v != beklenen:
            sorun.append(f"{yol}: {v!r} ≠ {beklenen!r} (ana kaynak {ANA}: {acik})")
    try:
        yeni = launcher_uret.hooks_metni(kok)
        eski = (kok / launcher_uret.HOOKS_YOLU).read_bytes().decode("utf-8")
        if yeni.replace("\r\n", "\n") != eski.replace("\r\n", "\n"):
            sorun.append(
                f"{launcher_uret.HOOKS_YOLU}: LangString bloğu dil listesiyle / katalogla ayrışmış → launcher_uret.py"
            )
    except SystemExit as e:
        sorun.append(str(e))
    try:
        yeni_js = auth_uret.js_metni(kok)
        eski_js = (kok / auth_uret.JS_YOLU).read_bytes().decode("utf-8")
        if yeni_js.replace("\r\n", "\n") != eski_js.replace("\r\n", "\n"):
            sorun.append(f"{auth_uret.JS_YOLU}: katalog / bayrakla ayrışmış → scripts/i18n/auth_uret.py")
    except (OSError, SystemExit) as e:
        sorun.append(f"{auth_uret.JS_YOLU}: {e}")
    return sorun


def ayarla(kok: Path, acik: bool) -> None:
    ana = kok / ANA
    # Satır sonu dosyanınki korunur (autocrlf'li çalışma kopyasında `--ac` → `--kapat` dosyayı BAYT BAYT geri getirsin).
    sonu = "\r\n" if ana.exists() and b"\r\n" in ana.read_bytes() else "\n"
    ana.write_bytes((json.dumps({"I18N_EN_ACIK": acik}, indent=2) + "\n").replace("\n", sonu).encode("utf-8"))
    deger = "true" if acik else "false"
    for y in TS_SABITLERI:
        p = kok / y
        ham = p.read_bytes().decode("utf-8")
        p.write_bytes(TS_DESEN.sub(lambda m: m.group(1) + deger, ham, count=1).encode("utf-8"))
    p = kok / RS_SABITI
    ham = p.read_bytes().decode("utf-8")
    p.write_bytes(RS_DESEN.sub(lambda m: m.group(1) + deger + m.group(3), ham, count=1).encode("utf-8"))
    p = kok / launcher_uret.TAURI_CONF
    ham = p.read_bytes().decode("utf-8")
    yeni_liste = json.dumps(NSIS_DILLERI[acik], ensure_ascii=False)
    yeni, n = re.subn(r'("languages"\s*:\s*)\[[^\]]*\]', lambda m: m.group(1) + yeni_liste, ham, count=1)
    if n != 1:
        raise SystemExit(f"{launcher_uret.TAURI_CONF}: bundle.windows.nsis.languages bulunamadı")
    p.write_bytes(yeni.encode("utf-8"))
    launcher_uret.main(["--kok", str(kok)])
    auth_uret.main(["--kok", str(kok)])


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--ac", action="store_true")
    g.add_argument("--kapat", action="store_true")
    g.add_argument("--denetle", action="store_true")
    ap.add_argument("--kok")
    a = ap.parse_args(argv)
    kok = Path(a.kok).resolve() if a.kok else ortak.KOK
    if a.denetle:
        s = denetle(kok)
        for x in s:
            print("  ✗", x)
        print("[OK] bayrak her yüzeyde ana kaynakla aynı" if not s else f"[SORUN] {len(s)}")
        return 1 if s else 0
    ayarla(kok, a.ac)
    s = denetle(kok)
    print(
        f"[{'OK' if not s else 'SORUN'}] I18N_EN_ACIK = {a.ac} — {len(TS_SABITLERI) + 2} yüzey + hooks bloğu"
        + (f": {s}" if s else "")
    )
    return 1 if s else 0


if __name__ == "__main__":
    raise SystemExit(main())
