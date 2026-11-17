/**
 * @jest-environment jsdom
 */
/**
 * KP-8 · src/screens/AiHubScreen.tsx · WEB — SES / RNA / FGS / TERMAL / RETİKÜLOSİT / KEDİ ORGAN sonuç gösterimi kalan dallar
 * (düzenek KP3-AiHub-gorselModullerWeb ile AYNI — sahte en alt katta). Sözleşmeler:
 *  1) Kedi Sesi modülü: TANINMAYAN sınıf adı aynen başlıkta, olasılık gelmezse %0 (ekranda ve AI kaydında), açıklama genel "analiz
 *     edildi", ısı haritası hatası görünür; bilgi tonlu sınıf (anne çağrısı) kendi önerisiyle; sınıf adı hiç gelmezse boş adla (çökmez).
 *  2) Ev sahibi ses kartı: ağrı → kırmızı vurgu, uyarı → sarı, bilgi → birincil renk; tanınmayan sınıf adı aynen + genel açıklama;
 *     olasılık gelmezse kayıtta %0.
 *  3) Böbrek RNA: KIRC'siz sonuç olumlu yorumla; ısı haritası hatası görünür; tahmin listesi gelmezse hasta satırı yok.
 *  4) FGS: yüz bulunamadı → "yüz yok"; Termal: güven gelmezse yüzdesiz başlık (anormallik ve normal); Retikülosit: eksik sayım boş,
 *     ısı haritası hatası görünür.
 *  5) Kedi Organ: güveni gelmeyen organ %0, en güvenilir organ başlıkta; "organ çıkarılamadı" yanıtı kayda "Organ çıkarılamadı" yazar.
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


it("Kedi Sesi: tanınmayan sınıf aynen + %0 (ekran ve kayıt), genel açıklama, ısı haritası hatası; bilgi tonu; adsız sınıf", async () => {
  await analizEt("veterinarian", "ai.modul.kediSesi.ad", "ai.ses.sesYukle", ses(), "ai.ses.analiziBaslat", "/ai/sound/cat", [
    { status: "success", top_1_class: "YeniSinif", xai_error: "KP8 mel yok" },
    { status: "success", top_1_class: "MotherCall", top_1_prob: 0.5, top_k: [{ class: "MotherCall", prob: 0.5 }] },
    { status: "success" },
  ], (i) => {
    const g = govdeMetni();
    if (i === 0) {
      expect(g).toContain(T("ai.ses.baslikYuzde", { ad: "YeniSinif", pct: 0 }));
      expect(g).toContain(T("ai.ses.analizEdildi"));
      expect(g).toContain("🔍 KP8 mel yok");
      expect(sonKayitOzeti()).toContain("%0");
    } else if (i === 1) {
      expect(g).toContain(T("ai.ses.oneri.anneCagrisi.metin"));
    } else {
      expect(g).toContain(T("ai.ses.baslikYuzde", { ad: "", pct: 0 }));
    }
  });
});

it("Ev sahibi ses kartı: ağrı kırmızı, uyarı sarı, bilgi birincil; tanınmayan sınıf aynen + genel açıklama; kayıtta %0", async () => {
  await analizEt("pet_owner", null, "ai.ses.sesYukle", ses(), "ai.ses.sesiAnalizEt", "/ai/sound/cat", [
    { status: "success", top_1_class: "Paining", top_1_prob: 0.9 },
    { status: "success", top_1_class: "Warning", top_1_prob: 0.8 },
    { status: "success", top_1_class: "MotherCall", top_1_prob: 0.7 },
    { status: "success", top_1_class: "BilinmeyenSes" },
    { status: "success" },
  ], (i) => {
    const g = govdeMetni();
    if (i === 0) {
      expect(renk(T("ai.ses.oneri.agri.metin"))).toBe(hex(colors.danger));
    } else if (i === 1) {
      expect(renk(T("ai.ses.oneri.uyari.baslik"))).toBe(hex(colors.warning));
    } else if (i === 2) {
      expect(renk(T("ai.ses.oneri.anneCagrisi.baslik"))).toBe(hex(colors.primary));
    } else if (i === 3) {
      expect(g).toContain("BilinmeyenSes");
      expect(g).toContain(T("ai.ses.analizEdildi"));
      expect(sonKayitOzeti()).toContain("%0");
    } else {
      expect(g).toContain(T("ai.ses.analizEdildi"));
    }
  });
});

it("Böbrek RNA: KIRC'siz sonuç olumlu, ısı haritası hatası görünür; tahmin listesi gelmezse hasta satırı yok", async () => {
  await analizEt("researcher", "ai.modul.bobrekRna.ad", "ai.rna.csvSec", csv(), "ai.rna.analiziBaslat", "/ai/rna/kidney", [
    { status: "success", n_patients: 1, predictions: [{ patient_id: "P-KP8", label: "Normal" }], xai_lime: { yanlis: "bicim" },
      xai_error: "KP8 lime yok" },
    { status: "success", n_patients: 0 },
  ], (i) => {
    const g = govdeMetni();
    if (i === 0) {
      expect(g).toContain(T("ai.rna.sonuc.kircYok"));
      expect(g).toContain(T("ai.rna.sonuc.kircYokMetin"));
      expect(g).toContain("P-KP8");
      expect(g).toContain("🔍 KP8 lime yok");
    } else {
      expect(g).not.toContain("P-KP8");
    }
  });
});

it("FGS: yüz bulunamadı → 'yüz yok' yorumu", async () => {
  await analizEt("veterinarian", "ai.modul.yuzAgrisi.ad", "ai.ortak.galeridenSec", foto("Y"), "ai.fgs.analiziBaslat", "/ai/vision/landmark", [
    { status: "success", detected: false, fgs_total: 4 },
  ]);
  expect(govdeMetni()).toContain(T("ai.fgs.yuzYok.baslik"));
});

it("Termal: güven gelmezse yüzdesiz başlık (anormallik ve normal); Retikülosit: eksik sayım boş, ısı haritası hatası görünür", async () => {
  await analizEt("veterinarian", "ai.modul.termal.ad", "ai.ortak.galeridenSec", foto("T"), "ai.fgs.analiziBaslat", "/ai/vision/thermal", [
    { status: "success", prediction: { label: "Sick" } },
    { status: "success", prediction: { label: "Healthy" } },
  ], (i) => {
    expect(govdeMetni()).toContain(i === 0 ? T("ai.termal.anormallik") : T("ai.termal.anormallikYok"));
  });
  await s.sok(); webSok(); webKur((y) => ozel(y) as never); s = new Sahne();
  await analizEt("veterinarian", "ai.modul.retikulosit.ad", "ai.ortak.galeridenSec", foto("R"), "ai.fgs.analiziBaslat", "/ai/vision/reticulocytes", [
    { status: "success", counts: {}, xai_error: "KP8 cam yok" },
  ]);
  const g = govdeMetni();
  expect(g).toContain(T("ai.retikulosit.eritrosit", { sayi: "" }));
  expect(g).toContain("🔍 KP8 cam yok");
});

it("Kedi Organ: güveni gelmeyen organ %0, en güvenilir başlıkta; 'organ çıkarılamadı' kaydı", async () => {
  await analizEt("veterinarian", "ai.modul.kediOrgan.ad", "ai.ortak.galeridenSec", foto("O"), "ai.organ.analiziBaslat", "/ai/vision/cat_organ", [
    { status: "success", n_organs: 2, organs: [{ name: "KP8-A" }, { name: "KP8-B", reliability: 0.4 }] },
    { status: "success", bulunamadi: "organ_cikarilamadi", organs: [] },
  ], (i) => {
    const g = govdeMetni();
    if (i === 0) {
      expect(g).toContain(T("ai.organ.bulundu", { count: 2, bestName: "KP8-B", bestPct: 40 }));
      expect(g).toContain(T("ai.ortak.yuzde", { deger: 0 }));
    } else {
      expect(sonKayitOzeti()).toContain("Organ çıkarılamadı");
    }
  });
});
