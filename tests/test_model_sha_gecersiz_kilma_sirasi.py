# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""MODEL ACILMADAN ONCE SHA KAYDI GECERSIZ KILINIR (denetim 2026-08-23, bulgu C12).

OLCULEN DURUM: `flow.rs`te model paketi acan IKI dongu var ve AYNI kurali paylasmalari gerekiyordu:

  · `profilleri_yenile`  → `record_model_sha(..., "")` ONCE, extract SONRA, gercek sha EN SON. ✅
  · `install_profiles`   → extract ONCE, sha SONRA. ❌ (arada gecersiz kilma YOK)

NEDEN ONEMLI: `repair()` dogrudan `install_profiles`e duser ve onarim senaryosunda
`installed_packages.json` ZATEN o modelin dogru sha'sini tasir. Model zip'i acilirken elektrik
kesilir / kullanici iptal ederse diskte YARIM (kesik .onnx) bir model agaci kalir ama kayit hala
manifest sha'siyla ESLESIR → `pending_updates` o profili "guncel" sayar ve oto-guncelleme onu bir
daha ASLA yenilemez. `kurulum_saglam_mi` yalniz runtime agacina baktigi icin client "Hazir!" der.

⚠️ D5.52 (B-10.144, 2026-10-27): bu dosya eskiden HAM METINDE sira ariyordu — `if false { record_model_sha(…, "") }`
mutanti metni yerinde biraktigi icin YESIL kaliyordu. Kural artik TEK yerde (`flow.rs::profil_modelini_ac`) ve DAVRANISI
Rust birim testleri olcer (`flow::tests::D5_52_*`: acilim duserse kayit BOS kalir, profil kurulu isaretlenmez; basarida gercek
sha yazilir). Bu dosya YAPIYI kilitler (yorum-soyulmus kaynakta): iki model dongusu de o tek yardimciyi kullanir, kendi kopya
`record_model_sha` / acilim satirini tasimaz; yardimcinin sirasi gecersiz-kil → ac → gercek-sha.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from kaynak_soyucu import rust_soy

_KOK = Path(__file__).resolve().parents[1]
_FLOW = _KOK / "launcher" / "core" / "src" / "flow.rs"


@pytest.fixture(scope="module")
def kaynak() -> str:
    return rust_soy(_FLOW.read_text(encoding="utf-8", errors="replace"))


def _govde(kaynak: str, fonksiyon: str) -> str:
    m = re.search(rf"\bfn {re.escape(fonksiyon)}\s*\(", kaynak)
    assert m, f"`{fonksiyon}` bulunamadi — flow.rs bicimi degismis olabilir"
    sonraki = re.search(r"\n(?:pub(?:\(crate\))?\s+)?fn\s+\w+\s*\(", kaynak[m.end() :])
    return kaynak[m.end() : m.end() + (sonraki.start() if sonraki else len(kaynak))]


@pytest.mark.parametrize("fonksiyon", ["install_profiles", "profilleri_yenile"])
def test_KRITIK_iki_model_dongusu_TEK_sira_yardimcisini_kullanir(kaynak, fonksiyon):
    """🔴 'Ayni kural iki yerde, biri unutulmus' (bu deponun 1 numarali deseni) — kopya kural geri gelmesin."""
    g = _govde(kaynak, fonksiyon)
    assert re.search(r"\bprofil_modelini_ac\s*\(", g), (
        f"`{fonksiyon}` model zip'lerini `profil_modelini_ac` DISINDA aciyor — gecersiz kilma sirasi (C12) bu yolda olculmez"
    )
    assert "record_model_sha" not in g, (
        f"`{fonksiyon}` model sha'sini yardimci DISINDA yaziyor — yarida kesilen acilim 'guncel' kaydi birakabilir (C12)"
    )


def test_KRITIK_yardimci_GECERSIZ_KIL_AC_GERCEK_SHA_sirasinda(kaynak):
    g = _govde(kaynak, "profil_modelini_ac")
    i_gecersiz = g.find('record_model_sha(install_root, name, "")')
    i_ac = g.find("ac(model_zip)?")
    i_gercek = g.find("record_model_sha(install_root, name, gercek_sha)")
    assert -1 not in (i_gecersiz, i_ac, i_gercek), f"yardimcinin uc adimi yerinde degil: {(i_gecersiz, i_ac, i_gercek)}"
    assert i_gecersiz < i_ac < i_gercek, "sira bozuk: once gecersiz kil, sonra ac, EN SON gercek sha"
