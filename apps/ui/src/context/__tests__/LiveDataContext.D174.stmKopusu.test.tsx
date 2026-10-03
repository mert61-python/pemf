// Author: mertaygn, cglrgrkn
/**
 * D1.74 · İG-6.1 — STM kopunca kayan ACİL DURDUR "(bağlantı yok)" ile EKRANDA KALIR (seanssız manuel bobin).
 * =========================================================================================================
 * ÖLÇÜLEN KUSUR (aday doğrulaması İG-6.1, gerçek backend + headless Chrome): `stm_coil_update` işleyicisi STM bobini
 * için `snapshot.stm`'i "online" yapıyordu. Kopuşta backend ÖNCE `stm_status{warning}`, SONRA her STM bobini için
 * `stm_coil_update{connected:false}` yayınlar → son yazan "online" olunca GES'in "(bağlantı yok)" dalı ölüyor, düğme
 * 259 ms'de kayboluyor (60 örneğin 1'i) ve Ana Ekran "Donanım: çevrimiçi" diyordu. Seans senaryosu arkadan gelen tam
 * `snapshot` yüzünden kusuru MASKELER; bu yüzden kapı SEANSSIZ manuel bobin dizisini oynatır.
 *
 * Dizi ELLE YAZILMADI: `__fixtures__/stmKopusuManuelBobin.ws.json` GERÇEK backend'den (`HeadlessCore` satır işleyicisi →
 * olay veriyolu → `live_state`) üretilir; bayatlarsa `tests/test_D174_stm_cevrimici_YALNIZ_gercek_baglantidan.py`
 * KIRMIZI olur. Sahte olan yalnız WS taşıması (mesajlar sırasıyla enjekte edilir).
 *
 * ⚠️ MUTASYON: işleyiciye `isStmCoil(coilId) ? { stm: "online" } : {}` geri konursa iki iddia da KIRILIR.
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

const mockWs: { onMessage?: (m: any) => void; onState?: (c: boolean) => void } = {};
jest.mock("@/services/wsClient", () => ({
  connectPemfWebSocket: (onMessage: any, onState: any) => {
    mockWs.onMessage = onMessage;
    mockWs.onState = onState;
    return () => undefined;
  },
}));

import React from "react";
import { render, act } from "@testing-library/react-native";
import { Text } from "react-native";
import { LiveDataProvider, useLiveData } from "@/context/LiveDataContext";
import { GlobalEmergencyStop } from "@/components/ui/GlobalEmergencyStop";

const dizi: any[] = require("./__fixtures__/stmKopusuManuelBobin.ws.json");

function Probe() {
  const { snapshot } = useLiveData();
  return <Text testID="stm">{String(snapshot.stm)}</Text>;
}

const send = async (msg: any) => {
  await act(async () => {
    mockWs.onMessage?.(msg);
  });
};

describe("D1.74 / İG-6.1 — gerçek backend dizisi: seanssız manuel bobin + STM kopuşu", () => {
  it("KRİTİK: kopuştan sonra snapshot.stm 'warning' kalır ve GES '(bağlantı yok)' ile EKRANDA kalır", async () => {
    const ekran = render(
      <LiveDataProvider>
        <Probe />
        <GlobalEmergencyStop />
      </LiveDataProvider>
    );
    await act(async () => {
      mockWs.onState?.(true);
    });
    const kopus = dizi.findIndex((m) => m.type === "stm_status" && m.data?.stm === "warning");
    expect(kopus).toBeGreaterThan(0);
    for (const m of dizi.slice(0, kopus)) await send(m);
    // Aparat: kopuştan ÖNCE bobin 1 çalışıyor görünür (dizi gerçekten sürüş içeriyor).
    expect(ekran.getByTestId("stm").props.children).toBe("online");
    expect(ekran.queryByText(/ACİL DURDUR \(1 bobin\)/)).not.toBeNull();

    for (const m of dizi.slice(kopus)) await send(m);

    expect(ekran.getByTestId("stm").props.children).toBe("warning");
    expect(ekran.queryByLabelText("Acil durdur")).not.toBeNull();
    expect(ekran.queryByText(/bağlantı yok/)).not.toBeNull();
  });
});
