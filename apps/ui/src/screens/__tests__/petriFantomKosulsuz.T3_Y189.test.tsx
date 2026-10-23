// Author: mertaygn, cglrgrkn
/**
 * T3 · Y189 (sahip + Çağlar Hoca, 2026-10-23) — petri / fantom analizinde "Koşullu | Koşulsuz" ve "Kabin kamerasından çek".
 *
 * Ölçülen (78d6a0ad): petri ve fantom formunda koşul seçimi YOK (engeller her istekte uygulanır; petri "Gelişmiş ▸ denetim" yalnız
 * makullik reddini kapatıyordu, AI Pro'ya etkisi yoktu); "Fotoğraf Çek" tarayıcının / WebView'in VARSAYILAN kamerasını açıyor —
 * sahip: "otomatik laptop kamerasına attı, harici kameraya geçemedim".
 * Kapı: varsayılan KOŞULLU (istekte `kosulsuz` alanı HİÇ yok = eski istek), "Koşulsuz" seçilince `kosulsuz=true` gider ve uyarı
 * görünür; "Kabin kamerasından çek" `/settings/kabin-kamerasi/kare` karesini analiz girdisi yapar; backend başka makinedeyse
 * düğme YOK (kamera backend'in makinesinde).
 */
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
let mockHastaId = 18900;
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigate: jest.fn(), selectedPatient: { id: mockHastaId, name: `Y189-${mockHastaId}` } }),
}));
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionFresh: false }) }));
jest.mock("@/components/domain/PatientGate", () => {
  const React = require("react");
  return { PatientGate: ({ children }: any) => React.createElement(React.Fragment, null, children) };
});
jest.mock("expo-camera", () => ({ CameraView: () => null, useCameraPermissions: () => [{ granted: true }, jest.fn()] }));
jest.mock("expo-audio", () => ({
  useAudioRecorder: () => ({ record: jest.fn(), stop: jest.fn(), uri: null }),
  RecordingPresets: { HIGH_QUALITY: {} },
  setAudioModeAsync: jest.fn(),
  requestRecordingPermissionsAsync: jest.fn(async () => ({ granted: true })),
}));
jest.mock("expo-document-picker", () => ({ getDocumentAsync: jest.fn(async () => ({ canceled: true })) }));
jest.mock("expo-image-picker", () => ({
  MediaTypeOptions: { Images: "Images" },
  launchImageLibraryAsync: jest.fn(async () => ({ canceled: false, assets: [{ uri: "file:///g.jpg", base64: "G64", file: null }] })),
  launchCameraAsync: jest.fn(async () => ({ canceled: true })),
}));
jest.mock("expo-image-manipulator", () => ({
  SaveFormat: { JPEG: "jpeg" },
  manipulateAsync: jest.fn(async () => ({ uri: "file:///g-kucuk.jpg", base64: "G64" })),
}));

import React from "react";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";

import { serviceConfig } from "@/services/config";
import { AiHubScreen as Ekran } from "@/screens/AiHubScreen";

function formAlanlari(body: any): Record<string, string> {
  const cikti: Record<string, string> = {};
  const parts = body?._parts;
  if (Array.isArray(parts)) {
    for (const [k, v] of parts) cikti[String(k)] = typeof v === "object" ? "[blob]" : String(v);
    return cikti;
  }
  if (typeof body?.forEach === "function") body.forEach((v: any, k: string) => { cikti[k] = typeof v === "object" ? "[blob]" : String(v); });
  return cikti;
}
function sonForm(): Record<string, string> {
  const c = (global.fetch as jest.Mock).mock.calls;
  return formAlanlari(c[c.length - 1][1].body);
}

const PETRI = {
  status: "success", success: true, method: "plate_grid", mm_per_px: 0.118, n_wells: 1, n_cancer: 0, n_healthy: 1,
  wells: [{ well_id: "W1", label: "healthy", organ_id: 0, centroid_cabin_mm: [19.3, 0, 0], D: [0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3],
    E_cancer: 0.1, E_healthy: 0.1, area_mm2: 150, cancer_reasons: [] }],
  image_base64: "OUT64", yolo_ayar: { conf: 0.25, iou: 0.7 }, resize: {}, plausibility: {}, pemf_valid: true, kosulsuz: true,
  warnings: ["kosulsuz_makullik: not_a_petri_plate - x"],
  pemf_kapisi: { surulebilir: true, pemf_gecerli: true, kosulsuz: true, atlanan: [], nedenler: [], eylem: "", mesajlar: [], varsayimlar: [] },
};
const FANTOM = {
  status: "success", success: true, method: "coil_ring", mm_per_px: 0.31, n_tumor: 1, n_healthy: 0, healthy_regions: [],
  tumor_regions: [{ tumor_id: "T1", centroid_cabin_mm: [-43.6, -15, -9.2], D: [0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4], E_cancer: 0.005, E_healthy: 0.004, area_mm2: 316 }],
  image_base64: "OUT64", pemf_valid: true, reliable: false, warnings: [],
  pemf_kapisi: { surulebilir: true, pemf_gecerli: true, kosulsuz: true, atlanan: ["guvenilir_degil"], nedenler: ["guvenilir_degil"],
    eylem: "Tümör tespiti güvenilir değil", mesajlar: [{ kod: "guvenilir_degil", metin: "Tümör tespiti güvenilir değil" }], varsayimlar: [] },
};

let mockYanit: any = PETRI;
beforeEach(() => {
  mockHastaId += 1;
  mockMode = "researcher";
  mockToast.mockClear();
  (serviceConfig as any).apiBaseUrl = "http://127.0.0.1:8000/api";
  global.fetch = jest.fn(async () => ({ ok: true, json: async () => mockYanit })) as any;
});

async function modulAc(etiket: string, baslik: string, dugme: string, galeri = true) {
  const u = render(<Ekran />);
  fireEvent.press(u.getAllByLabelText(etiket)[0]);
  await waitFor(() => u.getByText(baslik));
  if (galeri) {
    await act(async () => { fireEvent.press(u.getByText("Galeriden Seç")); });
    await waitFor(() => expect(u.getByText(dugme)).toBeTruthy());
  }
  return u;
}
async function analizEt(u: ReturnType<typeof render>, dugme: string) {
  await waitFor(() => u.getByText(dugme));
  // `Button` aynı eylemi 400 ms içinde iki kez ateşlemez (çift-tık koruması) — art arda analizde bekle.
  await act(async () => { await new Promise((r) => setTimeout(r, 450)); });
  const once = (global.fetch as jest.Mock).mock.calls.length;
  await act(async () => { fireEvent.press(u.getByText(dugme)); });
  await waitFor(() => expect((global.fetch as jest.Mock).mock.calls.length).toBeGreaterThan(once));
  const form = sonForm();
  await waitFor(() => u.getByText(dugme));
  return form;
}

describe.each([
  ["Petri Kuyu", "Petri Kuyu Analizi", "Petri Analizini Başlat", "petri-kosul", PETRI],
  ["Fantom Tümör", "Fantom Tümör Analizi", "Fantom Analizini Başlat", "fantom-kosul", FANTOM],
])("%s", (etiket, baslik, dugme, testID, yanit) => {
  it("KRİTİK: varsayılan KOŞULLU — istekte `kosulsuz` YOK (eski istek); Koşulsuz seçilince `kosulsuz=true` + uyarı", async () => {
    mockYanit = yanit;
    const u = await modulAc(etiket, baslik, dugme);
    expect(u.getByTestId(testID)).toBeTruthy();
    expect(u.getByLabelText("Koşullu").props.accessibilityState?.selected).toBe(true);
    const f0 = await analizEt(u, dugme);
    expect(f0.kosulsuz).toBeUndefined();
    fireEvent.press(u.getByLabelText("Koşulsuz"));
    await waitFor(() => expect(u.getByLabelText("Koşulsuz").props.accessibilityState?.selected).toBe(true));
    expect(String(u.getByTestId(`${testID}-aciklama`).props.children)).toContain("sonuç doğrulanmamıştır");
    const f1 = await analizEt(u, dugme);
    expect(f1.kosulsuz).toBe("true");
    await waitFor(() => u.getByTestId("pemf-kapisi-kosulsuz"));
  });

  it("KRİTİK: 'Kabin kamerasından çek' karesi analiz girdisi olur (backend bu makinede)", async () => {
    mockYanit = yanit;
    const u = await modulAc(etiket, baslik, dugme, false);
    (global.fetch as jest.Mock).mockImplementationOnce(async () => ({
      ok: true, json: async () => ({ status: "success", indeks: 1, genislik: 1920, yukseklik: 1080, image_base64: "KABIN64" }),
    }));
    await act(async () => { fireEvent.press(u.getByText("Kabin kamerasından çek")); });
    const cagri = (global.fetch as jest.Mock).mock.calls[0];
    expect(String(cagri[0])).toBe("http://127.0.0.1:8000/api/settings/kabin-kamerasi/kare");
    expect(cagri[1].method).toBe("POST");
    const f = await analizEt(u, dugme);
    expect(f.image_base64).toBe("KABIN64");
  });

  it("KRİTİK: kare alınamazsa backend'in EYLEM metni gösterilir, analiz girdisi değişmez", async () => {
    mockYanit = yanit;
    const u = await modulAc(etiket, baslik, dugme, false);
    const DETAY = "Kabin kamerası seçilmedi. Ayarlar ▸ Kabin kamerası bölümünden kabin kamerasını seçip yeniden deneyin.";
    (global.fetch as jest.Mock).mockImplementationOnce(async () => ({ ok: false, json: async () => ({ detail: DETAY }) }));
    await act(async () => { fireEvent.press(u.getByText("Kabin kamerasından çek")); });
    await waitFor(() => expect(mockToast).toHaveBeenCalled());
    expect(String(mockToast.mock.calls[0][0])).toContain("Ayarlar ▸ Kabin kamerası");
    expect(u.getByText(dugme).props).toBeTruthy();
  });

  it("KARŞIT: backend başka makinedeyse (LAN) 'Kabin kamerasından çek' YOK", async () => {
    (serviceConfig as any).apiBaseUrl = "http://192.168.1.50:8000/api";
    const u = await modulAc(etiket, baslik, dugme, false);
    expect(u.queryByText("Kabin kamerasından çek")).toBeNull();
    expect(u.getByTestId(testID)).toBeTruthy();
  });
});
