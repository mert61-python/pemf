# -*- coding: utf-8 -*-
"""YH · S-YH.2 (sahip Y294): SESSİZ kaldırmada bayat `backend.port` SİLİNİR, `veri_koku.txt` KALIR.

Tezgâh-2 listesi 6: `uninstall.exe /S` (veriler korunarak kaldırma) kurulum dizininde `backend.port` ve `veri_koku.txt`
bırakıyordu. `backend.port` artık ÖLÜ bir backend'in portudur — PREUNINSTALL her yolda önce bobin E-stop'unu POST'lar, sonra
`taskkill /F /IM PEMF_Backend.exe` ile backend'i öldürür; işaretli ("Uygulama verilerini sil") dal bu dosyayı zaten siliyordu.
Karar: sessiz kaldırmada port ipucu gider (yeniden kurulumda bayat porta yönelme yok); veri kökü kaydı KALIR (veriler korunarak
kaldırıldı → yeniden kurulum aynı hasta veri kökünü bulur). Yükseltme (`/UPDATE`) yolu DEĞİŞMEZ: hiçbir şey silinmez.

Uçtan uca: GERÇEK `hooks.nsi`'nin KOPYASI (`$LOCALAPPDATA` / `$APPDATA` → sahte dizin; kayıt defteri silmesi → iz satırı) gerçek
`makensis` ile sessiz bir sınama kurucusuna derlenir; YALNIZ `NSIS_HOOK_POSTUNINSTALL` koşar (PREUNINSTALL'ın E-stop / taskkill
satırları derlemeye GİRMEZ). Kopya koşmadan ÖNCE denetlenir: gerçek kullanıcı dizini / kayıt defteri / süreç çağrısı kalırsa test
HİÇBİR ŞEY KOŞTURMADAN düşer.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parents[1]
HOOKS = KOK / "launcher" / "app" / "windows" / "hooks.nsi"

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows NSIS")


def _makensis() -> str | None:
    adaylar = [os.environ.get("PEMF_MAKENSIS", "")]
    if os.environ.get("LOCALAPPDATA"):
        adaylar.append(str(Path(os.environ["LOCALAPPDATA"]) / "tauri" / "NSIS" / "makensis.exe"))
    return next((a for a in adaylar if a and Path(a).is_file()), None)


def _post_govdesi(metin: str) -> str:
    m = re.search(r"^!macro\s+NSIS_HOOK_POSTUNINSTALL\s*$(.*?)^!macroend\s*$", metin, flags=re.M | re.S)
    assert m, "hooks.nsi'de NSIS_HOOK_POSTUNINSTALL makrosu yok"
    return m.group(1)


def _kanca_kopyasi(hedef: Path, sahte_yerel: Path, sahte_dolasan: Path) -> None:
    metin = HOOKS.read_text(encoding="utf-8")
    metin = metin.replace("$LOCALAPPDATA", str(sahte_yerel)).replace("$APPDATA", str(sahte_dolasan))
    metin = re.sub(
        r"^(\s*)(DeleteRegKey|DeleteRegValue)\b.*$", r'\1DetailPrint "kayit-defteri-atlandi"', metin, flags=re.M
    )
    # GÜVENLİK ÖN DENETİMİ — koşturulacak gövde (POSTUNINSTALL) gerçek kaynağa dokunamaz. Tam yorum satırları (`;`) komut değildir
    # (gövdenin açıklaması PREUNINSTALL'ın `taskkill`ini anar); satır sonu yorumları bilerek TARANIR (ihtiyatlı).
    govde = "\n".join(s for s in _post_govdesi(metin).splitlines() if not s.lstrip().startswith(";"))
    yasak = [
        y
        for y in (
            "$LOCALAPPDATA",
            "$APPDATA",
            "$PROFILE",
            "$PROGRAMFILES",
            "$DESKTOP",
            "$SMPROGRAMS",
            "DeleteRegKey",
            "DeleteRegValue",
            "nsExec",
            "ExecWait",
            "taskkill",
            "Stop-Process",
        )
        if y in govde
    ]
    if yasak:
        pytest.fail(f"kanca kopyası GÜVENLİ DEĞİL, koşturulmadı: {yasak}")
    hedef.write_text(metin, encoding="utf-8")


_VERI_KOKU = "C:\\ProgramData\\PEMF_System\\PEMF_GUI"


def _kur(tmp: Path) -> dict[str, Path]:
    kur, yerel, dolasan = tmp / "kur", tmp / "yerel", tmp / "dolasan"
    for d in (kur / "runtime", kur / "ai_models", yerel / "PEMF_System", dolasan / "com.pemfmedical.vetclient"):
        d.mkdir(parents=True, exist_ok=True)
    (kur / "backend.port").write_text("8123", encoding="ascii")
    (kur / "veri_koku.txt").write_bytes(_VERI_KOKU.encode("utf-16-le"))
    (kur / "installed_packages.json").write_text('{"app": "a"}', encoding="utf-8")
    (kur / "auth_session.bin").write_bytes(b"\x01\x02")
    (kur / "runtime" / "r.txt").write_text("r", encoding="utf-8")
    (kur / "ai_models" / "m.bin").write_bytes(b"m")
    (yerel / "PEMF_System" / "hotspot.log").write_text("h", encoding="utf-8")
    (dolasan / "com.pemfmedical.vetclient" / "x.txt").write_text("x", encoding="utf-8")
    return {"kur": kur, "yerel": yerel, "dolasan": dolasan}


def _kos(tmp: Path, *, yukseltme: bool) -> dict[str, Path]:
    mk = _makensis()
    if not mk:
        capraz.atla("makensis yok (PEMF_MAKENSIS / LOCALAPPDATA\\tauri\\NSIS)")
    d = _kur(tmp)
    _kanca_kopyasi(tmp / "hooks_kopya.nsi", d["yerel"], d["dolasan"])
    nsi = tmp / "syh2_kosu.nsi"
    nsi.write_text(
        "Unicode true\n"
        f'OutFile "{tmp / "syh2_kosu.exe"}"\n'
        'Name "S-YH.2"\nRequestExecutionLevel user\nSilentInstall silent\n'
        '!include "LogicLib.nsh"\nVar UpdateMode\nVar DeleteAppDataCheckboxState\n'
        f'!include "{tmp / "hooks_kopya.nsi"}"\n'
        "Section\n"
        f"  StrCpy $UpdateMode {1 if yukseltme else 0}\n"
        "  StrCpy $DeleteAppDataCheckboxState 0\n"
        "  !insertmacro NSIS_HOOK_POSTUNINSTALL\n"
        "SectionEnd\n",
        encoding="utf-8",
    )
    r = subprocess.run(
        [mk, "/V2", str(nsi)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180
    )
    assert r.returncode == 0, r.stdout + r.stderr
    k = subprocess.run(
        [str(tmp / "syh2_kosu.exe"), "/S", f"/D={d['kur']}"], capture_output=True, timeout=180, creationflags=0x08000000
    )
    assert k.returncode == 0, k.returncode
    return d


def _korunanlar_yerinde(d: dict[str, Path]) -> list[str]:
    beklenen = [
        d["kur"] / "installed_packages.json",
        d["kur"] / "auth_session.bin",
        d["kur"] / "runtime" / "r.txt",
        d["kur"] / "ai_models" / "m.bin",
        d["yerel"] / "PEMF_System" / "hotspot.log",
        d["dolasan"] / "com.pemfmedical.vetclient" / "x.txt",
    ]
    return [str(p) for p in beklenen if not p.exists()]


def test_KRITIK_SYH2_sessiz_kaldirmada_backend_port_SILINIR_veri_koku_KALIR(tmp_path):
    d = _kos(tmp_path, yukseltme=False)
    assert not (d["kur"] / "backend.port").exists(), (
        "sessiz kaldırmada ölü backend'in bayat `backend.port`'u KALDI (S-YH.2: silinmeli)"
    )
    vk = d["kur"] / "veri_koku.txt"
    assert vk.exists(), "sessiz kaldırmada `veri_koku.txt` SİLİNDİ (S-YH.2: veri kökü kaydı KALIR)"
    assert vk.read_bytes() == _VERI_KOKU.encode("utf-16-le"), "`veri_koku.txt` içeriği değişti"
    eksik = _korunanlar_yerinde(d)
    assert not eksik, f"sessiz kaldırma (veriler korunur) başka dosyaları da sildi: {eksik}"


def test_SYH2_KARSIT_yukseltmede_HICBIR_sey_silinmez_port_dosyasi_dahil(tmp_path):
    d = _kos(tmp_path, yukseltme=True)
    assert (d["kur"] / "backend.port").read_text(encoding="ascii") == "8123", (
        "yükseltmede (`/UPDATE`) `backend.port` silindi — yükseltme yolu DEĞİŞMEMELİ"
    )
    assert (d["kur"] / "veri_koku.txt").exists(), "yükseltmede `veri_koku.txt` silindi"
    eksik = _korunanlar_yerinde(d)
    assert not eksik, f"yükseltmede dosya silindi: {eksik}"


def test_SYH2_veri_koku_silmesi_YALNIZ_isaretli_tam_temizlik_dalinda():
    """`veri_koku.txt` silmesi tek yerde: "Uygulama verilerini sil" İŞARETLİ dalında (sessiz / yükseltme dalında DEĞİL)."""
    govde = _post_govdesi(HOOKS.read_text(encoding="utf-8"))
    sessiz = govde.split("${ElseIf} $DeleteAppDataCheckboxState = 1", 1)
    assert len(sessiz) == 2, "işaretli dal (`${ElseIf} $DeleteAppDataCheckboxState = 1`) bulunamadı"
    assert 'Delete "$INSTDIR\\veri_koku.txt"' not in sessiz[0], "sessiz / yükseltme dalı `veri_koku.txt`'yi siliyor"
    assert sessiz[1].count('Delete "$INSTDIR\\veri_koku.txt"') == 1, "işaretli dal `veri_koku.txt`'yi silmiyor"
