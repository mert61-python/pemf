/**
 * KP-8 · RealtimeChart NATIVE (react-native-svg) kalan dallar — GERÇEK bileşen (geçmiş doğrudan prop; KP3 native-kenar deseni):
 *  - Ölçü / eksen seçimi verilmezse (DIŞ bileşenin varsayılanları — yerel çizici değerleri hep açıkça alır) 800 × 300 tuval, mT ve
 *    °C eksenleri AÇIK.
 *  - Sıcaklık ekseni kapalıyken °C eksen etiketleri ÇİZİLMEZ.
 *  - Tek noktalı seri NaN koordinat üretmez.
 */
import React from "react";
import { render } from "@testing-library/react-native";
import Svg, { Polyline, Text as SvgText } from "react-native-svg";
import { RealtimeChart } from "@/components/visual/RealtimeChart";

type Nokta = { timestamp: unknown; magneticMt: number; objectTemp: number; olculen?: string[] };
const nokta = (i: number, mt: number, c: number): Nokta =>
  ({ timestamp: 1_700_000_000_000 + i * 1000, magneticMt: mt, objectTemp: c, olculen: ["magneticMt", "objectTemp"] });
/** Eksen etiketleri renkle ayrılır: mT yeşil (#22c55e), °C turuncu (#fb923c). */
const eksen = (u: ReturnType<typeof render>, renk: string) => u.UNSAFE_queryAllByType(SvgText).filter((x) => x.props.fill === renk).length;

it("ölçü / eksen verilmezse 800 × 300, mT ve °C eksenleri açık", () => {
  const u = render(<RealtimeChart history={{ 6: [nokta(0, 10, 30), nokta(1, 12, 32)] } as never} visibleCoils={new Set([6])} />);
  const svg = u.UNSAFE_getAllByType(Svg)[0];
  expect([svg.props.width, svg.props.height]).toEqual([800, 300]);
  expect(eksen(u, "#22c55e")).toBeGreaterThan(0);
  expect(eksen(u, "#fb923c")).toBeGreaterThan(0);
});

it("sıcaklık ekseni kapalı: mT ekseni var, °C etiketi YOK", () => {
  const u = render(
    <RealtimeChart history={{ 6: [nokta(0, 10, 30), nokta(1, 12, 32)] } as never} visibleCoils={new Set([6])} showTemp={false} width={600} height={240} />,
  );
  expect(eksen(u, "#22c55e")).toBeGreaterThan(0);
  expect(eksen(u, "#fb923c")).toBe(0);
});

it("tek noktalı seri: köşelerde NaN yok", () => {
  const u = render(<RealtimeChart history={{ 6: [nokta(0, 10, 30)] } as never} visibleCoils={new Set([6])} width={600} height={240} />);
  const k = u.UNSAFE_queryAllByType(Polyline).map((p) => String(p.props.points));
  expect(k.join(" ")).not.toMatch(/NaN/);
});
