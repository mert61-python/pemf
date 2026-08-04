"""Denetim 2026-08-04 (P3): yayınlanan `manifest.json`'ın v1/v2 tutarlılığı.

Manifest AYNI paketi İKİ ŞEMADA birden anlatır:
  • v2 (yeni launcher)  : `runtimes.<platform>` / `models.<profil>`
  • v1 (geriye uyum)    : `base` / `base_linux` / `base_mac` / `profiles.<profil>`

`scripts/make_manifest.py` her iki yere AYNI sözlük NESNESİNİ koyar → üretimde ayrışamaz.
Ancak sahip notlarında "manifest ÇİFT-base gotcha'sı: sha/size İKİ yerde" diye kayıtlı bir
tuzak var: manifest ELLE düzenlendiğinde (sürüm bumpı, tek bir asset'in yeniden yayını) biri
güncellenip diğeri unutulabiliyor. Sonuç sinsi: v1 okuyan ESKİ istemciler bayat bir sha256
görür, indirdikleri YENİ dosyayla eşleşmez ve kurulum "paket kurcalanmış" hatasıyla düşer —
gerçekte kurcalanma yoktur, sadece manifest tutarsızdır. Saha teşhisi çok zordur.

Bu test o ayrışmayı yakalar. Ağ gerektirmez; depodaki gerçek manifest'i okur.
(Rust tarafında `manifest::tests::depodaki_gercek_manifest_ayristirilir` aynı dosyayı
ayrıştırılabilirlik ve URL-pinleme açısından denetler — bu ikisi birbirini tamamlar.)
"""

import json
from pathlib import Path

import pytest

_MANIFEST = Path(__file__).resolve().parent.parent / "pemf-app-packages" / "manifest.json"

# (v2 bölümü, v2 anahtarı, v1 alan adı)
_RUNTIME_PAIRS = [
    ("runtimes", "win-x64", "base"),
    ("runtimes", "linux-x64", "base_linux"),
    ("runtimes", "mac-arm64", "base_mac"),
]


@pytest.fixture(scope="module")
def manifest() -> dict:
    # ⚠️ DENETİM 2026-08-04 (P2): burada `pytest.skip` vardı ve `pemf-app-packages/manifest.json`
    # git'te İZLENMİYORDU → temiz bir CI checkout'unda dosya hiç bulunmuyor, üç test de sessizce
    # ATLANIYOR ve CI YEŞİL raporluyordu. Yani kapı, koruduğunu sandığı ayrışmayı hiç görmüyordu.
    # Manifest artık izleniyor (3,5 KB; paketlerin kendisi .gitignore'da) ve YOKLUĞU HATADIR.
    assert _MANIFEST.exists(), (
        f"manifest bulunamadi: {_MANIFEST}. Bu dosya BILEREK git'te izlenir — cift-base "
        f"regresyon kapisi onun uzerinde kosar. Silinmis/tasinmissa kapi etkisizlesir."
    )
    return json.loads(_MANIFEST.read_text(encoding="utf-8"))


def test_runtime_paketleri_v1_ve_v2de_ayni(manifest):
    """`base*` (v1) ile `runtimes.*` (v2) BİREBİR aynı olmalı — sha/size/url dahil."""
    for section, key, v1_key in _RUNTIME_PAIRS:
        v2 = (manifest.get(section) or {}).get(key)
        v1 = manifest.get(v1_key)
        if v2 is None and v1 is None:
            continue  # o platform hiç yayınlanmamış — ayrı bir sorun, burada değil
        assert v2 is not None, f"{v1_key} v1'de var ama v2 `{section}.{key}` YOK"
        assert v1 is not None, f"`{section}.{key}` v2'de var ama v1 `{v1_key}` YOK"
        for alan in ("url", "sha256", "size"):
            assert v2.get(alan) == v1.get(alan), (
                f"AYRISMA `{alan}`: v2 {section}.{key}={v2.get(alan)!r} != v1 {v1_key}={v1.get(alan)!r}. "
                f"Eski istemciler bayat digest'i kullanip kurulumu 'paket kurcalanmis' diye reddeder."
            )


def test_profil_paketleri_v1_ve_v2de_ayni(manifest):
    """`models.<profil>` (v2) ile `profiles.<profil>` (v1) birebir aynı olmalı."""
    models = manifest.get("models") or {}
    profiles = manifest.get("profiles") or {}
    assert models, "manifest'te hic model/profil paketi yok"
    assert set(models) == set(profiles), (
        f"profil kumeleri ayrisik: v2={sorted(models)} v1={sorted(profiles)}"
    )
    for k, v2 in models.items():
        assert v2 == profiles[k], f"AYRISMA profil `{k}`: v2={v2} != v1={profiles[k]}"


def test_her_paketin_digesti_ve_boyutu_makul(manifest):
    """Elle düzenlemede en sık kırılan iki alan: 64 haneli hex sha256 + pozitif boyut."""
    sayac = 0
    for section in ("runtimes", "models"):
        for key, entry in (manifest.get(section) or {}).items():
            sayac += 1
            sha = entry.get("sha256", "")
            assert isinstance(sha, str) and len(sha) == 64 and all(
                c in "0123456789abcdef" for c in sha.lower()
            ), f"{section}.{key}: gecersiz sha256 {sha!r}"
            assert isinstance(entry.get("size"), int) and entry["size"] > 0, (
                f"{section}.{key}: gecersiz size {entry.get('size')!r}"
            )
            assert str(entry.get("url", "")).startswith("https://"), (
                f"{section}.{key}: url HTTPS degil: {entry.get('url')!r}"
            )
    assert sayac >= 4, f"beklenenden az paket ({sayac}) — manifest bozulmus olabilir"


def test_launcher_blogu_da_dogrulanir(manifest):
    """⚠️ DENETİM 2026-08-04 (P2): kapı `launcher` bloğunu HİÇ denetlemiyordu.

    Oysa aynı denetimde Rust tarafı sertleştirildi: `installer_url` varken bozuk bir
    `launcher.sha256` artık TÜM manifest'i reddediyor. Yani operatör elle düzenlerken 63
    karakter yapıştırırsa kapı YEŞİL kalırken sahadaki HER kurulum kırılabilirdi.
    """
    l = manifest.get("launcher")
    if not l:
        pytest.skip("manifest'te launcher blogu yok (opsiyonel)")
    if not l.get("installer_url"):
        return  # installer_url yoksa sha256 zorunlu degil (Rust tarafi da oyle)
    sha = str(l.get("sha256", ""))
    assert len(sha) == 64 and all(c in "0123456789abcdef" for c in sha.lower()), (
        f"launcher.sha256 gecersiz ({sha!r}) — Rust tarafi TUM manifest'i reddeder, "
        f"sahadaki her kurulum kirilir."
    )
    assert isinstance(l.get("size"), int) and l["size"] > 0, f"launcher.size gecersiz: {l.get('size')!r}"
    assert str(l["installer_url"]).startswith("https://"), "launcher.installer_url HTTPS degil"
