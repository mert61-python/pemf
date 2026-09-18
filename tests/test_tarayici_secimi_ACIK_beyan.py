# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""TARAYICI SECIMI — ACIK BEYAN, TAHMIN LISTESINI EZER (2026-09-18).

⚠️ OLCULEN ARIZA (site-ci kirmizi, run 35339653466):
`.github/workflows/site.yml` `browser-actions/setup-chrome` ile BILEREK Chrome kuruyordu.
Ama `scripts/responsive_kapisi.tarayici_bul` sabit bir aday listesi tariyor ve o listede
`/usr/bin/microsoft-edge`, `/usr/bin/google-chrome`dan ONCE geliyordu. GitHub runner imaji
artik Edge de tasidigi icin betik, CI'in KURDUGU Chrome'u yok sayip Edge'i secti; o Edge de
runner'da CDP portunu acamadi (D-Bus hatasi) ve kapi KIRMIZI dondu.

⚠️ YANLIS DUZELTME: "tarayici acilmazsa kapiyi atla". Betigin kendi hata metni bunu ZATEN
yasakliyor: *"Tarayici hic kurulamiyorsa kapi ORTAM YOK (cikis 3) ile atlanmali, BU YOL
DEGIL."* Var olan ama calismayan bir tarayiciyi sessizce gecmek, kapiyi anlamsiz kilardi.

DOGRU DUZELTME — iki parca:
  1. `tarayici_bul` adaylarinda `PEMF_TARAYICI` ve `CHROME_PATH` SABIT YOLLARDAN ONCE gelir.
  2. Workflow, kurulum adiminin CIKTISINI (`steps.tarayici.outputs.chrome-path`) dogrudan
     `PEMF_TARAYICI` olarak verir → tahmin listesi devreye HIC girmez.

Sinif: "tahmin listesi, ortamin ACIK beyanini ezdi". Ayni sinif bu depoda daha once
`kapi-ortam-varsayimi-cogunluk` olarak kayda gecmisti.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "responsive_kapisi.py"
WF = KOK / ".github" / "workflows" / "site.yml"


def _adaylar_listesi() -> list[str]:
    """`tarayici_bul` icindeki aday listesini AST ile, SIRASIYLA cikar."""
    agac = ast.parse(BETIK.read_text(encoding="utf-8"))
    fn = next(
        (n for n in ast.walk(agac) if isinstance(n, ast.FunctionDef) and n.name == "tarayici_bul"),
        None,
    )
    assert fn is not None, "`tarayici_bul` YOK — betik degismis, kapi guncellenmeli"
    for n in ast.walk(fn):
        if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "adaylar" for t in n.targets):
            return [ast.unparse(e) for e in n.value.elts]
    raise AssertionError("`adaylar` listesi bulunamadi")


def test_KRITIK_ACIK_BEYAN_sabit_yollardan_ONCE_gelir():
    """⚠️ Kapinin ozu: ortam hangi tarayiciyi kurduysa O kullanilmali.

    MUTASYON: `CHROME_PATH`i listeden cikar ya da sabit yollardan SONRAYA al -> KIRMIZI.
    """
    adaylar = _adaylar_listesi()
    ilk_sabit = next((i for i, a in enumerate(adaylar) if "Program Files" in a or a.startswith("'/usr/")), None)
    assert ilk_sabit is not None, "sabit tarayici yolu hic yok — liste yapisi degismis"

    for beyan in ("PEMF_TARAYICI", "CHROME_PATH"):
        yeri = next((i for i, a in enumerate(adaylar) if beyan in a), None)
        assert yeri is not None, (
            f"`{beyan}` aday listesinde YOK -> ortamin ACIK beyani yok sayilir ve tahmin "
            "listesi kazanir (site-ci'i kirmizi yapan tam buydu)"
        )
        assert yeri < ilk_sabit, (
            f"`{beyan}` sabit yollardan SONRA geliyor (sira {yeri} > {ilk_sabit}) -> "
            "runner'da kurulu olmayan/bozuk bir tarayici once secilebilir"
        )


def test_KRITIK_workflow_KURULAN_tarayiciyi_BETIGE_veriyor():
    """Betik tarafi hazir olsa da workflow beyan etmezse hicbir sey degismez."""
    metin = WF.read_text(encoding="utf-8")
    assert "browser-actions/setup-chrome" in metin, "site-ci tarayici kurmuyor — kapi ortamsiz kalir"
    assert re.search(r"id:\s*tarayici", metin), "tarayici kurulum adiminin `id`si yok -> ciktisi referans edilemez"
    assert re.search(r"PEMF_TARAYICI:\s*\$\{\{\s*steps\.tarayici\.outputs\.chrome-path\s*\}\}", metin), (
        "kurulan tarayicinin yolu `PEMF_TARAYICI` olarak betige VERILMIYOR -> betik yine "
        "tahmin listesine duser ve Edge'i secebilir"
    )


def test_KARSIT_KANIT_kapi_ORTAM_YOK_yolunu_KAPATMIYOR():
    """⚠️ Duzeltme, kapiyi susturmaya DONUSMEMELI.

    Tarayici HIC kurulamadiginda `--zorunlu` olmadan cikis 3 ("ORTAM YOK") donmeli ve
    workflow bunu uyariyla atlamali. Var olan ama calismayan tarayici ise KIRMIZI kalmali —
    betigin kendi hata metni bunu soyluyor.
    """
    metin = BETIK.read_text(encoding="utf-8")
    assert "return 2 if a.zorunlu else 3" in metin, (
        "ORTAM YOK (cikis 3) yolu kaybolmus -> tarayicisiz ortamda kapi kirmizi olur"
    )
    wf = WF.read_text(encoding="utf-8")
    assert '"${KOD:-0}" = "3"' in wf, "workflow cikis 3'u ATLAMA olarak ele almiyor"
    # ⚠️ "her hatada atla" olmamali: yalniz 3 atlanir, digerleri kirmizi kalir.
    assert 'exit "${KOD:-0}"' in wf, "workflow diger hata kodlarini YUTUYOR olabilir"
