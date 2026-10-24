// Author: mertaygn, cglrgrkn
/**
 * T3 · Y191 (sahip 2026-10-24: "yolo güven skoru 0.6 falan set eder misin petride") — arayüz petri YOLO güveni varsayılanını 0,6
 * bilir: tekil kipte "Tespit güveni" alanı "varsayılan 0.6" der; 0,6 ile üretilen sonuçta "değiştirilmiş ayarlarla üretildi" satırı
 * ÇIKMAZ (ölçülen önce: arayüz 0,25'i sabit karşılaştırıyordu → yeni varsayılanla her sonuç "değiştirilmiş" görünürdü); açıkça 0,25
 * ile üretilen sonuç o satırda "conf 0,25" olarak görünür (karşıt).
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
let mockHastaId = 19190;
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigate: jest.fn(), selectedPatient: { id: mockHastaId, name: `Y191-${mockHastaId}` } }),
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

const PETRI = (conf: number) => ({
  status: "success", success: true, method: "plate_grid", mm_per_px: 0.118, n_wells: 1, n_cancer: 0, n_healthy: 1,
  wells: [{ well_id: "W1", label: "healthy", organ_id: 0, centroid_cabin_mm: [19.3, 0, 0], D: [0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3],
    E_cancer: 0.1, E_healthy: 0.1, area_mm2: 150, cancer_reasons: [] }],
  image_base64: "OUT64", yolo_ayar: { conf, iou: 0.7 }, resize: {}, plausibility: {}, pemf_valid: true, kosulsuz: false, warnings: [],
  pemf_kapisi: { surulebilir: true, pemf_gecerli: true, kosulsuz: false, atlanan: [], nedenler: [], eylem: "", mesajlar: [], varsayimlar: [] },
});

let mockYanit: any = PETRI(0.6);
beforeEach(() => {
  mockHastaId += 1;
  mockToast.mockClear();
  global.fetch = jest.fn(async () => ({ ok: true, json: async () => mockYanit })) as any;
});

async function analiz(conf: number) {
  mockYanit = PETRI(conf);
  const u = render(<Ekran />);
  fireEvent.press(u.getAllByLabelText("Petri Kuyu")[0]);
  await waitFor(() => u.getByText("Petri Kuyu Analizi"));
  await act(async () => { fireEvent.press(u.getByText("Galeriden Seç")); });
  await waitFor(() => u.getByText("Petri Analizini Başlat"));
  await act(async () => { await new Promise((r) => setTimeout(r, 450)); });
  await act(async () => { fireEvent.press(u.getByText("Petri Analizini Başlat")); });
  await waitFor(() => u.getByText(/W1/));
  return u;
}

it("KRİTİK: varsayılan 0,6 ile üretilen sonuçta 'değiştirilmiş ayarlarla üretildi' satırı YOK", async () => {
  const u = await analiz(0.6);
  expect(u.queryByText(/değiştirilmiş ayarlarla üretildi/)).toBeNull();
});

it("KARŞIT: açıkça 0,25 ile üretilen sonuç 'conf 0,25' olarak işaretlenir", async () => {
  const u = await analiz(0.25);
  await waitFor(() => expect(u.getByText(/değiştirilmiş ayarlarla üretildi/)).toBeTruthy());
  expect(String(u.getByText(/değiştirilmiş ayarlarla üretildi/).props.children)).toMatch(/conf 0[,.]25/);
});

it("KRİTİK: tekil kipte 'Tespit güveni' alanı varsayılanı 0.6 gösterir", async () => {
  const u = render(<Ekran />);
  fireEvent.press(u.getAllByLabelText("Petri Kuyu")[0]);
  await waitFor(() => u.getByText("Petri Kuyu Analizi"));
  fireEvent.press(u.getByLabelText("Tekil petri kapları"));
  fireEvent.press(u.getByLabelText("Gelişmiş araştırma ayarları"));
  await waitFor(() => u.getByLabelText("Tespit güveni (conf)"));
  expect(String(u.getByLabelText("Tespit güveni (conf)").props.placeholder)).toContain("0.6");
});
