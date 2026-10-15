// Author: mertaygn, cglrgrkn
/**
 * TD6 · K3 (tezgâh Oturum 13) — tekil bobin START'ını kart REDDETTİYSE panel NEDENİ ve EYLEMİ gösterir.
 *
 * ÖLÇÜLEN: çift yönlü bobin 1'e %80 → API "success", bobin başlamıyor, ekranda sebep yok. Backend artık kartın duty reddinde
 * `{status:"error", kartReddetti:true, mesaj:"Bobin 1 çift yönlü kipte en fazla %50 çalışabilir; …"}` döner; panel bu metni gösterir.
 * Gerçek `apiPost` (fetch sahte) — yanıt istemci katmanından olduğu gibi geçer.
 */
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api", bridgeBaseUrl: "http://127.0.0.1:8000/api", apiToken: "" },
}));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn(() => true) }));
jest.mock("@/services/therapyLimits", () => ({
  clampTherapyParams: (p: Record<string, number>) => ({ values: p, warnings: [] }),
}));

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";
import { Alert } from "react-native";
import { CoilParameterPanel } from "@/components/domain/CoilParameterPanel";

const K3 =
  "Bobin 1 çift yönlü kipte en fazla %50 çalışabilir; %80 kabul edilmedi. Duty'yi %50 veya altına indirip yeniden başlatın " +
  "(ya da ⚡ Sürüş Kipi'nden bu bobini Unipolar yapın).";
let govdeYaniti: unknown = null;

beforeEach(() => {
  jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
  (global as any).fetch = jest.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => govdeYaniti,
    text: async () => JSON.stringify(govdeYaniti),
  }));
});
afterEach(() => jest.restoreAllMocks());

const bobin = {
  coilId: 1, connected: true, running: false, objectTemp: 0, frequencyHz: 0, dutyCycle: 0, magneticMt: 0, currentA: 0,
  stm32Driven: true, stmConnected: true,
};

it("KRİTİK K3: kart duty'yi reddederse panel kartın NEDEN + EYLEM metnini gösterir", async () => {
  govdeYaniti = { status: "error", transport: "stm32", kartReddetti: true, mesaj: K3 };
  const u = render(<CoilParameterPanel {...bobin} />);
  await act(async () => {
    fireEvent.press(u.getByLabelText("Bobini başlat"));
  });
  expect(u.getByText(K3)).toBeTruthy();
  expect(u.queryByText(/Komut onaylanamadı/)).toBeNull();
});

it("KARŞIT K3: nedensiz red eski genel metni korur", async () => {
  govdeYaniti = { status: "error", transport: "stm32" };
  const u = render(<CoilParameterPanel {...bobin} />);
  await act(async () => {
    fireEvent.press(u.getByLabelText("Bobini başlat"));
  });
  expect(u.getByText(/Komut onaylanamadı — bobin başlatılamamış olabilir/)).toBeTruthy();
});
