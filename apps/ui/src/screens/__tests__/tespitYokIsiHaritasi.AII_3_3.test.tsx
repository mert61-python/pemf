// Author: mertaygn, cglrgrkn
/**
 * AII-3.3 (AI incelemesi A3, 2026-10-12) — tespit YOKKEN ısı haritası "tespitleri açıklıyor" diye sunulmaz.
 *
 * Ölçülen (gerçek yolov8s PT/ONNX, CPU; `_inceleme/kayit/k2_yolo_sonda.json`): siyah / düz gri / beyaz / gürültü görüntüde canlı
 * ONNX tespiti 0 kutu (PT ankraj en yüksek skoru 4e-5…0,19 < 0,25); `YoloDetCAM` bu durumda "en iyi 5 ankraja" düşer ve haritayı
 * maks = 1'e ölçekler → yanıt "başarılı" + parlak kırmızı leke. BT kartı aynı ekranda "Görüntüde böbrek yapısı tespit edilemedi" /
 * "✓ Taş veya kist bulgusu yok" derken haritanın notu "Kırmızı bölgeler modelin KUTULARDAKİ TESPİTLERE karar verirken en çok
 * dayandığı alanlardır … kutuyla birlikte okuyun" diyor; retikülosit kartı 0/0/0 sayımın altında "kırmızı = karara güçlü etki".
 * ONNX ↔ PT kutu kümeleri birebir (14/14, Δgüven 0,0) ve iki eşik de katı `> 0,25` → "ekranda 0 tespit" ⇔ "harita eşik altı aday".
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
let mockHastaId = 3300;
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

async function sec(u: ReturnType<typeof render>, etiket: string) {
  fireEvent.press(u.getAllByLabelText(etiket)[0]);
  const adaylar = u.getAllByText("Galeriden Seç");
  await act(async () => { fireEvent.press(adaylar[adaylar.length - 1]); });
}

beforeEach(() => {
  mockHastaId += 1;
  mockMode = "veterinarian";
  global.fetch = jest.fn();
  jest.spyOn(Image, "getSize").mockImplementation(((_u: string, ok: (w: number, h: number) => void) => { ok(800, 600); }) as any);
});
afterEach(() => { jest.restoreAllMocks(); });

const TESPIT_YOK = /Tespit yok/;
const KUTU_IDDIASI = /kutulardaki tespitlere/;

describe("AII-3.3: tespit yokken ısı haritası tespiti açıklıyor diye sunulmaz", () => {
  it("BT: 0 tespit + harita → 'Tespit yok' notu; 'kutulardaki tespitlere' iddiası YOK", async () => {
    mockMode = "researcher";
    const u = render(<Ekran />);
    await sec(u, "Böbrek CT");
    fireEvent.press(u.getByText(/Isı haritası üret \(tespit hedefli HiRes-CAM/));
    fetchYaniti({ status: "success", n_detections: 0, image_base64: "IMG64", xai_image_base64: "XAI64", xai_method: "hirescam",
      class_counts: {}, detections: [] });
    await act(async () => { fireEvent.press(u.getByText("CT Analizini Başlat")); });
    await waitFor(() => u.getByText(/böbrek yapısı tespit edilemedi/));
    expect(u.queryByText(KUTU_IDDIASI)).toBeNull();
    expect(u.getByText(TESPIT_YOK)).toBeTruthy();
  });

  it("BT KARŞIT: tespit varken eski not ('kutuyla birlikte okuyun') aynen kalır", async () => {
    mockMode = "researcher";
    const u = render(<Ekran />);
    await sec(u, "Böbrek CT");
    fireEvent.press(u.getByText(/Isı haritası üret \(tespit hedefli HiRes-CAM/));
    fetchYaniti({ status: "success", n_detections: 1, image_base64: "IMG64", xai_image_base64: "XAI64", xai_method: "hirescam",
      class_counts: { "Kidney Stone": 1 }, detections: [{ class_name: "Kidney Stone", conf: 0.9, bbox_xyxy: [0, 0, 10, 10] }] });
    await act(async () => { fireEvent.press(u.getByText("CT Analizini Başlat")); });
    await waitFor(() => u.getByText(KUTU_IDDIASI));
    expect(u.queryByText(TESPIT_YOK)).toBeNull();
  });

  it("Retikülosit: 0/0/0 sayım + harita → 'Tespit yok' notu", async () => {
    const u = render(<Ekran />);
    await sec(u, "Retikülosit");
    fireEvent.press(u.getByText(/Isı haritası üret/));
    fetchYaniti({ status: "success", image_base64: "IMG64", xai_image_base64: "XAI64", xai_method: "hirescam",
      counts: { erythrocyte: 0, "punctate reticulocyte": 0, "aggregate reticulocyte": 0 } });
    await act(async () => { fireEvent.press(u.getByText("AI Analizini Başlat")); });
    await waitFor(() => u.getByText(/Isı haritası — modelin baktığı bölgeler/));
    expect(u.getByText(TESPIT_YOK)).toBeTruthy();
  });

  it("Retikülosit KARŞIT: hücre sayıldıysa 'Tespit yok' notu YOK", async () => {
    const u = render(<Ekran />);
    await sec(u, "Retikülosit");
    fireEvent.press(u.getByText(/Isı haritası üret/));
    fetchYaniti({ status: "success", image_base64: "IMG64", xai_image_base64: "XAI64", xai_method: "hirescam",
      counts: { erythrocyte: 40, "punctate reticulocyte": 2, "aggregate reticulocyte": 1 } });
    await act(async () => { fireEvent.press(u.getByText("AI Analizini Başlat")); });
    await waitFor(() => u.getByText(/Isı haritası — modelin baktığı bölgeler/));
    expect(u.queryByText(TESPIT_YOK)).toBeNull();
  });

  it("Retikülosit KARŞIT (karışık sayım): eritrosit sayıldı, retikülosit 0 → 'Tespit yok' notu YOK", async () => {
    // Orkestratör (AI inceleme): normal yaymada retikülosit 0 olağandır; "herhangi bir sınıf 0" (`some`) mutantı ajanın
    // karşıtında (tüm sınıflar > 0) YEŞİL kalıyordu — gerçekçi karışık sayım bu kolu kilitler.
    const u = render(<Ekran />);
    await sec(u, "Retikülosit");
    fireEvent.press(u.getByText(/Isı haritası üret/));
    fetchYaniti({ status: "success", image_base64: "IMG64", xai_image_base64: "XAI64", xai_method: "hirescam",
      counts: { erythrocyte: 40, "punctate reticulocyte": 0, "aggregate reticulocyte": 0 } });
    await act(async () => { fireEvent.press(u.getByText("AI Analizini Başlat")); });
    await waitFor(() => u.getByText(/Isı haritası — modelin baktığı bölgeler/));
    expect(u.queryByText(TESPIT_YOK)).toBeNull();
  });
});
