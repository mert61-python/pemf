# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""SİTE "TAHMİNİ İNDİRME" SAYISI GERÇEK PAKETLERLE UYUŞMUYORDU (denetim 2026-08-18).

`pemf-vet-web` indirme sayfasındaki paket seçici (`PackageBuilder`) kullanıcıya
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
"""

import json
import re
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parent.parent
_MANIFEST = _KOK / "pemf-app-packages" / "manifest.json"
_SITE_CONFIG = _KOK / "pemf-vet-web" / "src" / "config.ts"

#: Site sayıyı `toFixed(1)` ile gösterir → 0,05 GB yuvarlama payı + küçük paket dalgalanması.
_GB_TOLERANS = 0.06
_TABAN_TOLERANS_ORAN = 0.05


def _gb(bayt: int) -> float:
    return bayt / 2**30


@pytest.fixture(scope="module")
def manifest() -> dict:
    if not _MANIFEST.is_file():
        pytest.skip(f"paket manifesti yok (yerel yapı çıktısı): {_MANIFEST}")
    return json.loads(_MANIFEST.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def site() -> str:
    if not _SITE_CONFIG.is_file():
        pytest.skip(f"site deposu bu çalışma kopyasında yok: {_SITE_CONFIG}")
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


def test_KRITIK_profil_boyutlari_manifestle_uyusur(manifest, site):
    """Her profilin sitede yazan boyutu, yayınlanan paketin boyutu olmalı."""
    site_gb = _site_profil_gb(site)
    assert site_gb, "site MODULES dizisinden sizeGB okunamadi"
    for pid, kayit in manifest["profiles"].items():
        assert pid in site_gb, f"manifest'te olan profil sitede YOK: {pid}"
        gercek = _gb(kayit["size"])
        assert abs(site_gb[pid] - gercek) <= _GB_TOLERANS, (
            f"profil '{pid}': site {site_gb[pid]} GB diyor, gercek {gercek:.2f} GB "
            f"(fark {abs(site_gb[pid] - gercek):.2f} GB)"
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
