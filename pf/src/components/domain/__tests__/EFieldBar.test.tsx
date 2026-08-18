// Author: mertaygn, cglrgrkn
/**
 * CANLI E-ALANI BARI (2026-08-06) — yanlış güvence vermeme kuralları.
 *
 * Bar tıbbi bir gösterge: operatör buna bakıp "alan uygulanıyor" diye karar veriyor.
 * Bu yüzden kilitlenen davranışlar YOKLUK tarafında:
 *   * veri yoksa bar HİÇ çıkmaz (uydurma/boş bar gösterme),
 *   * veri bayatsa "canlı" DEMEZ,
 *   * bobin durmuşsa bunu açıkça söyler.
 */
import React from "react";
import { render } from "@testing-library/react-native";

const mockLive: { snapshot: any } = { snapshot: null };
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => mockLive,
}));

import { EFieldBar } from "../EFieldBar";

const efield = (over: Partial<Record<string, number>> = {}) => ({
  healthy: 0.02,
  cancer: 0.05,
  avg: 0.035,
  activeCoils: 5,
  achievedB_T: 0.0025,
  dutySum: 1.5,
  ts: Date.now() / 1000,
  ...over,
});

afterEach(() => {
  mockLive.snapshot = null;
});

describe("EFieldBar", () => {
  it("snapshot yokken HİÇBİR ŞEY render etmez", () => {
    mockLive.snapshot = null;
    const { toJSON } = render(<EFieldBar />);
    expect(toJSON()).toBeNull();
  });

  it("eField null iken bar ÇIKMAZ (analiz yapılmamış / seans pasif)", () => {
    mockLive.snapshot = { eField: null, coils: [] };
    const { toJSON } = render(<EFieldBar />);
    expect(toJSON()).toBeNull();
  });

  it("veri varken tümör ve sağlıklı değerlerini gösterir", () => {
    mockLive.snapshot = { eField: efield() };
    const { getByText, queryByText } = render(<EFieldBar />);
    expect(getByText("Tümör")).toBeTruthy();
    expect(getByText("Sağlıklı")).toBeTruthy();
    expect(getByText("0.0500")).toBeTruthy();   // cancer
    expect(getByText("0.0200")).toBeTruthy();   // healthy
    expect(queryByText("duraklandı")).toBeNull();
  });

  it("taze veride 'canlı' rozeti gösterir", () => {
    mockLive.snapshot = { eField: efield() };
    const { getByText } = render(<EFieldBar />);
    expect(getByText("● canlı")).toBeTruthy();
  });

  it("BAYAT veride 'canlı' DEMEZ — donmuş sayı canlı sanılmasın", () => {
    mockLive.snapshot = { eField: efield({ ts: Date.now() / 1000 - 30 }) };
    const { getByText, queryByText } = render(<EFieldBar />);
    expect(getByText("duraklandı")).toBeTruthy();
    expect(queryByText("● canlı")).toBeNull();
  });

  it("bobinler durunca bunu AÇIKÇA yazar", () => {
    mockLive.snapshot = { eField: efield({ activeCoils: 0, cancer: 0, healthy: 0 }) };
    const { getByText } = render(<EFieldBar />);
    expect(getByText("Bobinler durdu — alan üretilmiyor.")).toBeTruthy();
  });

  it("canlı model girdilerini şeffaf gösterir (B ve Σduty)", () => {
    mockLive.snapshot = { eField: efield() };
    const { getByText } = render(<EFieldBar />);
    expect(getByText("5 bobin · B=2.50 mT · Σduty=1.50")).toBeTruthy();
  });

  it("bozuk sayıda ÇÖKMEZ (NaN/undefined → 0)", () => {
    mockLive.snapshot = { eField: { ...efield(), cancer: NaN, healthy: undefined } };
    const { getAllByText, getByText } = render(<EFieldBar />);
    // İKİ satır da 0.0000 gösterir (bozuk değer sessizce büyük bir sayıya dönüşmez).
    expect(getAllByText("0.0000")).toHaveLength(2);
    expect(getByText("Tümör")).toBeTruthy();   // bileşen ayakta, çökmedi
  });
});
