# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""RUNBOOK GERÇEĞE UYGUN MU (2026-08-09 denetimi, Tier 3).

ARIZA: "Kötü güncelleme sonrası sorun" satırı iki kez yanlıştı —
  • var olmayan bir `DEPLOYMENT.md`ye yönlendiriyordu,
  • ve `POST /api/update/rollback` öneriyordu. O uç eski `exe` kanalına ait; kanalın
    `latest.json`ı 404 (ölçüldü 2026-08-10), `previousStable` hiç dolmuyor → komut HİÇBİR ŞEY
    YAPMIYOR. Bugün ayrıca kanal bilinçli olarak kapalı.

Yanlış runbook, runbook'suzluktan tehlikelidir: olay anında insan onu doğru sanıp uygular,
zaman kaybeder ve "geri aldım" diye yanlış rapor verir.

Bu testler runbook'un ÖLÇÜLEBİLİR iddialarını kilitler: gösterdiği dosyalar var mı, gösterdiği
API yolları kayıtlı mı, gösterdiği araçlar diskte mi, ve ölü komutu çözüm olarak sunuyor mu.
"""

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
RUNBOOK = KOK / "docs" / "RUNBOOK.md"


@pytest.fixture(scope="module")
def metin():
    if not RUNBOOK.exists():
        pytest.fail("docs/RUNBOOK.md yok — olay mudahale rehberi kayip")
    return RUNBOOK.read_text(encoding="utf-8")


# ── ölü komut ───────────────────────────────────────────────────────────────


def test_KRITIK_olu_rollback_komutu_COZUM_olarak_sunulmaz(metin):
    """`/api/update/rollback` metinde geçebilir — ama YALNIZ uyarı olarak."""
    for satir in metin.splitlines():
        if "/api/update/rollback" not in satir:
            continue
        uyari = (
            "KULLANMAYIN" in satir
            or "kullanmayın" in satir.lower()
            or "⚠" in satir
            or "hiçbir şey yapmaz" in satir.lower()
        )
        assert uyari, "RUNBOOK olu `/api/update/rollback` komutunu UYARISIZ oneriyor:\n  " + satir.strip()


def test_KRITIK_kotu_guncelleme_bolumu_GERCEK_yolu_anlatir(metin):
    """Olayın gerçek kurtarma yolu launcher'dadır; runbook onu adlandırmalı."""
    assert "## Kötü güncelleme" in metin, "kotu-guncelleme bolumu yok"
    bolum = metin.split("## Kötü güncelleme", 1)[1].split("\n## ", 1)[0]
    for anahtar in ("launcher", "min-supported-version", "rollout"):
        assert anahtar in bolum, f"kotu-guncelleme bolumunde '{anahtar}' gecmiyor"


# ── gösterdiği dosyalar / araçlar var mı ────────────────────────────────────


def test_atif_verilen_MD_dosyalari_VAR(metin):
    """`DEPLOYMENT.md` sınıfı hayalet atıflar bir daha girmesin."""
    kayip = []
    for ad in sorted(set(re.findall(r"\b([A-Za-z0-9_\-/]+\.md)\b", metin))):
        temiz = ad.lstrip("./")
        if any((KOK / k / temiz).exists() for k in ("", "docs")) or (KOK / temiz).exists():
            continue
        kayip.append(ad)
    assert not kayip, f"RUNBOOK var olmayan belgelere yonlendiriyor: {kayip}"


def test_gosterilen_araclar_DISKTE(metin):
    """`python tools\\kurtarma.py ...` gibi komutlar gerçekten çalışabilmeli."""
    kayip = [y for y in set(re.findall(r"python\s+([\w\\/]+\.py)", metin)) if not (KOK / y.replace("\\", "/")).exists()]
    assert not kayip, f"RUNBOOK var olmayan araclari gosteriyor: {kayip}"


# ── gösterdiği API yolları kayıtlı mı ───────────────────────────────────────


def test_gosterilen_API_yollari_KAYITLI(metin):
    from servers import api_server

    kayitli = {r.path for r in api_server.app.routes if hasattr(r, "path")}
    gecen = set(re.findall(r"127\.0\.0\.1:8000(/[\w/\-{}]+)", metin))
    gecen |= set(re.findall(r"`(/api/[\w/\-]+)`", metin))
    kayip = sorted(y for y in gecen if y not in kayitli)
    assert not kayip, (
        f"RUNBOOK kayitli OLMAYAN API yollari gosteriyor: {kayip} — uc yeniden adlandirildiysa runbook da guncellenmeli"
    )


def test_gosterilen_make_manifest_bayraklari_GERCEK(metin):
    """Yayıncı tablosundaki bayraklar `scripts/make_manifest.py`de tanımlı olmalı."""
    src = (KOK / "scripts" / "make_manifest.py").read_text(encoding="utf-8", errors="replace")
    bolum = metin.split("## Kötü güncelleme", 1)[1].split("\n## ", 1)[0]
    kayip = [b for b in set(re.findall(r"`(--[\w\-]+)", bolum)) if b not in src]
    assert not kayip, f"RUNBOOK var olmayan make_manifest bayraklarini gosteriyor: {kayip}"
