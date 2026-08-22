# Author: mertaygn, cglrgrkn
"""Yorum-soyma yardımcısı — C/C++ kaynak için STRING-BİLİNÇLİ (17. parti, 2026-08-20).

Eski desen (`re.sub(r"//[^\n]*", ...)`) string literal İÇİNDEKİ `//`yi yorum sanıyordu:
`url.startsWith("https://")` satırının kalanı siliniyor ve yasak-token kapıları o bölgeyi
GÖREMİYORDU — adversaryal test-gaming incelemesi bunu, canlı bir SYNC_ALL dispatch'ini
`String("s://")` hilesiyle kapılardan kaçırarak AMPİRİK kanıtladı.

Bu soyucu string/char literallerini OLDUĞU GİBİ korur (komut-dizesi kapıları — `"set_params"`,
`cmdStr == "UPDATE"` — string içeriğine dayanır), yalnız GERÇEK yorumları söker. Token-in-string
hilesine karşı savunma bu modülün işi değildir: onu, kapıların token VARLIĞI yerine TAM İFADE
pinlemesi karşılar (aynı incelemenin ikinci dersi — bkz. test_sureli_crashloop_ikizi 17. parti
güçlendirmesi).

Durum makinesi: KOD / "STRING" / 'CHAR' / //SATIR / /*BLOK*/ (kaçışlar dahil). Yorumlar satır
yapısını koruyacak biçimde boşlukla değiştirilir (dizin-tabanlı dilimlemeler bozulmasın).
"""

from __future__ import annotations


def c_soy(src: str) -> str:
    """Yorumları söker; string/char literalleri (içerik dahil) aynen korur."""
    out = []
    i, n = 0, len(src)
    KOD, STR, CHR, SATIR, BLOK = 0, 1, 2, 3, 4
    durum = KOD
    while i < n:
        c = src[i]
        nx = src[i + 1] if i + 1 < n else ""
        if durum == KOD:
            if c == "/" and nx == "/":
                durum = SATIR
                out.append("  ")
                i += 2
                continue
            if c == "/" and nx == "*":
                durum = BLOK
                out.append("  ")
                i += 2
                continue
            if c == '"':
                durum = STR
            elif c == "'":
                durum = CHR
            out.append(c)
        elif durum == STR:
            if c == "\\" and nx:
                out.append(c)
                out.append(nx)
                i += 2
                continue
            if c == '"':
                durum = KOD
            out.append(c)
        elif durum == CHR:
            if c == "\\" and nx:
                out.append(c)
                out.append(nx)
                i += 2
                continue
            if c == "'":
                durum = KOD
            out.append(c)
        elif durum == SATIR:
            if c == "\n":
                durum = KOD
                out.append("\n")
            else:
                out.append(" ")
        elif durum == BLOK:
            if c == "*" and nx == "/":
                durum = KOD
                out.append("  ")
                i += 2
                continue
            out.append("\n" if c == "\n" else " ")
        i += 1
    return "".join(out)
