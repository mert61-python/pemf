/**
 * KP-3 C · RealtimeChart NATIVE (react-native-svg) yolunun kenar durumları — her test bir DAVRANIŞ iddiası:
 *  - 120'den fazla nokta seyreltilir (çizim maliyeti sınırlı): 150 nokta → 75 köşe.
 *  - Sabit değerli seride eksen sıfır genişlikte kalmaz: mT ±0,1, °C ±1 açılır (eğri eksenin ortasında).
 *  - Hiçbir alan ÖLÇÜLMEMİŞSE eksen etiketleri "NaN" / "Infinity" değil, güvenli 0–1 aralığındaki SONLU sayılardır.
 *  - Zaman damgası okunamayan noktalar sıra ile yerleşir — köşe koordinatlarında NaN yok.
 * GERÇEK: RealtimeChart (sahte yok; geçmiş doğrudan prop olarak verilir).
 */
import React from "react";
import { render } from "@testing-library/react-native";
import { Polyline, Text as SvgText } from "react-native-svg";
import { RealtimeChart } from "@/components/visual/RealtimeChart";

// ⚠️ Geçmiş noktasında ölçülen alanlar `olculen` (WS iletisinin `measuredFields`i DEĞİL — LiveDataContext dönüştürür; ölçüldü).
type Nokta = { timestamp: unknown; magneticMt: number; objectTemp: number; olculen?: string[] };
const nokta = (i: number, mt: number, c: number, ek: Partial<Nokta> = {}): Nokta =>
  ({ timestamp: 1_700_000_000_000 + i * 1000, magneticMt: mt, objectTemp: c, olculen: ["magneticMt", "objectTemp"], ...ek });
const ciz = (h: Record<number, Nokta[]>) =>
  render(<RealtimeChart history={h as never} visibleCoils={new Set(Object.keys(h).map(Number))} width={600} height={300} />);
const koseler = (u: ReturnType<typeof render>) => u.UNSAFE_queryAllByType(Polyline).map((p) => String(p.props.points).trim().split(/\s+/));
const etiketler = (u: ReturnType<typeof render>) =>
  u.UNSAFE_queryAllByType(SvgText).map((x) => String(([] as unknown[]).concat(x.props.children).join("")));

it("120'den fazla nokta seyreltilir: 150 → 75 köşe", () => {
  const u = ciz({ 6: Array.from({ length: 150 }, (_, i) => nokta(i, 10 + i / 100, 30 + i / 100)) });
  const k = koseler(u);
  expect(k.length).toBeGreaterThanOrEqual(1);
  for (const seri of k) expect(seri).toHaveLength(75);
});

it("sabit değerli seride eksen açılır: mT ±0,1 · °C ±1", () => {
  const u = ciz({ 6: Array.from({ length: 5 }, (_, i) => nokta(i, 12, 31)) });
  const e = etiketler(u);
  expect(e).toEqual(expect.arrayContaining(["11.9", "12.1", "30.0", "32.0"]));
});

it("hiçbir alan ölçülmemişse eksen 0–1, etiketlerin HEPSİ sonlu sayı", () => {
  const u = ciz({ 6: Array.from({ length: 5 }, (_, i) => nokta(i, 0, 0, { olculen: [] })) });
  const e = etiketler(u);
  const sayisal = e.filter((x) => /^-?[\dA-Za-z.]+$/.test(x) && /\d|Infinity|NaN/.test(x));
  expect(sayisal.length).toBeGreaterThanOrEqual(4); // mT + °C eksenleri
  for (const x of sayisal) expect(x).toMatch(/^-?\d+\.\d$/); // "NaN" / "Infinity" yok
  expect(sayisal).toEqual(expect.arrayContaining(["0.0", "1.0"]));
});

it("okunamayan zaman damgalı noktalar sıra ile yerleşir — köşelerde NaN yok", () => {
  const u = ciz({ 6: Array.from({ length: 4 }, (_, i) => nokta(i, 10 + i, 30 + i, { timestamp: "bozuk" })) });
  const k = koseler(u).flat();
  expect(k.length).toBeGreaterThan(0);
  expect(k.join(" ")).not.toMatch(/NaN/);
});
