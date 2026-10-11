# -*- coding: utf-8 -*-
"""4A-3.7 önce-kırmızı (A3 incelemesi): kopyleft kapısı (`test_license_surface::test_KRITIK_YENI_kopyleft_bagimlilik_EKLENMEZ`)
lisansı `metadata_lisansi`nin TEK alanından okur: License-Expression > License > İLK `Classifier: License ::`. `License: UNKNOWN`,
serbest metin (`Dual License`, `Copyright (c) …` — bugünkü NOTICE'te 7 paket böyle) ya da ilk sınıflandırıcı MIT olan bir paketin
GPL sınıflandırıcısı GÖRÜNMEZ.

Kapı fonksiyonu DOĞRUDAN koşulur; yalnız modülün `PAKET`i sahte bir base-deps.zip'e çevrilir (gerçek pakete dokunulmaz).
"""

from __future__ import annotations

import zipfile

import pytest
import test_license_surface as TL

_SINIF_GPL3 = "Classifier: License :: OSI Approved :: GNU General Public License v3 (GPLv3)\n"
MASKELI = {
    "unknown": "Name: gizli1\nLicense: UNKNOWN\n" + _SINIF_GPL3,
    "serbest_metin": "Name: gizli2\nLicense: Copyright (c) 2020 Ornek Ltd.\n" + _SINIF_GPL3,
    "ilk_siniflandirici_mit": "Name: gizli3\nClassifier: License :: OSI Approved :: MIT License\n" + _SINIF_GPL3,
}


@pytest.mark.parametrize("bicim", sorted(MASKELI))
def test_KRITIK_kopyleft_kapisi_maskeli_GPL_paketini_YAKALAR(tmp_path, monkeypatch, bicim):
    sahte = tmp_path / "base-deps.zip"
    with zipfile.ZipFile(sahte, "w") as z:
        z.writestr("PEMF_Backend/_internal/gizli-1.0.dist-info/METADATA", MASKELI[bicim])
        z.writestr(
            "PEMF_Backend/_internal/ultralytics-8.0.dist-info/METADATA", "Name: ultralytics\nLicense: AGPL-3.0\n"
        )
    monkeypatch.setattr(TL, "PAKET", sahte)
    with pytest.raises(AssertionError, match="YENİ kopyleft"):
        TL.test_KRITIK_YENI_kopyleft_bagimlilik_EKLENMEZ(None)
