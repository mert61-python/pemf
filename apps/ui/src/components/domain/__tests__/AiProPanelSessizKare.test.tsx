// Author: mertaygn, cglrgrkn
/**
 * SESSİZ KARE YAKALAMA — saha bildirimi 2026-08-27.
 *
 * ARIZA: "AI Pro'da tedaviyi başlatınca HER KAREDE deklanşör sesi çıkıyor… sinir bozucu."
 * AI Pro hazırlık/seans döngüsü ~3 sn'de bir kare alır; sistem her `takePictureAsync`
 * çağrısında deklanşör sesi çalar. Klinikte hasta ÜZERİNDE süren bir seansta bu hem
 * operatörü rahatsız eder hem de hayvanı ürkütür — yakalanan şey bir fotoğraf değil,
 * ÖLÇÜM karesidir; sessiz olmalıdır.
 *
 * Test DAVRANIŞSAL: kaynakta desen aramaz, `takePictureAsync`e giden SEÇENEKLERİ ölçer.
 * `shutterSound: false` kaldırılırsa kırmızıya döner.
 */
let mockDurum: Record<string, unknown> = { active: false };

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

// Kamera casusu: takePictureAsync'e giden seçenekleri yakalar.
const cekimSecenekleri: Record<string, unknown>[] = [];
jest.mock("expo-camera", () => {
  const React2 = require("react");
  return {
    CameraView: React2.forwardRef((_p: unknown, ref: unknown) => {
      React2.useImperativeHandle(ref, () => ({
        takePictureAsync: async (secenekler: Record<string, unknown>) => {
          cekimSecenekleri.push(secenekler || {});
          return { base64: "AAAA" };
        },
      }));
      return null;
    }),
    useCameraPermissions: () => [{ granted: true }, jest.fn()],
  };
});

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";

import { AiProPanel } from "../AiProPanel";

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
  cekimSecenekleri.length = 0;
  mockDurum = { active: false };
});

it("KRİTİK: AI Pro kare yakalama SESSİZ — her çekimde shutterSound:false gider", async () => {
  const u = render(<AiProPanel patientName="Tekir" />);
  await act(async () => {});
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  // ⚠️ Sabit tur sayısı FLAKY (ölçüldü: soğuk koşuda 15 tur yetmedi, sıcakta yetti) —
  // kare GELENE KADAR ilerlet, tavanla sınırla.
  for (let i = 0; i < 120 && cekimSecenekleri.length === 0; i++) {
    await act(async () => { jest.advanceTimersByTime(1000); await Promise.resolve(); });
  }

  // ÖN-DOĞRULAMA: kare gerçekten alındı (aksi halde test vacuous olurdu)
  expect(cekimSecenekleri.length).toBeGreaterThan(0);
  // ASIL KİLİT: HER çekim sessiz olmalı — biri bile sesli kalırsa seans boyunca duyulur
  for (const s of cekimSecenekleri) {
    expect(s.shutterSound).toBe(false);
  }
  // Ölçüm karesi olduğu için işleme de atlanır (hız) — mevcut davranış korunsun
  expect(cekimSecenekleri[0].skipProcessing).toBe(true);

  await act(async () => { u.unmount(); });
});
