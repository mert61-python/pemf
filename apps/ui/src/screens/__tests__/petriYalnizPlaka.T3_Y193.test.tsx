// Author: mertaygn, cglrgrkn
/**
 * T3 · Y193 (sahip 2026-10-24: "24'lü ile tekilin farkı ne, sadece 24 kalsın, ai saf çalışsın") — petri modülünde YALNIZ 24 kuyucuklu
 * plaka kipi: kip seçici YOK, tekil kap alanları (petri çapı, tespit güveni, örtüşme, "petri değil" eşikleri) YOK, istekte kip / çap /
 * güven alanı GİTMEZ; "plaka bulunamadı" sonucu tekil kipe yönlendirmez. Ölçülen (önce, 87d91346): seçici ve tekil alanları VARDI,
 * sonuç "Görüntüde 24 kuyucuklu plaka değil tekil petri kapları varsa 'Tekil petri kapları' kipini seçin" diyordu.
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
let mockHastaId = 19300;
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigate: jest.fn(), selectedPatient: { id: mockHastaId, name: `Y193-${mockHastaId}` } }),
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

let mockYanit: any = null;
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

it("KRİTİK: kip seçici ve tekil kap alanları YOK; Gelişmiş'te yalnız plaka kipinde anlamlı sayısal alanlar; istekte kip / çap / güven GİTMEZ", async () => {
  mockYanit = { status: "no_detection", success: false, error: "plate_not_found", n_wells: 0, wells: [], warnings: [] };
  const u = await ac();
  for (const etiket of ["Petri analiz kipi", "24 kuyucuklu plaka", "Tekil petri kapları", "Petri çapı (cm)"]) {
    expect(u.queryByLabelText(etiket)).toBeNull();
  }
  fireEvent.press(u.getByLabelText("Gelişmiş araştırma ayarları"));
  expect(u.getByLabelText("Küçültme (uzun kenar, px)")).toBeTruthy();
  expect(u.getByLabelText("Kuyu skoru eşiği")).toBeTruthy();
  for (const etiket of ["Tespit güveni (conf)", "Örtüşme eşiği (IoU)", "Denetim: dairesellik ≥", "Denetim: güven ≥", "Denetim: en büyük tespit ≤"]) {
    expect(u.queryByLabelText(etiket)).toBeNull();
  }
  await act(async () => { fireEvent.press(u.getByText("Galeriden Seç")); });
  await waitFor(() => u.getByText("Petri Analizini Başlat"));
  await act(async () => { await new Promise((r) => setTimeout(r, 450)); });
  await act(async () => { fireEvent.press(u.getByText("Petri Analizini Başlat")); });
  await waitFor(() => expect((global.fetch as jest.Mock).mock.calls.length).toBeGreaterThan(0));
  const f = sonForm();
  for (const ad of ["plate_type", "petri_diameter_cm", "yolo_conf", "yolo_iou"]) expect(f[ad]).toBeUndefined();
  // "plaka bulunamadı" sonucu tekil kipe YÖNLENDİRMEZ
  await waitFor(() => u.getByText(/Plaka bulunamadı/));
  expect(u.queryByText(/Tekil petri kapları/)).toBeNull();
});
