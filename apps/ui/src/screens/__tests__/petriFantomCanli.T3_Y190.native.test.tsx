// Author: mertaygn, cglrgrkn
/**
 * T3 · Y190 (sahip 2026-10-24: "telefonda da telefonun kamerasını açmalı") — TELEFON (yerel uygulama): petri / fantom "Fotoğraf
 * Çek" telefonun kamerasını açar, "Canlı Kamera" telefonun kamerasıyla (CameraView) — kabin kamerası ucu ÇAĞRILMAZ, kabin bölümü YOK.
 * Arka uç adresi bilerek 127.0.0.1: "bu makinede" kararı yalnız web'de geçerli (telefonda kabin kamerası telefonun makinesinde değil).
 */
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
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: "researcher", hasAiHub: true }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "r@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "r@x.com" }) }));
jest.mock("@/context/EntitlementContext", () => ({ useEntitlement: () => ({ research: true }) }));
let mockHastaId = 19100;
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigate: jest.fn(), selectedPatient: { id: mockHastaId, name: `Y190n-${mockHastaId}` } }),
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
  launchCameraAsync: jest.fn(async () => ({ canceled: false, assets: [{ uri: "file:///tel.jpg", base64: "VEVM", file: null }] })),
}));
jest.mock("expo-image-manipulator", () => ({
  SaveFormat: { JPEG: "jpeg" },
  manipulateAsync: jest.fn(async () => ({ uri: "file:///tel-kucuk.jpg", base64: "VEVM" })),
}));

import React from "react";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import * as ImagePicker from "expo-image-picker";

import { AiHubScreen as Ekran } from "@/screens/AiHubScreen";

jest.setTimeout(20000);

const KOK = /^https?:\/\/[^/]+\/api/;
const yolu = (url: unknown) => String(url).replace(KOK, "");
const cagrilar = (onek: string) => (global.fetch as jest.Mock).mock.calls.filter((c) => yolu(c[0]).startsWith(onek));
function form(body: any): Record<string, string> {
  const c: Record<string, string> = {};
  const yaz = (k: string, v: any) => { c[k] = v && typeof v === "object" ? "[obj]" : String(v); };
  if (Array.isArray(body?._parts)) for (const [k, v] of body._parts) yaz(String(k), v);
  else if (typeof body?.forEach === "function") body.forEach((v: any, k: string) => yaz(k, v));
  return c;
}

beforeEach(() => {
  mockHastaId += 1;
  mockFoto.mockClear();
  (ImagePicker.launchCameraAsync as jest.Mock).mockClear();
  global.fetch = jest.fn(async () => ({
    ok: true, status: 200,
    json: async () => ({ status: "success", success: true, n_wells: 0, n_tumor: 0, wells: [], tumor_regions: [], warnings: [] }),
  })) as any;
});

describe.each([
  ["Petri Kuyu", "Petri Kuyu Analizi", "/ai/vision/em_petri"],
  ["Fantom Tümör", "Fantom Tümör Analizi", "/ai/vision/em_fantom"],
])("%s (telefon)", (etiket, baslik, uc) => {
  it("KRİTİK: 'Fotoğraf Çek' telefonun kamerasını açar; kabin ucu çağrılmaz, kabin bölümü YOK", async () => {
    const u = render(<Ekran />);
    fireEvent.press(u.getAllByLabelText(etiket)[0]);
    await waitFor(() => u.getByText(baslik));
    expect(u.queryByTestId("kabin-kamerasi-tara")).toBeNull();
    await act(async () => { fireEvent.press(u.getByText("Fotoğraf Çek")); });
    await waitFor(() => expect(ImagePicker.launchCameraAsync).toHaveBeenCalledTimes(1));
    expect(cagrilar("/settings/kabin-kamerasi")).toHaveLength(0);
  });

  it("KRİTİK: 'Canlı Kamera' telefonun kamerasıyla — kare `image_base64` + canlı oturum başlığı", async () => {
    const u = render(<Ekran />);
    fireEvent.press(u.getAllByLabelText(etiket)[0]);
    await waitFor(() => u.getByText(baslik));
    await act(async () => { fireEvent.press(u.getByText("Canlı Kamera")); });
    await waitFor(() => expect(cagrilar(uc).length).toBeGreaterThan(0), { timeout: 5000 });
    expect(mockFoto).toHaveBeenCalled();
    const c = cagrilar(uc)[0];
    expect(String(c[1].headers["X-PEMF-Canli-Oturum"])).toMatch(/^canli-/);
    expect(form(c[1].body).image_base64).toBe("VEVM");
    expect(cagrilar("/settings/kabin-kamerasi")).toHaveLength(0);
    await act(async () => { fireEvent.press(u.getByText("Canlıyı Durdur")); });
  });
});
