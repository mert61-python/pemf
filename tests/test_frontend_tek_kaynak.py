# Author: mertaygn, cglrgrkn
"""Denetim 2026-08-15: arayüz kaynağı TEK olmalı — ikinci bir kopya SESSİZ ayrışma üretir.

NE OLDU: `guii/` altında AYNI deponun (`pemf-frontend.git`) İKİ ayrı klonu duruyordu:
  • `pf/`       — geliştirilen ağaç (mobil + web ortak kaynak)
  • `frontend/` — build'in OKUDUĞU ağaç
İkisi de `.gitignore`'da olduğu için ana depoda görünmüyorlardı ve sessizce ayrıştılar.
Ölçüldü: `frontend/` HEAD'i `pf/` HEAD'inin **15 commit gerisindeydi**; `agTanisi.ts`,
`sesYukleme.ts` gibi dosyalar orada HİÇ YOKTU.

SONUCU: arayüzde yapılan düzeltmeler masaüstü paketine HİÇ ULAŞMIYORDU. Doğrulanan örnek —
web'de canlı ses kaydı "expo-file-system web'de yok" diye çöküyordu; düzeltme `pf/`ye yazıldı
ama installer `frontend/dist`ten paketlendiği için kullanıcıya ESKİ arayüz gidiyordu. Hata
"düzeltildi ama geçmedi" görünür; teşhisi çok zordur çünkü kaynak dosyada düzeltme DURUYOR.

ÇÖZÜM: ikinci klon kaldırıldı, tüm build yolları `pf/`ye çevrildi (build_installer.ps1,
PEMF_Backend_onedir/onefile.spec, .github/workflows/linux-backend.yml).

Bu dosya tekrarını kilitler: ikinci bir kaynak ağacı belirirse ya da bir build yolu geri
`frontend/`ye dönerse test kırılır. (Paket İÇİ yol `frontend/dist` OLARAK KALIR — backend ve
launcher orayı arar; kilitlenen şey KAYNAK dizindir.)
"""

import re
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parent.parent

# Arayüz kaynağının TEK adresi.
_KAYNAK = _KOK / "pf"

# Aynı deponun ikinci bir kopyası olarak geçmişte görülen / görülebilecek adlar.
_IKINCI_KOPYA_ADAYLARI = ("frontend", "frontend_new", "pf_new", "pemf-frontend")


def _kaynak_agaci_mi(dizin: Path) -> bool:
    """Bu dizin bir Expo/RN arayüz KAYNAK ağacı mı? (yalnız `dist` çıktısı değil)"""
    return (dizin / "package.json").is_file() and (dizin / "src").is_dir()


def test_arayuz_kaynagi_var():
    """`pf/` artık BU deponun içinde (tek depo, 2026-08-18) — temiz checkout'ta da vardır.

    ⚠️ ESKİ GEREKÇE GEÇERSİZ: burada "`pf/` GITIGNORE'LUDUR (ayrı bir depo: pemf-frontend.git),
    CI'da YOKTUR" yazıyordu ve test bu yüzden atlanıyordu. `pemf-frontend` tek depoya taşındı
    ve arşivlendi; `git ls-files pf` artık 218 dosya döndürüyor, `.gitignore` de dışlamıyor.
    Atlama yolu yine de DURUYOR: dizin gerçekten yoksa (parçalı bir sparse-checkout, ya da
    yalnız backend'in çıkarıldığı bir kopya) bu bir arıza değildir. Asıl değişmez olan
    `test_KRITIK_ikinci_arayuz_kaynagi_YOK` koşulsuz kalır: ikinci bir kopya HER ortamda
    yasaktır, çünkü zararı checkout'a bağlı değildir.
    """
    if not _KAYNAK.exists():
        pytest.skip("pf/ bu çalışma kopyasında yok (parçalı checkout)")
    assert _kaynak_agaci_mi(_KAYNAK), f"arayüz kaynağı bulunamadı: {_KAYNAK}"


def test_KRITIK_ikinci_arayuz_kaynagi_YOK():
    """🔴 ASIL REGRESYON: ikinci bir kopya = sessiz ayrışma = düzeltmeler pakete ulaşmaz."""
    ikizler = [ad for ad in _IKINCI_KOPYA_ADAYLARI if ad != _KAYNAK.name and _kaynak_agaci_mi(_KOK / ad)]
    assert not ikizler, (
        f"guii/ altında İKİNCİ arayüz kaynak ağacı var: {ikizler}. Aynı deponun iki klonu "
        "sessizce ayrışır ve build yanlış olanı okur — arayüz düzeltmeleri pakete ulaşmaz. "
        f"Tek kaynak: {_KAYNAK.name}/"
    )


@pytest.mark.parametrize(
    "yol,desen,aciklama",
    [
        ("build_tools/build_installer.ps1", r'\$FrontendDir\s*=\s*Join-Path\s+\$ProjectRoot\s+"([^"]+)"', "installer"),
        (
            "build_tools/PEMF_Backend_onedir.spec",
            r"frontend_dir\s*=\s*os\.path\.join\(project_path,\s*'([^']+)'",
            "onedir spec",
        ),
        (
            "build_tools/PEMF_Backend_onefile.spec",
            r"frontend_dir\s*=\s*os\.path\.join\(project_path,\s*'([^']+)'",
            "onefile spec",
        ),
    ],
)
def test_build_yollari_TEK_kaynagi_gosterir(yol, desen, aciklama):
    """Her build yolu `pf/`yi okumalı — biri geri dönerse paket yine eski arayüzü taşır."""
    dosya = _KOK / yol
    assert dosya.is_file(), f"{yol} yok"
    m = re.search(desen, dosya.read_text(encoding="utf-8"))
    assert m, f"{aciklama}: frontend kaynak yolu ayrıştırılamadı ({yol})"
    assert m.group(1) == _KAYNAK.name, (
        f"{aciklama} '{m.group(1)}/' okuyor ama tek kaynak '{_KAYNAK.name}/'. "
        "Ayrışma geri döner: arayüz düzeltmeleri pakete ulaşmaz."
    )


def test_ci_export_adimi_da_TEK_kaynaktan_alir():
    """CI'daki web export de aynı ağaçtan olmalı; yoksa Linux paketi eski arayüz taşır."""
    ci = _KOK / ".github" / "workflows" / "linux-backend.yml"
    if not ci.is_file():
        pytest.skip("linux-backend.yml yok")
    metin = ci.read_text(encoding="utf-8")
    m = re.search(r"^\s*cd\s+(\S+)\s*$", metin, re.M)
    assert m, "CI'da export dizinine geçiş satırı bulunamadı"
    assert m.group(1) == _KAYNAK.name, f"CI '{m.group(1)}' dizininden export alıyor, tek kaynak '{_KAYNAK.name}'."


def test_paket_ICI_yolu_frontend_dist_OLARAK_KALIR():
    """⚠️ Kaynak dizin değişti diye paket içi yol değiştirilmemeli.

    Backend `_internal/frontend/dist`i servis eder ve launcher bütünlük kontrolünde tam bu
    yola bakar (`launcher/core/src/flow.rs`). Hedefi 'pf/dist' yapmak, kurulumu "arayüz yok"
    durumuna düşürürdü — kaynak yolu düzeltirken kolayca yapılabilecek bir hata.
    """
    for spec in ("PEMF_Backend_onedir.spec", "PEMF_Backend_onefile.spec"):
        metin = (_KOK / "build_tools" / spec).read_text(encoding="utf-8")
        assert "os.path.join('frontend', 'dist')" in metin, (
            f"{spec}: paket İÇİ hedef yolu 'frontend/dist' olmaktan çıkmış — backend ve "
            "launcher orayı arar, kurulum arayüzsüz kalır."
        )
