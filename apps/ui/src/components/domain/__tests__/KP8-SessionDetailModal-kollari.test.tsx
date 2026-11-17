/**
 * KP-8 · SessionDetailModal kalan dallar (KP3 / D6_24 düzeneği; sahte yalnız apiClient.apiGet — GERÇEK modal + katalog):
 *  - Yanıtta bobin çalışması / sensör örneği listesi YOKSA tablo boş, "sensör verisi yok" (çökmez).
 *  - Başlangıç saati yok ama bitiş varsa aralık "— – 10:20".
 *  - Bobin kimliği olmayan çalışma satırı "Bobin —" yazar (uydurma numara yok); bilinmeyen bobin numarası (palet dışı) gri renkle.
 *  - Modal kapanıp yanıt GEÇ gelirse durum yazılmaz (söküm sonrası yazım yok — hata yok).
 */
import React from "react";
import { act, render, waitFor } from "@testing-library/react-native";
import i18n from "i18next";

const mockApiGet = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => mockApiGet(...a),
  apiPost: jest.fn(),
  platformAlert: jest.fn(),
}));

import { SessionDetailModal } from "@/components/domain/SessionDetailModal";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
const seans = (id: number, ek: Record<string, unknown> = {}) => ({
  id, patient_name: "Mia", session_date: "2026-11-01", start_time: "10:00", end_time: "10:20", duration_minutes: 20,
  treatment_mode: "Manuel", session_status: "completed", ...ek,
});

beforeEach(() => mockApiGet.mockReset());

it("liste alanları yoksa tablo boş + 'sensör verisi yok'; başlangıç yoksa aralık '— – 10:20'", async () => {
  mockApiGet.mockResolvedValue({ session: seans(5, { start_time: "" }) });
  const u = render(<SessionDetailModal visible sessionId={5} onClose={() => {}} />);
  await waitFor(() => expect(u.getByText("Mia")).toBeTruthy());
  expect(u.getByText(T("seans.detay.sensorVerisiYok"))).toBeTruthy();
  expect(u.getByText(/— – 10:20/)).toBeTruthy();
});

it("kimliksiz çalışma satırı 'Bobin —'; palet dışı bobin numarası da çizilir", async () => {
  mockApiGet.mockResolvedValue({
    session: seans(6),
    coil_runs: [
      { started_epoch: 1000, duration_seconds: 60, hw_type: "stm32" },
      { coil_id: 42, duration_seconds: 30, hw_type: "stm32" },
    ],
    sensor_samples: [],
  });
  const u = render(<SessionDetailModal visible sessionId={6} onClose={() => {}} />);
  await waitFor(() => expect(u.getByTestId("seans-bobin-satiri-0")).toBeTruthy());
  expect(u.getByText(T("seans.detay.bobinNo", { no: "—" }))).toBeTruthy();
  expect(u.getByTestId("seans-bobin-satiri-42")).toBeTruthy();
});

it("modal yanıt gelmeden kapanırsa geç yanıt durum YAZMAZ (hata yok)", async () => {
  let coz!: (v: unknown) => void;
  mockApiGet.mockImplementation(() => new Promise((r) => { coz = r; }));
  const hata = jest.spyOn(console, "error").mockImplementation(() => {});
  try {
    const u = render(<SessionDetailModal visible sessionId={9} onClose={() => {}} />);
    await waitFor(() => expect(mockApiGet).toHaveBeenCalledWith("/history/9/details", null));
    u.rerender(<SessionDetailModal visible={false} sessionId={9} onClose={() => {}} />);
    await act(async () => { coz({ session: seans(9), coil_runs: [], sensor_samples: [] }); });
    expect(hata).not.toHaveBeenCalled();
  } finally {
    hata.mockRestore();
  }
});
