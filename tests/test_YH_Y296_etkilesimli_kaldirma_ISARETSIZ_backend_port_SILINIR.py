# -*- coding: utf-8 -*-
"""YH B2 · Y296 (sahip, 17 Kasım: "Evet, aynısı olsun"): ETKİLEŞİMLİ kaldırmada "Uygulama verilerini sil" kutusu İŞARETSİZKEN de
bayat `backend.port` SİLİNİR, `veri_koku.txt` KALIR — Y294'teki sessiz kaldırma (S-YH.2) davranışının aynısı.

ÖLÇÜLEN (YH-B1 açık gözlemi, `YAYIN-HAZIRLIK.md` (1) A-ek): S-YH.2 yalnız sessiz / yükseltme dalını düzeltti; kutu işaretsiz
etkileşimli kaldırmada (Denetim Masası → Kaldır, kutu varsayılanı) `${Else}` dalı yalnız iletiyi yazıyordu → ölü backend'in portu
kurulum dizininde kalıyordu. PREUNINSTALL her yolda önce bobin E-stop'unu POST'lar, sonra backend'i öldürür → dosya bayattır.
Yükseltme (`/UPDATE`, etkileşimli olsa da) DEĞİŞMEZ: hiçbir şey silinmez.

Uçtan uca: S-YH.2 düzeneği (GERÇEK `hooks.nsi` kopyası, sahte kullanıcı dizinleri, kayıt defteri silmesi → iz satırı, gerçek
`makensis`, YALNIZ `NSIS_HOOK_POSTUNINSTALL`). Etkileşimli dal pencere AÇMADAN koşar: kopyada `${Silent}` düzenek değişkenine
(`$SahteSessiz = 1`) çevrilir, `MessageBox` iz satırına; sınama kurucusunun kendisi `/S` ile SESSİZ kalır. Çevrilmemiş `${Silent}` /
`MessageBox` kalırsa test HİÇBİR ŞEY KOŞTURMADAN düşer.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import capraz
import pytest
from test_YH_SYH2_sessiz_kaldirma_backend_port_SILINIR_veri_koku_KALIR import (
    _VERI_KOKU,
    _kanca_kopyasi,
    _korunanlar_yerinde,
    _kur,
    _makensis,
    _post_govdesi,
)

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows NSIS")


def _etkilesimli_kopya(hedef: Path, d: dict[str, Path]) -> None:
    _kanca_kopyasi(hedef, d["yerel"], d["dolasan"])  # S-YH.2 güvenlik ön denetimi burada
    metin = hedef.read_text(encoding="utf-8")
    assert "${Silent}" in _post_govdesi(metin), (
        "aparat: POSTUNINSTALL'da ${Silent} yok — sessiz / etkileşimli ayrımı değişmiş"
    )
    metin = metin.replace("${Silent}", "$SahteSessiz = 1")
    metin = re.sub(r"^(\s*)MessageBox\b.*$", r'\1DetailPrint "mesaj-kutusu-atlandi"', metin, flags=re.M)
    govde = "\n".join(s for s in _post_govdesi(metin).splitlines() if not s.lstrip().startswith(";"))
    kalan = [y for y in ("${Silent}", "MessageBox") if y in govde]
    if kalan:
        pytest.fail(f"etkileşimli kopya pencere açabilir, koşturulmadı: {kalan}")
    hedef.write_text(metin, encoding="utf-8")


def _kos(tmp: Path, *, yukseltme: bool, isaretli: bool = False) -> dict[str, Path]:
    mk = _makensis()
    if not mk:
        capraz.atla("makensis yok (PEMF_MAKENSIS / LOCALAPPDATA\\tauri\\NSIS)")
    d = _kur(tmp)
    _etkilesimli_kopya(tmp / "hooks_kopya.nsi", d)
    nsi = tmp / "y296_kosu.nsi"
    nsi.write_text(
        "Unicode true\n"
        f'OutFile "{tmp / "y296_kosu.exe"}"\n'
        'Name "Y296"\nRequestExecutionLevel user\nSilentInstall silent\n'
        '!include "LogicLib.nsh"\nVar UpdateMode\nVar DeleteAppDataCheckboxState\nVar SahteSessiz\n'
        f'!include "{tmp / "hooks_kopya.nsi"}"\n'
        "Section\n"
        "  StrCpy $SahteSessiz 0\n"
        f"  StrCpy $UpdateMode {1 if yukseltme else 0}\n"
        f"  StrCpy $DeleteAppDataCheckboxState {1 if isaretli else 0}\n"
        "  !insertmacro NSIS_HOOK_POSTUNINSTALL\n"
        "SectionEnd\n",
        encoding="utf-8",
    )
    r = subprocess.run(
        [mk, "/V2", str(nsi)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180
    )
    assert r.returncode == 0, r.stdout + r.stderr
    k = subprocess.run(
        [str(tmp / "y296_kosu.exe"), "/S", f"/D={d['kur']}"], capture_output=True, timeout=180, creationflags=0x08000000
    )
    assert k.returncode == 0, k.returncode
    return d


def test_KRITIK_Y296_etkilesimli_ISARETSIZ_kaldirmada_backend_port_SILINIR_veri_koku_KALIR(tmp_path):
    d = _kos(tmp_path, yukseltme=False)
    assert not (d["kur"] / "backend.port").exists(), (
        "etkileşimli kaldırmada (kutu işaretsiz) ölü backend'in bayat `backend.port`'u KALDI (Y296: silinmeli)"
    )
    vk = d["kur"] / "veri_koku.txt"
    assert vk.exists() and vk.read_bytes() == _VERI_KOKU.encode("utf-16-le"), (
        "kutu işaretsiz kaldırmada `veri_koku.txt` silindi / değişti (Y296: veri kökü kaydı KALIR)"
    )
    eksik = _korunanlar_yerinde(d)
    assert not eksik, f"kutu işaretsiz kaldırma (indirilenler korunur) başka dosyaları da sildi: {eksik}"


def test_Y296_KARSIT_etkilesimli_YUKSELTMEDE_hicbir_sey_silinmez(tmp_path):
    d = _kos(tmp_path, yukseltme=True)
    assert (d["kur"] / "backend.port").read_text(encoding="ascii") == "8123", (
        "etkileşimli yükseltmede `backend.port` silindi"
    )
    assert (d["kur"] / "veri_koku.txt").exists(), "etkileşimli yükseltmede `veri_koku.txt` silindi"
    assert not _korunanlar_yerinde(d), _korunanlar_yerinde(d)


def test_Y296_KARSIT_ISARETLI_tam_temizlik_AYNEN_port_ve_veri_koku_kaydi_gider(tmp_path):
    """Kutu işaretli dal değişmedi: port + veri kökü KAYDI + indirilenler + kullanıcı dizinleri gider (hasta verisi zaten kurulum
    dizininde değil — KVKK iletisi ayrı)."""
    d = _kos(tmp_path, yukseltme=False, isaretli=True)
    assert not (d["kur"] / "backend.port").exists() and not (d["kur"] / "veri_koku.txt").exists()
    assert not (d["kur"] / "runtime").exists() and not (d["yerel"] / "PEMF_System").exists()
