# Author: mertaygn, cglrgrkn
"""İZLENEN METİN DOSYALARINDA BAŞIBOŞ KONTROL BAYTI OLMAZ.

NEDEN VAR: BUILD.md'ye bir belge eki kabuk heredoc'u üzerinden yazılırken `\b` ve `\r` kaçış
dizileri YORUMLANDI ve dosyaya 0x08 (backspace) / 0x0D (CR) baytları olarak düştü. Sonuç göze
çarpmıyordu — terminal `scripts\restore_assets.ps1` yerine `scriptsestore_assets.ps1` gösteriyor,
CR ise satırı başa sarıp önceki metnin üzerine yazıyordu. 5 build komutu KOPYALA-YAPIŞTIR
YAPILDIĞINDA VAR OLMAYAN yola gidiyordu (2026-08-18'de ölçüldü: `.\bootstrap.ps1` → `.ootstrap.ps1`).

Bu kapı yalnız belgeyi değil, izlenen TÜM metin dosyalarını tarar: aynı heredoc hatası bir
.ps1/.py içine düşseydi çalışma zamanında kırılırdı.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]

# 0x09 sekme, 0x0A satırsonu ve CRLF'in 0x0D'si meşru. Geri kalan C0 kontrolleri metinde İŞE YARAMAZ.
YASAK = {0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x0B, 0x0C, 0x0E, 0x0F, 0x1A, 0x1B}

METIN_UZANTILARI = {
    ".md",
    ".py",
    ".ps1",
    ".psm1",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".yml",
    ".yaml",
    ".toml",
    ".cfg",
    ".ini",
    ".txt",
    ".sql",
    ".sh",
    ".rs",
    ".html",
    ".css",
    ".c",
    ".h",
    ".cpp",
    ".ino",
}

NUL = chr(0)

# ⚠️ ÜRETİLMİŞ ÇIKTI — elle yazılmadığı için bu kapının konusu değil. `pemf_vet_landing/` bir SSR
# sitesinin birebir çıkarılmış render'ı; hidrasyon yükündeki `__root__\x00` / `\x00download download`
# rota kimlikleri framework'ün KENDİ ayracıdır (2026-08-18'de 4 dosyada 5'er NUL ölçüldü, tarayıcı
# sorunsuz açıyor). Buradan gelen NUL'ı kusur saymak kapıyı sürekli yanlış-kırmızı yapardı.
URETILMIS = ("pemf_vet_landing/",)


def _izlenen_metin_dosyalari() -> list[Path]:
    ch = subprocess.run(["git", "ls-files", "-z"], cwd=KOK, capture_output=True, text=True, timeout=120)
    if ch.returncode != 0:
        pytest.skip("git deposu değil")
    yollar = []
    for ad in ch.stdout.split(NUL):
        if not ad:
            continue
        if ad.startswith(URETILMIS):
            continue
        p = KOK / ad
        if p.suffix.lower() in METIN_UZANTILARI and p.is_file():
            yollar.append(p)
    return yollar


def _kusurlu(ham: bytes) -> set[int]:
    """CRLF'in CR'ini meşru say; yalnız YALNIZ-CR'ı ve diğer C0 kontrollerini bildir."""
    kotu = {b for b in ham if b in YASAK}
    i = ham.find(0x0D)
    while i != -1:
        if i + 1 >= len(ham) or ham[i + 1] != 0x0A:
            kotu.add(0x0D)
            break
        i = ham.find(0x0D, i + 1)
    return kotu


def test_KRITIK_izlenen_metin_dosyalarinda_kacis_yenmis_kontrol_bayti_YOK():
    dosyalar = _izlenen_metin_dosyalari()
    assert len(dosyalar) > 200, f"tarama çok dar ({len(dosyalar)}) — kapı boş dönüyor olabilir"

    kusurlu = {}
    for p in dosyalar:
        kotu = _kusurlu(p.read_bytes())
        if kotu:
            kusurlu[p.relative_to(KOK).as_posix()] = sorted(hex(b) for b in kotu)

    assert not kusurlu, (
        "İzlenen metin dosyalarında başıboş kontrol baytı var: "
        + "; ".join(f"{k} -> {v}" for k, v in sorted(kusurlu.items()))
        + ". Çoğunlukla kabuk heredoc'unun kaçış dizisini yorumlamasından olur "
        + r"(0x08 = yenmiş '\b', 0x0D = yenmiş '\r'). İlgili kaçışı geri yazın."
    )


def test_KARSIT_KANIT_kapi_gercekten_yakaliyor():
    """Kapının boş geçmediğini kanıtla: BUILD.md'nin bozuk hâli YAKALANMALI."""
    saglam = (KOK / "BUILD.md").read_bytes()
    assert not _kusurlu(saglam), "BUILD.md şu an temiz olmalı"

    bozuk = saglam.replace(rb"scripts\restore_assets", b"scripts" + bytes([13]) + b"estore_assets")
    assert bozuk != saglam, "mutasyon uygulanamadı — test bayat"
    assert 0x0D in _kusurlu(bozuk), "kapı yenmiş CR'i KAÇIRIYOR"

    bozuk2 = saglam.replace(rb".\bootstrap", b"." + bytes([8]) + b"ootstrap")
    assert bozuk2 != saglam, "mutasyon uygulanamadı — test bayat"
    assert 0x08 in _kusurlu(bozuk2), "kapı yenmiş BS'i KAÇIRIYOR"


def test_KARSIT_KANIT_muafiyet_kapiyi_BOSALTMIYOR():
    """ "Kırmızıyı sustur" diye muafiyet listesini genişleten bir yamayı yakalar.

    Kapının değeri kapsamında: elle yazılan her katman taranmaya DEVAM etmeli.
    """
    assert len(URETILMIS) <= 2, f"muafiyet listesi şişmiş: {URETILMIS}"

    tarandi = {p.relative_to(KOK).as_posix().split("/")[0] for p in _izlenen_metin_dosyalari()}
    for katman in ("servers", "scripts", "build_tools", "launcher", "pf", "pemf-vet-web", "tests", "docs"):
        assert katman in tarandi, f"{katman}/ tarama dışında kalmış — kapı bu katmanı KORUMUYOR"


def test_KARSIT_KANIT_mesru_CRLF_ve_sekme_YANLIS_KIRMIZI_vermez():
    """Windows deposu: CRLF'li ve sekmeli dosyalar kusurlu SAYILMAMALI."""
    assert not _kusurlu(b"birinci" + bytes([13, 10]) + b"ikinci" + bytes([13, 10]))
    assert not _kusurlu(b"anahtar" + bytes([9]) + b"deger" + bytes([10]))
