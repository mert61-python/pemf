# -*- coding: utf-8 -*-
"""E2-3.7 (2-E incelemesi A3) — kurtarma yönergesi (KURTARMA-KODU.txt · OKU-KURTARMA.txt) launcher DIŞI desteklenen kurulumda da
çalışan EXE'yi gösterir ve zarf yolu cmd'nin çalışma dizinine bağlı DEĞİLDİR.

D2.75 komutu TEK kaynağa (`KURTARMA_EXE` = `%LOCALAPPDATA%\\PEMF Vet Client\\runtime\\PEMF_Backend\\PEMF_Backend.exe`) indirdi. Ama:
  (1) A-11 (sahip kararı) `install_backend_service.ps1` DESTEKLENEN ikinci kurulum yoludur; Inno kurulumu `{autopf}\\PEMF Backend`e
      (`build_tools/PEMF_Backend_Setup.iss:58`) kurar. O kurulumların yazdığı KURTARMA-KODU.txt / OKU-KURTARMA.txt yalnız launcher yolunu
      söylüyor — cmd "sistem belirtilen yolu bulamıyor" der; metinde "yoksa şurada" satırı YOK.
  (2) OKU-KURTARMA.txt zarfı GÖRELİ adla verir (`--zarf kurtarma-zarfi.enc`); operatörün açtığı cmd `%USERPROFILE%`de başlar → araç
      "zarf bulunamadi" (rc 2) der (`tools/kurtarma.py:109` `zarf.exists()` çalışma dizinine göre).
Kapı: üreticiler GERÇEK çağrılır (`kod_dosyasi_metni`, makine dışı notun gerçek `_copy_offsite` yazıcısı).
"""

from __future__ import annotations

import re
import threading

import pytest


@pytest.fixture
def notlar(temp_app_data, tmp_path, monkeypatch):
    from services.headless_db_maintenance import HeadlessDBMaintenance
    from utils import backup_recovery as br

    nas = tmp_path / "NAS"
    monkeypatch.setenv("PEMF_BACKUP_DIR", str(nas))
    w = object.__new__(HeadlessDBMaintenance)
    w.app_data_dir, w.db, w.patient_db = temp_app_data, None, None
    w.backup_interval, w.backup_retention_keep = 24 * 3600, 14
    w._stop, w._thread = threading.Event(), None
    zarf = temp_app_data / "kurtarma-zarfi.enc"
    zarf.write_bytes(b'{"tur": "kurtarma-zarfi", "v": 1, "aparat": "E237"}')
    w._copy_offsite([zarf])
    oku = (nas / "OKU-KURTARMA.txt").read_text(encoding="utf-8")
    return {"KURTARMA-KODU.txt": br.kod_dosyasi_metni(br.generate_recovery_code()), "OKU-KURTARMA.txt": oku}


@pytest.mark.parametrize("ad", ["KURTARMA-KODU.txt", "OKU-KURTARMA.txt"])
def test_KRITIK_yonerge_SERVIS_kurulumundaki_EXEyi_de_soyler_E237(notlar, ad):
    metin = notlar[ad]
    assert "Program Files\\PEMF Backend" in metin, (
        f"{ad}: launcher dışı (servis / Inno, A-11) kurulumda PEMF_Backend.exe'nin yeri söylenmiyor — yalnız launcher yolu:\n{metin}"
    )


def test_KRITIK_OKU_KURTARMA_zarf_yolu_CALISMA_DIZININE_bagli_degil_E237(notlar):
    metin = notlar["OKU-KURTARMA.txt"]
    zarf_argumanlari = re.findall(r"--zarf\s+(\S+)", metin)
    assert zarf_argumanlari, "aparat: OKU-KURTARMA.txt'te --zarf bulunamadı"
    goreli = [z for z in zarf_argumanlari if not re.match(r'^"?(<[^>]+>\\|[A-Za-z]:\\|\\\\)', z)]
    assert not goreli, (
        f"OKU-KURTARMA.txt zarfı GÖRELİ adla veriyor {goreli} — cmd %USERPROFILE%'da açılır, araç 'zarf bulunamadi' der"
    )
