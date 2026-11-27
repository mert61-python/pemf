// Author: mertaygn, cglrgrkn
/**
 * Y330 karşıt kolu: yerel (native) RN `sticky` desteklemez — orada düğme bugünkü gibi AKIŞTA (APK derlenmiyor; yine de yerel yapı
 * bozulmasın). Düğme her iki platformda da çizilir ve basış aynı yoldur (web kapısı: ControlScreen.Y330.yapiskanAcilDurdur.web).
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "android";
  return RN;
});
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api", bridgeBaseUrl: "http://127.0.0.1:8000/api", apiToken: "" },
}));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn(() => true) }));
jest.mock("@/services/deviceRegistry", () => ({ getRemoteUrlForDevice: jest.fn(async () => null) }));
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({
    snapshot: {
      gateway: "devre_disi", mqtt: "devre_disi", stm: "online", patient: null,
      activeTreatment: { isActive: false, mode: "Sistem Hazır", frequencyHz: 0, intensityMt: 0, remainingMin: 0, elapsedSec: 0, durationSec: 0 },
      notifications: [], coils: [], system: {}, sessions: [],
    },
    wsConnected: true, connectionQuality: "live", haveRealData: true, telemetryStale: false, sensorHistory: {}, unreadCount: 0,
    markAllRead: jest.fn(), clearNotifications: jest.fn(), refresh: jest.fn(), reconnect: jest.fn(), aiVisionFresh: false,
    donanimBelirsiz: false,
  }),
}));
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ userMode: "veterinarian", isExpert: true, isResearcher: false }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({
  useOperator: () => ({ operator: "Dr. X" }),
  useOperatorOptional: () => null,
}));
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({
    navigate: jest.fn(), goTo: jest.fn(), navigateTo: jest.fn(),
    selectedPatient: { id: "1", name: "Boncuk" }, setSelectedPatient: jest.fn(),
  }),
}));
jest.mock("@/components/domain/AiProPanel", () => ({ AiProPanel: () => null }));
jest.mock("@/components/domain/EFieldBar", () => ({ EFieldBar: () => null }));
jest.mock("@/components/domain/ObservationNotesModal", () => ({ ObservationNotesModal: () => null }));
jest.mock("@/components/domain/CoilParameterPanel", () => ({ CoilParameterPanel: () => null }));

import { act, render } from "@testing-library/react-native";
import React from "react";
import { StyleSheet } from "react-native";
import { ControlScreen } from "@/screens/ControlScreen";

beforeEach(() => {
  (global as { fetch: unknown }).fetch = jest.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: async () => ({ is_active: false }), text: async () => "{}" }),
  );
  jest.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(() => jest.restoreAllMocks());

it("KARŞIT Y330: yerelde düğme çizilir ve AKIŞTA kalır (sticky YOK)", async () => {
  const u = render(<ControlScreen />);
  await act(async () => {});
  const stil = StyleSheet.flatten(u.getByTestId("kontrol-acil-durdur-tum").props.style) as Record<string, unknown>;
  expect(stil.position).not.toBe("sticky");
  expect(u.queryAllByLabelText("Tüm bobinleri acil durdur")).toHaveLength(1);
  u.unmount();
});
