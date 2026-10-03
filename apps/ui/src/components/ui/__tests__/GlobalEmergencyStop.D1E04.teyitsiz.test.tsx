// Author: mertaygn, cglrgrkn
/**
 * D1.E04 · İG-6.7 — TEYİTSİZ acil durdurmadan sonra kayan ACİL DURDUR "(teyitsiz)" ile EKRANDA KALIR; ta ki teyitli bir
 * E-stop ya da kartın gerçek tüm-sıfır ACK'i (backend `estop_teyit {teyitli:true}`) gelene dek.
 * =====================================================================================================================
 * ÖLÇÜLEN KUSUR (aday İG-6.7, gerçek backend + STOP'a yanıtsız sahte STM + gerçek web): GES'e basıldı → "ACİL DURDURMA
 * DOĞRULANAMADI" uyarısı → ama backend'in teyitten BAĞIMSIZ `coil_status running:false` yayını yüzünden düğme KALKTI, Ana
 * Ekran "Sistem Hazır" dedi (STM 16 tüm-sıfır paketin 9'u yanıtsız). Uyarı bir kez gösterilip durdurma kontrolü kayboluyordu.
 *
 * Dizi ELLE YAZILMADI: `__fixtures__/teyitsizAcilDurdur.ws.json` GERÇEK `_emergency_stop_all`'dan üretilir (bayatlık kapısı
 * `tests/test_D1E04_teyitsiz_estop_teyit_durumu_AYRI_yayinlanir.py`). GERÇEK: `LiveDataProvider`, `GlobalEmergencyStop`.
 * ⚠️ MUTASYON: GES görünürlüğünden teyitsiz koşulu silinirse ya da `estop_teyit` iletisi işlenmezse KIRMIZI. Ö.4-Y8:
 * yalnız görünürlük ARTAR.
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
let mockTeyit = false;
jest.mock("@/services/emergencyStop", () => ({
  performEmergencyStop: jest.fn(async () => ({ confirmed: mockTeyit })),
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
import { act, fireEvent, render } from "@testing-library/react-native";
import { LiveDataProvider } from "@/context/LiveDataContext";
import { GlobalEmergencyStop } from "@/components/ui/GlobalEmergencyStop";

const dizi: any[] = require("./__fixtures__/teyitsizAcilDurdur.ws.json");

const calisan = {
  type: "snapshot",
  data: {
    stm: "online", gateway: "online", mqtt: "devre_disi",
    activeTreatment: { isActive: false, mode: "Sistem Hazır" },
    coils: [1, 2, 3, 4, 5, 6, 7].map((id) => ({ id, connected: true, running: id === 1 })),
    notifications: [],
  },
};

async function kur() {
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
  expect(u.queryByText(/ACİL DURDUR \(1 bobin\)/)).not.toBeNull(); // aparat: bobin çalışıyor
  return u;
}
const gonder = async (mesajlar: any[]) => {
  for (const m of mesajlar) {
    await act(async () => {
      mockWs.onMessage?.(m);
    });
  }
};

beforeEach(() => {
  mockTeyit = false;
});

describe("D1.E04 / İG-6.7 — teyitsiz E-stop'tan sonra kayan ACİL DURDUR kalır", () => {
  it("KRİTİK: basış teyitsiz + backend dizisi (running:false, estop_teyit teyitli:false) → düğme '(teyitsiz)' ile DOM'da", async () => {
    const u = await kur();
    await act(async () => {
      fireEvent.press(u.getByLabelText("Acil durdur"));
    });
    await gonder(dizi);
    expect(u.queryByLabelText("Acil durdur")).not.toBeNull();
    expect(u.queryByText(/teyitsiz/)).not.toBeNull();
  });

  it("KRİTİK: başka istemcinin teyitsiz E-stop'u da (yalnız WS dizisi) düğmeyi tutar", async () => {
    const u = await kur();
    await gonder(dizi);
    expect(u.queryByText(/teyitsiz/)).not.toBeNull();
  });

  it("KARŞIT: kartın tüm-sıfır ACK'iyle gelen teyit (estop_teyit teyitli:true) düğmeyi KALDIRIR (bobin çalışmıyor)", async () => {
    const u = await kur();
    await act(async () => {
      fireEvent.press(u.getByLabelText("Acil durdur"));
    });
    await gonder(dizi);
    await gonder([{ type: "estop_teyit", data: { teyitli: true, kaynak: "stm_ack" } }]);
    expect(u.queryByLabelText("Acil durdur")).toBeNull();
  });

  it("KARŞIT: teyitli basış + teyitli dizi → düğme kalkar ('teyitsiz' yok)", async () => {
    mockTeyit = true;
    const u = await kur();
    await act(async () => {
      fireEvent.press(u.getByLabelText("Acil durdur"));
    });
    const teyitli = dizi.map((m) => (m.type === "estop_teyit" ? { ...m, data: { ...m.data, teyitli: true } } : m));
    await gonder(teyitli);
    expect(u.queryByLabelText("Acil durdur")).toBeNull();
  });
});
