/**
 * KP-3 C · CoilParameterPanel kapsanmayan kolları — her test bir DAVRANIŞ iddiası:
 *  - START uçuştayken basılan DURDUR'un yinelenen STOP'u onaylanmazsa operatöre "DURDURMA ONAYLANAMADI — ACİL DURDUR'a basın" denir
 *    (sahte güvence yok).
 *  - Komut hazırlanırken beklenmeyen hata: "Komut gönderilemedi" denir, istek GİTMEZ ve panel kilitli kalmaz (Durdur yine basılabilir).
 *  - Ana paneldeki faz değeri değişince bu bobinin faz alanı onu izler.
 * GERÇEK: CoilParameterPanel + apiClient. SAHTE: fetch (ağ sınırı), sınır kıskacı (girdi; ikinci testte atar), toast köprüsü.
 * ⚠️ Ürün kodu (bobin sürme / DURDUR) DEĞİŞMEDİ — yalnız test.
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
import { Alert } from "react-native";
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

it("yinelenen STOP onaylanmazsa 'DURDURMA ONAYLANAMADI — ACİL DURDUR'a basın' denir", async () => {
  const u = render(<CoilParameterPanel {...bobin} />);
  await act(async () => { fireEvent.press(u.getByLabelText(T("kontrol.panel.baslatEtiketi"))); });
  stopYanitlari = [{ status: "success", transport: "stm32" }, { status: "mqtt_unavailable" }];
  await act(async () => { fireEvent.press(u.getByLabelText(T("kontrol.panel.durdurEtiketi"))); });
  await act(async () => { startCoz!({ status: "success", transport: "stm32" }); });
  await act(async () => {});
  expect(istekler.map((i) => i.start)).toEqual([true, false, false]);
  expect(u.getByText(T("kontrol.panel.durdurmaOnaylanamadi"))).toBeTruthy();
});

it("komut hazırlanırken hata: 'Komut gönderilemedi', istek gitmez, Durdur yine basılabilir", async () => {
  mockKiskacAtar = true;
  const u = render(<CoilParameterPanel {...bobin} />);
  await act(async () => { fireEvent.press(u.getByLabelText(T("kontrol.panel.baslatEtiketi"))); });
  expect(u.getByText(T("kontrol.panel.komutGonderilemedi"))).toBeTruthy();
  expect(istekler).toHaveLength(0);
  mockKiskacAtar = false;
  await act(async () => { fireEvent.press(u.getByLabelText(T("kontrol.panel.durdurEtiketi"))); });
  expect(istekler.map((i) => i.start)).toEqual([false]);
});

it("ana paneldeki faz değişince bobinin faz alanı izler", () => {
  const u = render(<CoilParameterPanel {...bobin} defaultPhase={0} />);
  const faz = () => u.getByLabelText(T("kontrol.panel.fazDerece"));
  expect(faz().props.value).toBe("0");
  u.rerender(<CoilParameterPanel {...bobin} defaultPhase={90} />);
  expect(faz().props.value).toBe("90");
});
