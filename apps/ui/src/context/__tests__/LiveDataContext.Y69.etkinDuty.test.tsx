// Author: mertaygn, cglrgrkn
/**
 * Y69 (sahip, S-G4) — canlı veri bağlamı bobinin ETKİN duty'sinde (`dutyEtkin`, ACK `E=`) "kart BİLDİRMEDİ" (null) ile
 * 0'ı ("sürülmüyor") AYIRIR. Diğer sayısal alanlar `_num` ile 0'a zorlanır (çökmeyi önlemek için); bu alan zorlanırsa
 * bildirmeyen eski firmware / ESP bobini / kopuk kart arayüzde "uygulanan 0.0%" — yani "sürülmüyor" — görünürdü.
 * Sahte olan yalnız WS taşıması (mesajlar sırasıyla enjekte edilir); normalizasyon GERÇEK sağlayıcınınki.
 * ⚠️ MUTASYON: `dutyEtkin: _numVeyaYok(...)` → `_num(...)` yapılırsa KIRMIZI.
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
import { Text } from "react-native";
import { LiveDataProvider, useLiveData } from "@/context/LiveDataContext";

function Probe() {
  const { snapshot } = useLiveData();
  const d = snapshot.coils.find((c) => c.id === 1)?.dutyEtkin;
  return <Text testID="etkin">{`${typeof d}:${String(d)}`}</Text>;
}

const send = async (msg: any) => {
  await act(async () => {
    mockWs.onMessage?.(msg);
  });
};

describe("Y69 — LiveDataContext: dutyEtkin null ≠ 0", () => {
  it("KRİTİK: bildirilmeyen etkin duty null kalır; sayı/dize sayıya, 0 0'a çözülür", async () => {
    const ekran = render(
      <LiveDataProvider>
        <Probe />
      </LiveDataProvider>
    );
    await act(async () => {
      mockWs.onState?.(true);
    });
    const oku = () => ekran.getByTestId("etkin").props.children;
    expect(oku()).toBe("object:null"); // başlangıç: alan hiç gelmedi
    await send({ type: "coil_status", coilId: 1, data: { dutyEtkin: 46 } });
    expect(oku()).toBe("number:46");
    await send({ type: "coil_status", coilId: 1, data: { dutyEtkin: "30.5" } });
    expect(oku()).toBe("number:30.5");
    await send({ type: "coil_status", coilId: 1, data: { dutyEtkin: null } });
    expect(oku()).toBe("object:null");
    await send({ type: "stm_coil_update", coilId: 1, data: { dutyEtkin: 0 } });
    expect(oku()).toBe("number:0");
  });
});
