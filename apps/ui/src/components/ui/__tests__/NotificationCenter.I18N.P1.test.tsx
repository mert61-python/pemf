// Author: mertaygn, cglrgrkn
/**
 * I18N-P1 · KRİTİK — bildirim merkezi: sunucu bildirimi İKİ DİLLİ gelir (`mesajlar` {tr, en}); arayüz KENDİ dilindekini gösterir.
 * Eski sunucu (`mesajlar` yok) → Türkçe `message` (her iki dilde de) — sunucu metnine göre DALLANMA yok (KURALLAR §4.9).
 * Metinler gerçek ACİL DURDUR / STOP bildirimleridir (sunucu kataloğuyla aynı; sunucu tarafı `test_sunucu_ana_sunucu_bildirimleri_iki_dilli_P1.py`).
 */
jest.mock("@/services/apiClient", () => ({
  platformConfirm: jest.fn(async () => true),
}));

let mockBildirimler: any[] = [];
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({
    snapshot: { notifications: mockBildirimler },
    unreadCount: 0,
    markAllRead: jest.fn(),
    clearNotifications: jest.fn(),
  }),
}));

import React from "react";
import { act, render, waitFor } from "@testing-library/react-native";

import { NotificationCenter } from "@/components/ui/NotificationCenter";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };

const TR_STOP =
  "⚠️ Süre doldu — otomatik durdurma: bobin(ler) [2, 5] için donanım STOP'u DOĞRULANAMADI — HÂLÂ ÇALIŞIYOR olabilirler. ACİL DURDUR'a basın ya da bobinleri elle kontrol edin.";
const EN_STOP =
  "⚠️ Time is up — automatic stop: the hardware STOP could NOT be VERIFIED for coil(s) [2, 5] — they may STILL BE RUNNING. Press EMERGENCY STOP or check the coils by hand.";
const TR_KOPTU = "Sistem bağlantısı kesildi";

beforeEach(() => {
  mockBildirimler = [
    { id: 2, message: TR_STOP, mesajlar: { tr: TR_STOP, en: EN_STOP }, level: "error", timestamp: "2026-10-20T12:00:00" },
    { id: 1, message: TR_KOPTU, level: "warning", timestamp: "2026-10-20T11:59:00" }, // eski sunucu: `mesajlar` yok
  ];
});
afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

describe("KRİTİK: bildirim merkezi — sunucu bildirimi seçili dilde", () => {
  it("Türkçe: sunucunun Türkçe metni BAYT BAYT (ACİL DURDUR'a basın)", async () => {
    const u = render(<NotificationCenter />);
    await waitFor(() => u.getAllByTestId("bildirim-metni"));
    expect(u.getAllByTestId("bildirim-metni")).toHaveLength(2);
    expect(u.getByText(TR_STOP)).toBeTruthy();
    expect(u.getByText(TR_KOPTU)).toBeTruthy();
  });

  it("İngilizce (bayrak açık): iki dilli bildirim İngilizce (Press EMERGENCY STOP); eski sunucu bildirimi Türkçe kalır; dil dönünce Türkçe", async () => {
    __bayrakTestiAyarla(true);
    const u = render(<NotificationCenter />);
    await waitFor(() => u.getAllByTestId("bildirim-metni"));
    await act(async () => {
      await dilSec("en", depo);
    });
    expect(u.getByText(EN_STOP)).toBeTruthy();
    expect(u.getByText(TR_KOPTU)).toBeTruthy();
    expect(u.queryByText(TR_STOP)).toBeNull();
    await act(async () => {
      await dilSec("tr", depo);
    });
    expect(u.getByText(TR_STOP)).toBeTruthy();
    expect(u.queryByText(EN_STOP)).toBeNull();
  });
});

// KP-7 C · Y295 (17-11, sahip): bildirim SAATİ etkin dilde biçimlenir — İngilizcede İngiliz biçimi (`en-GB`, 24 saat: "12:00:00", "12:00:00
// PM" DEĞİL), Türkçede `tr-TR`. ÖNCE-KIRMIZI: sabit "tr-TR". Dil AÇIKÇA kurulur.
describe("KP-7 C · Y295 bildirim saati", () => {
  it("İngilizcede en-GB ile (24 saat), Türkçede tr-TR ile biçimlenir", async () => {
    const casus = jest.spyOn(Date.prototype, "toLocaleTimeString");
    try {
      __bayrakTestiAyarla(true);
      await act(async () => { await dilSec("en", depo); });
      const en = render(<NotificationCenter />);
      await waitFor(() => en.getAllByTestId("bildirim-metni"));
      expect(casus.mock.calls.map((c) => c[0])).toContain("en-GB");
      expect(casus.mock.calls.map((c) => c[0])).not.toContain("tr-TR");
      expect(en.queryAllByText(/PM|AM/)).toHaveLength(0);
      en.unmount();
      casus.mockClear();
      await act(async () => { await dilSec("tr", depo); });
      const tr = render(<NotificationCenter />);
      await waitFor(() => tr.getAllByTestId("bildirim-metni"));
      expect(casus.mock.calls.map((c) => c[0])).toContain("tr-TR");
    } finally {
      casus.mockRestore();
    }
  });
});
