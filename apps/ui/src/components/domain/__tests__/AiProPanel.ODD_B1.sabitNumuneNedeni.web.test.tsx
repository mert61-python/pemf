// Author: mertaygn, cglrgrkn
/**
 * ODD B-1 · Y300 (ODK-B keşfi 18-11) — petri (sabit numune) seansında ölçüm doğrulanamayınca sunucu son onaylı planla sürmeye devam
 * eder (`dogrulamaKalanSn`) ve pencere dolunca bobinleri durdurup NEDENİ yollar (`surusDurduNeden`, cihaz dili). Panel ikisini de
 * seans sürerken GÖRÜNÜR şeritte söyler (eskiden yalnız günlükte "ENGELLİ" — operatör bobinin neden durduğunu göremiyordu).
 * Alanlar yoksa (kedi / eski backend) şerit YOK. Düzen `AiProPanel.AP_B1…` ile aynı (web, seans benimsenmiş).
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});
let mockDurum: Record<string, unknown> = { active: false, localized: false };
let mockV: Record<string, unknown> | undefined;
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
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionData: mockV, aiVisionFresh: true }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "a@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({
  useOperator: () => ({ operatorEmail: "a@x.com" }),
  useOperatorOptional: () => ({ operatorEmail: "a@x.com" }),
}));
jest.mock("expo-camera", () => {
  const React2 = require("react");
  return { CameraView: React2.forwardRef(() => null), useCameraPermissions: () => [{ granted: true }, jest.fn()] };
});

import { act, render } from "@testing-library/react-native";
import React from "react";

import i18n from "@/i18n";

import { AiProPanel } from "../AiProPanel";

const NEDEN = "Plaka 30 sn boyunca doğrulanamadı — bobinler durduruldu. Neden: X. Ölçüm sürüyor; plaka yeniden doğrulanınca sürüş kendiliğinden devam eder.";

beforeEach(() => {
  jest.useFakeTimers();
  mockDurum = { active: true, ownerClientId: "web-id", model: "petri", organId: 11 };
  mockV = undefined;
});
afterEach(async () => {
  jest.useRealTimers();
  await i18n.changeLanguage("tr");
});

async function seansPaneli() {
  const u = render(<AiProPanel patientName="Örnek-1" secilebilirModeller={["fantom", "petri"]} kullaniciKipi="researcher" />);
  for (let i = 0; i < 2; i++) await act(async () => { jest.advanceTimersByTime(3000); await Promise.resolve(); });
  expect(u.queryByLabelText("AI Pro otonom seansı durdur")).toBeTruthy(); // ön-doğrulama: seans sürüyor
  return u;
}

it("KRİTİK B-1: pencere doldu → sunucunun NEDENİ görünür uyarı şeridinde (alert rolü)", async () => {
  mockV = { detected: false, surusDurduNeden: NEDEN, dogrulamaKalanSn: null };
  const u = await seansPaneli();
  const serit = u.getByTestId("aipro-surus-durdu-neden");
  expect(serit.props.accessibilityRole).toBe("alert");
  expect(u.getByText(NEDEN)).toBeTruthy();
  expect(u.queryByTestId("aipro-dogrulama-suruyor")).toBeNull();
});

it("KRİTİK B-1: doğrulanamayan turda 'son onaylı planla sürüyor' + kalan sn (TR ve EN katalogdan)", async () => {
  mockV = { detected: false, surusDurduNeden: "", dogrulamaKalanSn: 17 };
  const u = await seansPaneli();
  const kutu = u.getByTestId("aipro-dogrulama-suruyor");
  expect(kutu).toBeTruthy();
  expect(u.getByText("Plaka yeniden doğrulanıyor — son onaylı planla sürüş sürüyor (en çok 17 sn daha).")).toBeTruthy();
  await act(async () => { await i18n.changeLanguage("en"); });
  expect(u.getByText("Re-verifying the plate — driving continues with the last approved plan (for at most 17 s more).")).toBeTruthy();
  expect(u.queryByTestId("aipro-surus-durdu-neden")).toBeNull();
});

it("KARŞIT B-1: alanlar yok (kedi / eski backend) ya da 0 sn değil null → şerit YOK; seans yokken neden gösterilmez", async () => {
  mockV = { detected: true };
  const u = await seansPaneli();
  expect(u.queryByTestId("aipro-surus-durdu-neden")).toBeNull();
  expect(u.queryByTestId("aipro-dogrulama-suruyor")).toBeNull();
  u.unmount();
  mockDurum = { active: false, localized: false };
  mockV = { detected: false, surusDurduNeden: NEDEN, dogrulamaKalanSn: 5 };
  const u2 = render(<AiProPanel patientName="Örnek-1" secilebilirModeller={["fantom", "petri"]} kullaniciKipi="researcher" />);
  await act(async () => { jest.advanceTimersByTime(3000); await Promise.resolve(); });
  expect(u2.queryByTestId("aipro-surus-durdu-neden")).toBeNull();
  expect(u2.queryByTestId("aipro-dogrulama-suruyor")).toBeNull();
});

it("B-1: kalan sn 0 da sayıdır (şerit görünür)", async () => {
  mockV = { detected: false, dogrulamaKalanSn: 0 };
  const u = await seansPaneli();
  expect(u.getByTestId("aipro-dogrulama-suruyor")).toBeTruthy();
  expect(u.getByText(/en çok 0 sn daha/)).toBeTruthy();
});
