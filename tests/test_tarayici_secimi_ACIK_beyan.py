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

    Tarayici HIC yokken betik `--zorunlu` OLMADAN 3 ("ORTAM YOK") doner (yerel kosu). CI adimi `--zorunlu` ile cagirir →
    2 ve adim KIRMIZI. D6.56 (B-10.184): workflow'daki "3 ise atla" dali `--zorunlu` altinda ULASILAMAZDI ve "kurulum
    basarisizsa is akisi kirmizi olmaz" yorumu yanlisti — dal ve yorum kaldirildi; bu kapi ikisinin GERI gelmesini reddeder.
    Var olan ama calismayan tarayici da KIRMIZI kalir (betigin kendi hata metni).
    """
    metin = BETIK.read_text(encoding="utf-8")
    assert "return 2 if a.zorunlu else 3" in metin, (
        "ORTAM YOK (cikis 3) yolu kaybolmus -> yerel tarayicisiz kosu kirmizi olur"
    )
    wf = WF.read_text(encoding="utf-8")
    i = wf.find("- name: Gorunum alani + dokunma hedefi kapisi")
    assert i != -1, "site.yml'de responsive kapi adimi yok"
    j = wf.find("- name:", i + 10)
    adim = wf[i : j if j != -1 else len(wf)]
    # CI'da kapi SART (betik basligi + `--zorunlu` yardimi): tarayicisiz runner'da adim KIRMIZI biter, sessizce atlanmaz.
    assert "--zorunlu" in adim, (
        "CI responsive kapisi `--zorunlu` olmadan cagriliyor — tarayicisiz runner'da kapi sessizce atlanir"
    )
    assert not re.search(r'"\$\{KOD:-0\}"\s*=\s*"3"', adim), (
        "--zorunlu altinda betik 3 DONMEZ — workflow'daki '3 ise atla' dali OLU ve yaniltici (D6.56)"
    )
    assert not re.search(r"ATLANIR \(exit 3\)|is akisi kirmizi olmaz", wf), (
        "site.yml yorumu tarayici kurulamazsa kapinin ATLANDIGINI soyluyor — --zorunlu ile adim KIRMIZI biter (D6.56)"
    )
    # ⚠️ "her hatada atla" olmamali: sifir-disi her kod adimi kirmizi yapar.
    assert 'exit "${KOD:-0}"' in adim, "workflow diger hata kodlarini YUTUYOR olabilir"
