// Author: mertaygn, cglrgrkn
/**
 * AI-2 C5 — AI Hub petri / fantom kartları hocanın v2 / v3 sonucunu DÜRÜST gösterir (2026-10-12).
 *
 * KİLİTLENEN DAVRANIŞLAR (varlık değil UYGULAMA — gönderilen FormData ve ekrandaki metin ölçülür):
 *  1) PEMF tüketim kapısı geçmezse kart backend'in EYLEM metnini AYNEN gösterir ("PEMF değerleri geçersiz: plakanın
 *     kabindeki konumu bilinmiyor — kabine ArUco koyun ya da konumu ayarlayın.") ve "⛔ PEMF girdisi GEÇERSİZ" rozetini;
 *     laboratuvar VARSAYIMLARI ayrıca listelenir. Eski backend (alan yok) → kutu ÇİZİLMEZ, kart çökmez.
 *  2) Kuyucuk kimliği A1–D6, tümör kimliği T1–T5 başlıkta; kanser gerekçesi v2 nedenleri (blue_frac / delta_b / lab_b).
 *  3) KİP: yalnız "24 kuyucuklu plaka" (T3 · Y193: tekil kap kipi arayüzden kalktı) — HİÇBİR kip alanı gitmez. Plaka kipinde
 *     ÖLÇÜLEN anlamsız alanlar (conf / IoU / "petri değil" eşikleri / petri çapı) GÖRÜNMEZ ve GİTMEZ; kontrol kuyucukları ve A1
 *     köşesi gider.
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
let mockHastaId = 900;
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigate: jest.fn(), selectedPatient: { id: mockHastaId, name: `V2V3-${mockHastaId}` } }),
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

import { AiHubScreen as Ekran } from "@/screens/AiHubScreen";

const EYLEM = "PEMF değerleri geçersiz: plakanın kabindeki konumu bilinmiyor — kabine ArUco koyun ya da konumu ayarlayın.";

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

const kuyu = (id: string, label = "healthy", reasons: string[] = []) => ({
  well_id: id, label, organ_id: label === "cancer" ? 1 : 0, centroid_cabin_mm: [19.3, 0, 0], D: [0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3],
  E_cancer: 0.1, E_healthy: 0.1, area_mm2: 150, cancer_reasons: reasons,
});

const PETRI_V2 = {
  status: "success", success: true, method: "plate_grid", mm_per_px: 0.118, n_wells: 2, n_cancer: 1, n_healthy: 1,
  wells: [kuyu("A1"), kuyu("B2", "cancer", ["delta_b"])], image_base64: "OUT64", yolo_ayar: { conf: 0.6, iou: 0.7, imgsz: 640, plate_type: 24 },
  resize: {}, plausibility: { kip: "plaka" }, pemf_valid: false, coord_frame: "plate", warnings: ["pemf_frame_unknown: x"],
  pemf_kapisi: {
    surulebilir: false, pemf_gecerli: false, nedenler: ["pemf_gecersiz"], eylem: EYLEM,
    mesajlar: [{ kod: "pemf_gecersiz", metin: EYLEM }],
    varsayimlar: [{ kod: "a1_kosesi", metin: "VARSAYIM: plakanın A1 köşesi görüntüden okunmuyor (test)." }],
  },
};

const FANTOM_V3 = {
  status: "success", success: true, method: "coil_ring", mm_per_px: 0.31, n_tumor: 2, n_healthy: 0, healthy_regions: [],
  tumor_regions: [
    { tumor_id: "T1", centroid_cabin_mm: [-43.6, -15, -9.2], D: [0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4], E_cancer: 0.005, E_healthy: 0.004, area_mm2: 316 },
    { tumor_id: "T2", centroid_cabin_mm: [-43.6, -16.5, 15.3], D: [0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4], E_cancer: 0.006, E_healthy: 0.006, area_mm2: 490 },
  ],
  image_base64: "OUT64", pemf_valid: true, reliable: true, pemf_source: "cst_phantom_box", coord_frame: "cabin_cst_phantom_box",
  warnings: ["pemf_axis_sign_assumed: x"],
  pemf_kapisi: {
    surulebilir: true, pemf_gecerli: true, nedenler: [], eylem: "", mesajlar: [],
    varsayimlar: [{ kod: "pemf_axis_sign_assumed", metin: "VARSAYIM: fantom CST eğitim kutusuna eşlendi (test)." }],
  },
};

let mockYanit: any = PETRI_V2;
beforeEach(() => {
  mockHastaId += 1;
  mockMode = "researcher";
  mockToast.mockClear();
  global.fetch = jest.fn(async () => ({ ok: true, json: async () => mockYanit })) as any;
});

async function modulAc(etiket: string, baslik: string, dugme: string) {
  const u = render(<Ekran />);
  fireEvent.press(u.getAllByLabelText(etiket)[0]);
  await waitFor(() => u.getByText(baslik));
  // act: görsel seçici + küçültme SÖZLERİ çözülsün (yoksa analiz düğmesi görselsiz basılır, istek atılmaz — E07 deseni)
  await act(async () => {
    fireEvent.press(u.getByText("Galeriden Seç"));
  });
  await waitFor(() => expect(u.getByText(dugme)).toBeTruthy());
  return u;
}

async function analizEt(u: ReturnType<typeof render>, dugme: string) {
  await act(async () => {
    fireEvent.press(u.getByText(dugme));
  });
  await waitFor(() => expect(global.fetch as jest.Mock).toHaveBeenCalled());
  return formAlanlari((global.fetch as jest.Mock).mock.calls[0][1].body);
}

describe("AI-2 C5 · petri v2 kartı", () => {
  it("KRİTİK: PEMF geçersizken EYLEM metni ve GEÇERSİZ rozeti AYNEN görünür; A1–D6 + v2 kanser gerekçesi", async () => {
    mockYanit = PETRI_V2;
    const u = await modulAc("Petri Kuyu", "Petri Kuyu Analizi", "Petri Analizini Başlat");
    await analizEt(u, "Petri Analizini Başlat");
    await waitFor(() => u.getByTestId("pemf-kapisi"));
    expect(u.getByText("⛔ PEMF girdisi GEÇERSİZ")).toBeTruthy();
    expect(u.getByTestId("pemf-kapisi-pemf_gecersiz").props.children.join("")).toContain(EYLEM);
    expect(u.getByTestId("pemf-varsayim-a1_kosesi")).toBeTruthy();
    expect(u.getByText(/D \/ P \/ E değerleri bobin sürüşüne ESAS ALINMAZ/)).toBeTruthy();
    expect(u.getAllByText(/^A1/).length).toBeGreaterThan(0);
    expect(u.getByText(/gerekçe: delta_b/)).toBeTruthy();
  });

  it("KRİTİK: varsayılan PLAKA kipi kip alanı GÖNDERMEZ; conf / IoU / denetim eşikleri GÖRÜNMEZ", async () => {
    mockYanit = PETRI_V2;
    const u = await modulAc("Petri Kuyu", "Petri Kuyu Analizi", "Petri Analizini Başlat");
    fireEvent.press(u.getByLabelText("Gelişmiş araştırma ayarları"));
    expect(u.queryByLabelText("Tespit güveni (conf)")).toBeNull();
    expect(u.queryByLabelText("Denetim: güven ≥")).toBeNull();
    expect(u.queryByLabelText("Petri çapı (cm)")).toBeNull();
    expect(u.getByLabelText("Küçültme (uzun kenar, px)")).toBeTruthy();
    const alanlar = await analizEt(u, "Petri Analizini Başlat");
    for (const ad of ["plate_type", "control_healthy", "control_cancer", "a1_corner", "yolo_conf", "petri_diameter_cm"]) {
      expect(alanlar[ad]).toBeUndefined();
    }
  });

  it("KRİTİK: plaka kipinde KONTROL KUYUCUKLARI ve A1 köşesi GİDER", async () => {
    mockYanit = PETRI_V2;
    const u = await modulAc("Petri Kuyu", "Petri Kuyu Analizi", "Petri Analizini Başlat");
    fireEvent.press(u.getByLabelText("Gelişmiş araştırma ayarları"));
    fireEvent.changeText(u.getByLabelText("Sağlıklı kontrol kuyucukları"), "a1, D6");
    fireEvent.changeText(u.getByLabelText("Boyalı kontrol kuyucukları"), "B2");
    fireEvent.press(u.getByLabelText("A1 köşesi sağ-alt"));
    const alanlar = await analizEt(u, "Petri Analizini Başlat");
    expect(alanlar.control_healthy).toBe("a1, D6");
    expect(alanlar.control_cancer).toBe("B2");
    expect(alanlar.a1_corner).toBe("br");
    expect(alanlar.plate_type).toBeUndefined();
  });

  it("KRİTİK (T3 · Y193): kip seçici YOK — tekil kap kipi seçilemez, plate_type hiçbir yolda GİTMEZ; küçültme gider", async () => {
    mockYanit = PETRI_V2;
    const u = await modulAc("Petri Kuyu", "Petri Kuyu Analizi", "Petri Analizini Başlat");
    expect(u.queryByLabelText("Tekil petri kapları")).toBeNull();
    expect(u.queryByLabelText("24 kuyucuklu plaka")).toBeNull();
    expect(u.queryByLabelText("Petri çapı (cm)")).toBeNull();
    fireEvent.press(u.getByLabelText("Gelişmiş araştırma ayarları"));
    fireEvent.changeText(u.getByLabelText("Küçültme (uzun kenar, px)"), "960");
    const alanlar = await analizEt(u, "Petri Analizini Başlat");
    expect(alanlar.plate_type).toBeUndefined();
    expect(alanlar.petri_diameter_cm).toBeUndefined();
    expect(alanlar.resize_max).toBe("960");
  });

  it("KARŞIT: eski backend (pemf_kapisi YOK) → kutu çizilmez, kart çökmez", async () => {
    const { pemf_kapisi, pemf_valid, ...eski } = PETRI_V2 as any;
    mockYanit = { ...eski, wells: [{ ...kuyu("W1"), cancer_reasons: undefined }] };
    const u = await modulAc("Petri Kuyu", "Petri Kuyu Analizi", "Petri Analizini Başlat");
    await analizEt(u, "Petri Analizini Başlat");
    await waitFor(() => u.getByText(/kuyu ·/));
    expect(u.queryByTestId("pemf-kapisi")).toBeNull();
  });
});

describe("AI-2 C5 · fantom v3 kartı", () => {
  it("KRİTİK: tümör kimliği T1–T5, geçerli + güvenilir rozetleri ve CST VARSAYIMI görünür", async () => {
    mockYanit = FANTOM_V3;
    const u = await modulAc("Fantom Tümör", "Fantom Tümör Analizi", "Fantom Analizini Başlat");
    await analizEt(u, "Fantom Analizini Başlat");
    await waitFor(() => u.getByTestId("pemf-kapisi"));
    expect(u.getByText(/^Tümör T1/)).toBeTruthy();
    expect(u.getByText(/^Tümör T2/)).toBeTruthy();
    expect(u.getByText(/✔ PEMF girdisi geçerli/)).toBeTruthy();
    expect(u.getByText(/✔ tespit güvenilir/)).toBeTruthy();
    expect(u.getByTestId("pemf-varsayim-pemf_axis_sign_assumed")).toBeTruthy();
    expect(u.queryByText(/ESAS ALINMAZ/)).toBeNull();
  });

  it("KRİTİK: güvenilmez fantom sonucu GÜVENİLİR DEĞİL rozeti + backend eylemi", async () => {
    const m = "Tümör tespiti güvenilir değil (test) — yeniden çekin.";
    mockYanit = { ...FANTOM_V3, reliable: false, pemf_kapisi: { ...FANTOM_V3.pemf_kapisi, surulebilir: false, nedenler: ["guvenilir_degil"], eylem: m, mesajlar: [{ kod: "guvenilir_degil", metin: m }] } };
    const u = await modulAc("Fantom Tümör", "Fantom Tümör Analizi", "Fantom Analizini Başlat");
    await analizEt(u, "Fantom Analizini Başlat");
    await waitFor(() => u.getByTestId("pemf-kapisi"));
    expect(u.getByText(/⛔ tespit güvenilir DEĞİL/)).toBeTruthy();
    expect(u.getByTestId("pemf-kapisi-guvenilir_degil").props.children.join("")).toContain(m);
  });
});
