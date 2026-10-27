# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5.52 — `tests/kaynak_soyucu.py` (Rust / Kotlin dizge-farkında yorum soyucu) kendi kapısı.

Soyucu kapıların EN ALT katıdır (hafıza "sahteyi en alt katta"): yanlış soyarsa üstündeki her kapı ya kör (gerçek kodu siler)
ya da yanlış-kırmızı (yorumu kod sayar) olur. Bu dosya iki yönü de ölçer: yorum gider, dizge / karakter sabiti / ham dizge KALIR,
uzunluk ve satırlar korunur.
"""

from __future__ import annotations

from kaynak_soyucu import kotlin_soy, rust_soy


def _korur(soyulmus: str, kaynak: str) -> None:
    assert len(soyulmus) == len(kaynak) and soyulmus.count("\n") == kaynak.count("\n"), "uzunluk/satır korunmadı"


def test_KRITIK_kotlin_dizgedeki_cift_egik_cizgi_YORUM_DEGIL_ayni_satirdaki_return_GORUNUR():
    k = 'fun f(u: String): Int {\n  if (u == "http://dur") return START_NOT_STICKY // gerekce\n  startForeground(1, b)\n}\n'
    s = kotlin_soy(k)
    _korur(s, k)
    assert 'if (u == "http://dur") return START_NOT_STICKY' in s, (
        "dizge içindeki // satırın kalanını sildi (return gizlendi)"
    )
    assert "gerekce" not in s


def test_KRITIK_rust_yorumdaki_kod_SOKULUR_dizgedeki_KALIR():
    r = 'fn a() {\n    // let _kilit = install::kurulum_kilidi_al(&root)?;\n    let u = "http://x // y";\n    /* dis /* ic */ hala */ let b = 1;\n}\n'
    s = rust_soy(r)
    _korur(s, r)
    assert "kurulum_kilidi_al" not in s, "yorumdaki kilit satırı kod sayıldı"
    assert '"http://x // y"' in s, "dizge bozuldu"
    assert "hala" not in s and "let b = 1;" in s, "iç içe blok yorum doğru kapanmadı"


def test_rust_ham_dizge_ve_omur_ve_karakter_sabiti():
    r = "fn b<'a>(x: &'a str) -> char {\n    let h = r#\"a \"// degil\" b\"#;\n    let t = br\"\\\";  // yorum\n    let c = '\"'; let d = '\\''; // yorum2\n    '/'\n}\n"
    s = rust_soy(r)
    _korur(s, r)
    assert 'r#"a "// degil" b"#' in s, "ham dizge içindeki // yorum sanıldı"
    assert 'br"\\"' in s and "yorum" not in s, "ters bölüyle biten ham dizge sonrası yorum sökülmedi"
    assert "let c = '\"'; let d = '\\'';" in s, "karakter sabiti bozuldu"
    assert "<'a>(x: &'a str)" in s, "ömür adı karakter sabiti sanıldı"


def test_kotlin_sablon_icindeki_dizge_ve_ham_dizge():
    k = 'val a = "x ${f("//y")} z" // yorum\nval b = """ham // degil """ /* blok */\n'
    s = kotlin_soy(k)
    _korur(s, k)
    assert '"x ${f("//y")} z"' in s and "yorum" not in s, "şablon içindeki iç dizge bozuldu"
    assert '"""ham // degil """' in s and "blok" not in s
