// Author: mertaygn, cglrgrkn
/**
 * D5.42 · İG-6.66 — STM bobin aralığı tek kaynaktan (1..7): STM koptuğunda bobin 6-7 de "bağlı / çalışıyor" GÖRÜNMEZ ve kayan
 * ACİL DURDUR "(bağlantı yok)" ile EKRANDA KALIR (planın "uyandırır" notu: aralık 6-7'ye genişleyince durdurma görünürlüğü bozulmasın).
 * ===========================================================================================================================
 * HEAD'de `LiveDataContext` yerel `STM_COIL_MAX_ID = 5` ile bobin 6-7'yi ESP sayıyordu: `stm_status{warning}` sonrası bobin 6 eski
 * `running:true, connected:true` değeriyle kalıyordu (yanlış "bağlı"). Gerçek backend 6-7'yi de `stm_coil_update` ile yayınlar
 * (`__fixtures__/stmKopusuManuelBobin.ws.json`). Kopuşta durdurma görünürlüğü `useStmBelirsiz`'de (bir kez çalıştıysa kilit).
 * Gerçek olanlar: `LiveDataProvider`, `GlobalEmergencyStop`. Sahte: WS taşıması (mesajlar sırayla enjekte edilir), ağ.
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
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));
jest.mock("@/services/emergencyStop", () => ({
  performEmergencyStop: jest.fn(async () => ({ confirmed: true })),
  EMERGENCY_STOP_UNCONFIRMED_TITLE: "t",
  EMERGENCY_STOP_UNCONFIRMED_BODY: "b",
}));

const mockWs: { onMessage?: (m: unknown) => void; onState?: (c: boolean) => void } = {};
jest.mock("@/services/wsClient", () => ({
  connectPemfWebSocket: (onMessage: (m: unknown) => void, onState: (c: boolean) => void) => {
    mockWs.onMessage = onMessage;
    mockWs.onState = onState;
    return () => undefined;
  },
}));

import React from "react";
import { act, render } from "@testing-library/react-native";
import { Text } from "react-native";
import { LiveDataProvider, useLiveData } from "@/context/LiveDataContext";
import { GlobalEmergencyStop } from "@/components/ui/GlobalEmergencyStop";

function Probe() {
  const { snapshot } = useLiveData();
  const b = (id: number) => (snapshot.coils ?? []).find((c) => c.id === id);
  return (
    <Text testID="durum">
      {JSON.stringify({ stm: snapshot.stm, b6: [b(6)?.connected, b(6)?.running], b7: [b(7)?.connected], b8: [b(8)?.connected] })}
    </Text>
  );
}

const gonder = async (msg: unknown) => {
  await act(async () => {
    mockWs.onMessage?.(msg);
  });
};
const durum = (u: ReturnType<typeof render>) => JSON.parse(String(u.getByTestId("durum").props.children));

async function kur() {
  const u = render(
    <LiveDataProvider>
      <Probe />
      <GlobalEmergencyStop />
    </LiveDataProvider>
  );
  await act(async () => {
    mockWs.onState?.(true);
  });
  await gonder({
    type: "snapshot",
    data: {
      stm: "online",
      activeTreatment: { isActive: false, mode: "Sistem Hazır" },
      coils: [1, 2, 3, 4, 5, 6, 7, 8].map((id) => ({ id, connected: true, running: false })),
    },
  });
  await gonder({ type: "stm_coil_update", coilId: 6, data: { connected: true, running: true } });
  return u;
}

describe("D5.42 — bobin 6-7 STM'de: kopuşta bayat 'bağlı' yok, ACİL DURDUR görünür", () => {
  it("KRİTİK: bobin 6 çalışırken STM koparsa kayan ACİL DURDUR '(bağlantı yok)' ile EKRANDA KALIR", async () => {
    const u = await kur();
    expect(u.queryByText(/ACİL DURDUR \(1 bobin\)/)).not.toBeNull(); // aparat: bobin 6 gerçekten çalışıyor görünür
    await gonder({ type: "stm_status", data: { stm: "warning", connected: false } });
    expect(u.queryByLabelText("Acil durdur")).not.toBeNull();
    expect(u.queryByText(/bağlantı yok/)).not.toBeNull();
  });

  it("KRİTİK: STM koptuktan sonra bobin 6-7 'bağlı / çalışıyor' GÖRÜNMEZ (bayat değer kalmaz)", async () => {
    const u = await kur();
    expect(durum(u).b6).toEqual([true, true]);
    await gonder({ type: "stm_status", data: { stm: "warning", connected: false } });
    expect(durum(u)).toMatchObject({ stm: "warning", b6: [false, false], b7: [false] });
  });

  it("KARŞIT: ESP slotu 8 STM durumundan ETKİLENMEZ (kendi bağlantısı)", async () => {
    const u = await kur();
    await gonder({ type: "stm_status", data: { stm: "warning", connected: false } });
    expect(durum(u).b8).toEqual([true]);
  });
});
