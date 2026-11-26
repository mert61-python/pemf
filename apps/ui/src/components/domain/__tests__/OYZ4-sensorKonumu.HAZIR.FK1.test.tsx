// Author: mertaygn, cglrgrkn
/**
 * FK · K1 d2 (istem 58) — "Kabin sensörü (MLX)" konum formunda tezgâh planının HAZIR NOKTALARI.
 * SÖZLEŞME: canlı uç `hazir` listesi verirse form açılınca sırayla dokunulabilir noktalar çizilir (ad dile göre: TR / EN); dokununca sol /
 * ön / yükseklik (dile göre ondalık) ve not (= nokta adı) DOLAR, kayıt mevcut "Konumu kaydet" ile aynı gövdeyi gönderir. Liste yok / boş →
 * hiçbir şey çizilmez (form bugünküyle aynı). Yeni uç / şema YOK.
 * GERÇEK: KabinSensoruKarti, SensorKonumuFormu, katalog; sahte: apiClient + canlı veri bağlamı.
 */
import React from "react";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";

const mockApiGet = jest.fn();
const mockApiPost = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => mockApiGet(...a),
  apiPost: (...a: unknown[]) => mockApiPost(...a),
  apiDelete: jest.fn(),
  platformAlert: jest.fn(),
}));
let mockSnap: unknown = null;
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => ({ snapshot: mockSnap }) }));

import { KabinSensoruKarti } from "@/components/domain/KabinSensoruKarti";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };
const HAZIR = [
  { ad: { tr: "Kedi orta · karaciğer", en: "Cat orta · liver" }, sol_cm: 28.2, on_cm: 20, yukseklik_cm: 7.25 },
  { ad: { tr: "Kedi p1 · mesane", en: "Cat p1 · bladder" }, sol_cm: 13.3, on_cm: 25.9, yukseklik_cm: 7.25 },
];

beforeEach(() => {
  mockApiGet.mockReset();
  mockApiPost.mockReset();
  mockSnap = { coils: [{ id: 6, magneticMt: 0.8, measuredFields: ["magneticMt"] }], activeTreatment: { isActive: true } };
});
afterEach(async () => {
  mockSnap = null;
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

async function formAc(hazir: unknown) {
  mockApiGet.mockResolvedValue({ aktif: true, konum: null, ...(hazir === undefined ? {} : { hazir }) });
  const u = render(<KabinSensoruKarti />);
  await waitFor(() => expect(mockApiGet).toHaveBeenCalledWith("/session/sensor_konumu", null, { silent: true }));
  fireEvent.press(u.getByTestId("kabin-sensoru-konum-dugmesi"));
  return u;
}

it("KRİTİK hazır noktalar SIRAYLA çizilir; dokununca alanlar + not dolar, kayıt aynı gövdeyle (TR, ondalık virgül)", async () => {
  mockApiPost.mockResolvedValue({ status: "success" });
  const u = await formAc(HAZIR);
  expect(u.getByTestId("sensor-konumu-hazir")).toBeTruthy();
  expect(u.getByTestId("sensor-konumu-hazir-0")).toHaveTextContent("Kedi orta · karaciğer");
  expect(u.getByTestId("sensor-konumu-hazir-1")).toHaveTextContent("Kedi p1 · mesane");
  fireEvent.press(u.getByTestId("sensor-konumu-hazir-1"));
  expect(u.getByTestId("sensor-konumu-sol").props.value).toBe("13,3");
  expect(u.getByTestId("sensor-konumu-on").props.value).toBe("25,9");
  expect(u.getByTestId("sensor-konumu-yukseklik").props.value).toBe("7,25");
  expect(u.getByTestId("sensor-konumu-not").props.value).toBe("Kedi p1 · mesane");
  await act(async () => {
    fireEvent.press(u.getByTestId("sensor-konumu-kaydet"));
  });
  expect(mockApiPost).toHaveBeenCalledWith(
    "/session/sensor_konumu",
    { serbest: false, solCm: 13.3, onCm: 25.9, yukseklikCm: 7.25, notMetni: "Kedi p1 · mesane" },
    null,
    expect.anything(),
  );
});

it("KRİTİK EN: nokta adı İngilizce, ondalık nokta", async () => {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
  const u = await formAc(HAZIR);
  expect(u.getByTestId("sensor-konumu-hazir-0")).toHaveTextContent("Cat orta · liver");
  fireEvent.press(u.getByTestId("sensor-konumu-hazir-0"));
  expect(u.getByTestId("sensor-konumu-sol").props.value).toBe("28.2");
  expect(u.getByTestId("sensor-konumu-on").props.value).toBe("20");
  expect(u.getByTestId("sensor-konumu-not").props.value).toBe("Cat orta · liver");
});

it.each([[undefined], [[]]])("KARŞIT hazır liste yok / boş (%p) → hiçbir şey çizilmez", async (hazir) => {
  const u = await formAc(hazir);
  expect(u.getByTestId("sensor-konumu-formu")).toBeTruthy();
  expect(u.queryByTestId("sensor-konumu-hazir")).toBeNull();
});
