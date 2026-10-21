# -*- coding: utf-8 -*-
"""I18N ortak tanımlar — yüzeyler, katalog yolları, katalog okuma / düzleştirme, yer tutucu ve doğal dil sezgisi.

TEK KAYNAK: araçlar (`cikar`, `uygula`, `katalog`, `bayrak`) ve kapılar (`tests/test_i18n_*.py`, `tests/i18n_yardimci.py`) bu modülü
kullanır. Yüzey / katalog yolu burada değişirse hepsi birlikte değişir.

⚠️ `dogal_mi` JS karşılığı `scripts/i18n/cikar_ts.cjs::dogalMi` ile AYNI kuralı uygular; `tests/test_i18n_araclar.py` iki
uygulamayı aynı örnek listesiyle karşılaştırır (sürüklenme kapısı).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]
DILLER = ("tr", "en")
YEDEK_DIL = "tr"


def varsayilan_taban() -> Path:
    """Göç öncesi TR tabanı (`cikar.py --taban` çıktısı) — depo DIŞINDA, denetim klasöründe. `PEMF_I18N_TABAN` ile değişir; sahte
    evli kafes koşucusunda (ev / PEMF_* sıfırlanır) araçlara `--taban <yol>` AÇIKÇA verilir."""
    return Path(
        os.environ.get("PEMF_I18N_TABAN") or Path.home() / "Desktop" / "DENETIM" / "I18N" / "taban-tr-metinler.json"
    )


#: Yüzey → katalog düzeni. "dizin": {dil}/<ad-alanı>.json (ad alanı = dosya adı, kök anahtar) · "dosya": {dil}.json (tek dosya).
KATALOGLAR = {
    "arayuz": {"kok": "apps/ui/src/i18n", "duzen": "dizin"},
    "site": {"kok": "apps/web/src/i18n", "duzen": "dizin"},
    "sunucu": {"kok": "apps/backend/i18n", "duzen": "dosya"},
    "launcher": {"kok": "launcher/i18n", "duzen": "dosya"},
    "dema": {"kok": "dema-terapi-simülatörü/src/i18n", "duzen": "dosya"},
}

#: Yüzey → izlenen kaynak dosya desenleri (git ls-files yol önekleri + uzantılar) ve dışlananlar.
YUZEYLER = {
    "arayuz": {
        # I18NI-A2.13: `apps/ui/modules/` (Expo yerli modülleri — APK kurucu köprüsü) de arayüz yüzeyidir; Kotlin çıkarıcı YOK → yerli
        # metin JS katalogundan Intent ile gelir (kapı tests/test_I18NI_android_bildirim_metni_katalogdan.py).
        "onek": ("apps/ui/src/", "apps/ui/app/", "apps/ui/auth-pages/", "apps/ui/modules/"),
        "uzanti": (".ts", ".tsx", ".html"),
    },
    "sunucu": {
        "onek": ("apps/backend/",),
        "uzanti": (".py",),
    },
    "launcher": {
        "onek": ("launcher/app/ui/", "launcher/app/src/", "launcher/core/src/", "launcher/app/windows/"),
        "uzanti": (".html", ".rs", ".nsi"),
    },
    "site": {
        "onek": ("apps/web/src/", "apps/web/api/", "apps/web/index.html"),
        "uzanti": (".ts", ".tsx", ".html"),
    },
    "dema": {
        "onek": ("dema-terapi-simülatörü/src/", "dema-terapi-simülatörü/index.html"),
        "uzanti": (".ts", ".tsx", ".html"),
    },
}
#: Hiçbir yüzeyde kaynak sayılmayanlar: testler, tür bildirimleri, i18n altyapısının KENDİ katalog dosyaları.
DISLA = re.compile(
    r"(/__tests__/|\.test\.(ts|tsx)$|\.spec\.(ts|tsx)$|\.d\.ts$|/i18n/(tr|en)(/|\.json$)|/tests?/|_test\.py$|/test_[^/]*\.py$)"
)


def yuzey_dosyalari(yuzey: str, kok: Path | None = None) -> list[str]:
    """Yüzeyin izlenen (git) kaynak dosyaları — depo-göreli, '/' ayraçlı, sıralı. git yoksa dosya sistemi taranır."""
    kok = kok or KOK
    tanim = YUZEYLER[yuzey]
    try:
        cikti = subprocess.run(
            ["git", "-c", "core.quotepath=off", "ls-files", "-z", "--", *[o.rstrip("/") for o in tanim["onek"]]],
            cwd=kok,
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8")
        yollar = [y for y in cikti.split("\0") if y]
    except Exception:
        yollar = []
        for o in tanim["onek"]:
            p = kok / o
            if p.is_file():
                yollar.append(o)
            elif p.is_dir():
                yollar += [
                    x.relative_to(kok).as_posix() for x in p.rglob("*") if x.is_file() and "node_modules" not in x.parts
                ]
    secilen = sorted({y for y in yollar if y.endswith(tanim["uzanti"]) and not DISLA.search("/" + y)})
    return secilen


def dosyanin_yuzeyi(yol: str) -> str | None:
    y = yol.replace("\\", "/")
    for ad, tanim in YUZEYLER.items():
        if any(y.startswith(o) for o in tanim["onek"]) and y.endswith(tanim["uzanti"]):
            return ad
    return None


# ── Katalog ─────────────────────────────────────────────────────────────────────────────────────────────────


def katalog_dosyalari(yuzey: str, dil: str, kok: Path | None = None) -> dict[str, Path]:
    """{ad_alanı | "": dosya yolu}. "dizin" düzeninde ad alanı dosya adıdır; "dosya" düzeninde tek anahtar ""."""
    kok = kok or KOK
    t = KATALOGLAR[yuzey]
    taban = kok / t["kok"]
    if t["duzen"] == "dizin":
        d = taban / dil
        return {p.stem: p for p in sorted(d.glob("*.json"))} if d.is_dir() else {}
    p = taban / f"{dil}.json"
    return {"": p} if p.exists() else {}


def json_oku(yol: Path) -> dict:
    return json.loads(Path(yol).read_text(encoding="utf-8"))


def katalog_yukle(yuzey: str, dil: str, kok: Path | None = None) -> dict:
    """İç içe katalog. "dizin" düzeninde {ad_alanı: içerik} birleşimi (anahtar `adalani.x.y`)."""
    sonuc: dict = {}
    for ns, yol in katalog_dosyalari(yuzey, dil, kok).items():
        icerik = json_oku(yol)
        if ns:
            sonuc[ns] = icerik
        else:
            sonuc.update(icerik)
    return sonuc


def duzlestir(d: dict, onek: str = "") -> dict[str, str]:
    """{'a': {'b': 'x'}} → {'a.b': 'x'}. Yaprak dizgi değilse (sayı / liste) değer str'e çevrilmez — kapı bunu ayrıca yakalar."""
    duz: dict[str, str] = {}
    for k, v in d.items():
        tam = f"{onek}.{k}" if onek else str(k)
        if isinstance(v, dict):
            duz.update(duzlestir(v, tam))
        else:
            duz[tam] = v
    return duz


COGUL_SONEKLERI = ("_zero", "_one", "_two", "_few", "_many", "_other")


def cogul_koku(anahtar: str) -> str | None:
    for s in COGUL_SONEKLERI:
        if anahtar.endswith(s):
            return anahtar[: -len(s)]
    return None


#: i18next v4 dili için gereken çoğul biçimleri (CLDR): tr ve en ikisi de one / other.
COGUL_BICIMLERI = {"tr": ("_one", "_other"), "en": ("_one", "_other")}

YER_TUTUCU = re.compile(r"\{\{\s*-?\s*([A-Za-z_][\w.]*)\s*(?:,[^}]*)?\}\}")


def yer_tutuculari(metin) -> set[str]:
    return set(YER_TUTUCU.findall(str(metin))) if isinstance(metin, str) else set()


def yer_tutucu_normal(metin: str) -> str:
    """Yer tutucu ADLARI yok sayılarak karşılaştırma için: `{{gun}}` ≡ `{{days}}` → `{{}}` (göçte anlamlı ad verilir, metin aynı kalır)."""
    return YER_TUTUCU.sub("{{}}", str(metin))


#: Kaynakta katalog anahtarı kullanımı: t("…") / t('…') / i18n.t("…") / ceviri.t("…") / kritikMetin("…") / dil::t("…") / t_ile("…" /
#: tf("…") / data-i18n="…" / <Trans i18nKey="…"> (zengin metin, I18N-P1) / NSIS $(PEMF_…) — ilk argüman DEĞİŞMEZ dizgi (dinamik anahtar K-3 izin listesinde). TEK KAYNAK: araçlar
#: (`katalog.py taban`) ve kapılar (`tests/i18n_yardimci.py`).
ANAHTAR_KULLANIMI = re.compile(
    r"""(?:\b(?:t|tf|kritikMetin|t_ile)|\bi18n\.t|\bceviri\.t|\bdil::t|\bdil::t_ile)\(\s*["']([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+)["']"""
    r"""|(?:data-i18n(?:-[a-z]+)?|\bi18nKey)=\{?["']([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+)["']"""
    r"""|\$\(PEMF_([A-Za-z0-9_]+)\)"""
)


def kullanilan_anahtarlar(metin: str) -> set[str]:
    sonuc = set()
    for m in ANAHTAR_KULLANIMI.finditer(metin):
        if m.group(1) or m.group(2):
            sonuc.add(m.group(1) or m.group(2))
        elif m.group(3):
            sonuc.add("nsis." + m.group(3).replace("_", "."))
    return sonuc


def anahtar_kullanilabilir(anahtar: str, duz: dict[str, str]) -> bool:
    """Anahtar katalogda var mı (çoğul anahtar `x` için `x_one` / `x_other` de sayılır)."""
    if anahtar in duz:
        return True
    return any(anahtar + s in duz for s in COGUL_SONEKLERI)


# ── Doğal dil sezgisi (cikar_ts.cjs::dogalMi ile AYNI kural) ──────────────────────────────────────────────────

TR_HARF = re.compile(r"[çğıöşüÇĞİÖŞÜâîûÂÎÛ]")
_HARF = re.compile(r"[^\W\d_]")
_HARF2 = re.compile(r"[^\W\d_]{2,}")


def _harf_mi(c: str) -> bool:
    return c.isalpha()


def _alnum_mi(c: str) -> bool:
    return c.isalpha() or c.isdigit()


def dogal_mi(ham) -> bool:
    s0 = str(ham).strip()
    if len(s0) < 2 or not _HARF.search(s0):
        return False
    ilk = s0[0]
    sus = (not _alnum_mi(ilk) and not ilk.isspace() and ilk not in "\"'`([{</\\#@$_.-") or s0[-1] in "✓✔✗✕…!?"
    i, j = 0, len(s0)
    while i < j and not _alnum_mi(s0[i]):
        i += 1
    while j > i and not _alnum_mi(s0[j - 1]):
        j -= 1
    s = s0[i:j] or s0
    if sus and _HARF2.search(s):
        return True
    if TR_HARF.search(s):
        if re.fullmatch(
            r"[\w.\-/\\:çğıöşüÇĞİÖŞÜ]+\.(tsx?|jsx?|json|py|rs|md|png|jpe?g|pdf|csv|zip|exe|log|db)", s, re.I
        ):
            return False
        return True
    if re.match(r"^[a-z][a-z0-9+.\-]*://", s, re.I) or re.match(r"^(mailto|tel|data|blob):", s, re.I):
        return False
    if re.fullmatch(r"/[\w\-./:{}?=&%]*", s):
        return False
    if re.fullmatch(r"[\w\-]+/[\w\-+.]+(;.*)?", s) and not re.search(r"\s", s):
        return False
    if re.fullmatch(r"#[0-9a-f]{3,8}", s, re.I) or re.match(r"^(rgba?|hsla?)\(", s, re.I):
        return False
    if re.fullmatch(r"[\w.\-]+@[\w.\-]+", s):
        return False
    if re.fullmatch(r"[A-ZÇĞİÖŞÜ]{3,}[.!?…:]", s0):  # "UYARI:", "DURDURULUYOR…" (sabit adı değil, noktalamalı vurgu)
        return True
    if re.fullmatch(r"[A-Z0-9_]+", s):
        return False
    if re.fullmatch(r"[a-z][A-Za-z0-9_]*", s):
        return False
    if re.fullmatch(r"[a-z0-9]+([_\-.:][a-z0-9]+)+", s, re.I) and not re.search(r"\s", s):
        return False
    if re.fullmatch(r"[\d\s.,:;%+\-*/()=<>xX°]+[a-zA-Zµ°%]{0,3}", s):
        return False
    if re.fullmatch(r"(mT|Hz|kHz|MHz|ms|sn|dk|sa|°C|µT|uT|V/m|mA|A|V|W|kg|g|mm|cm|m|px|dp|pt|em|rem|vh|vw|fr|%)", s):
        return False
    if re.search(r"\s", s):
        sozcuk = [w for w in re.split(r"\s+", s) if _HARF2.search(w)]
        return len(sozcuk) >= 2 or bool(re.match(r"[A-ZÇĞİÖŞÜ]", s))
    if re.fullmatch(r"[A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,}[.!?…:]?", s):
        return True
    return False


_KATLA = str.maketrans(
    {
        "ç": "c",
        "ğ": "g",
        "ı": "i",
        "ö": "o",
        "ş": "s",
        "ü": "u",
        "Ç": "C",
        "Ğ": "G",
        "İ": "I",
        "Ö": "O",
        "Ş": "S",
        "Ü": "U",
        "â": "a",
        "î": "i",
        "û": "u",
    }
)


def anahtar_parcasi(metin: str) -> str:
    """Öneri anahtar parçası — ASCII camelCase, ilk 4 sözcük (cikar_ts.cjs::anahtarParcasi ile aynı)."""
    s = YER_TUTUCU.sub(" ", str(metin)).translate(_KATLA)
    s = re.sub(r"[^A-Za-z0-9 ]+", " ", s).strip()
    soz = [w for w in s.split() if w][:4]
    if not soz:
        return "metin"
    return "".join(
        w[:1].lower() + w[1:].lower() if i == 0 else w[:1].upper() + w[1:].lower() for i, w in enumerate(soz)
    )


def tek_satir(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip()


#: Düzenli ifade değişmezi bu karakterlerden SONRA başlar (bölme işareti değil). `<` / `>` YOK: TSX kapanış etiketi `</Text>`.
_REGEX_ONCESI = set("(,=:[!&|?{};+-*%~^\n")


def ts_yorumsuz(s: str) -> str:
    """TS / TSX / JS yorumlarını soyar — DİZGİYİ YORUM SAYMAZ (I18NI-A2.5). Konum korunur: yorum karakterleri boşluk, satır sonları kalır.

    `re.sub(r"/\\*.*?\\*/", …, re.S)` dizgideki `/*`'ı (`input.accept = 'image/*'`) yorum başlangıcı sayıp bir SONRAKİ `*/`'a kadar KODU
    yutuyordu (ölçüldü: AiHubScreen 1024 kod satırı / 100 çeviri çağrısı K-3 ve K-5'e görünmüyordu). Kurallar: `'…'` / `"…"` aynı satırda
    kapanmazsa dizgi değildir (JSX metnindeki kesme işareti: `Wi-Fi'de`); şablon `` `…` `` içindeki `${…}` atlanır; `/` önceki anlamlı
    karakter bir işleç / ayraçsa düzenli ifade değişmezidir (aynı satırda kapanır)."""
    out = list(s)
    n = len(s)
    i = 0
    while i < n:
        c = s[i]
        nx = s[i + 1] if i + 1 < n else ""
        if c == "/" and nx == "/":
            j = s.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                out[k] = " "
            i = j
            continue
        if c == "/" and nx == "*":
            j = s.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
            continue
        if c in "\"'":
            j = i + 1
            while j < n and s[j] not in (c, "\n"):
                j += 2 if s[j] == "\\" else 1
            i = j + 1 if j < n and s[j] == c else i + 1
            continue
        if c == "`":
            j = i + 1
            while j < n and s[j] != "`":
                if s[j] == "\\":
                    j += 2
                elif s[j] == "$" and j + 1 < n and s[j + 1] == "{":
                    derinlik, j = 1, j + 2
                    while j < n and derinlik:
                        derinlik += {"{": 1, "}": -1}.get(s[j], 0)
                        j += 1
                else:
                    j += 1
            i = j + 1
            continue
        if c == "/":
            k = i - 1
            while k >= 0 and s[k] in " \t":
                k -= 1
            if k < 0 or s[k] in _REGEX_ONCESI or s[max(0, k - 5) : k + 1] == "return":
                j, sinif = i + 1, False
                while j < n and s[j] != "\n":
                    if s[j] == "\\":
                        j += 2
                        continue
                    if s[j] == "[":
                        sinif = True
                    elif s[j] == "]":
                        sinif = False
                    elif s[j] == "/" and not sinif:
                        break
                    j += 1
                if j < n and s[j] == "/":
                    i = j + 1
                    continue
        i += 1
    return "".join(out)
