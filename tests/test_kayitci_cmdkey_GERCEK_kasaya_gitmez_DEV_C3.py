# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""DEV-C3 (D1B §8 #10 · D1C §7 #16): kimlik kasası testlerinin aparatı GERÇEK `cmdkey.exe`'yi HİÇ başlatmaz — kafessiz koşuda da.

`tests/test_teardown_kimlik_dogrulama.py` ve `tests/test_teardown_system_kasasi.py` kayıtçı `cmdkey`i (`tests/kayitci_cmdkey.py`)
kullanır. Ölçüm (HEAD 5bc99be1):
  • Python tarafı kayıtçıyı `cmd.exe /c <tmp>\\kayitci_cmdkey\\cmdkey.cmd` diye başlatıyordu → adı cmdkey olan program; test kafesi
    (gerçek kasayı korur) bunu gerçek araçtan AYIRAMAZ → kafeste 5 test kırmızı (kafes günlüğü: 8 ENGEL, hepsi kayıtçı yolu).
  • Bekçi yalnız `subprocess.run`ı sarıyordu: `Popen` / `call` / `os.system` / `os.startfile` ile başlatılan `cmdkey`i GÖRMEZ.
  • Torun süreçlerin (pwsh / Windows PowerShell 5.1) yalın `cmdkey`i kayıtçıya çözdüğü yalnız dolaylı iddia ediliyordu.
Bu kapı:
  (1) Bekçi her başlatma yolunda adı cmdkey olan programı süreç BAŞLATILMADAN durdurur. Karşıt kollar `_winapi.CreateProcess`,
      `os.system`, `os.spawnv`, `os.startfile` SAHTE iken koşar → bekçi bozulsa bile hiçbir gerçek süreç başlamaz.
  (2) Bekçi aşırı engellemez (adı cmdkey olmayan program başlatma yoluna ulaşır) ve kayıtçı uçtan uca çalışır (sahte kasaya yazar).
  (3) `kur` sonrası pwsh 7 ve PS 5.1 yalın `cmdkey`i KAYITÇIYA çözer (Get-Command kanıtı; araç çalıştırılmaz).
  (4) `scripts/pemf_teardown.ps1` cmdkey'i yalnız ADIYLA çağırır: tam yollu çağrıyı PATH kayıtçısı (ve işlev gölgesi) yakalamaz —
      ürün betiği tam yola geçerse önce aparat değişmeli; bu kapı o geçişi teardown testleri gerçek kasaya gitmeden yakalar.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import kayitci_cmdkey
import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="cmdkey / Credential Manager yalnız Windows")

_KOK = Path(__file__).resolve().parents[1]
_TEARDOWN = _KOK / "scripts" / "pemf_teardown.ps1"
_PWSH = shutil.which("pwsh")
_PS51 = shutil.which("powershell")
_SYS32_CMDKEY = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmdkey.exe")


class _SahteBaslatma(RuntimeError):
    """Bekçinin ARDINDAKİ başlatma katmanı (sahte) — buraya ulaşmak 'bekçi geçirdi' demektir."""


@pytest.fixture()
def sahte_baslatma(tmp_path, monkeypatch):
    """Başlatma katmanlarını ÖNCE sahteye çevir, SONRA kayıtçıyı kur: bekçi bunları sarar; bekçi bozuksa sahte yakalanır."""
    ulasan: list[str] = []

    def _sahte(ad):
        def _f(*a, **k):
            ulasan.append(ad)
            raise _SahteBaslatma(f"{ad}: başlatma katmanına ulaşıldı (bekçi geçirdi)")

        return _f

    monkeypatch.setattr(subprocess._winapi, "CreateProcess", _sahte("CreateProcess"))
    monkeypatch.setattr(os, "system", _sahte("os.system"))
    monkeypatch.setattr(os, "spawnv", _sahte("os.spawnv"))
    monkeypatch.setattr(os, "startfile", _sahte("os.startfile"))
    kayitci = kayitci_cmdkey.kur(tmp_path, monkeypatch)
    return kayitci, ulasan


def _yollar(kayitci):
    yok = str(Path(kayitci.kok).parent / "yok" / "cmdkey.exe")
    return {
        "run_yalin": lambda: subprocess.run(["cmdkey", "/list:PEMF_GATE_X"], capture_output=True),
        "popen_sys32_tam_yol": lambda: subprocess.Popen([_SYS32_CMDKEY, "/list:PEMF_GATE_X"]),
        "popen_buyuk_harf_exe": lambda: subprocess.Popen(["CMDKEY.EXE", "/list"]),
        "check_output_shell": lambda: subprocess.check_output("cmdkey /list:PEMF_GATE_X", shell=True),
        "call_cmd_c_yalin": lambda: subprocess.call(["cmd.exe", "/c", "cmdkey", "/list"]),
        "run_cmd_c_kayitci_shim": lambda: subprocess.run(["cmd.exe", "/c", str(kayitci.kok / "cmdkey.cmd"), "/list"]),
        "run_executable_param": lambda: subprocess.run(["x", "/list"], executable=_SYS32_CMDKEY),
        "os_system": lambda: os.system(f'"{yok}" /list:PEMF_GATE_X'),
        "os_spawnv": lambda: os.spawnv(os.P_WAIT, _SYS32_CMDKEY, ["cmdkey", "/list"]),
        "os_startfile": lambda: os.startfile(_SYS32_CMDKEY),
    }


_YOL_ADLARI = [
    "run_yalin",
    "popen_sys32_tam_yol",
    "popen_buyuk_harf_exe",
    "check_output_shell",
    "call_cmd_c_yalin",
    "run_cmd_c_kayitci_shim",
    "run_executable_param",
    "os_system",
    "os_spawnv",
    "os_startfile",
]


@pytest.mark.parametrize("yol", _YOL_ADLARI)
def test_KRITIK_bekci_cmdkey_i_HER_baslatma_yolunda_surec_BASLAMADAN_durdurur(sahte_baslatma, yol):
    kayitci, ulasan = sahte_baslatma
    with pytest.raises(AssertionError, match="GERÇEK cmdkey'i"):
        _yollar(kayitci)[yol]()
    assert ulasan == [], f"bekçi '{yol}' yolunda cmdkey'i başlatma katmanına GEÇİRDİ: {ulasan}"


def test_karsit_bekci_ASIRI_ENGELLEMEZ_baska_program_baslatma_katmanina_ulasir(sahte_baslatma):
    """Karşıt: adı cmdkey OLMAYAN program (adında 'cmdkey' geçse bile) bekçiden geçer — sahte katman yakalar."""
    kayitci, ulasan = sahte_baslatma
    for komut in (
        [sys.executable, "-c", "pass"],
        ["powershell.exe", "-NoProfile", "-File", str(kayitci.kok / "kayitci_cmdkey.ps1"), "/list"],
        ["cmd.exe", "/c", "echo", "cmdkey"],
    ):
        with pytest.raises(_SahteBaslatma):
            subprocess.run(komut, capture_output=True)
    assert ulasan == ["CreateProcess"] * 3


def test_KRITIK_kayitci_uctan_uca_SAHTE_kasaya_yazar_gercek_programi_baslatmaz(tmp_path, monkeypatch):
    """Karşıt (olumlu): kayıtçı çağrısı bekçiden ve test kafesinden geçer, sahte kasaya yazar, çağrıyı kaydeder."""
    kayitci = kayitci_cmdkey.kur(tmp_path, monkeypatch)
    ad = f"PEMF_GATE_DEVC3_{uuid.uuid4().hex}"
    r = kayitci_cmdkey.cmdkey(f"/add:{ad}", "/user:x", "/pass:y")
    assert r.returncode == 0, f"kayıtçı /add başarısız: {r.stdout!r} {r.stderr!r}"
    assert ad in kayitci.kasa.read_text(encoding="utf-8-sig"), "kayıtçı sahte kasaya yazmadı"
    assert f"/add:{ad} /user:x /pass:y" in kayitci_cmdkey.cagrilar(kayitci)
    liste = kayitci_cmdkey.cmdkey(f"/list:{ad}").stdout.decode("utf-8", "replace")
    assert liste.count(ad) == 2, f"kayıtçı /list:<ad> tel sözleşmesi bozuk: {liste!r}"
    sil = kayitci_cmdkey.cmdkey(f"/delete:{ad}")
    assert sil.returncode == 0 and ad not in kayitci.kasa.read_text(encoding="utf-8-sig")
    assert kayitci_cmdkey.cmdkey(f"/delete:{ad}").returncode == 1, (
        "var olmayan /delete rc 1 olmalı (gerçek cmdkey gibi)"
    )


_KABUKLAR = [pytest.param(_PWSH, id="pwsh7"), pytest.param(_PS51, id="ps51")]


@pytest.mark.parametrize("kabuk", _KABUKLAR)
def test_KRITIK_torun_kabuk_yalin_cmdkey_i_KAYITCIYA_cozer(tmp_path, monkeypatch, kabuk):
    """`kur` sonrası teardown sürücülerinin kabukları yalın `cmdkey`i kayıtçıya çözer (Get-Command; araç ÇALIŞTIRILMAZ)."""
    if kabuk is None:
        pytest.skip("kabuk bulunamadı")
    kayitci = kayitci_cmdkey.kur(tmp_path, monkeypatch)
    r = subprocess.run(
        [kabuk, "-NoProfile", "-NonInteractive", "-Command", "(Get-Command cmdkey).Source"],
        capture_output=True,
        timeout=60,
    )
    kaynak = r.stdout.decode("utf-8", "replace").strip()
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")[-800:]
    assert os.path.normcase(kaynak) == os.path.normcase(str(kayitci.kok / "cmdkey.cmd")), (
        f"{Path(kabuk).name} yalın cmdkey'i kayıtçıya DEĞİL {kaynak!r}'e çözüyor → teardown testleri GERÇEK kasaya gider"
    )


def test_KRITIK_teardown_betigi_cmdkey_i_yalniz_ADIYLA_cagirir():
    """Tam yollu (`...\\System32\\cmdkey.exe`) ya da uzantılı çağrıyı PATH kayıtçısı yakalamaz → teardown testleri gerçek kasaya
    giderdi. Ürün betiği tam yola geçecekse ÖNCE aparat (gölge) değişmeli; bu kapı o anı, gerçek kasaya gidilmeden kırmızıyla yakalar."""
    metin = _TEARDOWN.read_text(encoding="utf-8-sig")
    yasak = [
        (no, satir.strip())
        for no, satir in enumerate(metin.splitlines(), 1)
        if re.search(r"(?i)cmdkey\.(exe|com|bat|cmd)\b|[\\/]cmdkey\b|Join-Path[^\n]*['\"]cmdkey", satir)
    ]
    assert not yasak, f"pemf_teardown.ps1 cmdkey'i tam yol/uzantıyla çağırıyor (kayıtçı atlanır): {yasak}"
    assert re.search(r"&\s*cmdkey\s+/delete:", metin), "çıpa kaydı: `& cmdkey /delete:` çağrısı bulunamadı"
