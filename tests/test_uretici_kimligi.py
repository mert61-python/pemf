# Author: mertaygn, cglrgrkn
"""ÜRETİCİ KİMLİĞİ — kurulumda görünen yayıncı adı doğru şirket olmalı.

SAHA HATASI (2026-08-11). Kurulumda çıkan Windows UAC penceresi yayıncıyı
**"PEMF Medical Technologies"** gösteriyordu; oysa tescilli ünvan
**"İBİA Teknoloji Ltd. Şti."**dir. Ünvan sitede ve client arayüzünde güncellenmişti ama
Windows sürüm-kaynaklarında (version resource) eski ad kalmıştı — yani kullanıcıya
gösterilen TEK yerde yanlış ad duruyordu.

Bu, kozmetik değil: UAC'de görünen ad kurulumun kime ait olduğuna dair kullanıcının
gördüğü ilk (ve imzasız kurulumda TEK) kimlik bilgisidir.
"""

import json
import os
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent

#: Tescilli ünvanın telif satırında kullanılan kısa hâli. TEK KAYNAK:
#: `pemf-vet-web/src/config.ts` → `LEGAL.company`.
UNVAN = "İBİA Teknoloji Ltd. Şti."

#: Artık HİÇBİR kullanıcıya-görünen kimlik alanında bulunmamalı.
ESKI_UNVAN = "PEMF Medical Technologies"


def _oku(gorece: str) -> str:
    return (KOK / gorece).read_text(encoding="utf-8")


def test_KRITIK_site_unvani_TEK_KAYNAK():
    """Ünvanın kanonik yazımı sitede tanımlı; bu test onu çıpa alır.
    Site değişirse burada da bilinçli güncelleme gerekir."""
    src = _oku("pemf-vet-web/src/config.ts")
    assert f"company: '{UNVAN}'" in src, (
        "site telif ünvanı beklenenden farklı — kanonik yazım değiştiyse UNVAN sabitini güncelle"
    )


@pytest.mark.parametrize(
    "dosya",
    [
        "docs/version_info.txt",  # PEMF_Backend.exe sürüm kaynağı (PyInstaller)
        "build_tools/build_installer.ps1",  # aynı kaynağı ÜRETEN betik (ikisi ayrışmamalı)
        "build_tools/PEMF_Backend_Setup.iss",  # Inno kurulum yayıncısı
        "launcher/app/tauri.conf.json",  # client kurulumu (UAC'de görünen)
    ],
)
def test_KRITIK_eski_unvan_KALMADI(dosya):
    """Kullanıcıya görünen hiçbir kimlik alanında eski ad kalmamalı."""
    assert ESKI_UNVAN not in _oku(dosya), f"{dosya} hâlâ eski ünvanı taşıyor: {ESKI_UNVAN}"


@pytest.mark.parametrize(
    "dosya",
    [
        "docs/version_info.txt",
        "build_tools/build_installer.ps1",
        "build_tools/PEMF_Backend_Setup.iss",
        "launcher/app/tauri.conf.json",
    ],
)
def test_KRITIK_guncel_unvan_VAR(dosya):
    assert UNVAN in _oku(dosya), f"{dosya} güncel ünvanı ({UNVAN}) taşımıyor"


def test_KRITIK_tauri_publisher_ALANI_VAR():
    """Windows UAC'de görünen yayıncı `bundle.publisher`den gelir. Alan YOKSA Tauri başka bir
    değere (copyright/identifier) düşer ve ad sessizce yanlış görünür — arızanın kaynağı buydu."""
    conf = json.loads(_oku("launcher/app/tauri.conf.json"))
    yayinci = (conf.get("bundle") or {}).get("publisher")
    assert yayinci == UNVAN, f"tauri bundle.publisher yanlış/eksik: {yayinci!r}"


def test_KRITIK_uygulama_kimligi_DEGISMEDI():
    """⚠️ `identifier` (com.pemfmedical.vetclient) ÜNVAN DEĞİL, KURULUM KİMLİĞİDİR.

    Değiştirmek: kurulum yollarını (`%APPDATA%\\<identifier>`), kaldırma kaydını ve
    oto-güncellemenin mevcut kurulumu tanımasını BOZAR — sahadaki her cihaz yetim kalır.
    Ünvan düzeltmesi sırasında 'tutarlılık olsun' diye değiştirilmemeli."""
    conf = json.loads(_oku("launcher/app/tauri.conf.json"))
    assert conf.get("identifier") == "com.pemfmedical.vetclient", (
        "uygulama kimliği değişmiş → sahadaki kurulumlar yetim kalır (kaldırma + oto-güncelleme kırılır)"
    )


def test_KRITIK_kaldirma_araci_ESKI_adi_da_tarar():
    """Inno kurulumu `SOFTWARE\\<yayıncı>` altına yazar. Ünvan değiştiği için kaldırma aracı
    HER İKİ adı da taramalı; yoksa eski adla kurulmuş makinelerde registry kalıntısı kalır."""
    src = _oku("scripts/pemf_footprint.ps1")
    assert UNVAN in src, "footprint güncel üretici adını taramıyor"
    assert ESKI_UNVAN in src, (
        "footprint ESKİ üretici adını taramayı bırakmış → o adla kurulmuş makineler tam temizlenemez"
    )


def test_KRITIK_client_ESKI_uretici_anahtari_da_taranir():
    """Client (NSIS) kurulum yolunu `Software\\<MANUFACTURER>\\<ürün>` altına yazar.

    `bundle.publisher` tanımsızken Tauri kimliğin ikinci parçasına düşüp **`pemfmedical`**
    yazıyordu. Ünvan tanımlanınca yol değişti → eski anahtar kaldırmada artık eşleşmez ve
    GERİDE KALIR. Kaldırma aracı ikisini de taramalı.

    (Kaldırma KAYDI `Uninstall\\<ürün adı>` olduğu için yerinde güncelleme bozulmaz —
    Programlar listesinde çift kayıt oluşmaz; risk yalnız yetim registry anahtarıdır.)"""
    src = _oku("scripts/pemf_footprint.ps1")
    assert "HKCU:\\Software\\pemfmedical" in src, (
        "eski client üretici anahtarı (pemfmedical) taranmıyor → kaldırmada geride kalır"
    )
    assert f"HKCU:\\Software\\{UNVAN}" in src, "güncel client üretici anahtarı taranmıyor"


def test_version_info_ile_uretici_betik_AYRISMIYOR():
    """`docs/version_info.txt` elle de düzenlenebiliyor, `build_installer.ps1` onu ÜRETİYOR.
    İkisi ayrışırsa build sessizce eski adı geri yazar."""
    vi = _oku("docs/version_info.txt")
    ps = _oku("build_tools/build_installer.ps1")
    for alan in ("CompanyName", "LegalCopyright"):
        d_vi = re.search(rf"StringStruct\(u'{alan}', u'([^']*)'\)", vi)
        d_ps = re.search(rf"StringStruct\(u'{alan}', u'([^']*)'\)", ps)
        assert d_vi and d_ps, f"{alan} iki dosyanın birinde bulunamadı"
        assert UNVAN in d_vi.group(1) and UNVAN in d_ps.group(1), (
            f"{alan} ayrışmış: version_info={d_vi.group(1)!r} betik={d_ps.group(1)!r}"
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
