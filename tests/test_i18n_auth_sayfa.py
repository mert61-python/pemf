# -*- coding: utf-8 -*-
"""I18N-P1 · AUTH SAYFALARI (`apps/ui/auth-pages/*.html`: şifre sıfırlama / e-posta onayı) — uygulamanın DIŞINDA barındırılan statik
sayfaların iki dilli metni.

Sözleşme (her biri aşağıda bir test):
  1. `i18n_katalog.js` ÜRETİLMİŞTİR: katalog (`authSayfa.*`) + bayrakla (`i18n/bayrak.json`) ayrışırsa kırmızı (`auth_uret.py --denetle`).
  2. Sayfalardaki her `data-i18n*` / `tf("…")` anahtarı tr + en katalogda VAR, yer tutucu kümesi AYNI; katalogdaki her anahtar kullanılıyor.
  3. Sayfa HTML'inde SABİT Türkçe metin kalmadı (metin yalnız katalogdan dolar) — TR görünüm göç öncesiyle aynı kalsın diye aşağıdaki
     BİREBİR Türkçe değerler (göç öncesi sayfadan) kilitlidir.
  4. ÇALIŞMA ZAMANI (node `vm`, sahte `window` / `document`): bayrak KAPALIYKEN sayfa HER ZAMAN Türkçedir (tarayıcı dili `en-US` ve `?dil=en`
     olsa bile); bayrak açıkken `?dil=` > tarayıcı dili; `uygulaDil()` `data-i18n` / `data-i18n-html` / `data-i18n-placeholder` doldurur.
MUTASYON: katalogdan bir TR değeri değişirse (3) ya da dosya yeniden üretilmeden katalog değişirse (1) KIRMIZI.
"""

from __future__ import annotations

import html.parser
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from scripts.i18n import auth_uret, ortak  # noqa: E402

SAYFALAR = ("apps/ui/auth-pages/reset.html", "apps/ui/auth-pages/verified.html")
TR_HARF = re.compile(r"[çğıöşüÇĞİÖŞÜ]")

#: Göç ÖNCESİ sayfalardaki Türkçe (bayt bayt): anahtar → değer (çıkarıcının `ham` değerleri; `taban-tr-metinler.json`).
TR_BIREBIR = {
    "authSayfa.reset.sayfaBasligi": "PEMF Vet — Yeni Şifre Belirle",
    "authSayfa.reset.baslik": "Yeni Şifre Belirle",
    "authSayfa.reset.aciklama": "Hesabın için yeni bir şifre gir.",
    "authSayfa.reset.sifreYer": "Yeni şifre (en az 6 karakter)",
    "authSayfa.reset.sifreTekrarYer": "Yeni şifre (tekrar)",
    "authSayfa.reset.guncelle": "Şifreyi Güncelle",
    "authSayfa.reset.hata.kurallar": "Şifre en az 8 karakter olmalı; büyük harf, küçük harf ve rakam içermeli.",
    "authSayfa.reset.hata.eslesmiyor": "Şifreler eşleşmiyor.",
    "authSayfa.reset.guncelleniyor": "Güncelleniyor…",
    "authSayfa.reset.guncellendiBaslik": "Şifren güncellendi ✓",
    "authSayfa.ortak.uygulamayaDon": "Uygulamaya Dön",
    "authSayfa.verified.sayfaBasligi": "PEMF Vet — E-posta Onaylandı",
    "authSayfa.verified.baslik": "E-postan onaylandı!",
    "authSayfa.verified.aciklama": "Hesabın başarıyla doğrulandı. Artık <b>PEMF Vet</b> uygulamasına geri dönüp e-posta ve şifrenle giriş yapabilirsin.",
    "authSayfa.verified.kapatabilirsin": "Bu sekmeyi güvenle kapatabilirsin.",
}


def _kaynak(yol: str) -> str:
    return (KOK / yol).read_text(encoding="utf-8")


def _katalog(dil: str) -> dict[str, str]:
    return auth_uret._duz(KOK, dil)


def _kullanilan(metin: str) -> set[str]:
    return ortak.kullanilan_anahtarlar(metin)


def test_uretilmis_dosya_katalog_ve_bayrakla_ayni():
    assert auth_uret.main(["--denetle"]) == 0


def test_uretilmis_dosyadaki_bayrak_ana_kaynakla_ayni():
    js = _kaynak(auth_uret.JS_YOLU)
    m = re.search(r"var EN_ACIK = (true|false);", js)
    assert m, "i18n_katalog.js'te EN_ACIK sabiti yok"
    assert (m.group(1) == "true") == auth_uret.bayrak_acik(KOK)


@pytest.mark.parametrize("sayfa", SAYFALAR)
def test_sayfa_anahtarlari_iki_katalogda_ve_yer_tutucular_ayni(sayfa):
    anahtarlar = _kullanilan(_kaynak(sayfa))
    assert anahtarlar, f"{sayfa}: hiç katalog anahtarı kullanmıyor"
    tr, en = _katalog("tr"), _katalog("en")
    eksik = sorted(k for k in anahtarlar if not tr.get(k, "").strip() or not en.get(k, "").strip())
    assert not eksik, f"{sayfa}: tr / en katalogda eksik: {eksik}"
    for k in anahtarlar:
        assert ortak.yer_tutuculari(tr[k]) == ortak.yer_tutuculari(en[k]), k


def test_katalogdaki_her_anahtar_bir_sayfada_kullaniliyor():
    kullanilan = set().union(*(_kullanilan(_kaynak(s)) for s in SAYFALAR))
    artik = sorted(set(_katalog("tr")) - kullanilan)
    assert not artik, f"authSayfa anahtarı hiçbir sayfada kullanılmıyor (ölü anahtar): {artik}"


class _MetinDugumleri(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.metinler: list[str] = []
        self._ust: list[str] = []

    def handle_starttag(self, tag, attrs):
        self._ust.append(tag)
        for k, v in attrs:
            if k in ("placeholder", "title", "aria-label", "alt") and v and TR_HARF.search(v):
                self.metinler.append(f"{tag}[{k}]={v}")

    def handle_endtag(self, tag):
        while self._ust and self._ust[-1] != tag:
            self._ust.pop()
        if self._ust:
            self._ust.pop()

    def handle_data(self, data):
        if self._ust and self._ust[-1] in ("script", "style"):
            return
        if data.strip() and TR_HARF.search(data):
            self.metinler.append(data.strip())


@pytest.mark.parametrize("sayfa", SAYFALAR)
def test_sayfada_sabit_turkce_metin_kalmadi(sayfa):
    p = _MetinDugumleri()
    p.feed(_kaynak(sayfa))
    assert not p.metinler, f"{sayfa}: sabit Türkçe metin kaldı (katalogdan dolmalı): {p.metinler}"


def test_turkce_gorunum_goc_oncesiyle_birebir():
    tr = _katalog("tr")
    for k, beklenen in TR_BIREBIR.items():
        assert tr.get(k) == beklenen, f"{k}: TR değeri değişmiş: {tr.get(k)!r} ≠ {beklenen!r}"


# ── çalışma zamanı (node vm) ───────────────────────────────────────────────────────────────────────────────────
_NODE = shutil.which("node")

_HARNESS = r"""
const vm = require("vm"); const fs = require("fs");
const [jsYol, bayrak, dilTarayici, sorgu] = process.argv.slice(1);
let kod = fs.readFileSync(jsYol, "utf8");
kod = kod.replace(/var EN_ACIK = (true|false);/, "var EN_ACIK = " + bayrak + ";");
const ogeler = [
  { nitelik: { "data-i18n": "authSayfa.reset.baslik" }, textContent: "", innerHTML: "" },
  { nitelik: { "data-i18n-html": "authSayfa.verified.aciklama" }, textContent: "", innerHTML: "" },
  { nitelik: { "data-i18n-placeholder": "authSayfa.reset.sifreYer" }, textContent: "", innerHTML: "", ph: "" },
];
for (const e of ogeler) { e.getAttribute = (a) => e.nitelik[a]; e.setAttribute = (a, v) => { if (a === "placeholder") e.ph = v; }; }
const kok = { lang: "", documentElement: { setAttribute: (a, v) => { kok.lang = v; } },
  querySelectorAll: (sec) => ogeler.filter((e) => sec.slice(1, -1) in e.nitelik) };
const pencere = { document: kok, location: { search: sorgu || "" }, navigator: { language: dilTarayici } };
const ctx = vm.createContext({ window: pencere, URLSearchParams });
vm.runInContext(kod, ctx);
pencere.uygulaDil();
console.log(JSON.stringify({ dil: pencere.PEMF_DIL, lang: kok.lang, baslik: ogeler[0].textContent, aciklama: ogeler[1].innerHTML, ph: ogeler[2].ph,
  yok: pencere.tf("authSayfa.yok.anahtar") }));
"""


def _kos(bayrak: str, tarayici: str, sorgu: str = "") -> dict:
    cikti = subprocess.run(
        [_NODE, "-e", _HARNESS, str(KOK / auth_uret.JS_YOLU), bayrak, tarayici, sorgu],
        capture_output=True,
        check=True,
        timeout=60,
    ).stdout.decode("utf-8")
    return json.loads(cikti)


@pytest.mark.skipif(not _NODE, reason="node yok — çalışma zamanı denetimi atlandı")
def test_bayrak_kapaliyken_sayfa_her_zaman_turkce():
    for tarayici, sorgu in (("en-US", ""), ("en-US", "?dil=en"), ("de-DE", ""), ("tr-TR", "")):
        r = _kos("false", tarayici, sorgu)
        assert r["dil"] == "tr" and r["lang"] == "tr", (tarayici, sorgu, r)
        assert r["baslik"] == "Yeni Şifre Belirle"
        assert r["aciklama"] == TR_BIREBIR["authSayfa.verified.aciklama"]
        assert r["ph"] == "Yeni şifre (en az 6 karakter)"
        assert r["yok"] == "authSayfa.yok.anahtar"  # eksik anahtar çökmez, anahtarı gösterir


@pytest.mark.skipif(not _NODE, reason="node yok — çalışma zamanı denetimi atlandı")
def test_bayrak_acikken_dil_secimi():
    assert _kos("true", "en-US")["baslik"] == "Set a New Password"
    assert _kos("true", "de-DE")["dil"] == "en"
    assert _kos("true", "tr-TR")["dil"] == "tr"
    assert _kos("true", "en-US", "?dil=tr")["baslik"] == "Yeni Şifre Belirle"
    assert _kos("true", "tr-TR", "?dil=en")["lang"] == "en"
    r = _kos("true", "en-US")
    assert r["ph"] == "New password (at least 6 characters)"
    assert r["aciklama"].endswith("sign in with your email and password.") and "<b>PEMF Vet</b>" in r["aciklama"]
