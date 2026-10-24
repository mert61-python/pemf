// Author: mertaygn, cglrgrkn
/**
 * T3 · Y190 (sahip 2026-10-24) — petri / fantom: "Fotoğraf Çek" DOĞRUDAN kabin kamerası, kamera seçimi panelde, CANLI kamera.
 *
 * Sahip: "fotoğraf çek direkt kabin kamerasından çekmeliydi … kabin kamerasından çek gereksiz buton. kamera seçimi de burada
 * olmalı, ayarlar içinde değil. telefonda telefonun kamerasını açmalı. galeriden seç normal kalmalı. bir de canlı kamera eklenmeli
 * hem fantoma hem petriye." Kararlar: canlı = önizleme + otomatik analiz · seçim panelde + AI Pro'da · telefonda telefonun kamerası
 * · jeton dakika başı (Y148).
 * Ölçülen (3a4c2f5b): bu makinede "Fotoğraf Çek" tarayıcının / WebView'in VARSAYILAN kamerasını (dizüstünün kendi kamerası) açıyor,
 * kabin kamerası ayrı bir "Kabin kamerasından çek" düğmesinde; kamera seçimi yalnız Ayarlar'da; petri / fantomda canlı kip YOK.
 * Kapı (web, backend bu makinede): "Fotoğraf Çek" `/settings/kabin-kamerasi/kare` karesini girdi yapar (ayrı düğme YOK); panelde
 * "Kabin kamerası" bölümü; "Canlı Kamera" backend canlı oturumunu açar, önizleme küçük kare, analiz TAM kare + `X-PEMF-Canli-Oturum`
 * başlığı; durdurunca oturum kapanır ve son kare elle (başlıksız) analiz edilebilir; kamera AI Pro'ya geçerse canlı durur ve EYLEM
 * söyler; uzak backend'de (LAN) kabin yolu YOK, canlı cihazın kendi kamerasıyla.
 * ⚠️ Beklenen metinler BURADA sabittir. Platform.OS="web".
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});
let mockMode = "researcher";
const mockToast = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => null),
  apiPost: jest.fn(async () => null),
  authHeaders: jest.fn(() => ({})),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  AI_TIMEOUT_MS: 120000,
  aiHataMesaji: jest.fn(() => "hata"),
}));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" } }));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: mockToast }) }));
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: mockMode, hasAiHub: true }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "r@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "r@x.com" }) }));
jest.mock("@/context/EntitlementContext", () => ({ useEntitlement: () => ({ research: true }) }));
let mockHastaId = 19000;
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigate: jest.fn(), selectedPatient: { id: mockHastaId, name: `Y190-${mockHastaId}` } }),
}));
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionFresh: false }) }));
jest.mock("@/components/domain/PatientGate", () => {
  const React = require("react");
  return { PatientGate: ({ children }: any) => React.createElement(React.Fragment, null, children) };
});
const mockFoto = jest.fn(async () => ({ uri: "file:///canli.jpg" }));
jest.mock("expo-camera", () => {
  const R = require("react");
  return {
    CameraView: R.forwardRef((_p: any, ref: any) => {
      R.useImperativeHandle(ref, () => ({ takePictureAsync: mockFoto }));
      return null;
    }),
    useCameraPermissions: () => [{ granted: true }, jest.fn(async () => ({ granted: true }))],
  };
});
jest.mock("expo-audio", () => ({
  useAudioRecorder: () => ({ record: jest.fn(), stop: jest.fn(), uri: null }),
  RecordingPresets: { HIGH_QUALITY: {} },
  setAudioModeAsync: jest.fn(),
  requestRecordingPermissionsAsync: jest.fn(async () => ({ granted: true })),
}));
jest.mock("expo-document-picker", () => ({ getDocumentAsync: jest.fn(async () => ({ canceled: true })) }));
jest.mock("expo-image-picker", () => ({
  MediaTypeOptions: { Images: "Images" },
  launchImageLibraryAsync: jest.fn(async () => ({ canceled: true })),
  launchCameraAsync: jest.fn(async () => ({ canceled: true })),
}));
jest.mock("expo-image-manipulator", () => ({
  SaveFormat: { JPEG: "jpeg" },
  manipulateAsync: jest.fn(async () => ({ uri: "file:///canli-kucuk.jpg", base64: "VEVM" })),
}));

import React from "react";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";

import { apiPost } from "@/services/apiClient";
import { serviceConfig } from "@/services/config";
import { AiHubScreen as Ekran } from "@/screens/AiHubScreen";
import * as ImagePicker from "expo-image-picker";

jest.setTimeout(20000);

type Yanit = { ok: boolean; status: number; json: () => Promise<any> };
const yanit = (veri: any, status = 200): Yanit => ({ ok: status >= 200 && status < 300, status, json: async () => veri });
let mockOzel: Record<string, () => Yanit> = {};
let mockYanit: any = null;
const KOK = /^https?:\/\/[^/]+\/api/;

function yolu(url: unknown): string {
  return String(url).replace(KOK, "");
}
function cagrilar(onek: string): any[][] {
  return (global.fetch as jest.Mock).mock.calls.filter((c) => yolu(c[0]).startsWith(onek));
}
/** FormData alanları; Blob → `[blob:<bayt>]` (hangi karenin gittiği bayt sayısından okunur). */
function form(body: any): Record<string, string> {
  const cikti: Record<string, string> = {};
  const yaz = (k: string, v: any) => {
    cikti[k] = v && typeof v === "object" ? `[blob:${typeof v.size === "number" ? v.size : "?"}]` : String(v);
  };
  if (Array.isArray(body?._parts)) for (const [k, v] of body._parts) yaz(String(k), v);
  else if (typeof body?.forEach === "function") body.forEach((v: any, k: string) => yaz(k, v));
  return cikti;
}
const bekle = (ms: number) => act(async () => { await new Promise((r) => setTimeout(r, ms)); });

const PETRI = {
  status: "success", success: true, method: "plate_grid", mm_per_px: 0.118, n_wells: 1, n_cancer: 0, n_healthy: 1,
  wells: [{ well_id: "W1", label: "healthy", organ_id: 0, centroid_cabin_mm: [19.3, 0, 0], D: [0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3],
    E_cancer: 0.1, E_healthy: 0.1, area_mm2: 150, cancer_reasons: [] }],
  image_base64: "OUT64", yolo_ayar: { conf: 0.25, iou: 0.7 }, resize: {}, plausibility: {}, pemf_valid: true, kosulsuz: false, warnings: [],
  pemf_kapisi: { surulebilir: true, pemf_gecerli: true, kosulsuz: false, atlanan: [], nedenler: [], eylem: "", mesajlar: [], varsayimlar: [] },
};
const FANTOM = {
  status: "success", success: true, method: "coil_ring", mm_per_px: 0.31, n_tumor: 1, n_healthy: 0, healthy_regions: [],
  tumor_regions: [{ tumor_id: "T1", centroid_cabin_mm: [-43.6, -15, -9.2], D: [0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4], E_cancer: 0.005, E_healthy: 0.004, area_mm2: 316 }],
  image_base64: "OUT64", pemf_valid: true, reliable: true, warnings: [],
  pemf_kapisi: { surulebilir: true, pemf_gecerli: true, kosulsuz: false, atlanan: [], nedenler: [], eylem: "", mesajlar: [], varsayimlar: [] },
};

beforeEach(() => {
  mockHastaId += 1;
  mockMode = "researcher";
  mockToast.mockClear();
  mockFoto.mockClear();
  (apiPost as jest.Mock).mockClear();
  (ImagePicker.launchCameraAsync as jest.Mock).mockClear();
  mockOzel = {};
  (serviceConfig as any).apiBaseUrl = "http://127.0.0.1:8000/api";
  global.fetch = jest.fn(async (url: unknown) => {
    const yol = yolu(url);
    const ozel = mockOzel[yol.split("?")[0]];
    if (ozel) return ozel();
    if (yol === "/settings/kabin-kamerasi/kare") return yanit({ status: "success", genislik: 1920, yukseklik: 1080, image_base64: "S0FCSU4=" });
    if (yol === "/settings/kabin-kamerasi/canli/baslat") return yanit({ status: "success", indeks: 1, acik: true });
    if (yol.startsWith("/settings/kabin-kamerasi/canli/kare")) {
      return yanit({ status: "success", yas_ms: 3, image_base64: yol.includes("tam=true") ? "VEFN" : "T05J" });
    }
    if (yol === "/settings/kabin-kamerasi/canli/durdur") return yanit({ status: "success" });
    if (yol.startsWith("/ai/vision/em_")) return yanit(mockYanit);
    return yanit({});
  }) as any;
});

async function modulAc(etiket: string, baslik: string) {
  const u = render(<Ekran />);
  fireEvent.press(u.getAllByLabelText(etiket)[0]);
  await waitFor(() => u.getByText(baslik));
  return u;
}

describe.each([
  ["Petri Kuyu", "Petri Kuyu Analizi", "Petri Analizini Başlat", "/ai/vision/em_petri", PETRI],
  ["Fantom Tümör", "Fantom Tümör Analizi", "Fantom Analizini Başlat", "/ai/vision/em_fantom", FANTOM],
])("%s", (etiket, baslik, dugme, uc, sonuc) => {
  beforeEach(() => {
    mockYanit = sonuc;
  });

  it("KRİTİK: 'Fotoğraf Çek' bu makinede SEÇİLİ kabin kamerasından (tarayıcı kamerası AÇILMAZ); ayrı 'Kabin kamerasından çek' YOK", async () => {
    const u = await modulAc(etiket, baslik);
    expect(u.queryByText("Kabin kamerasından çek")).toBeNull();
    expect(u.getByText("Galeriden Seç")).toBeTruthy();
    await act(async () => { fireEvent.press(u.getByText("Fotoğraf Çek")); });
    await waitFor(() => expect(cagrilar("/settings/kabin-kamerasi/kare")).toHaveLength(1));
    expect(cagrilar("/settings/kabin-kamerasi/kare")[0][1].method).toBe("POST");
    expect(ImagePicker.launchCameraAsync).not.toHaveBeenCalled();
    await bekle(450);
    await act(async () => { fireEvent.press(u.getByText(dugme)); });
    await waitFor(() => expect(cagrilar(uc)).toHaveLength(1));
    expect(form(cagrilar(uc)[0][1].body).file).toBe("[blob:5]"); // "KABIN" — kabin karesi
  });

  it("KRİTİK: kabin karesi alınamazsa sunucunun EYLEM metni (paneldeki bölüme yönlendirir) gösterilir", async () => {
    const DETAY =
      "Kabin kamerası seçilmedi. Analiz ya da AI Pro ekranındaki \"Kabin kamerası\" bölümünden kabin kamerasını seçip yeniden deneyin.";
    mockOzel["/settings/kabin-kamerasi/kare"] = () => yanit({ detail: DETAY }, 409);
    const u = await modulAc(etiket, baslik);
    await act(async () => { fireEvent.press(u.getByText("Fotoğraf Çek")); });
    await waitFor(() => expect(mockToast).toHaveBeenCalled());
    expect(String(mockToast.mock.calls[0][0])).toBe(DETAY);
  });

  it("KRİTİK: kamera seçimi PANELDE ('Kabin kamerası' bölümü + 'Kameraları tara')", async () => {
    const u = await modulAc(etiket, baslik);
    expect(u.getByTestId("kabin-kamerasi-tara")).toBeTruthy();
    expect(u.getAllByText("Kabin kamerası").length).toBeGreaterThan(0);
  });

  it("KRİTİK: 'Canlı Kamera' kabin canlı oturumu — önizleme KÜÇÜK kare, analiz TAM kare + canlı oturum başlığı; durdurunca oturum kapanır, son kare elle analiz edilir", async () => {
    const u = await modulAc(etiket, baslik);
    await act(async () => { fireEvent.press(u.getByText("Canlı Kamera")); });
    await waitFor(() => expect(cagrilar("/settings/kabin-kamerasi/canli/baslat")).toHaveLength(1));
    await waitFor(() => expect(cagrilar(uc).length).toBeGreaterThan(0), { timeout: 5000 });
    const ilk = cagrilar(uc)[0];
    expect(String(ilk[1].headers["X-PEMF-Canli-Oturum"])).toMatch(/^canli-/);
    expect(form(ilk[1].body).file).toBe("[blob:3]"); // "TAM" — tam kare (önizleme karesi DEĞİL)
    expect(cagrilar("/settings/kabin-kamerasi/canli/kare?tam=true").length).toBeGreaterThan(0);
    await waitFor(() => expect(String(u.getByTestId("em-canli-onizleme").props.source.uri)).toContain("T05J"));
    await waitFor(() => expect(u.getByTestId("canli-durum").props.children).toBe("Son kare analiz edildi."));
    expect(u.getByText("Canlıyı Durdur")).toBeTruthy();
    // canlıyken kamera seçimi KİLİTLİ (tarama canlı oturumun kamerasını açamaz)
    await act(async () => { fireEvent.press(u.getByTestId("kabin-kamerasi-tara")); });
    expect((apiPost as jest.Mock).mock.calls.filter((c) => String(c[0]).includes("/tara"))).toHaveLength(0);

    await act(async () => { fireEvent.press(u.getByText("Canlıyı Durdur")); });
    await waitFor(() => expect(cagrilar("/settings/kabin-kamerasi/canli/durdur").length).toBeGreaterThan(0));
    const sayi = cagrilar(uc).length;
    await bekle(1600);
    expect(cagrilar(uc).length).toBe(sayi); // döngü durdu
    expect(u.queryByTestId("em-canli-onizleme")).toBeNull();
    await act(async () => { fireEvent.press(u.getByText(dugme)); });
    await waitFor(() => expect(cagrilar(uc).length).toBe(sayi + 1));
    const elle = cagrilar(uc)[sayi];
    expect(elle[1].headers["X-PEMF-Canli-Oturum"]).toBeUndefined(); // elle analiz kare başı (Y148)
    expect(form(elle[1].body).file).toBe("[blob:3]"); // son canlı kare
  });

  it("KRİTİK: canlı oturum açılamazsa (AI Pro kamerayı tutuyor) EYLEM metni, canlı AÇILMAZ", async () => {
    const DETAY = "AI Pro kamerayı şu anda kullanıyor. Hazırlığı ya da seansı durdurup canlı kamerayı yeniden açın.";
    mockOzel["/settings/kabin-kamerasi/canli/baslat"] = () => yanit({ detail: DETAY }, 409);
    const u = await modulAc(etiket, baslik);
    await act(async () => { fireEvent.press(u.getByText("Canlı Kamera")); });
    await waitFor(() => expect(mockToast).toHaveBeenCalledWith(DETAY, "error"));
    await bekle(1300);
    expect(cagrilar(uc)).toHaveLength(0);
    expect(u.getByText("Canlı Kamera")).toBeTruthy();
  });

  it("KRİTİK: canlıyken kamera AI Pro'ya geçerse (409) canlı DURUR ve EYLEM söyler", async () => {
    const DETAY = "Canlı kamera açık değil. \"Canlı Kamera\" düğmesiyle yeniden başlatın.";
    mockOzel["/settings/kabin-kamerasi/canli/kare"] = () => yanit({ detail: DETAY }, 409);
    const u = await modulAc(etiket, baslik);
    await act(async () => { fireEvent.press(u.getByText("Canlı Kamera")); });
    await waitFor(() => expect(mockToast).toHaveBeenCalledWith(DETAY, "error"));
    await waitFor(() => expect(u.getByText("Canlı Kamera")).toBeTruthy());
    expect(u.queryByTestId("em-canli-kutusu")).toBeNull();
  });

  it("KRİTİK: 'tespit yok' karesi durum satırında SONUÇSUZ görünür (dakika ücretlenmez)", async () => {
    mockYanit = { status: "no_detection", success: false, error: "plate_not_found", pemf_valid: false, warnings: [] };
    const u = await modulAc(etiket, baslik);
    await act(async () => { fireEvent.press(u.getByText("Canlı Kamera")); });
    await waitFor(() => expect(String(u.getByTestId("canli-durum").props.children)).toContain("tespit yok"), { timeout: 5000 });
  });

  it("KARŞIT: backend başka makinede (LAN) → kabin bölümü YOK; canlı CİHAZIN kamerasıyla, kabin ucuna çağrı YOK", async () => {
    (serviceConfig as any).apiBaseUrl = "http://192.168.1.50:8000/api";
    const u = await modulAc(etiket, baslik);
    expect(u.queryByTestId("kabin-kamerasi-tara")).toBeNull();
    await act(async () => { fireEvent.press(u.getByText("Canlı Kamera")); });
    await waitFor(() => expect(cagrilar(uc).length).toBeGreaterThan(0), { timeout: 5000 });
    expect(mockFoto).toHaveBeenCalled();
    expect(String(cagrilar(uc)[0][1].headers["X-PEMF-Canli-Oturum"])).toMatch(/^canli-/);
    expect(form(cagrilar(uc)[0][1].body).file).toBe("[blob:3]"); // "TEL" — cihaz kamerası karesi
    expect((global.fetch as jest.Mock).mock.calls.filter((c) => yolu(c[0]).startsWith("/settings/kabin-kamerasi"))).toHaveLength(0);
    await act(async () => { fireEvent.press(u.getByText("Canlıyı Durdur")); });
  });
});
