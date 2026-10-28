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
import { act, render } from "@testing-library/react-native";

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
    // D6.25 (B-6.16): yaş verinin ALINIŞINDAN ölçülür (sunucu damgası yerel saatle karşılaştırılmaz) → "bayat" = 30 sn boyunca YENİ
    // hesap gelmedi. Kapı: EFieldBar.D6_25.alinisTazeligi.test.tsx (GERÇEK LiveDataProvider + saat kayması).
    jest.useFakeTimers();
    try {
      mockLive.snapshot = { eField: efield() };
      const { getByText, queryByText } = render(<EFieldBar />);
      expect(getByText("● canlı")).toBeTruthy(); // ARA: alındığı an canlı
      act(() => { jest.advanceTimersByTime(30_000); });
      expect(getByText("duraklandı")).toBeTruthy();
      expect(queryByText("● canlı")).toBeNull();
    } finally {
      jest.useRealTimers();
    }
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

  it("bozuk sayıda ÇÖKMEZ (NaN/undefined → '—')", () => {
    // ⚠️ D1.76 · Y6 (2026-10-02): eskiden bozuk değer "0.0000" çiziliyordu — "ölçüldü, sıfır" diye okunur. Artık '—'
    // (sayı olmayan değer sayı gibi gösterilmez); bileşen yine çökmez. Ayrıntılı kapı: EFieldBar.durust.test.tsx.
    mockLive.snapshot = { eField: { ...efield(), cancer: NaN, healthy: undefined } };
    const { getAllByText, getByText, queryByText } = render(<EFieldBar />);
    expect(getAllByText("—")).toHaveLength(2);
    expect(queryByText("0.0000")).toBeNull();
    expect(getByText("Tümör")).toBeTruthy();   // bileşen ayakta, çökmedi
  });
});
