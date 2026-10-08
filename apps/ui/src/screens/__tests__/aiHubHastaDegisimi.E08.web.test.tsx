/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * D2.E08 (İG-6.23) — ev sahibi AI ekranı hasta değişince TAMAMEN sıfırlanır: önceki hastanın fotoğrafı/sesi/formu/sonucu yeni
 * hastada görünmez ve yeni hastaya gönderilemez.
 * ===========================================================================================================================
 * ÖLÇÜLEN KUSUR (ADAY-DOGRULAMA-D2 İG-6.23, Chrome+CDP, N=2): Mia analizlerinden sonra şeritten Pamuk seçilince ekranda
 * "Teşhis Et", FGS "1 / 10", ses yorumu ve "En olası: …" KALIYOR; Pamuk'a "Teşhis Et" Mia'nın dosyasını (bayt bayt) gönderiyor
 * ve kayıt Pamuk'un kimliğiyle yazılıyordu. Kök: `<PetOwnerAiScreen/>` anahtarsız; önbellek temizliği ebeveynin `useEffect`'inde
 * — çocuğun `useState(moduleCache…)` başlatıcıları temizlikten ÖNCE okuyor ("yalnız key" de yetmez — ölçüldü, 623k).
 * GERÇEK: AuthProvider, UserModeProvider (pet_owner), OperatorProvider (Kural 2), AppNavProvider, PatientGate, AiHubScreen,
 * apiClient. Sahte: fetch (gövdedeki DOSYA karşılaştırılır), Supabase, toast, dosya seçici, cihaz modülleri, abonelik gösterimi.
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
  aiLogGovdeleri, aparat, cihazSahteleriniKur, cihazSahteleriniSok, ciftTikKorumasiniBekle, gidenDosyaIcerikleri, gidenDosyalar,
  hastaSec, kurAiHub, metinVar, Sahne,
} from "./aiHubAparati";

const SAHIP = "sahip@ev.com";
const HASTALAR = [
  { id: "u-mia", name: "Mia", operator_email: SAHIP, species: "Kedi" },
  { id: "u-pamuk", name: "Pamuk", operator_email: SAHIP, species: "Kedi" },
];
const FGS = { status: "success", detected: true, fgs_total: 1, pain_level: "Mild", raw_fgs: { action_units: {} },
  action_units: {}, hw_status: "idle", hw_params: {} };
const SES = { status: "success", top_1_class: "Happy", top_1_prob: 0.91, top_k: [], guvenilir: true };
const HASTALIK = { status: "success", results: [{ disease: "Gastroenteritis", probability: 0.71 }] };

function yanitlar(yol: string, _g: unknown, yontem: string): [number, unknown] | undefined {
  if (yontem === "POST" && yol === "/ai/vision/landmark") return [200, FGS];
  if (yontem === "POST" && yol === "/ai/sound/cat") return [200, SES];
  if (yontem === "POST" && yol === "/ai/disease") return [200, HASTALIK];
  return undefined;
}

const MIA_FOTO = new File([new Uint8Array([77, 73, 65])], "mia.jpg", { type: "image/jpeg" });
const MIA_SES = new File([new Uint8Array([7, 7, 7])], "mia.wav", { type: "audio/wav" });
const PAMUK_FOTO = new File([new Uint8Array([80, 65, 77])], "pamuk.jpg", { type: "image/jpeg" });

let s: Sahne;
beforeEach(() => {
  s = new Sahne();
  cihazSahteleriniKur();
});
afterEach(async () => {
  await s.sok();
  cihazSahteleriniSok();
});

/** Mia için üç analiz (FGS + ses + hastalık) — ekranda üç sonuç. */
async function miaAnalizleri() {
  await kurAiHub(s, { mod: "pet_owner", hastalar: HASTALAR, ozel: yanitlar });
  await hastaSec(s, "Mia");
  aparat.dosyaSiradaki = MIA_FOTO;
  await s.metneTikla("Galeriden Seç");
  await s.metneTikla("Teşhis Et");
  aparat.dosyaSiradaki = MIA_SES;
  await s.metneTikla("Ses Yükle");
  await s.metneTikla("Sesi Analiz Et");
  await s.metneTikla("İştah Kaybı");
  await s.metneTikla("Kusma");
  await s.metneTikla("Teşhisi Başlat");
  // ARA: üç sonuç da Mia için ekranda, üç kayıt Mia'ya yazıldı
  expect(s.metin()).toContain("Ağrı Skoru (FGS):");
  expect(s.metin()).toContain("Yapay Zeka Yorumu");
  expect(s.metin()).toContain("Gastroenteritis");
  expect(aiLogGovdeleri().map((g) => g.patient_id)).toEqual(["u-mia", "u-mia", "u-mia"]);
}

it("KRİTİK E08: Mia → Pamuk: önceki hastanın fotoğrafı, ses dosyası ve üç sonucu ekranda KALMAZ", async () => {
  await miaAnalizleri();
  await hastaSec(s, "Pamuk");
  expect(s.metin()).toContain("Evcil Hayvanım:Pamuk"); // ARA: seçim gerçekten değişti
  expect(metinVar("Teşhis Et")).toBe(false); // Mia'nın fotoğrafı yüklü değil → "Teşhis Et" yok
  expect(s.metin()).not.toContain("Ağrı Skoru (FGS):");
  expect(s.metin()).not.toContain("Yapay Zeka Yorumu");
  expect(s.metin()).not.toContain("mia.wav");
  expect(s.metin()).not.toContain("Gastroenteritis");
});

it("KRİTİK E08: Pamuk'a 'Sesi Analiz Et' Mia'nın sesini GÖNDEREMEZ; Pamuk'un fotoğrafı kendi dosyasıyla gider", async () => {
  await miaAnalizleri();
  await hastaSec(s, "Pamuk");
  await ciftTikKorumasiniBekle(s); // aynı düğmelere yeniden basılacak (ürünün 400 ms koruması)
  const sesOnce = gidenDosyalar("/ai/sound/cat").length;
  if (metinVar("Sesi Analiz Et")) await s.metneTikla("Sesi Analiz Et"); // düğme etkinse bas — Mia'nın sesi gitmemeli
  expect(gidenDosyalar("/ai/sound/cat").slice(sesOnce)).toEqual([]);
  aparat.dosyaSiradaki = PAMUK_FOTO;
  await s.metneTikla("Galeriden Seç");
  await s.metneTikla("Teşhis Et");
  // Dosyalar İÇERİKLE karşılaştırılır (MIA_FOTO = "MIA", PAMUK_FOTO = "PAM"): yalnız Mia'nın KENDİ analizi + Pamuk'unki.
  expect(await gidenDosyaIcerikleri("/ai/vision/landmark")).toEqual(["MIA", "PAM"]);
  const son = aiLogGovdeleri().slice(-1)[0];
  expect([son.patient_id, son.patient_name]).toEqual(["u-pamuk", "Pamuk"]);
});

it("KARŞIT E08: aynı hasta yeniden seçilince (sahip değişmez) Mia'nın sonuçları KORUNUR", async () => {
  await miaAnalizleri();
  await hastaSec(s, "Mia");
  expect(s.metin()).toContain("Ağrı Skoru (FGS):");
  expect(s.metin()).toContain("Yapay Zeka Yorumu");
  expect(s.metin()).toContain("Gastroenteritis");
  expect(metinVar("Teşhis Et")).toBe(true);
});

it("KRİTİK E08 (hekim AI Hub — diğer modül): Mia'nın hastalık sonucu Pamuk'a geçince görünmez; modül yeniden açılınca da yok", async () => {
  await kurAiHub(s, { mod: "veterinarian", hastalar: HASTALAR, ozel: yanitlar });
  await hastaSec(s, "Mia");
  await s.metneTikla("Hastalık");
  await s.metneTikla("İştah Kaybı");
  await s.metneTikla("Kusma");
  await s.metneTikla("Teşhisi Başlat");
  expect(s.metin()).toContain("Gastroenteritis"); // ARA: Mia'nın sonucu ekranda
  await hastaSec(s, "Pamuk");
  expect(s.metin()).not.toContain("Gastroenteritis");
  await ciftTikKorumasiniBekle(s);
  await s.metneTikla("Hastalık");
  expect(s.metin()).toContain("Teşhisi Başlat"); // ARA: modül Pamuk için açıldı
  expect(s.metin()).not.toContain("Gastroenteritis");
});
