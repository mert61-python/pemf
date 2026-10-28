# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D6.45 (B-11.20) — jeton belgeleri kapının BUGÜNKÜ anahtarını anlatsın (Y194: jeton KOD düzeyinde kapalı).

🔴 ÖLÇÜLEN (HEAD ebf1c3fe): Y194 (`3bb0d3e0`, 2026-10-24) jetonu KOD düzeyinde kapattı — `apps/backend/servers/jeton.py`
`JETON_SAHIP_ACIK = False`, `JETON_ENFORCED = JETON_SAHIP_ACIK and _flag("PEMF_JETON_ENFORCED")`; ölçüm (`aj.sh betik`): ortam `1` →
`JETON_ENFORCED=False`. Belgeler hâlâ yalnız ORTAM bayrağını anlatıyordu:
  · `docs/JETON-SISTEMI.md` §5 "`PEMF_JETON_ENFORCED` kapalı" ve Adım 6 "Bayrağı aç: `PEMF_JETON_ENFORCED=1`" — bugün bu adım HİÇBİR şeyi
    değiştirmez (kodu açmadan saha ekibi "açtım" sanır; tersine Y194 öncesi bir makinede ortam `1` her analizi bakiyeden düşürüyordu);
  · `apps/web/METIN-KILAVUZU.md` kontrol listesi "`PEMF_JETON_ENFORCED` kapalı";
  · `docs/SAHA-TEST-LISTESI.md` 8.4 (+ HTML kopyası) "jeton kapısı uykuda" — NEDENİ (kod anahtarı) ve ortam `1`'in etkisizliği yok.

ÖLÇÜT (belge ↔ ÖLÇÜLEN kod, iki yönlü): kapı jeton modülünü ortam `PEMF_JETON_ENFORCED=1` ile YENİDEN YÜKLER ve kapının etkin olup olmadığını
okur. Etkin DEĞİLSE (bugün, Y194) belgeler kod anahtarını (`JETON_SAHIP_ACIK`) anlatmalı ve açma adımı onu içermeli; etkinse (sahip
anahtarı açarsa) belgeler "KOD düzeyinde kapalı" DİYEMEZ → kapı belgelerin güncellenmesini ister.
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

JETON_BELGESI = KOK / "docs" / "JETON-SISTEMI.md"
KILAVUZ = KOK / "apps" / "web" / "METIN-KILAVUZU.md"
SAHA = KOK / "docs" / "SAHA-TEST-LISTESI.md"

KOD_KAPALI = re.compile(r"KOD\s+düzeyinde\s+(?:KAPALI|kapalı)", re.I)


@pytest.fixture()
def ortam_1_ile_kapi(tmp_path, monkeypatch):
    """Ortam bayrağı AÇIK (`1`) iken kapı gerçekten etkin mi — modül yeniden yüklenir, test sonunda temiz ortamla geri yüklenir."""
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PEMF_JETON_ENFORCED", "1")
    import servers.jeton as j

    importlib.reload(j)
    yield {"etkin": bool(j.JETON_ENFORCED), "sahip_acik": bool(j.JETON_SAHIP_ACIK)}
    monkeypatch.delenv("PEMF_JETON_ENFORCED", raising=False)
    importlib.reload(j)


def _bolum(metin: str, baslik_deseni: str) -> str:
    """`### …` / `## …` başlığından bir sonraki aynı / üst düzey başlığa kadar."""
    m = re.search(baslik_deseni, metin, re.M)
    assert m, f"belgede bölüm bulunamadı: {baslik_deseni!r} — kapı bayat"
    duzey = len(re.match(r"#+", metin[m.start() :]).group(0))
    son = re.compile(r"^#{1,%d} " % duzey, re.M).search(metin, m.end())
    return metin[m.start() : son.start() if son else len(metin)]


def _saha_84() -> str:
    satir = [s for s in SAHA.read_text(encoding="utf-8").splitlines() if s.startswith("| 8.4 |")]
    assert len(satir) == 1, "SAHA-TEST-LISTESI'nde tek 8.4 satırı bulunamadı — kapı bayat"
    return satir[0]


def test_OLCUM_ortam_1_ile_kapinin_durumu_okunur(ortam_1_ile_kapi):
    """Ön koşul / vakum: ölçüm gerçekten yapılıyor (iki alan bool) ve Y194 durumu bugün beklenen hâlde."""
    assert ortam_1_ile_kapi["etkin"] is (ortam_1_ile_kapi["sahip_acik"]), (
        "kapı sahip anahtarından bağımsız açılıyor — ölçüm / kod tutarsız"
    )


def test_KRITIK_belgeler_KOD_ANAHTARINI_anlatir_ve_acma_adimi_onu_icerir(ortam_1_ile_kapi):
    jeton = JETON_BELGESI.read_text(encoding="utf-8")
    durum = _bolum(jeton, r"^## 5\. Devreye alma").split("\n### ", 1)[
        0
    ]  # yalnız "Bugünkü durum" girişi (adımlar hariç)
    adim6 = _bolum(jeton, r"^### Adım 6 ")
    kilavuz = KILAVUZ.read_text(encoding="utf-8")
    saha = _saha_84()
    if not ortam_1_ile_kapi["etkin"]:
        sorun = []
        if not ("JETON_SAHIP_ACIK" in durum and KOD_KAPALI.search(durum)):
            sorun.append(
                "JETON-SISTEMI §5 'Bugünkü durum' jetonun KOD düzeyinde (JETON_SAHIP_ACIK) kapalı olduğunu söylemiyor"
            )
        if "JETON_SAHIP_ACIK = True" not in adim6:
            sorun.append(
                "JETON-SISTEMI Adım 6 yalnız ortam bayrağını açtırıyor — bugün `PEMF_JETON_ENFORCED=1` TEK BAŞINA hiçbir şey değiştirmez"
            )
        if "JETON_SAHIP_ACIK" not in kilavuz:
            sorun.append("METIN-KILAVUZU kontrol listesi kapanmanın kod anahtarını (JETON_SAHIP_ACIK) anmıyor")
        if not (KOD_KAPALI.search(saha) and "PEMF_JETON_ENFORCED=1" in saha):
            sorun.append(f"SAHA-TEST 8.4 kod düzeyindeki kapanmayı ve ortam `1`'in etkisizliğini söylemiyor: {saha!r}")
        assert not sorun, (
            "ortam PEMF_JETON_ENFORCED=1 iken jeton KAPALI (Y194) ama belgeler bunu anlatmıyor:\n  "
            + "\n  ".join(sorun)
        )
    else:
        bayat = [
            ad
            for ad, m in (("JETON-SISTEMI §5", durum), ("METIN-KILAVUZU", kilavuz), ("SAHA-TEST 8.4", saha))
            if KOD_KAPALI.search(m)
        ]
        assert not bayat, (
            f"jeton kodda AÇILMIŞ (JETON_SAHIP_ACIK=True, ortam 1 → etkin) ama belgeler hâlâ 'KOD düzeyinde kapalı' diyor: {bayat}"
        )


def test_KARSIT_KANIT_bolum_ayiricisi_ve_desen():
    """Bölüm ayırıcı Adım 6'yı Adım 7'ye taşırmaz; desen 'kod düzeyinde kapalı' yazımlarını tanır, 'kapı uykuda'yı tanımaz."""
    ornek = "## 5. Devreye alma\n\nx\n\n### Adım 6 — Aç\n\nJETON_SAHIP_ACIK = True\n\n### Adım 7 — Sonra\n\nbaşka\n"
    assert "Adım 7" not in _bolum(ornek, r"^### Adım 6 ")
    assert "Adım 7" in _bolum(ornek, r"^## 5\. Devreye alma")
    assert KOD_KAPALI.search("jeton KOD düzeyinde kapalı (Y194)") and KOD_KAPALI.search("KOD düzeyinde KAPALI")
    assert not KOD_KAPALI.search("jeton kapısı uykuda")


# TUR 2 (çürütücü kolu): yukarıdaki kapı yalnız DOĞRU ifadenin VARLIĞINA bakıyordu; aynı bölüme "`PEMF_JETON_ENFORCED=1` yapılınca jeton devreye
# girer" gibi ÇELİŞEN bir cümle eklenince yeşil kalıyordu (mutant `cur645_n2` YAŞIYORDU). Bugünkü durumu anlatan yüzeylerde ortam bayrağını
# AÇICI diye anan her cümle kod anahtarını (JETON_SAHIP_ACIK) ya da sınırı ("tek başına açamaz", "olsa bile", "etkisiz") da söylemeli.
_ACAR = re.compile(r"devreye\s+gir|devrede|açılır|açar\b|etkin|bakiyeden\s+düş|\b402\b", re.I)
_SINIRLI = re.compile(r"JETON_SAHIP_ACIK|tek\s+başına|açamaz|açmaz|olsa\s+bile|etkisiz|no-op", re.I)


def _ortam_tek_basina_acar_diyen_cumleler(metin: str) -> list[str]:
    duz = re.sub(r"\s+", " ", metin)
    return [
        c
        for c in re.split(r"(?<=[.!?])\s", duz)
        if "PEMF_JETON_ENFORCED=1" in c and _ACAR.search(c) and not _SINIRLI.search(c)
    ]


def test_KRITIK_bugunku_durum_ortam_bayraginin_TEK_BASINA_actigini_SOYLEMEZ():
    jeton = JETON_BELGESI.read_text(encoding="utf-8")
    durum = _bolum(jeton, r"^## 5\. Devreye alma").split("\n### ", 1)[0]
    yuzeyler = {
        "JETON-SISTEMI §5": durum,
        "METIN-KILAVUZU": KILAVUZ.read_text(encoding="utf-8"),
        "SAHA-TEST 8.4": _saha_84(),
    }
    sorun = [f"{ad}: {c!r}" for ad, m in yuzeyler.items() for c in _ortam_tek_basina_acar_diyen_cumleler(m)]
    assert not sorun, (
        "belge ortam bayrağının jetonu TEK BAŞINA açtığını söylüyor (Y194: kod anahtarı JETON_SAHIP_ACIK da gerekir):\n  "
        + "\n  ".join(sorun)
    )


def test_KARSIT_KANIT_celiski_deseni_AYIRIYOR():
    assert _ortam_tek_basina_acar_diyen_cumleler(
        "Servis ortamında `PEMF_JETON_ENFORCED=1` yapılınca jeton devreye girer."
    )
    assert _ortam_tek_basina_acar_diyen_cumleler("`PEMF_JETON_ENFORCED=1` ise her AI analizi bakiyeden düşer.")
    assert not _ortam_tek_basina_acar_diyen_cumleler("Ortamdaki `PEMF_JETON_ENFORCED=1` tek başına açamaz.")
    assert not _ortam_tek_basina_acar_diyen_cumleler(
        "Jeton (`JETON_SAHIP_ACIK = True` VE `PEMF_JETON_ENFORCED=1`) açıkken devreye girer."
    )
    assert not _ortam_tek_basina_acar_diyen_cumleler("Servis ortamında `PEMF_JETON_ENFORCED=1` olsa bile kapalı.")
