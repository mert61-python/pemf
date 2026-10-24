// Author: mertaygn, cglrgrkn
/**
 * T3 · Y191b (sahip + Çağlar Hoca 2026-10-24: "o üstünde yazan skora threshold koycam … 0.6" · "UI'dan da ayarlanır olsun o skor") —
 * plaka kipinde Gelişmiş ayarlarda "Kuyu skoru eşiği" (varsayılan 0.6; girilen değer istekte `kuyu_skor_esigi`), tekil kipte YOK
 * (hücre skoru yalnız ızgarada var); elenen hücreler sonuçta adıyla ve skoruyla söylenir; varsayılandan farklı eşik "değiştirilmiş
 * ayarlar" satırında görünür. Ölçülen (önce, 7432f62c): alan yok, eşik yok, elenen hücre bilgisi yok.
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
let mockHastaId = 19195;
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigate: jest.fn(), selectedPatient: { id: mockHastaId, name: `Y191b-${mockHastaId}` } }),
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

const PETRI = (plate: Record<string, unknown>) => ({
  status: "success", success: true, method: "plate_grid", mm_per_px: 0.118, n_wells: 1, n_cancer: 0, n_healthy: 1,
  wells: [{ well_id: "A1", label: "healthy", organ_id: 0, centroid_cabin_mm: [19.3, 0, 0], D: [0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3],
    E_cancer: 0.1, E_healthy: 0.1, area_mm2: 150, cancer_reasons: [] }],
  image_base64: "OUT64", yolo_ayar: { conf: 0.6, iou: 0.7 }, resize: {}, plausibility: {}, pemf_valid: true, kosulsuz: false, warnings: [],
  plate: { plate_type: 24, ...plate },
  pemf_kapisi: { surulebilir: true, pemf_gecerli: true, kosulsuz: false, atlanan: [], nedenler: [], eylem: "", mesajlar: [], varsayimlar: [] },
});

let mockYanit: any = PETRI({ kuyu_skor_esigi: 0.6, elenen_kuyular: [] });
beforeEach(() => {
  mockHastaId += 1;
  mockToast.mockClear();
  global.fetch = jest.fn(async () => ({ ok: true, json: async () => mockYanit })) as any;
});

async function ac() {
  const u = render(<Ekran />);
  fireEvent.press(u.getAllByLabelText("Petri Kuyu")[0]);
  await waitFor(() => u.getByText("Petri Kuyu Analizi"));
  return u;
}
async function analiz(u: ReturnType<typeof render>) {
  await act(async () => { fireEvent.press(u.getByText("Galeriden Seç")); });
  await waitFor(() => u.getByText("Petri Analizini Başlat"));
  await act(async () => { await new Promise((r) => setTimeout(r, 450)); });
  await act(async () => { fireEvent.press(u.getByText("Petri Analizini Başlat")); });
  await waitFor(() => u.getByText(/0\.118 mm\/px/));  // sonuç çizildi (A1 metni Gelişmiş panelinde de geçer)
}

it("KRİTİK: plaka kipinde 'Kuyu skoru eşiği' alanı VAR (varsayılan 0.6); girilen değer istekte `kuyu_skor_esigi`", async () => {
  const u = await ac();
  fireEvent.press(u.getByLabelText("Gelişmiş araştırma ayarları"));
  const alan = await waitFor(() => u.getByLabelText("Kuyu skoru eşiği"));
  expect(String(alan.props.placeholder)).toContain("0.6");
  fireEvent.changeText(alan, "0,4");
  await analiz(u);
  expect(sonForm().kuyu_skor_esigi).toBe("0.4");
});

it("KARŞIT: alan boşsa istekte `kuyu_skor_esigi` YOK (sunucu varsayılanı 0,6); tekil kipte alan GÖRÜNMEZ", async () => {
  const u = await ac();
  await analiz(u);
  expect(sonForm().kuyu_skor_esigi).toBeUndefined();
  const t = await ac();
  fireEvent.press(t.getByLabelText("Tekil petri kapları"));
  fireEvent.press(t.getByLabelText("Gelişmiş araştırma ayarları"));
  await waitFor(() => t.getByLabelText("Tespit güveni (conf)"));
  expect(t.queryByLabelText("Kuyu skoru eşiği")).toBeNull();
});

it("KRİTİK: elenen hücreler sonuçta ADIYLA ve skoruyla söylenir", async () => {
  mockYanit = PETRI({ kuyu_skor_esigi: 0.6, elenen_kuyular: [{ well_id: "D1", skor: 0 }, { well_id: "D3", skor: 0.195 }] });
  const u = await ac();
  await analiz(u);
  const satir = await waitFor(() => u.getByTestId("petri-elenen-kuyular"));
  const metin = String([].concat(satir.props.children).join(""));
  expect(metin).toContain("2 hücre kuyu sayılmadı");
  expect(metin).toMatch(/D1 \(0[,.]00\)/);
  expect(metin).toMatch(/D3 \(0[,.]20\)/);
});

it("KRİTİK: varsayılandan farklı eşik 'değiştirilmiş ayarlar' satırında; varsayılan (0,6) satır üretmez", async () => {
  mockYanit = PETRI({ kuyu_skor_esigi: 0.4, elenen_kuyular: [] });
  const u = await ac();
  await analiz(u);
  await waitFor(() => expect(String(u.getByText(/değiştirilmiş ayarlarla üretildi/).props.children)).toMatch(/kuyu skoru eşiği 0[,.]4/));
  mockYanit = PETRI({ kuyu_skor_esigi: 0.6, elenen_kuyular: [] });
  const v = await ac();
  await analiz(v);
  expect(v.queryByText(/değiştirilmiş ayarlarla üretildi/)).toBeNull();
  expect(v.queryByTestId("petri-elenen-kuyular")).toBeNull();
});
