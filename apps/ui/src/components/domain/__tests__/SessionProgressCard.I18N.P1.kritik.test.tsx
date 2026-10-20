// Author: mertaygn, cglrgrkn
/**
 * I18N-P1 · KRİTİK — seans kartı (Ana Ekran / Kontrol): "ACİL DURDUR" düğmesi çeviri sisteminden BAĞIMSIZ (kritikMetin + KRITIK_YEDEK),
 * TR / EN görünür, basış AYNI işlevi çağırır; bayat bağlantı uyarısı ve etiketler iki dilde.
 */
import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";
import i18n from "i18next";
import { SessionProgressCard } from "@/components/domain/SessionProgressCard";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };
const temel = {
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

afterEach(async () => {
  jest.restoreAllMocks();
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

async function enYap() {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
}

it("Türkçe: göç öncesiyle aynı etiketler ve ACİL DURDUR düğmesi", () => {
  const u = render(<SessionProgressCard {...temel} stale />);
  expect(u.getByText("🚨 ACİL DURDUR")).toBeTruthy();
  expect(u.getByLabelText("Acil durdurma — tüm bobinleri anında durdur")).toBeTruthy();
  expect(u.getByText("VERİ DOĞRULANMADI")).toBeTruthy();
  expect(u.getByText("⚠️ Bağlantı bayat/çevrimdışı — gösterilen süre ve değerler gerçek zamanlı doğrulanamıyor.")).toBeTruthy();
  expect(u.getByText("YOĞUNLUK (kayıt)")).toBeTruthy();
  expect(u.getByLabelText("Seansı durdur")).toBeTruthy();
});

it("İngilizce: EMERGENCY STOP düğmesi + etiketler; basış AYNI işlevi çağırır; durdurulurken 'STOPPING…'", async () => {
  await enYap();
  temel.onEmergencyStop.mockClear();
  const u = render(<SessionProgressCard {...temel} stale />);
  expect(u.getByText("🚨 EMERGENCY STOP")).toBeTruthy();
  expect(u.getByText("DATA NOT VERIFIED")).toBeTruthy();
  expect(u.getByText("INTENSITY (record)")).toBeTruthy();
  expect(u.getByLabelText("Stop the session")).toBeTruthy();
  fireEvent.press(u.getByLabelText("Emergency stop — stop all coils immediately"));
  expect(temel.onEmergencyStop).toHaveBeenCalledTimes(1);
  u.rerender(<SessionProgressCard {...temel} stale stopping />);
  expect(u.getByText("🚨 STOPPING…")).toBeTruthy();
});

it("katalog anahtarları EKSİK / i18n bozuk: ACİL DURDUR yine görünür (KRITIK_YEDEK) ve çalışır", async () => {
  await enYap();
  temel.onEmergencyStop.mockClear();
  const gercek = i18n.exists.bind(i18n);
  jest.spyOn(i18n, "exists").mockImplementation(((k: string, o?: object) => (String(k).startsWith("guvenlik.acilDurdur.") ? false : gercek(k, o as never))) as never);
  const u = render(<SessionProgressCard {...temel} />);
  expect(u.getByText("🚨 EMERGENCY STOP")).toBeTruthy();
  fireEvent.press(u.getByLabelText("Emergency stop — stop all coils immediately"));
  expect(temel.onEmergencyStop).toHaveBeenCalledTimes(1);
});
