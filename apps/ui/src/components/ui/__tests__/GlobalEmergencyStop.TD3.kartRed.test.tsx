// Author: mertaygn, cglrgrkn
/**
 * TD3 (tezgâh Oturum 13) — kart ACİL DURDUR'un STOP'unu REDDETTİYSE (STM_NACK) operatör EYLEM metni görür.
 * =====================================================================================================================
 * ÖLÇÜLEN KUSUR: 120 B saha kartı STOP dahil her pakete CRC NACK dönerken backend `confirmed:true` diyordu → arayüz
 * "Tüm bobinler durduruldu ✓". Backend artık `confirmed:false, stmKartYaniti:"red"` döner
 * (tests/test_TD3_estop_kartin_STOP_NACKi_teyit_DEGILDIR.py); `performEmergencyStop` bunu `kartReddetti` olarak taşır.
 * SÖZLEŞME: kart reddettiyse başlık/gövde KART_RED ("gücünü kesin ya da USB kablosunu çıkarın"); yalnız teyitsizse ortak metin.
 * ⚠️ MUTASYON: GES'te `kartReddetti` dalı ortak metne düşürülürse KIRMIZI. Ö.4-Y8: yalnız uyarı metni değişir.
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
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));
let mockSonuc: { confirmed: boolean; kartReddetti: boolean } = { confirmed: false, kartReddetti: true };
jest.mock("@/services/emergencyStop", () => ({
  performEmergencyStop: jest.fn(async () => mockSonuc),
  EMERGENCY_STOP_UNCONFIRMED_TITLE: "ortak-baslik",
  EMERGENCY_STOP_UNCONFIRMED_BODY: "ortak-govde",
  EMERGENCY_STOP_KART_RED_TITLE: "red-baslik",
  EMERGENCY_STOP_KART_RED_BODY: "red-govde",
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
import { act, fireEvent, render } from "@testing-library/react-native";
import { platformAlert } from "@/services/apiClient";
import { LiveDataProvider } from "@/context/LiveDataContext";
import { GlobalEmergencyStop } from "@/components/ui/GlobalEmergencyStop";

const calisan = {
  type: "snapshot",
  data: {
    stm: "online", gateway: "online", mqtt: "devre_disi",
    activeTreatment: { isActive: false, mode: "Sistem Hazır" },
    coils: [1, 2, 3, 4, 5, 6, 7].map((id) => ({ id, connected: true, running: id === 1 })),
    notifications: [],
  },
};

async function bas() {
  const u = render(
    <LiveDataProvider>
      <GlobalEmergencyStop />
    </LiveDataProvider>
  );
  await act(async () => {});
  await act(async () => {
    mockWs.onState?.(true);
  });
  await act(async () => {
    mockWs.onMessage?.(calisan);
  });
  await act(async () => {
    fireEvent.press(u.getByLabelText("Acil durdur"));
  });
  return u;
}

beforeEach(() => {
  (platformAlert as jest.Mock).mockClear();
});

describe("TD3 — kart STOP'u reddetti → eylem metni", () => {
  it("KRİTİK: kartReddetti → KART_RED başlık ve gövde", async () => {
    mockSonuc = { confirmed: false, kartReddetti: true };
    await bas();
    expect(platformAlert).toHaveBeenCalledWith("red-baslik", "red-govde");
  });

  it("KARŞIT: yalnız teyitsiz (kart reddi yok) → ortak metin", async () => {
    mockSonuc = { confirmed: false, kartReddetti: false };
    await bas();
    expect(platformAlert).toHaveBeenCalledWith("ortak-baslik", "ortak-govde");
  });
});
