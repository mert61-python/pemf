// Author: mertaygn, cglrgrkn
/**
 * D1.76 · İG-5.83 · Y6 — canlı E barı HESAPLANMAYAN değeri sayı gibi göstermez ('—').
 *
 * Backend (servers/efield_live.py) E'yi şu durumlarda hesaplamaz ve `healthy/cancer/avg = null` gönderir:
 *   * ölçülen B modelin EĞİTİM aralığı dışında (`egitimAraligiDisi`) — model orada anlamsız sayı üretir,
 *   * hiçbir çalışan bobinde alan ölçülmüyor (`bOlculmuyor`, `achievedB_T = null`),
 *   * aralık okunamadı (`egitimAraligiBilinmiyor`).
 * Eski bar sayı olmayan değeri `0` yapıp "0.0000" çiziyordu — "ölçüldü, sıfır" diye okunur (Y6 ihlali).
 */
import React from "react";
import { render } from "@testing-library/react-native";

const mockLive: { snapshot: any } = { snapshot: null };
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => mockLive,
}));

import { EFieldBar } from "../EFieldBar";

const temel = {
  avg: null,
  healthy: null,
  cancer: null,
  activeCoils: 3,
  dutySum: 0.9,
  ts: Date.now() / 1000,
};

afterEach(() => {
  mockLive.snapshot = null;
});

it("KRİTİK (İG-5.83): B eğitim aralığı DIŞINDA → E '—', '0.0000' YOK, nedeni yazılır", () => {
  mockLive.snapshot = { eField: { ...temel, achievedB_T: 0.0246, egitimAraligiDisi: true } };
  const u = render(<EFieldBar />);
  expect(u.getAllByText("—")).toHaveLength(2);
  expect(u.queryByText("0.0000")).toBeNull();
  expect(u.getByText(/eğitim aralığı dışında/i)).toBeTruthy();
  expect(u.getByText(/B=24\.60 mT/)).toBeTruthy(); // ölçülen B şeffaf kalır
});

it("KRİTİK (D1.76 · Y6): alan ölçülmüyorsa E ve B '—', nedeni yazılır", () => {
  mockLive.snapshot = { eField: { ...temel, achievedB_T: null, bOlculmuyor: true } };
  const u = render(<EFieldBar />);
  expect(u.getAllByText("—")).toHaveLength(2);
  expect(u.queryByText("0.0000")).toBeNull();
  expect(u.getByText(/B=— /)).toBeTruthy();
  expect(u.getByText(/alan \(B\) ölçülmüyor/i)).toBeTruthy();
});

it("KARŞIT: hesaplanan E sayı olarak görünür, uyarı yok", () => {
  mockLive.snapshot = { eField: { ...temel, healthy: 0.02, cancer: 0.05, avg: 0.035, achievedB_T: 0.001 } };
  const u = render(<EFieldBar />);
  expect(u.getByText("0.0500")).toBeTruthy();
  expect(u.queryByText("—")).toBeNull();
  expect(u.queryByText(/eğitim aralığı dışında/i)).toBeNull();
});

it("KRİTİK ODK (istem 45): canlı E hâlâ eski vekil modelden → 'yaklaşık' olduğu ve dozun ODAK'tan okunacağı SÖYLENİR", () => {
  mockLive.snapshot = { eField: { ...temel, healthy: 0.02, cancer: 0.05, avg: 0.035, achievedB_T: 0.001 } };
  const u = render(<EFieldBar />);
  expect(u.getByTestId("efield-yaklasik").props.children).toBe(
    "Yaklaşık değer — eski vekil modelden, ODAK'a henüz bağlanmadı. Doz için onay ekranındaki ODAK değerlerine bakın.",
  );
});
