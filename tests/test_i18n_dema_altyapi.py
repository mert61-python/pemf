# -*- coding: utf-8 -*-
"""I18N-0 · DEMA SİMÜLATÖRÜ ALTYAPISI (Y159) — `dema-terapi-simülatörü/src/i18n` (i18next YOK: tek sayfa, dil sayfa içinde değişmez).

Kilitlenen davranış (GERÇEK `index.ts` / `main.tsx` TypeScript derleyicisiyle CommonJS'e çevrilip node'da KOŞTURULUR — metin pini değil):
  * sayfa dili `?dil=tr|en` > tarayıcı dili (`tr*` → tr, diğer → en); bayrak (`I18N_EN_ACIK`) KAPALIYKEN her durumda tr;
  * eksik İngilizce anahtar Türkçe değere düşer (boş metin yok); `{{ad}}` yer tutucuları doldurulur;
  * `main.tsx` sekme başlığını katalogdan kurar ve `<html lang>`ı SAYFA DİLİNE eşitler (Y162, yayın hazırlığı: CSS `uppercase` dile göre
    büyütür — göç öncesi `lang="en"` Türkçede "KARE SINYALI" / "DERI" yazıyordu; `tr` ile "KARE SİNYALİ" / "DERİ"); `index.html` varsayılanı `tr`;
  * iki katalogda aynı anahtarlar, İngilizce değerler boş değil.
Uygulama tarafı (çerçeve `?dil=` ile yüklenir, dil değişince yeniden yüklenir): jest
`apps/ui/src/screens/__tests__/DemaSimulatorScreen.I18N0.dilParametresi.test.tsx`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
DEMA = KOK / "dema-terapi-simülatörü"
I18N = DEMA / "src" / "i18n"
sys.path.insert(0, str(KOK / "scripts"))

from i18n import ortak  # noqa: E402

_NODE = shutil.which("node")
_TS_VAR = any(
    (KOK / a / "node_modules" / "typescript" / "package.json").is_file() for a in ("apps/ui", "apps/web", DEMA.name)
)
ts_gerekli = pytest.mark.skipif(
    not (_NODE and _TS_VAR), reason="node ya da apps/ui|apps/web node_modules/typescript yok (npm ci)"
)

# Koşum: TS → CommonJS (TypeScript derleyicisi), göreli içe aktarmalar gerçek dosyadan, `ozel` eşlemi sahte modüller.
_KOSUM = r"""
const fs = require("fs");
const path = require("path");
const ts = require(process.argv[2]).tsYukle();
const DEMA = process.argv[3];
const senaryolar = JSON.parse(fs.readFileSync(process.argv[4], "utf8"));

function yukle(dosya, ozel) {
  const kod = ts.transpileModule(fs.readFileSync(dosya, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
    fileName: dosya,
  }).outputText;
  const modul = { exports: {} };
  const iste = (ad) => {
    if (Object.prototype.hasOwnProperty.call(ozel, ad)) return ozel[ad];
    if (!ad.startsWith(".")) throw new Error("beklenmeyen paket: " + ad);
    const y = path.resolve(path.dirname(dosya), ad);
    if (y.endsWith(".json")) return JSON.parse(fs.readFileSync(y, "utf8"));
    for (const aday of [y, y + ".ts", y + ".tsx", path.join(y, "index.ts")]) {
      if (fs.existsSync(aday) && fs.statSync(aday).isFile()) return yukle(aday, ozel);
    }
    throw new Error("bulunamadı: " + ad);
  };
  new Function("require", "module", "exports", kod)(iste, modul, modul.exports);
  return modul.exports;
}

const sonuc = [];
for (const s of senaryolar) {
  // node ≥ 21'de `navigator` yerleşik salt-okur alıcı: düz atama SESSİZCE düşer, makinenin yereli sızar (ölçüldü) → defineProperty.
  Object.defineProperty(globalThis, "location", { value: { search: s.arama }, configurable: true, writable: true });
  Object.defineProperty(globalThis, "navigator", { value: { language: s.tarayici }, configurable: true, writable: true });
  const ozel = {};
  if (s.bayrak !== null) ozel["./bayrak"] = { I18N_EN_ACIK: s.bayrak };
  if (s.en !== null) ozel["./en.json"] = s.en;
  if (s.tr !== null) ozel["./tr.json"] = s.tr;
  if (s.ana) {
    const belge = { documentElement: { lang: "__ozgun__" }, title: "", getElementById: () => ({}) };
    globalThis.document = belge;
    Object.assign(ozel, {
      react: { StrictMode: "StrictMode" },
      "react/jsx-runtime": { jsx: () => null, jsxs: () => null },
      "react-dom/client": { createRoot: () => ({ render: () => undefined }) },
      "./App.tsx": { default: () => null },
      "./index.css": {},
    });
    yukle(path.join(DEMA, "src", "main.tsx"), ozel);
    sonuc.push({ lang: belge.documentElement.lang, title: belge.title });
    continue;
  }
  const m = yukle(path.join(DEMA, "src", "i18n", "index.ts"), ozel);
  sonuc.push({ dil: m.DIL, metin: m.t(s.anahtar, s.p || undefined) });
}
process.stdout.write(JSON.stringify(sonuc));
"""


def _senaryo(
    arama: str = "",
    tarayici: str = "tr-TR",
    bayrak: bool | None = None,
    anahtar: str = "baslik.uygulama",
    en: dict | None = None,
    tr: dict | None = None,
    p: dict | None = None,
    ana: bool = False,
) -> dict:
    return {
        "arama": arama,
        "tarayici": tarayici,
        "bayrak": bayrak,
        "anahtar": anahtar,
        "en": en,
        "tr": tr,
        "p": p,
        "ana": ana,
    }


def _kos(tmp_path: Path, senaryolar: list[dict]) -> list[dict]:
    betik = tmp_path / "kosum.cjs"
    betik.write_text(_KOSUM, encoding="utf-8")
    girdi = tmp_path / "senaryolar.json"
    girdi.write_text(json.dumps(senaryolar, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run(
        [_NODE, str(betik), str(KOK / "scripts" / "i18n" / "cikar_ts.cjs"), str(DEMA), str(girdi)],
        capture_output=True,
    )
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    return json.loads(r.stdout.decode("utf-8"))


def _katalog(dil: str) -> dict:
    return json.loads((I18N / f"{dil}.json").read_text(encoding="utf-8"))


def test_kataloglar_ayni_anahtarlar_ingilizce_dolu():
    tr, en = ortak.duzlestir(_katalog("tr")), ortak.duzlestir(_katalog("en"))
    assert set(tr) == set(en), f"anahtar eşliği bozuk: yalnız tr {set(tr) - set(en)} · yalnız en {set(en) - set(tr)}"
    assert all(str(v).strip() for v in en.values()), "boş İngilizce değer"


def test_bayrak_kaynakta_ANA_DEGERLE_ayni():
    """I18NI-A3.8: eskiden "kaynakta false" pinliydi (bayrağı açan commit'te kırmızı) — DEMA sabiti tek kaynakla (`i18n/bayrak.json`) aynı."""
    from scripts.i18n import bayrak

    deger = "true" if bayrak.ana_deger(KOK) else "false"
    assert f"export const I18N_EN_ACIK: boolean = {deger};" in (I18N / "bayrak.ts").read_text(encoding="utf-8")


@ts_gerekli
def test_bayrak_KAPALI_her_durumda_turkce(tmp_path):
    tr = _katalog("tr")["baslik"]["uygulama"]
    # I18NI-A3.8: kapalı dal AÇIKÇA (`bayrak=False`) — depo bayrağı açıkken de bu kural sınanır
    sonuc = _kos(
        tmp_path,
        [
            _senaryo(arama="?dil=en", tarayici="en-US", bayrak=False),
            _senaryo(tarayici="de-DE", bayrak=False),
            _senaryo(arama="?dil=tr", tarayici="en-GB", bayrak=False),
        ],
    )
    assert sonuc == [{"dil": "tr", "metin": tr}] * 3


@ts_gerekli
def test_bayrak_ACIK_parametre_sonra_tarayici_dili(tmp_path):
    tr, en = _katalog("tr")["baslik"]["uygulama"], _katalog("en")["baslik"]["uygulama"]
    sonuc = _kos(
        tmp_path,
        [
            _senaryo(arama="?dil=en", tarayici="tr-TR", bayrak=True),
            _senaryo(arama="?dil=tr", tarayici="en-US", bayrak=True),
            _senaryo(arama="", tarayici="de-DE", bayrak=True),
            _senaryo(arama="", tarayici="tr", bayrak=True),
            _senaryo(arama="?dil=xx", tarayici="tr-TR", bayrak=True),
        ],
    )
    assert [s["dil"] for s in sonuc] == ["en", "tr", "en", "tr", "tr"]
    assert [s["metin"] for s in sonuc] == [en, tr, en, tr, tr]


@ts_gerekli
def test_eksik_ingilizce_TURKCEYE_duser_yer_tutucu_dolar(tmp_path):
    tr = _katalog("tr")["baslik"]["uygulama"]
    sonuc = _kos(
        tmp_path,
        [
            _senaryo(arama="?dil=en", bayrak=True, en={}),
            _senaryo(tr={"x": {"y": "{{adet}} bobin"}}, anahtar="x.y", p={"adet": 3}),
        ],
    )
    assert sonuc[0] == {"dil": "en", "metin": tr}
    assert sonuc[1]["metin"] == "3 bobin"


@ts_gerekli
def test_main_html_langi_SAYFA_DILINE_esitler_sekme_basligi_katalogdan(tmp_path):
    """Y162 (S-I18N.10, sahip 2026-10-20): `<html lang>` SAYFA DİLİNİ taşır — CSS `uppercase` dile göre büyütür; Türkçe sayfada `tr`
    olmalı ki "Kare sinyali" → "KARE SİNYALİ", "Deri" → "DERİ" olsun (göç öncesi `lang="en"` "KARE SINYALI" / "DERI" yazıyordu).
    Bu test I18N-0'daki "lang'a dokunmaz" kilidinin BİLEREK ters çevrilmiş hâlidir (yayın hazırlığı, YH A1)."""
    sonuc = _kos(
        tmp_path,
        [
            _senaryo(arama="?dil=en", tarayici="en-US", bayrak=False, ana=True),
            _senaryo(arama="?dil=en", tarayici="tr-TR", bayrak=True, ana=True),
            _senaryo(arama="?dil=tr", tarayici="en-US", bayrak=True, ana=True),
            _senaryo(arama="", tarayici="de-DE", bayrak=True, ana=True),
            _senaryo(arama="", tarayici="tr-TR", bayrak=True, ana=True),
        ],
    )
    tr, en = _katalog("tr")["baslik"]["belge"], _katalog("en")["baslik"]["belge"]
    assert sonuc == [
        {"lang": "tr", "title": tr},
        {"lang": "en", "title": en},
        {"lang": "tr", "title": tr},
        {"lang": "en", "title": en},
        {"lang": "tr", "title": tr},
    ]


def test_index_html_lang_VARSAYILAN_turkce():
    """Y162: betik koşmadan önceki (ve betiksiz) varsayılan dil Türkçe — sayfanın kendi başlığı Türkçe, ürünün varsayılan dili Türkçe.
    Betik yüklenince `main.tsx` sayfa diline (`?dil=` / tarayıcı dili; bayrak kapalıyken tr) eşitler."""
    bas = (DEMA / "index.html").read_text(encoding="utf-8")
    assert '<html lang="tr">' in bas, (
        "DEMA index.html <html lang> Türkçe değil — Türkçe büyük İ (SİNYALİ / DERİ) bozulur"
    )
    assert '<html lang="en">' not in bas
