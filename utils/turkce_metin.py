# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""TÜRKÇE-GÜVENLİ METİN KATLAMA — arama/karşılaştırma için TEK KAYNAK.

⚠️ NEDEN (saha bulgusu 2026-08-30): Python `str.lower()` Türkçe'de yanlıştır ve tıbbi kayıtta
hasta erişimini bozar:
    'İ'.lower() → 'i̇'  (i + U+0307 BİRLEŞİK NOKTA, İKİ karakter)
    'I'.lower() → 'i'   (oysa Türkçe'de 'ı' beklenir)

Ölçülen sonuç: "İhsan" kaydedip "ihsan" arayan doktor hastayı BULAMIYORDU. Aynı tuzak, hasta
adının `.lower()` ile karşılaştırıldığı HER yerde (arama indeksi, PDF rapor filtresi) tekrarlar.
Bu modül o mantığı TEK yerde toplar → bir yüzeyde düzeltilip başka yüzeyde unutulması imkânsız.

`arama_katla` GÖRÜNTÜLENEN metni DEĞİŞTİRMEZ; yalnız arama/karşılaştırma token'ı üretir. Katlama
bilinçli olarak GENİŞtir (kullanıcı ASCII klavyeyle de arayabilmeli: "isik" → "Işık"); yanlış
eşleşme değil, geniş eşleşme — sonucu insan seçer.
"""

from __future__ import annotations

import re
import unicodedata

# Türkçe → ASCII katlama. `str.lower()`ın bozduğu İ/I/ı BURADA, düşürmeden ÖNCE çözülür.
_TR_FOLD = str.maketrans(
    {
        "İ": "i",
        "I": "i",
        "ı": "i",
        "Ş": "s",
        "ş": "s",
        "Ğ": "g",
        "ğ": "g",
        "Ç": "c",
        "ç": "c",
        "Ö": "o",
        "ö": "o",
        "Ü": "u",
        "ü": "u",
    }
)

# Bu mantık her değişince ARTIR. Arama indeksi parmak-izine katılır
# (database.patient_database._SEARCH_NORM_VERSION) → sahadaki indeks kendiliğinden yeniden kurulur.
SURUM = 2


def arama_katla(value: str) -> str:
    """Metni Türkçe-güvenli, ASCII-katlanmış, boşluk-normalize bir arama token'ına indirger.

    Kayıt ve sorgu AYNI fonksiyondan geçtiğinde "İhsan"/"ihsan"/"IHSAN"/"isik" hepsi eşleşir.
    """
    text = str(value or "").strip()
    # 1) Türkçe özel harfler ÖNCE (str.lower'ın İ/I bozması burada engellenir).
    text = text.translate(_TR_FOLD)
    # 2) Kalan aksanları (é, ñ …) NFKD ile ayrıştırıp birleşik işaretleri at.
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    # 3) Artık ASCII-güvenli; düşürme birleşik-nokta üretmez.
    text = text.lower()
    return re.sub(r"\s+", " ", text)
