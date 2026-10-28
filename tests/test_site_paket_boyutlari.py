# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""SİTE "TAHMİNİ İNDİRME" SAYISI GERÇEK PAKETLERLE UYUŞMUYORDU (denetim 2026-08-18).

`apps/web` indirme sayfasındaki paket seçici (`PackageBuilder`) kullanıcıya
"Tahmini indirme ≈ X GB" gösteriyor ve X'i `CLIENT_BASE_MB / 1024 + Σ profil.sizeGB` ile
hesaplıyor. İki sayı da gerçeği yansıtmıyordu:

  · `CLIENT_BASE_MB = 52` YALNIZ client uygulamasıydı; oysa launcher kurulumdan sonra profil
    seçiminden BAĞIMSIZ olarak `app` + `deps` katmanlarını indiriyor (~1,43 GB).
  · Profil boyutları eskimişti: `home` 0.6 (gerçek 0,30 — `cat_organ` çekirdeğe taşınınca
    home.zip 528 → 318 MB'a düştü), `vet` 0.9 (gerçek 0,12 — 7 kat fazla), `research` 1.9
    (gerçek 1,46).

Somut zarar: yalnız "Ev Sahibi" seçen kullanıcıya ≈0,7 GB gösteriliyordu, gerçek indirme
≈1,7 GB'dır (2,5 kat). Kırsal/kotalı bağlantıdaki bir klinik için bu, yanlış karara götüren
bir sayıdır — ve bu depo "uydurma sayı göstermektense hiç gösterme" ilkesini başka yerlerde
(usageStats, DownloadStats, "SHA-256 doğrulanır" ifadesi) zaten uyguluyor.

⚠️ TEK KAYNAK `pemf-app-packages/manifest.json`tir (yayınlanan paketlerin kendisi). Bu kapı
site sabitlerini ona karşı kilitler; paketler yeniden üretilip boyut kayarsa burada patlar.
⚠️ Manifest yerel bir YAPI ÇIKTISIDIR: yoksa test ATLANIR (temiz klonda yanlış-kırmızı olmasın).

🔴 D6.42 + D6.66 (B-7.2 · B-7.14 · B-11.14, 2026-10-28): üç sayı daha manifestten kopmuştu ve kapı ikisini KİLİTLİYORDU:
  · Windows kurulum dosyası: site / README "≈3 MB NSIS launcher" — manifest `launcher.size` 265.032.239 B (≈253 MiB; 1.9.43'ten beri WebView2
    çevrimdışı kurucusu gömülü). `yolculuk.test.ts` "sizeMB < 50" ile yanlış değeri kilitliyordu. Tek kaynak + TEK eşik (±%10) bu dosyada.
  · Araştırma profili: site 1,5 GB — profil paketi (`profiles.research` 1,50 GiB) YANINDA ayrı model parçası iner (`model_parts.research`
    research-2.zip 1,69 GiB) → gerçek 3,19 GiB (3,43 GB). Kapı yalnız `profiles[pid]`a bakıyordu; artık profil + parçaları.
  · Disk gereksinimi "3–5 GB": başlatıcı kurulumdan ÖNCE `2 × indirilecek + %10` boş alan ister (`launcher/core/src/disk.rs`
    `gereken_alan` — zip önbellekte kalır, açılmış boyut ≈ zip); üç profil birlikte ≈11,2 GiB.
"""

import json
import math
import re
from pathlib import Path

import capraz
import pytest

_KOK = Path(__file__).resolve().parent.parent
_MANIFEST = _KOK / "pemf-app-packages" / "manifest.json"
_SITE_CONFIG = _KOK / "apps/web" / "src" / "config.ts"
_SITE_README = _KOK / "apps/web" / "README.md"
_SITE_KATALOG = {d: _KOK / "apps/web" / "src" / "i18n" / d / "indirme.json" for d in ("tr", "en")}

#: Site sayıyı `toFixed(1)` ile gösterir → 0,05 GB yuvarlama payı + küçük paket dalgalanması.
_GB_TOLERANS = 0.06
_TABAN_TOLERANS_ORAN = 0.05
#: D6.42 + D6.66: kurulum dosyası boyutu için TEK eşik (n=234 %50 / n=276 2× çelişkisi kapandı) — MiB / MB yazımı ikisi de içinde kalır.
_KURULUM_TOLERANS_ORAN = 0.10
#: `launcher/core/src/disk.rs::gereken_alan` kuralı (kapıda PİNLİ — ürün sabitinden okunmaz): indirilecek ×2 (zip önbellekte + açılmış) + %10 pay.
_DISK_CARPAN = 2
_DISK_PAY = 0.10


def _gb(bayt: int) -> float:
    return bayt / 2**30


@pytest.fixture(scope="module")
def manifest() -> dict:
    # D5-F: `pemf-app-packages/manifest.json` İZLENİR (git ls-files) — eski düz pytest.skip, ZORUNLU kipte DÜŞER
    capraz.atla_yoksa("pemf-app-packages/manifest.json", izlenen=True)
    return json.loads(_MANIFEST.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def site() -> str:
    capraz.atla_yoksa("apps/web/src/config.ts", izlenen=True)  # D5-F: eski düz pytest.skip — ZORUNLU kipte DÜŞER
    return _SITE_CONFIG.read_text(encoding="utf-8")


def _site_taban_mb(src: str) -> int:
    m = re.search(r"export const CLIENT_BASE_MB\s*=\s*(\d+)", src)
    assert m, "CLIENT_BASE_MB bulunamadi (site sabiti yeniden adlandirilmis olabilir)"
    return int(m.group(1))


def _site_profil_gb(src: str) -> dict:
    """`MODULES` dizisindeki her `id` için `sizeGB`."""
    out = {}
    for parca in src.split("    id: '")[1:]:
        pid = parca.split("'", 1)[0]
        m = re.search(r"sizeGB:\s*([0-9.]+)", parca)
        if m:
            out[pid] = float(m.group(1))
    return out


def test_KRITIK_zorunlu_TABAN_indirmesi_sitede_dogru(manifest, site):
    """Profil seçiminden bağımsız inen `app`+`deps` katmanları siteye YANSIMALI."""
    kat = manifest["layers"]["win-x64"]
    gercek_mb = (kat["app"]["size"] + kat["deps"]["size"]) / 2**20
    site_mb = _site_taban_mb(site)
    assert abs(site_mb - gercek_mb) <= gercek_mb * _TABAN_TOLERANS_ORAN, (
        f"site ZORUNLU taban indirmesini {site_mb} MB diyor, gercek {gercek_mb:.0f} MB "
        f"(app+deps). Paket secici kullaniciya {(gercek_mb - site_mb) / 1024:.2f} GB EKSIK "
        f"gosteriyor -> kotali baglantida yanlis karar."
    )


def _profil_bayt(manifest: dict, pid: str) -> int:
    """Profil seçilince İNEN toplam: profil paketi + o profilin ayrı model parçaları (`model_parts[pid]`)."""
    return manifest["profiles"][pid]["size"] + sum(p["size"] for p in manifest.get("model_parts", {}).get(pid, []))


def test_KRITIK_profil_boyutlari_manifestle_uyusur(manifest, site):
    """Her profilin sitede yazan boyutu, o profil seçilince inen paketlerin (profil + model parçaları) TOPLAMI olmalı."""
    site_gb = _site_profil_gb(site)
    assert site_gb, "site MODULES dizisinden sizeGB okunamadi"
    for pid in manifest["profiles"]:
        assert pid in site_gb, f"manifest'te olan profil sitede YOK: {pid}"
        gercek = _gb(_profil_bayt(manifest, pid))
        assert abs(site_gb[pid] - gercek) <= _GB_TOLERANS, (
            f"profil '{pid}': site {site_gb[pid]} GB diyor, gercek {gercek:.2f} GB (profil paketi + model parcalari; "
            f"fark {abs(site_gb[pid] - gercek):.2f} GB)"
        )


def test_KARSIT_KANIT_model_parcasi_OLAN_profil_var(manifest):
    """Vakum olmasın: manifestte ayrı model parçası taşıyan profil gerçekten var (yoksa toplam kolu boş koşar)."""
    assert any(manifest.get("model_parts", {}).get(pid) for pid in manifest["profiles"]), (
        "manifest'te model_parts YOK — kol bayat"
    )


def _site_windows_kurulum_mb(src: str) -> int:
    """`CLIENT.downloads.windows` bloğundaki `sizeMB` (Windows kurulum dosyası — kart ve ana sayfa bunu gösterir)."""
    m = re.search(r"\n    windows: \{(.*?)\n    \},", src, re.S)
    assert m, "config.ts'de CLIENT.downloads.windows bloğu bulunamadı — kapı bayat"
    s = re.search(r"\bsizeMB:\s*(\d+)", m.group(1))
    assert s, "Windows indirme kartında `sizeMB` YOK — kurulum dosyası boyutu Windows'a özel alandan gelmeli (D6.42)"
    return int(s.group(1))


def test_KRITIK_windows_kurulum_dosyasi_boyutu_manifestle_uyusur(manifest, site):
    """D6.42 + D6.66: sitenin söylediği Windows kurulum dosyası boyutu, yayınlanan `launcher.size` ile TEK eşikte uyuşur."""
    gercek_mb = manifest["launcher"]["size"] / 2**20
    site_mb = _site_windows_kurulum_mb(site)
    assert abs(site_mb - gercek_mb) <= gercek_mb * _KURULUM_TOLERANS_ORAN, (
        f"site Windows kurulum dosyasını ≈{site_mb} MB diyor, yayınlanan kurulum dosyası {gercek_mb:.0f} MiB "
        f"(manifest launcher.size {manifest['launcher']['size']:,} B) — eşik ±%{_KURULUM_TOLERANS_ORAN * 100:.0f}"
    )
    assert "sizeMB: 3," not in site and not re.search(r"^\s*sizeMB:\s*\d+\s*,", site.split("downloads:")[0], re.M), (
        "CLIENT düzeyinde platformdan bağımsız tek `sizeMB` kaldı — Windows'a özel alan kullanılmalı"
    )


def test_KRITIK_site_README_kurulum_boyutu_manifestle_uyusur(manifest):
    """`apps/web/README.md` launcher / client satırlarındaki "~N MB" de aynı eşikte (README "~3 MB NSIS launcher" diyordu)."""
    capraz.atla_yoksa("apps/web/README.md", izlenen=True)
    gercek_mb = manifest["launcher"]["size"] / 2**20
    sayilar = [
        int(m.group(1))
        for satir in _SITE_README.read_text(encoding="utf-8").splitlines()
        if re.search(r"launcher|client|kurulum", satir, re.I)
        for m in re.finditer(r"~\s?(\d+)\s?MB\b", satir)
    ]
    assert sayilar, "README launcher / kurulum dosyası boyutunu söylemiyor — kapı bayat"
    yanlis = [n for n in sayilar if abs(n - gercek_mb) > gercek_mb * _KURULUM_TOLERANS_ORAN]
    assert not yanlis, (
        f"README kurulum dosyasını {yanlis} MB diyor; yayınlanan {gercek_mb:.0f} MiB (manifest launcher.size)"
    )


def _disk_araligi(dil: str) -> tuple[int, int]:
    deger = json.loads(_SITE_KATALOG[dil].read_text(encoding="utf-8"))["gereksinim"]["disk"]
    m = re.search(r"(\d+)\s*[–-]\s*(\d+)\s*GB", deger)
    assert m, f"{dil}: disk gereksinimi aralık söylemiyor: {deger!r}"
    return int(m.group(1)), int(m.group(2))


def test_KRITIK_disk_gereksinimi_baslaticinin_istedigi_alani_KARSILAR(manifest):
    """Üç profil birden seçilince başlatıcının istediği boş alan, sitenin üst sınırını AŞMAZ; varsayılan seçim (Ev + Veteriner) alt
    sınırın ALTINDA kalmaz (alt sınır abartılmasın)."""
    kat = manifest["layers"]["win-x64"]
    taban = kat["app"]["size"] + kat["deps"]["size"]

    def gerek(pidler) -> float:
        indir = taban + sum(_profil_bayt(manifest, p) for p in pidler)
        return _gb(indir * _DISK_CARPAN * (1 + _DISK_PAY))

    hepsi, varsayilan = gerek(list(manifest["profiles"])), gerek(["home", "vet"])
    for dil in ("tr", "en"):
        alt, ust = _disk_araligi(dil)
        assert ust >= math.ceil(hepsi), (
            f"{dil}: site en çok {ust} GB boş disk diyor; üç profil için başlatıcı {hepsi:.1f} GB ister (2 × indirme + %10)"
        )
        assert alt <= varsayilan, (
            f"{dil}: site en az {alt} GB diyor; varsayılan seçim (Ev + Veteriner) {varsayilan:.1f} GB ister"
        )


def test_KARSIT_KANIT_site_sayilari_SIFIRLANARAK_gecirilemez(site):
    """Karşıt-kanıt: "hepsini 0 yap" biçiminde bir yama kapıyı geçmemeli — sayı anlamlı kalmalı."""
    assert _site_taban_mb(site) > 0, "taban indirmesi 0 MB gosteriliyor"
    for pid, gb in _site_profil_gb(site).items():
        assert gb > 0, f"profil '{pid}' 0 GB gosteriliyor"


def test_KARSIT_KANIT_toplam_tahmin_gercek_indirmeyi_ASMAZ(manifest, site):
    """Karşıt-kanıt: taban sabitini şişirerek kapıyı geçmek de yanlış — bu kez fazla gösterir."""
    kat = manifest["layers"]["win-x64"]
    gercek_gb = _gb(kat["app"]["size"] + kat["deps"]["size"]) + _gb(manifest["profiles"]["home"]["size"])
    site_gb = _site_taban_mb(site) / 1024 + _site_profil_gb(site)["home"]
    assert abs(site_gb - gercek_gb) <= 0.12, (
        f"yalniz 'Ev Sahibi' secen kullaniciya {site_gb:.2f} GB gosteriliyor, gercek {gercek_gb:.2f} GB"
    )


if __name__ == "__main__":
    import os

    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
