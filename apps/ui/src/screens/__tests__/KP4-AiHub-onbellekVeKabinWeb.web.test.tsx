/**
 * @jest-environment jsdom
 */
/**
 * KP-4 B1 · src/screens/AiHubScreen.tsx · WEB — önbellekten geri gelen görüntü, kabin canlı analiz döngüsünün hata kolları, AI Pro köprüsü.
 *  1) Modül kapatılıp yeniden açılınca (akordeon) önbellekteki galeri görüntüsü KAYBOLMAZ: "Analizi Başlat" onu nesne URL'sinden okuyup
 *     modülün DOSYA ADIYLA gönderir (FGS · Kedi Organ · Fantom · Petri · Böbrek CT · Böbrek Patoloji).
 *  2) FGS: önbellekteki dosya görsel DEĞİLSE analiz isteği GİTMEZ, kullanıcıya hata iletisi çıkar.
 *  3) Petri / Fantom kabin canlı (backend bu makinede): analiz karesi alınırken kamera AI Pro'ya geçerse (409) canlı DURUR, sunucunun
 *     EYLEM metni gösterilir, kamera oturumu kapatılır, analiz isteği gitmez; başka bir kabin hatasında canlı SÜRER ve sunucunun metni
 *     durum satırındadır (sonraki kare yeniden denenir).
 *  4) Fantom / Petri başarılı sonuçtaki "Bu hedefe AI Pro seansı" köprüsü YALNIZ Kontrol'e gider ve modeli ön-seçer; `/ai/pro/*`
 *     isteği ATMAZ (otonom onay kapısı Kontrol → AI Pro'da).
 * GERÇEK: AiHubScreen (+ modülleri), ToastProvider, apiClient, korunanFetch, AnalizKosulu (kabin kamerası istemcisi), utils/canliKare.
 * SAHTE (en alt kat): fetch, dosya seçici, nesne URL'leri, Date.now kayması (aparat), zamanlayıcılar; platform sınırı (güvenli alan,
 * "backend bu makinede mi"); bağlamlar sabit girdi (gezinme çağrıları gözlenir).
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
let mockKip: "veterinarian" | "researcher" = "veterinarian";
let mockBuMakinede = false;
let mockHastaNo = 47000;
const mockGit = jest.fn();
const mockAiProModeli = jest.fn();
jest.mock("@/services/backendKonumu", () => ({ backendBuMakinede: () => mockBuMakinede }));
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: mockKip, hasAiHub: true }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "dr@klinik.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({
  useOperator: () => ({ operatorEmail: "dr@klinik.com" }),
  useOperatorOptional: () => ({ operatorEmail: "dr@klinik.com", operators: [] }),
}));
jest.mock("@/context/EntitlementContext", () => ({ useEntitlement: () => ({ research: true, realtime: true }) }));
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigateTo: mockGit, setAiProModeli: mockAiProModeli,
    selectedPatient: { id: `kp4w-${mockHastaNo}`, name: `Pamuk-${mockHastaNo}` } }),
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
import {
  alanlar, blobMetni, ekraniCiz, etiketeBas, ileti, metneBas, postlar, saatiIlerlet, Sahne, web, webKur, webSok,
} from "./KP3_aiHubWebAparati";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);

interface Modul {
  ad: string;
  kip: "veterinarian" | "researcher";
  uc: string;
  dosya: string;
  baslat: string;
}
const MODULLER: Modul[] = [
  { ad: "ai.modul.yuzAgrisi.ad", kip: "veterinarian", uc: "/ai/vision/landmark", dosya: "upload.jpg", baslat: "ai.fgs.analiziBaslat" },
  { ad: "ai.modul.kediOrgan.ad", kip: "veterinarian", uc: "/ai/vision/cat_organ", dosya: "cat.jpg", baslat: "ai.organ.analiziBaslat" },
  { ad: "ai.modul.fantomTumor.ad", kip: "researcher", uc: "/ai/vision/em_fantom", dosya: "phantom.jpg", baslat: "ai.fantom.analiziBaslat" },
  { ad: "ai.modul.petriKuyu.ad", kip: "researcher", uc: "/ai/vision/em_petri", dosya: "petri.jpg", baslat: "ai.petri.analiziBaslat" },
  { ad: "ai.modul.bobrekCt.ad", kip: "researcher", uc: "/ai/vision/kidney_ct", dosya: "ct.jpg", baslat: "ai.ct.analiziBaslat" },
  { ad: "ai.modul.bobrekPatoloji.ad", kip: "researcher", uc: "/ai/vision/histopath", dosya: "histo.jpg", baslat: "ai.patoloji.analiziBaslat" },
];

const KAPI = { surulebilir: true, pemf_gecerli: true, kosulsuz: false, atlanan: [], nedenler: [], eylem: "", mesajlar: [], varsayimlar: [] };
const FANTOM = {
  status: "success", success: true, method: "coil_ring", mm_per_px: 0.31, n_tumor: 1, n_healthy: 0, healthy_regions: [],
  tumor_regions: [{ tumor_id: "T1", centroid_cabin_mm: [-43.6, -15, -9.2], D: [0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4], E_cancer: 0.005,
    E_healthy: 0.004, area_mm2: 316 }],
  image_base64: "T1VU", pemf_valid: true, reliable: true, warnings: [], pemf_kapisi: KAPI,
};
const PETRI = {
  status: "success", success: true, method: "plate_grid", mm_per_px: 0.118, n_wells: 1, n_cancer: 0, n_healthy: 1,
  wells: [{ well_id: "W1", label: "healthy", organ_id: 0, centroid_cabin_mm: [19.3, 0, 0], D: [0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3],
    E_cancer: 0.1, E_healthy: 0.1, area_mm2: 150, cancer_reasons: [] }],
  image_base64: "T1VU", yolo_ayar: { conf: 0.25, iou: 0.7 }, resize: {}, plausibility: {}, pemf_valid: true, kosulsuz: false, warnings: [],
  pemf_kapisi: KAPI,
};

let ozel: (yol: string, govde: unknown, yontem: string) => any = () => undefined;
let s: Sahne;

beforeEach(() => {
  mockHastaNo += 1;
  mockBuMakinede = false;
  mockGit.mockClear();
  mockAiProModeli.mockClear();
  ozel = () => undefined;
  webKur((y, g, m) => ozel(y, g, m));
  s = new Sahne();
});
afterEach(async () => {
  await s.sok();
  jest.useRealTimers();
  webSok();
});

async function moduluAc(ad: string, kip: Modul["kip"]) {
  mockKip = kip;
  await ekraniCiz(s);
  await etiketeBas(s, T(ad));
}
async function galeridenSec(f: File) {
  web.dosyaSiradaki = f;
  await metneBas(s, T("ai.ortak.galeridenSec"));
  await s.bosalt(4);
}
const getler = (yol: string) => web.istekler.filter((i) => i.yontem === "GET" && i.yol === yol);

describe.each(MODULLER)("$uc · önbellek", (m) => {
  it("KRİTİK: modül kapatılıp açılınca önbellekteki görüntü nesne URL'sinden okunup modülün dosya adıyla gönderilir", async () => {
    await moduluAc(m.ad, m.kip);
    await galeridenSec(new File(["ONBELLEK"], "secilen.jpg", { type: "image/jpeg" }));
    await etiketeBas(s, T(m.ad)); // kapat
    expect(s.metin()).not.toContain(T(m.baslat));
    await etiketeBas(s, T(m.ad)); // yeniden aç — seçim kaybolmadı
    await metneBas(s, T(m.baslat));
    const giden = postlar(m.uc);
    expect(giden).toHaveLength(1);
    const f = alanlar(giden[0].govde).file as File;
    expect(f.name).toBe(m.dosya);
    expect(await blobMetni(f)).toBe("ONBELLEK");
  });
});

it("KRİTİK: FGS önbellekteki dosya GÖRSEL DEĞİLSE analiz isteği gitmez, hata iletisi çıkar", async () => {
  await moduluAc("ai.modul.yuzAgrisi.ad", "veterinarian");
  await galeridenSec(new File(["DUZ METIN"], "not.txt", { type: "text/plain" }));
  await etiketeBas(s, T("ai.modul.yuzAgrisi.ad"));
  await etiketeBas(s, T("ai.modul.yuzAgrisi.ad"));
  await metneBas(s, T("ai.fgs.analiziBaslat"));
  expect(postlar("/ai/vision/landmark")).toHaveLength(0);
  expect(ileti()).toBeTruthy();
});

describe.each([
  ["ai.modul.petriKuyu.ad", "/ai/vision/em_petri"],
  ["ai.modul.fantomTumor.ad", "/ai/vision/em_fantom"],
])("%s · kabin canlı analiz döngüsü", (ad, uc) => {
  const ONIZLEME = "/settings/kabin-kamerasi/canli/kare";
  const TAM = "/settings/kabin-kamerasi/canli/kare?tam=true";
  function kabin(tam: () => [number, unknown]) {
    ozel = (y) => {
      if (y === "/settings/kabin-kamerasi/canli/baslat" || y === "/settings/kabin-kamerasi/canli/durdur") return [200, { status: "success" }];
      if (y === ONIZLEME) return [200, { status: "success", image_base64: "T05J" }];
      if (y === TAM) return tam();
      return undefined;
    };
  }

  it("KRİTİK: analiz karesi alınırken kamera AI Pro'ya geçerse (409) canlı DURUR, EYLEM metni, oturum kapanır, analiz gitmez", async () => {
    mockBuMakinede = true;
    const EYLEM = "Kabin kamerası AI Pro hazırlığına geçti. Önce oradaki hazırlığı durdurun.";
    kabin(() => [409, { detail: EYLEM }]);
    jest.useFakeTimers({ doNotFake: ["queueMicrotask", "nextTick", "Date"] });
    await moduluAc(ad, "researcher");
    await metneBas(s, T("ai.gorsel.canliKamera"));
    expect(postlar("/settings/kabin-kamerasi/canli/baslat")).toHaveLength(1);
    expect(document.querySelector('[data-testid="em-canli-kutusu"]')).not.toBeNull();
    await s.ilerlet(1100);
    await s.bosalt(10);
    expect(getler(TAM)).toHaveLength(1);
    expect(ileti()).toContain(EYLEM);
    expect(document.querySelector('[data-testid="em-canli-kutusu"]')).toBeNull();
    expect(postlar("/settings/kabin-kamerasi/canli/durdur")).toHaveLength(1);
    expect(postlar(uc)).toHaveLength(0);
    saatiIlerlet();
    await s.ilerlet(3000);
    expect(getler(TAM)).toHaveLength(1); // döngü durdu
  });

  it("KARŞIT: başka bir kabin hatasında canlı SÜRER, sunucunun metni durum satırında; sonraki kare yeniden denenir", async () => {
    mockBuMakinede = true;
    const NEDEN = "Kabin kamerasından kare okunamadı; USB kablosunu kontrol edin.";
    kabin(() => [500, { detail: NEDEN }]);
    jest.useFakeTimers({ doNotFake: ["queueMicrotask", "nextTick", "Date"] });
    await moduluAc(ad, "researcher");
    await metneBas(s, T("ai.gorsel.canliKamera"));
    await s.ilerlet(1100);
    await s.bosalt(10);
    const durum = document.querySelector('[data-testid="canli-durum"]');
    expect(durum?.textContent).toContain(NEDEN.replace(/\.$/, ""));
    expect(durum?.textContent?.startsWith(T("ai.canli.sonKareHata", { hata: "" }).trim().replace(/:$/, ""))).toBe(true);
    expect(document.querySelector('[data-testid="em-canli-kutusu"]')).not.toBeNull();
    expect(postlar("/settings/kabin-kamerasi/canli/durdur")).toHaveLength(0);
    saatiIlerlet();
    await s.ilerlet(1100);
    await s.bosalt(10);
    expect(getler(TAM)).toHaveLength(2);
    expect(postlar(uc)).toHaveLength(0);
    await metneBas(s, T("ai.gorsel.canliyiDurdur"));
  });
});

describe.each([
  ["ai.modul.fantomTumor.ad", "/ai/vision/em_fantom", "ai.fantom.analiziBaslat", FANTOM, "fantom", "ai.kopru.hedefFantom"],
  ["ai.modul.petriKuyu.ad", "/ai/vision/em_petri", "ai.petri.analiziBaslat", PETRI, "petri", "ai.kopru.hedefPetri"],
])("%s · AI Pro köprüsü", (ad, uc, baslat, sonuc, model, hedef) => {
  it("KRİTİK: başarılı sonuçtaki köprü YALNIZ Kontrol'e gider ve modeli ön-seçer; /ai/pro/* isteği ATMAZ", async () => {
    ozel = (y, _g, yon) => (yon === "POST" && y === uc ? [200, sonuc] : undefined);
    await moduluAc(ad, "researcher");
    await galeridenSec(new File(["GORUNTU"], "secilen.jpg", { type: "image/jpeg" }));
    await metneBas(s, T(baslat));
    expect(postlar(uc)).toHaveLength(1);
    expect(mockGit).not.toHaveBeenCalled();
    await etiketeBas(s, T("ai.kopru.etiket", { hedef: T(hedef) }));
    expect(mockAiProModeli).toHaveBeenCalledWith(model);
    expect(mockGit).toHaveBeenCalledWith("control");
    expect(web.istekler.filter((i) => i.yol.startsWith("/ai/pro/"))).toHaveLength(0);
  });
});
