/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * O-A3.6 (2-B incelemesi) — seçili hasta ve AI önbelleği KİMLİK değişiminde düşer.
 * ===========================================================================================================================
 * KUSUR: seçili hasta (`AppNavContext`) ve AI önbelleği sahibi (profil + hasta) operatör kimliğinden bağımsızdı: Dr. A "Kilitle"
 * dedikten sonra ekran Mia seçili kalıyor, AI modülü açık — kimliksiz (sahipsiz) analiz ve seans başlatılabiliyordu; Dr. B PIN
 * girip Mia'yı seçince Dr. A'nın sonucu önbellekten geri geliyordu.
 * GERÇEK: AuthProvider, UserModeProvider (veterinarian), OperatorProvider, OperatorSwitcher (çip → PIN → Geçiş yap / Kilitle),
 * AppNavProvider, PatientGate, AiHubScreen, apiClient. Sahte: fetch, Supabase, toast, cihaz modülleri, abonelik gösterimi.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/services/supabaseAuth", () => {
  const aparat = require("../../context/__tests__/operatorAparati");
  return aparat.supabaseSahte("klinik@ortak.com");
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
  aiLogGovdeleri, cihazSahteleriniKur, cihazSahteleriniSok, ciftTikKorumasiniBekle, hastaSec, hastaSeridi, kurAiHub, metinVar, Sahne,
} from "./aiHubAparati";
import { aktifOperator, cipEtiketi, pinleSec } from "../../context/__tests__/operatorAparati";

const A = "dr.a@klinik.com";
const B = "dr.b@klinik.com";
const IKI_HEKIM = [{ email: A, display_name: "Dr. A" }, { email: B, display_name: "Dr. B" }];
const HASTALAR = [
  { id: "u-mia", name: "Mia", operator_email: A, species: "Kedi" },
  { id: "u-pamuk", name: "Pamuk", operator_email: B, species: "Kedi" },
];
const HASTALIK = { status: "success", results: [{ disease: "Gastroenteritis", probability: 0.71 }] };
const yanit = (yol: string, _g: unknown, yontem: string): [number, unknown] | undefined =>
  (yontem === "POST" && yol === "/ai/disease" ? [200, HASTALIK] : undefined);

let s: Sahne;
beforeEach(() => {
  s = new Sahne();
  cihazSahteleriniKur();
});
afterEach(async () => {
  await s.sok();
  cihazSahteleriniSok();
});

/** Dr. A PIN'le geçer, Mia'yı seçer, hastalık analizi yapar (sonuç ekranda). */
async function drAMiaAnalizi() {
  await kurAiHub(s, { mod: "veterinarian", hastalar: HASTALAR, operatorler: IKI_HEKIM, ozel: yanit, operatorCipi: true });
  await pinleSec(s, "Dr. A");
  expect(aktifOperator()).toBe("Dr. A"); // ARA: gerçek PIN akışı kimliği kurdu
  await hastaSec(s, "Mia");
  await s.metneTikla("Hastalık");
  await s.metneTikla("İştah Kaybı");
  await s.metneTikla("Kusma");
  await s.metneTikla("Teşhisi Başlat");
  expect(s.metin()).toContain("Gastroenteritis"); // ARA: Dr. A'nın sonucu ekranda
  expect(aiLogGovdeleri().map((g) => g.patient_id)).toEqual(["u-mia"]);
}

it("KRİTİK O-A3.6: 'Kilitle' sonrası seçili hasta DÜŞER — kimliksiz ekranda Mia'ya analiz başlatılamaz", async () => {
  await drAMiaAnalizi();
  await s.tikla(cipEtiketi());
  await s.tikla("Oturumu kilitle");
  expect(aktifOperator()).toBeNull(); // ARA: kilit gerçekten kimliği düşürdü
  expect(hastaSeridi()).toBeNull(); // seçili hasta şeridi yok
  expect(metinVar("Teşhisi Başlat")).toBe(false);
  expect(s.metin()).not.toContain("Gastroenteritis");
});

it("KRİTİK O-A3.6: Dr. A → Dr. B geçişinde seçim düşer; Dr. B Mia'yı seçince Dr. A'nın sonucu önbellekten GELMEZ", async () => {
  await drAMiaAnalizi();
  await pinleSec(s, "Dr. B");
  expect(aktifOperator()).toBe("Dr. B");
  expect(hastaSeridi()).toBeNull();
  await hastaSec(s, "Mia");
  await ciftTikKorumasiniBekle(s);
  await s.metneTikla("Hastalık");
  expect(metinVar("Teşhisi Başlat")).toBe(true); // ARA: modül Dr. B için açıldı
  expect(s.metin()).not.toContain("Gastroenteritis");
});

it("KARŞIT O-A3.6 (Kural 2): kayıtlı operatörsüz klinikte kimlik değişmez — seçim ve sonuç KORUNUR", async () => {
  await kurAiHub(s, { mod: "veterinarian", hastalar: HASTALAR.map((h) => ({ ...h, operator_email: "klinik@ortak.com" })),
    ozel: yanit, operatorCipi: true });
  await hastaSec(s, "Mia");
  await s.metneTikla("Hastalık");
  await s.metneTikla("İştah Kaybı");
  await s.metneTikla("Kusma");
  await s.metneTikla("Teşhisi Başlat");
  await s.bosalt(10);
  expect(hastaSeridi()).not.toBeNull();
  expect(s.metin()).toContain("Gastroenteritis");
  expect(aiLogGovdeleri().map((g) => [g.patient_id, g.patient_name])).toEqual([["u-mia", "Mia"]]);
});
