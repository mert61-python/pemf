/**
 * KP-3 C · SessionDetailModal kapsanmayan kolları — her test bir DAVRANIŞ iddiası (D6_24 düzeneği; sahte yalnız apiClient.apiGet):
 *  - Yanıt BAŞKA seansa aitse (kimlik eşleşmez — hızlı seans değişiminde geç gelen yanıt) o hastanın adı / notu GÖSTERİLMEZ, "bilgi yok"
 *    yazar (yanlış hasta sızıntısı yok).
 *  - Sıcaklık grafiği: tek ölçümlü bobin çizgi yerine NOKTA olarak çizilir; tümü aynı sıcaklıktaki seriler de çizilir (eksen ±1 °C
 *    açılır, sıfıra bölme yok); geçersiz (eksik / sonsuz) örnekler atlanır, hiç geçerli örnek yoksa "sensör verisi yok".
 * GERÇEK: SessionDetailModal + katalog.
 */
import React from "react";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import { Rect, Polyline, Text as SvgText } from "react-native-svg";
import i18n from "i18next";

const mockApiGet = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => mockApiGet(...a),
  apiPost: jest.fn(),
  platformAlert: jest.fn(),
}));

import { SessionDetailModal } from "@/components/domain/SessionDetailModal";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
const seans = (id: number, ad: string) => ({
  id, patient_name: ad, session_date: "2026-11-01", start_time: "10:00", end_time: "10:20", duration_minutes: 20,
  treatment_mode: "Manuel", session_status: "completed",
});

it("yanıt başka seansa aitse o hastanın adı GÖSTERİLMEZ, 'bilgi yok' yazar", async () => {
  mockApiGet.mockResolvedValue({ session: seans(99, "Başka-Hasta"), coil_runs: [], sensor_samples: [] });
  const u = render(<SessionDetailModal visible sessionId={7} onClose={() => {}} />);
  await waitFor(() => expect(mockApiGet).toHaveBeenCalledWith("/history/7/details", null));
  await waitFor(() => expect(u.getByText(T("seans.detay.bilgiYok"))).toBeTruthy());
  expect(u.queryByText("Başka-Hasta")).toBeNull();
});

it("tek ölçümlü bobin NOKTA olarak, sabit sıcaklıklı seri ±1 °C eksenle çizilir; geçersiz örnekler atlanır", async () => {
  mockApiGet.mockResolvedValue({
    session: seans(8, "Mia"), coil_runs: [],
    sensor_samples: [
      { coil_id: 6, sample_ts: 1000, temperature_c: 31 }, // tek nokta → işaret
      { coil_id: 7, sample_ts: 1000, temperature_c: 31 },
      { coil_id: 7, sample_ts: 1060, temperature_c: 31 }, // sabit seri
      { coil_id: 7, sample_ts: 1120, temperature_c: Number.POSITIVE_INFINITY }, // atlanır
      { coil_id: 5, sample_ts: undefined, temperature_c: 40 }, // atlanır
    ],
  });
  const u = render(<SessionDetailModal visible sessionId={8} onClose={() => {}} />);
  await waitFor(() => expect(u.getByTestId("seans-sicaklik-grafigi")).toBeTruthy());
  // grafik GENİŞLİK ÖLÇÜLÜNCE çizilir (S7 · 1:1 viewBox) → ölçüm olayı verilir
  await act(async () => { fireEvent(u.getByTestId("seans-sicaklik-grafigi"), "layout", { nativeEvent: { layout: { width: 600, height: 240 } } }); });
  const isaretler = u.UNSAFE_queryAllByType(Rect).filter((r) => r.props.width === 4 && r.props.height === 4);
  expect(isaretler).toHaveLength(1);
  expect(u.UNSAFE_queryAllByType(Polyline)).toHaveLength(1); // yalnız 2+ geçerli noktalı bobin 7 çizgi
  expect(u.queryByText(T("seans.detay.sensorVerisiYok"))).toBeNull();
  const eksen = u.UNSAFE_queryAllByType(SvgText).map((x) => String(([] as unknown[]).concat(x.props.children).join("")));
  expect(eksen).toEqual(expect.arrayContaining(["30.0", "32.0"])); // tümü 31 °C → eksen ±1 açıldı
});

it("hiç geçerli örnek yoksa 'sensör verisi yok'", async () => {
  mockApiGet.mockResolvedValue({
    session: seans(9, "Pamuk"), coil_runs: [],
    sensor_samples: [{ coil_id: 6, sample_ts: 1000, temperature_c: Number.NaN }],
  });
  const u = render(<SessionDetailModal visible sessionId={9} onClose={() => {}} />);
  await waitFor(() => expect(u.getByText(T("seans.detay.sensorVerisiYok"))).toBeTruthy());
});
