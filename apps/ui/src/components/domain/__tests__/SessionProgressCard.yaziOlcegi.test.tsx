// Author: mertaygn, cglrgrkn
/**
 * SEANS SÜRESİ — HER YAZI ÖLÇEĞİNDE TEK SATIR  [S6 adım 4 / ekranB-8, 2026-09-04 denetimi]
 * ========================================================================================
 * ⚠️ HASTA GÜVENLİĞİ SINIRINDA: KALAN süre ile ACİL DURDUR aynı kartta okunur. Süre biçimi
 * saatli ("1:05:30") olduğunda 320 px'lik telefonda NORMAL yazı ölçeğinde bile taşıyor, sistem
 * ölçeği 1,3'te kırpılıyordu — hekim ne kadar kaldığını göremiyordu.
 *
 * SÖZLEŞME:
 *  1. Biçim HER ZAMAN 'mm:ss'; 65 dakika "65:30" olarak yazılır (klinik kapak 120 dk → 6 karakter).
 *  2. Süre metinleri tek satır, sığmazsa KÜÇÜLTÜLEREK sığdırılır, ölçek tavanı 1,1.
 *  3. "Süresiz" seansta da aynı sözleşme geçerli (metin kırpılmaz).
 *
 * ⚠️ MUTASYON: saatli dal geri eklenirse 1. vaka; adjustsFontSizeToFit kaldırılırsa 2. vaka KIRILIR.
 */
import React from "react";
import { render } from "@testing-library/react-native";

import { SessionProgressCard } from "../SessionProgressCard";

const temel = {
  isActive: true,
  mode: "manual" as const,
  elapsedSec: 0,
  remainingSec: 0,
  durationSec: 1200,
  frequencyHz: 10,
  intensityMt: 1.5,
  onStop: () => {},
  onEmergencyStop: () => {},
};

describe("süre biçimi", () => {
  it("KRİTİK: 65 dakika 'saat' biçimine dönmez — 65:30 yazılır", () => {
    const u = render(<SessionProgressCard {...temel} elapsedSec={3930} remainingSec={3270} durationSec={7200} />);
    expect(u.getByText("65:30")).toBeTruthy();
    expect(u.queryByText("1:05:30")).toBeNull();
  });

  it("bir saatin altında biçim değişmez", () => {
    const u = render(<SessionProgressCard {...temel} elapsedSec={90} remainingSec={510} />);
    expect(u.getByText("01:30")).toBeTruthy();
    expect(u.getByText("08:30")).toBeTruthy();
  });

  it("klinik kapağı (120 dk) en fazla 6 karakter üretir", () => {
    const u = render(<SessionProgressCard {...temel} elapsedSec={0} remainingSec={7200} durationSec={7200} />);
    expect(u.getByText("120:00").props.children).toHaveLength(6);
  });
});

describe("yazı ölçeği dayanıklılığı", () => {
  const sureProps = (metin: string) => {
    const u = render(<SessionProgressCard {...temel} elapsedSec={3930} remainingSec={3270} durationSec={7200} />);
    return u.getByText(metin).props as {
      numberOfLines?: number;
      adjustsFontSizeToFit?: boolean;
      maxFontSizeMultiplier?: number;
    };
  };

  it("KRİTİK: KALAN süre tek satır ve sığdırılarak yazılır", () => {
    const p = sureProps("54:30");
    expect(p.numberOfLines).toBe(1);
    expect(p.adjustsFontSizeToFit).toBe(true);
    expect(p.maxFontSizeMultiplier).toBe(1.1);
  });

  it("GEÇEN süre de aynı sözleşmeye tabi", () => {
    const p = sureProps("65:30");
    expect(p.numberOfLines).toBe(1);
    expect(p.adjustsFontSizeToFit).toBe(true);
  });

  it("süresiz seansta 'Süresiz' metni de tek satır", () => {
    const u = render(<SessionProgressCard {...temel} elapsedSec={30} remainingSec={0} durationSec={0} />);
    const p = u.getByText("Süresiz").props as { numberOfLines?: number };
    expect(p.numberOfLines).toBe(1);
  });
});
