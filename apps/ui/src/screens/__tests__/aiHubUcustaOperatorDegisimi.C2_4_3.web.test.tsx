/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * C2-4.3 (2-C incelemesi, orkestratör — kapsamlar arası zincir) · Y87 ilkesi HEKİM için: uçuştaki AI analizi, uçuşta operatör
 * değişse bile analizi BAŞLATAN hekimin adına kaydedilir.
 * ===========================================================================================================================
 * KUSUR (ölçüldü — arayüz kaydı + GERÇEK uç + SQL): Dr. A kendi hastası Mia'ya hastalık analizi başlatıyor; yanıt ASKIDAYKEN
 * operatör çipinden PIN'le Dr. B'ye geçiliyor; yanıt gelince `/ai/log` Dr. B'nin JETONUYLA ve `operator_email: dr.b` ile gidiyordu →
 * GERÇEK uç satırı `('dr.b@klinik.com', 'u-mia', 'Mia')` yazdı: Dr. A'nın işi Dr. B'ye imzalandı. D2.E09 (Y87) hastayı başlangıçta
 * sabitledi; hekim tamamlanma anından okunuyordu.
 * DÜZELTME: `hastaAnligi()` analizi başlatan hekimin jetonunu + e-postasını da sabitler; `logAiResult` isteği o jetonla gönderir
 * (`apiPost(..., { operatorJetonu })`). Kilitle (D2.E14) jetonu sunucuda iptal ettiğinden o kolda kayıt bugünkü gibi sahipsiz (Y109).
 * GERÇEK: AuthProvider, UserModeProvider (veterinarian), OperatorProvider, OperatorSwitcher (çip → PIN → Geçiş yap / Kilitle),
 * AppNavProvider, PatientGate, AiHubScreen, apiClient. Sahte: fetch (istek + operatör başlığı kaydı), Supabase, toast, cihaz modülleri.
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

import { act } from "react";
import { aparat, Askida, cihazSahteleriniKur, cihazSahteleriniSok, hastaSec, kurAiHub, Sahne } from "./aiHubAparati";
import { aktifOperator, cipEtiketi, pinleSec } from "../../context/__tests__/operatorAparati";

const A = "dr.a@klinik.com";
const B = "dr.b@klinik.com";
const IKI_HEKIM = [{ email: A, display_name: "Dr. A" }, { email: B, display_name: "Dr. B" }];
const HASTALAR = [
  { id: "u-mia", name: "Mia", operator_email: A, species: "Kedi" },
  { id: "u-pamuk", name: "Pamuk", operator_email: B, species: "Kedi" },
];
const HASTALIK = { status: "success", results: [{ disease: "Gastroenteritis", probability: 0.71 }] };

let s: Sahne;
beforeEach(() => {
  s = new Sahne();
  cihazSahteleriniKur();
});
afterEach(async () => {
  await s.sok();
  cihazSahteleriniSok();
});

/** Dr. A (PIN) Mia'ya hastalık analizi başlatır; yanıt ASKIDAYKEN `degistir` uygulanır; yanıt gelir → `/ai/log` kayıtları. */
async function ucustaKimlik(degistir: "B" | "kilit" | "yok", operatorlu = true) {
  const bekle = new Askida();
  await kurAiHub(s, {
    mod: "veterinarian",
    hastalar: operatorlu ? HASTALAR : HASTALAR.map((h) => ({ ...h, operator_email: "klinik@ortak.com" })),
    operatorler: operatorlu ? IKI_HEKIM : [],
    operatorCipi: true,
    ozel: (yol, _g, yontem) => (yontem === "POST" && yol === "/ai/disease" ? bekle : undefined),
  });
  if (operatorlu) {
    await pinleSec(s, "Dr. A");
    expect(aktifOperator()).toBe("Dr. A"); // ARA: gerçek PIN akışı
  }
  await hastaSec(s, "Mia");
  await s.metneTikla("Hastalık");
  await s.metneTikla("İştah Kaybı");
  await s.metneTikla("Kusma");
  await s.metneTikla("Teşhisi Başlat");
  const analiz = aparat.kayit.filter((i) => i.yontem === "POST" && i.yol === "/ai/disease");
  expect(analiz).toHaveLength(1); // ARA: analiz uçuşta
  if (degistir === "B") {
    await pinleSec(s, "Dr. B");
    expect(aktifOperator()).toBe("Dr. B"); // ARA: geçiş gerçekten oldu
  } else if (degistir === "kilit") {
    await s.tikla(cipEtiketi());
    await s.tikla("Oturumu kilitle");
    expect(aktifOperator()).toBeNull();
  }
  await act(async () => { bekle.serbest(200, HASTALIK); });
  await s.bosalt(10);
  return { analiz: analiz[0], log: aparat.kayit.filter((i) => i.yontem === "POST" && i.yol === "/ai/log") };
}

const govde = (i: { govde: unknown }) => i.govde as Record<string, unknown>;

it("KRİTİK C2-4.3: uçuşta Dr. A → Dr. B geçişi — kayıt analizi BAŞLATAN Dr. A'nın jetonu ve e-postasıyla, başlatılan hastaya", async () => {
  const { analiz, log } = await ucustaKimlik("B");
  expect(analiz.operator).toBe(`JETON-${A}`); // ARA: analiz Dr. A'nın jetonuyla başladı
  expect(log).toHaveLength(1); // Y87: atılmaz
  expect(log[0].operator).toBe(`JETON-${A}`);
  expect(govde(log[0]).operator_email).toBe(A);
  expect([govde(log[0]).patient_id, govde(log[0]).patient_name]).toEqual(["u-mia", "Mia"]);
});

it("KARŞIT C2-4.3: kimlik değişmezse kayıt Dr. A'nın jetonuyla (bugünkü gibi)", async () => {
  const { log } = await ucustaKimlik("yok");
  expect(log.map((i) => [i.operator, govde(i).operator_email, govde(i).patient_id])).toEqual([[`JETON-${A}`, A, "u-mia"]]);
});

it("DAVRANIŞ C2-4.3: uçuşta Kilitle — kayıt ATILMAZ (Y87), Dr. B'ye gitmez; giden jeton Dr. A'nınki (sunucu kilitte iptal etti → Y109 sahipsiz; HEAD jetonsuz gönderiyordu — aynı sonuç)", async () => {
  const { log } = await ucustaKimlik("kilit");
  expect(log).toHaveLength(1);
  expect(log[0].operator).toBe(`JETON-${A}`);
  expect(govde(log[0]).operator_email).not.toBe(B);
});

it("KARŞIT C2-4.3 (Kural 2): kayıtlı operatörsüz klinikte jetonsuz, beyan oturum e-postası (değişmez)", async () => {
  const { log } = await ucustaKimlik("yok", false);
  expect(log.map((i) => [i.operator, govde(i).operator_email, govde(i).patient_id])).toEqual([[null, "klinik@ortak.com", "u-mia"]]);
});
