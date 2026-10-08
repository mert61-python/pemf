/**
 * @jest-environment jsdom
 */
// Author: A1 (2-C inceleme)
/**
 * C2-1.8 — O-A3.6 m3 "EŞDEĞER" iddiası YANLIŞ: AI önbellek sahibi anahtarındaki KİMLİK katmanı, seçim temizliği OLMADAN ayrı
 * ölçülebilir. Bu kol `AppNavContext`i kimliğe BAĞLI OLMAYAN bir sağlayıcıyla değiştirir (seçim kimlik değişiminde KORUNUR —
 * yalnız ikinci katman kalır); GERÇEK AuthProvider/UserModeProvider/OperatorProvider/OperatorSwitcher (PIN) + AiHubScreen.
 * Dr. A Mia'da Hastalık analizi → Dr. B'ye PIN ile geçiş (seçim Mia kalır) → Dr. A'nın sonucu ekranda/önbellekten GELMEMELİ.
 * HEAD'de YEŞİL (anahtar kimliği taşıyor); anahtardan kimlik çıkarılınca (2-C'nin m3'ü) KIRMIZI olmalı.
 */
jest.mock("@/context/AppNavContext", () => {
  const R = require("react");
  const Ctx = R.createContext(null);
  function AppNavProvider({ children }: { children: unknown }) {
    const [selectedPatient, setSelectedPatient] = R.useState(null);
    const [aiProModeli, setAiProModeli] = R.useState("");
    const value = R.useMemo(() => ({ navigateTo: () => undefined, selectedPatient, setSelectedPatient, aiProModeli, setAiProModeli }),
      [selectedPatient, aiProModeli]);
    return R.createElement(Ctx.Provider, { value }, children);
  }
  return { AppNavProvider, useAppNav: () => R.useContext(Ctx) };
});
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
const HASTALAR = [{ id: "u-mia", name: "Mia", operator_email: A, species: "Kedi" }];
const HASTALIK = { status: "success", results: [{ disease: "Gastroenteritis", probability: 0.71 }] };
const yanit = (yol: string, _g: unknown, yontem: string): [number, unknown] | undefined =>
  (yontem === "POST" && yol === "/ai/disease" ? [200, HASTALIK] : undefined);

let s: Sahne;
beforeEach(() => { s = new Sahne(); cihazSahteleriniKur(); });
afterEach(async () => { await s.sok(); cihazSahteleriniSok(); });

it("KRİTİK C2-1.8 (katman kolu): seçim kimlik değişiminde KORUNSA bile Dr. A'nın AI sonucu Dr. B'ye önbellekten GELMEZ", async () => {
  await kurAiHub(s, { mod: "veterinarian", hastalar: HASTALAR, operatorler: IKI_HEKIM, ozel: yanit, operatorCipi: true });
  await pinleSec(s, "Dr. A");
  expect(aktifOperator()).toBe("Dr. A");
  await hastaSec(s, "Mia");
  await s.metneTikla("Hastalık");
  await s.metneTikla("İştah Kaybı");
  await s.metneTikla("Kusma");
  await s.metneTikla("Teşhisi Başlat");
  expect(s.metin()).toContain("Gastroenteritis"); // ARA: Dr. A'nın sonucu ekranda
  await pinleSec(s, "Dr. B");
  expect(aktifOperator()).toBe("Dr. B");
  expect(hastaSeridi()).not.toBeNull(); // ARA: bu kolda seçim KORUNDU (yalnız önbellek anahtarı katmanı ölçülüyor)
  expect(s.metin()).not.toContain("Gastroenteritis");
  await ciftTikKorumasiniBekle(s);
  if (!metinVar("Teşhisi Başlat")) await s.metneTikla("Hastalık");
  expect(metinVar("Teşhisi Başlat")).toBe(true); // ARA: modül Dr. B için açık
  expect(s.metin()).not.toContain("Gastroenteritis");
});
