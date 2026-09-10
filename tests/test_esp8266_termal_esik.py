# -*- coding: utf-8 -*-
# Author: mertaygn
"""8266 TERMAL KESME EŞİĞİ — sahip kararı 100 °C + eşik sayısı MESAJA KOPYALANMAZ.

SAHİP KARARI 2026-09-10: 8266'nın yerel termal kesmesi **48 °C → 100 °C**.
S3 ve STM32 48 °C'de KALDI (bilinçli asimetri; STM eşiği
`tests/test_stm_dalga_sozlesmesi.py` ile ayrıca pinli).

⚠️ NEDEN BU KAPI VAR — İKİ AYRI SEBEP:

1. **Eşik TEK koruma katmanı.** Backend hiçbir sıcaklık limiti dayatmıyor (ölçüldü:
   `servers/` içinde sıcaklık eşiği yok; safety-limit bilinçli kaldırılmıştı). Bobini
   durduracak tek şey firmware'deki bu sabit. Kazara 48'e geri dönmek sahibin kararını
   sessizce iptal eder; kazara 200'e çıkmak da koruma bırakmaz.

2. **SÜRÜKLENME YASAĞI (asıl değer).** Eşik ESKİDEN kullanıcıya giden mesajın içine
   ELLE kopyalanmıştı:

       publishEvent("thermal_lock", "Start reddedildi: bobin sicak (>48C), ...")

   Sabit 100'e çekilince bu mesaj YALAN oldu. Bu, depoda tekrar eden "sihirli sayı ikinci
   bir yere kopyalanmış" sınıfı (aynı sınıf 8266 status buffer'ında 480 ↔ 640
   sürüklenmesi olarak telemetriyi komple düşürmüştü). Artık mesaj `TERMAL_KESME_C`'den
   `snprintf` ile TÜRETİLİYOR ve bu kapı sabit sayının geri kopyalanmasını YASAKLIYOR.

C bu makinede DERLENEMEZ → doğrulanabilir olan YAPISAL. Gerçek doğrulama (bobin 100 °C'de
gerçekten duruyor, panel doğru eşiği yazıyor) tezgâh-ONLY.
⚠️ REFLASH gerekli — firmware pakete girmez.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
ESP8266 = KOK / "firmware" / "esp8266_pemf_coil"
S3 = KOK / "firmware" / "esps3_pemf_coil"

pytestmark = pytest.mark.skipif(not ESP8266.exists(), reason="firmware/ kaynak agaci yok")

#: Sahip kararı (2026-09-10). Değiştirilirse BİLİNÇLİ olsun diye pinli.
BEKLENEN_KESME = 100.0
BEKLENEN_DONUS = 97.0


def _oku(p: Path) -> str:
    return io.open(p, encoding="utf-8", errors="replace").read()


def _sabit(kaynak: str, ad: str) -> float | None:
    m = re.search(r"#define\s+" + ad + r"\s+([0-9]+(?:\.[0-9]+)?)f?", kaynak)
    return float(m.group(1)) if m else None


def string_literalleri(kaynak: str) -> list[tuple[int, str]]:
    """Kaynaktaki C string literallerini (satir_no, icerik) olarak döndürür.

    Karakter-karakter durum makinesi: regex + ters-bölü kombinasyonu bu ortamda
    kırılgan olduğu için elle yürütülüyor. Yorumlar ATLANIR (yorumdaki bir sayı
    kullanıcıya gitmez, dolayısıyla sürüklenme riski değildir).
    """
    BS = chr(92)
    TEK = chr(39)
    out: list[tuple[int, str]] = []
    i, n, durum = 0, len(kaynak), "kod"
    bicim: list[str] = []
    satir = 1
    while i < n:
        ch = kaynak[i]
        if ch == "\n":
            satir += 1
        if durum == "kod":
            if kaynak[i : i + 2] == "//":
                durum = "satiryorum"
                i += 2
                continue
            if kaynak[i : i + 2] == "/*":
                durum = "blokyorum"
                i += 2
                continue
            if ch == '"':
                durum = "str"
                bicim = []
                bas_satir = satir
                i += 1
                continue
            if ch == TEK:
                durum = "chr"
                i += 1
                continue
        elif durum == "satiryorum":
            if ch == "\n":
                durum = "kod"
        elif durum == "blokyorum":
            if kaynak[i : i + 2] == "*/":
                durum = "kod"
                i += 2
                continue
        elif durum == "str":
            if ch == BS:
                bicim.append(kaynak[i : i + 2])
                i += 2
                continue
            if ch == '"':
                out.append((bas_satir, "".join(bicim)))
                durum = "kod"
                i += 1
                continue
            bicim.append(ch)
        elif durum == "chr":
            if ch == BS:
                i += 2
                continue
            if ch == TEK:
                durum = "kod"
        i += 1
    return out


#: "48C", "100 C", ">=48C" gibi SICAKLIK gibi görünen sabit sayı (format belirteci DEĞİL).
SICAKLIK_SAYISI = re.compile(r"[0-9]{2,3}\s?C(?![a-zA-Z0-9_])")


def sabit_esik_tasiyan_mesajlar(kaynak: str) -> list[tuple[int, str]]:
    return [(s, t) for s, t in string_literalleri(kaynak) if SICAKLIK_SAYISI.search(t)]


def test_KRITIK_8266_kesme_esigi_SAHIP_KARARI():
    """8266 eşiği 100 °C, dönüş 97 °C olmalı (sahip kararı 2026-09-10)."""
    h = _oku(ESP8266 / "SharedDefs.h")
    kesme = _sabit(h, "TERMAL_KESME_C")
    donus = _sabit(h, "TERMAL_DONUS_C")
    assert kesme == BEKLENEN_KESME, (
        f"8266 TERMAL_KESME_C={kesme}, sahip karari {BEKLENEN_KESME}. Backend hicbir "
        "sicaklik limiti dayatmadigi icin bu sabit TEK koruma katmanidir; degisiklik "
        "BILINCLI olmali."
    )
    assert donus == BEKLENEN_DONUS, f"8266 TERMAL_DONUS_C={donus}, beklenen {BEKLENEN_DONUS}"


def test_KRITIK_histerezis_TUTARLI():
    """Dönüş eşiği kesmeden KÜÇÜK olmalı, yoksa kilit hiç açılmaz ya da hemen açılır."""
    h = _oku(ESP8266 / "SharedDefs.h")
    kesme = _sabit(h, "TERMAL_KESME_C")
    donus = _sabit(h, "TERMAL_DONUS_C")
    assert donus < kesme, f"TERMAL_DONUS_C ({donus}) kesmeden ({kesme}) KUCUK olmali"
    assert kesme - donus >= 2.0, (
        f"histerezis bandi {kesme - donus} °C COK DAR: sensor gurultusu kesme/serbest cirpinmasi (chatter) uretir"
    )


def test_KRITIK_esik_sayisi_MESAJA_KOPYALANMAMIS():
    """Kullanıcıya giden hiçbir mesaj sabit sıcaklık sayısı TAŞIMAMALI.

    MUTASYON: mesajı `snprintf`/`TERMAL_KESME_C` yerine tekrar elle yaz
    (`"... (>48C) ..."` ya da `"... (>100C) ..."`) → KIRMIZI.
    Sahadaki etki: eşik değişince mesaj yalan söyler ve operatör yanlış eşiğe güvenir.
    """
    ihlal: list[tuple[str, int, str]] = []
    for p in sorted(list(ESP8266.glob("*.ino")) + list(ESP8266.glob("*.cpp"))):
        for satir, metin in sabit_esik_tasiyan_mesajlar(_oku(p)):
            ihlal.append((p.name, satir, metin))
    assert not ihlal, (
        "Kullaniciya giden mesaj(lar)da SABIT sicaklik sayisi var → esik degisince "
        "mesaj YALAN olur. `snprintf` + TERMAL_KESME_C ile turetilmeli. Bulunanlar: "
        + "; ".join(f"{a}:{b} {c!r}" for a, b, c in ihlal)
    )


def test_KRITIK_mesaj_esik_sabitinden_TURETILIYOR():
    """Termal kilit mesajı gerçekten `TERMAL_KESME_C`'den üretilmeli.

    Karşıt kanıt: yukarıdaki yasak, mesajdan sayıyı TAMAMEN silmekle de sağlanabilirdi
    (o zaman operatör eşiği hiç görmezdi). Eşiğin mesaja SABİTTEN aktığını da pinle.
    """
    ino = _oku(ESP8266 / "esp8266_pemf_coil.ino")
    i = ino.find("thermal_lock")
    assert i > 0, "thermal_lock olayi bulunamadi -> kapi BAYAT"
    pencere = ino[max(0, i - 700) : i + 200]
    assert "TERMAL_KESME_C" in pencere, (
        "thermal_lock mesaji TERMAL_KESME_C'den turetilmiyor -> operator esigi goremez "
        "ya da sabit yeniden kopyalanmis olur"
    )


def test_S3_ve_asimetri_BILINCLI():
    """S3 48 °C'de KALDI — sahip yalnız 8266 dedi; asimetri kasıtlı, pinli.

    Karşıt kanıt: biri "tutarlılık" adına S3'ü de 100'e çekmesin.
    """
    if not (S3 / "SharedDefs.h").exists():
        pytest.skip("esps3 kaynagi yok")
    s3 = _oku(S3 / "SharedDefs.h")
    assert _sabit(s3, "TERMAL_KESME_C") == 48.0, (
        "S3 termal esigi degismis. Sahip 2026-09-10'da YALNIZ 8266 icin 100 °C dedi; "
        "S3'u de degistirmek AYRI bir karar gerektirir."
    )


def test_KARSIT_KANIT_kapi_gercekten_olcuyor():
    """Öz-test: literal ayrıştırıcı ve sıcaklık deseni gerçekten ayırt ediyor."""
    # sabit sayi TASIYAN mesaj -> ihlal
    kotu = 'void f() { publishEvent("x", "bobin sicak (>48C), bekleniyor"); }'
    assert sabit_esik_tasiyan_mesajlar(kotu), "kapi sabit 48C tasiyan mesaji YAKALAMADI"

    # turetilmis mesaj -> ihlal DEGIL (format belirteci sayi degil)
    iyi = 'void f() { snprintf(m, n, "bobin sicak (>=%.0fC)", (double)TERMAL_KESME_C); }'
    assert not sabit_esik_tasiyan_mesajlar(iyi), "kapi TURETILMIS mesaji ihlal sandi"

    # YORUM icindeki sayi kapiyi ALDATMAMALI (yorum kullaniciya gitmez)
    yorum = 'void f() { /* eski esik 48C idi */ publishEvent("x", "ok"); }'
    assert not sabit_esik_tasiyan_mesajlar(yorum), (
        "YORUM icindeki sayi ihlal sayildi -> literal ayristirici yorumlari atlamiyor"
    )

    # 100C de yakalanmali (yeni degerin geri kopyalanmasi da yasak)
    yeni_kotu = 'void f() { publishEvent("x", "bobin sicak (>100C)"); }'
    assert sabit_esik_tasiyan_mesajlar(yeni_kotu), "kapi YENI degerin kopyasini yakalamadi"
