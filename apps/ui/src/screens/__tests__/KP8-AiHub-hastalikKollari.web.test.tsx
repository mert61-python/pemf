/**
 * @jest-environment jsdom
 */
/**
 * KP-8 · src/screens/AiHubScreen.tsx · WEB — Hastalık modülü sonuç gösterimi kalan dallar (düzenek KP8-AiHub-sonucKollari2 ile AYNI):
 *  - Hiçbir hastalık eşleşmezse "eşleşme yok" yorumu; AI kaydı "Belirgin sonuç yok".
 *  - En olası hastalık %60'ın altındaysa yorum UYARI değil BİLGİ tonunda ve "birden çok olasılık" der; olasılık satırları %30–60 SARI,
 *    %30 altı soluk.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("react-native-safe-area-context", () => {
  const R = require("react");
  const { View } = require("react-native-web");
  return {
    useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
    SafeAreaProvider: ({ children }: { children?: unknown }) => children,
    SafeAreaView: ({ children, style }: { children?: unknown; style?: unknown }) => R.createElement(View, { style }, children),
  };
});
let mockKip: "veterinarian" | "researcher" | "pet_owner" = "veterinarian";
// "Backend bu makinede mi?" kararı (platform sınırı). Ölçüldü: bu ortamda `URL` RN çoklu-dolgusu, kurucu DEĞİL → gerçek karar HEP false
// (SettingsKabinKamerasiYok.T3_Y190 ile aynı) — kabin dalı için açıkça verilir.
let mockBuMakinede = false;
jest.mock("@/services/backendKonumu", () => ({ backendBuMakinede: () => mockBuMakinede }));
let mockHastaNo = 91000;
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: mockKip, hasAiHub: mockKip !== "pet_owner" }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "dr@klinik.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({
  useOperator: () => ({ operatorEmail: "dr@klinik.com" }),
  useOperatorOptional: () => ({ operatorEmail: "dr@klinik.com", operators: [] }),
}));
jest.mock("@/context/EntitlementContext", () => ({ useEntitlement: () => ({ research: true, realtime: false }) }));
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigate: jest.fn(), selectedPatient: { id: `kp3h-${mockHastaNo}`, name: `Tekir-${mockHastaNo}` } }),
}));
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionFresh: false }) }));
jest.mock("@/components/domain/PatientGate", () => {
  const React = require("react");
  return { PatientGate: ({ children }: any) => React.createElement(React.Fragment, null, children) };
});
jest.mock("@/components/UpgradeModal", () => ({ UpgradeModal: () => null }));
jest.mock("expo-camera", () => ({ CameraView: () => null, useCameraPermissions: () => [{ granted: true }, jest.fn()] }));
jest.mock("expo-audio", () => ({
  useAudioRecorder: () => ({ record: jest.fn(), stop: jest.fn(), prepareToRecordAsync: jest.fn(), uri: null }),
  RecordingPresets: { HIGH_QUALITY: {} },
  setAudioModeAsync: jest.fn(),
  requestRecordingPermissionsAsync: jest.fn(async () => ({ granted: true })),
}));
jest.mock("expo-image-picker", () => ({ MediaTypeOptions: { Images: "Images" }, launchImageLibraryAsync: jest.fn(), launchCameraAsync: jest.fn() }));
jest.mock("expo-image-manipulator", () => ({ SaveFormat: { JPEG: "jpeg" }, manipulateAsync: jest.fn() }));
jest.mock("expo-document-picker", () => ({ getDocumentAsync: jest.fn() }));
jest.mock("expo-file-system/legacy", () => ({ readAsStringAsync: jest.fn(), documentDirectory: "file:///" }));
jest.mock("expo-haptics", () => ({ impactAsync: jest.fn(async () => undefined), notificationAsync: jest.fn(), selectionAsync: jest.fn(),
  ImpactFeedbackStyle: {}, NotificationFeedbackType: {} }));
jest.mock("expo-linear-gradient", () => {
  const R = require("react");
  const { View } = require("react-native-web");
  return { LinearGradient: ({ children, style }: { children?: unknown; style?: unknown }) => R.createElement(View, { style }, children) };
});

import i18n from "i18next";
import { ekraniCiz, etiketeBas, metneBas, postlar, Sahne, web, webKur, webSok } from "./KP3_aiHubWebAparati";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);



const foto = (icerik: string) => new File([icerik], "secilen.jpg", { type: "image/jpeg" });
let s: Sahne;
let ozel: (yol: string) => unknown = () => undefined;
beforeEach(async () => {
  mockHastaNo += 1;
  ozel = () => undefined;
  webKur((y) => ozel(y) as never);
  mockBuMakinede = false;
  s = new Sahne();
  await i18n.changeLanguage("tr");
});
afterEach(async () => {
  await s.sok();
  jest.useRealTimers();
  webSok();
  await i18n.changeLanguage("tr");
});

const govdeMetni = () => document.body.textContent || "";
/** Metni TAM olarak `m` olan eleman sayısı (D çubuğu etiketi "D1" — açıklamadaki "D1–D7" sayılmaz). */
const tamMetinSayisi = (m: string) =>
  Array.from(document.querySelectorAll("*")).filter((e) => e.children.length === 0 && (e.textContent || "").trim() === m).length;

/** Modülü aç (ev sahibinde modül YOK), `secici` düğmesiyle `dosya`yı seç, `baslat`a her yanıt için bir kez bas. */
async function analizEt(kip: "veterinarian" | "researcher" | "pet_owner", modul: string | null, secici: string, dosya: File,
  baslat: string, uc: string, yanitlar: unknown[], her?: (i: number) => void | Promise<void>) {
  mockKip = kip;
  let n = 0;
  ozel = (y) => (y === uc ? [200, yanitlar[Math.min(n++, yanitlar.length - 1)]] : undefined);
  await ekraniCiz(s);
  if (modul) await etiketeBas(s, T(modul));
  web.dosyaSiradaki = dosya;
  await metneBas(s, T(secici));
  await s.bosalt(4);
  for (let i = 0; i < yanitlar.length; i++) {
    await metneBas(s, T(baslat));
    await s.bosalt(6);
    expect(postlar(uc)).toHaveLength(i + 1);
    await her?.(i);
  }
}
const ses = () => new File(["SES"], "miyav.mp3", { type: "audio/mpeg" });
const csv = () => new File(["patient_id,g1\nP1,1\n"], "rna.csv", { type: "text/csv" });
/** /ai/log'a giden son kaydın gövdesi (dizge). */
const sonKayitOzeti = () => {
  const k = postlar("/ai/log");
  return k.length ? JSON.stringify(k[k.length - 1].govde) : "";
};
const { colors } = jest.requireActual("@/theme/tokens");
const hex = (h: string) => { const n = parseInt(h.slice(1, 7), 16); return `rgb(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255})`; };

/** Metni TAM `metin` olan en derin elemanın hesaplanmış rengi (react-native-web satır içi stil). */
function renk(metin: string): string {
  const el = Array.from(document.querySelectorAll("*")).filter(
    (e) => (e.textContent || "").trim() === metin && !Array.from(e.children).some((c) => (c.textContent || "").trim() === metin),
  ).pop() as HTMLElement | undefined;
  if (!el) throw new Error(`metin yok: ${metin}`);
  return getComputedStyle(el).color;
}



async function teshis(yanit: unknown) {
  mockKip = "veterinarian";
  ozel = (y) => (y === "/ai/disease" ? [200, yanit] : undefined);
  await ekraniCiz(s);
  await etiketeBas(s, T("ai.modul.hastalik.ad"));
  await metneBas(s, "İştah Kaybı");
  await metneBas(s, "Kusma");
  await metneBas(s, T("ai.hastalik.teshisiBaslat"));
  await s.bosalt(6);
  expect(postlar("/ai/disease")).toHaveLength(1);
}

it("eşleşme yok → 'eşleşme yok' yorumu; kayıt 'Belirgin sonuç yok'", async () => {
  await teshis({ status: "success", results: [] });
  expect(govdeMetni()).toContain(T("ai.hastalik.sonuc.eslesmeYok"));
  expect(sonKayitOzeti()).toContain("Belirgin sonuç yok");
});

it("en olası < %60 → bilgi tonu + 'birden çok'; %30–60 sarı, %30 altı soluk", async () => {
  await teshis({ status: "success", results: [{ disease: "KP8-A", probability: 0.5 }, { disease: "KP8-B", probability: 0.2 }] });
  const g = govdeMetni();
  expect(g).toContain(T("ai.hastalik.sonuc.birdenCok", { disease: "KP8-A", pct: 50 }));
  expect(renk(T("ai.ortak.yuzde", { deger: "50.0" }))).toBe(hex(colors.warning));
  expect(renk(T("ai.ortak.yuzde", { deger: "20.0" }))).toBe(hex(colors.textMuted));
});
