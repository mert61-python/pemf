/**
 * @jest-environment jsdom
 */
/**
 * KP-2 · src/screens/AiHubScreen.tsx · EV SAHİBİ (pet_owner) ekranı — WEB sözleşmeleri.
 *
 * Sözleşmeler:
 *  1) "Kamerayı Aç" (web): arka kamerayı isteyen seçici açılır (`accept=image/*`, `capture=environment`); seçilen fotoğraf "Teşhis Et"
 *     ile `/ai/vision/landmark`'a çok parçalı `file` olarak GİDER.
 *  2) Sunucu reddi → sunucunun Türkçe gerekçesi ekranda; fetch reddi → "istek gönderilemedi" iletisi (ham hata metni yok).
 *  3) Şiddetli ağrı (FGS > 5): "VETERİNER HEKİMİNİZE BAŞVURUN" önerisi + "Veteriner Kliniğini Ara": hesap profilindeki klinik telefonu,
 *     yoksa eski yerel kayıt, boşluksuz `tel:` adresiyle aranır; hiçbiri yoksa "Klinik telefonu ayarlı değil" uyarısı.
 *  4) Ses kartı: sunucu reddi "Analiz sırasında hata oluştu."; Error OLMAYAN ret "Hata: <ileti>" (sınıflandırılamayan hata metni kırpılıp
 *     gösterilir).
 *  5) Web'de dosya nesnesi YOKKEN (eski web görüntü seçicisi base64 / data: URI verir — platform katı çekim anında "ios" yapılarak
 *     üretilir): base64 → `image/jpeg` Blob; `data:` URI → kendi MIME türüyle Blob; ikisi de yoksa istek GİTMEZ ve hata iletisi görünür.
 * GERÇEK: AiHubScreen, ToastProvider, apiClient, korunanFetch. SAHTE (en alt kat): fetch, dosya seçici, URL nesne-URL'leri, Linking, alert,
 * expo modülleri; bağlamlar sabit girdi.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
// KP-3 ÖLÇÜM: KP-2 taslağı burada "Test suite failed to run" ile kırmızıydı — gerçek ToastProvider `react-native-safe-area-context`i
// çeker; onun yerel özelliği (NativeSafeAreaContext) react-native-web altında TurboModuleRegistry bulamaz. Platform sınırı → sıfır inset.
jest.mock("react-native-safe-area-context", () => {
  const R = require("react");
  const { View } = require("react-native-web");
  return {
    useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
    SafeAreaProvider: ({ children }: { children?: unknown }) => children,
    SafeAreaView: ({ children, style }: { children?: unknown; style?: unknown }) => R.createElement(View, { style }, children),
  };
});
let mockHastaNo = 81000;
let mockOturum: { email: string; profile?: { clinic_phone?: string } } = { email: "sahip@ev.com" };
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: "pet_owner", hasAiHub: false }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: mockOturum }) }));
jest.mock("@/context/OperatorContext", () => ({
  useOperator: () => ({ operatorEmail: "sahip@ev.com" }),
  useOperatorOptional: () => ({ operatorEmail: "sahip@ev.com", operators: [] }),
}));
jest.mock("@/context/EntitlementContext", () => ({ useEntitlement: () => ({ research: false, realtime: false }) }));
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigate: jest.fn(), selectedPatient: { id: `kp2e-${mockHastaNo}`, name: `Mia-${mockHastaNo}` } }),
}));
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionFresh: false }) }));
jest.mock("@/components/domain/PatientGate", () => {
  const React = require("react");
  return { PatientGate: ({ children }: any) => React.createElement(React.Fragment, null, children) };
});
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

import { act } from "react";
import i18n from "i18next";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { aiZamanAsimiMesaji } from "@/services/apiClient";
import * as ImagePicker from "expo-image-picker";
import * as ImageManipulator from "expo-image-manipulator";
import {
  alanlar, blobMetni, ekraniCiz, ileti, metneBas, postlar, Sahne, saatiIlerlet, web, webKur, webSok,
} from "./KP3_aiHubWebAparati";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
// eslint-disable-next-line @typescript-eslint/no-var-requires
const RNW = require("react-native");

let ozel: (yol: string, govde: unknown, yontem: string) => any = () => undefined;
let s: Sahne;
let linkYamasi: jest.SpyInstance;
let alertYamasi: jest.SpyInstance;

beforeEach(async () => {
  mockHastaNo += 1;
  mockOturum = { email: "sahip@ev.com" };
  ozel = () => undefined;
  webKur((y, g, m) => ozel(y, g, m));
  (ImagePicker.launchImageLibraryAsync as jest.Mock).mockReset();
  (ImageManipulator.manipulateAsync as jest.Mock).mockReset();
  linkYamasi = jest.spyOn(RNW.Linking, "openURL").mockResolvedValue(true);
  alertYamasi = jest.spyOn(window, "alert").mockImplementation(() => undefined);
  await AsyncStorage.clear();
  s = new Sahne();
});
afterEach(async () => {
  await s.sok();
  linkYamasi.mockRestore();
  alertYamasi.mockRestore();
  RNW.Platform.OS = "web";
  webSok();
});

const FOTO = new File([new Uint8Array([70, 79, 84, 79])], "kedi.jpg", { type: "image/jpeg" });

async function fotografCekVeTeshis() {
  web.dosyaSiradaki = FOTO;
  await metneBas(s, T("ai.hayvanSahibi.kamerayiAc"));
  await metneBas(s, T("ai.hayvanSahibi.teshisEt"));
}

describe("web kamerası ve teşhis isteği", () => {
  it("'Kamerayı Aç' → arka kamera seçicisi (image/*, capture=environment); seçilen fotoğraf landmark'a `file` olarak gider", async () => {
    ozel = (y, _g, m) => (m === "POST" && y === "/ai/vision/landmark" ? [200, { status: "success", detected: true, fgs_total: 2 }] : undefined);
    await ekraniCiz(s);
    await fotografCekVeTeshis();
    expect(web.acilanSeciciler).toEqual([{ accept: "image/*", capture: "environment" }]);
    const giden = postlar("/ai/vision/landmark");
    expect(giden).toHaveLength(1);
    const f = alanlar(giden[0].govde).file as File;
    expect(await blobMetni(f)).toBe("FOTO");
    expect(f.name).toBe("camera_capture.jpg");
    expect(s.metin()).toContain(T("ai.hayvanSahibi.oneri.hafif"));
  });

  it("sunucu reddi (422 + Türkçe gerekçe) → gerekçe ekranda, öneri kutusu çizilmez", async () => {
    ozel = (y, _g, m) =>
      m === "POST" && y === "/ai/vision/landmark" ? [422, { detail: "Görüntü çözünürlüğü yetersiz, yeniden çekin." }] : undefined;
    await ekraniCiz(s);
    await fotografCekVeTeshis();
    expect(ileti()).toBe("Görüntü çözünürlüğü yetersiz, yeniden çekin.");
    expect(s.metin()).not.toContain(T("ai.hayvanSahibi.sonucBaslik"));
  });

  it("fetch reddi (TypeError: Failed to fetch) → 'istek gönderilemedi' iletisi, analiz kaydı yazılmaz", async () => {
    ozel = (y, _g, m) => (m === "POST" && y === "/ai/vision/landmark" ? { hata: new TypeError("Failed to fetch") } : undefined);
    await ekraniCiz(s);
    await fotografCekVeTeshis();
    expect(ileti()).toBe(T("ortak.hata.aiGonderilemedi"));
    expect(postlar("/ai/log")).toHaveLength(0);
  });
});

describe("şiddetli ağrı → klinik araması", () => {
  async function siddetliSonuc() {
    ozel = (y, _g, m) => (m === "POST" && y === "/ai/vision/landmark" ? [200, { status: "success", detected: true, fgs_total: 7 }] : undefined);
    await ekraniCiz(s);
    await fotografCekVeTeshis();
    expect(s.metin()).toContain("7 / 10");
    expect(s.metin()).toContain(T("ai.hayvanSahibi.oneri.siddetli"));
  }

  it("profilde klinik telefonu varsa boşluksuz tel: adresi açılır", async () => {
    mockOturum = { email: "sahip@ev.com", profile: { clinic_phone: "0532 111 22 33" } };
    await siddetliSonuc();
    await metneBas(s, T("ai.hayvanSahibi.klinigiAra"));
    expect(linkYamasi).toHaveBeenCalledWith("tel:05321112233");
    expect(alertYamasi).not.toHaveBeenCalled();
  });

  it("profilde yoksa eski yerel kayıttaki ('pemf_clinic_phone') telefon aranır", async () => {
    await AsyncStorage.setItem("pemf_clinic_phone", "0 212 555 00 00");
    await siddetliSonuc();
    await metneBas(s, T("ai.hayvanSahibi.klinigiAra"));
    expect(linkYamasi).toHaveBeenCalledWith("tel:02125550000");
  });

  it("hiçbir yerde telefon yoksa arama YAPILMAZ, 'Klinik telefonu ayarlı değil' uyarısı gösterilir", async () => {
    await siddetliSonuc();
    await metneBas(s, T("ai.hayvanSahibi.klinigiAra"));
    expect(linkYamasi).not.toHaveBeenCalled();
    expect(alertYamasi).toHaveBeenCalledWith(
      `${T("ai.hayvanSahibi.klinikTelefonuYokBaslik")}\n${T("ai.hayvanSahibi.klinikTelefonuYokGovde")}`,
    );
  });
});

// ── KP-7 B (işlev ölçüsü): yanıtsız sunucu ve açılamayan arama ─────────────────────────────────────────────────────────────────
describe("KP-7 B · ev sahibi — askıdaki analiz ve açılamayan arama", () => {
  afterEach(() => jest.useRealTimers());

  it("teşhis askıda kalırsa 8 sn sonra 'model hazırlanıyor' ipucu; 120 sn sonra istek kesilir → zaman aşımı iletisi, ipucu kalkar", async () => {
    jest.useFakeTimers();
    ozel = (y, _g, m) => (m === "POST" && y === "/ai/vision/landmark" ? { askida: true } : undefined);
    await ekraniCiz(s);
    await fotografCekVeTeshis();
    await act(async () => { jest.advanceTimersByTime(7999); });
    expect(s.metin()).not.toContain(T("ai.hayvanSahibi.modelHazirlaniyor"));
    await act(async () => { jest.advanceTimersByTime(1); });
    expect(s.metin()).toContain(T("ai.hayvanSahibi.modelHazirlaniyor"));
    await act(async () => { jest.advanceTimersByTime(112_000); });
    await s.bosalt(8);
    expect(ileti()).toBe(aiZamanAsimiMesaji());
    expect(s.metin()).not.toContain(T("ai.hayvanSahibi.modelHazirlaniyor"));
    expect(postlar("/ai/log")).toHaveLength(0);
  });

  it("ses analizi askıda kalırsa 120 sn sonra istek kesilir → zaman aşımı iletisi", async () => {
    jest.useFakeTimers();
    ozel = (y, _g, m) => (m === "POST" && y === "/ai/sound/cat" ? { askida: true } : undefined);
    await ekraniCiz(s);
    web.dosyaSiradaki = new File([new Uint8Array([1, 2, 3])], "miyav.wav", { type: "audio/wav" });
    await metneBas(s, T("ai.ses.sesYukle"));
    await metneBas(s, T("ai.ses.sesiAnalizEt"));
    expect(postlar("/ai/sound/cat")).toHaveLength(1);
    await act(async () => { jest.advanceTimersByTime(119_999); });
    expect(ileti()).toBeNull();
    await act(async () => { jest.advanceTimersByTime(1); });
    await s.bosalt(8);
    expect(ileti()).toBe(aiZamanAsimiMesaji());
  });

  it("klinik araması açılamazsa (tel: desteklenmiyor) uygulama düşmez, uyarı ya da hata iletisi çıkmaz", async () => {
    mockOturum = { email: "sahip@ev.com", profile: { clinic_phone: "0532 111 22 33" } };
    linkYamasi.mockRejectedValueOnce(new Error("tel: desteklenmiyor"));
    ozel = (y, _g, m) => (m === "POST" && y === "/ai/vision/landmark" ? [200, { status: "success", detected: true, fgs_total: 7 }] : undefined);
    await ekraniCiz(s);
    await fotografCekVeTeshis();
    await metneBas(s, T("ai.hayvanSahibi.klinigiAra"));
    expect(linkYamasi).toHaveBeenCalledWith("tel:05321112233");
    expect(alertYamasi).not.toHaveBeenCalled();
    expect(ileti()).toBeNull();
  });
});

describe("ses kartı hata yolları", () => {
  async function sesYukleVeAnaliz() {
    await ekraniCiz(s);
    web.dosyaSiradaki = new File([new Uint8Array([1, 2, 3])], "miyav.wav", { type: "audio/wav" });
    await metneBas(s, T("ai.ses.sesYukle"));
    await metneBas(s, T("ai.ses.sesiAnalizEt"));
  }

  it("sunucu 500 (gerekçesiz) → 'Analiz sırasında hata oluştu.'; yorum kartı çizilmez", async () => {
    ozel = (y, _g, m) => (m === "POST" && y === "/ai/sound/cat" ? [500, { status: "error" }] : undefined);
    await sesYukleVeAnaliz();
    expect(postlar("/ai/sound/cat")).toHaveLength(1);
    expect(ileti()).toBe(T("ai.hata.analizSirasinda"));
    expect(s.metin()).not.toContain(T("ai.ses.yorumBaslik"));
  });

  it("Error OLMAYAN ret (düz dizge) → 'Hata: <ileti>' gösterilir", async () => {
    ozel = (y, _g, m) => (m === "POST" && y === "/ai/sound/cat" ? { hata: "tünel kapandı" } : undefined);
    await sesYukleVeAnaliz();
    expect(ileti()).toBe(T("ai.hata.hataIleti", { ileti: "tünel kapandı" }));
  });
});

describe("web'de dosya nesnesi yokken (eski web seçicisi: base64 / data: URI)", () => {
  /** Görüntüyü eski seçici yolundan al: çekim ANINDA platform "ios" (seçici dalı), hemen ardından "web"e döner. */
  async function eskiSeciciylePick(secim: { uri: string }, kucuk: { uri: string; base64: string } | Error) {
    (ImagePicker.launchImageLibraryAsync as jest.Mock).mockResolvedValue({ canceled: false, assets: [secim] });
    if (kucuk instanceof Error) (ImageManipulator.manipulateAsync as jest.Mock).mockRejectedValue(kucuk);
    else (ImageManipulator.manipulateAsync as jest.Mock).mockResolvedValue(kucuk);
    const dugme = Array.from(document.querySelectorAll("*")).filter(
      (e) => (e.textContent || "").trim() === T("ai.ortak.galeridenSec") && !e.children.length,
    ).pop() as HTMLElement;
    saatiIlerlet();
    RNW.Platform.OS = "ios";
    dugme.click();
    RNW.Platform.OS = "web";
    await s.bosalt(8);
    expect(ImagePicker.launchImageLibraryAsync).toHaveBeenCalledTimes(1); // ARA: eski seçici dalı gerçekten koştu
  }

  it("base64 var → JPEG Blob ('camera_capture.jpg', image/jpeg) gönderilir", async () => {
    ozel = (y, _g, m) => (m === "POST" && y === "/ai/vision/landmark" ? [200, { status: "success", detected: true, fgs_total: 0 }] : undefined);
    await ekraniCiz(s);
    await eskiSeciciylePick({ uri: "file:///eski.jpg" }, { uri: "file:///eski-k.jpg", base64: btoa("JPEGBAYT") });
    await metneBas(s, T("ai.hayvanSahibi.teshisEt"));
    const f = alanlar(postlar("/ai/vision/landmark")[0].govde).file as File;
    expect(f.type).toBe("image/jpeg");
    expect(await blobMetni(f)).toBe("JPEGBAYT");
  });

  it("base64 yok, data: URI var → URI'nin KENDİ MIME türüyle (image/png) Blob gönderilir", async () => {
    ozel = (y, _g, m) => (m === "POST" && y === "/ai/vision/landmark" ? [200, { status: "success", detected: true, fgs_total: 0 }] : undefined);
    await ekraniCiz(s);
    await eskiSeciciylePick({ uri: `data:image/png;base64,${btoa("PNGBAYT")}` }, new Error("küçültülemedi"));
    await metneBas(s, T("ai.hayvanSahibi.teshisEt"));
    const f = alanlar(postlar("/ai/vision/landmark")[0].govde).file as File;
    expect(f.type).toBe("image/png");
    expect(await blobMetni(f)).toBe("PNGBAYT");
  });

  it("ne dosya ne base64 ne data: URI → istek GİTMEZ, hata iletisi görünür", async () => {
    await ekraniCiz(s);
    await eskiSeciciylePick({ uri: "file:///web-de-okunamaz.jpg" }, new Error("küçültülemedi"));
    await metneBas(s, T("ai.hayvanSahibi.teshisEt"));
    expect(postlar("/ai/vision/landmark")).toHaveLength(0);
    expect(ileti()).toBe(T("ai.hata.baglanti"));
  });
});
