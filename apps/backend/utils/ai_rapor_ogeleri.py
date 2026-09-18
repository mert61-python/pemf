# -*- coding: utf-8 -*-
# Author: mertaygn
"""AI ANALİZ KAYDI → PDF ÖĞELERİ (ev sahibi paylaşımı, 2026-09-12).

===============================================================================
NEDEN VAR
===============================================================================
Ev sahibi profili analiz yapıyor ama sonucu veterinerine GÖNDEREMİYORDU: PDF üretimi
yalnız SEANS kayıtları için vardı (`generate_session_report`), AI analizleri için yoktu.
Sahibin "pet owner için ne ekleyebiliriz" sorusuna verilen dört cevaptan biri buydu.

===============================================================================
TASARIM
===============================================================================
`result_detail` HETEROJENDİR: her AI modülü kendi şeklini yazar (petri kuyu sayıları,
böbrek CT sınıfı, yara kapanma yüzdesi, ses sınıfları...). Bu modül o sözlüğü PDF
üreticisinin beklediği düz `{"etiket", "aciklama"}` listesine çevirir.

⚠️ SAF FONKSİYON — DB/HTTP/dosya YOK. Böylece heterojen gerçek kayıtlarla test edilebilir;
"şu modülde çöküyor" sınıfı arızalar kapıyla yakalanır (bkz. tests/test_ai_rapor_pdf.py).

⚠️ GÖRSEL ALANLARI DIŞARIDA BIRAKILIR: `result_detail` içinde base64 görseller olabilir
(panel mozaikleri). Onları metne çevirmek raporu kilometrelerce uzatır ve okunamaz kılar.
"""

from __future__ import annotations

from typing import Any

#: Rapora ALINMAYACAK alanlar — base64 görseller ve iç ayrıntılar.
#: ⚠️ Değer bazlı değil AD bazlı eleme: 40 KB'lık bir base64 dizgisini "açıklama" diye
#: yazdırmak PDF'i kullanılamaz hâle getirirdi.
GIZLI_ALAN_PARCALARI = ("base64", "_b64", "image", "mask", "panel", "overlay", "heatmap")

#: Tek bir değerin metin karşılığında izin verilen azami uzunluk.
#: ⚠️ Uzun serileri (ör. 500 elemanlı olasılık dizisi) kırpıp "… (N öğe)" demek, hem
#: raporu okunur tutar hem de bilginin var olduğunu SÖYLER (sessizce atmaz).
AZAMI_DEGER_UZUNLUGU = 300

#: Türkçe etiketler — bilinen anahtarlar için. Bilinmeyen anahtar HAM gösterilir
#: (sessizce atılmaz: operatör alanın var olduğunu görmeli).
ETIKETLER = {
    "closure_pct": "Kapanma (%)",
    "mean_gap_um": "Ortalama gap (µm)",
    "max_gap_um": "Maksimum gap (µm)",
    "gap_area_mm2": "Gap alanı (mm²)",
    "n_cells": "Hücre sayısı",
    "coverage_ratio": "Kaplama oranı",
    "score_mean": "Ortalama skor",
    "device": "Cihaz",
    "confidence": "Güven",
    "predicted_class": "Tahmin",
    "class_name": "Sınıf",
    "n_wells": "Kuyu sayısı",
    "n_tumors": "Tümör sayısı",
}


def _gizli_mi(anahtar: str) -> bool:
    a = str(anahtar).lower()
    return any(p in a for p in GIZLI_ALAN_PARCALARI)


def _metne_cevir(deger: Any) -> str:
    """Bir değeri PDF'e yazılabilir tek satıra çevirir (uzunsa KIRPAR ama SÖYLER)."""
    if isinstance(deger, bool):
        return "Evet" if deger else "Hayır"
    if isinstance(deger, float):
        return f"{deger:.4g}".replace(".", ",")
    if isinstance(deger, (list, tuple)):
        if not deger:
            return "—"
        parcalar = [_metne_cevir(x) for x in deger[:8]]
        kuyruk = f" … ({len(deger)} öğe)" if len(deger) > 8 else ""
        return ", ".join(parcalar) + kuyruk
    if isinstance(deger, dict):
        if not deger:
            return "—"
        ic = ", ".join(f"{k}: {_metne_cevir(v)}" for k, v in list(deger.items())[:6] if not _gizli_mi(k))
        return (ic or "—")[:AZAMI_DEGER_UZUNLUGU]
    s = "—" if deger is None else str(deger)
    if len(s) > AZAMI_DEGER_UZUNLUGU:
        return s[:AZAMI_DEGER_UZUNLUGU] + f"… (toplam {len(s)} karakter)"
    return s


def analiz_pdf_ogeleri(kayit: dict) -> list[dict]:
    """Bir AI analiz kaydını `generate_xai_report`ın beklediği öğe listesine çevirir.

    ⚠️ ÜST BİLGİ ÖNCE: hasta, tarih, modül ve güven — veteriner raporu açtığında ilk
    görmesi gereken şey "kim, ne zaman, hangi model" olmalı.
    """
    ogeler: list[dict] = []

    def ekle(etiket: str, deger: Any) -> None:
        metin = _metne_cevir(deger)
        if metin and metin != "—":
            ogeler.append({"etiket": etiket, "aciklama": metin})

    ekle("Hasta", kayit.get("patient_name"))
    ekle("Tarih", kayit.get("created_at"))
    ekle("Analiz", kayit.get("module_label") or kayit.get("module_id"))
    ekle("Sonuç", kayit.get("result_summary"))
    g = kayit.get("confidence")
    if isinstance(g, (int, float)):
        ekle("Güven", f"%{round(float(g) * 100)}")

    detay = kayit.get("result_detail")
    if isinstance(detay, dict):
        for anahtar, deger in detay.items():
            if _gizli_mi(anahtar):
                continue
            ekle(ETIKETLER.get(anahtar, str(anahtar)), deger)

    # ⚠️ HEKİM DEĞERLENDİRMESİ EN SONDA ve AYRI: AI çıktısı öneridir, klinik karar hekimindir.
    # Raporun sonunda durması, okuyanın önce ölçümü sonra yorumu görmesini sağlar.
    ekle("Hekim değerlendirmesi", kayit.get("review_note") or kayit.get("vet_review"))
    return ogeler
