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

from utils import ceviri

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

#: Alan → sade etiket (katalog ANAHTARI `ai.etiket.*`; metin istek dilinde — I18N-P1, K-7: arayüzle ortak kimlikte aynı İngilizce).
ETIKETLER = {
    "detected": "ai.etiket.detected",
    "fgs_total": "ai.etiket.fgs_total",
    "fgs_score": "ai.etiket.fgs_score",
    "pain": "ai.etiket.pain",
    "pain_level": "ai.etiket.pain_level",
    "cat_count": "ai.etiket.cat_count",
    "n_tumor": "ai.etiket.n_tumor",
    "n_tumors": "ai.etiket.n_tumors",
    "n_wells": "ai.etiket.n_wells",
    "n_cancer": "ai.etiket.n_cancer",
    "n_wells_cancer": "ai.etiket.n_wells_cancer",
    "n_healthy": "ai.etiket.n_healthy",
    "n_detections": "ai.etiket.n_detections",
    "n_organs": "ai.etiket.n_organs",
    "n_patients": "ai.etiket.n_patients",
    "n_masks": "ai.etiket.n_masks",
    "top_1_class": "ai.etiket.top_1_class",
    "top_1_prob": "ai.etiket.top_1_prob",
    "top_2_class": "ai.etiket.top_2_class",
    "top_2_prob": "ai.etiket.top_2_prob",
    "top_3_class": "ai.etiket.top_3_class",
    "top_3_prob": "ai.etiket.top_3_prob",
    "prediction": "ai.etiket.prediction",
    "predicted_class": "ai.etiket.predicted_class",
    "class_name": "ai.etiket.class_name",
    "disease": "ai.etiket.disease",
    "label": "ai.etiket.label",
    "class": "ai.etiket.class",
    "prob": "ai.etiket.prob",
    "probability": "ai.etiket.probability",
    "prob_pct": "ai.etiket.prob_pct",
    "probability_sick": "ai.etiket.probability_sick",
    "confidence": "ai.etiket.confidence",
    "conf": "ai.etiket.conf",
    "grade": "ai.etiket.grade",
    "counts": "ai.etiket.counts",
    "class_counts": "ai.etiket.class_counts",
    "pose_type": "ai.etiket.pose_type",
    "area_mm2": "ai.etiket.area_mm2",
    "organs": "ai.etiket.organs",
    "organ": "ai.etiket.organ",
    "organ_name": "ai.etiket.organ_name",
    "localized": "ai.etiket.localized",
    "reliability": "ai.etiket.reliability",
    "risk": "ai.etiket.risk",
    "risk_level": "ai.etiket.risk_level",
    "stage": "ai.etiket.stage",
    "severity": "ai.etiket.severity",
    "recommendation": "ai.etiket.recommendation",
    "note": "ai.etiket.note",
    "not": "ai.etiket.not",
    "summary": "ai.etiket.summary",
    "result": "ai.etiket.result",
    "n_cells": "ai.etiket.n_cells",
    "coverage_ratio": "ai.etiket.coverage_ratio",
    "closure": "ai.etiket.closure",
    "closure_pct": "ai.etiket.closure_pct",
    "mean_gap_um": "ai.etiket.mean_gap_um",
    "max_gap_um": "ai.etiket.max_gap_um",
    "gap_area_mm2": "ai.etiket.gap_area_mm2",
    "scratch_yonu": "ai.etiket.scratch_yonu",
    "uyari": "ai.etiket.uyari",
    "closure_uyari": "ai.etiket.closure_uyari",
    "warnings": "ai.etiket.warnings",
    "pemf_valid": "ai.etiket.pemf_valid",
    "pemf_gecerli": "ai.etiket.pemf_gecerli",
    "reliable": "ai.etiket.reliable",
    "surulebilir": "ai.etiket.surulebilir",
    "pemf_kapisi": "ai.etiket.pemf_kapisi",
    "eylem": "ai.etiket.eylem",
    "cancer_reasons": "ai.etiket.cancer_reasons",
    "bulunamadi_mesaji": "ai.etiket.bulunamadi_mesaji",
    "tumor_regions": "ai.etiket.tumor_regions",
    "healthy_regions": "ai.etiket.healthy_regions",
    "yon_notu": "ai.etiket.yon_notu",
}

#: Bilinen İngilizce / iç değerler → okunur metin (küçük harf anahtar; katalog ANAHTARI `ai.deger.*`). Arayüz `VALUE_LABELS` + sade açıklamalar.
DEGERLER = {
    # I18NI-A1.7: yüz bulunamayınca `pain_level` VERİSİ (ai_router Türkçe sabit) — PDF'te istek dilinde
    "kedi yüzü tespit edilemedi": "ai.deger.kediYuzuYok",
    "no pain": "ai.deger.no_pain",
    "mild": "ai.deger.mild",
    "mild pain": "ai.deger.mild_pain",
    "moderate": "ai.deger.moderate",
    "moderate pain": "ai.deger.moderate_pain",
    "severe": "ai.deger.severe",
    "severe pain": "ai.deger.severe_pain",
    "normal": "ai.deger.normal",
    "healthy": "ai.deger.healthy",
    "sick": "ai.deger.sick",
    "cancer": "ai.deger.cancer",
    "abnormal": "ai.deger.abnormal",
    "positive": "ai.deger.positive",
    "negative": "ai.deger.negative",
    "unknown": "ai.deger.unknown",
    "none": "ai.deger.none",
    "yes": "ai.deger.yes",
    "no": "ai.deger.no",
    "stone": "ai.deger.stone",
    "cyst": "ai.deger.cyst",
    "tumor": "ai.deger.tumor",
    "kidney": "ai.deger.kidney",
    "happy": "ai.deger.happy",
    "resting": "ai.deger.resting",
    "mothercall": "ai.deger.mothercall",
    "mating": "ai.deger.mating",
    "huntingmind": "ai.deger.huntingmind",
    "warning": "ai.deger.warning",
    "defence": "ai.deger.defence",
    "angry": "ai.deger.angry",
    "fighting": "ai.deger.fighting",
    "paining": "ai.deger.paining",
    "mide": "ai.deger.mide",
    "bobrek": "ai.deger.bobrek",
    "karaciger": "ai.deger.karaciger",
    "mesane": "ai.deger.mesane",
    "pankreas": "ai.deger.pankreas",
    "bagirsak": "ai.deger.bagirsak",
    "kalp": "ai.deger.kalp",
    "dalak": "ai.deger.dalak",
    "akciger_sag": "ai.deger.akciger_sag",
    "akciger_sol": "ai.deger.akciger_sol",
    "kutu_butun": "ai.deger.kutu_butun",
    "lateral": "ai.deger.lateral",
    "sphinx": "ai.deger.sphinx",
    "standing": "ai.deger.standing",
    "dorsal": "ai.deger.dorsal",
    "frontal": "ai.deger.frontal",
    "oblique": "ai.deger.oblique",
    "kidney stone": "ai.deger.kidney_stone",
    "kidney cyst": "ai.deger.kidney_cyst",
    "grade0": "ai.deger.grade0",
    "grade1": "ai.deger.grade1",
    "grade2": "ai.deger.grade2",
    "grade3": "ai.deger.grade3",
    "grade4": "ai.deger.grade4",
    "kirc": "ai.deger.kirc",
    "other": "ai.deger.other",
    "ckd": "ai.deger.ckd",
    "notckd": "ai.deger.notckd",
    "erythrocyte": "ai.deger.erythrocyte",
    "punctate reticulocyte": "ai.deger.punctate_reticulocyte",
    "aggregate reticulocyte": "ai.deger.aggregate_reticulocyte",
    "conjunctivitis": "ai.deger.conjunctivitis",
    "feline asthma": "ai.deger.feline_asthma",
    "feline calicivirus": "ai.deger.feline_calicivirus",
    "feline chlamydiosis": "ai.deger.feline_chlamydiosis",
    "feline herpesvirus": "ai.deger.feline_herpesvirus",
    "feline immunodeficiency virus": "ai.deger.feline_immunodeficiency_virus",
    "feline infectious peritonitis": "ai.deger.feline_infectious_peritonitis",
    "feline leukemia virus": "ai.deger.feline_leukemia_virus",
    "feline panleukopenia": "ai.deger.feline_panleukopenia",
    "feline renal disease": "ai.deger.feline_renal_disease",
    "fungal infection": "ai.deger.fungal_infection",
    "gastroenteritis": "ai.deger.gastroenteritis",
    "hyperthyroidism": "ai.deger.hyperthyroidism",
    "inflammatory bowel disease": "ai.deger.inflammatory_bowel_disease",
    "intestinal parasites": "ai.deger.intestinal_parasites",
    "pancreatitis": "ai.deger.pancreatitis",
    "ringworm": "ai.deger.ringworm",
    "upper respiratory infection": "ai.deger.upper_respiratory_infection",
}

#: Hastalık modelinin girdi belirtileri → sade ad (katalog ANAHTARI `ai.belirti.*`; arayüz `DISEASE_FEATURE_TR`).
BELIRTILER = {
    "Age": "ai.belirti.Age",
    "Weight": "ai.belirti.Weight",
    "Heart_Rate": "ai.belirti.Heart_Rate",
    "Body_Temperature": "ai.belirti.Body_Temperature",
    "Duration_days": "ai.belirti.Duration_days",
    "Appetite_Loss_bin": "ai.belirti.Appetite_Loss_bin",
    "Vomiting_bin": "ai.belirti.Vomiting_bin",
    "Diarrhea_bin": "ai.belirti.Diarrhea_bin",
    "Coughing_bin": "ai.belirti.Coughing_bin",
    "Labored_Breathing_bin": "ai.belirti.Labored_Breathing_bin",
    "Lameness_bin": "ai.belirti.Lameness_bin",
    "Skin_Lesions_bin": "ai.belirti.Skin_Lesions_bin",
    "Nasal_Discharge_bin": "ai.belirti.Nasal_Discharge_bin",
    "Eye_Discharge_bin": "ai.belirti.Eye_Discharge_bin",
    "has_Lethargy": "ai.belirti.has_Lethargy",
    "has_Weight_Loss": "ai.belirti.has_Weight_Loss",
    "has_Sneezing": "ai.belirti.has_Sneezing",
    "has_Dehydration": "ai.belirti.has_Dehydration",
    "has_Fever": "ai.belirti.has_Fever",
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


#: Rapor sonundaki sabit not (okuyucu: hayvan sahibi + veteriner) — istek dilinde.
def kesin_tani_notu() -> str:
    return ceviri.t("ai.rapor.kesinTani")


def eksik_alan_notu() -> str:
    return ceviri.t("ai.rapor.eksikAlan")


def dusuk_guven_notu() -> str:
    return ceviri.t("ai.rapor.dusukGuven")


def _gizli_mi(anahtar: str) -> bool:
    a = str(anahtar).lower()
    return str(anahtar) in IC_ALANLAR or any(p in a for p in GIZLI_ALAN_PARCALARI)


def turkce_deger(v: Any) -> str:
    """Bilinen İngilizce / iç değeri Türkçeye çevir; bilinmiyorsa aynen."""
    s = str(v if v is not None else "").strip()
    if not s:
        return "—"
    deger_anahtari = DEGERLER.get(s.lower())
    return ceviri.t(deger_anahtari) if deger_anahtari else s


def _sayi(v: float, basamak: int = 2) -> str:
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return "—"
    if float(v).is_integer():
        return str(int(v))
    return f"{v:.{basamak}f}".rstrip("0").rstrip(",.").replace(".", "," if ceviri.etkin_dil() == "tr" else ".")


def _yuzde(p: Any) -> str | None:
    """0–1 arası olasılık → "%78"; 1–100 arası zaten yüzde ise o; değilse None."""
    if isinstance(p, bool) or not isinstance(p, (int, float)) or math.isnan(float(p)):
        return None
    p = float(p)
    if 0.0 <= p <= 1.0:
        p *= 100.0
    if not 0.0 <= p <= 100.0:
        return None
    return ceviri.t("ai.rapor.yuzde", deger=round(p)) if p >= 1 or p == 0 else ceviri.t("ai.rapor.yuzdeAlti")


def _metne_cevir(deger: Any, anahtar: str = "") -> str:
    """Bir değeri okunur tek satıra çevirir (uzunsa KIRPAR ama SÖYLER). İç içe sözlükte bilinmeyen alt alan ATLANIR."""
    if isinstance(deger, bool):
        return ceviri.t("ai.rapor.evet") if deger else ceviri.t("ai.rapor.hayir")
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
            return ceviri.t("ai.rapor.kayit", count=len(deger))
        kuyruk = ceviri.t("ai.rapor.kuyruk", count=len(deger)) if len(deger) > 8 else ""
        return ", ".join(parcalar) + kuyruk
    if isinstance(deger, dict):
        ic = []
        for k, v in list(deger.items())[:12]:
            if _gizli_mi(k) or isinstance(v, (dict, list, tuple)):
                continue
            etiket_anahtari = ETIKETLER.get(str(k)) or (
                DEGERLER.get(str(k).lower()) if str(k).lower() in DEGERLER else None
            )
            if not etiket_anahtari:
                continue
            ic.append(f"{ceviri.t(etiket_anahtari)}: {_metne_cevir(v, str(k))}")
        return ("; ".join(ic) or "—")[:AZAMI_DEGER_UZUNLUGU]
    s = turkce_deger(deger)
    if len(s) > AZAMI_DEGER_UZUNLUGU:
        return s[:AZAMI_DEGER_UZUNLUGU] + ceviri.t("ai.rapor.kirpildi", n=len(s))
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
    return ceviri.tarih_metni(t)


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
        guc = (
            ceviri.t("ai.rapor.gucluEtki")
            if oran >= 0.66
            else (ceviri.t("ai.rapor.ortaEtki") if oran >= 0.33 else ceviri.t("ai.rapor.zayifEtki"))
        )
        yon = ceviri.t("ai.rapor.yonArtirdi") if a >= 0 else ceviri.t("ai.rapor.yonAzaltti")
        belirti_anahtari = BELIRTILER.get(str(f["feature"]))
        if not belirti_anahtari:
            continue  # bilinmeyen model girdisi adı HAM yazılmaz
        satirlar.append(ceviri.t("ai.rapor.etkiSatiri", ad=ceviri.t(belirti_anahtari), guc=guc, yon=yon))
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

    ekle(ceviri.t("ai.rapor.hasta"), kayit.get("patient_name"))
    tarih = _tarih(kayit.get("created_at"))
    if tarih != "—":
        ogeler.append({"etiket": ceviri.t("ai.rapor.analizTarihi"), "aciklama": tarih})
    ekle(ceviri.t("ai.rapor.analizTuru"), kayit.get("module_label") or kayit.get("module_id"))
    ekle(ceviri.t("ai.rapor.sonuc"), kayit.get("result_summary"))
    g = kayit.get("confidence")
    if isinstance(g, (int, float)) and not isinstance(g, bool) and _yuzde(g):
        ogeler.append(
            {
                "etiket": ceviri.t("ai.rapor.guven"),
                "aciklama": ceviri.t("ai.rapor.guvenAciklama", yuzde=_yuzde(g)),
            }
        )

    detay = kayit.get("result_detail")
    atlanan = 0
    if isinstance(detay, dict):
        if detay.get("low_confidence") is True:
            ogeler.append({"etiket": ceviri.t("ai.rapor.dikkat"), "aciklama": dusuk_guven_notu()})
        bolum(
            ceviri.t("ai.rapor.olasiTanilar"),
            _olasi_sonuclar(detay.get("results") or detay.get("top_k") or detay.get("probabilities")),
        )
        bolum(
            ceviri.t("ai.rapor.etkileyenBelirtiler"),
            _etkileyen_belirtiler(detay.get("xai")),
            ceviri.t("ai.rapor.etkileyenAciklama"),
        )
        gd = detay.get("girdi_dogrulama")
        if isinstance(gd, dict):
            if gd.get("dogrulandi") is True:
                ogeler.append(
                    {"etiket": ceviri.t("ai.rapor.goruntuKontrolu"), "aciklama": ceviri.t("ai.rapor.termalDogrulandi")}
                )
            elif isinstance(gd.get("uyari"), str) and gd["uyari"]:
                ogeler.append({"etiket": ceviri.t("ai.rapor.goruntuKontrolu"), "aciklama": gd["uyari"]})
            if isinstance(gd.get("yon_notu"), str) and gd["yon_notu"]:
                ogeler.append({"etiket": ceviri.t("ai.rapor.not"), "aciklama": gd["yon_notu"]})
        tahmin = detay.get("prediction")
        if isinstance(tahmin, dict):
            if tahmin.get("label"):
                ekle(ceviri.t("ai.rapor.tahmin"), tahmin.get("label"))
            ps = tahmin.get("probability_sick")
            if isinstance(ps, (int, float)) and not isinstance(ps, bool):
                ekle(ceviri.t("ai.rapor.hastalikOlasiligi"), ps, "probability_sick")
        for anahtar, deger in detay.items():
            if _gizli_mi(anahtar) or (anahtar == "prediction" and isinstance(deger, dict)):
                continue
            etiket_anahtari = ETIKETLER.get(str(anahtar))
            if not etiket_anahtari:
                atlanan += 1  # bilinmeyen alan adı HAM gösterilmez (okuyucu: veteriner / hayvan sahibi)
                continue
            ekle(ceviri.t(etiket_anahtari), deger, str(anahtar))

    # ⚠️ HEKİM DEĞERLENDİRMESİ EN SONDA ve AYRI: AI çıktısı öneridir, klinik karar hekimindir.
    ekle(ceviri.t("ai.rapor.vetDegerlendirme"), kayit.get("review_note") or kayit.get("vet_review"))
    if atlanan:
        ogeler.append({"etiket": ceviri.t("ai.rapor.not"), "aciklama": eksik_alan_notu()})
    ogeler.append({"etiket": ceviri.t("ai.rapor.onemli"), "aciklama": kesin_tani_notu()})
    return ogeler
