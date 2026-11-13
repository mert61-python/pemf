// Author: mertaygn, cglrgrkn
/**
 * ODK10 (istem 45 · sahip 13 Kasım 2026: petri için CST'de petri kabı + kuyu sıvısı benzetimi): petri seansında canlı E çubuğu E'yi KUYU
 * SIVISI İÇİNDE gösterir (`ortam: "kuyu"`) ve bunu söyler; havadaki (ortamsız) değer kuyu içindekinin ~190 katıydı. Kedi (ortam benzetimi
 * yok) "havada" etiketiyle kalır. Kuyu E'si mV/m düzeyinde → "0.0000" ("sıfır" diye okunur) YOK, 3 anlamlı basamak.
 */
import React from "react";
import { render } from "@testing-library/react-native";

const mockLive: { snapshot: any } = { snapshot: null };
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => mockLive,
}));

import { EFieldBar } from "../EFieldBar";

const temel = { activeCoils: 3, dutySum: 0.9, achievedB_T: 0.0008, ts: Date.now() / 1000, kaynak: "cst" };

afterEach(() => {
  mockLive.snapshot = null;
});

it("KRİTİK ODK10: petri (ortam kuyu) → 'kuyu sıvısı içinde' etiketi, 'havada' etiketi YOK", () => {
  mockLive.snapshot = { eField: { ...temel, healthy: 0.0021, cancer: 0.0034, avg: 0.00275, ortam: "kuyu" } };
  const u = render(<EFieldBar />);
  expect(u.getByTestId("efield-cst-kuyu").props.children).toBe(
    "Kuyu sıvısı içinde hesaplanan değer (ölçülen B + kuyu geometrisi; CST petri benzetimiyle doğrulandı). E doğrudan ölçülmedi.",
  );
  expect(u.queryByTestId("efield-cst")).toBeNull();
  expect(u.queryByTestId("efield-yaklasik")).toBeNull();
  expect(u.getByText("0.0034")).toBeTruthy();
});

it("KARŞIT ODK10: kedi (ortam hava / yok) → 'havada (ortamsız)' etiketi, kuyu etiketi YOK", () => {
  for (const ortam of ["hava", undefined, null]) {
    mockLive.snapshot = { eField: { ...temel, healthy: 0.2, cancer: 0.5, avg: 0.35, ortam } };
    const u = render(<EFieldBar />);
    expect(u.getByTestId("efield-cst").props.children).toBe(
      "Havada (ortamsız) hesaplanan değer — doku / tümör içindeki E çok daha düşüktür. E doğrudan ölçülmedi.",
    );
    expect(u.queryByTestId("efield-cst-kuyu")).toBeNull();
    u.unmount();
  }
});

it("KRİTİK ODK10: 0,001 V/m altı kuyu E'si '0.0000' DEĞİL — 3 anlamlı basamak; sıfır yine '0.0000'", () => {
  mockLive.snapshot = { eField: { ...temel, healthy: 0, cancer: 0.000512, avg: 0.000256, ortam: "kuyu" } };
  const u = render(<EFieldBar />);
  expect(u.getByText("0.000512")).toBeTruthy();
  expect(u.getByText("0.0000")).toBeTruthy(); // gerçek sıfır (çevre) — hesaplanan sıfır
});

it("YAPISAL ODK10: vekil (analiz bağlamı) ortam alanından ETKİLENMEZ — 'yaklaşık' kalır", () => {
  mockLive.snapshot = { eField: { ...temel, kaynak: undefined, healthy: 0.02, cancer: 0.05, avg: 0.035, ortam: "kuyu" } };
  const u = render(<EFieldBar />);
  expect(u.getByTestId("efield-yaklasik")).toBeTruthy();
  expect(u.queryByTestId("efield-cst-kuyu")).toBeNull();
});
