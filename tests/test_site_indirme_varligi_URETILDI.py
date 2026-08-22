# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""SITENIN INDIRME BAGLANTISININ ISARET ETTIGI DOSYA URETILMIS OLMALI (2026-08-22).

OLCULEN ARIZA. 1.9.18 yayininda `versions.json` mobil surumu 2.3.19'a cikarildi ve site
`DOWNLOAD_HOST.androidVersion` ile birlikte guncellendi. Site indirme URL'sini SURUMDEN turetiyor:

    <androidTag>/PEMF_Vet_Mobil-<androidVersion>.apk

Ama yayina yalnizca `PEMF_Vet_Mobil.apk` (surumsuz ad, OTA/manifest icin) yuklendi ve o da
BASKA bir etikete gitti. Sonuc: sitedeki "Android icin indir" dugmesi **404** verdi ve bu
saatlerce fark edilmedi — mevcut testler yalnizca "site surumu versions.json ile AYNI mi" diye
bakiyordu; DOSYANIN URETILIP URETILMEDIGINE bakan hicbir kapi yoktu.

Bu dosya o bosluga bakar: surum yukseltildiyse, o surumun SURUMLU APK dosyasi
`release_assets/` altinda GERCEKTEN durmali. Ag gerektirmez, belirlenimcidir; yayindan
once "yukleyecek dosya var mi?" sorusunu commit aninda sorar.

⚠️ Bu kapi "yuklendi mi"yi kanitlamaz (bunun icin ag lazim) — "URETILDI mi"yi kanitlar.
Yayin akisinin geri kalani (varlik yukleme + HTTP 200 dogrulamasi) runbook'ta.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]


def _surumler() -> dict:
    return json.loads((_KOK / "versions.json").read_text(encoding="utf-8"))


def _site_apk_adi() -> str:
    """Sitenin URETTIGI dosya adi — sablon config.ts'ten okunur, elle yazilmaz."""
    src = (_KOK / "pemf-vet-web" / "src" / "config.ts").read_text(encoding="utf-8", errors="replace")
    m = re.search(r"get androidAsset\(\):\s*string\s*\{\s*return\s*`([^`]+)`", src)
    assert m, "config.ts icinde androidAsset sablonu bulunamadi — bicim degismis olabilir"
    sablon = m.group(1)  # ornek: PEMF_Vet_Mobil-${this.androidVersion}.apk
    surum = _surumler()["mobile"]["name"]
    return sablon.replace("${this.androidVersion}", surum)


def _yayin_makinesi_mi() -> bool:
    """⚠️ Bu kapi YAYIN MAKINESINDE anlamlidir, CI'da degil.

    `release_assets/*.apk` gitignore'ludur (her biri ~128 MB ikili) — taze klonda ve CI
    runner'inda HIC APK yoktur. Ilk yazimda bu dusunulmemisti ve kapi CI'da kosulsuz KIRMIZI
    verdi (kosu 32571564448). Dogru olcum: "hic APK yoksa burasi yayin makinesi degildir, atla".

    ⚠️ ATLAMA BIR ARKA KAPI DEGIL: en az bir APK varsa (yani burada APK URETILIYORSA) kapi
    CALISIR. Yakalamak istedigimiz ariza zaten "derledim ama surumlu kopyayi koymadim"dir.
    """
    return any((_KOK / "release_assets").glob("*.apk"))


def test_KRITIK_sitenin_isaret_ettigi_APK_URETILMIS():
    if not _yayin_makinesi_mi():
        pytest.skip("release_assets/ altinda hic APK yok — yayin makinesi degil (CI/taze klon)")
    ad = _site_apk_adi()
    yol = _KOK / "release_assets" / ad
    assert yol.exists(), (
        f"Site '{ad}' dosyasini indirtiyor ama o dosya URETILMEMIS "
        f"(release_assets/ altinda yok). Yayinlanirsa 'Android icin indir' 404 verir — "
        "2026-08-22'de tam bu oldu. `build_tools/build_apk.ps1` calistirin ve surumlu adla "
        "kopyalayin."
    )
    assert yol.stat().st_size > 50 * 1024 * 1024, (
        f"{ad} beklenenden kucuk ({yol.stat().st_size} bayt) — yarim/bozuk kopya olabilir"
    )


def test_KRITIK_surumsuz_APK_da_URETILMIS():
    """Manifest/OTA yolu surumsuz adi kullanir; ikisi de gerekir."""
    if not _yayin_makinesi_mi():
        pytest.skip("release_assets/ altinda hic APK yok — yayin makinesi degil (CI/taze klon)")
    yol = _KOK / "release_assets" / "PEMF_Vet_Mobil.apk"
    assert yol.exists(), "PEMF_Vet_Mobil.apk yok — OTA (manifest) yolu bu adi kullanir"


def test_KRITIK_iki_APK_AYNI_ikili():
    """Surumlu ve surumsuz kopya AYNI dosya olmali; ayrisirsa site ile OTA farkli yazilim dagitir
    (tibbi cihazda 'ayni surum, iki farkli ikili' kabul edilemez — bkz. make_base_zip monolith notu)."""
    import hashlib

    a = _KOK / "release_assets" / _site_apk_adi()
    b = _KOK / "release_assets" / "PEMF_Vet_Mobil.apk"
    if not (a.exists() and b.exists()):
        pytest.skip("APK'lardan biri yok (yukaridaki testler zaten kirmizi)")
    sa = hashlib.sha256(a.read_bytes()).hexdigest()
    sb = hashlib.sha256(b.read_bytes()).hexdigest()
    assert sa == sb, (
        f"site kopyasi ({sa[:12]}) ile OTA kopyasi ({sb[:12]}) FARKLI ikili — "
        "ayni surum numarasi altinda iki farkli yazilim dagitilir"
    )


def test_KARSIT_KANIT_APK_icindeki_surum_versions_json_ile_AYNI():
    """Dosya ADI dogru ama ICERIGI eski olabilir (yeniden derlemeden kopyalanmis).

    ⚠️ HAM BAYTTA ARAMAK ISE YARAMAZ (ilk yazimda denendi, yanlis-KIRMIZI verdi): APK bir ZIP'tir
    ve `AndroidManifest.xml` DEFLATE ile sikistirilmistir — dosyanin ham baytlarinda surum dizesi
    GECMEZ. Manifest ayrica ikili XML'dir ve dizeleri UTF-16LE havuzunda tutar. Dogru olcum:
    manifesti ZIP'ten ACIP UTF-16LE olarak ara.
    """
    import zipfile

    surum = _surumler()["mobile"]["name"]
    yol = _KOK / "release_assets" / _site_apk_adi()
    if not yol.exists():
        pytest.skip("APK yok (yukaridaki test zaten kirmizi)")
    with zipfile.ZipFile(yol) as z:
        manifest = z.read("AndroidManifest.xml")
    assert surum in manifest.decode("utf-16-le", "ignore"), (
        f"APK manifestinde '{surum}' surumu bulunamadi — dosya ADI guncel ama ICERIGI eski "
        "olabilir (yeniden derlemeden kopyalanmis)"
    )
