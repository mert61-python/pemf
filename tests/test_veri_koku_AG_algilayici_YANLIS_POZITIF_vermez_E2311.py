# -*- coding: utf-8 -*-
"""E2-3.11 (2-E incelemesi A3) — Y118 algılayıcısının KARŞIT kolları: USB / RAM disk / bilinmeyen sürücü ve `\\\\.\\C:` cihaz-ad alanı yolu ağ
SAYILMAZ (yanlış pozitif yok); yalnız DRIVE_REMOTE ve UNC ağdır.

Ürün HEAD'de doğru (2-E incelemesi A3 2-E incelemesi kaydı), ama 2-E'nin Y118 kapısı + şekil sözleşmesi (13 test) şu mutantlarda
YEŞİL kaldı (2-E incelemesi kaydı): k4a `\\\\.\\` öneki soyulmaz (`\\\\.\\C:\\…` UNC sayılır → yanlış bant) · k4b DRIVE_REMOVABLE
(USB) da ağ sayılır. Sürücü türü YALNIZ en alt sarmalayıcıda (`path_utils._surucu_turu`) benzetilir — sürücü OLUŞTURULMAZ.
"""

from __future__ import annotations

import pytest

DRIVE = {"UNKNOWN": 0, "NO_ROOT_DIR": 1, "REMOVABLE": 2, "FIXED": 3, "REMOTE": 4, "CDROM": 5, "RAMDISK": 6}


@pytest.mark.parametrize("tur", ["UNKNOWN", "NO_ROOT_DIR", "REMOVABLE", "FIXED", "CDROM", "RAMDISK"])
@pytest.mark.parametrize(
    "yol", [r"E:\PEMF_System", r"\\?\E:\PEMF_System", r"\\.\E:\PEMF_System"], ids=["duz", "uzun_onek", "cihaz_ad_alani"]
)
def test_KRITIK_ag_OLMAYAN_surucu_turu_ag_SAYILMAZ_E2311(monkeypatch, tur, yol):
    from utils import path_utils as pu

    monkeypatch.setattr(pu, "_surucu_turu", lambda kok: DRIVE[tur])
    assert pu.veri_koku_ag_paylasiminda_mi(yol) is False, f"{tur} sürücüsündeki {yol} AĞ sayıldı (yanlış bant)"


@pytest.mark.parametrize(
    "yol", [r"E:\PEMF_System", r"\\?\E:\PEMF_System", r"\\.\E:\PEMF_System"], ids=["duz", "uzun_onek", "cihaz_ad_alani"]
)
def test_KARSIT_DRIVE_REMOTE_ag_sayilir_E2311(monkeypatch, yol):
    from utils import path_utils as pu

    monkeypatch.setattr(pu, "_surucu_turu", lambda kok: DRIVE["REMOTE"])
    assert pu.veri_koku_ag_paylasiminda_mi(yol) is True
