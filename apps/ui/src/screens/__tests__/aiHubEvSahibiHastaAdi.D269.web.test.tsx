/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * D2.69 (B-6.29) — ev sahibinin FGS, ses ve hastalık analizleri geçmişe SEÇİLİ HASTANIN ADIYLA yazılır.
 * ===========================================================================================================================
 * ÖLÇÜLEN KUSUR: `PetOwnerAiScreen` `logAiResult("", …)` (FGS + ses) ve `<DiseaseModule patientName="" />` → `/ai/log`
 * gövdesinde `patient_name: ""`: ev sahibi geçmişinde hayvan ayrımı ve takip grafiği bu profilde hiç oluşmuyordu (06-2 g3a/g3b).
 * Kapı GERÇEK isteği yakalar (gerçek PatientGate'ten 'Mia' seçilir → gerçek analiz akışı → gerçek `apiPost` gövdesi); metin
 * araması yapmaz. Kimlik (`patient_id`) aynı hastanın olmalı (ad ile kimlik ayrı hastaya işaret edemez).
 * GERÇEK: AuthProvider, UserModeProvider (pet_owner), OperatorProvider (kayıtlı operatörsüz cihaz — Kural 2), AppNavProvider,
 * PatientGate, AiHubScreen, apiClient. Sahte: fetch, Supabase, toast, dosya seçici, cihaz modülleri, abonelik gösterimi.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/services/supabaseAuth", () => {
  const aparat = require("../../context/__tests__/operatorAparati");
  return aparat.supabaseSahte("sahip@ev.com");
});
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("@/context/EntitlementContext", () => ({
  useEntitlement: () => ({ research: false, realtime: false }),
  EntitlementProvider: ({ children }: { children: unknown }) => children,
}));
// Abonelik penceresi (UpgradeModal) yerel safe-area modülünü ister (jest-expo YEREL çözer) — kapının konusu değil.
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

import { aiLogGovdeleri, aparat, cihazSahteleriniKur, cihazSahteleriniSok, hastaSec, kurAiHub, Sahne } from "./aiHubAparati";

const SAHIP = "sahip@ev.com";
const HASTALAR = [
  { id: "u-mia", name: "Mia", operator_email: SAHIP, species: "Kedi" },
  { id: "u-pamuk", name: "Pamuk", operator_email: SAHIP, species: "Kedi" },
];
const FGS = { status: "success", detected: true, fgs_total: 2, pain_level: "Mild", raw_fgs: { action_units: {} },
  action_units: {}, hw_status: "idle", hw_params: {} };
const SES = { status: "success", top_1_class: "Happy", top_1_prob: 0.91, top_k: [], guvenilir: true };
const HASTALIK = { status: "success", results: [{ disease: "Gastroenteritis", probability: 0.71 }] };

function analizYanitlari(yol: string, _g: unknown, yontem: string): [number, unknown] | undefined {
  if (yontem === "POST" && yol === "/ai/vision/landmark") return [200, FGS];
  if (yontem === "POST" && yol === "/ai/sound/cat") return [200, SES];
  if (yontem === "POST" && yol === "/ai/disease") return [200, HASTALIK];
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

async function evSahibiMiaIle() {
  await kurAiHub(s, { mod: "pet_owner", hastalar: HASTALAR, ozel: analizYanitlari });
  await hastaSec(s, "Mia");
  expect(s.metin()).toContain("Akıllı Teşhis Asistanı"); // ARA: hasta kapısı geçildi, ev sahibi ekranı çizildi
}

it("KRİTİK D2.69: ev sahibi FGS analizi /ai/log'a seçili hastanın ADI ve KİMLİĞİYLE yazılır", async () => {
  await evSahibiMiaIle();
  aparat.dosyaSiradaki = new File([new Uint8Array([1, 2, 3])], "mia.jpg", { type: "image/jpeg" });
  await s.metneTikla("Galeriden Seç");
  await s.metneTikla("Teşhis Et");
  const g = aiLogGovdeleri();
  expect(g).toHaveLength(1); // ARA: gerçek akış kaydı gönderdi
  expect(g[0].module_id).toBe("landmark");
  expect(g[0].patient_name).toBe("Mia");
  expect(g[0].patient_id).toBe("u-mia");
});

it("KRİTİK D2.69: ev sahibi SES analizi /ai/log'a seçili hastanın ADI ve KİMLİĞİYLE yazılır", async () => {
  await evSahibiMiaIle();
  aparat.dosyaSiradaki = new File([new Uint8Array([9, 9])], "mia.wav", { type: "audio/wav" });
  await s.metneTikla("Ses Yükle");
  await s.metneTikla("Sesi Analiz Et");
  const g = aiLogGovdeleri();
  expect(g).toHaveLength(1);
  expect(g[0].module_id).toBe("cat_sound");
  expect(g[0].patient_name).toBe("Mia");
  expect(g[0].patient_id).toBe("u-mia");
});

it("KRİTİK D2.69: ev sahibi HASTALIK analizi /ai/log'a seçili hastanın ADI ve KİMLİĞİYLE yazılır", async () => {
  await evSahibiMiaIle();
  await s.metneTikla("İştah Kaybı");
  await s.metneTikla("Kusma");
  await s.metneTikla("Teşhisi Başlat");
  const g = aiLogGovdeleri();
  expect(g).toHaveLength(1);
  expect(g[0].module_id).toBe("disease");
  expect(g[0].patient_name).toBe("Mia");
  expect(g[0].patient_id).toBe("u-mia");
});

it("KARŞIT D2.69: hekim profilinde (AI Hub) hastalık analizi seçili hastanın adını yazmaya DEVAM eder", async () => {
  await kurAiHub(s, { mod: "veterinarian", hastalar: HASTALAR, ozel: analizYanitlari });
  await hastaSec(s, "Pamuk");
  await s.metneTikla("Hastalık");
  await s.metneTikla("İştah Kaybı");
  await s.metneTikla("Kusma");
  await s.metneTikla("Teşhisi Başlat");
  const g = aiLogGovdeleri();
  expect(g).toHaveLength(1);
  expect(g[0].patient_name).toBe("Pamuk");
  expect(g[0].patient_id).toBe("u-pamuk");
});
