/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * D5 (D3 devri, sağlamlık listesi · 2-C incelemesi §9 #8) — AI kaydı (`/ai/log`) kilitli DB'de 8 sn'yi aşınca ÇİFT KAYIT riski.
 * ===========================================================================================================================
 * ÖLÇÜLEN KUSUR: kilitli hasta / tedavi DB'sinde tek `/ai/log` ~40 sn sürebiliyor (A1); arayüz kaydı varsayılan 8 sn sınırıyla
 * gönderiyordu → istek iptal, ekran "İşlem zaman aşımına uğradı … Tekrar deneyin" diyordu. Sunucu kaydı SONRA yazıyor; hekim
 * "tekrar deneyin" üzerine analizi yeniden koşunca aynı analiz İKİ kez geçmişe giriyordu. Emsal Y84 (D2.E03, `/data/export|import`):
 * ayrı UZUN sınır + "sürüyor olabilir, tekrarlamayın" metni. İstemcide otomatik yeniden deneme YOK (ölçüldü) — tek yol bu metindi.
 * GERÇEK: sağlayıcılar, AiHubScreen (hastalık modülü), apiClient (zaman aşımı + metin), toastBridge. `/ai/log` yanıtı ASKIDA tutulur
 * (aparatın `Askida`sı; istemci iptali gerçek fetch gibi AbortError). Sahte zamanlayıcı analiz başlatılmadan hemen önce kurulur.
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

import { act } from "react";

import { setToastHandler } from "@/services/toastBridge";
import { aiLogGovdeleri, Askida, cihazSahteleriniKur, cihazSahteleriniSok, hastaSec, kurAiHub, Sahne } from "./aiHubAparati";

const HEKIM = "dr.a@klinik.com";
const HASTALAR = [{ id: "u-mia", name: "Mia", operator_email: HEKIM, species: "Kedi" }];
const HASTALIK = { status: "success", results: [{ disease: "Gastroenteritis", probability: 0.71 }] };

let s: Sahne;
let bildirimler: Array<{ mesaj: string; tur?: string }>;
let kayit: Askida;
beforeEach(() => {
  s = new Sahne();
  cihazSahteleriniKur();
  bildirimler = [];
  setToastHandler((mesaj, tur) => { bildirimler.push({ mesaj, tur }); });
});
afterEach(async () => {
  kayit?.serbest(200, { status: "success", id: 1 });
  await s.sok();
  setToastHandler(null);
  cihazSahteleriniSok();
  jest.useRealTimers();
});

const hatalar = () => bildirimler.filter((b) => b.tur === "error").map((b) => b.mesaj).join(" | ");

async function analizKaydiAskida() {
  kayit = new Askida();
  await kurAiHub(s, {
    mod: "veterinarian",
    hastalar: HASTALAR,
    ozel: (yol, _g, yontem) => {
      if (yontem === "POST" && yol === "/ai/disease") return [200, HASTALIK];
      if (yontem === "POST" && yol === "/ai/log") return kayit;
      return undefined;
    },
  });
  await hastaSec(s, "Mia");
  await s.metneTikla("Hastalık");
  await s.metneTikla("İştah Kaybı");
  await s.metneTikla("Kusma");
  jest.useFakeTimers();
  await s.metneTikla("Teşhisi Başlat");
  await s.bosalt();
  expect(aiLogGovdeleri()).toHaveLength(1); // ARA: kayıt gönderildi ve ASKIDA
  expect(s.metin()).toContain("Gastroenteritis");
}

it("KRİTİK: kayıt 8 sn'yi aşınca 'Tekrar deneyin' zaman aşımı GÖSTERİLMEZ; sunucu yazınca da hata yok, tek kayıt", async () => {
  await analizKaydiAskida();
  await s.ilerlet(9000);
  expect(hatalar()).toBe("");
  await act(async () => { kayit.serbest(200, { status: "success", id: 7 }); });
  await s.bosalt();
  expect(hatalar()).toBe("");
  expect(aiLogGovdeleri()).toHaveLength(1);
});

it("KRİTİK: uzun sınır da dolarsa metin kaydın SÜRÜYOR olabileceğini söyler, yeniden çalıştırmayı YASAKLAR, 'Tekrar deneyin' DEMEZ", async () => {
  await analizKaydiAskida();
  await s.ilerlet(61000);
  const h = hatalar();
  expect(h).toContain("hâlâ yazılıyor olabilir");
  expect(h).toContain("yeniden çalıştırmayın");
  expect(h).toContain("AI Geçmişi");
  expect(h).not.toMatch(/Tekrar deneyin/);
});
