# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""TÜRKÇE-DOĞRU ARAMA NORMALİZASYONU — arama/karşılaştırma için TEK KAYNAK.

⚠️ NEDEN (saha bulgusu 2026-08-30): Python `str.lower()` Türkçe'de yanlıştır ve tıbbi kayıtta
hasta erişimini bozar:
    'İ'.lower() → 'i̇'  (i + U+0307 BİRLEŞİK NOKTA, İKİ karakter)
    'I'.lower() → 'i'   (oysa Türkçe'de 'ı' beklenir)

Ölçülen sonuç: "İhsan" kaydedip "ihsan" arayan doktor hastayı BULAMIYORDU. Aynı tuzak, hasta
adının `.lower()` ile karşılaştırıldığı HER yerde (arama indeksi, PDF rapor filtresi) tekrarlar.
Bu modül o mantığı TEK yerde toplar → bir yüzeyde düzeltilip başka yüzeyde unutulması imkânsız.

⚠️ KURAL YALNIZ İ/I'DİR — AKSAN DÜZLEŞTİRİLMEZ (mobil `pf/src/utils/aramaNormalize.ts` ile
BİREBİR AYNI, bilinçli hizalama 2026-08-30). İlk düzeltme aksanları da katlıyordu (ş→s, ç→c,
ö→o…); bu YANLIŞTI: "Şirin" ile "Sirin"i, "Gökçe" ile "Gokce"yi birleştirmek bir HASTA-KİMLİĞİ
ekranında yanlış kayda bakma riski demektir (mobil ekip bunu daha önce ölçüp reddetmişti). Üstelik
ı ve i Türkçe'de AYRI harflerdir; onları birleştirmek dilbilimsel olarak da yanlış. İki uç (mobil
client-side süzme + backend arama indeksi) artık AYNI kuralı kullanır → aynı hasta, aynı terim,
iki cihazda AYNI sonuç.

`arama_katla` GÖRÜNTÜLENEN metni DEĞİŞTİRMEZ; yalnız arama/karşılaştırma token'ı üretir.
"""

from __future__ import annotations

import re
import unicodedata

# Türkçe-DOĞRU küçültme: İ→i, I→ı. `str.lower()`ın bozduğu tam bu iki harf; ötekiler `.lower()`e
# bırakılır. Mobil `toLocaleLowerCase("tr")` eşdeğeri. ⚠️ AKSAN (ş/ç/ğ/ö/ü) BURADA YOK — bilinçli.
_TR_LOWER = str.maketrans({"İ": "i", "I": "ı"})

# Bu mantık her değişince ARTIR. Arama indeksi parmak-izine katılır
# (database.patient_database._SEARCH_NORM_VERSION) → sahadaki indeks kendiliğinden yeniden kurulur.
# v2: Türkçe düzeltme (aksan katlamalı, geri alındı). v3: mobil ile hizalı (İ/I-only, aksan korunur).
SURUM = 3


def arama_katla(value: str) -> str:
    """Metni Türkçe-doğru küçültülmüş, NFC-normalize, boşluk-tekilleştirilmiş bir arama token'ına
    indirger. Kayıt ve sorgu AYNI fonksiyondan geçtiğinde "İhsan"/"ihsan"/"İHSAN" eşleşir; ama
    "Şirin"/"Sirin" ve "Işık"/"isik" AYRI kalır (aksan ve ı/i korunur — mobil ile aynı).
    """
    text = str(value or "").strip()
    # 1) İ→i, I→ı (Türkçe-doğru); kalan harfler .lower() ile — İ/I map'i önce olduğu için
    #    `str.lower()`ın birleşik-nokta/yanlış-eşleme tuzağı devreye girmez.
    text = text.translate(_TR_LOWER).lower()
    # 2) NFC: farklı kaynaklardan (klavye, kopyala-yapıştır, DB) gelen birleşik işaretleri tek
    #    kod noktasına toparla ki aynı görünen metinler eşit karşılaşsın. Aksan SİLİNMEZ.
    text = unicodedata.normalize("NFC", text)
    return re.sub(r"\s+", " ", text)


def sayiya_cevir(deger, varsayilan=None):
    """Türkçe ondalık-virgül TOLERANSLI sayı çözümü. "3,5" → 3.5, "3.5" → 3.5, 3.5 → 3.5.

    ⚠️ NEDEN (saha bulgusu 2026-08-30, hasta güvenliği): Python `float("3,5")` → ValueError.
    `ai/hybrid_recommender` hasta kilosunu `float(weight)` ile çözüp HATA'da SESSİZCE 15 kg
    varsayılana düşüyordu → 3,5 kg'lık küçük hayvan "medium" kategoriye girip YANLIŞ DOZ süresi
    alıyordu. Frontend nokta-normalize ediyor ama eski kayıt / import / doğrudan-API virgül
    içerebilir. Kilo ve yaş DOZA girer → parse HER YÜZEYDE virgül-toleranslı olmalı; tek kaynak.

    Geçersiz (harf, boş, None) girdide `varsayilan` döner — çağıran güvenli bir varsayılan verir.
    ⚠️ Binlik ayraç DESTEKLENMEZ (tıbbi kilo/yaşta kullanılmaz): "1.234,5" → başarısız → varsayılan.
    """
    if deger is None:
        return varsayilan
    if isinstance(deger, bool):  # bool int'in alt-tipi; kiloda anlamsız
        return varsayilan
    if isinstance(deger, (int, float)):
        return float(deger)
    try:
        return float(str(deger).strip().replace(",", "."))
    except (ValueError, TypeError):
        return varsayilan
