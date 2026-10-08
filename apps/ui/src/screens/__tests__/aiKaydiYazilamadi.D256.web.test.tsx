/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * D2.56 (B-3.86) — AI analizi geçmişe YAZILAMAZSA hekim BİLDİRİM görür (kaydın düşmediği sessiz kalmaz).
 * ===========================================================================================================================
 * ÖLÇÜLEN KUSUR: backend yazılamayan AI kaydı için `200 {"status": "success", "id": null}` dönüyordu → `apiPost` başarı görüp
 * hiçbir şey göstermiyordu; değerlendirme ve PDF üretilemeyen analiz "kaydedildi" sanılıyordu.
 * `/ai/log` yanıtı GERÇEK backend'den üretilen fikstürdür (`tests/test_ai_log_YAZILAMAZSA_basari_DONMEZ_D256.py`, disk
 * korkuluğu yazımı reddederken GERÇEK uç) — jest Python koşturamaz; fikstür bayatlarsa o kapı KIRMIZI.
 * GERÇEK: AuthProvider, UserModeProvider (veterinarian), OperatorProvider (kayıtlı operatörsüz cihaz — Kural 2), AppNavProvider,
 * PatientGate, AiHubScreen (hastalık modülü), apiClient. Sahte: fetch, Supabase, dosya seçici, cihaz modülleri, abonelik
 * gösterimi; bildirim EN ALT katta yakalanır (`toastBridge` işleyicisi — ToastProvider'ın kaydettiği yer).
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/services/supabaseAuth", () => {
  const aparat = require("../../context/__tests__/operatorAparati");
  return aparat.supabaseSahte("dr.a@klinik.com");
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

import { setToastHandler } from "@/services/toastBridge";
import { aiLogGovdeleri, cihazSahteleriniKur, cihazSahteleriniSok, hastaSec, kurAiHub, Sahne } from "./aiHubAparati";
import YAZILAMADI from "./__fixtures__/aiLogYazilamadi.D256.json";

const HEKIM = "dr.a@klinik.com";
const HASTALAR = [{ id: "u-mia", name: "Mia", operator_email: HEKIM, species: "Kedi" }];
const HASTALIK = { status: "success", results: [{ disease: "Gastroenteritis", probability: 0.71 }] };

let s: Sahne;
let bildirimler: Array<{ mesaj: string; tur?: string }>;
beforeEach(() => {
  s = new Sahne();
  cihazSahteleriniKur();
  bildirimler = [];
  setToastHandler((mesaj, tur) => { bildirimler.push({ mesaj, tur }); });
});
afterEach(async () => {
  await s.sok();
  setToastHandler(null);
  cihazSahteleriniSok();
});

async function hastalikAnalizi(aiLogYaniti: [number, unknown]) {
  await kurAiHub(s, {
    mod: "veterinarian",
    hastalar: HASTALAR,
    ozel: (yol, _g, yontem) => {
      if (yontem === "POST" && yol === "/ai/disease") return [200, HASTALIK];
      if (yontem === "POST" && yol === "/ai/log") return aiLogYaniti;
      return undefined;
    },
  });
  await hastaSec(s, "Mia");
  await s.metneTikla("Hastalık");
  await s.metneTikla("İştah Kaybı");
  await s.metneTikla("Kusma");
  await s.metneTikla("Teşhisi Başlat");
  expect(aiLogGovdeleri()).toHaveLength(1); // ARA: gerçek akış kaydı göndermeyi denedi
}

it("KRİTİK D2.56: GERÇEK backend AI kaydını yazamayınca hekim 'kaydedilemedi' HATA bildirimi görür", async () => {
  await hastalikAnalizi([YAZILAMADI.durum, YAZILAMADI.govde]);
  const hatalar = bildirimler.filter((b) => b.tur === "error");
  expect(hatalar.map((b) => b.mesaj).join(" | ")).toContain("kaydedilemedi");
  expect(s.metin()).toContain("Gastroenteritis"); // sonuç ekranda KALIR (yalnız kayıt düştü)
});

it("KARŞIT D2.56: kayıt yazılınca HATA bildirimi YOK", async () => {
  await hastalikAnalizi([200, { status: "success", id: 7 }]);
  expect(bildirimler.filter((b) => b.tur === "error")).toEqual([]);
});
