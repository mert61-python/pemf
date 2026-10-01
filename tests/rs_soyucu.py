# Author: mertaygn, cglrgrkn
"""Yorum-soyma yardımcısı — RUST kaynağı için DİZE-BİLİNÇLİ (Dalga 1, D1.35). ⚠️ pytest TOPLAMAZ.

(`test_` ön eki yok; `c_soyucu.py` / `topoloji.py` ile aynı desen.)

NEDEN AYRI: `c_soyucu.c_soy` C içindir; Rust'ta iki yerde YANLIŞ soyar —
  * ömür belirteci (`&'static str`, `<'a>`) karakter sabiti sanılır → soyucu "CHAR" durumunda
    takılır ve dosyanın geri kalanındaki yorumlar SOYULMAZ (kapı yorumdaki kopyayı görür);
  * ham dize (`r#"..."#`, `r"..."`) içindeki `"` ve `//` normal dize/yorum sanılır.
Ayrıca Rust blok yorumları İÇ İÇE geçebilir (`/* a /* b */ c */`).

`rs_soy(src)`: yorumları satır yapısını ve UZUNLUĞU koruyarak boşlukla değiştirir; dize/karakter
sabitleri aynen kalır (tam ifade kapıları dize içeriğine dayanabilir).
`rs_soy(src, dizeleri_bosalt=True)`: ek olarak dize/karakter İÇERİKLERİNİ boşlukla değiştirir
(tırnaklar kalır) — süslü parantez eşlemesi için (`format!("{e}")` içindeki `{` blok değildir).
İki çıktı aynı uzunluktadır: birinde bulunan dizin ötekinde de geçerlidir.
"""

from __future__ import annotations

import re


def rs_soy(src: str, dizeleri_bosalt: bool = False) -> str:
    out: list[str] = []
    i, n = 0, len(src)

    def bos(c: str) -> str:
        return "\n" if c == "\n" else " "

    while i < n:
        c = src[i]
        nx = src[i + 1] if i + 1 < n else ""
        # satır yorumu (//, ///, //!)
        if c == "/" and nx == "/":
            while i < n and src[i] != "\n":
                out.append(" ")
                i += 1
            continue
        # blok yorumu — İÇ İÇE
        if c == "/" and nx == "*":
            derinlik = 0
            while i < n:
                if src.startswith("/*", i):
                    derinlik += 1
                    out.append("  ")
                    i += 2
                    continue
                if src.startswith("*/", i):
                    derinlik -= 1
                    out.append("  ")
                    i += 2
                    if derinlik == 0:
                        break
                    continue
                out.append(bos(src[i]))
                i += 1
            continue
        # ham dize: r"..", r#".."#, br"..", br#".."# (önceki karakter tanımlayıcı parçası OLMAMALI)
        m = re.compile(r'b?r(#*)"').match(src, i)
        if m and (i == 0 or not (src[i - 1].isalnum() or src[i - 1] == "_")):
            hash_ = m.group(1)
            kapanis = '"' + hash_
            bas = m.end()
            son = src.find(kapanis, bas)
            son = n if son < 0 else son
            out.append(src[i:bas])
            govde = src[bas:son]
            out.append("".join(bos(x) for x in govde) if dizeleri_bosalt else govde)
            out.append(src[son : son + len(kapanis)])
            i = son + len(kapanis)
            continue
        # normal dize (b"..." dahil — 'b' koda zaten eklendi)
        if c == '"':
            out.append(c)
            i += 1
            while i < n:
                d = src[i]
                if d == "\\" and i + 1 < n:
                    out.append("  " if dizeleri_bosalt else src[i : i + 2])
                    i += 2
                    continue
                if d == '"':
                    out.append(d)
                    i += 1
                    break
                out.append(bos(d) if dizeleri_bosalt else d)
                i += 1
            continue
        # karakter sabiti mi ömür belirteci mi?
        if c == "'":
            if nx == "\\":  # '\n', '\'', '\u{..}'
                j = src.find("'", i + 2)
                if src.startswith("u{", i + 2):
                    j = src.find("'", src.find("}", i + 2))
                j = n - 1 if j < 0 else j
                out.append("'" + ("".join(bos(x) for x in src[i + 1 : j]) if dizeleri_bosalt else src[i + 1 : j]) + "'")
                i = j + 1
                continue
            if i + 2 < n and src[i + 2] == "'":  # 'x'
                out.append("' '" if dizeleri_bosalt else src[i : i + 3])
                i += 3
                continue
            out.append(c)  # ömür belirteci: 'a, 'static, '_
            i += 1
            continue
        out.append(c)
        i += 1
    sonuc = "".join(out)
    assert len(sonuc) == len(src), "rs_soy uzunluğu korumadı (dizin eşlemesi bozulur)"
    return sonuc


def blok_sonu(maske: str, ac: int) -> int:
    """`maske[ac] == '{'` için eşleşen `}`'nin dizini (maske = dizeleri boşaltılmış soyulmuş metin)."""
    assert maske[ac] == "{", f"{ac}. karakter '{{' değil: {maske[ac]!r}"
    derinlik = 0
    for k in range(ac, len(maske)):
        if maske[k] == "{":
            derinlik += 1
        elif maske[k] == "}":
            derinlik -= 1
            if derinlik == 0:
                return k
    raise AssertionError("blok kapanmıyor")


def ifade_deseni(ifade: str) -> re.Pattern:
    """Tam ifade → boşluk-esnek düzenli ifade (belirteçler arasındaki boşluk serbest, belirteçler AYNEN)."""
    parcalar = re.findall(r"\w+|[^\w\s]", ifade)
    return re.compile(r"\s*".join(re.escape(p) for p in parcalar))


def ust_duzey_eslesmeler(soyulmus: str, maske: str, bas: int, son: int, ifade: str) -> list[int]:
    """[bas, son) aralığında, aralığın KENDİ süslü-parantez derinliğinde (alt blok İÇİNDE değil)
    geçen tam ifade eşleşmelerinin başlangıç dizinleri. `if false { X; }` içine alınmış X SAYILMAZ."""
    sonuc = []
    for m in ifade_deseni(ifade).finditer(soyulmus, bas, son):
        derinlik = 0
        for k in range(bas, m.start()):
            if maske[k] == "{":
                derinlik += 1
            elif maske[k] == "}":
                derinlik -= 1
        if derinlik == 0:
            sonuc.append(m.start())
    return sonuc
