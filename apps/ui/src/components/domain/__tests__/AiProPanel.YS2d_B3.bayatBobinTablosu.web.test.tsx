// Author: mertaygn, cglrgrkn
/**
 * YS2 d · B3 (YG0 25-11): Kontrol › Bobin Diagnostiği elle Durdur'dan sonra son komut duty'lerini (%17–36) göstermeye devam ediyordu
 * (son `ai_vision` karesi bağlamda kalıcı; sayfa değişse de). Bobinler durmuşken tablo "sürülüyor" demez: seans sürmüyorsa son karenin
 * değerleri gösterilmez. Seans sürerken tablo AYNEN canlı kareyi gösterir.
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});
let mockDurum: Record<string, unknown> = { active: false, localized: false };
let mockVision: Record<string, unknown> | undefined;
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async (yol: string) =>
    yol === "/ai/hazirlik"
      ? { moduller: [{ modul: "em_fantom", hazir: true }, { modul: "em_petri", hazir: true }, { modul: "petri_yolo", hazir: true }] }
      : mockDurum,
  ),
  apiPost: jest.fn(async () => ({ status: "success" })),
  authHeaders: jest.fn(() => ({})),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  AI_TIMEOUT_MS: 120000,
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" },
  getClientInstanceId: jest.fn(async () => "web-id"),
}));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionData: mockVision, aiVisionFresh: !!mockVision }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "a@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "a@x.com" }) }));
jest.mock("expo-camera", () => {
  const React2 = require("react");
  return { CameraView: React2.forwardRef(() => null), useCameraPermissions: () => [{ granted: true }, jest.fn()] };
});

import { act, render } from "@testing-library/react-native";
import React from "react";

import { AiProPanel } from "../AiProPanel";

const SON_KARE = {
  detected: true,
  perCoil: [
    { id: 1, freq: 100, duty: 36, phase: 0, suruldu: true },
    { id: 2, freq: 100, duty: 17, phase: 10, suruldu: true },
  ],
};

beforeEach(() => {
  jest.useFakeTimers();
  mockDurum = { active: false, localized: false };
  mockVision = undefined;
});
afterEach(() => {
  jest.useRealTimers();
});

async function ciz() {
  const u = render(<AiProPanel patientName="Örnek-1" secilebilirModeller={["fantom", "petri"]} kullaniciKipi="researcher" />);
  await act(async () => { jest.advanceTimersByTime(3000); await Promise.resolve(); });
  return u;
}

it("KRİTİK B3: seans DURDUKTAN sonra tablo son karenin duty'lerini (36% / 17%) GÖSTERMEZ", async () => {
  mockVision = SON_KARE; // durdurmadan önceki son kare bağlamda kaldı
  const u = await ciz();
  expect(u.queryByText("36%")).toBeNull();
  expect(u.queryByText("17%")).toBeNull();
  expect(u.getAllByText("0%").length).toBeGreaterThan(0); // boş satırlar (bobinler durdu)
});

it("KARŞIT B3: seans SÜRERKEN tablo canlı karenin duty'lerini gösterir", async () => {
  mockVision = SON_KARE;
  mockDurum = { active: true, ownerClientId: "web-id", model: "petri", organId: 11, targetsModel: "petri", targets: [] };
  const u = await ciz();
  expect(u.getByText("36%")).toBeTruthy();
  expect(u.getByText("17%")).toBeTruthy();
});
