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

import re


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
    return _if0_soy("".join(out))


_IF0 = re.compile(r"^\s*#\s*if\s+\(?\s*0\s*\)?\s*$")
_IF_DIGER = re.compile(r"^\s*#\s*(if|ifdef|ifndef)\b")
_ELSE = re.compile(r"^\s*#\s*(else|elif)\b")
_ENDIF = re.compile(r"^\s*#\s*endif\b")


def _if0_soy(metin: str) -> str:
    """Önişlemciyle ÖLÜ kodu (`#if 0` … `#else`/`#elif`/`#endif`) da boşlukla değiştirir (uzunluk ve satırlar korunur).

    ⚠️ 1-B bağımsız inceleme (i3): yorum soyucu `#if 0` içine alınmış kodu CANLI sayıyordu — Error_Handler'daki bobin
    kesme çağrısı `#if 0 … #endif` içine alınınca 29 STM kapı dosyası 300/300 YEŞİLDİ. `#else`/`#elif` dalı CANLI
    kabul edilir (tutucu: koşullu kod kaybolmaz); iç içe `#if`'ler ölü bölgede ölü kalır."""
    satirlar = metin.split("\n")
    yigin: list[bool] = []  # her açık #if çerçevesi için: bu çerçevede kod ÖLÜ mü
    for k, satir in enumerate(satirlar):
        ust_olu = any(yigin)
        if _IF0.match(satir):
            yigin.append(True)
            satirlar[k] = " " * len(satir)
            continue
        if _IF_DIGER.match(satir):
            yigin.append(False)
            if ust_olu:
                satirlar[k] = " " * len(satir)
            continue
        if _ELSE.match(satir) and yigin:
            disari_olu = any(yigin[:-1])
            yigin[-1] = False
            if disari_olu:
                satirlar[k] = " " * len(satir)
            continue
        if _ENDIF.match(satir) and yigin:
            yigin.pop()
            if any(yigin) or ust_olu:
                satirlar[k] = " " * len(satir)
            continue
        if ust_olu:
            satirlar[k] = " " * len(satir)
    return "\n".join(satirlar)
