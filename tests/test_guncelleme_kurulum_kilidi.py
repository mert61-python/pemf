# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Denetim 2026-08-16 (Bulgu 3): OTO-GÜNCELLEME kurulum kilidini ALMIYORDU.

Üç ELLE yıkıcı işlem kilidi alıyordu — `install_and_launch`, `repair`, `uninstall` — ama AYNI
runtime ağacını değiştiren OTOMATİK güncelleme almıyordu:

    install_and_launch      kilit VAR
    repair                  kilit VAR
    uninstall               kilit VAR
    apply_runtime_update    kilit YOK   ← runtime.new'e yazıp takas ediyor
    prefetch_runtime_update kilit YOK

Tek-instance koruması da yok (bilinen durum). Yani ikinci bir client penceresi açılırsa ya da
kullanıcı güncelleme sürerken "Onar"a basarsa iki akış `runtime.new` üzerinde çakışır.

İKİ YOLUN SEMANTİĞİ FARKLI — ve bu bilinçli:
  • `apply_runtime_update` AĞACI DEĞİŞTİRİR → TAM kilit (`?` ile), alınamazsa güncelleme YOK.
  • `prefetch_runtime_update` yalnız İNDİRİR (ağaca hiç dokunmaz) ve 45 dk sürebilir. Kilidi o
    süre boyunca TUTSAYDI kullanıcı "Onar"/profil kurulumu yapamazdı — oysa bu akışın TEK amacı
    kullanıcıyı bekletmemek. Bu yüzden kilit yalnız YOKLANIR: doluysa bu tur ATLANIR.
"""

import re
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parent.parent
_MAIN_RS = _KOK / "launcher" / "app" / "src" / "main.rs"


@pytest.fixture(scope="module")
def rs() -> str:
    return _MAIN_RS.read_text(encoding="utf-8")


def _govde(rs: str, ad: str) -> str:
    m = re.search(rf"(?:async )?fn {ad}\((.*?)\n}}\n", rs, re.S)
    assert m, f"{ad} bulunamadı"
    return m.group(1)


def test_KRITIK_apply_runtime_update_TAM_kilit_alir(rs):
    """🔴 ASIL BULGU: ağacı değiştiren tek otomatik yol korumasızdı."""
    g = _govde(rs, "apply_runtime_update")
    assert "kurulum_kilidi_al" in g, (
        "oto-güncelleme kurulum kilidini ALMIYOR — ikinci pencere/onarım ile runtime.new üzerinde çakışır"
    )
    assert re.search(r"let _kilit = install::kurulum_kilidi_al\(&root\)\?;", g), (
        "kilit `?` ile alınmalı: elde edilemezse güncelleme YAPILMAMALI"
    )


def test_KRITIK_kilit_seans_kapisindan_ONCE_alinir(rs):
    """Kilit önce alınmazsa iki akış aynı anda seans kapısını geçip ilerleyebilir."""
    g = _govde(rs, "apply_runtime_update")
    i_kilit = g.index("kurulum_kilidi_al")
    i_seans = g.index("aktif_seans_kapisi")
    assert i_kilit < i_seans, "kilit, seans kapısından SONRA alınıyor → yarış penceresi açık"


def test_KRITIK_prefetch_kilit_TUTMAZ_yalnizca_yoklar(rs):
    """🔴 Ön-indirme kilidi 45 dk tutarsa kullanıcı 'Onar' yapamaz — akışın amacına aykırı.

    Doğru davranış: kilit YOKLANIR ve HEMEN bırakılır; doluysa bu tur atlanır.
    """
    g = _govde(rs, "prefetch_runtime_update")
    assert "kurulum_kilidi_al" in g, "ön-indirme kilidi hiç yoklamıyor → kurulumla aynı anda koşar"
    assert "drop(k)" in g, "kilit TUTULUYOR (drop yok) → 45 dakikalık indirme boyunca kullanıcı kurulum/onarım yapamaz"
    assert '"skipped"' in g, "kilit doluyken atlama durumu bildirilmiyor"
    # `?` ile alınırsa komut HATA döner ve UI'da kırmızı görünür — oysa bu isteğe bağlı bir iştir.
    assert not re.search(r"let _kilit = install::kurulum_kilidi_al\(&root\)\?;", g), (
        "ön-indirme kilidi TAM alıyor → kullanıcıyı bloklar"
    )


def test_prefetch_atlanmasi_HATA_gibi_gorunmez(rs):
    """Atlama normal bir durumdur; komut `Err` dönerse UI kırmızı hata gösterir."""
    g = _govde(rs, "prefetch_runtime_update")
    m = re.search(r"Err\(_\) => \{(.*?)\n        \}", g, re.S)
    assert m, "kilit-dolu dalı bulunamadı"
    dal = m.group(1)
    # ⚠️ "içinde `return Ok(` var mı" YETMEZ: dalda hem Err hem Ok bulunabilir ve İLK olan
    # kazanır (mutasyon turu 2026-08-16 bunu gösterdi). `Err` dönüşü hiç OLMAMALI.
    assert "return Err(" not in dal, (
        "kilit doluyken `Err` dönülüyor → UI kırmızı hata gösterir; oysa atlama normal bir durum"
    )
    assert "return Ok(" in dal, "atlama durumu bildirilmiyor"


@pytest.mark.parametrize("komut", ["install_and_launch", "repair", "uninstall", "apply_runtime_update"])
def test_AGACI_DEGISTIREN_tum_yollar_kilitli(rs, komut):
    """Ağaca yazan her yol kilitli olmalı — biri unutulursa yarış geri gelir."""
    assert "kurulum_kilidi_al" in _govde(rs, komut), f"{komut} kurulum kilidi almıyor"


def test_kilit_mesaji_kullaniciya_NE_YAPACAGINI_soyler():
    """Kilit hatası kullanıcıya gösteriliyor; anlaşılır olmalı."""
    kaynak = (_KOK / "launcher" / "core" / "src" / "install.rs").read_text(encoding="utf-8")
    m = re.search(r"pub fn kurulum_kilidi_al.*?Err\(format!\(\s*\"(.*?)\"", kaynak, re.S)
    assert m, "kilit hata mesajı bulunamadı"
    mesaj = m.group(1)
    assert "pencere" in mesaj.lower(), f"mesaj sebebi söylemiyor: {mesaj!r}"
