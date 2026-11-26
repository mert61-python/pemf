/**
 * KP-3 C · SensorMonitorScreen kapsanmayan kolları — her test bir DAVRANIŞ iddiası:
 *  - Anlık görüntüde bobin listesi yokken 7 STM bobininin çipi yine çizilir (ekran boş kalmaz).
 *  - Bobin çipi grafikten o bobini ÇIKARIR, ikinci basış geri ekler; mT / °C eksen çipleri grafiğe iletilir.
 *  - Grafik genişlik ölçülmeden çizilmez.
 * SAHTE: canlı veri bağlamı (girdi) · RealtimeChart (aldığı props kaydedilir).
 */
let mockSnap: { coils: { id: number; connected?: boolean; running?: boolean }[] } = { coils: [] };
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: mockSnap, sensorHistory: {}, connectionQuality: "live", telemetryStale: false }),
}));
type Pencere = { tip: string; sn?: number; bas?: number; son?: number };
const mockGrafik: { visibleCoils: Set<number>; showMagnetic?: boolean; showTemp?: boolean; pencere?: Pencere; onAralikSec?: (bas: number, son: number) => void }[] = [];
jest.mock("@/components/visual/RealtimeChart", () => ({
  RealtimeChart: (p: { visibleCoils: Set<number>; showMagnetic?: boolean; showTemp?: boolean; pencere?: Pencere; onAralikSec?: (bas: number, son: number) => void }) => { mockGrafik.push(p); return null; },
}));

import React from "react";
import { View } from "react-native";
import { act, fireEvent, render } from "@testing-library/react-native";
import i18n from "i18next";
import { SensorMonitorScreen } from "@/screens/SensorMonitorScreen";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
const son = () => mockGrafik[mockGrafik.length - 1];
async function olc(u: ReturnType<typeof render>) {
  const kutular = u.UNSAFE_getAllByType(View).filter((v) => typeof v.props.onLayout === "function");
  await act(async () => { for (const k of kutular) fireEvent(k, "layout", { nativeEvent: { layout: { width: 700, height: 300 } } }); });
}

beforeEach(() => { mockGrafik.length = 0; });

it("bobin listesi yokken 7 STM bobini çipi; grafik ölçümden önce çizilmez", async () => {
  mockSnap = { coils: [] };
  const u = render(<SensorMonitorScreen />);
  for (let id = 1; id <= 7; id++) expect(u.getByLabelText(T("sensor.grafikGosterGizle", { id }))).toBeTruthy();
  expect(u.queryByLabelText(T("sensor.grafikGosterGizle", { id: 8 }))).toBeNull();
  expect(mockGrafik).toHaveLength(0);
  await olc(u);
  expect(mockGrafik.length).toBeGreaterThan(0);
});

it("bobin çipi grafikten çıkarır / geri ekler; eksen çipleri grafiğe iletilir", async () => {
  mockSnap = { coils: [1, 2, 3, 4, 5, 6, 7].map((id) => ({ id, connected: true })) };
  const u = render(<SensorMonitorScreen />);
  await olc(u);
  expect(son().visibleCoils.has(3)).toBe(true);
  await act(async () => { fireEvent.press(u.getByLabelText(T("sensor.grafikGosterGizle", { id: 3 }))); });
  expect(son().visibleCoils.has(3)).toBe(false);
  await act(async () => { fireEvent.press(u.getByLabelText(T("sensor.grafikGosterGizle", { id: 3 }))); });
  expect(son().visibleCoils.has(3)).toBe(true);
  expect([son().showMagnetic, son().showTemp]).toEqual([true, true]);
  await act(async () => { fireEvent.press(u.getByText(T("sensor.manyetik"))); });
  expect(son().showMagnetic).toBe(false);
  await act(async () => { fireEvent.press(u.getByText(T("sensor.sicaklik"))); });
  expect(son().showTemp).toBe(false);
});

it("KP-5 C9 · ZG-1: zaman penceresi çipleri grafiğe pencereyi iletir; grafikte seçilen aralık 'seçili' olur, 'canlıya dön' tümüne", async () => {
  mockSnap = { coils: [] };
  const u = render(<SensorMonitorScreen />);
  await olc(u);
  expect(son().pencere).toEqual({ tip: "tumu" });
  for (const [kimlik, sn] of [["zaman-600", 600], ["zaman-120", 120], ["zaman-30", 30]] as const) {
    await act(async () => { fireEvent.press(u.getByTestId(kimlik)); });
    expect(son().pencere).toEqual({ tip: "son", sn });
  }
  await act(async () => { fireEvent.press(u.getByTestId("zaman-tumu")); });
  expect(son().pencere).toEqual({ tip: "tumu" });
  expect(u.queryByTestId("zaman-secili")).toBeNull();
  await act(async () => { son().onAralikSec!(1000, 1060); });
  expect(son().pencere).toEqual({ tip: "sabit", bas: 1000, son: 1060 });
  expect(u.getByTestId("zaman-secili")).toBeTruthy();
  await act(async () => { fireEvent.press(u.getByTestId("zaman-canli")); });
  expect(son().pencere).toEqual({ tip: "tumu" });
  expect(u.queryByTestId("zaman-secili")).toBeNull();
});
