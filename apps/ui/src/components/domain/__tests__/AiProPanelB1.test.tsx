// Author: mertaygn, cglrgrkn
/**
 * AI PRO KARE SAHİPLİĞİ — 3. tur denetimi bulgu B1 (frontend yarısı).
 *
 * (1) ownedRef DRIFT: ikinci istemci "Başlat"a basınca backend "Already running" + MEVCUT sahibin
 *     (A) ownerClientId'sini döndürür. Panel ownedRef'i YALNIZ ownerClientId===kendi id ise true
 *     yapmalı; aksi halde B, panelini kapatınca A'nın onaylı seansına /stop gönderirdi (<3sn drift).
 * (2) client_id PROPAGASYONU: /calibrate (ve /organ) çağrıları client_id taşımalı ki backend
 *     YABANCI istemcinin mid-seans organ/relocalize müdahalesini reddedebilsin.
 *
 * ⚠️ Testler DAVRANIŞSAL: kaynakta desen değil, apiPost çağrı argümanları / stop sayısı ölçülür.
 */
let mockDurum: Record<string, unknown> = { active: false };
let mockStartYaniti: Record<string, unknown> = { status: "success" };

jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => mockDurum),
  apiPost: jest.fn(async (yol: string) => {
    if (yol === "/ai/pro/propose") {
      return {
        proposalId: "p1",
        specs: {
          organ_id: 0, duration_minutes: 20, coil_ids: [1, 2, 3, 4, 5, 6, 7],
          D: [1, 1, 1, 1, 1, 1, 1], P: [0, 0, 0, 0, 0, 0, 0], e_field: 0.07,
        },
        meta: {},
        expiresAt: 0,
      };
    }
    if (yol === "/ai/pro/start") return mockStartYaniti;
    return { status: "success" };
  }),
  authHeaders: jest.fn(() => ({})),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  AI_TIMEOUT_MS: 120000,
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" },
  getClientInstanceId: jest.fn(async () => "benim-id"),
}));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionData: null, aiVisionFresh: false }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "v@x.com" }) }));
jest.mock("expo-camera", () => {
  const React2 = require("react");
  return {
    CameraView: React2.forwardRef((_p: unknown, ref: unknown) => {
      React2.useImperativeHandle(ref, () => ({
        takePictureAsync: async () => ({ base64: "AAAA" }),
      }));
      return null;
    }),
    useCameraPermissions: () => [{ granted: true }, jest.fn()],
  };
});

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";

import { apiPost } from "@/services/apiClient";

import { AiProPanel } from "../AiProPanel";

const stopCagrilari = () =>
  (apiPost as jest.Mock).mock.calls.filter((c) => c[0] === "/ai/pro/stop");
const cagri = (yol: string) => (apiPost as jest.Mock).mock.calls.find((c) => c[0] === yol);

const gercekFetch = global.fetch;
beforeAll(() => {
  jest.useFakeTimers();
  // localizedAt YOK → damga undefined → kare-başı sayım (F2 geriye-uyum) → 2 karede öneri istenir.
  global.fetch = jest.fn(async () => ({
    ok: true,
    json: async () => ({ status: "success", detected: true, catDetected: true, reliability: 0.9 }),
  })) as unknown as typeof fetch;
});
afterAll(() => { global.fetch = gercekFetch; jest.useRealTimers(); });

beforeEach(() => {
  (apiPost as jest.Mock).mockClear();
  mockDurum = { active: false };
  mockStartYaniti = { status: "success" };
});

async function hazirligiIlerlet() {
  for (let i = 0; i < 30; i++) {
    await act(async () => { jest.advanceTimersByTime(1000); await Promise.resolve(); });
  }
}
async function panel() {
  const u = render(<AiProPanel patientName="Tekir" />);
  await act(async () => {});
  return u;
}

it("KRİTİK B1: start 'Already running' + BAŞKA ownerClientId → unmount DURDURMA göndermez", async () => {
  // İkinci istemci B: seansı A başlatmış; B'nin start'ı Already-running + A'nın id'sini döndürür.
  mockStartYaniti = { status: "success", message: "Already running", ownerClientId: "baska-A" };
  const u = await panel();
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  await hazirligiIlerlet();
  await act(async () => { fireEvent.press(u.getByLabelText("Öneriyi onayla ve seansı başlat")); });

  // ÖN-DOĞRULAMA: start GERÇEKTEN çağrıldı (Already-running yolunu geçtik).
  expect(cagri("/ai/pro/start")).toBeTruthy();

  await act(async () => { u.unmount(); });
  // ownerClientId (baska-A) !== benim-id → ownedRef=false → A'nın seansına DURDURMA gitmez.
  expect(stopCagrilari()).toHaveLength(0);
});

it("KARŞIT-KANIT B1: start ownerClientId === benim id → unmount DURDURUR (kendi seansımız)", async () => {
  mockStartYaniti = { status: "success", message: "AI Pro Closed-Loop Started", ownerClientId: "benim-id" };
  const u = await panel();
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  await hazirligiIlerlet();
  await act(async () => { fireEvent.press(u.getByLabelText("Öneriyi onayla ve seansı başlat")); });
  expect(cagri("/ai/pro/start")).toBeTruthy();

  await act(async () => { u.unmount(); });
  expect(stopCagrilari()).toHaveLength(1);
});

it("SÜRÜM KAYMASI B1: start yanıtında ownerClientId YOKSA eski davranış (başarı=sahip) korunur", async () => {
  mockStartYaniti = { status: "success" }; // eski backend: alan yok
  const u = await panel();
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  await hazirligiIlerlet();
  await act(async () => { fireEvent.press(u.getByLabelText("Öneriyi onayla ve seansı başlat")); });
  expect(cagri("/ai/pro/start")).toBeTruthy();

  await act(async () => { u.unmount(); });
  expect(stopCagrilari()).toHaveLength(1);
});

it("B1: 'Başlat' /calibrate çağrısı client_id taşır (backend yabancı müdahaleyi reddedebilsin)", async () => {
  const u = await panel();
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  const cal = cagri("/ai/pro/calibrate");
  expect(cal).toBeTruthy();
  expect(cal![1]).toMatchObject({ client_id: "benim-id" });
});
