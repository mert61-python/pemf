# -*- coding: utf-8 -*-
"""K-1 · ANAHTAR EŞLİĞİ (T14) — her yüzeyin kataloğunda tr ve en: aynı anahtar kümesi, boş değer yok, aynı yer tutucu kümesi, çoğul
biçimleri tam (tr / en: `_one` + `_other`), NSIS değişkenleri aynı, sunucuda `{{dil}}` yok; katalog dosyaları kanonik biçimde;
arayüz / site `kaynaklar.ts` her ad alanı dosyasını iki dilde içe aktarıyor; launcher'ın ÜRETİLMİŞ dosyaları katalogla aynı.

Neden kapı: eksik EN anahtarı i18next'te sessizce TR'ye düşer (fallbackLng) — İngilizce kullanıcı Türkçe kalmış metin görür; yer tutucu
farkı İngilizcede değerin hiç görünmemesi demektir ({{sayi}} → boş). Bu kapı onları commit'te durdurur.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from scripts.i18n import katalog, launcher_uret, ortak  # noqa: E402


@pytest.mark.parametrize("yuzey", list(ortak.KATALOGLAR))
def test_K1_tr_en_eslik(yuzey):
    assert ortak.katalog_dosyalari(yuzey, "tr"), f"{yuzey}: tr kataloğu yok"
    sorun = katalog.esle(KOK, [yuzey])
    assert not sorun, "\n".join(sorun)


def test_K1_katalog_dosyalari_kanonik():
    farkli = katalog.bicimle(KOK, None, denetle=True)
    assert not farkli, f"kanonik olmayan katalog(lar): {farkli} → `katalog.py bicimle`"


@pytest.mark.parametrize("yuzey", ["arayuz", "site"])
def test_K1_kaynaklar_ts_her_ad_alanini_iki_dilde_iceri_alir(yuzey):
    ts = (KOK / ortak.KATALOGLAR[yuzey]["kok"] / "kaynaklar.ts").read_text(encoding="utf-8")
    for dil in ortak.DILLER:
        for ad in ortak.katalog_dosyalari(yuzey, dil):
            assert re.search(rf"""from\s+["']\./{dil}/{ad}\.json["']""", ts), (
                f"{yuzey}: kaynaklar.ts {dil}/{ad}.json'u içe aktarmıyor"
            )


def test_K1_launcher_uretilmis_dosyalari_katalogla_ayni():
    assert launcher_uret.main(["--denetle"]) == 0, (
        "launcher i18n_katalog.js / hooks.nsi LangString bloğu bayat → scripts/i18n/launcher_uret.py"
    )


def test_K1_KARSIT_esle_eksik_ve_yer_tutucu_farkini_YAKALAR(tmp_path):
    """Kapının kör olmadığı: sahte katalogda eksik EN, boş değer, yer tutucu farkı, eksik çoğul → hepsi sorun."""
    for d in ("tr", "en"):
        (tmp_path / "launcher" / "i18n").mkdir(parents=True, exist_ok=True)
    (tmp_path / "launcher" / "i18n" / "tr.json").write_text(
        '{"a": {"b": "Bobin {{n}}", "c": "x", "d_one": "1 bobin", "d_other": "{{count}} bobin", "e": "y"}}',
        encoding="utf-8",
    )
    (tmp_path / "launcher" / "i18n" / "en.json").write_text(
        '{"a": {"b": "Coil", "c": " ", "d_other": "{{count}} coils"}}', encoding="utf-8"
    )
    s = "\n".join(katalog.esle(tmp_path, ["launcher"]))
    assert (
        "en'de YOK: a.e" in s
        and "BOŞ değer: a.c" in s
        and "yer tutucu farklı a.b" in s
        and "çoğul biçimi eksik: a.d_one" in s
    )
