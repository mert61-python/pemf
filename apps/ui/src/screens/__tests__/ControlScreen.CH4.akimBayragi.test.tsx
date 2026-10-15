// Author: mertaygn, cglrgrkn
/**
 * CH4 · Y154 — Kontrol ekranı akım sensörü bayrağını (`snapshot.akimOlcumu`) bobin panellerine GEÇİRİR.
 * ===================================================================================================
 * Panelin kendisi `akimOlcumu` prop'uyla "A" okumasını çizer / gizler (akimSensoruKapali.CH4.test.tsx). Bu kapı ekranın bayrağı
 * GERÇEKTEN geçirdiğini ölçer (saf işlev testi ekranın çağırdığını görmez — Ö.7): kapalı / eksik → false, açık → true.
 * GERÇEK: `ControlScreen`, `gorunurBobinler`, `akimOlcumuAcik`; sahte olan bağlamlar, `fetch` ve panelin kendisi (prop yakalayıcı).
 * ⚠️ MUTASYON: ekran `akimOlcumu={true}` ya da sabit geçirirse KIRMIZI.
 */
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:65530/api", bridgeBaseUrl: "http://127.0.0.1:65530/api", apiToken: "" },
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
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: "veterinarian" }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operator: "Dr. X" }) }));
jest.mock("@/context/AppNavContext", () => ({ useAppNav: () => ({ navigate: jest.fn(), goTo: jest.fn() }) }));
jest.mock("@/components/domain/AiProPanel", () => ({ AiProPanel: () => null }));
jest.mock("@/components/domain/EFieldBar", () => ({ EFieldBar: () => null }));
jest.mock("@/components/domain/ObservationNotesModal", () => ({ ObservationNotesModal: () => null }));
const mockPanelProps: any[] = [];
jest.mock("@/components/domain/CoilParameterPanel", () => ({
  CoilParameterPanel: (p: any) => {
    mockPanelProps.push(p);
    return null;
  },
}));
jest.mock("@/components/domain/PatientGate", () => ({
  PatientGate: ({ children }: { children: React.ReactNode }) => children,
}));

import { act, render } from "@testing-library/react-native";
import React from "react";
import { Alert } from "react-native";
import { ControlScreen } from "@/screens/ControlScreen";

const yanit = (o: unknown) =>
  Promise.resolve({ ok: true, status: 200, json: async () => o, text: async () => JSON.stringify(o) });

beforeEach(() => {
  mockPanelProps.length = 0;
  jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
  (global as any).fetch = jest.fn(() => yanit({ status: "success" }));
});

async function ciz(akimOlcumu: boolean | undefined) {
  mockSnap = {
    gateway: "devre_disi", mqtt: "devre_disi", stm: "online",
    patient: { name: "", species: "", breed: "", owner: "" },
    activeTreatment: { isActive: false }, notifications: [],
    coils: [1, 2, 3, 4, 5, 6, 7].map((id) => ({ id, connected: true, running: false, currentA: 1.234, measuredFields: ["currentA"] })),
  };
  if (akimOlcumu !== undefined) mockSnap.akimOlcumu = akimOlcumu;
  render(<ControlScreen />);
  await act(async () => {});
  expect(mockPanelProps.length).toBeGreaterThan(0); // vakum değil: paneller çizildi
  return mockPanelProps.map((p) => p.akimOlcumu);
}

it.each([
  ["false", false],
  ["eksik (eski backend)", undefined],
])("KRİTİK bayrak %s → her panele akimOlcumu=false", async (_ad, bayrak) => {
  const degerler = await ciz(bayrak);
  expect(new Set(degerler)).toEqual(new Set([false]));
});

it("KARŞIT bayrak true → her panele akimOlcumu=true", async () => {
  const degerler = await ciz(true);
  expect(new Set(degerler)).toEqual(new Set([true]));
});
