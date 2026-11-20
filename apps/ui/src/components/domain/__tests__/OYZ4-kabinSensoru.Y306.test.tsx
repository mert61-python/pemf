// Author: mertaygn, cglrgrkn
/**
 * Y306 (sahip 19-11, madde 6): TEK MLX sensörü var, kabinde GEZDİRİLİYOR — ama seans detayında "Alan (ölçülen)" bobin 6 satırına
 * yazılıyor, grafik efsanesi "Bobin 6" diyordu (kartın sensör kanalı). SÖZLEŞME: MLX bir bobinin değil KABİNİN sensörü →
 * "Kabin sensörü (MLX)" adıyla bobin satırlarından AYRI satır / kart + açıklama; kanal → sensör eşlemesi TEK sabit (bugün 6); eski
 * kayıtlar da yeni adla (veri göçü yok). Değer yalnız ölçülüyorsa (`measuredFields`) ve doğrulandıysa gösterilir. TR + EN.
 * GERÇEK: SessionDetailModal, KabinSensoruKarti, yardımcılar, katalog; sahte yalnız apiClient.apiGet ve canlı veri bağlamı.
 */
import React from "react";
import { act, render, waitFor, within } from "@testing-library/react-native";

const mockApiGet = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => mockApiGet(...a),
  apiPost: jest.fn(),
  platformAlert: jest.fn(),
}));
let mockSnap: unknown = null;
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => ({ snapshot: mockSnap }) }));

import { SessionDetailModal } from "@/components/domain/SessionDetailModal";
import { KabinSensoruKarti, kabinSensoruAlani } from "@/components/domain/KabinSensoruKarti";
import { KABIN_SENSORU_KANALI, bobinKartiVerisi, bobinOlcumAlanlari, kabinSensoruKanaliMi } from "@/utils/kabinSensoru";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };
const seans = { id: 9, patient_name: "Plaka 1", session_date: "2026-11-19", start_time: "18:07", end_time: "18:13", duration_minutes: 6,
  treatment_mode: "AI Pro · Petri Kuyu", session_status: "stopped" };
const kosu = (coil: number, field: number | null, sure = 60, ek: Record<string, unknown> = {}) => ({
  coil_id: coil, started_epoch: 1795107000, duration_seconds: sure, frequency_hz: 100, duty_percent: 30, intensity_mt: null,
  summary: { field_avg: field, temp_avg: null, temp_max: null, ...ek },
});

afterEach(async () => {
  mockSnap = null;
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

function metin(d: any): string {
  if (d == null || typeof d === "boolean") return "";
  if (typeof d === "string" || typeof d === "number") return String(d);
  if (Array.isArray(d)) return d.map(metin).join("");
  return (d.children || []).map(metin).join("");
}

async function detay(coil_runs: unknown[], sensor_samples: unknown[] = []) {
  mockApiGet.mockResolvedValue({ session: seans, coil_runs, sensor_samples });
  const u = render(<SessionDetailModal visible sessionId={9} onClose={() => {}} />);
  await waitFor(() => expect(u.queryAllByTestId(/^seans-bobin-satiri-/).length).toBeGreaterThan(0));
  return u;
}

it("KRİTİK seans detayı: kanal 6'nın alanı bobin 6 satırında '—', AYRI 'Kabin sensörü (MLX)' satırında (süre ağırlıklı) + açıklama", async () => {
  const u = await detay([kosu(1, null), kosu(6, 1.2, 60), kosu(6, 1.5, 120, { alan_notu: "÷5" })]);
  expect(u.getAllByTestId("seans-bobin-olculen-alan-6").map((x) => metin(x.props.children))).toEqual(["—", "—"]);
  expect(within(u.getByTestId("seans-kabin-sensoru-satiri")).getByText("Kabin sensörü (MLX)")).toBeTruthy();
  expect(metin(u.getByTestId("seans-kabin-sensoru-alan").props.children)).toBe("1.40 mT *"); // (1,2·60 + 1,5·120) / 180
  expect(metin(u.getByTestId("seans-kabin-sensoru-notu").props.children)).toBe(
    "Kabin sensörü (MLX): Tek sensör, kabinde taşınır — değer sensörün o anki konumundaki alandır, bobin değil.",
  );
});

it("KARŞIT: kabin kanalında alan ölçülmediyse kabin satırı ve notu YOK; başka bobinin alanı (÷5 yıldızı dahil) AYNEN", async () => {
  const y = await detay([kosu(1, 0.8, 60, { alan_notu: "÷5" }), kosu(6, 1.0, 0), kosu(6, 2.0, Number.NaN)]);
  expect(metin(y.getByTestId("seans-bobin-olculen-alan-1").props.children)).toBe("0.80 mT *");
  expect(metin(y.getByTestId("seans-kabin-sensoru-alan").props.children)).toBe("1.50 mT"); // süresiz koşular eşit ağırlık
  const u = await detay([kosu(1, 0.8), kosu(6, null)]);
  expect(u.queryByTestId("seans-kabin-sensoru-satiri")).toBeNull();
  expect(u.queryByTestId("seans-kabin-sensoru-notu")).toBeNull();
  expect(metin(u.getByTestId("seans-bobin-olculen-alan-1").props.children)).toBe("0.80 mT");
});

it("KRİTİK grafik efsanesi: kanal 6 'Kabin sensörü (MLX)', 'Bobin 6' YOK; EN 'Cabin sensor (MLX)'", async () => {
  const ornek = [
    { coil_id: "6", sample_ts: 1000, magnetic_field_mt: 1.35 },
    { coil_id: "6", sample_ts: 1060, magnetic_field_mt: 1.37 },
    { coil_id: "1", sample_ts: 1000, magnetic_field_mt: 0.5 }, // eski ESP kaydı / sanal kart: kabin dışı kanal "Bobin 1" kalır
  ];
  const u = await detay([kosu(6, 1.36)], ornek);
  await waitFor(() => expect(u.getByTestId("seans-alan-bolumu")).toBeTruthy());
  const bolum = within(u.getByTestId("seans-alan-bolumu"));
  expect(bolum.getByText("Kabin sensörü (MLX)")).toBeTruthy();
  expect(bolum.queryByText("Bobin 6")).toBeNull();
  expect(bolum.getByText("Bobin 1")).toBeTruthy();
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
  const e = await detay([kosu(6, 1.36)], ornek);
  await waitFor(() => expect(e.getByTestId("seans-alan-bolumu")).toBeTruthy());
  expect(within(e.getByTestId("seans-alan-bolumu")).getByText("Cabin sensor (MLX)")).toBeTruthy();
});

it("KRİTİK kabin sensörü kartı: ölçülen alan dile göre; ölçülmüyorsa / doğrulanamadıysa '—' (0 UYDURULMAZ)", async () => {
  mockSnap = { coils: [{ id: 6, magneticMt: 1.842, measuredFields: ["magneticMt"] }] };
  const u = render(<KabinSensoruKarti />);
  expect(u.getByTestId("kabin-sensoru-deger").props.children).toBe("1,84 mT");
  expect(u.getByText("Kabin sensörü (MLX)")).toBeTruthy();
  expect(u.getByText("Tek sensör, kabinde taşınır — değer sensörün o anki konumundaki alandır, bobin değil.")).toBeTruthy();
  mockSnap = { coils: [{ id: 6, magneticMt: 1.842, measuredFields: ["objectTemp"] }] };
  expect(render(<KabinSensoruKarti />).getByTestId("kabin-sensoru-deger").props.children).toBe("—");
  mockSnap = { coils: [{ id: 6, magneticMt: 1.842, measuredFields: ["magneticMt"], alanDogrulanamadi: true }] };
  const d = render(<KabinSensoruKarti />);
  expect(d.getByTestId("kabin-sensoru-deger").props.children).toBe("—");
  expect(d.getByText("sensör doğrulanamadı")).toBeTruthy();
  mockSnap = null;
  expect(render(<KabinSensoruKarti />).getByTestId("kabin-sensoru-deger").props.children).toBe("—");
  expect(kabinSensoruAlani([{ id: 6, magneticMt: Number.NaN, measuredFields: ["magneticMt"] } as never])).toBeNull();
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
  mockSnap = { coils: [{ id: 6, magneticMt: 1.842, measuredFields: ["magneticMt"] }] };
  const e = render(<KabinSensoruKarti />);
  expect(e.getByTestId("kabin-sensoru-deger").props.children).toBe("1.84 mT");
  expect(e.getByText("Cabin sensor (MLX)")).toBeTruthy();
});

it("tek sabit + bobin kartı yardımcıları: kabin kanalında alan bobinin ölçümünden çıkar, başka kanal AYNEN", () => {
  expect(KABIN_SENSORU_KANALI).toBe(6);
  expect([6, "6", 6.0].every(kabinSensoruKanaliMi)).toBe(true);
  expect([7, "7", null, undefined, "", "x"].some(kabinSensoruKanaliMi)).toBe(false);
  expect(bobinOlcumAlanlari(6, ["magneticMt", "objectTemp"])).toEqual(["objectTemp"]);
  expect(bobinOlcumAlanlari(6, undefined)).toEqual(["objectTemp", "ambientTemp", "currentA"]);
  const liste = ["magneticMt"];
  expect(bobinOlcumAlanlari(7, liste)).toBe(liste);
  const k6 = { id: 6, measuredFields: ["magneticMt", "objectTemp"], alanDogrulanamadi: true };
  expect(bobinKartiVerisi(k6)).toEqual({ id: 6, measuredFields: ["objectTemp"], alanDogrulanamadi: false });
  const k7 = { id: 7, measuredFields: ["magneticMt"], alanDogrulanamadi: true };
  expect(bobinKartiVerisi(k7)).toBe(k7);
});
