// Author: mertaygn, cglrgrkn
/**
 * Y69 (sahip, S-G4) — Kontrol ekranı bobin panelinin canlı okumaları İSTENEN "DC%"nin yanında kartın UYGULADIĞINI
 * ("Uyg.%", canlı durumun `dutyEtkin` alanı = ACK `E=`) gösterir. Bildirilmediyse panelin kısa çizgisi ("-"); 0 gerçek
 * değerdir ("0.0" — 0 tick'e nicelenmiş bobin SÜRÜLMÜYOR).
 * ⚠️ MUTASYON: okuma kaldırılırsa ya da bildirilmeyen değer 0 gösterilirse KIRMIZI.
 */
jest.mock("@/services/apiClient", () => ({ apiPost: jest.fn(async () => ({ status: "success" })) }));
jest.mock("@/services/therapyLimits", () => ({
  clampTherapyParams: (p: unknown) => p,
}));

import { render } from "@testing-library/react-native";
import { CoilParameterPanel } from "@/components/domain/CoilParameterPanel";

const temel = {
  coilId: 1,
  connected: true,
  running: true,
  objectTemp: 0,
  frequencyHz: 1000,
  dutyCycle: 50,
  magneticMt: 0,
  currentA: 0,
  stm32Driven: true,
  stmConnected: true,
  measuredFields: [] as string[],
};

/** "Uyg.%" etiketini taşıyan okuma kutusundaki (host View) DEĞER metni — kutuda değer + etiket olmak üzere iki metin. */
function uygulanan(ekran: ReturnType<typeof render>): string {
  let kutu: any = ekran.getByText("Uyg.%").parent;
  while (kutu && kutu.type !== "View") kutu = kutu.parent;
  const metinler = (kutu?.findAll((n: any) => n.type === "Text") ?? []).map((n: any) => String(n.props.children));
  expect(metinler).toHaveLength(2);
  expect(metinler[1]).toBe("Uyg.%");
  return metinler[0];
}

describe("Y69 — CoilParameterPanel: DC% + Uyg.%", () => {
  it("KRİTİK: istenen DC%'nin yanında uygulanan okunur", () => {
    const ekran = render(<CoilParameterPanel {...temel} dutyEtkin={46} />);
    expect(ekran.getByText("DC%")).toBeTruthy();
    expect(uygulanan(ekran)).toBe("46.0");
  });

  it.each([
    ["undefined", undefined],
    ["null", null],
  ])("KRİTİK: bildirilmediyse (%s) kısa çizgi — 0 DEĞİL", (_ad, deger) => {
    const ekran = render(<CoilParameterPanel {...temel} dutyEtkin={deger} />);
    expect(uygulanan(ekran)).toBe("-");
  });

  it("KARŞIT: 0 tick'e nicelenen bobin 0.0 okunur", () => {
    const ekran = render(<CoilParameterPanel {...temel} frequencyHz={10000} dutyCycle={10} dutyEtkin={0} />);
    expect(uygulanan(ekran)).toBe("0.0");
  });
});
