// Author: mertaygn, cglrgrkn
/**
 * ZG-1 (sahip 13 Kasım 2026) — WEB (canvas) grafiği: altta ANLIK SAAT etiketleri; pencere (son 30 sn) eksen aralığını ve eğriyi YALNIZ
 * penceredeki noktalardan kurar; grafikte sürükleyerek seçilen aralık `onAralikSec`e saniye olarak döner. Çizim kodu GERÇEK; canvas
 * bağlamı kaydedici sahte (`fillText` metin + renk).
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});

import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";
import { RealtimeChart } from "@/components/visual/RealtimeChart";

const yerel = (s: number, d: number, sn: number) => new Date(2026, 10, 13, s, d, sn).getTime() / 1000;
const T0 = yerel(15, 25, 0);
// 120 sn, 1 Hz: ilk 89 sn 5,0 mT, son 31 sn 1,0 mT (pencere [tMax − 30, tMax] uçlar dahil) (pencere son 30 sn'de eksen ~1'e iner)
const GECMIS: any = { 1: Array.from({ length: 120 }, (_, i) => ({ timestamp: T0 + i, magneticMt: i < 89 ? 5 : 1, objectTemp: 30 })) };

function kaydediciTuval() {
  const yazilar: { metin: string; renk: string }[] = [];
  const durum: Record<string, unknown> = { fillStyle: "" };
  const ctx = new Proxy(durum, {
    get(h, ad: string) {
      if (ad === "fillText") return (metin: string) => yazilar.push({ metin: String(metin), renk: String(h.fillStyle) });
      if (ad in h) return h[ad];
      return () => undefined;
    },
    set(h, ad: string, v) {
      h[ad] = v;
      return true;
    },
  });
  return { tuval: { width: 0, height: 0, style: {}, getContext: () => ctx }, yazilar };
}

const gercekRaf = (global as any).requestAnimationFrame;
beforeAll(() => {
  (global as any).requestAnimationFrame = (cb: (t: number) => void) => {
    cb(0);
    return 1;
  };
});
afterAll(() => {
  (global as any).requestAnimationFrame = gercekRaf;
});

function ciz(props: Record<string, unknown>) {
  const { tuval, yazilar } = kaydediciTuval();
  const u = render(<RealtimeChart history={GECMIS} visibleCoils={new Set([1])} showTemp={false} width={600} height={300} {...props} />, {
    createNodeMock: (el: any) => (el.type === "canvas" ? tuval : null),
  });
  return { u, yazilar };
}

it("KRİTİK ZG-1: altta anlık saat etiketleri (SS:DD:ss) çizilir", async () => {
  const { yazilar } = ciz({});
  await act(async () => {});
  const saat = yazilar.filter((y) => /^\d\d:\d\d:\d\d$/.test(y.metin)).map((y) => y.metin);
  expect(saat.length).toBeGreaterThanOrEqual(3);
  expect(saat).toContain("15:26:00");
});

it("KRİTİK ZG-1: son 30 sn penceresi — mT ekseni yalnız penceredeki 1,0'lardan (5,0 dışarıda), saatler pencerede", async () => {
  const { yazilar } = ciz({ pencere: { tip: "son", sn: 30 } });
  await act(async () => {});
  const mt = yazilar.filter((y) => y.renk === "#22c55e" && /^-?\d+\.\d$/.test(y.metin)).map((y) => Number(y.metin));
  expect(mt.length).toBeGreaterThanOrEqual(5);
  expect(Math.max(...mt.slice(-5))).toBeLessThan(2);
  const saat = yazilar.filter((y) => /^\d\d:\d\d:\d\d$/.test(y.metin)).map((y) => y.metin);
  expect(saat.every((s) => s >= "15:26:29" && s <= "15:26:59")).toBe(true);
});

it("KRİTİK ZG-1: grafikte sürükleyerek seçim → onAralikSec(bas, son) saniye; kısa sürükleme yok sayılır", async () => {
  const sec = jest.fn();
  const { u } = ciz({ onAralikSec: sec });
  await act(async () => {});
  const tuvalEl = u.UNSAFE_getByType("canvas" as any);
  fireEvent(tuvalEl, "mouseDown", { nativeEvent: { offsetX: 100 } });
  fireEvent(tuvalEl, "mouseMove", { nativeEvent: { offsetX: 103 } });
  fireEvent(tuvalEl, "mouseUp", {});
  expect(sec).not.toHaveBeenCalled();
  fireEvent(tuvalEl, "mouseDown", { nativeEvent: { offsetX: 120 } });
  fireEvent(tuvalEl, "mouseMove", { nativeEvent: { offsetX: 360 } });
  fireEvent(tuvalEl, "mouseUp", {});
  expect(sec).toHaveBeenCalledTimes(1);
  const [bas, son] = sec.mock.calls[0];
  expect(bas).toBeGreaterThan(T0);
  expect(son).toBeLessThan(T0 + 119);
  expect(son - bas).toBeGreaterThan(30);
});
