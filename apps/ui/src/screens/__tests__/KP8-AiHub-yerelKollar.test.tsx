/**
 * KP-8 · src/screens/AiHubScreen.tsx · YEREL (native) kalan dallar — düzenek KP2_AiHub_yerelGirdi'den AYNEN (sahte en alt katta).
 * Sözleşmeler:
 *  1) Yerel seçici (görüntü kitaplığı / kamera / belge) VAZGEÇİLİRSE hiçbir modülde girdi OLUŞMAZ: küçültücü çağrılmaz, "seçilmedi" yer
 *     tutucusu durur, analiz ucuna istek gitmez.
 *  2) GENİŞ içerik düzeninde (masaüstü / tablet yatay) görüntü modüllerinin girdi düğmeleri YAN YANA eşit pay alır (flex 1); dar
 *     düzende alt alta tam genişlik.
 * SAHTE: KP2 ile aynı + düzen kancası (`useResponsive`) — yalnız `isCompact` testte geniş yapılır, geri kalanı gerçek.
 */
const mockDuzen = { genis: false };
jest.mock("@/hooks/useResponsive", () => {
  const gercek = jest.requireActual("@/hooks/useResponsive");
  return { useResponsive: () => ({ ...gercek.useResponsive(), ...(mockDuzen?.genis ? { isCompact: false } : {}) }) };
});
let mockMode: "veterinarian" | "researcher" | "pet_owner" = "veterinarian";
let mockHastaNo = 71000;
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ userMode: mockMode, hasAiHub: mockMode !== "pet_owner" }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({
  useOperator: () => ({ operatorEmail: "v@x.com" }),
  useOperatorOptional: () => ({ operatorEmail: "v@x.com", operators: [] }),
}));
jest.mock("@/context/EntitlementContext", () => ({ useEntitlement: () => ({ research: true, realtime: false }) }));
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({
    navigate: jest.fn(), navigateTo: jest.fn(), setAiProModeli: jest.fn(),
    selectedPatient: { id: `kp2y-${mockHastaNo}`, name: `KP2Y-${mockHastaNo}` },
  }),
}));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionFresh: false }),
}));
jest.mock("@/components/domain/PatientGate", () => {
  const React = require("react");
  return { PatientGate: ({ children }: any) => React.createElement(React.Fragment, null, children) };
});
const mockKamera = {
  izinli: true,
  izinIste: jest.fn(async () => ({ granted: false })),
};
jest.mock("expo-camera", () => ({
  CameraView: () => null,
  useCameraPermissions: () => [{ granted: mockKamera.izinli }, mockKamera.izinIste],
}));
const mockKaydedici = {
  record: jest.fn(),
  stop: jest.fn(async () => undefined),
  prepareToRecordAsync: jest.fn(async () => undefined),
  uri: "file:///kayit-yerel.m4a" as string | null,
};
jest.mock("expo-audio", () => ({
  useAudioRecorder: () => mockKaydedici,
  RecordingPresets: { HIGH_QUALITY: {} },
  setAudioModeAsync: jest.fn(async () => undefined),
  requestRecordingPermissionsAsync: jest.fn(async () => ({ granted: true })),
}));
jest.mock("expo-image-picker", () => ({
  MediaTypeOptions: { Images: "Images" },
  launchImageLibraryAsync: jest.fn(),
  launchCameraAsync: jest.fn(),
}));
jest.mock("expo-image-manipulator", () => ({ SaveFormat: { JPEG: "jpeg" }, manipulateAsync: jest.fn() }));
jest.mock("expo-document-picker", () => ({ getDocumentAsync: jest.fn() }));
jest.mock("expo-file-system/legacy", () => ({ readAsStringAsync: jest.fn(async () => "U0VTNjQ=") }));

import React from "react";
import { StyleSheet } from "react-native";
import { act, fireEvent, render } from "@testing-library/react-native";
import i18n from "i18next";
import * as ImagePicker from "expo-image-picker";
import * as ImageManipulator from "expo-image-manipulator";
import * as DocumentPicker from "expo-document-picker";
import * as FileSystemLegacy from "expo-file-system/legacy";
import * as Audio from "expo-audio";

import { AiHubScreen } from "@/screens/AiHubScreen";
import { ToastProvider } from "@/components/ui/ToastProvider";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);

type Istek = { yol: string; init: { method?: string; body?: any } };
let istekler: Istek[] = [];
let mockYanitlar: Record<string, () => unknown> = {};
const yanit = (veri: unknown, durum = 200) => ({
  ok: durum < 400, status: durum, json: async () => veri, text: async () => JSON.stringify(veri),
  headers: { get: () => "application/json" },
});

/** RN FormData parçaları (`_parts`) → [ad, değer] listesi. */
function parcalar(govde: any): [string, any][] {
  return Array.isArray(govde?._parts) ? (govde._parts as [string, any][]) : [];
}
/** RN'nin GERÇEK çok parçalı serileştiricisinin (`getParts`) `file` parçası — cihazda telden giden başlıklar. */
function dosyaParcasi(govde: any): any {
  return typeof govde?.getParts === "function" ? govde.getParts().find((p: any) => p.fieldName === "file") : undefined;
}

// ⚠️ Jest'in node ortamındaki küresel `FormData` (undici) RN dosya nesnesini "[object Object]" dizgesine çevirir (ölçüldü) — cihazdaki
// davranış DEĞİL. Platform katı en altta: RN'nin kendi FormData sınıfı (cihazda çalışan) küresele konur, sonda geri alınır.
const RNFormData = jest.requireActual("react-native/Libraries/Network/FormData").default;
let eskiFormData: unknown;
beforeAll(() => {
  eskiFormData = (global as any).FormData;
  (global as any).FormData = RNFormData;
});
afterAll(() => {
  (global as any).FormData = eskiFormData;
});
function postlar(yol: string): Istek[] {
  return istekler.filter((i) => i.yol === yol && (i.init.method || "GET") === "POST");
}

// Ürünün `Button`'ı aynı etiketin 400 ms içindeki ikinci basışını yutar (Date.now) → testler saati ileri alır (gerçek bekleme YOK).
let kayma = 0;
const gercekSimdi = Date.now.bind(Date);
function saatiIlerlet() {
  kayma += 1000;
}

beforeEach(() => {
  mockDuzen.genis = false;
  mockMode = "veterinarian";
  mockHastaNo += 1;
  mockKamera.izinli = true;
  mockKamera.izinIste.mockReset().mockResolvedValue({ granted: false });
  mockKaydedici.record.mockReset();
  mockKaydedici.stop.mockReset().mockResolvedValue(undefined);
  mockKaydedici.prepareToRecordAsync.mockReset().mockResolvedValue(undefined);
  mockKaydedici.uri = "file:///kayit-yerel.m4a";
  (Audio.setAudioModeAsync as jest.Mock).mockReset().mockResolvedValue(undefined);
  (Audio.requestRecordingPermissionsAsync as jest.Mock).mockReset().mockResolvedValue({ granted: true });
  (ImagePicker.launchCameraAsync as jest.Mock).mockReset();
  (ImagePicker.launchImageLibraryAsync as jest.Mock).mockReset();
  (ImageManipulator.manipulateAsync as jest.Mock).mockReset();
  (DocumentPicker.getDocumentAsync as jest.Mock).mockReset();
  (FileSystemLegacy.readAsStringAsync as jest.Mock).mockReset().mockResolvedValue("U0VTNjQ=");
  istekler = [];
  mockYanitlar = {};
  kayma = 0;
  jest.spyOn(Date, "now").mockImplementation(() => gercekSimdi() + kayma);
  global.fetch = jest.fn(async (url: unknown, init: any = {}) => {
    const yol = String(url).replace(/^[a-z]+:\/\/[^/]+/i, "").replace(/^\/api/, "");
    istekler.push({ yol, init });
    const f = mockYanitlar[yol.split("?")[0]];
    if (f) return f();
    if (yol.startsWith("/ai/log")) return yanit({ status: "success", data: [] });
    return yanit({});
  }) as unknown as typeof fetch;
});
afterEach(() => {
  (Date.now as unknown as jest.SpyInstance).mockRestore?.();
});

async function bosalt(n = 6) {
  for (let i = 0; i < n; i++) await act(async () => { await Promise.resolve(); });
}

function ciz() {
  return render(
    <ToastProvider>
      <AiHubScreen />
    </ToastProvider>,
  );
}

/** Düğmeye bas. Aynı metin ipucu satırında da geçebilir (Kedi Organ: "… **Fotoğraf Çek** …") → düğme EN SONDAKİ eşleşmedir. */
async function bas(u: ReturnType<typeof render>, metin: string) {
  saatiIlerlet();
  const hepsi = u.getAllByText(metin);
  await act(async () => { fireEvent.press(hepsi[hepsi.length - 1]); });
  await bosalt();
}

async function moduluAc(u: ReturnType<typeof render>, ad: string) {
  await act(async () => { fireEvent.press(u.getAllByLabelText(ad)[0]); });
  await bosalt();
}


type Secici = "kitaplik" | "kamera" | "belge";
const IPTAL: { ad: string; mod: "veterinarian" | "researcher" | "pet_owner"; modul: string | null; dugme: string; secici: Secici;
  yer: string; uc: string }[] = [
  { ad: "FGS galeri", mod: "veterinarian", modul: "ai.modul.yuzAgrisi.ad", dugme: "ai.ortak.galeridenSec", secici: "kitaplik",
    yer: "ai.ortak.goruntuSecilmedi", uc: "/ai/vision/landmark" },
  { ad: "FGS kamera", mod: "veterinarian", modul: "ai.modul.yuzAgrisi.ad", dugme: "ai.gorsel.fotografCek", secici: "kamera",
    yer: "ai.ortak.goruntuSecilmedi", uc: "/ai/vision/landmark" },
  { ad: "Fantom galeri", mod: "researcher", modul: "ai.modul.fantomTumor.ad", dugme: "ai.ortak.galeridenSec", secici: "kitaplik",
    yer: "ai.ortak.goruntuSecilmedi", uc: "/ai/vision/em_fantom" },
  { ad: "Fantom kamera", mod: "researcher", modul: "ai.modul.fantomTumor.ad", dugme: "ai.gorsel.fotografCek", secici: "kamera",
    yer: "ai.ortak.goruntuSecilmedi", uc: "/ai/vision/em_fantom" },
  { ad: "Petri galeri", mod: "researcher", modul: "ai.modul.petriKuyu.ad", dugme: "ai.ortak.galeridenSec", secici: "kitaplik",
    yer: "ai.ortak.goruntuSecilmedi", uc: "/ai/vision/em_petri" },
  { ad: "Petri kamera", mod: "researcher", modul: "ai.modul.petriKuyu.ad", dugme: "ai.gorsel.fotografCek", secici: "kamera",
    yer: "ai.ortak.goruntuSecilmedi", uc: "/ai/vision/em_petri" },
  { ad: "Böbrek CT galeri", mod: "researcher", modul: "ai.modul.bobrekCt.ad", dugme: "ai.ortak.galeridenSec", secici: "kitaplik",
    yer: "ai.ortak.goruntuSecilmedi", uc: "/ai/vision/kidney_ct" },
  { ad: "Böbrek Patoloji galeri", mod: "researcher", modul: "ai.modul.bobrekPatoloji.ad", dugme: "ai.ortak.galeridenSec", secici: "kitaplik",
    yer: "ai.ortak.goruntuSecilmedi", uc: "/ai/vision/histopath" },
  { ad: "Kedi Organ galeri", mod: "veterinarian", modul: "ai.modul.kediOrgan.ad", dugme: "ai.ortak.galeridenSec", secici: "kitaplik",
    yer: "ai.ortak.goruntuSecilmedi", uc: "/ai/vision/cat_organ" },
  { ad: "Kedi Sesi belge", mod: "veterinarian", modul: "ai.modul.kediSesi.ad", dugme: "ai.ses.sesYukle", secici: "belge",
    yer: "ai.ses.sesSecilmedi", uc: "/ai/sound/cat" },
  { ad: "Böbrek RNA belge", mod: "researcher", modul: "ai.modul.bobrekRna.ad", dugme: "ai.rna.csvSec", secici: "belge",
    yer: "ai.rna.csvSec", uc: "/ai/rna/kidney" },
  { ad: "Ev sahibi galeri", mod: "pet_owner", modul: null, dugme: "ai.ortak.galeridenSec", secici: "kitaplik",
    yer: "ai.hayvanSahibi.kamerayiAc", uc: "/ai/vision/landmark" },
];

describe("yerel seçici vazgeçilirse girdi oluşmaz (her modül)", () => {
  it.each(IPTAL)("$ad: vazgeç → küçültücü çağrılmaz, yer tutucu durur, istek gitmez", async (d) => {
    mockMode = d.mod;
    (ImagePicker.launchImageLibraryAsync as jest.Mock).mockResolvedValue({ canceled: true, assets: [] });
    (ImagePicker.launchCameraAsync as jest.Mock).mockResolvedValue({ canceled: true, assets: [] });
    (DocumentPicker.getDocumentAsync as jest.Mock).mockResolvedValue({ canceled: true, assets: [] });
    const u = ciz();
    if (d.modul) await moduluAc(u, T(d.modul));
    const once = istekler.length;
    await bas(u, T(d.dugme));
    const cagrilan = { kitaplik: ImagePicker.launchImageLibraryAsync, kamera: ImagePicker.launchCameraAsync, belge: DocumentPicker.getDocumentAsync }[d.secici];
    expect(cagrilan).toHaveBeenCalledTimes(1);
    expect(ImageManipulator.manipulateAsync).not.toHaveBeenCalled();
    expect(FileSystemLegacy.readAsStringAsync).not.toHaveBeenCalled();
    expect(u.getAllByText(T(d.yer)).length).toBeGreaterThan(0);
    expect(istekler.slice(once).filter((i) => !i.yol.startsWith("/ai/log") && !i.yol.startsWith("/jeton"))).toEqual([]);
    expect(postlar(d.uc)).toHaveLength(0);
  });
});

describe("geniş içerik düzeninde girdi düğmeleri yan yana (flex 1), dar düzende alt alta", () => {
  const MODULLER: { ad: string; mod: "veterinarian" | "researcher"; modul: string }[] = [
    { ad: "FGS (görsel modül)", mod: "veterinarian", modul: "ai.modul.yuzAgrisi.ad" },
    { ad: "Fantom", mod: "researcher", modul: "ai.modul.fantomTumor.ad" },
    { ad: "Petri", mod: "researcher", modul: "ai.modul.petriKuyu.ad" },
    { ad: "Kedi Organ", mod: "veterinarian", modul: "ai.modul.kediOrgan.ad" },
  ];
  /** Düğme metninin en yakın "pay" kabı: stili flex 1 YA DA width 100% olan ata. */
  function payKabi(u: ReturnType<typeof render>, metin: string) {
    const hepsi = u.getAllByText(metin);
    let ata = hepsi[hepsi.length - 1].parent;
    while (ata) {
      const st = StyleSheet.flatten(ata.props.style) || {};
      if (st.flex === 1 || st.width === "100%") return st;
      ata = ata.parent;
    }
    return null;
  }
  it.each(MODULLER)("$ad: geniş → galeri ve kamera düğmesi flex 1; dar → width 100%", async (d) => {
    mockMode = d.mod;
    mockDuzen.genis = true;
    const u = ciz();
    await moduluAc(u, T(d.modul));
    expect(payKabi(u, T("ai.ortak.galeridenSec"))).toEqual(expect.objectContaining({ flex: 1 }));
    expect(payKabi(u, T("ai.gorsel.fotografCek"))).toEqual(expect.objectContaining({ flex: 1 }));
    u.unmount();
    mockDuzen.genis = false;
    const u2 = ciz();
    await moduluAc(u2, T(d.modul));
    expect(payKabi(u2, T("ai.ortak.galeridenSec"))).toEqual(expect.objectContaining({ width: "100%" }));
  });
});
