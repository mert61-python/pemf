# -*- coding: utf-8 -*-
"""I18N-P1 · 11a — launcher arayüzü: metin kaynağı `launcher/i18n → ui.*` kataloğu; index.html'deki GERÇEK `t()` / `tf()` / `guideKur()` /
`profName()` / `profAciklama()` kodu Node'da koşar ve katalogla AYNI değerleri verir.

Göçte (ESKİ JS sözlüklerinden kataloğa) 248 karşılaştırma TR / EN BAYT BAYT aynı çıktı (eski sözlük değerleri ↔ yeni katalog + kod):
rapor `DUZELTME-I18N.md § P1`. Bu dosya KALICI kapı: katalog ile kod ayrışırsa / kılavuz dizileri bozulursa / yer tutucu doldurma bozulursa → KIRMIZI.
MUTASYON: `t()` dili ters okursa / `tf` yer tutucuyu boş bırakırsa / `guideKur` kullanım listesini düşürürse / `profName` kataloğu görmezse → KIRMIZI.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from i18n_yardimci import launcher_ui as ui

KOK = Path(__file__).resolve().parents[1]
HTML = KOK / "launcher" / "app" / "ui" / "index.html"
KAT_JS = KOK / "launcher" / "app" / "ui" / "i18n_katalog.js"

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node yok")

_JS = r"""
const fs = require("fs");
const vm = require("vm");
const html = fs.readFileSync(process.argv[2], "utf8").replace(/\r\n/g, "\n");
const katalogJs = fs.readFileSync(process.argv[3], "utf8");
function satir(onek) {
  const i = html.indexOf(onek);
  if (i < 0) throw new Error("bulunamadı: " + onek);
  return html.slice(i, html.indexOf("\n", i));
}
function blok(onek) {
  const i = html.indexOf(onek);
  if (i < 0) throw new Error("bulunamadı: " + onek);
  let d = 0, j = html.indexOf("{", i);
  for (; j < html.length; j++) {
    if (html[j] === "{") d++;
    else if (html[j] === "}") { d--; if (d === 0) break; }
  }
  return html.slice(i, j + 1);
}
const kod = [satir("const t = () =>"), satir("const tf = (k, p) =>"), blok("function guideKur()"),
             satir("const profName = "), satir("const profAciklama = ")]
  .map((s) => s.replace(/^[ \t]*const (t|tf|profName|profAciklama) =/, "var $1 =")).join("\n");
const sonuc = {};
for (const dil of ["tr", "en"]) {
  const ctx = { window: {} };
  vm.createContext(ctx);
  vm.runInContext(katalogJs, ctx);
  vm.runInContext(`var LANG = ${JSON.stringify(dil)};`, ctx);
  vm.runInContext(kod, ctx);
  const ic = (ifade) => JSON.parse(vm.runInContext(`JSON.stringify(${ifade})`, ctx));
  sonuc[dil] = {
    guide: ic("guideKur()"),
    profil: ic('["home", "vet", "research", "yok"].map((k) => [profName(k), profAciklama(k)])'),
    tf: ic('[tf("luReady", { surum: "9.9.9" }), tf("removeFailed", { neden: "x" }), tf("depNotice", { secili: "A", eksik: "B" }), tf("yokAnahtar", {}), tf("backupUnreachable", {})]'),
  };
}
process.stdout.write(JSON.stringify(sonuc));
"""


@pytest.fixture(scope="module")
def sonuc(tmp_path_factory):
    betik = tmp_path_factory.mktemp("lk") / "kod.cjs"
    betik.write_text(_JS, encoding="utf-8")
    r = subprocess.run(["node", str(betik), str(HTML), str(KAT_JS)], capture_output=True, timeout=120)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    return json.loads(r.stdout.decode("utf-8"))


def _sirali(d: dict) -> list:
    return [d[k] for k in sorted(d)]


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_KRITIK_kilavuz_katalogdan_kurulur_dizi_yapisi_ve_degerler(sonuc, dil):
    k = ui(dil)["kilavuz"]
    g = sonuc[dil]["guide"]
    assert g["intro"] == k["intro"] and g["connect"] == k["connect"]
    assert g["stepsTitle"] == k["stepsTitle"] and g["profTitle"] == k["profTitle"]
    assert g["connectTitle"] == k["connectTitle"] and g["troubleTitle"] == k["troubleTitle"]
    assert g["steps"] == [[s["t"], s["b"]] for s in _sirali(k["steps"])]
    assert len(g["steps"]) == 3
    assert g["profiles"] == [
        {"key": p["key"], "who": p["who"], "does": p["does"], "use": _sirali(p["use"])} for p in _sirali(k["profiles"])
    ]
    assert [p["key"] for p in g["profiles"]] == ["home", "vet", "research"], "kılavuz profil SIRASI bozulmuş"
    assert all(len(p["use"]) == 4 for p in g["profiles"]), "kılavuzda profil kullanım maddeleri eksik"
    assert g["trouble"] == [[s["t"], s["b"]] for s in _sirali(k["trouble"])]
    assert len(g["trouble"]) == 4


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_KRITIK_profil_adlari_katalogdan_bilinmeyen_anahtar_kendini_gosterir(sonuc, dil):
    meta = ui(dil)["profilMeta"]
    beklenen = [[meta[k]["ad"], meta[k]["aciklama"]] for k in ("home", "vet", "research")]
    assert sonuc[dil]["profil"][:3] == beklenen
    assert sonuc[dil]["profil"][3] == ["yok", ""], "bilinmeyen profil anahtarı kendini göstermeli, aciklama boş"


def test_KRITIK_tf_yer_tutucuyu_doldurur_eksik_parametre_bos_bilinmeyen_anahtar_kendini_gosterir(sonuc):
    tr = sonuc["tr"]["tf"]
    # D5.28 (B-10.228): ekranda "Client" yok — süreç adı "başlatıcı" (TR DEĞİŞTİ ui.luReady).
    assert tr[0] == "PEMF Vet başlatıcısının 9.9.9 sürümü yayınlandı — uygulamayı kapatıp açtığınızda kurulacak."
    assert tr[1] == "Profil kaldırılamadı: x"
    assert tr[2].startswith("“A” seçildi ama “B” yok.") and "B paketindeki" in tr[2]
    assert tr[3] == "yokAnahtar", "katalogda olmayan anahtar kendini göstermeli (boş metin YOK)"
    assert tr[4].startswith("Yedek hedefi şu an erişilemiyor:  —"), "eksik parametre boş dize olmalı (`undefined` YOK)"
    en = sonuc["en"]["tf"]
    assert en[0] == "PEMF Vet launcher 9.9.9 is available — it will be installed when you close and reopen the app."
    assert en[1] == "Profile could not be removed: x"
    assert en[2].startswith("“A” is selected without “B”.") and "from the B package" in en[2]


def test_aria_etiketleri_dil_degisince_katalogdan_yazilir():
    ham = HTML.read_text(encoding="utf-8")
    # ⚠️ Çalıştırılan İFADE (satır başında) aranır: yorum satırına alınmış kopya "var" sayılmasın (mutasyonla ölçüldü)
    for kimlik, anahtar in (("lang-seg", "langLabel"), ("guide-close", "guideClose")):
        desen = rf'^[ 	]+\$\("{kimlik}"\)\.setAttribute\("aria-label", x\.{anahtar}\);[ 	]*$'
        assert re.search(desen, ham, re.M), f"applyLang {kimlik} aria-label'ını katalogdan yazmıyor"
    assert 'id="lang-seg"' in ham
    assert ui("tr")["langLabel"] == "dil" and ui("tr")["guideClose"] == "kapat"
    assert ui("en")["langLabel"] == "language" and ui("en")["guideClose"] == "close"


def test_guvenlik_duvari_bandi_ve_dugmesi_katalogdan_iki_dilde():
    """Eskiden YALNIZ Türkçeydi (İngilizce arayüzde de Türkçe okunurdu); şimdi iki dilde, TR bayt bayt aynı."""
    ham = HTML.read_text(encoding="utf-8")
    assert "t().fwEngel : t().fwKuralYok" in ham and "t().fwIzinVer" in ham
    tr, en = ui("tr"), ui("en")
    assert tr["fwEngel"] == (
        "Windows güvenlik duvarı bu uygulamanın ağdan bağlantı almasını ENGELLİYOR — "
        "mobil uygulama cihazı bulamaz. Cihaz ekranından kullanım etkilenmez."
    )
    assert tr["fwKuralYok"] == (
        "Mobil uygulama bu cihaza bağlanamayabilir: Windows güvenlik duvarında gelen "
        "bağlantı izni yok. Cihaz ekranından kullanım etkilenmez."
    )
    assert tr["fwIzinVer"] == "İzin ver (yönetici)"
    for k in ("fwEngel", "fwKuralYok", "fwIzinVer"):
        assert en[k] and not any(c in en[k] for c in "çğıöşüÇĞİÖŞÜ"), f"EN {k}: boş ya da Türkçe harf var"
