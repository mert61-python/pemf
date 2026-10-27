# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Yorum soyucu — Rust ve Kotlin kaynağı için DİZGE-FARKINDA (D5.52 · B-10.127/.144/.145/.150).

⚠️ BU DOSYA BİR TEST DEĞİL, YARDIMCIDIR (adı `test_*` değil; pytest TOPLAMAZ).

NEDEN: launcher (Rust) ve mobil (Kotlin) kaynak kapıları ya ham metinde arıyordu (`// let _kilit = …` yorumu kilidi "alınmış"
gösteriyordu) ya da naif bir soyucu kullanıyordu: dizge içindeki `//`yi (ör. `"http://…"`) yorum başı sanıp satırın KALANINI
siliyordu → aynı satıra konan erken `return` kapıdan GİZLENİYORDU (ölçüldü). Bu soyucu:
  * `//` satır yorumu ve İÇ İÇE `/* … */` blok yorumu (iki dil de iç içe bloğa izin verir) → boşluk (satır sonları ve uzunluk KORUNUR:
    dizin aritmetiği yapan kapılar bozulmaz);
  * dizgeleri ve karakter sabitlerini OLDUĞU GİBİ korur: `"…"` (kaçışlarla), Rust ham dizgesi `r"…"` / `r#"…"#` / `br"…"`, bayt dizgesi
    `b"…"`, Kotlin ham dizgesi `\"\"\"…\"\"\"` ve şablon ifadesi `"${ … "iç dizge" … }"`;
  * Rust ömür adını (`'a`, `'static`) karakter sabitinden (`'x'`, `'\\n'`, `'\\u{1F600}'`) ayırır.
"""

from __future__ import annotations


def _bosalt(parca: str) -> str:
    return "".join("\n" if c == "\n" else " " for c in parca)


def _blok_sonu(src: str, i: int) -> int:
    """`/*` ile başlayan (İÇ İÇE olabilen) blok yorumun bittiği dizin (kapanmazsa dosya sonu)."""
    derinlik, j, n = 0, i, len(src)
    while j < n:
        if src.startswith("/*", j):
            derinlik += 1
            j += 2
        elif src.startswith("*/", j):
            derinlik -= 1
            j += 2
            if derinlik == 0:
                return j
        else:
            j += 1
    return n


def _dizge_sonu(src: str, i: int, kotlin: bool) -> int:
    """`"` ile başlayan normal dizgenin bittiği dizin (kapanış tırnağından sonra). Kotlin `${ … }` şablonu içinde iç dizgeler atlanır."""
    j, n = i + 1, len(src)
    while j < n:
        c = src[j]
        if c == "\\":
            j += 2
            continue
        if c == '"':
            return j + 1
        if kotlin and src.startswith("${", j):
            j = _sablon_sonu(src, j + 2)
            continue
        if c == "\n" and kotlin:
            return j  # Kotlin normal dizgesi satır aşamaz (bozuk girdi — taşma olmasın)
        j += 1
    return n


def _sablon_sonu(src: str, j: int) -> int:
    """Kotlin `${` şablon ifadesinin kapanışından sonraki dizin (içindeki dizgeler ve süslü parantez dengesi dahil)."""
    derinlik, n = 1, len(src)
    while j < n:
        c = src[j]
        if c == '"':
            j = _kotlin_ham_sonu(src, j) if src.startswith('"""', j) else _dizge_sonu(src, j, kotlin=True)
            continue
        if c == "{":
            derinlik += 1
        elif c == "}":
            derinlik -= 1
            if derinlik == 0:
                return j + 1
        j += 1
    return n


def _kotlin_ham_sonu(src: str, i: int) -> int:
    j = src.find('"""', i + 3)
    if j == -1:
        return len(src)
    j += 3
    while j < len(src) and src[j] == '"':  # """…""""  → fazla tırnaklar dizgeye aittir
        j += 1
    return j


def _rust_ham_basi(src: str, i: int) -> int | None:
    """`r"`, `r#…#"`, `br"`, `br#"` başı ise hash sayısını döndürür; değilse None. Tanımlayıcı ortasında (ör. `bar"`) DEĞİL."""
    if i > 0 and (src[i - 1].isalnum() or src[i - 1] == "_"):
        return None
    j = i + 2 if src.startswith("br", i) else i + 1 if src[i] == "r" else -1
    if j < 0:
        return None
    k = j
    while k < len(src) and src[k] == "#":
        k += 1
    return (k - j) if k < len(src) and src[k] == '"' else None


def _rust_karakter_sonu(src: str, i: int) -> int | None:
    """`'` karakter sabiti ise bittiği dizin; ömür adıysa (`'a`, `'static`) None."""
    n = len(src)
    if i + 1 >= n:
        return None
    if src[i + 1] == "\\":
        j = src.find("'", i + 2)
        return None if j == -1 else j + 1
    if i + 2 < n and src[i + 2] == "'":
        return i + 3
    return None


def _soy(src: str, dil: str) -> str:
    kotlin = dil == "kotlin"
    out: list[str] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j == -1 else j
            out.append(" " * (j - i))
            i = j
        elif src.startswith("/*", i):
            j = _blok_sonu(src, i)
            out.append(_bosalt(src[i:j]))
            i = j
        elif kotlin and src.startswith('"""', i):
            j = _kotlin_ham_sonu(src, i)
            out.append(src[i:j])
            i = j
        elif c == '"':
            j = _dizge_sonu(src, i, kotlin)
            out.append(src[i:j])
            i = j
        elif not kotlin and c in "rb" and (h := _rust_ham_basi(src, i)) is not None:
            bas = src.index('"', i)
            kap = '"' + "#" * h
            j = src.find(kap, bas + 1)
            j = n if j == -1 else j + len(kap)
            out.append(src[i:j])
            i = j
        elif (
            not kotlin
            and c == "b"
            and src.startswith('b"', i)
            and not (i > 0 and (src[i - 1].isalnum() or src[i - 1] == "_"))
        ):
            j = _dizge_sonu(src, i + 1, kotlin=False)
            out.append(src[i:j])
            i = j
        elif c == "'":
            if kotlin:
                j = src.find("'", i + 2 if src.startswith("'\\", i) else i + 1)
                j = n if j == -1 else j + 1
            else:
                k = _rust_karakter_sonu(src, i)
                j = i + 1 if k is None else k
            out.append(src[i:j])
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def rust_soy(src: str) -> str:
    """Rust kaynağının yorumlarını söker; dizge / karakter sabitlerini (ham dizgeler dahil) korur. Uzunluk ve satırlar korunur."""
    return _soy(src, "rust")


def kotlin_soy(src: str) -> str:
    """Kotlin kaynağının yorumlarını söker; dizgeleri (ham + şablon) korur. Uzunluk ve satırlar korunur."""
    return _soy(src, "kotlin")
