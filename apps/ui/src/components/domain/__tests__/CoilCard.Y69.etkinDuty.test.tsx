// Author: mertaygn, cglrgrkn
/**
 * Y69 (sahip, S-G4) — Ana Ekran bobin kartı İSTENEN duty'nin yanında kartın UYGULADIĞINI gösterir.
 * =================================================================================================
 * ÖLÇÜLEN KUSUR (1-G §(b)4): bipolar %50 1 kHz'de etkin %46, 10 kHz'de %20; 10 kHz %10 → 0 tick (bobin SÜRÜLMEZ) — kart
 * yalnız istenen "50%"yi gösteriyordu. Kaynak: canlı durumun `dutyEtkin` alanı (ACK `E=`; backend kapısı
 * tests/test_firmware_ETKIN_duty_ACK_Y69.py).
 * SÖZLEŞME: sayı → "uygulanan 46.0%"; kart BİLDİRMEDİYSE (null/undefined: eski firmware / ESP / kopuk) → "uygulanan —";
 * 0 GERÇEK değerdir → "uygulanan 0.0%" (kısa çizgi DEĞİL).
 * ⚠️ MUTASYON: `alt` satırı kaldırılırsa ya da bildirilmeyen değer 0'a zorlanırsa KIRMIZI.
 */
import { render } from "@testing-library/react-native";
import { CoilCard } from "@/components/domain/CoilCard";
import { CoilStatus } from "@/types/domain";

const temel: CoilStatus = {
  id: 1,
  connected: true,
  running: true,
  frequencyHz: 1000,
  dutyCycle: 50,
  magneticMt: 0,
  objectTemp: 0,
  ambientTemp: 0,
  currentA: 0,
  stm32Driven: true,
  measuredFields: [],
};

describe("Y69 — CoilCard: istenen + UYGULANAN duty", () => {
  it("KRİTİK: istenen duty'nin yanında kartın uyguladığı gösterilir", () => {
    const { getByText } = render(<CoilCard coil={{ ...temel, dutyEtkin: 46 }} />);
    expect(getByText("50%")).toBeTruthy();
    expect(getByText("uygulanan 46.0%")).toBeTruthy();
  });

  it.each([
    ["undefined", undefined],
    ["null", null],
  ])("KRİTİK: kart bildirmediyse (%s) kısa çizgi — 0 DEĞİL", (_ad, deger) => {
    const { getByText, queryByText } = render(<CoilCard coil={{ ...temel, dutyEtkin: deger }} />);
    expect(getByText("uygulanan —")).toBeTruthy();
    expect(queryByText("uygulanan 0.0%")).toBeNull();
  });

  it("KARŞIT: 0 tick'e nicelenen bobin 0 gösterir (bildirilmedi değil)", () => {
    const { getByText } = render(<CoilCard coil={{ ...temel, frequencyHz: 10000, dutyCycle: 10, dutyEtkin: 0 }} />);
    expect(getByText("10%")).toBeTruthy();
    expect(getByText("uygulanan 0.0%")).toBeTruthy();
  });
});
