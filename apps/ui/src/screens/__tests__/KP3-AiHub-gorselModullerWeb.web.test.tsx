/**
 * @jest-environment jsdom
 */
/**
 * KP-3 C · src/screens/AiHubScreen.tsx · HEKİM / ARAŞTIRMACI GÖRÜNTÜ MODÜLLERİ — WEB sözleşmeleri (her modülde AYNI iddialar):
 *  1) "Galeriden Seç" (web): `image/*` seçici (kamera İSTEMEZ) açılır; seçilen görüntü "Analizi Başlat" ile modülün ucuna çok parçalı
 *     `file` alanında, modülün DOSYA ADIYLA gider. İkinci seçimde önceki görüntünün nesne URL'si BIRAKILIR (gün boyu açık web
 *     istemcisinde bellek birikmez).
 *  2) Sunucu reddi → sunucunun Türkçe gerekçesi ekranda; fetch reddi → "istek gönderilemedi" (ham hata metni YOK).
 *  3) "Fotoğraf Çek" (web, backend UZAK makinede): arka kamerayı isteyen seçici (`capture=environment`) açılır; çekilen kare gider.
 *  4) Fantom / Petri (backend BU makinede): "Fotoğraf Çek" seçili KABİN kamerasından kare alır (dizüstü kamerası / seçici AÇILMAZ);
 *     kabin karesi analize JPEG olarak gider, önceki galeri görüntüsünün nesne URL'si bırakılır; kabin hatası sunucunun eylem metniyle.
 *  5) Analiz 8 sn'yi aşarsa "model hazırlanıyor" ipucu görünür; AI_TIMEOUT_MS dolunca istek İPTAL edilir ve zaman aşımı iletisi çıkar.
 * GERÇEK: AiHubScreen (+ modülleri), ToastProvider, apiClient, korunanFetch, AnalizKosulu (kabin kamerası istemcisi), config.
 * SAHTE (en alt kat): fetch, dosya seçici, URL nesne-URL'leri, platform sınırı (güvenli alan), expo modülleri; bağlamlar sabit girdi.
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
// "Backend bu makinede mi?" kararı (platform sınırı). Ölçüldü: bu ortamda `URL` RN çoklu-dolgusu, kurucu DEĞİL → gerçek karar HEP false
// (SettingsKabinKamerasiYok.T3_Y190 ile aynı) — kabin dalı için açıkça verilir.
let mockBuMakinede = false;
jest.mock("@/services/backendKonumu", () => ({ backendBuMakinede: () => mockBuMakinede }));
let mockHastaNo = 91000;
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: mockKip, hasAiHub: true }) }));
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
import { AI_TIMEOUT_MS } from "@/services/apiClient";
import {
  alanlar, blobMetni, ekraniCiz, etiketeBas, ileti, metneBas, postlar, Sahne, web, webKur, webSok,
} from "./KP3_aiHubWebAparati";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);

interface Modul {
  ad: string;
  kip: "veterinarian" | "researcher";
  uc: string;
  dosya: string;
  baslat: string;
  kamera: boolean;
  kabinli?: boolean;
  ipucu?: string;
}
const MODULLER: Modul[] = [
  { ad: "ai.modul.yuzAgrisi.ad", kip: "veterinarian", uc: "/ai/vision/landmark", dosya: "upload.jpg", baslat: "ai.fgs.analiziBaslat", kamera: true },
  { ad: "ai.modul.kediOrgan.ad", kip: "veterinarian", uc: "/ai/vision/cat_organ", dosya: "cat.jpg", baslat: "ai.organ.analiziBaslat", kamera: true, ipucu: "ai.organ.modelHazirlaniyor" },
  { ad: "ai.modul.fantomTumor.ad", kip: "researcher", uc: "/ai/vision/em_fantom", dosya: "phantom.jpg", baslat: "ai.fantom.analiziBaslat", kamera: true, kabinli: true },
  { ad: "ai.modul.petriKuyu.ad", kip: "researcher", uc: "/ai/vision/em_petri", dosya: "petri.jpg", baslat: "ai.petri.analiziBaslat", kamera: true, kabinli: true },
  { ad: "ai.modul.bobrekCt.ad", kip: "researcher", uc: "/ai/vision/kidney_ct", dosya: "ct.jpg", baslat: "ai.ct.analiziBaslat", kamera: false },
  { ad: "ai.modul.bobrekPatoloji.ad", kip: "researcher", uc: "/ai/vision/histopath", dosya: "histo.jpg", baslat: "ai.patoloji.analiziBaslat", kamera: false, ipucu: "ai.patoloji.modelHazirlaniyor" },
];
const RET = "Görüntü çözünürlüğü yetersiz, yeniden çekin.";

let ozel: (yol: string, govde: unknown, yontem: string) => any = () => undefined;
let s: Sahne;

const foto = (icerik: string) => new File([icerik], "secilen.jpg", { type: "image/jpeg" });
const urller = () => Array.from(web.nesneUrlleri.keys());

beforeEach(() => {
  mockHastaNo += 1;
  ozel = () => undefined;
  webKur((y, g, m) => ozel(y, g, m));
  mockBuMakinede = false;
  s = new Sahne();
});
afterEach(async () => {
  await s.sok();
  jest.useRealTimers();
  webSok();
});

async function moduluAc(m: Modul) {
  mockKip = m.kip;
  await ekraniCiz(s);
  await etiketeBas(s, T(m.ad));
}

async function galeridenSec(icerik: string) {
  web.dosyaSiradaki = foto(icerik);
  await metneBas(s, T("ai.ortak.galeridenSec"));
  await s.bosalt(4);
}

describe.each(MODULLER)("$uc", (m) => {
  it("galeri: image/* seçici (kamera yok) → `file` modülün dosya adıyla gider; ikinci seçimde önceki nesne URL'si bırakılır", async () => {
    await moduluAc(m);
    await galeridenSec("BIR");
    expect(web.acilanSeciciler).toEqual([{ accept: "image/*", capture: null }]);
    const ilkUrl = urller()[0];
    expect(ilkUrl).toBeDefined();
    await galeridenSec("IKI");
    expect(web.serbestBirakilan).toContain(ilkUrl);
    await metneBas(s, T(m.baslat));
    const giden = postlar(m.uc);
    expect(giden).toHaveLength(1);
    const f = alanlar(giden[0].govde).file as File;
    expect(f.name).toBe(m.dosya);
    expect(await blobMetni(f)).toBe("IKI");
  });

  it("sunucu reddi → Türkçe gerekçe ekranda; fetch reddi → 'istek gönderilemedi'", async () => {
    await moduluAc(m);
    await galeridenSec("RED");
    ozel = (y, _g, yon) => (yon === "POST" && y === m.uc ? [422, { detail: RET }] : undefined);
    await metneBas(s, T(m.baslat));
    expect(ileti()).toBe(RET);
    ozel = (y, _g, yon) => (yon === "POST" && y === m.uc ? { hata: new TypeError("Failed to fetch") } : undefined);
    await metneBas(s, T(m.baslat));
    expect(ileti()).toBe(T("ortak.hata.aiGonderilemedi"));
    expect(postlar(m.uc)).toHaveLength(2);
  });

  it("8 sn'yi aşan analizde 'model hazırlanıyor' ipucu; AI_TIMEOUT_MS dolunca istek iptal → zaman aşımı iletisi", async () => {
    await moduluAc(m);
    await galeridenSec("YAVAS");
    let iptalEdildi = false;
    const asili = jest.fn((_u: unknown, init: { signal?: AbortSignal }) => new Promise((_coz, reddet) => {
      init.signal?.addEventListener("abort", () => {
        iptalEdildi = true;
        reddet(Object.assign(new Error("The operation was aborted."), { name: "AbortError" }));
      });
    }));
    const kayitli = global.fetch;
    global.fetch = jest.fn((u: unknown, init: any) => (String(u).includes(m.uc) ? asili(u, init) : (kayitli as any)(u, init))) as any;
    jest.useFakeTimers({ doNotFake: ["queueMicrotask", "nextTick", "Date"] });
    await metneBas(s, T(m.baslat));
    expect(s.metin()).not.toContain(T(m.ipucu ?? "ai.ortak.modelHazirlaniyor"));
    await s.ilerlet(8000);
    expect(s.metin()).toContain(T(m.ipucu ?? "ai.ortak.modelHazirlaniyor"));
    expect(iptalEdildi).toBe(false);
    await s.ilerlet(AI_TIMEOUT_MS);
    await s.bosalt(6);
    expect(iptalEdildi).toBe(true);
    expect(ileti()).toBe(T("ortak.hata.aiZamanAsimi"));
    expect(s.metin()).not.toContain(T(m.ipucu ?? "ai.ortak.modelHazirlaniyor"));
  });
});

describe.each(MODULLER.filter((m) => m.kamera))("$uc · kamera", (m) => {
  it("backend UZAK makinede: 'Fotoğraf Çek' arka kamera seçicisini açar; çekilen kare analize gider", async () => {
    await moduluAc(m);
    web.dosyaSiradaki = foto("KAMERA");
    await metneBas(s, T("ai.gorsel.fotografCek"));
    await s.bosalt(4);
    expect(web.acilanSeciciler).toEqual([{ accept: "image/*", capture: "environment" }]);
    await metneBas(s, T(m.baslat));
    const f = alanlar(postlar(m.uc)[0].govde).file as File;
    expect(await blobMetni(f)).toBe("KAMERA");
  });
});

describe.each(MODULLER.filter((m) => m.kabinli))("$uc · kabin kamerası (backend bu makinede)", (m) => {
  it("'Fotoğraf Çek' kabin karesini alır (seçici AÇILMAZ); kare JPEG olarak gider; önceki galeri URL'si bırakılır", async () => {
    mockBuMakinede = true;
    ozel = (y, _g, yon) => (yon === "POST" && y === "/settings/kabin-kamerasi/kare" ? [200, { image_base64: btoa("KABINKARESI") }] : undefined);
    await moduluAc(m);
    await galeridenSec("GALERI");
    const galeriUrl = urller()[0];
    await metneBas(s, T("ai.gorsel.fotografCek"));
    expect(web.acilanSeciciler).toHaveLength(1); // yalnız galeri — kamera seçicisi açılmadı
    expect(postlar("/settings/kabin-kamerasi/kare")).toHaveLength(1);
    expect(web.serbestBirakilan).toContain(galeriUrl);
    await metneBas(s, T(m.baslat));
    const f = alanlar(postlar(m.uc)[0].govde).file as File;
    expect(f.type).toBe("image/jpeg");
    expect(f.name).toBe(m.dosya);
    expect(await blobMetni(f)).toBe("KABINKARESI");
  });

  it("kabin kamerası reddederse sunucunun eylem metni gösterilir, analiz isteği gitmez", async () => {
    mockBuMakinede = true;
    const EYLEM = "Kabin kamerası AI Pro'da kullanılıyor; önce orada durdurun.";
    ozel = (y, _g, yon) => (yon === "POST" && y === "/settings/kabin-kamerasi/kare" ? [409, { detail: EYLEM }] : undefined);
    await moduluAc(m);
    await metneBas(s, T("ai.gorsel.fotografCek"));
    expect(ileti()).toBe(EYLEM);
    expect(postlar(m.uc)).toHaveLength(0);
  });
});
