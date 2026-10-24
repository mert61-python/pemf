// Author: mertaygn, cglrgrkn
/**
 * T3 · Y192 (sahip 2026-10-24: "canlı kamera çalışmıyor bu makinede … açmıyor" · "canlı kamerada belli bir fps değerinde anlık görüntü
 * alıp analiz yapmalı").
 * Ölçülen (GERÇEK HP kamerası, 85acab5e): başlatma 0,28–0,53 sn, ilk kare ~0,5–1,8 sn sonra; arada sunucu "kapalı" (409) diyordu ve arayüz
 * canlıyı durduruyordu. Düzeltmeden sonra sunucu ilk kareyi kısa süre bekler, gelmezse 200 `bekliyor` döner.
 * Kapı (web, backend bu makinede): `bekliyor` yanıtı canlıyı DURDURMAZ ve "analiz edilemedi" HATASI göstermez (o tur atlanır, sonraki
 * turda kare gelince analiz edilir); analiz hızı seçilebilir (1 kare/sn varsayılan · 1 kare / 2 sn · 1 kare / 5 sn) ve uygulanır;
 * gerçekleşen hız görünür.
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
let mockHastaId = 19200;
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigate: jest.fn(), selectedPatient: { id: mockHastaId, name: `Y192-${mockHastaId}` } }),
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

let t0 = 0;
let mockBekleMs = 0;
beforeEach(() => {
  mockHastaId += 1;
  mockToast.mockClear();
  mockFoto.mockClear();
  (apiPost as jest.Mock).mockClear();
  (serviceConfig as any).apiBaseUrl = "http://127.0.0.1:8000/api";
  t0 = Date.now();
  global.fetch = jest.fn(async (url: unknown) => {
    const yol = yolu(url);
    if (yol === "/settings/kabin-kamerasi/canli/baslat") {
      t0 = Date.now(); // ilk kare gecikmesi canlı BAŞLATMADAN ölçülür (ekranın çizilme süresi sayılmaz)
      return yanit({ status: "success", indeks: 0, acik: true });
    }
    if (yol.startsWith("/settings/kabin-kamerasi/canli/kare")) {
      if (Date.now() - t0 < mockBekleMs) return yanit({ status: "bekliyor", indeks: 0, hazir: false });
      return yanit({ status: "success", hazir: true, yas_ms: 3, image_base64: yol.includes("tam=true") ? "VEFN" : "T05J" });
    }
    if (yol === "/settings/kabin-kamerasi/canli/durdur") return yanit({ status: "success" });
    if (yol.startsWith("/ai/vision/em_")) return yanit(PETRI);
    return yanit({});
  }) as any;
});

async function canliAc() {
  const u = render(<Ekran />);
  fireEvent.press(u.getAllByLabelText("Petri Kuyu")[0]);
  await waitFor(() => u.getByText("Petri Kuyu Analizi"));
  await act(async () => { fireEvent.press(u.getByText("Canlı Kamera")); });
  return u;
}
const emSayisi = () => cagrilar("/ai/vision/em_petri").length;

it("KRİTİK: ilk kare gelene dek 'bekliyor' — canlı DURMAZ, hata göstermez, kare gelince analiz eder", async () => {
  mockBekleMs = 1900;
  const u = await canliAc();
  // ilk analiz turu ~1 sn'de "bekliyor" alır; bekleme penceresinin İÇİNDE (1,5 sn) durum satırı HATA göstermemeli
  await bekle(1500);
  expect(emSayisi()).toBe(0);
  expect(u.queryByTestId("canli-durum")).toBeNull();
  expect(mockToast).not.toHaveBeenCalled();
  expect(u.getByText("Canlıyı Durdur")).toBeTruthy();
  await waitFor(() => expect(emSayisi()).toBeGreaterThan(0), { timeout: 6000 });
  await waitFor(() => expect(String(u.getByTestId("em-canli-onizleme").props.source.uri)).toContain("T05J"));
  await act(async () => { fireEvent.press(u.getByText("Canlıyı Durdur")); });
});

it("KRİTİK: analiz hızı seçilir ve UYGULANIR — 1 kare / 5 sn seçilince 3 sn içinde ikinci analiz YOK", async () => {
  mockBekleMs = 0;
  const u = await canliAc();
  await waitFor(() => expect(emSayisi()).toBe(1), { timeout: 4000 });
  await act(async () => { fireEvent.press(u.getByLabelText("1 kare / 5 sn")); });
  expect(u.getByLabelText("1 kare / 5 sn").props.accessibilityState?.selected).toBe(true);
  const once = emSayisi();
  await bekle(3000);
  expect(emSayisi()).toBe(once);
  await act(async () => { fireEvent.press(u.getByText("Canlıyı Durdur")); });
});

it("KARŞIT: varsayılan 1 kare/sn — 3,5 sn içinde en az iki analiz; gerçekleşen hız görünür", async () => {
  mockBekleMs = 0;
  const u = await canliAc();
  expect(u.getByLabelText("1 kare/sn").props.accessibilityState?.selected).toBe(true);
  await waitFor(() => expect(emSayisi()).toBeGreaterThanOrEqual(3), { timeout: 5000 });
  await waitFor(() => expect(String(u.getByTestId("em-canli-hiz").props.children)).toMatch(/Gerçekleşen: [0-9]+[,.][0-9] kare\/sn/));
  await act(async () => { fireEvent.press(u.getByText("Canlıyı Durdur")); });
});
