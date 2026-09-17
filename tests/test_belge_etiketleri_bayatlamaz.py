# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ELLE YAZILAN TARIH ETIKETLERI BAYATLAR (2026-09-17).

Denetim dort belgeyi "bayat" diye isaretlemisti. Olculdu — UCU ICIN IDDIA YANLIS, ama
altindan BASKA bir sinif cikti: bayat olan BELGELER degil, uzerlerindeki ELLE YAZILMIS
ETIKETLER.

    docs/PEMF_SISTEM_RAPORU.md   son commit 2026-09-15 (govde GUNCEL, hatta kendi
                                 "BU BOLUM BAYAT" notunu tasiyor)
                                 ama docs/README.md onu "(2026-03)" diye etiketliyor
    docs/LAUNCHER_SPEC.md        son commit 2026-09-15, govdede 2026-09-13 OLCUMLERI var
                                 ama basligi "Durum: taslak · Karar tarihi: 2026-07-21"
    frontend_version.json        "version" GUNCEL (1.4.2 = versions.json frontendOta)
                                 ama "date": "2026-06-27" — sync_versions.ps1 o alani
                                 HIC YAZMIYOR (yalniz `"version"` deseni) -> KALICI YANLIS
    docs/RUNBOOK.md              GERCEKTEN bayat: 2026-08-15, ESP devre disi birakilalı
                                 (2026-09-11) guncellenmemis

⚠️ SINIF: elle yazilan, turetilmeyen ve KIMSE tarafindan guncellenmeyen metadata. Ayni
sinif README surum tablosunda UC kez yasandi (test_readme_surum_bayatlamaz.py).

SOZLESME
  · `frontend_version.json` yalnizca BAKIMI YAPILAN alanlari tasir. `sync_versions.ps1`
    guncellemedigi bir alan (or. "date") oraya KONULMAZ — konursa kalici yalan olur.
  · Belge indeksi (`docs/README.md`) belgeleri TARIHLE etiketlemez; tarih dosyanin
    kendisinde/gecmisinde vardir ve indekste kopyasi bayatlar.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
_FRONTEND_SURUM = KOK / "frontend_version.json"
_SYNC = KOK / "build_tools" / "sync_versions.ps1"
_INDEKS = KOK / "docs" / "README.md"
_RUNBOOK = KOK / "docs" / "RUNBOOK.md"

#: `sync_versions.ps1`in GERCEKTEN yazdigi + sabit kalmasi mesru alanlar.
_IZINLI_ALANLAR = {"version", "download_url"}


# ═══════════════════════════════════════════════════════════════════════════════════════
# ASIL SOZLESME
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_frontend_surum_dosyasinda_BAKIMSIZ_alan_YOK():
    """⚠️ BU TEST DUZELTMEDEN ONCE KIRMIZIYDI ("date": "2026-06-27").

    `sync_versions.ps1:130` yalnizca `"version"` desenini gunceller. Baska her alan
    yazildigi gun donar ve bir daha dogru olmaz.
    """
    d = json.loads(_FRONTEND_SURUM.read_text(encoding="utf-8"))
    fazla = sorted(set(d) - _IZINLI_ALANLAR)
    assert not fazla, (
        f"frontend_version.json bakimsiz alan(lar) tasiyor: {fazla}. `sync_versions.ps1` "
        "onlari GUNCELLEMIYOR -> yazildiklari gun donarlar. Kaldirin ya da sync'e ekleyin."
    )


def test_KRITIK_surum_alani_versions_json_ILE_UYUMLU():
    """Izinli alan da bayatlayabilir — zinciri dogrula."""
    d = json.loads(_FRONTEND_SURUM.read_text(encoding="utf-8"))
    beklenen = json.loads((KOK / "versions.json").read_text(encoding="utf-8"))["frontendOta"]
    assert d.get("version") == beklenen, (
        f"frontend_version.json version={d.get('version')!r} ama versions.json "
        f"frontendOta={beklenen!r} -> `build_tools/sync_versions.ps1` calistirin"
    )


def test_KRITIK_belge_indeksi_TARIH_etiketi_TASIMAZ():
    """⚠️ Indekste yazan tarih, belge guncellendiginde GUNCELLENMEZ.

    Olculdu: `PEMF_SISTEM_RAPORU.md` 2026-09-15'te guncellenmisti ama indeks onu hala
    "(2026-03)" diye etiketliyordu — alti aylik bir yalan. Tarih dosyanin kendisinde ve
    git gecmisinde zaten var; indekste KOPYASI olmamali.
    """
    ihlaller = []
    for no, satir in enumerate(_INDEKS.read_text(encoding="utf-8").splitlines(), 1):
        if not satir.lstrip().startswith("|"):
            continue
        for m in re.finditer(r"\((20\d{2}-\d{2})\)", satir):
            ihlaller.append((no, m.group(1), satir.strip()[:90]))
    assert not ihlaller, (
        "Belge indeksinde ELLE yazilmis tarih etiketi var:\n"
        + "\n".join(f"  satir {n}: ({t}) -> {s}" for n, t, s in ihlaller)
        + "\n\nBelge guncellenince bu etiket guncellenmez; kaldirin."
    )


def test_KRITIK_RUNBOOK_ESP_durumunu_SOYLER():
    """ESP 2026-09-11'de devre disi birakildi; RUNBOOK hala canliymis gibi anlatiyordu.

    ⚠️ ESP KODU SILINMEDI, yalniz bayrakla kapatildi (sahip karari) — RUNBOOK bunu
    ACIKCA soylemeli, yoksa saha "MQTT/ESP bobinleri olu" satirini okuyup olmayan bir
    arizayi kovalar.
    """
    metin = _RUNBOOK.read_text(encoding="utf-8")
    assert "PEMF_ESP_ENABLED" in metin, (
        "RUNBOOK ESP'nin devre disi oldugunu (PEMF_ESP_ENABLED) SOYLEMIYOR -> sahada olmayan bir ESP arizasi kovalanir"
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# KARSIT-KANITLAR
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_KARSIT_KANIT_sync_GERCEKTEN_version_alanini_yaziyor():
    """Izinli alan listesi bir IDDIADIR: `version`i sync'in yazdigini dogrula.

    Yazmiyorsa "izinli" demek anlamsiz olur ve o alan da bayatlar.
    """
    ps = _SYNC.read_text(encoding="utf-8")
    assert "frontend_version.json" in ps, "sync_versions.ps1 bu dosyaya hic dokunmuyor"
    m = re.search(r'frontend_version\.json.*?\n.*?Pattern\s+\'([^\']+)\'', ps, re.S)
    assert m, "sync'in kullandigi desen okunamadi -> izinli-alan iddiasi dogrulanamiyor"
    assert '"version"' in m.group(1), (
        f"sync deseni `version` alanini hedeflemiyor: {m.group(1)!r} -> izinli listesi yanlis"
    )


def test_KARSIT_KANIT_indeks_kapisi_TARIHSIZ_satiri_yakalamaz():
    """Kural "indekste parantez yasak"a kaymamali; yalnizca TARIH etiketi hedeflenir."""
    ornek = "| [`RUNBOOK.md`](RUNBOOK.md) | Saha calistirma defteri (operasyon) | Teknisyen |"
    assert not re.search(r"\((20\d{2}-\d{2})\)", ornek), "tarihsiz satir yanlislikla yakalandi"
    kotu = "| [`X.md`](X.md) | Rapor (2026-03) | Yonetici |"
    assert re.search(r"\((20\d{2}-\d{2})\)", kotu), "gercek tarih etiketi yakalanmiyor"


def test_KARSIT_KANIT_RUNBOOK_ESPyi_SILMIYOR():
    """⚠️ Sahip karari: ESP kodu SILINMEZ, devre disi birakilir.

    RUNBOOK'tan ESP'yi tamamen cikarmak, geri acildiginda saha defterini eksik birakirdi.
    """
    metin = _RUNBOOK.read_text(encoding="utf-8")
    assert "ESP" in metin, "RUNBOOK'tan ESP tamamen cikarilmis -> geri acildiginda defter eksik"
