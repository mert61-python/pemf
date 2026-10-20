import i18n from "i18next";
// Author: mertaygn, cglrgrkn
// AI analiz sonuç-detayı için PAYLAŞILAN yardımcılar — TEK KAYNAK (config/access.ts prensibi).
// Yazma tarafı (cleanDetail) ile okuma/gösterim tarafı (detailRows) aynı gizli-anahtar + Türkçe
// etiket + değer-çeviri setini kullanır → iki dosyada kopyalanmaz, drift olmaz.
//
// Amaç: AI Analiz Geçmişi detayları TEMİZ + Türkçe + kullanıcı-dostu olsun — ham İngilizce anahtar,
// teknik iç-alan (raw_fgs/action_units/hw_*) ve "[object Object]" ASLA gösterilmez.

/** String uzunluk eşikleri (adlandırılmış sabitler — magic-number yok). */
export const STRIP_STRING_LEN = 600; // yazma: bu uzunluğun üstündeki string SAKLANMAZ (blob)
export const DISPLAY_STRING_LEN = 400; // gösterim: bu uzunluğun üstündeki string satırı ATLANIR
export const VALUE_TRUNC_LEN = 140; // gösterim: değer bu uzunlukta kırpılır

/** Görsel/binary anahtar mı (base64, image, overlay, mask, bytes...). Geçmişe yazılmaz/gösterilmez. */
export function isHeavyKey(k: string): boolean {
  return /base64|image|overlay|mask|thumbnail|_b64|bytes|heatmap|figure|plot|png|jpe?g/i.test(k);
}

/**
 * İçsel/teknik/ham anahtarlar — kullanıcıya anlamsız; SAKLANMAZ + GÖSTERİLMEZ.
 * (raw_fgs/action_units/measurements = ham FGS iç-verisi; hw_* = donanım; model/inference = teknik.)
 */
export const INTERNAL_KEYS = new Set([
  // genel iç alanlar
  "status", "ok", "patient_id", "message", "error", "success", "legacy", "timestamp",
  "id", "created_at", "module", "module_id", "input_type", "request_id", "correlation_id",
  // ham / iç-içe teknik AI çıktıları (bunlar "[object Object]" veya anlamsız dökülüyordu)
  "raw_fgs", "raw", "action_units", "measurements", "landmarks", "keypoints", "points",
  "bbox", "boxes", "polygon", "polygons", "contours", "segments", "vertices",
  // donanım alanları (analiz geçmişinde alakasız)
  "hw_status", "hw_params", "hw_result", "hw_updated", "hw_error", "hw", "hardware",
  // model / çalışma-zamanı teknikleri
  "model", "model_version", "model_name", "version", "backend", "device", "engine",
  "inference_ms", "elapsed", "elapsed_ms", "took_ms", "latency_ms", "duration_ms",
  "shape", "dtype", "meta", "debug", "trace", "logits", "embedding", "features",
  // AI model ham/teknik çıktıları (kapsamlı denetim 2026-07-28 — koordinat/bbox/em_kedi ham dizileri):
  "pnp_residual_px", "coord_3d_cm", "coord_cabin_cm", "timing_ms", "organ_id", "centroid_px",
  "centroid_cabin_mm", "area_px", "bbox_px", "result_E", "class_id", "bbox_xyxy", "bbox_xywh",
  "D", "P", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "P1", "P2", "P3", "P4", "P5", "P6", "P7",
]);

/**
 * Katalog metni. Tablo DEĞERLERİ katalog ANAHTARIDIR (KURALLAR §4.5; kapalı küme — K-3 izni). `lng` verilirse O dilde (VERİ yolu: kayda / özete
 * giden metin arayüz dili EN olsa da TR kalır), verilmezse arayüz dilinde (EKRAN).
 */
const katalogMetni = (anahtar: string, lng?: "tr"): string => i18n.t(anahtar as never, lng ? { lng } : {}) as string;

/** Sonuç anahtarları → etiket KATALOG ANAHTARI (bilinmeyen anahtar VALUE_LABELS'a, o da yoksa ham gösterilir). */
export const DETAIL_LABELS: Record<string, string> = {
  detected: "ai.etiket.detected",
  fgs_total: "ai.etiket.fgs_total", fgs_score: "ai.etiket.fgs_score",
  pain: "ai.etiket.pain", pain_level: "ai.etiket.pain_level",
  // D1.E09 (1-D inceleme i3-F-8): landmark modeli nokta görünürlüğünü bildirmiyor (örtülü yüzde skor yanıltıcı olabilir).
  nokta_gorunurlugu_dogrulanmadi: "ai.etiket.nokta_gorunurlugu_dogrulanmadi",
  n_tumor: "ai.etiket.n_tumor", n_wells: "ai.etiket.n_wells", n_cancer: "ai.etiket.n_cancer", n_healthy: "ai.etiket.n_healthy",
  n_wells_cancer: "ai.etiket.n_wells_cancer", n_detections: "ai.etiket.n_detections", n_organs: "ai.etiket.n_organs",
  n_patients: "ai.etiket.n_patients", n_masks: "ai.etiket.n_masks", cat_count: "ai.etiket.cat_count",
  E_cancer: "ai.etiket.E_cancer", E_healthy: "ai.etiket.E_healthy",
  top_1_class: "ai.etiket.top_1_class", top_1_prob: "ai.etiket.top_1_prob", top_2_class: "ai.etiket.top_2_class", top_2_prob: "ai.etiket.top_2_prob",
  top_3_class: "ai.etiket.top_3_class", top_3_prob: "ai.etiket.top_3_prob",
  prediction: "ai.etiket.prediction", disease: "ai.etiket.disease", label: "ai.etiket.label", class: "ai.etiket.class",
  prob: "ai.etiket.prob", probability: "ai.etiket.probability", prob_pct: "ai.etiket.prob_pct", confidence: "ai.etiket.confidence",
  grade: "ai.etiket.grade", counts: "ai.etiket.counts", class_counts: "ai.etiket.class_counts",
  pose_type: "ai.etiket.pose_type", area_mm2: "ai.etiket.area_mm2", area: "ai.etiket.area",
  organs: "ai.etiket.organs", tumors: "ai.etiket.tumors", wells: "ai.etiket.wells", detections: "ai.etiket.detections",
  reliability: "ai.etiket.reliability", localized: "ai.etiket.localized", organ: "ai.etiket.organ", organ_name: "ai.etiket.organ_name",
  risk: "ai.etiket.risk", risk_level: "ai.etiket.risk_level", stage: "ai.etiket.stage", severity: "ai.etiket.severity",
  recommendation: "ai.etiket.recommendation", note: "ai.etiket.note", summary: "ai.etiket.summary", result: "ai.etiket.result",
  // Kapsamlı AI-model denetimi (2026-07-28) — tüm modeller Türkçe:
  name: "ai.etiket.name", calibrated: "ai.etiket.calibrated", top_k: "ai.etiket.top_k", probabilities: "ai.etiket.probabilities",
  method: "ai.etiket.method", mm_per_px: "ai.etiket.mm_per_px", tumor_regions: "ai.etiket.tumor_regions",
  healthy_regions: "ai.etiket.healthy_regions", centroid_cabin_cm: "ai.etiket.centroid_cabin_cm", E_avg: "ai.etiket.E_avg",
  well_id: "ai.etiket.well_id", n_cancer_pixels: "ai.etiket.n_cancer_pixels", driven: "ai.etiket.driven",
  sessionActive: "ai.etiket.sessionActive", organId: "ai.etiket.organId", organName: "ai.etiket.organName", target: "ai.etiket.target",
  eField: "ai.etiket.eField", perCoil: "ai.etiket.perCoil", freq: "ai.etiket.freq", duty: "ai.etiket.duty",
  phase: "ai.etiket.phase", durationMin: "ai.etiket.durationMin", remainingSec: "ai.etiket.remainingSec", active: "ai.etiket.active",
  class_name: "ai.etiket.class_name", conf: "ai.etiket.conf", classes: "ai.etiket.classes", predictions: "ai.etiket.predictions",
  prob_KIRC: "ai.etiket.prob_KIRC", prob_other: "ai.etiket.probDiger", results: "ai.etiket.results",
  top_probability: "ai.etiket.top_probability", low_confidence: "ai.etiket.low_confidence",
  // cell_scratch — Yara Kapanma (2026-08-26): metrikler geçmiş detayında Türkçe görünsün
  n_cells: "ai.etiket.n_cells", coverage_ratio: "ai.etiket.coverage_ratio",
  closure: "ai.etiket.closure", closure_pct: "ai.etiket.closure_pct",
  mean_gap_um: "ai.etiket.mean_gap_um", max_gap_um: "ai.etiket.max_gap_um",
  gap_area_mm2: "ai.etiket.gap_area_mm2", scratch_yonu: "ai.etiket.scratch_yonu",
  pixel_mm: "ai.etiket.pixel_mm", uyari: "ai.etiket.uyari", closure_uyari: "ai.etiket.closure_uyari",
  inference_ms: "ai.etiket.inference_ms", device: "ai.etiket.device",
  cell_area_mean: "ai.etiket.cell_area_mean", cell_area_median: "ai.etiket.cell_area_median",
  score_mean: "ai.etiket.score_mean", score_min: "ai.etiket.score_min",
  // AI-2 (hoca petri v2 / fantom v3): geçerlilik + tüketim kapısı geçmiş ayrıntısında Türkçe görünsün
  pemf_valid: "ai.etiket.pemf_valid", reliable: "ai.etiket.reliable", coord_frame: "ai.etiket.coord_frame",
  pemf_source: "ai.etiket.pemf_source", warnings: "ai.etiket.warnings", tumor_id: "ai.etiket.tumor_id",
  pemf_kapisi: "ai.etiket.pemf_kapisi", surulebilir: "ai.etiket.surulebilir", pemf_gecerli: "ai.etiket.pemf_gecerli",
  eylem: "ai.etiket.eylem", cancer_reasons: "ai.etiket.cancer_reasons", source: "ai.etiket.source",
};

/** Girdi tipi → katalog anahtarı (`girdiAdi()` ile gösterilir). */
export const INPUT_LABELS: Record<string, string> = {
  image: "ai.girdi.image", clinical: "ai.girdi.clinical", audio: "ai.girdi.audio", csv: "ai.girdi.csv", form: "ai.girdi.form",
};

/**
 * Bilinen İngilizce/enum DEĞERLER → katalog anahtarı (yalnız gösterim; sonuç semantiği korunur). Anahtar
 * küçük-harf. class_counts gibi nesnelerde ALT-ANAHTAR da (stone/cyst...) bu tablodan çevrilir.
 */
const VALUE_LABELS: Record<string, string> = {
  // FGS ağrı seviyeleri
  "no pain": "ai.deger.no_pain", "mild": "ai.deger.mild", "mild pain": "ai.deger.mild_pain",
  "moderate": "ai.deger.moderate", "moderate pain": "ai.deger.moderate_pain", "severe": "ai.deger.severe", "severe pain": "ai.deger.severe_pain",
  // genel durum
  "normal": "ai.deger.normal", "healthy": "ai.deger.healthy", "cancer": "ai.deger.cancer", "abnormal": "ai.deger.abnormal",
  "positive": "ai.deger.positive", "negative": "ai.deger.negative", "unknown": "ai.deger.unknown", "none": "ai.deger.none",
  "idle": "ai.deger.idle", "updated": "ai.deger.updated", "running": "ai.deger.running", "stopped": "ai.deger.stopped",
  "yes": "ai.deger.yes", "no": "ai.deger.no",
  // böbrek CT sınıfları
  "stone": "ai.deger.stone", "cyst": "ai.deger.cyst", "tumor": "ai.deger.tumor", "kidney": "ai.deger.kidney",
  // kedi sesi sınıfları
  "happy": "ai.deger.happy", "resting": "ai.deger.resting", "mothercall": "ai.deger.mothercall", "mating": "ai.deger.mating",
  "huntingmind": "ai.deger.huntingmind", "warning": "ai.deger.warning", "defence": "ai.deger.defence", "angry": "ai.deger.angry",
  "fighting": "ai.deger.fighting", "paining": "ai.deger.paining",
  // Organlar (cat_organ / em_kedi):
  "mide": "ai.deger.mide", "bobrek": "ai.deger.bobrek", "karaciger": "ai.deger.karaciger", "mesane": "ai.deger.mesane",
  "pankreas": "ai.deger.pankreas", "bagirsak": "ai.deger.bagirsak", "kalp": "ai.deger.kalp", "dalak": "ai.deger.dalak",
  "akciger_sag": "ai.deger.akciger_sag", "akciger_sol": "ai.deger.akciger_sol", "kutu_butun": "ai.deger.kutu_butun",
  // Poz tipleri (cat_organ):
  "lateral": "ai.deger.lateral", "sphinx": "ai.deger.sphinx", "standing": "ai.deger.standing",
  "dorsal": "ai.deger.dorsal", "frontal": "ai.deger.frontal", "oblique": "ai.deger.oblique",
  // Kalibrasyon yöntemi (em_fantom / em_petri):
  "aruco_pnp": "ai.deger.aruco_pnp", "phantom_length": "ai.deger.phantom_length",
  "petri_diameter": "ai.deger.petri_diameter", "pixel": "ai.deger.pixel",
  // AI-2: v2 / v3 yöntem ve çerçeve değerleri
  "plate_grid": "ai.deger.plate_grid", "coil_ring": "ai.deger.coil_ring",
  "phantom_layout": "ai.deger.phantom_layout", "cabin_aruco": "ai.deger.cabin_aruco", "plate": "ai.deger.plate",
  "cabin_placement": "ai.deger.cabin_placement", "cabin_cst_phantom_box": "ai.deger.cabin_cst_phantom_box",
  "cst_phantom_box": "ai.deger.cst_phantom_box", "aruco": "ai.deger.aruco", "placement": "ai.deger.placement",
  // Böbrek CT / patoloji:
  "kidney stone": "ai.deger.kidney_stone", "kidney cyst": "ai.deger.kidney_cyst",
  "grade0": "ai.deger.grade0", "grade1": "ai.deger.grade1", "grade2": "ai.deger.grade2", "grade3": "ai.deger.grade3", "grade4": "ai.deger.grade4",
  "kirc": "ai.deger.kirc", "other": "ai.deger.other",
  // KBH (böbrek hastalığı):
  "ckd": "ai.deger.ckd", "notckd": "ai.deger.notckd",
  // Kedi hastalıkları (disease):
  "conjunctivitis": "ai.deger.conjunctivitis", "feline asthma": "ai.deger.feline_asthma",
  "feline calicivirus": "ai.deger.feline_calicivirus", "feline chlamydiosis": "ai.deger.feline_chlamydiosis",
  "feline herpesvirus": "ai.deger.feline_herpesvirus", "feline immunodeficiency virus": "ai.deger.feline_immunodeficiency_virus",
  "feline infectious peritonitis": "ai.deger.feline_infectious_peritonitis", "feline leukemia virus": "ai.deger.feline_leukemia_virus",
  "feline panleukopenia": "ai.deger.feline_panleukopenia", "feline renal disease": "ai.deger.feline_renal_disease",
  "fungal infection": "ai.deger.fungal_infection", "gastroenteritis": "ai.deger.gastroenteritis",
  "hyperthyroidism": "ai.deger.hyperthyroidism", "inflammatory bowel disease": "ai.deger.inflammatory_bowel_disease",
  "intestinal parasites": "ai.deger.intestinal_parasites", "pancreatitis": "ai.deger.pancreatitis",
  "ringworm": "ai.deger.ringworm", "upper respiratory infection": "ai.deger.upper_respiratory_infection",
};

function degerCevir(v: unknown, lng?: "tr"): string {
  const s = String(v ?? "").trim();
  if (!s) return "—";
  const anahtar = VALUE_LABELS[s.toLowerCase()];
  return typeof anahtar === "string" && anahtar ? katalogMetni(anahtar, lng) : s;
}

/**
 * Bilinen İngilizce/enum bir değeri TÜRKÇE'ye çevir (yoksa aynen döner). VERİ YOLU: AI geçmişi kaydına / özete giden metin (`logAiResult`,
 * `summarizeVision`) arayüz dili EN olsa da TR kalır (kayıt dilden bağımsız). Ekranda gösterim için `degerAdi()` kullanılır.
 */
export function trValue(v: unknown): string {
  return degerCevir(v, "tr");
}

/** Bilinen İngilizce/enum bir değeri ARAYÜZ DİLİNDE gösterim metnine çevir (yoksa aynen döner). Yalnız EKRAN. */
export function degerAdi(v: unknown): string {
  return degerCevir(v);
}

/** Girdi tipi (`image` / `clinical` / `audio` / `csv` / `form`) → arayüz dilinde ad (bilinmeyen tip → boş dize). */
export function girdiAdi(tip: string): string {
  const anahtar = INPUT_LABELS[tip];
  return typeof anahtar === "string" ? katalogMetni(anahtar) : "";
}

/** Anahtar → etiket (arayüz dilinde): önce DETAIL_LABELS, sonra VALUE_LABELS (class_counts alt-anahtarları için), yoksa ham. */
function etiketAdi(k: string): string {
  const d = DETAIL_LABELS[k];
  const anahtar = (typeof d === "string" && d) || VALUE_LABELS[k.trim().toLowerCase()];
  return typeof anahtar === "string" && anahtar ? katalogMetni(anahtar) : k;
}

/** Skaler değeri güvenli string'e çevir — nesne/dizi buraya düşerse ASLA "[object Object]" yazma. */
function fmtScalar(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(2);
  if (typeof v === "boolean") return v ? i18n.t("ai.ckd.secenek.evet") : i18n.t("ai.ckd.secenek.hayir");
  if (typeof v === "string") return degerAdi(v);
  return "—"; // nesne/dizi → burada özetlenmez (fmtVal ayrı ele alır)
}

/** Düz nesneyi "etiket: değer, ..." biçiminde çevir; iç-içe nesne alt-değerleri ATLANIR ([object Object] önlenir). */
function fmtFlatObject(o: Record<string, unknown>): string {
  const keys = Object.keys(o).filter((k) => !isHeavyKey(k) && !INTERNAL_KEYS.has(k));
  const parts: string[] = [];
  for (const k of keys.slice(0, 8)) {
    const val = o[k];
    if (val != null && typeof val !== "object") parts.push(`${etiketAdi(k)}: ${fmtScalar(val)}`);
  }
  if (parts.length === 0) return keys.length ? i18n.t("ai.etiket.alanSayisi", { count: keys.length }) : "—";
  return parts.join(", ") + (keys.length > parts.length ? "…" : "");
}

/** Tek bir değeri kullanıcı-dostu string'e çevir (sayı yuvarla, dizi/nesne temiz özetle, değer çevir). */
export function fmtVal(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(3);
  if (typeof v === "boolean") return v ? i18n.t("ai.ckd.secenek.evet") : i18n.t("ai.ckd.secenek.hayir");
  if (typeof v === "string") {
    const s = v.length > VALUE_TRUNC_LEN ? v.slice(0, VALUE_TRUNC_LEN) + "…" : v;
    return degerAdi(s);
  }
  if (Array.isArray(v)) {
    // skaler dizi → değerleri (çevrili); nesne dizisi → "N öğe"
    if (v.every((x) => x == null || typeof x !== "object")) {
      return v.slice(0, 8).map((x) => fmtScalar(x)).join(", ") + (v.length > 8 ? "…" : "");
    }
    return i18n.t("ai.etiket.ogeSayisi", { count: v.length });
  }
  if (typeof v === "object") return fmtFlatObject(v as Record<string, unknown>);
  return "—";
}

/**
 * AI sonuç JSON'undan görsel/binary + devasa string + içsel/teknik alanları ÇIKAR (özyinelemeli, iç içe
 * nesneler dahil). Geçmiş kaydı temiz, küçük ve güvenlik/KVKK-dostu kalır. Diziler olduğu gibi bırakılır.
 */
export function cleanDetail(v: unknown, depth = 0): Record<string, unknown> {
  if (!v || typeof v !== "object" || Array.isArray(v)) return {};
  const out: Record<string, unknown> = {};
  for (const [k, val] of Object.entries(v as Record<string, unknown>)) {
    if (isHeavyKey(k) || INTERNAL_KEYS.has(k)) continue;
    if (typeof val === "string" && val.length > STRIP_STRING_LEN) continue;
    if (val && typeof val === "object" && !Array.isArray(val) && depth < 2) {
      out[k] = cleanDetail(val, depth + 1); // iç içe nesneyi de temizle (nested base64/teknik sızmasın)
    } else {
      out[k] = val;
    }
  }
  return out;
}

/** result_detail → temiz Türkçe {etiket, değer} satırları (görsel/binary/içsel/teknik/boş satır atılır). */
export function detailRows(detail: unknown): { label: string; value: string }[] {
  if (!detail || typeof detail !== "object") return [];
  const rows: { label: string; value: string }[] = [];
  for (const [k, v] of Object.entries(detail as Record<string, unknown>)) {
    if (INTERNAL_KEYS.has(k) || isHeavyKey(k)) continue;
    if (typeof v === "string" && v.length > DISPLAY_STRING_LEN) continue;
    const value = fmtVal(v);
    // Anlamsız boş satırları atla (null/boş nesne → "—"), ama gerçek 0/false gösterilir.
    if (value === "—") continue;
    rows.push({ label: etiketAdi(k), value });
  }
  return rows;
}
