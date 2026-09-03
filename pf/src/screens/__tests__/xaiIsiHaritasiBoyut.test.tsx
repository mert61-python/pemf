// Author: mertaygn, cglrgrkn
/**
 * B2-isi-haritasi-ui — XAI ısı haritası görselinin BOYUT kilidi.
 *
 * Kök neden (ölçüldü): heatmap <Image> `styles.imagePreview` ({width:"100%", height:"100%"})
 * ile SABİT-yükseklikli `imagePreviewContainer` DIŞINDA, otomatik-yükseklikli `resultBox`
 * içinde çiziliyordu → web'de %100 yükseklik belirsiz ebeveynde `auto`=0 çözülür; RNW Image
 * (background-image div + absolute <img>) sıfır-yükseklikli kutudan taşar → ince şerit +
 * alttaki karta taşma. Kilit: her modülde heatmap görseli AÇIK sayısal yükseklik ya da
 * aspectRatio taşımalı; "100%" yükseklik YASAK.
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
let mockHastaId = 500;
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigate: jest.fn(), selectedPatient: { id: mockHastaId, name: `Deney-${mockHastaId}` } }),
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
  getDocumentAsync: jest.fn(async () => ({
    canceled: false,
    assets: [{ uri: "file:///ses.wav", name: "ses.wav", file: null, mimeType: "audio/wav" }],
  })),
}));

import React from "react";
import { Image, StyleSheet } from "react-native";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";

import { AiHubScreen as Ekran } from "@/screens/AiHubScreen";

function fetchYaniti(govde: any) {
  (global.fetch as jest.Mock).mockResolvedValueOnce({ ok: true, json: async () => govde });
}

async function acVeSec(u: ReturnType<typeof render>, modulEtiketi: string) {
  fireEvent.press(u.getAllByLabelText(modulEtiketi)[0]);
  const adaylar = u.getAllByText("Galeriden Seç");
  await act(async () => { fireEvent.press(adaylar[adaylar.length - 1]); });
}

/** Kaynağı XAI64 olan <Image>'ın düzleştirilmiş stili. */
function isiHaritasiStili(u: ReturnType<typeof render>) {
  const imgs = u.UNSAFE_getAllByType(Image).filter((n: any) => String(n.props.source?.uri || "").includes("XAI64"));
  expect(imgs.length).toBe(1);
  return StyleSheet.flatten(imgs[0].props.style) as any;
}

function boyutKilidi(st: any) {
  // %100 yükseklik = belirsiz ebeveynde 0 → ince şerit + taşma (kök neden). YASAK.
  expect(st.height).not.toBe("100%");
  const sayisalYukseklik = typeof st.height === "number" && st.height > 0;
  const oranVar = typeof st.aspectRatio === "number" && st.aspectRatio > 0;
  expect(sayisalYukseklik || oranVar).toBe(true);
  expect(st.width).toBe("100%");
}

beforeEach(() => {
  mockHastaId += 1;
  mockMode = "veterinarian";
  global.fetch = jest.fn();
  // Image.getSize: jsdom/RN mock ortamında gerçek decode yok — deterministik 4:3 döndür.
  jest.spyOn(Image, "getSize").mockImplementation(((_u: string, ok: (w: number, h: number) => void) => { ok(800, 600); }) as any);
});
afterEach(() => { jest.restoreAllMocks(); });

describe("B2: XAI ısı haritası görseli — boyut/hizalama kilidi", () => {
  it("Retikülosit: heatmap görseli %100-yükseklik tuzağında DEĞİL (analiz görseliyle aynı sahne boyutu)", async () => {
    const u = render(<Ekran />);
    await acVeSec(u, "Retikülosit");
    fireEvent.press(u.getByText(/Isı haritası üret \(modelin baktığı bölgeler/));
    fetchYaniti({
      status: "success", image_base64: "IMG64", xai_image_base64: "XAI64",
      counts: { erythrocyte: 120, "punctate reticulocyte": 3, "aggregate reticulocyte": 1 },
    });
    await act(async () => { fireEvent.press(u.getByText("AI Analizini Başlat")); });
    await waitFor(() => u.getByText(/Isı haritası — modelin baktığı bölgeler/));
    const st = isiHaritasiStili(u);
    boyutKilidi(st);
  });

  it("Termal: aynı ortak kilit (VisionModule paylaşımlı)", async () => {
    const u = render(<Ekran />);
    await acVeSec(u, "Termal");
    fireEvent.press(u.getByText(/Isı haritası üret \(modelin baktığı bölgeler/));
    fetchYaniti({ status: "success", image_base64: "IMG64", xai_image_base64: "XAI64", prediction: { label: "Sick", confidence: 0.9 } });
    await act(async () => { fireEvent.press(u.getByText("AI Analizini Başlat")); });
    await waitFor(() => u.getByText(/Isı haritası — modelin baktığı bölgeler/));
    boyutKilidi(isiHaritasiStili(u));
  });

  it("Kedi Sesi: mel ısı haritası da %100-yükseklik tuzağında DEĞİL", async () => {
    const u = render(<Ekran />);
    fireEvent.press(u.getAllByLabelText("Kedi Sesi")[0]);
    await act(async () => { fireEvent.press(u.getByText("Ses Yükle")); });
    fireEvent.press(u.getByText(/Isı haritası üret \(modelin dinlediği/));
    fetchYaniti({
      status: "success", top_1_class: "Angry", top_1_prob: 0.8, top_k: [{ class: "Angry", prob: 0.8 }], xai_image_base64: "XAI64",
    });
    await act(async () => { fireEvent.press(u.getByText("Ses Analizini Başlat")); });
    await waitFor(() => u.getByText(/Mel ısı haritası/));
    boyutKilidi(isiHaritasiStili(u));
  });

  it("Böbrek Patoloji: konsensus + kararsızlık haritaları da ortak sahnede", async () => {
    mockMode = "researcher";
    const u = render(<Ekran />);
    await acVeSec(u, "Böbrek Patoloji");
    fireEvent.press(u.getByText(/Isı haritası üret \(3-model konsensus/));
    fetchYaniti({
      status: "success", grade: "grade2", confidence: 0.7, top_k: [{ class: "grade2", prob: 0.7 }],
      xai_image_base64: "XAI64", xai_disagreement_base64: "KARARSIZ64",
    });
    await act(async () => { fireEvent.press(u.getByText("Patoloji Analizini Başlat")); });
    await waitFor(() => u.getByText(/Konsensus ısı haritası/));
    boyutKilidi(isiHaritasiStili(u));
    const kararsiz = u.getByTestId("xai-kararsizlik-haritasi");
    boyutKilidi(StyleSheet.flatten(kararsiz.props.style) as any);
  });
});
