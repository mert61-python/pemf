# -*- coding: utf-8 -*-
"""OTB T-9b (kum havuzu 19-11, kayıtlı gerçek karelerle B-1 seansı): TÜM PETRİ seansında canlı seans kartı "AI Pro · Petri Kuyu · Kuyu
(otomatik)" diyordu — döngü / kare yolu mod metninin hedef parçasını `hedef_adi(0)` ile yazıyordu (T-9 kaydı ve canlı kart hedefi
düzeldi, mod metni kalmıştı). SÖZLEŞME: mühürlü ODAK kipi TÜM PETRİ iken mod hedefi "Tüm petri" (VERİ, Türkçe saklanır); gösterimde
istek dilinde (PDF / CSV / KPI `mod_etiketi`, arayüz `modEtiketi`). Diğer kipler AYNEN."""

from __future__ import annotations

from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]


def test_KRITIK_T9b_TUM_PETRI_seansinda_mod_hedefi_Tum_petri_digerlerinde_AYNEN():
    from servers import ai_pro_hedef as hedef

    p = hedef.PetriSaglayici()
    assert hedef.hedef_veri_adi(p, 0) == "Kuyu (otomatik)"  # seans yok
    hedef.odak_ayarla(p, {"doz_mT": 1.4, "kip": "TUM_PETRI"}, "Tüm petri")
    assert hedef.hedef_veri_adi(p, 0) == "Tüm petri"
    hedef.odak_ayarla(p, {"doz_mT": 0.6, "kip": "KUYUCUK"}, "Kuyu C2")
    assert hedef.hedef_veri_adi(p, 0) == "Kuyu (otomatik)" and hedef.hedef_veri_adi(p, 7) == p.hedef_adi(7)
    hedef.odak_ayarla(p, None)


def test_KRITIK_T9b_dongu_ve_kare_yolu_mod_metnini_TEK_kaynaktan_yazar():
    kaynak = (KOK / "apps/backend/servers/ai_router.py").read_text(encoding="utf-8")
    assert kaynak.count("ai_pro_hedef.hedef_veri_adi(_aktif_saglayici(), _gosterim_oid)") == 2
    assert "hedef_adi(_gosterim_oid)}\"" not in kaynak and ".hedef_adi(_gosterim_oid)}" not in kaynak


@pytest.mark.parametrize("dil,beklenen", [("tr", "AI Pro · Petri Kuyu · Tüm petri"), ("en", "Whole well plate")])
def test_T9b_mod_GOSTERIMI_iki_dilde(dil, beklenen):
    from utils import ceviri
    from utils.seans_durum import mod_etiketi

    jeton = ceviri.istek_dili_var.set(dil)
    try:
        g = mod_etiketi("AI Pro · Petri Kuyu · Tüm petri")
    finally:
        ceviri.istek_dili_var.reset(jeton)
    assert beklenen in g, g
    if dil == "en":
        assert not any(c in g for c in "çğıöşüÇĞİÖŞÜ"), g
