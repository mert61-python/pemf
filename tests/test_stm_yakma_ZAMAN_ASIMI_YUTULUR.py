# -*- coding: utf-8 -*-
# Author: mertaygn
"""Yakıcı ASILIRSA istisna AÇILIŞ YOLUNA KAÇMAZ — hata KODUNA dönüşür.

BULGU (2026-09-22, donanım runbook'u türetilirken ölçüldü): `_kos()` içindeki
`subprocess.run(..., timeout=...)` zaman aşımında `subprocess.TimeoutExpired` FIRLATIR.
Bu istisna ne `yedek_al()`de, ne `yak()`ta, ne de `yakma_akisi()`nda yakalanıyordu.

NEDEN ÖNEMLİ — bu bir AÇILIŞ yolu:
`backend_service.main()` açılışta `_donanim_guncellemesi_safe(core, logger)` çağırıyor ve o
da `firmware_manager.acilis_denetimi` → `stm_yakma.yakma_akisi` zincirini sürüyor. Zincirin
içindeki bir istisna `_donanim_guncellemesi_safe` tarafından YUTULUYOR — ama ancak
**yakıcı asılmayı bitirdikten sonra**. O ana kadar açılış BLOKE: yedekte 300 sn, yakmada
600 sn. Tıbbi cihaz 10 dakika açılmayabilir ve sebebi hiçbir yerde "zaman aşımı" demez.

DOĞRU DAVRANIŞ: `_kos()` istisnayı BAŞARISIZLIK KODUNA çevirir. Çağıranlar zaten `rc != 0`
denetliyor, dolayısıyla akış kendiliğinden doğru dala düşer:
  · `yedek_al` → (False, ...) → `YEDEK_ALINAMADI`
  · `yak`      → (False, ...) → `YAKMA_HATASI`
⚠️ Ve bu, "yedek alınamazsa YAKMA" değişmezini KORUR — asılan bir yedek, alınmış sayılmaz.

Aynı sınıf: yakıcı keşiften SONRA silinirse `subprocess.run` `OSError` fırlatır. O da
kaçmamalı.

⚠️ ÇIPA KAYNAĞA PİNLİ DEĞİL, DAVRANIŞA: `subprocess.run` sahtelenip istisna fırlatılır ve
ÜRÜN fonksiyonunun ne döndürdüğüne bakılır. Kaynakta `try` aramak kapıyı kör ederdi —
`try`ı yanlış yere koymak da testi geçerdi.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from stlink_sahte import liste as stlink_liste  # T-b: sahte yakıcı `-l st-link` prob listesi

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "apps" / "backend"))

from utils import stm_yakma as sy  # noqa: E402


@pytest.fixture()
def sahte_cli(tmp_path: Path) -> Path:
    p = tmp_path / "STM32_Programmer_CLI.exe"
    p.write_bytes(b"MZ")
    return p


def _asilan(*a, **k):
    raise subprocess.TimeoutExpired(cmd="STM32_Programmer_CLI.exe", timeout=600.0)


def _kayip(*a, **k):
    raise OSError(2, "yakici kayboldu")


# ── _kos: istisna KODA dönüşür ───────────────────────────────────────────────────
@pytest.mark.parametrize("firlatan,ad", [(_asilan, "zaman aşımı"), (_kayip, "OSError")])
def test_KRITIK_kos_istisna_FIRLATMAZ_koda_donusur(monkeypatch, sahte_cli, firlatan, ad):
    monkeypatch.setattr(subprocess, "run", firlatan)
    rc, cikti = sy._kos(sahte_cli, ["-c", "port=SWD"])
    assert rc != 0, f"{ad}: başarısızlık kodu dönmeli"
    assert cikti.strip(), f"{ad}: sebep boş bırakılmamalı — tanı imkânsızlaşır"


# ── yedek_al / yak: asılma BAŞARISIZLIK, istisna DEĞİL ──────────────────────────
def test_KRITIK_yedek_al_asilinca_BASARISIZ_doner(monkeypatch, sahte_cli, tmp_path):
    monkeypatch.setattr(subprocess, "run", _asilan)
    ok, mesaj = sy.yedek_al(sahte_cli, tmp_path / "yedek.bin", 1024)
    assert ok is False, "asılan yedek ALINMIŞ sayılamaz — 'yedeksiz yakma' kapısını açar"
    assert mesaj.strip()


def test_KRITIK_yak_asilinca_BASARISIZ_doner(monkeypatch, sahte_cli, tmp_path):
    ikili = tmp_path / "pemf.bin"
    ikili.write_bytes(b"\x00" * 64)
    monkeypatch.setattr(subprocess, "run", _asilan)
    ok, mesaj = sy.yak(sahte_cli, ikili)
    assert ok is False
    assert mesaj.strip()


# ── AÇILIŞ YOLU: tam akış istisna KAÇIRMAZ ──────────────────────────────────────
def test_KRITIK_yakma_akisi_ACILIS_yoluna_istisna_KACIRMAZ(monkeypatch, sahte_cli, tmp_path):
    """Asıl iddia bu: açılışta çağrılan akış, yakıcı asılsa bile KOD döndürür."""
    ikili = tmp_path / "pemf.bin"
    ikili.write_bytes(b"\x00" * 64)
    monkeypatch.setattr(sy, "programmer_cli", lambda: sahte_cli)
    monkeypatch.setattr(sy, "seans_ve_bobin_kontrolu", lambda backend: (True, "temiz"))

    def _asilan_listeli(cmd, *a, **k):  # T-b: ST-Link listesi gelir, karta giden komutlar ASILIR
        if "-l" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=stlink_liste(), stderr="")
        return _asilan(cmd, *a, **k)

    monkeypatch.setattr(subprocess, "run", _asilan_listeli)

    sonuc = sy.yakma_akisi(ikili, beklenen_sha256=sy.sha256(ikili), yedek_dizin=tmp_path)

    assert isinstance(sonuc, sy.Sonuc), "akış Sonuc döndürmeli, istisna fırlatmamalı"
    assert sonuc.kod != sy.TAMAM, "asılan yakıcı BAŞARILI sayılamaz"
    assert sonuc.kod in (sy.YEDEK_ALINAMADI, sy.YAKMA_HATASI), f"beklenen başarısızlık kodu değil: {sonuc.kod}"

    # T-b: listeleme (yakıcının İLK çağrısı) asılırsa da istisna YOK — karta dokunulmadan ST-Link seçilemedi.
    monkeypatch.setattr(subprocess, "run", _asilan)
    sonuc = sy.yakma_akisi(ikili, beklenen_sha256=sy.sha256(ikili), yedek_dizin=tmp_path)
    assert isinstance(sonuc, sy.Sonuc) and sonuc.kod == sy.STLINK_SECILEMEDI, sonuc.kod


# ── KARŞIT KANIT: normal yol BOZULMADI ──────────────────────────────────────────
def test_karsit_kanit_basarili_kosum_HALA_calisir(monkeypatch, sahte_cli):
    class _R:
        returncode = 0
        stdout = "Download verified successfully"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
    rc, cikti = sy._kos(sahte_cli, ["-c", "port=SWD"])
    assert rc == 0 and "verified" in cikti, "başarı yolu bozulmamalı"


def test_karsit_kanit_basarisiz_kosum_KODU_korunur(monkeypatch, sahte_cli):
    """Gerçek bir hata kodu, zaman aşımı koduyla EZİLMEMELİ."""

    class _R:
        returncode = 42
        stdout = ""
        stderr = "Error: no STM32 target found"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
    rc, cikti = sy._kos(sahte_cli, ["-c", "port=SWD"])
    assert rc == 42, "yakıcının kendi hata kodu korunmalı"
    assert "no STM32 target" in cikti
