# -*- coding: utf-8 -*-
# Author: mertaygn
"""SAHA TEST LİSTESİ — Markdown ile HTML AYRIŞMASIN.

===============================================================================
NEDEN
===============================================================================
Liste iki dosyada duruyordu: okunan `SAHA-TEST-LISTESI.md` ve sahada telefonla
işaretlenen `saha-test-listesi.html`. İkisi de ELLE güncelleniyordu ve **ayrışmıştı** —
HTML 5 kademede kalmış, Markdown'a eklenen senaryolar sahada HİÇ görünmüyordu.

⚠️ SINIF: "aynı kural N yerde kopyalanmış". Bu depoda tekrar eden arıza sınıfı; burada
sonucu sessizdi — test eden kişi listenin eksik olduğunu ANLAYAMAZ, çünkü her iki dosya da
kendi içinde tutarlı görünür.

ÇÖZÜM: tek kaynak Markdown; HTML'in `const VERI` bloğu `scripts/saha_test_html_uret.py`
ile üretilir. Bu kapı, üretilenle diskteki HTML'i kıyaslar.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

BETIK = KOK / "scripts" / "saha_test_html_uret.py"
MD = KOK / "docs" / "SAHA-TEST-LISTESI.md"
HTML = KOK / "docs" / "saha-test-listesi.html"


def _uretici():
    spec = importlib.util.spec_from_file_location("saha_test_html_uret", BETIK)
    modul = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modul)
    return modul


@pytest.fixture(scope="module")
def uretici():
    if not BETIK.exists():
        pytest.fail(f"uretici betik YOK: {BETIK}")
    return _uretici()


def test_KRITIK_html_markdown_ile_SENKRON(uretici):
    """⚠️ ASIL KAPI.

    MUTASYON: `SAHA-TEST-LISTESI.md`ye yeni bir tablo satırı ekle ama betiği koşturma
    → KIRMIZI (sahada o senaryo görünmezdi).
    """
    kademeler = uretici.kademeleri_oku(MD.read_text(encoding="utf-8"))
    beklenen = uretici.html_uret(HTML.read_text(encoding="utf-8"), uretici.veri_blogu(kademeler))
    assert beklenen == HTML.read_text(encoding="utf-8"), (
        "saha-test-listesi.html, SAHA-TEST-LISTESI.md ile AYRISMIS -> sahada eksik liste "
        "kosulur ve bu SESSIZ olur. Duzeltme: python scripts/saha_test_html_uret.py"
    )


def test_KRITIK_mobil_kademesi_VAR(uretici):
    """Sahip 2026-09-12: "mobil tarafı için de testler ekle, oraya hiç bakmadım denebilir".

    MUTASYON: Markdown'dan "Kademe 6 — MOBİL" başlığını sil → KIRMIZI.
    """
    kademeler = uretici.kademeleri_oku(MD.read_text(encoding="utf-8"))
    adlar = " ".join(kd["ad"] for kd in kademeler).lower()
    assert "mobil" in adlar, "MOBIL kademesi YOK -> en az bakilan katman yine test edilmez"

    mobil = [kd for kd in kademeler if "mobil" in kd["ad"].lower()][0]
    sayi = sum(len(g["items"]) for g in mobil["gruplar"])
    assert sayi >= 30, f"mobil kademesinde yalnizca {sayi} senaryo var (asgari 30)"


def test_KRITIK_hasta_guvenligi_kademesi_BLOK(uretici):
    """Kademe 1 "yayını durdurur" olarak işaretli olmalı; aksi halde arayüzde uyarı çıkmaz.

    MUTASYON: `BLOK` kümesinden "1"i çıkar → KIRMIZI.
    """
    kademeler = uretici.kademeleri_oku(MD.read_text(encoding="utf-8"))
    birinci = [kd for kd in kademeler if kd["no"] == "1"][0]
    assert birinci["blok"] is True, "Kademe 1 blok isaretli DEGIL -> yayin durduran sinif kaybolur"
    # Karşıt kanıt: her kademe blok DEĞİL (aksi halde işaret anlamsızlaşır).
    assert any(kd["blok"] is False for kd in kademeler)


def test_senaryo_numaralari_BENZERSIZ(uretici):
    """Aynı numara iki satırda olursa işaretler birbirini ezer (localStorage anahtarı = no)."""
    kademeler = uretici.kademeleri_oku(MD.read_text(encoding="utf-8"))
    numaralar = [no for kd in kademeler for g in kd["gruplar"] for (no, _s, _b) in g["items"]]
    tekrar = sorted({n for n in numaralar if numaralar.count(n) > 1})
    assert not tekrar, f"tekrarlayan senaryo numaralari: {tekrar} -> isaretler birbirini EZER"
    assert len(numaralar) >= 150, f"liste beklenenden kisa ({len(numaralar)} senaryo)"


def test_her_senaryonun_BEKLENENI_var(uretici):
    """ "Beklenen" boşsa senaryo ölçülemez — sahada "bir şey oldu" denir, bulgu yazılamaz."""
    kademeler = uretici.kademeleri_oku(MD.read_text(encoding="utf-8"))
    bos = [
        no for kd in kademeler for g in kd["gruplar"] for (no, _s, beklenen) in g["items"] if len(beklenen.strip()) < 10
    ]
    assert not bos, f"beklenen sonucu yazilmamis senaryolar: {bos}"
