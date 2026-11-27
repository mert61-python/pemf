# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""FARK KAPSAMI KAPISI (CT1 f-3 · istem 66 · Y311 / Y325) — değişen her ölçülen satır testle koşmalı (%100).

NEDEN: kapsam tabanı (`tests/kapsam_tabani.json`) paket TOPLAMINI kilitler; ama büyük bir pakette yeni eklenen testsiz 20 satır toplamı
ancak 0,05 puan düşürür ve yuvarlamada kaybolabilir. Bu kapı dalın DEĞİŞTİRDİĞİ satırlara bakar: rapordaki (ölçülen) bir satır değiştiyse
ve hiç koşmadıysa → KIRMIZI. Bilinçli açık kalan kol (CLAUDE.md "Test kapsamı" madde 3) kodda gerekçeli etiketle ölçümden çıkar
(`# pragma: no cover — <neden>` / `/* istanbul ignore next — <neden> */` / `LCOV_EXCL_LINE`) → rapora hiç girmez, sayılmaz.

RAPORLAR (birden çok verilebilir; her biri kendi kökünden çözülür):
    --covjson coverage.json[:<kök>]    coverage.py JSON (`scripts/kapsam_tabani_kapisi.py --json`) — yollar <kök>'e göre, TEK anlamlı
                                       (⚠️ Cobertura XML dosya adını paket köküne göre yazar: `__init__.py` gibi adlar paketler arası
                                       ÇAKIŞIR — Python için JSON kullanın)
    --cobertura coverage.xml[:<kök>]   Cobertura (tek kaynak kökü olan araçlar için)
    --lcov lcov.info[:<kök>]           jest / vitest / cargo llvm-cov / gcov (lcov) — SF yolları mutlak ya da <kök>'e göre
Ölçülen satır = raporda satır kaydı (DA / <line>) olan satır; dal bilgisi (BRDA / condition-coverage) varsa kısmi dallı satır da AÇIK sayılır.
Rapordaki dosyalar dışındaki değişiklikler (testler, belgeler, ölçülmeyen paketler) bu kapının konusu DEĞİL.

TABAN: `--taban <ref>` (birleşme tabanı alınır); verilmezse ilk bulunan: origin/duzeltme/dalga-2, duzeltme/dalga-2,
origin/production-hardening. Değişen satır = `git diff -U0 <birleşme-tabanı>` (çalışma ağacı dahil: commit öncesi kapıda da koşar).
ÇIKIŞ: 0 = değişen ölçülen satırların hepsi koştu · 1 = açık satır var · 2 = taban / rapor yok (kör kapı).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
TABAN_ADAYLARI = ("origin/duzeltme/dalga-2", "duzeltme/dalga-2", "origin/production-hardening")


def _git(*a: str, kok: Path = KOK) -> str:
    return subprocess.run(
        ["git", "-c", "core.quotepath=false", *a], cwd=kok, capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout


def birlesme_tabani(taban: str | None, kok: Path = KOK) -> str | None:
    for aday in [taban] if taban else TABAN_ADAYLARI:
        try:
            return _git("merge-base", "HEAD", aday, kok=kok).strip()
        except subprocess.CalledProcessError:
            continue
    return None


def degisen_satirlar(taban_sha: str, kok: Path = KOK) -> dict[str, set[int]]:
    """depo-göreli yol (/) → eklenen / değişen satır numaraları (yeni dosyada)."""
    sonuc: dict[str, set[int]] = {}
    dosya = None
    for s in _git("diff", "-U0", "--no-color", "--no-ext-diff", taban_sha, kok=kok).splitlines():
        if s.startswith("+++ "):
            dosya = None if s[4:] == "/dev/null" else s[6:] if s.startswith("+++ b/") else s[4:]
            if dosya is not None:
                sonuc.setdefault(dosya, set())
        elif s.startswith("@@") and dosya is not None:
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", s)
            bas, adet = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
            sonuc[dosya].update(range(bas, bas + adet))
    return {d: s for d, s in sonuc.items() if s}


def _goreli(yol: str, kok: Path, depo: Path) -> str | None:
    p = Path(yol)
    p = p if p.is_absolute() else kok / p
    try:
        return p.resolve().relative_to(depo.resolve()).as_posix()
    except ValueError:
        return None


def cobertura_oku(yol: Path, kok: Path, depo: Path) -> dict[str, dict[int, bool]]:
    """dosya → {satır: koştu_mu (dal kısmiyse False)}."""
    agac = ET.parse(yol).getroot()
    kaynaklar = [Path(s.text.strip()) for s in agac.iter("source") if s.text and s.text.strip()] or [kok]
    sonuc: dict[str, dict[int, bool]] = {}
    for sinif in agac.iter("class"):
        ad = sinif.get("filename", "")
        for k in kaynaklar:
            goreli = _goreli(str(Path(k) / ad) if not Path(ad).is_absolute() else ad, kok, depo)
            if goreli and (depo / goreli).exists():
                break
        else:  # hiçbir kaynak kökünde bulunmadı → ölçüme girmez (son aday tutulmaz)
            continue
        satirlar = sonuc.setdefault(goreli, {})
        for ln in sinif.iter("line"):
            no = int(ln.get("number"))
            kostu = int(ln.get("hits", "0")) > 0
            cc = ln.get("condition-coverage", "")
            if ln.get("branch") == "true" and cc and not cc.startswith("100%"):
                kostu = False
            satirlar[no] = satirlar.get(no, True) and kostu
    return sonuc


def covjson_oku(yol: Path, kok: Path, depo: Path) -> dict[str, dict[int, bool]]:
    """coverage.py JSON: koşan / koşmayan satırlar; dal bilgisi varsa kısmi dallı satır (missing_branches kaynağı) AÇIK."""
    sonuc: dict[str, dict[int, bool]] = {}
    for ad, d in json.loads(yol.read_text(encoding="utf-8")).get("files", {}).items():
        goreli = _goreli(ad, kok, depo)
        if not goreli:
            continue
        s = {int(n): True for n in d.get("executed_lines", [])}
        s.update({int(n): False for n in d.get("missing_lines", [])})
        for kaynak_satir, _hedef in d.get("missing_branches", []):
            if int(kaynak_satir) in s:
                s[int(kaynak_satir)] = False
        sonuc[goreli] = s
    return sonuc


def lcov_oku(yol: Path, kok: Path, depo: Path) -> dict[str, dict[int, bool]]:
    sonuc: dict[str, dict[int, bool]] = {}
    goreli, satirlar = None, None
    for s in yol.read_text(encoding="utf-8", errors="replace").splitlines():
        if s.startswith("SF:"):
            goreli = _goreli(s[3:].strip(), kok, depo)
            satirlar = sonuc.setdefault(goreli, {}) if goreli else None
        elif satirlar is None:
            continue
        elif s.startswith("DA:"):
            no, hit = s[3:].split(",")[:2]
            satirlar[int(no)] = satirlar.get(int(no), True) and int(float(hit)) > 0
        elif s.startswith("BRDA:"):
            no, _blok, _dal, hit = s[5:].split(",")[:4]
            if hit in ("-", "0"):  # koşmayan dal → satır AÇIK (lcov'da BRDA, DA'dan önce gelir; DA bunu ezmez)
                satirlar[int(no)] = False
        elif s == "end_of_record":
            goreli, satirlar = None, None
    return sonuc


def _rapor(arg: str) -> tuple[Path, Path]:
    # "yol[:kök]" — Windows sürücü harfi (C:\…) iki noktayla karışmasın: kök ayırıcısı SON '::' değil, sürücüden sonraki ':'
    m = re.match(r"^((?:[A-Za-z]:)?[^:]+)(?::((?:[A-Za-z]:)?[^:]+))?$", arg)
    if not m:
        raise ValueError(f"rapor bağımsız değişkeni çözülemedi: {arg!r}")
    return Path(m.group(1)), Path(m.group(2)) if m.group(2) else KOK


def denetle(taban: str | None, cobertura: list[str], lcov: list[str], depo: Path = KOK, covjson: list[str] = ()) -> int:
    t = birlesme_tabani(taban, depo)
    if not t:
        print(f"!!! fark tabanı bulunamadı ({taban or ' / '.join(TABAN_ADAYLARI)}) — kapı kör")
        return 2
    olcum: dict[str, dict[int, bool]] = {}
    okuyucu = {"cobertura": cobertura_oku, "lcov": lcov_oku, "covjson": covjson_oku}
    for tur, liste in (("cobertura", cobertura), ("lcov", lcov), ("covjson", covjson)):
        for arg in liste:
            yol, kok = _rapor(arg)
            if not yol.is_file():
                print(f"!!! kapsam raporu yok: {yol} — kapı kör")
                return 2
            okunan = okuyucu[tur](yol, kok, depo)
            for d, s in okunan.items():
                hedef = olcum.setdefault(d, {})
                for no, k in s.items():
                    hedef[no] = hedef.get(no, False) or k  # birden çok rapor: herhangi biri koşturduysa koştu
    if not olcum:
        print("!!! kapsam raporları BOŞ — kapı kör")
        return 2
    degisen = degisen_satirlar(t, depo)
    toplam, acik = 0, {}
    for d, satirlar in sorted(degisen.items()):
        if d not in olcum:
            continue
        olculen = {n: olcum[d][n] for n in satirlar if n in olcum[d]}
        toplam += len(olculen)
        a = sorted(n for n, k in olculen.items() if not k)
        if a:
            acik[d] = a
    acik_say = sum(len(v) for v in acik.values())
    yuzde = 100.0 if toplam == 0 else 100.0 * (toplam - acik_say) / toplam
    print(f"fark kapsamı: taban {t[:8]} · değişen ölçülen satır {toplam} · açık {acik_say} · %{yuzde:.2f}")
    if acik:
        print(
            "!!! FARK KAPSAMI KAPISI KIRMIZI — değişen ama testle koşmayan satırlar (test ekleyin; bilinçli açık kalan türse "
            "gerekçeli etiket — CLAUDE.md 'Test kapsamı'):"
        )
        for d, a in acik.items():
            print(f"  {d}: {_araliklar(a)}")
        return 1
    return 0


def _araliklar(n: list[int]) -> str:
    parca, bas, onceki = [], n[0], n[0]
    for x in n[1:] + [None]:
        if x is not None and x == onceki + 1:
            onceki = x
            continue
        parca.append(str(bas) if bas == onceki else f"{bas}–{onceki}")
        if x is not None:
            bas = onceki = x
    return ", ".join(parca)


def _konsol_utf8(akislar=None) -> None:
    """windows-latest konsolu cp1252 (YS1a dersi): Türkçe ileti yazımı düşmesin."""
    for akis in akislar or (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _konsol_utf8()
    ap = argparse.ArgumentParser(description="Fark kapsamı kapısı (CT1 f-3 · Y311 / Y325)")
    ap.add_argument("--taban")
    ap.add_argument("--cobertura", action="append", default=[])
    ap.add_argument("--lcov", action="append", default=[])
    ap.add_argument("--covjson", action="append", default=[])
    a = ap.parse_args(argv)
    if not a.cobertura and not a.lcov and not a.covjson:
        print("!!! en az bir kapsam raporu (--covjson / --cobertura / --lcov) gerekli")
        return 2
    return denetle(a.taban, a.cobertura, a.lcov, covjson=a.covjson)


if __name__ == "__main__":
    sys.exit(main())
