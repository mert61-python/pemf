// Author: mertaygn, cglrgrkn
/**
 * I18NI-A1.4 (kapsam 3) — ACİL DURDUR, ÜRÜN kipinde (jest'in KATI eksik-anahtar atışı KAPALI) katalog GERÇEKTEN bozukken:
 *   · seans kartı ACİL DURDUR düğmesi yedekten DOLU ve basınca eylem çağrılır (kritikMetin) — `t()`'ye dönen mutantta ham anahtar görünür;
 *   · EN'de yalnız EN katalog bozuksa düğme GÖRÜNÜR ve DOLU (ham anahtar yok; hangi dilin yedeği seçildiği pinlenmez);
 *   · mandal bandı (react-i18next `t()`) katalog bozukken GÖRÜNÜR, "Sıfırla" basılabilir ve AYNI ucu `{onay: true}` ile çağırır (Ö.4-Y8:
 *     işlev kaybı yok). Bantta metnin ham anahtara düşmesi bugünkü davranıştır (GÖZLEM, I18NI raporu) — burada PİNLENMEZ.
 * Orkestratör yeniden üretimi: ajanın iki "ÖLÇÜM" testi bugünkü yan davranışı (TR'ye düşüş, ham anahtar metni) pinliyordu → davranış
 * güvencesine çevrildi.
 * Katalog bozma: `removeResourceBundle` (i18next kaynakları KOPYALAMADAN tutar → `trKaynak` / `enKaynak` başvurusundan geri yüklenir).
 */
let mockSnapshot: Record<string, unknown> = { coils: [], activeTreatment: { isActive: false } };
const mockPost = jest.fn();
const mockConfirm = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiPost: (...a: unknown[]) => mockPost(...a),
  platformConfirm: (...a: unknown[]) => mockConfirm(...a),
  platformAlert: jest.fn(),
}));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn() }));
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => ({ snapshot: mockSnapshot }) }));

import React from "react";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import i18n from "i18next";
import { SessionProgressCard } from "@/components/domain/SessionProgressCard";
import { EstopMandalBandi, SIFIRLA_YOLU } from "@/components/ui/EstopMandalBandi";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";
import { enKaynak, trKaynak } from "@/i18n/kaynaklar";

const depo = { setItem: async () => undefined };
const kart = {
  isActive: true,
  mode: "manual" as const,
  elapsedSec: 60,
  remainingSec: 540,
  durationSec: 600,
  frequencyHz: 10,
  intensityMt: 1.5,
  onStop: jest.fn(),
  onEmergencyStop: jest.fn(),
};
const opts = i18n.options as unknown as { saveMissing?: boolean };
let eskiSave: boolean | undefined;

function bozuk(diller: ("tr" | "en")[]) {
  eskiSave = opts.saveMissing;
  opts.saveMissing = false; // ÜRÜN kipi: eksik anahtar ATMAZ, anahtarı döner
  for (const d of diller) i18n.removeResourceBundle(d, "translation");
}

afterEach(async () => {
  if (!i18n.hasResourceBundle("tr", "translation")) i18n.addResourceBundle("tr", "translation", trKaynak);
  if (!i18n.hasResourceBundle("en", "translation")) i18n.addResourceBundle("en", "translation", enKaynak);
  opts.saveMissing = eskiSave;
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

it("seans kartı: katalog (tr + en) yok — ACİL DURDUR yedekten DOLU, ham anahtar YOK, basınca eylem", () => {
  bozuk(["tr", "en"]);
  kart.onEmergencyStop.mockClear();
  const u = render(<SessionProgressCard {...kart} />);
  expect(u.getByText("🚨 ACİL DURDUR")).toBeTruthy();
  expect(u.queryByText(/guvenlik\.acilDurdur\./)).toBeNull();
  fireEvent.press(u.getByLabelText("Acil durdurma — tüm bobinleri anında durdur"));
  expect(kart.onEmergencyStop).toHaveBeenCalledTimes(1);
});

it("EN etkin, yalnız EN katalog bozuk: seans kartı ACİL DURDUR GÖRÜNÜR, DOLU, ham anahtar YOK, basınca eylem", async () => {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
  bozuk(["en"]);
  kart.onEmergencyStop.mockClear();
  const u = render(<SessionProgressCard {...kart} />);
  const metin = u.getAllByText(/ACİL DURDUR|EMERGENCY STOP/).map((n) => String(n.props.children));
  expect(metin).toHaveLength(1);
  expect(metin[0].trim().length).toBeGreaterThan(3);
  expect(u.queryByText(/guvenlik\.acilDurdur\./)).toBeNull();
  fireEvent.press(u.getAllByRole("button").find((b) => /ACİL|EMERGENCY|Acil|Emergency/.test(String(b.props.accessibilityLabel ?? "")))!);
  expect(kart.onEmergencyStop).toHaveBeenCalledTimes(1);
});

it("mandal bandı katalog bozukken: GÖRÜNÜR, Sıfırla basılabilir ve AYNI ucu {onay: true} ile çağırır", async () => {
  bozuk(["tr", "en"]);
  mockSnapshot = { coils: [], activeTreatment: { isActive: false }, estopMandali: { aktif: true, neden: "manual" } };
  mockPost.mockReset().mockResolvedValue({ status: "success" });
  mockConfirm.mockReset().mockResolvedValue(true);
  const u = render(<EstopMandalBandi />);
  expect(u.UNSAFE_getAllByProps({ accessibilityRole: "alert" }).length).toBeGreaterThan(0); // bant çizildi (accessible olmayan View)
  fireEvent.press(u.UNSAFE_getByProps({ accessibilityRole: "button" }));
  await waitFor(() => expect(mockPost).toHaveBeenCalled());
  expect(mockPost.mock.calls[0][0]).toBe(SIFIRLA_YOLU);
  expect(mockPost.mock.calls[0][1]).toEqual({ onay: true });
});
