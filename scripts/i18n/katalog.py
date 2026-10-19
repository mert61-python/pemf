# -*- coding: utf-8 -*-
"""I18N KATALOG ARACI — biçimle, eşlik raporu, anahtar / ad alanı ekle, çeviri parçası çıkar / geri al, TR taban karşılaştırması.

Kullanım (depo kökünden, gömülü Python):
  ..\\python.exe scripts\\i18n\\katalog.py bicimle [--yuzey Y ...] [--denetle]
      Kataloğu kanonik biçime yazar (2 boşluk girinti, anahtarlar alfabetik, UTF-8, LF, son satır sonu). --denetle: yazmaz, fark → çıkış 1.
  ..\\python.exe scripts\\i18n\\katalog.py esle [--yuzey Y ...]
      Eşlik raporu: tr ↔ en anahtar kümesi, boş değer, yer tutucu kümesi, çoğul biçimleri, NSIS değişkenleri. Sorun → çıkış 1.
  ..\\python.exe scripts\\i18n\\katalog.py adalani-ekle <arayuz|site> <ad>
      `src/i18n/{tr,en}/<ad>.json` (boş) + `kaynaklar.ts` içe aktarması / girdisi.
  ..\\python.exe scripts\\i18n\\katalog.py anahtar-ekle <yuzey> <anahtar> --tr "…" --en "…" [--ustune-yaz]
      Tek anahtarı İKİ DİLDE ekler (yer tutucu kümesi aynı olmalı). TR değeri ELLE YAZILMAZ — `uygula` kaynaktan taşır; bu komut
      yalnız kaynakta karşılığı olmayan YENİ metin içindir.
  ..\\python.exe scripts\\i18n\\katalog.py parca-cikar <yuzey> [--onek P] [--eksik-en] [--boyut 150] [--aday aday.json] --cikti parca.json
      Çeviri parçası: [{anahtar, tr, en, baglam}] (≤ boyut). --eksik-en: yalnız en'i boş / olmayanlar. --aday: bağlam notu (dosya:satır +
      kaynak satırı) `cikar` çıktısından.
  ..\\python.exe scripts\\i18n\\katalog.py parca-geri-al <parca.json> [--yuzey Y]
      Parçadaki DOLU `en` değerlerini kataloğa yazar; yer tutucu kümesi tr ile aynı değilse REDDEDER.
  ..\\python.exe scripts\\i18n\\katalog.py taban (--grup G | --dosya F ...) [--taban YOL]
      Göç öncesi TR tabanındaki (`DENETIM\\I18N\\taban-tr-metinler.json`) bu dosyalara ait her metin: tr katalogda AYNEN var mı, ya da
      kapsam defterinde MUAF mı, ya da BİRLEŞİK istisna listesinde mi? Karşılanmayan → çıkış 1 (Türkçe gerilemesi).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.i18n import kapsam, ortak  # noqa: E402

VARSAYILAN_TABAN = ortak.varsayilan_taban()
NSIS_DEGISKEN = re.compile(r"\$(?:\{\w+\}|\w+)")


def kanonik(d: dict) -> str:
    return json.dumps(d, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def yuzeyler(secim: list[str] | None) -> list[str]:
    return list(ortak.KATALOGLAR) if not secim or "hepsi" in secim else secim


# ── bicimle ──────────────────────────────────────────────────────────────────────────────────────────────────


def bicimle(kok: Path, secim: list[str] | None, denetle: bool) -> list[str]:
    farkli = []
    for y in yuzeyler(secim):
        for dil in ortak.DILLER:
            for _ns, yol in ortak.katalog_dosyalari(y, dil, kok).items():
                ham = yol.read_bytes().decode("utf-8")
                yeni = kanonik(json.loads(ham))
                if ham.replace("\r\n", "\n") != yeni:
                    farkli.append(str(yol.relative_to(kok)).replace("\\", "/"))
                    if not denetle:
                        yol.write_bytes(yeni.encode("utf-8"))
    return farkli


# ── esle (eşlik raporu) ──────────────────────────────────────────────────────────────────────────────────────


def esle(kok: Path, secim: list[str] | None) -> list[str]:
    sorunlar: list[str] = []
    for y in yuzeyler(secim):
        tr_dosya = ortak.katalog_dosyalari(y, "tr", kok)
        en_dosya = ortak.katalog_dosyalari(y, "en", kok)
        if set(tr_dosya) != set(en_dosya):
            sorunlar.append(f"{y}: ad alanı dosyaları farklı tr={sorted(tr_dosya)} en={sorted(en_dosya)}")
        tr = ortak.duzlestir(ortak.katalog_yukle(y, "tr", kok))
        en = ortak.duzlestir(ortak.katalog_yukle(y, "en", kok))
        for k in sorted(set(tr) - set(en)):
            sorunlar.append(f"{y}: en'de YOK: {k}")
        for k in sorted(set(en) - set(tr)):
            sorunlar.append(f"{y}: tr'de YOK: {k}")
        for dil, duz in (("tr", tr), ("en", en)):
            for k, v in duz.items():
                if not isinstance(v, str):
                    sorunlar.append(f"{y}/{dil}: dizgi değil: {k} = {v!r}")
                elif not v.strip():
                    sorunlar.append(f"{y}/{dil}: BOŞ değer: {k}")
                if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)*", k):
                    sorunlar.append(f"{y}/{dil}: anahtar ASCII / noktalı değil: {k}")
        for k in sorted(set(tr) & set(en)):
            if ortak.yer_tutuculari(tr[k]) != ortak.yer_tutuculari(en[k]):
                sorunlar.append(
                    f"{y}: yer tutucu farklı {k}: tr={sorted(ortak.yer_tutuculari(tr[k]))} en={sorted(ortak.yer_tutuculari(en[k]))}"
                )
            if y == "launcher" and k.startswith("nsis."):
                a, b = set(NSIS_DEGISKEN.findall(str(tr[k]))), set(NSIS_DEGISKEN.findall(str(en[k])))
                if a != b:
                    sorunlar.append(f"{y}: NSIS değişkenleri farklı {k}: tr={sorted(a)} en={sorted(b)}")
            yasak = {"dil", "anahtar"} & ortak.yer_tutuculari(tr[k])
            if y == "sunucu" and yasak:
                sorunlar.append(
                    f"{y}: {sorted(yasak)} yer tutucusu yasak (ceviri.t(anahtar, dil=…) parametreleriyle çakışır): {k}"
                )
        for dil, duz in (("tr", tr), ("en", en)):
            kokler = {ortak.cogul_koku(k) for k in duz if ortak.cogul_koku(k)}
            for kk in sorted(kokler):
                for s in ortak.COGUL_BICIMLERI[dil]:
                    if kk + s not in duz:
                        sorunlar.append(f"{y}/{dil}: çoğul biçimi eksik: {kk}{s}")
    return sorunlar


# ── adalani-ekle / anahtar-ekle ──────────────────────────────────────────────────────────────────────────────


def _kaynaklar_ts(kok: Path, yuzey: str) -> Path:
    return kok / ortak.KATALOGLAR[yuzey]["kok"] / "kaynaklar.ts"


def adalani_ekle(kok: Path, yuzey: str, ad: str) -> None:
    if ortak.KATALOGLAR[yuzey]["duzen"] != "dizin":
        raise SystemExit(f"{yuzey} tek dosyalı katalog — ad alanı yerine üst düzey anahtar ekleyin")
    if not re.fullmatch(r"[a-z][A-Za-z0-9]*", ad):
        raise SystemExit("ad alanı ASCII camelCase olmalı (ör. hastaListesi)")
    taban = kok / ortak.KATALOGLAR[yuzey]["kok"]
    for dil in ortak.DILLER:
        p = taban / dil / f"{ad}.json"
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"{}\n")
    ts = _kaynaklar_ts(kok, yuzey)
    metin = ts.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in metin else "\n"
    tirnak = '"' if yuzey == "arayuz" else "'"
    noktali_virgul = ";" if yuzey == "arayuz" else ""
    buyuk = ad[0].upper() + ad[1:]
    for dil in ("tr", "en"):
        satir = f"import {dil}{buyuk} from {tirnak}./{dil}/{ad}.json{tirnak}{noktali_virgul}"
        if satir not in metin:
            # `[^\r\n]*` — `.*$` CRLF dosyada `\r`'yi de yutar, ekleme `\r`'den SONRA düşüp `\r\r\n` (sondaki boşluk) üretirdi (ölçüldü)
            son_import = [m.end() for m in re.finditer(r"^import [^\r\n]*", metin, re.M)]
            konum = son_import[-1] if son_import else 0
            metin = metin[:konum] + nl + satir + metin[konum:]
    for dil in ("tr", "en"):
        blok = re.search(rf"export const {dil}Kaynak[^=]*= \{{(.*?)\r?\n\}}", metin, re.S)
        if not blok:
            raise SystemExit(f"kaynaklar.ts içinde {dil}Kaynak bloğu bulunamadı")
        girdi = f"  {ad}: {dil}{buyuk},"
        if girdi not in blok.group(1):
            metin = metin[: blok.end(1)] + nl + girdi + metin[blok.end(1) :]
    ts.write_bytes(metin.encode("utf-8"))


def _katalog_yolu(kok: Path, yuzey: str, dil: str, anahtar: str) -> tuple[Path, list[str]]:
    t = ortak.KATALOGLAR[yuzey]
    parca = anahtar.split(".")
    if t["duzen"] == "dizin":
        return kok / t["kok"] / dil / f"{parca[0]}.json", parca[1:]
    return kok / t["kok"] / f"{dil}.json", parca


def anahtar_yaz(kok: Path, yuzey: str, dil: str, anahtar: str, deger: str, ustune_yaz: bool = False) -> None:
    yol, parca = _katalog_yolu(kok, yuzey, dil, anahtar)
    if not yol.exists():
        raise SystemExit(f"katalog dosyası yok: {yol} (önce `katalog.py adalani-ekle {yuzey} {anahtar.split('.')[0]}`)")
    veri = json.loads(yol.read_text(encoding="utf-8"))
    d = veri
    for p in parca[:-1]:
        d = d.setdefault(p, {})
        if not isinstance(d, dict):
            raise SystemExit(f"{anahtar}: '{p}' bir yaprak — alt anahtar eklenemez")
    son = parca[-1]
    if son in d and d[son] != deger and not ustune_yaz:
        raise SystemExit(
            f"{anahtar} ({dil}) zaten FARKLI değerle var: {d[son]!r} — aynı anlamsa var olanı kullanın; değilse yeni anahtar"
        )
    d[son] = deger
    yol.write_bytes(kanonik(veri).encode("utf-8"))


def anahtar_ekle(kok: Path, yuzey: str, anahtar: str, tr: str, en: str, ustune_yaz: bool = False) -> None:
    if ortak.yer_tutuculari(tr) != ortak.yer_tutuculari(en):
        raise SystemExit(
            f"yer tutucu kümesi farklı: tr={sorted(ortak.yer_tutuculari(tr))} en={sorted(ortak.yer_tutuculari(en))}"
        )
    anahtar_yaz(kok, yuzey, "tr", anahtar, tr, ustune_yaz)
    anahtar_yaz(kok, yuzey, "en", anahtar, en, ustune_yaz)


# ── parca-cikar / parca-geri-al ──────────────────────────────────────────────────────────────────────────────


def parca_cikar(kok: Path, yuzey: str, onek: str | None, eksik_en: bool, boyut: int, aday: Path | None) -> list[dict]:
    tr = ortak.duzlestir(ortak.katalog_yukle(yuzey, "tr", kok))
    en = ortak.duzlestir(ortak.katalog_yukle(yuzey, "en", kok))
    baglam: dict[str, str] = {}
    if aday:
        for a in json.loads(Path(aday).read_text(encoding="utf-8")).get("adaylar", []):
            baglam.setdefault(
                a.get("ham") or a.get("metin"),
                f"{a['dosya']}:{a['satir']} · {a.get('tur')} · {a.get('kaynakSatiri', '')[:160]}",
            )
    sonuc = []
    for k in sorted(tr):
        if onek and not k.startswith(onek):
            continue
        if eksik_en and str(en.get(k, "")).strip():
            continue
        sonuc.append({"anahtar": k, "tr": tr[k], "en": en.get(k, ""), "baglam": baglam.get(tr[k], "")})
        if len(sonuc) >= boyut:
            break
    return sonuc


def parca_geri_al(kok: Path, parca: list[dict], yuzey: str) -> tuple[int, list[str]]:
    tr = ortak.duzlestir(ortak.katalog_yukle(yuzey, "tr", kok))
    yazilan, red = 0, []
    for p in parca:
        k, en = p["anahtar"], str(p.get("en") or "")
        if not en.strip():
            continue
        if k not in tr:
            red.append(f"{k}: tr katalogda yok")
            continue
        if ortak.yer_tutuculari(tr[k]) != ortak.yer_tutuculari(en):
            red.append(
                f"{k}: yer tutucu farklı tr={sorted(ortak.yer_tutuculari(tr[k]))} en={sorted(ortak.yer_tutuculari(en))}"
            )
            continue
        anahtar_yaz(kok, yuzey, "en", k, en, ustune_yaz=True)
        yazilan += 1
    return yazilan, red


# ── taban (Türkçe gerilemesi) ────────────────────────────────────────────────────────────────────────────────


def taban_karsilastir(kok: Path, dosyalar: list[str], taban_yolu: Path) -> list[str]:
    taban = json.loads(Path(taban_yolu).read_text(encoding="utf-8"))
    defter_yolu = kok / "i18n" / "kapsam.json"
    defter = json.loads(defter_yolu.read_text(encoding="utf-8")) if defter_yolu.exists() else {"dosyalar": {}}
    tr_degerleri: dict[str, set[str]] = {}
    sorun = []
    hedef = set(dosyalar)
    for m in taban["metinler"]:
        if m["dosya"] not in hedef:
            continue
        y = m["yuzey"]
        if y not in tr_degerleri:
            tr_degerleri[y] = (
                set(ortak.duzlestir(ortak.katalog_yukle(y, "tr", kok)).values()) if y in ortak.KATALOGLAR else set()
            )
        kayit = defter["dosyalar"].get(m["dosya"], {})
        birlesik = {x.get("once") for x in kayit.get("birlesikIstisna", [])}
        ham = m.get("ham") or m["metin"]
        if ham in tr_degerleri[y] or m["metin"] in tr_degerleri[y] or m["metin"] in birlesik:
            continue
        if kapsam.muaf_mi(defter, m["dosya"], m["metin"]):
            continue
        sorun.append(f"{m['dosya']}:{m['satir']} [{m['tur']}] tr katalogda YOK / muaf değil: {ham!r}")
    return sorun


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="I18N katalog aracı")
    ap.add_argument("--kok")
    alt = ap.add_subparsers(dest="komut", required=True)
    b = alt.add_parser("bicimle")
    b.add_argument("--yuzey", nargs="*")
    b.add_argument("--denetle", action="store_true")
    e = alt.add_parser("esle")
    e.add_argument("--yuzey", nargs="*")
    a = alt.add_parser("adalani-ekle")
    a.add_argument("yuzey", choices=["arayuz", "site"])
    a.add_argument("ad")
    k = alt.add_parser("anahtar-ekle")
    k.add_argument("yuzey", choices=list(ortak.KATALOGLAR))
    k.add_argument("anahtar")
    k.add_argument("--tr", required=True)
    k.add_argument("--en", required=True)
    k.add_argument("--ustune-yaz", action="store_true")
    p = alt.add_parser("parca-cikar")
    p.add_argument("yuzey", choices=list(ortak.KATALOGLAR))
    p.add_argument("--onek")
    p.add_argument("--eksik-en", action="store_true")
    p.add_argument("--boyut", type=int, default=150)
    p.add_argument("--aday")
    p.add_argument("--cikti", required=True)
    g = alt.add_parser("parca-geri-al")
    g.add_argument("parca")
    g.add_argument("--yuzey", choices=list(ortak.KATALOGLAR))
    t = alt.add_parser("taban")
    t.add_argument("--grup")
    t.add_argument("--dosya", nargs="*", default=[])
    t.add_argument("--taban", default=str(VARSAYILAN_TABAN))
    a_ = ap.parse_args(argv)
    kok = Path(a_.kok).resolve() if a_.kok else ortak.KOK

    if a_.komut == "bicimle":
        f = bicimle(kok, a_.yuzey, a_.denetle)
        print(("[FARK] " if a_.denetle and f else "") + (", ".join(f) if f else "[OK] kanonik"))
        return 1 if (a_.denetle and f) else 0
    if a_.komut == "esle":
        s = esle(kok, a_.yuzey)
        for x in s:
            print("  ✗", x)
        print(f"{'[SORUN] ' + str(len(s)) if s else '[OK] eşlik tam'}")
        return 1 if s else 0
    if a_.komut == "adalani-ekle":
        adalani_ekle(kok, a_.yuzey, a_.ad)
        print(f"[OK] {a_.yuzey}: {a_.ad} ad alanı (tr + en + kaynaklar.ts)")
        return 0
    if a_.komut == "anahtar-ekle":
        anahtar_ekle(kok, a_.yuzey, a_.anahtar, a_.tr, a_.en, a_.ustune_yaz)
        print(f"[OK] {a_.yuzey}: {a_.anahtar}")
        return 0
    if a_.komut == "parca-cikar":
        r = parca_cikar(kok, a_.yuzey, a_.onek, a_.eksik_en, a_.boyut, Path(a_.aday) if a_.aday else None)
        Path(a_.cikti).write_text(
            json.dumps({"yuzey": a_.yuzey, "parca": r}, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(f"[OK] {len(r)} anahtar → {a_.cikti}")
        return 0
    if a_.komut == "parca-geri-al":
        veri = json.loads(Path(a_.parca).read_text(encoding="utf-8"))
        y = a_.yuzey or veri.get("yuzey")
        n, red = parca_geri_al(kok, veri["parca"] if isinstance(veri, dict) else veri, y)
        for x in red:
            print("  ✗", x)
        print(f"[{'SORUN' if red else 'OK'}] {n} en değeri yazıldı, {len(red)} reddedildi")
        return 1 if red else 0
    if a_.komut == "taban":
        dosyalar = list(a_.dosya)
        if a_.grup:
            defter = json.loads((kok / "i18n" / "kapsam.json").read_text(encoding="utf-8"))
            dosyalar += [d for d, k_ in defter["dosyalar"].items() if k_.get("grup") == a_.grup]
        s = taban_karsilastir(kok, dosyalar, Path(a_.taban))
        for x in s:
            print("  ✗", x)
        print(
            f"{'[GERİLEME] ' + str(len(s)) if s else '[OK] taban TR metinlerinin hepsi katalogda / muaf'} ({len(dosyalar)} dosya)"
        )
        return 1 if s else 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
