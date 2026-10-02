// Author: mertaygn, cglrgrkn
/**
 * A-47 / Y2 · 1-D inceleme i2-F-2 — Kontrol EKRANI düzeyinde otomatik termal STOP YOK.
 * Ölçülen körlük: ControlScreen testleri `CoilParameterPanel`'i sahteyle değiştirip bobinleri 30 °C ile kurar → ekran
 * düzeyinde geri eklenen "ölçülen > 48 °C → /coil/{id}/control {start:false}" bütün suite'lerde yeşil kalıyordu.
 * Burada GERÇEK panel çizilir: bobin 6-7 ölçülen 60 °C + çalışıyor → durdurma isteği yok, iki görsel uyarı var.
 */
const mockApiPost = jest.fn(async () => ({ status: "success" }));

jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => null),
  apiPost: (...a: unknown[]) => mockApiPost(...(a as [])),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  authHeaders: jest.fn(() => ({})),
}));
jest.mock("@/hooks/useSessionControl", () => ({
  useSessionControl: () => ({
    isActive: true, treatment: null, elapsedSec: 0, remainingSec: 600,
    loading: false, stopping: false, error: null, lastError: () => null,
    startSession: jest.fn(), stopSession: jest.fn(), emergencyStop: jest.fn(),
  }),
}));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://x/api" } }));
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));

const mockSnap = {
  gateway: "online", mqtt: "online", stm: "online",
  patient: { name: "Boncuk", species: "Kedi", breed: "", owner: "S" },
  activeTreatment: { isActive: true, mode: "Manuel", frequencyHz: 100, intensityMt: 1, remainingMin: 10, elapsedSec: 0, durationSec: 600 },
  notifications: [],
  coils: Array.from({ length: 7 }, (_, i) => ({
    id: i + 1, running: true, connected: true, stm32Driven: true, frequencyHz: 100, dutyCycle: 40,
    objectTemp: i >= 5 ? 60 : 0, magneticMt: 1, currentA: 0, ambientTemp: 25,
    measuredFields: i >= 5 ? ["objectTemp", "magneticMt"] : [],
  })),
  system: {}, sessions: [],
};
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
jest.mock("@/components/domain/SessionProgressCard", () => ({ SessionProgressCard: () => null }));
jest.mock("@/components/domain/AiProPanel", () => ({ AiProPanel: () => null }));
jest.mock("@/components/domain/EFieldBar", () => ({ EFieldBar: () => null }));
jest.mock("@/components/domain/ObservationNotesModal", () => ({ ObservationNotesModal: () => null }));
jest.mock("@/components/domain/PatientGate", () => ({
  PatientGate: ({ children }: { children: React.ReactNode }) => children,
}));

import { act, render } from "@testing-library/react-native";
import React from "react";

import { ControlScreen } from "@/screens/ControlScreen";

it("KRİTİK: ölçülen 60 °C'de çalışan bobin 6-7 varken ekran kendiliğinden durdurma isteği ATMAZ (A-47)", async () => {
  mockApiPost.mockClear();
  const u = render(<ControlScreen />);
  await act(async () => {});
  await act(async () => {});
  const durdurma = mockApiPost.mock.calls.filter(
    (c: any[]) => /control|stop|emergency/.test(String(c[0])) && (c[1]?.start === false || /stop|emergency/.test(String(c[0]))),
  );
  expect(durdurma).toEqual([]);
  expect(u.getAllByTestId("sicaklik-uyarisi").length).toBe(2);
});
