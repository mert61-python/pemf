// Author: mertaygn, cglrgrkn
/**
 * YS2 b · B6 (YG0 25-11): Seans Detayı'nda "Bu seansın CSV'si" → `/history/{id}/coil_runs.csv` (`downloadFileWithAuth`; Y308 dilimleri).
 * Bildirim üst ekrandan (prop) gelir — modal toast sağlayıcısına bağlı DEĞİL (sağlayıcısız çizilen ekran düşmez). TR + EN etiket.
 * YS2 d · B7: kabin sensörü konumu en çok 2 ondalık, sondaki sıfır yok, ayırıcı dilde (0,75 → "0,75"; eskiden "0,8").
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});

let mockDetay: unknown = null;
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => mockDetay),
  apiPost: jest.fn(async () => ({ status: "success" })),
  authHeaders: jest.fn(() => ({})),
}));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" } }));
const mockIndir = jest.fn();
jest.mock("@/services/dosyaIndir", () => ({ downloadFileWithAuth: (...a: unknown[]) => mockIndir(...a) }));

import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import i18n from "i18next";
import React from "react";

import { SessionDetailModal } from "@/components/domain/SessionDetailModal";
import { konumOzeti } from "@/components/domain/KabinSensoruKarti";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };

afterEach(async () => {
  mockIndir.mockReset();
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});
async function enYap() {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
}

const DETAY = {
  session: {
    id: 42,
    patient_name: "Petri1",
    session_date: "2026-11-25",
    start_time: "13:27",
    end_time: "13:32",
    duration_minutes: 5,
    treatment_mode: "Manuel",
    target_condition: "",
    operator_name: "Dr. A",
    session_status: "completed",
    patient_notes: "",
  },
  coil_runs: [],
  sensor_samples: [],
};

async function ac() {
  mockDetay = DETAY;
  const u = render(<SessionDetailModal visible sessionId={42} onClose={() => {}} />);
  await waitFor(() => expect(u.getAllByText(/Petri1/).length).toBeGreaterThan(0));
  return u;
}

describe("Seans Detayı · Bu seansın CSV'si (B6)", () => {
  it("TR: düğme görünür; basınca bu seansın coil_runs.csv'si indirilir (toast sağlayıcısı olmadan düşmez)", async () => {
    const u = await ac();
    const d = u.getByTestId("seans-detay-csv");
    expect(u.getByText("Bu seansın CSV'si")).toBeTruthy();
    expect(d.props.accessibilityLabel).toBe("Bu seansın bobin ve konum dilimi tablosunu CSV olarak indir");
    fireEvent.press(d);
    expect(mockIndir).toHaveBeenCalledTimes(1);
    const [url, ad] = mockIndir.mock.calls[0];
    expect(url).toBe("http://127.0.0.1:8000/api/history/42/coil_runs.csv");
    expect(ad).toBe("PEMF_Session_42_Coils.csv");
  });

  it("üst ekranın bildirimi indirme sonucuna geçer (masaüstünde 'kaydedildi' / hata söylenir)", async () => {
    mockDetay = DETAY;
    const bildir = jest.fn();
    const u = render(<SessionDetailModal visible sessionId={42} onClose={() => {}} bildir={bildir} />);
    await waitFor(() => expect(u.getAllByText(/Petri1/).length).toBeGreaterThan(0));
    fireEvent.press(u.getByTestId("seans-detay-csv"));
    expect(mockIndir.mock.calls[0][2]).toBe(bildir);
  });

  it("EN: etiket İngilizce", async () => {
    await enYap();
    const u = await ac();
    expect(u.getByText("This session's CSV")).toBeTruthy();
    expect(u.getByTestId("seans-detay-csv").props.accessibilityLabel).toBe(
      "Download this session's coil and position-segment table as CSV",
    );
  });

  it("detay yüklenmeden (seans yok) düğme ÇİZİLMEZ", async () => {
    mockDetay = null;
    const u = render(<SessionDetailModal visible sessionId={42} onClose={() => {}} />);
    await waitFor(() => expect(u.queryByText(i18n.t("seans.detay.yuklenemedi") as string)).toBeTruthy());
    expect(u.queryByTestId("seans-detay-csv")).toBeNull();
  });
});

describe("konumOzeti (B7)", () => {
  const k = (sol: number, on: number, y: number) => ({
    id: 1, zaman_epoch: 0, serbest: false, sol_cm: sol, on_cm: on, yukseklik_cm: y, not_metni: "",
  });
  it("TR: 0,75 korunur, 0,80 → 0,8, tam sayı ondalıksız", () => {
    const m = konumOzeti(i18n.t, k(35, 9, 0.75));
    expect(m).toContain("0,75");
    expect(m).not.toContain("0,8 ");
    expect(konumOzeti(i18n.t, k(35.0, 9.8, 0.8))).toContain("9,8");
    expect(konumOzeti(i18n.t, k(35.0, 9, 0.8))).toMatch(/35\b/);
    expect(konumOzeti(i18n.t, k(35.0, 9, 0.8))).not.toMatch(/35[.,]/);
  });
  it("EN: nokta ayırıcı", async () => {
    await enYap();
    expect(konumOzeti(i18n.t, k(35, 9, 0.75))).toContain("0.75");
  });
});
