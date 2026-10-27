// Author: mertaygn, cglrgrkn
/**
 * İG-6.33 — bobin paneli: YALNIZ BİR alan değişince giden komut o alanın YENİ değerini taşır (bayat kapanış yok).
 * =========================================================================================================
 * ÖLÇÜLEN KÖRLÜK (D5 doğrulaması): `sendCommand` useCallback bağımlılıklarından `freq, duty` silinince (bayat kapanış) panel
 * yeni frekansı GÖSTERİP eskisini GÖNDERİYOR; 129 ilgili jest dosyası 1592/1592 YEŞİL kalıyordu. `CoilParametreSenkronu.test.tsx`
 * frekans + duty + süreyi BİRLİKTE değiştirdiği için `duration` bağımlılığı kapanışı yeniliyor ve kusuru maskeliyordu.
 * Bu, 2026-09-11 saha arızasının sınıfı (görünen doz ≠ giden doz).
 *
 * GERÇEK: `CoilParameterPanel` + `apiClient` + `config`. Sahte EN ALT katta: `global.fetch` (gövde kaydedici) ve sınır kıskacı
 * (ilgisiz: değerleri olduğu gibi geçirir). Taban LAN (başlatma düz-HTTP kapısından geçer).
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

it("KRİTİK: operatör YALNIZ frekansı değiştirip Başlat'a basınca GİDEN frekans yeni değer (duty / süre değişmedi)", async () => {
  const u = render(<CoilParameterPanel {...temel} />);
  fireEvent.changeText(u.getByLabelText("Frekans (Hz)"), "76");
  await bas(u, "Bobini başlat");
  expect(gidenler).toEqual([{ freq: 76, duty: 25, phase: 0, duration: 20 * 60, start: true }]);
});

it("KRİTİK: operatör YALNIZ duty'yi değiştirince GİDEN duty yeni değer", async () => {
  const u = render(<CoilParameterPanel {...temel} />);
  fireEvent.changeText(u.getByLabelText("Duty (%)"), "50");
  await bas(u, "Bobini başlat");
  expect(gidenler).toEqual([{ freq: 100, duty: 50, phase: 0, duration: 20 * 60, start: true }]);
});

it("KRİTİK: toplu uygulama YALNIZ master frekansı değiştirince (76) panel de 76 GÖNDERİR", async () => {
  const u = render(<CoilParameterPanel {...temel} />);
  u.rerender(<CoilParameterPanel {...temel} defaultFreq={76} />);
  await bas(u, "Bobini başlat");
  expect(gidenler.map((g) => g.freq)).toEqual([76]);
});

it("KRİTİK: ÇALIŞAN bobinde yalnız frekans değişip 'Uygula'ya basılınca kesintisiz güncelleme yeni frekansı taşır", async () => {
  const u = render(<CoilParameterPanel {...temel} running />);
  fireEvent.changeText(u.getByLabelText("Frekans (Hz)"), "76");
  await bas(u, "Bobinin parametrelerini güncelle");
  expect(gidenler.map((g) => [g.freq, g.duty, g.start])).toEqual([[76, 25, true]]);
});

it("KARŞIT: hiçbir alan değişmezse varsayılanlar gider (kaydedici ve etiketler ölçüyor)", async () => {
  const u = render(<CoilParameterPanel {...temel} />);
  await bas(u, "Bobini başlat");
  expect(gidenler).toEqual([{ freq: 100, duty: 25, phase: 0, duration: 20 * 60, start: true }]);
});
