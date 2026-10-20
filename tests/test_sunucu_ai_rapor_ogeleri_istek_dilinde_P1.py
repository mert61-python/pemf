# -*- coding: utf-8 -*-
"""I18N-P1 · SUNUCU 10d — AI analiz PDF öğeleri (`utils/ai_rapor_ogeleri.py`) istek dilinde.

Türkçe çıktı ESKİ uygulamanın çıktısıyla BAYT BAYT aynı (beklenen liste, taşıma ÖNCESİ kodla üretildi ve burada sabittir); `X-PEMF-Dil: en` → İngilizce:
etiketler, sınıf / belirti adları, yüzde biçimi (%78 ↔ 78%), ondalık ayracı (virgül ↔ nokta), tarih (13 Ekim 2026 ↔ 13 Oct 2026), notlar. Arayüzle ORTAK kimliklerde
İngilizce arayüzünkiyle aynıdır (K-7 kapısı). MUTASYON: katalog TR değeri değişirse / tablo ham metne dönerse / yüzde biçimi dile bağlanmazsa KIRMIZI.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
for p in (KOK, KOK / "apps" / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

TR_HARF = re.compile(r"[çğıöşüÇĞİÖŞÜ]")

KAYIT = {
    "patient_name": "Mia",
    "created_at": "2026-10-13T19:45:00",
    "module_label": "feline disease",
    "result_summary": "Conjunctivitis",
    "confidence": 0.78,
    "review_note": "Kontrol edildi",
    "result_detail": {
        "low_confidence": True,
        "results": [
            {"disease": "conjunctivitis", "probability": 0.78},
            {"disease": "feline asthma", "probability": 0.004},
            {"disease": "kidney stone", "probability": 0.2},
        ],
        "xai": {
            "top_features": [
                {"feature": "Eye_Discharge_bin", "attribution": -3.196},
                {"feature": "Age", "attribution": 1.2},
                {"feature": "has_Fever", "attribution": 0.2},
                {"feature": "Bilinmeyen_X", "attribution": 9},
            ]
        },
        "girdi_dogrulama": {"dogrulandi": False, "uyari": "UYARI METNİ", "yon_notu": "YÖN NOTU"},
        "prediction": {"label": "sick", "probability_sick": 0.912},
        "n_cancer": 3,
        "localized": True,
        "closure_pct": 42.5,
        "mean_gap_um": 12.345,
        "pose_type": "lateral",
        "pain_level": "no pain",
        "risk_level": "mild pain",
        "cat_count": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "warnings": [0, 1, 2],
        "class_counts": {"erythrocyte": 5, "punctate reticulocyte": 2, "bilinmeyen": 3},
        "not": "y" * 400,
        "gizemli_alan": 1,
    },
}

#: ESKİ (taşıma öncesi) kodun çıktısı — Türkçe bayt bayt.
ESKI_TR = [
    {'etiket': 'Hasta', 'aciklama': 'Mia'},
    {'etiket': 'Analiz tarihi', 'aciklama': '13 Ekim 2026, 19:45'},
    {'etiket': 'Analiz türü', 'aciklama': 'feline disease'},
    {'etiket': 'Sonuç', 'aciklama': 'Konjonktivit (göz nezlesi)'},
    {
        'etiket': 'Yapay zekânın bu sonuca güveni',
        'aciklama': '%78 — modelin kendi tahminine ne kadar güvendiğini gösterir; kesin tanı değildir.',
    },
    {
        'etiket': 'Dikkat',
        'aciklama': 'Yapay zekânın bu sonuca güveni düşük. Sonucu tek başına kullanmayın; mutlaka veteriner hekiminize danışın.',
    },
    {
        'etiket': 'Olası tanılar (olasılık sırasıyla)',
        'satirlar': ['1. Konjonktivit (göz nezlesi) — %78', '2. Böbrek taşı — %20', "3. Kedi astımı — %1'in altında"],
    },
    {
        'etiket': 'Sonucu en çok etkileyen belirtiler',
        'satirlar': [
            'Göz akıntısı: orta etki — bu tanının olasılığını azalttı',
            'Yaş: zayıf etki — bu tanının olasılığını artırdı',
            'Ateş: zayıf etki — bu tanının olasılığını artırdı',
        ],
        'aciklama': 'Yapay zekânın bu sonuca varırken en çok dikkate aldığı bilgiler. Belirtinin hayvanda bulunması ya da bulunmaması sonucu bu '
        'yönde etkiledi.',
    },
    {'etiket': 'Görüntü kontrolü', 'aciklama': 'UYARI METNİ'},
    {'etiket': 'Not', 'aciklama': 'YÖN NOTU'},
    {'etiket': 'Tahmin', 'aciklama': 'Hasta (riskli)'},
    {'etiket': 'Hastalık olasılığı', 'aciklama': '%91'},
    {'etiket': 'Kanserli kuyucuk sayısı', 'aciklama': '3'},
    {'etiket': 'Konumu belirlendi mi', 'aciklama': 'Evet'},
    {'etiket': 'Yara kapanma oranı (%)', 'aciklama': '42,5'},
    {'etiket': 'Ortalama yara aralığı (µm)', 'aciklama': '12,35'},
    {'etiket': 'Hayvanın duruşu', 'aciklama': 'Yandan'},
    {'etiket': 'Ağrı düzeyi', 'aciklama': 'Ağrı yok'},
    {'etiket': 'Risk düzeyi', 'aciklama': 'Hafif ağrı'},
    {'etiket': 'Görüntüdeki kedi sayısı', 'aciklama': '1, 2, 3, 4, 5, 6, 7, 8 … (10 öğe)'},
    {'etiket': 'Uyarılar', 'aciklama': '0, 1, 2'},
    {'etiket': 'Bulgu sayıları', 'aciklama': 'Eritrosit (alyuvar): 5; Noktalı retikülosit (genç alyuvar): 2'},
    {
        'etiket': 'Not',
        'aciklama': 'yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy… '
        '(toplam 400 karakter)',
    },
    {'etiket': 'Veteriner hekim değerlendirmesi', 'aciklama': 'Kontrol edildi'},
    {
        'etiket': 'Not',
        'aciklama': 'Bazı teknik ölçümler bu rapora alınmadı; tamamı uygulamadaki analiz geçmişinde görülebilir.',
    },
    {
        'etiket': 'Önemli',
        'aciklama': 'Bu rapor yapay zekâ ile hazırlanmış bir ön değerlendirmedir. Kesin tanı ve tedavi kararını veteriner hekim verir.',
    },
]


@pytest.fixture(params=["tr", "en"])
def dil(request):
    from utils import ceviri

    jeton = ceviri.istek_dili_var.set(request.param)
    try:
        yield request.param
    finally:
        ceviri.istek_dili_var.reset(jeton)


def test_Turkce_cikti_eski_kodla_BAYT_BAYT_ayni():
    from utils import ceviri
    from utils.ai_rapor_ogeleri import analiz_pdf_ogeleri

    jeton = ceviri.istek_dili_var.set("tr")
    try:
        assert analiz_pdf_ogeleri(KAYIT) == ESKI_TR
    finally:
        ceviri.istek_dili_var.reset(jeton)
    assert analiz_pdf_ogeleri(KAYIT) == ESKI_TR  # dil bağlamı yok = Türkçe (cihaz dili ayarsız)


def test_Ingilizce_cikti_Ingilizce_ve_bicimler_dile_gore():
    from utils import ceviri
    from utils.ai_rapor_ogeleri import analiz_pdf_ogeleri

    jeton = ceviri.istek_dili_var.set("en")
    try:
        o = analiz_pdf_ogeleri(KAYIT)
    finally:
        ceviri.istek_dili_var.reset(jeton)
    assert len(o) == len(ESKI_TR)
    metin = " | ".join(
        str(x.get("etiket")) + " " + str(x.get("aciklama", "")) + " " + " ".join(x.get("satirlar", [])) for x in o
    )
    # Türkçe HARF yalnız kullanıcı verisinde (UYARI METNİ / YÖN NOTU = sunucu girdisi, "Kontrol edildi" = hekim notu)
    veri_haric = metin.replace("UYARI METNİ", "").replace("YÖN NOTU", "").replace("Kontrol edildi", "")
    assert not TR_HARF.search(veri_haric), TR_HARF.findall(veri_haric)
    harita = {x["etiket"]: x for x in o}
    assert o[0] == {"etiket": "Patient", "aciklama": "Mia"}
    assert harita["Analysis date"]["aciklama"] == "13 Oct 2026, 19:45"
    assert harita["AI confidence in this result"]["aciklama"].startswith("78% — shows how confident the model is")
    assert harita["Possible diagnoses (in order of probability)"]["satirlar"] == [
        "1. Conjunctivitis (pink eye) — 78%",
        "2. Kidney stone — 20%",
        "3. Feline asthma — below 1%",
    ]
    assert harita["Signs that influenced the result most"]["satirlar"] == [
        "Eye discharge: moderate effect — decreased the likelihood of this diagnosis",
        "Age: weak effect — increased the likelihood of this diagnosis",
        "Fever: weak effect — increased the likelihood of this diagnosis",
    ]
    assert harita["Wound closure rate (%)"]["aciklama"] == "42.5"  # ondalık ayracı nokta (Türkçede 42,5)
    assert harita["Mean wound gap (µm)"]["aciklama"] == "12.35"
    assert harita["Probability of disease"]["aciklama"] == "91%"
    assert harita["Position determined"]["aciklama"] == "Yes"
    assert harita["Number of cats in the image"]["aciklama"] == "1, 2, 3, 4, 5, 6, 7, 8 … (10 items)"
    assert harita["Prediction"]["aciklama"] == "Sick patient (at risk)"
    assert harita["Finding counts"]["aciklama"].startswith(
        "Erythrocyte (red blood cell): 5; Punctate reticulocyte (young red blood cell): 2"
    )
    assert (
        harita["Veterinarian's assessment"]["aciklama"] == "Kontrol edildi"
    )  # hekim notu: kullanıcı verisi, çevrilmez
    assert o[-1]["etiket"] == "Important" and o[-1]["aciklama"].startswith("This report is a preliminary assessment")
    assert any(
        x["etiket"] == "Note" and x["aciklama"].startswith("Some technical measurements were not included") for x in o
    )
    assert any(x["aciklama"].endswith("… (400 characters in total)") for x in o if "aciklama" in x)


def test_Ingilizce_ortak_kimliklerde_arayuzle_ayni_K7_ile_tutarli():
    """Ortak kimliğin EN'i arayüz kataloğundakiyle aynı (K-7'nin sunucu tarafı örneklemi)."""
    from utils import ceviri

    assert ceviri.t("ai.etiket.detected", dil="en") != ""
    assert ceviri.t("ai.deger.no_pain", dil="en") == "No pain"
    assert ceviri.t("ai.deger.no_pain", dil="tr") == "Ağrı yok"
    assert ceviri.t("ai.belirti.Age", dil="en") == "Age"


@pytest.mark.parametrize("n,tr,en", [(1, "1 kayıt", "1 record"), (3, "3 kayıt", "3 records")])
def test_cogul_kayit(n, tr, en):
    from utils import ceviri

    assert ceviri.t("ai.rapor.kayit", dil="tr", count=n) == tr
    assert ceviri.t("ai.rapor.kayit", dil="en", count=n) == en


def test_bilinmeyen_deger_ceviri_olmadan_aynen_ve_ham_alan_gosterilmez(dil):
    from utils import ceviri
    from utils.ai_rapor_ogeleri import analiz_pdf_ogeleri, turkce_deger

    assert turkce_deger("Tamamen-Bilinmeyen Deger") == "Tamamen-Bilinmeyen Deger"  # T8: eşlemesiz değer olduğu gibi
    assert turkce_deger(None) == "—"
    o = analiz_pdf_ogeleri({"result_detail": {"gizemli_alan": 1, "status": "ok"}})
    assert not any("gizemli" in str(x).lower() for x in o)  # bilinmeyen alan adı HAM gösterilmez
    assert ceviri.etkin_dil() == dil
