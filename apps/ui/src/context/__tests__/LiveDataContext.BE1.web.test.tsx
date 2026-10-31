/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * BE 1 · Y229 — WEB'İN BAĞLANTI DAVRANIŞI DEĞİŞMEZ (makale B2 web istemcisinden ölçer). Telefon yolundaki iyimser kayıtlı adres,
 * 5 sn'lik hafif yoklama ve soğumayı atlayan tetikler YALNIZ yerel (Android / iOS) yolda; web kökenden (`window.location`) bağlanır.
 * Sahte ağ: `baglantiAparati.tsx` (backend KAPALI).
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/services/apiClient", () => ({
  ...jest.requireActual("@/services/apiClient"),
  apiGet: jest.fn(async (_p: string, fb: unknown) => fb),
  apiPost: jest.fn(async (_p: string, _b: unknown, fb: unknown) => fb),
}));
jest.mock("@/services/deviceRegistry", () => ({ getRemoteUrlForDevice: jest.fn(async () => null) }));

import React from "react";
import { render } from "@testing-library/react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { LiveDataProvider } from "@/context/LiveDataContext";
import { serviceConfig } from "@/services/config";
import { PC, Probe, SahteWS, ag, agiSifirla, ilerle, iz, iziSifirla, sahteFetch } from "./baglantiAparati";

let origWS: unknown;
let origFetch: unknown;
let ekran: ReturnType<typeof render> | null = null;

beforeEach(async () => {
  jest.useFakeTimers();
  agiSifirla();
  iziSifirla();
  await AsyncStorage.clear();
  origWS = (global as unknown as { WebSocket: unknown }).WebSocket;
  (global as unknown as { WebSocket: unknown }).WebSocket = SahteWS;
  origFetch = global.fetch;
  global.fetch = jest.fn(sahteFetch) as unknown as typeof fetch;
});

// ⚠️ Söküm ve sahte saatten çıkış TESTİN İÇİNDE (finally): jsdom'da RNTL'nin kendi temizlik kancası sahte saat açıkken asılıyor.
async function sok() {
  ekran?.unmount();
  ekran = null;
  await ilerle(90000, 1000);
  (global as unknown as { WebSocket: unknown }).WebSocket = origWS;
  global.fetch = origFetch as typeof fetch;
  jest.clearAllTimers();
  jest.useRealTimers();
}

it("web: kayıtlı LAN adresi iyimser UYGULANMAZ, çevrimdışıyken 5 sn'lik yoklama YOK, soğumadaki elle dokunma keşif BAŞLATMAZ", async () => {
  try {
    const kokenWs = serviceConfig.websocketUrl;
    await AsyncStorage.setItem("@pemf_server_address", `http://${PC}:8000`);
    ekran = render(
      <LiveDataProvider>
        <Probe />
      </LiveDataProvider>
    );
    await ilerle(500);
    expect(serviceConfig.websocketUrl).toBe(kokenWs);
    // Açılış turu (köken + kayıtlı adres, ~5 sn) başarısız biter → 20 sn soğuma. Soğumadaki elle dokunma web'de keşif başlatmaz.
    await ilerle(9500, 100);
    const once = ag.saglik.length;
    iz.reconnect();
    await ilerle(8000, 100);
    expect(ag.saglik.length).toBe(once);
    await ilerle(12000, 100);
    // Açılıştaki TEK keşif turu kayıtlı adresi bir kez dener (web merdiveni); hafif yoklama web'de koşmaz.
    expect(ag.saglik.filter((s) => s.host === PC).length).toBe(1);
    expect(serviceConfig.websocketUrl).toBe(kokenWs);
  } finally {
    await sok();
  }
}, 60000);
