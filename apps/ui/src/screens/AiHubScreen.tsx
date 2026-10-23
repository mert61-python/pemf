// Author: mertaygn, cglrgrkn
import { useState, useEffect, useRef, useCallback, type MutableRefObject } from "react";
import { StyleSheet, Text, View, Image, ActivityIndicator, TouchableOpacity, TextInput, Platform, Linking } from "react-native";
import * as ImagePicker from "expo-image-picker";
import * as ImageManipulator from "expo-image-manipulator";
import * as DocumentPicker from "expo-document-picker";
import * as FileSystemLegacy from "expo-file-system/legacy";
import { useAudioRecorder, RecordingPresets, setAudioModeAsync, requestRecordingPermissionsAsync } from "expo-audio";
import { Camera, Image as ImageIcon, Sparkles, Stethoscope, ScissorsSquare as Scan, Activity, Microscope, Video, SwitchCamera, Crosshair, FlaskConical, Dna, FileText, HeartPulse, Mic, Square, AudioLines, ScanLine, PawPrint, Lock } from "lucide-react-native";
import { CameraView, useCameraPermissions } from 'expo-camera';
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ResponsiveGrid } from "@/components/ui/ResponsiveGrid";
import { useGaleriYuksekligi, useStageHeight } from "@/hooks/useStageHeight";
import { GorselSahne } from "@/components/ui/GorselSahne";
import { sahneSayfalari } from "@/utils/gorselSahneSayfalari";
import { kameraKutusu, kareOrani } from "@/utils/kameraKutusu";
import { colors, radius, spacing, typography, rf, rs, layoutMax, touch } from "@/theme/tokens";
import { EmDozSatiri, konumMetni, pikselKipiNotu } from "@/components/domain/EmDozSatiri";
import { PemfKapisiKutusu, type PemfKapisi } from "@/components/domain/PemfKapisiKutusu";
import { KabinKaresiDugmesi, KosulSecici } from "@/components/domain/AnalizKosulu";
import { useToast } from "@/components/ui/ToastProvider";
import { webIcinKucult } from "@/services/gorselKucult";
import { apiGet, apiPost, authHeaders, platformAlert, AI_TIMEOUT_MS, aiHataMesaji } from "@/services/apiClient";
import { aiDetayCumlesi } from "@/utils/aiHataDetayi";
import {
  CANLI_OTURUM_BASLIGI,
  canliJetonMetni,
  canliKareDurumu,
  canliOturumBaslat,
  canliSonrakiBekleme,
  type CanliDurum,
} from "@/utils/canliKare";
import { jetonBakiyesiGetir } from "@/services/jetonBakiye";
import { ckdOnKontrol } from "@/utils/ckdOnKontrol"; // B5: CKD gönderim-öncesi eyleme dönük ön-kontrol (klinik_asgari paritesi)
import AsyncStorage from "@react-native-async-storage/async-storage";
import { serviceConfig } from "@/services/config";
import { useUserMode, UserMode } from "@/context/UserModeContext";
import { cleanDetail, trValue } from "@/utils/aiDetail";
import { sesFormDataHazirla } from "@/utils/sesYukleme";
import { useLiveData } from "@/context/LiveDataContext";
import { useAppNav } from "@/context/AppNavContext";
import { useAuth } from "@/context/AuthContext";
import { useOperator, useOperatorOptional } from "@/context/OperatorContext";
import { useEntitlement } from "@/context/EntitlementContext";
import { UpgradeModal, type UpgradeFeature } from "@/components/UpgradeModal";
import { useResponsive } from "@/hooks/useResponsive";
import { PatientGate } from "@/components/domain/PatientGate";
import { GenisletilebilirMetin } from "@/components/ui/GenisletilebilirMetin";
import { hastaninSonAnalizi, hastayaGoreSonAnaliz, kapsamda, sonAnalizOzeti, type AnalizKaydi } from "@/utils/sonAnaliz";
import { effectiveScope } from "@/utils/patientScope";
import i18n from "i18next";
import { Trans, useTranslation } from "react-i18next";

type AiModule = "disease" | "landmark" | "segmentation" | "thermal" | "reticulocytes" | "em_fantom" | "em_petri" | "kidney_rna" | "kidney_disease" | "cat_sound" | "kidney_ct" | "histopath" | "cat_organ" | "cell_scratch";

// D1.E09 (İG-5.31): model nokta görünürlüğünü bildirmiyor → örtülü yüzde skor yanıltıcı olabilir. TEK KAYNAK: hekim/araştırma
// kartı ve hayvan sahibi kartı aynı metni gösterir (1-D inceleme i3-F-2: sahip kartında uyarı yoktu).
const noktaGorunurluguUyarisi = (): string => i18n.t("ai.ortak.noktaGorunurluguUyarisi");

// Görüntü yalnız ekranda: seçim İNDEKS ile gider (`symptom_indices`), metin sunucuya gitmez → dil değişince çevrilir.
const semptomlar = (): string[] => [
  i18n.t("ai.hastalik.semptom.istahKaybi"),
  i18n.t("ai.hastalik.semptom.kusma"),
  i18n.t("ai.hastalik.semptom.ishal"),
  i18n.t("ai.hastalik.semptom.oksuruk"),
  i18n.t("ai.hastalik.semptom.solunumGuclugu"),
  i18n.t("ai.hastalik.semptom.topallik"),
  i18n.t("ai.hastalik.semptom.deriLezyonlari"),
  i18n.t("ai.hastalik.semptom.burunAkintisi"),
  i18n.t("ai.hastalik.semptom.gozAkintisi"),
  i18n.t("ai.hastalik.semptom.halsizlik"),
  i18n.t("ai.hastalik.semptom.kiloKaybi"),
  i18n.t("ai.hastalik.semptom.hapsirma"),
  i18n.t("ai.hastalik.semptom.dehidrasyon"),
  i18n.t("ai.hastalik.semptom.ates"),
];

/**
 * Herhangi bir telefondan gelen fotoğrafı YÜKLEME-ÖNCESİ küçültür: uzun kenar max 1500px + JPEG %70.
 * Sonuç hep <1MB → backend'in (Starlette) 1MB multipart part limitine TAKILMAZ ("Part exceeded
 * maximum size of 1024KB" hatası biter). Ayrıca yükleme+inference daha hızlı, tünelde OOM riski yok.
 * AI modelleri zaten iç boyuta küçültüyor (YOLO 640px), 1500px fazlasıyla yeterli. Manipülasyon
 * başarısızsa orijinali döndürür (akış kırılmasın).
 */
async function shrinkForUpload(uri: string): Promise<{ uri: string; base64: string | null }> {
  try {
    const out = await ImageManipulator.manipulateAsync(
      uri,
      // ORTA fix: SABİT 1500px hedef. rs() yoğunluk-ölçeklidir → yüksek-DPI cihazda 3000-4500px'e şişip
      // "<1MB upload" hedefini bozuyor + gereksiz RAM/ağ tüketiyordu. Upload boyutu cihaz-DPI'dan bağımsız olmalı.
      [{ resize: { width: 1500 } }],
      { compress: 0.7, format: ImageManipulator.SaveFormat.JPEG, base64: true }
    );
    return { uri: out.uri, base64: out.base64 ?? null };
  } catch {
    return { uri, base64: null };
  }
}

/** Otonom Biofeedback yönlendirmesi — canlı ve elle analizde AYNI metin (D1.88 · A-19: onay akışı AI Pro'da).
 *  Terminoloji (karar #12): araştırmacı bir HEKİM değildir; "hekim onayı" metni araştırma modunda yanlış rol atfeder. */
function otonomYonlendirmeMetni(): string {
  return currentAiMode === "researcher"
    ? i18n.t("ai.ortak.otonomOnayArastirma")
    : i18n.t("ai.ortak.otonomOnayHekim");
}

/** AI teşhis sonucunu kalıcı audit loguna gönderir (hasta + modül + özet). */
// AiHubScreen mount'ta set eder → logAiResult (modül-seviyesi, hook DEĞİL) aktif profili bilir.
let currentAiMode: UserMode = null;
/**
 * Seçili hastanın OPAK KİMLİĞİ — analiz kaydına yazılır (2026-09-12 taşıması).
 *
 * ⚠️ NEDEN AD YETMİYOR: aynı adlı iki hayvanda analizler karışıyor, hasta kaydında ad
 * düzeltilince eski analizler kopuyor ve `PEMF_MASK_HISTORY_PII=1` açıkken TÜM adlar
 * `[SIFRELENMEMIS-DB]` yazıldığı için eşleme bütünüyle çöküyordu.
 * ⚠️ `currentAiMode`/`currentOperatorEmail` ile AYNI desen: `logAiResult` bir React
 * bileşeni değil, bu yüzden bağlamı modül değişkeninden okur.
 */
let currentPatient: { id: string; name: string } = { id: "", name: "" };

/** Analizin bağlandığı hasta: KİMLİK ve AD birlikte (aynı anın görüntüsü) + analizi BAŞLATAN hekim (jeton + e-posta, C2-4.3). */
type HastaAnligi = { id: string; name: string; operatorJetonu: string | null; operatorEmail: string };

/**
 * ⚠️ D2.E09 (İG-6.24) · SAHİP KARARI Y87: uçuştaki analiz, hasta değiştirilse bile BAŞLATILDIĞI hastaya yazılır. Her analiz işlevi
 * İLK `await`'ten ÖNCE `const hasta = hastaAnligi()` alır ve kaydı onunla yazar. Eskiden ad çağıranın kapanışından (başlangıçtaki
 * hasta), KİMLİK bu modül değişkeninden (tamamlanma anındaki hasta) okunuyordu → satır iki hayvanın geçmişinde görünüyordu
 * (ölçüldü: "Mia" + Pamuk'un kimliği). Kapı: __tests__/aiHubUcustakiAnaliz.E09.Y87.web.test.tsx (çağıranlar kaynaktan türetilir).
 * ⚠️ C2-4.3 (2-C incelemesi, aynı ilke — hekim için): görüntü analizi BAŞLATAN hekimin operatör jetonunu ve e-postasını da taşır.
 * Eskiden kayıt tamamlanma anındaki jetonla gidiyordu → Dr. A'nın başlattığı analiz, uçuşta "Geçiş yap" ile Dr. B'ye geçilince
 * Dr. B'ye imzalanıyordu (ölçüldü, SQL: `('dr.b', 'u-mia', 'Mia')`). Kilitle (D2.E14) jetonu sunucuda iptal ettiğinden o durumda
 * kayıt bugünkü gibi sahipsiz yazılır (Y109). Kapı: __tests__/aiHubUcustaOperatorDegisimi.C2_4_3.web.test.tsx.
 */
function hastaAnligi(): HastaAnligi {
  // Jeton `authHeaders()`'tan: gönderimle AYNI güvenli-taban kapısı (güvensiz tabana jeton zaten gitmez).
  return {
    ...currentPatient,
    operatorJetonu: authHeaders()["X-PEMF-Operator"] || null,
    operatorEmail: currentOperatorEmail,
  };
}
// Aynı desen: giriş yapan hekim e-postası (klinik-içi "Benim/Tüm Klinik" AI-analiz filtresi).
let currentOperatorEmail: string = "";

// Tüm AI modelleri sonuçlarını buradan ŞİFRELİ ai_analyses geçmişine yazar (profesyonel + detaylı).
// result_detail utils/aiDetail.cleanDetail ile temizlenir (görsel/binary/devasa alanlar atılır).
// extra: modül-id + girdi-tipi + sonuç detayı (cleanDetail ile temizlenir) + opsiyonel güven. mode oto.
async function logAiResult(
  hasta: HastaAnligi,
  module: string,
  summary: string,
  extra?: { moduleId?: string; inputType?: string; detail?: unknown; confidence?: number }
) {
  try {
    await apiPost("/ai/log", {
      patient_name: hasta.name || "",
      module,
      summary,
      mode: currentAiMode || "",
      module_id: extra?.moduleId || "",
      input_type: extra?.inputType || "",
      result_detail: cleanDetail(extra?.detail),
      confidence: extra?.confidence ?? null,
      // C2-4.3: analizi BAŞLATAN hekim (görüntüden) — tamamlanma anındaki hekim DEĞİL.
      operator_email: hasta.operatorEmail || "",
      // ⚠️ Hasta KİMLİĞİ (opak) — ad bazlı eşlemenin üç kırılganlığını kapatır (bkz. currentPatient). Ad ile AYNI görüntüden
      // (D2.E09). Boş geçerse backend eskisi gibi ada bağlı çalışır (geriye uyumlu).
      patient_id: hasta.id || "",
    }, null, { operatorJetonu: hasta.operatorJetonu });
  } catch {
    /* audit başarısız — kullanıcı akışını bozma */
  }
}

/** Yakalanan hatadan (unknown) güvenli mesaj çıkarır — `catch (e: any)` yerine (audit B-2.4). */
function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

// `aiHataMesaji` (zaman aşımı / gönderilemedi / geçersiz yanıt sınıflandırması) 2026-09-08'de
// `@/services/apiClient`e taşındı: saf fonksiyon, testi `services/__tests__/aiHataMesaji.test.ts`.


// audit B-2.4: AI-sonuç eleman şekilleri — .map/.filter/.reduce callback'lerini tiplemek için
// (display render; tsc-doğrulanabilir). Sonuç CONTAINER state'i (useState) heterojen per-model
// backend yanıtı olduğundan permissive bırakıldı (tam tipleme backend response-sözleşmesi ister).
// D1.E07 (İG-5.76): piksel kipinde E/alan hesaplanmaz → null (bkz. EmDozSatiri).
interface AiTumorRegion { area_mm2?: number | null; area_px?: number; centroid_cabin_mm?: number[] | null; konum_hatasi?: string | null; D?: number[]; E_cancer?: number | null; E_healthy?: number | null; tumor_id?: string; }
interface AiWell { area_mm2?: number | null; area_px?: number; centroid_cabin_mm?: number[] | null; konum_hatasi?: string | null; D?: number[]; label?: string; organ_id?: number; well_id?: string | number; E_cancer?: number | null; E_healthy?: number | null; cancer_reasons?: string[]; source?: string; }
interface AiPrediction { confidence?: number; patient_id?: string; prediction?: string; [k: `prob_${string}`]: number | undefined; }
interface AiTopK { class: string; prob: number; }
interface AiDetection { class_name: string; conf?: number; bbox_xyxy?: number[]; index?: number; }
interface AiOrgan { name: string; coord_cabin_cm?: number[]; coord_3d_cm?: number[]; reliability?: number; }
interface DiseasePrediction { disease: string; probability: number; }
interface ThermalPrediction { label?: string; confidence?: number; }
interface FgsRaw {
  measurements?: Record<string, number>; action_units?: Record<string, { score?: number | string }>; }

/**
 * AI backend yanıt sözleşmesi (audit B-2.4): 8+ modelin (vision/CT/patoloji/ses/RNA/CKD/organ)
 * heterojen JSON yanıtı. TÜM alanlar opsiyonel — her alt-bileşen KENDİ modelinin alanlarını okur;
 * `any` yerine bu tip → alan-adı typo'ları derleme-zamanı yakalanır + autocomplete.
 * (disease modülü DİZİ döndürür → DiseasePrediction[], AiResult değil.)
 */
/**
 * [S7 adım 8 / aihub-3] Duty çubuğu dolgusu YÜZDE ile. Eskiden `26 px` sabitine göre hesaplanıyordu:
 * kap yüksekliği ölçekle değişince (rs) dolgu kabın dışına taşıyor ya da yarısında kalıyordu.
 * Yüzde dolgu `soundBarFill` deseniyle aynı ve her ölçekte doğru.
 */
const dutyYuzde = (d: number) => `${Math.max(4, Math.round((Math.min(Math.max(d, 0), 0.5) / 0.5) * 100))}%` as const;

interface AiResult {
  status?: string; success?: boolean; method?: string; image_base64?: string;
  /** [S7 adım 4] Kodlanan karenin gerçek boyutu — önizleme kutusunun oran kilidi.
   *  ⚠️ Opsiyonel: eski backend göndermez → cihaz yönü varsayılanına düşülür. */
  image_w?: number; image_h?: number;
  // disease vision (FGS / termal / segmentasyon / retikülosit / AI-Pro donanım)
  fgs_total?: number | null; detected?: boolean; raw_fgs?: FgsRaw;
  nokta_gorunurlugu_dogrulanmadi?: boolean; // D1.E09: model nokta görünürlüğünü bildirmiyor
  prediction?: ThermalPrediction; cat_count?: number; counts?: Record<string, number>;
  hw_status?: string; hw_params?: { freq?: number; duty?: number };
  // em_fantom (tümör) / em_petri (kuyucuk)
  n_tumor?: number; mm_per_px?: number; tumor_regions?: AiTumorRegion[];
  n_cancer?: number; n_wells?: number; n_healthy?: number; wells?: AiWell[];
  // AI-2 (hoca petri v2 / fantom v3): tüketim kapısı + geçerlilik (alan yoksa = eski backend; kutu çizilmez)
  pemf_kapisi?: PemfKapisi; pemf_valid?: boolean; reliable?: boolean; warnings?: string[]; pemf_source?: string; coord_frame?: string;
  // kidney_rna / kidney_disease (CKD)
  predictions?: AiPrediction[]; n_patients?: number;
  label?: string; prob_pct?: number; model?: string;
  // Sunum-katmanı XAI (2026-08-26): SHAP top-özellikler (alan yoksa satır gizli)
  xai?: { disease?: string; prob_ckd?: number; top_features?: { feature: string; attribution: number }[] } | null;
  // Faz 2: gradient ısı haritası (termal/ses; explain=true istenirse)
  xai_image_base64?: string; xai_method?: string; xai_error?: string;
  xai_hedef?: "Sick" | "Healthy";  // AI1.X1: termal haritanın AÇIKLADIĞI karar (tahmin edilen sınıf)
  xai_disagreement_base64?: string;  // histopat: 3-model kararsızlık haritası
  // top-k sınıflandırma (cat_sound / histopath / reticulocytes)
  top_1_class?: string; top_1_prob?: number; top_k?: AiTopK[];
  // cat_sound BELİRSİZLİK (sunucu ölçer — utils/ses_kalitesi). Model "kedi sesi yok" DİYEMEZ
  // (10 sınıfın hepsi kedi duygusu), bu yüzden sunucu dağılımın entropisini gönderir ve
  // `guvenilir === false` iken sonuç kesin bir bulgu gibi GÖSTERİLMEZ. Sessiz kayıt zaten
  // sunucuda reddedilir; bu alan yalnız "analiz edildi ama zayıf" durumu içindir.
  guvenilir?: boolean; belirsizlik?: number; rms_dbfs?: number | null;
  // kidney_ct / cat_organ
  class_counts?: Record<string, number>; detections?: AiDetection[];
  n_organs?: number; organs?: AiOrgan[]; pose_type?: string; pnp_residual_px?: number;
  // cell_scratch (Yara Kapanma — plan: scratch-entegrasyon-plani.md v3). Görsel alanlar
  // TOP-LEVEL tutulur (cleanDetail depth≥2 iç-nesneyi olduğu gibi kopyalar — ölçüldü).
  n_cells?: number; coverage_ratio?: number; score_mean?: number;
  scratch_yonu?: string; pixel_mm?: number;
  closure?: { closure_pct: number; mean_gap_um: number; max_gap_um: number; gap_area_mm2: number } | null;
  uyari?: string; closure_uyari?: string; device?: string;
  input_image_base64?: string; seg_image_base64?: string; overlay_image_base64?: string;
  analysis_image_base64?: string; closure_image_base64?: string; xai_side_by_side_base64?: string;
  _xai_istendi?: boolean; // B4 ScratchModule: ısı haritası bu analizde İSTENDİ mi (istenip gelmeyeni sessiz bırakmamak için)
  // SG.G4: termal girdinin makullik doğrulaması (backend `utils/image_domain.termal_girdi_dogrulamasi`; arayüz yalnız gösterir)
  // S-SGI.4: `yon_notu` — kapı palet YÖNÜNÜ ölçmez; eşleşen paletin kamera yönü ("doğrulandı" sonucunda da gösterilir)
  girdi_dogrulama?: { durum: string; dogrulandi: boolean; uyari: string | null; yon_notu?: string | null } | null;
  // SG.G5: kedi organ "bulunamadı" BİLGİSİ (backend `catorgan_predictor.BULUNAMADI_METNI`)
  bulunamadi?: string; bulunamadi_mesaji?: string;
}

function summarizeVision(d: any): string {
  if (d?.fgs_total !== undefined) return `FGS ${d.fgs_total}/10${d?.pain_level ? ` (${trValue(d.pain_level)})` : ""}`;
  if (d?.cat_count !== undefined) return `${d.cat_count} kedi tespit edildi`;
  if (d?.prediction?.label) {
    return `Termal: ${trValue(d.prediction.label)}${d?.girdi_dogrulama?.dogrulandi === false ? " · girdi termal olarak doğrulanamadı" : ""}`;
  }
  if (d?.counts) return `Eritrosit ${d.counts["erythrocyte"] ?? "?"} / Retikülosit ${(d.counts["punctate reticulocyte"] ?? 0) + (d.counts["aggregate reticulocyte"] ?? 0)}`;
  return "Analiz tamamlandı";
}

export function AiHubScreen() {
  const { t } = useTranslation();
  const { userMode, hasAiHub } = useUserMode();
  const { selectedPatient } = useAppNav();
  const { session } = useAuth();
  // null = hepsi kapalı (akordeon). Karta tıkla → altında açılır; tekrar tıkla → kapanır.
  const { research } = useEntitlement();
  const [upgradeFor, setUpgradeFor] = useState<UpgradeFeature | null>(null);
  // ⚠️ ÇOKLU AÇIK MODÜL (saha bildirimi 2026-08-12). Eskiden `activeModule` TEK bir modül
  // tutuyordu: ikinci modüle dokunulduğunda birincinin gövdesi KAPANIYOR, geriye yalnız başlığı
  // kalıyordu. Oysa akış karşılaştırmalı: hekim FGS skorunu görürken ses analizini de açıp iki
  // sonuca BİRLİKTE bakmak istiyor (araştırma modunda da aynısı). Küme → istenen kadar modül
  // açık kalır ve sayfa aşağı doğru uzar. Kapatma yine aynı: açık bir modüle dokunmak kapatır.
  const [acikModuller, setAcikModuller] = useState<Set<AiModule>>(() => new Set());

  /** Modülü aç/kapat — küme KOPYALANARAK değişir (React referans eşitliğiyle render'ı tetikler). */
  const moduluDegistir = useCallback((id: AiModule) => {
    setAcikModuller((onceki) => {
      const yeni = new Set(onceki);
      if (yeni.has(id)) yeni.delete(id);
      else yeni.add(id);
      return yeni;
    });
  }, []);

  // logAiResult (hook değil) aktif profili bilsin diye modül-değişkenine yaz (analiz kaydına mode gitsin).
  useEffect(() => { currentAiMode = userMode; }, [userMode]);
  useEffect(() => {
    currentPatient = { id: selectedPatient?.id || "", name: selectedPatient?.name || "" };
  }, [selectedPatient?.id, selectedPatient?.name]);
  // Aynı desen: giriş yapan hekim e-postasını modül-değişkenine yaz (AI analiz sahipliği).
  const { operatorEmail } = useOperator();
  useEffect(() => { currentOperatorEmail = operatorEmail; }, [operatorEmail]);

  // KRİTİK fix (bkz. resetAiCachesForOwner): profil/hasta değişince AI cache'lerini TEMİZLE + açık modülü
  // kapat → önceki hastanın görüntüsü/sonucu yeni hastada görünmesin ve yanlış hastaya analiz yazılmasın.
  // O-A3.6: sahip = profil + KİMLİK + hasta — başka hekim aynı hastayı seçince önceki hekimin görüntüsü/sonucu geri gelmez.
  const aiCacheOwnerKey = `${userMode ?? ""}:${(operatorEmail || "").toLowerCase()}:${selectedPatient?.id ?? selectedPatient?.name ?? ""}`;
  // ⚠️ D2.E08 (İG-6.23): temizlik ÇİZİM sırasında, yeni sahibin çocukları kurulmadan ÖNCE. Eskiden `useEffect`teydi: çocuğun
  // `useState(moduleCache…)` başlatıcıları temizlikten ÖNCE okuyordu → ev sahibi ekranında önceki hastanın fotoğrafı/sesi/
  // sonucu kalıyor, "Teşhis Et" önceki hastanın dosyasını YENİ hastaya gönderiyordu (ölçüldü; "yalnız key" de yetmiyordu).
  // `resetAiCachesForOwner` eşdeğer çağrıda no-op (aynı sahip) — tekrarlanan çizim güvenli. Açık modüllerin kapanması durum
  // güncellemesidir → etkide kalır.
  resetAiCachesForOwner(aiCacheOwnerKey);
  const sonSahip = useRef(aiCacheOwnerKey);
  useEffect(() => {
    if (sonSahip.current === aiCacheOwnerKey) return;
    sonSahip.current = aiCacheOwnerKey;
    setAcikModuller(new Set());
  }, [aiCacheOwnerKey]);

  // pet_owner → basit ekran; veterinarian/researcher → modüler AI Hub (modüller profile göre filtreli).
  // HASTA KAPISI (2026-08-07): analiz sonucu `ai_analyses`'e hasta adıyla yazılır → hasta
  // seçilmeden analiz, geçmişte SAHİPSİZ kayıt üretir. Üç profilde de kapı var; ev sahibi
  // profilinde "Hastalar" ekranı olmadığı için hasta ekleme de bu kapının içinde yapılır.
  if (!hasAiHub) {
    return (
      <PatientGate>
        {/* D2.E08: hasta/profil değişince ev sahibi ekranı (FGS + ses kartı + hastalık formu) YENİDEN KURULUR. */}
        <PetOwnerAiScreen key={aiCacheOwnerKey} />
      </PatientGate>
    );
  }

  const patientName = selectedPatient?.name || "";

  // Modüller profile göre filtrelenir: veterinarian → 7 kedi modeli; researcher → 7 araştırma modeli
  // (fantom/petri/böbrek). Yeni model eklenince yalnız modes'unu ayarla. (pet_owner yukarıda ayrılır.)
  // 2026-08-06 sahip kararı araştırma profiline CİHAZ ROTALARINI açtı (config/access.ts); AI Hub'ın
  // bu bölüşümü BİLİNÇLİ olarak DEĞİŞMEDİ — kedi modelleri klinik, araştırma modelleri laboratuvar işi.
  const ALL_MODULES: { id: AiModule; label: string; desc: string; icon: any; modes: UserMode[] }[] = [
    { id: "landmark", label: t("ai.modul.yuzAgrisi.ad"), desc: t("ai.modul.yuzAgrisi.aciklama"), icon: Scan, modes: ["veterinarian"] },
    { id: "disease", label: t("ai.modul.hastalik.ad"), desc: t("ai.modul.hastalik.aciklama"), icon: Stethoscope, modes: ["veterinarian"] },
    { id: "segmentation", label: t("ai.modul.segmentasyon.ad"), desc: t("ai.modul.segmentasyon.aciklama"), icon: Scan, modes: ["veterinarian"] },
    { id: "thermal", label: t("ai.modul.termal.ad"), desc: t("ai.modul.termal.aciklama"), icon: Activity, modes: ["veterinarian"] },
    { id: "reticulocytes", label: t("ai.modul.retikulosit.ad"), desc: t("ai.modul.retikulosit.aciklama"), icon: Microscope, modes: ["veterinarian"] },
    { id: "em_fantom", label: t("ai.modul.fantomTumor.ad"), desc: t("ai.modul.fantomTumor.aciklama"), icon: Crosshair, modes: ["researcher"] },
    { id: "em_petri", label: t("ai.modul.petriKuyu.ad"), desc: t("ai.modul.petriKuyu.aciklama"), icon: FlaskConical, modes: ["researcher"] },
    { id: "kidney_rna", label: t("ai.modul.bobrekRna.ad"), desc: t("ai.modul.bobrekRna.aciklama"), icon: Dna, modes: ["researcher"] },
    { id: "kidney_disease", label: t("ai.modul.bobrekHastaligi.ad"), desc: t("ai.modul.bobrekHastaligi.aciklama"), icon: HeartPulse, modes: ["researcher"] },
    { id: "cat_sound", label: t("ai.modul.kediSesi.ad"), desc: t("ai.modul.kediSesi.aciklama"), icon: AudioLines, modes: ["veterinarian"] },
    { id: "kidney_ct", label: t("ai.modul.bobrekCt.ad"), desc: t("ai.modul.bobrekCt.aciklama"), icon: ScanLine, modes: ["researcher"] },
    { id: "histopath", label: t("ai.modul.bobrekPatoloji.ad"), desc: t("ai.modul.bobrekPatoloji.aciklama"), icon: Microscope, modes: ["researcher"] },
    { id: "cell_scratch", label: t("ai.modul.yaraKapanma.ad"), desc: t("ai.modul.yaraKapanma.aciklama"), icon: FlaskConical, modes: ["researcher"] },
    { id: "cat_organ", label: t("ai.modul.kediOrgan.ad"), desc: t("ai.modul.kediOrgan.aciklama"), icon: PawPrint, modes: ["veterinarian"] },
  ];
  const MODULES = ALL_MODULES.filter((m) => userMode != null && m.modes.includes(userMode));

  // Aktif modülün içeriğini döndür (akordeon gövdesi). key= sabit → cache ile sonuç korunur.
  const renderModuleBody = (id: AiModule) => {
    switch (id) {
      case "disease": return <DiseaseModule patientName={patientName} />;
      case "landmark": return <VisionModule key="landmark" endpoint="/vision/landmark" title={t("ai.gorsel.yuzAgrisi.baslik")} subtitle={t("ai.gorsel.yuzAgrisi.altBaslik")} patientName={patientName} />;
      case "segmentation": return <VisionModule key="segmentation" endpoint="/vision/segmentation" title={t("ai.gorsel.segmentasyon.baslik")} subtitle={t("ai.gorsel.segmentasyon.altBaslik")} patientName={patientName} />;
      case "thermal": return <VisionModule key="thermal" endpoint="/vision/thermal" title={t("ai.gorsel.termal.baslik")} subtitle={t("ai.gorsel.termal.altBaslik")} patientName={patientName} explainDestegi />;
      case "reticulocytes": return <VisionModule key="reticulocytes" endpoint="/vision/reticulocytes" title={t("ai.gorsel.retikulosit.baslik")} subtitle={t("ai.gorsel.retikulosit.altBaslik")} patientName={patientName} galleryOnly explainDestegi />;
      case "em_fantom": return <PhantomModule key="em_fantom" patientName={patientName} />;
      case "em_petri": return <PetriModule key="em_petri" patientName={patientName} />;
      case "kidney_rna": return <RnaModule key="kidney_rna" patientName={patientName} />;
      case "kidney_disease": return <KidneyDiseaseModule key="kidney_disease" patientName={patientName} />;
      case "cat_sound": return <CatSoundModule key="cat_sound" patientName={patientName} />;
      case "kidney_ct": return <KidneyCTModule key="kidney_ct" patientName={patientName} />;
      case "histopath": return <HistopathModule key="histopath" patientName={patientName} />;
      case "cell_scratch": return <ScratchModule key="cell_scratch" patientName={patientName} />;
      case "cat_organ": return <CatOrganModule key="cat_organ" patientName={patientName} />;
      default: return null;
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.content}>
  {/* [S4 adım 3] İç dikey ScrollView KALDIRILDI: kabuk (AppShell) zaten tek kaydırıcı ve
  keyboardShouldPersistTaps='handled' taşıyor. İç ScrollView'ın yükseklik sınırı
  olmadığı için kendi kaydırmasını hiç üretmiyordu; ama klavye açıkken dokunuşu
  yutup 'Kaydet/Bağlan' düğmelerini İKİ dokunuş gerektiriyordu. */}
        {/* HASTA KAPISI (2026-08-07): hasta seçilmeden modüller GÖSTERİLMEZ. AI Hub'da
            güvenlik-kritik bir kontrol (ACİL DURDUR vb.) yok → sert kapı güvenli.
            Kontrol ekranında ise `soft` kip kullanılır, bkz. PatientGate prop açıklaması. */}
        <PatientGate>
        <Text style={styles.selectorHeading}>{t("ai.hub.baslik")}</Text>
        <View style={styles.aiWelcome}>
          <Text style={styles.aiWelcomeTitle}>{t("ai.hub.nasilCalisir")}</Text>
          <Text style={styles.aiWelcomeText}>
            <Trans i18nKey="ai.hub.nasilCalisirGovde" components={{ kalin: <Text style={styles.aiWelcomeBold} /> }} />
          </Text>
          <Text style={styles.aiWelcomeNote}>
            <Trans i18nKey="ai.hub.ilkAnalizNotu" components={{ kalin: <Text style={styles.aiWelcomeBold} /> }} />
          </Text>
        </View>
        <View style={styles.moduleGrid}>
          {MODULES.map((m) => {
            const Icon = m.icon;
            const active = acikModuller.has(m.id);
            const gated = m.modes.includes("researcher") && !research;
            return (
              <View key={m.id}>
                {/* a11y: akordeon kartında rol/durum yoktu → ekran okuyucu başlığı okuyor ama
                    bunun AÇILIP KAPANAN bir kontrol olduğunu ve o an açık mı olduğunu bildirmiyordu. */}
                <TouchableOpacity
                  style={[styles.moduleCard, active && styles.moduleCardActive]}
                  onPress={() => moduluDegistir(m.id)}
                  activeOpacity={0.85}
                  accessibilityRole="button"
                  accessibilityState={{ expanded: active }}
                  accessibilityLabel={gated ? t("ai.hub.modulEtiketiEklenti", { ad: m.label }) : m.label}
                  accessibilityHint={active ? t("ai.hub.kapatmakIcin") : t("ai.hub.acmakIcin")}
                >
                  <View style={[styles.moduleIconWrap, active && styles.moduleIconWrapActive]}>
                    <Icon size={22} color={active ? colors.white : colors.primary} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={[styles.moduleLabel, active && styles.moduleLabelActive]} numberOfLines={1}>{m.label}</Text>
                    <Text style={styles.moduleDesc} numberOfLines={2}>{m.desc}</Text>{/* kısa etiket — cümle değil, genişletme gerekmez */}
                  </View>
                  {gated && (
                    <TouchableOpacity
                      onPress={() => setUpgradeFor("research")}
                      style={styles.gateBadge}
                      accessibilityRole="button"
                      accessibilityLabel={t("ai.hub.eklentiGerekli")}
                    >
                      <Lock size={11} color={colors.violet} />
                      <Text style={styles.gateBadgeText}>{t("ai.hub.eklenti")}</Text>
                    </TouchableOpacity>
                  )}
                  <Text style={[styles.moduleChevron, active && styles.moduleChevronActive]}>{active ? "▲" : "▼"}</Text>
                </TouchableOpacity>
                {active && <View style={styles.moduleBody}>{renderModuleBody(m.id)}</View>}
              </View>
            );
          })}
        </View>
        </PatientGate>
      </View>
      <UpgradeModal visible={!!upgradeFor} onClose={() => setUpgradeFor(null)} feature={upgradeFor ?? "tier"} />
    </View>
  );
}

function PetOwnerAiScreen() {
  const { t } = useTranslation();
  // Galeri ASIL okuma yuzeyi: daha yuksek tavan, AYNI responsive oran (bkz. useGaleriYuksekligi).
  const galeriH = useGaleriYuksekligi();
  const { showToast } = useToast();
  const { session } = useAuth();
  // Sonuç + görüntü modül-cache'ten init → tab değişip geri gelince KAYBOLMAZ (yeni analize/hastaya kadar kalıcı).
  const [imageUri, setImageUri] = useState<string | null>(moduleCache.pet_owner?.imageUri ?? null);
  const [imageBase64, setImageBase64] = useState<string | null>(moduleCache.pet_owner?.imageBase64 ?? null);
  const [imageFile, setImageFile] = useState<any>(moduleCache.pet_owner?.imageFile ?? null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AiResult | null>(moduleCache.pet_owner?.result ?? null);
  const [treatmentStatus, setTreatmentStatus] = useState<string>("");
  const [longLoading, setLongLoading] = useState(false);
  useEffect(() => {
    if (!loading) { setLongLoading(false); return; }
    const t = setTimeout(() => setLongLoading(true), 8000);
    return () => clearTimeout(t);
  }, [loading]);
  // Cache'i güncel tut → unmount'ta (tab değişimi) sonuç/görüntü korunur. resetAiCachesForOwner (profil/hasta değişimi) temizler.
  useEffect(() => { moduleCache.pet_owner = { result, imageUri, imageBase64, imageFile }; }, [result, imageUri, imageBase64, imageFile]);

  // ── "KALDIĞIN YERDEN" (sahip isteği 2026-09-12, ev sahibi önerisi #2) ────────────
  // Ev sahibi uygulamayı "Mia'ya tekrar bakayım" diye açıyor. Seçili hastanın SON analizini
  // şeritte göstermek, "en son ne çıkmıştı?" sorusunu ekran değiştirmeden cevaplar.
  // ⚠️ YENİ BACKEND YOK: `/api/ai/log` hasta filtresini zaten destekliyor.
  // ⚠️ HATA SESSİZ: geçmiş okunamazsa şerit çizilmez; analiz ekranı ETKİLENMEZ.
  const { selectedPatient: secili } = useAppNav();
  // ⚠️ KİMLİK: `useOperatorOptional` — sağlayıcı yoksa giriş e-postasına düşer
  // (TreatmentHistoryScreen ile AYNI desen; `useOperator` sağlayıcısız FIRLATIR).
  const _op = useOperatorOptional();
  const benimEpostam = (_op ? _op.operatorEmail : (session?.email || "")).toLowerCase();
  const [sonKayit, setSonKayit] = useState<AnalizKaydi | null>(null);
  useEffect(() => {
    const ad = secili?.name || "";
    if (!ad) { setSonKayit(null); return; }
    let iptal = false;
    (async () => {
      // ⚠️ KİMLİK + AD BİRLİKTE: backend bunları VEYA ile bağlar → kimliği yazılmış YENİ
      // kayıtlar ile aynı hastanın ESKİ (kimliksiz) kayıtları TEK listede gelir. Yalnız
      // kimlikle sorsaydık taşıma öncesi geçmiş kaybolur, yalnız adla sorsaydık aynı adlı
      // ikinci hayvanın kayıtları karışırdı.
      const _kimlik = secili?.id ? `&patient_id=${encodeURIComponent(secili.id)}` : "";
      const y = await apiGet<{ data?: AnalizKaydi[] } | null>(
        `/ai/log?limit=20&patient_name=${encodeURIComponent(ad)}${_kimlik}`, null);
      if (iptal) return;
      // ⚠️ KAPSAM SÜZGECİ ŞART (denetim 2026-09-12, KENDİ EKLEMEMDE bulundu):
      // `/api/ai/log` operatör süzgeci DESTEKLEMİYOR — TÜM kliniğin analizlerini döndürür.
      // Ev sahibi profili kapsam olarak HER ZAMAN "mine"dır (KVKK kapısı,
      // utils/patientScope.effectiveScope); süzmeden göstermek, ev sahibine bir hekimin
      // analiz özetini sızdırırdı. TEK KAYNAK: patientScope.inScope.
      const kayitlar = (Array.isArray(y?.data) ? y!.data! : []).filter((k) =>
        kapsamda(k, effectiveScope("mine", { isExpert: false, isResearcher: false, operatorKayitli: (_op?.operators?.length ?? 0) > 0 }), benimEpostam));
      const harita = hastayaGoreSonAnaliz(kayitlar);
      setSonKayit(hastaninSonAnalizi(harita, { id: secili?.id, name: ad }) ?? null);
    })();
    return () => { iptal = true; };
    // ⚠️ `result` bağımlılıkta: yeni analiz bitince şerit KENDİNİ tazeler, yoksa bir
    // önceki sonucu göstermeye devam ederdi (kullanıcı "güncellenmedi" sanır).
  }, [secili?.name, secili?.id, result, benimEpostam]);

  const takePhoto = async () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = 'image/*';
      (input as any).capture = 'environment';
      input.onchange = (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0];
        if (file) {
          // `pickImage` bunu yapıyordu, `takePhoto` YAPMIYORDU: her yeni fotoğrafta önceki blob
          // URL'si serbest bırakılmadan yenisi oluşturuluyor, tam boyutlu görüntüler bellekte
          // birikiyordu (web istemcisi klinikte gün boyu açık kalır).
          if (imageUri && imageUri.startsWith("blob:")) URL.revokeObjectURL(imageUri);
          setResult(null); setTreatmentStatus("");
          // ⚠️ WEB KÜÇÜLTME (AI Hub planı, ADIM 1): web'de HİÇ küçültme yoktu → ham dosya
          // yükleniyor, aynı analiz platforma göre 8× farklı boyutta gidiyor ve backend'in
          // 1 MB multipart sınırına takılıyordu. `webIcinKucult` başarısızlıkta ORİJİNALİ
          // döndürür (fail-open) — küçültme bir optimizasyondur, kapı değil.
          void webIcinKucult(file).then((k) => { setImageFile(k); setImageUri(URL.createObjectURL(k)); });
        }
      };
      input.click();
    } else {
      let res = await ImagePicker.launchCameraAsync({ allowsEditing: true, quality: 0.7, base64: true });
      if (!res.canceled) {
        const shrunk = await shrinkForUpload(res.assets[0].uri);
        setImageUri(shrunk.uri);
        setImageBase64(shrunk.base64);
        setImageFile((res.assets[0] as any).file || null);
        setResult(null); setTreatmentStatus("");
      }
    }
  };

  const pickImage = async () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = 'image/*';
      input.onchange = (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0];
        if (file) {
          // BUG #3 FIX: Eski objectURL'yi revoke et, memory leak önlenir
          if (imageUri && imageUri.startsWith('blob:')) URL.revokeObjectURL(imageUri);
          setResult(null); setTreatmentStatus("");
          // ⚠️ WEB KÜÇÜLTME (AI Hub planı, ADIM 1): web'de HİÇ küçültme yoktu → ham dosya
          // yükleniyor, aynı analiz platforma göre 8× farklı boyutta gidiyor ve backend'in
          // 1 MB multipart sınırına takılıyordu. `webIcinKucult` başarısızlıkta ORİJİNALİ
          // döndürür (fail-open) — küçültme bir optimizasyondur, kapı değil.
          void webIcinKucult(file).then((k) => { setImageFile(k); setImageUri(URL.createObjectURL(k)); });
        }
      };
      input.click();
    } else {
      let res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, allowsEditing: true, quality: 0.7, base64: true });
      if (!res.canceled) {
        const shrunk = await shrinkForUpload(res.assets[0].uri);
        setImageUri(shrunk.uri);
        setImageBase64(shrunk.base64);
        setImageFile((res.assets[0] as any).file || null);
        setResult(null); setTreatmentStatus("");
      }
    }
  };

  const analyzeImage = async () => {
    const hasta = hastaAnligi(); // D2.E09 (Y87): kayıt analizin BAŞLADIĞI hastaya yazılır
    if (!imageUri) return;
    setLoading(true);
    try {
      const formData = new FormData();
      if (Platform.OS === 'web') {
        let blob = imageFile;
        if (!blob && imageBase64) {
          const bstr = atob(imageBase64);
          let n = bstr.length;
          const u8arr = new Uint8Array(n);
          while (n--) {
            u8arr[n] = bstr.charCodeAt(n);
          }
          blob = new Blob([u8arr], { type: 'image/jpeg' });
        } else if (!blob && imageUri && imageUri.startsWith('data:')) {
          const arr = imageUri.split(',');
          const mime = arr[0].match(/:(.*?);/)?.[1] || 'image/jpeg';
          const bstr = atob(arr[1]);
          let n = bstr.length;
          const u8arr = new Uint8Array(n);
          while (n--) {
            u8arr[n] = bstr.charCodeAt(n);
          }
          blob = new Blob([u8arr], { type: mime });
        } else if (!blob) {
          throw new Error("Web ortamında geçerli bir dosya bulunamadı.");
        }
        formData.append("file", blob, "camera_capture.jpg");
      } else {
        if (imageBase64) {
          formData.append("image_base64", imageBase64);
        } else {
          formData.append("file", { uri: imageUri, name: "camera_capture.jpg", type: "image/jpeg" } as any);
        }
      }
      // Zaman aşımı YOKTU: yarı-açık bağlantıda (tünel takılı / captive portal) fetch ne çözülür
      // ne reddedilir → `finally` hiç çalışmaz, buton sonsuza dek "Analiz Ediliyor…"da kilitlenirdi.
      const ctrl = new AbortController();
      const to = setTimeout(() => ctrl.abort(), AI_TIMEOUT_MS); // ilk kullanımda model yüklemesi uzun sürebilir
      let response: Response;
      try {
        response = await fetch(serviceConfig.apiBaseUrl + "/ai/vision/landmark", {
          method: "POST",
          body: formData,
          headers: { "Accept": "application/json", ...authHeaders() },
          signal: ctrl.signal,
        });
      } finally {
        clearTimeout(to);
      }
      const data = await response.json();
      if (response.ok && data.status === "success") {
        setResult(data);
        // AI Geçmişi'ne kaydet (Evcil Hayvan Sahibi FGS ağrı analizi de audit'e yazılsın — eskiden atlanıyordu).
        // ⚠️ D2.69 (B-6.29): seçili hastanın ADIYLA — eskiden "" yazılıyordu, ev sahibi geçmişinde hayvan ayrımı oluşmuyordu.
        logAiResult(hasta, "Ağrı Analizi (FGS)", summarizeVision(data), { moduleId: "landmark", inputType: "image", detail: data });
      } else {
        showToast(aiDetayCumlesi(data?.detail, t("ai.hata.teshisSirasinda")), "error");
      }
    } catch (error) {
      // Satır-içi AbortError ayrımı `aiHataMesaji`ye devredildi (2026-08-12): mesaj tek
      // kaynaktan gelsin. Eski metin "bağlantıyı kontrol edin" diyordu — zaman aşımında
      // bağlantı SAĞLAMDIR, yanıltıcıydı.
      showToast(aiHataMesaji(error, t("ai.hata.baglanti")), "error");
    } finally {
      setLoading(false);
    }
  };

  // NOT: Evcil Hayvan Sahibi profili YALNIZ ANALİZ yapar — otonom rahatlama terapisi (auto_preset)
  // buradan KALDIRILDI. Ev kullanıcısı cihaz sürmez; ağrı bulgusunda veteriner hekime yönlendirilir.

  return (
    <View style={styles.container}>
  {/* [S4 adım 3] İç dikey ScrollView KALDIRILDI: kabuk (AppShell) zaten tek kaydırıcı ve
  keyboardShouldPersistTaps='handled' taşıyor. İç ScrollView'ın yükseklik sınırı
  olmadığı için kendi kaydırmasını hiç üretmiyordu; ama klavye açıkken dokunuşu
  yutup 'Kaydet/Bağlan' düğmelerini İKİ dokunuş gerektiriyordu. */}
      <Card style={styles.card}>
        <View style={styles.cardHeader}>
          <Sparkles color={colors.primary} size={28} />
          <Text style={[styles.title, { fontSize: rf(24) }]}>{t("ai.hayvanSahibi.baslik")}</Text>
        </View>
        <Text style={styles.subtitle}>{t("ai.hayvanSahibi.aciklama")}</Text>

        {/* ⚠️ YALNIZ SONUÇ EKRANDA YOKKEN: analiz sonucu dururken "son analiz" şeridi
            göstermek, kullanıcının HANGİSİNE baktığını karıştırır. */}
        {!result && sonAnalizOzeti(sonKayit) ? (
          <View style={styles.kaldiginYerden} testID="pet-son-analiz">
            <Text style={styles.kaldiginYerdenBaslik} numberOfLines={1}>
              {t("ai.hayvanSahibi.sonAnaliz", { ad: secili?.name ?? "" })}
            </Text>
            <Text style={styles.kaldiginYerdenOzet} numberOfLines={3}>
              {sonAnalizOzeti(sonKayit)}
            </Text>
          </View>
        ) : null}

        {!imageUri ? (
          <>
            <View style={styles.photoGuide}>
              <Text style={styles.photoGuideTitle}>{t("ai.hayvanSahibi.netSonucIcin")}</Text>
              <Text style={styles.photoGuideItem}><Trans i18nKey="ai.hayvanSahibi.ipucuYuz" components={{ kalin: <Text style={styles.photoGuideBold} /> }} /></Text>
              <Text style={styles.photoGuideItem}>{t("ai.hayvanSahibi.ipucuIsik")}</Text>
              <Text style={styles.photoGuideItem}>{t("ai.hayvanSahibi.ipucuTekKedi")}</Text>
            </View>
            <View style={styles.actions}>
              <TouchableOpacity style={styles.bigActionBtn} onPress={takePhoto}>
                <Camera color="#fff" size={32} />
                <Text style={styles.bigActionText}>{t("ai.hayvanSahibi.kamerayiAc")}</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.secondaryActionBtn} onPress={pickImage}>
                <ImageIcon color={colors.primary} size={24} />
                <Text style={styles.secondaryActionText}>{t("ai.ortak.galeridenSec")}</Text>
              </TouchableOpacity>
            </View>
          </>
        ) : (
          <View style={{ gap: spacing.lg, marginTop: spacing.md }}>
            {/* ⚠️ ÖLÇÜLEN KAYIP (ADIM 4): bu ekran `/ai/vision/landmark` çağırıyor ve uç FGS
                işaretleriyle çizilmiş bir görsel döndürüyordu — ama burada YALNIZ yerel fotoğraf
                gösteriliyordu, işaretli kare hiç çizilmiyordu ("üretildi ama kimse görmedi").
                Galeri hem girdiyi hem işaretli sonucu erişilebilir kılar. */}
            <GorselSahne
              sayfalar={sahneSayfalari(result, imageUri)}
              tavanY={galeriH}
              sifirlaAnahtari={imageUri}
              testID="petowner-sahne"
            />
            <View style={{ flexDirection: 'row', gap: spacing.md }}>
              <View style={{ flex: 1 }}>
                {/* ⚠️ `setResult(null)` EKLENDİ: sonuç temizlenmeyince "Yeni Fotoğraf"a basıldığında
                    girdi gidiyor ama ALTTAKİ ESKİ TEŞHİS ekranda kalıyordu — hayvan sahibi, henüz
                    yüklemediği bir fotoğrafın sonucuna bakıyor sanıyordu. */}
                <Button variant="secondary" label={t("ai.hayvanSahibi.yeniFotograf")} onPress={() => { setImageUri(null); setImageBase64(null); setImageFile(null); setResult(null); }} />
              </View>
              <View style={{ flex: 1 }}>
                <Button variant="primary" label={loading ? t("ai.ortak.analizEdiliyor") : t("ai.hayvanSahibi.teshisEt")} onPress={() => analyzeImage()} disabled={loading} icon={loading ? <ActivityIndicator color="#fff" /> : <Sparkles color="#fff" size={16} />} />
              </View>
            </View>
          </View>
        )}

        {longLoading && <Text style={styles.modelHint}>{t("ai.hayvanSahibi.modelHazirlaniyor")}</Text>}

        {result && (() => {
          let recommendation = "";
          let requiresVet = false;
          const score = result.fgs_total;
          // GÜVENLİK: tespit yoksa (detected=false / score yok / <0) "ağrı yok" YANLIŞ güvencesi VERME.
          const notDetected = result.detected === false || score == null || score < 0;

          if (notDetected) {
            recommendation = t("ai.hayvanSahibi.oneri.tespitYok");
          } else if (score === 0) {
            recommendation = t("ai.hayvanSahibi.oneri.agriYok");
          } else if (score > 0 && score <= 3) {
            recommendation = t("ai.hayvanSahibi.oneri.hafif");
          } else if (score > 3 && score <= 5) {
            recommendation = t("ai.hayvanSahibi.oneri.orta");
          } else {
            recommendation = t("ai.hayvanSahibi.oneri.siddetli");
            requiresVet = true;
          }

          return (
            <View style={styles.petOwnerResult}>
              <Text style={styles.petOwnerResultTitle}>{t("ai.hayvanSahibi.sonucBaslik")}</Text>

              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.sm }}>
                <Text style={styles.body}>{t("ai.hayvanSahibi.agriSkoru")}</Text>
                <Text style={[styles.title, { color: notDetected ? colors.textMuted : score > 3 ? colors.danger : colors.success }]}>{notDetected ? "—" : `${score} / 10`}</Text>
              </View>
              {/* D1.E09 · 1-D inceleme i3-F-2: hekimsiz kullanıcıya örtülü yüzde uyarısız "ağrı yok" güvencesi verilmez. */}
              {!notDetected && result.nokta_gorunurlugu_dogrulanmadi ? (
                <Text style={[styles.body, { fontSize: typography.small, color: colors.textMuted, marginBottom: spacing.sm }]}>
                  {noktaGorunurluguUyarisi()}
                </Text>
              ) : null}

              <View style={[styles.recommendationBox, requiresVet && { backgroundColor: colors.danger + "22", borderColor: colors.danger }]}>
                <Text style={[styles.recommendationText, requiresVet && { color: colors.danger, fontWeight: 'bold' }]}>
                  {recommendation}
                </Text>

                {requiresVet && (
                  <TouchableOpacity
                    style={[styles.startTherapyBtn, { backgroundColor: colors.danger }]}
                    onPress={async () => {
                      // Klinik acil telefon: önce hesap profili (kayıtta girilir), yoksa eski AsyncStorage yedeği.
                      const fromProfile = session?.profile?.clinic_phone || "";
                      const legacy = fromProfile ? "" : ((await AsyncStorage.getItem("pemf_clinic_phone")) || "");
                      const phone = (fromProfile || legacy).replace(/\s/g, "");
                      if (phone) Linking.openURL(`tel:${phone}`).catch(() => {});
                      else platformAlert(t("ai.hayvanSahibi.klinikTelefonuYokBaslik"), t("ai.hayvanSahibi.klinikTelefonuYokGovde"));
                    }}
                  >
                    <Stethoscope color="#fff" size={20} />
                    <Text style={styles.startTherapyText}>{t("ai.hayvanSahibi.klinigiAra")}</Text>
                  </TouchableOpacity>
                )}
              </View>

              {treatmentStatus ? <Text style={[styles.statusText, { textAlign: 'center', marginTop: spacing.md }]}>{treatmentStatus}</Text> : null}
            </View>
          );
        })()}
      </Card>

      <View style={{ marginTop: spacing.xl }}>
        <PetOwnerSoundCard />
      </View>

      <View style={{ marginTop: spacing.xl }}>
        <DiseaseModule patientName={secili?.name || ""} />
      </View>
    </View>
  );
}

/** Kedi sesi tek sınıf → evcil hayvan sahibi için dostça yorum + ton (renk/aksiyon). */
const catSoundAdvice = (): Record<string, { emoji: string; title: string; text: string; tone: "positive" | "info" | "alert" | "pain" }> => ({
  Happy: { emoji: "😊", title: i18n.t("ai.ses.oneri.mutlu.baslik"), text: i18n.t("ai.ses.oneri.mutlu.metin"), tone: "positive" },
  Resting: { emoji: "😌", title: i18n.t("ai.ses.oneri.sakin.baslik"), text: i18n.t("ai.ses.oneri.sakin.metin"), tone: "positive" },
  MotherCall: { emoji: "🐱", title: i18n.t("ai.ses.oneri.anneCagrisi.baslik"), text: i18n.t("ai.ses.oneri.anneCagrisi.metin"), tone: "info" },
  Mating: { emoji: "💕", title: i18n.t("ai.ses.oneri.ciftlesme.baslik"), text: i18n.t("ai.ses.oneri.ciftlesme.metin"), tone: "info" },
  HuntingMind: { emoji: "🐾", title: i18n.t("ai.ses.oneri.avOyun.baslik"), text: i18n.t("ai.ses.oneri.avOyun.metin"), tone: "info" },
  Warning: { emoji: "⚠️", title: i18n.t("ai.ses.oneri.uyari.baslik"), text: i18n.t("ai.ses.oneri.uyari.metin"), tone: "alert" },
  Defence: { emoji: "🛡️", title: i18n.t("ai.ses.oneri.savunma.baslik"), text: i18n.t("ai.ses.oneri.savunma.metin"), tone: "alert" },
  Angry: { emoji: "😾", title: i18n.t("ai.ses.oneri.kizgin.baslik"), text: i18n.t("ai.ses.oneri.kizgin.metin"), tone: "alert" },
  Fighting: { emoji: "🙀", title: i18n.t("ai.ses.oneri.kavga.baslik"), text: i18n.t("ai.ses.oneri.kavga.metin"), tone: "alert" },
  Paining: { emoji: "😿", title: i18n.t("ai.ses.oneri.agri.baslik"), text: i18n.t("ai.ses.oneri.agri.metin"), tone: "pain" },
});

/**
 * PetOwnerSoundCard — evcil hayvan sahibi profili için "Sesini Dinleyelim" kartı.
 * Miyavı kaydet/yükle → POST /ai/sound/cat → tek sınıf → dostça ruh-hali yorumu (teknik bar YOK).
 * Ağrı (Paining) durumunda otonom rahatlama terapisi önerilir (foto/FGS akışıyla tutarlı).
 */
function PetOwnerSoundCard() {
  const { t } = useTranslation();
  const { showToast } = useToast();
  // D2.69: ses analizi de seçili hastanın adıyla kaydedilir.
  const { selectedPatient: secili } = useAppNav();
  const [audioUri, setAudioUri] = useState<string | null>(moduleCache.pet_owner_sound?.audioUri ?? null);
  const [fileName, setFileName] = useState<string>(moduleCache.pet_owner_sound?.fileName ?? "");
  const [webFile, setWebFile] = useState<any>(moduleCache.pet_owner_sound?.webFile ?? null);
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const [isRecording, setIsRecording] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AiResult | null>(moduleCache.pet_owner_sound?.result ?? null);
  const [treatmentStatus, setTreatmentStatus] = useState<string>("");
  // Sonuç tab değişince kaybolmasın (yeni kayda/hastaya kadar kalıcı) — modül-cache.
  useEffect(() => { moduleCache.pet_owner_sound = { result, audioUri, fileName, webFile }; }, [result, audioUri, fileName, webFile]);

  const startRecording = async () => {
    try {
      const perm = await requestRecordingPermissionsAsync();
      if (!perm.granted) { showToast(t("ai.ses.mikrofonIzni"), "error"); return; }
      await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
      setIsRecording(true); setResult(null); setAudioUri(null); setWebFile(null); setTreatmentStatus("");
    } catch (e) {
      showToast(t("ai.ses.kayitBaslatilamadi"), "error");
    }
  };

  const stopRecording = async () => {
    setIsRecording(false);
    try {
      await recorder.stop();
      setAudioUri(recorder.uri || null); setFileName("kayıt.m4a");
    } catch (e) {
      showToast(t("ai.ses.kayitDurdurulamadi"), "error");
    }
  };

  const pickAudio = async () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file'; input.accept = 'audio/*';
      input.onchange = (e: Event) => {
        const f = (e.target as HTMLInputElement).files?.[0];
        if (f) { setWebFile(f); setFileName(f.name); setAudioUri("web"); setResult(null); setTreatmentStatus(""); }
      };
      input.click();
    } else {
      const res = await DocumentPicker.getDocumentAsync({ type: ["audio/*"], copyToCacheDirectory: true });
      if (!res.canceled && res.assets?.[0]) {
        setAudioUri(res.assets[0].uri); setFileName(res.assets[0].name); setWebFile(null); setResult(null); setTreatmentStatus("");
      }
    }
  };

  const analyze = async () => {
    const hasta = hastaAnligi(); // D2.E09 (Y87): kayıt analizin BAŞLADIĞI hastaya yazılır
    if (!audioUri) return;
    setLoading(true);
    try {
      // ⚠️ Web'de CANLI KAYIT `webFile` üretmez (yalnız `blob:` URI) — eskiden burada
      // native dalına düşülüp `expo-file-system` çağrılıyor ve web'de çöküyordu. Yükleme
      // artık platform+veri'ye göre tek yerde kuruluyor (utils/sesYukleme).
      const formData = await sesFormDataHazirla(
        { webFile, uri: audioUri, fileName: fileName || "sound.mp3" },
        Platform.OS === "web",
        (uri) => FileSystemLegacy.readAsStringAsync(uri, { encoding: "base64" as any }),
      );
      const ctrl = new AbortController();
      const to = setTimeout(() => ctrl.abort(), AI_TIMEOUT_MS);
      const response = await fetch(serviceConfig.apiBaseUrl + "/ai/sound/cat", {
        method: "POST", body: formData, headers: { Accept: "application/json", ...authHeaders() }, signal: ctrl.signal,
      });
      clearTimeout(to);
      const data = await response.json();
      if (response.ok && data.status === "success") {
        setResult(data);
        logAiResult(hasta, "Kedi Sesi", `${trValue(data.top_1_class)} %${Math.round((data.top_1_prob || 0) * 100)}`, { moduleId: "cat_sound", inputType: "audio", detail: data, confidence: data.top_1_prob });
      } else {
        showToast(aiDetayCumlesi(data?.detail, t("ai.hata.analizSirasinda")), "error");
      }
    } catch (e) {
      showToast(aiHataMesaji(e, t("ai.hata.hataIleti", { ileti: errorMessage(e).slice(0, 120) })), "error");
    } finally {
      setLoading(false);
    }
  };

  // Evcil Hayvan Sahibi = YALNIZ ANALİZ: ses ağrı bulgusunda otonom terapi (auto_preset) KALDIRILDI;
  // ev kullanıcısı cihaz sürmez, veteriner hekime yönlendirilir.

  const advice = result ? (catSoundAdvice()[result.top_1_class ?? ""] || { emoji: "🐈", title: result.top_1_class ?? "", text: t("ai.ses.analizEdildi"), tone: "info" as const }) : null;
  const toneColor = advice ? (advice.tone === "positive" ? colors.success : advice.tone === "pain" ? colors.danger : advice.tone === "alert" ? colors.warning : colors.primary) : colors.primary;

  return (
    <Card style={styles.card}>
      <View style={styles.cardHeader}>
        <AudioLines color={colors.primary} size={28} />
        <Text style={[styles.title, { fontSize: rf(24) }]}>{t("ai.ses.baslik")}</Text>
      </View>
      <Text style={styles.subtitle}>{t("ai.ses.aciklama")}</Text>

      <View style={styles.soundStatusBox}>
        {isRecording ? (
          <View style={{ alignItems: "center" }}><View style={styles.recDot} /><Text style={styles.recText}>{t("ai.ses.kaydediliyor")}</Text></View>
        ) : audioUri ? (
          <View style={{ alignItems: "center" }}><AudioLines color={colors.primary} size={40} /><Text style={styles.soundFileName} numberOfLines={1}>🎵 {fileName}</Text></View>
        ) : (
          <View style={{ alignItems: "center" }}><Mic color={colors.textMuted} size={40} /><Text style={styles.placeholderText}>{t("ai.ses.kayitYok")}</Text></View>
        )}
      </View>

      <View style={styles.btnRow}>
        <View style={{ flex: 1 }}>
          <Button label={isRecording ? t("ai.ses.durdur") : t("ai.ses.kaydet")} variant={isRecording ? "danger" : "primary"} icon={isRecording ? <Square color={colors.white} size={16} /> : <Mic color={colors.white} size={16} />} onPress={isRecording ? stopRecording : startRecording} />
        </View>
        <View style={{ flex: 1 }}>
          <Button label={t("ai.ses.sesYukle")} variant="secondary" icon={<FileText color={colors.primary} size={16} />} onPress={pickAudio} disabled={isRecording} />
        </View>
      </View>

      <View style={{ marginTop: spacing.md }}>
        <Button variant="primary" label={loading ? t("ai.ortak.analizEdiliyor") : t("ai.ses.sesiAnalizEt")} icon={loading ? <ActivityIndicator color={colors.white} /> : <Sparkles color={colors.white} size={16} />} disabled={!audioUri || loading || isRecording} onPress={analyze} />
      </View>

      {advice && (
        <View style={styles.petOwnerResult}>
          <Text style={styles.petOwnerResultTitle}>{t("ai.ses.yorumBaslik")}</Text>
          {/* ⚠️ Model "kedi sesi yok" DİYEMEZ: 10 sınıfın hepsi kedi duygusu, softmax her
              girdiye mutlaka bir duygu atar. Sunucu belirsizliği ölçüp `guvenilir` alanıyla
              gönderiyor; emin olmadığında sonucu kesin bir bulgu gibi göstermiyoruz.
              (Reddetmiyoruz: ölçümde gerçek bir AĞRI kaydı da düşük güvendeydi — reddetmek
              ev sahibinin gerçek ağrıyı kaçırmasına yol açardı.) */}
          {result?.guvenilir === false && (
            <View style={styles.sesGuvenUyari}>
              <Text style={styles.sesGuvenUyariText}>
                {t("ai.ses.guvenilirDegil")}
              </Text>
            </View>
          )}
          <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.sm }}>
            <Text style={{ fontSize: rf(32) }}>{advice.emoji}</Text>
            <Text style={[styles.title, { color: toneColor, flex: 1 }]}>{advice.title}</Text>
          </View>
          <View style={[styles.recommendationBox, advice.tone === "pain" && { backgroundColor: colors.danger + "22", borderColor: colors.danger }]}>
            <Text style={[styles.recommendationText, advice.tone === "pain" && { color: colors.danger, fontWeight: "bold" }]}>{advice.text}</Text>
          </View>
          {treatmentStatus ? <Text style={[styles.statusText, { textAlign: "center", marginTop: spacing.md }]}>{treatmentStatus}</Text> : null}
        </View>
      )}
    </Card>
  );
}

/** Medikal sorumluluk reddi — her AI sonucunun altında gösterilir (karar-destek / yasal). */
function MedicalDisclaimer() {
  const { t } = useTranslation();
  return (
    <Text style={styles.disclaimer}>
      {t("ai.ortak.tibbiSorumlulukReddi")}
    </Text>
  );
}

/**
 * XaiIsiHaritasi — TÜM modüllerin ORTAK ısı haritası (Grad-CAM / EigenCAM / HiRes-CAM) sahnesi.
 *
 * B2-isi-haritasi-ui (2026-09-03, ölçüldü): heatmap <Image> eskiden `styles.imagePreview`
 * ({width:"100%", height:"100%"}) ile SABİT-yükseklikli `imagePreviewContainer`ın DIŞINDA,
 * otomatik-yükseklikli `resultBox` içinde çiziliyordu. Yüzde yükseklik yalnız ebeveyni sabitse
 * anlamlıdır: web'de (RNW ScrollView zinciri) resultBox'un KENDİ yüksekliğine çözülüp kutudan
 * taşıyor (ince şerit + alttaki karta sarkan kopya), belirsiz zincirde ise 0px'e çöküyordu.
 * Çözüm: görselin KENDİSİNE analiz sahnesiyle (imagePreviewContainer, rs(300)) birebir aynı
 * ölçüde AÇIK yükseklik ver → heatmap analiz görseliyle aynı boyut/hizada, konteynere sığar.
 * Ebeveyne bağımlılık yok (refaktörde başka kutuya taşınsa da bozulmaz).
 */
/**
 * AI1.X1 (hoca XAI v3, 2026-10): termal ısı haritası başlığı haritanın HANGİ KARARI açıkladığını söyler. Sunucu açıklanan
 * sınıfı `xai_hedef` ile döner (harita artık tahmin edilen sınıfın kanıtı; eskiden "Sağlıklı" sonuçta bile "Hasta"
 * kararının kanıtı gösteriliyordu). `xai_hedef` yoksa (retikülosit ya da eski sunucu) genel başlık kalır.
 */
function isiHaritasiBasligi(r: { xai_hedef?: string }): string {
  if (r.xai_hedef === "Healthy") {
    return i18n.t("ai.xai.isiHaritasiSaglikli");
  }
  if (r.xai_hedef === "Sick") {
    return i18n.t("ai.xai.isiHaritasiHasta");
  }
  return i18n.t("ai.xai.isiHaritasiGenel");
}

/**
 * AII-3.3 (AI incelemesi): canlı tespit 0 kutuyken tespit hedefli CAM (YoloDetCAM) eşik altı en güçlü 5 adaya düşer ve haritayı
 * maks'a ölçekler (harita boş dönmez) — bu harita tespitin ya da tanının kanıtı DEĞİLDİR. ONNX ↔ PT kutuları birebir ve iki eşik
 * de katı `> 0,25` olduğundan "ekranda 0 tespit" ⇔ "harita eşik altı adaylar".
 */
const tespitYokHaritaNotu = (): string => i18n.t("ai.xai.tespitYokNotu");

function XaiIsiHaritasi({ base64, etiket, not, testID }: { base64: string; etiket: string; not?: string; testID?: string }) {
  // [S1 adım 7 / aihub-10] Sahne yüksekliği CANLI: pencere küçülünce/cihaz yan yatınca daralır.
  const sahneH = useStageHeight();
  return (
    <>
      <Text style={styles.ctSubLabel}>{etiket}</Text>
      <Image
        testID={testID ?? "xai-isi-haritasi"}
        accessibilityLabel={etiket}
        source={{ uri: `data:image/jpeg;base64,${base64}` }}
        style={[styles.xaiStage, { height: sahneH }]}
        resizeMode="contain"
      />
      {not ? <Text style={styles.ctHint}>{not}</Text> : null}
    </>
  );
}

type InterpTone = "positive" | "info" | "alert" | "critical";
const TONE_COLOR: Record<InterpTone, string> = {
  positive: colors.success, info: colors.primary, alert: colors.warning, critical: colors.danger,
};

/**
 * AI PRO KÖPRÜSÜ (Faz 3) — "bu hedefi analiz ettim, şimdi seans yapmak istiyorum".
 *
 * Araştırmacı fantom/petri ANALİZİNİ burada yapar; otonom seans YALNIZ Kontrol → AI Pro
 * panelinde (propose → onay → start) başlar. Bu düğme o yolu KISALTIR: Kontrol'e geçer ve model
 * kartını ön-seçer.
 *
 * ⚠️ HİÇBİR `/ai/pro/*` ÇAĞRISI YAPMAZ. Bu ekrandan otonom başlatma denemesi 2026-08-17
 * denetiminde kaldırıldı (onay kapısı olmadan `/start` çağrılıyordu; eski bir backend'e karşı
 * ONAYSIZ seans başlatabilirdi). Kapı: src/screens/__tests__/aiHubOtonomOnayKapisi.test.tsx
 */
function AiProKopruDugmesi({ model }: { model: "fantom" | "petri" }) {
  const { t } = useTranslation();
  const { navigateTo, setAiProModeli } = useAppNav();
  // dal başına SABİT anahtar (K-3: iç içe dinamik t() yok)
  const hedef = model === "fantom" ? t("ai.kopru.hedefFantom") : t("ai.kopru.hedefPetri");
  return (
    <TouchableOpacity
      style={styles.aiProKopru}
      onPress={() => {
        setAiProModeli(model);   // Kontrol ekranındaki AI Pro paneli kartı seçili açar
        navigateTo("control");
      }}
      accessibilityRole="button"
      accessibilityLabel={t("ai.kopru.etiket", { hedef })}
      accessibilityHint={t("ai.kopru.ipucu")}
    >
      <Text style={styles.aiProKopruMetin}>{t("ai.kopru.metin")}</Text>
    </TouchableOpacity>
  );
}

/**
 * ResultInterpretation — her AI sonucunun EN ÜSTÜNE konan düz-dil yorum banner'ı.
 * Rakam/sınıf yerine "ne anlama geliyor + ne yapmalı" der; tona göre renklenir.
 * `points` (opsiyonel): kısa madde-işaretli açıklamalar (nasıl okunur / öneriler).
 */
function ResultInterpretation({ tone, title, text, emoji, points }: {
  tone: InterpTone; title: string; text: string; emoji?: string; points?: string[];
}) {
  const c = TONE_COLOR[tone];
  return (
    <View style={[styles.interpBox, { backgroundColor: c + "14", borderColor: c }]}>
      <Text style={[styles.interpTitle, { color: c }]}>{emoji ? `${emoji} ` : ""}{title}</Text>
      <Text style={styles.interpText}>{text}</Text>
      {points && points.length > 0 && (
        <View style={{ marginTop: 6, gap: 2 }}>
          {points.map((p, i) => (
            <Text key={i} style={styles.interpPoint}>• {p}</Text>
          ))}
        </View>
      )}
    </View>
  );
}

/** Sunum-katmanı XAI (2026-08-26): backend SHAP özellik adları → kullanıcı diline. */
// Backend SHAP özellik kimliği → katalog ANAHTARI (K-7: aiDetail.ts ile aynı desen; gösterimde `diseaseFeatureAdi` çevirir).
const DISEASE_FEATURE_TR: Record<string, string> = {
  Age: "hasta.form.yasEtiketi",
  Weight: "ai.hastalik.form.kilo",
  Heart_Rate: "ai.hastalik.form.nabiz",
  Body_Temperature: "ai.hastalik.form.ates",
  Duration_days: "ai.hastalik.ozellik.sikayetSuresi",
  Appetite_Loss_bin: "ai.hastalik.ozellik.istahKaybi",
  Vomiting_bin: "ai.hastalik.semptom.kusma",
  Diarrhea_bin: "ai.hastalik.semptom.ishal",
  Coughing_bin: "ai.hastalik.semptom.oksuruk",
  Labored_Breathing_bin: "ai.hastalik.ozellik.zorSolunum",
  Lameness_bin: "ai.hastalik.ozellik.topallama",
  Skin_Lesions_bin: "ai.hastalik.ozellik.deriLezyonu",
  Nasal_Discharge_bin: "ai.hastalik.ozellik.burunAkintisi",
  Eye_Discharge_bin: "ai.hastalik.ozellik.gozAkintisi",
  has_Lethargy: "ai.hastalik.ozellik.halsizlik",
  has_Weight_Loss: "ai.hastalik.ozellik.kiloKaybi",
  has_Sneezing: "ai.hastalik.ozellik.hapsirik",
  has_Dehydration: "ai.hastalik.semptom.dehidrasyon",
  has_Fever: "ai.hastalik.ozellik.atesSemptom",
};
// Bilinmeyen özellik kimliği HAM gösterilir (eski davranış: `?? f`). Dinamik anahtar → i18n/dinamik-anahtarlar.json (kapalı küme).
const diseaseFeatureAdi = (f: string): string => {
  const k = DISEASE_FEATURE_TR[f];
  return k ? i18n.t(k as never) : f;
};

type DiseaseXai = { disease?: string; top_features?: { feature: string; attribution: number }[] } | null;

/** Ortak XAI satırı: "🔍 Kararı sürükleyenler: Öksürük ↑ · Süre ↑ · Nabız ↓" (↑ tahmin lehine). */
function XaiSatiri({ xai, etiketle }: { xai: DiseaseXai; etiketle: (f: string) => string }) {
  const { t } = useTranslation();
  if (!xai?.top_features?.length) return null;
  const metin = xai.top_features
    .slice(0, 5)
    .map((oz) => `${etiketle(oz.feature)} ${oz.attribution >= 0 ? "↑" : "↓"}`)
    .join(" · ");
  return <Text style={styles.xaiSatiri}>{t("ai.xai.kararSurukleyenler", { metin })}</Text>;
}

function DiseaseModule({ patientName }: { patientName: string }) {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DiseasePrediction[] | null>(moduleCache.disease?.result ?? null);
  const [xai, setXai] = useState<DiseaseXai>(moduleCache.disease?.xai ?? null);
  const [form, setForm] = useState(moduleCache.disease?.form ?? { age: "", weight: "", hr: "", temp: "", duration: "" });
  const [selectedSymptoms, setSelectedSymptoms] = useState<number[]>(moduleCache.disease?.symptoms ?? []);
  const [resultUsedDefaults, setResultUsedDefaults] = useState<boolean>(moduleCache.disease?.usedDefaults ?? false);
  useEffect(() => { moduleCache.disease = { result, xai, form, symptoms: selectedSymptoms, usedDefaults: resultUsedDefaults }; }, [result, xai, form, selectedSymptoms, resultUsedDefaults]);

  const toggleSymptom = (idx: number) => {
    if (selectedSymptoms.includes(idx)) setSelectedSymptoms(selectedSymptoms.filter(i => i !== idx));
    else setSelectedSymptoms([...selectedSymptoms, idx]);
  };

  const analyze = async () => {
    const hasta = hastaAnligi(); // D2.E09 (Y87): kayıt analizin BAŞLADIĞI hastaya yazılır
    if (selectedSymptoms.length < 2) {
      showToast(t("ai.hastalik.enAz2Semptom"), "error");
      return;
    }
    // Girdi aralık validasyonu (boş alanlar serbest; doluysa makul aralıkta olmalı).
    const ranges: Record<string, [number, number, string]> = {
      age: [0, 40, t("hasta.form.yasEtiketi")], weight: [0, 80, t("ai.hastalik.form.kilo")], hr: [0, 400, t("ai.hastalik.form.nabiz")],
      temp: [25, 46, t("ai.hastalik.form.ates")], duration: [0, 3650, t("kontrol.sinir.sure")],
    };
    for (const k of Object.keys(ranges)) {
      const raw = (form as any)[k];
      if (raw !== "" && raw != null) {
        const n = Number(raw);
        const [lo, hi, label] = ranges[k];
        if (isNaN(n) || n < lo || n > hi) {
          showToast(t("ai.hastalik.gecersizAralik", { label, lo, hi }), "error");
          return;
        }
      }
    }
    // Vitaller ZORUNLU DEĞİL — sadece semptomla da tahmin çalışır (min 2 semptom yeterli).
    // Ancak modele SIFIR vital vermek yanıltıcı sonuç üretir (0 kg/0°C canlı bir kedide olamaz;
    // ölçeklemede aşırı-uç değere düşer → çöp tahmin). Bu yüzden boş bırakılan vitaller yerine
    // SAĞLIKLI KEDİ NORMALLERİNİ gönderiyoruz: model o zaman semptom-temelli doğru tahmin verir.
    // Kullanıcı gerçek nabız/ateş/kilo girerse ayırt edicilik artar (ör. ateşli sindirim →
    // gastroenterit yerine panleukopeni). Not: normal-default'lar backend'in vital validasyonunu
    // (0<x aralık) geçtiği için 422 alınmaz.
    const usedDefaults = !form.weight || !form.hr || !form.temp;
    setLoading(true);
    const res = await apiPost<any>("/ai/disease", {
      age: parseFloat(form.age) || 3,        // yetişkin kedi ortalaması
      weight: parseFloat(form.weight) || 4,  // normal yetişkin kedi ~4 kg
      hr: parseFloat(form.hr) || 140,        // normal kedi nabzı ~120-140 bpm
      temp: parseFloat(form.temp) || 38.5,   // normal kedi vücut sıcaklığı ~38.5 °C
      duration: parseFloat(form.duration) || 3,
      symptom_indices: selectedSymptoms.map(i => i + 1),
      // Sunum-katmanı XAI (2026-08-26): TreeExplainer ms-hızlı → her analizde iste;
      // hata/eski-backend'de alan gelmez, satır gizlenir (zarif düşüş).
      explain: true
      // AI_TIMEOUT_MS: apiPost'un varsayılan 8sn'si AI ÇIKARIMI için çok kısa. Modeller gecikmeli
      // yüklenir; ölçüm (soğuk backend): /ai/disease ilk çağrı 3.2sn, /ai/sound/cat ilk çağrı 28sn.
      // Eşzamanlı ikinci bir analizle CPU çekişmesinde 8sn rahatça aşılıyor → istek SESSİZCE iptal
      // ediliyor ve sonuç boş görünüyordu; ikinci denemede model artık bellekte olduğu için anında
      // çalışıyordu (kullanıcı bildirimi 2026-08-06).
    }, { status: "error" }, { timeoutMs: AI_TIMEOUT_MS });
    setLoading(false);
    if (res.status === "success") {
      setResult(res.results);
      setXai(res.xai ?? null); // sunum-katmanı XAI (alan yoksa satır gizli)
      setResultUsedDefaults(usedDefaults);
      const top = res.results?.[0];
      logAiResult(hasta, "Hastalık Analizi", top ? `${trValue(top.disease)} (%${(top.probability * 100).toFixed(0)})` : "Belirgin sonuç yok", { moduleId: "disease", inputType: "clinical", detail: res, confidence: top?.probability });
    }
    // Hata durumunda apiClient zaten kullanıcıya bildirim gösterir (çift-popup önlendi).
  };

  return (
    <Card style={styles.card}>
      <Text style={styles.title}>{t("ai.hastalik.baslik")}</Text>
      <ResponsiveGrid minItemWidth={150}>
        <TextInput style={styles.input} placeholder={t("hasta.form.yasEtiketi")} accessibilityLabel={t("hasta.form.yasEtiketi")} keyboardType="numeric" value={form.age} onChangeText={t => setForm({...form, age: t})} />
        <TextInput style={styles.input} placeholder={t("ai.hastalik.form.kilo")} accessibilityLabel={t("hasta.form.kiloEtiketi")} keyboardType="numeric" value={form.weight} onChangeText={t => setForm({...form, weight: t})} />
        <TextInput style={styles.input} placeholder={t("ai.hastalik.form.nabiz")} accessibilityLabel={t("ai.hastalik.form.nabizEtiketi")} keyboardType="numeric" value={form.hr} onChangeText={t => setForm({...form, hr: t})} />
        <TextInput style={styles.input} placeholder={t("ai.hastalik.form.ates")} accessibilityLabel={t("ai.hastalik.form.atesEtiketi")} keyboardType="numeric" value={form.temp} onChangeText={t => setForm({...form, temp: t})} />
        <TextInput style={styles.input} placeholder={t("kontrol.sinir.sure")} accessibilityLabel={t("ai.hastalik.form.sureEtiketi")} keyboardType="numeric" value={form.duration} onChangeText={t => setForm({...form, duration: t})} />
      </ResponsiveGrid>
      <Text style={styles.diseaseHint}>
        {t("ai.hastalik.ipucu")}
      </Text>
      <View style={styles.symptomsGrid}>
        {semptomlar().map((s, idx) => (
          <TouchableOpacity key={idx} style={[styles.symptomBtn, selectedSymptoms.includes(idx) && styles.symptomBtnActive]} onPress={() => toggleSymptom(idx)}>
            <Text style={[styles.symptomLabel, selectedSymptoms.includes(idx) && styles.symptomLabelActive]}>{s}</Text>
          </TouchableOpacity>
        ))}
      </View>
      <View style={{ marginTop: spacing.sm }}>
        <Button variant="primary" label={loading ? t("ai.ortak.analizEdiliyor") : t("ai.hastalik.teshisiBaslat")} onPress={analyze} disabled={loading} />
      </View>

      {result && (
        <View style={styles.resultBox}>
          {result.length === 0 ? (
            <ResultInterpretation tone="info" emoji="🔍" title={t("ai.hastalik.sonuc.eslesmeYok")}
              text={t("ai.hastalik.sonuc.eslesmeYokMetin")} />
          ) : (
            <>
              {(() => {
                const top = result[0];
                const pct = Math.round(top.probability * 100);
                const strong = top.probability > 0.6;
                return (
                  <ResultInterpretation
                    tone={strong ? "alert" : "info"} emoji="🩺"
                    title={t("ai.hastalik.sonuc.enOlasi", { disease: top.disease, pct })}
                    text={strong
                      ? t("ai.hastalik.sonuc.uyumlu", { disease: top.disease, pct })
                      : t("ai.hastalik.sonuc.birdenCok", { disease: top.disease, pct })}
                    points={[t("ai.hastalik.sonuc.yuzdeNotu"), t("ai.hastalik.sonuc.siralamaNotu")]}
                  />
                );
              })()}
              <Text style={styles.ctSubLabel}>{t("ai.hastalik.sonuc.tumOlasiliklar")}</Text>
              {result.map((r, i) => (
                <View key={i} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: spacing.xs }}>
                  <Text style={[styles.resultText, { flex: 1 }]}>{i + 1}. {r.disease}</Text>
                  <Text style={[styles.resultText, { fontWeight: 'bold', color: r.probability > 0.6 ? colors.danger : r.probability > 0.3 ? colors.warning : colors.textMuted }]}>
                    {t("ai.ortak.yuzde", { deger: (r.probability * 100).toFixed(1) })}
                  </Text>
                </View>
              ))}
              <XaiSatiri xai={xai} etiketle={(f) => diseaseFeatureAdi(f)} />
            </>
          )}
          {resultUsedDefaults && result.length > 0 && (
            <Text style={styles.diseaseDefaultsNote}>
              {t("ai.hastalik.varsayilanVital")}
            </Text>
          )}
          <MedicalDisclaimer />
        </View>
      )}
    </Card>
  );
}

// Tab değişiminde (VisionModule unmount olur) foto/sonuç kaybolmasın diye modül-seviyesi cache.
const visionCache: Record<string, { imageUri: string | null; imageBase64: string | null; result: any }> = {};
// Görüntü-dışı modüller (form/CSV/ses) için sonuç+girdi kalıcılığı: modül kapanıp açılınca
// (akordeon) veya tab değişiminde sonuç KORUNUR; yeni analiz/girdi başlatana ya da app kapanana kadar.
const moduleCache: Record<string, any> = {};

// KRİTİK (yanlış-hasta + KVKK): Yukarıdaki cache'ler modül/endpoint-anahtarlı — HASTA-anahtarlı DEĞİL.
// aiCacheOwner cache'in hangi (profil+hasta)ya ait olduğunu izler. Sahip değişince cache TEMİZLENİR:
// yoksa önceki hastanın tıbbi görüntüsü/formu yeni hastada geri gelir, Analiz'e basınca stale görüntü
// gönderilir ama sonuç GÜNCEL (yanlış) hastaya yazılır; ayrıca base64 görüntüler bellekte/ekranda kalır.
// Aynı sahip içinde (aynı hastada ekranlar arası gidiş-geliş) cache KORUNUR (gereksiz temizleme yok).
let aiCacheOwner: string | null = null;
function resetAiCachesForOwner(owner: string | null): boolean {
  if (aiCacheOwner === owner) return false;
  // Web'de `imageUri` bir blob: URL'si olabilir. Cache girdisini silmek blob'u serbest BIRAKMAZ →
  // her hasta/profil değişiminde tam boyutlu tıbbi görüntüler bellekte kalıcı olarak birikiyordu.
  const revoke = (u: unknown) => {
    if (typeof u === "string" && u.startsWith("blob:")) {
      try { URL.revokeObjectURL(u); } catch { /* ignore */ }
    }
  };
  for (const k of Object.keys(visionCache)) { revoke(visionCache[k]?.imageUri); delete visionCache[k]; }
  for (const k of Object.keys(moduleCache)) { revoke(moduleCache[k]?.imageUri); delete moduleCache[k]; }
  aiCacheOwner = owner;
  return true;
}

/**
 * CANLI KAMERA KUTUSU — SG.G6 (sahip: "fgs de canlı kamera açınca görüntü soluk görünüyor sanki").
 * ⚠️ Eskiden analiz edilmiş karenin TAMAMI canlı önizlemenin üstüne `opacity: 0.8` ile biniyordu (`styles.cameraOverlay`):
 * (a) canlı akış %20 sızıyor → soluk / hayalet; (b) bindirilen kare saniyeler eski → hareketle çift görüntü; (c) web'de ön kamera
 * önizlemesi AYNALI, sunucu karesi aynasız → yazılar ve noktalar ters tarafta; (d) `contain` ↔ kamera `cover` ölçek farkı.
 * Artık iki görüntü ASLA yarı saydam üst üste binmez: son analiz karesi (noktalar / maske SUNUCUNUN çizdiği yerde, aynasız) OPAK
 * ve kutunun tamamında; canlı önizleme köşede küçük pencere (nişan almak için). İlk sonuç gelene dek canlı önizleme tam kutu. Son
 * karenin yaşı görünür ("Son analiz 1,8 sn önce"). `CameraView` hep aynı ağaç konumunda kalır (yeniden bağlanmaz; kare yakalama
 * önizleme boyutundan bağımsızdır).
 */
function CanliKameraKutusu({ cameraRef, facing, onFlip, sonKareB64, sonKareYasMs, rozet }: {
  cameraRef: MutableRefObject<any>; facing: "back" | "front"; onFlip: () => void;
  sonKareB64: string | null; sonKareYasMs: number | null; rozet: string;
}) {
  const { t } = useTranslation();
  const yas = sonKareB64 && sonKareYasMs != null ? (Math.max(0, sonKareYasMs) / 1000).toFixed(1).replace(".", i18n.language === "en" ? "." : ",") : null;
  return (
    <View style={styles.cameraContainer}>
      {sonKareB64 ? (
        <Image
          source={{ uri: `data:image/jpeg;base64,${sonKareB64}` }}
          style={styles.canliSonKare}
          resizeMode="contain"
          testID="canli-son-kare"
          accessibilityLabel={t("ai.canli.sonKare")}
        />
      ) : null}
      <View style={sonKareB64 ? styles.canliOnizlemeKose : styles.canliOnizlemeTam} testID={sonKareB64 ? "canli-onizleme-kose" : "canli-onizleme-tam"}>
        <CameraView ref={cameraRef} style={styles.cameraView} facing={facing} />
      </View>
      <TouchableOpacity style={styles.flipCameraBtn} onPress={onFlip} accessibilityRole="button" accessibilityLabel={t("ai.canli.kamerayiCevir")}>
        <SwitchCamera color={colors.white} size={20} />
      </TouchableOpacity>
      <View style={styles.liveIndicator}>
        <View style={styles.liveDot} />
        <Text style={styles.liveText}>{rozet}</Text>
      </View>
      {yas != null ? (
        <View style={styles.canliYasEtiketi}>
          <Text style={styles.liveText} testID="canli-son-kare-yasi">{t("ai.canli.sonAnaliz", { sn: yas })}</Text>
        </View>
      ) : null}
    </View>
  );
}

/** SG.G5: son canlı karenin durumu — SÜREKLİ görünür satır (toast yağmuru yok); metin backend yanıtından (`utils/canliKare`). */
function CanliDurumSatiri({ durum, jeton }: { durum: CanliDurum; jeton?: number | null }) {
  const uyari = durum.tur === "red" || durum.tur === "hata";
  return (
    <>
      <Text
        style={[styles.canliDurum, uyari ? styles.canliDurumUyari : durum.tur === "bulunamadi" ? styles.canliDurumBilgi : null]}
        accessibilityLiveRegion="polite"
        testID="canli-durum"
      >
        {durum.metin}
      </Text>
      {/* TD9 [ÖNERİLEN]: ücretlendirme etkinken canlı oturumun jetonu (dakika başına). */}
      {typeof jeton === "number" ? (
        <Text style={[styles.canliDurum, styles.canliDurumBilgi]} testID="canli-jeton">
          {canliJetonMetni(jeton)}
        </Text>
      ) : null}
    </>
  );
}

/** TD9: canlı kip açıkken ücretlendirme ETKİN mi (sayaç yalnız o zaman); okunamazsa sayaç gösterilmez. */
function useCanliJetonEtkin(canli: boolean): boolean {
  const [etkin, setEtkin] = useState(false);
  useEffect(() => {
    if (!canli) return;
    let iptal = false;
    jetonBakiyesiGetir()
      .then((b) => {
        if (!iptal) setEtkin(Boolean(b?.etkin));
      })
      .catch(() => undefined);
    return () => {
      iptal = true;
    };
  }, [canli]);
  return etkin;
}

/** AI geçmişi kaydına (`ai_analyses.module`) giden modül adı — VERİ: dilden bağımsız TR kalır (EN ekranda da aynı kayıt). `title` ÇEVRİLMİŞ gösterim
 *  metnidir, kayda GİTMEZ; geçmişte gösterimde değer → anahtar eşlemesi 06c / 07b'de. Kapı: `aiHubScreen.I18N.P1` (EN iken giden kayıt TR ile BAYT BAYT aynı). */
const MODUL_KAYIT_ADI: Record<string, string> = {
  "/vision/landmark": "Yüz Ağrısı Skoru (FGS)",
  "/vision/segmentation": "Kedi Segmentasyonu",
  "/vision/thermal": "Termal Görüntü Analizi",
  "/vision/reticulocytes": "Retikülosit Sayımı",
};

function VisionModule({ endpoint, title, subtitle, patientName, galleryOnly, explainDestegi }: { endpoint: string, title: string, subtitle: string, patientName: string, galleryOnly?: boolean, explainDestegi?: boolean }) {
  const { t } = useTranslation();
  // [S1 adım 7 / aihub-10] Sahne yüksekliği CANLI: pencere küçülünce/cihaz yan yatınca daralır.
  const sahneH = useStageHeight();
  // Galeri ASIL okuma yuzeyi: daha yuksek tavan, AYNI responsive oran (bkz. useGaleriYuksekligi).
  const galeriH = useGaleriYuksekligi();
  // [S7 adım 5 / aihub-1] ÖNİZLEME KUTUSU ORAN KİLİDİ. Kutu sabit yükseklikteydi ve canlı
  // kamera ile üzerine bindirilen sunucu overlay'i farklı ölçeklerde oturuyordu: organ işaretleri
  // görüntüyle KAYIYORDU (tıbbi karar ekranı). Kutu artık karenin GERÇEK oranında açık px.
  const [onizlemeW, setOnizlemeW] = useState(0);
  const { width: pencereX, height: pencereY } = useResponsive();
  const { showToast } = useToast();
  const { realtime } = useEntitlement();
  const [imageUri, setImageUri] = useState<string | null>(visionCache[endpoint]?.imageUri ?? null);
  const [imageBase64, setImageBase64] = useState<string | null>(visionCache[endpoint]?.imageBase64 ?? null);
  const [imageFile, setImageFile] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  /** Sunum-katmanı XAI (Faz 2, 2026-08-26): opt-in Grad-CAM ısı haritası — CPU'da sn'ler
   *  sürebildiği için OTOMATİK DEĞİL; yalnız manuel analizde ve destekleyen uçlarda. */
  const [isiHaritasi, setIsiHaritasi] = useState(false);
  const [result, setResult] = useState<AiResult | null>(visionCache[endpoint]?.result ?? null);
  const onizlemeKutu =
    onizlemeW > 0 ? kameraKutusu(onizlemeW, kareOrani(result, pencereY > pencereX), pencereY, 0.55) : null;

  const [isLive, setIsLive] = useState(false);
  // BUG FIX: Canlı kamera varsayılan olarak ARKA ('back') kamera (kediyi çekmek için);
  // selfie/ön kamera açılmasını engeller. Flip butonu ile ön↔arka geçiş yapılabilir.
  const [facing, setFacing] = useState<"back" | "front">("back");
  const [autoAdjust, setAutoAdjust] = useState(false);
  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<any>(null);
  // SG.G5 / G6: son canlı karenin durumu (sürekli görünür) + son analiz karesinin zamanı (yaş etiketi).
  const [canliDurum, setCanliDurum] = useState<CanliDurum | null>(null);
  // TD9 (Y148): canlı oturumun dakika-başı jetonu (sayaç yalnız ücretlendirme etkinken).
  const [canliJeton, setCanliJeton] = useState(0);
  const canliJetonEtkin = useCanliJetonEtkin(isLive && !autoAdjust);
  const [sonKareZamani, setSonKareZamani] = useState<number | null>(null);
  const [simdi, setSimdi] = useState(() => Date.now());
  // BUG #2 FIX: loading state'ini useRef ile takip et, döngü closure'u her zaman güncel değeri okur
  const loadingRef = useRef(false);
  const autoAdjustRef = useRef(autoAdjust);
  const { aiVisionData, aiVisionFresh } = useLiveData();
  const { isCompact } = useResponsive();

  useEffect(() => {
    autoAdjustRef.current = autoAdjust;
  }, [autoAdjust]);

  // Unmount'ta uçuştaki CANLI kare analizi iptal edilir; mountedRef await-sonrası setState'leri kapılar.
  // ⚠️ D2.E09 (Y87): uçuştaki MANUEL analiz İPTAL EDİLMEZ — eskiden iptal edilip atılıyordu (sahip "atılmaz" dedi); sonuç
  // analizin BAŞLADIĞI hastaya kaydedilir (`hasta` görüntüsü), yalnız ekran güncellenmez. Yanlış hastaya yazma görüntüyle
  // kapandığı için iptale gerek kalmadı.
  const mountedRef = useRef(true);
  /** Canlı kamera döngüsündeki uçuştaki kare analizi (unmount'ta iptal edilir). */
  const liveAbortRef = useRef<AbortController | null>(null);
  useEffect(() => () => {
    mountedRef.current = false;
    try { liveAbortRef.current?.abort(); } catch { /* ignore */ }
  }, []);

  // Foto/sonuç'u cache'e yaz → tab değişip geri dönünce korunur (tekrar yükleme gerekmez).
  useEffect(() => {
    visionCache[endpoint] = { imageUri, imageBase64, result };
  }, [endpoint, imageUri, imageBase64, result]);

  // ── P0 (hasta güvenliği): otonom mod yaşam döngüsü ────────────────────────────────────────────
  // ESKİDEN: bu effect mount'ta (isLive=false, autoAdjust=false) ELSE dalına düşüp KOŞULSUZ
  // POST /ai/pro/stop atıyordu. Backend'deki stop_ai_pro (servers/ai_router.py) AI Pro çalışıyor mu
  // diye BAKMADAN `_stop_session_coils(range(1,9))` çağırır → 8 bobine donanım STOP. VisionModule
  // FGS/Segmentasyon/Termal/Retikülosit modüllerinin HEPSİNDE mount olduğundan, süren bir
  // Manuel/Otomatik tedavi sırasında "Akıllı Teşhis"te herhangi bir modülü açmak tedaviyi KESİYORDU.
  // Üstelik backend `_active_session`'ı yalnız mode "AI" ile başlıyorsa kapattığı için sunucu seansı
  // "aktif" kalıyor, useSessionControl reconcile'ı bunu okuyup UI'da geri saymaya devam ediyordu
  // (bobinler ölüyken "tedavi sürüyor" görüntüsü) — mümkün olan en kötü kombinasyon.
  // ⚠️ OTONOM BİOFEEDBACK BU EKRANDAN BAŞLATILAMAZ (denetim 2026-08-17, bulgu 21).
  //
  // 2026-08-06'da eklenen SERT ONAY KAPISI `/ai/pro/start`'ı onaylanmış bir `proposal_id` ile
  // ZORUNLU kıldı (`servers/ai_router.py` → `ai_approval.consume` → 428). Bu ekran gövdeyi `{}`
  // ile gönderiyordu, yani istek HER ZAMAN 428 dönüyordu: otonom seans HİÇ başlamıyor, ama
  // ekrandaki toggle AÇIK kalıyor ve ekranın kendi toast'ı YANLIŞ sebebi söylüyordu
  // ("kamera/model erişilemedi" — gerçek sebep: hekim onayı yok). Üstüne, aynı bloktaki
  // watchdog `setInterval`'ı HİÇ kurulmuyordu (`startedByUsRef` yalnız `.then()` içinde
  // atanıyor, ref ataması re-render tetiklemez ve dep dizisi değişmez) → ölü koruma.
  //
  // ⚠️ SÜRÜM KAYMASI RİSKİ, DÜZELTMENİN ASIL GEREKÇESİ: onay kapısından ÖNCEKİ bir backend
  // EXE'sine bağlanan yeni bir mobil sürümde bu start BAŞARILI olur ve ONAYSIZ otonom tedavi
  // başlatır — yani kapı istemci tarafından atlatılır. Bu yüzden çağrı KALDIRILDI, "düzeltilmedi".
  //
  // ⚠️ Onay akışı (propose → approve → start) YALNIZ Kontrol → AI Pro panelinde var; kullanıcı
  // oraya YÖNLENDİRİLİR. Toggle açık BIRAKILMAZ ve mesaj DOĞRU sebebi söyler.
  // ⚠️ `autoAdjustRef` KALDI: manuel-analiz sürüş yolu onu ayrıca okuyor.
  useEffect(() => {
    if (!(isLive && autoAdjust)) return;
    // ⚠️ Effect gövdesinde setState KASITLI: toggle'ın AÇIK kalmaması gereken tek yer burası.
    // `isLive`, kullanıcının basışından BAĞIMSIZ olarak da true olabiliyor (kamera hazır olunca),
    // dolayısıyla kapatma yalnız onPress'te yapılamaz. Tek ek render, yanlış "aktif" izleniminin
    // ekranda kalmasından yeğdir.
    setAutoAdjust(false);
    showToast(otonomYonlendirmeMetni(), "info");
    // `showToast` deps'te GÜVENLE durabilir: ToastProvider onu `useCallback(..., [])` ile stabil
    // veriyor (eski "KARARSIZ referans" notu bayattı).
  }, [isLive, autoAdjust, showToast]);

  // Canlı kamera (otonom-OLMAYAN mod): telefon kamerasından kare yakala → analiz et.
  // SG.G5 / G6 / G4-2 (sahip gözlemleri 2026-10-13): eskiden sabit `setInterval(capture, 2500)` + HER hata sessiz yutuluyordu
  // (`catch {}`) ve yalnız başarılı yanıt gösteriliyordu → modalite kapısının 422'si alan segmentasyon karesi "hiç analiz yapmıyor"
  // gibi görünüyor, termalde normal kamera reddedilince ESKİ teşhis ekranda kalıyordu. Artık (`utils/canliKare`): uyarlamalı döngü
  // (önceki kare bitince, başlangıçlar arası en az ~1 sn; kuyruk birikmez) · son karenin durumu backend yanıtından türetilip SÜREKLİ
  // görünür (toast yok) · ret (4xx) gelince bu kare için geçerli sonuç YOK → teşhis ekrandan kalkar.
  useEffect(() => {
    if (!isLive || autoAdjust) return;
    let bitti = false;
    let zamanlayici: ReturnType<typeof setTimeout> | null = null;
    const oturum = canliOturumBaslat(); // TD9: dakika başı jeton — oturum kimliği her kare isteğinde
    setCanliJeton(0);
    const tur = async () => {
      if (bitti) return;
      const bas = Date.now();
      if (!loadingRef.current && cameraRef.current) {
        loadingRef.current = true;
        try {
          // shutterSound: false — canlı analiz döngüsü sık kare alır; her karede deklanşör sesi klinikte rahatsız edici
          // (saha bildirimi 2026-08-27).
          const photo = await cameraRef.current.takePictureAsync({
            quality: 0.5, skipProcessing: true, shutterSound: false,
          });
          const shrunk = photo?.uri ? await shrinkForUpload(photo.uri) : { uri: "", base64: null };
          if (shrunk.base64 && !bitti) {
            const fd = new FormData();
            fd.append("image_base64", shrunk.base64);
            fd.append("auto_adjust", "false");
            // Uçuştaki istek unmount'ta / kip değişiminde İPTAL edilir (cleanup abort eder; setState öncesi mountedRef / bitti).
            const ctrl = new AbortController();
            // CANLI-DONGU: kisa sinir ZORUNLU (uzun timeout kamera akisini kilitler)
            const t = setTimeout(() => ctrl.abort(), 15000);
            liveAbortRef.current = ctrl;
            try {
              const r = await fetch(serviceConfig.apiBaseUrl + "/ai" + endpoint, {
                method: "POST", body: fd,
                headers: { Accept: "application/json", ...authHeaders(), [CANLI_OTURUM_BASLIGI]: oturum.kimlik },
                signal: ctrl.signal,
              });
              const data = await r.json().catch(() => ({}));
              if (!mountedRef.current || bitti) return;
              const kareDurumu = canliKareDurumu(endpoint, r.ok, r.status, data);
              setCanliDurum(kareDurumu);
              oturum.kareBildir(kareDurumu, bas);
              setCanliJeton(oturum.jetonSayisi());
              if (r.ok && data?.status === "success") {
                setResult(data);
                setSonKareZamani(Date.now());
              } else {
                setResult(null);
                setSonKareZamani(null);
              }
            } finally {
              clearTimeout(t);
            }
          }
        } catch (e) {
          if (mountedRef.current && !bitti) setCanliDurum({ tur: "hata", metin: t("ai.canli.sonKareHata", { hata: aiHataMesaji(e) }) });
        } finally {
          loadingRef.current = false;
        }
      }
      if (bitti) return;
      zamanlayici = setTimeout(tur, canliSonrakiBekleme(Date.now() - bas));
    };
    zamanlayici = setTimeout(tur, canliSonrakiBekleme(0));
    return () => {
      bitti = true;
      if (zamanlayici) clearTimeout(zamanlayici);
      // Uçuştaki kare analizini de iptal et (boşa çıkarım + unmount sonrası setState).
      try { liveAbortRef.current?.abort(); } catch { /* ignore */ }
      liveAbortRef.current = null;
    };
  }, [isLive, autoAdjust, endpoint, t]);

  // SG.G6: canlı kipte gösterilen son analiz karesinin yaşı ("1,8 sn önce") — kare eskidikçe operatör görür.
  useEffect(() => {
    if (!isLive) return;
    const t = setInterval(() => setSimdi(Date.now()), 500);
    return () => clearInterval(t);
  }, [isLive]);

  // "Model hazırlanıyor" ipucu: analiz 8sn'den uzun sürerse (ilk-kullanım model indirme).
  const [longLoading, setLongLoading] = useState(false);
  useEffect(() => {
    if (!loading) {
      setLongLoading(false);
      return;
    }
    const t = setTimeout(() => setLongLoading(true), 8000);
    return () => clearTimeout(t);
  }, [loading]);

  const toggleLive = async () => {
    if (!isLive) {
      // Kamerayı açarken izin yoksa iste.
      if (!permission?.granted) {
        const res = await requestPermission();
        if (!res?.granted) {
          showToast(t("ai.canli.kameraIzni"), "error");
          return;
        }
      }
    }
    const next = !isLive;
    setIsLive(next);
    setCanliDurum(null);
    setSonKareZamani(null);
    // SG.G6: sıfırlama HER İKİ yönde (Kedi Organ B1 deseni) — canlı kip son analiz karesini OPAK gösterdiği için galeri
    // fotoğrafının sonucu canlıya geçişte "son kare" gibi görünmemeli.
    if (imageUri && imageUri.startsWith("blob:")) { try { URL.revokeObjectURL(imageUri); } catch { /* ignore */ } }
    setImageUri(null);
    setImageBase64(null);
    setImageFile(null);
    setResult(null);
  };

  const takePhoto = async () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = 'image/*';
      (input as any).capture = 'environment';
      input.onchange = (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0];
        if (file) {
          // BUG #3 FIX: eski objectURL'yi temizle
          if (imageUri && imageUri.startsWith('blob:')) URL.revokeObjectURL(imageUri);
          setImageBase64(null);
          setResult(null);
          // ⚠️ WEB KÜÇÜLTME (AI Hub planı, ADIM 1): web'de HİÇ küçültme yoktu → ham dosya
          // yükleniyor, aynı analiz platforma göre 8× farklı boyutta gidiyor ve backend'in
          // 1 MB multipart sınırına takılıyordu. `webIcinKucult` başarısızlıkta ORİJİNALİ
          // döndürür (fail-open) — küçültme bir optimizasyondur, kapı değil.
          void webIcinKucult(file).then((k) => { setImageFile(k); setImageUri(URL.createObjectURL(k)); });
        }
      };
      input.click();
    } else {
      let res = await ImagePicker.launchCameraAsync({ allowsEditing: true, quality: 0.8, base64: true });
      if (!res.canceled) {
        const shrunk = await shrinkForUpload(res.assets[0].uri);
        setImageUri(shrunk.uri);
        setImageBase64(shrunk.base64);
        setImageFile((res.assets[0] as any).file || null);
        setResult(null);
      }
    }
  };

  const pickImage = async () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = 'image/*';
      input.onchange = (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0];
        if (file) {
          // BUG #3 FIX: eski objectURL'yi temizle
          if (imageUri && imageUri.startsWith('blob:')) URL.revokeObjectURL(imageUri);
          setImageBase64(null);
          setResult(null);
          // ⚠️ WEB KÜÇÜLTME (AI Hub planı, ADIM 1): web'de HİÇ küçültme yoktu → ham dosya
          // yükleniyor, aynı analiz platforma göre 8× farklı boyutta gidiyor ve backend'in
          // 1 MB multipart sınırına takılıyordu. `webIcinKucult` başarısızlıkta ORİJİNALİ
          // döndürür (fail-open) — küçültme bir optimizasyondur, kapı değil.
          void webIcinKucult(file).then((k) => { setImageFile(k); setImageUri(URL.createObjectURL(k)); });
        }
      };
      input.click();
    } else {
      let res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, allowsEditing: true, quality: 0.8, base64: true });
      if (!res.canceled) {
        const shrunk = await shrinkForUpload(res.assets[0].uri);
        setImageUri(shrunk.uri);
        setImageBase64(shrunk.base64);
        setImageFile((res.assets[0] as any).file || null);
        setResult(null);
      }
    }
  };

  const analyzeImage = async (uriToAnalyze?: string | null) => {
    const hasta = hastaAnligi(); // D2.E09 (Y87): kayıt analizin BAŞLADIĞI hastaya yazılır
    uriToAnalyze = typeof uriToAnalyze === "string" ? uriToAnalyze : imageUri;
    if (!uriToAnalyze) return;
    // BUG #2 FIX: loadingRef hem state hem de interval closure için güncelleniyor
    setLoading(true);
    loadingRef.current = true;
    try {
      const formData = new FormData();
      if (Platform.OS === 'web') {
        let blob: Blob | null = null;
        if (uriToAnalyze === imageUri && imageFile) {
          blob = imageFile;
        } else if (uriToAnalyze.startsWith('data:')) {
          const arr = uriToAnalyze.split(',');
          const mime = arr[0].match(/:(.*?);/)?.[1] || 'image/jpeg';
          const bstr = atob(arr[1]);
          let n = bstr.length;
          const u8arr = new Uint8Array(n);
          while (n--) {
            u8arr[n] = bstr.charCodeAt(n);
          }
          blob = new Blob([u8arr], { type: mime });
        } else if (uriToAnalyze === imageUri && imageBase64) {
          const bstr = atob(imageBase64);
          let n = bstr.length;
          const u8arr = new Uint8Array(n);
          while (n--) {
            u8arr[n] = bstr.charCodeAt(n);
          }
          blob = new Blob([u8arr], { type: 'image/jpeg' });
        } else {
          const res = await fetch(uriToAnalyze);
          blob = await res.blob();
          if (blob.type && !blob.type.startsWith("image/")) {
            throw new Error("Seçilen dosya görsel olarak okunamadı.");
          }
        }
        if (!blob) {
          throw new Error("Görüntü dosyası hazırlanamadı.");
        }
        formData.append("file", blob, "upload.jpg");
      } else {
        if (uriToAnalyze === imageUri && imageBase64) {
          formData.append("image_base64", imageBase64);
        } else {
          formData.append("file", { uri: uriToAnalyze, name: "upload.jpg", type: "image/jpeg" } as any);
        }
      }
      // HASTA GÜVENLİĞİ: `auto_adjust=true` backend'de _drive_landmark_auto()'yu tetikler →
      // start_ai_session(..., 30dk, bobin 1-8) + ESP 6/7/8'e duration=1800 publish. Yani TEK KARE
      // analizinden 30 DAKİKALIK 8 BOBİNLİ otonom tedavi başlar. Eskiden bu, "Otonom Biofeedback"
      // rozeti açıkken galeriden seçilen bir fotoğrafta da (canlı kamera hiç açılmadan) SESSİZCE
      // oluyordu: onay yok, hasta kontrolü yok, süre girişi yok, geri sayım yok — üstelik sonuç
      // kartı `!autoAdjust` ile gizlendiğinden EKRANDA HİÇBİR geri bildirim de çıkmıyordu.
      // ⚠️ D1.88 (B-6.30 · A-19, sahip kararı): Otonom Biofeedback AI Pro MÜHRÜNE bağlı — bu ekran cihazı SÜRMEZ.
      // Bir ara "AÇIK ONAY" (platformConfirm) eklenmişti; ama onay penceresi hekim onayı → mühür akışı DEĞİLDİR ve
      // aynı durumda AI Pro 428 veriyordu (onay asimetrisi). Otonom açıksa kullanıcı onay akışına yönlendirilir;
      // istek HER ZAMAN salt analizdir (backend `auto_adjust=true`yu 428 ile reddeder).
      if (autoAdjustRef.current) {
        setAutoAdjust(false);
        showToast(otonomYonlendirmeMetni(), "info");
      }
      formData.append("auto_adjust", "false");
      // Sunum-katmanı XAI: yalnız MANUEL analizde ve kullanıcı açıkça istediyse (canlı
      // döngüde ASLA — kare başına sn'lerce Grad-CAM akışı kilitler).
      if (explainDestegi && isiHaritasi) formData.append("explain", "true");
      const ctrl = new AbortController();
      const to = setTimeout(() => ctrl.abort(), AI_TIMEOUT_MS); // ilk-kullanım model indirme için geniş timeout
      const response = await fetch(serviceConfig.apiBaseUrl + "/ai" + endpoint, {
        method: "POST",
        body: formData,
        headers: { "Accept": "application/json", ...authHeaders() },
        signal: ctrl.signal,
      });
      clearTimeout(to);
      const data = await response.json();
      const basarili = response.ok && data.status === "success";
      // D2.E09 (Y87): kayıt ekrandan BAĞIMSIZ — modül kapansa / hasta değişse de başlatılan hastaya (sadece manuel analizler).
      if (basarili && !isLive) logAiResult(hasta, MODUL_KAYIT_ADI[endpoint] ?? endpoint, summarizeVision(data), { moduleId: endpoint.replace("/vision/", ""), inputType: "image", detail: data });
      if (!mountedRef.current) return; // unmount olduysa stale setState yapma
      if (basarili) {
        setResult(data);
        if (isLive) setImageUri(`data:image/jpeg;base64,${data.image_base64}`); // overlay updated
      }
      else if (!isLive) showToast(aiDetayCumlesi(data?.detail, t("ai.hata.analizSirasinda")), "error");
    } catch (error) {
      if (mountedRef.current && !isLive) showToast(aiHataMesaji(error), "error");
    } finally {
      if (mountedRef.current) setLoading(false);
      loadingRef.current = false;
    }
  };

  return (
    <Card style={styles.card}>
      <View style={{flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start'}}>
        <View style={{flex: 1}}>
          <Text style={styles.title}>{title}</Text>
          <Text style={styles.subtitle}>{subtitle}</Text>
        </View>
        {endpoint === "/vision/landmark" && (
          <View style={{ alignItems: "flex-end", gap: 6 }}>
            {/* a11y: DONANIM SÜREN bir anahtarda rol/durum yoktu. */}
            <TouchableOpacity
              style={[styles.autoAdjustBtn, autoAdjust ? styles.autoAdjustActive : null]}
              onPress={() => setAutoAdjust(!autoAdjust)}
              accessibilityRole="switch"
              accessibilityState={{ checked: autoAdjust }}
              accessibilityLabel={t("ai.otonom.etiket")}
              accessibilityHint={t("ai.otonom.ipucu")}
            >
              <Activity color={autoAdjust ? colors.white : colors.primary} size={16} />
              <Text style={[styles.autoAdjustText, autoAdjust ? {color: colors.white} : null]}>
                {t("ai.otonom.baslik")}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => { if (!realtime) showToast(t("ai.gorsel.gercekZamanliIpucu"), "info"); }}
              style={[styles.rtTag, realtime ? styles.rtTagOn : styles.rtTagOff]}
              accessibilityRole="button"
              accessibilityLabel={realtime ? t("ai.gorsel.gercekZamanliEtiket") : t("ai.gorsel.kuyrukluEtiket")}
            >
              <Text style={realtime ? styles.rtTagOnText : styles.rtTagOffText}>
                {realtime ? t("ai.gorsel.gercekZamanliRozet") : t("ai.gorsel.kuyrukluRozet")}
              </Text>
            </TouchableOpacity>
          </View>
        )}
      </View>

      {!imageUri && !isLive && (
        <View style={styles.photoGuide}>
          {endpoint === "/vision/landmark" ? (
            <>
              <Text style={styles.photoGuideTitle}>{t("ai.fgs.ipucuBaslik")}</Text>
              <Text style={styles.photoGuideItem}><Trans i18nKey="ai.fgs.ipucuYuz" components={{ kalin: <Text style={styles.photoGuideBold} /> }} /></Text>
              <Text style={styles.photoGuideItem}>{t("ai.fgs.ipucuAydinlatma")}</Text>
              <Text style={styles.photoGuideItem}>{t("ai.fgs.ipucuYuzOgeleri")}</Text>
              <Text style={styles.photoGuideItem}>{t("ai.fgs.ipucuTekKedi")}</Text>
            </>
          ) : (
            <>
              <Text style={styles.photoGuideTitle}>{t("ai.gorsel.ipucuBaslik")}</Text>
              <Text style={styles.photoGuideItem}>{t("ai.gorsel.ipucuNet")}</Text>
            </>
          )}
          <Text style={styles.photoGuideWarn}>{t("ai.gorsel.yanlisFoto")}</Text>
        </View>
      )}
      {/* ⚠️ CANLI KAMERA ve SONUÇ GALERİSİ AYRI DALLAR (ADIM 4). Eskiden ikisi de sabit
          yükseklikli tek bir kapta çiziliyordu ve sonuç dalı şu ternary'ydi:
            `uri: result?.image_base64 ? 'data:…' : imageUri`
          → sonuç gelir gelmez kullanıcının GİRDİSİ ekrandan siliniyordu. Artık girdi bir
          galeri sayfası: her zaman bir çip uzaklıkta.
          ⚠️ Canlı daldaki `kameraKutusu(onizlemeW…)` oran kilidi DOKUNULMADAN kalır — kamera
          karesi ile üzerine bindirilen organ işaretlerinin hizası ona bağlı. */}
      {!isLive ? (
        <GorselSahne
          sayfalar={sahneSayfalari(result, imageUri)}
          tavanY={galeriH}
          sifirlaAnahtari={imageUri}
          testID="vision-sahne"
          bos={
            <View style={[styles.imagePreviewContainer, { height: sahneH }]}>
              <View style={styles.placeholderBox}>
                <ImageIcon color={colors.textMuted} size={48} />
                <Text style={styles.placeholderText}>{t("ai.ortak.goruntuSecilmedi")}</Text>
              </View>
            </View>
          }
        />
      ) : (
      <View
        style={[
          styles.imagePreviewContainer,
          onizlemeKutu
            ? { width: onizlemeKutu.width, height: onizlemeKutu.height, alignSelf: "center" }
            : { height: sahneH },
        ]}
        onLayout={(e) => {
          const w = Math.round(e.nativeEvent.layout.width);
          // Kutu kendi genişliğini de değiştirir → yalnız İLK ölçüm alınır (ölç-daralt döngüsü yok).
          setOnizlemeW((eski) => (eski > 0 ? eski : w));
        }}
      >
        {autoAdjust ? (
          // Otonom Biofeedback: SUNUCU (klinik) kamerası sürüyor — telefon kamerası DEĞİL.
          // Sunucu karesi gelene kadar telefon CameraView'ı GÖSTERME (kafa-karışıklığı önlenir).
          <View style={styles.cameraContainer}>
            {aiVisionData?.imageBase64 ? (
              <>
                <Image source={{ uri: `data:image/jpeg;base64,${aiVisionData.imageBase64}` }} style={styles.cameraView} resizeMode="contain" />
                {/* Rozet ARTIK tazeliğe bağlı: aiVisionData son kareyi kalıcı tuttuğundan, backend
                    döngüsü bittiğinde (süre dolumu / E-stop / kamera hatası) "AKTİF" yazısı donmuş
                    kareyle sonsuza dek açık kalıyordu. */}
                {/* B3 (2026-09-03): AI Pro HAZIRLIK önizleme kareleri de `ai_vision` ile gelir
                    (`preview:true`, bobin SÜRÜLMÜYOR) → "AKTİF" DEME, önizleme olduğunu söyle. */}
                <View style={[styles.liveIndicator, (!aiVisionFresh || aiVisionData.preview) && { backgroundColor: colors.warning }]}>
                  <View style={styles.liveDot} />
                  <Text style={styles.liveText}>
                    {!aiVisionFresh ? t("ai.otonom.yayinDurdu") : aiVisionData.preview ? t("ai.otonom.onizlemeRozet") : t("ai.otonom.aktifRozet")}
                  </Text>
                </View>
              </>
            ) : (
              <View style={[styles.cameraView, { alignItems: "center", justifyContent: "center", gap: spacing.sm }]}>
                <Activity color={colors.primary} size={32} />
                <Text style={styles.placeholderText}>{t("ai.otonom.sunucuKamerasiBekleniyor")}</Text>
              </View>
            )}
            <Text style={styles.serverCamNote}>{t("ai.otonom.sunucuKamerasiNotu")}</Text>
          </View>
        ) : (
          <CanliKameraKutusu
            cameraRef={cameraRef}
            facing={facing}
            onFlip={() => setFacing((f) => (f === "back" ? "front" : "back"))}
            sonKareB64={result?.image_base64 || null}
            sonKareYasMs={sonKareZamani != null ? simdi - sonKareZamani : null}
            rozet={t("ai.canli.kameraAktif")}
          />
        )}
      </View>
      )}
      {isLive && !autoAdjust && canliDurum ? (
        <CanliDurumSatiri durum={canliDurum} jeton={canliJetonEtkin ? canliJeton : null} />
      ) : null}

      <View style={[styles.btnRow, isCompact && { flexDirection: "column" }]}>
        <View style={isCompact ? { width: "100%" } : { flex: 1 }}>
          <Button label={t("ai.ortak.galeridenSec")} icon={<ImageIcon color={colors.white} size={16} />} onPress={pickImage} disabled={isLive} />
        </View>
        {/* Foto çek + canlı kamera: mikroskop/CT gibi dosya-tabanlı modüllerde (galleryOnly) gizli */}
        {!galleryOnly && (
          <View style={isCompact ? { width: "100%" } : { flex: 1 }}>
            <Button label={t("ai.gorsel.fotografCek")} icon={<Camera color={colors.white} size={16} />} onPress={takePhoto} disabled={isLive} />
          </View>
        )}
        {!galleryOnly && (
          <View style={isCompact ? { width: "100%" } : { flex: 1 }}>
            <Button
              label={isLive ? t("ai.gorsel.canliyiDurdur") : t("ai.gorsel.canliKamera")}
              variant={isLive ? "danger" : "secondary"}
              icon={<Video color={isLive ? colors.white : colors.primary} size={16} />}
              onPress={toggleLive}
            />
          </View>
        )}
      </View>

      <View style={styles.analyzeBtn}>
        {explainDestegi && (
          <TouchableOpacity
            style={styles.xaiToggle}
            onPress={() => setIsiHaritasi((v) => !v)}
            accessibilityRole="switch"
            accessibilityState={{ checked: isiHaritasi }}
            accessibilityLabel={t("ai.xai.isiHaritasiUretEtiketi")}
          >
            <Text style={styles.xaiToggleText}>
              {isiHaritasi ? "☑" : "☐"}{t("ai.xai.isiHaritasiUret")}
            </Text>
          </TouchableOpacity>
        )}
        <Button variant="primary" label={loading ? t("ai.ortak.analizEdiliyor") : t("ai.fgs.analiziBaslat")} icon={loading ? <ActivityIndicator color={colors.white} /> : <Sparkles color={colors.white} size={16} />} disabled={!imageUri || loading} onPress={() => analyzeImage()} />
      </View>
      {longLoading && <Text style={styles.modelHint}>{t("ai.ortak.modelHazirlaniyor")}</Text>}

      {result && !autoAdjust && (
        <View style={styles.resultBox}>
          {/* SG.G4: termal girdi doğrulanamadıysa (akromatik / kararsız / denetim kapalı) sonuçtan ÖNCE ve görünür söylenir. */}
          {result.girdi_dogrulama && result.girdi_dogrulama.dogrulandi === false && result.girdi_dogrulama.uyari ? (
            <Text style={styles.scUyari} testID="termal-girdi-uyarisi">⚠ {result.girdi_dogrulama.uyari}</Text>
          ) : null}
          {/* S-SGI.4: ters palette model teşhisi tersine çevirir (ölçüldü) — "doğrulandı" sonucunda da yön notu sonuçtan ÖNCE. */}
          {result.girdi_dogrulama?.yon_notu ? (
            <Text style={styles.scUyari} testID="termal-yon-notu">ⓘ {result.girdi_dogrulama.yon_notu}</Text>
          ) : null}
          {(() => {
            const notDet = result.detected === false || result.fgs_total === null || (typeof result.fgs_total === "number" && result.fgs_total < 0);
            // ── FGS / yüz ağrısı ──
            if (result.fgs_total !== undefined) {
              if (notDet) return <ResultInterpretation tone="alert" emoji="⚠️" title={t("ai.fgs.yuzYok.baslik")}
                text={t("ai.fgs.yuzYok.metin")} />;
              const s = result.fgs_total ?? 0;  // null/negatif yukarıda notDet ile döndü → burada geçerli sayı
              if (s === 0) return <ResultInterpretation tone="positive" emoji="😌" title={t("ai.fgs.agriYok.baslik")}
                text={t("ai.fgs.agriYok.metin")} />;
              if (s <= 3) return <ResultInterpretation tone="info" emoji="🙂" title={t("ai.fgs.hafif.baslik", { s })}
                text={t("ai.fgs.hafif.metin")}
                points={[t("ai.fgs.hafif.nokta1"), t("ai.fgs.hafif.nokta2")]} />;
              if (s <= 5) return <ResultInterpretation tone="alert" emoji="😾" title={t("ai.fgs.orta.baslik", { s })}
                text={t("ai.fgs.orta.metin")} />;
              return <ResultInterpretation tone="critical" emoji="🚨" title={t("ai.fgs.siddetli.baslik", { s })}
                text={t("ai.fgs.siddetli.metin")} />;
            }
            // ── Termal ──
            if (result.prediction) {
              const sick = result.prediction.label === "Sick";
              const prob = result.prediction.confidence !== undefined ? Math.round(result.prediction.confidence * 100) : null;
              return sick
                ? <ResultInterpretation tone="alert" emoji="🌡️" title={prob != null ? t("ai.termal.anormallikGuven", { prob }) : t("ai.termal.anormallik")}
                    text={t("ai.termal.anormallikMetin")} />
                : <ResultInterpretation tone="positive" emoji="🌡️" title={prob != null ? t("ai.termal.anormallikYokGuven", { prob }) : t("ai.termal.anormallikYok")}
                    text={t("ai.termal.anormallikYokMetin")} />;
            }
            // ── Segmentasyon ──
            if (result.cat_count !== undefined) {
              return <ResultInterpretation tone={result.cat_count > 0 ? "positive" : "alert"} emoji="🐾"
                title={t("ai.segmentasyon.kediTespit", { count: result.cat_count })}
                text={result.cat_count > 0
                  ? t("ai.segmentasyon.basarili")
                  : t("ai.segmentasyon.kediYok")} />;
            }
            // ── Retikülosit ──
            if (result.counts) {
              const ery = Number(result.counts["erythrocyte"] || 0);
              const ret = Number(result.counts["punctate reticulocyte"] || 0) + Number(result.counts["aggregate reticulocyte"] || 0);
              const total = ery + ret;
              const pctR = total > 0 ? (ret / total) * 100 : 0;
              const high = pctR >= 4;
              return <ResultInterpretation tone={high ? "alert" : "info"} emoji="🔬" title={t("ai.retikulosit.oran", { oran: pctR.toFixed(1) })}
                text={high
                  ? t("ai.retikulosit.yuksek")
                  : t("ai.retikulosit.dusuk")}
                points={[t("ai.retikulosit.nokta")]} />;
            }
            return null;
          })()}
          {result.fgs_total != null && result.fgs_total >= 0 && (
            <View>
              <Text style={styles.resultText}>{t("ai.fgs.skoru")}<Text style={{fontWeight:'bold'}}>{result.fgs_total} / 10</Text></Text>
              {/* D1.E09 (İG-5.31): model nokta görünürlüğünü bildirmiyor → örtülü yüzde skor yanıltıcı olabilir. */}
              {result.nokta_gorunurlugu_dogrulanmadi ? (
                <Text style={[styles.resultText, { fontSize: typography.small, color: colors.textMuted }]}>
                  {noktaGorunurluguUyarisi()}
                </Text>
              ) : null}
              {result.raw_fgs?.action_units && (
                <View style={{ marginTop: spacing.sm, paddingLeft: spacing.md, borderLeftWidth: 2, borderLeftColor: colors.primarySoft }}>
                  <Text style={[styles.resultText, {fontSize: typography.small}]}>{t("ai.fgs.au.kulak", { puan: result.raw_fgs.action_units["AU1_Ear_Position"]?.score ?? "-" })}</Text>
                  <Text style={[styles.resultText, {fontSize: typography.small}]}>{t("ai.fgs.au.goz", { puan: result.raw_fgs.action_units["AU2_Orbital_Tightening"]?.score ?? "-" })}</Text>
                  <Text style={[styles.resultText, {fontSize: typography.small}]}>{t("ai.fgs.au.burun", { puan: result.raw_fgs.action_units["AU3_Muzzle_Tension"]?.score ?? "-" })}</Text>
                  <Text style={[styles.resultText, {fontSize: typography.small}]}>{t("ai.fgs.au.biyik", { puan: result.raw_fgs.action_units["AU4_Whisker_Position"]?.score ?? "-" })}</Text>
                  <Text style={[styles.resultText, {fontSize: typography.small}]}>{t("ai.fgs.au.bas", { puan: result.raw_fgs.action_units["AU5_Head_Position"]?.score ?? "-" })}</Text>
                </View>
              )}
              {result.raw_fgs?.measurements && (result as any).fgs_bantlari ? (() => {
                const OLCUM_TR: Record<string, string> = {
                  ear_angle: t("ai.fgs.olcum.kulakAcisi"), ear_elev: t("ai.fgs.olcum.kulakYuksekligi"), ear_spread: t("ai.fgs.olcum.kulakAciklik"),
                  eye_ratio_avg: t("ai.fgs.olcum.gozOrani"), mouth_aspect: t("ai.fgs.olcum.agizOrani"), muzzle_compact: t("ai.fgs.olcum.burunSikiligi"),
                  whisker_tension: t("ai.fgs.olcum.biyikGerginligi"), head_center_y: t("ai.fgs.olcum.basKonumu"),
                };
                // ⚠️ Bant anahtarları (thresholds_calibrated.json) ile measurements adları AYNI
                // DEĞİL (ölçüldü: ear_angle↔ear_angle_avg vb.) — eşleme olmadan 8 satırın 4'ü
                // sessizce hiç basılmıyordu (düşman-doğrulama 2026-08-27).
                const OLCUM_KAYNAK: Record<string, string> = {
                  ear_angle: "ear_angle_avg", ear_elev: "ear_elevation", ear_spread: "ear_spread",
                  eye_ratio_avg: "eye_aperture_ratio", mouth_aspect: "mouth_aspect",
                  muzzle_compact: "muzzle_compactness", whisker_tension: "whisker_tension",
                  head_center_y: "head_center_y",
                };
                const bant = (result as any).fgs_bantlari as Record<string, { p5: number; p95: number }>;
                const olc = result.raw_fgs!.measurements as Record<string, number>;
                const satirlar = Object.keys(OLCUM_TR).filter(
                  (k) => bant[k] && Number.isFinite(Number(bant[k].p5)) && Number.isFinite(Number(bant[k].p95))
                    && Number.isFinite(Number(olc[OLCUM_KAYNAK[k]])),
                );
                if (!satirlar.length) return null;
                return (
                  <View style={{ marginTop: spacing.sm }}>
                    <Text style={styles.ctSubLabel}>{t("ai.fgs.olcumBandi")}</Text>
                    {satirlar.map((k) => {
                      const v = Number(olc[OLCUM_KAYNAK[k]]); const b = bant[k];
                      const disari = v < b.p5 || v > b.p95;
                      return (
                        <Text key={k} style={[styles.resultText, { fontSize: typography.small }]}>
                          • {OLCUM_TR[k]}: <Text style={{ fontWeight: "bold", color: disari ? colors.warning : colors.text }}>{v.toFixed(3)}</Text>
                          <Text style={{ color: colors.textMuted }}>{disari ? t("ai.fgs.bantAraligiDisinda", { alt: b.p5.toFixed(2), ust: b.p95.toFixed(2) }) : t("ai.fgs.bantAraligi", { alt: b.p5.toFixed(2), ust: b.p95.toFixed(2) })}</Text>
                        </Text>
                      );
                    })}
                    <Text style={styles.ctHint}>{t("ai.fgs.bantNotu")}</Text>
                  </View>
                );
              })() : null}
            </View>
          )}
          {result.cat_count !== undefined && <Text style={styles.resultText}>{t("ai.gorsel.tespitEdilenKedi")}<Text style={{fontWeight:'bold'}}>{result.cat_count}</Text></Text>}
          {result.prediction && (() => {
             const lbl = result.prediction.label === "Sick" ? t("ai.termal.hastaRiskli") : t("kontrol.efield.saglikli");
             const prob = result.prediction.confidence !== undefined ? (result.prediction.confidence * 100).toFixed(1) : "?";
             // SG.G4-3: model güveni DOĞRULUK DEĞİLDİR (softmax alakasız girdide de %95 verir) — eski etiket "Doğruluk" yanıltıyordu.
             return <Text style={styles.resultText}><Trans i18nKey="ai.termal.tespitSatiri" values={{ etiket: lbl, oran: prob }} components={{ kalin: <Text style={{fontWeight:'bold', color: result.prediction.label === "Sick" ? colors.danger : colors.success}} /> }} /></Text>;
          })()}
          {result.counts && (
            <>
              <Text style={styles.resultText}>{t("ai.retikulosit.eritrosit", { sayi: result.counts["erythrocyte"] ?? "" })}</Text>
              <Text style={styles.resultText}>{t("ai.retikulosit.noktali", { sayi: result.counts["punctate reticulocyte"] ?? "" })}</Text>
              <Text style={styles.resultText}>{t("ai.retikulosit.agrege", { sayi: result.counts["aggregate reticulocyte"] ?? "" })}</Text>
            </>
          )}
          {/* Sunum-katmanı XAI (Faz 2): CAM ısı haritası — istenip üretildiyse. AI1.X1: termalde başlık AÇIKLANAN kararı söyler. */}
          {result.xai_image_base64 && (
            <XaiIsiHaritasi base64={result.xai_image_base64} etiket={isiHaritasiBasligi(result)}
              not={result.counts && Object.values(result.counts).every((v) => !Number(v)) ? tespitYokHaritaNotu() : undefined} />
          )}
          {result.xai_error && <Text style={styles.xaiSatiri}>🔍 {result.xai_error}</Text>}
          <MedicalDisclaimer />
        </View>
      )}

      {/* DONANIM SONUCU — sonuç kartından AYRI ve `autoAdjust`'tan BAĞIMSIZ.
          Eskiden bu blok `result && !autoAdjust` kapısının içindeydi: donanımı sürebilen TEK durum
          (autoAdjust açık) tam da bu kapının kapalı olduğu durumdu → kullanıcı bobinlerin sürülüp
          sürülmediğini HİÇ göremiyordu. Ayrıca yalnız "updated" gösteriliyordu; backend'in
          "skipped_*" yanıtları (aktif farklı-mod seansı, kimliksiz uzak istek, döngü zaten açık)
          sessizce yutuluyordu → kullanıcı seansın başladığını sanabiliyordu. */}
      {/* ⚠️ "idle" GÖSTERİLMEZ (sahip bildirimi 2026-09-13: "cihaz sürülemedi kısmını kaldır,
          burası ai modu"). `hw_status` varsayılanı `"idle"`dır (ai_router.py:500) ve otonom mod
          KAPALIYKEN — yani düz analizde — hep o kalır. Orada "⚠️ Cihaz SÜRÜLMEDİ" yazmak, hiç
          istenmemiş bir şeyin olmadığını duyurmaktır: gerçek uyarıların yanında gürültü yapar ve
          uyarı körlüğü üretir.
          ⚠️ BLOK KALDIRILMADI, yalnız `idle` elendi: `skipped_session_active` /
          `skipped_unauthenticated` / `skipped_no_detection` durumlarında kullanıcı otonom sürüş
          İSTEMİŞTİR ve olmadığını GÖRMEK ZORUNDADIR — aksi halde seansın başladığını sanar
          (bu blok tam olarak o boşluk için eklenmişti, üstteki nota bakın). */}
      {result?.hw_status && result.hw_status !== "idle" ? (
        result.hw_status === "updated" ? (
          <View style={{ marginTop: spacing.sm, padding: spacing.sm, backgroundColor: colors.success + "22", borderRadius: radius.sm, borderWidth: 1, borderColor: colors.success }}>
            <Text style={[styles.resultText, { fontWeight: "bold", color: colors.success }]}>{t("ai.otonom.suruluyor")}</Text>
            <Text style={styles.resultText}>{t("ai.otonom.frekansSiddet", { frekans: Number(result.hw_params?.freq ?? 0).toFixed(1), duty: Number(result.hw_params?.duty ?? 0).toFixed(1) })}</Text>
            <Text style={styles.resultText}>{t("ai.otonom.durdurmakIcin")}</Text>
          </View>
        ) : (
          <View style={{ marginTop: spacing.sm, padding: spacing.sm, backgroundColor: colors.warning + "22", borderRadius: radius.sm, borderWidth: 1, borderColor: colors.warning }}>
            <Text style={[styles.resultText, { fontWeight: "bold", color: colors.warning }]}>{t("ai.otonom.surulmedi")}</Text>
            <Text style={styles.resultText}>
              {result.hw_status === "skipped_session_active"
                ? t("ai.otonom.baskaSeans")
                : result.hw_status === "skipped_unauthenticated"
                  ? t("ai.otonom.kimliksiz")
                  : t("ai.otonom.atlandi", { durum: String(result.hw_status) })}
            </Text>
          </View>
        )
      ) : null}

      {isLive && autoAdjust && aiVisionData && (
        <View style={styles.resultBox}>
          <Text style={styles.resultTitle}>{t("ai.otonom.canliSonuc")}</Text>
          {/* Eskiden burada `Anlık FGS Skoru: {aiVisionData.fgs_total} / 10` yazıyordu; backend'in
              ai_vision yayınında fgs_total alanı YOK (cat_organ pipeline'ına geçilince kaldırıldı) →
              satır her zaman "Anlık FGS Skoru:  / 10" olarak BOŞ basılıyordu. Yayının gerçekten
              içerdiği alanları göster. */}
          <Text style={styles.resultText}>
            {t("ai.otonom.hedefOrgan")}<Text style={{ fontWeight: "bold" }}>{aiVisionData.organName || "—"}</Text>
            {aiVisionData.detected === false ? t("ai.otonom.konumlandirilamadi") : ""}
          </Text>
          {typeof aiVisionData.reliability === "number" && (
            <Text style={styles.resultText}>{t("ai.otonom.lokalizasyonGuveni")}<Text style={{ fontWeight: "bold" }}>{t("ai.ortak.yuzde", { deger: (aiVisionData.reliability * 100).toFixed(0) })}</Text></Text>
          )}
          {typeof aiVisionData.eField === "number" && (
            <Text style={styles.resultText}>{t("ai.otonom.eAlan")}<Text style={{ fontWeight: "bold" }}>{aiVisionData.eField.toFixed(2)}</Text></Text>
          )}
          {typeof aiVisionData.remainingSec === "number" && (
            <Text style={styles.resultText}>{t("ai.otonom.kalanSure")}<Text style={{ fontWeight: "bold" }}>{t("ai.otonom.kalanDakika", { dk: Math.max(0, Math.round(aiVisionData.remainingSec / 60)) })}</Text></Text>
          )}
          {/* Tazelik kapısı: yayın durduysa "güncelleniyor" DEME (donmuş kareyi canlı gösterme).
              Bu, kaldırılan GLOBAL 3-durumlu göstergeyi geri getirmez — yalnız aktif otonom
              seansa özgü, yerel bir doğrulama. */}
          {aiVisionFresh && aiVisionData.preview ? (
            // B3: hazırlık önizlemesi — lokalizasyon var, SÜRÜŞ YOK. "güncelleniyor" DEME.
            <View style={{ marginTop: spacing.sm, padding: spacing.sm, backgroundColor: colors.warning + "22", borderRadius: radius.sm, borderWidth: 1, borderColor: colors.warning }}>
              <Text style={[styles.resultText, { fontWeight: "bold", color: colors.warning }]}>{t("ai.otonom.onizleme")}</Text>
            </View>
          ) : aiVisionFresh ? (
            <View style={{ marginTop: spacing.sm, padding: spacing.sm, backgroundColor: colors.success + "22", borderRadius: radius.sm, borderWidth: 1, borderColor: colors.success }}>
              <Text style={[styles.resultText, { fontWeight: "bold", color: colors.success }]}>{t("ai.otonom.guncelleniyor")}</Text>
            </View>
          ) : (
            <View style={{ marginTop: spacing.sm, padding: spacing.sm, backgroundColor: colors.warning + "22", borderRadius: radius.sm, borderWidth: 1, borderColor: colors.warning }}>
              <Text style={[styles.resultText, { fontWeight: "bold", color: colors.warning }]}>{t("ai.otonom.yayinDurduUyari")}</Text>
              <Text style={styles.resultText}>{t("ai.otonom.yayinDurduNot")}</Text>
            </View>
          )}
        </View>
      )}
    </Card>
  );
}

/**
 * Fantom Tümör Analizi — sentetik böbrek fantomu fotoğrafından mavi tümör odaklarını
 * tespit eder (klasik CV), 3B konum + PhantomPredictor (BiLSTM ONNX) ile her tümör için
 * PEMF bobin duty (D1-7) + E-alan (E_cancer/E_healthy) tahmini üretir.
 * Backend: POST /api/ai/vision/em_fantom (phantom_cv_v3 — hocanın v3'ü). Canlı kamera/otonom YOK — tek foto.
 */
function PhantomModule({ patientName }: { patientName: string }) {
  const { t } = useTranslation();
  // [S1 adım 7 / aihub-10] Sahne yüksekliği CANLI: pencere küçülünce/cihaz yan yatınca daralır.
  const sahneH = useStageHeight();
  // Galeri ASIL okuma yuzeyi: daha yuksek tavan, AYNI responsive oran (bkz. useGaleriYuksekligi).
  const galeriH = useGaleriYuksekligi();
  const { showToast } = useToast();
  const CK = "/vision/em_fantom";
  const [imageUri, setImageUri] = useState<string | null>(visionCache[CK]?.imageUri ?? null);
  const [imageBase64, setImageBase64] = useState<string | null>(visionCache[CK]?.imageBase64 ?? null);
  const [imageFile, setImageFile] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AiResult | null>(visionCache[CK]?.result ?? null);
  const [phantomLen, setPhantomLen] = useState<string>("");   // cm — boş = piksel modu
  const [longLoading, setLongLoading] = useState(false);
  const { isCompact } = useResponsive();
  // T3 · Y189: Koşullu | Koşulsuz (varsayılan koşullu, hatırlanmaz) — kural backend'de (`pemf_kapisi`).
  const [kosulsuz, setKosulsuz] = useState(false);
  const kabinKaresiGeldi = (image_base64: string) => {
    if (imageUri && imageUri.startsWith('blob:')) URL.revokeObjectURL(imageUri);
    setImageFile(null); setImageBase64(image_base64); setImageUri(`data:image/jpeg;base64,${image_base64}`); setResult(null);
  };

  useEffect(() => {
    visionCache[CK] = { imageUri, imageBase64, result };
  }, [imageUri, imageBase64, result]);

  useEffect(() => {
    if (!loading) { setLongLoading(false); return; }
    const t = setTimeout(() => setLongLoading(true), 8000);
    return () => clearTimeout(t);
  }, [loading]);

  const takePhoto = async () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file'; input.accept = 'image/*'; (input as any).capture = 'environment';
      input.onchange = (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0];
        if (file) {
          if (imageUri && imageUri.startsWith('blob:')) URL.revokeObjectURL(imageUri);
          setImageBase64(null); setResult(null); void webIcinKucult(file).then((k) => { setImageFile(k); setImageUri(URL.createObjectURL(k)); });
        }
      };
      input.click();
    } else {
      const res = await ImagePicker.launchCameraAsync({ allowsEditing: false, quality: 0.8, base64: true });
      if (!res.canceled) {
        const shrunk = await shrinkForUpload(res.assets[0].uri);
        setImageUri(shrunk.uri); setImageBase64(shrunk.base64);
        setImageFile((res.assets[0] as any).file || null); setResult(null);
      }
    }
  };

  const pickImage = async () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file'; input.accept = 'image/*';
      input.onchange = (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0];
        if (file) {
          if (imageUri && imageUri.startsWith('blob:')) URL.revokeObjectURL(imageUri);
          setImageBase64(null); setResult(null); void webIcinKucult(file).then((k) => { setImageFile(k); setImageUri(URL.createObjectURL(k)); });
        }
      };
      input.click();
    } else {
      const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, allowsEditing: false, quality: 0.8, base64: true });
      if (!res.canceled) {
        const shrunk = await shrinkForUpload(res.assets[0].uri);
        setImageUri(shrunk.uri); setImageBase64(shrunk.base64);
        setImageFile((res.assets[0] as any).file || null); setResult(null);
      }
    }
  };

  const analyze = async () => {
    const hasta = hastaAnligi(); // D2.E09 (Y87): kayıt analizin BAŞLADIĞI hastaya yazılır
    if (!imageUri) return;
    setLoading(true);
    try {
      const formData = new FormData();
      if (Platform.OS === 'web') {
        let blob: Blob | null = null;
        if (imageFile) blob = imageFile;
        else if (imageBase64) {
          const bstr = atob(imageBase64); let n = bstr.length; const u8 = new Uint8Array(n);
          while (n--) u8[n] = bstr.charCodeAt(n);
          blob = new Blob([u8], { type: 'image/jpeg' });
        } else {
          const r = await fetch(imageUri); blob = await r.blob();
        }
        if (!blob) throw new Error("Görüntü hazırlanamadı.");
        formData.append("file", blob, "phantom.jpg");
      } else {
        if (imageBase64) formData.append("image_base64", imageBase64);
        else formData.append("file", { uri: imageUri, name: "phantom.jpg", type: "image/jpeg" } as any);
      }
      const plen = parseFloat(phantomLen.replace(",", "."));
      if (!isNaN(plen) && plen > 0) formData.append("phantom_length_cm", String(plen));
      if (kosulsuz) formData.append("kosulsuz", "true");  // T3 · Y189 (koşulluda HİÇ gönderilmez = eski istek)

      const ctrl = new AbortController();
      const to = setTimeout(() => ctrl.abort(), AI_TIMEOUT_MS); // ilk-kullanım model indirme için geniş
      const response = await fetch(serviceConfig.apiBaseUrl + "/ai/vision/em_fantom", {
        method: "POST", body: formData, headers: { Accept: "application/json", ...authHeaders() }, signal: ctrl.signal,
      });
      clearTimeout(to);
      const data = await response.json();
      if (response.ok && (data.status === "success" || data.status === "no_detection")) {
        setResult(data);
        if (data.status === "success") {
          const ec = data.tumor_regions?.[0]?.E_cancer;
          logAiResult(hasta, "Fantom Tümör Analizi", `${data.n_tumor} tümör${ec != null ? `, E_c≈${Number(ec).toFixed(3)}` : ""}`, { moduleId: "em_fantom", inputType: "image", detail: data });
        }
      } else {
        showToast(aiDetayCumlesi(data?.detail, t("ai.hata.analizSirasinda")), "error");
      }
    } catch (e) {
      showToast(aiHataMesaji(e), "error");
    } finally {
      setLoading(false);
    }
  };

  const method = result?.method;
  const unit = method === "pixel" ? "px" : "mm";

  return (
    <Card style={styles.card}>
      <Text style={styles.title}>{t("ai.fantom.baslik")}</Text>
      <Text style={styles.subtitle}>{t("ai.fantom.aciklama")}</Text>

      {!imageUri && (
        <View style={styles.photoGuide}>
          <Text style={styles.photoGuideTitle}>{t("ai.fantom.ipucuBaslik")}</Text>
          <Text style={styles.photoGuideItem}><Trans i18nKey="ai.fantom.ipucuUst" components={{ kalin: <Text style={styles.photoGuideBold} /> }} /></Text>
          <Text style={styles.photoGuideItem}>{t("ai.fantom.ipucuMavi")}</Text>
          <Text style={styles.photoGuideItem}><Trans i18nKey="ai.fantom.ipucuHalka" components={{ kalin: <Text style={styles.photoGuideBold} /> }} /></Text>
          <Text style={styles.photoGuideItem}>{t("ai.fantom.ipucuBoy")}</Text>
        </View>
      )}

      {/* ⚠️ ÇOK PANELLİ GALERİ (ADIM 4). Eskiden burada şu ternary vardı:
            `uri: result?.image_base64 ? 'data:…' : imageUri`
          → sonuç gelir gelmez kullanıcının GİRDİSİ ekrandan siliniyordu; üstelik gösterilen tek
          şey okunmaz `07_combined` mozaiğiydi (panel başına ~81 px). Artık backend'in ürettiği
          7 panel de gezilebilir ve girdi bir çip uzaklıkta. */}
      <GorselSahne
        sayfalar={sahneSayfalari(result, imageUri)}
        tavanY={galeriH}
        sifirlaAnahtari={imageUri}
        testID="fantom-sahne"
          bos={
            <View style={[styles.imagePreviewContainer, { height: sahneH }]}>
              <View style={styles.placeholderBox}>
                <ImageIcon color={colors.textMuted} size={48} />
                <Text style={styles.placeholderText}>{t("ai.ortak.goruntuSecilmedi")}</Text>
              </View>
            </View>
          }
      />

      <View style={styles.fantomLenRow}>
        <Text style={styles.fantomLenLabel}>{t("ai.fantom.boy")}</Text>
        <TextInput
          style={styles.fantomLenInput}
          keyboardType="numeric"
          accessibilityLabel={t("ai.fantom.boy")}
          placeholder={t("ai.fantom.boyYerTutucu")}
          placeholderTextColor={colors.textMuted}
          value={phantomLen}
          onChangeText={setPhantomLen}
        />
      </View>
      <KosulSecici kosulsuz={kosulsuz} onDegis={setKosulsuz} kilitli={loading} testID="fantom-kosul" />

      <View style={[styles.btnRow, isCompact && { flexDirection: "column" }]}>
        <View style={isCompact ? { width: "100%" } : { flex: 1 }}>
          <Button label={t("ai.ortak.galeridenSec")} icon={<ImageIcon color={colors.white} size={16} />} onPress={pickImage} />
        </View>
        <View style={isCompact ? { width: "100%" } : { flex: 1 }}>
          <Button label={t("ai.gorsel.fotografCek")} icon={<Camera color={colors.white} size={16} />} onPress={takePhoto} />
        </View>
      </View>
      {/* T3 · Y189: görüntü VARSAYILAN kameradan değil, Ayarlar ▸ Kabin kamerası'nda seçilen kameradan (1920×1080). */}
      <KabinKaresiDugmesi onKare={kabinKaresiGeldi} />

      <View style={styles.analyzeBtn}>
        <Button variant="primary" label={loading ? t("ai.ortak.analizEdiliyor") : t("ai.fantom.analiziBaslat")} icon={loading ? <ActivityIndicator color={colors.white} /> : <Sparkles color={colors.white} size={16} />} disabled={!imageUri || loading} onPress={analyze} />
      </View>
      {longLoading && <Text style={styles.modelHint}>{t("ai.ortak.modelHazirlaniyor")}</Text>}

      {result && (
        <View style={styles.resultBox}>
          {(result.status === "no_detection" || !result.success) ? (
            <ResultInterpretation tone="alert" emoji="⚠️" title={t("ai.fantom.tespitYok.baslik")}
              text={t("ai.fantom.tespitYok.metin")} />
          ) : (
            <>
              {(() => {
                const n = result.n_tumor || 0;
                return <ResultInterpretation tone={n > 0 ? "alert" : "info"} emoji="🎯" title={t("ai.fantom.odak.baslik", { count: n })}
                  text={method === "pixel" ? pikselKipiNotu(t("ai.fantom.olcekGirdisi")) : t("ai.fantom.hesaplandi")}
                  points={[t("ai.fantom.nokta1"), t("ai.fantom.nokta2"), t("ai.fantom.nokta3")]} />;
              })()}
              <Text style={styles.resultText}><Trans i18nKey="ai.fantom.ozet" values={{ n: result.n_tumor ?? "", olcek: method === "pixel" ? t("ai.ortak.piksel") : `${result.mm_per_px} mm/px` }} components={{ kalin: <Text style={{ fontWeight: "bold" }} /> }} /></Text>
              {/* AI-2: hocanın tüketim kontrolleri (pemf_valid / reliable / uyarılar / VARSAYIMLAR) — metin backend'den. */}
              <PemfKapisiKutusu kapi={result.pemf_kapisi} reliable={result.reliable} model="fantom" />
              {(result.tumor_regions || []).map((bolge: AiTumorRegion, i: number) => {
                const D: number[] = Array.isArray(bolge.D) ? bolge.D : [];
                return (
                  <View key={i} style={styles.tumorRow}>
                    <Text style={styles.tumorHeader}>{bolge.tumor_id ? t("ai.fantom.tumorBaslik", { id: bolge.tumor_id }) : t("ai.fantom.tumorBaslik", { id: i + 1 })}   ·   {konumMetni(bolge.centroid_cabin_mm, unit)}</Text>
                    <EmDozSatiri r={bolge} style={[styles.resultText, { fontSize: typography.small }]} />
                    {D.length > 0 && (
                      <View style={styles.dBarRow}>
                        {D.map((d: number, j: number) => (
                          <View key={j} style={styles.dBarWrap}>
                            <View style={styles.dBarTrack}>
                              <View style={[styles.dBarFill, { height: dutyYuzde(d) }]} />
                            </View>
                            <Text style={styles.dBarLabel}>D{j + 1}</Text>
                          </View>
                        ))}
                      </View>
                    )}
                  </View>
                );
              })}
            </>
          )}
          {/* Analizden seansa köprü (Faz 3): bu ekran otonom seans BAŞLATMAZ, yalnız
              Kontrol → AI Pro'ya geçer ve model kartını ön-seçer. */}
          {result.success ? <AiProKopruDugmesi model="fantom" /> : null}
          <MedicalDisclaimer />
        </View>
      )}
    </Card>
  );
}

/**
 * PETRİ GELİŞMİŞ (ARAŞTIRMA) AYARLARI — sahip talebi 2026-09-09 ("altısı da ayarlanabilir olsun").
 *
 * NEDEN VAR: "PEMF uygulaması kuyucukları görmüyor" bulgusu ölçüldü (Desktop/petri test/sonuclar/
 * BULGULAR.md). Kök neden entegrasyon DEĞİL, ÖLÇEK: YOLO ONNX'i 640×640'a SABİT export edilmiş,
 * 3024×4032'lik telefon fotoğrafında kuyucuklar o boyuta inince kayboluyor. Ölçülen: tespit
 * güveni 0,25 → 0,05 aynı karede 1 → 3 kuyucuk; plakaya kırpma 1 → 5 kuyucuk. Araştırmacının
 * bu iki kolu sahada çevirebilmesi gerekiyor.
 *
 * ⚠️ SINIR TABLOSU BİR TEL SÖZLEŞMESİDİR: tek kaynak
 * `ai_hub/inference_petri_dish/petri_ayar.py::SINIRLAR` + `varsayilanlar()`. TypeScript Python'u
 * import edemediği için değerler burada KOPYA duruyor; `tests/test_petri_ayar_parametreleri.py`
 * eşitliği kilitler → sessizce ayrışamaz (`_PETRI_NOT_PLATE` ile aynı desen).
 */
/** Alan etiketi / ipucu katalog ANAHTARIDIR (gösterimde `t(a.etiket as never)` çevirir — K-3 izni: kapalı 12 anahtar); `vars` / `alt` / `ust` / `ad` VERİDİR
 *  (backend `petri_ayar` ile eşitlik kapısı bu alanları okur: tests/test_petri_ayar_parametreleri.py). */
const PETRI_AYAR_ALANLARI: {
  ad: string; etiket: string; vars: string; alt: number; ust: number; ipucu: string;
}[] = [
  {
    ad: "yolo_conf", etiket: "ai.petri.ayar.yoloConf.etiket", vars: "0.25", alt: 0.01, ust: 0.95,
    ipucu: "ai.petri.ayar.yoloConf.ipucu",
  },
  {
    ad: "yolo_iou", etiket: "ai.petri.ayar.yoloIou.etiket", vars: "0.7", alt: 0.1, ust: 0.95,
    ipucu: "ai.petri.ayar.yoloIou.ipucu",
  },
  {
    ad: "resize_max", etiket: "ai.petri.ayar.resizeMax.etiket", vars: "kapalı", alt: 320, ust: 8000,
    ipucu: "ai.petri.ayar.resizeMax.ipucu",
  },
  {
    ad: "plaus_circularity", etiket: "ai.petri.ayar.plausCircularity.etiket", vars: "0.55", alt: 0, ust: 1,
    ipucu: "ai.petri.ayar.plausCircularity.ipucu",
  },
  {
    ad: "plaus_conf", etiket: "ai.petri.ayar.plausConf.etiket", vars: "0.85", alt: 0, ust: 1,
    ipucu: "ai.petri.ayar.plausConf.ipucu",
  },
  {
    ad: "plaus_area_frac", etiket: "ai.petri.ayar.plausAreaFrac.etiket", vars: "0.25", alt: 0.01, ust: 1,
    ipucu: "ai.petri.ayar.plausAreaFrac.ipucu",
  },
];

/** Ayar alanının "varsayılan" gösterimi: sayısal alanlar tablodaki değer, `resize_max` "kapalı" sözcüğü (gösterimde çevrilir). */
const ayarVarsayilani = (a: { ad: string; vars: string }): string => (a.ad === "resize_max" ? i18n.t("ai.petri.kapali") : a.vars);

/** AI-2 (hocanın petri v2'si) — PLAKA kipinde anlamlı olan tek eski ayar küçültmedir. ÖLÇÜLDÜ (6 plaka fotoğrafı):
 *  conf 0,05 / 0,9, IoU 0,3 ve gevşetilmiş "petri değil" eşikleri sonucu BİREBİR aynı bıraktı (YOLO plaka kipinde yalnız ipucu,
 *  makullik plaka kuralıyla); küçültme ölçeği ve doğrulanan aday sayısını değiştirdi (640'ta 2/6 düşük çözünürlüklü plaka RED). */
const PLAKA_KIPI_AYARLARI = new Set(["resize_max"]);
/** A1 köşesi seçenekleri (backend `petri_ayar.A1_KOSELERI`). */
const a1KoseAdi = (k: "auto" | "tl" | "tr" | "br" | "bl"): string =>
  k === "auto" ? i18n.t("ai.petri.a1KoseAdi.otomatik")
    : k === "tl" ? i18n.t("ai.petri.a1KoseAdi.solUst")
      : k === "tr" ? i18n.t("ai.petri.a1KoseAdi.sagUst")
        : k === "br" ? i18n.t("ai.petri.a1KoseAdi.sagAlt")
          : i18n.t("ai.petri.a1KoseAdi.solAlt");

/**
 * Petri Kuyu Analizi — petri fotoğrafından YOLO11m-seg ile N kuyucuk tespit eder,
 * her kuyuda HSV kanser sınıflandırması yapar, 3B konum + PetriPredictor (BaggingRegressor
 * ONNX) ile kuyu başına PEMF bobin duty (D1-7) + E-alan (E_cancer/E_healthy) tahmini üretir.
 * Backend: POST /api/ai/vision/em_petri (petri_cv_v2 — hocanın v2'si). Canlı kamera/otonom YOK — tek foto.
 */
function PetriModule({ patientName }: { patientName: string }) {
  const { t } = useTranslation();
  // [S1 adım 7 / aihub-10] Sahne yüksekliği CANLI: pencere küçülünce/cihaz yan yatınca daralır.
  const sahneH = useStageHeight();
  // Galeri ASIL okuma yuzeyi: daha yuksek tavan, AYNI responsive oran (bkz. useGaleriYuksekligi).
  const galeriH = useGaleriYuksekligi();
  const { showToast } = useToast();
  const CK = "/vision/em_petri";
  const [imageUri, setImageUri] = useState<string | null>(visionCache[CK]?.imageUri ?? null);
  const [imageBase64, setImageBase64] = useState<string | null>(visionCache[CK]?.imageBase64 ?? null);
  const [imageFile, setImageFile] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AiResult | null>(visionCache[CK]?.result ?? null);
  const [petriDia, setPetriDia] = useState<string>("");   // cm — boş = piksel modu
  const [longLoading, setLongLoading] = useState(false);
  const { isCompact } = useResponsive();
  // Gelişmiş (araştırma) ayarları — VARSAYILAN olarak KAPALI ve BOŞ. Boş alan gönderilmez;
  // gönderilmeyen alan backend'de boru hattı varsayılanında kalır → hiçbir ayara dokunmayan
  // kullanıcı için davranış bugünküyle BİT-BİT aynı.
  const [advAcik, setAdvAcik] = useState(false);
  const [adv, setAdv] = useState<Record<string, string>>({});
  // "Petri değil" denetimi: AÇIK durumda HİÇBİR ŞEY gönderilmez (ortam değişkeni
  // PEMF_AI_PLAUSIBILITY_GUARD kararını korur); yalnız kullanıcı KAPATIRSA `false` gider.
  const [denetimAcik, setDenetimAcik] = useState(true);
  // AI-2 (hocanın petri v2'si): KİP — "plaka" (24 kuyucuklu plaka ızgarası, A1–D6; varsayılan) | "tekil" (tekil petri
  // kapları, eski YOLO kipi). ÖLÇÜLDÜ: plaka kipinde tespit güveni / örtüşme / "petri değil" eşikleri sonucu DEĞİŞTİRMEZ
  // (6/6 plaka fotoğrafında birebir aynı) → o alanlar yalnız tekil kipte gösterilir ve GÖNDERİLİR.
  const [kip, setKip] = useState<"plaka" | "tekil">("plaka");
  const [kontrolSaglikli, setKontrolSaglikli] = useState("");
  const [kontrolKanser, setKontrolKanser] = useState("");
  const [a1Kose, setA1Kose] = useState<"auto" | "tl" | "tr" | "br" | "bl">("auto");
  // T3 · Y189: Koşullu | Koşulsuz (varsayılan koşullu, hatırlanmaz). Koşulsuzda plaka bulunamazsa ham YOLO tespiti, makullik reddi
  // ve kalite / yeniden-çekim nedenleri analizi KESMEZ (uyarı) — kural backend'de.
  const [kosulsuz, setKosulsuz] = useState(false);
  const kabinKaresiGeldi = (image_base64: string) => {
    if (imageUri && imageUri.startsWith('blob:')) URL.revokeObjectURL(imageUri);
    setImageFile(null); setImageBase64(image_base64); setImageUri(`data:image/jpeg;base64,${image_base64}`); setResult(null);
  };
  const gorunenAyarlar = PETRI_AYAR_ALANLARI.filter((a) => kip === "tekil" || PLAKA_KIPI_AYARLARI.has(a.ad));
  const advDegisti = !denetimAcik || gorunenAyarlar.some((a) => (adv[a.ad] || "").trim() !== "")
    || (kip === "plaka" && (kontrolSaglikli.trim() !== "" || kontrolKanser.trim() !== "" || a1Kose !== "auto"));

  useEffect(() => {
    visionCache[CK] = { imageUri, imageBase64, result };
  }, [imageUri, imageBase64, result]);

  useEffect(() => {
    if (!loading) { setLongLoading(false); return; }
    const t = setTimeout(() => setLongLoading(true), 8000);
    return () => clearTimeout(t);
  }, [loading]);

  const takePhoto = async () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file'; input.accept = 'image/*'; (input as any).capture = 'environment';
      input.onchange = (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0];
        if (file) {
          if (imageUri && imageUri.startsWith('blob:')) URL.revokeObjectURL(imageUri);
          setImageBase64(null); setResult(null); void webIcinKucult(file).then((k) => { setImageFile(k); setImageUri(URL.createObjectURL(k)); });
        }
      };
      input.click();
    } else {
      const res = await ImagePicker.launchCameraAsync({ allowsEditing: false, quality: 0.8, base64: true });
      if (!res.canceled) {
        const shrunk = await shrinkForUpload(res.assets[0].uri);
        setImageUri(shrunk.uri); setImageBase64(shrunk.base64);
        setImageFile((res.assets[0] as any).file || null); setResult(null);
      }
    }
  };

  const pickImage = async () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file'; input.accept = 'image/*';
      input.onchange = (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0];
        if (file) {
          if (imageUri && imageUri.startsWith('blob:')) URL.revokeObjectURL(imageUri);
          setImageBase64(null); setResult(null); void webIcinKucult(file).then((k) => { setImageFile(k); setImageUri(URL.createObjectURL(k)); });
        }
      };
      input.click();
    } else {
      const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, allowsEditing: false, quality: 0.8, base64: true });
      if (!res.canceled) {
        const shrunk = await shrinkForUpload(res.assets[0].uri);
        setImageUri(shrunk.uri); setImageBase64(shrunk.base64);
        setImageFile((res.assets[0] as any).file || null); setResult(null);
      }
    }
  };

  const analyze = async () => {
    const hasta = hastaAnligi(); // D2.E09 (Y87): kayıt analizin BAŞLADIĞI hastaya yazılır
    if (!imageUri) return;
    setLoading(true);
    try {
      const formData = new FormData();
      if (Platform.OS === 'web') {
        let blob: Blob | null = null;
        if (imageFile) blob = imageFile;
        else if (imageBase64) {
          const bstr = atob(imageBase64); let n = bstr.length; const u8 = new Uint8Array(n);
          while (n--) u8[n] = bstr.charCodeAt(n);
          blob = new Blob([u8], { type: 'image/jpeg' });
        } else {
          const r = await fetch(imageUri); blob = await r.blob();
        }
        if (!blob) throw new Error("Görüntü hazırlanamadı.");
        formData.append("file", blob, "petri.jpg");
      } else {
        if (imageBase64) formData.append("image_base64", imageBase64);
        else formData.append("file", { uri: imageUri, name: "petri.jpg", type: "image/jpeg" } as any);
      }
      // AI-2: kip + laboratuvar protokolü. Plaka kipi varsayılandır (YAML) → hiçbir şey gönderilmez; tekil kipte plate_type=0.
      if (kip === "tekil") {
        formData.append("plate_type", "0");
        const dia = parseFloat(petriDia.replace(",", "."));
        if (!isNaN(dia) && dia > 0) formData.append("petri_diameter_cm", String(dia));
      } else {
        if (kontrolSaglikli.trim()) formData.append("control_healthy", kontrolSaglikli.trim());
        if (kontrolKanser.trim()) formData.append("control_cancer", kontrolKanser.trim());
        if (a1Kose !== "auto") formData.append("a1_corner", a1Kose);
      }

      // ── Gelişmiş (araştırma) ayarları ────────────────────────────────────────────────
      // ⚠️ `sayiya_cevir` dersi: Türkçe klavyede "0,05" yazılır. `parseFloat("0,05")` = 0
      // döner (SESSİZ yanlış değer) — virgül noktaya çevrilmeden okunmaz.
      for (const a of gorunenAyarlar) {  // AI-2: gizli (kipe göre anlamsız) alanın eski değeri GÖNDERİLMEZ
        const ham = (adv[a.ad] || "").trim();
        if (!ham) continue;                       // boş = varsayılanda kal
        const d = parseFloat(ham.replace(",", "."));
        if (isNaN(d)) { showToast(t("ai.petri.sayiGirin", { etiket: t(a.etiket as never), vars: ayarVarsayilani(a) }), "error"); setLoading(false); return; }
        // resize_max için 0 = "küçültme kapalı" (sınır ihlali değil).
        const kapali = a.ad === "resize_max" && d === 0;
        if (!kapali && (d < a.alt || d > a.ust)) {
          showToast(t("ai.petri.aralikDisi", { etiket: t(a.etiket as never), alt: a.alt, ust: a.ust, ham }), "error");
          setLoading(false); return;
        }
        formData.append(a.ad, String(d));
      }
      // Denetim KAPATILDIYSA açıkça bildir; açıkken göndermeyiz ki sunucudaki
      // PEMF_AI_PLAUSIBILITY_GUARD kaçış kapağı arayüz tarafından EZİLMESİN.
      if (!denetimAcik) formData.append("plaus_guard", "false");
      if (kosulsuz) formData.append("kosulsuz", "true");  // T3 · Y189 (koşulluda HİÇ gönderilmez = eski istek)

      const ctrl = new AbortController();
      const to = setTimeout(() => ctrl.abort(), AI_TIMEOUT_MS); // ilk-kullanım model indirme için geniş
      const response = await fetch(serviceConfig.apiBaseUrl + "/ai/vision/em_petri", {
        method: "POST", body: formData, headers: { Accept: "application/json", ...authHeaders() }, signal: ctrl.signal,
      });
      clearTimeout(to);
      const data = await response.json();
      if (response.ok && (data.status === "success" || data.status === "no_detection")) {
        setResult(data);
        if (data.status === "success") {
          logAiResult(hasta, "Petri Kuyu Analizi", `${data.n_wells} kuyu (${data.n_cancer} kanser)`, { moduleId: "em_petri", inputType: "image", detail: data });
        }
      } else {
        showToast(aiDetayCumlesi(data?.detail, t("ai.hata.analizSirasinda")), "error");
      }
    } catch (e) {
      showToast(aiHataMesaji(e), "error");
    } finally {
      setLoading(false);
    }
  };

  const method = result?.method;
  const unit = method === "pixel" ? "px" : "mm";

  return (
    <Card style={styles.card}>
      <Text style={styles.title}>{t("ai.petri.baslik")}</Text>
      <Text style={styles.subtitle}>{t("ai.petri.aciklama")}</Text>

      {!imageUri && (
        <View style={styles.photoGuide}>
          <Text style={styles.photoGuideTitle}>{t("ai.petri.ipucuBaslik")}</Text>
          <Text style={styles.photoGuideItem}><Trans i18nKey="ai.petri.ipucuUst" components={{ kalin: <Text style={styles.photoGuideBold} /> }} /></Text>
          <Text style={styles.photoGuideItem}>{t("ai.petri.ipucuKenar")}</Text>
          <Text style={styles.photoGuideItem}><Trans i18nKey="ai.petri.ipucuKontrol" components={{ kalin: <Text style={styles.photoGuideBold} /> }} /></Text>
        </View>
      )}

      {/* ⚠️ ÇOK PANELLİ GALERİ (ADIM 4). Eskiden burada şu ternary vardı:
            `uri: result?.image_base64 ? 'data:…' : imageUri`
          → sonuç gelir gelmez kullanıcının GİRDİSİ ekrandan siliniyordu; üstelik gösterilen tek
          şey okunmaz `07_combined` mozaiğiydi (panel başına ~81 px). Artık backend'in ürettiği
          7 panel de gezilebilir ve girdi bir çip uzaklıkta. */}
      <GorselSahne
        sayfalar={sahneSayfalari(result, imageUri)}
        tavanY={galeriH}
        sifirlaAnahtari={imageUri}
        testID="petri-sahne"
          bos={
            <View style={[styles.imagePreviewContainer, { height: sahneH }]}>
              <View style={styles.placeholderBox}>
                <ImageIcon color={colors.textMuted} size={48} />
                <Text style={styles.placeholderText}>{t("ai.ortak.goruntuSecilmedi")}</Text>
              </View>
            </View>
          }
      />

      <View style={styles.btnRow} accessibilityRole="radiogroup" accessibilityLabel={t("ai.petri.kipEtiketi")}>
        {([["plaka", t("ai.petri.kipPlaka")], ["tekil", t("ai.petri.kipTekil")]] as const).map(([k, et]) => (
          <TouchableOpacity
            key={k}
            style={[styles.advAnahtar, { flex: 1, opacity: kip === k ? 1 : 0.6 }]}
            onPress={() => setKip(k)}
            accessibilityRole="radio"
            accessibilityState={{ selected: kip === k }}
            accessibilityLabel={et}
          >
            <Text style={styles.advAnahtarMetin}>{kip === k ? "◉" : "○"} {et}</Text>
          </TouchableOpacity>
        ))}
      </View>
      {kip === "tekil" && (<>
      <View style={styles.fantomLenRow}>
        <Text style={styles.fantomLenLabel}>{t("ai.petri.cap")}</Text>
        <TextInput
          style={styles.fantomLenInput}
          keyboardType="numeric"
          accessibilityLabel={t("ai.petri.cap")}
          placeholder={t("ai.petri.capYerTutucu")}
          placeholderTextColor={colors.textMuted}
          value={petriDia}
          onChangeText={setPetriDia}
        />
      </View>
      <Text style={styles.petriHint}>{t("ai.petri.qrNotu")}</Text>
      </>)}
      {kip === "plaka" && (
        <Text style={styles.petriHint}>{t("ai.petri.plakaNotu")}</Text>
      )}
      <KosulSecici kosulsuz={kosulsuz} onDegis={setKosulsuz} kilitli={loading} testID="petri-kosul" />

      {/* GELİŞMİŞ (ARAŞTIRMA) AYARLARI — kapalı başlar; hiçbir alana dokunulmazsa istek
          bugünküyle AYNI gider (boş alan gönderilmez). */}
      <TouchableOpacity
        style={styles.advBaslik}
        onPress={() => setAdvAcik((v) => !v)}
        accessibilityRole="button"
        accessibilityState={{ expanded: advAcik }}
        accessibilityLabel={t("ai.petri.gelismisEtiketi")}
        accessibilityHint={advAcik ? t("ai.petri.gelismisKapat") : t("ai.petri.gelismisAc")}
      >
        <Text style={styles.advBaslikMetin}>
          {advAcik ? "▾" : "▸"}{t("ai.petri.gelismis")}{advDegisti ? t("ai.petri.degistirildi") : ""}
        </Text>
      </TouchableOpacity>

      {advAcik && (
        <View style={styles.advGovde}>
          <Text style={styles.advNot}>
            {kip === "tekil"
              ? t("ai.petri.advNotTekil")
              : t("ai.petri.advNotPlaka")}
          </Text>
          {kip === "plaka" && (
            <View style={styles.advAlan}>
              <View style={styles.advSatir}>
                <Text style={styles.advEtiket}>{t("ai.petri.saglikliKontrol")}</Text>
                <TextInput style={styles.advGirdi} accessibilityLabel={t("ai.petri.saglikliKontrol")} placeholder={t("ai.petri.ornekA1D6")}
                  placeholderTextColor={colors.textMuted} value={kontrolSaglikli} onChangeText={setKontrolSaglikli} autoCapitalize="characters" />
              </View>
              <View style={styles.advSatir}>
                <Text style={styles.advEtiket}>{t("ai.petri.boyaliKontrol")}</Text>
                <TextInput style={styles.advGirdi} accessibilityLabel={t("ai.petri.boyaliKontrolEtiketi")} placeholder={t("ai.petri.ornekB2")}
                  placeholderTextColor={colors.textMuted} value={kontrolKanser} onChangeText={setKontrolKanser} autoCapitalize="characters" />
              </View>
              <Text style={styles.advIpucu}>{t("ai.petri.kontrolNotu")}</Text>
              <View style={styles.advSatir} accessibilityRole="radiogroup" accessibilityLabel={t("ai.petri.a1Kose")}>
                <Text style={styles.advEtiket}>{t("ai.petri.a1Kose")}</Text>
                {(["auto", "tl", "tr", "br", "bl"] as const).map((k) => (
                  <TouchableOpacity key={k} style={styles.advAnahtar} onPress={() => setA1Kose(k)} accessibilityRole="radio"
                    accessibilityState={{ selected: a1Kose === k }} accessibilityLabel={t("ai.petri.a1KoseSecenek", { secenek: a1KoseAdi(k) })}>
                    <Text style={styles.advAnahtarMetin}>{a1Kose === k ? "◉" : "○"} {a1KoseAdi(k)}  </Text>
                  </TouchableOpacity>
                ))}
              </View>
              <Text style={styles.advIpucu}>{t("ai.petri.a1Notu")}</Text>
            </View>
          )}
          {gorunenAyarlar.map((a) => (
            <View key={a.ad} style={styles.advAlan}>
              <View style={styles.advSatir}>
                <Text style={styles.advEtiket}>{t(a.etiket as never)}</Text>
                <TextInput
                  style={styles.advGirdi}
                  keyboardType="numeric"
                  accessibilityLabel={t(a.etiket as never)}
                  placeholder={t("ai.petri.varsayilan", { vars: ayarVarsayilani(a) })}
                  placeholderTextColor={colors.textMuted}
                  value={adv[a.ad] || ""}
                  onChangeText={(t) => setAdv((p) => ({ ...p, [a.ad]: t }))}
                />
              </View>
              <Text style={styles.advIpucu}>{t(a.ipucu as never)}</Text>
            </View>
          ))}

          <TouchableOpacity
            style={styles.advAnahtar}
            onPress={() => setDenetimAcik((v) => !v)}
            accessibilityRole="switch"
            accessibilityState={{ checked: denetimAcik }}
            accessibilityLabel={t("ai.petri.denetimEtiketi")}
          >
            <Text style={styles.advAnahtarMetin}>
              {denetimAcik ? "☑" : "☐"}{t("ai.petri.denetimAcik")}
            </Text>
          </TouchableOpacity>
          {!denetimAcik && (
            <Text style={styles.advUyari}>
              {t("ai.petri.denetimKapaliUyari")}
            </Text>
          )}

          <TouchableOpacity
            style={styles.advSifirla}
            onPress={() => { setAdv({}); setDenetimAcik(true); setKontrolSaglikli(""); setKontrolKanser(""); setA1Kose("auto"); }}
            accessibilityRole="button"
            accessibilityLabel={t("ai.petri.varsayilanaDon")}
          >
            <Text style={styles.advSifirlaMetin}>{t("ai.petri.varsayilanlaraDon")}</Text>
          </TouchableOpacity>
        </View>
      )}

      <View style={[styles.btnRow, isCompact && { flexDirection: "column" }]}>
        <View style={isCompact ? { width: "100%" } : { flex: 1 }}>
          <Button label={t("ai.ortak.galeridenSec")} icon={<ImageIcon color={colors.white} size={16} />} onPress={pickImage} />
        </View>
        <View style={isCompact ? { width: "100%" } : { flex: 1 }}>
          <Button label={t("ai.gorsel.fotografCek")} icon={<Camera color={colors.white} size={16} />} onPress={takePhoto} />
        </View>
      </View>
      {/* T3 · Y189: görüntü VARSAYILAN kameradan değil, Ayarlar ▸ Kabin kamerası'nda seçilen kameradan (1920×1080). */}
      <KabinKaresiDugmesi onKare={kabinKaresiGeldi} />

      <View style={styles.analyzeBtn}>
        <Button variant="primary" label={loading ? t("ai.ortak.analizEdiliyor") : t("ai.petri.analiziBaslat")} icon={loading ? <ActivityIndicator color={colors.white} /> : <Sparkles color={colors.white} size={16} />} disabled={!imageUri || loading} onPress={analyze} />
      </View>
      {longLoading && <Text style={styles.modelHint}>{t("ai.ortak.modelHazirlaniyor")}</Text>}

      {result && (
        <View style={styles.resultBox}>
          {(result.status === "no_detection" || !result.success) ? (
            /* Ölçülen saha nedeni (BULGULAR.md): tam kare telefon fotoğrafında kuyucuklar
               640 px'lik model girdisine inince kayboluyor. "Tekrar deneyin" tek başına
               kullanıcıyı aynı sonuca götürüyordu — çıkışı olan bir yönlendirme veriyoruz. */
            <ResultInterpretation tone="alert" emoji="⚠️" title={kip === "plaka" ? t("ai.petri.plakaYok") : t("ai.petri.kuyucukYok")}
              text={t("ai.petri.tespitYokMetin")}
              points={kip === "plaka" ? [
                t("ai.petri.plakaKipiNotu"),
                t("ai.petri.tekilKipNotu"),
              ] : [
                t("ai.petri.kadrajNotu"),
                t("ai.petri.ayarNotu"),
              ]} />
          ) : (
            <>
              {(() => {
                const nc = result.n_cancer || 0;
                return <ResultInterpretation tone={nc > 0 ? "alert" : "positive"} emoji="🧫"
                  title={t("ai.petri.sonuc.baslik", { count: result.n_wells, nc, n_healthy: result.n_healthy })}
                  text={method === "pixel" ? pikselKipiNotu(t("ai.petri.olcekGirdisi")) : nc > 0
                    ? t("ai.petri.sonuc.kanserSiniflandi", { count: nc })
                    : t("ai.petri.sonuc.kanserYok")}
                  points={[t("ai.petri.nokta1"), t("ai.fantom.nokta2")]} />;
              })()}
              <Text style={styles.resultText}>
                <Trans i18nKey="ai.petri.ozet" values={{ n: result.n_wells ?? "", kanser: result.n_cancer ?? "", saglikli: result.n_healthy ?? "" }} components={{ kalin: <Text style={{ fontWeight: "bold" }} />, kanser: <Text style={{ fontWeight: "bold", color: colors.danger }} />, saglikli: <Text style={{ fontWeight: "bold", color: colors.success }} /> }} />
              </Text>
              <Text style={[styles.resultText, { fontSize: typography.small }]}>{t("ai.petri.olcek", { olcek: method === "pixel" ? t("ai.ortak.piksel") : `${result.mm_per_px} mm/px` })}</Text>
              {/* AI-2: hocanın tüketim kontrolleri — pemf_valid / kontrol QC / çekim uyarıları / VARSAYIMLAR (metin backend'den). */}
              <PemfKapisiKutusu kapi={result.pemf_kapisi} model="petri" />
              {(result.wells || []).map((w: AiWell, i: number) => {
                const D: number[] = Array.isArray(w.D) ? w.D : [];
                const isCancer = w.label === "cancer" || w.organ_id === 1;
                return (
                  <View key={i} style={styles.tumorRow}>
                    <Text style={styles.tumorHeader}>
                      {w.well_id}   ·   <Text style={{ color: isCancer ? colors.danger : colors.success }}>{isCancer ? t("ai.petri.kanser") : t("kontrol.efield.saglikli")}</Text>   ·   {konumMetni(w.centroid_cabin_mm, unit)}
                      {isCancer && Array.isArray(w.cancer_reasons) && w.cancer_reasons.length > 0 ? <Text style={{ color: colors.textMuted, fontSize: typography.small }}>{t("ai.petri.gerekce", { neden: w.cancer_reasons.join(", ") })}</Text>
                        : isCancer && (w as any).n_cancer_pixels != null ? <Text style={{ color: colors.textMuted, fontSize: typography.small }}>{t("ai.petri.gerekceMavi", { n: (w as any).n_cancer_pixels })}</Text> : null}
                    </Text>
                    <EmDozSatiri r={w} style={[styles.resultText, { fontSize: typography.small }]} />
                    {D.length > 0 && (
                      <View style={styles.dBarRow}>
                        {D.map((d: number, j: number) => (
                          <View key={j} style={styles.dBarWrap}>
                            <View style={styles.dBarTrack}>
                              <View style={[styles.dBarFill, { height: dutyYuzde(d) }]} />
                            </View>
                            <Text style={styles.dBarLabel}>D{j + 1}</Text>
                          </View>
                        ))}
                      </View>
                    )}
                  </View>
                );
              })}
            </>
          )}
          {/* ETKİN AYARLAR — istek DEĞİL, boru hattının gerçekten kullandığı değerler.
              Gevşetilmiş bir eşikle çıkan sonucun "normal" görünmesini engeller (denetim izi);
              varsayılanla koşulduysa hiçbir şey yazılmaz, arayüz kalabalıklaşmaz. */}
          {(() => {
            const ya = (result as any).yolo_ayar || {};
            const rz = (result as any).resize || {};
            const th = ((result as any).plausibility || {}).thresholds || {};
            const thVars = ((result as any).plausibility || {}).thresholds_default || {};
            const parca: string[] = [];
            if (ya.conf != null && Number(ya.conf) !== 0.25) parca.push(`conf ${trValue(ya.conf)}`);
            if (ya.iou != null && Number(ya.iou) !== 0.7) parca.push(`IoU ${trValue(ya.iou)}`);
            if (rz.max) parca.push(t("ai.petri.etkin.kucultme", { a: String(rz.from?.[0]), b: String(rz.from?.[1]), c: String(rz.to?.[0]), d: String(rz.to?.[1]) }));
            for (const [k, etiket] of [["circularity_med", t("ai.petri.etkin.dairesellik")], ["conf_med", t("ai.petri.etkin.guven")], ["max_area_frac", t("ai.petri.etkin.alanOrani")]] as const) {
              if (th[k] != null && thVars[k] != null && Number(th[k]) !== Number(thVars[k])) parca.push(t("ai.petri.etkin.denetim", { etiket, deger: trValue(th[k]) }));
            }
            if (((result as any).plausibility || {}).guard === "off") parca.push(t("ai.petri.etkin.denetimKapali"));
            if (!parca.length) return null;
            return <Text style={styles.advEtkin}>{t("ai.petri.etkin.baslik", { ayarlar: parca.join(" · ") })}</Text>;
          })()}
          {/* Analizden seansa köprü (Faz 3): bu ekran otonom seans BAŞLATMAZ, yalnız
              Kontrol → AI Pro'ya geçer ve model kartını ön-seçer. */}
          {result.success ? <AiProKopruDugmesi model="petri" /> : null}
          <MedicalDisclaimer />
        </View>
      )}
    </Card>
  );
}

/**
 * Böbrek RNA Analizi (KIRC) — RNA-seq gen-ekspresyon CSV'sinden böbrek renal clear cell
 * karsinom (KIRC) vs "other" sınıflandırması. Foto DEĞİL — CSV dosya yükleme (expo-document-picker).
 * Backend: POST /api/ai/rna/kidney (MLP-medium ONNX; log2→scaler→top-1000→softmax).
 */
function RnaModule({ patientName }: { patientName: string }) {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const [file, setFile] = useState<{ name: string; uri: string; webFile?: any } | null>(moduleCache.kidney_rna?.file ?? null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AiResult | null>(moduleCache.kidney_rna?.result ?? null);
  const [longLoading, setLongLoading] = useState(false);
  // XAI opt-in (plan §KALAN A1): IG top-genler — hasta başına en etkili genler.
  const [isiHaritasi, setIsiHaritasi] = useState(false);
  useEffect(() => { moduleCache.kidney_rna = { result, file }; }, [result, file]);

  useEffect(() => {
    if (!loading) { setLongLoading(false); return; }
    const t = setTimeout(() => setLongLoading(true), 8000);
    return () => clearTimeout(t);
  }, [loading]);

  const pickCsv = async () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file'; input.accept = '.csv,text/csv';
      input.onchange = (e: Event) => {
        const f = (e.target as HTMLInputElement).files?.[0];
        if (f) { setFile({ name: f.name, uri: '', webFile: f }); setResult(null); }
      };
      input.click();
    } else {
      const res = await DocumentPicker.getDocumentAsync({
        type: ["text/csv", "text/comma-separated-values", "application/vnd.ms-excel", "*/*"],
        copyToCacheDirectory: true,
      });
      if (!res.canceled && res.assets?.[0]) {
        setFile({ name: res.assets[0].name, uri: res.assets[0].uri });
        setResult(null);
      }
    }
  };

  const analyze = async () => {
    const hasta = hastaAnligi(); // D2.E09 (Y87): kayıt analizin BAŞLADIĞI hastaya yazılır
    if (!file) return;
    setLoading(true);
    try {
      const formData = new FormData();
      if (Platform.OS === 'web' && file.webFile) {
        formData.append("file", file.webFile, file.name);
      } else {
        // Native: CSV'yi base64 oku → csv_base64 alanı. DocumentPicker file:// URI'sini RN
        // multipart doğrudan okuyamadığı için (Ağ hatası); base64 okuma bu sorunu atlar.
        const b64 = await FileSystemLegacy.readAsStringAsync(file.uri, { encoding: "base64" as any });
        formData.append("csv_base64", b64);
      }
      const ctrl = new AbortController();
      const to = setTimeout(() => ctrl.abort(), AI_TIMEOUT_MS);
      if (isiHaritasi) formData.append("explain", "true");
      const response = await fetch(serviceConfig.apiBaseUrl + "/ai/rna/kidney", {
        method: "POST", body: formData, headers: { Accept: "application/json", ...authHeaders() }, signal: ctrl.signal,
      });
      clearTimeout(to);
      const data = await response.json();
      if (response.ok && data.status === "success") {
        setResult(data);
        logAiResult(hasta, "Böbrek RNA (KIRC)", `${data.n_patients} hasta`, { moduleId: "kidney_rna", inputType: "csv", detail: data });
      } else {
        showToast(aiDetayCumlesi(data?.detail, t("ai.hata.analizSirasinda")), "error");
      }
    } catch (e) {
      // Ham istisna metni kullanıcıya basılıyordu; dosya seçici yolunda bu metin DOSYA YOLU/ADI
      // (hasta adı içerebilir) taşıyabiliyor. Ayrıntı konsola, kullanıcıya sade mesaj.
      console.error("RNA analizi hatası:", e);
      // Satır-içi AbortError ayrımı `aiHataMesaji`ye devredildi (2026-08-12).
      showToast(aiHataMesaji(e, t("ai.rna.basarisiz")), "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card style={styles.card}>
      <Text style={styles.title}>{t("ai.rna.baslik")}</Text>
      <Text style={styles.subtitle}>{t("ai.rna.aciklama")}</Text>

      <View style={styles.photoGuide}>
        <Text style={styles.photoGuideTitle}>{t("ai.rna.csvBaslik")}</Text>
        <Text style={styles.photoGuideItem}><Trans i18nKey="ai.rna.csvSatir" components={{ kalin: <Text style={styles.photoGuideBold} /> }} /></Text>
        <Text style={styles.photoGuideItem}>{t("ai.rna.csvKimlik")}</Text>
        <Text style={styles.photoGuideItem}>{t("ai.rna.csvLab")}</Text>
      </View>

      <View style={styles.analyzeBtn}>
        <Button label={file ? t("ai.rna.baskaCsv") : t("ai.rna.csvSec")} icon={<FileText color={colors.white} size={16} />} onPress={pickCsv} />
      </View>
      {file && <Text style={styles.rnaFileName} numberOfLines={1}>📄 {file.name}</Text>}

      <TouchableOpacity style={styles.xaiToggle} accessibilityRole="switch" accessibilityState={{ checked: isiHaritasi }} onPress={() => setIsiHaritasi(!isiHaritasi)}>
        <Text style={styles.xaiToggleText}>{isiHaritasi ? "☑" : "☐"}{t("ai.rna.genleriGoster")}</Text>
      </TouchableOpacity>

      <View style={styles.analyzeBtn}>
        <Button variant="primary" label={loading ? t("ai.ortak.analizEdiliyor") : t("ai.rna.analiziBaslat")} icon={loading ? <ActivityIndicator color={colors.white} /> : <Sparkles color={colors.white} size={16} />} disabled={!file || loading} onPress={analyze} />
      </View>
      {longLoading && <Text style={styles.modelHint}>{t("ai.ortak.modelHazirlaniyor")}</Text>}

      {result && (
        <View style={styles.resultBox}>
          {(() => {
            const preds = result.predictions || [];
            const kirc = preds.filter((p: AiPrediction) => p.prediction === "KIRC").length;
            return <ResultInterpretation tone={kirc > 0 ? "alert" : "positive"} emoji="🧬"
              title={kirc > 0 ? t("ai.rna.sonuc.kircVar", { kirc, n_patients: result.n_patients }) : t("ai.rna.sonuc.kircYok")}
              text={kirc > 0
                ? t("ai.rna.sonuc.kircVarMetin")
                : t("ai.rna.sonuc.kircYokMetin")}
              points={[t("ai.rna.nokta1"), t("ai.rna.nokta2")]} />;
          })()}
          <Text style={styles.resultText}>{t("ai.rna.hastaSayisi")}<Text style={{ fontWeight: "bold" }}>{result.n_patients}</Text></Text>
          {(result.predictions || []).map((p: AiPrediction, i: number) => {
            const isKirc = p.prediction === "KIRC";
            return (
              <View key={i} style={styles.tumorRow}>
                {/* Model etiketleri ham İngilizce basılıyordu ("KIRC" / "other") — uygulamanın
                    geri kalanı Türkçe. KIRC klinik bir kısaltma olduğundan korunur, açıklaması eklenir. */}
                <Text style={styles.tumorHeader}>
                  {p.patient_id}   ·   <Text style={{ color: isKirc ? colors.danger : colors.success }}>
                    {isKirc ? t("ai.rna.kircIsareti") : t("ai.rna.kircDegil")}
                  </Text>
                </Text>
                <Text style={[styles.resultText, { fontSize: typography.small }]}>
                  {t("ai.rna.guven")}<Text style={{ fontWeight: "bold" }}>{t("ai.ortak.yuzde", { deger: (Number(p.confidence) * 100).toFixed(1) })}</Text>
                  {p.prob_KIRC != null ? t("ai.rna.kircOlasiligi", { oran: (Number(p.prob_KIRC) * 100).toFixed(1) }) : ""}
                </Text>
                {(() => {
                  const xl = (result as any).xai as { patient_id: string; top_genes: { gene: string; attribution: number }[] }[] | undefined;
                  const h = Array.isArray(xl) ? xl.find((x) => x.patient_id === p.patient_id) : undefined;
                  if (!h || !h.top_genes?.length) return null;
                  return (
                    // ⚠️ Sahip 2026-09-12: "ai analiz detaylarında yine üç nokta sorunu ve
                    // devamını göremeyiş". Beş genlik gerekçe iki satıra sığmıyordu ve son
                    // genler (çoğu zaman ters yönlü olanlar) üç noktanın arkasında kalıyordu.
                    <GenisletilebilirMetin style={styles.xaiSatiri} satir={2} testID="xai-genler">
                      {t("ai.rna.surukleyenGenler", { genler: h.top_genes.slice(0, 5).map((g) => `${g.gene} ${g.attribution >= 0 ? "↑" : "↓"}`).join("  ·  ") })}
                    </GenisletilebilirMetin>
                  );
                })()}
              </View>
            );
          })}
          {result.xai_error ? <Text style={styles.xaiSatiri}>🔍 {result.xai_error}</Text> : null}
          <MedicalDisclaimer />
        </View>
      )}
    </Card>
  );
}

// UCI-CKD 24 özellik. Sayısal (14) + kategorik (10). Kategorik değerler predictor'ın
// beklediği stringlerle eşleşmeli (yes/no, normal/abnormal, present/notpresent, good/poor).
const CKD_NUMERIC: { k: string; label: string }[] = [
  { k: "age", label: "hasta.form.yasEtiketi" }, { k: "bp", label: "ai.ckd.alan.bp" },
  { k: "sg", label: "ai.ckd.alan.sg" }, { k: "al", label: "ai.ckd.alan.al" },
  { k: "su", label: "ai.ckd.alan.su" }, { k: "bgr", label: "ai.ckd.alan.bgr" },
  { k: "bu", label: "ai.ckd.alan.bu" }, { k: "sc", label: "ai.ckd.alan.sc" },
  { k: "sod", label: "ai.ckd.alan.sod" }, { k: "pot", label: "ai.ckd.alan.pot" },
  { k: "hemo", label: "ai.ckd.alan.hemo" }, { k: "pcv", label: "ai.ckd.alan.pcv" },
  { k: "wc", label: "ai.ckd.alan.wc" }, { k: "rc", label: "ai.ckd.alan.rc" },
];

const CKD_CATEGORICAL: { k: string; label: string; opts: [string, string][] }[] = [
  { k: "rbc", label: "ai.ckd.alan.rbc", opts: [["normal", "ai.ckd.secenek.normal"], ["abnormal", "ai.ckd.secenek.anormal"]] },
  { k: "pc", label: "ai.ckd.alan.pc", opts: [["normal", "ai.ckd.secenek.normal"], ["abnormal", "ai.ckd.secenek.anormal"]] },
  { k: "pcc", label: "ai.ckd.alan.pcc", opts: [["notpresent", "ai.ckd.secenek.yok"], ["present", "ai.ckd.secenek.var"]] },
  { k: "ba", label: "ai.ckd.alan.ba", opts: [["notpresent", "ai.ckd.secenek.yok"], ["present", "ai.ckd.secenek.var"]] },
  { k: "htn", label: "ai.ckd.alan.htn", opts: [["no", "ai.ckd.secenek.hayir"], ["yes", "ai.ckd.secenek.evet"]] },
  { k: "dm", label: "ai.ckd.alan.dm", opts: [["no", "ai.ckd.secenek.hayir"], ["yes", "ai.ckd.secenek.evet"]] },
  { k: "cad", label: "ai.ckd.alan.cad", opts: [["no", "ai.ckd.secenek.hayir"], ["yes", "ai.ckd.secenek.evet"]] },
  { k: "appet", label: "ai.ckd.alan.appet", opts: [["good", "ai.ckd.secenek.iyi"], ["poor", "ai.ckd.secenek.kotu"]] },
  { k: "pe", label: "ai.ckd.alan.pe", opts: [["no", "ai.ckd.secenek.hayir"], ["yes", "ai.ckd.secenek.evet"]] },
  { k: "ane", label: "ai.ckd.alan.ane", opts: [["no", "ai.ckd.secenek.hayir"], ["yes", "ai.ckd.secenek.evet"]] },
];
// Sunum-katmanı XAI + ön-kontrol bildirimi: alan kodu → görünen etiket (form etiketiyle TEK kaynak; tablo ANAHTAR saklar, çağrı anında çevrilir — K-3 izni).
const ckdEtiket = (k: string): string => {
  const e = [...CKD_NUMERIC, ...CKD_CATEGORICAL].find((x) => x.k === k);
  return e ? i18n.t(e.label as never) : k;
};

/**
 * Böbrek Hastalığı Analizi (UCI-CKD) — 24 klinik değerden kronik böbrek hastalığı tahmini.
 * Foto/CSV DEĞİL — FORM girişi (kedi DiseaseModule deseni). Eksik alanlar backend'de impute
 * edilir. Backend: POST /api/ai/disease/kidney (ExtraTrees ONNX, EXE'ye gömülü).
 */
function KidneyDiseaseModule({ patientName }: { patientName: string }) {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AiResult | null>(moduleCache.kidney_disease?.result ?? null);
  const [num, setNum] = useState<Record<string, string>>(moduleCache.kidney_disease?.num ?? {});
  const [cat, setCat] = useState<Record<string, string | undefined>>(moduleCache.kidney_disease?.cat ?? {});
  useEffect(() => { moduleCache.kidney_disease = { result, num, cat }; }, [result, num, cat]);

  const analyze = async () => {
    const hasta = hastaAnligi(); // D2.E09 (Y87): kayıt analizin BAŞLADIĞI hastaya yazılır
    setLoading(true);
    setResult(null);
    try {
      const payload: any = {};
      CKD_NUMERIC.forEach(({ k }) => {
        const v = parseFloat((num[k] || "").replace(",", "."));
        if (!isNaN(v)) payload[k] = v;
      });
      CKD_CATEGORICAL.forEach(({ k }) => { if (cat[k]) payload[k] = cat[k]; });
      // B5 (2026-09-03): GÖNDERİM ÖNCESİ eyleme dönük ön-kontrol — utils/klinik_asgari.py
      // (CKD_MIN_ALAN=6 / CKD_CEKIRDEK {sc,bu,sg,al,hemo}) ile hizalı; sunucu 422 kapısı NİHAİ.
      // Eskiden yalnız bulgu düğmeleriyle basınca sunucu 422 dönüyor, UI bunu jenerik
      // "Analiz sırasında hata oluştu."a çeviriyordu → operatör "ne seçersem seçeyim çalışmıyor" görüyordu.
      // ⚠️ `payload.explain = true` bu sayımdan SONRA gelmeli (bayrak alan sayılmaz; fonksiyon yine de eler).
      const onKontrol = ckdOnKontrol(payload, (k) => ckdEtiket(k));
      if (onKontrol) { showToast(onKontrol, "error"); return; } // finally → setLoading(false)
      // Sunum-katmanı XAI (2026-08-26): SHAP top-özellikler — hata/eski-backend'de alan
      // gelmez, satır gizlenir (backend zarif düşüşü).
      payload.explain = true;
      // B5: sunucunun gerekçesi (422: hangi alanlar eksik / 500: model) KAYBOLMASIN.
      // ⚠️ `silent: true` KULLANMA — apiClient'ın zaman-aşımı toast'ı ("ilk analiz model yüklemesi
      // nedeniyle uzun sürebilir") korunmalı (2026-08-12 "analiz boş döndü" dersi). HTTP hatasında
      // apiClient zaten "Sunucu Hatası: <gerekçe>" toast'ını basar → modül İKİNCİ toast basıp onu EZMESİN.
      let sunucuBildirdi = false;
      let sunucuDetay: string | undefined;
      const res = await apiPost<any>("/ai/disease/kidney", payload, null, {
        timeoutMs: AI_TIMEOUT_MS,
        onHttpError: (_st, detail) => { sunucuBildirdi = true; sunucuDetay = detail; },
      });
      if (res && res.status === "success") {
        setResult(res);
        logAiResult(hasta, "Böbrek Hastalığı (CKD)", `${trValue(res.label)} %${res.prob_pct}`, { moduleId: "kidney_disease", inputType: "clinical", detail: res, confidence: res.prob_pct != null ? res.prob_pct / 100 : undefined });
      } else if (!sunucuBildirdi) {
        // Ağ/JSON-boş yolu (HTTP hatası değil): sunucu bir gerekçe vermedi → anlaşılır varsayılan.
        showToast(t("ai.ckd.tamamlanamadi"), "error");
      } else if (!sunucuDetay) {
        // HTTP hatası ama gerekçe metni yok (beklenmedik gövde) → teknik metin yerine eylem cümlesi.
        showToast(aiDetayCumlesi(undefined, t("ai.ckd.tamamlanamadi")), "error");
      }
    } catch (e) {
      showToast(aiHataMesaji(e), "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card style={styles.card}>
      <Text style={styles.title}>{t("ai.ckd.baslik")}</Text>
      <Text style={styles.subtitle}>{t("ai.ckd.aciklama")}</Text>

      <Text style={styles.ckdSection}>{t("ai.ckd.laboratuvar")}</Text>
      <View style={styles.ckdGrid}>
        {CKD_NUMERIC.map(({ k, label }) => (
          <View key={k} style={styles.ckdNumCell}>
            <Text style={styles.ckdNumLabel} numberOfLines={1}>{t(label as never)}</Text>
            <TextInput
              style={styles.ckdNumInput}
              keyboardType="numeric"
              placeholder="—"
              placeholderTextColor={colors.textMuted}
              value={num[k] || ""}
              onChangeText={(t) => setNum((s) => ({ ...s, [k]: t }))}
            />
          </View>
        ))}
      </View>

      <Text style={styles.ckdSection}>{t("ai.ckd.bulgular")}</Text>
      {CKD_CATEGORICAL.map(({ k, label, opts }) => (
        <View key={k} style={styles.ckdCatRow}>
          <Text style={styles.ckdCatLabel} numberOfLines={1}>{t(label as never)}</Text>
          <View style={styles.ckdCatBtns}>
            {opts.map(([val, lbl]) => {
              const active = cat[k] === val;
              return (
                <TouchableOpacity
                  key={val}
                  style={[styles.ckdCatBtn, active && styles.ckdCatBtnActive]}
                  onPress={() => setCat((s) => ({ ...s, [k]: active ? undefined : val }))}
                  activeOpacity={0.8}
                >
                  <Text style={[styles.ckdCatBtnText, active && { color: colors.white }]}>{t(lbl as never)}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>
      ))}

      <View style={styles.analyzeBtn}>
        <Button variant="primary" label={loading ? t("ai.ortak.analizEdiliyor") : t("ai.ckd.analiziBaslat")} icon={loading ? <ActivityIndicator color={colors.white} /> : <Sparkles color={colors.white} size={16} />} disabled={loading} onPress={analyze} />
      </View>

      {result && (
        <View style={styles.resultBox}>
          {(() => {
            const isCkd = result.label === "ckd";
            const pct = result.prob_pct;
            return (
              <>
                <ResultInterpretation tone={isCkd ? "critical" : "positive"} emoji={isCkd ? "🩺" : "✅"}
                  title={isCkd ? t("ai.ckd.sonuc.ckdOlasi", { pct }) : t("ai.ckd.sonuc.saglikli", { pct })}
                  text={isCkd
                    ? t("ai.ckd.sonuc.ckdMetin", { pct })
                    : t("ai.ckd.sonuc.dusukMetin", { pct })}
                  points={[t("ai.ckd.nokta1"), t("ai.ckd.nokta2")]} />
                <Text style={[styles.resultText, { fontSize: typography.small, color: colors.textMuted }]}>{t("ai.ckd.model")}{result.model}</Text>
                <XaiSatiri
                  xai={result.xai ?? null}
                  etiketle={(f) => ckdEtiket(f)}
                />
              </>
            );
          })()}
          <MedicalDisclaimer />
        </View>
      )}
    </Card>
  );
}

/** Ses sınıfı kimliği → katalog ANAHTARI (gösterimde `sesSinifAdi` çevirir; bilinmeyen sınıf HAM). */
const CATSOUND_ANAHTARI: Record<string, string> = {
  Angry: "ai.ses.sinif.kizgin",
  Defence: "ai.ses.sinif.savunma",
  Fighting: "ai.ses.sinif.kavga",
  Happy: "ai.ses.sinif.mutlu",
  HuntingMind: "ai.ses.sinif.avModu",
  Mating: "ai.ses.sinif.ciftlesme",
  MotherCall: "ai.ses.sinif.anneCagrisi",
  Paining: "ai.ses.sinif.agri",
  Resting: "ai.ses.sinif.dinlenme",
  Warning: "ai.ses.sinif.uyari",
};
const sesSinifAdi = (sinif: string): string => {
  const k = CATSOUND_ANAHTARI[sinif];
  return k ? i18n.t(k as never) : sinif;
};

/**
 * Kedi Sesi Analizi — miyavdan 10 sınıf duygu/durum (Angry..Warning). Foto/CSV/form DEĞİL — SES.
 * Mikrofonla kaydet (expo-av) VEYA ses dosyası yükle (expo-document-picker). Backend:
 * POST /api/ai/sound/cat (ffmpeg→WAV→librosa mel→EfficientNet_Lite0 ONNX).
 */
function CatSoundModule({ patientName }: { patientName: string }) {
  const { t } = useTranslation();
  const { isCompact } = useResponsive();
  const { showToast } = useToast();
  const [audioUri, setAudioUri] = useState<string | null>(moduleCache.cat_sound?.audioUri ?? null);
  const [fileName, setFileName] = useState<string>(moduleCache.cat_sound?.fileName ?? "");
  const [webFile, setWebFile] = useState<any>(moduleCache.cat_sound?.webFile ?? null);
  /** Sunum-katmanı XAI (Faz 2): opt-in mel ısı haritası (Grad-CAM — pahalı, otomatik değil). */
  const [isiHaritasi, setIsiHaritasi] = useState(false);
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const [isRecording, setIsRecording] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AiResult | null>(moduleCache.cat_sound?.result ?? null);
  const [longLoading, setLongLoading] = useState(false);
  useEffect(() => { moduleCache.cat_sound = { result, audioUri, fileName, webFile }; }, [result, audioUri, fileName, webFile]);

  useEffect(() => {
    if (!loading) { setLongLoading(false); return; }
    const t = setTimeout(() => setLongLoading(true), 8000);
    return () => clearTimeout(t);
  }, [loading]);

  const startRecording = async () => {
    try {
      const perm = await requestRecordingPermissionsAsync();
      if (!perm.granted) { showToast(t("ai.ses.mikrofonIzni"), "error"); return; }
      await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
      setIsRecording(true); setResult(null); setAudioUri(null); setWebFile(null);
    } catch (e) {
      showToast(t("ai.ses.kayitBaslatilamadi"), "error");
    }
  };

  const stopRecording = async () => {
    setIsRecording(false);
    try {
      await recorder.stop();
      const uri = recorder.uri;
      setAudioUri(uri || null); setFileName("kayıt.m4a");
    } catch (e) {
      showToast(t("ai.ses.kayitDurdurulamadi"), "error");
    }
  };

  const pickAudio = async () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file'; input.accept = 'audio/*';
      input.onchange = (e: Event) => {
        const f = (e.target as HTMLInputElement).files?.[0];
        if (f) { setWebFile(f); setFileName(f.name); setAudioUri("web"); setResult(null); }
      };
      input.click();
    } else {
      const res = await DocumentPicker.getDocumentAsync({ type: ["audio/*"], copyToCacheDirectory: true });
      if (!res.canceled && res.assets?.[0]) {
        setAudioUri(res.assets[0].uri); setFileName(res.assets[0].name); setWebFile(null); setResult(null);
      }
    }
  };

  const analyze = async () => {
    const hasta = hastaAnligi(); // D2.E09 (Y87): kayıt analizin BAŞLADIĞI hastaya yazılır
    if (!audioUri) return;
    setLoading(true);
    try {
      // ⚠️ Web'de CANLI KAYIT `webFile` üretmez (yalnız `blob:` URI) — eskiden burada native
      // dalına düşülüp `expo-file-system` çağrılıyor ve web'de çöküyordu. (Native: base64 →
      // `audio_base64`; RN multipart `file://` URI'sini doğrudan okuyamıyor.)
      const formData = await sesFormDataHazirla(
        { webFile, uri: audioUri, fileName: fileName || "sound.mp3" },
        Platform.OS === "web",
        (uri) => FileSystemLegacy.readAsStringAsync(uri, { encoding: "base64" as any }),
      );
      // Sunum-katmanı XAI (Faz 2): kullanıcı açıkça istediyse mel ısı haritası.
      if (isiHaritasi) formData.append("explain", "true");
      const ctrl = new AbortController();
      const to = setTimeout(() => ctrl.abort(), AI_TIMEOUT_MS);
      const response = await fetch(serviceConfig.apiBaseUrl + "/ai/sound/cat", {
        method: "POST", body: formData, headers: { Accept: "application/json", ...authHeaders() }, signal: ctrl.signal,
      });
      clearTimeout(to);
      const data = await response.json();
      if (response.ok && data.status === "success") {
        setResult(data);
        logAiResult(hasta, "Kedi Sesi", `${trValue(data.top_1_class)} %${Math.round((data.top_1_prob ?? 0) * 100)}`, { moduleId: "cat_sound", inputType: "audio", detail: data, confidence: data.top_1_prob });
      } else {
        showToast(aiDetayCumlesi(data?.detail, t("ai.hata.analizSirasinda")), "error");
      }
    } catch (e) {
      showToast(aiHataMesaji(e, t("ai.hata.hataIleti", { ileti: errorMessage(e).slice(0, 120) })), "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card style={styles.card}>
      <Text style={styles.title}>{t("ai.ses.modulBaslik")}</Text>
      <Text style={styles.subtitle}>{t("ai.ses.modulAciklama")}</Text>

      <View style={styles.photoGuide}>
        <Text style={styles.photoGuideTitle}>{t("ai.ses.ipuclariBaslik")}</Text>
        <Text style={styles.photoGuideItem}><Trans i18nKey="ai.ses.ipucuKayit" components={{ kalin: <Text style={styles.photoGuideBold} /> }} /></Text>
        <Text style={styles.photoGuideItem}>{t("ai.ses.ipucuNet")}</Text>
        <Text style={styles.photoGuideItem}>{t("ai.ses.ipucuDosya")}</Text>
      </View>

      <View style={styles.soundStatusBox}>
        {isRecording ? (
          <View style={{ alignItems: "center" }}>
            <View style={styles.recDot} />
            <Text style={styles.recText}>{t("ai.ses.kaydediliyor")}</Text>
          </View>
        ) : audioUri ? (
          <View style={{ alignItems: "center" }}>
            <AudioLines color={colors.primary} size={40} />
            <Text style={styles.soundFileName} numberOfLines={1}>🎵 {fileName}</Text>
          </View>
        ) : (
          <View style={{ alignItems: "center" }}>
            <Mic color={colors.textMuted} size={40} />
            <Text style={styles.placeholderText}>{t("ai.ses.sesSecilmedi")}</Text>
          </View>
        )}
      </View>

      <View style={styles.btnRow}>
        <View style={{ flex: 1 }}>
          <Button
            label={isRecording ? t("ai.ses.durdur") : t("ai.ses.kaydet")}
            variant={isRecording ? "danger" : "primary"}
            icon={isRecording ? <Square color={colors.white} size={16} /> : <Mic color={colors.white} size={16} />}
            onPress={isRecording ? stopRecording : startRecording}
          />
        </View>
        <View style={{ flex: 1 }}>
          <Button label={t("ai.ses.sesYukle")} variant="secondary" icon={<FileText color={colors.primary} size={16} />} onPress={pickAudio} disabled={isRecording} />
        </View>
      </View>

      <TouchableOpacity
        style={styles.xaiToggle}
        onPress={() => setIsiHaritasi((v) => !v)}
        accessibilityRole="switch"
        accessibilityState={{ checked: isiHaritasi }}
        accessibilityLabel={t("ai.ses.melEtiketi")}
      >
        <Text style={styles.xaiToggleText}>
          {isiHaritasi ? "☑" : "☐"}{t("ai.ses.melGoster")}
        </Text>
      </TouchableOpacity>
      <View style={styles.analyzeBtn}>
        <Button variant="primary" label={loading ? t("ai.ortak.analizEdiliyor") : t("ai.ses.analiziBaslat")} icon={loading ? <ActivityIndicator color={colors.white} /> : <Sparkles color={colors.white} size={16} />} disabled={!audioUri || loading || isRecording} onPress={analyze} />
      </View>
      {longLoading && <Text style={styles.modelHint}>{t("ai.ortak.modelHazirlaniyor")}</Text>}

      {result && (
        <View style={styles.resultBox}>
          {(() => {
            const tc = result.top_1_class ?? "";
            const a = catSoundAdvice()[tc];
            const tone: InterpTone = a ? (a.tone === "positive" ? "positive" : a.tone === "pain" ? "critical" : a.tone === "alert" ? "alert" : "info") : "info";
            const pct = Math.round((result.top_1_prob || 0) * 100);
            return <ResultInterpretation tone={tone} emoji={a?.emoji || "🐈"}
              title={t("ai.ses.baslikYuzde", { ad: a?.title || sesSinifAdi(tc), pct })}
              text={a?.text || t("ai.ses.analizEdildi")}
              points={[t("ai.ses.nokta1")]} />;
          })()}
          <Text style={styles.ctSubLabel}>{t("ai.ses.enOlasi3")}</Text>
          <View style={{ marginTop: 2 }}>
            {(result.top_k || []).map((sk: AiTopK, i: number) => {
              const pct = Math.round(sk.prob * 100);
              return (
                <View key={i} style={[styles.soundBarRow, isCompact && styles.soundBarRowCompact]}>
                  {/* [S7 adım 9] Dar ekranda etiket ve yüzde ÜSTTE tek satırda, çubuk altta tam
                      genişlikte: aynı satırda çubuk 30-40 px'e düşüp okunmaz oluyordu. */}
                  <View style={isCompact ? styles.soundBarUst : styles.soundBarSatirIci}>
                    <Text style={styles.soundBarLabel} numberOfLines={1}>{i + 1}. {sesSinifAdi(sk.class)}</Text>
                    {isCompact ? <Text style={styles.soundBarPct}>{t("ai.ortak.yuzde", { deger: pct })}</Text> : null}
                  </View>
                  <View style={[styles.soundBarTrack, isCompact && { flex: 0, width: "100%" }]}>
                    <View style={[styles.soundBarFill, { width: (`${Math.max(2, pct)}%` as any) }]} />
                  </View>
                  {isCompact ? null : <Text style={styles.soundBarPct}>{t("ai.ortak.yuzde", { deger: pct })}</Text>}
                </View>
              );
            })}
          </View>
          {/* Sunum-katmanı XAI (Faz 2): mel-spektrogram ısı haritası — istenip üretildiyse. */}
          {result.xai_image_base64 && (
            <XaiIsiHaritasi base64={result.xai_image_base64} etiket={t("ai.ses.melIsiHaritasi")} />
          )}
          {result.xai_error && <Text style={styles.xaiSatiri}>🔍 {result.xai_error}</Text>}
          <MedicalDisclaimer />
        </View>
      )}
    </Card>
  );
}

/** CT sınıf kimliği → katalog ANAHTARI (gösterimde `ctSinifAdi` çevirir; bilinmeyen sınıf HAM). */
const CT_ANAHTARI: Record<string, string> = { "Kidney Stone": "ai.ct.sinif.tas", "Kidney": "ai.ct.sinif.bobrek", "Kidney Cyst": "ai.ct.sinif.kist" };
const ctSinifAdi = (ad: string): string => {
  const k = CT_ANAHTARI[ad];
  return k ? i18n.t(k as never) : ad;
};

/**
 * Böbrek CT Analizi — CT görüntüsünde YOLOv8s ile taş/böbrek/kist tespiti (3 sınıf).
 * Backend: POST /api/ai/vision/kidney_ct → annotated görsel + sınıf sayıları + tespit listesi.
 */
function KidneyCTModule({ patientName }: { patientName: string }) {
  const { t } = useTranslation();
  // [S1 adım 7 / aihub-10] Sahne yüksekliği CANLI: pencere küçülünce/cihaz yan yatınca daralır.
  const sahneH = useStageHeight();
  // Galeri ASIL okuma yuzeyi: daha yuksek tavan, AYNI responsive oran (bkz. useGaleriYuksekligi).
  const galeriH = useGaleriYuksekligi();
  const { showToast } = useToast();
  const CK = "/vision/kidney_ct";
  const [imageUri, setImageUri] = useState<string | null>(visionCache[CK]?.imageUri ?? null);
  const [imageBase64, setImageBase64] = useState<string | null>(visionCache[CK]?.imageBase64 ?? null);
  const [imageFile, setImageFile] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AiResult | null>(visionCache[CK]?.result ?? null);
  const [longLoading, setLongLoading] = useState(false);
  // XAI opt-in (plan §KALAN A1): backend explain'i destekliyordu, düğme yoktu.
  const [isiHaritasi, setIsiHaritasi] = useState(false);
  const { isCompact } = useResponsive();

  useEffect(() => { visionCache[CK] = { imageUri, imageBase64, result }; }, [imageUri, imageBase64, result]);
  useEffect(() => {
    if (!loading) { setLongLoading(false); return; }
    const t = setTimeout(() => setLongLoading(true), 8000);
    return () => clearTimeout(t);
  }, [loading]);

  const takePhoto = async () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file'; input.accept = 'image/*'; (input as any).capture = 'environment';
      input.onchange = (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0];
        if (file) { if (imageUri && imageUri.startsWith('blob:')) URL.revokeObjectURL(imageUri); setImageBase64(null); setResult(null); void webIcinKucult(file).then((k) => { setImageFile(k); setImageUri(URL.createObjectURL(k)); }); }
      };
      input.click();
    } else {
      const res = await ImagePicker.launchCameraAsync({ allowsEditing: false, quality: 0.8, base64: true });
      if (!res.canceled) { const shrunk = await shrinkForUpload(res.assets[0].uri); setImageUri(shrunk.uri); setImageBase64(shrunk.base64); setImageFile((res.assets[0] as any).file || null); setResult(null); }
    }
  };

  const pickImage = async () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file'; input.accept = 'image/*';
      input.onchange = (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0];
        if (file) { if (imageUri && imageUri.startsWith('blob:')) URL.revokeObjectURL(imageUri); setImageBase64(null); setResult(null); void webIcinKucult(file).then((k) => { setImageFile(k); setImageUri(URL.createObjectURL(k)); }); }
      };
      input.click();
    } else {
      const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, allowsEditing: false, quality: 0.8, base64: true });
      if (!res.canceled) { const shrunk = await shrinkForUpload(res.assets[0].uri); setImageUri(shrunk.uri); setImageBase64(shrunk.base64); setImageFile((res.assets[0] as any).file || null); setResult(null); }
    }
  };

  const analyze = async () => {
    const hasta = hastaAnligi(); // D2.E09 (Y87): kayıt analizin BAŞLADIĞI hastaya yazılır
    if (!imageUri) return;
    setLoading(true);
    try {
      const formData = new FormData();
      if (Platform.OS === 'web') {
        let blob: Blob | null = null;
        if (imageFile) blob = imageFile;
        else if (imageBase64) { const bstr = atob(imageBase64); let n = bstr.length; const u8 = new Uint8Array(n); while (n--) u8[n] = bstr.charCodeAt(n); blob = new Blob([u8], { type: 'image/jpeg' }); }
        else { const r = await fetch(imageUri); blob = await r.blob(); }
        if (!blob) throw new Error("Görüntü hazırlanamadı.");
        formData.append("file", blob, "ct.jpg");
      } else {
        if (imageBase64) formData.append("image_base64", imageBase64);
        else formData.append("file", { uri: imageUri, name: "ct.jpg", type: "image/jpeg" } as any);
      }
      if (isiHaritasi) formData.append("explain", "true");
      const ctrl = new AbortController();
      const to = setTimeout(() => ctrl.abort(), AI_TIMEOUT_MS);
      const response = await fetch(serviceConfig.apiBaseUrl + "/ai/vision/kidney_ct", { method: "POST", body: formData, headers: { Accept: "application/json", ...authHeaders() }, signal: ctrl.signal });
      clearTimeout(to);
      const data = await response.json();
      if (response.ok && data.status === "success") {
        setResult(data);
        const c = data.class_counts || {};
        logAiResult(hasta, "Böbrek CT", `${data.n_detections} tespit (taş:${c["Kidney Stone"] ?? 0} kist:${c["Kidney Cyst"] ?? 0})`, { moduleId: "kidney_ct", inputType: "image", detail: data });
      } else {
        showToast(aiDetayCumlesi(data?.detail, t("ai.hata.analizSirasinda")), "error");
      }
    } catch (e) {
      showToast(aiHataMesaji(e), "error");
    } finally {
      setLoading(false);
    }
  };

  const cc = result?.class_counts || {};
  const nStone = cc["Kidney Stone"] ?? 0;
  const nCyst = cc["Kidney Cyst"] ?? 0;
  const nKidney = cc["Kidney"] ?? 0;
  const dets = result?.detections || [];
  // Özet cümle
  const parts: string[] = [];
  if (nKidney) parts.push(t("ai.ct.parcaBobrek", { count: nKidney }));
  if (nCyst) parts.push(t("ai.ct.parcaKist", { count: nCyst }));
  if (nStone) parts.push(t("ai.ct.parcaTas", { count: nStone }));
  const summary = parts.length ? t("ai.ct.ozet", { parcalar: parts.join(", ") }) : t("ai.ct.ozetYok");
  // Aynı sınıftan birden çok tespiti görüntüdeki yatay konuma göre ayırt et (kullanıcı hangi böbrek olduğunu görsün)
  const byClass: Record<string, any[]> = {};
  dets.forEach((d: AiDetection) => { (byClass[d.class_name] = byClass[d.class_name] || []).push(d); });
  const cx = (d: AiDetection) => (((d.bbox_xyxy?.[0] ?? 0) + (d.bbox_xyxy?.[2] ?? 0)) / 2);
  const posLabel = (d: AiDetection) => {
    const g = byClass[d.class_name] || [];
    if (g.length < 2) return "";
    const sorted = [...g].sort((a, b) => cx(a) - cx(b));
    const idx = sorted.indexOf(d);
    if (g.length === 2) return idx === 0 ? t("ai.ct.solda") : t("ai.ct.sagda");
    return t("ai.ct.soldanSira", { sira: idx + 1 });
  };
  return (
    <Card style={styles.card}>
      <Text style={styles.title}>{t("ai.ct.baslik")}</Text>
      <Text style={styles.subtitle}>{t("ai.ct.aciklama")}</Text>

      {!imageUri && (
        <View style={styles.photoGuide}>
          <Text style={styles.photoGuideTitle}>{t("ai.ct.ipucuBaslik")}</Text>
          <Text style={styles.photoGuideItem}>{t("ai.ct.ipucuNet")}</Text>
          <Text style={styles.photoGuideItem}>{t("ai.ct.ipucuRenk")}</Text>
        </View>
      )}

      {/* ⚠️ ÇOK PANELLİ GALERİ (ADIM 4). Eskiden burada şu ternary vardı:
            `uri: result?.image_base64 ? 'data:…' : imageUri`
          → sonuç gelir gelmez kullanıcının GİRDİSİ ekrandan siliniyordu; üstelik gösterilen tek
          şey okunmaz `07_combined` mozaiğiydi (panel başına ~81 px). Artık backend'in ürettiği
          7 panel de gezilebilir ve girdi bir çip uzaklıkta. */}
      <GorselSahne
        sayfalar={sahneSayfalari(result, imageUri)}
        tavanY={galeriH}
        sifirlaAnahtari={imageUri}
        testID="kidneyct-sahne"
          bos={
            <View style={[styles.imagePreviewContainer, { height: sahneH }]}>
              <View style={styles.placeholderBox}><ImageIcon color={colors.textMuted} size={48} /><Text style={styles.placeholderText}>{t("ai.ortak.goruntuSecilmedi")}</Text></View>
            </View>
          }
      />

      <View style={styles.btnRow}>
        <View style={{ flex: 1 }}><Button label={t("ai.ortak.galeridenSec")} icon={<ImageIcon color={colors.white} size={16} />} onPress={pickImage} /></View>
      </View>

      <TouchableOpacity style={styles.xaiToggle} accessibilityRole="switch" accessibilityState={{ checked: isiHaritasi }} onPress={() => setIsiHaritasi(!isiHaritasi)}>
        <Text style={styles.xaiToggleText}>{isiHaritasi ? "☑" : "☐"}{t("ai.ct.isiHaritasiUret")}</Text>
      </TouchableOpacity>

      <View style={styles.analyzeBtn}>
        <Button variant="primary" label={loading ? t("ai.ortak.analizEdiliyor") : t("ai.ct.analiziBaslat")} icon={loading ? <ActivityIndicator color={colors.white} /> : <Sparkles color={colors.white} size={16} />} disabled={!imageUri || loading} onPress={analyze} />
      </View>
      {longLoading && <Text style={styles.modelHint}>{t("ai.ortak.modelHazirlaniyor")}</Text>}

      {result && (
        <View style={styles.resultBox}>
          <Text style={styles.resultTitle}>{t("ai.ortak.analizSonucu")}</Text>

          {/* Özet cümle */}
          <Text style={[styles.resultText, { marginBottom: 6 }]}>{summary}</Text>

          {/* Bulgu vurgusu */}
          {(nStone > 0 || nCyst > 0) ? (
            <View style={[styles.ctFindingChip, { backgroundColor: nStone > 0 ? colors.danger + "22" : colors.warning + "22", borderColor: nStone > 0 ? colors.danger : colors.warning }]}>
              <Text style={[styles.resultText, { fontWeight: "800", color: nStone > 0 ? colors.danger : colors.warning }]}>
                {t("ai.ct.bulgu", { parcalar: [nStone > 0 ? t("ai.ct.bulguTas", { count: nStone }) : "", nCyst > 0 ? t("ai.ct.parcaKist", { count: nCyst }) : ""].filter(Boolean).join(" + ") })}
              </Text>
            </View>
          ) : (
            <View style={[styles.ctFindingChip, { backgroundColor: colors.success + "22", borderColor: colors.success }]}>
              <Text style={[styles.resultText, { fontWeight: "800", color: colors.success }]}>{t("ai.ct.bulguYok")}</Text>
            </View>
          )}

          {/* Tespit sayıları */}
          <Text style={styles.ctSubLabel}>{t("ai.ct.sayilar")}</Text>
          <Text style={styles.resultText}>{t("ai.ct.sayiTas")}<Text style={{ fontWeight: "bold", color: nStone > 0 ? colors.danger : colors.textMuted }}>{nStone}</Text></Text>
          <Text style={styles.resultText}>{t("ai.ct.sayiKist")}<Text style={{ fontWeight: "bold", color: nCyst > 0 ? colors.warning : colors.textMuted }}>{nCyst}</Text></Text>
          <Text style={styles.resultText}>{t("ai.ct.sayiDoku")}<Text style={{ fontWeight: "bold", color: nKidney > 0 ? colors.success : colors.textMuted }}>{nKidney}</Text></Text>

          {/* Tespit detayları — numaralı + konumlu + güven açıklamalı */}
          {dets.length > 0 && (
            <>
              <Text style={styles.ctSubLabel}>{t("ai.ct.detaylar")}</Text>
              {dets.map((d: AiDetection, i: number) => (
                <Text key={i} style={[styles.resultText, { fontSize: typography.small }]}>
                  {i + 1}. {ctSinifAdi(d.class_name)}
                  <Text style={{ color: colors.textMuted }}>{posLabel(d)}</Text>
                  {t("ai.ct.guven")}
                  <Text style={{ fontWeight: "bold" }}>{t("ai.ortak.yuzde", { deger: Math.round((d.conf || 0) * 100) })}</Text>
                </Text>
              ))}
              <Text style={styles.ctHint}>{t("ai.ct.guvenNotu")}</Text>
            </>
          )}
          {result.xai_image_base64 ? (
            <XaiIsiHaritasi base64={result.xai_image_base64} etiket={t("ai.ct.isiHaritasi")}
              not={dets.length > 0
                ? t("ai.ct.isiHaritasiNot")
                : tespitYokHaritaNotu()} />
          ) : null}
          {result.xai_error ? <Text style={styles.xaiSatiri}>🔍 {result.xai_error}</Text> : null}
          <MedicalDisclaimer />
        </View>
      )}
    </Card>
  );
}

/** Histopatoloji sınıf kimliği → katalog ANAHTARI (gösterimde `dereceAdi` çevirir; bilinmeyen kimlik HAM). */
const HISTO_ANAHTARI: Record<string, string> = { grade0: "ai.patoloji.derece.g0", grade1: "ai.patoloji.derece.g1", grade2: "ai.patoloji.derece.g2", grade3: "ai.patoloji.derece.g3", grade4: "ai.patoloji.derece.g4" };
const dereceAdi = (derece: string): string => {
  const k = HISTO_ANAHTARI[derece];
  return k ? i18n.t(k as never) : derece;
};
const HISTO_COLOR: Record<string, string> = { grade0: colors.success, grade1: "#84CC16", grade2: colors.warning, grade3: "#F97316", grade4: colors.danger };

/**
 * Böbrek Histopatoloji Analizi — doku (biyopsi) görüntüsünde V22-KMC-ClassicTrio ensemble ile
 * grade0–grade4 derece sınıflandırması. Backend: POST /api/ai/vision/histopath → grade + top-k +
 * olasılıklar (sınıflandırıcı, detektör değil → overlay yok, orijinal görüntü gösterilir).
 */
function HistopathModule({ patientName }: { patientName: string }) {
  const { t } = useTranslation();
  // [S1 adım 7 / aihub-10] Sahne yüksekliği CANLI: pencere küçülünce/cihaz yan yatınca daralır.
  const sahneH = useStageHeight();
  const { showToast } = useToast();
  const CK = "/vision/histopath";
  const [imageUri, setImageUri] = useState<string | null>(visionCache[CK]?.imageUri ?? null);
  const [imageBase64, setImageBase64] = useState<string | null>(visionCache[CK]?.imageBase64 ?? null);
  const [imageFile, setImageFile] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AiResult | null>(visionCache[CK]?.result ?? null);
  const [longLoading, setLongLoading] = useState(false);
  // XAI opt-in (plan §KALAN A1): ensemble HiRes-CAM + kararsızlık; CPU'da DAKİKALAR.
  const [isiHaritasi, setIsiHaritasi] = useState(false);
  const { isCompact } = useResponsive();

  useEffect(() => { visionCache[CK] = { imageUri, imageBase64, result }; }, [imageUri, imageBase64, result]);
  useEffect(() => {
    if (!loading) { setLongLoading(false); return; }
    const t = setTimeout(() => setLongLoading(true), 8000);
    return () => clearTimeout(t);
  }, [loading]);

  const takePhoto = async () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file'; input.accept = 'image/*'; (input as any).capture = 'environment';
      input.onchange = (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0];
        if (file) { if (imageUri && imageUri.startsWith('blob:')) URL.revokeObjectURL(imageUri); setImageBase64(null); setResult(null); void webIcinKucult(file).then((k) => { setImageFile(k); setImageUri(URL.createObjectURL(k)); }); }
      };
      input.click();
    } else {
      const res = await ImagePicker.launchCameraAsync({ allowsEditing: false, quality: 0.8, base64: true });
      if (!res.canceled) { const shrunk = await shrinkForUpload(res.assets[0].uri); setImageUri(shrunk.uri); setImageBase64(shrunk.base64); setImageFile((res.assets[0] as any).file || null); setResult(null); }
    }
  };

  const pickImage = async () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file'; input.accept = 'image/*';
      input.onchange = (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0];
        if (file) { if (imageUri && imageUri.startsWith('blob:')) URL.revokeObjectURL(imageUri); setImageBase64(null); setResult(null); void webIcinKucult(file).then((k) => { setImageFile(k); setImageUri(URL.createObjectURL(k)); }); }
      };
      input.click();
    } else {
      const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, allowsEditing: false, quality: 0.8, base64: true });
      if (!res.canceled) { const shrunk = await shrinkForUpload(res.assets[0].uri); setImageUri(shrunk.uri); setImageBase64(shrunk.base64); setImageFile((res.assets[0] as any).file || null); setResult(null); }
    }
  };

  const analyze = async () => {
    const hasta = hastaAnligi(); // D2.E09 (Y87): kayıt analizin BAŞLADIĞI hastaya yazılır
    if (!imageUri) return;
    setLoading(true);
    try {
      const formData = new FormData();
      if (Platform.OS === 'web') {
        let blob: Blob | null = null;
        if (imageFile) blob = imageFile;
        else if (imageBase64) { const bstr = atob(imageBase64); let n = bstr.length; const u8 = new Uint8Array(n); while (n--) u8[n] = bstr.charCodeAt(n); blob = new Blob([u8], { type: 'image/jpeg' }); }
        else { const r = await fetch(imageUri); blob = await r.blob(); }
        if (!blob) throw new Error("Görüntü hazırlanamadı.");
        formData.append("file", blob, "histo.jpg");
      } else {
        if (imageBase64) formData.append("image_base64", imageBase64);
        else formData.append("file", { uri: imageUri, name: "histo.jpg", type: "image/jpeg" } as any);
      }
      if (isiHaritasi) formData.append("explain", "true");
      const ctrl = new AbortController();
      const to = setTimeout(() => ctrl.abort(), AI_TIMEOUT_MS);
      const response = await fetch(serviceConfig.apiBaseUrl + "/ai/vision/histopath", { method: "POST", body: formData, headers: { Accept: "application/json", ...authHeaders() }, signal: ctrl.signal });
      clearTimeout(to);
      const data = await response.json();
      if (response.ok && data.status === "success") {
        setResult(data);
        logAiResult(hasta, "Böbrek Patoloji", `${trValue(data.top_1_class)} %${Math.round((data.top_1_prob || 0) * 100)}`, { moduleId: "histopath", inputType: "image", detail: data, confidence: data.top_1_prob });
      } else {
        showToast(aiDetayCumlesi(data?.detail, t("ai.hata.analizSirasinda")), "error");
      }
    } catch (e) {
      showToast(aiHataMesaji(e), "error");
    } finally {
      setLoading(false);
    }
  };

  const topClass = result?.top_1_class ?? "";
  return (
    <Card style={styles.card}>
      <Text style={styles.title}>{t("ai.patoloji.baslik")}</Text>
      <Text style={styles.subtitle}>{t("ai.patoloji.aciklama")}</Text>

      {!imageUri && (
        <View style={styles.photoGuide}>
          <Text style={styles.photoGuideTitle}>{t("ai.patoloji.ipucuBaslik")}</Text>
          <Text style={styles.photoGuideItem}>{t("ai.patoloji.ipucuNet")}</Text>
          <Text style={styles.photoGuideItem}>{t("ai.patoloji.ipucuDerece")}</Text>
        </View>
      )}

      <View style={[styles.imagePreviewContainer, { height: sahneH }]}>
        {imageUri ? (
          <Image source={{ uri: imageUri }} style={styles.imagePreview} resizeMode="contain" />
        ) : (
          <View style={styles.placeholderBox}><ImageIcon color={colors.textMuted} size={48} /><Text style={styles.placeholderText}>{t("ai.ortak.goruntuSecilmedi")}</Text></View>
        )}
      </View>

      <View style={styles.btnRow}>
        <View style={{ flex: 1 }}><Button label={t("ai.ortak.galeridenSec")} icon={<ImageIcon color={colors.white} size={16} />} onPress={pickImage} /></View>
      </View>

      <TouchableOpacity style={styles.xaiToggle} accessibilityRole="switch" accessibilityState={{ checked: isiHaritasi }} onPress={() => setIsiHaritasi(!isiHaritasi)}>
        <Text style={styles.xaiToggleText}>{isiHaritasi ? "☑" : "☐"} {t("ai.patoloji.isiHaritasiUret")}</Text>
      </TouchableOpacity>

      <View style={styles.analyzeBtn}>
        <Button variant="primary" label={loading ? t("ai.ortak.analizEdiliyor") : t("ai.patoloji.analiziBaslat")} icon={loading ? <ActivityIndicator color={colors.white} /> : <Sparkles color={colors.white} size={16} />} disabled={!imageUri || loading} onPress={analyze} />
      </View>
      {longLoading && <Text style={styles.modelHint}>{t("ai.patoloji.modelHazirlaniyor")}</Text>}

      {result && (
        <View style={styles.resultBox}>
          <Text style={styles.resultTitle}>{t("ai.ortak.analizSonucu")}</Text>
          <View style={[styles.ctFindingChip, { backgroundColor: (HISTO_COLOR[topClass] || colors.text) + "22", borderColor: HISTO_COLOR[topClass] || colors.text }]}>
            <Text style={[styles.resultText, { fontWeight: "800", color: HISTO_COLOR[topClass] || colors.text }]}>
              {t("ai.patoloji.tahmin", { derece: dereceAdi(topClass), pct: Math.round((result.top_1_prob || 0) * 100) })}
            </Text>
          </View>

          <Text style={styles.ctSubLabel}>{t("ai.patoloji.tumDereceler")}</Text>
          {(result.top_k || []).map((sk: AiTopK, i: number) => {
            const pct = Math.round((sk.prob || 0) * 100);
            return (
              <View key={i} style={styles.soundBarRow}>
                <Text style={styles.soundBarLabel} numberOfLines={1}>{String(sk.class).replace("grade", "Grade ")}</Text>
                <View style={styles.soundBarTrack}>
                  <View style={[styles.soundBarFill, { width: (`${Math.max(2, pct)}%` as any), backgroundColor: HISTO_COLOR[sk.class] || colors.primary }]} />
                </View>
                <Text style={styles.soundBarPct}>{t("ai.ortak.yuzde", { deger: pct })}</Text>
              </View>
            );
          })}
          <Text style={styles.ctHint}>{t("ai.patoloji.guvenNotu")}</Text>
          {result.xai_image_base64 ? (
            <XaiIsiHaritasi base64={result.xai_image_base64} etiket={t("ai.patoloji.konsensusEtiketi")}
              not={t("ai.patoloji.konsensusNot")} />
          ) : null}
          {result.xai_disagreement_base64 ? (
            <XaiIsiHaritasi base64={result.xai_disagreement_base64} etiket={t("ai.patoloji.kararsizlikEtiketi")} testID="xai-kararsizlik-haritasi"
              not={t("ai.patoloji.kararsizlikNot")} />
          ) : null}
          {result.xai_error ? <Text style={styles.xaiSatiri}>🔍 {result.xai_error}</Text> : null}
          <MedicalDisclaimer />
        </View>
      )}
    </Card>
  );
}

/** Organ kimliği → katalog ANAHTARI (gösterimde `organAdi` çevirir; bilinmeyen kimlik HAM). */
const ORGAN_ANAHTARI: Record<string, string> = {
  mide: "ai.organ.ad.mide",
  bobrek: "ai.organ.ad.bobrek",
  karaciger: "ai.organ.ad.karaciger",
  mesane: "ai.organ.ad.mesane",
  pankreas: "ai.organ.ad.pankreas",
  bagirsak: "ai.organ.ad.bagirsak",
  kalp: "ai.organ.ad.kalp",
  dalak: "ai.organ.ad.dalak",
  akciger_sag: "ai.organ.ad.akciger_sag",
  akciger_sol: "ai.organ.ad.akciger_sol",
};
const organAdi = (organ: string): string => {
  const k = ORGAN_ANAHTARI[organ];
  return k ? i18n.t(k as never) : organ;
};
const relColor = (r: number) => (r >= 0.6 ? colors.success : r >= 0.4 ? colors.warning : colors.danger);

/**
 * Kedi Organ 3B Lokalizasyon — kedi fotoğrafından 10 organın 3B konumu (YOLOseg+DLC+RTMPose+PnP).
 * Backend: POST /api/ai/vision/cat_organ → organ overlay + organ tablosu (3B koordinat + güven).
 */
// ── Yara Kapanma (Scratch) — plan: guii/scratch-entegrasyon-plani.md v3 (§5) ─────────────────
// TEK girdi → ÇOKLU görsel çıktı; butonlu galeri (dikey istif DEĞİL — 6 görsel ekranı kaydırır).
// TIF gerçekleri (plan v2 §2/11, ÖLÇÜLDÜ): tarayıcı/RN Image TIF RENDER EDEMEZ ve shrinkForUpload
// (a) TIFF decode edemez (b) 1500px JPEG'e küçültür — µm/mm² ÖLÇÜMÜNÜ BOZAR. Bu modül shrink'i
// BYPASS eder: HAM dosya file-part gider (base64 form-part Starlette 1MB sınırına takılır),
// önizleme yerine dosya-adı gösterilir, orijinal [Orijinal] sekmesinde sunucu JPEG'iyle gelir.
// Modül-LOKAL 300sn timeout: 872MB CPN soğuk başlatması CPU'da dakikalar (karar 0.1) — global
// AI_TIMEOUT_MS'e DOKUNULMAZ (13 modülü etkiler).
const SCRATCH_TIMEOUT_MS = 300_000;
const SCRATCH_OBJEKTIFLER = [
  { ad: "4×", pmm: "0.0016" }, { ad: "10×", pmm: "0.00065" },
  { ad: "20×", pmm: "0.00033" }, { ad: "40×", pmm: "0.00016" },
] as const;
const SCRATCH_GALERI: { k: string; ad: string; alan: keyof AiResult; not: string }[] = [
  { k: "closure", ad: "ai.scratch.galeri.kapanma.ad", alan: "closure_image_base64", not: "ai.scratch.galeri.kapanma.not" },
  { k: "analysis", ad: "ai.scratch.galeri.analiz.ad", alan: "analysis_image_base64", // ⚠️ ESKİ METİN "yaraya dik" diyordu ve çizim de öyleydi: dikey yara seçilince YATAY
    // kuşak çiziliyordu (2026-09-09 sahip bildirimi). Kuşak yarayı İÇİNE alır.
    not: "ai.scratch.galeri.analiz.not" },
  { k: "seg", ad: "ai.modul.segmentasyon.ad", alan: "seg_image_base64", not: "ai.scratch.galeri.seg.not" },
  { k: "overlay", ad: "ai.scratch.galeri.overlay.ad", alan: "overlay_image_base64", not: "ai.scratch.galeri.overlay.not" },
  { k: "input", ad: "ai.scratch.galeri.input.ad", alan: "input_image_base64", not: "ai.scratch.galeri.input.not" },
  { k: "xai", ad: "ai.scratch.galeri.xai.ad", alan: "xai_image_base64", not: "ai.scratch.galeri.xai.not" },
  { k: "panel", ad: "ai.scratch.galeri.panel.ad", alan: "xai_side_by_side_base64", not: "ai.scratch.galeri.panel.not" },
];
type ScratchKayit = { etiket: string; closure_pct: number; mean_gap_um: number };

function ScratchModule({ patientName }: { patientName: string }) {
  const { t } = useTranslation();
  // [S1 adım 7 / aihub-10] Sahne yüksekliği CANLI: pencere küçülünce/cihaz yan yatınca daralır.
  const sahneH = useStageHeight();
  const CK = "cell_scratch";
  const onceki = moduleCache[CK] || {};
  const [dosya, setDosya] = useState<{ uri: string | null; name: string; file: File | null } | null>(onceki.dosya ?? null);
  const [yon, setYon] = useState<"dikey" | "yatay">(onceki.yon ?? "dikey");
  const [pmm, setPmm] = useState<string>(onceki.pmm ?? "0.0016");
  const [xaiAc, setXaiAc] = useState<boolean>(onceki.xaiAc ?? false);
  const [result, setResult] = useState<AiResult | null>(onceki.result ?? null);
  const [galeri, setGaleri] = useState<string>(onceki.galeri ?? "closure");
  const [loading, setLoading] = useState(false);
  const [longLoading, setLongLoading] = useState(false);
  const [yenidenGerek, setYenidenGerek] = useState<boolean>(onceki.yenidenGerek ?? false);
  const [kayitlar, setKayitlar] = useState<ScratchKayit[]>(onceki.kayitlar ?? []);
  const [karsiAcik, setKarsiAcik] = useState(false);
  const mountedRef = useRef(true);
  // DÜŞMAN-DOĞRULAMA: 300sn'lik pencerede kullanıcı yeni dosya/parametre seçebilir;
  // ESKİ isteğin yanıtı gelirse sessizce yeni girdinin sonucu sanılırdı → istek-kimliği.
  const istekRef = useRef(0);
  const { showToast } = useToast();
  // ⚠️ D2.E09 (Y87): unmount'ta uçuştaki analiz İPTAL EDİLMEZ — sonuç başlatıldığı hastaya kaydedilir (atılmaz); ekran güncellenmez.
  useEffect(() => () => { mountedRef.current = false; }, []);
  // Kalıcılık: moduleCache (hasta/profil değişince resetAiCachesForOwner temizler — KRİTİK desen).
  // `imageUri` alias'ı BİLİNÇLİ: resetAiCachesForOwner blob revoke'unu bu alandan yapar
  // (düşman-doğrulama: dosya.uri altında saklanan web blob'u temizlikte kaçıyordu).
  useEffect(() => { moduleCache[CK] = { dosya, yon, pmm, xaiAc, result, galeri, yenidenGerek, kayitlar, imageUri: dosya?.uri ?? null }; });

  const parametreDegisti = () => { istekRef.current++; if (result) setYenidenGerek(true); };

  const dosyaSec = async () => {
    if (loading) return; // analiz sürerken girdi değiştirilemez (stale-yanıt yarışı)
    // DocumentPicker (RNA deseni): image/* + image/tiff — native foto seçici TIFF listelemez.
    const res = await DocumentPicker.getDocumentAsync({ type: ["image/*", "image/tiff"], copyToCacheDirectory: true });
    if (res.canceled || !res.assets?.[0]) return;
    const a = res.assets[0];
    istekRef.current++; // olası eski yanıtları geçersiz kıl
    if (dosya?.uri?.startsWith("blob:")) { try { URL.revokeObjectURL(dosya.uri); } catch { /* ignore */ } }
    setDosya({ uri: a.uri, name: a.name || "goruntu", file: (a as any).file || null });
    setResult(null); setYenidenGerek(false);
  };

  /**
   * Girdi önizlemesinin kaynağı — TEK yerde türetilir.
   *  · png/jpg/webp/bmp: yerel dosya URI'si (anında görünür)
   *  · tif/tiff: tarayıcı render EDEMEZ → analizden sonra sunucunun JPEG'i
   *  · seçim yok: önizleme yok
   */
  const onizlemeKaynagi = (() => {
    if (!dosya) return null;
    if (/\.(png|jpe?g|webp|bmp)$/i.test(dosya.name) && dosya.uri) return dosya.uri;
    if (result?.input_image_base64) return `data:image/jpeg;base64,${result.input_image_base64}`;
    return null;
  })();

  const analiz = async () => {
    const hasta = hastaAnligi(); // D2.E09 (Y87): kayıt analizin BAŞLADIĞI hastaya yazılır
    if (!dosya || loading) return;
    setLoading(true); setLongLoading(false);
    const benimIstek = ++istekRef.current;
    const uzun = setTimeout(() => { if (mountedRef.current) setLongLoading(true); }, 8000);
    try {
      const fd = new FormData();
      if (Platform.OS === "web") {
        let blob: Blob | null = dosya.file;
        if (!blob && dosya.uri) blob = await (await fetch(dosya.uri)).blob();
        if (!blob) throw new Error("Dosya okunamadı.");
        fd.append("file", blob, dosya.name);
      } else {
        // ÖLÇÜLMÜŞ (RNA/cat_sound notları): RN multipart file:// URI'sini doğrudan
        // OKUYAMIYOR ("Ağ hatası") → base64 okuyup image_base64 gönderilir (shrink YOK —
        // µm ölçümü bozulmaz). ⚠️ 2026-08-30: base64 FORM ALANI Starlette 1MB part-limitine
        // takılıyordu ("Part exceeded maximum size of 1024KB"); backend artık limiti 32MB'a
        // çıkarıyor (utils/multipart_limit — Request.form patch'i). Eski router dependency
        // _allow_large_upload BU İŞİ YAPAMIYORDU (ölçüldü: FastAPI form-cache'i erken doluyor).
        const b64 = await FileSystemLegacy.readAsStringAsync(dosya.uri!, { encoding: "base64" });
        fd.append("image_base64", b64);
      }
      fd.append("scratch_yonu", yon);
      fd.append("pixel_mm", pmm);
      if (xaiAc) fd.append("explain", "true");
      const ctrl = new AbortController();
      const to = setTimeout(() => ctrl.abort(), SCRATCH_TIMEOUT_MS);
      const r = await fetch(serviceConfig.apiBaseUrl + "/ai/vision/scratch", {
        method: "POST", body: fd,
        headers: { Accept: "application/json", ...authHeaders() }, signal: ctrl.signal,
      });
      clearTimeout(to);
      const data = await r.json();
      if (istekRef.current !== benimIstek) return; // stale yanıt: girdi/parametre değişti
      const basarili = r.ok && data.status === "success";
      // D2.E09 (Y87): kayıt ekrandan BAĞIMSIZ — modül kapansa / hasta değişse de başlatılan hastaya.
      if (basarili) {
        logAiResult(hasta, "Yara Kapanma (Scratch)",
          data.uyari ? "Hücre tespit edilemedi" : `Kapanma %${data.closure?.closure_pct ?? "?"} · ${data.n_cells} hücre`,
          { moduleId: "cell_scratch", inputType: "image", detail: data });
      }
      if (!mountedRef.current) return;
      if (basarili) {
        // B4 (2026-09-03): ısı haritası bu analizde İSTENDİ mi → istenip gelmeyeni sessiz bırakmamak için.
        setResult({ ...data, _xai_istendi: xaiAc }); setYenidenGerek(false);
        // Isı haritası İSTENDİYSE ve geldiyse sahne onunla açılır (diğer modüllerle parite: ısı haritası
        // sonuç kartında hemen görünür). Eskiden hep "Kapanma"ya iniyor, [XAI] chip'i sessiz kalıyordu.
        setGaleri(data.uyari ? "input" : (xaiAc && data.xai_image_base64 ? "xai" : "closure"));
        if (!data.uyari && data.closure) {
          const etiket = dosya.name.replace(/\.[^.]+$/, "");
          // Aynı etiketin tekrar analizi (örn. objektif düzeltmesi) yeni kayıt AÇMAZ,
          // mevcut kaydı günceller — Δ kartı aynı görüntüyü kendisiyle kıyaslamasın.
          setKayitlar((k) => [...k.filter((x) => x.etiket !== etiket).slice(-7), {
            etiket, closure_pct: data.closure.closure_pct, mean_gap_um: data.closure.mean_gap_um,
          }]);
        }
      } else showToast(aiDetayCumlesi(data?.detail || data?.error, t("ai.hata.analizSirasinda")), "error");
    } catch (e) {
      if (mountedRef.current) showToast(aiHataMesaji(e), "error");
    } finally {
      clearTimeout(uzun);
      if (mountedRef.current) { setLoading(false); setLongLoading(false); }
    }
  };

  const aktifGaleri = SCRATCH_GALERI.filter((g) => result && (result as any)[g.alan]);
  const seciliGorsel = aktifGaleri.find((g) => g.k === galeri) || aktifGaleri[0];
  const son2 = kayitlar.slice(-2);

  return (
    <Card style={styles.card}>
      <Text style={styles.title}>{t("ai.modul.yaraKapanma.ad")}</Text>
      <Text style={styles.subtitle}>{t("ai.scratch.aciklama")}</Text>

      <TouchableOpacity style={styles.scFileBtn} onPress={dosyaSec} accessibilityRole="button">
        <FileText size={16} color={colors.textMuted} />
        <Text style={styles.scFileText} numberOfLines={1}>
          {dosya ? dosya.name : t("ai.scratch.dosyaSec")}
        </Text>
      </TouchableOpacity>

      {/* GİRDİ ÖNİZLEMESİ (2026-09-09 sahip isteği: "girdi fotosu görünmüyor, sadece ismi yazıyor").
          ⚠️ shrinkForUpload ÇAĞRILMAZ: bu modül ham dosyayı gönderir çünkü küçültme µm/mm²
          ölçümünü bozar (plan v2 §2/11 ölçümü). Önizleme YALNIZ görüntülemedir, yüklenen veriye
          DOKUNMAZ. TIF'i tarayıcı/RN Image render EDEMEZ → onun önizlemesi analizden sonra
          sunucunun ürettiği JPEG'den (`input_image_base64`) gösterilir. */}
      {onizlemeKaynagi ? (
        <View style={styles.scOnizlemeKutu}>
          <Image source={{ uri: onizlemeKaynagi }} style={styles.imagePreview}
            accessibilityLabel={t("ai.scratch.onizlemeEtiketi", { ad: dosya?.name ?? "" })} />
        </View>
      ) : null}
      {dosya && /\.tiff?$/i.test(dosya.name) && !result?.input_image_base64 && (
        <Text style={styles.ctHint}>
          {t("ai.scratch.tifNotu")}
        </Text>
      )}

      <Text style={styles.ctSubLabel}>{t("ai.scratch.yara")}</Text>
      <View style={styles.scChipRow} accessibilityRole="radiogroup">
        {(["dikey", "yatay"] as const).map((v) => (
          <TouchableOpacity key={v} accessibilityRole="radio" accessibilityState={{ selected: yon === v }}
            style={[styles.scChip, yon === v && styles.scChipOn]}
            onPress={() => { setYon(v); parametreDegisti(); }}>
            <Text style={[styles.scChipText, yon === v && styles.scChipTextOn]}>{v === "dikey" ? t("ai.scratch.dikey") : t("ai.scratch.yatay")}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <Text style={styles.ctSubLabel}>{t("ai.scratch.objektif")}</Text>
      <View style={styles.scChipRow} accessibilityRole="radiogroup">
        {SCRATCH_OBJEKTIFLER.map((o) => (
          <TouchableOpacity key={o.ad} accessibilityRole="radio" accessibilityState={{ selected: pmm === o.pmm }}
            style={[styles.scChip, pmm === o.pmm && styles.scChipOn]}
            onPress={() => { setPmm(o.pmm); parametreDegisti(); }}>
            <Text style={[styles.scChipText, pmm === o.pmm && styles.scChipTextOn]}>{o.ad}</Text>
          </TouchableOpacity>
        ))}
      </View>
      <Text style={styles.ctHint}>{t("ai.scratch.objektifNotu", { pmm })}</Text>

      <TouchableOpacity style={styles.xaiToggle} accessibilityRole="switch" accessibilityState={{ checked: xaiAc }}
        onPress={() => { setXaiAc(!xaiAc); parametreDegisti(); }}>
        <Text style={styles.xaiToggleText}>{xaiAc ? "☑" : "☐"}{t("ai.scratch.isiHaritasiUret")}</Text>
      </TouchableOpacity>

      <Button label={loading ? t("ai.scratch.analizEdiliyor") : t("ai.scratch.analizEt")} onPress={analiz} disabled={!dosya || loading} loading={loading} block />
      {loading && longLoading && (
        <Text style={styles.modelHint}>{t("ai.scratch.modelHazirlaniyor")}</Text>
      )}
      {yenidenGerek && !loading && (
        <Text style={styles.modelHint}>{t("ai.scratch.parametreDegisti")}</Text>
      )}

      {result && (
        <View style={styles.resultBox}>
          {result.uyari ? (
            <Text style={styles.scUyari}>⚠ {result.uyari}</Text>
          ) : (
            <>
              <View style={styles.scMetricRow}>
                <View style={[styles.scMetricBox, styles.scMetricHero]}>
                  <Text style={[styles.scMetricVal, { color: colors.primary }]}>{t("ai.ortak.yuzde", { deger: result.closure?.closure_pct ?? "" })}</Text>
                  <Text style={styles.scMetricLbl}>{t("ai.scratch.galeri.kapanma.ad")}</Text>
                </View>
                <View style={styles.scMetricBox}>
                  <Text style={styles.scMetricVal}>{result.closure?.mean_gap_um} µm</Text>
                  <Text style={styles.scMetricLbl}>{t("ai.scratch.ortGap")}</Text>
                </View>
                <View style={styles.scMetricBox}>
                  <Text style={styles.scMetricVal}>{result.closure?.max_gap_um} µm</Text>
                  <Text style={styles.scMetricLbl}>{t("ai.scratch.maksGap")}</Text>
                </View>
                <View style={styles.scMetricBox}>
                  <Text style={styles.scMetricVal}>{result.n_cells}</Text>
                  <Text style={styles.scMetricLbl}>{t("ai.scratch.hucre")}</Text>
                </View>
              </View>
              <Text style={styles.ctHint}>
                {t("ai.scratch.metrikler", { alan: result.closure?.gap_area_mm2 ?? "", coverage: result.coverage_ratio ?? "", skor: result.score_mean ?? "", cihaz: result.device ?? "" })}
              </Text>
            </>
          )}

          {aktifGaleri.length > 0 && (
            <>
              <View style={styles.scChipRow} accessibilityRole="tablist">
                {aktifGaleri.map((g) => (
                  <TouchableOpacity key={g.k} accessibilityRole="tab" accessibilityState={{ selected: seciliGorsel?.k === g.k }}
                    style={[styles.scChip, seciliGorsel?.k === g.k && styles.scChipOn]} onPress={() => setGaleri(g.k)}>
                    <Text style={[styles.scChipText, seciliGorsel?.k === g.k && styles.scChipTextOn]}>{t(g.ad as never)}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              {seciliGorsel && (
                <>
                  {/* AÇIK yükseklik (plan v2: styles.imagePreview %100-yükseklik tuzağı) */}
                  <Image testID="sc-stage" source={{ uri: `data:image/jpeg;base64,${(result as any)[seciliGorsel.alan]}` }}
                    style={[styles.scStage, { height: sahneH }]} resizeMode="contain" />
                  <Text style={styles.ctHint}>{t(seciliGorsel.not as never)}</Text>
                </>
              )}
              {!result.uyari && (
                <Text style={styles.ctHint}>{t("ai.scratch.goruntuIciNot")}</Text>
              )}
            </>
          )}
          {result.xai_error ? <Text style={styles.xaiSatiri}>🔍 {result.xai_error}</Text> : null}
          {/* B4 (2026-09-03): ısı haritası İSTENDİ ama yanıt ne XAI alanı ne xai_error taşıyorsa SESSİZ KALMA
              (eski backend / XAI üretmeyen sürüm). `!result.uyari` ŞART: hücre-yok `uyari` yolunda backend
              explain'e hiç girmez (tasarım) → orada bu uyarı YANLIŞ teşhis olur (doğrulayıcı mutasyonla kanıtladı). */}
          {(result as any)._xai_istendi && !result.uyari && !result.xai_image_base64 && !result.xai_error ? (
            <Text style={styles.xaiSatiri}>{t("ai.scratch.xaiGelmedi")}</Text>
          ) : null}
          {result.closure_uyari ? <Text style={styles.scUyari}>⚠ {result.closure_uyari}</Text> : null}

          {kayitlar.length >= 2 && (
            <>
              <TouchableOpacity style={[styles.scChip, karsiAcik && styles.scChipOn, { alignSelf: "stretch", alignItems: "center", marginTop: spacing.sm }]}
                onPress={() => setKarsiAcik(!karsiAcik)} accessibilityRole="button">
                <Text style={[styles.scChipText, karsiAcik && styles.scChipTextOn]}>{t("ai.scratch.karsilastir")}</Text>
              </TouchableOpacity>
              {karsiAcik && son2.length === 2 && (
                <View style={styles.scDelta}>
                  <Text style={styles.scDeltaVal}>
                    {t("ai.scratch.delta", { isaret: (son2[1].closure_pct - son2[0].closure_pct) >= 0 ? "+" : "", fark: (son2[1].closure_pct - son2[0].closure_pct).toFixed(1) })}
                  </Text>
                  <Text style={styles.ctHint}>
                    {t("ai.scratch.karsilastirmaSatiri", { e1: son2[0].etiket, p1: son2[0].closure_pct, e2: son2[1].etiket, p2: son2[1].closure_pct, g1: son2[0].mean_gap_um, g2: son2[1].mean_gap_um })}
                  </Text>
                </View>
              )}
            </>
          )}
          <MedicalDisclaimer />
        </View>
      )}
    </Card>
  );
}

function CatOrganModule({ patientName }: { patientName: string }) {
  const { t } = useTranslation();
  // [S1 adım 7 / aihub-10] Sahne yüksekliği CANLI: pencere küçülünce/cihaz yan yatınca daralır.
  const sahneH = useStageHeight();
  // Galeri ASIL okuma yuzeyi: daha yuksek tavan, AYNI responsive oran (bkz. useGaleriYuksekligi).
  const galeriH = useGaleriYuksekligi();
  // [S7 adım 5 / aihub-1] ÖNİZLEME KUTUSU ORAN KİLİDİ. Kutu sabit yükseklikteydi ve canlı
  // kamera ile üzerine bindirilen sunucu overlay'i farklı ölçeklerde oturuyordu: organ işaretleri
  // görüntüyle KAYIYORDU (tıbbi karar ekranı). Kutu artık karenin GERÇEK oranında açık px.
  const [onizlemeW, setOnizlemeW] = useState(0);
  const { width: pencereX, height: pencereY } = useResponsive();
  const { showToast } = useToast();
  const CK = "/vision/cat_organ";
  const [imageUri, setImageUri] = useState<string | null>(visionCache[CK]?.imageUri ?? null);
  const [imageBase64, setImageBase64] = useState<string | null>(visionCache[CK]?.imageBase64 ?? null);
  const [imageFile, setImageFile] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AiResult | null>(visionCache[CK]?.result ?? null);
  const onizlemeKutu =
    onizlemeW > 0 ? kameraKutusu(onizlemeW, kareOrani(result, pencereY > pencereX), pencereY, 0.55) : null;
  const [longLoading, setLongLoading] = useState(false);
  const { isCompact } = useResponsive();

  // Canlı kamera: telefon/web kamerasından periyodik kare → cat_organ analizi → overlay güncelle.
  const [isLive, setIsLive] = useState(false);
  const [facing, setFacing] = useState<"back" | "front">("back");
  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<any>(null);
  // SG.G5 / G6: son canlı karenin durumu + son analiz karesinin yaşı (VisionModule ile AYNI kural — `utils/canliKare`).
  const [canliDurum, setCanliDurum] = useState<CanliDurum | null>(null);
  // TD9 (Y148): canlı oturumun dakika-başı jetonu (sayaç yalnız ücretlendirme etkinken).
  const [canliJeton, setCanliJeton] = useState(0);
  const canliJetonEtkin = useCanliJetonEtkin(isLive);
  const [sonKareZamani, setSonKareZamani] = useState<number | null>(null);
  const [simdi, setSimdi] = useState(() => Date.now());
  const liveLoadingRef = useRef(false);
  // B1: mod geçişinde UÇUŞTAKİ istek sonucu (statik analiz ↔ canlı kare) diğer modun ekranına düşmesin.
  const liveAbortRef = useRef<AbortController | null>(null);
  const isLiveRef = useRef(false);
  useEffect(() => { isLiveRef.current = isLive; }, [isLive]);

  useEffect(() => { visionCache[CK] = { imageUri, imageBase64, result }; }, [imageUri, imageBase64, result]);
  useEffect(() => {
    if (!loading) { setLongLoading(false); return; }
    const t = setTimeout(() => setLongLoading(true), 8000);
    return () => clearTimeout(t);
  }, [loading]);

  // Canlı kare döngüsü — SG.G5 / G6: VisionModule ile AYNI kural (`utils/canliKare`): uyarlamalı (3 modelli ağır hat kendi
  // hızında; önceki kare bitmeden yenisi başlamaz), hata YUTULMAZ (son kare durumu sürekli görünür), "kedi / organ bulunamadı"
  // backend'in BİLGİ yanıtıdır (eskiden 500 → sessiz). Eski sabit `setInterval(capture, 3500)` + `catch {}` kalktı.
  useEffect(() => {
    if (!isLive) return;
    let bitti = false;
    let zamanlayici: ReturnType<typeof setTimeout> | null = null;
    const oturum = canliOturumBaslat(); // TD9: dakika başı jeton — oturum kimliği her kare isteğinde
    setCanliJeton(0);
    const tur = async () => {
      if (bitti) return;
      const bas = Date.now();
      if (!liveLoadingRef.current && cameraRef.current) {
        liveLoadingRef.current = true;
        try {
          // shutterSound: false — canlı organ takibi sık kare alır (saha bildirimi).
          const photo = await cameraRef.current.takePictureAsync({
            quality: 0.6, skipProcessing: true, shutterSound: false,
          });
          const shrunk = photo?.uri ? await shrinkForUpload(photo.uri) : { uri: "", base64: null };
          if (shrunk.base64 && !bitti) {
            const fd = new FormData();
            fd.append("image_base64", shrunk.base64);
            const ctrl = new AbortController();
            liveAbortRef.current = ctrl;
            // CANLI-DONGU: kisa sinir ZORUNLU (uzun timeout kamera akisini kilitler); 3 modelli hat → 25 sn.
            const t = setTimeout(() => ctrl.abort(), 25000);
            try {
              const r = await fetch(serviceConfig.apiBaseUrl + "/ai/vision/cat_organ", {
                method: "POST", body: fd,
                headers: { Accept: "application/json", ...authHeaders(), [CANLI_OTURUM_BASLIGI]: oturum.kimlik },
                signal: ctrl.signal,
              });
              const data = await r.json().catch(() => ({}));
              // B1: "Canlıyı Durdur" sonrası geç gelen kare sonucu boş statik ekrana düşmesin.
              if (bitti || !isLiveRef.current) return;
              const kareDurumu = canliKareDurumu("/vision/cat_organ", r.ok, r.status, data);
              setCanliDurum(kareDurumu);
              oturum.kareBildir(kareDurumu, bas);
              setCanliJeton(oturum.jetonSayisi());
              if (r.ok && data?.status === "success") {
                setResult(data);
                setSonKareZamani(Date.now());
              } else {
                setResult(null);
                setSonKareZamani(null);
              }
            } finally {
              clearTimeout(t);
            }
          }
        } catch (e) {
          if (!bitti && isLiveRef.current) setCanliDurum({ tur: "hata", metin: t("ai.canli.sonKareHata", { hata: aiHataMesaji(e) }) });
        } finally {
          liveLoadingRef.current = false;
        }
      }
      if (bitti) return;
      zamanlayici = setTimeout(tur, canliSonrakiBekleme(Date.now() - bas));
    };
    zamanlayici = setTimeout(tur, canliSonrakiBekleme(0));
    return () => {
      bitti = true;
      if (zamanlayici) clearTimeout(zamanlayici);
      try { liveAbortRef.current?.abort(); } catch { /* ignore */ }
      liveAbortRef.current = null;
    };
  }, [isLive, t]);

  // SG.G6: son analiz karesinin yaşı.
  useEffect(() => {
    if (!isLive) return;
    const t = setInterval(() => setSimdi(Date.now()), 500);
    return () => clearInterval(t);
  }, [isLive]);

  const toggleLive = async () => {
    if (!isLive) {
      if (!permission?.granted) {
        const res = await requestPermission();
        if (!res?.granted) { showToast(t("ai.organ.canliKameraIzni"), "error"); return; }
      }
    }
    const next = !isLive;
    setIsLive(next);
    // B1-organ-canli-kalinti: sıfırlama HER İKİ yönde de yapılır. Eskiden yalnız DURDURURKEN
    // (`!next`) temizleniyordu → galeri fotoğrafının analiz sonucu (result.image_base64 overlay'i,
    // "10 ORGAN" rozeti, organ listesi) canlı kadrajın ÜSTÜNDE kalıyordu; ilk canlı kare
    // (~3,5 sn) gelene dek kullanıcı eski fotoğrafın keypoint'lerini canlı kedi üzerinde görüyordu.
    if (imageUri && imageUri.startsWith('blob:')) { try { URL.revokeObjectURL(imageUri); } catch { /* ignore */ } }
    setImageUri(null); setImageBase64(null); setImageFile(null); setResult(null);
    setCanliDurum(null); setSonKareZamani(null);
  };

  const takePhoto = async () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file'; input.accept = 'image/*'; (input as any).capture = 'environment';
      input.onchange = (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0];
        if (file) { if (imageUri && imageUri.startsWith('blob:')) URL.revokeObjectURL(imageUri); setImageBase64(null); setResult(null); void webIcinKucult(file).then((k) => { setImageFile(k); setImageUri(URL.createObjectURL(k)); }); }
      };
      input.click();
    } else {
      const res = await ImagePicker.launchCameraAsync({ allowsEditing: false, quality: 0.8, base64: true });
      if (!res.canceled) { const shrunk = await shrinkForUpload(res.assets[0].uri); setImageUri(shrunk.uri); setImageBase64(shrunk.base64); setImageFile((res.assets[0] as any).file || null); setResult(null); }
    }
  };

  const pickImage = async () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file'; input.accept = 'image/*';
      input.onchange = (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0];
        if (file) { if (imageUri && imageUri.startsWith('blob:')) URL.revokeObjectURL(imageUri); setImageBase64(null); setResult(null); void webIcinKucult(file).then((k) => { setImageFile(k); setImageUri(URL.createObjectURL(k)); }); }
      };
      input.click();
    } else {
      const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, allowsEditing: false, quality: 0.8, base64: true });
      if (!res.canceled) { const shrunk = await shrinkForUpload(res.assets[0].uri); setImageUri(shrunk.uri); setImageBase64(shrunk.base64); setImageFile((res.assets[0] as any).file || null); setResult(null); }
    }
  };

  const analyze = async () => {
    const hasta = hastaAnligi(); // D2.E09 (Y87): kayıt analizin BAŞLADIĞI hastaya yazılır
    if (!imageUri) return;
    setLoading(true);
    try {
      const formData = new FormData();
      if (Platform.OS === 'web') {
        let blob: Blob | null = null;
        if (imageFile) blob = imageFile;
        else if (imageBase64) { const bstr = atob(imageBase64); let n = bstr.length; const u8 = new Uint8Array(n); while (n--) u8[n] = bstr.charCodeAt(n); blob = new Blob([u8], { type: 'image/jpeg' }); }
        else { const r = await fetch(imageUri); blob = await r.blob(); }
        if (!blob) throw new Error("Görüntü hazırlanamadı.");
        formData.append("file", blob, "cat.jpg");
      } else {
        if (imageBase64) formData.append("image_base64", imageBase64);
        else formData.append("file", { uri: imageUri, name: "cat.jpg", type: "image/jpeg" } as any);
      }
      const ctrl = new AbortController();
      const to = setTimeout(() => ctrl.abort(), AI_TIMEOUT_MS);
      const response = await fetch(serviceConfig.apiBaseUrl + "/ai/vision/cat_organ", { method: "POST", body: formData, headers: { Accept: "application/json", ...authHeaders() }, signal: ctrl.signal });
      clearTimeout(to);
      const data = await response.json();
      // B1: analiz sürerken "Canlı Kamera"ya geçildiyse statik sonuç canlı kadrajın üstüne düşmesin.
      if (isLiveRef.current) return;
      if (response.ok && data.status === "success") {
        setResult(data);
        logAiResult(hasta, "Kedi Organ", data.bulunamadi ? (data.bulunamadi === "kedi_bulunamadi" ? "Kedi bulunamadı" : "Organ çıkarılamadı") : `${data.n_organs} organ lokalize`, { moduleId: "cat_organ", inputType: "image", detail: data });
      } else {
        showToast(aiDetayCumlesi(data?.detail, t("ai.hata.analizSirasinda")), "error");
      }
    } catch (e) {
      showToast(aiHataMesaji(e), "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card style={styles.card}>
      <Text style={styles.title}>{t("ai.organ.baslik")}</Text>
      <Text style={styles.subtitle}>{t("ai.organ.aciklama")}</Text>

      {!imageUri && !isLive && (
        <View style={styles.photoGuide}>
          <Text style={styles.photoGuideTitle}>{t("ai.organ.nasil")}</Text>
          <Text style={styles.photoGuideItem}><Trans i18nKey="ai.organ.ipucuTekKare" components={{ kalin: <Text style={styles.photoGuideBold} /> }} /></Text>
          <Text style={styles.photoGuideItem}><Trans i18nKey="ai.organ.ipucuCanli" components={{ kalin: <Text style={styles.photoGuideBold} /> }} /></Text>
          <Text style={styles.photoGuideItem}>{t("ai.organ.ipucuTum")}</Text>
          <Text style={styles.photoGuideItem}>{t("ai.organ.ipucuAruco")}</Text>
        </View>
      )}

      {/* ⚠️ CANLI KAMERA ve SONUÇ GALERİSİ AYRI DALLAR (ADIM 4) — eski ternary
            `uri: result?.image_base64 ? 'data:…' : imageUri`
          sonuç gelince kullanıcının GİRDİSİNİ ekrandan siliyordu. Canlı daldaki
          `kameraKutusu(onizlemeW…)` oran kilidi DOKUNULMADAN kalır: kamera karesi ile üzerine
          bindirilen organ işaretlerinin hizası ona bağlı (tıbbi karar ekranı). */}
      {!isLive ? (
        <GorselSahne
          sayfalar={sahneSayfalari(result, imageUri)}
          tavanY={galeriH}
          sifirlaAnahtari={imageUri}
          testID="catorgan-sahne"
          bos={
            <View style={[styles.imagePreviewContainer, { height: sahneH }]}>
              <View style={styles.placeholderBox}><ImageIcon color={colors.textMuted} size={48} /><Text style={styles.placeholderText}>{t("ai.ortak.goruntuSecilmedi")}</Text></View>
            </View>
          }
        />
      ) : (
        <View
          style={[
            styles.imagePreviewContainer,
            onizlemeKutu
              ? { width: onizlemeKutu.width, height: onizlemeKutu.height, alignSelf: "center" }
              : { height: sahneH },
          ]}
          onLayout={(e) => {
            const w = Math.round(e.nativeEvent.layout.width);
            // Kutu kendi genişliğini de değiştirir → yalnız İLK ölçüm alınır (ölç-daralt döngüsü yok).
            setOnizlemeW((eski) => (eski > 0 ? eski : w));
          }}
        >
          <CanliKameraKutusu
            cameraRef={cameraRef}
            facing={facing}
            onFlip={() => setFacing((f) => (f === "back" ? "front" : "back"))}
            sonKareB64={result?.image_base64 || null}
            sonKareYasMs={sonKareZamani != null ? simdi - sonKareZamani : null}
            rozet={result ? t("ai.organ.rozet", { count: result.n_organs ?? 0 }) : t("ai.organ.rozetAraniyor")}
          />
        </View>
      )}

      {isLive && canliDurum ? <CanliDurumSatiri durum={canliDurum} jeton={canliJetonEtkin ? canliJeton : null} /> : null}
      {isLive && (
        <Text style={styles.liveHint}>{t("ai.organ.canliIpucu")}</Text>
      )}

      <View style={[styles.btnRow, isCompact && { flexDirection: "column" }]}>
        <View style={isCompact ? { width: "100%" } : { flex: 1 }}><Button label={t("ai.ortak.galeridenSec")} icon={<ImageIcon color={colors.white} size={16} />} onPress={pickImage} disabled={isLive} /></View>
        <View style={isCompact ? { width: "100%" } : { flex: 1 }}><Button label={t("ai.gorsel.fotografCek")} icon={<Camera color={colors.white} size={16} />} onPress={takePhoto} disabled={isLive} /></View>
        <View style={isCompact ? { width: "100%" } : { flex: 1 }}>
          <Button label={isLive ? t("ai.gorsel.canliyiDurdur") : t("ai.gorsel.canliKamera")} variant={isLive ? "danger" : "secondary"} icon={<Video color={isLive ? colors.white : colors.primary} size={16} />} onPress={toggleLive} />
        </View>
      </View>

      {!isLive && (
        <View style={styles.analyzeBtn}>
          <Button variant="primary" label={loading ? t("ai.ortak.analizEdiliyor") : t("ai.organ.analiziBaslat")} icon={loading ? <ActivityIndicator color={colors.white} /> : <Sparkles color={colors.white} size={16} />} disabled={!imageUri || loading} onPress={analyze} />
        </View>
      )}
      {longLoading && <Text style={styles.modelHint}>{t("ai.organ.modelHazirlaniyor")}</Text>}

      {result && (
        <View style={styles.resultBox}>
          {(result as any).mirror_warning ? (
            <Text style={styles.scUyari}>{t("ai.organ.ayna")}</Text>
          ) : null}
          {(result as any).anatomic_consistency && (result as any).anatomic_consistency.passed === false ? (
            <Text style={styles.scUyari}>{t("ai.organ.anatomik")}</Text>
          ) : null}
          {/* İNCELEME-2 i5-F-2 (D1.E08 · İG-5.27): kabin yapılandırması yüklenemediyse organ konumları KALİBRASYONSUZDUR —
              backend metni (tek kaynak `catorgan_predictor.KABIN_UYARISI`) operatöre GÖSTERİLİR (eskiden yalnız yanıtta). */}
          {(result as any).kabin_uyarisi ? (
            <Text style={styles.scUyari}>⚠ {(result as any).kabin_uyarisi}</Text>
          ) : null}
          {(() => {
            const organs = result.organs || [];
            if (organs.length === 0) {
              // SG.G5: backend "bulunamadı" BİLGİSİNİ nedeniyle söylüyorsa (kedi yok / organ çıkarılamadı) o metin gösterilir.
              return <ResultInterpretation tone="alert" emoji="🔍" title={result.bulunamadi === "kedi_bulunamadi" ? t("ai.organ.kediYok") : t("ai.organ.organYok")}
                text={result.bulunamadi_mesaji || t("ai.organ.bulunamadiMetin")} />;
            }
            const best = organs.reduce((a: AiOrgan, b: AiOrgan) => ((b.reliability || 0) > (a.reliability || 0) ? b : a), organs[0]);
            const bestPct = Math.round(Math.max(0, Math.min(1, best.reliability || 0)) * 100);
            const bestName = organAdi(best.name);
            const strong = bestPct >= 60;
            return <ResultInterpretation
              tone={strong ? "positive" : "info"} emoji="🐾"
              title={t("ai.organ.bulundu", { count: organs.length, bestName, bestPct })}
              text={strong
                ? t("ai.organ.guvenilir")
                : t("ai.organ.dusukGuven")}
              points={[t("ai.organ.nokta1"), t("ai.organ.nokta2")]} />;
          })()}
          {/* ⚠️ "PnP undefinedpx" (saha, 2026-09-11): alan koşulsuz basılıyordu ve GPU
              profilinde `pnp_residual_px` HİÇ gelmiyordu (`ai_service/app.py`de yoktu).
              Backend tarafı ADIM 2'de düzeltildi; burası İKİNCİ savunma: alan yoksa
              teknik satırda "—" çıkar. Bir sayı uydurmak (0px) daha kötü olurdu —
              operatör onu "mükemmel uyum" diye okur. */}
          <Text style={styles.ctSubLabel}>
            {t("ai.organ.teknik", { poz: result.pose_type ?? "?", pnp: typeof result.pnp_residual_px === "number" ? `${result.pnp_residual_px}px` : "—" })}
          </Text>
          <Text style={styles.ctSubLabel}>{t("ai.organ.organlar")}</Text>
          {(result.organs || []).map((o: AiOrgan, i: number) => {
            const c = o.coord_cabin_cm || o.coord_3d_cm || [0, 0, 0];
            const rel = Math.max(0, Math.min(1, o.reliability || 0));
            const pct = Math.round(rel * 100);
            return (
              <View key={i} style={{ marginTop: spacing.xs }}>
                <Text style={styles.resultText}>{organAdi(o.name)} <Text style={{ color: colors.textMuted, fontSize: typography.small }}>({(+c[0]).toFixed(1)}, {(+c[1]).toFixed(1)}, {(+c[2]).toFixed(1)}) cm</Text></Text>
                <View style={styles.soundBarRow}>
                  <View style={styles.soundBarTrack}>
                    <View style={[styles.soundBarFill, { width: (`${Math.max(2, pct)}%` as any), backgroundColor: relColor(rel) }]} />
                  </View>
                  <Text style={styles.soundBarPct}>{t("ai.ortak.yuzde", { deger: pct })}</Text>
                </View>
              </View>
            );
          })}
          <Text style={styles.ctHint}>{t("ai.organ.koordinatNotu")}</Text>
          <MedicalDisclaimer />
        </View>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  selectorHeading: { color: colors.text, fontSize: typography.subtitle, fontWeight: "800", marginTop: spacing.lg, marginBottom: spacing.md },
  aiWelcome: { backgroundColor: colors.primarySoft, borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.md, gap: 6, borderWidth: 1, borderColor: colors.primarySoft },
  aiWelcomeTitle: { color: colors.text, fontSize: typography.body, fontWeight: "800" },
  aiWelcomeText: { color: colors.textMuted, fontSize: typography.small, lineHeight: rf(18) },
  aiWelcomeNote: { color: colors.textMuted, fontSize: typography.small, lineHeight: rf(18), marginTop: 2 },
  aiWelcomeBold: { color: colors.text, fontWeight: "700" },
  moduleGrid: { gap: spacing.sm, marginBottom: spacing.lg },
  moduleCard: { width: "100%", flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, borderRadius: radius.lg, backgroundColor: colors.bgAlt, borderWidth: 1, borderColor: colors.border },
  moduleCardActive: { backgroundColor: colors.primarySoft, borderColor: colors.primary, borderBottomLeftRadius: 0, borderBottomRightRadius: 0 },
  gateBadge: { flexDirection: "row", alignItems: "center", gap: 4, paddingVertical: 3, paddingHorizontal: 8, borderRadius: 999, backgroundColor: "rgba(139,92,246,0.14)", borderWidth: 1, borderColor: "rgba(139,92,246,0.40)" },
  gateBadgeText: { color: colors.violet, fontWeight: "700", fontSize: 11 },
  rtTag: { paddingVertical: 3, paddingHorizontal: 8, borderRadius: 999, borderWidth: 1 },
  rtTagOn: { backgroundColor: "rgba(79,140,255,0.12)", borderColor: "rgba(79,140,255,0.40)" },
  rtTagOff: { backgroundColor: colors.bgAlt, borderColor: colors.border },
  rtTagOnText: { color: colors.primary, fontWeight: "700", fontSize: 11 },
  rtTagOffText: { color: colors.textMuted, fontWeight: "700", fontSize: 11 },
  moduleChevron: { color: colors.textMuted, fontSize: rf(12), marginLeft: spacing.xs },
  moduleChevronActive: { color: colors.primary },
  moduleBody: { marginTop: -1, marginBottom: spacing.xs, paddingHorizontal: 2 },
  moduleIconWrap: { width: touch.min, height: touch.min, borderRadius: radius.md, alignItems: "center", justifyContent: "center", backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border },
  moduleIconWrapActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  moduleLabel: { color: colors.text, fontSize: typography.body, fontWeight: "700" },
  moduleLabelActive: { color: colors.primary },
  moduleDesc: { color: colors.textMuted, fontSize: typography.small, marginTop: 2, lineHeight: rf(15) },
  // [S4 adım 3] Alt boşluk TEK yerde: AppShell içerik ScrollView'ı rs(160)+güvenli alan (mobil) /
  // rs(84) (masaüstü) veriyor. Ekranın kendi paddingBottom'ı bunun ÜSTÜNE binip sayfa sonunda
  // ~200 px ölü alan bırakıyordu.
  content: { paddingHorizontal: spacing.lg, width: "100%", maxWidth: layoutMax.aiHub, alignSelf: "center" },
  card: { gap: spacing.lg },
  cardHeader: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.sm },
  title: { color: colors.text, fontSize: typography.subtitle, fontWeight: "800" },
  subtitle: { color: colors.textMuted, fontSize: typography.body, marginBottom: spacing.sm },
  input: { backgroundColor: colors.bg, color: colors.text, padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  diseaseHint: { color: colors.textMuted, fontSize: typography.small, fontStyle: 'italic', lineHeight: rf(17), marginTop: 6, marginBottom: spacing.sm },
  diseaseDefaultsNote: { color: colors.textMuted, fontSize: typography.small, lineHeight: rf(17), marginTop: spacing.sm, backgroundColor: colors.bg, borderRadius: radius.sm, padding: spacing.sm },
  // Sunum-katmanı XAI satırı (2026-08-26): "kararı sürükleyenler" — sessiz, sonucun altında.
  xaiSatiri: { color: colors.textMuted, fontSize: typography.small, marginTop: spacing.sm },
  // Faz 2: opt-in ısı haritası anahtarı (Grad-CAM pahalı — otomatik değil).
  xaiToggle: { paddingVertical: spacing.xs, marginBottom: spacing.xs },
  xaiToggleText: { color: colors.textMuted, fontSize: typography.small },
  liveHint: { color: colors.textMuted, fontSize: typography.small, lineHeight: rf(17), marginTop: spacing.xs, backgroundColor: colors.primarySoft, borderRadius: radius.sm, padding: spacing.sm },
  symptomsGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  symptomBtn: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.sm, backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border },
  symptomBtnActive: { backgroundColor: colors.primarySoft, borderColor: colors.primary },
  symptomLabel: { color: colors.textMuted, fontSize: typography.small },
  symptomLabelActive: { color: colors.primary, fontWeight: "bold" },
  imagePreviewContainer: { width: "100%", height: rs(300), backgroundColor: colors.bg, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, overflow: "hidden", justifyContent: "center", alignItems: "center", position: "relative" },
  // "Kaldığın yerden" şeridi — dikkat çeksin ama analiz düğmesiyle YARIŞMASIN:
  // yumuşak zemin + ince kenar, birincil renkte BAŞLIK, gövde nötr.
  kaldiginYerden: { backgroundColor: colors.bgAlt, borderRadius: radius.md, padding: spacing.md,
                    borderWidth: 1, borderColor: colors.border, gap: 2 },
  kaldiginYerdenBaslik: { color: colors.primary, fontWeight: "800", fontSize: typography.small },
  kaldiginYerdenOzet: { color: colors.text, fontSize: typography.small },
  photoGuide: { backgroundColor: colors.primarySoft, borderRadius: radius.md, padding: spacing.md, gap: 3, borderWidth: 1, borderColor: colors.primarySoft },
  photoGuideTitle: { color: colors.text, fontSize: typography.small, fontWeight: "800", marginBottom: 2 },
  photoGuideItem: { color: colors.textMuted, fontSize: typography.small, lineHeight: rf(18) },
  photoGuideBold: { color: colors.text, fontWeight: "bold" },
  photoGuideWarn: { color: colors.warning, fontSize: typography.small, fontStyle: "italic", marginTop: spacing.xs },
  // ⚠️ imagePreview YALNIZ sabit-yükseklikli imagePreviewContainer İÇİNDE kullanılır (%100 yükseklik
  // ebeveyne bağlıdır). Serbest duran görsel (ısı haritası vb.) için xaiStage/scStage (AÇIK yükseklik).
  imagePreview: { width: "100%", height: "100%", resizeMode: "contain" },
  // Scratch girdi önizlemesi: formu ezmemesi için imagePreviewContainer'dan (300) daha kısa.
  scOnizlemeKutu: { width: "100%", height: rs(180), backgroundColor: colors.bg, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, overflow: "hidden", justifyContent: "center",
    alignItems: "center", marginTop: spacing.xs },
  // B2-isi-haritasi-ui: heatmap sahnesi — imagePreviewContainer ile BİREBİR aynı ölçü/çerçeve
  // (rs(300) + 1px kenarlık) → analiz görseliyle aynı boyut/hiza; yükseklik ebeveynden bağımsız.
  xaiStage: { width: "100%", height: rs(300), borderRadius: radius.md, backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border, marginTop: 4 },
  cameraContainer: { width: "100%", height: "100%", position: "relative" },
  cameraView: { flex: 1 },
  // SG.G6: canlı kipte son analiz karesi OPAK (yarı saydam bindirme YOK) + canlı önizleme köşede küçük pencere.
  canliSonKare: { position: "absolute", top: 0, left: 0, width: "100%", height: "100%", backgroundColor: "#000" },
  canliOnizlemeTam: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 },
  canliOnizlemeKose: {
    position: "absolute", top: 12, left: 12, width: "30%", aspectRatio: 4 / 3, borderRadius: radius.sm,
    overflow: "hidden", borderWidth: 2, borderColor: colors.white, backgroundColor: "#000",
  },
  canliYasEtiketi: { position: "absolute", bottom: 12, left: 12, backgroundColor: "rgba(0,0,0,0.6)", paddingHorizontal: 8, paddingVertical: 4, borderRadius: 12 },
  canliDurum: { color: colors.text, fontSize: typography.small, lineHeight: rf(17), marginTop: spacing.xs, backgroundColor: colors.primarySoft, borderRadius: radius.sm, padding: spacing.sm },
  canliDurumUyari: { color: colors.warning, backgroundColor: colors.warning + "22" },
  canliDurumBilgi: { color: colors.textMuted },
  liveIndicator: { position: "absolute", top: 12, right: 12, flexDirection: "row", alignItems: "center", backgroundColor: "rgba(0,0,0,0.6)", paddingHorizontal: 8, paddingVertical: 4, borderRadius: 12, gap: 6 },
  flipCameraBtn: { position: "absolute", bottom: 12, right: 12, width: touch.min, height: touch.min, borderRadius: 22, backgroundColor: "rgba(0,0,0,0.6)", alignItems: "center", justifyContent: "center" },
  liveDot: { width: rs(8), height: rs(8), borderRadius: 4, backgroundColor: colors.danger },
  // [S7 adım 10] 10 px rozet metni 320 px'te 8-9 px'e düşüyordu.
  liveText: { color: colors.white, fontSize: typography.small, fontWeight: "bold" },
  serverCamNote: { position: "absolute", bottom: 0, left: 0, right: 0, backgroundColor: "rgba(0,0,0,0.65)", color: colors.white, fontSize: typography.small, textAlign: "center", paddingVertical: 5, paddingHorizontal: 8 },
  placeholderBox: { alignItems: "center", gap: spacing.md },
  placeholderText: { color: colors.textMuted, fontSize: typography.body },
  btnRow: { flexDirection: "row", gap: spacing.md },
  analyzeBtn: { marginTop: spacing.sm },
  resultBox: { marginTop: spacing.md, padding: spacing.md, backgroundColor: colors.bgAlt, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.primarySoft },
  // AI Pro köprüsü — dokunma tabanı ölçekle küçülmez (dokunma-hedefi kapısı: touch.min).
  aiProKopru: {
    minHeight: touch.min, justifyContent: "center", alignItems: "center", marginTop: spacing.sm,
    borderRadius: radius.sm, borderWidth: 1, borderColor: colors.primary, backgroundColor: colors.primarySoft,
    paddingHorizontal: spacing.md,
  },
  aiProKopruMetin: { color: colors.white, fontWeight: "800", fontSize: typography.small },
  interpBox: { padding: spacing.md, borderRadius: radius.md, borderWidth: 1, marginBottom: spacing.md },
  interpTitle: { fontSize: typography.body, fontWeight: "800", marginBottom: 4 },
  interpText: { color: colors.text, fontSize: typography.small, lineHeight: rf(19) },
  interpPoint: { color: colors.textMuted, fontSize: typography.small, lineHeight: rf(18) },
  resultTitle: { color: colors.primary, fontSize: typography.body, fontWeight: "800", marginBottom: spacing.xs },
  resultText: { color: colors.text, fontSize: typography.body, marginTop: spacing.xs },
  fantomLenRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.sm },
  fantomLenLabel: { color: colors.textMuted, fontSize: typography.small },
  fantomLenInput: { flex: 1, backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, color: colors.text, fontSize: typography.body },
  petriHint: { color: colors.textMuted, fontSize: typography.small, fontStyle: "italic", marginTop: spacing.xs },
  // Petri gelişmiş (araştırma) ayarları. `touch.min` ZORUNLU: 320 px telefonda `rs()` ölçeği
  // 44 px erişilebilirlik tabanını 37 px'e düşürürdü (bkz. tests/test_dokunma_hedefi_kapisi.py).
  advBaslik: { minHeight: touch.min, justifyContent: "center", marginTop: spacing.sm },
  advBaslikMetin: { color: colors.primary, fontSize: typography.small, fontWeight: "600" },
  advGovde: { backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, padding: spacing.md, gap: spacing.sm },
  advNot: { color: colors.textMuted, fontSize: typography.small },
  advAlan: { gap: rs(2) },
  advSatir: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  advEtiket: { color: colors.text, fontSize: typography.small, flex: 1 },
  advGirdi: { width: rs(120), minHeight: touch.min, backgroundColor: colors.panel, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.sm, color: colors.text, fontSize: typography.small, textAlign: "center" },
  advIpucu: { color: colors.textMuted, fontSize: typography.small, fontStyle: "italic" },
  advAnahtar: { minHeight: touch.min, justifyContent: "center" },
  advAnahtarMetin: { color: colors.text, fontSize: typography.small },
  advUyari: { color: colors.warning, fontSize: typography.small },
  advSifirla: { minHeight: touch.min, justifyContent: "center", alignSelf: "flex-start" },
  advSifirlaMetin: { color: colors.primary, fontSize: typography.small, fontWeight: "600" },
  advEtkin: { color: colors.textMuted, fontSize: typography.small, marginTop: spacing.sm, fontStyle: "italic" },
  rnaFileName: { color: colors.text, fontSize: typography.small, marginTop: spacing.xs, fontWeight: "600" },
  ckdSection: { color: colors.primary, fontSize: typography.small, fontWeight: "800", marginTop: spacing.md, marginBottom: spacing.xs, textTransform: "uppercase" },
  ckdGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  ckdNumCell: { width: "47%", flexGrow: 1 },
  ckdNumLabel: { color: colors.textMuted, fontSize: typography.small, marginBottom: 2 },
  ckdNumInput: { backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, color: colors.text, fontSize: typography.body },
  ckdCatRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: spacing.sm },
  ckdCatLabel: { color: colors.text, fontSize: typography.body, flex: 1 },
  ckdCatBtns: { flexDirection: "row", gap: spacing.xs },
  ckdCatBtn: { paddingHorizontal: spacing.md, paddingVertical: spacing.xs, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg, minWidth: rs(56), alignItems: "center" },
  ckdCatBtnActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  ckdCatBtnText: { color: colors.text, fontSize: typography.small, fontWeight: "600" },
  soundStatusBox: { alignItems: "center", justifyContent: "center", paddingVertical: spacing.lg, backgroundColor: colors.bgAlt, borderRadius: radius.sm, marginTop: spacing.sm, minHeight: rs(96) },
  recDot: { width: rs(18), height: rs(18), borderRadius: 9, backgroundColor: colors.danger, marginBottom: spacing.xs },
  recText: { color: colors.danger, fontSize: typography.body, fontWeight: "700" },
  soundFileName: { color: colors.text, fontSize: typography.small, marginTop: spacing.xs, fontWeight: "600", maxWidth: rs(220) },
  soundBarRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.xs },
  // [S7 adım 9 / aihub-11] Dar ekranda etiket + çubuk + yüzde aynı satıra sığmıyor, çubuk
  // 30-40 px'e düşüp okunmaz oluyordu. Kompaktta etiket/yüzde üstte, çubuk tam genişlikte.
  soundBarRowCompact: { flexDirection: "column", alignItems: "stretch", gap: 2 },
  soundBarUst: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: spacing.xs },
  soundBarSatirIci: { flexShrink: 1 },
  soundBarLabel: { color: colors.text, fontSize: typography.small, width: rs(96) },
  soundBarTrack: { flex: 1, height: rs(12), backgroundColor: colors.primarySoft + "44", borderRadius: 6, overflow: "hidden" },
  soundBarFill: { height: "100%", backgroundColor: colors.primary, borderRadius: 6 },
  soundBarPct: { color: colors.textMuted, fontSize: typography.small, width: rs(40), textAlign: "right" },
  tumorRow: { marginTop: spacing.sm, paddingTop: spacing.sm, borderTopWidth: 1, borderTopColor: colors.primarySoft },
  tumorHeader: { color: colors.text, fontSize: typography.body, fontWeight: "700" },
  dBarRow: { flexDirection: "row", alignItems: "flex-end", gap: spacing.xs, marginTop: spacing.sm },
  dBarWrap: { flex: 1, alignItems: "center", justifyContent: "flex-end" },
  dBarTrack: { width: "100%", height: rs(26), justifyContent: "flex-end", backgroundColor: colors.primarySoft + "44", borderRadius: 2, overflow: "hidden" },
  dBarFill: { width: "100%", backgroundColor: colors.primary, borderRadius: 2 },
  dBarLabel: { color: colors.textMuted, fontSize: rf(9), marginTop: 2 },
  actions: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.lg },
  bigActionBtn: { flex: 1, backgroundColor: colors.primary, borderRadius: radius.md, alignItems: 'center', padding: spacing.xl, gap: spacing.sm },
  bigActionText: { color: '#fff', fontSize: typography.subtitle, fontWeight: '800' },
  secondaryActionBtn: { flex: 1, backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, alignItems: 'center', padding: spacing.xl, gap: spacing.sm },
  secondaryActionText: { color: colors.primary, fontSize: typography.subtitle, fontWeight: '700' },
  previewImage: { width: '100%', height: rs(300), borderRadius: radius.md, backgroundColor: colors.bg },
  petOwnerResult: { marginTop: spacing.lg, padding: spacing.md, backgroundColor: colors.bgAlt, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  petOwnerResultTitle: { fontSize: typography.subtitle, color: colors.text, fontWeight: '800', marginBottom: spacing.sm },
  // Düşük güven uyarısı: sonuç GÖSTERİLİR ama kesin bulgu gibi okunmasın diye üstünde durur.
  sesGuvenUyari: {
    backgroundColor: colors.warning + "22", borderColor: colors.warning, borderWidth: 1,
    borderRadius: 10, padding: spacing.sm, marginBottom: spacing.sm,
  },
  sesGuvenUyariText: { color: colors.warning, fontSize: typography.small, fontWeight: '700' },
  body: { color: colors.text, fontSize: typography.body, marginBottom: 4 },
  recommendationBox: { backgroundColor: colors.warning + "22", padding: spacing.md, borderRadius: radius.md, marginTop: spacing.md, borderWidth: 1, borderColor: colors.warning },
  recommendationText: { color: colors.text, fontSize: typography.small, marginBottom: spacing.md },
  startTherapyBtn: { backgroundColor: colors.success, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', padding: spacing.md, borderRadius: radius.md, gap: spacing.sm },
  startTherapyText: { color: '#fff', fontWeight: '800', fontSize: typography.body },
  statusText: { color: colors.primary, fontWeight: 'bold' },
  autoAdjustBtn: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs, borderWidth: 1, borderColor: colors.primary, paddingHorizontal: spacing.sm, paddingVertical: spacing.xs, borderRadius: radius.sm },
  autoAdjustActive: { backgroundColor: colors.primary },
  autoAdjustText: { color: colors.primary, fontSize: typography.small, fontWeight: 'bold' },
  disclaimer: { color: colors.textMuted, fontSize: typography.small, fontStyle: 'italic', marginTop: spacing.md, lineHeight: rf(16) },
  modelHint: { color: colors.warning, fontSize: typography.small, textAlign: 'center', marginTop: spacing.sm, fontStyle: 'italic' },
  ctFindingChip: { alignSelf: 'flex-start', paddingVertical: 4, paddingHorizontal: 10, borderRadius: radius.md, borderWidth: 1, marginBottom: spacing.sm },
  ctSubLabel: { color: colors.textMuted, fontSize: typography.small, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.5, marginTop: spacing.sm, marginBottom: 2 },
  ctHint: { color: colors.textMuted, fontSize: typography.small, fontStyle: 'italic', lineHeight: rf(17), marginTop: 6 },
  // ── Yara Kapanma (Scratch) — butonlu galeri + metrik kartları (plan §5) ──
  scFileBtn: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: colors.panel, borderWidth: 1, borderColor: colors.border, borderStyle: 'dashed', borderRadius: radius.md, paddingVertical: 10, paddingHorizontal: 12, marginTop: spacing.sm },
  scFileText: { color: colors.text, fontSize: typography.small, flex: 1 },
  scChipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 6 },
  scChip: { backgroundColor: colors.panel, borderWidth: 1, borderColor: colors.border, borderRadius: 999, paddingVertical: 6, paddingHorizontal: 14 },
  scChipOn: { backgroundColor: colors.primary + '22', borderColor: colors.primary },
  scChipText: { color: colors.textMuted, fontSize: typography.small, fontWeight: '600' },
  scChipTextOn: { color: colors.primary },
  // AÇIK yükseklik — styles.imagePreview'ın %100-yükseklik tuzağına KARŞI (plan v2)
  scStage: { width: '100%', height: rs(300), borderRadius: radius.md, backgroundColor: '#0C111C', marginTop: spacing.sm },
  scMetricRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  scMetricBox: { flexGrow: 1, minWidth: 110, backgroundColor: colors.panel, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingVertical: 8, paddingHorizontal: 12 },
  scMetricHero: { borderColor: colors.primary },
  scMetricVal: { color: colors.text, fontSize: rf(19), fontWeight: '800', fontVariant: ['tabular-nums'] },
  scMetricLbl: { color: colors.textMuted, fontSize: typography.small, textTransform: 'uppercase', letterSpacing: 0.5 },
  scUyari: { color: colors.warning, fontSize: typography.small, marginTop: spacing.sm, lineHeight: rf(17) },
  scDelta: { backgroundColor: colors.success + '18', borderWidth: 1, borderColor: colors.success, borderRadius: radius.md, padding: spacing.sm, marginTop: spacing.sm },
  scDeltaVal: { color: colors.success, fontSize: rf(18), fontWeight: '800', fontVariant: ['tabular-nums'] }
});
