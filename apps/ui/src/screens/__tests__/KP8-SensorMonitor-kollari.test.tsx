/**
 * KP-8 · SensorMonitorScreen kalan dallar (KP3-SensorMonitor-kollari düzeneği — canlı veri bağlamı girdi, grafik sahte):
 *  - Telemetri BAYATSA rozet "gecikmeli" der (CANLI demez) ve sarı tonda çizilir.
 *  - Ölçülen bobin kartı: alan ÖLÇÜLÜYORSA "sonda alanı" etiketiyle mT değeri, sıcaklık ölçülüyorsa °C; ölçülen 45 °C üstü KIRMIZI.
 *  - Alan sensörü ayarı doğrulanamadıysa değer yerine "—" ve NEDEN metni.
 */
let mockSnap: { coils?: Record<string, unknown>[] } = { coils: [] };
let mockBayat = false;
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: mockSnap, sensorHistory: {}, connectionQuality: mockBayat ? "stale" : "live", telemetryStale: mockBayat }),
}));
jest.mock("@/components/visual/RealtimeChart", () => ({ RealtimeChart: () => null }));

import React from "react";
import { StyleSheet } from "react-native";
import { render } from "@testing-library/react-native";
import i18n from "i18next";
import { SensorMonitorScreen } from "@/screens/SensorMonitorScreen";
import { alanDogrulanamadiMetni } from "@/utils/olculenAlan";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
const bobin = (id: number, ek: Record<string, unknown> = {}) => ({
  id, connected: true, running: false, magneticMt: 0, objectTemp: 0, currentA: 0, frequencyHz: 0, ...ek,
});

beforeEach(() => { mockBayat = false; });

it("telemetri bayatsa rozet 'gecikmeli' (CANLI değil), sarı ton", () => {
  mockBayat = true;
  mockSnap = { coils: [] };
  const u = render(<SensorMonitorScreen />);
  const rozet = u.getByText(T("sensor.gecikmeli"));
  expect(StyleSheet.flatten(rozet.props.style).color).toBe("#f59e0b");
  expect(u.queryByText(T("sensor.rozetCanli"))).toBeNull();
});

it("ölçülen alan 'sonda alanı' + mT, ölçülen 45 °C üstü kırmızı; doğrulanamayan alan '—' + neden", () => {
  mockSnap = {
    coils: [
      bobin(6, { magneticMt: 1.842, objectTemp: 50, measuredFields: ["magneticMt", "objectTemp"] }),
      bobin(7, { magneticMt: 9.9, measuredFields: ["magneticMt"], alanDogrulanamadi: true }),
    ],
  };
  const u = render(<SensorMonitorScreen />);
  // Y306 (madde 6): MLX alanı bobin 6 kartında DEĞİL — ayrı kabin sensörü kartında (ondalık dile göre).
  expect(u.getByTestId("kabin-sensoru-deger").props.children).toBe("1,84 mT");
  expect(u.queryByText("1.84 mT")).toBeNull();
  expect(u.queryAllByText(T("sensor.alanSonda")).length).toBe(0);
  const sicak = u.getByText("50.0 °C");
  expect(StyleSheet.flatten(sicak.props.style).color).toBe("#ef4444");
  expect(u.queryByText("9.90 mT")).toBeNull();
  expect(u.getByText(alanDogrulanamadiMetni())).toBeTruthy();
});
