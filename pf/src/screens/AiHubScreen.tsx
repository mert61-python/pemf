// Author: mertaygn, cglrgrkn
import { useState, useEffect, useRef, useCallback } from "react";
import { StyleSheet, Text, View, Image, ScrollView, ActivityIndicator, TouchableOpacity, TextInput, Platform, Linking } from "react-native";
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
import { colors, radius, spacing, typography, rf, rs } from "@/theme/tokens";
import { useToast } from "@/components/ui/ToastProvider";
import { apiPost, authHeaders, platformAlert, platformConfirm, AI_TIMEOUT_MS } from "@/services/apiClient";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { serviceConfig } from "@/services/config";
import { useUserMode, UserMode } from "@/context/UserModeContext";
import { cleanDetail, trValue } from "@/utils/aiDetail";
import { sesFormDataHazirla } from "@/utils/sesYukleme";
import { useLiveData } from "@/context/LiveDataContext";
import { useAppNav } from "@/context/AppNavContext";
import { useAuth } from "@/context/AuthContext";
import { useOperator } from "@/context/OperatorContext";
import { useEntitlement } from "@/context/EntitlementContext";
import { UpgradeModal, type UpgradeFeature } from "@/components/UpgradeModal";
import { useResponsive } from "@/hooks/useResponsive";
import { PatientGate } from "@/components/domain/PatientGate";

type AiModule = "disease" | "landmark" | "segmentation" | "thermal" | "reticulocytes" | "em_fantom" | "em_petri" | "kidney_rna" | "kidney_disease" | "cat_sound" | "kidney_ct" | "histopath" | "cat_organ" | "cell_scratch";

const SYMPTOMS = [
  "İştah Kaybı", "Kusma", "İshal", "Öksürük", "Solunum Güçlüğü",
  "Topallık", "Deri Lezyonları", "Burun Akıntısı", "Göz Akıntısı",
  "Halsizlik / Uyuşukluk", "Kilo Kaybı", "Hapşırma", "Dehidrasyon", "Ateş"
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

/** AI teşhis sonucunu kalıcı audit loguna gönderir (hasta + modül + özet). */
// AiHubScreen mount'ta set eder → logAiResult (modül-seviyesi, hook DEĞİL) aktif profili bilir.
let currentAiMode: UserMode = null;
// Aynı desen: giriş yapan hekim e-postası (klinik-içi "Benim/Tüm Klinik" AI-analiz filtresi).
let currentOperatorEmail: string = "";

// Tüm AI modelleri sonuçlarını buradan ŞİFRELİ ai_analyses geçmişine yazar (profesyonel + detaylı).
// result_detail utils/aiDetail.cleanDetail ile temizlenir (görsel/binary/devasa alanlar atılır).
// extra: modül-id + girdi-tipi + sonuç detayı (cleanDetail ile temizlenir) + opsiyonel güven. mode oto.
async function logAiResult(
  patientName: string,
  module: string,
  summary: string,
  extra?: { moduleId?: string; inputType?: string; detail?: unknown; confidence?: number }
) {
  try {
    await apiPost("/ai/log", {
      patient_name: patientName || "",
      module,
      summary,
      mode: currentAiMode || "",
      module_id: extra?.moduleId || "",
      input_type: extra?.inputType || "",
      result_detail: cleanDetail(extra?.detail),
      confidence: extra?.confidence ?? null,
      operator_email: currentOperatorEmail || "",
    }, null);
  } catch {
    /* audit başarısız — kullanıcı akışını bozma */
  }
}

/** Yakalanan hatadan (unknown) güvenli mesaj çıkarır — `catch (e: any)` yerine (audit B-2.4). */
function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

/** SAHA HATASI 2026-08-12 — "signal is aborted" kullanıcıya GÖSTERİLİYORDU.
 *
 * Ev kullanıcısı fps + hastalık + ses analizlerini PEŞ PEŞE başlattı; ilk ikisi döndü, ses
 * `AbortError: signal is aborted without reason` verdi. Hemen ardından tek başına denediğinde
 * ANINDA sonuçlandı. Sebep: `cat_sound` ilk çağrıda numba/librosa JIT derler (ölçüm: tek
 * başına 28 sn) ve üç analizin CPU çekişmesinde o elle yazılmış 60 sn'lik sınırı aşıyordu.
 *
 * İki ayrı kusur vardı ve ikisi de burada kapanıyor:
 *   • Sınır tek kaynaktan gelmiyordu → 10 çağrı `AI_TIMEOUT_MS`e bağlandı. (Aynı arıza
 *     2026-08-06'da `/ai/disease` için düzeltilmişti ama YALNIZ `apiPost` yolunda; ham
 *     `fetch` kullanan modüller atlanmıştı — bu yüzden aynı hata ses modülünde tekrarladı.)
 *   • İptal mesajı ham DOM metniydi. Zaman aşımı ile ağ hatası AYRI şeylerdir: ilkinde
 *     tekrar denemek İŞE YARAR (model artık bellekte), ikincisinde yaramaz. Kullanıcı bunu
 *     ayırt edebilmeli, yoksa "bozuk" sanıp vazgeçer.
 */
const AI_ZAMAN_ASIMI_MESAJI =
  "Analiz zaman aşımına uğradı. Bir modelin İLK çalıştırılması ~30 saniye sürebilir; " +
  "aynı anda başka analizler çalışıyorsa daha da uzar. Tekrar deneyin — model artık " +
  "hazır olduğu için bu kez hızlı sonuçlanır.";

function aiHataMesaji(e: unknown, varsayilan = "Ağ veya sunucu hatası."): string {
  // `AbortController.abort()` → DOMException(name: "AbortError"). `instanceof DOMException`
  // React Native'de güvenilir DEĞİL (DOM yok) → ada bakılır; tarayıcı ve RN'de de aynı.
  const ad = (e as { name?: string } | null)?.name;
  if (ad === "AbortError" || ad === "TimeoutError") return AI_ZAMAN_ASIMI_MESAJI;
  return varsayilan;
}

// audit B-2.4: AI-sonuç eleman şekilleri — .map/.filter/.reduce callback'lerini tiplemek için
// (display render; tsc-doğrulanabilir). Sonuç CONTAINER state'i (useState) heterojen per-model
// backend yanıtı olduğundan permissive bırakıldı (tam tipleme backend response-sözleşmesi ister).
interface AiTumorRegion { area_mm2?: number; centroid_cabin_mm?: number[]; D?: number[]; E_cancer?: number; E_healthy?: number; }
interface AiWell { area_mm2?: number; centroid_cabin_mm?: number[]; D?: number[]; label?: string; organ_id?: number; well_id?: number; E_cancer?: number; E_healthy?: number; }
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
interface AiResult {
  status?: string; success?: boolean; method?: string; image_base64?: string;
  // disease vision (FGS / termal / segmentasyon / retikülosit / AI-Pro donanım)
  fgs_total?: number | null; detected?: boolean; raw_fgs?: FgsRaw;
  prediction?: ThermalPrediction; cat_count?: number; counts?: Record<string, number>;
  hw_status?: string; hw_params?: { freq?: number; duty?: number };
  // em_fantom (tümör) / em_petri (kuyucuk)
  n_tumor?: number; mm_per_px?: number; tumor_regions?: AiTumorRegion[];
  n_cancer?: number; n_wells?: number; n_healthy?: number; wells?: AiWell[];
  // kidney_rna / kidney_disease (CKD)
  predictions?: AiPrediction[]; n_patients?: number;
  label?: string; prob_pct?: number; model?: string;
  // Sunum-katmanı XAI (2026-08-26): SHAP top-özellikler (alan yoksa satır gizli)
  xai?: { disease?: string; prob_ckd?: number; top_features?: { feature: string; attribution: number }[] } | null;
  // Faz 2: gradient ısı haritası (termal/ses; explain=true istenirse)
  xai_image_base64?: string; xai_method?: string; xai_error?: string;
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
}

function summarizeVision(d: any): string {
  if (d?.fgs_total !== undefined) return `FGS ${d.fgs_total}/10${d?.pain_level ? ` (${trValue(d.pain_level)})` : ""}`;
  if (d?.cat_count !== undefined) return `${d.cat_count} kedi tespit edildi`;
  if (d?.prediction?.label) return `Termal: ${trValue(d.prediction.label)}`;
  if (d?.counts) return `Eritrosit ${d.counts["erythrocyte"] ?? "?"} / Retikülosit ${(d.counts["punctate reticulocyte"] ?? 0) + (d.counts["aggregate reticulocyte"] ?? 0)}`;
  return "Analiz tamamlandı";
}

export function AiHubScreen() {
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
  // Aynı desen: giriş yapan hekim e-postasını modül-değişkenine yaz (AI analiz sahipliği).
  const { operatorEmail } = useOperator();
  useEffect(() => { currentOperatorEmail = operatorEmail; }, [operatorEmail]);

  // KRİTİK fix (bkz. resetAiCachesForOwner): profil/hasta değişince AI cache'lerini TEMİZLE + açık modülü
  // kapat → önceki hastanın görüntüsü/sonucu yeni hastada görünmesin ve yanlış hastaya analiz yazılmasın.
  const aiCacheOwnerKey = `${userMode ?? ""}:${selectedPatient?.id ?? selectedPatient?.name ?? ""}`;
  useEffect(() => {
    if (resetAiCachesForOwner(aiCacheOwnerKey)) setAcikModuller(new Set());
  }, [aiCacheOwnerKey]);

  // pet_owner → basit ekran; veterinarian/researcher → modüler AI Hub (modüller profile göre filtreli).
  // HASTA KAPISI (2026-08-07): analiz sonucu `ai_analyses`'e hasta adıyla yazılır → hasta
  // seçilmeden analiz, geçmişte SAHİPSİZ kayıt üretir. Üç profilde de kapı var; ev sahibi
  // profilinde "Hastalar" ekranı olmadığı için hasta ekleme de bu kapının içinde yapılır.
  if (!hasAiHub) {
    return (
      <PatientGate>
        <PetOwnerAiScreen />
      </PatientGate>
    );
  }

  const patientName = selectedPatient?.name || "";

  // Modüller profile göre filtrelenir: veterinarian → 7 kedi modeli; researcher → 7 araştırma modeli
  // (fantom/petri/böbrek). Yeni model eklenince yalnız modes'unu ayarla. (pet_owner yukarıda ayrılır.)
  // 2026-08-06 sahip kararı araştırma profiline CİHAZ ROTALARINI açtı (config/access.ts); AI Hub'ın
  // bu bölüşümü BİLİNÇLİ olarak DEĞİŞMEDİ — kedi modelleri klinik, araştırma modelleri laboratuvar işi.
  const ALL_MODULES: { id: AiModule; label: string; desc: string; icon: any; modes: UserMode[] }[] = [
    { id: "landmark", label: "Yüz Ağrısı (FGS)", desc: "YOLO-pose ile yüz ağrı skoru", icon: Scan, modes: ["veterinarian"] },
    { id: "disease", label: "Hastalık", desc: "XGBoost ile hastalık tahmini", icon: Stethoscope, modes: ["veterinarian"] },
    { id: "segmentation", label: "Segmentasyon", desc: "Vücut sınırı tespiti", icon: Scan, modes: ["veterinarian"] },
    { id: "thermal", label: "Termal", desc: "Termal anormallik analizi", icon: Activity, modes: ["veterinarian"] },
    { id: "reticulocytes", label: "Retikülosit", desc: "Mikroskobik hücre sayımı", icon: Microscope, modes: ["veterinarian"] },
    { id: "em_fantom", label: "Fantom Tümör", desc: "Fantomda tümör + EM alan tahmini", icon: Crosshair, modes: ["researcher"] },
    { id: "em_petri", label: "Petri Kuyu", desc: "Kuyularda kanser + EM alan tahmini", icon: FlaskConical, modes: ["researcher"] },
    { id: "kidney_rna", label: "Böbrek RNA", desc: "RNA-seq → KIRC sınıflandırma", icon: Dna, modes: ["researcher"] },
    { id: "kidney_disease", label: "Böbrek Hastalığı", desc: "Klinik değerlerden CKD tahmini", icon: HeartPulse, modes: ["researcher"] },
    { id: "cat_sound", label: "Kedi Sesi", desc: "Miyavdan duygu/durum sınıflandırma", icon: AudioLines, modes: ["veterinarian"] },
    { id: "kidney_ct", label: "Böbrek CT", desc: "CT'de taş / kist tespiti", icon: ScanLine, modes: ["researcher"] },
    { id: "histopath", label: "Böbrek Patoloji", desc: "Histopatoloji derece (grade 0–4)", icon: Microscope, modes: ["researcher"] },
    { id: "cell_scratch", label: "Yara Kapanma (Scratch)", desc: "Hücre segmentasyonu + kapanma metrikleri", icon: FlaskConical, modes: ["researcher"] },
    { id: "cat_organ", label: "Kedi Organ", desc: "Organ 3B lokalizasyon (10 organ)", icon: PawPrint, modes: ["veterinarian"] },
  ];
  const MODULES = ALL_MODULES.filter((m) => userMode != null && m.modes.includes(userMode));

  // Aktif modülün içeriğini döndür (akordeon gövdesi). key= sabit → cache ile sonuç korunur.
  const renderModuleBody = (id: AiModule) => {
    switch (id) {
      case "disease": return <DiseaseModule patientName={patientName} />;
      case "landmark": return <VisionModule key="landmark" endpoint="/vision/landmark" title="Yüz Ağrısı Skoru (FGS)" subtitle="YOLO-pose modeli ile yüzdeki kilit noktaları analiz eder." patientName={patientName} />;
      case "segmentation": return <VisionModule key="segmentation" endpoint="/vision/segmentation" title="Kedi Segmentasyonu" subtitle="YOLOv8-seg modeli ile kedinin vücut sınırlarını tespit eder." patientName={patientName} />;
      case "thermal": return <VisionModule key="thermal" endpoint="/vision/thermal" title="Termal Görüntü Analizi" subtitle="GhostNetV2 ile termal anormallikleri tespit eder." patientName={patientName} explainDestegi />;
      case "reticulocytes": return <VisionModule key="reticulocytes" endpoint="/vision/reticulocytes" title="Retikülosit Sayımı" subtitle="Mikroskop görüntüsünden hücreleri otomatik sayar." patientName={patientName} galleryOnly explainDestegi />;
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
      <ScrollView contentContainerStyle={styles.content}>
        {/* HASTA KAPISI (2026-08-07): hasta seçilmeden modüller GÖSTERİLMEZ. AI Hub'da
            güvenlik-kritik bir kontrol (ACİL DURDUR vb.) yok → sert kapı güvenli.
            Kontrol ekranında ise `soft` kip kullanılır, bkz. PatientGate prop açıklaması. */}
        <PatientGate>
        <Text style={styles.selectorHeading}>Tanı Modülleri</Text>
        <View style={styles.aiWelcome}>
          <Text style={styles.aiWelcomeTitle}>👋 Nasıl çalışır?</Text>
          <Text style={styles.aiWelcomeText}>
            Bir modüle <Text style={styles.aiWelcomeBold}>dokunun</Text> → hemen altında açılır; <Text style={styles.aiWelcomeBold}>birden fazlasını aynı anda açık tutabilirsiniz</Text>. İhtiyaca göre
            <Text style={styles.aiWelcomeBold}> fotoğraf/canlı kamera</Text>, <Text style={styles.aiWelcomeBold}>ses</Text> ya da
            <Text style={styles.aiWelcomeBold}> klinik değer</Text> girip analizi başlatın. Her modülün başında kısa bir kullanım ipucu var.
          </Text>
          <Text style={styles.aiWelcomeNote}>
            ℹ️ İlk analiz model hazırlığından dolayı biraz uzun sürebilir. Sonuçlar bir <Text style={styles.aiWelcomeBold}>ön-değerlendirmedir</Text>, kesin tanı değildir.
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
                  accessibilityLabel={`${m.label}${gated ? " — araştırma eklentisi gerekli" : ""}`}
                  accessibilityHint={active ? "Kapatmak için dokunun" : "Açmak için dokunun"}
                >
                  <View style={[styles.moduleIconWrap, active && styles.moduleIconWrapActive]}>
                    <Icon size={22} color={active ? colors.white : colors.primary} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={[styles.moduleLabel, active && styles.moduleLabelActive]} numberOfLines={1}>{m.label}</Text>
                    <Text style={styles.moduleDesc} numberOfLines={2}>{m.desc}</Text>
                  </View>
                  {gated && (
                    <TouchableOpacity
                      onPress={() => setUpgradeFor("research")}
                      style={styles.gateBadge}
                      accessibilityRole="button"
                      accessibilityLabel="Araştırma eklentisi gerekli"
                    >
                      <Lock size={11} color={colors.violet} />
                      <Text style={styles.gateBadgeText}>Eklenti</Text>
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
      </ScrollView>
      <UpgradeModal visible={!!upgradeFor} onClose={() => setUpgradeFor(null)} feature={upgradeFor ?? "tier"} />
    </View>
  );
}

function PetOwnerAiScreen() {
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
          setImageFile(file);
          setImageUri(URL.createObjectURL(file));
          setResult(null); setTreatmentStatus("");
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
          setImageFile(file);
          setImageUri(URL.createObjectURL(file));
          setResult(null); setTreatmentStatus("");
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
        logAiResult("", "Ağrı Analizi (FGS)", summarizeVision(data), { moduleId: "landmark", inputType: "image", detail: data });
      } else {
        showToast(data?.detail || "Teşhis sırasında hata oluştu.", "error");
      }
    } catch (error) {
      // Satır-içi AbortError ayrımı `aiHataMesaji`ye devredildi (2026-08-12): mesaj tek
      // kaynaktan gelsin. Eski metin "bağlantıyı kontrol edin" diyordu — zaman aşımında
      // bağlantı SAĞLAMDIR, yanıltıcıydı.
      showToast(aiHataMesaji(error, "Bağlantı hatası."), "error");
    } finally {
      setLoading(false);
    }
  };

  // NOT: Evcil Hayvan Sahibi profili YALNIZ ANALİZ yapar — otonom rahatlama terapisi (auto_preset)
  // buradan KALDIRILDI. Ev kullanıcısı cihaz sürmez; ağrı bulgusunda veteriner hekime yönlendirilir.

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Card style={styles.card}>
        <View style={styles.cardHeader}>
          <Sparkles color={colors.primary} size={28} />
          <Text style={[styles.title, { fontSize: rf(24) }]}>Akıllı Teşhis Asistanı</Text>
        </View>
        <Text style={styles.subtitle}>Dostunuzun fotoğrafını çekin, yapay zeka anında ağrı ve stres durumunu analiz etsin. Gerekirse veteriner hekiminize danışın.</Text>

        {!imageUri ? (
          <>
            <View style={styles.photoGuide}>
              <Text style={styles.photoGuideTitle}>📸 Net sonuç için</Text>
              <Text style={styles.photoGuideItem}>• Dostunuzun yüzünü <Text style={styles.photoGuideBold}>tam karşıdan</Text>, yakın ve net çekin</Text>
              <Text style={styles.photoGuideItem}>• İyi ışık olsun; gözler, kulaklar ve bıyıklar görünsün</Text>
              <Text style={styles.photoGuideItem}>• Tek kedi kadraja girsin, bulanık olmasın</Text>
            </View>
            <View style={styles.actions}>
              <TouchableOpacity style={styles.bigActionBtn} onPress={takePhoto}>
                <Camera color="#fff" size={32} />
                <Text style={styles.bigActionText}>Kamerayı Aç</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.secondaryActionBtn} onPress={pickImage}>
                <ImageIcon color={colors.primary} size={24} />
                <Text style={styles.secondaryActionText}>Galeriden Seç</Text>
              </TouchableOpacity>
            </View>
          </>
        ) : (
          <View style={{ gap: spacing.lg, marginTop: spacing.md }}>
            <Image source={{ uri: imageUri }} style={styles.previewImage} resizeMode="contain" />
            <View style={{ flexDirection: 'row', gap: spacing.md }}>
              <View style={{ flex: 1 }}>
                <Button variant="secondary" label="Yeni Fotoğraf" onPress={() => { setImageUri(null); setImageBase64(null); setImageFile(null); }} />
              </View>
              <View style={{ flex: 1 }}>
                <Button variant="primary" label={loading ? "Analiz Ediliyor..." : "Teşhis Et"} onPress={() => analyzeImage()} disabled={loading} icon={loading ? <ActivityIndicator color="#fff" /> : <Sparkles color="#fff" size={16} />} />
              </View>
            </View>
          </View>
        )}

        {longLoading && <Text style={styles.modelHint}>Model hazırlanıyor, analiz sürüyor…</Text>}

        {result && (() => {
          let recommendation = "";
          let requiresVet = false;
          const score = result.fgs_total;
          // GÜVENLİK: tespit yoksa (detected=false / score yok / <0) "ağrı yok" YANLIŞ güvencesi VERME.
          const notDetected = result.detected === false || score == null || score < 0;

          if (notDetected) {
            recommendation = "Kedinin yüzü net tespit edilemedi. Lütfen yüzü net, iyi aydınlatılmış ve tam karşıdan çekilmiş bir fotoğrafla tekrar deneyin.";
          } else if (score === 0) {
            recommendation = "Dostunuzun yüz hatlarında herhangi bir ağrı veya stres belirtisi görülmüyor. Oldukça rahat görünüyor!";
          } else if (score > 0 && score <= 3) {
            recommendation = "Dostunuzda hafif bir rahatsızlık veya yorgunluk belirtisi olabilir. Bu durum geçici olabilir ancak gözlemlemeye devam edin. Belirtiler sürerse veteriner hekiminize danışın.";
          } else if (score > 3 && score <= 5) {
            recommendation = "Orta derecede ağrı veya stres belirtileri tespit edildi! Yüz hatlarında belirgin bir gerginlik var. Belirtiler 1-2 günden uzun sürerse veteriner hekiminize danışın.";
          } else {
            recommendation = "ŞİDDETLİ AĞRI BELİRTİSİ! Dostumuz ciddi bir rahatsızlık yaşıyor olabilir. Lütfen vakit kaybetmeden VETERİNER HEKİMİNİZE BAŞVURUN.";
            requiresVet = true;
          }

          return (
            <View style={styles.petOwnerResult}>
              <Text style={styles.petOwnerResultTitle}>Yapay Zeka Analiz Sonucu</Text>

              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.sm }}>
                <Text style={styles.body}>Ağrı Skoru (FGS):</Text>
                <Text style={[styles.title, { color: notDetected ? colors.textMuted : score > 3 ? colors.danger : colors.success }]}>{notDetected ? "—" : `${score} / 10`}</Text>
              </View>

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
                      else platformAlert("Klinik telefonu ayarlı değil", "Kayıt (hesap) bilgilerinde klinik acil telefonu girilmemiş.");
                    }}
                  >
                    <Stethoscope color="#fff" size={20} />
                    <Text style={styles.startTherapyText}>Veteriner Kliniğini Ara</Text>
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
        <DiseaseModule patientName="" />
      </View>
    </ScrollView>
  );
}

/** Kedi sesi tek sınıf → evcil hayvan sahibi için dostça yorum + ton (renk/aksiyon). */
const CAT_SOUND_ADVICE: Record<string, { emoji: string; title: string; text: string; tone: "positive" | "info" | "alert" | "pain" }> = {
  Happy: { emoji: "😊", title: "Mutlu ve Keyifli", text: "Dostunuz kendini iyi ve mutlu hissediyor. Her şey yolunda görünüyor!", tone: "positive" },
  Resting: { emoji: "😌", title: "Sakin ve Dinlenmede", text: "Rahat ve huzurlu bir durumda, keyfini çıkarıyor.", tone: "positive" },
  MotherCall: { emoji: "🐱", title: "Anne Çağrısı", text: "Yavrusunu arıyor ya da anne içgüdüsüyle sesleniyor — doğal bir davranış.", tone: "info" },
  Mating: { emoji: "💕", title: "Çiftleşme Dönemi", text: "Çiftleşme dönemine ait bir ses. Doğaldır; huzursuzsa sakin bir ortam sağlayın.", tone: "info" },
  HuntingMind: { emoji: "🐾", title: "Av / Oyun Modunda", text: "Meraklı ve hareketli, avlanma içgüdüsü aktif. Oyunla enerjisini atmasına yardımcı olun.", tone: "info" },
  Warning: { emoji: "⚠️", title: "Tedirgin / Uyarıyor", text: "Bir şeyden rahatsız ya da tedirgin olabilir. Ortamı kontrol edip onu sakinleştirin.", tone: "alert" },
  Defence: { emoji: "🛡️", title: "Savunmada", text: "Kendini tehdit altında hissediyor olabilir. Zorlamadan ona güvenli bir alan tanıyın.", tone: "alert" },
  Angry: { emoji: "😾", title: "Kızgın / Gergin", text: "Şu an gergin. Ona alan tanıyın, zorlamayın; kısa sürede sakinleşebilir.", tone: "alert" },
  Fighting: { emoji: "🙀", title: "Kavga / Çatışma", text: "Bir çatışma sesi. Diğer hayvanlardan uzaklaştırıp güvenli bir yere alın.", tone: "alert" },
  Paining: { emoji: "😿", title: "Ağrı Belirtisi Olabilir", text: "Bu ses bir ağrı ya da rahatsızlık işareti olabilir. Dostunuzu yakından gözlemleyin; belirti sürerse veteriner hekiminize danışın.", tone: "pain" },
};

/**
 * PetOwnerSoundCard — evcil hayvan sahibi profili için "Sesini Dinleyelim" kartı.
 * Miyavı kaydet/yükle → POST /ai/sound/cat → tek sınıf → dostça ruh-hali yorumu (teknik bar YOK).
 * Ağrı (Paining) durumunda otonom rahatlama terapisi önerilir (foto/FGS akışıyla tutarlı).
 */
function PetOwnerSoundCard() {
  const { showToast } = useToast();
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
      if (!perm.granted) { showToast("Mikrofon izni gerekli.", "error"); return; }
      await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
      setIsRecording(true); setResult(null); setAudioUri(null); setWebFile(null); setTreatmentStatus("");
    } catch (e) {
      showToast("Kayıt başlatılamadı (mikrofon?).", "error");
    }
  };

  const stopRecording = async () => {
    setIsRecording(false);
    try {
      await recorder.stop();
      setAudioUri(recorder.uri || null); setFileName("kayıt.m4a");
    } catch (e) {
      showToast("Kayıt durdurulamadı.", "error");
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
        logAiResult("", "Kedi Sesi", `${trValue(data.top_1_class)} %${Math.round((data.top_1_prob || 0) * 100)}`, { moduleId: "cat_sound", inputType: "audio", detail: data, confidence: data.top_1_prob });
      } else {
        showToast(data?.detail || "Analiz sırasında hata oluştu.", "error");
      }
    } catch (e) {
      showToast(aiHataMesaji(e, "Hata: " + errorMessage(e).slice(0, 120)), "error");
    } finally {
      setLoading(false);
    }
  };

  // Evcil Hayvan Sahibi = YALNIZ ANALİZ: ses ağrı bulgusunda otonom terapi (auto_preset) KALDIRILDI;
  // ev kullanıcısı cihaz sürmez, veteriner hekime yönlendirilir.

  const advice = result ? (CAT_SOUND_ADVICE[result.top_1_class ?? ""] || { emoji: "🐈", title: result.top_1_class ?? "", text: "Ses analiz edildi.", tone: "info" as const }) : null;
  const toneColor = advice ? (advice.tone === "positive" ? colors.success : advice.tone === "pain" ? colors.danger : advice.tone === "alert" ? colors.warning : colors.primary) : colors.primary;

  return (
    <Card style={styles.card}>
      <View style={styles.cardHeader}>
        <AudioLines color={colors.primary} size={28} />
        <Text style={[styles.title, { fontSize: rf(24) }]}>Sesini Dinleyelim</Text>
      </View>
      <Text style={styles.subtitle}>Dostunuzun miyavını kaydedin, yapay zeka ruh halini yorumlasın. Sessiz bir ortamda ~5 saniye kaydetmeniz yeterli.</Text>

      <View style={styles.soundStatusBox}>
        {isRecording ? (
          <View style={{ alignItems: "center" }}><View style={styles.recDot} /><Text style={styles.recText}>Kaydediliyor…</Text></View>
        ) : audioUri ? (
          <View style={{ alignItems: "center" }}><AudioLines color={colors.primary} size={40} /><Text style={styles.soundFileName} numberOfLines={1}>🎵 {fileName}</Text></View>
        ) : (
          <View style={{ alignItems: "center" }}><Mic color={colors.textMuted} size={40} /><Text style={styles.placeholderText}>Ses kaydedilmedi</Text></View>
        )}
      </View>

      <View style={styles.btnRow}>
        <View style={{ flex: 1 }}>
          <Button label={isRecording ? "Durdur" : "Kaydet"} variant={isRecording ? "danger" : "primary"} icon={isRecording ? <Square color={colors.white} size={16} /> : <Mic color={colors.white} size={16} />} onPress={isRecording ? stopRecording : startRecording} />
        </View>
        <View style={{ flex: 1 }}>
          <Button label="Ses Yükle" variant="secondary" icon={<FileText color={colors.primary} size={16} />} onPress={pickAudio} disabled={isRecording} />
        </View>
      </View>

      <View style={{ marginTop: spacing.md }}>
        <Button variant="primary" label={loading ? "Analiz Ediliyor..." : "Sesi Analiz Et"} icon={loading ? <ActivityIndicator color={colors.white} /> : <Sparkles color={colors.white} size={16} />} disabled={!audioUri || loading || isRecording} onPress={analyze} />
      </View>

      {advice && (
        <View style={styles.petOwnerResult}>
          <Text style={styles.petOwnerResultTitle}>Yapay Zeka Yorumu</Text>
          {/* ⚠️ Model "kedi sesi yok" DİYEMEZ: 10 sınıfın hepsi kedi duygusu, softmax her
              girdiye mutlaka bir duygu atar. Sunucu belirsizliği ölçüp `guvenilir` alanıyla
              gönderiyor; emin olmadığında sonucu kesin bir bulgu gibi göstermiyoruz.
              (Reddetmiyoruz: ölçümde gerçek bir AĞRI kaydı da düşük güvendeydi — reddetmek
              ev sahibinin gerçek ağrıyı kaçırmasına yol açardı.) */}
          {result?.guvenilir === false && (
            <View style={styles.sesGuvenUyari}>
              <Text style={styles.sesGuvenUyariText}>
                ⚠️ Bu sonuç güvenilir değil — kayıtta net bir kedi sesi ayırt edilemedi.
                Sessiz bir ortamda, mikrofonu yaklaştırıp tekrar kaydedin.
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
  return (
    <Text style={styles.disclaimer}>
      ⚠️ Bu yapay zeka sonucu yalnızca karar-destek amaçlıdır; veteriner hekim muayenesi ve
      teşhisinin yerine geçmez. Nihai karar hekime aittir.
    </Text>
  );
}

type InterpTone = "positive" | "info" | "alert" | "critical";
const TONE_COLOR: Record<InterpTone, string> = {
  positive: colors.success, info: colors.primary, alert: colors.warning, critical: colors.danger,
};

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
const DISEASE_FEATURE_TR: Record<string, string> = {
  Age: "Yaş", Weight: "Kilo", Heart_Rate: "Nabız", Body_Temperature: "Ateş",
  Duration_days: "Şikâyet süresi", Appetite_Loss_bin: "İştah kaybı", Vomiting_bin: "Kusma",
  Diarrhea_bin: "İshal", Coughing_bin: "Öksürük", Labored_Breathing_bin: "Zor solunum",
  Lameness_bin: "Topallama", Skin_Lesions_bin: "Deri lezyonu", Nasal_Discharge_bin: "Burun akıntısı",
  Eye_Discharge_bin: "Göz akıntısı", has_Lethargy: "Halsizlik", has_Weight_Loss: "Kilo kaybı",
  has_Sneezing: "Hapşırık", has_Dehydration: "Dehidrasyon", has_Fever: "Ateş (semptom)",
};

type DiseaseXai = { disease?: string; top_features?: { feature: string; attribution: number }[] } | null;

/** Ortak XAI satırı: "🔍 Kararı sürükleyenler: Öksürük ↑ · Süre ↑ · Nabız ↓" (↑ tahmin lehine). */
function XaiSatiri({ xai, etiketle }: { xai: DiseaseXai; etiketle: (f: string) => string }) {
  if (!xai?.top_features?.length) return null;
  const metin = xai.top_features
    .slice(0, 5)
    .map((t) => `${etiketle(t.feature)} ${t.attribution >= 0 ? "↑" : "↓"}`)
    .join(" · ");
  return <Text style={styles.xaiSatiri}>{`🔍 Kararı sürükleyenler: ${metin}`}</Text>;
}

function DiseaseModule({ patientName }: { patientName: string }) {
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
    if (selectedSymptoms.length < 2) {
      showToast("Lütfen en az 2 semptom seçin.", "error");
      return;
    }
    // Girdi aralık validasyonu (boş alanlar serbest; doluysa makul aralıkta olmalı).
    const ranges: Record<string, [number, number, string]> = {
      age: [0, 40, "Yaş"], weight: [0, 80, "Kilo"], hr: [0, 400, "Nabız"],
      temp: [25, 46, "Ateş"], duration: [0, 3650, "Süre"],
    };
    for (const k of Object.keys(ranges)) {
      const raw = (form as any)[k];
      if (raw !== "" && raw != null) {
        const n = Number(raw);
        const [lo, hi, label] = ranges[k];
        if (isNaN(n) || n < lo || n > hi) {
          showToast(`${label} geçersiz (${lo}–${hi} aralığında olmalı).`, "error");
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
      logAiResult(patientName, "Hastalık Analizi", top ? `${trValue(top.disease)} (%${(top.probability * 100).toFixed(0)})` : "Belirgin sonuç yok", { moduleId: "disease", inputType: "clinical", detail: res, confidence: top?.probability });
    }
    // Hata durumunda apiClient zaten kullanıcıya bildirim gösterir (çift-popup önlendi).
  };

  return (
    <Card style={styles.card}>
      <Text style={styles.title}>Kedi Hastalık Tahmini (XGBoost)</Text>
      <ResponsiveGrid minItemWidth={150}>
        <TextInput style={styles.input} placeholder="Yaş" accessibilityLabel="Yaş" keyboardType="numeric" value={form.age} onChangeText={t => setForm({...form, age: t})} />
        <TextInput style={styles.input} placeholder="Kilo" accessibilityLabel="Kilo (kg)" keyboardType="numeric" value={form.weight} onChangeText={t => setForm({...form, weight: t})} />
        <TextInput style={styles.input} placeholder="Nabız" accessibilityLabel="Nabız (atım/dk)" keyboardType="numeric" value={form.hr} onChangeText={t => setForm({...form, hr: t})} />
        <TextInput style={styles.input} placeholder="Ateş" accessibilityLabel="Ateş (°C)" keyboardType="numeric" value={form.temp} onChangeText={t => setForm({...form, temp: t})} />
        <TextInput style={styles.input} placeholder="Süre" accessibilityLabel="Süre (gün)" keyboardType="numeric" value={form.duration} onChangeText={t => setForm({...form, duration: t})} />
      </ResponsiveGrid>
      <Text style={styles.diseaseHint}>
        En az 2 semptom seçmeniz yeterli. Nabız, ateş ve kilo girmek zorunlu değildir —
        ama girerseniz tahmin belirginleşir (ör. ateş/nabız yüksekse model daha spesifik hastalığa yönelir).
      </Text>
      <View style={styles.symptomsGrid}>
        {SYMPTOMS.map((s, idx) => (
          <TouchableOpacity key={idx} style={[styles.symptomBtn, selectedSymptoms.includes(idx) && styles.symptomBtnActive]} onPress={() => toggleSymptom(idx)}>
            <Text style={[styles.symptomLabel, selectedSymptoms.includes(idx) && styles.symptomLabelActive]}>{s}</Text>
          </TouchableOpacity>
        ))}
      </View>
      <View style={{ marginTop: spacing.sm }}>
        <Button variant="primary" label={loading ? "Analiz Ediliyor..." : "Teşhisi Başlat"} onPress={analyze} disabled={loading} />
      </View>

      {result && (
        <View style={styles.resultBox}>
          {result.length === 0 ? (
            <ResultInterpretation tone="info" emoji="🔍" title="Belirgin bir eşleşme bulunamadı"
              text="Seçtiğiniz semptomlarla yüksek olasılıklı bir hastalık eşleşmedi. Farklı ya da daha fazla semptom ekleyerek tekrar deneyebilir; belirtiler sürüyorsa veteriner hekime danışabilirsiniz." />
          ) : (
            <>
              {(() => {
                const top = result[0];
                const pct = Math.round(top.probability * 100);
                const strong = top.probability > 0.6;
                return (
                  <ResultInterpretation
                    tone={strong ? "alert" : "info"} emoji="🩺"
                    title={`En olası: ${top.disease}  ·  %${pct}`}
                    text={strong
                      ? `Girilen semptomlar en çok "${top.disease}" tablosuyla uyumlu (%${pct}). Bu bir ön-değerlendirmedir, kesin teşhis değildir — belirtiler sürüyorsa veteriner hekim muayenesi önerilir.`
                      : `Semptomlar birden çok olası duruma işaret ediyor; en yükseği "${top.disease}" (%${pct}). Güven düşük olduğundan hekim muayenesiyle netleştirmek gerekir.`}
                    points={["Yüzde = modelin o hastalığa güveni; hastalığın şiddeti DEĞİL.", "Aşağıda tüm olasılıklar güvene göre sıralı."]}
                  />
                );
              })()}
              <Text style={styles.ctSubLabel}>Tüm olasılıklar (güvene göre)</Text>
              {result.map((r, i) => (
                <View key={i} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: spacing.xs }}>
                  <Text style={[styles.resultText, { flex: 1 }]}>{i + 1}. {r.disease}</Text>
                  <Text style={[styles.resultText, { fontWeight: 'bold', color: r.probability > 0.6 ? colors.danger : r.probability > 0.3 ? colors.warning : colors.textMuted }]}>
                    %{(r.probability * 100).toFixed(1)}
                  </Text>
                </View>
              ))}
              <XaiSatiri xai={xai} etiketle={(f) => DISEASE_FEATURE_TR[f] ?? f} />
            </>
          )}
          {resultUsedDefaults && result.length > 0 && (
            <Text style={styles.diseaseDefaultsNote}>
              ℹ️ Bu tahmin, girilmeyen vitaller için sağlıklı kedi ortalamaları (nabız ~140, ateş ~38.5°C, kilo ~4 kg)
              varsayılarak yapıldı. Gerçek ölçümleri girerseniz sonuç daha isabetli olur.
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

function VisionModule({ endpoint, title, subtitle, patientName, galleryOnly, explainDestegi }: { endpoint: string, title: string, subtitle: string, patientName: string, galleryOnly?: boolean, explainDestegi?: boolean }) {
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

  const [isLive, setIsLive] = useState(false);
  // BUG FIX: Canlı kamera varsayılan olarak ARKA ('back') kamera (kediyi çekmek için);
  // selfie/ön kamera açılmasını engeller. Flip butonu ile ön↔arka geçiş yapılabilir.
  const [facing, setFacing] = useState<"back" | "front">("back");
  const [autoAdjust, setAutoAdjust] = useState(false);
  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<any>(null);
  const liveIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // BUG #2 FIX: loading state'ini useRef ile takip et, setInterval closure'u her zaman güncel değeri okur
  const loadingRef = useRef(false);
  const autoAdjustRef = useRef(autoAdjust);
  const { aiVisionData, aiVisionFresh } = useLiveData();
  const { isCompact } = useResponsive();

  useEffect(() => {
    autoAdjustRef.current = autoAdjust;
  }, [autoAdjust]);

  // YÜKSEK fix: unmount'ta uçuştaki MANUEL analizi iptal et → boşa 60-90sn model pipeline'ı + unmount-sonrası
  // setState (stale sonuç/yanlış-loglama) önlenir. mountedRef await-sonrası setState'leri de kapılar.
  const mountedRef = useRef(true);
  const analyzeAbortRef = useRef<AbortController | null>(null);
  /** Canlı kamera döngüsündeki uçuştaki kare analizi (unmount'ta iptal edilir). */
  const liveAbortRef = useRef<AbortController | null>(null);
  useEffect(() => () => {
    mountedRef.current = false;
    analyzeAbortRef.current?.abort();
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
    showToast(
      "Otonom Biofeedback hekim onayı gerektirir: Kontrol → AI Pro sekmesinden öneriyi alıp onaylayın.",
      "info",
    );
    // `showToast` deps'te GÜVENLE durabilir: ToastProvider onu `useCallback(..., [])` ile stabil
    // veriyor (eski "KARARSIZ referans" notu bayattı).
  }, [isLive, autoAdjust, showToast]);

  // Canlı kamera (otonom-OLMAYAN mod): telefon kamerasından periyodik kare yakala → analiz et.
  useEffect(() => {
    if (!isLive || autoAdjust) return;
    const capture = async () => {
      if (loadingRef.current || !cameraRef.current) return;
      loadingRef.current = true;
      try {
        // shutterSound: false — canlı analiz döngüsü saniyeler arayla kare alır; her karede
        // deklanşör sesi çalmak klinik ortamda rahatsız edici (saha bildirimi 2026-08-27).
        const photo = await cameraRef.current.takePictureAsync({
          quality: 0.5, skipProcessing: true, shutterSound: false,
        });
        const shrunk = photo?.uri ? await shrinkForUpload(photo.uri) : { uri: "", base64: null };
        if (shrunk.base64) {
          const fd = new FormData();
          fd.append("image_base64", shrunk.base64);
          fd.append("auto_adjust", "false");
          const ctrl = new AbortController();
          // Uçuştaki istek unmount'ta İPTAL EDİLMİYORDU: ekran değişince model çıkarımı boşuna
          // sürüyor, dönen sonuç sökülmüş bileşende setResult çağırıyordu. Controller'ı ref'e koy
          // (cleanup abort eder) ve setState öncesi mountedRef'i kontrol et.
          // CANLI-DONGU: kisa sinir ZORUNLU (uzun timeout kamera akisini kilitler)
          const t = setTimeout(() => ctrl.abort(), 15000);
          liveAbortRef.current = ctrl;
          const r = await fetch(serviceConfig.apiBaseUrl + "/ai" + endpoint, {
            method: "POST", body: fd, headers: { Accept: "application/json", ...authHeaders() }, signal: ctrl.signal,
          });
          clearTimeout(t);
          const data = await r.json();
          if (!mountedRef.current) return;
          if (r.ok && data?.status === "success") setResult(data); // overlay result.image_base64 ile güncellenir
        }
      } catch {
        /* canlı modda kare hatalarını sessiz geç */
      } finally {
        loadingRef.current = false;
      }
    };
    liveIntervalRef.current = setInterval(capture, 2500);
    return () => {
      if (liveIntervalRef.current) {
        clearInterval(liveIntervalRef.current);
        liveIntervalRef.current = null;
      }
      // Uçuştaki kare analizini de iptal et (boşa çıkarım + unmount sonrası setState).
      try { liveAbortRef.current?.abort(); } catch { /* ignore */ }
      liveAbortRef.current = null;
    };
  }, [isLive, autoAdjust, endpoint]);

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
          showToast("Kamera için izin gerekli.", "error");
          return;
        }
      }
    }
    const next = !isLive;
    setIsLive(next);
    if (!next) {
      setImageUri(null);
      setImageBase64(null);
      setImageFile(null);
      setResult(null);
    }
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
          setImageFile(file);
          setImageUri(URL.createObjectURL(file));
          setImageBase64(null);
          setResult(null);
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
          setImageFile(file);
          setImageUri(URL.createObjectURL(file));
          setImageBase64(null);
          setResult(null);
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
      // ARTIK: canlı otonom döngü dışındaki her sürüş için AÇIK ONAY şart.
      let driveHw = false;
      if (autoAdjustRef.current) {
        if (isLive) {
          driveHw = true;                       // canlı kapalı-döngü: zaten bilinçli başlatıldı
        } else {
          driveHw = await platformConfirm(
            "Cihaz otonom sürülsün mü?",
            `Bu analizin sonucuna göre 8 bobin ${patientName ? `"${patientName}" hastasında ` : ""}30 dakika boyunca otomatik sürülecek. ` +
            "Hayvanın kabinde ve gözetim altında olduğundan emin olun.",
            "Evet, seansı başlat"
          );
          if (!mountedRef.current) return;
        }
      }
      formData.append("auto_adjust", driveHw ? "true" : "false");
      // Sunum-katmanı XAI: yalnız MANUEL analizde ve kullanıcı açıkça istediyse (canlı
      // döngüde ASLA — kare başına sn'lerce Grad-CAM akışı kilitler).
      if (explainDestegi && isiHaritasi) formData.append("explain", "true");
      const ctrl = new AbortController();
      analyzeAbortRef.current = ctrl; // unmount iptali için sakla
      const to = setTimeout(() => ctrl.abort(), AI_TIMEOUT_MS); // ilk-kullanım model indirme için geniş timeout
      const response = await fetch(serviceConfig.apiBaseUrl + "/ai" + endpoint, {
        method: "POST",
        body: formData,
        headers: { "Accept": "application/json", ...authHeaders() },
        signal: ctrl.signal,
      });
      clearTimeout(to);
      const data = await response.json();
      if (!mountedRef.current) return; // unmount olduysa stale setState/yanlış-loglama yapma
      if (response.ok && data.status === "success") {
        setResult(data);
        if (isLive) setImageUri(`data:image/jpeg;base64,${data.image_base64}`); // overlay updated
        else logAiResult(patientName, title, summarizeVision(data), { moduleId: endpoint.replace("/vision/", ""), inputType: "image", detail: data }); // sadece manuel analizleri audit'e yaz
      }
      else if (!isLive) showToast(data?.detail || "Analiz sırasında hata oluştu.", "error");
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
              accessibilityLabel="Otonom biofeedback"
              accessibilityHint="Açıkken analiz sonucuna göre bobinler otomatik sürülür"
            >
              <Activity color={autoAdjust ? colors.white : colors.primary} size={16} />
              <Text style={[styles.autoAdjustText, autoAdjust ? {color: colors.white} : null]}>
                Otonom Biofeedback
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => { if (!realtime) showToast("Gerçek-zamanlı işlem Pro+ planında sunulur; Pro'da istekler paylaşımlı kuyruğa girer.", "info"); }}
              style={[styles.rtTag, realtime ? styles.rtTagOn : styles.rtTagOff]}
              accessibilityRole="button"
              accessibilityLabel={realtime ? "Gerçek-zamanlı işlem" : "Kuyruklu işlem — Pro+ ile anlık"}
            >
              <Text style={realtime ? styles.rtTagOnText : styles.rtTagOffText}>
                {realtime ? "⚡ Gerçek-zamanlı" : "Kuyruklu · Pro+ anlık"}
              </Text>
            </TouchableOpacity>
          </View>
        )}
      </View>

      {!imageUri && !isLive && (
        <View style={styles.photoGuide}>
          {endpoint === "/vision/landmark" ? (
            <>
              <Text style={styles.photoGuideTitle}>📸 Doğru FGS analizi için fotoğraf ipuçları</Text>
              <Text style={styles.photoGuideItem}>• Kedinin yüzünü <Text style={styles.photoGuideBold}>tam karşıdan</Text>, net ve yakın çekin</Text>
              <Text style={styles.photoGuideItem}>• İyi aydınlatma — bulanık veya karanlık olmasın</Text>
              <Text style={styles.photoGuideItem}>• Gözler, kulaklar, burun ve bıyıklar net görünsün</Text>
              <Text style={styles.photoGuideItem}>• Tek kedi, yüz kameraya dönük olsun</Text>
            </>
          ) : (
            <>
              <Text style={styles.photoGuideTitle}>📸 Fotoğraf ipuçları</Text>
              <Text style={styles.photoGuideItem}>• Net, iyi aydınlatılmış, yakın görüntü kullanın (bulanık olmasın)</Text>
            </>
          )}
          <Text style={styles.photoGuideWarn}>⚠️ Yanlış/bulanık fotoğraf hatalı sonuç verir. Yüz net tespit edilemezse uyarı gösterilir.</Text>
        </View>
      )}
      <View style={styles.imagePreviewContainer}>
        {(isLive && autoAdjust) ? (
          // Otonom Biofeedback: SUNUCU (klinik) kamerası sürüyor — telefon kamerası DEĞİL.
          // Sunucu karesi gelene kadar telefon CameraView'ı GÖSTERME (kafa-karışıklığı önlenir).
          <View style={styles.cameraContainer}>
            {aiVisionData?.imageBase64 ? (
              <>
                <Image source={{ uri: `data:image/jpeg;base64,${aiVisionData.imageBase64}` }} style={styles.cameraView} resizeMode="contain" />
                {/* Rozet ARTIK tazeliğe bağlı: aiVisionData son kareyi kalıcı tuttuğundan, backend
                    döngüsü bittiğinde (süre dolumu / E-stop / kamera hatası) "AKTİF" yazısı donmuş
                    kareyle sonsuza dek açık kalıyordu. */}
                <View style={[styles.liveIndicator, !aiVisionFresh && { backgroundColor: colors.warning }]}>
                  <View style={styles.liveDot} />
                  <Text style={styles.liveText}>{aiVisionFresh ? "OTONOM BİOFEEDBACK AKTİF" : "YAYIN DURDU — GÜNCEL DEĞİL"}</Text>
                </View>
              </>
            ) : (
              <View style={[styles.cameraView, { alignItems: "center", justifyContent: "center", gap: spacing.sm }]}>
                <Activity color={colors.primary} size={32} />
                <Text style={styles.placeholderText}>Sunucu kamerası bekleniyor…</Text>
              </View>
            )}
            <Text style={styles.serverCamNote}>🖥️ Sunucu (klinik) kamerası seansı sürüyor — telefon kamerası kullanılmıyor</Text>
          </View>
        ) : isLive ? (
          <View style={styles.cameraContainer}>
            <CameraView ref={cameraRef} style={styles.cameraView} facing={facing} />
            {result?.image_base64 && (
              <Image source={{ uri: `data:image/jpeg;base64,${result.image_base64}` }} style={styles.cameraOverlay} />
            )}
            <TouchableOpacity
              style={styles.flipCameraBtn}
              onPress={() => setFacing((f) => (f === "back" ? "front" : "back"))}
              accessibilityRole="button"
              accessibilityLabel="Kamerayı çevir"
            >
              <SwitchCamera color={colors.white} size={20} />
            </TouchableOpacity>
            <View style={styles.liveIndicator}>
              <View style={styles.liveDot} />
              <Text style={styles.liveText}>KAMERA AKTİF</Text>
            </View>
          </View>
        ) : imageUri ? (
          <Image source={{ uri: result?.image_base64 ? `data:image/jpeg;base64,${result.image_base64}` : imageUri }} style={styles.imagePreview} />
        ) : (
          <View style={styles.placeholderBox}>
            <ImageIcon color={colors.textMuted} size={48} />
            <Text style={styles.placeholderText}>Görüntü seçilmedi</Text>
          </View>
        )}
      </View>

      <View style={[styles.btnRow, isCompact && { flexDirection: "column" }]}>
        <View style={isCompact ? { width: "100%" } : { flex: 1 }}>
          <Button label="Galeriden Seç" icon={<ImageIcon color={colors.white} size={16} />} onPress={pickImage} disabled={isLive} />
        </View>
        {/* Foto çek + canlı kamera: mikroskop/CT gibi dosya-tabanlı modüllerde (galleryOnly) gizli */}
        {!galleryOnly && (
          <View style={isCompact ? { width: "100%" } : { flex: 1 }}>
            <Button label="Fotoğraf Çek" icon={<Camera color={colors.white} size={16} />} onPress={takePhoto} disabled={isLive} />
          </View>
        )}
        {!galleryOnly && (
          <View style={isCompact ? { width: "100%" } : { flex: 1 }}>
            <Button
              label={isLive ? "Canlıyı Durdur" : "Canlı Kamera"}
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
            accessibilityLabel="Isı haritası üret (Grad-CAM)"
          >
            <Text style={styles.xaiToggleText}>
              {isiHaritasi ? "☑" : "☐"} 🔍 Isı haritası üret (modelin baktığı bölgeler — analiz biraz uzar)
            </Text>
          </TouchableOpacity>
        )}
        <Button variant="primary" label={loading ? "Analiz Ediliyor..." : "AI Analizini Başlat"} icon={loading ? <ActivityIndicator color={colors.white} /> : <Sparkles color={colors.white} size={16} />} disabled={!imageUri || loading} onPress={() => analyzeImage()} />
      </View>
      {longLoading && <Text style={styles.modelHint}>Model hazırlanıyor (ilk kullanım uzun sürebilir)…</Text>}

      {result && !autoAdjust && (
        <View style={styles.resultBox}>
          {(() => {
            const notDet = result.detected === false || result.fgs_total === null || (typeof result.fgs_total === "number" && result.fgs_total < 0);
            // ── FGS / yüz ağrısı ──
            if (result.fgs_total !== undefined) {
              if (notDet) return <ResultInterpretation tone="alert" emoji="⚠️" title="Yüz net tespit edilemedi"
                text="Kedinin yüzü net seçilemediği için ağrı skoru hesaplanamadı. Net, iyi aydınlatılmış ve tam karşıdan çekilmiş bir fotoğrafla tekrar deneyin." />;
              const s = result.fgs_total ?? 0;  // null/negatif yukarıda notDet ile döndü → burada geçerli sayı
              if (s === 0) return <ResultInterpretation tone="positive" emoji="😌" title="Ağrı belirtisi yok (FGS 0/10)"
                text="Yüz hatlarında ağrı ya da stres bulgusu görülmüyor; kedi rahat görünüyor." />;
              if (s <= 3) return <ResultInterpretation tone="info" emoji="🙂" title={`Hafif bulgu — FGS ${s}/10`}
                text="Hafif bir rahatsızlık ya da gerginlik olabilir. Gözlemlemeye devam edin; isterseniz PEMF ile rahatlatabilirsiniz."
                points={["Kulak/göz/burun/bıyık/baş pozisyon skorları aşağıda.", "FGS = Feline Grimace Scale (yüz ağrı ölçeği)."]} />;
              if (s <= 5) return <ResultInterpretation tone="alert" emoji="😾" title={`Orta derece ağrı — FGS ${s}/10`}
                text="Yüz hatlarında belirgin gerginlik var. Otonom PEMF terapisi uygulanabilir; belirti 1-2 günden uzun sürerse veteriner hekime danışın." />;
              return <ResultInterpretation tone="critical" emoji="🚨" title={`Şiddetli ağrı — FGS ${s}/10`}
                text="Ciddi ağrı bulgusu tespit edildi. Vakit kaybetmeden veteriner hekime başvurulması önerilir." />;
            }
            // ── Termal ──
            if (result.prediction) {
              const sick = result.prediction.label === "Sick";
              const prob = result.prediction.confidence !== undefined ? Math.round(result.prediction.confidence * 100) : null;
              return sick
                ? <ResultInterpretation tone="alert" emoji="🌡️" title={`Termal anormallik${prob != null ? ` · %${prob} güven` : ""}`}
                    text="Termal görüntüde olası bir sıcaklık anormalliği (iltihap/enfeksiyon odağı olabilir) tespit edildi. İlgili bölgeyi hekimle değerlendirin." />
                : <ResultInterpretation tone="positive" emoji="🌡️" title={`Belirgin termal anormallik yok${prob != null ? ` · %${prob} güven` : ""}`}
                    text="Termal dağılımda dikkat çekici bir anormallik görülmedi." />;
            }
            // ── Segmentasyon ──
            if (result.cat_count !== undefined) {
              return <ResultInterpretation tone={result.cat_count > 0 ? "positive" : "alert"} emoji="🐾"
                title={`${result.cat_count} kedi tespit edildi`}
                text={result.cat_count > 0
                  ? "Vücut sınırları başarıyla çıkarıldı. Segmentasyon; ölçüm ve diğer analizler için bir ön-işleme adımıdır."
                  : "Görüntüde kedi tespit edilemedi. Kedinin tümü kadraja girecek şekilde tekrar deneyin."} />;
            }
            // ── Retikülosit ──
            if (result.counts) {
              const ery = Number(result.counts["erythrocyte"] || 0);
              const ret = Number(result.counts["punctate reticulocyte"] || 0) + Number(result.counts["aggregate reticulocyte"] || 0);
              const total = ery + ret;
              const pctR = total > 0 ? (ret / total) * 100 : 0;
              const high = pctR >= 4;
              return <ResultInterpretation tone={high ? "alert" : "info"} emoji="🔬" title={`Retikülosit oranı ~%${pctR.toFixed(1)}`}
                text={high
                  ? "Görece yüksek retikülosit oranı, kemik iliğinin yeni kırmızı küre ürettiğini (rejeneratif yanıt — ör. kanamaya/anemiye tepki) düşündürebilir. Klinik bağlamla birlikte değerlendirin."
                  : "Retikülosit oranı düşük–normal aralıkta görünüyor. Anemi varsa non-rejeneratif olabilir; kesin yorum klinik bağlam gerektirir."}
                points={["Sayılar tek bir mikroskop alanına aittir, tanısal referans aralığı değildir."]} />;
            }
            return null;
          })()}
          {result.fgs_total != null && result.fgs_total >= 0 && (
            <View>
              <Text style={styles.resultText}>FGS Skoru: <Text style={{fontWeight:'bold'}}>{result.fgs_total} / 10</Text></Text>
              {result.raw_fgs?.action_units && (
                <View style={{ marginTop: spacing.sm, paddingLeft: spacing.md, borderLeftWidth: 2, borderLeftColor: colors.primarySoft }}>
                  <Text style={[styles.resultText, {fontSize: typography.small}]}>• Kulak Pozisyonu: {result.raw_fgs.action_units["AU1_Ear_Position"]?.score ?? "-"}</Text>
                  <Text style={[styles.resultText, {fontSize: typography.small}]}>• Göz Kısma: {result.raw_fgs.action_units["AU2_Orbital_Tightening"]?.score ?? "-"}</Text>
                  <Text style={[styles.resultText, {fontSize: typography.small}]}>• Burun Kasılması: {result.raw_fgs.action_units["AU3_Muzzle_Tension"]?.score ?? "-"}</Text>
                  <Text style={[styles.resultText, {fontSize: typography.small}]}>• Bıyık Değişimi: {result.raw_fgs.action_units["AU4_Whisker_Position"]?.score ?? "-"}</Text>
                  <Text style={[styles.resultText, {fontSize: typography.small}]}>• Baş Pozisyonu: {result.raw_fgs.action_units["AU5_Head_Position"]?.score ?? "-"}</Text>
                </View>
              )}
              {result.raw_fgs?.measurements && (result as any).fgs_bantlari ? (() => {
                const OLCUM_TR: Record<string, string> = {
                  ear_angle: "Kulak açısı", ear_elev: "Kulak yüksekliği", ear_spread: "Kulak açıklığı",
                  eye_ratio_avg: "Göz oranı", mouth_aspect: "Ağız oranı", muzzle_compact: "Burun sıkılığı",
                  whisker_tension: "Bıyık gerginliği", head_center_y: "Baş konumu",
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
                    <Text style={styles.ctSubLabel}>Ölçümler · popülasyon bandı (p5–p95)</Text>
                    {satirlar.map((k) => {
                      const v = Number(olc[OLCUM_KAYNAK[k]]); const b = bant[k];
                      const disari = v < b.p5 || v > b.p95;
                      return (
                        <Text key={k} style={[styles.resultText, { fontSize: typography.small }]}>
                          • {OLCUM_TR[k]}: <Text style={{ fontWeight: "bold", color: disari ? colors.warning : colors.text }}>{v.toFixed(3)}</Text>
                          <Text style={{ color: colors.textMuted }}>{`  [${b.p5.toFixed(2)} – ${b.p95.toFixed(2)}]${disari ? "  ← bant dışı" : ""}`}</Text>
                        </Text>
                      );
                    })}
                    <Text style={styles.ctHint}>Bant, sağlıklı kalibrasyon popülasyonunun p5–p95 aralığıdır; bant dışı değer tek başına tanı değildir.</Text>
                  </View>
                );
              })() : null}
            </View>
          )}
          {result.cat_count !== undefined && <Text style={styles.resultText}>Tespit Edilen Kedi: <Text style={{fontWeight:'bold'}}>{result.cat_count}</Text></Text>}
          {result.prediction && (() => {
             const lbl = result.prediction.label === "Sick" ? "Hasta (Riskli)" : "Sağlıklı";
             const prob = result.prediction.confidence !== undefined ? (result.prediction.confidence * 100).toFixed(1) : "?";
             return <Text style={styles.resultText}>Termal Tespit: <Text style={{fontWeight:'bold', color: result.prediction.label === "Sick" ? colors.danger : colors.success}}>{lbl}</Text> (Doğruluk: %{prob})</Text>;
          })()}
          {result.counts && (
            <>
              <Text style={styles.resultText}>Eritrosit: {result.counts["erythrocyte"]}</Text>
              <Text style={styles.resultText}>Noktalı Retikülosit: {result.counts["punctate reticulocyte"]}</Text>
              <Text style={styles.resultText}>Agrege Retikülosit: {result.counts["aggregate reticulocyte"]}</Text>
            </>
          )}
          {/* Sunum-katmanı XAI (Faz 2): Grad-CAM ısı haritası — istenip üretildiyse. */}
          {result.xai_image_base64 && (
            <>
              <Text style={styles.ctSubLabel}>🔍 Isı haritası — modelin baktığı bölgeler (kırmızı = karara güçlü etki)</Text>
              <Image source={{ uri: `data:image/jpeg;base64,${result.xai_image_base64}` }} style={styles.imagePreview} resizeMode="contain" />
            </>
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
      {result?.hw_status ? (
        result.hw_status === "updated" ? (
          <View style={{ marginTop: spacing.sm, padding: spacing.sm, backgroundColor: colors.success + "22", borderRadius: radius.sm, borderWidth: 1, borderColor: colors.success }}>
            <Text style={[styles.resultText, { fontWeight: "bold", color: colors.success }]}>⚡ Cihaz otonom olarak sürülüyor</Text>
            <Text style={styles.resultText}>Frekans: {Number(result.hw_params?.freq ?? 0).toFixed(1)} Hz · Şiddet: {Number(result.hw_params?.duty ?? 0).toFixed(1)} %</Text>
            <Text style={styles.resultText}>Durdurmak için Kontrol ekranındaki ACİL DURDUR&apos;u kullanın.</Text>
          </View>
        ) : (
          <View style={{ marginTop: spacing.sm, padding: spacing.sm, backgroundColor: colors.warning + "22", borderRadius: radius.sm, borderWidth: 1, borderColor: colors.warning }}>
            <Text style={[styles.resultText, { fontWeight: "bold", color: colors.warning }]}>⚠️ Cihaz SÜRÜLMEDİ</Text>
            <Text style={styles.resultText}>
              {result.hw_status === "skipped_session_active"
                ? "Başka bir seans zaten aktif — otonom sürüş atlandı."
                : result.hw_status === "skipped_unauthenticated"
                  ? "Uzaktan kimliksiz istekte otonom sürüş yapılmaz (güvenlik)."
                  : `Otonom sürüş atlandı (${String(result.hw_status)}).`}
            </Text>
          </View>
        )
      ) : null}

      {isLive && autoAdjust && aiVisionData && (
        <View style={styles.resultBox}>
          <Text style={styles.resultTitle}>Otonom Canlı Sonuç:</Text>
          {/* Eskiden burada `Anlık FGS Skoru: {aiVisionData.fgs_total} / 10` yazıyordu; backend'in
              ai_vision yayınında fgs_total alanı YOK (cat_organ pipeline'ına geçilince kaldırıldı) →
              satır her zaman "Anlık FGS Skoru:  / 10" olarak BOŞ basılıyordu. Yayının gerçekten
              içerdiği alanları göster. */}
          <Text style={styles.resultText}>
            Hedef organ: <Text style={{ fontWeight: "bold" }}>{aiVisionData.organName || "—"}</Text>
            {aiVisionData.detected === false ? " (konumlandırılamadı)" : ""}
          </Text>
          {typeof aiVisionData.reliability === "number" && (
            <Text style={styles.resultText}>Lokalizasyon güveni: <Text style={{ fontWeight: "bold" }}>%{(aiVisionData.reliability * 100).toFixed(0)}</Text></Text>
          )}
          {typeof aiVisionData.eField === "number" && (
            <Text style={styles.resultText}>E-alan: <Text style={{ fontWeight: "bold" }}>{aiVisionData.eField.toFixed(2)}</Text></Text>
          )}
          {typeof aiVisionData.remainingSec === "number" && (
            <Text style={styles.resultText}>Kalan süre: <Text style={{ fontWeight: "bold" }}>{Math.max(0, Math.round(aiVisionData.remainingSec / 60))} dk</Text></Text>
          )}
          {/* Tazelik kapısı: yayın durduysa "güncelleniyor" DEME (donmuş kareyi canlı gösterme).
              Bu, kaldırılan GLOBAL 3-durumlu göstergeyi geri getirmez — yalnız aktif otonom
              seansa özgü, yerel bir doğrulama. */}
          {aiVisionFresh ? (
            <View style={{ marginTop: spacing.sm, padding: spacing.sm, backgroundColor: colors.success + "22", borderRadius: radius.sm, borderWidth: 1, borderColor: colors.success }}>
              <Text style={[styles.resultText, { fontWeight: "bold", color: colors.success }]}>Cihaz otonom olarak güncelleniyor (saniyede 1)</Text>
            </View>
          ) : (
            <View style={{ marginTop: spacing.sm, padding: spacing.sm, backgroundColor: colors.warning + "22", borderRadius: radius.sm, borderWidth: 1, borderColor: colors.warning }}>
              <Text style={[styles.resultText, { fontWeight: "bold", color: colors.warning }]}>⚠️ Canlı yayın durdu — gösterilen kare GÜNCEL DEĞİL</Text>
              <Text style={styles.resultText}>Seansın sürdüğü doğrulanamıyor. Kontrol ekranından durumu teyit edin.</Text>
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
 * Backend: POST /api/ai/vision/em_fantom (phantom_cv). Canlı kamera/otonom YOK — tek foto.
 */
function PhantomModule({ patientName }: { patientName: string }) {
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
          setImageFile(file); setImageUri(URL.createObjectURL(file)); setImageBase64(null); setResult(null);
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
          setImageFile(file); setImageUri(URL.createObjectURL(file)); setImageBase64(null); setResult(null);
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
          logAiResult(patientName, "Fantom Tümör Analizi", `${data.n_tumor} tümör${ec != null ? `, E_c≈${Number(ec).toFixed(3)}` : ""}`, { moduleId: "em_fantom", inputType: "image", detail: data });
        }
      } else {
        showToast(data?.detail || "Analiz sırasında hata oluştu.", "error");
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
      <Text style={styles.title}>Fantom Tümör Analizi</Text>
      <Text style={styles.subtitle}>Sentetik böbrek fantomundan mavi tümör odaklarını tespit eder; 3B konum + PEMF bobin/E-alan tahmini üretir.</Text>

      {!imageUri && (
        <View style={styles.photoGuide}>
          <Text style={styles.photoGuideTitle}>📸 Fantom fotoğraf ipuçları</Text>
          <Text style={styles.photoGuideItem}>• Fantomu <Text style={styles.photoGuideBold}>tam tepeden</Text>, net ve iyi aydınlatılmış çekin</Text>
          <Text style={styles.photoGuideItem}>• Mavi tümör noktaları belirgin görünsün</Text>
          <Text style={styles.photoGuideItem}>• Gerçek mm ölçüm için fantom boyunu (cm) girin — boş bırakılırsa piksel modu</Text>
        </View>
      )}

      <View style={styles.imagePreviewContainer}>
        {imageUri ? (
          <Image source={{ uri: result?.image_base64 ? `data:image/jpeg;base64,${result.image_base64}` : imageUri }} style={styles.imagePreview} resizeMode="contain" />
        ) : (
          <View style={styles.placeholderBox}>
            <ImageIcon color={colors.textMuted} size={48} />
            <Text style={styles.placeholderText}>Görüntü seçilmedi</Text>
          </View>
        )}
      </View>

      <View style={styles.fantomLenRow}>
        <Text style={styles.fantomLenLabel}>Fantom boyu (cm)</Text>
        <TextInput
          style={styles.fantomLenInput}
          keyboardType="numeric"
          accessibilityLabel="Fantom boyu (cm)"
          placeholder="ör. 10 · boş = piksel"
          placeholderTextColor={colors.textMuted}
          value={phantomLen}
          onChangeText={setPhantomLen}
        />
      </View>

      <View style={[styles.btnRow, isCompact && { flexDirection: "column" }]}>
        <View style={isCompact ? { width: "100%" } : { flex: 1 }}>
          <Button label="Galeriden Seç" icon={<ImageIcon color={colors.white} size={16} />} onPress={pickImage} />
        </View>
        <View style={isCompact ? { width: "100%" } : { flex: 1 }}>
          <Button label="Fotoğraf Çek" icon={<Camera color={colors.white} size={16} />} onPress={takePhoto} />
        </View>
      </View>

      <View style={styles.analyzeBtn}>
        <Button variant="primary" label={loading ? "Analiz Ediliyor..." : "Fantom Analizini Başlat"} icon={loading ? <ActivityIndicator color={colors.white} /> : <Sparkles color={colors.white} size={16} />} disabled={!imageUri || loading} onPress={analyze} />
      </View>
      {longLoading && <Text style={styles.modelHint}>Model hazırlanıyor (ilk kullanım uzun sürebilir)…</Text>}

      {result && (
        <View style={styles.resultBox}>
          {(result.status === "no_detection" || !result.success) ? (
            <ResultInterpretation tone="alert" emoji="⚠️" title="Fantom / tümör tespit edilemedi"
              text="Net, tepeden ve iyi aydınlatılmış bir fotoğrafla tekrar deneyin." />
          ) : (
            <>
              {(() => {
                const n = result.n_tumor || 0;
                return <ResultInterpretation tone={n > 0 ? "alert" : "info"} emoji="🎯" title={`${n} tümör odağı bulundu`}
                  text="Her tümör için kanserli ve sağlıklı dokuya düşen elektrik alanı (E) hesaplandı; 7 PEMF bobininin duty ayarı (D1–D7) buna göre üretildi."
                  points={["E_kanser yüksekse alan o bölgeye daha odaklıdır.", "D1–D7 çubukları her bobinin sürüş oranını (duty %) gösterir.", "3B koordinat: tümör merkezinin ölçek/kabin çerçevesindeki konumu."]} />;
              })()}
              <Text style={styles.resultText}>Tespit edilen tümör: <Text style={{ fontWeight: "bold" }}>{result.n_tumor}</Text>   ·   Ölçek: <Text style={{ fontWeight: "bold" }}>{method === "pixel" ? "piksel" : `${result.mm_per_px} mm/px`}</Text></Text>
              {(result.tumor_regions || []).map((t: AiTumorRegion, i: number) => {
                const c = t.centroid_cabin_mm || [0, 0, 0];
                const D: number[] = Array.isArray(t.D) ? t.D : [];
                return (
                  <View key={i} style={styles.tumorRow}>
                    <Text style={styles.tumorHeader}>Tümör {i + 1}   ·   ({Number(c[0]).toFixed(1)}, {Number(c[1]).toFixed(1)}, {Number(c[2]).toFixed(1)}) {unit}</Text>
                    <Text style={[styles.resultText, { fontSize: typography.small }]}>
                      E_kanser: <Text style={{ fontWeight: "bold", color: colors.danger }}>{Number(t.E_cancer).toFixed(4)}</Text>   ·   E_sağlıklı: {Number(t.E_healthy).toFixed(4)}   ·   Alan: {Number(t.area_mm2).toFixed(1)} mm²
                    </Text>
                    {D.length > 0 && (
                      <View style={styles.dBarRow}>
                        {D.map((d: number, j: number) => (
                          <View key={j} style={styles.dBarWrap}>
                            <View style={styles.dBarTrack}>
                              <View style={[styles.dBarFill, { height: Math.max(2, Math.round((Math.min(Math.max(d, 0), 0.5) / 0.5) * 26)) }]} />
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
          <MedicalDisclaimer />
        </View>
      )}
    </Card>
  );
}

/**
 * Petri Kuyu Analizi — petri fotoğrafından YOLO11m-seg ile N kuyucuk tespit eder,
 * her kuyuda HSV kanser sınıflandırması yapar, 3B konum + PetriPredictor (BaggingRegressor
 * ONNX) ile kuyu başına PEMF bobin duty (D1-7) + E-alan (E_cancer/E_healthy) tahmini üretir.
 * Backend: POST /api/ai/vision/em_petri (petri_cv). Canlı kamera/otonom YOK — tek foto.
 */
function PetriModule({ patientName }: { patientName: string }) {
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
          setImageFile(file); setImageUri(URL.createObjectURL(file)); setImageBase64(null); setResult(null);
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
          setImageFile(file); setImageUri(URL.createObjectURL(file)); setImageBase64(null); setResult(null);
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
      const dia = parseFloat(petriDia.replace(",", "."));
      if (!isNaN(dia) && dia > 0) formData.append("petri_diameter_cm", String(dia));

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
          logAiResult(patientName, "Petri Kuyu Analizi", `${data.n_wells} kuyu (${data.n_cancer} kanser)`, { moduleId: "em_petri", inputType: "image", detail: data });
        }
      } else {
        showToast(data?.detail || "Analiz sırasında hata oluştu.", "error");
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
      <Text style={styles.title}>Petri Kuyu Analizi</Text>
      <Text style={styles.subtitle}>Petri fotoğrafından kuyucukları tespit eder, her kuyuda kanser sınıflandırması + PEMF bobin/E-alan tahmini üretir.</Text>

      {!imageUri && (
        <View style={styles.photoGuide}>
          <Text style={styles.photoGuideTitle}>📸 Petri fotoğraf ipuçları</Text>
          <Text style={styles.photoGuideItem}>• Petri kabını <Text style={styles.photoGuideBold}>tam tepeden</Text>, net ve iyi aydınlatılmış çekin</Text>
          <Text style={styles.photoGuideItem}>• Tüm kuyucuklar ve mavi kanser bölgeleri görünsün</Text>
          <Text style={styles.photoGuideItem}>• Gerçek mm ölçüm için petri çapını (cm) girin — boş bırakılırsa piksel modu</Text>
        </View>
      )}

      <View style={styles.imagePreviewContainer}>
        {imageUri ? (
          <Image source={{ uri: result?.image_base64 ? `data:image/jpeg;base64,${result.image_base64}` : imageUri }} style={styles.imagePreview} resizeMode="contain" />
        ) : (
          <View style={styles.placeholderBox}>
            <ImageIcon color={colors.textMuted} size={48} />
            <Text style={styles.placeholderText}>Görüntü seçilmedi</Text>
          </View>
        )}
      </View>

      <View style={styles.fantomLenRow}>
        <Text style={styles.fantomLenLabel}>Petri çapı (cm)</Text>
        <TextInput
          style={styles.fantomLenInput}
          keyboardType="numeric"
          accessibilityLabel="Petri çapı (cm)"
          placeholder="ör. 8 · boş = piksel"
          placeholderTextColor={colors.textMuted}
          value={petriDia}
          onChangeText={setPetriDia}
        />
      </View>
      <Text style={styles.petriHint}>QR marker fotoğrafta varsa konum otomatik çıkarılır (QR); yoksa petri çapı ile ölçeklenir.</Text>

      <View style={[styles.btnRow, isCompact && { flexDirection: "column" }]}>
        <View style={isCompact ? { width: "100%" } : { flex: 1 }}>
          <Button label="Galeriden Seç" icon={<ImageIcon color={colors.white} size={16} />} onPress={pickImage} />
        </View>
        <View style={isCompact ? { width: "100%" } : { flex: 1 }}>
          <Button label="Fotoğraf Çek" icon={<Camera color={colors.white} size={16} />} onPress={takePhoto} />
        </View>
      </View>

      <View style={styles.analyzeBtn}>
        <Button variant="primary" label={loading ? "Analiz Ediliyor..." : "Petri Analizini Başlat"} icon={loading ? <ActivityIndicator color={colors.white} /> : <Sparkles color={colors.white} size={16} />} disabled={!imageUri || loading} onPress={analyze} />
      </View>
      {longLoading && <Text style={styles.modelHint}>Model hazırlanıyor (ilk kullanım uzun sürebilir)…</Text>}

      {result && (
        <View style={styles.resultBox}>
          {(result.status === "no_detection" || !result.success) ? (
            <ResultInterpretation tone="alert" emoji="⚠️" title="Kuyucuk tespit edilemedi"
              text="Net, tepeden ve iyi aydınlatılmış bir fotoğrafla tekrar deneyin." />
          ) : (
            <>
              {(() => {
                const nc = result.n_cancer || 0;
                return <ResultInterpretation tone={nc > 0 ? "alert" : "positive"} emoji="🧫"
                  title={`${result.n_wells} kuyu · ${nc} kanser, ${result.n_healthy} sağlıklı`}
                  text={nc > 0
                    ? `${nc} kuyuda kanser sınıflandırıldı. Her kuyu için 3B konum, elektrik alanı (E) ve 7 bobinin duty ayarı (D1–D7) aşağıda listelenir.`
                    : "Kuyularda kanser bulgusu sınıflandırılmadı; yine de her kuyu için hesaplanan E-alanı ve bobin ayarı aşağıda."}
                  points={["Kırmızı = kanser, yeşil = sağlıklı sınıflandırma.", "D1–D7 çubukları her bobinin sürüş oranını (duty %) gösterir."]} />;
              })()}
              <Text style={styles.resultText}>
                Kuyu: <Text style={{ fontWeight: "bold" }}>{result.n_wells}</Text>   ·   Kanser: <Text style={{ fontWeight: "bold", color: colors.danger }}>{result.n_cancer}</Text>   ·   Sağlıklı: <Text style={{ fontWeight: "bold", color: colors.success }}>{result.n_healthy}</Text>
              </Text>
              <Text style={[styles.resultText, { fontSize: typography.small }]}>Ölçek: {method === "pixel" ? "piksel" : `${result.mm_per_px} mm/px`}</Text>
              {(result.wells || []).map((w: AiWell, i: number) => {
                const c = w.centroid_cabin_mm || [0, 0, 0];
                const D: number[] = Array.isArray(w.D) ? w.D : [];
                const isCancer = w.label === "cancer" || w.organ_id === 1;
                return (
                  <View key={i} style={styles.tumorRow}>
                    <Text style={styles.tumorHeader}>
                      {w.well_id}   ·   <Text style={{ color: isCancer ? colors.danger : colors.success }}>{isCancer ? "Kanser" : "Sağlıklı"}</Text>   ·   ({Number(c[0]).toFixed(1)}, {Number(c[1]).toFixed(1)}, {Number(c[2]).toFixed(1)}) {unit}
                      {isCancer && (w as any).n_cancer_pixels != null ? <Text style={{ color: colors.textMuted, fontSize: typography.small }}>{`  — gerekçe: ${(w as any).n_cancer_pixels} mavi piksel (eşik ≥30)`}</Text> : null}
                    </Text>
                    <Text style={[styles.resultText, { fontSize: typography.small }]}>
                      E_kanser: <Text style={{ fontWeight: "bold", color: colors.danger }}>{Number(w.E_cancer).toFixed(4)}</Text>   ·   E_sağlıklı: {Number(w.E_healthy).toFixed(4)}   ·   Alan: {Number(w.area_mm2).toFixed(1)} mm²
                    </Text>
                    {D.length > 0 && (
                      <View style={styles.dBarRow}>
                        {D.map((d: number, j: number) => (
                          <View key={j} style={styles.dBarWrap}>
                            <View style={styles.dBarTrack}>
                              <View style={[styles.dBarFill, { height: Math.max(2, Math.round((Math.min(Math.max(d, 0), 0.5) / 0.5) * 26)) }]} />
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
        logAiResult(patientName, "Böbrek RNA (KIRC)", `${data.n_patients} hasta`, { moduleId: "kidney_rna", inputType: "csv", detail: data });
      } else {
        showToast(data?.detail || "Analiz sırasında hata oluştu.", "error");
      }
    } catch (e) {
      // Ham istisna metni kullanıcıya basılıyordu; dosya seçici yolunda bu metin DOSYA YOLU/ADI
      // (hasta adı içerebilir) taşıyabiliyor. Ayrıntı konsola, kullanıcıya sade mesaj.
      console.error("RNA analizi hatası:", e);
      // Satır-içi AbortError ayrımı `aiHataMesaji`ye devredildi (2026-08-12).
      showToast(aiHataMesaji(e, "Analiz başarısız. Dosyayı ve bağlantıyı kontrol edip tekrar deneyin."), "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card style={styles.card}>
      <Text style={styles.title}>Böbrek RNA Analizi (KIRC)</Text>
      <Text style={styles.subtitle}>RNA-seq gen ekspresyon CSV&apos;sinden böbrek renal clear cell karsinom (KIRC) sınıflandırması.</Text>

      <View style={styles.photoGuide}>
        <Text style={styles.photoGuideTitle}>📄 CSV formatı</Text>
        <Text style={styles.photoGuideItem}>• Satır = hasta, sütun = <Text style={styles.photoGuideBold}>20531 gen</Text> (eğitim/TCGA sırasında)</Text>
        <Text style={styles.photoGuideItem}>• 1. sütun = hasta ID (metin)</Text>
        <Text style={styles.photoGuideItem}>• Bir sekans laboratuvarı çıktısı — fotoğraf değil</Text>
      </View>

      <View style={styles.analyzeBtn}>
        <Button label={file ? "Başka CSV Seç" : "CSV Seç"} icon={<FileText color={colors.white} size={16} />} onPress={pickCsv} />
      </View>
      {file && <Text style={styles.rnaFileName} numberOfLines={1}>📄 {file.name}</Text>}

      <TouchableOpacity style={styles.xaiToggle} accessibilityRole="switch" accessibilityState={{ checked: isiHaritasi }} onPress={() => setIsiHaritasi(!isiHaritasi)}>
        <Text style={styles.xaiToggleText}>{isiHaritasi ? "☑" : "☐"} 🔍 Sürükleyen genleri göster (Integrated Gradients — en fazla 25 hasta)</Text>
      </TouchableOpacity>

      <View style={styles.analyzeBtn}>
        <Button variant="primary" label={loading ? "Analiz Ediliyor..." : "RNA Analizini Başlat"} icon={loading ? <ActivityIndicator color={colors.white} /> : <Sparkles color={colors.white} size={16} />} disabled={!file || loading} onPress={analyze} />
      </View>
      {longLoading && <Text style={styles.modelHint}>Model hazırlanıyor (ilk kullanım uzun sürebilir)…</Text>}

      {result && (
        <View style={styles.resultBox}>
          {(() => {
            const preds = result.predictions || [];
            const kirc = preds.filter((p: AiPrediction) => p.prediction === "KIRC").length;
            return <ResultInterpretation tone={kirc > 0 ? "alert" : "positive"} emoji="🧬"
              title={kirc > 0 ? `${kirc}/${result.n_patients} örnekte KIRC işareti` : "KIRC işareti bulunamadı"}
              text={kirc > 0
                ? "KIRC (böbrek berrak hücreli karsinom) en yaygın böbrek kanseri türüdür. Model, gen-ekspresyon (RNA-seq) desenine göre sınıflandırma yaptı — yüksek güven bile KESİN tanı değildir, klinik ve patolojik doğrulama gerekir."
                : "Örnekler 'other' (KIRC değil) olarak sınıflandı. Bu bir tarama sonucudur, kesin tanının yerine geçmez."}
              points={["Güven = modelin o sınıfa olasılığı.", "Sonuç gen-ekspresyon profiline dayanır; tek başına tanısal değildir."]} />;
          })()}
          <Text style={styles.resultText}>Hasta sayısı: <Text style={{ fontWeight: "bold" }}>{result.n_patients}</Text></Text>
          {(result.predictions || []).map((p: AiPrediction, i: number) => {
            const isKirc = p.prediction === "KIRC";
            return (
              <View key={i} style={styles.tumorRow}>
                {/* Model etiketleri ham İngilizce basılıyordu ("KIRC" / "other") — uygulamanın
                    geri kalanı Türkçe. KIRC klinik bir kısaltma olduğundan korunur, açıklaması eklenir. */}
                <Text style={styles.tumorHeader}>
                  {p.patient_id}   ·   <Text style={{ color: isKirc ? colors.danger : colors.success }}>
                    {isKirc ? "KIRC işareti" : "KIRC değil"}
                  </Text>
                </Text>
                <Text style={[styles.resultText, { fontSize: typography.small }]}>
                  Güven: <Text style={{ fontWeight: "bold" }}>%{(Number(p.confidence) * 100).toFixed(1)}</Text>
                  {p.prob_KIRC != null ? `   ·   KIRC olasılığı: %${(Number(p.prob_KIRC) * 100).toFixed(1)}` : ""}
                </Text>
                {(() => {
                  const xl = (result as any).xai as { patient_id: string; top_genes: { gene: string; attribution: number }[] }[] | undefined;
                  const h = Array.isArray(xl) ? xl.find((x) => x.patient_id === p.patient_id) : undefined;
                  if (!h || !h.top_genes?.length) return null;
                  return (
                    <Text style={styles.xaiSatiri} numberOfLines={2}>
                      🔍 Sürükleyen genler: {h.top_genes.slice(0, 5).map((g) => `${g.gene} ${g.attribution >= 0 ? "↑" : "↓"}`).join("  ·  ")}
                    </Text>
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
  { k: "age", label: "Yaş" }, { k: "bp", label: "Tansiyon (mmHg)" },
  { k: "sg", label: "İdrar öz.ağ." }, { k: "al", label: "Albümin (0-5)" },
  { k: "su", label: "Şeker (0-5)" }, { k: "bgr", label: "Kan şekeri (mg/dL)" },
  { k: "bu", label: "Üre (mg/dL)" }, { k: "sc", label: "Kreatinin (mg/dL)" },
  { k: "sod", label: "Sodyum (mEq/L)" }, { k: "pot", label: "Potasyum (mEq/L)" },
  { k: "hemo", label: "Hemoglobin (g/dL)" }, { k: "pcv", label: "Hematokrit (%)" },
  { k: "wc", label: "Beyaz küre (/µL)" }, { k: "rc", label: "Kırmızı küre (mil/µL)" },
];
// Sunum-katmanı XAI (2026-08-26): SHAP özellik kodu → mevcut form etiketleri (tek kaynak).
// Not: harita CKD_CATEGORICAL tanımından SONRA doldurulur (aşağıda).
const CKD_XAI_ETIKET: Record<string, string> = {};

const CKD_CATEGORICAL: { k: string; label: string; opts: [string, string][] }[] = [
  { k: "rbc", label: "Kırmızı küre", opts: [["normal", "Normal"], ["abnormal", "Anormal"]] },
  { k: "pc", label: "Pus hücresi", opts: [["normal", "Normal"], ["abnormal", "Anormal"]] },
  { k: "pcc", label: "Pus hücre kümesi", opts: [["notpresent", "Yok"], ["present", "Var"]] },
  { k: "ba", label: "Bakteri", opts: [["notpresent", "Yok"], ["present", "Var"]] },
  { k: "htn", label: "Hipertansiyon", opts: [["no", "Hayır"], ["yes", "Evet"]] },
  { k: "dm", label: "Diyabet", opts: [["no", "Hayır"], ["yes", "Evet"]] },
  { k: "cad", label: "Koroner arter hast.", opts: [["no", "Hayır"], ["yes", "Evet"]] },
  { k: "appet", label: "İştah", opts: [["good", "İyi"], ["poor", "Kötü"]] },
  { k: "pe", label: "Ödem (pedal)", opts: [["no", "Hayır"], ["yes", "Evet"]] },
  { k: "ane", label: "Anemi", opts: [["no", "Hayır"], ["yes", "Evet"]] },
];
// XAI etiket haritasını MEVCUT form etiketlerinden doldur (ikinci bir kopya tutma).
for (const { k, label } of [...CKD_NUMERIC, ...CKD_CATEGORICAL]) CKD_XAI_ETIKET[k] = label;

/**
 * Böbrek Hastalığı Analizi (UCI-CKD) — 24 klinik değerden kronik böbrek hastalığı tahmini.
 * Foto/CSV DEĞİL — FORM girişi (kedi DiseaseModule deseni). Eksik alanlar backend'de impute
 * edilir. Backend: POST /api/ai/disease/kidney (ExtraTrees ONNX, EXE'ye gömülü).
 */
function KidneyDiseaseModule({ patientName }: { patientName: string }) {
  const { showToast } = useToast();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AiResult | null>(moduleCache.kidney_disease?.result ?? null);
  const [num, setNum] = useState<Record<string, string>>(moduleCache.kidney_disease?.num ?? {});
  const [cat, setCat] = useState<Record<string, string | undefined>>(moduleCache.kidney_disease?.cat ?? {});
  useEffect(() => { moduleCache.kidney_disease = { result, num, cat }; }, [result, num, cat]);

  const analyze = async () => {
    setLoading(true);
    setResult(null);
    try {
      const payload: any = {};
      CKD_NUMERIC.forEach(({ k }) => {
        const v = parseFloat((num[k] || "").replace(",", "."));
        if (!isNaN(v)) payload[k] = v;
      });
      CKD_CATEGORICAL.forEach(({ k }) => { if (cat[k]) payload[k] = cat[k]; });
      // Sunum-katmanı XAI (2026-08-26): SHAP top-özellikler — hata/eski-backend'de alan
      // gelmez, satır gizlenir (backend zarif düşüşü).
      payload.explain = true;
      const res = await apiPost<any>("/ai/disease/kidney", payload, null, { timeoutMs: AI_TIMEOUT_MS });
      if (res && res.status === "success") {
        setResult(res);
        logAiResult(patientName, "Böbrek Hastalığı (CKD)", `${trValue(res.label)} %${res.prob_pct}`, { moduleId: "kidney_disease", inputType: "clinical", detail: res, confidence: res.prob_pct != null ? res.prob_pct / 100 : undefined });
      } else {
        showToast("Analiz sırasında hata oluştu.", "error");
      }
    } catch (e) {
      showToast(aiHataMesaji(e), "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card style={styles.card}>
      <Text style={styles.title}>Böbrek Hastalığı Analizi (CKD)</Text>
      <Text style={styles.subtitle}>Klinik değerlerden kronik böbrek hastalığı (CKD) tahmini. Bilinmeyen alanları boş bırakabilirsiniz — otomatik tamamlanır (ama ne kadar çok değer, o kadar isabetli).</Text>

      <Text style={styles.ckdSection}>Laboratuvar / Vital</Text>
      <View style={styles.ckdGrid}>
        {CKD_NUMERIC.map(({ k, label }) => (
          <View key={k} style={styles.ckdNumCell}>
            <Text style={styles.ckdNumLabel} numberOfLines={1}>{label}</Text>
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

      <Text style={styles.ckdSection}>Bulgular</Text>
      {CKD_CATEGORICAL.map(({ k, label, opts }) => (
        <View key={k} style={styles.ckdCatRow}>
          <Text style={styles.ckdCatLabel} numberOfLines={1}>{label}</Text>
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
                  <Text style={[styles.ckdCatBtnText, active && { color: colors.white }]}>{lbl}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>
      ))}

      <View style={styles.analyzeBtn}>
        <Button variant="primary" label={loading ? "Analiz Ediliyor..." : "CKD Analizini Başlat"} icon={loading ? <ActivityIndicator color={colors.white} /> : <Sparkles color={colors.white} size={16} />} disabled={loading} onPress={analyze} />
      </View>

      {result && (
        <View style={styles.resultBox}>
          {(() => {
            const isCkd = result.label === "ckd";
            const pct = result.prob_pct;
            return (
              <>
                <ResultInterpretation tone={isCkd ? "critical" : "positive"} emoji={isCkd ? "🩺" : "✅"}
                  title={isCkd ? `Kronik Böbrek Hastalığı olası · %${pct}` : `Sağlıklı görünüyor · %${pct} CKD olasılığı`}
                  text={isCkd
                    ? `Girilen klinik değerlere göre model %${pct} olasılıkla kronik böbrek hastalığına (CKD) işaret ediyor. CKD'de erken tanı çok önemlidir; bu sonucu kan/idrar tahlilleri ve veteriner hekim değerlendirmesiyle doğrulayın.`
                    : `Girilen değerlere göre CKD olasılığı düşük (%${pct}). Yine de şüphe varsa periyodik kontrol ve hekim değerlendirmesi önerilir.`}
                  points={["Sonuç girilen 24 klinik değere dayanır; boş alanlar tahmin edilir (impute).", "Bu bir tarama tahminidir, kesin tanı değildir."]} />
                <Text style={[styles.resultText, { fontSize: typography.small, color: colors.textMuted }]}>Model: {result.model}</Text>
                <XaiSatiri
                  xai={result.xai ?? null}
                  etiketle={(f) => CKD_XAI_ETIKET[f] ?? f}
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

const CATSOUND_TR: Record<string, string> = {
  Angry: "Kızgın", Defence: "Savunma", Fighting: "Kavga", Happy: "Mutlu",
  HuntingMind: "Av modu", Mating: "Çiftleşme", MotherCall: "Anne çağrısı",
  Paining: "Ağrı", Resting: "Dinlenme", Warning: "Uyarı",
};

/**
 * Kedi Sesi Analizi — miyavdan 10 sınıf duygu/durum (Angry..Warning). Foto/CSV/form DEĞİL — SES.
 * Mikrofonla kaydet (expo-av) VEYA ses dosyası yükle (expo-document-picker). Backend:
 * POST /api/ai/sound/cat (ffmpeg→WAV→librosa mel→EfficientNet_Lite0 ONNX).
 */
function CatSoundModule({ patientName }: { patientName: string }) {
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
      if (!perm.granted) { showToast("Mikrofon izni gerekli.", "error"); return; }
      await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
      setIsRecording(true); setResult(null); setAudioUri(null); setWebFile(null);
    } catch (e) {
      showToast("Kayıt başlatılamadı (mikrofon?).", "error");
    }
  };

  const stopRecording = async () => {
    setIsRecording(false);
    try {
      await recorder.stop();
      const uri = recorder.uri;
      setAudioUri(uri || null); setFileName("kayıt.m4a");
    } catch (e) {
      showToast("Kayıt durdurulamadı.", "error");
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
        logAiResult(patientName, "Kedi Sesi", `${trValue(data.top_1_class)} %${Math.round((data.top_1_prob ?? 0) * 100)}`, { moduleId: "cat_sound", inputType: "audio", detail: data, confidence: data.top_1_prob });
      } else {
        showToast(data?.detail || "Analiz sırasında hata oluştu.", "error");
      }
    } catch (e) {
      showToast(aiHataMesaji(e, "Hata: " + errorMessage(e).slice(0, 120)), "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card style={styles.card}>
      <Text style={styles.title}>Kedi Sesi Analizi</Text>
      <Text style={styles.subtitle}>Kedi miyavından duygu/durum sınıflandırması (10 sınıf). Mikrofonla kaydet ya da ses dosyası yükle.</Text>

      <View style={styles.photoGuide}>
        <Text style={styles.photoGuideTitle}>🎙️ İpuçları</Text>
        <Text style={styles.photoGuideItem}>• Kediye yakın, sessiz ortamda <Text style={styles.photoGuideBold}>~5 saniye</Text> kaydet</Text>
        <Text style={styles.photoGuideItem}>• Tek miyav/ses net olsun (arka plan gürültüsü az)</Text>
        <Text style={styles.photoGuideItem}>• Hazır ses dosyası (mp3/wav/m4a) da yükleyebilirsin</Text>
      </View>

      <View style={styles.soundStatusBox}>
        {isRecording ? (
          <View style={{ alignItems: "center" }}>
            <View style={styles.recDot} />
            <Text style={styles.recText}>Kaydediliyor…</Text>
          </View>
        ) : audioUri ? (
          <View style={{ alignItems: "center" }}>
            <AudioLines color={colors.primary} size={40} />
            <Text style={styles.soundFileName} numberOfLines={1}>🎵 {fileName}</Text>
          </View>
        ) : (
          <View style={{ alignItems: "center" }}>
            <Mic color={colors.textMuted} size={40} />
            <Text style={styles.placeholderText}>Ses seçilmedi</Text>
          </View>
        )}
      </View>

      <View style={styles.btnRow}>
        <View style={{ flex: 1 }}>
          <Button
            label={isRecording ? "Durdur" : "Kaydet"}
            variant={isRecording ? "danger" : "primary"}
            icon={isRecording ? <Square color={colors.white} size={16} /> : <Mic color={colors.white} size={16} />}
            onPress={isRecording ? stopRecording : startRecording}
          />
        </View>
        <View style={{ flex: 1 }}>
          <Button label="Ses Yükle" variant="secondary" icon={<FileText color={colors.primary} size={16} />} onPress={pickAudio} disabled={isRecording} />
        </View>
      </View>

      <TouchableOpacity
        style={styles.xaiToggle}
        onPress={() => setIsiHaritasi((v) => !v)}
        accessibilityRole="switch"
        accessibilityState={{ checked: isiHaritasi }}
        accessibilityLabel="Mel ısı haritası üret (Grad-CAM)"
      >
        <Text style={styles.xaiToggleText}>
          {isiHaritasi ? "☑" : "☐"} 🔍 Isı haritası üret (modelin dinlediği frekans/zaman bandı — analiz biraz uzar)
        </Text>
      </TouchableOpacity>
      <View style={styles.analyzeBtn}>
        <Button variant="primary" label={loading ? "Analiz Ediliyor..." : "Ses Analizini Başlat"} icon={loading ? <ActivityIndicator color={colors.white} /> : <Sparkles color={colors.white} size={16} />} disabled={!audioUri || loading || isRecording} onPress={analyze} />
      </View>
      {longLoading && <Text style={styles.modelHint}>Model hazırlanıyor (ilk kullanım uzun sürebilir)…</Text>}

      {result && (
        <View style={styles.resultBox}>
          {(() => {
            const tc = result.top_1_class ?? "";
            const a = CAT_SOUND_ADVICE[tc];
            const tone: InterpTone = a ? (a.tone === "positive" ? "positive" : a.tone === "pain" ? "critical" : a.tone === "alert" ? "alert" : "info") : "info";
            const pct = Math.round((result.top_1_prob || 0) * 100);
            return <ResultInterpretation tone={tone} emoji={a?.emoji || "🐈"}
              title={`${a?.title || CATSOUND_TR[tc] || tc} · %${pct}`}
              text={a?.text || "Ses analiz edildi."}
              points={["Aşağıda modelin en olası 3 durumu güvene göre sıralı."]} />;
          })()}
          <Text style={styles.ctSubLabel}>En olası 3 durum</Text>
          <View style={{ marginTop: 2 }}>
            {(result.top_k || []).map((t: AiTopK, i: number) => {
              const pct = Math.round(t.prob * 100);
              return (
                <View key={i} style={styles.soundBarRow}>
                  <Text style={styles.soundBarLabel} numberOfLines={1}>{i + 1}. {CATSOUND_TR[t.class] || t.class}</Text>
                  <View style={styles.soundBarTrack}>
                    <View style={[styles.soundBarFill, { width: (`${Math.max(2, pct)}%` as any) }]} />
                  </View>
                  <Text style={styles.soundBarPct}>%{pct}</Text>
                </View>
              );
            })}
          </View>
          {/* Sunum-katmanı XAI (Faz 2): mel-spektrogram ısı haritası — istenip üretildiyse. */}
          {result.xai_image_base64 && (
            <>
              <Text style={styles.ctSubLabel}>🔍 Mel ısı haritası — modelin dinlediği bölgeler (kırmızı = karara güçlü etki)</Text>
              <Image source={{ uri: `data:image/jpeg;base64,${result.xai_image_base64}` }} style={styles.imagePreview} resizeMode="contain" />
            </>
          )}
          {result.xai_error && <Text style={styles.xaiSatiri}>🔍 {result.xai_error}</Text>}
          <MedicalDisclaimer />
        </View>
      )}
    </Card>
  );
}

const CT_TR: Record<string, string> = { "Kidney Stone": "Böbrek Taşı", "Kidney": "Böbrek", "Kidney Cyst": "Böbrek Kisti" };

/**
 * Böbrek CT Analizi — CT görüntüsünde YOLOv8s ile taş/böbrek/kist tespiti (3 sınıf).
 * Backend: POST /api/ai/vision/kidney_ct → annotated görsel + sınıf sayıları + tespit listesi.
 */
function KidneyCTModule({ patientName }: { patientName: string }) {
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
        if (file) { if (imageUri && imageUri.startsWith('blob:')) URL.revokeObjectURL(imageUri); setImageFile(file); setImageUri(URL.createObjectURL(file)); setImageBase64(null); setResult(null); }
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
        if (file) { if (imageUri && imageUri.startsWith('blob:')) URL.revokeObjectURL(imageUri); setImageFile(file); setImageUri(URL.createObjectURL(file)); setImageBase64(null); setResult(null); }
      };
      input.click();
    } else {
      const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, allowsEditing: false, quality: 0.8, base64: true });
      if (!res.canceled) { const shrunk = await shrinkForUpload(res.assets[0].uri); setImageUri(shrunk.uri); setImageBase64(shrunk.base64); setImageFile((res.assets[0] as any).file || null); setResult(null); }
    }
  };

  const analyze = async () => {
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
        logAiResult(patientName, "Böbrek CT", `${data.n_detections} tespit (taş:${c["Kidney Stone"] ?? 0} kist:${c["Kidney Cyst"] ?? 0})`, { moduleId: "kidney_ct", inputType: "image", detail: data });
      } else {
        showToast(data?.detail || "Analiz sırasında hata oluştu.", "error");
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
  if (nKidney) parts.push(`${nKidney} böbrek dokusu`);
  if (nCyst) parts.push(`${nCyst} kist`);
  if (nStone) parts.push(`${nStone} taş`);
  const summary = parts.length ? `Görüntüde ${parts.join(", ")} tespit edildi.` : "Görüntüde böbrek yapısı tespit edilemedi.";
  // Aynı sınıftan birden çok tespiti görüntüdeki yatay konuma göre ayırt et (kullanıcı hangi böbrek olduğunu görsün)
  const byClass: Record<string, any[]> = {};
  dets.forEach((d: AiDetection) => { (byClass[d.class_name] = byClass[d.class_name] || []).push(d); });
  const cx = (d: AiDetection) => (((d.bbox_xyxy?.[0] ?? 0) + (d.bbox_xyxy?.[2] ?? 0)) / 2);
  const posLabel = (d: AiDetection) => {
    const g = byClass[d.class_name] || [];
    if (g.length < 2) return "";
    const sorted = [...g].sort((a, b) => cx(a) - cx(b));
    const idx = sorted.indexOf(d);
    if (g.length === 2) return idx === 0 ? " (görüntüde solda)" : " (görüntüde sağda)";
    return ` (soldan ${idx + 1}.)`;
  };
  return (
    <Card style={styles.card}>
      <Text style={styles.title}>Böbrek CT Analizi</Text>
      <Text style={styles.subtitle}>Böbrek CT görüntüsünde taş, kist ve böbrek dokusu tespiti (YOLOv8s).</Text>

      {!imageUri && (
        <View style={styles.photoGuide}>
          <Text style={styles.photoGuideTitle}>🩻 CT görüntü ipuçları</Text>
          <Text style={styles.photoGuideItem}>• Net, tek kesitli bir böbrek CT görüntüsü seçin/çekin</Text>
          <Text style={styles.photoGuideItem}>• Kırmızı=taş, yeşil=böbrek, turuncu=kist olarak işaretlenir</Text>
        </View>
      )}

      <View style={styles.imagePreviewContainer}>
        {imageUri ? (
          <Image source={{ uri: result?.image_base64 ? `data:image/jpeg;base64,${result.image_base64}` : imageUri }} style={styles.imagePreview} resizeMode="contain" />
        ) : (
          <View style={styles.placeholderBox}><ImageIcon color={colors.textMuted} size={48} /><Text style={styles.placeholderText}>Görüntü seçilmedi</Text></View>
        )}
      </View>

      <View style={styles.btnRow}>
        <View style={{ flex: 1 }}><Button label="Galeriden Seç" icon={<ImageIcon color={colors.white} size={16} />} onPress={pickImage} /></View>
      </View>

      <TouchableOpacity style={styles.xaiToggle} accessibilityRole="switch" accessibilityState={{ checked: isiHaritasi }} onPress={() => setIsiHaritasi(!isiHaritasi)}>
        <Text style={styles.xaiToggleText}>{isiHaritasi ? "☑" : "☐"} 🔍 Isı haritası üret (EigenCAM — modelin baktığı bölgeler)</Text>
      </TouchableOpacity>

      <View style={styles.analyzeBtn}>
        <Button variant="primary" label={loading ? "Analiz Ediliyor..." : "CT Analizini Başlat"} icon={loading ? <ActivityIndicator color={colors.white} /> : <Sparkles color={colors.white} size={16} />} disabled={!imageUri || loading} onPress={analyze} />
      </View>
      {longLoading && <Text style={styles.modelHint}>Model hazırlanıyor (ilk kullanım uzun sürebilir)…</Text>}

      {result && (
        <View style={styles.resultBox}>
          <Text style={styles.resultTitle}>Analiz Sonucu</Text>

          {/* Özet cümle */}
          <Text style={[styles.resultText, { marginBottom: 6 }]}>{summary}</Text>

          {/* Bulgu vurgusu */}
          {(nStone > 0 || nCyst > 0) ? (
            <View style={[styles.ctFindingChip, { backgroundColor: nStone > 0 ? colors.danger + "22" : colors.warning + "22", borderColor: nStone > 0 ? colors.danger : colors.warning }]}>
              <Text style={[styles.resultText, { fontWeight: "800", color: nStone > 0 ? colors.danger : colors.warning }]}>
                ⚠ {[nStone > 0 ? `${nStone} böbrek taşı` : "", nCyst > 0 ? `${nCyst} kist` : ""].filter(Boolean).join(" + ")} bulgusu
              </Text>
            </View>
          ) : (
            <View style={[styles.ctFindingChip, { backgroundColor: colors.success + "22", borderColor: colors.success }]}>
              <Text style={[styles.resultText, { fontWeight: "800", color: colors.success }]}>✓ Taş veya kist bulgusu yok</Text>
            </View>
          )}

          {/* Tespit sayıları */}
          <Text style={styles.ctSubLabel}>Tespit sayıları</Text>
          <Text style={styles.resultText}>Böbrek Taşı: <Text style={{ fontWeight: "bold", color: nStone > 0 ? colors.danger : colors.textMuted }}>{nStone}</Text></Text>
          <Text style={styles.resultText}>Böbrek Kisti: <Text style={{ fontWeight: "bold", color: nCyst > 0 ? colors.warning : colors.textMuted }}>{nCyst}</Text></Text>
          <Text style={styles.resultText}>Böbrek (doku): <Text style={{ fontWeight: "bold", color: nKidney > 0 ? colors.success : colors.textMuted }}>{nKidney}</Text></Text>

          {/* Tespit detayları — numaralı + konumlu + güven açıklamalı */}
          {dets.length > 0 && (
            <>
              <Text style={styles.ctSubLabel}>Tespit detayları</Text>
              {dets.map((d: AiDetection, i: number) => (
                <Text key={i} style={[styles.resultText, { fontSize: typography.small }]}>
                  {i + 1}. {CT_TR[d.class_name] || d.class_name}
                  <Text style={{ color: colors.textMuted }}>{posLabel(d)}</Text>
                  {" — güven "}
                  <Text style={{ fontWeight: "bold" }}>%{Math.round((d.conf || 0) * 100)}</Text>
                </Text>
              ))}
              <Text style={styles.ctHint}>“Güven”, modelin o bölgeyi doğru tanıma olasılığıdır. İki böbrek dokusunun güveni farklı olabilir (ör. %89 ve %87) — bunlar aynı böbreğin iki ölçümü değil, görüntüdeki iki ayrı böbrek bölgesidir.</Text>
            </>
          )}
          {result.xai_image_base64 ? (
            <>
              <Text style={styles.ctSubLabel}>🔍 Isı haritası (EigenCAM)</Text>
              <Image source={{ uri: `data:image/jpeg;base64,${result.xai_image_base64}` }} style={styles.scStage} resizeMode="contain" />
              <Text style={styles.ctHint}>Kırmızı bölgeler modelin tespitte en çok dayandığı alanlardır (bölgesel ilgi — tanı kanıtı değildir).</Text>
            </>
          ) : null}
          {result.xai_error ? <Text style={styles.xaiSatiri}>🔍 {result.xai_error}</Text> : null}
          <MedicalDisclaimer />
        </View>
      )}
    </Card>
  );
}

const HISTO_TR: Record<string, string> = { grade0: "Grade 0 (en hafif)", grade1: "Grade 1", grade2: "Grade 2", grade3: "Grade 3", grade4: "Grade 4 (en ileri)" };
const HISTO_COLOR: Record<string, string> = { grade0: colors.success, grade1: "#84CC16", grade2: colors.warning, grade3: "#F97316", grade4: colors.danger };

/**
 * Böbrek Histopatoloji Analizi — doku (biyopsi) görüntüsünde V22-KMC-ClassicTrio ensemble ile
 * grade0–grade4 derece sınıflandırması. Backend: POST /api/ai/vision/histopath → grade + top-k +
 * olasılıklar (sınıflandırıcı, detektör değil → overlay yok, orijinal görüntü gösterilir).
 */
function HistopathModule({ patientName }: { patientName: string }) {
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
        if (file) { if (imageUri && imageUri.startsWith('blob:')) URL.revokeObjectURL(imageUri); setImageFile(file); setImageUri(URL.createObjectURL(file)); setImageBase64(null); setResult(null); }
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
        if (file) { if (imageUri && imageUri.startsWith('blob:')) URL.revokeObjectURL(imageUri); setImageFile(file); setImageUri(URL.createObjectURL(file)); setImageBase64(null); setResult(null); }
      };
      input.click();
    } else {
      const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, allowsEditing: false, quality: 0.8, base64: true });
      if (!res.canceled) { const shrunk = await shrinkForUpload(res.assets[0].uri); setImageUri(shrunk.uri); setImageBase64(shrunk.base64); setImageFile((res.assets[0] as any).file || null); setResult(null); }
    }
  };

  const analyze = async () => {
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
        logAiResult(patientName, "Böbrek Patoloji", `${trValue(data.top_1_class)} %${Math.round((data.top_1_prob || 0) * 100)}`, { moduleId: "histopath", inputType: "image", detail: data, confidence: data.top_1_prob });
      } else {
        showToast(data?.detail || "Analiz sırasında hata oluştu.", "error");
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
      <Text style={styles.title}>Böbrek Histopatoloji Analizi</Text>
      <Text style={styles.subtitle}>Böbrek doku (biyopsi) görüntüsünde derece sınıflandırması: Grade 0–4 (V22-KMC-ClassicTrio).</Text>

      {!imageUri && (
        <View style={styles.photoGuide}>
          <Text style={styles.photoGuideTitle}>🔬 Doku görüntü ipuçları</Text>
          <Text style={styles.photoGuideItem}>• Net, tek kesitli bir histopatoloji (mikroskop) görüntüsü seçin</Text>
          <Text style={styles.photoGuideItem}>• Grade 0 = en hafif, Grade 4 = en ileri histopatolojik derece</Text>
        </View>
      )}

      <View style={styles.imagePreviewContainer}>
        {imageUri ? (
          <Image source={{ uri: imageUri }} style={styles.imagePreview} resizeMode="contain" />
        ) : (
          <View style={styles.placeholderBox}><ImageIcon color={colors.textMuted} size={48} /><Text style={styles.placeholderText}>Görüntü seçilmedi</Text></View>
        )}
      </View>

      <View style={styles.btnRow}>
        <View style={{ flex: 1 }}><Button label="Galeriden Seç" icon={<ImageIcon color={colors.white} size={16} />} onPress={pickImage} /></View>
      </View>

      <TouchableOpacity style={styles.xaiToggle} accessibilityRole="switch" accessibilityState={{ checked: isiHaritasi }} onPress={() => setIsiHaritasi(!isiHaritasi)}>
        <Text style={styles.xaiToggleText}>{isiHaritasi ? "☑" : "☐"} {"🔍 Isı haritası üret (3-model konsensus + kararsızlık — CPU'da dakikalar sürebilir)"}</Text>
      </TouchableOpacity>

      <View style={styles.analyzeBtn}>
        <Button variant="primary" label={loading ? "Analiz Ediliyor..." : "Patoloji Analizini Başlat"} icon={loading ? <ActivityIndicator color={colors.white} /> : <Sparkles color={colors.white} size={16} />} disabled={!imageUri || loading} onPress={analyze} />
      </View>
      {longLoading && <Text style={styles.modelHint}>Model hazırlanıyor (büyük model, ilk kullanım uzun sürebilir)…</Text>}

      {result && (
        <View style={styles.resultBox}>
          <Text style={styles.resultTitle}>Analiz Sonucu</Text>
          <View style={[styles.ctFindingChip, { backgroundColor: (HISTO_COLOR[topClass] || colors.text) + "22", borderColor: HISTO_COLOR[topClass] || colors.text }]}>
            <Text style={[styles.resultText, { fontWeight: "800", color: HISTO_COLOR[topClass] || colors.text }]}>
              Tahmin: {HISTO_TR[topClass] || topClass}  ·  güven %{Math.round((result.top_1_prob || 0) * 100)}
            </Text>
          </View>

          <Text style={styles.ctSubLabel}>Tüm dereceler</Text>
          {(result.top_k || []).map((t: AiTopK, i: number) => {
            const pct = Math.round((t.prob || 0) * 100);
            return (
              <View key={i} style={styles.soundBarRow}>
                <Text style={styles.soundBarLabel} numberOfLines={1}>{String(t.class).replace("grade", "Grade ")}</Text>
                <View style={styles.soundBarTrack}>
                  <View style={[styles.soundBarFill, { width: (`${Math.max(2, pct)}%` as any), backgroundColor: HISTO_COLOR[t.class] || colors.primary }]} />
                </View>
                <Text style={styles.soundBarPct}>%{pct}</Text>
              </View>
            );
          })}
          <Text style={styles.ctHint}>“Güven”, modelin görüntüyü o dereceye atama olasılığıdır. Grade 0 en hafif, Grade 4 en ileri histopatolojik derecedir; komşu dereceler (ör. 2↔3) benzer görünebilir.</Text>
          {result.xai_image_base64 ? (
            <>
              <Text style={styles.ctSubLabel}>🔍 Konsensus ısı haritası (3-model HiRes-CAM)</Text>
              <Image source={{ uri: `data:image/jpeg;base64,${result.xai_image_base64}` }} style={styles.scStage} resizeMode="contain" />
              <Text style={styles.ctHint}>Üç modelin ORTAK dayandığı doku bölgeleri.</Text>
            </>
          ) : null}
          {result.xai_disagreement_base64 ? (
            <>
              <Text style={styles.ctSubLabel}>⚠ Model kararsızlık haritası</Text>
              <Image source={{ uri: `data:image/jpeg;base64,${result.xai_disagreement_base64}` }} style={styles.scStage} resizeMode="contain" />
              <Text style={styles.ctHint}>Parlak bölgelerde üç model AYRIŞIYOR — derece o bölgede daha az güvenilirdir.</Text>
            </>
          ) : null}
          {result.xai_error ? <Text style={styles.xaiSatiri}>🔍 {result.xai_error}</Text> : null}
          <MedicalDisclaimer />
        </View>
      )}
    </Card>
  );
}

const ORGAN_TR: Record<string, string> = {
  mide: "Mide", bobrek: "Böbrek", karaciger: "Karaciğer", mesane: "Mesane", pankreas: "Pankreas",
  bagirsak: "Bağırsak", kalp: "Kalp", dalak: "Dalak", akciger_sag: "Akciğer (sağ)", akciger_sol: "Akciğer (sol)",
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
  { k: "closure", ad: "Kapanma", alan: "closure_image_base64", not: "Sarı bant = scratch ROI · kırmızı = maks gap · mavi = ort. gap" },
  { k: "analysis", ad: "Analiz", alan: "analysis_image_base64", not: "Kırmızı çizgiler = yaraya dik ROI kuşağı · sarı = kuşağa en yakın hücreler" },
  { k: "seg", ad: "Segmentasyon", alan: "seg_image_base64", not: "Her hücre ayrı renk (CPN instance)" },
  { k: "overlay", ad: "Overlay", alan: "overlay_image_base64", not: "Segmentasyon + orijinal karışımı" },
  { k: "input", ad: "Orijinal", alan: "input_image_base64", not: "Orijinal görüntü (sunucu JPEG önizlemesi — TIF tarayıcıda gösterilemez)" },
  { k: "xai", ad: "XAI", alan: "xai_image_base64", not: "EigenCAM — bölgesel model ilgisi (hücre-düzeyi açıklama DEĞİLDİR)" },
  { k: "panel", ad: "3'lü panel", alan: "xai_side_by_side_base64", not: "Orijinal | ısı haritası | overlay" },
];
type ScratchKayit = { etiket: string; closure_pct: number; mean_gap_um: number };

function ScratchModule({ patientName }: { patientName: string }) {
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
  const abortRef = useRef<AbortController | null>(null);
  // DÜŞMAN-DOĞRULAMA: 300sn'lik pencerede kullanıcı yeni dosya/parametre seçebilir;
  // ESKİ isteğin yanıtı gelirse sessizce yeni girdinin sonucu sanılırdı → istek-kimliği.
  const istekRef = useRef(0);
  const { showToast } = useToast();
  useEffect(() => () => { mountedRef.current = false; abortRef.current?.abort(); }, []);
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

  const analiz = async () => {
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
        // OKUYAMIYOR ("Ağ hatası") → base64 okuyup image_base64 gönderilir; router'ın
        // _allow_large_upload kapısı base64 form-part'ı 50MB'a açar (shrink YOK —
        // µm ölçümü bozulmaz; 20MB TIF base64 ~27MB sınıra sığar).
        const b64 = await FileSystemLegacy.readAsStringAsync(dosya.uri!, { encoding: "base64" });
        fd.append("image_base64", b64);
      }
      fd.append("scratch_yonu", yon);
      fd.append("pixel_mm", pmm);
      if (xaiAc) fd.append("explain", "true");
      const ctrl = new AbortController(); abortRef.current = ctrl;
      const to = setTimeout(() => ctrl.abort(), SCRATCH_TIMEOUT_MS);
      const r = await fetch(serviceConfig.apiBaseUrl + "/ai/vision/scratch", {
        method: "POST", body: fd,
        headers: { Accept: "application/json", ...authHeaders() }, signal: ctrl.signal,
      });
      clearTimeout(to);
      const data = await r.json();
      if (!mountedRef.current) return;
      if (istekRef.current !== benimIstek) return; // stale yanıt: girdi/parametre değişti
      if (r.ok && data.status === "success") {
        setResult(data); setYenidenGerek(false);
        setGaleri(data.uyari ? "input" : "closure");
        if (!data.uyari && data.closure) {
          const etiket = dosya.name.replace(/\.[^.]+$/, "");
          // Aynı etiketin tekrar analizi (örn. objektif düzeltmesi) yeni kayıt AÇMAZ,
          // mevcut kaydı günceller — Δ kartı aynı görüntüyü kendisiyle kıyaslamasın.
          setKayitlar((k) => [...k.filter((x) => x.etiket !== etiket).slice(-7), {
            etiket, closure_pct: data.closure.closure_pct, mean_gap_um: data.closure.mean_gap_um,
          }]);
        }
        logAiResult(patientName, "Yara Kapanma (Scratch)",
          data.uyari ? "Hücre tespit edilemedi" : `Kapanma %${data.closure?.closure_pct ?? "?"} · ${data.n_cells} hücre`,
          { moduleId: "cell_scratch", inputType: "image", detail: data });
      } else showToast(data?.detail || data?.error || "Analiz sırasında hata oluştu.", "error");
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
      <Text style={styles.title}>Yara Kapanma (Scratch)</Text>
      <Text style={styles.subtitle}>CPN hücre segmentasyonu + TScratch kapanma metrikleri (araştırma verisi — hasta kaydı değildir).</Text>

      <TouchableOpacity style={styles.scFileBtn} onPress={dosyaSec} accessibilityRole="button">
        <FileText size={16} color={colors.textMuted} />
        <Text style={styles.scFileText} numberOfLines={1}>
          {dosya ? dosya.name : "Görüntü seç (.tif / .png / .jpg)"}
        </Text>
      </TouchableOpacity>
      {dosya && /\.tiff?$/i.test(dosya.name) && !result && (
        <Text style={styles.ctHint}>TIF önizlemesi desteklenmez — analiz sonrası [Orijinal] sekmesini kullanın.</Text>
      )}

      <Text style={styles.ctSubLabel}>Yara yönü</Text>
      <View style={styles.scChipRow} accessibilityRole="radiogroup">
        {(["dikey", "yatay"] as const).map((v) => (
          <TouchableOpacity key={v} accessibilityRole="radio" accessibilityState={{ selected: yon === v }}
            style={[styles.scChip, yon === v && styles.scChipOn]}
            onPress={() => { setYon(v); parametreDegisti(); }}>
            <Text style={[styles.scChipText, yon === v && styles.scChipTextOn]}>{v === "dikey" ? "Dikey" : "Yatay"}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <Text style={styles.ctSubLabel}>Objektif (kalibrasyon)</Text>
      <View style={styles.scChipRow} accessibilityRole="radiogroup">
        {SCRATCH_OBJEKTIFLER.map((o) => (
          <TouchableOpacity key={o.ad} accessibilityRole="radio" accessibilityState={{ selected: pmm === o.pmm }}
            style={[styles.scChip, pmm === o.pmm && styles.scChipOn]}
            onPress={() => { setPmm(o.pmm); parametreDegisti(); }}>
            <Text style={[styles.scChipText, pmm === o.pmm && styles.scChipTextOn]}>{o.ad}</Text>
          </TouchableOpacity>
        ))}
      </View>
      <Text style={styles.ctHint}>pixel_mm = {pmm} mm/px — çekimde kullanılan objektifi seçin (µm/mm² doğruluğu buna bağlı).</Text>

      <TouchableOpacity style={styles.xaiToggle} accessibilityRole="switch" accessibilityState={{ checked: xaiAc }}
        onPress={() => { setXaiAc(!xaiAc); parametreDegisti(); }}>
        <Text style={styles.xaiToggleText}>{xaiAc ? "☑" : "☐"} 🔍 Isı haritası üret (bölgesel model ilgisi — hücre-düzeyi değildir)</Text>
      </TouchableOpacity>

      <Button label={loading ? "Analiz ediliyor…" : "Analiz Et"} onPress={analiz} disabled={!dosya || loading} loading={loading} block />
      {loading && longLoading && (
        <Text style={styles.modelHint}>Büyük model hazırlanıyor — ilk çalıştırma dakikalar sürebilir…</Text>
      )}
      {yenidenGerek && !loading && (
        <Text style={styles.modelHint}>⚠ Parametre değişti — sonuçlar eski ayarlara ait. Yeniden analiz edin.</Text>
      )}

      {result && (
        <View style={styles.resultBox}>
          {result.uyari ? (
            <Text style={styles.scUyari}>⚠ {result.uyari}</Text>
          ) : (
            <>
              <View style={styles.scMetricRow}>
                <View style={[styles.scMetricBox, styles.scMetricHero]}>
                  <Text style={[styles.scMetricVal, { color: colors.primary }]}>%{result.closure?.closure_pct}</Text>
                  <Text style={styles.scMetricLbl}>Kapanma</Text>
                </View>
                <View style={styles.scMetricBox}>
                  <Text style={styles.scMetricVal}>{result.closure?.mean_gap_um} µm</Text>
                  <Text style={styles.scMetricLbl}>Ort. gap</Text>
                </View>
                <View style={styles.scMetricBox}>
                  <Text style={styles.scMetricVal}>{result.closure?.max_gap_um} µm</Text>
                  <Text style={styles.scMetricLbl}>Maks gap</Text>
                </View>
                <View style={styles.scMetricBox}>
                  <Text style={styles.scMetricVal}>{result.n_cells}</Text>
                  <Text style={styles.scMetricLbl}>Hücre</Text>
                </View>
              </View>
              <Text style={styles.ctHint}>
                Gap alanı {result.closure?.gap_area_mm2} mm² · coverage {result.coverage_ratio} · skor {result.score_mean} · cihaz: {result.device}
              </Text>
            </>
          )}

          {aktifGaleri.length > 0 && (
            <>
              <View style={styles.scChipRow} accessibilityRole="tablist">
                {aktifGaleri.map((g) => (
                  <TouchableOpacity key={g.k} accessibilityRole="tab" accessibilityState={{ selected: seciliGorsel?.k === g.k }}
                    style={[styles.scChip, seciliGorsel?.k === g.k && styles.scChipOn]} onPress={() => setGaleri(g.k)}>
                    <Text style={[styles.scChipText, seciliGorsel?.k === g.k && styles.scChipTextOn]}>{g.ad}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              {seciliGorsel && (
                <>
                  {/* AÇIK yükseklik (plan v2: styles.imagePreview %100-yükseklik tuzağı) */}
                  <Image testID="sc-stage" source={{ uri: `data:image/jpeg;base64,${(result as any)[seciliGorsel.alan]}` }}
                    style={styles.scStage} resizeMode="contain" />
                  <Text style={styles.ctHint}>{seciliGorsel.not}</Text>
                </>
              )}
              {!result.uyari && (
                <Text style={styles.ctHint}>ℹ Görsel içi sayımlar ROI bandına aittir; toplam hücre sayısı üstteki karttadır.</Text>
              )}
            </>
          )}
          {result.xai_error ? <Text style={styles.xaiSatiri}>🔍 {result.xai_error}</Text> : null}
          {result.closure_uyari ? <Text style={styles.scUyari}>⚠ {result.closure_uyari}</Text> : null}

          {kayitlar.length >= 2 && (
            <>
              <TouchableOpacity style={[styles.scChip, karsiAcik && styles.scChipOn, { alignSelf: "stretch", alignItems: "center", marginTop: spacing.sm }]}
                onPress={() => setKarsiAcik(!karsiAcik)} accessibilityRole="button">
                <Text style={[styles.scChipText, karsiAcik && styles.scChipTextOn]}>⇄ Karşılaştır (son iki analiz)</Text>
              </TouchableOpacity>
              {karsiAcik && son2.length === 2 && (
                <View style={styles.scDelta}>
                  <Text style={styles.scDeltaVal}>
                    Δ {(son2[1].closure_pct - son2[0].closure_pct) >= 0 ? "+" : ""}{(son2[1].closure_pct - son2[0].closure_pct).toFixed(1)} puan
                  </Text>
                  <Text style={styles.ctHint}>
                    {son2[0].etiket} %{son2[0].closure_pct} → {son2[1].etiket} %{son2[1].closure_pct} · ort. gap {son2[0].mean_gap_um}→{son2[1].mean_gap_um} µm
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
  const { showToast } = useToast();
  const CK = "/vision/cat_organ";
  const [imageUri, setImageUri] = useState<string | null>(visionCache[CK]?.imageUri ?? null);
  const [imageBase64, setImageBase64] = useState<string | null>(visionCache[CK]?.imageBase64 ?? null);
  const [imageFile, setImageFile] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AiResult | null>(visionCache[CK]?.result ?? null);
  const [longLoading, setLongLoading] = useState(false);
  const { isCompact } = useResponsive();

  // Canlı kamera: telefon/web kamerasından periyodik kare → cat_organ analizi → overlay güncelle.
  const [isLive, setIsLive] = useState(false);
  const [facing, setFacing] = useState<"back" | "front">("back");
  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<any>(null);
  const liveIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const liveLoadingRef = useRef(false);

  useEffect(() => { visionCache[CK] = { imageUri, imageBase64, result }; }, [imageUri, imageBase64, result]);
  useEffect(() => {
    if (!loading) { setLongLoading(false); return; }
    const t = setTimeout(() => setLongLoading(true), 8000);
    return () => clearTimeout(t);
  }, [loading]);

  // Canlı kare yakalama döngüsü (3 modelli ağır pipeline → 3.5sn aralık; önceki kare bitmeden yenisini başlatma).
  useEffect(() => {
    if (!isLive) return;
    const capture = async () => {
      if (liveLoadingRef.current || !cameraRef.current) return;
      liveLoadingRef.current = true;
      try {
        // shutterSound: false — canlı organ takibi ~3,5 sn'de bir kare alır (saha bildirimi).
        const photo = await cameraRef.current.takePictureAsync({
          quality: 0.6, skipProcessing: true, shutterSound: false,
        });
        const shrunk = photo?.uri ? await shrinkForUpload(photo.uri) : { uri: "", base64: null };
        if (shrunk.base64) {
          const fd = new FormData();
          fd.append("image_base64", shrunk.base64);
          const ctrl = new AbortController();
          // CANLI-DONGU: kisa sinir ZORUNLU (uzun timeout kamera akisini kilitler)
          const t = setTimeout(() => ctrl.abort(), 25000);
          const r = await fetch(serviceConfig.apiBaseUrl + "/ai/vision/cat_organ", { method: "POST", body: fd, headers: { Accept: "application/json", ...authHeaders() }, signal: ctrl.signal });
          clearTimeout(t);
          const data = await r.json();
          if (r.ok && data?.status === "success") setResult(data); // overlay = data.image_base64
        }
      } catch {
        /* canlı modda kare hatalarını sessiz geç */
      } finally {
        liveLoadingRef.current = false;
      }
    };
    liveIntervalRef.current = setInterval(capture, 3500);
    return () => { if (liveIntervalRef.current) { clearInterval(liveIntervalRef.current); liveIntervalRef.current = null; } };
  }, [isLive]);

  const toggleLive = async () => {
    if (!isLive) {
      if (!permission?.granted) {
        const res = await requestPermission();
        if (!res?.granted) { showToast("Canlı kamera için izin gerekli.", "error"); return; }
      }
    }
    const next = !isLive;
    setIsLive(next);
    if (!next) { setImageUri(null); setImageBase64(null); setImageFile(null); setResult(null); }
  };

  const takePhoto = async () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file'; input.accept = 'image/*'; (input as any).capture = 'environment';
      input.onchange = (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0];
        if (file) { if (imageUri && imageUri.startsWith('blob:')) URL.revokeObjectURL(imageUri); setImageFile(file); setImageUri(URL.createObjectURL(file)); setImageBase64(null); setResult(null); }
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
        if (file) { if (imageUri && imageUri.startsWith('blob:')) URL.revokeObjectURL(imageUri); setImageFile(file); setImageUri(URL.createObjectURL(file)); setImageBase64(null); setResult(null); }
      };
      input.click();
    } else {
      const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, allowsEditing: false, quality: 0.8, base64: true });
      if (!res.canceled) { const shrunk = await shrinkForUpload(res.assets[0].uri); setImageUri(shrunk.uri); setImageBase64(shrunk.base64); setImageFile((res.assets[0] as any).file || null); setResult(null); }
    }
  };

  const analyze = async () => {
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
      if (response.ok && data.status === "success") {
        setResult(data);
        logAiResult(patientName, "Kedi Organ", `${data.n_organs} organ lokalize`, { moduleId: "cat_organ", inputType: "image", detail: data });
      } else {
        showToast(data?.detail || "Analiz sırasında hata oluştu.", "error");
      }
    } catch (e) {
      showToast(aiHataMesaji(e), "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card style={styles.card}>
      <Text style={styles.title}>Kedi Organ Lokalizasyonu</Text>
      <Text style={styles.subtitle}>Kedi fotoğrafından 10 organın 3B konumu (segmentasyon + poz + canonical atlas + PnP).</Text>

      {!imageUri && !isLive && (
        <View style={styles.photoGuide}>
          <Text style={styles.photoGuideTitle}>🐾 Nasıl kullanılır?</Text>
          <Text style={styles.photoGuideItem}>• <Text style={styles.photoGuideBold}>Galeriden Seç</Text> veya <Text style={styles.photoGuideBold}>Fotoğraf Çek</Text> ile tek kare analiz edin</Text>
          <Text style={styles.photoGuideItem}>• <Text style={styles.photoGuideBold}>Canlı Kamera</Text> ile kediyi kadraja alın; organ haritası her birkaç saniyede güncellenir</Text>
          <Text style={styles.photoGuideItem}>• Kedinin tümü görünür, yandan/üstten net bir görüntü kullanın</Text>
          <Text style={styles.photoGuideItem}>• Kabinde ArUco işaretçi varsa 3B konum kabin koordinatında verilir</Text>
        </View>
      )}

      <View style={styles.imagePreviewContainer}>
        {isLive ? (
          <View style={styles.cameraContainer}>
            <CameraView ref={cameraRef} style={styles.cameraView} facing={facing} />
            {result?.image_base64 && (
              <Image source={{ uri: `data:image/jpeg;base64,${result.image_base64}` }} style={styles.cameraOverlay} />
            )}
            <TouchableOpacity style={styles.flipCameraBtn} onPress={() => setFacing((f) => (f === "back" ? "front" : "back"))} accessibilityRole="button" accessibilityLabel="Kamerayı çevir">
              <SwitchCamera color={colors.white} size={20} />
            </TouchableOpacity>
            <View style={styles.liveIndicator}>
              <View style={styles.liveDot} />
              <Text style={styles.liveText}>{result ? `${result.n_organs ?? 0} ORGAN` : "ORGAN ARANIYOR…"}</Text>
            </View>
          </View>
        ) : imageUri ? (
          <Image source={{ uri: result?.image_base64 ? `data:image/jpeg;base64,${result.image_base64}` : imageUri }} style={styles.imagePreview} resizeMode="contain" />
        ) : (
          <View style={styles.placeholderBox}><ImageIcon color={colors.textMuted} size={48} /><Text style={styles.placeholderText}>Görüntü seçilmedi</Text></View>
        )}
      </View>

      {isLive && (
        <Text style={styles.liveHint}>🎥 Canlı mod açık — kediyi kadraja alıp sabit tutun. Organ haritası ~3-4 saniyede bir güncellenir; barların rengi güven düzeyini gösterir.</Text>
      )}

      <View style={[styles.btnRow, isCompact && { flexDirection: "column" }]}>
        <View style={isCompact ? { width: "100%" } : { flex: 1 }}><Button label="Galeriden Seç" icon={<ImageIcon color={colors.white} size={16} />} onPress={pickImage} disabled={isLive} /></View>
        <View style={isCompact ? { width: "100%" } : { flex: 1 }}><Button label="Fotoğraf Çek" icon={<Camera color={colors.white} size={16} />} onPress={takePhoto} disabled={isLive} /></View>
        <View style={isCompact ? { width: "100%" } : { flex: 1 }}>
          <Button label={isLive ? "Canlıyı Durdur" : "Canlı Kamera"} variant={isLive ? "danger" : "secondary"} icon={<Video color={isLive ? colors.white : colors.primary} size={16} />} onPress={toggleLive} />
        </View>
      </View>

      {!isLive && (
        <View style={styles.analyzeBtn}>
          <Button variant="primary" label={loading ? "Analiz Ediliyor..." : "Organ Analizini Başlat"} icon={loading ? <ActivityIndicator color={colors.white} /> : <Sparkles color={colors.white} size={16} />} disabled={!imageUri || loading} onPress={analyze} />
        </View>
      )}
      {longLoading && <Text style={styles.modelHint}>Model hazırlanıyor (3 model, ilk kullanım uzun sürebilir)…</Text>}

      {result && (
        <View style={styles.resultBox}>
          {(result as any).mirror_warning ? (
            <Text style={styles.scUyari}>⚠ Ayna belirsizliği: bu karede sağ/sol organ ayrımı güvenilir olmayabilir — farklı açıdan ikinci kare önerilir.</Text>
          ) : null}
          {(result as any).anatomic_consistency && (result as any).anatomic_consistency.passed === false ? (
            <Text style={styles.scUyari}>⚠ Anatomik tutarlılık uyarısı: organ dizilimi beklenen anatomiyle çelişiyor — lokalizasyona temkinli yaklaşın.</Text>
          ) : null}
          {(() => {
            const organs = result.organs || [];
            if (organs.length === 0) {
              return <ResultInterpretation tone="alert" emoji="🔍" title="Organ tespit edilemedi"
                text="Bu görüntüde kedi/organ net seçilemedi. Kedinin tümü kadraja girsin, ışık iyi ve görüntü net olsun; yandan/üstten daha yakın bir kare deneyin." />;
            }
            const best = organs.reduce((a: AiOrgan, b: AiOrgan) => ((b.reliability || 0) > (a.reliability || 0) ? b : a), organs[0]);
            const bestPct = Math.round(Math.max(0, Math.min(1, best.reliability || 0)) * 100);
            const bestName = ORGAN_TR[best.name] || best.name;
            const strong = bestPct >= 60;
            return <ResultInterpretation
              tone={strong ? "positive" : "info"} emoji="🐾"
              title={`${organs.length} organ bulundu · en güvenilir: ${bestName} (%${bestPct})`}
              text={strong
                ? "Organlar güvenilir şekilde konumlandı. Aşağıdaki listede her organın 3B konumu (cm) ve güven düzeyi var."
                : "Organlar konumlandı ama güven düşük. Daha net/yakın bir görüntüyle sonuç iyileşir. Aşağıda tüm organlar ve güven düzeyleri var."}
              points={["Renkli bar = modelin o organ konumuna güveni (yeşil ≥%60, sarı ≥%40, kırmızı düşük).", "Bu bir ön-lokalizasyondur, tıbbi tanı değildir."]} />;
          })()}
          <Text style={styles.ctSubLabel}>Teknik: poz {result.pose_type ?? "?"} · PnP {result.pnp_residual_px}px</Text>
          <Text style={styles.ctSubLabel}>Organlar (3B konum · güven)</Text>
          {(result.organs || []).map((o: AiOrgan, i: number) => {
            const c = o.coord_cabin_cm || o.coord_3d_cm || [0, 0, 0];
            const rel = Math.max(0, Math.min(1, o.reliability || 0));
            const pct = Math.round(rel * 100);
            return (
              <View key={i} style={{ marginTop: spacing.xs }}>
                <Text style={styles.resultText}>{ORGAN_TR[o.name] || o.name} <Text style={{ color: colors.textMuted, fontSize: typography.small }}>({(+c[0]).toFixed(1)}, {(+c[1]).toFixed(1)}, {(+c[2]).toFixed(1)}) cm</Text></Text>
                <View style={styles.soundBarRow}>
                  <View style={styles.soundBarTrack}>
                    <View style={[styles.soundBarFill, { width: (`${Math.max(2, pct)}%` as any), backgroundColor: relColor(rel) }]} />
                  </View>
                  <Text style={styles.soundBarPct}>%{pct}</Text>
                </View>
              </View>
            );
          })}
          <Text style={styles.ctHint}>3B koordinat: kedi/kabin çerçevesinde organ merkezi (cm). “Güven”, modelin lokalizasyon kesinliğidir (yeşil ≥%60, sarı ≥%40, kırmızı düşük). Kabin ArUco kalibrasyonuyla konum kabin koordinatına oturur.</Text>
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
  moduleIconWrap: { width: rs(44), height: rs(44), borderRadius: radius.md, alignItems: "center", justifyContent: "center", backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border },
  moduleIconWrapActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  moduleLabel: { color: colors.text, fontSize: typography.body, fontWeight: "700" },
  moduleLabelActive: { color: colors.primary },
  moduleDesc: { color: colors.textMuted, fontSize: typography.small, marginTop: 2, lineHeight: rf(15) },
  content: { paddingHorizontal: spacing.lg, paddingBottom: spacing.xl, width: "100%", maxWidth: rs(980), alignSelf: "center" },
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
  photoGuide: { backgroundColor: colors.primarySoft, borderRadius: radius.md, padding: spacing.md, gap: 3, borderWidth: 1, borderColor: colors.primarySoft },
  photoGuideTitle: { color: colors.text, fontSize: typography.small, fontWeight: "800", marginBottom: 2 },
  photoGuideItem: { color: colors.textMuted, fontSize: typography.small, lineHeight: rf(18) },
  photoGuideBold: { color: colors.text, fontWeight: "bold" },
  photoGuideWarn: { color: colors.warning, fontSize: typography.small, fontStyle: "italic", marginTop: spacing.xs },
  imagePreview: { width: "100%", height: "100%", resizeMode: "contain" },
  cameraContainer: { width: "100%", height: "100%", position: "relative" },
  cameraView: { flex: 1 },
  cameraOverlay: { position: "absolute", top: 0, left: 0, width: "100%", height: "100%", resizeMode: "contain", opacity: 0.8 },
  liveIndicator: { position: "absolute", top: 12, right: 12, flexDirection: "row", alignItems: "center", backgroundColor: "rgba(0,0,0,0.6)", paddingHorizontal: 8, paddingVertical: 4, borderRadius: 12, gap: 6 },
  flipCameraBtn: { position: "absolute", bottom: 12, right: 12, width: rs(44), height: rs(44), borderRadius: 22, backgroundColor: "rgba(0,0,0,0.6)", alignItems: "center", justifyContent: "center" },
  liveDot: { width: rs(8), height: rs(8), borderRadius: 4, backgroundColor: colors.danger },
  liveText: { color: colors.white, fontSize: rf(10), fontWeight: "bold" },
  serverCamNote: { position: "absolute", bottom: 0, left: 0, right: 0, backgroundColor: "rgba(0,0,0,0.65)", color: colors.white, fontSize: rf(10), textAlign: "center", paddingVertical: 5, paddingHorizontal: 8 },
  placeholderBox: { alignItems: "center", gap: spacing.md },
  placeholderText: { color: colors.textMuted, fontSize: typography.body },
  btnRow: { flexDirection: "row", gap: spacing.md },
  analyzeBtn: { marginTop: spacing.sm },
  resultBox: { marginTop: spacing.md, padding: spacing.md, backgroundColor: colors.bgAlt, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.primarySoft },
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
