// Author: mertaygn, cglrgrkn
/**
 * D3I çapraz (C2) · Ö.4-Y8 — AI Pro'nun "Durdur"u ve panel kapanırken giden `/ai/pro/stop` düz-HTTP kapısına BAĞLI DEĞİL.
 * ==========================================================================================================
 * ÖLÇÜLEN KUSUR (doğrulayıcı D, okuma + A1.3 kapısının karşıt ölçümü): iki `/ai/pro/stop` çağrısı bayraksız `apiPost`'tu → genel
 * (özel ağ DIŞI) `http://` tabanında AI Pro otonom seansının durdurma isteği HİÇ gitmiyordu (önceden var; D3I-A1.3 kaçırmıştı).
 * Bayrağın istemci kapısını gerçekten aştığı `services/__tests__/acilDurdur.Y8.duzHttp.D3I.test.tsx`'te GERÇEK `apiClient` ile
 * ölçülür; burada panelin İKİ durdurma çağrısının da bayrağı taşıdığı ölçülür (sahiplik kurgusu `AiProPanelSahiplik.test.tsx`).
 * ⚠️ MUTASYON: herhangi bir `/ai/pro/stop` çağrısından `durdurma: true` silinirse KIRMIZI.
 */
let mockDurum: Record<string, unknown> = { active: false };

jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => mockDurum),
  apiPost: jest.fn(async () => ({ status: "success" })),
  authHeaders: jest.fn(() => ({})),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  AI_TIMEOUT_MS: 120000,
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://203.0.113.5:8000/api" },
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
      React2.useImperativeHandle(ref, () => ({ takePictureAsync: async () => ({ base64: "AAAA" }) }));
      return null;
    }),
    useCameraPermissions: () => [{ granted: true }, jest.fn()],
  };
});

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";

import { apiPost } from "@/services/apiClient";

import { AiProPanel } from "../AiProPanel";

const stopCagrilari = () => (apiPost as jest.Mock).mock.calls.filter((c) => c[0] === "/ai/pro/stop");

beforeEach(() => {
  (apiPost as jest.Mock).mockClear();
  mockDurum = { active: true, ownerClientId: "benim-id" };
});

async function panel() {
  const u = render(<AiProPanel patientName="Tekir" />);
  await act(async () => {});
  expect(u.queryByLabelText("AI Pro otonom seansı durdur")).toBeTruthy(); // ön-doğrulama: panel running=true'yu benimsedi
  return u;
}

it("KRİTİK: operatörün AÇIK 'Durdur'u `/ai/pro/stop`'u `durdurma: true` ile gönderir (Ö.4-Y8)", async () => {
  const u = await panel();
  await act(async () => {
    fireEvent.press(u.getByLabelText("AI Pro otonom seansı durdur"));
  });
  const c = stopCagrilari();
  expect(c).toHaveLength(1);
  expect(c[0][3]).toEqual({ durdurma: true });
});

it("KRİTİK: kendi seansımızın paneli kapanırken giden `/ai/pro/stop` da `durdurma: true` taşır", async () => {
  const u = await panel();
  await act(async () => {
    u.unmount();
  });
  const c = stopCagrilari();
  expect(c).toHaveLength(1);
  expect(c[0][3]).toEqual({ durdurma: true });
});
