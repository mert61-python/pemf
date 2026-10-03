// Author: mertaygn, cglrgrkn
/**
 * D1.82 · İG-6.8 · Y47 — bobin panelinin "⏹ Durdur"u kendi START isteği ASKIDAYKEN de basılabilir ve basış STOP gönderir;
 * START yanıtı durdurmadan SONRA gelirse STOP YENİDEN gider.
 * ==========================================================================================================
 * ÖLÇÜLEN KUSUR (aday doğrulaması İG-6.8, gerçek web + backend, CDP ile 5 sn bekletilen `/api/coil/1/control`):
 * START askıdayken "Bobini durdur" `aria-disabled`, basış → STOP isteği 0, telde bobin 1 duty 0,25 (çalışıyor). Kodun kendi
 * yorumu "DURDURMA ASLA KİLİTLENMEZ" diyordu. Planın "uyandırır" notu: geç gelen START durdurmadan sonra işlenirse bobin
 * yeniden başlar (elle tekil yolda nesil denetimi yok — 1-C bilinçli kapsam) → START yanıtından sonra STOP yinelenir.
 *
 * GERÇEK: `CoilParameterPanel` + `apiClient`. Sahte YALNIZ `fetch` (START asılı söz) ve sınır kıskacı (ilgisiz).
 * ⚠️ MUTASYON: Durdur'a `disabled={loading}` geri konursa ya da START sonrası STOP yinelemesi silinirse KIRMIZI.
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

const istekler: { start?: boolean }[] = [];
let startCoz: ((o: unknown) => void) | null = null;
const yanit = (o: unknown) =>
  Promise.resolve({ ok: true, status: 200, json: async () => o, text: async () => JSON.stringify(o) });

beforeEach(() => {
  istekler.length = 0;
  startCoz = null;
  jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
  (global as any).fetch = jest.fn((_url: string, init?: any) => {
    const govde = init?.body ? JSON.parse(init.body) : {};
    istekler.push(govde);
    if (govde.start === true) return new Promise((res) => { startCoz = (o) => res(yanit(o) as any); });
    return yanit({ status: "success", transport: "stm32" });
  });
});
afterEach(() => jest.restoreAllMocks());

const bobin = {
  coilId: 1, connected: true, running: false, objectTemp: 0, frequencyHz: 0, dutyCycle: 0, magneticMt: 0, currentA: 0,
  stm32Driven: true, stmConnected: true,
};

it("KRİTİK: START askıdayken 'Bobini durdur' basılabilir ve STOP (start:false) gönderir", async () => {
  const u = render(<CoilParameterPanel {...bobin} />);
  await act(async () => {
    fireEvent.press(u.getByLabelText("Bobini başlat"));
  });
  expect(istekler.map((i) => i.start)).toEqual([true]); // aparat: START uçuşta
  const durdur = u.getByLabelText("Bobini durdur");
  expect(durdur.props.accessibilityState?.disabled).not.toBe(true);
  await act(async () => {
    fireEvent.press(durdur);
  });
  expect(istekler.map((i) => i.start)).toEqual([true, false]);
});

it("KRİTİK: START yanıtı durdurmadan SONRA 'success' dönerse STOP YENİDEN gider (son söz durdurmanın)", async () => {
  const u = render(<CoilParameterPanel {...bobin} />);
  await act(async () => {
    fireEvent.press(u.getByLabelText("Bobini başlat"));
  });
  await act(async () => {
    fireEvent.press(u.getByLabelText("Bobini durdur"));
  });
  await act(async () => {
    startCoz!({ status: "success", transport: "stm32" });
  });
  await act(async () => {});
  expect(istekler.map((i) => i.start)).toEqual([true, false, false]);
});

it("KARŞIT: durdurma istenmediyse START yanıtından sonra STOP GÖNDERİLMEZ (gereksiz durdurma yok)", async () => {
  const u = render(<CoilParameterPanel {...bobin} />);
  await act(async () => {
    fireEvent.press(u.getByLabelText("Bobini başlat"));
  });
  await act(async () => {
    startCoz!({ status: "success", transport: "stm32" });
  });
  await act(async () => {});
  expect(istekler.map((i) => i.start)).toEqual([true]);
});
