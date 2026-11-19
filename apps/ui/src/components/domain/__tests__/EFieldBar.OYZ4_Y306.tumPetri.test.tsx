// Author: mertaygn, cglrgrkn
/**
 * Y306 (sahip 19-11 tezgâh denemesi 4c): "Canlı E-Alanı" kutusu "Tüm petri" hedefinde de "Hedef kuyu" diyordu ve değer BİRİMSİZDİ
 * ("0.0027"). SÖZLEŞME: hedef türüne göre etiket — `kip: "TUM_PETRI"` → "Tüm kuyular (ort.)" (tüm kuyuların ortalaması; çevre kuyu
 * yoksa çevre satırı ÇİZİLMEZ), `KUYUCUK` → "Hedef kuyu" + "Çevre kuyular" AYNEN; değerin yanında birim "V/m" (hesap yoksa '—', birim
 * yok); ondalık dile göre. TR + EN.
 */
import React from "react";
import { act, render } from "@testing-library/react-native";

const mockLive: { snapshot: any } = { snapshot: null };
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => mockLive,
}));

import { EFieldBar } from "../EFieldBar";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };
const temel = { activeCoils: 7, dutySum: 2.1, achievedB_T: 0.00132, ts: Date.now() / 1000, kaynak: "cst", ortam: "kuyu" };

afterEach(async () => {
  mockLive.snapshot = null;
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

it("KRİTİK: Tüm petri → 'Tüm kuyular (ort.)', 'Hedef kuyu' YOK; değer V/m birimli; çevre kuyu yoksa çevre satırı YOK", () => {
  mockLive.snapshot = { eField: { ...temel, kip: "TUM_PETRI", cancer: 0.0027, healthy: null, avg: 0.0027, ts: Date.now() / 1000 } };
  const u = render(<EFieldBar />);
  expect(u.getByText("Tüm kuyular (ort.)")).toBeTruthy();
  expect(u.queryByText("Hedef kuyu")).toBeNull();
  expect(u.queryByText("Çevre kuyular")).toBeNull();
  expect(u.getByText("0,0027")).toBeTruthy();
  expect(u.getAllByTestId("efield-birim").map((x) => x.props.children)).toEqual(["V/m"]);
  expect(u.queryByLabelText("Tüm kuyular (ort.) alan 0,0027 V/m")).not.toBeNull();
});

it("KARŞIT: Kuyucuk → 'Hedef kuyu' + 'Çevre kuyular' AYNEN, ikisi de birimli", () => {
  mockLive.snapshot = { eField: { ...temel, kip: "KUYUCUK", cancer: 0.0034, healthy: 0.0021, avg: 0.00275, ts: Date.now() / 1000 } };
  const u = render(<EFieldBar />);
  expect(u.getByText("Hedef kuyu")).toBeTruthy();
  expect(u.getByText("Çevre kuyular")).toBeTruthy();
  expect(u.queryByText("Tüm kuyular (ort.)")).toBeNull();
  expect(u.getAllByTestId("efield-birim")).toHaveLength(2);
});

it("Tüm petri'de çevre DEĞERİ varsa satır kalır; hesap yoksa ('—') birim yazılmaz", () => {
  mockLive.snapshot = { eField: { ...temel, kip: "TUM_PETRI", cancer: null, healthy: 0.001, avg: null, ts: Date.now() / 1000 } };
  const u = render(<EFieldBar />);
  expect(u.getByText("Çevre kuyular")).toBeTruthy();
  expect(u.getAllByTestId("efield-birim")).toHaveLength(1); // yalnız çevre (sayı); hedef '—'
  expect(u.queryByLabelText("Tüm kuyular (ort.) alan —")).not.toBeNull();
});

it("EN: 'All wells (avg.)', ondalık NOKTA, birim V/m", async () => {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
  mockLive.snapshot = { eField: { ...temel, kip: "TUM_PETRI", cancer: 0.0027, healthy: null, avg: 0.0027, ts: Date.now() / 1000 } };
  const u = render(<EFieldBar />);
  expect(u.getByText("All wells (avg.)")).toBeTruthy();
  expect(u.getByText("0.0027")).toBeTruthy();
  expect(u.getAllByTestId("efield-birim").map((x) => x.props.children)).toEqual(["V/m"]);
});

it("Y306 biçim kolları: ≥ 1 V/m 3 basamak virgüllü, Σduty yoksa '—', aralıksız duty uyarısı", () => {
  mockLive.snapshot = {
    eField: { ...temel, kaynak: undefined, ortam: null, kip: null, cancer: 1.2345, healthy: 0.5, avg: 0.86, dutySum: Number.NaN, dutyEgitimAraligiDisi: true, ts: Date.now() / 1000 },
  };
  const u = render(<EFieldBar />);
  expect(u.getByText("1,235")).toBeTruthy();
  expect(u.getByText(/Σduty=—/)).toBeTruthy();
  expect(u.getByTestId("efield-duty-araligi-disi").props.children).toBe("⚠️ Σduty eğitim aralığı dışı — güvenilmez");
});
