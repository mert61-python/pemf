/**
 * @jest-environment jsdom
 */
/**
 * KP-8 · src/screens/AiHubScreen.tsx · WEB kalan dallar (düzenek KP3-AiHub-gorselModullerWeb ile AYNI — sahte en alt katta).
 * Sözleşmeler:
 *  1) Web dosya seçicisi (görüntü / ses / CSV) dosya seçilmeden kapanırsa (vazgeç) hiçbir modülde girdi OLUŞMAZ: nesne URL'si üretilmez,
 *     yer tutucu durur, analiz ucuna istek gitmez — hem olay HİÇ gelmezse hem de seçici `change`'i BOŞ dosya listesiyle verirse.
 *  2) "Fotoğraf Çek" (web, arka kamera seçicisi) ile İKİNCİ kare alınınca önceki karenin nesne URL'si BIRAKILIR (galeri yolu KP-3'te).
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
beforeEach(() => {
  mockHastaNo += 1;
  webKur(() => undefined);
  mockBuMakinede = false;
  s = new Sahne();
});
afterEach(async () => {
  await s.sok();
  jest.useRealTimers();
  webSok();
});

const metinVar = (m: string) => (document.body.textContent || "").includes(m);

const IPTAL: Array<{ ad: string; kip: "veterinarian" | "researcher" | "pet_owner"; modul: string | null; dugme: string; accept: string;
  yer: string; uc: string }> = [
  { ad: "FGS galeri", kip: "veterinarian", modul: "ai.modul.yuzAgrisi.ad", dugme: "ai.ortak.galeridenSec", accept: "image/*",
    yer: "ai.ortak.goruntuSecilmedi", uc: "/ai/vision/landmark" },
  { ad: "FGS kamera", kip: "veterinarian", modul: "ai.modul.yuzAgrisi.ad", dugme: "ai.gorsel.fotografCek", accept: "image/*",
    yer: "ai.ortak.goruntuSecilmedi", uc: "/ai/vision/landmark" },
  { ad: "Fantom galeri", kip: "researcher", modul: "ai.modul.fantomTumor.ad", dugme: "ai.ortak.galeridenSec", accept: "image/*",
    yer: "ai.ortak.goruntuSecilmedi", uc: "/ai/vision/em_fantom" },
  { ad: "Fantom kamera", kip: "researcher", modul: "ai.modul.fantomTumor.ad", dugme: "ai.gorsel.fotografCek", accept: "image/*",
    yer: "ai.ortak.goruntuSecilmedi", uc: "/ai/vision/em_fantom" },
  { ad: "Petri galeri", kip: "researcher", modul: "ai.modul.petriKuyu.ad", dugme: "ai.ortak.galeridenSec", accept: "image/*",
    yer: "ai.ortak.goruntuSecilmedi", uc: "/ai/vision/em_petri" },
  { ad: "Petri kamera", kip: "researcher", modul: "ai.modul.petriKuyu.ad", dugme: "ai.gorsel.fotografCek", accept: "image/*",
    yer: "ai.ortak.goruntuSecilmedi", uc: "/ai/vision/em_petri" },
  { ad: "Böbrek CT galeri", kip: "researcher", modul: "ai.modul.bobrekCt.ad", dugme: "ai.ortak.galeridenSec", accept: "image/*",
    yer: "ai.ortak.goruntuSecilmedi", uc: "/ai/vision/kidney_ct" },
  { ad: "Böbrek Patoloji galeri", kip: "researcher", modul: "ai.modul.bobrekPatoloji.ad", dugme: "ai.ortak.galeridenSec", accept: "image/*",
    yer: "ai.ortak.goruntuSecilmedi", uc: "/ai/vision/histopath" },
  { ad: "Kedi Organ galeri", kip: "veterinarian", modul: "ai.modul.kediOrgan.ad", dugme: "ai.ortak.galeridenSec", accept: "image/*",
    yer: "ai.ortak.goruntuSecilmedi", uc: "/ai/vision/cat_organ" },
  { ad: "Kedi Organ kamera", kip: "veterinarian", modul: "ai.modul.kediOrgan.ad", dugme: "ai.gorsel.fotografCek", accept: "image/*",
    yer: "ai.ortak.goruntuSecilmedi", uc: "/ai/vision/cat_organ" },
  { ad: "Kedi Sesi ses", kip: "veterinarian", modul: "ai.modul.kediSesi.ad", dugme: "ai.ses.sesYukle", accept: "audio/*",
    yer: "ai.ses.sesSecilmedi", uc: "/ai/sound/cat" },
  { ad: "Böbrek RNA CSV", kip: "researcher", modul: "ai.modul.bobrekRna.ad", dugme: "ai.rna.csvSec", accept: ".csv,text/csv",
    yer: "ai.rna.csvSec", uc: "/ai/rna/kidney" },
  { ad: "Ev sahibi kamera", kip: "pet_owner", modul: null, dugme: "ai.hayvanSahibi.kamerayiAc", accept: "image/*",
    yer: "ai.hayvanSahibi.kamerayiAc", uc: "/ai/vision/landmark" },
  { ad: "Ev sahibi galeri", kip: "pet_owner", modul: null, dugme: "ai.ortak.galeridenSec", accept: "image/*",
    yer: "ai.hayvanSahibi.kamerayiAc", uc: "/ai/vision/landmark" },
  { ad: "Ev sahibi ses", kip: "pet_owner", modul: null, dugme: "ai.ses.sesYukle", accept: "audio/*",
    yer: "ai.ses.sesYukle", uc: "/ai/sound/cat" },
];

describe.each([false, true])("web seçicisi dosyasız kapanırsa girdi oluşmaz (her modül) · boş change olayı: %s", (bosDegisim) => {
  it.each(IPTAL)("$ad: vazgeç → nesne URL'si yok, yer tutucu durur, istek gitmez", async (d) => {
    mockKip = d.kip;
    web.bosDegisim = bosDegisim;
    await ekraniCiz(s);
    if (d.modul) await etiketeBas(s, T(d.modul));
    web.dosyaSiradaki = null;
    await metneBas(s, T(d.dugme));
    expect(web.acilanSeciciler.map((x) => x.accept)).toEqual([d.accept]);
    expect(web.nesneUrlleri.size).toBe(0);
    expect(metinVar(T(d.yer))).toBe(true);
    expect(postlar(d.uc)).toHaveLength(0);
  });
});

describe("web 'Fotoğraf Çek' ikinci kare → önceki nesne URL'si bırakılır", () => {
  const KAMERALI: Array<{ ad: string; kip: "veterinarian" | "researcher"; modul: string }> = [
    { ad: "FGS (görsel modül)", kip: "veterinarian", modul: "ai.modul.yuzAgrisi.ad" },
    { ad: "Fantom", kip: "researcher", modul: "ai.modul.fantomTumor.ad" },
    { ad: "Petri", kip: "researcher", modul: "ai.modul.petriKuyu.ad" },
    { ad: "Kedi Organ", kip: "veterinarian", modul: "ai.modul.kediOrgan.ad" },
  ];
  it.each(KAMERALI)("$ad: iki çekim → ilk karenin URL'si serbest, ikincisi tutulur", async (d) => {
    mockKip = d.kip;
    await ekraniCiz(s);
    await etiketeBas(s, T(d.modul));
    web.dosyaSiradaki = foto("BIR");
    await metneBas(s, T("ai.gorsel.fotografCek"));
    await s.bosalt(4);
    const ilk = Array.from(web.nesneUrlleri.keys());
    expect(ilk).toHaveLength(1);
    web.dosyaSiradaki = foto("IKI");
    await metneBas(s, T("ai.gorsel.fotografCek"));
    await s.bosalt(4);
    expect(web.acilanSeciciler.map((x) => x.capture)).toEqual(["environment", "environment"]);
    expect(web.serbestBirakilan).toContain(ilk[0]);
    const ikinci = Array.from(web.nesneUrlleri.keys()).filter((u) => u !== ilk[0]);
    expect(ikinci).toHaveLength(1);
    expect(web.serbestBirakilan).not.toContain(ikinci[0]);
  });
});
