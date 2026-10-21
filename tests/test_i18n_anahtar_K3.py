# -*- coding: utf-8 -*-
"""K-3 · KULLANILAN HER ANAHTAR KATALOGDA (T14) — statik: kaynaktaki `t("…")`, `i18n.t("…")`, `ceviri.t("…")`, `kritikMetin("…")`,
`dil::t("…")` / `t_ile("…"`, `data-i18n="…"`, NSIS `$(PEMF_…)` anahtarı o yüzeyin TR kataloğunda var (çoğul kökü `_one/_other` ile
sayılır). Dinamik: ilk argümanı DEĞİŞMEZ dizgi olmayan çeviri çağrısı yalnız `i18n/dinamik-anahtarlar.json` izin listesindeyse geçer ve
listedeki önek + değerlerin HEPSİ katalogda bulunur.

Neden kapı: arayüzde tür denetimi yanlış anahtarı yakalar, ama sunucu (Python), launcher (Rust / HTML / NSIS) ve DEMA'da yakalayan YOK —
eksik anahtar üründe ekrana anahtar adını basar (ya da Türkçeye düşer). Dinamik anahtar (`t(\`ai.deger.${x}\`)`) hiçbir statik denetime
görünmez; izin listesi onu görünür ve sınanabilir yapar.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
for p in (KOK, KOK / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import i18n_yardimci as iy  # noqa: E402

from scripts.i18n import cikar, ortak  # noqa: E402

DINAMIK = json.loads((KOK / "i18n" / "dinamik-anahtarlar.json").read_text(encoding="utf-8"))
#: Çeviri çağrısı, ilk argüman değişmez dizgi DEĞİL (şablon / değişken / ifade). Yorum satırları önceden soyulur.
DINAMIK_CAGRI = re.compile(r"""(?:\bi18n\.t|\bceviri\.t|\bkritikMetin|\bdil::t|\bt_ile|(?<![\w.])t)\(\s*(?!["'\s)])""")
#: Çevirmenin KENDİ tanımı (`def t(`, `pub fn t(`, `export function t(`) çağrı değildir — satırdan çıkarılıp öyle bakılır.
TANIM = re.compile(r"\b(?:def|fn|function)\s+(?:t|t_ile|kritikMetin)\s*\(")


def _yorumsuz(metin: str, dosya: str) -> str:
    if dosya.endswith(".py"):
        return re.sub(r"(?m)^[ \t]*#.*$", "", metin)  # `\s*` boş satırı yutup satır numarasını kaydırırdı (ölçüldü)
    if dosya.endswith(".rs"):
        # çıkarıcının KENDİ soyucusu: yorumlar + `#[cfg(test)]` / `#[test]` bölgeleri boşluk (satır numarası korunur)
        soy, _ = cikar._rust_soy(metin)
        out = list(soy)
        for a, b in cikar._rust_test_bolgeleri(soy):
            for i in range(a, b):
                if out[i] != "\n":
                    out[i] = " "
        return "".join(out)
    # I18NI-A2.5: dizgi farkında soyucu (eski düzenli ifade `'image/*'` dizgisinden sonraki KODU bir sonraki `*/`'a dek yutuyordu)
    return ortak.ts_yorumsuz(metin)


def _var(anahtar: str, duz: dict) -> bool:
    return ortak.anahtar_kullanilabilir(anahtar, duz)


@pytest.mark.parametrize("yuzey", list(ortak.YUZEYLER))
def test_K3_statik_anahtarlar_katalogda(yuzey):
    duz = ortak.duzlestir(ortak.katalog_yukle(yuzey, "tr"))
    eksik = []
    for f in ortak.yuzey_dosyalari(yuzey, KOK):
        for k in iy.kullanilan_anahtarlar(_yorumsuz((KOK / f).read_text(encoding="utf-8"), f)):
            if not _var(k, duz):
                eksik.append(f"{f}: {k}")
    assert not eksik, "katalogda olmayan anahtar(lar):\n" + "\n".join(eksik)


@pytest.mark.parametrize("yuzey", list(ortak.YUZEYLER))
def test_K3_dinamik_cagrilar_izin_listesinde_ve_degerleri_katalogda(yuzey):
    duz = ortak.duzlestir(ortak.katalog_yukle(yuzey, "tr"))
    izin = [d for d in DINAMIK["izinler"] if d["yuzey"] == yuzey]
    sorun = []
    for f in ortak.yuzey_dosyalari(yuzey, KOK):
        metin = _yorumsuz((KOK / f).read_text(encoding="utf-8"), f)
        for no, satir in enumerate(metin.splitlines(), 1):
            satir = TANIM.sub("", satir)
            if DINAMIK_CAGRI.search(satir) and not any(d["dosya"] == f and d["ifade"] in satir for d in izin):
                sorun.append(f"{f}:{no}: izin listesinde olmayan DİNAMİK çeviri çağrısı: {satir.strip()[:140]}")
    for d in izin:
        for v in d["degerler"]:
            if not _var(d["onek"] + v, duz):
                sorun.append(f"{d['dosya']}: dinamik anahtar katalogda yok: {d['onek'] + v}")
    assert not sorun, "\n".join(sorun)


def test_K3_KARSIT_kapi_eksik_anahtari_ve_dinamik_cagriyi_YAKALAR():
    kaynak = 'const a = t("olmayan.anahtar"); const b = t(`ai.deger.${x}`); const c = ceviri.t("ayni.yok")'
    assert {"olmayan.anahtar", "ayni.yok"} <= iy.kullanilan_anahtarlar(kaynak)
    assert DINAMIK_CAGRI.search('const b = t(`ai.deger.${x}`);') and not DINAMIK_CAGRI.search('t("x.y")')
    assert not DINAMIK_CAGRI.search("setTimeout(f, 1)") and not DINAMIK_CAGRI.search("obj.t(x)")


# ── I18NI-A2.3: TABLODA SAKLANAN anahtarlar (dinamik izinlerin `degerler`i elle kopya — koddaki tablo okunmalı) ──────────────────
#: Ad alanı önekli ama katalog anahtarı OLMAYAN değişmezler (gerekçeli): denetim günlüğü olay adı.
TABLO_ISTISNA = {("sunucu", "ai.review")}
_ANAHTAR_LIT = re.compile(r"""(["'`])([a-z][A-Za-z0-9]*(?:\.[A-Za-z0-9_]+)+)\1""")


def _py_dizgileri(metin: str) -> list[tuple[int, str]]:
    import ast

    agac = ast.parse(metin)
    belge = {
        id(n.body[0].value)
        for n in ast.walk(agac)
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and n.body
        and isinstance(n.body[0], ast.Expr)
        and isinstance(n.body[0].value, ast.Constant)
    }
    return [
        (n.lineno, n.value)
        for n in ast.walk(agac)
        if isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and id(n) not in belge
        and re.fullmatch(r"[a-z][A-Za-z0-9]*(?:\.[A-Za-z0-9_]+)+", n.value)
    ]


def tablo_anahtari_eksikleri(yuzey: str, kok: Path = KOK, dosyalar: list[str] | None = None) -> list[str]:
    duz = ortak.duzlestir(ortak.katalog_yukle(yuzey, "tr", kok))
    adalan = {k.split(".")[0] for k in duz}
    onekler = {".".join(k.split(".")[:i]) for k in duz for i in range(1, k.count(".") + 1)}
    sorun = []
    for f in dosyalar if dosyalar is not None else ortak.yuzey_dosyalari(yuzey, kok):
        metin = (kok / f).read_text(encoding="utf-8")
        if f.endswith(".py"):
            adaylar = _py_dizgileri(metin)
        else:
            kod = _yorumsuz(metin, f)
            adaylar = [(no, m.group(2)) for no, ln in enumerate(kod.split("\n"), 1) for m in _ANAHTAR_LIT.finditer(ln)]
        for no, a in adaylar:
            if a.split(".")[0] not in adalan or (yuzey, a) in TABLO_ISTISNA or _var(a, duz) or a in onekler:
                continue
            sorun.append(f"{f}:{no}: katalogda olmayan anahtar biçimli değişmez {a!r} (tabloda saklanan anahtar?)")
    return sorun


@pytest.mark.parametrize("yuzey", list(ortak.YUZEYLER))
def test_K3_tablodaki_anahtar_degismezleri_katalogda(yuzey):
    sorun = tablo_anahtari_eksikleri(yuzey)
    assert not sorun, "\n".join(sorun)


def test_K3_KARSIT_bozuk_tablo_anahtari_YAKALANIR(tmp_path):
    f = "apps/ui/src/screens/Ornek.tsx"
    (tmp_path / f).parent.mkdir(parents=True)
    (tmp_path / f).write_text(
        'const ORGAN_ANAHTARI = {\n  mide: "ai.organ.ad.mide",\n  bobrek: "ai.organ.ad.bobrekk",\n};\n'
        '// yorumda sayılmaz: "ai.organ.ad.yorumda"\n',
        encoding="utf-8",
    )
    for d in ortak.DILLER:
        hedef = tmp_path / "apps/ui/src/i18n" / d
        hedef.mkdir(parents=True, exist_ok=True)
        for p in (KOK / "apps/ui/src/i18n" / d).glob("*.json"):
            (hedef / p.name).write_bytes(p.read_bytes())
    sorun = tablo_anahtari_eksikleri("arayuz", tmp_path, [f])
    assert [s for s in sorun if "bobrekk" in s] and not [s for s in sorun if "mide" in s or "yorumda" in s], sorun
