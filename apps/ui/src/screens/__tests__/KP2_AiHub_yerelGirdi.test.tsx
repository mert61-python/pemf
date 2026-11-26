/**
 * KP-2 · src/screens/AiHubScreen.tsx · YEREL (native, Platform.OS = "ios") girdi yolu sözleşmeleri.
 *
 * Sözleşmeler:
 *  1) Fotoğraf küçültme (`expo-image-manipulator`) BAŞARISIZSA akış KIRILMAZ: analiz isteği ORİJİNAL dosyayı RN çok parçalı `file`
 *     parçası ({ uri, name, type: image/jpeg }) olarak gönderir, `image_base64` alanı GİTMEZ — her görüntü modülünde kendi dosya adıyla.
 *  2) Yerel "Fotoğraf Çek" kamerası modüle özgü seçeneklerle açılır; küçültülmüş kare `image_base64` ile gider; iptal edilen çekim girdi
 *     ÜRETMEZ.
 *  3) Ses kaydı (ev sahibi kartı + Kedi Sesi modülü): mikrofon izni yoksa kayıt BAŞLAMAZ ve izin iletisi görünür; kayıt başlarken ses kipi
 *     ayarlanır, durdurunca "kayıt.m4a" girdi olur; başlatma / durdurma hatası kullanıcıya söylenir. Yüklenen ses dosyası base64 okunup
 *     `audio_base64` ile gider.
 *  4) Canlı kamera izni reddedilirse canlı kip AÇILMAZ ve izin iletisi görünür (görsel modül · fantom · kedi organ).
 * GERÇEK: AiHubScreen + modülleri, ToastProvider (iletiler ekranda), apiClient, korunanFetch. SAHTE (en alt kat): fetch, expo kamera /
 * görüntü seçici / küçültücü / belge seçici / dosya sistemi / ses kaydedici; bağlamlar (profil, hasta, abonelik) sabit girdi.
 */
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

describe("küçültme başarısız → orijinal dosya `file` parçasıyla gider (her görüntü modülü)", () => {
  const DURUMLAR: {
    ad: string; mod: "veterinarian" | "researcher"; modul: string; girdi: "kamera" | "galeri"; dugme: string; uc: string; dosya: string;
  }[] = [
    { ad: "FGS (görsel modül)", mod: "veterinarian", modul: "ai.modul.yuzAgrisi.ad", girdi: "kamera", dugme: "ai.fgs.analiziBaslat",
      uc: "/ai/vision/landmark", dosya: "upload.jpg" },
    { ad: "Fantom", mod: "researcher", modul: "ai.modul.fantomTumor.ad", girdi: "galeri", dugme: "ai.fantom.analiziBaslat",
      uc: "/ai/vision/em_fantom", dosya: "phantom.jpg" },
    { ad: "Petri", mod: "researcher", modul: "ai.modul.petriKuyu.ad", girdi: "galeri", dugme: "ai.petri.analiziBaslat",
      uc: "/ai/vision/em_petri", dosya: "petri.jpg" },
    { ad: "Böbrek CT", mod: "researcher", modul: "ai.modul.bobrekCt.ad", girdi: "galeri", dugme: "ai.ct.analiziBaslat",
      uc: "/ai/vision/kidney_ct", dosya: "ct.jpg" },
    { ad: "Böbrek Patoloji", mod: "researcher", modul: "ai.modul.bobrekPatoloji.ad", girdi: "galeri", dugme: "ai.patoloji.analiziBaslat",
      uc: "/ai/vision/histopath", dosya: "histo.jpg" },
    { ad: "Kedi Organ", mod: "veterinarian", modul: "ai.modul.kediOrgan.ad", girdi: "kamera", dugme: "ai.organ.analiziBaslat",
      uc: "/ai/vision/cat_organ", dosya: "cat.jpg" },
  ];

  it.each(DURUMLAR)("$ad: küçültücü düşerse istek { uri: orijinal, name: $dosya, type: image/jpeg } taşır, image_base64 taşımaz", async (d) => {
    mockMode = d.mod;
    const secim = { canceled: false, assets: [{ uri: "file:///orijinal-buyuk.jpg" }] };
    (ImagePicker.launchCameraAsync as jest.Mock).mockResolvedValue(secim);
    (ImagePicker.launchImageLibraryAsync as jest.Mock).mockResolvedValue(secim);
    (ImageManipulator.manipulateAsync as jest.Mock).mockRejectedValue(new Error("bellek yetersiz"));
    mockYanitlar[d.uc.replace(/^\/api/, "")] = () => yanit({ status: "error", detail: "" }, 500);
    const u = ciz();
    await moduluAc(u, T(d.modul));
    await bas(u, T(d.girdi === "kamera" ? "ai.gorsel.fotografCek" : "ai.ortak.galeridenSec"));
    // ARA: doğru seçici açıldı, küçültme gerçekten denendi (ve düştü)
    expect(ImageManipulator.manipulateAsync).toHaveBeenCalledWith("file:///orijinal-buyuk.jpg", expect.any(Array), expect.any(Object));
    await bas(u, T(d.dugme));
    const giden = postlar(d.uc);
    expect(giden).toHaveLength(1);
    const p = parcalar(giden[0].init.body);
    expect(p.find(([k]) => k === "file")?.[1]).toEqual({ uri: "file:///orijinal-buyuk.jpg", name: d.dosya, type: "image/jpeg" });
    expect(p.some(([k]) => k === "image_base64")).toBe(false);
    // RN serileştiricisi bu parçayı DOSYA olarak yollar (dosya adı + içerik türü başlıkta)
    expect(dosyaParcasi(giden[0].init.body)?.headers).toEqual({
      "content-disposition": `form-data; name="file"; filename="${d.dosya}"`,
      "content-type": "image/jpeg",
    });
  });
});

describe("yerel kamera: modüle özgü seçenekler, base64 kare, iptal", () => {
  it("FGS 'Fotoğraf Çek' → kamera { allowsEditing: true, quality: 0.8, base64: true }; küçük kare image_base64 olarak gider", async () => {
    (ImagePicker.launchCameraAsync as jest.Mock).mockResolvedValue({ canceled: false, assets: [{ uri: "file:///cek.jpg" }] });
    (ImageManipulator.manipulateAsync as jest.Mock).mockResolvedValue({ uri: "file:///cek-kucuk.jpg", base64: "S1VDVUs=" });
    mockYanitlar["/ai/vision/landmark"] = () => yanit({ status: "success", fgs_total: 0, detected: true });
    const u = ciz();
    await moduluAc(u, T("ai.modul.yuzAgrisi.ad"));
    await bas(u, T("ai.gorsel.fotografCek"));
    expect(ImagePicker.launchCameraAsync).toHaveBeenCalledWith({ allowsEditing: true, quality: 0.8, base64: true });
    await bas(u, T("ai.fgs.analiziBaslat"));
    const p = parcalar(postlar("/ai/vision/landmark")[0].init.body);
    expect(p.find(([k]) => k === "image_base64")?.[1]).toBe("S1VDVUs=");
    expect(p.some(([k]) => k === "file")).toBe(false);
  });

  it("Kedi Organ 'Fotoğraf Çek' → kamera { allowsEditing: false, quality: 0.8, base64: true }; iptal edilen çekim girdi üretmez (analiz kapalı)", async () => {
    (ImagePicker.launchCameraAsync as jest.Mock).mockResolvedValue({ canceled: true, assets: [] });
    const u = ciz();
    await moduluAc(u, T("ai.modul.kediOrgan.ad"));
    await bas(u, T("ai.gorsel.fotografCek"));
    expect(ImagePicker.launchCameraAsync).toHaveBeenCalledWith({ allowsEditing: false, quality: 0.8, base64: true });
    expect(ImageManipulator.manipulateAsync).not.toHaveBeenCalled();
    // Görüntü yok → "görüntü seçilmedi" yer tutucusu durur, analiz düğmesi devre dışı
    expect(u.getByText(T("ai.ortak.goruntuSecilmedi"))).toBeTruthy();
    await bas(u, T("ai.organ.analiziBaslat"));
    expect(postlar("/ai/vision/cat_organ")).toHaveLength(0);
  });

  it("Ev sahibi 'Kamerayı Aç' → kamera { allowsEditing: true, quality: 0.7, base64: true }; 'Teşhis Et' küçük kareyi image_base64 ile landmark'a gönderir", async () => {
    mockMode = "pet_owner";
    (ImagePicker.launchCameraAsync as jest.Mock).mockResolvedValue({ canceled: false, assets: [{ uri: "file:///sahip.jpg" }] });
    (ImageManipulator.manipulateAsync as jest.Mock).mockResolvedValue({ uri: "file:///sahip-kucuk.jpg", base64: "U0FISVA=" });
    mockYanitlar["/ai/vision/landmark"] = () => yanit({ status: "success", fgs_total: 0, detected: true });
    const u = ciz();
    await bosalt();
    await bas(u, T("ai.hayvanSahibi.kamerayiAc"));
    expect(ImagePicker.launchCameraAsync).toHaveBeenCalledWith({ allowsEditing: true, quality: 0.7, base64: true });
    await bas(u, T("ai.hayvanSahibi.teshisEt"));
    const p = parcalar(postlar("/ai/vision/landmark")[0].init.body);
    expect(p).toEqual([["image_base64", "U0FISVA="]]);
    expect(u.getByText(T("ai.hayvanSahibi.oneri.agriYok"))).toBeTruthy();
  });

  it("Ev sahibi: küçültme düşerse 'Teşhis Et' { uri, name: camera_capture.jpg, type: image/jpeg } dosyasını gönderir", async () => {
    mockMode = "pet_owner";
    (ImagePicker.launchCameraAsync as jest.Mock).mockResolvedValue({ canceled: false, assets: [{ uri: "file:///sahip-ham.jpg" }] });
    (ImageManipulator.manipulateAsync as jest.Mock).mockRejectedValue(new Error("çözülemedi"));
    mockYanitlar["/ai/vision/landmark"] = () => yanit({ status: "success", fgs_total: 0, detected: true });
    const u = ciz();
    await bosalt();
    await bas(u, T("ai.hayvanSahibi.kamerayiAc"));
    await bas(u, T("ai.hayvanSahibi.teshisEt"));
    const p = parcalar(postlar("/ai/vision/landmark")[0].init.body);
    expect(p).toEqual([["file", { uri: "file:///sahip-ham.jpg", name: "camera_capture.jpg", type: "image/jpeg" }]]);
  });

  it("Ev sahibi: kamera iptal edilirse fotoğraf girdisi oluşmaz ('Teşhis Et' görünmez)", async () => {
    mockMode = "pet_owner";
    (ImagePicker.launchCameraAsync as jest.Mock).mockResolvedValue({ canceled: true, assets: [] });
    const u = ciz();
    await bosalt();
    await bas(u, T("ai.hayvanSahibi.kamerayiAc"));
    expect(ImageManipulator.manipulateAsync).not.toHaveBeenCalled();
    expect(u.queryByText(T("ai.hayvanSahibi.teshisEt"))).toBeNull();
  });
});

describe("ses kaydı (ev sahibi kartı ve Kedi Sesi modülü)", () => {
  const KARTLAR: { ad: string; mod: "pet_owner" | "veterinarian"; analiz: string }[] = [
    { ad: "ev sahibi kartı", mod: "pet_owner", analiz: "ai.ses.sesiAnalizEt" },
    { ad: "Kedi Sesi modülü", mod: "veterinarian", analiz: "ai.ses.analiziBaslat" },
  ];

  async function kartiAc(mod: "pet_owner" | "veterinarian") {
    mockMode = mod;
    const u = ciz();
    await bosalt();
    if (mod === "veterinarian") await moduluAc(u, T("ai.modul.kediSesi.ad"));
    return u;
  }

  it.each(KARTLAR)("$ad: mikrofon izni yoksa kayıt BAŞLAMAZ ve izin iletisi görünür", async (k) => {
    (Audio.requestRecordingPermissionsAsync as jest.Mock).mockResolvedValue({ granted: false });
    const u = await kartiAc(k.mod);
    await bas(u, T("ai.ses.kaydet"));
    expect(u.getByText(T("ai.ses.mikrofonIzni"))).toBeTruthy();
    expect(Audio.setAudioModeAsync).not.toHaveBeenCalled();
    expect(mockKaydedici.record).not.toHaveBeenCalled();
    expect(u.queryByText(T("ai.ses.durdur"))).toBeNull();
  });

  it.each(KARTLAR)("$ad: kayıt ses kipini ayarlayıp başlar; Durdur → 'kayıt.m4a' girdi olur ve base64 okunup audio_base64 ile gider", async (k) => {
    mockYanitlar["/ai/sound/cat"] = () => yanit({ status: "success", top_1_class: "Happy", top_1_prob: 0.9, top_k: [], guvenilir: true });
    const u = await kartiAc(k.mod);
    await bas(u, T("ai.ses.kaydet"));
    expect(Audio.setAudioModeAsync).toHaveBeenCalledWith({ playsInSilentMode: true, allowsRecording: true });
    expect(mockKaydedici.prepareToRecordAsync).toHaveBeenCalledTimes(1);
    expect(mockKaydedici.record).toHaveBeenCalledTimes(1);
    expect(u.getByText(T("ai.ses.kaydediliyor"))).toBeTruthy();
    await bas(u, T("ai.ses.durdur"));
    expect(mockKaydedici.stop).toHaveBeenCalledTimes(1);
    expect(u.getByText("🎵 kayıt.m4a")).toBeTruthy();
    await bas(u, T(k.analiz));
    expect(FileSystemLegacy.readAsStringAsync).toHaveBeenCalledWith("file:///kayit-yerel.m4a", { encoding: "base64" });
    expect(parcalar(postlar("/ai/sound/cat")[0].init.body)).toEqual([["audio_base64", "U0VTNjQ="]]);
  });

  it.each(KARTLAR)("$ad: kaydedici başlatılamazsa 'kayıt başlatılamadı' iletisi görünür, kayıt kipine geçilmez", async (k) => {
    mockKaydedici.prepareToRecordAsync.mockRejectedValue(new Error("mikrofon meşgul"));
    const u = await kartiAc(k.mod);
    await bas(u, T("ai.ses.kaydet"));
    expect(u.getByText(T("ai.ses.kayitBaslatilamadi"))).toBeTruthy();
    expect(mockKaydedici.record).not.toHaveBeenCalled();
    expect(u.queryByText(T("ai.ses.kaydediliyor"))).toBeNull();
  });

  it.each(KARTLAR)("$ad: kaydedici durdurulamazsa 'kayıt durdurulamadı' iletisi görünür ve kayıt girdisi oluşmaz", async (k) => {
    mockKaydedici.stop.mockRejectedValue(new Error("durmadı"));
    const u = await kartiAc(k.mod);
    await bas(u, T("ai.ses.kaydet"));
    await bas(u, T("ai.ses.durdur"));
    expect(u.getByText(T("ai.ses.kayitDurdurulamadi"))).toBeTruthy();
    expect(u.queryByText("🎵 kayıt.m4a")).toBeNull();
    expect(u.queryByText(T("ai.ses.kaydediliyor"))).toBeNull(); // kayıt kipinden çıkıldı (düğme tekrar "Kaydet")
    expect(u.getByText(T("ai.ses.kaydet"))).toBeTruthy();
  });

  it("ev sahibi kartı: 'Ses Yükle' belge seçicisi { type: [audio/*], copyToCacheDirectory: true } ile açılır; seçilen dosya adı görünür ve base64 gider", async () => {
    (DocumentPicker.getDocumentAsync as jest.Mock).mockResolvedValue({
      canceled: false, assets: [{ uri: "file:///miyav.mp3", name: "miyav.mp3" }],
    });
    mockYanitlar["/ai/sound/cat"] = () => yanit({ status: "success", top_1_class: "Resting", top_1_prob: 0.8, top_k: [], guvenilir: true });
    const u = await kartiAc("pet_owner");
    await bas(u, T("ai.ses.sesYukle"));
    expect(DocumentPicker.getDocumentAsync).toHaveBeenCalledWith({ type: ["audio/*"], copyToCacheDirectory: true });
    expect(u.getByText("🎵 miyav.mp3")).toBeTruthy();
    await bas(u, T("ai.ses.sesiAnalizEt"));
    expect(FileSystemLegacy.readAsStringAsync).toHaveBeenCalledWith("file:///miyav.mp3", { encoding: "base64" });
    expect(parcalar(postlar("/ai/sound/cat")[0].init.body)).toEqual([["audio_base64", "U0VTNjQ="]]);
    expect(u.getByText(T("ai.ses.oneri.sakin.baslik"))).toBeTruthy();
  });

  it("ev sahibi kartı: belge seçici iptal edilirse ses girdisi oluşmaz (analiz düğmesi işlemez)", async () => {
    (DocumentPicker.getDocumentAsync as jest.Mock).mockResolvedValue({ canceled: true, assets: [] });
    const u = await kartiAc("pet_owner");
    await bas(u, T("ai.ses.sesYukle"));
    expect(u.getByText(T("ai.ses.kayitYok"))).toBeTruthy();
    await bas(u, T("ai.ses.sesiAnalizEt"));
    expect(postlar("/ai/sound/cat")).toHaveLength(0);
  });
});

describe("canlı kamera izni reddedilirse canlı kip açılmaz", () => {
  const DURUMLAR: { ad: string; mod: "veterinarian" | "researcher"; modul: string; ileti: string }[] = [
    { ad: "görsel modül (FGS)", mod: "veterinarian", modul: "ai.modul.yuzAgrisi.ad", ileti: "ai.canli.kameraIzni" },
    { ad: "fantom (cihaz kamerası)", mod: "researcher", modul: "ai.modul.fantomTumor.ad", ileti: "ai.canli.kameraIzni" },
    { ad: "kedi organ", mod: "veterinarian", modul: "ai.modul.kediOrgan.ad", ileti: "ai.organ.canliKameraIzni" },
  ];
  it.each(DURUMLAR)("$ad: izin isteği reddedilir → izin iletisi, düğme 'Canlı Kamera' kalır", async (d) => {
    mockMode = d.mod;
    mockKamera.izinli = false;
    const u = ciz();
    await moduluAc(u, T(d.modul));
    await bas(u, T("ai.gorsel.canliKamera"));
    expect(mockKamera.izinIste).toHaveBeenCalledTimes(1);
    expect(u.getByText(T(d.ileti))).toBeTruthy();
    expect(u.queryByText(T("ai.gorsel.canliyiDurdur"))).toBeNull();
    expect(u.getAllByText(T("ai.gorsel.canliKamera")).length).toBeGreaterThan(0);
  });
});
