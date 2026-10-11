# -*- coding: utf-8 -*-
"""4A-3.6 önce-kırmızı (A3 incelemesi): D4.08 `kopyleft_mu` (ÜRÜN betiği scripts/lisans_envanteri_uret.py).

(a) YANLIŞ NEGATİF: LGPL'in UZUN adı (`GNU Lesser General Public License …`) `_LGPL` deseninde `[^,;()]*` ile virgül/parantez
    görene dek AÇGÖZLÜ silinir → aynı cümledeki "and GNU General Public License v3" / "and GPL-2.0" / "and GNU Affero …"
    da silinir → kopyleft GÖRÜNMEZ. D4.08'in kapattığı "LGPL geçerse TAMAMI muaf" sınıfının uzun-ad biçimi.
(b) YANLIŞ POZİTİF (güvenli yönde): "GPL-compatible" ibaresi (PSF / BSD türevleri) kopyleft sayılır → sahte kırmızı.
"""

from __future__ import annotations

import pytest

from scripts.lisans_envanteri_uret import kopyleft_mu


@pytest.mark.parametrize(
    "lisans",
    [
        "GNU Lesser General Public License v2.1 and GNU General Public License v3",
        "GNU Lesser General Public License v3 and GPL-2.0",
        "GNU Lesser General Public License v3 or later and GNU Affero General Public License v3",
    ],
)
def test_KRITIK_uzun_adli_LGPL_ardindaki_GPL_GORUNUR(lisans):
    assert kopyleft_mu(lisans), f"LGPL uzun adı ardındaki kopyleft GÖRÜNMEDİ: {lisans!r}"


@pytest.mark.parametrize(
    "lisans",
    ["GPL-compatible", "Python Software Foundation License (GPL-compatible)", "BSD (GPL compatible)"],
)
def test_GPL_uyumlu_ibaresi_kopyleft_SAYILMAZ(lisans):
    assert not kopyleft_mu(lisans), f"'GPL-compatible' kopyleft sayıldı: {lisans!r}"


@pytest.mark.parametrize(
    "lisans",
    [
        "GNU Lesser General Public License v2 or later (LGPLv2+)",
        "GNU Lesser General Public License v3 (LGPLv3)",
        "GNU Library or Lesser General Public License (LGPL)",
        "GNU Lesser General Public License, version 2.1",
    ],
)
def test_KARSIT_LGPL_uzun_adlari_hala_MUAF(lisans):
    assert not kopyleft_mu(lisans), f"LGPL kopyleft sayıldı: {lisans!r}"


# ── 4-A inc. S-A3.2 (Y123 önerilen): GPL ailesi DIŞINDAKİ güçlü kopyleftler ─────────────────────────────────────────────
@pytest.mark.parametrize(
    "lisans",
    [
        "EUPL-1.2",
        "European Union Public Licence 1.2 (EUPL 1.2)",
        "SSPL-1.0",
        "Server Side Public License, v 1",
        "OSL-3.0",
        "Open Software License 3.0 (OSL-3.0)",
        "MIT AND EUPL-1.2",
    ],
)
def test_KRITIK_GPL_ailesi_DISINDAKI_guclu_kopyleft_GORUNUR(lisans):
    assert kopyleft_mu(lisans), f"güçlü kopyleft (EUPL/SSPL/OSL) görünmedi: {lisans!r}"


@pytest.mark.parametrize(
    "lisans",
    [
        "MIT",
        "Apache-2.0",
        "BSD-3-Clause",
        "Open Software Foundation",
        "OSLO-1.0",
        "Mozilla Public License 2.0 (MPL 2.0)",
    ],
)
def test_KARSIT_benzer_adli_izin_verici_lisans_kopyleft_SAYILMAZ(lisans):
    assert not kopyleft_mu(lisans), f"izin verici lisans kopyleft sayıldı: {lisans!r}"
