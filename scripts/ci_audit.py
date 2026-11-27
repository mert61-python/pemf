# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""BAĞIMLILIK DENETİMİ BLOKLAYICI (istem 66 CT2 e · Y326 katman 8) — pip-audit / npm audit; yalnız gerekçeli liste yoksayılır.

Liste: `scripts/audit_borcu.json` (cargo audit deseni — `launcher/.cargo/audit.toml` ile TUTARLI politika):
  · `uygulanamaz` — bu üründe erişilemeyen / platform dışı tavsiyeler (gerekçe ZORUNLU). GERÇEK açık buraya ASLA eklenmez.
  · `bilinen_borc` — CT2'de (28-11) ölçülen GERÇEK açıklar: yükseltme kararı [SAHİBE] (Y3: onnx / torch sabit). CIRCIR — yalnız KÜÇÜLÜR:
    paket yükseltilince satır silinir; listede OLMAYAN her YENİ açık CI'ı KIRMIZI yapar (sessiz yeni açık biter).
Kipler:
  pip-yoksay                      → pip-audit `--ignore-vuln <kimlik>` argümanları (uygulanamaz + bilinen borç)
  npm <proje> <npm-audit.json>    → npm audit JSON'u listeyle karşılaştır (çıkış 1 = listede olmayan tavsiye)
  borc-uret --pip <json>… --npm <proje>=<json>…  → listeyi ölçümden yeniden yaz (YEREL araç; gerekçeler korunur)
Kapı: tests/test_CT2e_tedarik_zinciri_KAPILARI.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
BORC = KOK / "scripts" / "audit_borcu.json"
_GHSA = re.compile(r"GHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}")


def borc_oku(yol: Path = BORC) -> dict:
    return json.loads(yol.read_text(encoding="utf-8"))


def pip_kimlikleri(borc: dict) -> list[str]:
    kim: set[str] = set()
    for k in borc["pip"].get("uygulanamaz", []):
        kim.add(k["kimlik"])
    for k in borc["pip"].get("bilinen_borc", []):
        kim.update(k["kimlikler"])
    return sorted(kim)


def npm_bulgulari(audit: dict) -> set[tuple[str, str]]:
    """npm audit --json → {(paket, GHSA)}; yalnız DOĞRUDAN tavsiye kayıtları (`via` nesneleri)."""
    sonuc: set[tuple[str, str]] = set()
    for ad, v in (audit.get("vulnerabilities") or {}).items():
        for via in v.get("via") or []:
            if isinstance(via, dict):
                m = _GHSA.search(str(via.get("url", "")))
                sonuc.add((ad, m.group(0) if m else f"npm-{via.get('source')}"))
    return sonuc


def npm_karsilastir(proje: str, audit: dict, borc: dict) -> tuple[list[str], list[str]]:
    """→ (YENİ bulgular, kapanmış borç satırları)."""
    kayitli = {(k["paket"], k["tavsiye"]) for k in borc["npm"].get(proje, [])}
    kayitli |= {(k["paket"], k["tavsiye"]) for k in borc.get("npm_uygulanamaz", {}).get(proje, [])}
    bulunan = npm_bulgulari(audit)
    yeni = sorted(f"{p} {t}" for p, t in bulunan - kayitli)
    kapanan = sorted(f"{p} {t}" for p, t in kayitli - bulunan)
    return yeni, kapanan


def borc_uret(pip_jsonlari: list[Path], npm_jsonlari: dict[str, Path], eski: dict | None) -> dict:
    eski = eski or {"pip": {"uygulanamaz": [], "bilinen_borc": []}, "npm": {}}
    gerekce = {(k["paket"]): (k.get("gerekce"), k.get("karar")) for k in eski["pip"].get("bilinen_borc", [])}
    paketler: dict[tuple[str, str], dict] = {}
    for yol in pip_jsonlari:
        d = json.loads(yol.read_text(encoding="utf-8"))
        for p in d["dependencies"] if isinstance(d, dict) else d:
            for v in p.get("vulns") or []:
                k = paketler.setdefault(
                    (p["name"].lower(), p.get("version", "")),
                    {"paket": p["name"].lower(), "surum": p.get("version", ""), "kimlikler": set(), "kaynak": set()},
                )
                k["kimlikler"].add(v["id"])
                k["kaynak"].add(yol.stem)
    borc_listesi = []
    for (ad, _), k in sorted(paketler.items()):
        g, karar = gerekce.get(ad, (None, None))
        borc_listesi.append(
            {
                "paket": k["paket"],
                "surum": k["surum"],
                "kimlikler": sorted(k["kimlikler"]),
                "kaynak": sorted(k["kaynak"]),
                "gerekce": g or "CT2 e (28-11) ölçümünde açık — yamalı sürüme yükseltme kararı bekliyor",
                "karar": karar or "[SAHİBE] yükseltme",
            }
        )
    npm: dict[str, list] = {}
    for proje, yol in sorted(npm_jsonlari.items()):
        d = json.loads(yol.read_text(encoding="utf-8"))
        npm[proje] = [{"paket": p, "tavsiye": t} for p, t in sorted(npm_bulgulari(d))]
    yeni = dict(eski)
    yeni["pip"] = {"uygulanamaz": eski["pip"].get("uygulanamaz", []), "bilinen_borc": borc_listesi}
    yeni["npm"] = npm
    return yeni


def _konsol_utf8() -> None:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _konsol_utf8()
    ap = argparse.ArgumentParser(description="pip-audit / npm audit bloklayıcı karşılaştırma")
    alt = ap.add_subparsers(dest="kip", required=True)
    alt.add_parser("pip-yoksay")
    n = alt.add_parser("npm")
    n.add_argument("proje")
    n.add_argument("json", type=Path)
    b = alt.add_parser("borc-uret")
    b.add_argument("--pip", type=Path, nargs="*", default=[])
    b.add_argument("--npm", nargs="*", default=[])
    ap.add_argument("--borc", type=Path, default=BORC)
    a = ap.parse_args(argv)
    if a.kip == "pip-yoksay":
        print(" ".join(f"--ignore-vuln {k}" for k in pip_kimlikleri(borc_oku(a.borc))))
        return 0
    if a.kip == "npm":
        try:
            audit = json.loads(a.json.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"!!! npm audit çıktısı okunamadı ({a.json}): {e} — denetim KÖR")
            return 2
        if "vulnerabilities" not in audit:
            print(
                f"!!! npm audit çıktısında `vulnerabilities` yok ({a.json}) — kayıt defteri hatası? {str(audit)[:300]}"
            )
            return 2
        yeni, kapanan = npm_karsilastir(a.proje, audit, borc_oku(a.borc))
        print(
            f"npm audit {a.proje}: {len(npm_bulgulari(audit))} tavsiye · listede olmayan {len(yeni)} · kapanan borç {len(kapanan)}"
        )
        for s in kapanan:
            print(f"::warning::borç KAPANDI (scripts/audit_borcu.json'dan satırı silin): {a.proje} {s}")
        if yeni:
            print(
                "!!! YENİ GÜVENLİK TAVSİYESİ (listede yok) — paketi yükseltin; gerçek açık listeye EKLENMEZ:\n  "
                + "\n  ".join(yeni)
            )
            return 1
        return 0
    eski = borc_oku(a.borc) if a.borc.is_file() else None
    npm = dict(x.split("=", 1) for x in a.npm)
    yeni = borc_uret(a.pip, {k: Path(v) for k, v in npm.items()}, eski)
    a.borc.write_text(json.dumps(yeni, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(
        f"yazıldı: {a.borc} · pip {len(yeni['pip']['bilinen_borc'])} paket · npm {sum(len(v) for v in yeni['npm'].values())}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
