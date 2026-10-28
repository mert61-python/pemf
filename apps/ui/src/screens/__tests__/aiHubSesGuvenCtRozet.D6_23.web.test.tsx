/**
 * @jest-environment jsdom
 */
/**
 * D6.23 (B-6.31 · B-6.32) — Hekim Kedi Sesi modülü sunucunun `guvenilir: false` işaretini GÖSTERİR; Böbrek CT tespitsiz sonuçta yeşil
 * "✓ Taş veya kist bulgusu yok" rozeti ÇİZİLMEZ.
 * ===========================================================================================================================
 * ÖLÇÜLEN KUSURLAR (HEAD ebf1c3fe):
 *  · B-6.31: `/api/ai/sound/cat` belirsizliği `guvenilir` ile taşır (`servers/ai_router.py` dönüşü `"guvenilir": ses_guvenilir_mi(_probs)`;
 *    "düşük güven REDDEDİLMEZ, yalnız işaretlenir" — sahip kararı 2026-08-15). Ev sahibi kartı işareti gösterir; hekimin `CatSoundModule`'ü
 *    alanı HİÇ okumuyordu → zayıf sonuç kesin bulgu gibi ("Ağrılı %41") sunuluyordu.
 *  · B-6.32: `/api/ai/vision/kidney_ct` tespitsiz görüntüde `class_counts = {sınıf: 0 for sınıf in classes}`
 *    (`ai_hub/inference_human_kidney_ct` `cnt = {c: 0 for c in self.classes}`) döner; ekran "Görüntüde böbrek yapısı tespit edilemedi."
 *    derken YANINA yeşil "✓ Taş veya kist bulgusu yok" çiziyordu — böbreği görmeyen model taş / kist yokluğunu söyleyemez.
 * GERÇEK: AuthProvider, UserModeProvider, OperatorProvider, AppNavProvider, PatientGate, AiHubScreen (+ CatSoundModule, KidneyCTModule),
 * apiClient, katalog. Sahte (en alt kat): fetch, Supabase, toast, dosya seçici, cihaz modülleri, abonelik gösterimi (araştırma açık).
 * Yanıt gövdeleri backend dönüş sözlüklerinin ALAN KÜMESİYLE (değerler örnek).
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/services/supabaseAuth", () => {
  const aparat = require("../../context/__tests__/operatorAparati");
  return aparat.supabaseSahte("dr.a@klinik.com");
});
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("@/context/EntitlementContext", () => ({
  useEntitlement: () => ({ research: true, realtime: false }),
  EntitlementProvider: ({ children }: { children: unknown }) => children,
}));
jest.mock("@/components/UpgradeModal", () => ({ UpgradeModal: () => null }));
jest.mock("expo-camera", () => ({ CameraView: () => null, useCameraPermissions: () => [{ granted: true }, jest.fn()] }));
jest.mock("expo-audio", () => ({
  useAudioRecorder: () => ({ record: jest.fn(), stop: jest.fn(), prepareToRecordAsync: jest.fn(), uri: null }),
  RecordingPresets: { HIGH_QUALITY: {} },
  setAudioModeAsync: jest.fn(),
  requestRecordingPermissionsAsync: jest.fn(async () => ({ granted: true })),
}));
jest.mock("expo-image-picker", () => ({ MediaTypeOptions: { Images: "Images" }, launchImageLibraryAsync: jest.fn(),
  launchCameraAsync: jest.fn() }));
jest.mock("expo-image-manipulator", () => ({ SaveFormat: { JPEG: "jpeg" }, manipulateAsync: jest.fn() }));
jest.mock("expo-document-picker", () => ({ getDocumentAsync: jest.fn() }));
jest.mock("expo-file-system/legacy", () => ({ readAsStringAsync: jest.fn(), documentDirectory: "file:///" }));
jest.mock("expo-haptics", () => ({ impactAsync: jest.fn(), notificationAsync: jest.fn(), selectionAsync: jest.fn(),
  ImpactFeedbackStyle: {}, NotificationFeedbackType: {} }));
jest.mock("expo-linear-gradient", () => {
  const R = require("react");
  const { View } = require("react-native-web");
  return { LinearGradient: ({ children, style }: { children?: unknown; style?: unknown }) => R.createElement(View, { style }, children) };
});

import { EN, TR } from "@/i18n/__tests__/kaynakMetni";
import { colors } from "@/theme/tokens";
import { aparat, cihazSahteleriniKur, cihazSahteleriniSok, hastaSec, kurAiHub, Sahne } from "./aiHubAparati";

const HEKIM = "dr.a@klinik.com";
const HASTALAR = [{ id: "u-mia", name: "Mia", operator_email: HEKIM, species: "Kedi" }];

/** `/api/ai/sound/cat` başarı dönüşünün alan kümesi (`servers/ai_router.py`). */
const ses = (guvenilir: boolean) => ({
  status: "success",
  top_1_class: "Paining", // sınıf adları GERÇEK model yapılandırmasından (ai_hub/inference_cat_sound/experiment_config.json)
  top_1_prob: 0.41,
  top_k: [{ class: "Paining", prob: 0.41 }, { class: "Angry", prob: 0.22 }, { class: "Happy", prob: 0.12 }],
  probabilities: { Paining: 0.41, Angry: 0.22, Happy: 0.12 },
  guvenilir,
  belirsizlik: guvenilir ? 0.41 : 0.93,
  rms_dbfs: -31.2,
});
/** `/api/ai/vision/kidney_ct` başarı dönüşünün alan kümesi; `class_counts` her sınıfı taşır (`cnt = {c: 0 for c in classes}`). */
const ct = (tas: number, bobrek: number, kist: number) => {
  const detections = [
    ...Array.from({ length: bobrek }, (_, i) => ({ class_id: 1, class_name: "Kidney", conf: 0.88, bbox_xyxy: [10 + i * 50, 10, 40 + i * 50, 40] })),
    ...Array.from({ length: tas }, () => ({ class_id: 0, class_name: "Kidney Stone", conf: 0.71, bbox_xyxy: [20, 20, 25, 25] })),
    ...Array.from({ length: kist }, () => ({ class_id: 2, class_name: "Kidney Cyst", conf: 0.66, bbox_xyxy: [30, 30, 36, 36] })),
  ];
  return {
    status: "success",
    image_base64: "Q1Q=",
    image_w: 512,
    image_h: 512,
    n_detections: detections.length,
    class_counts: { "Kidney Stone": tas, Kidney: bobrek, "Kidney Cyst": kist },
    detections,
  };
};

let sesYaniti: unknown;
let ctYaniti: unknown;
function yanitlar(yol: string, _g: unknown, yontem: string): [number, unknown] | undefined {
  if (yontem === "POST" && yol === "/ai/sound/cat") return [200, sesYaniti];
  if (yontem === "POST" && yol === "/ai/vision/kidney_ct") return [200, ctYaniti];
  return undefined;
}

let s: Sahne;
beforeEach(() => {
  s = new Sahne();
  cihazSahteleriniKur();
});
afterEach(async () => {
  await s.sok();
  cihazSahteleriniSok();
});

const UYARI = "⚠️ Bu sonuç güvenilir değil — kayıtta net bir kedi sesi ayırt edilemedi.";
const YESIL = "✓ Taş veya kist bulgusu yok";
const BELIRSIZ = "Böbrek dokusu bulunamadığı için taş ve kist değerlendirilemedi";

async function hekimSesAnalizi(guvenilir: boolean) {
  sesYaniti = ses(guvenilir);
  await kurAiHub(s, { mod: "veterinarian", hastalar: HASTALAR, ozel: yanitlar });
  await hastaSec(s, "Mia");
  await s.metneTikla("Kedi Sesi");
  aparat.dosyaSiradaki = new File([new Uint8Array([3, 3, 3])], "mia.wav", { type: "audio/wav" });
  await s.metneTikla("Ses Yükle");
  await s.metneTikla("Ses Analizini Başlat");
  await s.bosalt(10);
  expect(s.metin()).toContain("En olası 3 durum"); // ARA: hekim modülünün sonuç kutusu çizildi
}

async function ctAnalizi(tas: number, bobrek: number, kist: number) {
  ctYaniti = ct(tas, bobrek, kist);
  await kurAiHub(s, { mod: "researcher", hastalar: HASTALAR, ozel: yanitlar });
  await hastaSec(s, "Mia");
  await s.metneTikla("Böbrek CT");
  aparat.dosyaSiradaki = new File([new Uint8Array([9, 9, 9])], "ct.jpg", { type: "image/jpeg" });
  await s.metneTikla("Galeriden Seç");
  await s.bosalt(10);
  await s.metneTikla("CT Analizini Başlat");
  await s.bosalt(10);
  expect(s.metin()).toContain("Tespit sayıları"); // ARA: CT sonuç kutusu çizildi
}

test("KRİTİK B-6.31: hekim Kedi Sesi — sunucu `guvenilir: false` derse 'güvenilir değil' uyarısı GÖRÜNÜR", async () => {
  await hekimSesAnalizi(false);
  expect(s.metin()).toContain(UYARI);
});

test("KARŞIT B-6.31: `guvenilir: true` — uyarı YOK (gereksiz uyarı gerçek bulguyu gölgelemez)", async () => {
  await hekimSesAnalizi(true);
  expect(s.metin()).not.toContain("Bu sonuç güvenilir değil");
});

test("KRİTİK B-6.32: Böbrek CT tespitsiz (tüm sınıflar 0) — yeşil 'bulgu yok' rozeti ÇİZİLMEZ; değerlendirilemediği söylenir", async () => {
  await ctAnalizi(0, 0, 0);
  expect(s.metin()).toContain("Görüntüde böbrek yapısı tespit edilemedi.");
  expect(s.metin()).not.toContain(YESIL);
  expect(s.metin()).toContain(BELIRSIZ);
  // D67 orkestratör mutantı (nötr not "başarı" yeşiliyle çizilir) YAŞADI: değerlendirilemeyen sonuç RENGİYLE de "bulgu yok" demez.
  const not = Array.from(document.querySelectorAll<HTMLElement>("div, span")).find(
    (e) => (e.textContent || "").startsWith(BELIRSIZ) && e.querySelector("div, span") === null,
  );
  expect(not).toBeTruthy();
  const yesil = (() => {
    const n = parseInt(colors.success.slice(1), 16);
    return `rgb(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255})`;
  })();
  expect(window.getComputedStyle(not as HTMLElement).color).not.toBe(yesil);
});

test("KARŞIT B-6.32: böbrek dokusu görüldü, taş / kist yok — yeşil 'bulgu yok' rozeti KALIR", async () => {
  await ctAnalizi(0, 2, 0);
  expect(s.metin()).toContain(YESIL);
  expect(s.metin()).not.toContain(BELIRSIZ);
});

test("KARŞIT B-6.32: böbrek dokusu görülmese de taş tespit edildiyse bulgu rozeti çizilir (yeşil yok, belirsiz notu yok)", async () => {
  await ctAnalizi(1, 0, 0);
  expect(s.metin()).toContain("⚠ 1 böbrek taşı bulgusu");
  expect(s.metin()).not.toContain(YESIL);
  expect(s.metin()).not.toContain(BELIRSIZ);
});

test("KARŞIT B-6.32: böbrek + taş + kist birlikte — bulgu rozeti (taş önde), yeşil / belirsiz notu yok", async () => {
  await ctAnalizi(1, 2, 1);
  expect(s.metin()).toContain("⚠ 1 böbrek taşı + 1 kist bulgusu");
  expect(s.metin()).not.toContain(YESIL);
  expect(s.metin()).not.toContain(BELIRSIZ);
});

test("KATALOG: yeni CT metni TR birebir, EN dolu; ses uyarısı VAR OLAN anahtardan (iki modül aynı metin)", () => {
  expect(TR["ai.ct.bulguDegerlendirilemedi"]).toBe(
    "Böbrek dokusu bulunamadığı için taş ve kist değerlendirilemedi — görüntünün böbrek CT kesiti olduğunu kontrol edin.",
  );
  expect(EN["ai.ct.bulguDegerlendirilemedi"]).toBe(
    "No kidney tissue was found, so stones and cysts could not be assessed — check that the image is a kidney CT slice.",
  );
  expect(TR["ai.ses.guvenilirDegil"].startsWith(UYARI)).toBe(true);
});

// TUR 2 (çürütücü kolu): `guvenilir` alanı HİÇ yoksa (GPU `ai_service/app.py` olasılık dönmeyen yanıtta alanı koymaz) sunucu belirsizlik
// İDDİA ETMEMİŞTİR → uyarı çizilmez (ev sahibi kartı ve tip yorumuyla aynı `=== false` sözleşmesi). Mutant `cur623_n1` (`!result.guvenilir`)
// bu dosyada YAŞIYORDU: alansız her sonuç "güvenilir değil" diye işaretlenirdi.
test("SINIR B-6.31: `guvenilir` alanı YOK — 'güvenilir değil' uyarısı ÇİZİLMEZ (yalnız sunucu açıkça false derse)", async () => {
  const { guvenilir: _g, belirsizlik: _b, ...alansiz } = ses(true);
  void _g;
  void _b;
  sesYaniti = alansiz;
  await kurAiHub(s, { mod: "veterinarian", hastalar: HASTALAR, ozel: yanitlar });
  await hastaSec(s, "Mia");
  await s.metneTikla("Kedi Sesi");
  aparat.dosyaSiradaki = new File([new Uint8Array([3, 3, 3])], "mia.wav", { type: "audio/wav" });
  await s.metneTikla("Ses Yükle");
  await s.metneTikla("Ses Analizini Başlat");
  await s.bosalt(10);
  expect(s.metin()).toContain("En olası 3 durum"); // ARA: hekim modülünün sonuç kutusu çizildi
  expect(s.metin()).not.toContain("Bu sonuç güvenilir değil");
});
