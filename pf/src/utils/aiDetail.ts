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

/** Sonuç anahtarları → Türkçe etiket (bilinmeyen anahtar VALUE_LABELS'a, o da yoksa ham gösterilir). */
export const DETAIL_LABELS: Record<string, string> = {
  detected: "Yüz tespit edildi",
  fgs_total: "FGS ağrı skoru", fgs_score: "FGS ağrı skoru",
  pain: "Ağrı belirtisi", pain_level: "Ağrı seviyesi",
  n_tumor: "Tümör sayısı", n_wells: "Kuyu sayısı", n_cancer: "Kanserli kuyu", n_healthy: "Sağlıklı kuyu",
  n_wells_cancer: "Kanserli kuyu", n_detections: "Tespit sayısı", n_organs: "Lokalize organ",
  n_patients: "Örnek/hasta sayısı", n_masks: "Maske sayısı", cat_count: "Kedi sayısı",
  E_cancer: "Kanser EM alanı", E_healthy: "Sağlıklı EM alanı",
  top_1_class: "Tahmin", top_1_prob: "Olasılık", top_2_class: "2. tahmin", top_2_prob: "2. olasılık",
  top_3_class: "3. tahmin", top_3_prob: "3. olasılık",
  prediction: "Tahmin", disease: "Hastalık", label: "Sonuç", class: "Sınıf",
  prob: "Olasılık", probability: "Olasılık", prob_pct: "Olasılık (%)", confidence: "Güven",
  grade: "Derece", counts: "Hücre sayımı", class_counts: "Sınıf sayıları",
  pose_type: "Poz tipi", area_mm2: "Alan (mm²)", area: "Alan",
  organs: "Organlar", tumors: "Tümörler", wells: "Kuyular", detections: "Tespitler",
  reliability: "Güvenilirlik", localized: "Lokalize edildi", organ: "Organ", organ_name: "Organ",
  risk: "Risk", risk_level: "Risk seviyesi", stage: "Evre", severity: "Şiddet",
  recommendation: "Öneri", note: "Not", summary: "Özet", result: "Sonuç",
  // Kapsamlı AI-model denetimi (2026-07-28) — tüm modeller Türkçe:
  name: "Ad", calibrated: "Kalibre edildi", top_k: "İlk tahminler", probabilities: "Olasılıklar",
  method: "Kalibrasyon yöntemi", mm_per_px: "Ölçek (mm/piksel)", tumor_regions: "Tümör bölgeleri",
  healthy_regions: "Sağlıklı bölgeler", centroid_cabin_cm: "Konum (cm)", E_avg: "Ortalama EM alanı",
  well_id: "Kuyu no", n_cancer_pixels: "Kanser piksel sayısı", driven: "Bobinler sürüldü",
  sessionActive: "Seans aktif", organId: "Organ no", organName: "Organ adı", target: "Hedef konum (mm)",
  eField: "Elektrik alanı (E)", perCoil: "Bobin ayarları", freq: "Frekans (Hz)", duty: "Doluluk (%)",
  phase: "Faz (°)", durationMin: "Toplam süre (dk)", remainingSec: "Kalan süre (sn)", active: "Aktif",
  class_name: "Bulgu türü", conf: "Güven", classes: "Sınıflar", predictions: "Tahminler",
  prob_KIRC: "Olasılık (KIRC)", prob_other: "Olasılık (diğer)", results: "Tahmin sonuçları",
  top_probability: "En yüksek olasılık", low_confidence: "Düşük güven uyarısı",
  // cell_scratch — Yara Kapanma (2026-08-26): metrikler geçmiş detayında Türkçe görünsün
  n_cells: "Hücre sayısı", coverage_ratio: "Hücre kaplama oranı",
  closure: "Kapanma metrikleri", closure_pct: "Kapanma (%)",
  mean_gap_um: "Ortalama gap (µm)", max_gap_um: "Maks gap (µm)",
  gap_area_mm2: "Gap alanı (mm²)", scratch_yonu: "Yara yönü",
  pixel_mm: "Kalibrasyon (mm/px)", uyari: "Uyarı", closure_uyari: "Kapanma uyarısı",
  inference_ms: "Analiz süresi (ms)", device: "Cihaz",
  cell_area_mean: "Hücre alanı (ort. px)", cell_area_median: "Hücre alanı (medyan px)",
  score_mean: "Ortalama skor", score_min: "En düşük skor",
};

/** Girdi tipi → Türkçe. */
export const INPUT_LABELS: Record<string, string> = {
  image: "Görüntü", clinical: "Klinik değerler", audio: "Ses", csv: "CSV / tablo", form: "Form",
};

/**
 * Bilinen İngilizce/enum DEĞERLER → Türkçe (yalnız gösterim; sonuç semantiği korunur). Anahtar
 * küçük-harf. class_counts gibi nesnelerde ALT-ANAHTAR da (stone/cyst...) bu tablodan çevrilir.
 */
const VALUE_LABELS: Record<string, string> = {
  // FGS ağrı seviyeleri
  "no pain": "Ağrı yok", "mild": "Hafif", "mild pain": "Hafif ağrı",
  "moderate": "Orta", "moderate pain": "Orta ağrı", "severe": "Şiddetli", "severe pain": "Şiddetli ağrı",
  // genel durum
  "normal": "Normal", "healthy": "Sağlıklı", "cancer": "Kanser", "abnormal": "Anormal",
  "positive": "Pozitif", "negative": "Negatif", "unknown": "Bilinmiyor", "none": "Yok",
  "idle": "Boşta", "updated": "Güncellendi", "running": "Çalışıyor", "stopped": "Durdu",
  "yes": "Evet", "no": "Hayır",
  // böbrek CT sınıfları
  "stone": "Taş", "cyst": "Kist", "tumor": "Tümör", "kidney": "Böbrek",
  // kedi sesi sınıfları
  "happy": "Mutlu", "resting": "Dinleniyor", "mothercall": "Anne çağrısı", "mating": "Çiftleşme",
  "huntingmind": "Av modu", "warning": "Uyarı", "defence": "Savunma", "angry": "Kızgın",
  "fighting": "Kavga", "paining": "Ağrı belirtisi",
  // Organlar (cat_organ / em_kedi):
  "mide": "Mide", "bobrek": "Böbrek", "karaciger": "Karaciğer", "mesane": "Mesane",
  "pankreas": "Pankreas", "bagirsak": "Bağırsak", "kalp": "Kalp", "dalak": "Dalak",
  "akciger_sag": "Akciğer (sağ)", "akciger_sol": "Akciğer (sol)", "kutu_butun": "Tüm Vücut",
  // Poz tipleri (cat_organ):
  "lateral": "Yandan (lateral)", "sphinx": "Sfenks (oturmuş, önden)", "standing": "Ayakta",
  "dorsal": "Sırtüstü", "frontal": "Önden", "oblique": "Eğik / çapraz",
  // Kalibrasyon yöntemi (em_fantom / em_petri):
  "aruco_pnp": "ArUco PnP (3B kalibre)", "phantom_length": "Fantom uzunluğu ölçekli",
  "petri_diameter": "Petri çapı ölçekli", "pixel": "Piksel modu (ölçeksiz)",
  // Böbrek CT / patoloji:
  "kidney stone": "Böbrek taşı", "kidney cyst": "Böbrek kisti",
  "grade0": "Derece 0", "grade1": "Derece 1", "grade2": "Derece 2", "grade3": "Derece 3", "grade4": "Derece 4",
  "kirc": "Böbrek berrak hücreli karsinom (KIRC)", "other": "Diğer",
  // KBH (böbrek hastalığı):
  "ckd": "Kronik Böbrek Hastalığı (KBH) var", "notckd": "KBH yok (sağlıklı)",
  // Kedi hastalıkları (disease):
  "conjunctivitis": "Konjonktivit (göz nezlesi)", "feline asthma": "Kedi Astımı",
  "feline calicivirus": "Kedi Kalisivirüsü", "feline chlamydiosis": "Kedi Klamidyozu",
  "feline herpesvirus": "Kedi Herpesvirüsü", "feline immunodeficiency virus": "Kedi Bağışıklık Yetmezliği Virüsü (FIV)",
  "feline infectious peritonitis": "Kedi Enfeksiyöz Peritoniti (FIP)", "feline leukemia virus": "Kedi Lösemi Virüsü (FeLV)",
  "feline panleukopenia": "Kedi Panlökopenisi", "feline renal disease": "Kedi Böbrek Hastalığı",
  "fungal infection": "Mantar Enfeksiyonu", "gastroenteritis": "Gastroenterit",
  "hyperthyroidism": "Hipertiroidizm", "inflammatory bowel disease": "İnflamatuar Bağırsak Hastalığı (IBD)",
  "intestinal parasites": "Bağırsak Parazitleri", "pancreatitis": "Pankreatit",
  "ringworm": "Saçkıran (Dermatofitoz)", "upper respiratory infection": "Üst Solunum Yolu Enfeksiyonu",
};

/** Bilinen İngilizce/enum bir değeri Türkçe'ye çevir (yoksa aynen döner). Dışa açık — özet üreticiler de kullanır. */
export function trValue(v: unknown): string {
  const s = String(v ?? "").trim();
  if (!s) return "—";
  return VALUE_LABELS[s.toLowerCase()] || s;
}

/** Anahtar → etiket: önce DETAIL_LABELS, sonra VALUE_LABELS (class_counts alt-anahtarları için), yoksa ham. */
function trLabel(k: string): string {
  return DETAIL_LABELS[k] || VALUE_LABELS[k.trim().toLowerCase()] || k;
}

/** Skaler değeri güvenli string'e çevir — nesne/dizi buraya düşerse ASLA "[object Object]" yazma. */
function fmtScalar(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(2);
  if (typeof v === "boolean") return v ? "Evet" : "Hayır";
  if (typeof v === "string") return trValue(v);
  return "—"; // nesne/dizi → burada özetlenmez (fmtVal ayrı ele alır)
}

/** Düz nesneyi "etiket: değer, ..." biçiminde çevir; iç-içe nesne alt-değerleri ATLANIR ([object Object] önlenir). */
function fmtFlatObject(o: Record<string, unknown>): string {
  const keys = Object.keys(o).filter((k) => !isHeavyKey(k) && !INTERNAL_KEYS.has(k));
  const parts: string[] = [];
  for (const k of keys.slice(0, 8)) {
    const val = o[k];
    if (val != null && typeof val !== "object") parts.push(`${trLabel(k)}: ${fmtScalar(val)}`);
  }
  if (parts.length === 0) return keys.length ? `${keys.length} alan` : "—";
  return parts.join(", ") + (keys.length > parts.length ? "…" : "");
}

/** Tek bir değeri kullanıcı-dostu string'e çevir (sayı yuvarla, dizi/nesne temiz özetle, değer çevir). */
export function fmtVal(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(3);
  if (typeof v === "boolean") return v ? "Evet" : "Hayır";
  if (typeof v === "string") {
    const s = v.length > VALUE_TRUNC_LEN ? v.slice(0, VALUE_TRUNC_LEN) + "…" : v;
    return trValue(s);
  }
  if (Array.isArray(v)) {
    // skaler dizi → değerleri (çevrili); nesne dizisi → "N öğe"
    if (v.every((x) => x == null || typeof x !== "object")) {
      return v.slice(0, 8).map((x) => fmtScalar(x)).join(", ") + (v.length > 8 ? "…" : "");
    }
    return `${v.length} öğe`;
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
    rows.push({ label: trLabel(k), value });
  }
  return rows;
}
