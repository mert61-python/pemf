// Author: mertaygn, cglrgrkn
/**
 * AI PRO WEB KAPALI-DÖNGÜ DÜZELTMESİ (2026-08-25).
 *
 * Web/sunucu-kameralı yolda "AI Pro Başlat" DOĞRUDAN /propose çağırıp "organ henüz
 * konumlandırılmadı" (409) alıyordu (sunucu kamerası seans öncesi lokalize etmiyor). Düzeltme:
 * web de telefondaki gibi ÖNCE /ai/pro/hazirlik/baslat ile sunucu kamerasını ısıtır; /status
 * `localized` görününce öneri OTOMATİK istenir.
 *
 * ⚠️ Platform.OS="web" mock'lanır (IS_WEB import anında hesaplanır → mock ÖNCE olmalı).
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web"; // yerinde değiştir (tüm RN yapısı korunur → svg/lucide bozulmaz)
  return RN;
});

let mockDurum: Record<string, unknown> = { active: false, localized: false };
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => mockDurum),
  apiPost: jest.fn(async (yol: string) => {
    if (yol === "/ai/pro/propose") {
      return {
        proposalId: "p1",
        specs: { organ_id: 3, duration_minutes: 20, coil_ids: [1, 2, 3, 4, 5, 6, 7], D: [1, 1, 1, 1, 1, 1, 1], P: [0, 0, 0, 0, 0, 0, 0], e_field: 0.07 },
        meta: {},
        expiresAt: 0,
      };
    }
    return { status: "success" };
  }),
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
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionData: null, aiVisionFresh: false }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "v@x.com" }) }));
jest.mock("expo-camera", () => {
  const React2 = require("react");
  return {
    CameraView: React2.forwardRef((_p: unknown, _ref: unknown) => null),
    useCameraPermissions: () => [{ granted: true }, jest.fn()],
  };
});

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";

import { apiPost } from "@/services/apiClient";

import { AiProPanel } from "../AiProPanel";

const cagri = (yol: string) => (apiPost as jest.Mock).mock.calls.filter((c) => c[0] === yol);

beforeEach(() => {
  jest.useFakeTimers();
  (apiPost as jest.Mock).mockClear();
  mockDurum = { active: false, localized: false };
});
afterEach(() => { jest.useRealTimers(); });

async function panel() {
  const u = render(<AiProPanel patientName="Tekir" />);
  await act(async () => {});
  return u;
}

it("KRİTİK WEB: 'Başlat' DOĞRUDAN propose ÇAĞIRMAZ — önce /hazirlik/baslat ile kamerayı ısıtır", async () => {
  const u = await panel();
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  // Web kapalı-döngü düzeltmesi: propose DEĞİL, hazırlık başlatılır.
  expect(cagri("/ai/pro/hazirlik/baslat")).toHaveLength(1);
  expect(cagri("/ai/pro/propose")).toHaveLength(0);
  // organ + client_id gövdede
  expect(cagri("/ai/pro/hazirlik/baslat")[0][1]).toMatchObject({ client_id: "web-id" });
});

it("KRİTİK WEB: /status `localized` görününce öneri OTOMATİK istenir + önizleme durdurulur", async () => {
  const u = await panel();
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  expect(cagri("/ai/pro/propose")).toHaveLength(0);

  // Sunucu önizlemesi lokalize etti → status artık localized:true. İki poll (3sn'lik interval) geçir.
  mockDurum = { active: false, localized: true };
  for (let i = 0; i < 4; i++) {
    await act(async () => { jest.advanceTimersByTime(3000); await Promise.resolve(); });
  }
  expect(cagri("/ai/pro/propose").length).toBeGreaterThan(0);
  // Öneri gelince önizleme durdurulur (kamera bırakılır).
  expect(cagri("/ai/pro/hazirlik/durdur").length).toBeGreaterThan(0);
});

it("KARŞIT-KANIT WEB: organ LOKALİZE OLMADIKÇA öneri İSTENMEZ (sürüş kapısı gevşemez)", async () => {
  const u = await panel();
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  // Sunucu önizlemesi henüz lokalize etmedi (localized:false) → status poll'ları geçse de propose YOK.
  mockDurum = { active: false, localized: false };
  for (let i = 0; i < 4; i++) {
    await act(async () => { jest.advanceTimersByTime(3000); await Promise.resolve(); });
  }
  expect(cagri("/ai/pro/propose")).toHaveLength(0);
});
