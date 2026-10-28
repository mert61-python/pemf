// Author: mertaygn, cglrgrkn
/**
 * SON-A1.8 (22-SON A1a · C36 / İG-6.33 kapı gücü) — bobin paneli: YALNIZ SÜRE ya da YALNIZ FAZ değişince giden komut YENİ değeri taşır.
 * =================================================================================================================================
 * ÖLÇÜLEN KÖRLÜK (uç 8b002fc0): C36 kapısı (`CoilParameterPanel.IG633.tekAlanDegisimi.test.tsx`) bayat kapanışı yalnız FREKANS ve DUTY
 * için ölçüyor. `sendCommand` useCallback bağımlılıklarından `duration` (ya da `phase`) silinince panel yeni süreyi GÖSTERİP eskisini
 * GÖNDERİYOR — `CoilParameterPanel`'i anan 31 jest dosyası 195 / 195 YEŞİL (iki mutant ayrı ayrı). Süre doz parametresidir (2026-09-11
 * saha arızası sınıfı: görünen doz ≠ giden doz).
 *
 * GERÇEK: `CoilParameterPanel` + `apiClient` + `config` (C36 kapısıyla AYNI aparat). Sahte EN ALT katta: `global.fetch` (gövde kaydedici)
 * ve sınır kıskacı (değerleri olduğu gibi geçirir).
 */
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn(() => true) }));
jest.mock("@/services/therapyLimits", () => ({
  clampTherapyParams: (p: Record<string, number>) => ({ values: p, warnings: [] }),
}));

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";
import { Alert } from "react-native";
import { updateServiceConfig } from "@/services/config";
import { CoilParameterPanel } from "@/components/domain/CoilParameterPanel";

type Govde = { freq: number; duty: number; phase: number; duration: number; start: boolean };
const gidenler: Govde[] = [];

beforeEach(() => {
  gidenler.length = 0;
  jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
  (global as { fetch: unknown }).fetch = jest.fn((url: string, init?: { body?: string }) => {
    if (/\/coil\/\d+\/control$/.test(String(url))) gidenler.push(JSON.parse(init?.body ?? "{}"));
    const g = { status: "success", transport: "stm32" };
    return Promise.resolve({ ok: true, status: 200, json: async () => g, text: async () => JSON.stringify(g) });
  });
  expect(updateServiceConfig("http://192.168.1.5:8000")).toBe(true);
});
afterEach(() => jest.restoreAllMocks());

const temel = {
  coilId: 1,
  connected: true,
  running: false,
  objectTemp: 0,
  frequencyHz: 0,
  dutyCycle: 0,
  magneticMt: 0,
  currentA: 0,
  stm32Driven: true,
  stmConnected: true,
  measuredFields: [] as string[],
  defaultFreq: 100,
  defaultDuty: 25,
  defaultPhase: 0,
  defaultDuration: 20,
};

async function bas(u: ReturnType<typeof render>, etiket: string) {
  await act(async () => {
    fireEvent.press(u.getByLabelText(etiket));
  });
}

it("KRİTİK: operatör YALNIZ SÜREYİ değiştirip Başlat'a basınca GİDEN süre yeni değer (frekans / duty / faz değişmedi)", async () => {
  const u = render(<CoilParameterPanel {...temel} />);
  fireEvent.changeText(u.getByLabelText("Süre (dk)"), "7");
  await bas(u, "Bobini başlat");
  expect(gidenler).toEqual([{ freq: 100, duty: 25, phase: 0, duration: 7 * 60, start: true }]);
});

it("KRİTİK: operatör YALNIZ FAZI değiştirince GİDEN faz yeni değer", async () => {
  const u = render(<CoilParameterPanel {...temel} />);
  fireEvent.changeText(u.getByLabelText("Faz (°)"), "90");
  await bas(u, "Bobini başlat");
  expect(gidenler).toEqual([{ freq: 100, duty: 25, phase: 90, duration: 20 * 60, start: true }]);
});
