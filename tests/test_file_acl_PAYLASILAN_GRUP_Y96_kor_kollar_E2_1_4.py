# -*- coding: utf-8 -*-
"""E2-1.4 (2-E incelemesi, A1) — KÖR KAPI: Y96 kapısı (`tests/test_file_acl_PAYLASILAN_GRUP_Y96.py`) iki savunmayı ÖLÇMÜYOR.

A1 mutantları (kayit/A1K1_mutasyon.txt) Y96 + D2.79 + file_acl kapılarında YEŞİL kaldı:
  k1m1  `os.environ.get(PEMF_DATA_GROUP_SID).strip()` → strip YOK   (launcher/kurulum değeri satır sonu ya da boşlukla verirse
        grup REDDEDİLİR, ikinci hesap veri kökünü yine açamaz — Y96'nın amacı sessizce düşer; yalnız bir ERROR/WARNING satırı)
  k1m2  `tur == SidTypeAlias and alan == bilgisayar` → yalnız `tur == SidTypeAlias` (etki alanına katılmış klinik PC'de bir
        ETKİ ALANI yerel grubu (SidTypeAlias, alan = CONTOSO) kabul edilir → sır dosyaları o etki alanı grubunun TÜM üyelerine açılır)
2-E bu kolu "etki alanı grubu bu makinede yok — BİLİNMİYOR" diye bıraktı; arıza EN ALT katta (advapi32 `LookupAccountSidW`'nin
döndürdüğü tür + etki alanı) kurularak ölçülebilir. Bu kapı HEAD'de YEŞİL, iki mutantta KIRMIZI olmalı.
"""

from __future__ import annotations

import ctypes
import logging
import os

import pytest

pytestmark = pytest.mark.skipif(os.name != "nt", reason="advapi32 yalnız Windows")

_SID = "S-1-5-21-1111111111-2222222222-3333333333-1500"


class _SahteLookup:
    """`LookupAccountSidW` — `alan` etki alanı adı ve `tur` SID türüyle başarılı döner (gerçek imza: ad, &ad_boy, alan, &alan_boy, &tur)."""

    argtypes = None
    restype = None

    def __init__(self, alan, tur):
        self.alan, self.tur = alan, tur
        self.cagri = 0

    def __call__(self, sistem, psid, ad, ad_boy, alan, alan_boy, tur):
        self.cagri += 1
        ad.value = "pemf-klinik"
        alan.value = self.alan
        tur._obj.value = self.tur  # ctypes.byref(c_int) → CArgObject._obj
        return 1


class _Vekil:
    def __init__(self, gercek, sahte):
        object.__setattr__(self, "_g", gercek)
        object.__setattr__(self, "_s", sahte)

    def __getattr__(self, ad):
        if ad == "LookupAccountSidW":
            return object.__getattribute__(self, "_s")
        return getattr(object.__getattribute__(self, "_g"), ad)


def _sahte_advapi(monkeypatch, alan, tur):
    gercek = ctypes.WinDLL
    sahte = _SahteLookup(alan, tur)

    def _windll(ad, *a, **k):
        g = gercek(ad, *a, **k)
        return _Vekil(g, sahte) if str(ad).lower().startswith("advapi32") else g

    monkeypatch.setattr(ctypes, "WinDLL", _windll)
    return sahte


def _bilgisayar_adi() -> str:
    from ctypes import wintypes

    b = ctypes.create_unicode_buffer(64)
    n = wintypes.DWORD(len(b))
    assert ctypes.windll.kernel32.GetComputerNameW(b, ctypes.byref(n))
    return b.value


def test_KRITIK_ETKI_ALANI_yerel_grubu_REDDEDILIR_E2_1_4(monkeypatch):
    from utils import file_acl as fa

    sahte = _sahte_advapi(monkeypatch, "CONTOSO", 4)  # SidTypeAlias, başka etki alanı
    sonuc = fa._bu_makinenin_yerel_grubu_mu(_SID)
    assert sahte.cagri == 1, "aparat: sahte LookupAccountSidW çağrılmadı"
    assert sonuc is False, (
        "etki alanı (CONTOSO) yerel grubu 'bu makinenin yerel grubu' sayıldı — sır dosyaları etki alanına açılır"
    )


def test_KARSIT_BU_BILGISAYARIN_yerel_grubu_KABUL_edilir_E2_1_4(monkeypatch):
    from utils import file_acl as fa

    ad = _bilgisayar_adi()
    sahte = _sahte_advapi(monkeypatch, ad.lower(), 4)  # büyük/küçük harf duyarsız karşılaştırma
    assert fa._bu_makinenin_yerel_grubu_mu(_SID) is True
    assert sahte.cagri == 1
    sahte2 = _sahte_advapi(monkeypatch, ad, 2)  # SidTypeGroup (etki alanı grubu) → red
    assert fa._bu_makinenin_yerel_grubu_mu(_SID) is False and sahte2.cagri == 1


@pytest.mark.parametrize("ek", ["\r\n", "\n", " ", "\t"], ids=["CRLF", "LF", "bosluk", "sekme"])
def test_KRITIK_satir_sonu_ya_da_bosluklu_grup_SID_i_KABUL_edilir_E2_1_4(monkeypatch, ek):
    from utils import file_acl as fa

    monkeypatch.setattr(fa, "_bu_makinenin_yerel_grubu_mu", lambda s: s == _SID)
    monkeypatch.setattr(fa, "_grup_uyarisi_verilen", set())
    monkeypatch.setenv("PEMF_DATA_GROUP_SID", (" " if ek == " " else "") + _SID + ek)
    assert fa._paylasilan_grup_ace("(OI)(CI)") == f"*{_SID}:(OI)(CI)F", (
        f"PEMF_DATA_GROUP_SID {ek!r} ekiyle verildi → grup REDDEDİLDİ (ikinci hesap veri kökünü açamaz)"
    )
