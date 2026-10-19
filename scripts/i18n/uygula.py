# -*- coding: utf-8 -*-
"""I18N BASİT DURUM DÖNÜŞTÜRÜCÜSÜ — eşleme dosyasındaki kararları KAYNAĞA ve KATALOĞA uygular.

İş akışı (KURALLAR.md §Parti adımları):
  1) ..\\python.exe scripts\\i18n\\cikar.py --grup <G> --cikti aday.json
  2) ..\\python.exe scripts\\i18n\\uygula.py sablon aday.json --cikti eslem.json
       Her aday için {dosya, satir, sutun, metin, ham, tur, baglam, anahtar (öneri), karar: "cevir", en: ""}. Oturum DÜZENLER:
       anahtarı adlandırma kuralına çevirir, kullanıcıya görünmeyen adayı `"karar": "muaf", "gerekce": "…"` yapar, isterse `en` doldurur.
  3) ..\\python.exe scripts\\i18n\\uygula.py uygula eslem.json [--kuru]
       · TS / TSX: `uygula_ts.cjs` (jsx metni, görünür öznitelik, bileşen içi dizgi / şablon; `t` yoksa `useTranslation` eklenir).
       · Python (sunucu): dizgi → `ceviri.t("anahtar")`, f-string → `ceviri.t("anahtar", ad=ifade)` (biçim belirteçli / `.format` / `%` /
         modül düzeyi REDDEDİLİR); `from utils import ceviri` yoksa eklenir.
       · Katalog: tr = aracın `ham` değeri (BAYT BAYT — elle yazılmaz), en = eşlemedeki `en` (boşsa yazılmaz → `katalog.py parca-cikar
         --eksik-en` bulur). Aynı anahtar farklı TR ile → RED (aynı anlam = aynı anahtar; farklı anlam = farklı anahtar).
       · `muaf` kararları `i18n/kapsam.json` → dosyanın `muaf` listesine (metin + gerekçe).
       Reddedilenler raporlanır → ELLE (KURALLAR.md örnekleri). `--kuru`: hiçbir şey yazmaz, yalnız rapor.
Diğer yüzeyler (Rust / HTML / NSIS / site işlevleri) bu araçla DÖNÜŞTÜRÜLMEZ — elle (KURALLAR.md §Launcher, §Site).
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.i18n import cikar, katalog, ortak  # noqa: E402

UYGULA_TS = Path(__file__).resolve().parent / "uygula_ts.cjs"
ANAHTAR = re.compile(r"[a-z][A-Za-z0-9]*(\.[A-Za-z0-9_]+)+")
#: `ceviri.t(anahtar, dil=None, **p)` — bu adlarda yer tutucu parametreyle çakışır (TypeError / dil seçimi bozulur).
YASAK_YER_TUTUCU = {"anahtar", "dil"}


def sablon(aday: dict) -> dict:
    islemler = []
    for a in aday.get("adaylar", []):
        islemler.append(
            {
                "dosya": a["dosya"],
                "satir": a["satir"],
                "sutun": a["sutun"],
                "metin": a["metin"],
                "ham": a.get("ham", a["metin"]),
                "tur": a.get("tur"),
                "baglam": a.get("baglam", ""),
                "birlesik": a.get("birlesik", False),
                "modulDuzeyi": a.get("modulDuzeyi", False),
                "kaynakSatiri": a.get("kaynakSatiri", ""),
                "anahtar": a.get("oneri", ""),
                "karar": "cevir",
                "en": "",
            }
        )
    return {
        "aciklama": "uygula.py eşleme dosyası — karar: cevir | muaf (+ gerekce); anahtar KURALLAR.md adlandırması",
        "islemler": islemler,
    }


# ── Python ───────────────────────────────────────────────────────────────────────────────────────────────────


def _bayt_konumu(satir_baslari: list[int], satir: int, sutun_bayt: int) -> int:
    return satir_baslari[satir - 1] + sutun_bayt


def py_uygula(dosya: str, metin: str, islemler: list[dict]) -> tuple[str, list[dict], list[dict]]:
    agac = ast.parse(metin)
    adaylar, _ = cikar.py_adaylari(dosya, metin)
    kodlu = metin.encode("utf-8")
    satir_baslari = [0]
    for i, b in enumerate(kodlu):
        if b == 0x0A:
            satir_baslari.append(i + 1)
    dugumler = {}
    for n in ast.walk(agac):
        # Python 3.10: f-string'in iç Constant parçaları f-string'in KENDİ konumunu taşır (ölçüldü) — ast.walk üstü önce verir,
        # setdefault dıştaki JoinedStr'ı korur (üzerine yazılsaydı f-string "birleştirme" diye reddedilirdi).
        if isinstance(n, (ast.Constant, ast.JoinedStr)) and hasattr(n, "end_lineno"):
            dugumler.setdefault((n.lineno, n.col_offset + 1), n)
    duzen, uygulanan, red = [], [], []
    for is_ in islemler:
        a = next(
            (
                x
                for x in adaylar
                if x["satir"] == is_["satir"] and x["sutun"] == is_["sutun"] and x["metin"] == is_["metin"]
            ),
            None,
        )
        n = dugumler.get((is_["satir"], is_["sutun"]))
        if not a or n is None:
            red.append({**is_, "neden": "aday / düğüm bulunamadı (cikar'ı yeniden koşun)"})
            continue
        if not ANAHTAR.fullmatch(is_.get("anahtar") or ""):
            red.append(
                {**is_, "neden": "anahtar biçimi geçersiz (ASCII camelCase, noktalı; ör. hasta.hata.bulunamadi)"}
            )
            continue
        if a.get("modulDuzeyi"):
            red.append({**is_, "neden": "modül düzeyi — içe aktarmada dil donar; işlev / anahtar saklama ile elle"})
            continue
        if a.get("birlesik") and not isinstance(n, ast.JoinedStr):
            red.append({**is_, "neden": "birleştirme / .format / % — elle tek anahtar + yer tutucu"})
            continue
        if isinstance(n, ast.JoinedStr):
            argumanlar, sira = [], 0
            ok = True
            for v in n.values:
                if isinstance(v, ast.FormattedValue):
                    sira += 1
                    if v.format_spec is not None or v.conversion != -1:
                        ok = False
                        break
                    ad = a["yertutucular"][sira - 1]
                    ad = (is_.get("yerAdlari") or {}).get(ad, ad)
                    argumanlar.append(f"{ad}={ast.get_source_segment(metin, v.value)}")
            if not ok:
                red.append({**is_, "neden": "f-string biçim belirteci ({x:.1f} / !r) — değeri önce biçimleyip elle"})
                continue
            adlar = is_.get("yerAdlari") or {}
            cakisan = YASAK_YER_TUTUCU & {
                adlar.get(x, x) for x in a["yertutucular"]
            }  # yeniden adlandırma çakışmayı çözebilir
            if cakisan:
                red.append(
                    {
                        **is_,
                        "neden": f"yer tutucu adı {sorted(cakisan)} ceviri.t parametresiyle çakışır — elle başka adla",
                    }
                )
                continue
            yeni = f'ceviri.t("{is_["anahtar"]}"' + ("".join(", " + x for x in argumanlar)) + ")"
        else:
            yeni = f'ceviri.t("{is_["anahtar"]}")'
        bas = _bayt_konumu(satir_baslari, n.lineno, n.col_offset)
        son = _bayt_konumu(satir_baslari, n.end_lineno, n.end_col_offset)
        duzen.append((bas, son, yeni.encode("utf-8")))
        uygulanan.append({**is_, "ham": a["ham"]})
    ss = b"\r\n" if b"\r\n" in kodlu else b"\n"  # eklenen satır dosyanın satır sonunu izler (karışık satır sonu yok)
    if duzen and not any(
        isinstance(s, ast.ImportFrom) and s.module == "utils" and any(al.name == "ceviri" for al in s.names)
        for s in agac.body
    ):
        ithal = [s for s in agac.body if isinstance(s, (ast.Import, ast.ImportFrom))]
        if ithal:
            son = ithal[-1]
            konum = _bayt_konumu(satir_baslari, son.end_lineno, son.end_col_offset)
            duzen.append((konum, konum, ss + b"from utils import ceviri"))
        else:
            duzen.append((0, 0, b"from utils import ceviri" + ss))
    for bas, son, yeni in sorted(duzen, key=lambda x: (-x[0], -x[1])):
        kodlu = kodlu[:bas] + yeni + kodlu[son:]
    return kodlu.decode("utf-8"), uygulanan, red


# ── TS / TSX ─────────────────────────────────────────────────────────────────────────────────────────────────


def ts_uygula(kok: Path, dosya: str, metin: str, islemler: list[dict]) -> tuple[str, list[dict], list[dict]]:
    girdi = {
        "dosya": dosya,
        "metin": metin,
        "islemler": [
            {k: i[k] for k in ("satir", "sutun", "metin", "anahtar", "yerAdlari") if k in i} for i in islemler
        ],
    }
    r = subprocess.run(["node", str(UYGULA_TS)], input=json.dumps(girdi).encode("utf-8"), capture_output=True, cwd=kok)
    if r.returncode != 0:
        raise RuntimeError(f"uygula_ts.cjs düştü: {r.stderr.decode('utf-8', 'replace')[:2000]}")
    cikti = json.loads(r.stdout.decode("utf-8"))
    eslem = {(i["satir"], i["sutun"], i["metin"]): i for i in islemler}
    uyg = [{**eslem[(u["satir"], u["sutun"], u["metin"])], "ham": u["ham"]} for u in cikti["uygulanan"]]
    red = [{**eslem[(x["satir"], x["sutun"], x["metin"])], "neden": x["neden"]} for x in cikti["reddedilen"]]
    return cikti["metin"], uyg, red


# ── Orkestra ─────────────────────────────────────────────────────────────────────────────────────────────────


def _katalog_yaz(kok: Path, yuzey: str, u: dict) -> None:
    """TR = aracın ham değeri (BAYT BAYT), `yerAdlari` ile yeniden adlandırılmış. `cogul: true` → `_one` + `_other` (TR ikisi de aynı
    — Türkçe tekil/çoğul ayırmaz; EN `{"one": …, "other": …}`), çağrı `t(k, { count })` ile seçer (yer tutucu adı `count` olmalı)."""
    tr = u["ham"]
    for eski, yeni in (u.get("yerAdlari") or {}).items():
        tr = tr.replace("{{" + eski + "}}", "{{" + yeni + "}}")
    if u.get("cogul"):
        if "count" not in ortak.yer_tutuculari(tr):
            raise SystemExit("cogul: TR değerinde {{count}} yok (yerAdlari ile sayıyı 'count' adlandırın)")
        en = u.get("en") or {}
        if en and not (isinstance(en, dict) and set(en) == {"one", "other"}):
            raise SystemExit('cogul: en {"one": "…", "other": "…"} olmalı')
        for bicim in ("one", "other"):
            katalog.anahtar_yaz(kok, yuzey, "tr", f"{u['anahtar']}_{bicim}", tr)
            if en:
                if ortak.yer_tutuculari(tr) != ortak.yer_tutuculari(en[bicim]):
                    raise SystemExit(f"en yer tutucuları tr ile farklı: {u['anahtar']}_{bicim}")
                katalog.anahtar_yaz(kok, yuzey, "en", f"{u['anahtar']}_{bicim}", en[bicim], ustune_yaz=True)
        return
    katalog.anahtar_yaz(kok, yuzey, "tr", u["anahtar"], tr)
    if str(u.get("en") or "").strip():
        if ortak.yer_tutuculari(tr) != ortak.yer_tutuculari(u["en"]):
            raise SystemExit(f"en yer tutucuları tr ile farklı: {u['anahtar']}")
        katalog.anahtar_yaz(kok, yuzey, "en", u["anahtar"], u["en"], ustune_yaz=True)


def uygula(kok: Path, eslem: dict, kuru: bool = False) -> dict:
    gruplar: dict[str, list[dict]] = {}
    muaflar: list[dict] = []
    for is_ in eslem["islemler"]:
        if is_.get("karar") == "muaf":
            if not str(is_.get("gerekce", "")).strip():
                raise SystemExit(f"muaf kararı gerekçesiz: {is_['dosya']}:{is_['satir']} {is_['metin']!r}")
            muaflar.append(is_)
        elif is_.get("karar") == "cevir":
            gruplar.setdefault(is_["dosya"], []).append(is_)
    rapor = {"uygulanan": [], "reddedilen": [], "muaf": len(muaflar), "katalogHatasi": []}
    for dosya, islemler in gruplar.items():
        p = kok / dosya
        metin = p.read_bytes().decode("utf-8")
        if dosya.endswith(".py"):
            yeni, uyg, red = py_uygula(dosya, metin, islemler)
        elif dosya.endswith((".ts", ".tsx")):
            yeni, uyg, red = ts_uygula(kok, dosya, metin, islemler)
        else:
            rapor["reddedilen"] += [
                {**i, "neden": "bu dosya türü elle dönüştürülür (Rust / HTML / NSIS)"} for i in islemler
            ]
            continue
        yuzey = ortak.dosyanin_yuzeyi(dosya)
        for u in uyg:
            try:
                if not kuru:
                    _katalog_yaz(kok, yuzey, u)
            except SystemExit as e:
                rapor["katalogHatasi"].append(f"{dosya}:{u['satir']} {u['anahtar']}: {e}")
        if not kuru and uyg and not rapor["katalogHatasi"]:
            p.write_bytes(yeni.encode("utf-8"))
        rapor["uygulanan"] += uyg
        rapor["reddedilen"] += red
    if muaflar and not kuru:
        dp = kok / "i18n" / "kapsam.json"
        defter = json.loads(dp.read_text(encoding="utf-8"))
        for m in muaflar:
            kayit = defter["dosyalar"].setdefault(m["dosya"], {})
            liste = kayit.setdefault("muaf", [])
            if not any(x.get("metin") == m["metin"] for x in liste):
                liste.append({"metin": m["metin"], "gerekce": m["gerekce"]})
        dp.write_text(json.dumps(defter, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    return rapor


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="I18N basit durum dönüştürücüsü")
    ap.add_argument("--kok")
    alt = ap.add_subparsers(dest="komut", required=True)
    s = alt.add_parser("sablon")
    s.add_argument("aday")
    s.add_argument("--cikti", required=True)
    u = alt.add_parser("uygula")
    u.add_argument("eslem")
    u.add_argument("--kuru", action="store_true")
    u.add_argument("--rapor")
    a = ap.parse_args(argv)
    kok = Path(a.kok).resolve() if a.kok else ortak.KOK
    if a.komut == "sablon":
        e = sablon(json.loads(Path(a.aday).read_text(encoding="utf-8")))
        Path(a.cikti).write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[OK] {len(e['islemler'])} işlem → {a.cikti} (anahtarları ve muaf kararlarını düzenleyin)")
        return 0
    r = uygula(kok, json.loads(Path(a.eslem).read_text(encoding="utf-8")), kuru=a.kuru)
    if a.rapor:
        Path(a.rapor).write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print(
        f"uygulanan {len(r['uygulanan'])} · reddedilen (ELLE) {len(r['reddedilen'])} · muaf {r['muaf']} · katalog hatası {len(r['katalogHatasi'])}"
    )
    for x in r["reddedilen"][:60]:
        print(f"  ELLE {x['dosya']}:{x['satir']} [{x.get('tur')}] {x['metin'][:70]!r} — {x['neden']}")
    for x in r["katalogHatasi"]:
        print("  ✗", x)
    return 1 if r["katalogHatasi"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
