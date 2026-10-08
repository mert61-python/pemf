/**
 * @jest-environment jsdom
 */
// Author: A1 (2-C inceleme)
/**
 * C2-1.9 — KÖR KAPI: D2.E08 / O-A3.6 kapıları önbellek temizliğinin İKİ kolunu ölçmüyor.
 *   (a) `visionCache` (hekim görüntü modülleri: Yüz Ağrısı, Segmentasyon, Termal, …) — E08 kapısı yalnız `moduleCache`
 *       (ev sahibi ekranı, Hastalık) kollarını sürüyor; `resetAiCachesForOwner`dan visionCache temizliği kaldırılınca 21/21 YEŞİL.
 *   (b) AYNI ADLI iki hayvan (A-62'nin senaryosu) — sahip anahtarı kimlik yerine adla kurulunca 21/21 YEŞİL.
 * İkisinde de önceki hastanın görüntüsü/sonucu yeni hastada geri gelir ve analiz düğmesi ÖNCEKİ hastanın görüntüsünü yeni
 * hastaya gönderir (İG-6.23'ün kusur sınıfı). GERÇEK sağlayıcılar + PatientGate + AiHubScreen (aiHubAparati). HEAD'de YEŞİL.
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

import {
  aiLogGovdeleri, aparat, cihazSahteleriniKur, cihazSahteleriniSok, ciftTikKorumasiniBekle, gidenDosyaIcerikleri, hastaSec,
  kurAiHub, metinVar, Sahne,
} from "./aiHubAparati";

const SAHIP = "sahip@ev.com";
const FGS = { status: "success", detected: true, fgs_total: 1, pain_level: "Mild", raw_fgs: { action_units: {} },
  action_units: {}, hw_status: "idle", hw_params: {} };
const HASTALIK = { status: "success", results: [{ disease: "Gastroenteritis", probability: 0.71 }] };
function yanitlar(yol: string, _g: unknown, yontem: string): [number, unknown] | undefined {
  if (yontem === "POST" && yol === "/ai/vision/landmark") return [200, FGS];
  if (yontem === "POST" && yol === "/ai/disease") return [200, HASTALIK];
  return undefined;
}

let s: Sahne;
beforeEach(() => { s = new Sahne(); cihazSahteleriniKur(); });
afterEach(async () => { await s.sok(); cihazSahteleriniSok(); });

it("KRİTİK C2-1.9a: hekim Yüz Ağrısı (visionCache) — Mia → Pamuk: Mia'nın görüntüsü/sonucu gelmez, Mia'nın görüntüsü Pamuk'a GİTMEZ", async () => {
  const HASTALAR = [
    { id: "u-mia", name: "Mia", operator_email: SAHIP, species: "Kedi" },
    { id: "u-pamuk", name: "Pamuk", operator_email: SAHIP, species: "Kedi" },
  ];
  await kurAiHub(s, { mod: "veterinarian", hastalar: HASTALAR, ozel: yanitlar });
  await hastaSec(s, "Mia");
  await s.metneTikla("Yüz Ağrısı (FGS)");
  aparat.dosyaSiradaki = new File([new Uint8Array([77, 73, 65])], "mia.jpg", { type: "image/jpeg" });
  await s.metneTikla("Galeriden Seç");
  await s.metneTikla("AI Analizini Başlat");
  expect(aiLogGovdeleri().map((g) => g.patient_id)).toEqual(["u-mia"]); // ARA: Mia analizi yapıldı
  await hastaSec(s, "Pamuk");
  await ciftTikKorumasiniBekle(s);
  if (!metinVar("AI Analizini Başlat") && !metinVar("Galeriden Seç")) await s.metneTikla("Yüz Ağrısı (FGS)");
  expect(metinVar("Galeriden Seç")).toBe(true); // ARA: modül Pamuk için açık
  expect(s.metin()).not.toContain("FGS Skoru"); // Mia'nın sonucu Pamuk'ta YOK
  if (metinVar("AI Analizini Başlat")) await s.metneTikla("AI Analizini Başlat");
  expect(await gidenDosyaIcerikleri("/ai/vision/landmark")).toEqual(["MIA"]); // Mia'nın görüntüsü Pamuk için GİTMEDİ
  expect(aiLogGovdeleri().map((g) => g.patient_id)).toEqual(["u-mia"]);
});

it("KRİTİK C2-1.9b: AYNI ADLI iki hayvan — Mia (Kedi) → Mia (Köpek): Hastalık sonucu ikinciye geçmez", async () => {
  const HASTALAR = [
    { id: "u-mia-kedi", name: "Mia", operator_email: SAHIP, species: "Kedi" },
    { id: "u-mia-kopek", name: "Mia", operator_email: SAHIP, species: "Köpek" },
  ];
  await kurAiHub(s, { mod: "veterinarian", hastalar: HASTALAR, ozel: yanitlar });
  await hastaSec(s, "Mia", "Kedi");
  await s.metneTikla("Hastalık");
  await s.metneTikla("İştah Kaybı");
  await s.metneTikla("Kusma");
  await s.metneTikla("Teşhisi Başlat");
  expect(s.metin()).toContain("Gastroenteritis"); // ARA
  await hastaSec(s, "Mia", "Köpek");
  await ciftTikKorumasiniBekle(s);
  if (!metinVar("Teşhisi Başlat")) await s.metneTikla("Hastalık");
  expect(metinVar("Teşhisi Başlat")).toBe(true); // ARA: modül ikinci Mia için açık
  expect(s.metin()).not.toContain("Gastroenteritis");
});
