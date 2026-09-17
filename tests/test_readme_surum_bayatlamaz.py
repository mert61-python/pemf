# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""README'DEKI SURUM SAYILARI BAYATLAYAMAZ (2026-09-16).

OLCULEN ARIZA — UCUNCU TEKRAR. `README.md` elle yazilmis bir "Yayindaki surumler" satiri
tasiyordu:

    Backend/App 1.9.5 · Launcher 1.9.9 · Mobil 2.3.3 (versionCode 10)

Gercek surumler olculdugunde: 1.9.50 / 1.9.51 / 2.3.34. On surum geride.

⚠️ EN CARPICI KISMI: ayni belgenin 47. satiri ZATEN "bu belgeye surum yazilmaz" diyor ve
bir onceki bayatlamayi (2026-08-06, `1.9.5 / 2.3.3` yazarken gercegi `1.9.16 / 2.3.17`)
anlatiyordu. Yani KURAL VARDI, YAZILIYDI, GEREKCESIYLE BIRLIKTE DURUYORDU — ve belge yine
bayatladi. Eksik olan sey kural degil, kurali ZORLAYAN KAPIYDI.

SOZLESME: README'de gecen her `X.Y.Z` bicimli surum sabiti ya
  (a) `versions.json`daki GUNCEL bir degere esit olmali, ya da
  (b) TARIHSEL oldugu satirda ACIKCA belirtilmis olmali ("eskiden", "donmustu",
      "kaldirildi" ya da satirdaki bir `20XX-` tarihi).

Boylece:
  · Dogru yazilmis guncel bir surum satiri GECER (yasak degil, bayatlamasi yasak).
  · Surum degistiginde o satir KIRMIZI doner — dorduncu bayatlama imkansiz.
  · Gecmisi anlatan satirlar (degisiklik gunlugu) serbest kalir.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
_README = KOK / "README.md"
_SURUMLER = KOK / "versions.json"

#: Satiri TARIHSEL ilan eden isaretler. Biri varsa o satirdaki eski surumler serbesttir.
# ⚠️ ASCII yazımları da ŞART: depo Türkçe karakterli ve karaktersiz yazımı karışık
# kullanıyor. Yalnız Türkçe yazımı tanımak, geçmişi anlatan bir satırı "bayat" sayıp
# yanlış alarm üretir (ölçüldü).
_TARIHSEL_ISARETLER = (
    "eskiden",
    "donmuştu",
    "donmustu",
    "kaldırıldı",
    "kaldirildi",
    "bayatlamıştı",
    "bayatlamisti",
    "bayatladı",
    "bayatladi",
)

# ⚠️ `(?!\.\d)` ŞART: IP adresleri. `127.0.0.1` içinden `127.0.0` ayıklanıyordu ve kapı
# README'deki loopback adresini "bayat sürüm" sandı (ölçüldü — ilk koşuda yanlış alarm).
# ⚠️ Tek yönlü bakmak YETMEDİ: sondaki `.1`i dışlayınca regex bu kez `127.0.0.1` içinden
# `0.0.1`i yakaladı (`127.` sonrasında sınır var). İKİ yön de dışlanmalı.
_SURUM_DESENI = re.compile(r"(?<![\d.])\d+\.\d+\.\d+(?![\d.])")
_TARIH_DESENI = re.compile(r"\b20\d{2}-\d{2}")


def _guncel_surumler() -> set[str]:
    d = json.loads(_SURUMLER.read_text(encoding="utf-8"))
    out: set[str] = set()
    for anahtar in ("backend", "launcher", "frontendOta"):
        v = d.get(anahtar)
        if isinstance(v, str):
            out.add(v)
    mob = d.get("mobile")
    if isinstance(mob, dict) and isinstance(mob.get("name"), str):
        out.add(mob["name"])
    elif isinstance(mob, str):
        out.add(mob)
    return out


def _tarihsel_mi(satir: str) -> bool:
    dusuk = satir.lower()
    return bool(_TARIH_DESENI.search(satir)) or any(i in dusuk for i in _TARIHSEL_ISARETLER)


def _baglam(satirlar: list[str], i: int) -> str:
    """Satirin TARIHSEL isaret aranacak baglami (1-tabanli `i`).

    ⚠️ SATIR BAZLI KONTROL YETMEZ (olculdu — ikinci yanlis alarm). Markdown prozu satir
    sonuna sarar; "ucuncu kez bayatlamisti" isareti bir satirda, eski surumler BIR SONRAKI
    satirda kalabiliyor. Bu yuzden proz bloklari (ardisik bos-olmayan satirlar) BUTUN
    olarak degerlendirilir.

    ⚠️ TABLO SATIRLARI ISTISNA: `|` ile baslayan satirlara tek tek bakilir. Aksi halde
    degisiklik gunlugu tablosundaki TEK bir "eskiden" kelimesi, ayni tablodaki BASKA bir
    satirdaki gercek bayat surumu de muaf kilardi.
    """
    if satirlar[i - 1].lstrip().startswith("|"):
        return satirlar[i - 1]
    bas = i - 1
    while bas > 0 and satirlar[bas - 1].strip() and not satirlar[bas - 1].lstrip().startswith("|"):
        bas -= 1
    son = i - 1
    while son + 1 < len(satirlar) and satirlar[son + 1].strip() and not satirlar[son + 1].lstrip().startswith("|"):
        son += 1
    return "\n".join(satirlar[bas : son + 1])


def _ihlaller(metin: str | None = None) -> list[tuple[int, str, list[str]]]:
    """Bayat surum tasiyan satirlar. `metin` verilirse README yerine O metne bakar.

    ⚠️ PARAMETRE TESTIN IHTIYACI DEGIL, KAPININ KAPISI. Once bu fonksiyon yalniz README'yi
    okuyordu ve karsit-kanit testi regex/isaret parcalarini AYRI AYRI sinayordu. Mutasyon
    (`_ihlaller`in basina `return []` koymak) butun testleri YESIL birakti — yani kapi,
    kendisinin devre disi birakilmasini goremiyordu. Artik karsit-kanit UYDURMA bir bayat
    belge verip bu fonksiyonun onu GERCEKTEN yakaladigini olcuyor.
    """
    guncel = _guncel_surumler()
    satirlar = (metin if metin is not None else _README.read_text(encoding="utf-8")).splitlines()
    out = []
    for i, satir in enumerate(satirlar, 1):
        bulunan = _SURUM_DESENI.findall(satir)
        if not bulunan or _tarihsel_mi(_baglam(satirlar, i)):
            continue
        bayat = [s for s in bulunan if s not in guncel]
        if bayat:
            out.append((i, satir.strip(), bayat))
    return out


# ═══════════════════════════════════════════════════════════════════════════════════════
# ASIL SOZLESME
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_READMEde_BAYAT_surum_YOK():
    """⚠️ BU TEST DUZELTMEDEN ONCE KIRMIZIYDI (1.9.5 / 1.9.9 / 2.3.3 satiri)."""
    ihlaller = _ihlaller()
    assert not ihlaller, (
        "README'de GUNCEL OLMAYAN surum sabitleri var:\n"
        + "\n".join(f"  satir {no}: {bayat} -> {metin[:110]}" for no, metin, bayat in ihlaller)
        + (
            f"\n\nGuncel degerler (versions.json): {sorted(_guncel_surumler())}\n"
            "Cozum: satiri kaldirip `versions.json`a yonlendirin. Gecmisi anlatiyorsa satirda "
            f"tarihsel oldugunu belirtin ({', '.join(_TARIHSEL_ISARETLER[:3])}... ya da bir 20XX- tarihi)."
        )
    )


def test_KRITIK_versions_json_OKUNABILIR():
    """Kapinin dayanagi. `versions.json` bozulursa kapi sessizce KOR kalirdi."""
    guncel = _guncel_surumler()
    assert len(guncel) >= 3, (
        f"versions.json'dan yalniz {len(guncel)} surum okundu: {guncel}. Sema degistiyse bu "
        "kapi bayat surumleri goremez -> `_guncel_surumler` guncellenmeli."
    )
    for s in guncel:
        assert _SURUM_DESENI.fullmatch(s), f"beklenmeyen surum bicimi: {s!r}"


# ═══════════════════════════════════════════════════════════════════════════════════════
# KARSIT-KANITLAR
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_KARSIT_KANIT_kapi_GERCEKTEN_bayat_yakalar():
    """⚠️ KAPININ KENDI KAPISI — ve bu testin ilk hali DELIKTI.

    Once regex ve tarihsel-isaret parcalari AYRI AYRI sinaniyordu. `_ihlaller`in basina
    `return []` koyan mutasyon butun dosyayi YESIL birakti: kapi, kendisinin devre disi
    birakilmasini goremiyordu. Artik dogrudan `_ihlaller` cagriliyor.
    """
    sahte = "\n".join(
        [
            "# Baslik",
            "",
            "**Yayındaki sürümler:** Backend `1.0.1` · Launcher `1.0.2`",
            "",
        ]
    )
    ihlaller = _ihlaller(sahte)
    assert ihlaller, "UYDURMA bayat belge yakalanmadi -> kapi devre disi (ya da kor)"
    bayat = sorted(b for _, _, bayatlar in ihlaller for b in bayatlar)
    assert bayat == ["1.0.1", "1.0.2"], f"bayat surumler dogru ayiklanmadi: {bayat}"


def test_KARSIT_KANIT_kapi_TEMIZ_belgede_sessiz():
    """Kural "her seyi yakala"ya kaymasin: guncel surum tasiyan belge TEMIZ cikmali."""
    guncel = sorted(_guncel_surumler())
    temiz = f"# Baslik\n\nYayındaki backend sürümü: `{guncel[0]}`\n"
    assert not _ihlaller(temiz), "guncel surum tasiyan TEMIZ belge ihlal sayildi -> kural fazla genis"


def test_KARSIT_KANIT_IP_adresi_surum_SAYILMAZ():
    """⚠️ Ilk kosuda yakalanan YANLIS ALARM: `127.0.0.1` icinden `127.0.0` ayiklaniyordu.

    Gurultulu bir kapi, gercek bulgular arasinda kaybolur ve zamanla kapatilir.
    """
    assert not _SURUM_DESENI.findall("yalniz 127.0.0.1 uzerinden"), "IP adresi surum sanildi"
    assert _SURUM_DESENI.findall("surum 1.9.50 yayinda") == ["1.9.50"], "gercek surum artik yakalanmiyor"


def test_KARSIT_KANIT_sarilmis_proz_BLOK_olarak_degerlendirilir():
    """⚠️ Ikinci YANLIS ALARM: tarihsel isaret bir satirda, surumler SONRAKI satirda kaliyordu."""
    satirlar = [
        "> Burada bir tablo vardi ve ucuncu kez bayatlamisti: `1.0.1`",
        "> / `1.0.2` yazarken gercek deger baskaydi.",
        "",
    ]
    assert _tarihsel_mi(_baglam(satirlar, 2)), "sarilmis prozun ikinci satiri baglamdan KOPTU"


def test_KARSIT_KANIT_TABLO_satiri_komsusundan_MUAF_OLMAZ():
    """Tablo satirlarina tek tek bakilir; birindeki "eskiden" digerini aklamaz."""
    satirlar = ["| A | eskiden boyleydi |", "| B | surum 1.0.9 |"]
    assert not _tarihsel_mi(_baglam(satirlar, 2)), (
        "tablo satiri komsusundaki tarihsel isaretten MUAF oldu -> gercek bayatlama kacar"
    )


def test_KARSIT_KANIT_TARIHSEL_satirlar_serbest():
    """Kural "README'de rakam yasak"a kaymamali.

    Degisiklik gunlugu gecmisteki surumleri anmak ZORUNDA; onlari yasaklamak belgeyi
    fakirlestirir ve kapiyi gereksiz yere gurultulu yapar.
    """
    ornekler = [
        "tablo 2026-08-06'da donmuştu: `1.9.5 / 2.3.3` yazarken gerçek sürümler `1.9.16`ydı",
        "Windows client `launcher-v1.9.9`; Android kendi etiketine taşındı — eskiden ortak etiket",
    ]
    for satir in ornekler:
        assert _tarihsel_mi(satir), f"tarihsel satir SERBEST kalmali ama yakalandi: {satir[:70]}"


def test_KARSIT_KANIT_GUNCEL_surum_yazmak_serbest():
    """Surum yazmak yasak DEGIL; BAYATLAMASI yasak. Guncel bir deger gecebilmeli."""
    guncel = sorted(_guncel_surumler())
    satir = f"Yayındaki sürüm: `{guncel[0]}`"
    bayat = [s for s in _SURUM_DESENI.findall(satir) if s not in _guncel_surumler()]
    assert not bayat, "guncel surum yazan bir satir kapiya takildi -> kural fazla genis"
