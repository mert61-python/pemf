// Author: mertaygn, cglrgrkn
/**
 * D1.90 · İG-6.90 · 1-E inceleme i-14.1 (web yolu, AÇIK kalmıştı) — WEB (canvas): ölçülmeyen alanın SON-DEĞER ucu çizilmez
 * ve eğrisi çizilmez (kalem kalkar; 0'a düşen sahte çizgi yok).
 * ======================================================================================================================
 * ÖLÇÜLEN KÖRLÜK (1-E inceleme K14-M2): web son-değer ucunu ölçülmeyen alanda da çizen mutant 628/628 YEŞİL kalıyordu —
 * web kaydedicisi yalnız `fillText` (eksen etiketleri) tutuyordu; native kol (r=3 uç) web'i görmez.
 * Burada kaydedici 2B bağlam `arc` (o anki `fillStyle`) ve yol çizimini (`moveTo`/`lineTo` → `stroke` anındaki
 * `strokeStyle` + çizgi deseni) kaydeder; her yeniden çizim arka plan `fillRect`iyle başlar → yalnız SON kare ölçülür.
 * Veri: GERÇEK `LiveDataProvider` + gerçek yayın fikstürü (bobin 6 alan ölçer; bobin 7 yalnız sıcaklık, `magneticMt: 0.0`;
 * bobin 1 sıcaklık ölçmez). Çizim kodu GERÇEK `RealtimeChart`.
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async (_p: string, fb: unknown) => fb),
  apiPost: jest.fn(async (_p: string, _b: unknown, fb: unknown) => fb),
  platformAlert: jest.fn(),
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api", websocketUrl: "ws://127.0.0.1:8000/ws", apiToken: "" },
  loadStoredApiToken: jest.fn(async () => undefined),
}));
jest.mock("@/services/discovery", () => ({ discoverBackend: jest.fn(async () => null) }));
jest.mock("@/hooks/useNetworkReachability", () => ({ useNetworkReachability: () => undefined }));
jest.mock("@/hooks/useForegroundReconnect", () => ({ useForegroundReconnect: () => undefined }));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn() }));
const mockWs: { onMessage?: (m: any) => void; onState?: (c: boolean) => void } = {};
jest.mock("@/services/wsClient", () => ({
  connectPemfWebSocket: (onMessage: any, onState: any) => {
    mockWs.onMessage = onMessage;
    mockWs.onState = onState;
    return () => undefined;
  },
}));

import React from "react";
import { act, render } from "@testing-library/react-native";
import { LiveDataProvider, useLiveData } from "@/context/LiveDataContext";
import { RealtimeChart } from "@/components/visual/RealtimeChart";

const dizi: any[] = require("./__fixtures__/sensorGrafigi.D190.ws.json");
const RENK = { 1: "#EF4444", 6: "#06B6D4", 7: "#EC4899" } as const; // RealtimeChart COIL_COLORS[(id-1) % 8]

type Cizgi = { renk: string; desen: string; inis: number; cizgi: number };
type Kare = { uclar: { r: number; renk: string }[]; cizgiler: Cizgi[] };

/** Kaydedici 2B bağlam: kare = arka plan `fillRect`inden sonraki çizimler. */
function kaydediciTuval() {
  const kareler: Kare[] = [];
  let yol = { inis: 0, cizgi: 0 };
  const durum: Record<string, unknown> = { fillStyle: "", strokeStyle: "", _desen: "" };
  const kare = () => kareler[kareler.length - 1];
  const ctx = new Proxy(durum, {
    get(h, ad: string) {
      if (ad === "fillRect") return () => kareler.push({ uclar: [], cizgiler: [] });
      if (ad === "beginPath") return () => (yol = { inis: 0, cizgi: 0 });
      if (ad === "moveTo") return () => (yol.inis += 1);
      if (ad === "lineTo") return () => (yol.cizgi += 1);
      if (ad === "setLineDash") return (d: number[]) => (h._desen = (d ?? []).join(","));
      if (ad === "stroke")
        return () => kare()?.cizgiler.push({ renk: String(h.strokeStyle), desen: String(h._desen), ...yol });
      if (ad === "arc") return (_x: number, _y: number, r: number) => kare()?.uclar.push({ r, renk: String(h.fillStyle) });
      if (ad in h) return h[ad];
      return () => undefined;
    },
    set(h, ad: string, v) {
      h[ad] = v;
      return true;
    },
  });
  const tuval = { width: 0, height: 0, style: {}, getContext: () => ctx };
  return { tuval, kareler };
}

function Grafik({ bobinler }: { bobinler: number[] }) {
  const { sensorHistory } = useLiveData();
  return <RealtimeChart history={sensorHistory} visibleCoils={new Set(bobinler)} width={600} height={300} />;
}

const gercekRaf = (global as any).requestAnimationFrame;
const gercekCaf = (global as any).cancelAnimationFrame;
beforeAll(() => {
  (global as any).requestAnimationFrame = (cb: (t: number) => void) => {
    cb(0);
    return 1;
  };
  (global as any).cancelAnimationFrame = () => undefined;
});
afterAll(() => {
  (global as any).requestAnimationFrame = gercekRaf;
  (global as any).cancelAnimationFrame = gercekCaf;
});

async function sonKare(bobinler: number[]): Promise<Kare> {
  const { tuval, kareler } = kaydediciTuval();
  render(
    <LiveDataProvider>
      <Grafik bobinler={bobinler} />
    </LiveDataProvider>,
    { createNodeMock: (el: any) => (el.type === "canvas" ? tuval : null) }
  );
  await act(async () => {});
  await act(async () => {
    mockWs.onState?.(true);
  });
  for (const m of dizi) {
    await act(async () => {
      mockWs.onMessage?.(m);
    });
  }
  expect(kareler.length).toBeGreaterThan(0);
  return kareler[kareler.length - 1];
}

const duz = (k: Kare, renk: string) => k.cizgiler.filter((c) => c.renk === renk && c.desen === "");
const kesik = (k: Kare, renk: string) => k.cizgiler.filter((c) => c.renk === renk && c.desen !== "");

it("aparat: yalnız bobin 6 — son karede bobin 6'nın mT eğrisi ve TEK son-değer ucu (r=3) çizilir", async () => {
  const k = await sonKare([6]);
  expect(duz(k, RENK[6]).some((c) => c.cizgi > 0)).toBe(true);
  expect(k.uclar.filter((u) => u.r === 3).map((u) => u.renk)).toEqual([RENK[6]]);
});

it("KRİTİK: bobin 6 + 7 — bobin 7'nin ölçülmeyen mT'si için SON-DEĞER ucu çizilmez (web)", async () => {
  const k = await sonKare([6, 7]);
  expect(k.uclar.filter((u) => u.r === 3).map((u) => u.renk)).toEqual([RENK[6]]);
  expect(k.uclar.some((u) => u.renk.startsWith(RENK[7]))).toBe(false);
});

it("KRİTİK: bobin 7'nin ölçülmeyen mT'si EĞRİ olarak çizilmez — kalem hiç inmez (0'a düşen sahte çizgi yok)", async () => {
  const k = await sonKare([6, 7]);
  const yedi = duz(k, RENK[7]);
  expect(yedi.length).toBe(1); // yol açılır ama
  expect(yedi[0].inis + yedi[0].cizgi).toBe(0); // hiçbir nokta çizilmez
});

it("KRİTİK: sıcaklık ölçmeyen bobin 1'in kesikli sıcaklık eğrisi çizilmez (web)", async () => {
  const k = await sonKare([1, 6]);
  const bir = kesik(k, RENK[1]);
  expect(bir.length).toBe(1);
  expect(bir[0].inis + bir[0].cizgi).toBe(0);
  expect(kesik(k, RENK[6]).some((c) => c.cizgi > 0)).toBe(true); // KARŞIT: ölçen bobin 6'nın sıcaklığı çizilir
});
