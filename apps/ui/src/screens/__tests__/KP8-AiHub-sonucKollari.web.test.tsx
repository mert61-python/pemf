/**
 * @jest-environment jsdom
 */
/**
 * KP-8 · src/screens/AiHubScreen.tsx · WEB görüntü modülleri — SONUÇ gösterimi kalan dallar (düzenek KP3-AiHub-gorselModullerWeb ile AYNI).
 * Sözleşmeler (sunucu yanıtı eksik / alışılmadık biçimde gelse de ekran ÇÖKMEZ, eksik alan boş / 0 / "—" gösterilir):
 *  1) Böbrek CT: yalnız kist varsa bulgu çipi UYARI renginde ("taş" yazmaz); aynı sınıftan iki tespit görüntüdeki yatay konumla
 *     (kutusu olmayan solda sayılır) "solda / sağda" ayrılır; güveni gelmeyen tespit %0; ısı haritası hatası satırı görünür.
 *  2) Böbrek Patoloji: bilinmeyen derece adı aynen + birincil renk; olasılığı gelmeyen derece %0 (çubuk en az %2); ısı haritası hatası görünür.
 *  3) Petri (İngilizce): elenen kuyuların skoru ve eşiği NOKTA ondalıkla; kuyu listesi gelmezse kuyu satırı yok; D dizisi
 *     olmayan kuyuda D çubukları çizilmez.
 *  4) Fantom: sayısı / bölge listesi gelmeyen başarılı yanıtta odak 0, bölge satırı yok; D dizisi olmayan bölgede D çubukları çizilmez.
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

async function analizEt(kip: "veterinarian" | "researcher", modul: string, baslat: string, uc: string, yanit: unknown) {
  mockKip = kip;
  ozel = (y) => (y === uc ? [200, yanit] : undefined);
  await ekraniCiz(s);
  await etiketeBas(s, T(modul));
  web.dosyaSiradaki = foto("KARE");
  await metneBas(s, T("ai.ortak.galeridenSec"));
  await s.bosalt(4);
  await metneBas(s, T(baslat));
  await s.bosalt(6);
  expect(postlar(uc)).toHaveLength(1);
}

/** Metni TAM `metin` olan en derin elemanın hesaplanmış rengi (react-native-web satır içi stil). */
function renk(metin: string): string {
  const el = Array.from(document.querySelectorAll("*")).filter(
    (e) => (e.textContent || "").trim() === metin && !Array.from(e.children).some((c) => (c.textContent || "").trim() === metin),
  ).pop() as HTMLElement | undefined;
  if (!el) throw new Error(`metin yok: ${metin}`);
  return getComputedStyle(el).color;
}

it("Böbrek CT: yalnız kist → uyarı renkli çip (taş yok); iki kist solda / sağda; güvensiz tespit %0; ısı haritası hatası görünür", async () => {
  await analizEt("researcher", "ai.modul.bobrekCt.ad", "ai.ct.analiziBaslat", "/ai/vision/kidney_ct", {
    status: "success",
    class_counts: { "Kidney Cyst": 2 },
    detections: [{ class_name: "Kidney Cyst" }, { class_name: "Kidney Cyst", bbox_xyxy: [100, 0, 200, 50], conf: 0.5 }],
    xai_error: "KP8 ısı haritası üretilemedi",
  });
  const g = govdeMetni();
  const cip = T("ai.ct.bulgu", { parcalar: T("ai.ct.parcaKist", { count: 2 }) });
  expect(g).toContain(cip);
  expect(g).not.toContain(T("ai.ct.bulguTas", { count: 0 }));
  expect(g).toContain(T("ai.ct.solda").trim());
  expect(g).toContain(T("ai.ct.sagda").trim());
  expect(g).toContain(T("ai.ortak.yuzde", { deger: 0 }));
  expect(g).toContain(T("ai.ortak.yuzde", { deger: 50 }));
  expect(g).toContain("🔍 KP8 ısı haritası üretilemedi");
  // uyarı (sarı) — tehlike (kırmızı) DEĞİL
  const { colors } = jest.requireActual("@/theme/tokens");
  const hex = (h: string) => { const n = parseInt(h.slice(1, 7), 16); return `rgb(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255})`; };
  expect(renk(cip)).toBe(hex(colors.warning));
});

it("Böbrek Patoloji: bilinmeyen derece aynen + birincil renk; olasılıksız derece %0; ısı haritası hatası görünür", async () => {
  await analizEt("researcher", "ai.modul.bobrekPatoloji.ad", "ai.patoloji.analiziBaslat", "/ai/vision/histopath", {
    status: "success",
    top_1_class: "grade9",
    top_k: [{ class: "grade9" }],
    xai_error: "KP8 konsensüs yok",
  });
  const g = govdeMetni();
  expect(g).toContain(T("ai.patoloji.tahmin", { derece: "grade9", pct: 0 }));
  expect(g).toContain("Grade 9");
  expect(g).toContain("🔍 KP8 konsensüs yok");
  const cubuk = Array.from(document.querySelectorAll("div")).find((d) => d.style.width === "2%");
  expect(cubuk).toBeTruthy();
});

it("Petri (EN): elenen kuyu skoru / eşiği nokta ondalık; kuyu listesi gelmezse kuyu satırı yok", async () => {
  await i18n.changeLanguage("en");
  await analizEt("researcher", "ai.modul.petriKuyu.ad", "ai.petri.analiziBaslat", "/ai/vision/em_petri", {
    status: "success", success: true, n_wells: 0, n_cancer: 0, n_healthy: 0,
    mm_per_px: 0.1,
    plate: { elenen_kuyular: [{ well_id: "A1", skor: 0.123 }], kuyu_skor_esigi: 0.5 },
  });
  const g = govdeMetni();
  expect(g).toContain(T("ai.petri.elenenKuyular", { n: 1, esik: "0.50", kuyular: "A1 (0.12)" }));
  expect(g).not.toContain("A1 (0,12)");
});

it("Petri: D dizisi olmayan kuyuda D çubukları çizilmez (kuyu satırı yine görünür)", async () => {
  await analizEt("researcher", "ai.modul.petriKuyu.ad", "ai.petri.analiziBaslat", "/ai/vision/em_petri", {
    status: "success", success: true, mm_per_px: 0.1, n_wells: 1, n_cancer: 0, n_healthy: 1,
    wells: [{ well_id: "B2", label: "healthy", D: null }],
  });
  const g = govdeMetni();
  expect(g).toContain("B2");
  expect(tamMetinSayisi("D1")).toBe(0);
});

it("Fantom: sayı ve bölge listesi gelmeyen başarılı yanıtta odak 0, bölge satırı yok; D dizisi olmayan bölgede D çubuğu çizilmez", async () => {
  await analizEt("researcher", "ai.modul.fantomTumor.ad", "ai.fantom.analiziBaslat", "/ai/vision/em_fantom", {
    status: "success", success: true, mm_per_px: 0.1,
  });
  expect(govdeMetni()).toContain(T("ai.fantom.odak.baslik", { count: 0 }));
  expect(govdeMetni()).not.toContain(T("ai.fantom.tumorBaslik", { id: 1 }));
  await s.sok();
  webSok();
  webKur((y) => ozel(y) as never);
  s = new Sahne();
  await analizEt("researcher", "ai.modul.fantomTumor.ad", "ai.fantom.analiziBaslat", "/ai/vision/em_fantom", {
    status: "success", success: true, mm_per_px: 0.1, n_tumor: 1, tumor_regions: [{ tumor_id: 7, D: "bozuk" }],
  });
  const g = govdeMetni();
  expect(g).toContain(T("ai.fantom.tumorBaslik", { id: 7 }));
  expect(tamMetinSayisi("D1")).toBe(0);
});
