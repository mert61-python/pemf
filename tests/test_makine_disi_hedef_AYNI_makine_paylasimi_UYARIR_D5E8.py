# -*- coding: utf-8 -*-
r"""2-F incelemesi §10 #8 (D5 · yardımcı E · A3 açık #9) — makine dışı yedek hedefi BU makinenin yönetici OLMAYAN bir paylaşımıysa
(`\\KLINIK-PC\PEMF_Yedek`, `\\localhost\PEMF_Yedek`) WARNING: kopya aynı bilgisayarda kalır ve paylaşımın hangi klasöre denk geldiği ağ
sorgusu yapılmadan bilinemez (veri kökünün içindeyse kaldırma / tam temizlik onu da siler).

ÖLÇÜLEN KUSUR (HEAD 9c6d4505): F2-3.7'nin `_yerel_esdeger`i yalnız yönetici paylaşımını (`\\<bu makine>\C$\…`) yerel yola indirger;
`\\<bu makine>\PEMF_Yedek` UNC olarak kalır, `_hedef_veri_kokunde_mi` → False ("kök dışı") ve kopya hiçbir uyarı olmadan "makine dışı"
sayılır — doğrulanınca günlük "baska makinede geri yuklenebilir" (INFO) der. Paylaşımın yerel yolunu çözmek ağ / API sorgusu ister
(NetShareGetInfo) — YAPILMAZ. Düzeltme: yalnız DİZGİ düzeyinde (ana bilgisayar adı = bu makine: localhost / 127.x / ::1 / COMPUTERNAME /
gethostname) WARNING; kopya DURMAZ (paylaşım kök dışında olabilir — davranış değişmez).
UNC YALNIZ DİZGİ düzeyinde: paylaşıma bağlanılmaz. `_copy_offsite` kolunda en alt katta `ntpath._getfinalpathname` (yönlendiricinin
`\\?\UNC\…` biçimi) ve UNC `Path.mkdir`'i (paylaşıma ulaşılamadı, WinError 67) sahte — sorgu ağa ÇIKMAZ.
"""

from __future__ import annotations

import logging
import ntpath
import os
import pathlib

import pytest
from test_makine_disi_yedek_hedefi_PEMF_KOKU_ALTINDA_olamaz_SE2I4 import o  # noqa: F401

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows UNC yolları")

BU_PC = "E8-KLINIK-PC"


@pytest.fixture
def ag_yok(monkeypatch):
    """EN ALT kat: UNC'ye hiçbir dosya sistemi çağrısı ağa çıkmaz."""
    monkeypatch.setenv("COMPUTERNAME", BU_PC)
    gercek_fp = ntpath._getfinalpathname
    gercek_mkdir = pathlib.Path.mkdir

    def _fp(p):
        p = str(p)
        if p.startswith("\\\\") and not p.startswith("\\\\?\\") and not p.startswith("\\\\.\\"):
            return "\\\\?\\UNC\\" + p[2:]
        return gercek_fp(p)

    def _mkdir(self, *a, **k):
        if str(self).startswith("\\\\"):
            raise OSError(22, "paylasima ulasilamadi (E8 benzetim)", str(self), 67)
        return gercek_mkdir(self, *a, **k)

    monkeypatch.setattr(ntpath, "_getfinalpathname", _fp)
    monkeypatch.setattr(pathlib.Path, "mkdir", _mkdir)


AYNI_MAKINE = [
    f"\\\\{BU_PC}\\PEMF_Yedek",
    f"\\\\{BU_PC.lower()}\\PEMF_Yedek\\klinik",
    "\\\\localhost\\PEMF_Yedek",
    "\\\\127.0.0.1\\PEMF_Yedek",
    f"\\\\?\\UNC\\{BU_PC}\\PEMF_Yedek",
]
BASKA = [
    "\\\\BASKA-PC\\PEMF_Yedek",
    "\\\\192.168.1.50\\PEMF_Yedek",
    "\\\\localhost\\C$\\PEMF_Disari",  # yönetici paylaşımı → yerel sürücü yoluna indirgenir (F2-3.7), bilinen yol
    "D:\\PEMF_Yedek",
]


@pytest.mark.parametrize("hedef", AYNI_MAKINE)
def test_KRITIK_ayni_makinenin_PAYLASIMI_taninir(o, ag_yok, hedef):  # noqa: F811
    assert o.w._ayni_makinenin_paylasimi_mi(hedef), f"bu makinenin paylaşımı tanınmadı: {hedef}"


@pytest.mark.parametrize("hedef", BASKA)
def test_KARSIT_baska_makine_yonetici_paylasimi_ve_yerel_yol_TANINMAZ(o, ag_yok, hedef):  # noqa: F811
    assert not o.w._ayni_makinenin_paylasimi_mi(hedef), (
        f"başka makine / bilinen yerel yol 'aynı makine paylaşımı' sayıldı: {hedef}"
    )


def test_KRITIK_copy_offsite_ayni_makine_paylasiminda_WARNING_verir(o, ag_yok, monkeypatch, caplog):  # noqa: F811
    monkeypatch.setenv("PEMF_BACKUP_DIR", f"\\\\{BU_PC}\\PEMF_Yedek")
    with caplog.at_level(logging.INFO, logger="services.headless_db_maintenance"):
        o.w._copy_offsite(o.dosyalar)
    uyarilar = [r for r in caplog.records if r.levelno == logging.WARNING and "PEMF_Yedek" in r.getMessage()]
    assert any("ayni bilgisayar" in r.getMessage() for r in uyarilar), (
        f"bu makinenin paylaşımı 'makine dışı' hedef sayıldı, uyarı YOK: {[r.getMessage() for r in caplog.records]}"
    )


def test_KARSIT_baska_makine_hedefinde_AYNI_MAKINE_uyarisi_YOK(o, ag_yok, monkeypatch, caplog):  # noqa: F811
    monkeypatch.setenv("PEMF_BACKUP_DIR", "\\\\BASKA-PC\\PEMF_Yedek")
    with caplog.at_level(logging.INFO, logger="services.headless_db_maintenance"):
        o.w._copy_offsite(o.dosyalar)
    assert not any("ayni bilgisayar" in r.getMessage() for r in caplog.records), (
        "başka makinenin paylaşımında yanlış uyarı"
    )
