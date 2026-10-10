# -*- coding: utf-8 -*-
r"""F2-3.7 (2-F incelemesi A3 · S-E2I.4 `1fd8793`) — `_hedef_veri_kokunde_mi` dolambaçlı yazılmış kök-içi hedefleri yakalar: `\\?\`
uzun yol öneki ve AYNI makinenin yönetici paylaşımı (`\\localhost\C$\…`) eskiden "kök dışı" sayılıyor, "makine dışı" kopya veri
köküne gidiyordu (ölçüldü — disk arızasında / kaldırmada yedekle birlikte kaybolur). Junction / 8.3 / harf KARŞIT kolları (zaten yakalanıyor).
Her şey KENDİ tmp'imde (sentetik veri kökü = `temp_app_data`). GERÇEK `HeadlessDBMaintenance._copy_offsite` + gerçek tedavi DB yedeği
(SE2I4 kapısının aparatı). UNC biçimi YALNIZ DİZGİ düzeyinde: ağa/paylaşıma bağlanılmaz (`ntpath._getfinalpathname` en alt katta
yönlendiricinin döndüreceği `\\\\?\\UNC\\...` biçimini verir; `_copy_offsite` UNC ile ÇAĞRILMAZ)."""

from __future__ import annotations

import ctypes
import ntpath
import os

import pytest
from test_makine_disi_yedek_hedefi_PEMF_KOKU_ALTINDA_olamaz_SE2I4 import ZARF, o  # noqa: F401

# Windows yolları (uzun yol öneki, UNC yönetici paylaşımı, junction, 8.3) — üretim platformu; Linux CI'da anlamsız.
pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows yol biçimleri")


def _kopyalanan(yol) -> list:
    return sorted(p.name for p in yol.glob("*")) if yol.exists() else []


def _uzun_onek(p) -> str:
    return "\\\\?\\" + str(p)


def test_KRITIK_uzun_yol_oneki_ile_kok_ici_hedef_REDDEDILIR(o, monkeypatch):
    """`\\\\?\\C:\\...\\<kök>\\yedek` — Windows'un uzun yol öneki; aynı klasör."""
    gercek = o.kok / "yedek_onekli"
    monkeypatch.setenv("PEMF_BACKUP_DIR", _uzun_onek(gercek))
    karar = o.w._hedef_veri_kokunde_mi(os.environ["PEMF_BACKUP_DIR"])
    o.w._copy_offsite(o.dosyalar)
    print(
        f"OLCUM onek karar_kokte={karar} realpath={os.path.realpath(_uzun_onek(gercek))!r} kopyalanan={_kopyalanan(gercek)}"
    )
    assert karar and not _kopyalanan(gercek), (
        f"\\\\?\\ önekli kök-içi hedef denetimi AŞTI; veri köküne kopyalandı: {_kopyalanan(gercek)}"
    )


def test_KARSIT_kok_disindan_JUNCTION_ile_kok_ici_hedef_REDDEDILIR(o, monkeypatch):
    import _winapi

    ic = o.kok / "junction_hedefi"
    ic.mkdir()
    dis = o.tmp / "disari_junction"
    _winapi.CreateJunction(str(ic), str(dis))
    monkeypatch.setenv("PEMF_BACKUP_DIR", str(dis))
    karar = o.w._hedef_veri_kokunde_mi(str(dis))
    o.w._copy_offsite(o.dosyalar)
    print(f"OLCUM junction karar_kokte={karar} realpath={os.path.realpath(str(dis))!r} kok_ici_kopya={_kopyalanan(ic)}")
    assert karar and not _kopyalanan(ic), f"junction ile kök-içi hedefe kopyalandı: {_kopyalanan(ic)}"


def test_KARSIT_83_KISA_ad_ile_kok_ici_hedef_REDDEDILIR(o, monkeypatch):
    uzun = o.kok / "Cok Uzun Klasor Adi Yedek"
    uzun.mkdir()
    tampon = ctypes.create_unicode_buffer(1024)
    n = ctypes.windll.kernel32.GetShortPathNameW(str(uzun), tampon, 1024)
    kisa = tampon.value if n else ""
    if not kisa or kisa.lower() == str(uzun).lower():
        pytest.skip(f"8.3 kısa ad üretilmiyor (birimde kapalı) — BİLİNMİYOR: {kisa!r}")
    monkeypatch.setenv("PEMF_BACKUP_DIR", kisa)
    karar = o.w._hedef_veri_kokunde_mi(kisa)
    o.w._copy_offsite(o.dosyalar)
    print(f"OLCUM kisa_ad {kisa!r} karar_kokte={karar} kopyalanan={_kopyalanan(uzun)}")
    assert karar and not _kopyalanan(uzun), f"8.3 kısa adla kök-içi hedefe kopyalandı: {_kopyalanan(uzun)}"


def test_KRITIK_yonetici_paylasimi_UNC_DIZGI_duzeyinde_REDDEDILIR(o, monkeypatch):
    """`\\\\localhost\\C$\\...\\<kök>\\yedek` aynı makinedeki aynı klasör. Ağa çıkılmaz: yönlendiricinin sonucu en alt katta verilir."""
    gercek_fp = ntpath._getfinalpathname

    def _yonlendirici(p):
        p = str(p)
        if p.startswith("\\\\") and not p.startswith("\\\\?\\"):
            return (
                "\\\\?\\UNC\\" + p[2:]
            )  # GetFinalPathNameByHandle'ın UNC için döndürdüğü biçim (yerel sürücü harfine ÇEVRİLMEZ)
        return gercek_fp(p)

    monkeypatch.setattr(ntpath, "_getfinalpathname", _yonlendirici)
    surucu, kuyruk = os.path.splitdrive(str(o.kok / "yedek_unc"))
    sonuc = {}
    for ad in ("localhost", "127.0.0.1"):
        unc = f"\\\\{ad}\\{surucu[0]}$" + kuyruk
        sonuc[unc] = o.w._hedef_veri_kokunde_mi(unc)
    print(f"OLCUM unc {sonuc}")
    assert all(sonuc.values()), f"aynı makinenin yönetici paylaşımı üzerinden kök-içi hedef 'kök dışı' sayıldı: {sonuc}"


def test_KARSIT_duz_ve_buyuk_harf_kok_ici_REDDEDILIR(o):
    assert o.w._hedef_veri_kokunde_mi(str(o.kok / "x"))
    assert o.w._hedef_veri_kokunde_mi(str(o.kok / "x").upper())
    assert not o.w._hedef_veri_kokunde_mi(str(o.tmp / "USB"))
