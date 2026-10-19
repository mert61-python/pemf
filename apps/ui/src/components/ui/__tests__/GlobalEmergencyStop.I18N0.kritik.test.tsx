// Author: mertaygn, cglrgrkn
/**
 * I18N-0 · T11a — ACİL DURDUR çeviri sisteminden BAĞIMSIZ görünür ve çalışır (Ö.4-Y8):
 *   · Türkçe görünüm göçten önceki gibi (bayrak kapalı);
 *   · İngilizcede (bayrak açık) "EMERGENCY STOP", bobin sayısı çoğul;
 *   · katalog BOZUK (çeviri kaynağı kaldırıldı) ya da i18n BAŞLATILMAMIŞ / `t` ATIYOR olsa da etiket boş kalmaz (sabit yedek) ve düğme
 *     STOP gönderir.
 * GERÇEK `GlobalEmergencyStop` + gerçek i18n; sahte: canlı veri (2 bobin çalışıyor), STOP isteği, uyarı / bildirim köprüsü.
 */
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: { coils: [{ running: true }, { running: true }], activeTreatment: { isActive: true } } }),
}));
jest.mock("@/hooks/useStmBelirsiz", () => ({ useStmBelirsiz: () => false }));
const mockStop = jest.fn(async () => ({ confirmed: false, kartReddetti: false }));
jest.mock("@/services/emergencyStop", () => ({ performEmergencyStop: () => mockStop() }));
const mockAlert = jest.fn();
jest.mock("@/services/apiClient", () => ({ platformAlert: (...a: unknown[]) => mockAlert(...a) }));
const mockToast = jest.fn();
jest.mock("@/services/toastBridge", () => ({ emitToast: (...a: unknown[]) => mockToast(...a) }));
jest.mock("@/components/ui/UstKatman", () => ({ UstKatman: ({ children }: { children: unknown }) => children }));

import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";
import i18n from "i18next";
import { GlobalEmergencyStop } from "@/components/ui/GlobalEmergencyStop";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";
import { trKaynak } from "@/i18n/kaynaklar";

const depo = { setItem: async () => undefined };

beforeEach(() => {
  mockStop.mockClear();
  mockAlert.mockClear();
  mockToast.mockClear();
});
afterEach(async () => {
  jest.restoreAllMocks();
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

it("Türkçe (bayrak kapalı): göç öncesiyle AYNI etiket / erişim adı; teyitsiz STOP Türkçe uyarı verir", async () => {
  const u = render(<GlobalEmergencyStop />);
  expect(u.getByText("🚨 ACİL DURDUR (2 bobin)")).toBeTruthy();
  expect(u.getByLabelText("Acil durdur")).toBeTruthy();
  await act(async () => {
    fireEvent.press(u.getByLabelText("Acil durdur"));
  });
  expect(mockStop).toHaveBeenCalledTimes(1);
  expect(mockToast).toHaveBeenCalledWith("Acil durdurma gönderiliyor…", "info");
  expect(mockAlert).toHaveBeenCalledWith(
    "⚠️ ACİL DURDURMA DOĞRULANAMADI",
    "Donanımın durduğu teyit edilemedi. Bobinler hâlâ çalışıyor olabilir — cihazı fiziksel güç düğmesinden kapatın.",
  );
});

it("İngilizce (bayrak açık): EMERGENCY STOP, bobin sayısı çoğul, dil değişince yeniden çizilir", async () => {
  __bayrakTestiAyarla(true);
  const u = render(<GlobalEmergencyStop />);
  expect(u.getByText("🚨 ACİL DURDUR (2 bobin)")).toBeTruthy();
  await act(async () => {
    await dilSec("en", depo);
  });
  expect(u.getByText("🚨 EMERGENCY STOP (2 coils)")).toBeTruthy();
  expect(u.getByLabelText("Emergency stop")).toBeTruthy();
});

it("katalog BOZUK (çeviri kaynağı kaldırıldı): etiket yedekten, düğme STOP gönderir", async () => {
  i18n.removeResourceBundle("tr", "translation");
  try {
    const u = render(<GlobalEmergencyStop />);
    expect(u.getByText("🚨 ACİL DURDUR (2 bobin)")).toBeTruthy();
    await act(async () => {
      fireEvent.press(u.getByLabelText("Acil durdur"));
    });
    expect(mockStop).toHaveBeenCalledTimes(1);
    expect(mockAlert.mock.calls[0][0]).toBe("⚠️ ACİL DURDURMA DOĞRULANAMADI");
  } finally {
    // ⚠️ i18next `init({ resources })` nesnesini KOPYALAMADAN tutar: removeResourceBundle `kaynaklar.tr.translation`'ı da siler
    // (ölçüldü) — geri yükleme ayrı başvurudan (`trKaynak`).
    i18n.addResourceBundle("tr", "translation", trKaynak);
  }
});

it("i18n başlatılmamış / t() ATIYOR: etiket yine boş değil (yedek)", () => {
  jest.spyOn(i18n, "exists").mockImplementation(() => {
    throw new Error("i18n bozuk");
  });
  const u = render(<GlobalEmergencyStop />);
  expect(u.getByText("🚨 ACİL DURDUR (2 bobin)")).toBeTruthy();
  expect(u.getByLabelText("Acil durdur")).toBeTruthy();
});
