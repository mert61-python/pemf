// Author: mertaygn, cglrgrkn
/**
 * D1.84 · B-5.2 · Y25 — AI Pro bobin tablosu yalnız TELDE sürülen bobini "sürüldü" (duty %) gösterir.
 *
 * Eski panel `perCoil`'deki PLAN değerini her bobin için "Duty %" diye yazıyordu; telde bobin 6-7 duty 0'ken (MQTT ölü
 * konu) ve kart bir bobini reddettiğinde de. Backend artık `suruldu` taşır; `false` → "sürülmedi (plan X%)".
 * ⚠️ DAVRANIŞSAL: GERÇEK `AiProPanel` (web kipi), WS verisi `LiveDataContext` üzerinden sahte.
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});

const mockVeri: { aiVisionData: unknown } = { aiVisionData: null };
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => ({ active: true, localized: true })),
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
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionData: mockVeri.aiVisionData, aiVisionFresh: true }),
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

import { act, render } from "@testing-library/react-native";
import React from "react";

import { AiProPanel } from "../AiProPanel";

function veri(suruldu: (id: number) => boolean | undefined) {
  return {
    detected: true,
    reliability: 0.8,
    organName: "Mide",
    remainingSec: 300,
    perCoil: [1, 2, 3, 4, 5, 6, 7].map((id) => ({ id, freq: 1, duty: 30 + id, phase: 0, suruldu: suruldu(id) })),
  };
}

function duz(d: any): string {
  if (d == null || typeof d === "boolean") return "";
  if (typeof d === "string" || typeof d === "number") return String(d);
  if (Array.isArray(d)) return d.map(duz).join("");
  const ic = (d.children || []).map(duz).join("");
  return d.type === "Text" ? ic : ` ${ic} `;
}

async function metin(v: unknown) {
  mockVeri.aiVisionData = v;
  const u = render(<AiProPanel patientName="Tekir" />);
  await act(async () => {});
  return duz(u.toJSON());
}

it("KRİTİK: telde sürülmeyen bobin (6) 'sürülmedi' gösterilir, plan duty'si 'uygulandı' gibi YAZILMAZ", async () => {
  const m = await metin(veri((id) => id !== 6));
  expect(m).toContain("sürülmedi (plan 36%)");
  expect(m).toContain("35%"); // bobin 5 sürüldü
});

it("KARŞIT: tüm bobinler sürüldüyse 'sürülmedi' YOK", async () => {
  const m = await metin(veri(() => true));
  expect(m).not.toContain("sürülmedi");
  expect(m).toContain("37%");
});

it("KARŞIT (sürüm kayması): alanı göndermeyen eski backend eski gösterimi korur", async () => {
  const m = await metin(veri(() => undefined));
  expect(m).not.toContain("sürülmedi");
});
