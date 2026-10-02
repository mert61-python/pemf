// Author: mertaygn, cglrgrkn
/**
 * D1.E07 · İG-5.76 · Y6 — Fantom/Petri sonuç kartı HESAPLANMAYAN doz ve alanı sayı gibi göstermez.
 *
 * Backend PİKSEL kipinde (ölçek yok: fantom boyu / petri çapı girilmedi) koordinatı piksel farkı olarak bilir;
 * doz modelini ÇAĞIRMAZ ve `E_cancer/E_healthy/area_mm2 = null` döner. Eski kart `Number(null).toFixed(4)` ile
 * "0.0000" ("hesaplandı, sıfır") basıyor, piksel alanını "mm²" etiketiyle gösteriyor ve açıklamada
 * "E hesaplandı; duty üretildi" diyordu.
 *
 * ⚠️ DAVRANIŞSAL: gerçek ekran, gerçek akış (Galeriden Seç → Analizi Başlat); yalnız ağ (`fetch`) ve görsel
 * seçici sahte.
 */
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => null),
  apiPost: jest.fn(async () => null),
  authHeaders: jest.fn(() => ({})),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  aiHataMesaji: jest.fn(() => "hata"),
  AI_TIMEOUT_MS: 120000,
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" },
}));
jest.mock("@/components/ui/ToastProvider", () => {
  const fn = jest.fn();
  return { useToast: () => ({ showToast: fn }), __toast: fn };
});
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ userMode: "researcher", hasAiHub: true }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "r@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "r@x.com" }) }));
jest.mock("@/context/EntitlementContext", () => ({ useEntitlement: () => ({ research: true }) }));
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigate: jest.fn(), selectedPatient: { id: 1, name: "Test Hasta" } }),
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
  MediaTypeOptions: { Images: "Images" },
  launchImageLibraryAsync: jest.fn(async () => ({ canceled: false, assets: [{ uri: "file:///kare.jpg" }] })),
  launchCameraAsync: jest.fn(),
}));
jest.mock("expo-image-manipulator", () => ({
  SaveFormat: { JPEG: "jpeg" },
  manipulateAsync: jest.fn(async (uri: string) => ({ uri, base64: "QUJD" })),
}));

import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";

import { AiHubScreen } from "@/screens/AiHubScreen";

const D7 = [0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3];

function fantomYaniti(pixel: boolean) {
  const bolge = pixel
    ? { centroid_cabin_mm: [10, -10, 0], area_px: 167, area_mm2: null, D: [], E_cancer: null, E_healthy: null }
    : { centroid_cabin_mm: [4.2, 26.5, 0], area_px: 167, area_mm2: 33.9, D: D7, E_cancer: 0.05, E_healthy: 0.02 };
  return {
    status: "success",
    success: true,
    n_tumor: 1,
    method: pixel ? "pixel" : "phantom_length",
    mm_per_px: pixel ? 1 : 0.45,
    tumor_regions: [bolge],
    healthy_regions: [],
    paneller: [],
  };
}

function petriYaniti(pixel: boolean) {
  const kuyu = pixel
    ? { well_id: "W1", label: "cancer", organ_id: 1, centroid_cabin_mm: [0, 0, 0], area_px: 31400, area_mm2: null, D: [], E_cancer: null, E_healthy: null }
    : { well_id: "W1", label: "cancer", organ_id: 1, centroid_cabin_mm: [0, 0, 0], area_px: 31400, area_mm2: 6358.5, D: D7, E_cancer: 0.05, E_healthy: 0.02 };
  return {
    status: "success",
    success: true,
    n_wells: 1,
    n_cancer: 1,
    n_healthy: 0,
    method: pixel ? "pixel" : "petri_diameter",
    mm_per_px: pixel ? 1 : 0.45,
    wells: [kuyu],
    paneller: [],
  };
}

async function analizEt(modul: "Fantom Tümör" | "Petri Kuyu", yanit: object) {
  (global as any).fetch = jest.fn(async () => ({ ok: true, json: async () => yanit }));
  const u = render(<AiHubScreen />);
  fireEvent.press(u.getAllByLabelText(modul)[0]);
  await act(async () => {
    fireEvent.press(u.getByText("Galeriden Seç"));
  });
  await act(async () => {
    fireEvent.press(u.getByText(modul === "Fantom Tümör" ? "Fantom Analizini Başlat" : "Petri Analizini Başlat"));
  });
  await act(async () => {});
  expect((global as any).fetch).toHaveBeenCalledTimes(1); // ARA DOĞRULAMA: gerçek akış istek attı
  return u;
}

/** Ekranda görünen metin: iç içe <Text> parçaları BİTİŞİK birleşir (ör. `{x} mm²` iki parça üretir). */
function duz(d: any): string {
  if (d == null || typeof d === "boolean") return "";
  if (typeof d === "string" || typeof d === "number") return String(d);
  if (Array.isArray(d)) return d.map(duz).join("");
  const ic = (d.children || []).map(duz).join("");
  return d.type === "Text" ? ic : ` ${ic} `;
}

const metin = (u: ReturnType<typeof render>) => duz(u.toJSON());

describe.each([
  ["Fantom Tümör", fantomYaniti, "167 px²", "fantom boyunu"],
  ["Petri Kuyu", petriYaniti, "31400 px²", "petri çapını"],
] as const)("%s sonuç kartı", (modul, yanit, pxAlan, olcekAlani) => {
  it("KRİTİK: piksel kipinde E '—', alan px² (mm² DEĞİL), açıklama doz hesaplanmadı der", async () => {
    const u = await analizEt(modul, yanit(true));
    const m = metin(u);
    expect(m).not.toMatch(/0\.0000/);
    expect(m).toContain("—");
    expect(m).toContain(pxAlan);
    expect(m).not.toMatch(/\d mm²/); // hiçbir sayı mm² diye etiketlenmez (eskiden "0.0 mm²")
    expect(m).toContain("doz (D1–D7) ve E hesaplanmadı");
    expect(m).toContain(olcekAlani);
    expect(m).not.toMatch(/E\) hesaplandı|hesaplanan E-alanı/);
  });

  it("KARŞIT: ölçekli kipte E ve mm² sayı olarak gösterilir", async () => {
    const u = await analizEt(modul, yanit(false));
    const m = metin(u);
    expect(m).toContain("0.0500");
    expect(m).toMatch(/(33\.9|6358\.5) mm²/);
    expect(m).not.toContain("hesaplanmadı");
  });
});
