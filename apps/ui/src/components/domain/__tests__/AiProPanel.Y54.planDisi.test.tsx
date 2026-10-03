// Author: mertaygn, cglrgrkn
/**
 * Y54 (sahip) — AI Pro sürerken operatörün durdurduğu bobin seans sonuna dek AI Pro planından ÇIKAR ve ekranda
 * "Bobin X AI Pro planından çıkarıldı" yazar. Backend `perCoil[].planDisi` (gerçek uç: `tests/test_Y54_…`).
 * ⚠️ MUTASYON: panel `planDisi`yi okumazsa "sürülmedi" der (neden gizlenir) → KIRMIZI.
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

function veri(planDisi: number[]) {
  return {
    detected: true,
    reliability: 0.8,
    organName: "Mide",
    remainingSec: 300,
    perCoil: [1, 2, 3, 4, 5, 6, 7].map((id) =>
      planDisi.includes(id)
        ? { id, freq: 0, duty: 0, phase: 0, suruldu: false, planDisi: true }
        : { id, freq: 1, duty: 30 + id, phase: 0, suruldu: true }
    ),
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

it("KRİTİK: plan dışı bobin için 'Bobin X AI Pro planından çıkarıldı' yazar; satırı 'sürülmedi' DEMEZ", async () => {
  const m = await metin(veri([2, 6]));
  expect(m).toContain("Bobin 2 AI Pro planından çıkarıldı");
  expect(m).toContain("Bobin 6 AI Pro planından çıkarıldı");
  expect(m).not.toContain("sürülmedi");
  expect(m).toContain("31%"); // bobin 1 sürüyor
});

it("KARŞIT: plan dışı bobin yoksa uyarı satırı YOK", async () => {
  const m = await metin(veri([]));
  expect(m).not.toContain("planından çıkarıldı");
});
