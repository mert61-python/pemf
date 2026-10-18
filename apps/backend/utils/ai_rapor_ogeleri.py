# -*- coding: utf-8 -*-
# Author: mertaygn
"""AI ANALİZ KAYDI → PDF ÖĞELERİ (ev sahibi paylaşımı, 2026-09-12; okunur Türkçe rapor 2026-10-18).

===============================================================================
NEDEN VAR
===============================================================================
Ev sahibi profili analiz yapıyor ama sonucu veterinerine GÖNDEREMİYORDU: PDF üretimi
yalnız SEANS kayıtları için vardı (`generate_session_report`), AI analizleri için yoktu.

===============================================================================
OKUYUCU: VETERİNER VE HAYVAN SAHİBİ (sahip bildirimi 2026-10-18)
===============================================================================
"raporda ne olduğu anlaşılmıyor çok yapay zeka mühendisi okuyacakmış gibi duruyor. ama veteriner bakmıcak mı ya da kedi
sahibi ona göre tamamen türkçe ve anlaşılır olmalı". Eski sürüm modülün HAM sonuç sözlüğünü döküyordu: `results`,
`top_probability`, `low_confidence`, `xai` anahtarları; İngilizce hastalık / belirti adları ("Eye_Discharge_bin, attribution:
-3,196"). Kural artık:
  * Etiket ve değerler TÜRKÇE (arayüzün `utils/aiDetail.ts` tablolarıyla aynı karşılıklar, sade dil);
  * olası tanılar sıralı ve yüzdeli; "sonucu etkileyen belirtiler" Türkçe adla ve "olasılığı artırdı / azalttı" diye;
  * teknik / iç alanlar (cihaz, kalibrasyon, kimlik, ham dizi, model ayrıntısı) rapora GİRMEZ; bilinmeyen alan HAM gösterilmez
    (sona kısa not: "ayrıntılar uygulamadaki analiz geçmişinde");
  * düşük güven yalnız GERÇEKTEN düşükse uyarı cümlesi olur; sonda "kesin tanı veteriner hekime aittir".

⚠️ SAF FONKSİYON — DB/HTTP/dosya YOK (heterojen gerçek kayıtlarla test edilebilir; bkz. tests/test_ai_analiz_pdf.py).
⚠️ GÖRSEL ALANLARI DIŞARIDA: `result_detail` içinde base64 görseller olabilir.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

#: Rapora ALINMAYACAK alanlar (ad parçası) — base64 görseller ve görsel türevleri. ⚠️ Değer bazlı değil AD bazlı eleme.
GIZLI_ALAN_PARCALARI = (
    "base64",
    "_b64",
    "image",
    "mask",
    "panel",
    "overlay",
    "heatmap",
    "thumbnail",
    "png",
    "jpg",
    "jpeg",
)

#: Tek bir değerin metin karşılığında izin verilen azami uzunluk (kırpılır ama SÖYLENİR).
AZAMI_DEGER_UZUNLUGU = 300

#: İç / teknik alanlar — veteriner ve hayvan sahibi için anlamsız (arayüz `INTERNAL_KEYS` + rapora özgü teknik alanlar).
IC_ALANLAR = frozenset(
    {
        "status",
        "ok",
        "patient_id",
        "message",
        "error",
        "success",
        "legacy",
        "timestamp",
        "id",
        "created_at",
        "module",
        "module_id",
        "input_type",
        "request_id",
        "correlation_id",
        "raw_fgs",
        "raw",
        "action_units",
        "measurements",
        "landmarks",
        "keypoints",
        "points",
        "bbox",
        "boxes",
        "polygon",
        "polygons",
        "contours",
        "segments",
        "vertices",
        "hw_status",
        "hw_params",
        "hw_result",
        "hw_updated",
        "hw_error",
        "hw",
        "hardware",
        "model",
        "model_version",
        "model_name",
        "version",
        "backend",
        "device",
        "engine",
        "inference_ms",
        "elapsed",
        "elapsed_ms",
        "took_ms",
        "latency_ms",
        "duration_ms",
        "shape",
        "dtype",
        "meta",
        "debug",
        "trace",
        "logits",
        "embedding",
        "features",
        "pnp_residual_px",
        "coord_3d_cm",
        "coord_cabin_cm",
        "timing_ms",
        "organ_id",
        "centroid_px",
        "centroid_cabin_mm",
        "area_px",
        "bbox_px",
        "result_E",
        "class_id",
        "bbox_xyxy",
        "bbox_xywh",
        # rapora özgü teknik ayrıntılar
        "calibrated",
        "method",
        "mm_per_px",
        "pixel_mm",
        "coord_frame",
        "pemf_source",
        "source",
        "tumor_id",
        "well_id",
        "n_cancer_pixels",
        "centroid_cabin_cm",
        "cell_area_mean",
        "cell_area_median",
        "score_mean",
        "score_min",
        "E_cancer",
        "E_healthy",
        "E_avg",
        "eField",
        "perCoil",
        "olcum",
        "durum",
        "nokta_gorunurlugu_dogrulanmadi",
        "_xai_istendi",
        "per_well",
        "bulunamadi",
        # ayrı ele alınanlar (aşağıda özel bölümler)
        "top_probability",
        "low_confidence",
        "xai",
        "results",
        "top_k",
        "probabilities",
        "girdi_dogrulama",
    }
)

#: Alan → sade Türkçe etiket.
ETIKETLER = {
    "detected": "Yüz bulundu mu",
    "fgs_total": "Yüz ifadesine göre ağrı skoru (FGS, 0–10)",
    "fgs_score": "Yüz ifadesine göre ağrı skoru (FGS, 0–10)",
    "pain": "Ağrı belirtisi",
    "pain_level": "Ağrı düzeyi",
    "cat_count": "Görüntüdeki kedi sayısı",
    "n_tumor": "Tümör sayısı",
    "n_tumors": "Tümör sayısı",
    "n_wells": "Kuyucuk sayısı",
    "n_cancer": "Kanserli kuyucuk sayısı",
    "n_wells_cancer": "Kanserli kuyucuk sayısı",
    "n_healthy": "Sağlıklı kuyucuk sayısı",
    "n_detections": "Bulgu sayısı",
    "n_organs": "Konumu bulunan organ sayısı",
    "n_patients": "Örnek sayısı",
    "n_masks": "Bulunan bölge sayısı",
    "top_1_class": "Tahmin",
    "top_1_prob": "Olasılık",
    "top_2_class": "İkinci olası sonuç",
    "top_2_prob": "İkinci sonucun olasılığı",
    "top_3_class": "Üçüncü olası sonuç",
    "top_3_prob": "Üçüncü sonucun olasılığı",
    "prediction": "Tahmin",
    "predicted_class": "Tahmin",
    "class_name": "Bulgu türü",
    "disease": "Hastalık",
    "label": "Sonuç",
    "class": "Sınıf",
    "prob": "Olasılık",
    "probability": "Olasılık",
    "prob_pct": "Olasılık (%)",
    "probability_sick": "Hastalık olasılığı",
    "confidence": "Güven",
    "conf": "Güven",
    "grade": "Derece",
    "counts": "Hücre sayımı",
    "class_counts": "Bulgu sayıları",
    "pose_type": "Hayvanın duruşu",
    "area_mm2": "Alan (mm²)",
    "organs": "Organlar",
    "organ": "Organ",
    "organ_name": "Organ",
    "localized": "Konumu belirlendi mi",
    "reliability": "Güvenilirlik",
    "risk": "Risk",
    "risk_level": "Risk düzeyi",
    "stage": "Evre",
    "severity": "Şiddet",
    "recommendation": "Öneri",
    "note": "Not",
    "not": "Not",
    "summary": "Özet",
    "result": "Sonuç",
    "n_cells": "Hücre sayısı",
    "coverage_ratio": "Hücrelerin kapladığı alan oranı",
    "closure": "Yara kapanma ölçümleri",
    "closure_pct": "Yara kapanma oranı (%)",
    "mean_gap_um": "Ortalama yara aralığı (µm)",
    "max_gap_um": "En geniş yara aralığı (µm)",
    "gap_area_mm2": "Açık kalan yara alanı (mm²)",
    "scratch_yonu": "Yara yönü",
    "uyari": "Uyarı",
    "closure_uyari": "Kapanma uyarısı",
    "warnings": "Uyarılar",
    "pemf_valid": "PEMF uygulamasına uygun mu",
    "pemf_gecerli": "PEMF uygulamasına uygun mu",
    "reliable": "Tespit güvenilir mi",
    "surulebilir": "Bobin ayarına esas alınabilir mi",
    "pemf_kapisi": "PEMF uygunluk denetimi",
    "eylem": "Yapılması gereken",
    "cancer_reasons": "Kanser değerlendirmesinin gerekçesi",
    "bulunamadi_mesaji": "Not",
    "tumor_regions": "Tümörlü bölgeler",
    "healthy_regions": "Sağlıklı bölgeler",
    "yon_notu": "Not",
}

#: Bilinen İngilizce / iç değerler → Türkçe (küçük harf anahtar). Arayüz `VALUE_LABELS` + sade açıklamalar.
DEGERLER = {
    "no pain": "Ağrı yok",
    "mild": "Hafif",
    "mild pain": "Hafif ağrı",
    "moderate": "Orta",
    "moderate pain": "Orta ağrı",
    "severe": "Şiddetli",
    "severe pain": "Şiddetli ağrı",
    "normal": "Normal",
    "healthy": "Sağlıklı",
    "sick": "Hasta (riskli)",
    "cancer": "Kanser",
    "abnormal": "Anormal",
    "positive": "Pozitif",
    "negative": "Negatif",
    "unknown": "Bilinmiyor",
    "none": "Yok",
    "yes": "Evet",
    "no": "Hayır",
    "stone": "Taş",
    "cyst": "Kist",
    "tumor": "Tümör",
    "kidney": "Böbrek",
    "happy": "Mutlu",
    "resting": "Dinleniyor",
    "mothercall": "Anne çağrısı",
    "mating": "Çiftleşme çağrısı",
    "huntingmind": "Av modunda",
    "warning": "Uyarı",
    "defence": "Savunma",
    "angry": "Kızgın",
    "fighting": "Kavga",
    "paining": "Ağrı belirtisi",
    "mide": "Mide",
    "bobrek": "Böbrek",
    "karaciger": "Karaciğer",
    "mesane": "Mesane",
    "pankreas": "Pankreas",
    "bagirsak": "Bağırsak",
    "kalp": "Kalp",
    "dalak": "Dalak",
    "akciger_sag": "Akciğer (sağ)",
    "akciger_sol": "Akciğer (sol)",
    "kutu_butun": "Tüm vücut",
    "lateral": "Yandan",
    "sphinx": "Oturmuş (önden)",
    "standing": "Ayakta",
    "dorsal": "Sırtüstü",
    "frontal": "Önden",
    "oblique": "Çapraz açıdan",
    "kidney stone": "Böbrek taşı",
    "kidney cyst": "Böbrek kisti",
    "grade0": "Derece 0",
    "grade1": "Derece 1",
    "grade2": "Derece 2",
    "grade3": "Derece 3",
    "grade4": "Derece 4",
    "kirc": "Böbrek berrak hücreli kanseri (KIRC)",
    "other": "Diğer",
    "ckd": "Kronik böbrek hastalığı (KBH) bulgusu var",
    "notckd": "Kronik böbrek hastalığı bulgusu yok",
    "erythrocyte": "Eritrosit (alyuvar)",
    "punctate reticulocyte": "Noktalı retikülosit (genç alyuvar)",
    "aggregate reticulocyte": "Kümeli retikülosit (genç alyuvar)",
    "conjunctivitis": "Konjonktivit (göz nezlesi)",
    "feline asthma": "Kedi astımı",
    "feline calicivirus": "Kedi kalisivirüs enfeksiyonu",
    "feline chlamydiosis": "Kedi klamidyozu",
    "feline herpesvirus": "Kedi herpes virüs enfeksiyonu",
    "feline immunodeficiency virus": "Kedi bağışıklık yetmezliği virüsü (FIV)",
    "feline infectious peritonitis": "Kedi enfeksiyöz peritoniti (FIP)",
    "feline leukemia virus": "Kedi lösemi virüsü (FeLV)",
    "feline panleukopenia": "Kedi panlökopenisi (kedi gençlik hastalığı)",
    "feline renal disease": "Kedi böbrek hastalığı",
    "fungal infection": "Mantar enfeksiyonu",
    "gastroenteritis": "Gastroenterit (mide-bağırsak iltihabı)",
    "hyperthyroidism": "Hipertiroidizm (tiroid bezi aşırı çalışması)",
    "inflammatory bowel disease": "İnflamatuvar bağırsak hastalığı (IBD)",
    "intestinal parasites": "Bağırsak parazitleri",
    "pancreatitis": "Pankreatit (pankreas iltihabı)",
    "ringworm": "Saçkıran (deri mantarı, dermatofitoz)",
    "upper respiratory infection": "Üst solunum yolu enfeksiyonu",
}

#: Hastalık modelinin girdi belirtileri → sade Türkçe (arayüz `DISEASE_FEATURE_TR`).
BELIRTILER = {
    "Age": "Yaş",
    "Weight": "Kilo",
    "Heart_Rate": "Nabız",
    "Body_Temperature": "Vücut ısısı (ateş)",
    "Duration_days": "Şikâyetin süresi",
    "Appetite_Loss_bin": "İştahsızlık",
    "Vomiting_bin": "Kusma",
    "Diarrhea_bin": "İshal",
    "Coughing_bin": "Öksürük",
    "Labored_Breathing_bin": "Zor nefes alma",
    "Lameness_bin": "Topallama",
    "Skin_Lesions_bin": "Deride yara / lezyon",
    "Nasal_Discharge_bin": "Burun akıntısı",
    "Eye_Discharge_bin": "Göz akıntısı",
    "has_Lethargy": "Halsizlik",
    "has_Weight_Loss": "Kilo kaybı",
    "has_Sneezing": "Hapşırma",
    "has_Dehydration": "Susuz kalma",
    "has_Fever": "Ateş",
}

#: Olasılık taşıyan alanlar (0–1 ise yüzde olarak yazılır).
OLASILIK_ALANLARI = frozenset(
    {"prob", "probability", "probability_sick", "top_1_prob", "top_2_prob", "top_3_prob", "confidence", "conf", "score"}
)
_AD_ALANLARI = (
    "disease",
    "class_name",
    "class",
    "label",
    "name",
    "organ_name",
    "organ",
    "prediction",
    "predicted_class",
)
_OLASILIK_SIRASI = ("probability", "prob", "confidence", "conf", "score")
_AYLAR = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")

#: Rapor sonundaki sabit not (okuyucu: hayvan sahibi + veteriner).
KESIN_TANI_NOTU = (
    "Bu rapor yapay zekâ ile hazırlanmış bir ön değerlendirmedir. Kesin tanı ve tedavi kararını veteriner hekim verir."
)
EKSIK_ALAN_NOTU = "Bazı teknik ölçümler bu rapora alınmadı; tamamı uygulamadaki analiz geçmişinde görülebilir."
DUSUK_GUVEN_NOTU = (
    "Yapay zekânın bu sonuca güveni düşük. Sonucu tek başına kullanmayın; mutlaka veteriner hekiminize danışın."
)


def _gizli_mi(anahtar: str) -> bool:
    a = str(anahtar).lower()
    return str(anahtar) in IC_ALANLAR or any(p in a for p in GIZLI_ALAN_PARCALARI)


def turkce_deger(v: Any) -> str:
    """Bilinen İngilizce / iç değeri Türkçeye çevir; bilinmiyorsa aynen."""
    s = str(v if v is not None else "").strip()
    return DEGERLER.get(s.lower(), s) if s else "—"


def _sayi(v: float, basamak: int = 2) -> str:
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return "—"
    if float(v).is_integer():
        return str(int(v))
    return f"{v:.{basamak}f}".rstrip("0").rstrip(",.").replace(".", ",")


def _yuzde(p: Any) -> str | None:
    """0–1 arası olasılık → "%78"; 1–100 arası zaten yüzde ise o; değilse None."""
    if isinstance(p, bool) or not isinstance(p, (int, float)) or math.isnan(float(p)):
        return None
    p = float(p)
    if 0.0 <= p <= 1.0:
        p *= 100.0
    if not 0.0 <= p <= 100.0:
        return None
    return f"%{round(p)}" if p >= 1 or p == 0 else "%1'in altında"


def _metne_cevir(deger: Any, anahtar: str = "") -> str:
    """Bir değeri okunur tek satıra çevirir (uzunsa KIRPAR ama SÖYLER). İç içe sözlükte bilinmeyen alt alan ATLANIR."""
    if isinstance(deger, bool):
        return "Evet" if deger else "Hayır"
    if isinstance(deger, (int, float)):
        if anahtar in OLASILIK_ALANLARI:
            y = _yuzde(deger)
            if y:
                return y
        return _sayi(deger)
    if isinstance(deger, (list, tuple)):
        if not deger:
            return "—"
        parcalar = [_metne_cevir(x) for x in deger[:8] if not isinstance(x, (dict, list, tuple))]
        if not parcalar:
            return f"{len(deger)} kayıt"
        kuyruk = f" … ({len(deger)} öğe)" if len(deger) > 8 else ""
        return ", ".join(parcalar) + kuyruk
    if isinstance(deger, dict):
        ic = []
        for k, v in list(deger.items())[:12]:
            if _gizli_mi(k) or isinstance(v, (dict, list, tuple)):
                continue
            etiket = ETIKETLER.get(str(k)) or (DEGERLER.get(str(k).lower()) if str(k).lower() in DEGERLER else None)
            if not etiket:
                continue
            ic.append(f"{etiket}: {_metne_cevir(v, str(k))}")
        return ("; ".join(ic) or "—")[:AZAMI_DEGER_UZUNLUGU]
    s = turkce_deger(deger)
    if len(s) > AZAMI_DEGER_UZUNLUGU:
        return s[:AZAMI_DEGER_UZUNLUGU] + f"… (toplam {len(s)} karakter)"
    return s


def _tarih(v: Any) -> str:
    """ISO tarih → "13 Ekim 2026, 19:45"; çözülemezse aynen."""
    s = str(v or "").strip()
    if not s:
        return "—"
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return s
    return f"{t.day} {_AYLAR[t.month - 1]} {t.year}, {t:%H:%M}"


def _olasi_sonuclar(liste: Any) -> list[str]:
    """[{disease/class…, probability/prob…}, …] → ["Konjonktivit (göz nezlesi) — %78", …] (olasılık sırasıyla)."""
    satirlar = []
    if not isinstance(liste, (list, tuple)):
        return satirlar
    ogeler = []
    for o in liste:
        if not isinstance(o, dict):
            continue
        ad = next((o[k] for k in _AD_ALANLARI if isinstance(o.get(k), str) and o.get(k)), None)
        p = next(
            (o[k] for k in _OLASILIK_SIRASI if isinstance(o.get(k), (int, float)) and not isinstance(o.get(k), bool)),
            None,
        )
        if ad is None:
            continue
        ogeler.append((float(p) if p is not None else -1.0, turkce_deger(ad), _yuzde(p) if p is not None else None))
    ogeler.sort(key=lambda x: x[0], reverse=True)
    for i, (_p, ad, y) in enumerate(ogeler[:5], 1):
        satirlar.append(f"{i}. {ad}" + (f" — {y}" if y else ""))
    return satirlar


def _etkileyen_belirtiler(xai: Any) -> list[str]:
    """XAI `top_features` → "Göz akıntısı: güçlü etki — bu tanının olasılığını azalttı" (en çok 5)."""
    if not isinstance(xai, dict):
        return []
    ozellikler = [
        f
        for f in (xai.get("top_features") or [])
        if isinstance(f, dict) and isinstance(f.get("attribution"), (int, float)) and f.get("feature")
    ]
    if not ozellikler:
        return []
    en_buyuk = max(abs(float(f["attribution"])) for f in ozellikler) or 1.0
    satirlar = []
    for f in ozellikler[:5]:
        a = float(f["attribution"])
        oran = abs(a) / en_buyuk
        guc = "güçlü etki" if oran >= 0.66 else ("orta etki" if oran >= 0.33 else "zayıf etki")
        yon = "bu tanının olasılığını artırdı" if a >= 0 else "bu tanının olasılığını azalttı"
        ad = BELIRTILER.get(str(f["feature"]))
        if not ad:
            continue  # bilinmeyen model girdisi adı HAM yazılmaz
        satirlar.append(f"{ad}: {guc} — {yon}")
    return satirlar


def analiz_pdf_ogeleri(kayit: dict) -> list[dict]:
    """Bir AI analiz kaydını `generate_xai_report`ın beklediği öğe listesine çevirir (okuyucu: veteriner + hayvan sahibi).

    Öğe: {"etiket": str, "aciklama": str} ya da çok satırlı bölüm için {"etiket": str, "satirlar": [str, …]}.
    ⚠️ ÜST BİLGİ ÖNCE: hasta, tarih, analiz, sonuç ve güven — raporu açan önce "kim, ne zaman, ne çıktı" görmeli.
    """
    ogeler: list[dict] = []

    def ekle(etiket: str, deger: Any, anahtar: str = "") -> None:
        metin = _metne_cevir(deger, anahtar)
        if metin and metin != "—":
            ogeler.append({"etiket": etiket, "aciklama": metin})

    def bolum(etiket: str, satirlar: list[str], aciklama: str = "") -> None:
        if satirlar:
            o = {"etiket": etiket, "satirlar": satirlar}
            if aciklama:
                o["aciklama"] = aciklama
            ogeler.append(o)

    ekle("Hasta", kayit.get("patient_name"))
    tarih = _tarih(kayit.get("created_at"))
    if tarih != "—":
        ogeler.append({"etiket": "Analiz tarihi", "aciklama": tarih})
    ekle("Analiz türü", kayit.get("module_label") or kayit.get("module_id"))
    ekle("Sonuç", kayit.get("result_summary"))
    g = kayit.get("confidence")
    if isinstance(g, (int, float)) and not isinstance(g, bool) and _yuzde(g):
        ogeler.append(
            {
                "etiket": "Yapay zekânın bu sonuca güveni",
                "aciklama": f"{_yuzde(g)} — modelin kendi tahminine ne kadar güvendiğini gösterir; kesin tanı değildir.",
            }
        )

    detay = kayit.get("result_detail")
    atlanan = 0
    if isinstance(detay, dict):
        if detay.get("low_confidence") is True:
            ogeler.append({"etiket": "Dikkat", "aciklama": DUSUK_GUVEN_NOTU})
        bolum(
            "Olası tanılar (olasılık sırasıyla)",
            _olasi_sonuclar(detay.get("results") or detay.get("top_k") or detay.get("probabilities")),
        )
        bolum(
            "Sonucu en çok etkileyen belirtiler",
            _etkileyen_belirtiler(detay.get("xai")),
            "Yapay zekânın bu sonuca varırken en çok dikkate aldığı bilgiler. Belirtinin hayvanda bulunması ya da "
            "bulunmaması sonucu bu yönde etkiledi.",
        )
        gd = detay.get("girdi_dogrulama")
        if isinstance(gd, dict):
            if gd.get("dogrulandi") is True:
                ogeler.append(
                    {"etiket": "Görüntü kontrolü", "aciklama": "Görüntü termal kamera görüntüsü olarak doğrulandı."}
                )
            elif isinstance(gd.get("uyari"), str) and gd["uyari"]:
                ogeler.append({"etiket": "Görüntü kontrolü", "aciklama": gd["uyari"]})
            if isinstance(gd.get("yon_notu"), str) and gd["yon_notu"]:
                ogeler.append({"etiket": "Not", "aciklama": gd["yon_notu"]})
        tahmin = detay.get("prediction")
        if isinstance(tahmin, dict):
            if tahmin.get("label"):
                ekle("Tahmin", tahmin.get("label"))
            ps = tahmin.get("probability_sick")
            if isinstance(ps, (int, float)) and not isinstance(ps, bool):
                ekle("Hastalık olasılığı", ps, "probability_sick")
        for anahtar, deger in detay.items():
            if _gizli_mi(anahtar) or (anahtar == "prediction" and isinstance(deger, dict)):
                continue
            etiket = ETIKETLER.get(str(anahtar))
            if not etiket:
                atlanan += 1  # bilinmeyen alan adı HAM gösterilmez (okuyucu: veteriner / hayvan sahibi)
                continue
            ekle(etiket, deger, str(anahtar))

    # ⚠️ HEKİM DEĞERLENDİRMESİ EN SONDA ve AYRI: AI çıktısı öneridir, klinik karar hekimindir.
    ekle("Veteriner hekim değerlendirmesi", kayit.get("review_note") or kayit.get("vet_review"))
    if atlanan:
        ogeler.append({"etiket": "Not", "aciklama": EKSIK_ALAN_NOTU})
    ogeler.append({"etiket": "Önemli", "aciklama": KESIN_TANI_NOTU})
    return ogeler
