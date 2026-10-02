// Author: mertaygn, cglrgrkn
/**
 * D1.60 · İG-6.10 — SAHİP KARARI A-16: seans sürerken mühürde olmayan organa geçiş YENİ ONAY ister.
 *
 * Backend artık mühür dışı organa `/ai/pro/organ` isteğini 409 ile reddeder (gerekçe `detail`te). Panelin organ
 * çipi ise seçimi İSTEKTEN ÖNCE yerelde değiştiriyordu: red gelince ekran yeni organı göstermeye devam ediyor
 * (bobinler onaylı organı sürerken — gösterilen ≠ uygulanan) ve operatöre yanlış sebep ("Komut sunucuya
 * ulaşmadı") söyleniyordu. Bu dosya gerçek `AiProPanel`i çizer ve ölçer: red/ulaşamama → seçim GERİ alınır ve
 * sunucunun gerekçesi (yeni onay gerektiği) gösterilir; başarı → seçim kalır.
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});
let mockDurum: Record<string, unknown> = { active: true, localized: true, organId: 2, remainingSec: 300 };
let mockOrganYaniti: "red409" | "ulasmadi" | "basari" = "red409";
const RED_METNI =
  "Seans sürerken onaylanmamış hedefe geçilemez: bu seansın onaylı hedefi «Böbrek». Başka hedef için AI Pro'yu " +
  "durdurun, yeni öneri alın ve hekimin yeni onayıyla başlatın.";
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async (yol: string) => (yol === "/ai/hazirlik" ? { moduller: [] } : mockDurum)),
  apiPost: jest.fn(async (yol: string, _govde: unknown, fallback: unknown, opts?: { onHttpError?: (s: number, d?: string) => void }) => {
    if (yol !== "/ai/pro/organ") return { status: "success" };
    if (mockOrganYaniti === "red409") {
      opts?.onHttpError?.(409, RED_METNI);
      return fallback;
    }
    if (mockOrganYaniti === "ulasmadi") return fallback;
    return { status: "success", organId: 5, organName: "Pankreas", model: "kedi" };
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
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionData: undefined, aiVisionFresh: false }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "a@x.com" } }) }));
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({
    navigateTo: jest.fn(),
    selectedPatient: null,
    setSelectedPatient: jest.fn(),
    aiProModeli: "",
    setAiProModeli: jest.fn(),
  }),
}));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "a@x.com" }) }));
jest.mock("expo-camera", () => {
  const React2 = require("react");
  return { CameraView: React2.forwardRef(() => null), useCameraPermissions: () => [{ granted: true }, jest.fn()] };
});

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";

import { apiPost, platformAlert } from "@/services/apiClient";

import { AiProPanel } from "../AiProPanel";

beforeEach(() => {
  jest.useFakeTimers();
  mockDurum = { active: true, localized: true, organId: 2, remainingSec: 300 };
  (apiPost as jest.Mock).mockClear();
  (platformAlert as jest.Mock).mockClear();
});

afterEach(() => {
  jest.useRealTimers();
});

async function cizVeSec(hedef: string) {
  const u = render(<AiProPanel />);
  await act(async () => {
    await Promise.resolve();
  });
  // Seans aktif → panel organı sunucudan (2 = Böbrek) senkronlar.
  expect(u.getByLabelText("Hedef organ: Böbrek").props.accessibilityState).toEqual({ selected: true });
  await act(async () => {
    fireEvent.press(u.getByLabelText(`Hedef organ: ${hedef}`));
    await Promise.resolve();
    await Promise.resolve();
  });
  return u;
}

function secili(u: ReturnType<typeof render>, ad: string): boolean {
  return Boolean(u.getByLabelText(`Hedef organ: ${ad}`).props.accessibilityState?.selected);
}

it("KRİTİK (A-16): 409 → seçim ONAYLI organa GERİ döner ve sunucunun 'yeni onay' gerekçesi gösterilir", async () => {
  mockOrganYaniti = "red409";
  const u = await cizVeSec("Pankreas");
  expect((apiPost as jest.Mock).mock.calls.some((c) => c[0] === "/ai/pro/organ" && c[1]?.organ_id === 5)).toBe(true);
  expect(secili(u, "Pankreas")).toBe(false);
  expect(secili(u, "Böbrek")).toBe(true);
  const cagri = (platformAlert as jest.Mock).mock.calls.at(-1);
  expect(cagri).toBeTruthy();
  expect(String(cagri[1])).toMatch(/yeni onay/i);
  expect(String(cagri[1])).not.toMatch(/ulaşmadı/);
});

it("KRİTİK: istek sunucuya ULAŞMADIYSA da seçim geri döner (ekran sunucudan farklı organ göstermez)", async () => {
  mockOrganYaniti = "ulasmadi";
  const u = await cizVeSec("Pankreas");
  expect(secili(u, "Pankreas")).toBe(false);
  expect(secili(u, "Böbrek")).toBe(true);
  expect(String((platformAlert as jest.Mock).mock.calls.at(-1)?.[1])).toMatch(/ulaşmadı/);
});

it("KARŞIT: sunucu kabul ederse seçim KALIR, uyarı çıkmaz", async () => {
  mockOrganYaniti = "basari";
  const u = await cizVeSec("Pankreas");
  expect(secili(u, "Pankreas")).toBe(true);
  expect(platformAlert).not.toHaveBeenCalled();
});
