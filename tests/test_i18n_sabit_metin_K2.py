# -*- coding: utf-8 -*-
"""K-2 · SABİT METİN YASAĞI (T14) — kapsam defterinde (`i18n/kapsam.json`) `tamam` işaretli dosyada kullanıcıya görünebilecek SABİT metin
kalmaz; gerekçeli muaflar (dosyanın `muaf` listesi + `genelMuaf`) hariç. Çıkarıcı göç aracıyla AYNI (`scripts/i18n/cikar.py`).
Ayrıca: yüzeylerin HER kaynak dosyası defterde (yeni dosya sınıflandırılmadan geçemez); `muaf` dosya gerekçeli; göç bitince
(`k2Kapsam: "hepsi"`) `bekliyor` dosya kalmaz.

TS / TSX dosyaları için node + TypeScript gerekir (`apps/ui|apps/web/node_modules/typescript`); yoksa O KISIM gerekçeyle atlanır — aynı
denetimi jest tarafı (`apps/ui/src/i18n/__tests__/sabitMetinYasagi.test.ts`) her koşuda yapar. Python / Rust / HTML / NSIS her koşuda.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from scripts.i18n import cikar, kapsam, ortak  # noqa: E402

DEFTER = json.loads((KOK / "i18n" / "kapsam.json").read_text(encoding="utf-8"))
_TS_VAR = bool(shutil.which("node")) and any(
    (KOK / a / "node_modules" / "typescript").is_dir() for a in ("apps/ui", "apps/web")
)
_TS = (".ts", ".tsx", ".js", ".jsx")


def _ihlaller(dosyalar: list[str], defter: dict = DEFTER) -> list[str]:
    """Muaf kuralı TEK yerde: `kapsam.muaf_mi` (dosyanın muaf listesi · genelMuaf · genelMuafDesen) — `katalog.py taban` ile aynı."""
    r = cikar.cikar(dosyalar, KOK)
    assert not r["hatalar"], r["hatalar"]
    return [
        f"{a['dosya']}:{a['satir']} [{a['tur']}] {a['metin']!r}"
        for a in r["adaylar"]
        if not kapsam.muaf_mi(defter, a["dosya"], a["metin"], a["tur"])  # I18NI-A2.2: muaf yalnız kaydedildiği türlerde
    ]


def _tamam(ts: bool) -> list[str]:
    return [d for d, k in DEFTER["dosyalar"].items() if k["durum"] == "tamam" and (d.endswith(_TS) == ts)]


def test_K2_tamam_dosyalarda_sabit_metin_yok_python_rust_html_nsis():
    dosyalar = _tamam(ts=False)
    if not dosyalar:
        pytest.skip("defterde henüz TS dışı tamam dosya yok (pilotla gelir) — boş kümede koşmaz")
    sorun = _ihlaller(dosyalar)
    assert not sorun, (
        "tamam dosyada sabit metin (katalog anahtarına taşıyın ya da GEREKÇEYLE muaf yazın):\n" + "\n".join(sorun)
    )


@pytest.mark.skipif(
    (not _TS_VAR) and not capraz.ZORUNLU,
    reason="node / TypeScript yok (npm ci) — jest tarafı sabitMetinYasagi.test.ts aynı denetimi yapar",
)
def test_K2_tamam_dosyalarda_sabit_metin_yok_ts_tsx():
    sorun = _ihlaller(_tamam(ts=True))
    assert not sorun, "tamam dosyada sabit metin:\n" + "\n".join(sorun)


def test_K2_her_yuzey_dosyasi_defterde():
    eksik = [f for y in ortak.YUZEYLER for f in ortak.yuzey_dosyalari(y, KOK) if f not in DEFTER["dosyalar"]]
    assert not eksik, (
        f"kapsam defterinde olmayan kaynak dosya(lar): {eksik} → `scripts/i18n/kapsam.py uret` ve grubunu doğrulayın"
    )


def test_K2_muaf_dosya_ve_muaf_metin_GEREKCELI():
    for d, k in DEFTER["dosyalar"].items():
        if k["durum"] == "muaf":
            assert k.get("not", "").strip(), f"{d}: muaf dosya gerekçesiz"
        for m in k.get("muaf", []):
            assert m.get("gerekce", "").strip(), f"{d}: muaf metin gerekçesiz: {m.get('metin')!r}"
    for m in DEFTER.get("genelMuaf", []):
        assert m.get("gerekce", "").strip(), f"genel muaf gerekçesiz: {m}"


def test_K2_goc_bitince_bekleyen_dosya_kalmaz():
    if DEFTER.get("k2Kapsam") != "hepsi":
        pytest.skip("göç sürüyor (k2Kapsam = tamam-dosyalar) — son parti 'hepsi' yapar")
    bekleyen = [d for d, k in DEFTER["dosyalar"].items() if k["durum"] == "bekliyor"]
    assert not bekleyen, f"göç bitti denmiş ama bekleyen dosya var: {bekleyen}"


def test_K2_KARSIT_cikarici_sabit_metni_YAKALAR(tmp_path):
    """Kapının kör olmadığı: Python + Rust + NSIS örneklerinde bilinen sabit metin aday çıkar."""
    py, _ = cikar.py_adaylari(
        "x.py",
        'from fastapi import HTTPException\ndef f():\n    raise HTTPException(400, detail="Hasta bulunamadı.")\n',
    )
    rs = cikar.rust_adaylari("x.rs", 'fn f() -> Result<(), String> { Err("Kurulum başarısız oldu.".into()) }\n')
    ns = cikar.nsis_adaylari("x.nsi", 'DetailPrint "PEMF: kaldırma tamamlandı."\n')
    assert [a["metin"] for a in py] == ["Hasta bulunamadı."]
    assert [a["metin"] for a in rs] == ["Kurulum başarısız oldu."]
    assert [a["metin"] for a in ns] == ["PEMF: kaldırma tamamlandı."]


def test_K2_KARSIT_muaf_kurali_TURKCE_metni_YUTMAZ():
    """Genel muaf (ürün adı / birim / kod belirteci / CSS sınıfı deseni) Türkçe arayüz metnini yanlışlıkla muaf saymamalı."""
    dosya = "apps/ui/src/screens/AuthScreen.tsx"
    for metin in ("e-posta", "Ön-izleme", "Kaydet", "Hasta bulunamadı.", "text muted", "Bobin"):
        assert not kapsam.muaf_mi(DEFTER, dosya, metin), metin
    for metin in ("PEMF Vet", "Hz", "btn-primary", "text-muted hover:text-fg", "rounded-md px-3 py-2.5 text-sm"):
        assert kapsam.muaf_mi(DEFTER, dosya, metin), metin
