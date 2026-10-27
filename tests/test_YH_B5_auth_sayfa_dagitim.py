# -*- coding: utf-8 -*-
"""YH B5 (S-I18NI-A3.a) — hesap sayfaları (şifre sıfırlama / e-posta onayı) uygulamanın DIŞINDA, GitHub Pages'te SAHİBİN ELLE yaptığı kopyayla
barınır (betik / iş akışı YOK — `i18n/KURALLAR.md` §4.13b). Sayfaların HTML'inde metin YOKTUR; metin `i18n_katalog.js`'ten dolar.

Kapı:
  1. Dağıtım kümesi: `apps/ui/auth-pages/` TAM ÜÇ dosya (reset.html · verified.html · i18n_katalog.js) — yeni dosya eklenirse yönerge de güncellenir.
  2. Her sayfa katalogu AYNI dizinden (`<script src="i18n_katalog.js">`) ve satır içi betiklerden ÖNCE yükler.
  3. Yayın yönergesi (`BUILD.md` §6) ve `KURALLAR.md` §4.13b "üç dosya BİRLİKTE kopyalanır" der ve üç adı sayar.
  4. ÇALIŞMA ZAMANI (node vm, sahte DOM): katalog eksik kopyalansa da (yüklenmediyse) satır içi betik DÜŞMEZ — şifre sıfırlama düğmesi bağlanır
     (bugüne dek ilk satır `uygulaDil()` ReferenceError ile bütün sıfırlama mantığını durduruyordu).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parent.parent
DIZIN = KOK / "apps" / "ui" / "auth-pages"
KUME = {"reset.html", "verified.html", "i18n_katalog.js"}
SAYFALAR = ("reset.html", "verified.html")


def test_dagitim_kumesi_TAM_UC_dosya():
    assert {p.name for p in DIZIN.iterdir() if p.is_file()} == KUME


@pytest.mark.parametrize("sayfa", SAYFALAR)
def test_sayfa_katalogu_ayni_dizinden_ve_ONCE_yukler(sayfa):
    s = (DIZIN / sayfa).read_text(encoding="utf-8")
    i = s.find('<script src="i18n_katalog.js"></script>')
    assert i >= 0, f"{sayfa}: katalog göreli adla yüklenmiyor"
    satir_ici = [m.start() for m in re.finditer(r"<script>", s)]
    assert satir_ici and all(i < j for j in satir_ici), f"{sayfa}: satır içi betik katalogdan önce"


def test_yayin_yonergesi_UC_DOSYA_BIRLIKTE_der():
    build = (KOK / "BUILD.md").read_text(encoding="utf-8")
    kurallar = (KOK / "i18n" / "KURALLAR.md").read_text(encoding="utf-8")
    satir = [x for x in build.splitlines() if "auth-pages" in x and "BİRLİKTE" in x]
    assert satir, "BUILD.md §6'da hesap sayfaları için 'üç dosya BİRLİKTE' satırı yok"
    blok = "\n".join(build.splitlines()[build.splitlines().index(satir[0]) : build.splitlines().index(satir[0]) + 4])
    for ad in KUME:
        assert ad in blok, f"BUILD.md hesap sayfası satırı {ad} adını saymıyor"
    assert "üç dosya BİRLİKTE" in kurallar and all(ad in kurallar for ad in KUME)


_NODE = shutil.which("node")
_KOSUM = r"""
const vm = require("vm"); const fs = require("fs");
const [htmlYol] = process.argv.slice(1);
const html = fs.readFileSync(htmlYol, "utf8");
const betikler = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
const ogeler = {};
const oge = (id) => (ogeler[id] = ogeler[id] || { id, value: "", textContent: "", innerHTML: "", className: "", style: {}, onclick: null });
const belge = { getElementById: oge, querySelectorAll: () => [], documentElement: { setAttribute() {} } };
const hatalar = [];
const konsol = { error: (...a) => hatalar.push(a.join(" ")), log() {}, warn() {} };
const supabase = { createClient: () => ({ auth: { onAuthStateChange() {}, updateUser: async () => ({}) } }) };
// tarayıcıdaki gibi `window` = genel nesne (window.x = … atanınca çıplak `x` görülür)
const ctx = vm.createContext({ document: belge, console: konsol, supabase, URLSearchParams, location: { search: "" }, navigator: { language: "tr-TR" } });
ctx.window = ctx;
let dustu = null;
try { for (const b of betikler) vm.runInContext(b, ctx); } catch (e) { dustu = String(e); }
console.log(JSON.stringify({ dustu, betik: betikler.length, dugmeBagli: typeof (ogeler.go && ogeler.go.onclick) === "function", hatalar }));
"""


@pytest.mark.skipif((not _NODE) and not capraz.ZORUNLU, reason="node yok — çalışma zamanı denetimi atlandı")
@pytest.mark.parametrize("sayfa", SAYFALAR)
def test_katalog_YUKLENMEDIYSE_betik_dusmez(sayfa):
    r = json.loads(
        subprocess.run(
            [_NODE, "-e", _KOSUM, str(DIZIN / sayfa)], capture_output=True, check=True, timeout=60
        ).stdout.decode("utf-8")
    )
    assert r["betik"] >= 1
    assert r["dustu"] is None, f"{sayfa}: katalog yokken satır içi betik düştü: {r['dustu']}"
    if sayfa == "reset.html":
        assert r["dugmeBagli"], "şifre sıfırlama düğmesi bağlanmadı (sıfırlama mantığı koşmadı)"
    assert any("i18n_katalog.js" in h for h in r["hatalar"]), "eksik katalog konsola yazılmadı (teşhis izi yok)"
