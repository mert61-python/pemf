// Author: mertaygn, cglrgrkn
/**
 * AI1.X1 (hoca XAI v3, 2026-10) — termal ısı haritası başlığı haritanın AÇIKLADIĞI kararı söyler.
 *
 * Ölçülen durum (2026-10-11, gerçek GhostNetV2.pt): sunucu ısı haritasında HER ZAMAN "Hasta" lojitini açıklıyordu; veteriner
 * "Sağlıklı" sonucun altında "kırmızı = karara güçlü etki" başlığıyla aslında "Hasta" kararının kanıtını görüyordu. Düzeltmede
 * harita tahmin edilen sınıfı açıklar ve sunucu açıklanan sınıfı `xai_hedef` ile döner; başlık bunu okumalı. `xai_hedef` yoksa
 * (eski sunucu / retikülosit) genel başlık kalır.
 */
let mockMode = "veterinarian";
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => null),
  apiPost: jest.fn(async () => null),
  authHeaders: jest.fn(() => ({})),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  AI_TIMEOUT_MS: 120000,
  aiHataMesaji: jest.fn(() => "hata"),
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" },
}));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ userMode: mockMode, hasAiHub: true }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "v@x.com" }) }));
jest.mock("@/context/EntitlementContext", () => ({ useEntitlement: () => ({ research: true }) }));
let mockHastaId = 900;
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigate: jest.fn(), selectedPatient: { id: mockHastaId, name: `Kedi-${mockHastaId}` } }),
}));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionFresh: false }),
}));
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
jest.mock("expo-image-picker", () => ({
  launchImageLibraryAsync: jest.fn(async () => ({ canceled: false, assets: [{ uri: "file:///foto.jpg" }] })),
  launchCameraAsync: jest.fn(async () => ({ canceled: false, assets: [{ uri: "file:///foto.jpg" }] })),
  MediaTypeOptions: { Images: "Images" },
}));
jest.mock("expo-image-manipulator", () => ({
  manipulateAsync: jest.fn(async () => ({ uri: "file:///kucuk.jpg", base64: "KUCUK64" })),
  SaveFormat: { JPEG: "jpeg" },
}));
jest.mock("expo-document-picker", () => ({
  getDocumentAsync: jest.fn(async () => ({ canceled: true, assets: [] })),
}));

import React from "react";
import { Image } from "react-native";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";

import { AiHubScreen as Ekran } from "@/screens/AiHubScreen";

function fetchYaniti(govde: any) {
  (global.fetch as jest.Mock).mockResolvedValueOnce({ ok: true, json: async () => govde });
}

async function termalAnalizi(govde: any) {
  const u = render(<Ekran />);
  fireEvent.press(u.getAllByLabelText("Termal")[0]);
  const adaylar = u.getAllByText("Galeriden Seç");
  await act(async () => { fireEvent.press(adaylar[adaylar.length - 1]); });
  fireEvent.press(u.getByText(/Isı haritası üret \(modelin baktığı bölgeler/));
  fetchYaniti(govde);
  await act(async () => { fireEvent.press(u.getByText("AI Analizini Başlat")); });
  return u;
}

beforeEach(() => {
  mockHastaId += 1;
  mockMode = "veterinarian";
  global.fetch = jest.fn();
  jest.spyOn(Image, "getSize").mockImplementation(((_u: string, ok: (w: number, h: number) => void) => { ok(800, 600); }) as any);
});
afterEach(() => { jest.restoreAllMocks(); });

describe("AI1.X1: termal ısı haritası başlığı açıklanan kararı söyler", () => {
  it("Sağlıklı sonuç + xai_hedef=Healthy → başlık 'Sağlıklı' kararını söyler, 'Hasta' DEMEZ", async () => {
    const u = await termalAnalizi({
      status: "success", image_base64: "IMG64", xai_image_base64: "XAI64", xai_method: "hirescam", xai_hedef: "Healthy",
      prediction: { label: "Healthy", confidence: 0.99, probability_sick: 0.01 },
    });
    await waitFor(() => u.getByText(/Isı haritası — modeli “Sağlıklı” kararına götüren bölgeler/));
    expect(u.queryByText(/Isı haritası — modeli “Hasta/)).toBeNull();
    expect(u.queryByText(/Isı haritası — modelin baktığı bölgeler/)).toBeNull();
  });

  it("Hasta sonuç + xai_hedef=Sick → başlık 'Hasta (Riskli)' kararını söyler", async () => {
    const u = await termalAnalizi({
      status: "success", image_base64: "IMG64", xai_image_base64: "XAI64", xai_method: "hirescam", xai_hedef: "Sick",
      prediction: { label: "Sick", confidence: 0.97, probability_sick: 0.97 },
    });
    await waitFor(() => u.getByText(/Isı haritası — modeli “Hasta \(Riskli\)” kararına götüren bölgeler/));
    expect(u.queryByText(/“Sağlıklı” kararına/)).toBeNull();
  });

  it("KARŞIT: xai_hedef YOKSA (eski sunucu) genel başlık kalır — karar uydurulmaz", async () => {
    const u = await termalAnalizi({
      status: "success", image_base64: "IMG64", xai_image_base64: "XAI64",
      prediction: { label: "Healthy", confidence: 0.99, probability_sick: 0.01 },
    });
    await waitFor(() => u.getByText(/Isı haritası — modelin baktığı bölgeler/));
    expect(u.queryByText(/kararına götüren bölgeler/)).toBeNull();
  });
});
