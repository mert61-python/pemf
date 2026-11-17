/**
 * KP-8 · CoilParameterPanel kalan dallar (düzenek KP3-CoilParameterPanel-kollari ile AYNI — GERÇEK panel + apiClient; sahte fetch,
 * sınır kıskacı girdisi, toast köprüsü):
 *  - Bağlı OLMAYAN bobin (STM bayrakları verilmeyen ESP yuvası): "bağlı değil" bandı, "çevrim dışı" durum etiketi; girişler kilitli.
 *  - Geçersiz (sayı olmayan) girdi SESSİZCE süresiz / 0 Hz'e DÖNMEZ: başlatma panelin VARSAYILANLARIYLA gider (frekans / duty / faz /
 *    süre ayrı ayrı).
 * ⚠️ Ürün kodu (bobin sürme) DEĞİŞMEDİ — yalnız test.
 */
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api", bridgeBaseUrl: "http://127.0.0.1:8000/api", apiToken: "" },
}));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn(() => true) }));
let mockKiskacAtar = false;
jest.mock("@/services/therapyLimits", () => ({
  clampTherapyParams: (p: Record<string, number>) => {
    if (mockKiskacAtar) throw new Error("sınır tablosu okunamadı (aparat)");
    return { values: p, warnings: [] };
  },
}));

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";
import { Alert, TextInput } from "react-native";
import i18n from "i18next";
import { CoilParameterPanel } from "@/components/domain/CoilParameterPanel";

const T = (k: string): string => (i18n.t as unknown as (k: string) => string)(k);
const istekler: { start?: boolean }[] = [];
let startCoz: ((o: unknown) => void) | null = null;
let stopYanitlari: unknown[] = [];
const yanit = (o: unknown) => Promise.resolve({ ok: true, status: 200, json: async () => o, text: async () => JSON.stringify(o) });

beforeEach(() => {
  istekler.length = 0;
  startCoz = null;
  stopYanitlari = [];
  mockKiskacAtar = false;
  jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
  (global as unknown as { fetch: unknown }).fetch = jest.fn((_url: string, init?: { body?: string }) => {
    const govde = init?.body ? JSON.parse(init.body) : {};
    istekler.push(govde);
    if (govde.start === true) return new Promise((res) => { startCoz = (o) => res(yanit(o)); });
    return yanit(stopYanitlari.length ? stopYanitlari.shift() : { status: "success", transport: "stm32" });
  });
});
afterEach(() => jest.restoreAllMocks());

const bobin = {
  coilId: 1, connected: true, running: false, objectTemp: 0, frequencyHz: 0, dutyCycle: 0, magneticMt: 0, currentA: 0,
  stm32Driven: true, stmConnected: true,
};


it("bağlı olmayan ESP yuvası: 'bağlı değil' bandı + 'çevrim dışı' etiketi; girişler kilitli", () => {
  const u = render(<CoilParameterPanel coilId={8} connected={false} running={false} objectTemp={0} frequencyHz={0} dutyCycle={0}
    magneticMt={0} currentA={0} />);
  expect(u.getByText(T("kontrol.panel.bobinBagliDegil"))).toBeTruthy();
  expect(u.getByText(T("kontrol.bobin.offline"))).toBeTruthy();
  expect(u.getByLabelText(T("kontrol.panel.durumCevrimdisiEtiketi"))).toBeTruthy();
  expect(u.UNSAFE_getAllByType(TextInput).every((x) => x.props.editable === false)).toBe(true);
});

it("geçersiz girdi → başlatma panelin VARSAYILANLARIYLA (40 Hz · %30 · 15° · 7 dk) gider", async () => {
  const u = render(<CoilParameterPanel {...bobin} defaultFreq={40} defaultDuty={30} defaultPhase={15} defaultDuration={7} />);
  for (const x of u.UNSAFE_getAllByType(TextInput)) await act(async () => { fireEvent.changeText(x, "abc"); });
  await act(async () => { fireEvent.press(u.getByLabelText(T("kontrol.panel.baslatEtiketi"))); });
  await act(async () => { startCoz?.({ status: "success", transport: "stm32" }); });
  expect(istekler[0]).toMatchObject({ start: true, freq: 40, duty: 30, phase: 15, duration: 7 * 60 });
});
