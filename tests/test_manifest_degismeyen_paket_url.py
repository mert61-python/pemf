# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
r"""Paket İÇERİĞİ değişmediyse manifest URL'si YENİ ETİKETE TAŞINMAMALI (sessiz 404).

DENETİM BULGUSU (2026-08-17). `scripts/make_manifest.py` diskte bulduğu HER paket için URL'yi
`--tag`'ten yeniden kuruyor:

    entry = {"url": f"{base_url}/{name}", "sha256": sha256(path), ...}

Ama BUILD.md bölüm 6'nın yükleme listesi yalnız `base-app.zip` / `base-deps.zip` / `manifest.json`
içeriyor. `pemf-app-packages/home.zip` diskte duruyor (318 390 934 B) ve yayındakiyle **birebir
aynı** (sha `1e528202…` = manifest değeri). Dolayısıyla sıradan bir app yayınında
`--tag client-app-v1.9.16` verildiğinde:

    models.home.url   : client-app-v1.9.11/home.zip  →  client-app-v1.9.16/home.zip
    profiles.home.url : (aynı)                       →  (aynı)

O etikete `home.zip` YÜKLENMEZ → **404**. "Ev Sahibi" profilini seçen her YENİ kurulum ve her
"Onar" hata ile düşer (`net.rs` 404'ü deterministik sayıp tekrar denemez). `vet.zip`/`research.zip`
yerelde olmadığı için taşınır ve URL'leri korunur → üç profilden **tam olarak biri** kırılır.

⚠️ HİÇBİR KAPI GÖREMEZ: `sha256` DEĞİŞMEDİĞİ için `tests/test_manifest_consistency.py`,
`manifest.rs::depodaki_gercek_manifest_ayristirilir` ve URL-pin kontrolü yeşil kalır.
`--drop-missing` de işe yaramaz — dosya *var*.

⚠️ Bugüne dek kaza olmamasının sebebi bir koruma DEĞİL: `git log -p pemf-app-packages/manifest.json`
home URL'sinin hiçbir commit'te değişmediğini gösteriyor; v1.9.11→v1.9.15 etiket bumplarının hepsi
`home.zip` diskte dururken yapıldı, yani betik o klasöre karşı hiç koşmadı (manifest fiilen elle
düzenleniyor). Betiği BUILD.md'nin dediği gibi koşturmak yeterli.

DOĞRU DAVRANIŞ: paket içeriği (sha) önceki manifest'tekiyle AYNIYSA URL KORUNUR — asset o eski
etikette zaten yayında ve bayt-bayt aynıdır. sha DEĞİŞTİYSE URL yeni etikete taşınır (yeni içerik
yeni etikete yüklenecektir).
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
BETIK = KOK / "scripts" / "make_manifest.py"
PY = sys.executable


def _paket_yaz(dizin: Path, ad: str, icerik: bytes) -> None:
    (dizin / ad).write_bytes(icerik)


def _kos(dizin: Path, tag: str, surum: str):
    return subprocess.run(
        [
            PY,
            str(BETIK),
            "--dir",
            str(dizin),
            "--version",
            surum,
            "--tag",
            tag,
            "--repo",
            "mert61-python/pemf-update",
            # İzole kum havuzunda `launcher`/`mobile` blokları yok; betiğin (doğru) kapısı
            # "client oto-güncellemesi ÇALIŞMAZDI" diye durduruyor. Bu testler URL taşıma
            # davranışını ölçüyor, o kapıyı değil (kapının kendisi başka testlerde kilitli).
            "--allow-missing-launcher",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )


@pytest.fixture()
def kum(tmp_path):
    """İzole paket klasörü: bir app katmanı + bir profil paketi."""
    d = tmp_path / "paketler"
    d.mkdir()
    # `base.zip` ŞART: betiğin "hiçbir base paketi bulunamadı" kapısı (doğru olarak) durduruyor —
    # eski (<=1.9.12) client'lar tek-parça `base`i okur ve o girdinin kaybolması onları kırar.
    _paket_yaz(d, "base.zip", b"BASE-v1")
    _paket_yaz(d, "base-app.zip", b"APP-v1")
    _paket_yaz(d, "base-deps.zip", b"DEPS-DEGISMEZ")
    _paket_yaz(d, "home.zip", b"HOME-DEGISMEZ-ICERIK")
    return d


def _manifest(d: Path) -> dict:
    return json.loads((d / "manifest.json").read_text(encoding="utf-8"))


def test_KRITIK_sha_AYNIYSA_paket_URLsi_KORUNUR(kum):
    """İçeriği değişmemiş paketin URL'si eski (yayında olan) etikette kalmalı."""
    r1 = _kos(kum, "client-app-v1.9.15", "1.9.15")
    assert r1.returncode == 0, f"ilk kosu basarisiz:\n{r1.stdout}\n{r1.stderr}"
    m1 = _manifest(kum)
    home_url_1 = m1["models"]["home"]["url"]
    assert "client-app-v1.9.15" in home_url_1, "on-kosul: ilk kosuda URL etikete yazilmali"

    # Sıradan bir sonraki yayın: yalnız app katmanı değişti, home.zip AYNI dosya.
    _paket_yaz(kum, "base-app.zip", b"APP-v2-DEGISTI")
    _paket_yaz(kum, "base.zip", b"BASE-v2-DEGISTI")
    r2 = _kos(kum, "client-app-v1.9.16", "1.9.16")
    assert r2.returncode == 0, f"ikinci kosu basarisiz:\n{r2.stdout}\n{r2.stderr}"
    m2 = _manifest(kum)

    assert m2["models"]["home"]["url"] == home_url_1, (
        f"degismemis home.zip'in URL'si yeni etikete TASINDI ({m2['models']['home']['url']}). "
        "O etikete home.zip yuklenmez → 'Ev Sahibi' profilini secen her YENI kurulum ve her "
        "'Onar' 404 alir. sha degismedigi icin hicbir mevcut kapi bunu goremez."
    )
    assert m2["profiles"]["home"]["url"] == home_url_1, "v1 `profiles` alani da korunmali"


def test_KRITIK_sha_DEGISTIYSE_URL_yeni_etikete_TASINIR_karsit_kanit(kum):
    """Karşı-kanıt: düzeltme URL'yi DONDURMAMALI — yeni içerik yeni etikete gider."""
    assert _kos(kum, "client-app-v1.9.15", "1.9.15").returncode == 0
    _paket_yaz(kum, "home.zip", b"HOME-YENI-ICERIK-DEGISTI")

    assert _kos(kum, "client-app-v1.9.16", "1.9.16").returncode == 0
    m = _manifest(kum)
    assert "client-app-v1.9.16" in m["models"]["home"]["url"], (
        "icerigi DEGISEN paketin URL'si eski etikette kaldi → yeni icerik hicbir zaman indirilmez"
    )


def test_app_katmani_her_yayinda_YENI_etikete_gider_karsit_kanit(kum):
    """Karşı-kanıt: her sürümde değişen `base-app.zip` normal akışını sürdürmeli."""
    assert _kos(kum, "client-app-v1.9.15", "1.9.15").returncode == 0
    _paket_yaz(kum, "base-app.zip", b"APP-v2-DEGISTI")
    _paket_yaz(kum, "base.zip", b"BASE-v2-DEGISTI")
    assert _kos(kum, "client-app-v1.9.16", "1.9.16").returncode == 0

    m = _manifest(kum)
    assert "client-app-v1.9.16" in m["layers"]["win-x64"]["app"]["url"], (
        "degisen app katmani yeni etikete tasinmadi → yayin gorunmez olur"
    )


def test_ILK_manifest_uretiminde_URL_etiketten_gelir_karsit_kanit(tmp_path):
    """Karşı-kanıt: önceki manifest YOKKEN (ilk üretim) URL elbette etiketten kurulur."""
    d = tmp_path / "ilk"
    d.mkdir()
    _paket_yaz(d, "base.zip", b"BASE")
    _paket_yaz(d, "base-app.zip", b"APP")
    _paket_yaz(d, "base-deps.zip", b"DEPS")
    _paket_yaz(d, "home.zip", b"HOME")
    assert _kos(d, "client-app-v1.0.0", "1.0.0").returncode == 0
    assert "client-app-v1.0.0" in _manifest(d)["models"]["home"]["url"]


def test_korunan_URL_ekranda_BILDIRILIR(kum, capfd=None):
    """Sessiz olmamalı: hangi paketin URL'si korundu, yayıncı görmeli."""
    assert _kos(kum, "client-app-v1.9.15", "1.9.15").returncode == 0
    _paket_yaz(kum, "base-app.zip", b"APP-v2")
    _paket_yaz(kum, "base.zip", b"BASE-v2")
    r = _kos(kum, "client-app-v1.9.16", "1.9.16")
    cikti = f"{r.stdout}\n{r.stderr}"
    assert "home.zip" in cikti and ("URL KORUNDU" in cikti or "url korundu" in cikti.lower()), (
        f"korunan URL bildirilmiyor → yayinci diff'te farki goremez.\n{cikti}"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
