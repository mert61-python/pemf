// Author: mertaygn, cglrgrkn
/**
 * AP · B1 (S-AP.1, sahip 13 Kasım 2026 "Seans sürsün"): Sensörler'e gidip dönünce Kontrol ekranı SON SEKMEYLE açılır — AI Pro seansı
 * sürerken dönen kullanıcı "Manuel" değil "AI Pro" görür. Bellek AppNav sağlayıcısında (uygulama oturumu, kalıcı değil); yoksa eskisi gibi
 * "Manuel". Mock düzeni `ControlScreen.I18N.P1.kritik.test.tsx` ile aynı.
 */
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api", bridgeBaseUrl: "http://127.0.0.1:8000/api", apiToken: "" },
}));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn(() => true) }));
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));
let mockSnap: any;
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({
    snapshot: mockSnap, wsConnected: true, connectionQuality: "live", haveRealData: true,
    telemetryStale: false, sensorHistory: {}, unreadCount: 0, markAllRead: jest.fn(),
    clearNotifications: jest.fn(), refresh: jest.fn(), reconnect: jest.fn(), aiVisionFresh: false,
  }),
}));
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: "researcher" }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operator: "Dr. X" }) }));
let mockHafiza: { current: Record<string, unknown> } | undefined;
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigate: jest.fn(), goTo: jest.fn(), selectedPatient: null, kontrolHafizasi: mockHafiza }),
}));
jest.mock("@/components/domain/AiProPanel", () => ({ AiProPanel: () => null }));
jest.mock("@/components/domain/EFieldBar", () => ({ EFieldBar: () => null }));
jest.mock("@/components/domain/ObservationNotesModal", () => ({ ObservationNotesModal: () => null }));
jest.mock("@/components/domain/CoilParameterPanel", () => ({ CoilParameterPanel: () => null }));
jest.mock("@/components/domain/PatientGate", () => ({
  PatientGate: ({ children }: { children: React.ReactNode }) => children,
}));

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";
import { ControlScreen } from "@/screens/ControlScreen";

const yanit = (o: unknown) =>
  Promise.resolve({ ok: true, status: 200, json: async () => o, text: async () => JSON.stringify(o) });

beforeEach(() => {
  (global as any).fetch = jest.fn((url: string) => {
    const yol = String(url).replace("http://127.0.0.1:8000/api", "");
    if (yol === "/session/active") return yanit({ is_active: false });
    return yanit({ status: "success" });
  });
  mockSnap = {
    gateway: "devre_disi", mqtt: "devre_disi", stm: "online",
    patient: { name: "Boncuk", species: "Kedi", breed: "", owner: "S" },
    activeTreatment: { isActive: false, mode: "Sistem Hazır", frequencyHz: 0, intensityMt: 0, remainingMin: 0, elapsedSec: 0, durationSec: 0 },
    notifications: [],
    coils: [1, 2, 3, 4, 5, 6, 7, 8].map((id) => ({
      id, running: false, connected: id < 8, stm32Driven: id < 8, frequencyHz: 0, dutyCycle: 0,
      objectTemp: 0, magneticMt: 0, currentA: 0, ambientTemp: 0, measuredFields: [],
    })),
    system: {}, sessions: [],
  };
});

const sekme = (u: ReturnType<typeof render>, ad: string) => u.getByLabelText(ad).props.accessibilityState?.selected;

it("KRİTİK S-AP.1: AI Pro sekmesinden başka ekrana gidip dönünce Kontrol AI Pro sekmesiyle açılır", async () => {
  mockHafiza = { current: {} };
  const u = render(<ControlScreen />);
  await act(async () => {});
  expect(sekme(u, "Manuel")).toBe(true);
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro")); });
  expect(sekme(u, "AI Pro")).toBe(true);
  u.unmount(); // rota değişimi (Sensörler) ekranı söker
  const u2 = render(<ControlScreen />);
  await act(async () => {});
  expect(sekme(u2, "AI Pro")).toBe(true);
  u2.unmount();
});

it("bellek yoksa (sağlayıcısız çizim) eskisi gibi Manuel sekmesiyle açılır", async () => {
  mockHafiza = undefined;
  const u = render(<ControlScreen />);
  await act(async () => {});
  expect(sekme(u, "Manuel")).toBe(true);
  u.unmount();
});
