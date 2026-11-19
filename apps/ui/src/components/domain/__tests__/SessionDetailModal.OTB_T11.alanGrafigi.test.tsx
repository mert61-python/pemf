// Author: mertaygn, cglrgrkn
/**
 * OTB T-11 (sahip 19-11 "bu yayına girsin"): seans detayında MANYETİK ALAN (MLX) grafiği — sıcaklık grafiğiyle AYNI desen: bobin kanalı
 * başına dakika ortalaması tepe |B| (mT), eksen "mT" ve 2 basamak; ölçülmeyen dakika (NULL) ÇİZİLMEZ (0 diye uydurulmaz); veri yoksa
 * neden söylenir; MLX ofset kuralı ve "sensör noktası, numunedeki doz değil" notu AÇIK. Sıcaklık grafiği AYNEN. TR + EN.
 * GERÇEK: SessionDetailModal + katalog; sahte yalnız apiClient.apiGet (D6_24 düzeneği).
 */
import React from "react";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import { Polyline, Text as SvgText } from "react-native-svg";
import i18n from "i18next";

const mockApiGet = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => mockApiGet(...a),
  apiPost: jest.fn(),
  platformAlert: jest.fn(),
}));

import { SessionDetailModal } from "@/components/domain/SessionDetailModal";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };
const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
const seans = (id: number) => ({
  id, patient_name: "Plaka 1", session_date: "2026-11-19", start_time: "12:58", end_time: "13:01", duration_minutes: 3,
  treatment_mode: "AI Pro · Petri Kuyu", session_status: "stopped",
});

afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

async function ac(sensor_samples: unknown[]) {
  mockApiGet.mockResolvedValue({ session: seans(36), coil_runs: [], sensor_samples });
  const u = render(<SessionDetailModal visible sessionId={36} onClose={() => {}} />);
  await waitFor(() => expect(mockApiGet).toHaveBeenCalledWith("/history/36/details", null));
  await waitFor(() => expect(u.getByTestId("seans-alan-bolumu")).toBeTruthy());
  return u;
}

it("KRİTİK T-11: MLX alanı bobin başına ÇİZİLİR (mT ekseni, 2 basamak); NULL dakika atlanır; not AÇIK", async () => {
  const u = await ac([
    { coil_id: 1, sample_ts: 1000, magnetic_field_mt: 1.12, temperature_c: null },
    { coil_id: 1, sample_ts: 1060, magnetic_field_mt: 1.18 },
    { coil_id: 1, sample_ts: 1120, magnetic_field_mt: null }, // ölçülmedi → çizilmez
    { coil_id: 4, sample_ts: 1000, magnetic_field_mt: 0.4 },
    { coil_id: 4, sample_ts: 1060, magnetic_field_mt: 0.42 },
  ]);
  const g = u.getByTestId("seans-alan-grafigi");
  await act(async () => { fireEvent(g, "layout", { nativeEvent: { layout: { width: 600, height: 240 } } }); });
  expect(u.UNSAFE_queryAllByType(Polyline)).toHaveLength(2);
  const eksen = u.UNSAFE_queryAllByType(SvgText).map((x) => String(([] as unknown[]).concat(x.props.children).join("")));
  expect(eksen).toEqual(expect.arrayContaining(["mT", "1.18", "0.40"]));
  expect(JSON.stringify(u.getByTestId("seans-alan-notu").props.children)).toMatch(/ofset/);
  // sıcaklık ölçümü yok → sıcaklık bölümü kendi "veri yok" metni (AYNEN)
  expect(u.getByText(T("seans.detay.sensorVerisiYok"))).toBeTruthy();
});

it("T-11: alan ölçümü HİÇ yoksa neden söylenir, grafik çizilmez", async () => {
  const u = await ac([{ coil_id: 6, sample_ts: 1000, temperature_c: 31, magnetic_field_mt: null }]);
  expect(u.queryByTestId("seans-alan-grafigi")).toBeNull();
  expect(u.getByText(T("seans.detay.alanVerisiYok"))).toBeTruthy();
  expect(u.getByTestId("seans-sicaklik-grafigi")).toBeTruthy(); // sıcaklık grafiği etkilenmedi
});

it("EN: alan grafiği başlığı / notu İngilizce", async () => {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
  const u = await ac([{ coil_id: 1, sample_ts: 1000, magnetic_field_mt: 1.1 }]);
  const m = JSON.stringify(u.toJSON());
  expect(m).toContain("Magnetic Field Chart (MLX)");
  expect(JSON.stringify(u.getByTestId("seans-alan-notu").props.children)).not.toMatch(/[çğıöşüÇĞİÖŞÜ]/);
});
