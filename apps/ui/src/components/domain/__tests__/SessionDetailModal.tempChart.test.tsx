// Author: mertaygn, cglrgrkn
/**
 * SEANS SICAKLIK GRAFİĞİ — ÖLÇÜLEN GENİŞLİK  [S7 adım 1 / ekranC-3, 2026-09-04 denetimi]
 * =====================================================================================
 * ÖLÇÜLEN DURUM: grafik `viewBox="0 0 720 260"` ile çiziliyor ve SVG `width="100%"` ile
 * geriliyordu. 360 px'lik telefonda tüm çizim 0,5 ölçekle küçülüyor, 11 px'lik eksen yazıları
 * ekranda 5-6 px'e düşüp OKUNMAZ oluyordu (hekim hangi bobinin kaç dereceye çıktığını göremiyor).
 *
 * SÖZLEŞME: SVG genişliği = ölçülen kap genişliği, viewBox aynı px (1:1 ölçek) → yazı boyutu
 * ekranda gerçek px. Ölçüm gelmeden grafik çizilmez (0 genişlikte NaN koordinat üretilmez).
 *
 * ⚠️ MUTASYON: sabit `width = 720` geri gelirse 2. vaka KIRILIR.
 */
import React from "react";
import { Svg } from "react-native-svg";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

const mockApiGet = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => mockApiGet(...a),
  apiPost: jest.fn(),
  platformAlert: jest.fn(),
}));

import { SessionDetailModal } from "../SessionDetailModal";

const SEANS = {
  session: { id: 7, started_epoch: 1_700_000_000, mode: "manual" },
  coil_runs: [
    {
      id: 1,
      coil_id: 1,
      started_epoch: 1_700_000_000,
      duration_seconds: 600,
      frequency_hz: 10,
      duty: 0.5,
      intensity_mt: 1.2,
      hardware: "stm",
    },
  ],
  sensor_samples: [
    { coil_id: 1, sample_ts: 1_700_000_000, temperature_c: 30.0 },
    { coil_id: 1, sample_ts: 1_700_000_300, temperature_c: 32.0 },
    { coil_id: 1, sample_ts: 1_700_000_600, temperature_c: 33.1 },
  ],
};

beforeEach(() => {
  mockApiGet.mockReset();
  mockApiGet.mockResolvedValue(SEANS);
});

/** Modalı aç, grafiği ölç ve SVG'yi döndür. */
async function ciz(genislik: number) {
  const u = render(<SessionDetailModal visible sessionId={7} onClose={() => {}} />);
  const kap = await waitFor(() => u.getByTestId("seans-sicaklik-grafigi"));
  fireEvent(kap, "layout", { nativeEvent: { layout: { width: genislik, height: 0 } } });
  return u;
}

describe("sıcaklık grafiği genişliği", () => {
  it("ölçüm gelmeden grafik çizilmez (NaN koordinat üretilmez)", async () => {
    const u = render(<SessionDetailModal visible sessionId={7} onClose={() => {}} />);
    await waitFor(() => u.getByTestId("seans-sicaklik-grafigi"));
    expect(u.UNSAFE_queryAllByType(Svg)).toHaveLength(0);
  });

  it("KRİTİK: SVG genişliği ÖLÇÜLEN kap genişliğidir (sabit 720 değil)", async () => {
    const u = await ciz(300);
    const svg = u.UNSAFE_getAllByType(Svg)[0];
    expect(svg.props.width).toBe(300);
    expect(String(svg.props.viewBox)).toContain("0 0 300");
    expect(String(svg.props.viewBox)).not.toContain("720");
  });

  it("kap genişleyince grafik de genişler (1:1 ölçek korunur)", async () => {
    const u = await ciz(300);
    fireEvent(u.getByTestId("seans-sicaklik-grafigi"), "layout", {
      nativeEvent: { layout: { width: 900, height: 0 } },
    });
    const svg = u.UNSAFE_getAllByType(Svg)[0];
    expect(svg.props.width).toBe(900);
    expect(String(svg.props.viewBox)).toContain("0 0 900");
  });

  it("1 px altı titreşim yeniden çizim tetiklemez", async () => {
    const u = await ciz(300);
    fireEvent(u.getByTestId("seans-sicaklik-grafigi"), "layout", {
      nativeEvent: { layout: { width: 300.4, height: 0 } },
    });
    expect(u.UNSAFE_getAllByType(Svg)[0].props.width).toBe(300);
  });
});
