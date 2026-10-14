// Author: mertaygn
/**
 * SG.G1 (sahip gözlemi 2026-10-13: "Performans Raporu … klinikle araştırma modunun alakası yok") — KPI sayıları artık profilin
 * seanslarıdır (backend `X-PEMF-Profil`), başlık da profilin dilinde. Sağlayıcısız çizimde (yalın ekran testi) veteriner metni.
 * ⚠️ DAVRANIŞSAL: GERÇEK `KpiDashboardScreen`, canlı veri `LiveDataContext` sahtesiyle.
 */
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => null),
  apiPost: jest.fn(async () => null),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  authHeaders: jest.fn(() => ({})),
}));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://127.0.0.1:65530/api" } }));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({
    snapshot: {
      gateway: "online", mqtt: "online", stm: "online",
      patient: { name: "", species: "", breed: "", owner: "" },
      activeTreatment: { isActive: false, mode: "", frequencyHz: 0, intensityMt: 0, remainingMin: 0, elapsedSec: 0, durationSec: 0 },
      notifications: [], coils: [], system: {}, sessions: [],
    },
    wsConnected: true, connectionQuality: "live", haveRealData: true, telemetryStale: false, sensorHistory: {},
    unreadCount: 0, markAllRead: jest.fn(), clearNotifications: jest.fn(), refresh: jest.fn(), reconnect: jest.fn(), aiVisionFresh: false,
  }),
}));
let mockMod: string | null = "researcher";
let mockSaglayiciYok = false;
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => {
    if (mockSaglayiciYok) throw new Error("useUserMode must be used within a UserModeProvider");
    return { userMode: mockMod };
  },
}));

import React from "react";
import { render, waitFor } from "@testing-library/react-native";
import { apiGet } from "@/services/apiClient";
import { KpiDashboardScreen } from "@/screens/KpiDashboardScreen";

async function baslik() {
  const u = render(<KpiDashboardScreen />);
  await waitFor(() => expect(apiGet).toHaveBeenCalled());
  return u;
}

afterEach(() => { mockMod = "researcher"; mockSaglayiciYok = false; });

it("KRİTİK: araştırma profilinde KPI başlığı 'Araştırma Göstergeleri' — 'Klinik' YOK", async () => {
  const u = await baslik();
  expect(u.getByText("📊 Araştırma Göstergeleri & Analitik")).toBeTruthy();
  expect(u.queryByText(/Klinik Göstergeler/)).toBeNull();
});

it("veteriner profilinde başlık AYNEN", async () => {
  mockMod = "veterinarian";
  const u = await baslik();
  expect(u.getByText("📊 Klinik Göstergeler & Analitik")).toBeTruthy();
});

it("sağlayıcısız çizim ÇÖKMEZ (veteriner metni)", async () => {
  mockSaglayiciYok = true;
  const u = await baslik();
  expect(u.getByText("📊 Klinik Göstergeler & Analitik")).toBeTruthy();
});
