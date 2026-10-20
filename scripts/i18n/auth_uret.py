# -*- coding: utf-8 -*-
"""AUTH SAYFALARI KATALOĞUNDAN ÜRETİLEN DOSYA (I18N-P1) — elle DÜZENLENMEZ; tek kaynak arayüz kataloğunun `authSayfa.*` alt ağacıdır
(`apps/ui/src/i18n/{tr,en}/authSayfa.json`).

`apps/ui/auth-pages/*.html` Supabase dönüş sayfalarıdır (şifre sıfırlama / e-posta onayı); uygulamanın DIŞINDA, GitHub Pages'te barındırılır ve
i18next'e erişemez. Sayfalar metni `data-i18n="authSayfa.…"` öznitelikleri ve `tf("authSayfa.…")` çağrılarıyla bu ÜRETİLMİŞ dosyadan alır:

    apps/ui/auth-pages/i18n_katalog.js  — katalog (düz anahtar → metin, tr + en) + küçük çalışma zamanı (`tf`, `uygulaDil`)

Dil seçimi: İngilizce bayrağı KAPALIYKEN (`i18n/bayrak.json`) sayfa HER ZAMAN Türkçedir (tarayıcı dili yok sayılır). Bayrak açıkken sorgu
parametresi `?dil=tr|en`, yoksa tarayıcı dili (`tr*` → tr, diğer → en). Bayrak `scripts/i18n/bayrak.py` ile açılır / kapanır ve bu dosyayı
birlikte yeniden üretir; `bayrak.py --denetle` ayrışmayı yakalar.

Kullanım:  ..\\python.exe scripts\\i18n\\auth_uret.py [--denetle]   (denetle: yazmaz, fark varsa çıkış 1)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.i18n import ortak  # noqa: E402

JS_YOLU = "apps/ui/auth-pages/i18n_katalog.js"
KOK_ANAHTAR = "authSayfa"
BAYRAK = "i18n/bayrak.json"

CALISMA_ZAMANI = """\
(function () {
  var K = %(katalog)s;
  var EN_ACIK = %(bayrak)s; // i18n/bayrak.json — scripts/i18n/bayrak.py (elle değiştirmeyin)
  var dil = "tr";
  if (EN_ACIK) {
    var q = "";
    try { q = new URLSearchParams(window.location.search).get("dil") || ""; } catch (e) { q = ""; }
    var d = String(q || window.navigator.language || "tr").toLowerCase();
    dil = d.indexOf("tr") === 0 ? "tr" : "en";
  }
  window.PEMF_DIL = dil;
  window.tf = function (anahtar) {
    return (K[dil] && K[dil][anahtar]) || (K.tr && K.tr[anahtar]) || anahtar;
  };
  window.uygulaDil = function () {
    var kok = window.document;
    kok.documentElement.setAttribute("lang", dil);
    kok.querySelectorAll("[data-i18n]").forEach(function (e) { e.textContent = window.tf(e.getAttribute("data-i18n")); });
    kok.querySelectorAll("[data-i18n-html]").forEach(function (e) { e.innerHTML = window.tf(e.getAttribute("data-i18n-html")); });
    kok.querySelectorAll("[data-i18n-placeholder]").forEach(function (e) { e.setAttribute("placeholder", window.tf(e.getAttribute("data-i18n-placeholder"))); });
  };
})();
"""


def _duz(kok: Path, dil: str) -> dict[str, str]:
    agac = ortak.katalog_yukle("arayuz", dil, kok).get(KOK_ANAHTAR, {})
    return ortak.duzlestir(agac, KOK_ANAHTAR)


def bayrak_acik(kok: Path) -> bool:
    return bool(json.loads((kok / BAYRAK).read_text(encoding="utf-8"))["I18N_EN_ACIK"])


def js_metni(kok: Path) -> str:
    katalog = {d: _duz(kok, d) for d in ortak.DILLER}
    govde = json.dumps(katalog, ensure_ascii=False, indent=2, sort_keys=True).replace("\n", "\n  ")
    return (
        "// ÜRETİLMİŞ DOSYA — ELLE DÜZENLEMEYİN. Kaynak: apps/ui/src/i18n/{tr,en}/authSayfa.json · Üreteç: scripts/i18n/auth_uret.py\n"
        "// (katalog / bayrak ile bu dosya ayrışırsa tests/test_i18n_auth_sayfa.py ve `bayrak.py --denetle` kırmızı.)\n"
        + CALISMA_ZAMANI
        % {"katalog": govde, "bayrak": "true" if bayrak_acik(kok) else "false"}
    )


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--denetle", action="store_true")
    ap.add_argument("--kok")
    a = ap.parse_args(argv)
    kok = Path(a.kok).resolve() if a.kok else ortak.KOK
    yeni = js_metni(kok)
    p = kok / JS_YOLU
    eski = p.read_bytes().decode("utf-8") if p.exists() else None
    fark = eski is None or eski.replace("\r\n", "\n") != yeni  # satır sonu (autocrlf) fark sayılmaz
    if a.denetle:
        print(
            "[OK] üretilmiş auth sayfası kataloğu katalogla aynı"
            if not fark
            else f"[FARK] {JS_YOLU} → scripts/i18n/auth_uret.py"
        )
        return 1 if fark else 0
    if fark:
        # Satır sonu mevcut dosyanınkini izler (yeni dosya: LF).
        sonu = "\r\n" if eski is not None and "\r\n" in eski else "\n"
        p.write_bytes(yeni.replace("\n", sonu).encode("utf-8"))
    print(f"yazıldı: {JS_YOLU if fark else 'değişiklik yok'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
