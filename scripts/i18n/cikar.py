# -*- coding: utf-8 -*-
"""I18N ADAY METİN ÇIKARIMI — bütün yüzeyler (arayüz · sunucu · launcher · site · DEMA).

Kullanım (depo kökünden; gömülü Python):
    ..\\python.exe scripts\\i18n\\cikar.py --yuzey arayuz --cikti aday.json          # bir yüzey
    ..\\python.exe scripts\\i18n\\cikar.py --grup arayuz-01-ortak --cikti aday.json  # kapsam defterindeki bir grup
    ..\\python.exe scripts\\i18n\\cikar.py --dosya apps/ui/src/screens/AuthScreen.tsx  # tek / birkaç dosya (stdout)
    ..\\python.exe scripts\\i18n\\cikar.py --yuzey hepsi --ozet                       # sayım tablosu
    ..\\python.exe scripts\\i18n\\cikar.py --yuzey hepsi --taban --cikti taban-tr-metinler.json   # göç öncesi TR tabanı
    ..\\python.exe scripts\\i18n\\cikar.py --yuzey hepsi --olcum --cikti olcum.json   # ön ölçüm (karşılaştırma, upper/lower …)

Aday kaydı: {yuzey, dosya, satir, sutun, metin (tek satır), ham (ekrandaki birebir), tur, baglam, oneri, yertutucular,
birlesik, modulDuzeyi, bilesen, tVar, kaynakSatiri}. `tur`:
  · TS/TSX: jsx-metin · oznitelik · oznitelik? (görünürlüğü bilinmeyen öznitelik) · ileti (Alert/toast/onay) · hata (new Error /
    throw) · nesne (nesne değeri; baglam = anahtar) · sabit (değişken ilk değeri) · sablon · sablon-parcasi · cagri · donus · dizi ·
    atama · varsayilan · jsx-ifade · dizgi
  · Python: detail (HTTPException / JSONResponse) · sozluk (kullanıcıya dönen sözlük değeri) · bildirim · istisna · pdf · dizgi
  · Rust: hata (#[error]) · rust · rust-sablon (format!) · HTML: html-metin · html-oznitelik (+ <script> içi TS türleri) · NSIS: nsis
Dışlanan (aday DEĞİL): günlük iletileri (logger / console / log_line / eprintln), docstring / yorum, import, tür, nesne ANAHTARI,
karşılaştırma değerleri (=== / in / startswith …), testID / style / href gibi kod öznitelikleri, Rust `#[cfg(test)]` modülleri.
⚠️ Muaf kararı ARACIN değil oturumun işidir: aday kullanıcıya görünmüyorsa `i18n/kapsam.json` muaf listesine GEREKÇEYLE yazılır.
"""

from __future__ import annotations

import argparse
import ast
import html.parser
import json
import re
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.i18n import ortak  # noqa: E402

CIKAR_TS = Path(__file__).resolve().parent / "cikar_ts.cjs"
TS_PARCA = 80  # node çağrısı başına dosya


# ── TS / TSX / JS (node + TypeScript derleyici API'si) ─────────────────────────────────────────────────────────


def ts_adaylari(girdiler: list[dict], kok: Path, olcum: bool = False) -> dict:
    """girdiler: [{"yol": mutlak} | {"ad", "metin", "satirOtele", "uzanti", "adAlani"}] → {adaylar, olcum, hatalar}."""
    tum = {"adaylar": [], "olcum": {}, "hatalar": []}
    for i in range(0, len(girdiler), TS_PARCA):
        parca = girdiler[i : i + TS_PARCA]
        arg = ["node", str(CIKAR_TS), "--stdin"] + (["--olcum"] if olcum else [])
        r = subprocess.run(arg, input=json.dumps(parca).encode("utf-8"), capture_output=True, cwd=kok)
        if r.returncode != 0:
            raise RuntimeError(f"cikar_ts.cjs düştü (rc={r.returncode}): {r.stderr.decode('utf-8', 'replace')[:2000]}")
        veri = json.loads(r.stdout.decode("utf-8"))
        tum["adaylar"] += veri["adaylar"]
        tum["hatalar"] += veri.get("hatalar", [])
        for k, v in (veri.get("olcum") or {}).items():
            tum["olcum"].setdefault(k, []).extend(v)
    return tum


# ── Python (ast) ───────────────────────────────────────────────────────────────────────────────────────────────

_GUNLUK_YONTEM = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log", "fatal"}
_GUNLUK_NESNE = re.compile(r"(^|_)(log|logger|logging|log_|_log|gunluk|kayitci)$|^logger_?\w*$|^LOG$|^_?logger$", re.I)
_KOD_YONTEMI = {
    "startswith",
    "endswith",
    "split",
    "rsplit",
    "replace",
    "strip",
    "lstrip",
    "rstrip",
    "get",
    "pop",
    "setdefault",
    "index",
    "find",
    "rfind",
    "count",
    "join",
    "encode",
    "decode",
    "match",
    "fullmatch",
    "search",
    "sub",
    "subn",
    "compile",
    "findall",
    "finditer",
    "getenv",
    "environ",
    "execute",
    "executemany",
    "executescript",
    "getattr",
    "hasattr",
    "setattr",
    "Path",
    "open",
    "glob",
    "rglob",
    "exists",
    "with_suffix",
    "joinpath",
    "headers",
    "cookies",
    "query_params",
    "add_api_route",
    "include_router",
    "APIRouter",
    "Depends",
    "Header",
    "Query",
    "Field",
    "Form",
    "File",
    "BaseModel",
    "removeprefix",
    "removesuffix",
    "partition",
    "rpartition",
    "translate",
    "maketrans",
    "zfill",
    "ljust",
    "rjust",
    "center",
    "lower",
    "upper",
    "casefold",
    "isoformat",
    "strftime",
    "strptime",
    "fromisoformat",
    "loads",
    "dumps",
    "load",
    "dump",
    "connect",
    "subscribe",
    "publish",
    "unsubscribe",
    "send_text",
    "register",
    "getLogger",
    "add_middleware",
    "mount",
    "on_event",
    "middleware",
    "websocket",
    "get_or_create",
    "registerFont",
    "registerFontFamily",
    "TTFont",
    "ParagraphStyle",
    "TableStyle",
    "HexColor",
    "send",
    "write_text",
    "read_text",
    "communicate",
    "Popen",
    "run",
    "check_output",
    "check_call",
    "call",
    "lookup",
    "getpreferredencoding",
    "strptime",
}
_KULLANICI_ANAHTARI = {
    "detail",
    "message",
    "mesaj",
    "hata",
    "uyari",
    "aciklama",
    "baslik",
    "title",
    "label",
    "text",
    "metin",
    "error",
    "neden",
    "eylem",
    "oneri",
    "bilgi",
    "not",
    "ozet",
    "durum_metni",
    "kullanici_mesaji",
    "uyarı",
}
_KULLANICI_KWARG = _KULLANICI_ANAHTARI | {"status_text", "description_tr"}
_SQL = re.compile(
    r"^\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|PRAGMA|WITH|BEGIN|COMMIT)\b|\b\w+\s*(=|<|>|<=|>=|LIKE)\s*\?|"
    r"\b(WHERE|FROM|VALUES|ORDER BY|GROUP BY|LEFT JOIN|INNER JOIN)\b"
)
#: Düzenli ifade deseni gibi görünen dizgi (boşluksuz + regex meta dizisi) — kod.
_REGEX_GIBI = re.compile(r"\\[dwsbDWSBp]|\(\?[:=!<P]|\[[^\]]+\][?*+]|^\^|[^\\]\$$|\|\w+\|")


def _ebeveynler(agac: ast.AST) -> dict:
    eb = {}
    for n in ast.walk(agac):
        for c in ast.iter_child_nodes(n):
            eb[c] = n
    return eb


def _docstring_dugumleri(agac: ast.AST) -> set:
    ds = set()
    for n in ast.walk(agac):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body:
            ilk = n.body[0]
            if isinstance(ilk, ast.Expr) and isinstance(ilk.value, ast.Constant) and isinstance(ilk.value.value, str):
                ds.add(ilk.value)
    return ds


def _cagri_adi(f: ast.AST) -> str:
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        sol = _cagri_adi(f.value)
        return f"{sol}.{f.attr}" if sol else f.attr
    if isinstance(f, ast.Call):
        return _cagri_adi(f.func)
    if isinstance(f, ast.Subscript):
        return _cagri_adi(f.value)
    return ""


_GUNLUK_ISLEV = re.compile(r"(^|_)(log|logla|gunluk|gunluge)(_|$)|^_?log[a-z_]*$|_log$", re.I)


def _gunluk_cagrisi_mi(c: ast.Call) -> bool:
    ad = _cagri_adi(c.func)
    if ad in ("print", "warnings.warn", "traceback.print_exc"):
        return True
    if _GUNLUK_ISLEV.search(ad.split(".")[-1]):  # self._log_info(...), log_line(...), _gunluk(...)
        return True
    parca = ad.split(".")
    if len(parca) >= 2 and parca[-1] in _GUNLUK_YONTEM:
        nesne = parca[-2]
        if (
            _GUNLUK_NESNE.search(nesne)
            or nesne in ("logging", "self.logger", "logger", "log", "_log", "LOG")
            or "log" in nesne.lower()
        ):
            return True
    if len(parca) >= 3 and parca[-1] in _GUNLUK_YONTEM and "log" in parca[-3].lower():
        return True
    return False


def _yt_adi(e: ast.AST, sira: int) -> str:
    if isinstance(e, ast.Name):
        return e.id
    if isinstance(e, ast.Attribute):
        return e.attr
    return f"deger{sira}"


def _fstring_metni(js: ast.JoinedStr) -> tuple[str, list[str]]:
    s, yt, sira = "", [], 0
    for v in js.values:
        if isinstance(v, ast.Constant):
            s += str(v.value)
        elif isinstance(v, ast.FormattedValue):
            sira += 1
            ad = _yt_adi(v.value, sira)
            while ad in yt:
                ad = f"{ad}{sira}"
            yt.append(ad)
            s += "{{" + ad + "}}"
    return s, yt


def _bicim_yer_tutuculari(s: str) -> tuple[str, list[str]]:
    """'Bobin {} durdu' / '%s' / '{ad}' → {{degerN}} / {{ad}}."""
    yt: list[str] = []
    sayac = [0]

    def ad_ver(m):
        sayac[0] += 1
        ic = m.group(1) if m.lastindex else ""
        ad = ic.split(":")[0].split("!")[0].strip() if ic else ""
        ad = ad if re.fullmatch(r"[A-Za-z_]\w*", ad or "") else f"deger{sayac[0]}"
        yt.append(ad)
        return "{{" + ad + "}}"

    s2 = re.sub(r"(?<!\{)\{([^{}]*)\}(?!\})", ad_ver, s)
    s2 = re.sub(r"%(?:\([A-Za-z_]\w*\))?[-+ #0]*\d*(?:\.\d+)?[sdifr]", lambda m: ad_ver(re.match(r"(.*)", "")), s2)
    return s2, yt


def py_adaylari(yol: str, metin: str) -> tuple[list[dict], list[dict]]:
    try:
        agac = ast.parse(metin)
    except SyntaxError as e:
        return [], [{"dosya": yol, "hata": f"SyntaxError: {e}"}]
    eb = _ebeveynler(agac)
    ds = _docstring_dugumleri(agac)
    satirlar = metin.splitlines()
    adaylar: list[dict] = []
    islenen: set = set()
    ns = Path(yol).stem

    def kapsam(n):
        x = eb.get(n)
        islev = None
        while x is not None:
            if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and islev is None:
                islev = x.name
            x = eb.get(x)
        return islev

    def sinif(n) -> tuple[str, str] | None:
        """None = kesin kod / günlük. Aksi hâlde (tür, bağlam)."""
        c, p = n, eb.get(n)
        while p is not None and isinstance(p, (ast.BinOp, ast.IfExp, ast.BoolOp, ast.JoinedStr, ast.FormattedValue)):
            if isinstance(p, ast.IfExp) and c is p.test:
                return None
            c, p = p, eb.get(p)
        if p is None:
            return ("dizgi", "")
        if isinstance(p, ast.Expr):
            return None  # docstring / çıplak ifade
        if isinstance(p, ast.Dict):
            if c in p.keys:
                return None
            idx = p.values.index(c) if c in p.values else -1
            k = p.keys[idx] if idx >= 0 else None
            ka = k.value if isinstance(k, ast.Constant) and isinstance(k.value, str) else ""
            if ka in ("detail",):
                return ("detail", ka)
            if ka in _KULLANICI_ANAHTARI:
                return ("sozluk", ka)
            return ("sozluk?", ka)
        if isinstance(p, ast.Subscript):
            return None
        if isinstance(p, ast.Compare):
            return None
        if isinstance(p, (ast.Assert,)):
            return None
        if isinstance(p, ast.keyword):
            cagri = eb.get(p)
            ad = _cagri_adi(cagri.func) if isinstance(cagri, ast.Call) else ""
            if isinstance(cagri, ast.Call) and _gunluk_cagrisi_mi(cagri):
                return None
            if p.arg == "detail":
                return ("detail", ad)
            if p.arg in _KULLANICI_KWARG:
                return ("sozluk", f"{ad}({p.arg}=)")
            if p.arg in (
                "description",
                "summary",
                "tags",
                "alias",
                "pattern",
                "regex",
                "media_type",
                "encoding",
                "mode",
                "sep",
                "prefix",
                "suffix",
                "dir",
                "fmt",
                "datefmt",
                "format",
                "name",
                "key",
                "path",
                "url",
                "method",
                "help",
                "metavar",
                "dest",
                "thread_name_prefix",
                "ad",
            ):
                return None
            return ("dizgi", f"{ad}({p.arg}=)")
        if isinstance(p, ast.Call):
            if _gunluk_cagrisi_mi(p):
                return None
            ad = _cagri_adi(p.func)
            son = ad.split(".")[-1]
            if son in _KOD_YONTEMI or ad in _KOD_YONTEMI:
                return None
            if son == "HTTPException":
                return ("detail", ad)
            if son in ("_push_notification", "push_notification", "_bildirim", "bildirim_ekle"):
                return ("bildirim", ad)
            if son in (
                "Paragraph",
                "Table",
                "drawString",
                "drawCentredString",
                "drawRightString",
                "setTitle",
                "setSubject",
            ):
                return ("pdf", ad)
            if son.endswith("Error") or son.endswith("Exception") or son in ("ModelKurulumEksik",):
                return ("istisna", ad)
            if son == "format" and isinstance(p.func, ast.Attribute) and p.func.value is c:
                return ("dizgi", "str.format")
            return ("cagri", ad)
        if isinstance(p, ast.Raise):
            return ("istisna", "raise")
        if isinstance(p, (ast.Assign, ast.AnnAssign)):
            hedef = p.targets[0] if isinstance(p, ast.Assign) else p.target
            ad = ast.unparse(hedef)[:60] if hasattr(ast, "unparse") else ""
            return ("sabit", ad)
        if isinstance(p, ast.Return):
            return ("donus", "")
        if isinstance(p, (ast.List, ast.Tuple, ast.Set)):
            return ("dizi", "")
        return ("dizgi", type(p).__name__)

    def ekle(n, m, tur, baglam, yt, birlesik):
        satir = getattr(n, "lineno", 0)
        adaylar.append(
            {
                "dosya": yol,
                "satir": satir,
                "sutun": getattr(n, "col_offset", 0) + 1,
                "metin": ortak.tek_satir(m),
                "ham": m,
                "tur": tur,
                "baglam": baglam,
                "oneri": f"{ns}.{ortak.anahtar_parcasi(m)}",
                "yertutucular": yt,
                "birlesik": birlesik,
                "modulDuzeyi": kapsam(n) is None,
                "islev": kapsam(n),
                "kaynakSatiri": ortak.tek_satir(satirlar[satir - 1])[:200] if 0 < satir <= len(satirlar) else "",
            }
        )

    for n in ast.walk(agac):
        if n in islenen:
            continue
        if isinstance(n, ast.JoinedStr):
            for alt in ast.walk(n):
                islenen.add(alt)
            m, yt = _fstring_metni(n)
            sade = ortak.YER_TUTUCU.sub(" ", m)
            s = sinif(n)
            if s and (ortak.dogal_mi(sade) or (ortak.TR_HARF.search(sade) is not None)) and not _SQL.search(m):
                ekle(n, m, s[0], s[1], yt, True)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            if n in ds:
                continue
            m = n.value
            if not ortak.dogal_mi(m) or _SQL.search(m) or (" " not in m.strip() and _REGEX_GIBI.search(m)):
                continue
            s = sinif(n)
            if not s:
                continue
            yt: list[str] = []
            birlesik = False
            p = eb.get(n)
            if isinstance(p, ast.Attribute) and p.attr == "format":
                m, yt = _bicim_yer_tutuculari(m)
                birlesik = True
            elif isinstance(p, ast.BinOp) and isinstance(p.op, (ast.Add, ast.Mod)):
                birlesik = True
                if isinstance(p.op, ast.Mod):
                    m, yt = _bicim_yer_tutuculari(m)
            ekle(n, m, s[0], s[1], yt, birlesik)
    adaylar.sort(key=lambda a: (a["satir"], a["sutun"]))
    return adaylar, []


# ── Rust (düzenli ifade; yorumlar ve #[cfg(test)] modülleri soyulur) ──────────────────────────────────────────

_RUST_GUNLUK = re.compile(
    r"(?:\beprintln!|\bprintln!|\beprint!|\bprint!|\blog::\w+!|(?<![\w])(?:debug|info|warn|error|trace)!|\blog_line|\blogla|\bgunluk|"
    r"\bkayit_yaz|\bdbg!|\.log|\blog_satiri|\byaz_log|\blog_yaz|\bpanic!|\bunreachable!|\bassert\w*!|\.expect|\btodo!|\bunimplemented!)"
    r"\s*\(\s*(?:&\s*)?(?:format!\s*\(\s*)?$"
    r"|\bwriteln!\s*\(\s*\w*(?:log|gunluk)\w*\s*,\s*$"
)


def _rust_soy(metin: str) -> tuple[str, list[tuple[int, int, str, bool]]]:
    """Yorumları boşlukla değiştirir; dizgi değişmezlerini (bas, son, içerik, ham_mi) döker. Uzunluk korunur (satır numarası için)."""
    out = list(metin)
    dizgiler = []
    i, n = 0, len(metin)
    while i < n:
        c = metin[i]
        if metin.startswith("//", i):
            j = metin.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                out[k] = " "
            i = j
        elif metin.startswith("/*", i):
            j = metin.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
        elif (
            c == "r"
            and re.match(r'r#*"', metin[i:])
            and (i == 0 or not (metin[i - 1].isalnum() or metin[i - 1] == "_"))
        ):
            m = re.match(r'r(#*)"', metin[i:])
            kapanis = '"' + m.group(1)
            bas = i + len(m.group(0))
            j = metin.find(kapanis, bas)
            j = n if j < 0 else j
            dizgiler.append((i, j + len(kapanis), metin[bas:j], True))
            i = j + len(kapanis)
        elif c == '"' and not (i > 0 and metin[i - 1] == "'" and i + 1 < n and metin[i + 1] == "'"):
            j = i + 1
            while j < n and metin[j] != '"':
                j += 2 if metin[j] == "\\" else 1
            dizgiler.append((i, j + 1, metin[i + 1 : j], False))
            i = j + 1
        elif (
            c == "'"
            and i + 2 < n
            and (metin[i + 2] == "'" or (metin[i + 1] == "\\" and metin.find("'", i + 2) - i <= 10))
        ):
            j = metin.find("'", i + 2 if metin[i + 1] != "\\" else i + 3)
            i = (j + 1) if j > 0 else i + 1
        else:
            i += 1
    return "".join(out), dizgiler


def _rust_kacis_coz(s: str) -> str:
    def rep(m):
        e = m.group(1)
        return {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "0": "\0", "'": "'"}.get(e, m.group(0))

    s = re.sub(r"\\\n\s*", "", s)  # satır devamı
    s = re.sub(r"\\u\{([0-9a-fA-F]+)\}", lambda m: chr(int(m.group(1), 16)), s)
    return re.sub(r"\\(.)", rep, s)


def _rust_test_bolgeleri(soyulmus: str) -> list[tuple[int, int]]:
    bolgeler = []
    for m in re.finditer(r"#\[cfg\(test\)\]\s*(pub\s+)?mod\s+\w+\s*\{", soyulmus):
        derinlik, j = 1, m.end()
        while j < len(soyulmus) and derinlik:
            if soyulmus[j] == "{":
                derinlik += 1
            elif soyulmus[j] == "}":
                derinlik -= 1
            j += 1
        bolgeler.append((m.start(), j))
    for m in re.finditer(r"#\[test\]\s*(#\[[^\]]*\]\s*)*fn\s+\w+[^{]*\{", soyulmus):
        derinlik, j = 1, m.end()
        while j < len(soyulmus) and derinlik:
            if soyulmus[j] == "{":
                derinlik += 1
            elif soyulmus[j] == "}":
                derinlik -= 1
            j += 1
        bolgeler.append((m.start(), j))
    return bolgeler


def rust_adaylari(yol: str, metin: str) -> list[dict]:
    soyulmus, dizgiler = _rust_soy(metin)
    testler = _rust_test_bolgeleri(soyulmus)
    satir_bas = [0] + [m.end() for m in re.finditer("\n", metin)]
    ns = Path(yol).stem
    adaylar = []
    import bisect

    for bas, son, icerik, ham_mi in dizgiler:
        if any(a <= bas < b for a, b in testler):
            continue
        deger = icerik if ham_mi else _rust_kacis_coz(icerik)
        satir_no = bisect.bisect_right(satir_bas, bas)
        onceki = soyulmus[max(0, bas - 120) : bas]
        onceki_satir = onceki.split("\n")[-1] if "\n" in onceki else onceki
        if _RUST_GUNLUK.search(onceki.rstrip().split(";")[-1]) or _RUST_GUNLUK.search(onceki_satir):
            continue
        yt: list[str] = []
        sablon = bool(
            re.search(r"format!\s*\(\s*$|write!\s*\([^,]*,\s*$|writeln!\s*\([^,]*,\s*$|#\[error\(\s*$", onceki)
        )
        m = deger
        if sablon or re.search(r"\{[A-Za-z_0-9:?.]*\}", deger):
            sayac = [0]

            def ad_ver(mm):
                sayac[0] += 1
                ic = mm.group(1).split(":")[0]
                ad = ic if re.fullmatch(r"[A-Za-z_]\w*", ic or "") else f"deger{sayac[0]}"
                yt.append(ad)
                return "{{" + ad + "}}"

            m = re.sub(r"(?<!\{)\{([A-Za-z_0-9.:?]*)\}(?!\})", ad_ver, deger).replace("{{{{", "{").replace("}}}}", "}")
        sade = ortak.YER_TUTUCU.sub(" ", m)
        if not (ortak.dogal_mi(sade) or (yt and ortak.TR_HARF.search(sade))):
            continue
        tur = "hata" if re.search(r"#\[error\(\s*$", onceki) else ("rust-sablon" if yt else "rust")
        adaylar.append(
            {
                "dosya": yol,
                "satir": satir_no,
                "sutun": bas - satir_bas[satir_no - 1] + 1,
                "metin": ortak.tek_satir(m),
                "ham": m,
                "tur": tur,
                "baglam": ortak.tek_satir(onceki_satir)[-60:],
                "oneri": f"{ns}.{ortak.anahtar_parcasi(m)}",
                "yertutucular": yt,
                "birlesik": bool(yt),
                "modulDuzeyi": False,
                "kaynakSatiri": ortak.tek_satir(metin.splitlines()[satir_no - 1])[:200],
            }
        )
    return adaylar


# ── HTML (metin düğümleri + görünür öznitelikler; <script> içeriği TS çıkarıcısına gider) ─────────────────────

_HTML_OZNITELIK = {"title", "placeholder", "aria-label", "alt", "aria-description", "label", "data-tooltip", "content"}


class _HtmlCikarici(html.parser.HTMLParser):
    def __init__(self, yol: str):
        super().__init__(convert_charrefs=True)
        self.yol = yol
        self.adaylar: list[dict] = []
        self.betikler: list[tuple[int, str]] = []
        self._etiket: list[str] = []
        self._betik_bas: int | None = None
        self._meta_ad = None

    def handle_starttag(self, tag, attrs):
        self._etiket.append(tag)
        if tag == "script":
            self._betik_bas = self.getpos()[0]
        a = dict(attrs)
        if tag == "meta" and a.get("name") not in ("description",):
            return
        for k, v in attrs:
            if k in _HTML_OZNITELIK and v and (ortak.dogal_mi(v) or (k != "content" and re.search(r"[^\W\d_]", v))):
                self._ekle(v, "html-oznitelik", f"{tag}[{k}]")
        if tag == "input" and a.get("type") in ("button", "submit") and a.get("value"):
            self._ekle(a["value"], "html-oznitelik", "input[value]")

    def handle_endtag(self, tag):
        while self._etiket and self._etiket[-1] != tag:
            self._etiket.pop()
        if self._etiket:
            self._etiket.pop()

    def handle_data(self, data):
        ust = self._etiket[-1] if self._etiket else ""
        if ust == "script":
            self.betikler.append((self.getpos()[0], data))
            return
        if ust == "style":
            return
        m = ortak.tek_satir(data)
        if m and re.search(r"[^\W\d_]", m):
            self._ekle(m, "html-metin", ust)

    def _ekle(self, m, tur, baglam):
        satir = self.getpos()[0]
        self.adaylar.append(
            {
                "dosya": self.yol,
                "satir": satir,
                "sutun": self.getpos()[1] + 1,
                "metin": ortak.tek_satir(m),
                "ham": ortak.tek_satir(m),
                "tur": tur,
                "baglam": baglam,
                "oneri": f"{Path(self.yol).stem}.{ortak.anahtar_parcasi(m)}",
                "yertutucular": [],
                "birlesik": False,
                "modulDuzeyi": False,
            }
        )


def html_adaylari(yol: str, metin: str) -> tuple[list[dict], list[dict]]:
    p = _HtmlCikarici(yol)
    p.feed(metin)
    p.close()
    girdiler = [
        {
            "ad": yol,
            "metin": icerik,
            "satirOtele": satir - 1,
            "uzanti": ".js",
            "adAlani": Path(yol).parent.name or Path(yol).stem,
        }
        for satir, icerik in p.betikler
        if icerik.strip()
    ]
    return p.adaylar, girdiler


# ── NSIS ───────────────────────────────────────────────────────────────────────────────────────────────────────


def nsis_adaylari(yol: str, metin: str) -> list[dict]:
    adaylar = []
    for no, satir in enumerate(metin.splitlines(), 1):
        s = satir.strip()
        if not s or s.startswith(";") or s.startswith("#"):
            continue
        m = re.match(
            r'(DetailPrint|MessageBox\s+[\w|]+|LangString\s+\w+\s+\S+|SetDetailsPrint\s+\w+|Abort)\s+"(.*)"', s
        )
        if not m:
            continue
        deger = m.group(2)
        gorunen = deger.replace("$\\r$\\n", "\n").replace("$\\n", "\n")
        if not re.search(r"[^\W\d_]{2,}", gorunen):
            continue
        adaylar.append(
            {
                "dosya": yol,
                "satir": no,
                "sutun": satir.find('"') + 2,
                "metin": ortak.tek_satir(gorunen),
                "ham": deger,
                "tur": "nsis",
                "baglam": m.group(1).split()[0],
                "oneri": f"nsis.{ortak.anahtar_parcasi(gorunen)}",
                "yertutucular": sorted(set(re.findall(r"\$\{?(\w+)\}?", deger)) - {"r", "n", "INSTDIR", "APPDATA"}),
                "birlesik": "$" in deger.replace("$\\r$\\n", ""),
                "modulDuzeyi": False,
            }
        )
    return adaylar


# ── Orkestra ───────────────────────────────────────────────────────────────────────────────────────────────────


def cikar(dosyalar: list[str], kok: Path | None = None, olcum: bool = False) -> dict:
    kok = kok or ortak.KOK
    sonuc = {"adaylar": [], "olcum": {}, "hatalar": []}
    ts_girdi: list[dict] = []
    for d in dosyalar:
        p = kok / d
        if not p.is_file():
            sonuc["hatalar"].append({"dosya": d, "hata": "dosya yok"})
            continue
        metin = p.read_text(encoding="utf-8", errors="replace")
        if d.endswith((".ts", ".tsx", ".js", ".jsx", ".cjs", ".mjs")):
            ts_girdi.append({"ad": d, "metin": metin})
        elif d.endswith(".py"):
            a, h = py_adaylari(d, metin)
            sonuc["adaylar"] += a
            sonuc["hatalar"] += h
        elif d.endswith(".rs"):
            sonuc["adaylar"] += rust_adaylari(d, metin)
        elif d.endswith((".html", ".htm")):
            a, betikler = html_adaylari(d, metin)
            sonuc["adaylar"] += a
            ts_girdi += betikler
        elif d.endswith((".nsi", ".nsh")):
            sonuc["adaylar"] += nsis_adaylari(d, metin)
    if ts_girdi:
        r = ts_adaylari(ts_girdi, kok, olcum=olcum)
        sonuc["adaylar"] += r["adaylar"]
        sonuc["hatalar"] += r["hatalar"]
        sonuc["olcum"] = r["olcum"]
    for a in sonuc["adaylar"]:
        a["yuzey"] = ortak.dosyanin_yuzeyi(a["dosya"]) or "?"
        for k in ("bas", "son"):
            a.pop(k, None)
    sonuc["adaylar"].sort(key=lambda a: (a["dosya"], a["satir"], a["sutun"]))
    return sonuc


def kapsam_grubu_dosyalari(grup: str, kok: Path | None = None) -> list[str]:
    kok = kok or ortak.KOK
    defter = ortak.json_oku(kok / "i18n" / "kapsam.json")
    return [d for d, k in defter["dosyalar"].items() if k.get("grup") == grup]


def ozet_tablosu(adaylar: list[dict]) -> str:
    from collections import Counter, defaultdict

    satir = []
    yz = Counter(a["yuzey"] for a in adaylar)
    dosya = defaultdict(set)
    for a in adaylar:
        dosya[a["yuzey"]].add(a["dosya"])
    satir.append(f"{'yüzey':10} {'aday':>6} {'dosya':>6} {'tekil':>6}")
    for y in sorted(yz):
        tekil = len({a["metin"] for a in adaylar if a["yuzey"] == y})
        satir.append(f"{y:10} {yz[y]:6} {len(dosya[y]):6} {tekil:6}")
    tur = Counter(f"{a['yuzey']}:{a['tur']}" for a in adaylar)
    satir.append("tür: " + ", ".join(f"{k}={v}" for k, v in sorted(tur.items())))
    return "\n".join(satir)


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="I18N aday metin çıkarımı")
    ap.add_argument("--yuzey", nargs="*", default=[], help="arayuz | sunucu | launcher | site | dema | hepsi")
    ap.add_argument("--grup", help="i18n/kapsam.json grup adı")
    ap.add_argument("--dosya", nargs="*", default=[])
    ap.add_argument("--kok", help="depo kökü (varsayılan: bu betiğin deposu)")
    ap.add_argument("--cikti", help="JSON çıktı dosyası (yoksa stdout)")
    ap.add_argument("--ozet", action="store_true", help="yalnız sayım tablosu")
    ap.add_argument("--olcum", action="store_true", help="ön ölçüm alanlarını da topla (TS)")
    ap.add_argument(
        "--taban", action="store_true", help="göç öncesi TR tabanı biçimi (yüzey/dosya/satır/metin/ham/tür)"
    )
    a = ap.parse_args(argv)
    kok = Path(a.kok).resolve() if a.kok else ortak.KOK
    dosyalar = list(a.dosya)
    yuzeyler = list(ortak.YUZEYLER) if "hepsi" in a.yuzey else a.yuzey
    for y in yuzeyler:
        dosyalar += ortak.yuzey_dosyalari(y, kok)
    if a.grup:
        dosyalar += kapsam_grubu_dosyalari(a.grup, kok)
    dosyalar = sorted(dict.fromkeys(d.replace("\\", "/") for d in dosyalar))
    sonuc = cikar(dosyalar, kok, olcum=a.olcum)
    sonuc["dosyaSayisi"] = len(dosyalar)
    if a.taban:
        sonuc = {
            "aciklama": "I18N göç öncesi TR tabanı — scripts/i18n/cikar.py --taban (değiştirme; katalog taban karşılaştırması buna bakar)",
            "dosyaSayisi": len(dosyalar),
            "dosyalar": dosyalar,
            "metinler": [
                {k: x.get(k) for k in ("yuzey", "dosya", "satir", "metin", "ham", "tur", "baglam", "birlesik")}
                for x in sonuc["adaylar"]
            ],
            "hatalar": sonuc["hatalar"],
        }
    if a.ozet:
        print(ozet_tablosu(sonuc.get("adaylar") or sonuc.get("metinler") or []))
        print(f"dosya: {len(dosyalar)} · hata: {len(sonuc['hatalar'])}")
        if not a.cikti:
            return 0
    metin = json.dumps(sonuc, ensure_ascii=False, indent=1)
    if a.cikti:
        Path(a.cikti).write_text(metin, encoding="utf-8")
        print(
            f"yazıldı: {a.cikti} ({len(sonuc.get('adaylar') or sonuc.get('metinler') or [])} aday, {len(dosyalar)} dosya)"
        )
    else:
        print(metin)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
