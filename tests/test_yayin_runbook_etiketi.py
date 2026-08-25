# Author: mertaygn, cglrgrkn
"""YAYIN RUNBOOK'U PAKET ETİKETİ — 2. tur denetimi bulgu [3.4] (2026-08-20).

ÖLÇÜLEN DURUM: BUILD.md §6 ve pemf-app-packages/README.md, paketleri (base-app/base-deps/base)
hâlâ `client-app-v1.8.0` SABİT etiketine yükletiyordu (0e2b1ed, sürüm-başına-etiket düzeninden
ÖNCE yazılmış ve hiç güncellenmemiş). Oysa `make_manifest.py` 1.9.16'dan beri paket URL'lerini
`--tag client-app-v<sürüm>` etiketine yazar (sha değişmeyenlerin URL'si korunur). Runbook'u
harfiyen izleyen bir yayında manifest v1.9.18/base-app.zip'i gösterir ama dosya v1.8.0'a
yüklenmiştir → sahadaki HER güncelleme ve HER taze kurulum 404 alır (net.rs 404'ü deterministik
sayar, tekrar denemez). Son yayınlarda kaza olmaması betiğe değil yayıncının ezberine bağlıydı.

SÖZLEŞME (bu kapının kilitlediği):
  · PAKET yükleme satırları sürüm-başına etikete gider — `client-app-v1.8.0` ASLA;
  · `manifest.json` yükleme satırları SABİT `client-app-v1.8.0` adresine gider (manifest'in
    KENDİ adresi sabittir; launcher oradan okur — bu YANLIŞ değil, tek sabit o);
  · gerçeklik çıpası: depodaki manifest'in layers.app URL'si zaten sürüm-başına etikettedir —
    tek-etiket düzenine bilinçli dönülürse önce bu çıpa kırmızıya döner, test bilerek güncellenir.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]

PAKETLER = ("base-app.zip", "base-deps.zip", "base.zip")


def _yukleme_satirlari(metin: str):
    return [s for s in metin.splitlines() if "gh release upload" in s]


def _oku(rel: str) -> str:
    return (KOK / rel).read_text(encoding="utf-8", errors="replace")


def test_KRITIK_runbook_paketleri_SABIT_v180_etiketine_yuklemiyor():
    for rel in ("BUILD.md", "pemf-app-packages/README.md"):
        for satir in _yukleme_satirlari(_oku(rel)):
            if any(p in satir for p in PAKETLER):
                assert "client-app-v1.8.0" not in satir, (
                    f"{rel}: paket yükleme satırı SABİT v1.8.0 etiketini hedefliyor — manifest "
                    f"URL'leri sürüm-başına etikete yazılır; bu talimat izlenirse saha-geneli 404 "
                    f"(bulgu [3.4]): {satir.strip()!r}"
                )


def test_KRITIK_runbook_paket_yuklemesini_surum_etiketiyle_TARIF_EDIYOR():
    """Yasak yetmez — doğru talimat da olmalı: en az bir paket-yükleme satırı sürüm-başına
    `client-app-v<sürüm>` biçimini kullanmalı (yer tutucu ya da somut sürüm)."""
    for rel in ("BUILD.md", "pemf-app-packages/README.md"):
        satirlar = [
            s
            for s in _yukleme_satirlari(_oku(rel))
            if any(p in s for p in PAKETLER) and re.search(r"client-app-v(?!1\.8\.0)", s)
        ]
        assert satirlar, f"{rel}: sürüm-başına etikete paket yükleyen hiçbir örnek satır yok"


def test_KARSIT_KANIT_manifestin_KENDI_adresi_sabit_v180_KALIR():
    """manifest.json'ın yükleme adresi SABİTTİR (launcher oradan okur) — 'v1.8.0 yasak' kuralı
    yanlışlıkla manifest satırına genişletilirse yayın zinciri kopar; bu yön de kilitli."""
    for rel in ("BUILD.md", "pemf-app-packages/README.md"):
        satirlar = [s for s in _yukleme_satirlari(_oku(rel)) if "manifest.json" in s]
        assert satirlar, f"{rel}: manifest.json yükleme satırı yok"
        assert any("client-app-v1.8.0" in s for s in satirlar), (
            f"{rel}: manifest.json artık sabit v1.8.0'a yüklenmiyor görünüyor — launcher'ın "
            f"okuduğu adres değişmişse bu test BİLİNÇLİ güncellenmeli: {satirlar!r}"
        )


def test_GERCEKLIK_CIPASI_manifest_layers_app_surum_etiketinde():
    m = json.loads(_oku("pemf-app-packages/manifest.json"))
    url = m["layers"]["win-x64"]["app"]["url"]
    assert "client-app-v" in url and "client-app-v1.8.0/" not in url, (
        f"layers.app URL'si artık sürüm-başına etikette değil ({url!r}) — tek-etiket düzenine "
        "dönüldüyse runbook kuralı ve bu test birlikte, BİLİNÇLİ güncellenmeli"
    )


def test_KRITIK_C7_runbook_surumsuz_EXE_release_assets_ten_alinir():
    """🔴 C7 (denetim 2026-08-24): §6 launcher `gh release create` satırı sürümsüz
    PEMFVetClient-Setup.exe'yi DEPO KÖKÜNDEN alıyordu (APK ise `release_assets\` önekli — asimetri).
    Kökte 2026-08-08 tarihli BAYAT bir kopya duruyor (gitignore'lu, hiçbir build tazelemiyor) →
    harfiyen izlenirse aynı etikete BAYAT launcher yüklenir; manifest sha taze kopyadan alınırsa
    saha self-update'i fail-closed düşer. Y1 (Setup dosyası iki adla yüklenir) EXE'nin SÜRÜMSÜZ
    kopyasını da release_assets'ten (taze) almalı — APK ile simetrik."""
    metin = _oku("BUILD.md")
    m = re.search(r"gh release create launcher-v\S+[^\n]*", metin)
    assert m, "launcher `gh release create` satırı bulunamadı — BUILD.md §6 biçimi değişmiş"
    satir = m.group(0)
    assert "PEMFVetClient-Setup.exe" in satir, "önkoşul: satır sürümsüz Setup.exe yüklüyor"
    assert re.search(r"release_assets[\\/]PEMFVetClient-Setup\.exe", satir), (
        "sürümsüz PEMFVetClient-Setup.exe DEPO KÖKÜNDEN alınıyor (release_assets öneki yok) — kök "
        "bayat kopya tuzağı; APK gibi release_assets'ten (taze) alınmalı (C7)"
    )
