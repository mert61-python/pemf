// Author: mertaygn, cglrgrkn
/**
 * D1.90 · B-6.22 + İG-6.90 — WEB (canvas) yolu: ölçülmeyen alan eksen aralığına GİRMEZ. Aday ölçümü bu yolda yapıldı
 * (`CanvasRenderingContext2D.fillText` sarmalanıp eksen etiketleri okundu: HEAD 0,0–12,3; düzeltilmiş 12,2–12,4).
 * Burada canvas bağlamı kaydedici bir sahtedir (jsdom/RN ortamında canvas yok); çizim kodu GERÇEK `RealtimeChart`.
 * Veri: GERÇEK `LiveDataProvider` + gerçek yayın fikstürü (bkz. native dosyası başlığı).
 * ⚠️ MUTASYON: web min/max döngüsünde ölçülmeyen nokta geri katılırsa KIRMIZI.
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

/** Kaydedici 2B bağlam: `fillText` çağrıları o anki `fillStyle` ile kaydedilir; diğer çizim çağrıları no-op. */
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
  const tuval = { width: 0, height: 0, style: {}, getContext: () => ctx };
  return { tuval, yazilar };
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

async function mTEkseni(bobinler: number[]): Promise<number[]> {
  const { tuval, yazilar } = kaydediciTuval();
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
  // Son çizimin 5 mT eksen etiketi (her yeniden çizim yeni bir takım basar).
  const mt = yazilar.filter((y) => y.renk === "#22c55e" && /^-?\d+\.\d$/.test(y.metin)).map((y) => Number(y.metin));
  return mt.slice(-5);
}

it("aparat: web yolunda eksen etiketleri okunuyor (yalnız bobin 6: > 12)", async () => {
  const mt = await mTEkseni([6]);
  expect(mt).toHaveLength(5);
  expect(Math.min(...mt)).toBeGreaterThan(12);
});

it("KRİTİK: bobin 6 + 7 — web mT ekseni 0'a ÇEKİLMEZ", async () => {
  expect(Math.min(...(await mTEkseni([6, 7])))).toBeGreaterThan(10);
});
