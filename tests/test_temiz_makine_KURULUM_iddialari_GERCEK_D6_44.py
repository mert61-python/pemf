# -*- coding: utf-8 -*-
"""D6.44 (Y28) — `docs/TEMIZ-MAKINE.md` Yol A kurulum iddiaları ÜRÜN KAYNAĞIYLA aynı: kurulum dosyası İMZASIZ.

ÖLÇÜLEN DURUM (HEAD ebf1c3fe, 2026-10-28):
  · `docs/TEMIZ-MAKINE.md:24` "Yayımcı: IBIA Teknoloji Ltd. Şti. (UAC uyarısında bu görünmeli)" — `launcher/app/tauri.conf.json`
    `bundle.windows`'ta imza ayarı (`certificateThumbprint` / `signCommand`) YOK, `build_tools/PEMF_Backend_Setup.iss`'te `SignTool`
    YOK → kurulum Authenticode ile imzalanmaz; UAC "Bilinmeyen yayımcı" gösterir. `bundle.publisher` yalnız paket meta verisidir.
    Sahip kararı Y28: kod imzası ŞİMDİLİK alınmaz; belge "Bilinmeyen yayımcı" uyarısını ve SHA ile doğrulamayı anlatır.
  · Gerçek ikilinin imzası (`Get-AuthenticodeSignature`) bu kapıda ÖLÇÜLMEZ (release_assets'e dokunulmaz) — kaynak düzeyinde imza
    yapılandırmasının YOKLUĞU ölçülür; imza yapılandırması eklenirse kapı belgeyi güncellemeye zorlar.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from utils.path_utils import kaynak_kokunu_bul

KOK = Path(kaynak_kokunu_bul(__file__))
BELGE = KOK / "docs" / "TEMIZ-MAKINE.md"
TAURI = KOK / "launcher" / "app" / "tauri.conf.json"
ISS = KOK / "build_tools" / "PEMF_Backend_Setup.iss"


def _yol_a() -> str:
    m = BELGE.read_text(encoding="utf-8")
    bas = m.index("## Yol A")
    son = m.index("\n## ", bas + 5)
    return re.sub(r"~~.*?~~", " ", m[bas:son], flags=re.S)


def _imza_yapilandirmasi_var() -> bool:
    w = json.loads(TAURI.read_text(encoding="utf-8")).get("bundle", {}).get("windows", {})
    tauri_imza = any(k in w for k in ("certificateThumbprint", "signCommand"))
    iss_imza = bool(re.search(r"^\s*SignTool\s*=", ISS.read_text(encoding="utf-8"), re.M | re.I))
    return tauri_imza or iss_imza


def test_KRITIK_kurulum_IMZASIZ_iken_belge_imzali_yayimci_IDDIA_ETMEZ():
    assert not _imza_yapilandirmasi_var(), (
        "imza yapılandırması EKLENMİŞ — Y28 değişti mi? TEMIZ-MAKINE 'Bilinmeyen yayımcı' anlatımını bilinçli güncelleyin"
    )
    a = _yol_a()
    assert not re.search(r"UAC uyarısında bu görünmeli", a), (
        "TEMIZ-MAKINE: imzasız kurulumda UAC yayımcı adı GÖSTERMEZ (Y28)"
    )
    assert not re.search(r"Yayımcı:\s*\*\*I[BİI]{1,2}A", a), "TEMIZ-MAKINE: 'Yayımcı: İBİA' iddiası (imzasız kurulum)"
    for parca in ("Bilinmeyen yayımcı", "Y28", "Get-FileHash", "SHA256", "launcher.sha256"):
        assert parca in a, f"TEMIZ-MAKINE Yol A '{parca}' anmalı (imzasız kurulumun doğrulama yolu — Y28)"


# ════════════════════════════════════════════════════════════════════════════════════════════════════════════
# TEMIZ-MAKINE belge kolları (D6.42 · D6.70 · A-47) — kurulum dosyası boyutu MANİFESTTEN; "termal koruma cihazda gömülü" YOK.
# ÖLÇÜLEN (HEAD ebf1c3fe): `:22` "Kurulum ~11 MB'lık launcher'ı yazar" ↔ `pemf-app-packages/manifest.json` `launcher.size` =
# 265.032.239 B (1.9.51; `tauri.conf.json` `webviewInstallMode: offlineInstaller` — WebView2 çevrimdışı kurucusu pakette).
# `:30-31` "Yerel acil-durdurma + termal koruma zaten cihazda gömülü" ↔ A-47: termal kesme / 48 °C engelleme HİÇBİR katmanda yok.
# ════════════════════════════════════════════════════════════════════════════════════════════════════════════

MANIFEST = KOK / "pemf-app-packages" / "manifest.json"
#: Belgedeki MB değeri manifestten en çok bu oranda sapabilir (yuvarlama payı).
BOYUT_TOLERANSI = 0.10


def test_KRITIK_kurulum_dosyasi_boyutu_MANIFESTLE_ayni():
    boyut = json.loads(MANIFEST.read_text(encoding="utf-8"))["launcher"]["size"]
    mb = boyut / 1_000_000
    a = _yol_a()
    m = re.search(r"Kurulum dosyası ~(\d+)\s*MB", a)
    assert m, "TEMIZ-MAKINE Yol A kurulum dosyası boyutunu ('Kurulum dosyası ~N MB') yazmalı"
    yazan = int(m.group(1))
    assert abs(yazan - mb) / mb <= BOYUT_TOLERANSI, (
        f"TEMIZ-MAKINE ~{yazan} MB diyor, manifest launcher.size {mb:.0f} MB"
    )
    assert not re.search(r"~11 MB'lık", a), "eski '~11 MB'lık launcher' iddiası (manifest ~265 MB)"


def test_KRITIK_termal_koruma_cihazda_gomulu_DEMEZ_A47():
    a = _yol_a()
    assert not re.search(r"termal koruma (zaten )?cihazda gömülü|\+\s*termal koruma", a, re.I), (
        "TEMIZ-MAKINE 'termal koruma cihazda gömülü' diyor — A-47: termal kesme YOK"
    )
    assert not re.search(r"sıcaklık kesmesi önceliklidir", a, re.I)
    assert "A-47" in a and re.search(r"[Tt]ermal koruma[^\n]{0,40}YOK", a), (
        "TEMIZ-MAKINE Yol A 'termal koruma … YOK (A-47)' demeli"
    )
