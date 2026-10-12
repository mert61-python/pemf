// Author: mertaygn, cglrgrkn
/**
 * Y142 (sahip 2026-10-13) — KEDİ AI Pro SÜRÜŞÜ KAPALIYKEN ekran GERÇEĞİ söyler.
 *
 * Backend kedi AI Pro başlatmasını / onay mührünü / bobin sürüşünü reddeder (`PEMF_KEDI_AIPRO_SURUS` yok = kapalı). Analiz,
 * hazırlık, öneri ve onay ekranı GÖRÜNÜR kalır; ama "AI Pro Başlat" ve "Onayla ve Başlat" düğmeleri sürüş BAŞLATMIYOR —
 * etiketleri bunu söylemeli (düğme etiketi gerçeği söyler) ve onay düğmesi `/approve` + `/start` göndermemeli.
 * Kaynak: `/ai/pro/status.kediAiProSurusAcik` ve öneri yanıtının `surusAcik` / `surusKapaliNedeni` alanları (YALNIZ EK —
 * alanlar yoksa eski backend → eski davranış; karşıt kollar bunu kilitler).
 * ⚠️ Beklenen metin BURADA sabittir (ürün sabitinden OKUNMAZ).
 */
let mockDurum: Record<string, unknown> = { active: false };
let mockOneriEk: Record<string, unknown> = {};

const MESAJ =
  "Kedi AI Pro sürüşü, kabin konumu doğrulanana kadar kapalı. Analizi ve öneriyi inceleyebilirsiniz; " +
  "seansı Kontrol ekranından elle başlatın.";

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
        ...mockOneriEk,
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
  mockDurum = { active: false };
  mockOneriEk = {};
});

async function ilerlet(n = 30) {
  for (let i = 0; i < n; i++) {
    await act(async () => { jest.advanceTimersByTime(1000); await Promise.resolve(); });
  }
}
async function panel() {
  const u = render(<AiProPanel patientName="Tekir" />);
  await act(async () => {});
  return u;
}

it("KRİTİK Y142: sürüş kapalıyken başlatma düğmesi 'sürüş kapalı' der ve nedeni GÖRÜNÜR", async () => {
  mockDurum = { active: false, kediAiProSurusAcik: false };
  const u = await panel();
  expect(u.queryByLabelText("AI Pro otonom seansı başlat")).toBeNull();
  expect(u.getByLabelText("AI Pro analiz ve öneri — kedi sürüşü kapalı")).toBeTruthy();
  expect(u.getAllByText(/sürüş kapalı/).length).toBeGreaterThan(0);
  expect(u.getAllByText(MESAJ).length).toBeGreaterThan(0);
});

it("KRİTİK Y142: öneri GÖRÜNÜR; onay ekranı sürüşün kapalı olduğunu söyler ve onay düğmesi /approve + /start GÖNDERMEZ", async () => {
  mockDurum = { active: false, kediAiProSurusAcik: false };
  mockOneriEk = { surusAcik: false, surusKapaliNedeni: MESAJ };
  const u = await panel();
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro analiz ve öneri — kedi sürüşü kapalı")); });
  await ilerlet();
  expect(cagrilar("/ai/pro/propose").length).toBe(1); // öneri yine istenir (görünür)
  expect(u.getByLabelText("AI seans önerisi onay penceresi")).toBeTruthy();
  expect(u.queryByLabelText("Öneriyi onayla ve seansı başlat")).toBeNull();
  const dugme = u.getByLabelText("Sürüş kapalı — onay seansı başlatmaz");
  expect(dugme.props.accessibilityState?.disabled).toBe(true);
  await act(async () => { fireEvent.press(dugme); });
  expect(cagrilar("/ai/pro/approve").length).toBe(0);
  expect(cagrilar("/ai/pro/start").length).toBe(0);
  expect(u.getAllByText(MESAJ).length).toBeGreaterThan(0);
});

it("KRİTİK Y142: durum ucu okunamasa da (alan yok) ÖNERİ 'sürüş kapalı' diyorsa onay düğmesi başlatmaz", async () => {
  mockDurum = { active: false }; // eski / okunamayan durum
  mockOneriEk = { surusAcik: false, surusKapaliNedeni: MESAJ };
  const u = await panel();
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  await ilerlet();
  const dugme = u.getByLabelText("Sürüş kapalı — onay seansı başlatmaz");
  await act(async () => { fireEvent.press(dugme); });
  expect(cagrilar("/ai/pro/approve").length).toBe(0);
  expect(cagrilar("/ai/pro/start").length).toBe(0);
});

it("KARŞIT Y142: sürüş AÇIK (ya da alan yok — eski backend) → bugünkü etiketler ve onay akışı AYNEN", async () => {
  mockDurum = { active: false, kediAiProSurusAcik: true };
  mockOneriEk = { surusAcik: true, surusKapaliNedeni: "" };
  const u = await panel();
  expect(u.queryByLabelText("AI Pro analiz ve öneri — kedi sürüşü kapalı")).toBeNull();
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  await ilerlet();
  expect(u.queryByLabelText("Sürüş kapalı — onay seansı başlatmaz")).toBeNull();
  await act(async () => { fireEvent.press(u.getByLabelText("Öneriyi onayla ve seansı başlat")); });
  await act(async () => {});
  expect(cagrilar("/ai/pro/approve").length).toBe(1);
  expect(cagrilar("/ai/pro/start").length).toBe(1);
  expect(u.queryByText(MESAJ)).toBeNull();
});
