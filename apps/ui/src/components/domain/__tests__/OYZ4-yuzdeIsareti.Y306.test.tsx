// Author: mertaygn, cglrgrkn
/**
 * Y306 (sahip 19-11, OTB [SAHİBE] 3): İngilizce seans detayında bobin koşusunun duty'si "%50" yazıyordu (Türkçe sıra). SÖZLEŞME: yüzde
 * işaretinin yeri DİLE GÖRE — TR "%50", EN "50%" (katalog `ai.ortak.yuzde`); canlı kartın AI Pro duty temsili (`canliYogunluk`) da aynı.
 * GERÇEK: SessionDetailModal + katalog; sahte yalnız apiClient.apiGet (T-11 düzeneği).
 */
import React from "react";
import { act, render, waitFor } from "@testing-library/react-native";

const mockApiGet = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => mockApiGet(...a),
  apiPost: jest.fn(),
  platformAlert: jest.fn(),
}));

import { SessionDetailModal } from "@/components/domain/SessionDetailModal";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";
import { canliYogunluk } from "@/utils/yogunlukGosterimi";

const depo = { setItem: async () => undefined };
const seans = {
  id: 41, patient_name: "Plaka 1", session_date: "2026-11-19", start_time: "18:07", end_time: "18:13", duration_minutes: 6,
  treatment_mode: "AI Pro · Petri Kuyu", session_status: "completed",
};
const kosu = { coil_id: 1, started_epoch: 1795107000, duration_seconds: 357, frequency_hz: 100, duty_percent: 50, intensity_mt: null };

afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

async function dil(d: "tr" | "en") {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec(d, depo);
  });
}

async function ac() {
  mockApiGet.mockResolvedValue({ session: seans, coil_runs: [kosu], sensor_samples: [] });
  const u = render(<SessionDetailModal visible sessionId={41} onClose={() => {}} />);
  await waitFor(() => expect(mockApiGet).toHaveBeenCalledWith("/history/41/details", null));
  await waitFor(() => expect(u.queryAllByText(/50/).length).toBeGreaterThan(0));
  return u;
}

it("KRİTİK EN: seans detayında bobin duty'si '50%' (yüzde işareti SONDA), '%50' YOK", async () => {
  await dil("en");
  const u = await ac();
  expect(u.queryByText("50%")).not.toBeNull();
  expect(u.queryByText("%50")).toBeNull();
});

it("KARŞIT TR: '%50' AYNEN", async () => {
  await dil("tr");
  const u = await ac();
  expect(u.queryByText("%50")).not.toBeNull();
  expect(u.queryByText("50%")).toBeNull();
});

it("canlı kart AI Pro duty temsili dile göre (TR %36 · EN 36%)", async () => {
  await dil("tr");
  expect(canliYogunluk({ dutyTemsilYuzde: 36 }).deger).toBe("%36");
  await dil("en");
  expect(canliYogunluk({ dutyTemsilYuzde: 36 }).deger).toBe("36%");
});
