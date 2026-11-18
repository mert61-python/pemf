// Author: mertaygn, cglrgrkn
/**
 * ODD K-3 / K-4 / K-5 (ODK-B keşfi 18-11, sahip 14–15.png): hazırlık sürerken ana düğme pasif görünümlü "Hazırlanıyor…" idi (yalnız şeritte
 * küçük "Vazgeç"; düğmeye basmak hazırlığı YENİDEN başlatıyordu) → "Hazırlığı durdur" ve basınca hazırlık durur. Petride gecikme ipucu
 * "numuneyi" değil "plakayı" der. "✓ Konumlandı" yalnız önizleme / seans sürerken (seans bitince yeşil kalıyordu). Düzen `AP22` ile aynı.
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});
let mockDurum: Record<string, unknown> = { active: false, localized: false };
const mockPost = jest.fn(async (_yol: string, _g?: unknown): Promise<unknown> => ({ status: "success" }));
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async (yol: string) =>
    yol === "/ai/hazirlik"
      ? { moduller: [{ modul: "em_fantom", hazir: true }, { modul: "em_petri", hazir: true }, { modul: "petri_yolo", hazir: true }] }
      : mockDurum,
  ),
  apiPost: (...a: unknown[]) => (mockPost as unknown as (...b: unknown[]) => unknown)(...a),
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

import { AiProPanel } from "../AiProPanel";

beforeEach(() => {
  jest.useFakeTimers();
  mockDurum = { active: false, localized: false };
  mockPost.mockClear();
});
afterEach(() => jest.useRealTimers());

async function ilerle(ms: number, adim = 3000) {
  for (let t = 0; t < ms; t += adim) await act(async () => { jest.advanceTimersByTime(adim); await Promise.resolve(); });
}
async function hazirlikta() {
  const u = render(<AiProPanel patientName="Örnek-1" secilebilirModeller={["fantom", "petri"]} kullaniciKipi="researcher" />);
  await act(async () => {});
  await act(async () => { fireEvent.press(u.getByLabelText(/Petri Kuyu/)); });
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  mockDurum = { active: false, localized: false, hazirlikActive: true, model: "petri" };
  await ilerle(3000);
  return u;
}
const metin = (u: ReturnType<typeof render>) => JSON.stringify(u.toJSON());

it("KRİTİK K-3: hazırlık sürerken GÖRÜNÜR 'Hazırlığı durdur' düğmesi — basınca hazırlık durur (yeniden BAŞLAMAZ)", async () => {
  const u = await hazirlikta();
  expect(metin(u)).toContain("🔎 Hazırlanıyor…"); // durum göstergesi (kritik anahtar) AYNEN
  const dugme = u.getByTestId("ai-pro-hazirlik-durdur");
  expect(dugme.props.accessibilityLabel).toBe("Hazırlığı durdur — kamera önizlemesi kapanır");
  expect(metin(u)).toContain("⏹ Hazırlığı durdur");
  const baslatOnce = mockPost.mock.calls.filter((k) => k[0] === "/ai/pro/hazirlik/baslat").length;
  await act(async () => { fireEvent.press(dugme); });
  expect(mockPost.mock.calls.filter((k) => k[0] === "/ai/pro/hazirlik/durdur").length).toBeGreaterThan(0);
  expect(mockPost.mock.calls.filter((k) => k[0] === "/ai/pro/hazirlik/baslat").length).toBe(baslatOnce);
  expect(u.queryByTestId("ai-pro-hazirlik-durdur")).toBeNull();
});

it("KARŞIT K-3: hazırlık yokken düğme YOK", async () => {
  const u = render(<AiProPanel patientName="Örnek-1" secilebilirModeller={["fantom", "petri"]} kullaniciKipi="researcher" />);
  await ilerle(3000);
  expect(u.queryByTestId("ai-pro-hazirlik-durdur")).toBeNull();
});

it("KRİTİK K-5: petride 45 sn sonra gecikme ipucu 'plakayı' der ('numuneyi' DEĞİL)", async () => {
  const u = await hazirlikta();
  await ilerle(48000);
  expect(metin(u)).toContain("Hâlâ bulunamadı: plakayı kabinin ortasına düz yerleştirin");
  expect(metin(u)).not.toContain("numuneyi kabinin ortasına");
});

it("KRİTİK K-4: hazırlık / seans yokken '✓ Konumlandı' gösterilmez (sunucu önbelleği lokalize olsa da)", async () => {
  mockDurum = { active: false, localized: true, model: "petri" };
  const u = render(<AiProPanel patientName="Örnek-1" secilebilirModeller={["fantom", "petri"]} kullaniciKipi="researcher" />);
  await ilerle(3000);
  expect(metin(u)).not.toContain("✓ Konumlandı");
});
