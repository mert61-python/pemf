// Author: mertaygn, cglrgrkn
/**
 * AP-22 (istem 48 · D ekran görüntüsü 14-11): onay penceresi hedefi HAM VERİ etiketiyle ("Kuyu C6") yazıyordu — EN arayüzde başlık,
 * "Kuyu" satırı ve otomatik mühür notu Türkçe kalıyordu. Artık öneri yanıtının `hedefGosterim`i (istek dilinde) gösterilir; alan
 * yoksa (eski backend / kedi) ham etikete düşer. Mühür VERİSİ (`specs.target_label`) değişmez. Düzen `AiProPanel.AP_B4…` ile aynı.
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});
let mockDurum: Record<string, unknown> = { active: false, localized: false };
let mockGosterim: string | undefined;
const ODAK = { kip: "KUYUCUK", doz_mT: 0.6, beklenen_mT: 0.6, tavan_mT: 1.2, pay_yuzde: 5, kuyular: [] };
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async (yol: string) =>
    yol === "/ai/hazirlik"
      ? { moduller: [{ modul: "em_fantom", hazir: true }, { modul: "em_petri", hazir: true }, { modul: "petri_yolo", hazir: true }] }
      : mockDurum,
  ),
  apiPost: jest.fn(async (yol: string) => {
    if (yol === "/ai/pro/propose") {
      return {
        proposalId: "p1",
        specs: { organ_id: 11, duration_minutes: 20, coil_ids: [1, 2, 3, 4, 5, 6, 7], D: [0.2, 0, 0, 0, 0, 0, 0], P: [0, 0, 0, 0, 0, 0, 0],
          e_field: 0, model: "petri", target_label: "Kuyu C6", odak: ODAK },
        meta: { otomatik_secim: true },
        expiresAt: 0,
        ...(mockGosterim === undefined ? {} : { hedefGosterim: mockGosterim }),
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
  mockGosterim = undefined;
});
afterEach(() => jest.useRealTimers());

async function oneriPenceresi() {
  const u = render(<AiProPanel patientName="Örnek-1" secilebilirModeller={["fantom", "petri"]} kullaniciKipi="researcher" />);
  await act(async () => {});
  await act(async () => { fireEvent.press(u.getByLabelText(/Petri Kuyu/)); });
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  mockDurum = { active: false, localized: true, hazirlikActive: true, model: "petri" };
  for (let i = 0; i < 3; i++) await act(async () => { jest.advanceTimersByTime(3000); await Promise.resolve(); });
  expect(u.getByTestId("odak-ozeti")).toBeTruthy(); // ön-doğrulama: onay penceresi açık
  return u;
}
const metin = (d: { props: { children: unknown } }) =>
  Array.isArray(d.props.children) ? d.props.children.join("") : String(d.props.children);

it("KRİTİK AP-22: pencere hedefi yanıtın GÖSTERİM adıyla yazar (başlık, satır, mühür notu) — ham VERİ etiketi görünmez", async () => {
  mockGosterim = "Well C6";
  const u = await oneriPenceresi();
  expect(u.getByText(/Petri Kuyu · Well C6/)).toBeTruthy();
  expect(u.getByText("Well C6")).toBeTruthy();
  expect(metin(u.getByTestId("ai-onay-otomatik-muhur"))).toContain("«Well C6»");
  expect(u.queryByText(/Kuyu C6/)).toBeNull();
});

it("AP-22 geri uyum: alan yoksa (eski backend) / boşsa (kedi) ham etiket", async () => {
  const u = await oneriPenceresi();
  expect(u.getByText(/Petri Kuyu · Kuyu C6/)).toBeTruthy();
  u.unmount();
  mockGosterim = "";
  const u2 = await oneriPenceresi();
  expect(u2.getByText(/Petri Kuyu · Kuyu C6/)).toBeTruthy();
});
