/**
 * @jest-environment jsdom
 */
// Author: A1 (2-C inceleme)
/**
 * C2-1.11 — KÖR KAPI: Y115 bayrağının ev sahibi "kaldığın yerden" şeridindeki kolu (AiHubScreen.tsx:462) hiçbir kapıda yok.
 * Ölçüldü (A1 k6m2): şeritte `operatorKayitli: false` (Y115 öncesi "mine" = kendi + SAHİPSİZ) → Y115, patientScope, E11, OA33,
 * Y105, D271 = 55/55 YEŞİL. Şeridin kapsam süzgecinin gerekçesi (kod yorumu): ev sahibine bir hekimin analiz özetini sızdırmamak.
 * Bu kol: kayıtlı operatörlü cihaz, GERÇEK PIN ile "Ev Sahibi" seçili, kendi hayvanı Mia; `/ai/log` yanıtında Mia'nın (kimliğiyle)
 * SAHİPSİZ ve daha YENİ bir analizi (operatörler kurulmadan önce hekimin yazdığı) + ev sahibinin kendi eski analizi →
 * şerit sahipsiz özeti GÖSTERMEZ (Y115: kayıtlı cihazda ev sahibinin kapsamı sahipsizi içermez). HEAD'de YEŞİL.
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
jest.mock("expo-sharing", () => ({ isAvailableAsync: jest.fn(async () => false), shareAsync: jest.fn() }));
jest.mock("expo-file-system/legacy", () => ({ readAsStringAsync: jest.fn(), documentDirectory: "file:///", writeAsStringAsync: jest.fn() }));
jest.mock("expo-haptics", () => ({ impactAsync: jest.fn(), notificationAsync: jest.fn(), selectionAsync: jest.fn(),
  ImpactFeedbackStyle: {}, NotificationFeedbackType: {} }));
jest.mock("expo-linear-gradient", () => {
  const R = require("react");
  const { View } = require("react-native-web");
  return { LinearGradient: ({ children, style }: { children?: unknown; style?: unknown }) => R.createElement(View, { style }, children) };
});
import { cihazSahteleriniKur, cihazSahteleriniSok, hastaSec, kurAiHub } from "./aiHubAparati";
import { aktifOperator, pinleSec, Sahne } from "../../context/__tests__/operatorAparati";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const GERCEK_KAYIT = require("./__fixtures__/aiLog.D271.json").data[0];
const S = "sahip@ev.com";
const A = "dr.a@klinik.com";
const KAYITLI = [{ email: A, display_name: "Dr. A" }, { email: S, display_name: "Ev Sahibi" }];
const HASTALAR = [{ id: "u-mia", name: "Mia", operator_email: S, species: "Kedi" }];
const ANALIZLER = [
  { ...GERCEK_KAYIT, id: 9, created_at: "2026-10-08 12:00:00", patient_name: "Mia", patient_uuid: "u-mia", operator_email: "",
    result_summary: "SAHIPSIZ-HEKIM-OZETI" },
  { ...GERCEK_KAYIT, id: 2, created_at: "2026-10-01 12:00:00", patient_name: "Mia", patient_uuid: "u-mia", operator_email: S,
    result_summary: "KENDI-ESKI-ANALIZ" },
];

let s: Sahne;
beforeEach(() => { s = new Sahne(); cihazSahteleriniKur(); });
afterEach(async () => { await s.sok(); cihazSahteleriniSok(); });

it("KRİTİK C2-1.11 (Y115, şerit): kayıtlı operatörlü cihazda ev sahibinin şeridi SAHİPSİZ analizi göstermez", async () => {
  await kurAiHub(s, { mod: "pet_owner", hastalar: HASTALAR, operatorler: KAYITLI, operatorCipi: true,
    ozel: (yol, _g, yontem) => (yontem === "GET" && yol.startsWith("/ai/log") ? [200, { status: "success", data: ANALIZLER }] : undefined) });
  await pinleSec(s, "Ev Sahibi");
  expect(aktifOperator()).toBe("Ev Sahibi");
  await hastaSec(s, "Mia");
  await s.bosalt(10);
  const serit = document.querySelector('[data-testid="pet-son-analiz"]')?.textContent || "";
  expect(serit).toContain("KENDI-ESKI-ANALIZ"); // ARA: şerit çizildi ve kendi kaydını gösteriyor
  expect(serit).not.toContain("SAHIPSIZ-HEKIM-OZETI");
});
