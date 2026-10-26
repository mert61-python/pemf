// Author: mertaygn, cglrgrkn
/**
 * D5 (D3 devri, sağlamlık listesi · 2-C incelemesi §9 #10) — "Onayla ve Başlat"a ÇİFT DOKUNMA.
 *
 * Düğme yalnız `approvalBusy` DURUMUYLA pasifleşiyordu; durum ancak yeniden çizimde uygulanır → aynı karede iki dokunuş iki
 * `/ai/pro/approve` gönderiyordu. İkincisi sunucuda 409 (öneri zaten onaylı) → gereksiz hata bildirimi ve `setApprovalBusy(false)`
 * ile düğme İLK istek sürerken yeniden açılıyordu [A1 ÖLÇTÜM]. Red penceresinin "Reddet"i de aynı sınıftı (gerekçe iki kez).
 * Bu dosya gerçek `AiProPanel`i çizer; `/approve` yanıtı elle tutulur (istek uçuşta) ve iki dokunuş AYNI `act` içinde verilir.
 */
let mockDurum: Record<string, unknown> = { active: false, kediAiProSurusAcik: true };
let onayCoz: ((v: unknown) => void) | null = null;
let mockOnayYaniti: "bekle" | "red" = "bekle";

jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => mockDurum),
  apiPost: jest.fn(async (yol: string) => {
    if (yol === "/ai/pro/propose") {
      return {
        proposalId: "p1",
        specs: {
          organ_id: 2, duration_minutes: 20, coil_ids: [1, 2, 3, 4, 5, 6, 7],
          D: [0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3], P: [0, 0, 0, 0, 0, 0, 0], e_field: 0.07, model: "kedi",
        },
        meta: {},
        expiresAt: 0,
        surusAcik: true,
      };
    }
    if (yol === "/ai/pro/approve") {
      if (mockOnayYaniti === "red") return null;
      return new Promise((coz) => { onayCoz = coz; });
    }
    if (yol === "/ai/pro/reject") return new Promise((coz) => { onayCoz = coz; });
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

const cagrilar = (yol: string) => (apiPost as jest.Mock).mock.calls.filter((c) => c[0] === yol);

const gercekFetch = global.fetch;
beforeAll(() => {
  jest.useFakeTimers();
  global.fetch = jest.fn(async () => ({
    ok: true,
    json: async () => ({ status: "success", detected: true, catDetected: true, reliability: 0.9 }),
  })) as unknown as typeof fetch;
});
afterAll(() => { global.fetch = gercekFetch; jest.useRealTimers(); });

beforeEach(() => {
  (apiPost as jest.Mock).mockClear();
  mockDurum = { active: false, kediAiProSurusAcik: true };
  mockOnayYaniti = "bekle";
  onayCoz = null;
});

async function ilerlet(n = 30) {
  for (let i = 0; i < n; i++) {
    await act(async () => { jest.advanceTimersByTime(1000); await Promise.resolve(); });
  }
}

async function onayPenceresi() {
  const u = render(<AiProPanel patientName="Tekir" />);
  await act(async () => {});
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  await ilerlet();
  expect(cagrilar("/ai/pro/propose").length).toBe(1);
  return u;
}

it("KRİTİK: 'Onayla ve Başlat'a aynı karede ÇİFT dokunma TEK /approve gönderir; düğme istek sürerken açılmaz", async () => {
  const u = await onayPenceresi();
  const dugme = u.getByLabelText("Öneriyi onayla ve seansı başlat");
  await act(async () => {
    fireEvent.press(dugme);
    fireEvent.press(dugme);
  });
  expect(cagrilar("/ai/pro/approve").length).toBe(1);
  // İlk istek hâlâ uçuşta: sonraki karede bir dokunuş daha da yeni istek açmaz.
  await act(async () => { fireEvent.press(u.getByLabelText("Öneriyi onayla ve seansı başlat")); });
  expect(cagrilar("/ai/pro/approve").length).toBe(1);
  expect(cagrilar("/ai/pro/start").length).toBe(0);
  await act(async () => { onayCoz?.({ status: "success" }); });
  await act(async () => {});
  expect(cagrilar("/ai/pro/start").length).toBe(1);
});

it("KRİTİK: red penceresinde 'Reddet'e çift dokunma TEK /reject gönderir (gerekçe iki kez yazılmaz)", async () => {
  const u = await onayPenceresi();
  await act(async () => { fireEvent.press(u.getByText("Reddet")); });
  await act(async () => { fireEvent.changeText(u.getByPlaceholderText(/./), "hasta huzursuz"); });
  const reddet = u.getAllByText("Reddet").at(-1)!;
  await act(async () => {
    fireEvent.press(reddet);
    fireEvent.press(reddet);
  });
  expect(cagrilar("/ai/pro/reject").length).toBe(1);
  await act(async () => { onayCoz?.({ status: "success", gerekceKaydedildi: true }); });
});

it("KARŞIT: onay geçmezse (yanıt yok) bekçi BIRAKILIR — hekim yeniden dokununca yeni /approve gider", async () => {
  mockOnayYaniti = "red";
  const u = await onayPenceresi();
  await act(async () => { fireEvent.press(u.getByLabelText("Öneriyi onayla ve seansı başlat")); });
  await act(async () => {});
  expect(cagrilar("/ai/pro/approve").length).toBe(1);
  await act(async () => { fireEvent.press(u.getByLabelText("Öneriyi onayla ve seansı başlat")); });
  await act(async () => {});
  expect(cagrilar("/ai/pro/approve").length).toBe(2);
  expect(cagrilar("/ai/pro/start").length).toBe(0);
});
