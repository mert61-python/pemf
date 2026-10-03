// Author: mertaygn, cglrgrkn
/**
 * D1.90 · B-6.22 + İG-6.90 — Sensör grafiği ÖLÇÜLMEYEN alanı (bobin 7'nin 0.0 mT'si, bobin 1'in 0.0 °C'si) eksen aralığına
 * ve eğriye KATMAZ. NATIVE (react-native-svg) yolu; web canvas yolu `RealtimeChart.D190.web.test.tsx`.
 * =======================================================================================================================
 * ÖLÇÜLEN KUSUR (aday İG-6.90, gerçek backend yayınları): bobin 6 alan basıyor (12,2–12,4 mT), bobin 7 yalnız sıcaklık;
 * WS `sensor_data` bobin 7 için `magneticMt: 0.0` + `measuredFields: ["objectTemp"]` taşıyor. Arayüz `measuredFields`i
 * geçmişe taşımadığı için mT ekseni 0,0–12,3'e çekiliyor, bobin 6'nın eğrisi eziliyordu; bobin 7'nin 0 çizgisi "ölçülen
 * alan" gibi çiziliyordu. Sıcaklık ekseninde aynısı (akım ölçen bobin 1'in 0.0 °C'si).
 *
 * Dizi ELLE YAZILMADI: `__fixtures__/sensorGrafigi.D190.ws.json` firmware satırlarından GERÇEK ayrıştırıcı + GERÇEK
 * `_handle_backend_event` ile üretilir (bayatlık kapısı `tests/test_D190_sensor_grafigi_OLCULMEYEN_alan_eksene_GIRMEZ.py`).
 * GERÇEK: `LiveDataProvider` (geçmiş tamponu), `RealtimeChart`.
 * ⚠️ MUTASYON: ölçülmeyen nokta min/max'a geri katılırsa ya da geçmiş `measuredFields`i taşımazsa KIRMIZI.
 */
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
import { Circle, Polyline, Text as SvgText } from "react-native-svg";
import { LiveDataProvider, useLiveData } from "@/context/LiveDataContext";
import { RealtimeChart } from "@/components/visual/RealtimeChart";

const dizi: any[] = require("./__fixtures__/sensorGrafigi.D190.ws.json");
const MT_RENGI = "#22c55e";
const C_RENGI = "#fb923c";

function Grafik({ bobinler }: { bobinler: number[] }) {
  const { sensorHistory } = useLiveData();
  return <RealtimeChart history={sensorHistory} visibleCoils={new Set(bobinler)} width={600} height={300} />;
}

async function ciz(bobinler: number[], mesajlar: any[] = dizi) {
  const u = render(
    <LiveDataProvider>
      <Grafik bobinler={bobinler} />
    </LiveDataProvider>
  );
  await act(async () => {});
  await act(async () => {
    mockWs.onState?.(true);
  });
  for (const m of mesajlar) {
    await act(async () => {
      mockWs.onMessage?.(m);
    });
  }
  return u;
}

/** Eksen etiketleri (5 adet, alttan üste): `fill` rengine göre seçilir. */
function eksen(u: ReturnType<typeof render>, renk: string): number[] {
  return u
    .UNSAFE_queryAllByType(SvgText)
    .filter((t) => t.props.fill === renk)
    .map((t) => Number(t.props.children));
}
const mTEgrileri = (u: ReturnType<typeof render>) =>
  u.UNSAFE_queryAllByType(Polyline).filter((p) => p.props.strokeWidth === 1.5);

describe("D1.90 / İG-6.90 — native grafik: ölçülmeyen alan eksene ve eğriye girmez", () => {
  it("aparat: yalnız bobin 6 görünürken mT ekseni 12,2–12,4 (gerçek yayın)", async () => {
    const u = await ciz([6]);
    const mt = eksen(u, MT_RENGI);
    expect(mt).toHaveLength(5);
    expect(Math.min(...mt)).toBeGreaterThan(12);
  });

  it("KRİTİK: bobin 6 + 7 görünürken mT ekseni 0'a ÇEKİLMEZ (bobin 7 alan ölçmüyor)", async () => {
    const u = await ciz([6, 7]);
    expect(Math.min(...eksen(u, MT_RENGI))).toBeGreaterThan(10);
  });

  it("KRİTİK: bobin 7'nin ölçülmeyen 0 mT'si EĞRİ olarak çizilmez (yalnız bobin 6'nın mT eğrisi)", async () => {
    const u = await ciz([6, 7]);
    expect(mTEgrileri(u)).toHaveLength(1);
  });

  it("KRİTİK: bobin 7'nin ölçülmeyen mT'si için SON-DEĞER noktası çizilmez (yalnız bobin 6'nın ucu)", async () => {
    // 1-E incelemesi (i-14.1): "son-değer ucu yalnız ölçülmüşse" kuralını kaldıran mutant native ve web'de 628/628 YEŞİL
    // kalıyordu — ölçülmeyen alan grafiğin sağ ucunda "şu anki değer" noktası olarak çiziliyordu.
    const u = await ciz([6, 7]);
    const uclar = u.UNSAFE_queryAllByType(Circle).filter((c) => c.props.r === 3);
    expect(uclar).toHaveLength(1);
  });

  it("KRİTİK: sıcaklık ekseni, sıcaklık ölçmeyen bobin 1 yüzünden 0'a ÇEKİLMEZ", async () => {
    const u = await ciz([1, 6, 7]);
    expect(Math.min(...eksen(u, C_RENGI))).toBeGreaterThan(30);
    expect(Math.min(...eksen(u, MT_RENGI))).toBeGreaterThan(10);
  });

  it("KARŞIT: `measuredFields` göndermeyen ESKİ backend'de eski davranış (değer çizilir; sessizce kaybolmaz)", async () => {
    const eski = dizi.map((m) => {
      const { measuredFields: _x, ...data } = m.data;
      return { ...m, data };
    });
    const u = await ciz([6, 7], eski);
    expect(Math.min(...eksen(u, MT_RENGI))).toBe(0);
    expect(mTEgrileri(u)).toHaveLength(2);
  });
});
