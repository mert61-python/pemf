// Author: mertaygn, cglrgrkn
/**
 * AP · B5 + B2 (istem 48, tezgâh 13 Kasım 2026): petri kuyusu seçerken "Organ değiştirilemedi — Hedef 11 'Kedi Organ' için desteklenmiyor"
 * ve elle seçilen kuyunun (C6) hazırlıkta otomatiğe (C2) düşmesi.
 *  · Durum ucunun hedef adayları SON LOKALİZASYONUN modeline aittir (`targetsModel`); panel başka modelin bayat adaylarını GÖSTERMEZ
 *    (seçilirse sunucu onları o modelin kurallarıyla reddederdi).
 *  · Aynı modelin adayından yapılan seçim `/organ`a panelin modeliyle gider ve hazırlığa TAŞINIR (otomatiğe düşmez).
 *  · Araştırmada ret başlığı "Hedef değiştirilemedi" — "Organ" DEĞİL (panel modeli henüz bilinmese de).
 * Alan yoksa (eski backend) eski davranış: adaylar gösterilir.
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});
let mockDurum: Record<string, unknown> = { active: false, localized: false };
let mockOrganRet: { durum: number; detay: string } | null = null;
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async (yol: string) =>
    yol === "/ai/hazirlik"
      ? { moduller: [{ modul: "em_fantom", hazir: true }, { modul: "em_petri", hazir: true }, { modul: "petri_yolo", hazir: true }] }
      : mockDurum,
  ),
  apiPost: jest.fn(async (yol: string, _g: unknown, _f: unknown, opts?: { onHttpError?: (d: number, x?: string) => void }) => {
    if (yol === "/ai/pro/organ" && mockOrganRet) {
      opts?.onHttpError?.(mockOrganRet.durum, mockOrganRet.detay);
      return null;
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
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionData: undefined, aiVisionFresh: false }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "a@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "a@x.com" }) }));
jest.mock("expo-camera", () => {
  const React2 = require("react");
  return { CameraView: React2.forwardRef(() => null), useCameraPermissions: () => [{ granted: true }, jest.fn()] };
});

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";

import { apiPost, platformAlert } from "@/services/apiClient";

import { AiProPanel } from "../AiProPanel";

const C6 = { id: 11, label: "Kuyu C6", etiketGosterim: "Kuyu C6", pxn: [0.6, 0.5], reliability: 0.9 };
const C2 = { id: 7, label: "Kuyu C2", etiketGosterim: "Kuyu C2", pxn: [0.3, 0.5], reliability: 0.95 };

beforeEach(() => {
  jest.useFakeTimers();
  mockDurum = { active: false, localized: false };
  mockOrganRet = null;
  (apiPost as jest.Mock).mockClear();
  (platformAlert as jest.Mock).mockClear();
});
afterEach(() => jest.useRealTimers());

async function petriPaneli() {
  const u = render(<AiProPanel patientName="Örnek-1" secilebilirModeller={["fantom", "petri"]} kullaniciKipi="researcher" />);
  await act(async () => {});
  await act(async () => { fireEvent.press(u.getByLabelText(/Petri Kuyu/)); });
  await act(async () => { jest.advanceTimersByTime(3000); await Promise.resolve(); });
  return u;
}
const govde = (yol: string) =>
  (apiPost as jest.Mock).mock.calls.filter((k) => k[0] === yol).pop()?.[1] as Record<string, unknown> | undefined;

it("KRİTİK B5: önbellekteki adaylar BAŞKA modelin (fantom) son lokalizasyonundansa petri panelinde GÖSTERİLMEZ", async () => {
  mockDurum = { active: false, model: "kedi", targetsModel: "fantom", targets: [C6, C2] };
  const u = await petriPaneli();
  expect(u.queryByTestId("hedef-satir-11")).toBeNull();
  expect(u.queryByTestId("hedef-halka-11")).toBeNull();
});

it("B5 + B2: durdurma sonrası (etkin model kedi) AYNI modelin adayı seçilir → /organ panelin modeliyle, seçim HAZIRLIĞA taşınır", async () => {
  mockDurum = { active: false, model: "kedi", targetsModel: "petri", targets: [C6, C2] };
  const u = await petriPaneli();
  await act(async () => { fireEvent.press(u.getByTestId("hedef-satir-11")); });
  expect(govde("/ai/pro/organ")).toMatchObject({ organ_id: 11, model: "petri" });
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  expect(govde("/ai/pro/hazirlik/baslat")).toMatchObject({ organ_id: 11, model: "petri" });
});

it("SÜRÜM KAYMASI: `targetsModel` alanı yoksa (eski backend) adaylar eskisi gibi gösterilir", async () => {
  mockDurum = { active: false, targets: [C6] };
  const u = await petriPaneli();
  expect(u.getByTestId("hedef-satir-11")).toBeTruthy();
});

it("B5: araştırmada ret başlığı 'Hedef değiştirilemedi' + sunucunun eylem metni; seçim geri alınır", async () => {
  mockDurum = { active: false, targetsModel: "petri", targets: [C6, C2] };
  mockOrganRet = { durum: 422, detay: "Hedef 11, 'Petri Kuyu' modeli için desteklenmiyor" };
  const u = await petriPaneli();
  await act(async () => { fireEvent.press(u.getByTestId("hedef-satir-11")); });
  expect(platformAlert).toHaveBeenCalledWith("Hedef değiştirilemedi", "Hedef 11, 'Petri Kuyu' modeli için desteklenmiyor");
  expect(u.getByTestId("hedef-satir-11").props.accessibilityState?.selected).toBeFalsy();
});

it("B5: model kartı henüz seçilmemişken (panel yeniden açıldı) bile araştırmada başlık 'Organ' DEĞİL 'Hedef değiştirilemedi'", async () => {
  mockDurum = { active: false, targets: [C6] }; // eski backend: targetsModel yok → adaylar görünür
  mockOrganRet = { durum: 422, detay: "Hedef 11, 'Kedi Organ' modeli için desteklenmiyor" };
  const u = render(<AiProPanel patientName="Örnek-1" secilebilirModeller={["fantom", "petri"]} kullaniciKipi="researcher" />);
  await act(async () => {});
  await act(async () => { jest.advanceTimersByTime(3000); await Promise.resolve(); });
  await act(async () => { fireEvent.press(u.getByTestId("hedef-satir-11")); });
  expect(platformAlert).toHaveBeenCalledWith("Hedef değiştirilemedi", "Hedef 11, 'Kedi Organ' modeli için desteklenmiyor");
});
