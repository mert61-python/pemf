/**
 * KP-4 B1 · src/screens/AiHubScreen.tsx (yerel) — CANLI KAMERA döngülerinin kalan sözleşmeleri + görüntü modüllerinin küçük kolları.
 *
 *  1) VisionModule canlı kip: ağ koparsa kare hatası SÜREKLİ durum satırında görünür (sessiz yutulmaz) ve döngü DURMAZ; bağlantı
 *     gelince sonraki kare analiz edilir. Canlı kutu karenin ORANINDA açık px (yalnız İLK ölçüm alınır — ölç / daralt döngüsü yok);
 *     "Kamerayı çevir" ön ↔ arka.
 *  2) Kedi Organ canlı kip: reddedilen karede ESKİ organ sonucu kadrajdan KALKAR (rozet yeniden "aranıyor"); ağ hatası görünür;
 *     oran kilidi + kamera çevirme aynı kuralla.
 *  3) Petri / Fantom canlı (telefon kamerası): geçersiz gelişmiş ayarla canlı DURUR ve istek GİTMEZ (elle analizle aynı form
 *     kaynağı); ağ hatası durum satırında; kamera çevrilebilir.
 *  4) FGS 6/10 "şiddetli" yorumu; tanınmayan (alan taşımayan) başarılı yanıtta yorum UYDURULMAZ, kayıt özeti "Analiz tamamlandı".
 *  5) Gerçek-zamanlı rozeti: Pro'da dokununca planı açıklar, Pro+'ta sessiz. Araştırma eklentisi rozeti plan penceresini açar /
 *     kapatır.
 * GERÇEK: AiHubScreen (+ modülleri), apiClient, korunanFetch, utils/canliKare, jetonBakiye, UpgradeModal.
 * SAHTE (en alt kat): fetch, kamera (kare yakalama + izin), görüntü seçici / küçültücü, sahte saat; bağlamlar sabit girdi; bildirim
 * kanalı (useToast) gözlemci.
 */
let mockKip: "veterinarian" | "researcher" = "veterinarian";
let mockArastirma = true;
let mockGercekZamanli = true;
let mockHastaNo = 44000;
const mockToast = jest.fn();
const mockFoto = jest.fn();
let mockFacing: string | undefined;
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: mockToast }) }));
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: mockKip, hasAiHub: true }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "v@x.com" }), useOperatorOptional: () => null }));
jest.mock("@/context/EntitlementContext", () => ({
  useEntitlement: () => ({ research: mockArastirma, realtime: mockGercekZamanli, tier: "pro" }),
}));
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigateTo: () => undefined, setAiProModeli: () => undefined,
    selectedPatient: { id: `kp4-${mockHastaNo}`, name: `Tekir-${mockHastaNo}` } }),
}));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionFresh: false, aiVisionData: null }),
}));
jest.mock("@/components/domain/PatientGate", () => {
  const React = require("react");
  return { PatientGate: ({ children }: any) => React.createElement(React.Fragment, null, children) };
});
jest.mock("expo-camera", () => {
  const R = require("react");
  const CameraView = R.forwardRef((p: { facing?: string }, ref: unknown) => {
    mockFacing = p.facing;
    R.useImperativeHandle(ref, () => ({ takePictureAsync: mockFoto }));
    return null;
  });
  return { CameraView, useCameraPermissions: () => [{ granted: true }, jest.fn(async () => ({ granted: true }))] };
});
jest.mock("expo-audio", () => ({
  useAudioRecorder: () => ({ record: jest.fn(), stop: jest.fn(), uri: null }),
  RecordingPresets: { HIGH_QUALITY: {} },
  setAudioModeAsync: jest.fn(),
  requestRecordingPermissionsAsync: jest.fn(async () => ({ granted: true })),
}));
jest.mock("expo-image-picker", () => ({
  MediaTypeOptions: { Images: "Images" },
  launchImageLibraryAsync: jest.fn(async () => ({ canceled: false, assets: [{ uri: "file:///kedi.jpg" }] })),
  launchCameraAsync: jest.fn(async () => ({ canceled: true })),
}));
jest.mock("expo-image-manipulator", () => ({
  SaveFormat: { JPEG: "jpeg" },
  manipulateAsync: jest.fn(async (uri: string) => ({ uri, base64: "QUJD" })),
}));

import React from "react";
import { StyleSheet } from "react-native";
import { act, fireEvent, render, type RenderResult } from "@testing-library/react-native";
import i18n from "i18next";

import { AiHubScreen } from "@/screens/AiHubScreen";
import { aiZamanAsimiMesaji } from "@/services/apiClient";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);

// KP-7 B: `askida` — istek yanıtsız kalır, yalnız iptal sinyaliyle reddedilir (yanıt vermeyen sunucu); `bozukGovde` — HTTP durumu var
// ama gövde JSON değil (vekil sunucunun HTML hata sayfası).
type Yanit = { durum: number; govde: unknown } | { hata: Error } | { askida: true } | { bozukGovde: number };
let rotalar: Record<string, Yanit[]>;
let fetchSahte: jest.Mock;

const basari = (govde: unknown): Yanit => ({ durum: 200, govde });
const AG_KOPUK = (): Yanit => ({ hata: new TypeError("Network request failed") });

function yolu(url: unknown): string {
  return String(url).replace(/^[a-z]+:\/\/[^/]+/i, "").replace(/^\/api/, "");
}
function cagrilar(yol: string): unknown[][] {
  return fetchSahte.mock.calls.filter((c) => yolu(c[0]) === yol);
}

beforeEach(() => {
  jest.useFakeTimers();
  mockHastaNo += 1;
  mockKip = "veterinarian";
  mockArastirma = true;
  mockGercekZamanli = true;
  mockFacing = undefined;
  mockToast.mockClear();
  mockFoto.mockReset().mockResolvedValue({ uri: "file:///kare.jpg" });
  rotalar = {};
  fetchSahte = jest.fn(async (url: unknown, init?: { signal?: AbortSignal }) => {
    const kuyruk = rotalar[yolu(url)];
    const y: Yanit = kuyruk && kuyruk.length ? (kuyruk.length > 1 ? kuyruk.shift()! : kuyruk[0]) : basari({});
    if ("hata" in y) throw y.hata;
    if ("askida" in y) {
      return new Promise((_c, reddet) => {
        init?.signal?.addEventListener("abort", () => reddet(Object.assign(new Error("aborted"), { name: "AbortError" })));
      });
    }
    if ("bozukGovde" in y) {
      return { ok: y.bozukGovde < 400, status: y.bozukGovde, json: async () => { throw new SyntaxError("Unexpected token <"); },
        text: async () => "<html>502</html>", headers: { get: () => "text/html" } };
    }
    return { ok: y.durum < 400, status: y.durum, json: async () => y.govde, text: async () => JSON.stringify(y.govde),
      headers: { get: () => "application/json" } };
  });
  (global as unknown as { fetch: unknown }).fetch = fetchSahte;
});
afterEach(() => {
  jest.useRealTimers();
});

async function bosalt(n = 25) {
  for (let i = 0; i < n; i++) await act(async () => { await Promise.resolve(); });
}
async function ilerle(ms: number) {
  await act(async () => { jest.advanceTimersByTime(ms); });
  await bosalt();
}
async function modulAc(etiket: string): Promise<RenderResult> {
  const u = render(<AiHubScreen />);
  await bosalt(5);
  fireEvent.press(u.getAllByLabelText(etiket)[0]);
  await bosalt(5);
  return u;
}
async function bas(u: RenderResult, etiket: string) {
  await act(async () => { fireEvent.press(u.getByRole("button", { name: etiket })); });
  await bosalt();
}
async function canliAc(etiket: string): Promise<RenderResult> {
  const u = await modulAc(etiket);
  await bas(u, T("ai.gorsel.canliKamera"));
  return u;
}
/** Canlı kutu: canlı önizlemenin ölçüm (onLayout) yapan atası. */
function canliKutu(u: RenderResult) {
  const ic = u.queryByTestId("canli-onizleme-kose") ?? u.getByTestId("canli-onizleme-tam");
  let n: any = ic;
  while (n && !n.props?.onLayout) n = n.parent;
  if (!n) throw new Error("canli kutu (onLayout) bulunamadi");
  return n;
}
const kutuBoyu = (u: RenderResult) => {
  const st = StyleSheet.flatten(canliKutu(u).props.style) as { width?: number; height?: number };
  return { width: st.width, height: st.height };
};
const durum = (u: RenderResult) => [u.getByTestId("canli-durum").props.children].flat().join("");
const AG_HATASI = () => T("ai.canli.sonKareHata", { hata: T("ortak.hata.aiGonderilemedi") });

describe("VisionModule canlı kip", () => {
  it("KRİTİK: ağ koparsa kare hatası durum satırında görünür, döngü DURMAZ; bağlantı gelince sonraki kare analiz edilir", async () => {
    rotalar["/ai/vision/segmentation"] = [AG_KOPUK(), basari({ status: "success", cat_count: 1, image_base64: "SEG" })];
    const u = await canliAc(T("ai.modul.segmentasyon.ad"));
    await ilerle(1100);
    expect(cagrilar("/ai/vision/segmentation")).toHaveLength(1);
    expect(durum(u)).toBe(AG_HATASI());
    await ilerle(1100);
    expect(cagrilar("/ai/vision/segmentation")).toHaveLength(2);
    expect(durum(u)).toBe(T("ai.canli.durum.analizEdildi"));
  });

  it("KRİTİK: kare yakalanamazsa (kamera hatası) da durum satırı söyler; istek gitmez", async () => {
    mockFoto.mockRejectedValue(new Error("Camera is not running"));
    const u = await canliAc(T("ai.modul.segmentasyon.ad"));
    await ilerle(1100);
    expect(cagrilar("/ai/vision/segmentation")).toHaveLength(0);
    expect(durum(u)).toBe(T("ai.canli.sonKareHata", { hata: T("ortak.hata.agSunucu") }));
  });

  it("KRİTİK: canlı kutu karenin ORANINDA (4:3 kare → 300×225); ikinci ölçüm kutuyu DEĞİŞTİRMEZ; kamera ön ↔ arka çevrilir", async () => {
    rotalar["/ai/vision/thermal"] = [basari({
      status: "success", image_base64: "TERMAL", image_w: 640, image_h: 480, prediction: { label: "Healthy", confidence: 0.9 },
    })];
    const u = await canliAc(T("ai.modul.termal.ad"));
    fireEvent(canliKutu(u), "layout", { nativeEvent: { layout: { width: 300, height: 600 } } });
    await bosalt(3);
    expect(kutuBoyu(u)).toEqual({ width: 300, height: 400 }); // sonuç yokken dikey telefon varsayılanı 3:4
    await ilerle(1100);
    expect(kutuBoyu(u)).toEqual({ width: 300, height: 225 });
    fireEvent(canliKutu(u), "layout", { nativeEvent: { layout: { width: 500, height: 600 } } });
    await bosalt(3);
    expect(kutuBoyu(u)).toEqual({ width: 300, height: 225 });

    expect(mockFacing).toBe("back");
    await act(async () => { fireEvent.press(u.getByLabelText(T("ai.canli.kamerayiCevir"))); });
    expect(mockFacing).toBe("front");
    await act(async () => { fireEvent.press(u.getByLabelText(T("ai.canli.kamerayiCevir"))); });
    expect(mockFacing).toBe("back");
  });
});

describe("Kedi Organ canlı kip", () => {
  const ORGAN = basari({
    status: "success", image_base64: "ORGAN1", n_organs: 3, detected: true, image_w: 640, image_h: 480,
    organs: [{ name: "kidney", reliability: 0.8 }],
  });
  const RED = { durum: 422, govde: { detail: "Görüntü bulanık; kamerayı sabit tutun." } };

  it("KRİTİK: reddedilen karede ESKİ organ sonucu kadrajdan KALKAR (rozet yeniden 'aranıyor'), gerekçe durum satırında", async () => {
    rotalar["/ai/vision/cat_organ"] = [ORGAN, RED];
    const u = await canliAc(T("ai.modul.kediOrgan.ad"));
    await ilerle(1100);
    expect(String(u.getByTestId("canli-son-kare").props.source.uri)).toContain("ORGAN1");
    expect(u.getByText(T("ai.organ.rozet", { count: 3 }))).toBeTruthy();
    await ilerle(1100);
    expect(cagrilar("/ai/vision/cat_organ")).toHaveLength(2);
    expect(u.queryByTestId("canli-son-kare")).toBeNull();
    expect(u.getByText(T("ai.organ.rozetAraniyor"))).toBeTruthy();
    expect(durum(u)).toContain("Görüntü bulanık");
  });

  it("KRİTİK: ağ koparsa kare hatası durum satırında; oran kilidi yalnız ilk ölçüm; kamera çevrilir", async () => {
    rotalar["/ai/vision/cat_organ"] = [AG_KOPUK(), ORGAN];
    const u = await canliAc(T("ai.modul.kediOrgan.ad"));
    fireEvent(canliKutu(u), "layout", { nativeEvent: { layout: { width: 300, height: 600 } } });
    await ilerle(1100);
    expect(durum(u)).toBe(AG_HATASI());
    expect(kutuBoyu(u)).toEqual({ width: 300, height: 400 });
    await ilerle(1100);
    expect(kutuBoyu(u)).toEqual({ width: 300, height: 225 });
    fireEvent(canliKutu(u), "layout", { nativeEvent: { layout: { width: 480, height: 600 } } });
    await bosalt(3);
    expect(kutuBoyu(u)).toEqual({ width: 300, height: 225 });
    await act(async () => { fireEvent.press(u.getByLabelText(T("ai.canli.kamerayiCevir"))); });
    expect(mockFacing).toBe("front");
  });
});

describe("Petri / Fantom canlı (telefon kamerası)", () => {
  it("KRİTİK: geçersiz gelişmiş ayarla canlı DURUR, analiz isteği GİTMEZ, ayar hatası söylenir", async () => {
    mockKip = "researcher";
    const u = await modulAc(T("ai.modul.petriKuyu.ad"));
    await act(async () => { fireEvent.press(u.getByLabelText(T("ai.petri.gelismisEtiketi"))); });
    fireEvent.changeText(u.getByLabelText(T("ai.petri.ayar.kuyuSkorEsigi.etiket")), "5");
    await bas(u, T("ai.gorsel.canliKamera"));
    expect(u.getByTestId("em-canli-kutusu")).toBeTruthy();
    await ilerle(1100);
    expect(mockFoto).toHaveBeenCalledTimes(1);
    expect(cagrilar("/ai/vision/em_petri")).toHaveLength(0);
    expect(mockToast).toHaveBeenCalledWith(
      T("ai.petri.aralikDisi", { etiket: T("ai.petri.ayar.kuyuSkorEsigi.etiket"), alt: 0, ust: 1, ham: "5" }), "error");
    expect(u.queryByTestId("em-canli-kutusu")).toBeNull();
    expect(u.getByRole("button", { name: T("ai.gorsel.canliKamera") })).toBeTruthy();
    await ilerle(3000);
    expect(mockFoto).toHaveBeenCalledTimes(1); // döngü durdu
  });

  it("KRİTİK: fantom canlıda ağ koparsa durum satırı söyler, döngü sürer; kamera çevrilir", async () => {
    mockKip = "researcher";
    rotalar["/ai/vision/em_fantom"] = [AG_KOPUK()];
    const u = await modulAc(T("ai.modul.fantomTumor.ad"));
    await bas(u, T("ai.gorsel.canliKamera"));
    await ilerle(1100);
    expect(durum(u)).toBe(AG_HATASI());
    await ilerle(1100);
    expect(cagrilar("/ai/vision/em_fantom").length).toBe(2);
    expect(mockFacing).toBe("back");
    await act(async () => { fireEvent.press(u.getByLabelText(T("ai.canli.kamerayiCevir"))); });
    expect(mockFacing).toBe("front");
    await bas(u, T("ai.gorsel.canliyiDurdur"));
  });
});

// ── KP-7 B (işlev ölçüsü): canlı kare isteği ASKIDA kalırsa kendi sınırında kesilir (kamera akışı kilitlenmez) ve gövdesi JSON olmayan
// yanıt (vekil HTML sayfası) döngüyü durdurmaz — üç canlı döngü (görüntü 15 sn · fantom 30 sn · kedi organ 25 sn).
describe("KP-7 B · canlı döngüde askıda istek ve bozuk gövde", () => {
  const ZAMAN_ASIMI = () => T("ai.canli.sonKareHata", { hata: aiZamanAsimiMesaji() });
  /** Durum satırı ilk kare sonucuna dek çizilmez → yoksa boş. */
  const durumVarsa = (u: RenderResult) => (u.queryByTestId("canli-durum") ? durum(u) : "");

  it("görüntü canlı: askıdaki kare 15 sn sonra kesilir (zaman aşımı); bozuk gövde 'analiz edilemedi'; döngü sürer", async () => {
    rotalar["/ai/vision/segmentation"] = [{ askida: true }, { bozukGovde: 502 }, basari({ status: "success", cat_count: 1, image_base64: "S" })];
    const u = await canliAc(T("ai.modul.segmentasyon.ad"));
    await ilerle(1100);
    expect(cagrilar("/ai/vision/segmentation")).toHaveLength(1);
    await ilerle(14_998);
    expect(durumVarsa(u)).not.toBe(ZAMAN_ASIMI());
    await ilerle(2);
    expect(durum(u)).toBe(ZAMAN_ASIMI());
    await ilerle(1100);
    expect(cagrilar("/ai/vision/segmentation")).toHaveLength(2);
    expect(durum(u)).toContain("502");
    await ilerle(1100);
    expect(durum(u)).toBe(T("ai.canli.durum.analizEdildi"));
  });

  it("fantom canlı: askıdaki kare 30 sn sonra kesilir (zaman aşımı); bozuk gövde döngüyü durdurmaz", async () => {
    mockKip = "researcher";
    rotalar["/ai/vision/em_fantom"] = [{ askida: true }, { bozukGovde: 502 }];
    const u = await modulAc(T("ai.modul.fantomTumor.ad"));
    await bas(u, T("ai.gorsel.canliKamera"));
    await ilerle(1100);
    await ilerle(29_998);
    expect(durumVarsa(u)).not.toBe(ZAMAN_ASIMI());
    await ilerle(2);
    expect(durum(u)).toBe(ZAMAN_ASIMI());
    await ilerle(1100);
    expect(cagrilar("/ai/vision/em_fantom").length).toBe(2);
    expect(durum(u)).toContain("502");
    await bas(u, T("ai.gorsel.canliyiDurdur"));
  });

  it("kedi organ canlı: askıdaki kare 25 sn sonra kesilir (zaman aşımı); bozuk gövde eski sonucu GÖSTERMEZ", async () => {
    rotalar["/ai/vision/cat_organ"] = [{ askida: true }, { bozukGovde: 502 }];
    const u = await canliAc(T("ai.modul.kediOrgan.ad"));
    await ilerle(1100);
    await ilerle(24_998);
    expect(durumVarsa(u)).not.toBe(ZAMAN_ASIMI());
    await ilerle(2);
    expect(durum(u)).toBe(ZAMAN_ASIMI());
    await ilerle(1100);
    expect(cagrilar("/ai/vision/cat_organ")).toHaveLength(2);
    expect(durum(u)).toContain("502");
    expect(u.queryByTestId("canli-son-kare")).toBeNull();
  });
});

describe("Görüntü modülü yorumları", () => {
  it("KRİTİK: FGS 6/10 'şiddetli' yorumu (5'in üstü); 5/10 'orta'", async () => {
    rotalar["/ai/vision/landmark"] = [basari({ status: "success", fgs_total: 6 }), basari({ status: "success", fgs_total: 5 })];
    const u = await modulAc(T("ai.modul.yuzAgrisi.ad"));
    await bas(u, T("ai.ortak.galeridenSec"));
    await bas(u, T("ai.fgs.analiziBaslat"));
    expect(u.getByText(`🚨 ${T("ai.fgs.siddetli.baslik", { s: 6 })}`)).toBeTruthy();
    await ilerle(500);
    await bas(u, T("ai.fgs.analiziBaslat"));
    expect(cagrilar("/ai/vision/landmark")).toHaveLength(2);
    expect(u.getByText(`😾 ${T("ai.fgs.orta.baslik", { s: 5 })}`)).toBeTruthy();
    expect(u.queryByText(`🚨 ${T("ai.fgs.siddetli.baslik", { s: 5 })}`)).toBeNull();
  });

  it("KRİTİK: tanınan alan taşımayan başarılı yanıtta yorum UYDURULMAZ; kayıt özeti 'Analiz tamamlandı'", async () => {
    rotalar["/ai/vision/reticulocytes"] = [basari({ status: "success" })];
    const u = await modulAc(T("ai.modul.retikulosit.ad"));
    await bas(u, T("ai.ortak.galeridenSec"));
    await bas(u, T("ai.fgs.analiziBaslat"));
    const kayit = cagrilar("/ai/log").filter((c) => (c[1] as { method?: string })?.method === "POST");
    expect(kayit).toHaveLength(1);
    const govde = JSON.parse(String((kayit[0][1] as { body: string }).body));
    expect(govde.summary).toBe("Analiz tamamlandı");
    expect(govde.module).toBe("Retikülosit Sayımı");
    expect(u.queryByText(/^🔬 /)).toBeNull(); // retikülosit yorum başlığı (🔬) çizilmez
    expect(u.queryByText(T("ai.retikulosit.yuksek"))).toBeNull();
    expect(u.queryByText(T("ai.retikulosit.dusuk"))).toBeNull();
  });
});

describe("Plan rozetleri", () => {
  it("KRİTİK: Pro'da 'kuyruklu' rozetine dokununca gerçek-zamanlı planı açıklar", async () => {
    mockGercekZamanli = false;
    const u = await modulAc(T("ai.modul.yuzAgrisi.ad"));
    await act(async () => { fireEvent.press(u.getByLabelText(T("ai.gorsel.kuyrukluEtiket"))); });
    expect(mockToast).toHaveBeenCalledWith(T("ai.gorsel.gercekZamanliIpucu"), "info");
  });

  it("KARŞIT: Pro+'ta 'gerçek-zamanlı' rozeti dokununca bildirim GÖSTERMEZ", async () => {
    mockGercekZamanli = true;
    const u = await modulAc(T("ai.modul.yuzAgrisi.ad"));
    await act(async () => { fireEvent.press(u.getByLabelText(T("ai.gorsel.gercekZamanliEtiket"))); });
    expect(mockToast).not.toHaveBeenCalled();
  });

  it("KRİTİK: eklentisiz araştırmacıda 'eklenti' rozeti ARAŞTIRMA plan penceresini açar; Kapat kapatır", async () => {
    mockKip = "researcher";
    mockArastirma = false;
    const u = render(<AiHubScreen />);
    await bosalt(5);
    expect(u.queryByTestId("upgrade-modal")).toBeNull();
    await act(async () => { fireEvent.press(u.getAllByLabelText(T("ai.hub.eklentiGerekli"))[0]); });
    expect(u.getByTestId("upgrade-modal")).toBeTruthy();
    expect(u.getByText(T("kabuk.planModal.arastirma.aciklama"))).toBeTruthy();
    await act(async () => { fireEvent.press(u.getByLabelText(T("ortak.kapat"))); });
    expect(u.queryByTestId("upgrade-modal")).toBeNull();
  });
});

describe("Hastalık modülü vital girişleri", () => {
  async function hastalikAc() {
    const u = await modulAc(T("ai.modul.hastalik.ad"));
    for (const s of ["ai.hastalik.semptom.kusma", "ai.hastalik.semptom.ishal"]) {
      await act(async () => { fireEvent.press(u.getByText(T(s))); });
    }
    return u;
  }

  it("KRİTİK: girilen kilo / nabız / ateş / süre isteğe AYNEN gider (boş yaş sağlıklı-kedi varsayılanıyla)", async () => {
    const u = await hastalikAc();
    fireEvent.changeText(u.getByLabelText(T("hasta.form.kiloEtiketi")), "5.2");
    fireEvent.changeText(u.getByLabelText(T("ai.hastalik.form.nabizEtiketi")), "180");
    fireEvent.changeText(u.getByLabelText(T("ai.hastalik.form.atesEtiketi")), "39.6");
    fireEvent.changeText(u.getByLabelText(T("ai.hastalik.form.sureEtiketi")), "10");
    await bas(u, T("ai.hastalik.teshisiBaslat"));
    const giden = cagrilar("/ai/disease");
    expect(giden).toHaveLength(1);
    const govde = JSON.parse(String((giden[0][1] as { body: string }).body));
    expect(govde).toEqual(expect.objectContaining({ age: 3, weight: 5.2, hr: 180, temp: 39.6, duration: 10, symptom_indices: [2, 3] }));
  });

  // KP-7 B (işlev ölçüsü): seçili belirtiye İKİNCİ kez dokunmak seçimi KALDIRIR — kaldırılan belirti isteğe GİTMEZ (yanlışlıkla seçilen
  // belirti teşhisi saptırmasın).
  it("seçili belirtiye ikinci dokunuş seçimi kaldırır; kaldırılan belirti isteğe gitmez", async () => {
    const u = await hastalikAc(); // kusma (2) + ishal (3) seçili
    await act(async () => { fireEvent.press(u.getByText(T("ai.hastalik.semptom.kusma"))); }); // kusma KALDIRILIR
    await act(async () => { fireEvent.press(u.getByText(T("ai.hastalik.semptom.oksuruk"))); }); // en az 2 kuralı: öksürük (4)
    await bas(u, T("ai.hastalik.teshisiBaslat"));
    expect(cagrilar("/ai/disease")).toHaveLength(1);
    const govde = JSON.parse(String((cagrilar("/ai/disease")[0][1] as { body: string }).body));
    expect(govde.symptom_indices).toEqual([3, 4]);
  });

  it("KARŞIT: aralık dışı ateş (50 °C) gönderilmez, aralık iletisi çıkar", async () => {
    const u = await hastalikAc();
    fireEvent.changeText(u.getByLabelText(T("ai.hastalik.form.atesEtiketi")), "50");
    await bas(u, T("ai.hastalik.teshisiBaslat"));
    expect(cagrilar("/ai/disease")).toHaveLength(0);
    expect(mockToast).toHaveBeenCalledWith(T("ai.hastalik.gecersizAralik", { label: T("ai.hastalik.form.ates"), lo: 25, hi: 46 }), "error");
  });
});
