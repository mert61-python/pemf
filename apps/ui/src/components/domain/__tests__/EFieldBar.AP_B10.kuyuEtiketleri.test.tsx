// Author: mertaygn, cglrgrkn
/**
 * AP-15 (istem 48 · B10): petri ODAK seansında canlı E çubuğunun iki satırı HEDEF KUYU ve ÇEVRE KUYULAR'dır (`ortam: "kuyu"`) — "Tümör /
 * Sağlıklı" yanıltıcıydı (petride sınıf değil konum). Kedi / vekil bağlamında eski etiketler kalır. Düzen `EFieldBar.ODK10…` ile aynı.
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

it("KRİTİK AP-15: petri (ortam kuyu) → 'Hedef kuyu' / 'Çevre kuyular'; 'Tümör' / 'Sağlıklı' YOK", () => {
  mockLive.snapshot = { eField: { ...temel, healthy: 0.0021, cancer: 0.0034, avg: 0.00275, ortam: "kuyu" } };
  const u = render(<EFieldBar />);
  expect(u.getByText("Hedef kuyu")).toBeTruthy();
  expect(u.getByText("Çevre kuyular")).toBeTruthy();
  expect(u.queryByText("Tümör")).toBeNull();
  expect(u.queryByText("Sağlıklı")).toBeNull();
});

it("KARŞIT AP-15: kedi / hava → eski etiketler", () => {
  mockLive.snapshot = { eField: { ...temel, healthy: 0.2, cancer: 0.5, avg: 0.35, ortam: "hava" } };
  const u = render(<EFieldBar />);
  expect(u.getByText("Tümör")).toBeTruthy();
  expect(u.getByText("Sağlıklı")).toBeTruthy();
});
