// Author: mertaygn, cglrgrkn
/**
 * GA (istem 53) — `LiveDataContext` canlı alan aboneliği: SAYAÇLI (0 → 1 sunucuya `alan_abone: true`, 1 → 0 `false` + harita temizlenir,
 * aradakiler ileti GÖNDERMEZ); abone yokken gelen `alan_haritasi` YOK SAYILIR; soket her yeniden açıldığında abonelik (varsa) yenilenir.
 */
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async (_p: string, fb: unknown) => fb),
  apiPost: jest.fn(async (_p: string, _b: unknown, fb: unknown) => fb),
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://192.168.1.5:8000/api", websocketUrl: "ws://192.168.1.5:8000/ws", apiToken: "" },
  loadStoredApiToken: jest.fn(async () => undefined),
}));
jest.mock("@/services/discovery", () => ({ discoverBackend: jest.fn(async () => null) }));
jest.mock("@/hooks/useNetworkReachability", () => ({ useNetworkReachability: () => undefined }));
jest.mock("@/hooks/useForegroundReconnect", () => ({ useForegroundReconnect: () => undefined }));

const mockWs: { onMessage?: (m: unknown) => void; kontrol?: { gonder?: unknown; acilinca?: () => void } } = {};
const mockGonder = jest.fn((_i: unknown) => true);
jest.mock("@/services/wsClient", () => ({
  connectPemfWebSocket: (onMessage: (m: unknown) => void, _s: unknown, _r: unknown, kontrol: { gonder?: unknown }) => {
    mockWs.onMessage = onMessage;
    kontrol.gonder = mockGonder;
    mockWs.kontrol = kontrol as typeof mockWs.kontrol;
    return () => undefined;
  },
}));

import React from "react";
import { Text } from "react-native";
import { act, render } from "@testing-library/react-native";
import { LiveDataProvider, useLiveData } from "@/context/LiveDataContext";

let abone: (acik: boolean) => void = () => {};
function Probe() {
  const { alanHaritasi, alanAbone } = useLiveData();
  abone = alanAbone!;
  return <Text testID="harita">{alanHaritasi ? String(alanHaritasi.durum) : "yok"}</Text>;
}

const ileti = (durum: string) => ({ type: "alan_haritasi", data: { surum: 1, durum, zaman: 1, modelTahmini: true } });

it("GA: sayaçlı abonelik, abone yokken ileti yok sayılır, yeniden açılışta yenilenir", async () => {
  const u = render(
    <LiveDataProvider>
      <Probe />
    </LiveDataProvider>,
  );
  await act(async () => {});
  act(() => mockWs.onMessage!(ileti("sifir")));
  expect(u.getByTestId("harita").props.children).toBe("yok"); // abone yok → yok sayıldı
  act(() => mockWs.kontrol!.acilinca!());
  expect(mockGonder).not.toHaveBeenCalled(); // abone yokken açılış abonelik göndermez
  act(() => abone(true));
  expect(mockGonder.mock.calls).toEqual([[{ type: "alan_abone", acik: true }]]);
  act(() => abone(true)); // ikinci tüketici (ör. Simülasyon köprüsü)
  expect(mockGonder).toHaveBeenCalledTimes(1);
  act(() => mockWs.onMessage!(ileti("tamam")));
  expect(u.getByTestId("harita").props.children).toBe("tamam");
  act(() => mockWs.onMessage!({ type: "alan_haritasi" }));
  expect(u.getByTestId("harita").props.children).toBe("yok"); // verisiz ileti → null
  act(() => mockWs.kontrol!.acilinca!()); // yeniden bağlanma → abonelik yenilenir
  expect(mockGonder.mock.calls[1]).toEqual([{ type: "alan_abone", acik: true }]);
  act(() => abone(false));
  expect(mockGonder).toHaveBeenCalledTimes(2); // bir tüketici hâlâ açık
  act(() => mockWs.onMessage!(ileti("sifir")));
  act(() => abone(false));
  expect(mockGonder.mock.calls[2]).toEqual([{ type: "alan_abone", acik: false }]);
  expect(u.getByTestId("harita").props.children).toBe("yok"); // son abone çıkınca temizlendi
  act(() => abone(false)); // fazladan çıkış sayacı eksiye düşürmez
  act(() => abone(true));
  expect(mockGonder.mock.calls[3]).toEqual([{ type: "alan_abone", acik: true }]);
});
