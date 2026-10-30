// Author: mertaygn, cglrgrkn
/**
 * Y222 (sahip, 2026-10-30) · KRİTİK — seans kartındaki ACİL DURDUR yazısı dar ekranda KESİLMEZ
 * ============================================================================================
 * ÖLÇÜLEN: 360 × 772 telefon / Chrome cihaz kipinde (web istemcisi) kart düğmesi "🚨 EMERGEN…" gösteriyordu. Neden: metin
 * `numberOfLines={1} adjustsFontSizeToFit` idi; react-native-web `adjustsFontSizeToFit`'i UYGULAMAZ, tek satır sınırı ise
 * CSS `text-overflow: ellipsis` olur → metin üç noktayla kesilir.
 *
 * SÖZLEŞME: yazı KISALTILMAZ ("🚨 EMERGENCY STOP" / "🚨 ACİL DURDUR" aynen) ve SATIR SINIRI YOKTUR — dar ekranda iki satıra
 * iner (ortalı); basış aynı işlevi çağırır (istekler bit bit aynı — `performEmergencyStop` değişmedi). Profil ekranındaki
 * büyük ACİL DURDUR barı (`GlobalEmergencyStop`) bu sözleşmenin dışında ve DEĞİŞMEZ (Y221).
 *
 * ⚠️ MUTASYON: `numberOfLines={1}` geri gelirse 1. ve 2. vaka; `numberOfLines={2}` (satır kırpma) da KIRILIR; metin kısaltılırsa
 * (`slice` / farklı anahtar) `getByText` tam eşleşmesi KIRILIR.
 */
import React from "react";
import { Dimensions, StyleSheet, type StyleProp, type TextStyle } from "react-native";
import { act, fireEvent, render } from "@testing-library/react-native";
import { SessionProgressCard } from "@/components/domain/SessionProgressCard";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };
const temel = {
  isActive: true,
  mode: "manual" as const,
  elapsedSec: 41,
  remainingSec: 3559,
  durationSec: 3600,
  frequencyHz: 40,
  intensityMt: 25,
  onStop: jest.fn(),
  onEmergencyStop: jest.fn(),
};

beforeEach(() => {
  // Dar telefon: Chrome cihaz kipi 360 × 772 (Şekil 2c). Bileşen genişliğe göre dal AÇMAZ — sözleşme her genişlikte aynı.
  const dar = { width: 360, height: 772, scale: 4, fontScale: 1 };
  jest.spyOn(Dimensions, "get").mockReturnValue(dar);
});

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

type MetinProps = { numberOfLines?: number; ellipsizeMode?: string; style?: StyleProp<TextStyle> };

function kesilmez(p: MetinProps) {
  // Satır sınırı yok → react-native-web ellipsis / line-clamp üretmez; yerelde de kırpılmaz.
  expect(p.numberOfLines).toBeUndefined();
  expect(p.ellipsizeMode).toBeUndefined();
  expect(StyleSheet.flatten(p.style)?.textAlign).toBe("center");
}

it("KRİTİK (EN, 360 px): '🚨 EMERGENCY STOP' tam metin, satır sınırı yok; basış aynı işlevi çağırır", async () => {
  await enYap();
  temel.onEmergencyStop.mockClear();
  const u = render(<SessionProgressCard {...temel} />);
  kesilmez(u.getByText("🚨 EMERGENCY STOP").props as MetinProps);
  fireEvent.press(u.getByLabelText("Emergency stop — stop all coils immediately"));
  expect(temel.onEmergencyStop).toHaveBeenCalledTimes(1);
});

it("KRİTİK (EN): durdurulurken '🚨 STOPPING…' de kesilmez", async () => {
  await enYap();
  const u = render(<SessionProgressCard {...temel} stopping />);
  kesilmez(u.getByText("🚨 STOPPING…").props as MetinProps);
});

it("KRİTİK (TR, 360 px): '🚨 ACİL DURDUR' tam metin, satır sınırı yok", () => {
  const u = render(<SessionProgressCard {...temel} />);
  kesilmez(u.getByText("🚨 ACİL DURDUR").props as MetinProps);
  expect(u.getByLabelText("Acil durdurma — tüm bobinleri anında durdur")).toBeTruthy();
});
