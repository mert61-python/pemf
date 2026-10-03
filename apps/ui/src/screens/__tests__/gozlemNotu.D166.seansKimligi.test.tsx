// Author: mertaygn, cglrgrkn
/**
 * D1.66 · B-1.2 — gözlem notu SEANS KİMLİĞİYLE gönderilir (kablolama: kanca → ControlScreen → modal → istek).
 *
 * ÖLÇÜLEN KUSUR: istemci `/api/session/notes`'a seans kimliği göndermiyordu; sunucu süreçteki SON seansı hedef alıyordu →
 * A hastasının notu, arada başlamış B hastasının satırına düşüyordu (B sürerken onu kapatıyordu). Sunucu artık
 * `session_id` alırsa YALNIZ o satıra yazar; bu dosya istemcinin onu GERÇEKTEN gönderdiğini kilitler.
 * ⚠️ DAVRANIŞSAL: gerçek ControlScreen + gerçek modal çizilir; giden istek gövdesi yakalanır.
 */
let mockAktif = false;
let mockDbSeans: number | null = null;
jest.mock("@/hooks/useSessionControl", () => ({
  useSessionControl: () => ({
    isActive: mockAktif,
    treatment: mockAktif ? { mode: "Manuel", frequencyHz: 10, intensityMt: 1, durationSec: 600 } : null,
    dbSessionId: mockDbSeans,
    elapsedSec: 0,
    remainingSec: 600,
    loading: false,
    starting: false,
    sessionStopping: false,
    stopping: false,
    error: null,
    lastError: () => null,
    startSession: jest.fn(),
    stopSession: jest.fn(),
    emergencyStop: jest.fn(),
  }),
}));

jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => null),
  apiPost: jest.fn(async () => ({ status: "success" })),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  authHeaders: jest.fn(() => ({})),
}));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://x/api" } }));
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));

const mockSnap = {
  gateway: "online",
  mqtt: "online",
  stm: "online",
  patient: { name: "Boncuk", species: "Kedi", breed: "", owner: "S" },
  activeTreatment: {
    isActive: false, mode: "Manuel", frequencyHz: 10, intensityMt: 1,
    remainingMin: 10, elapsedSec: 0, durationSec: 600,
  },
  notifications: [],
  coils: Array.from({ length: 8 }, (_, i) => ({
    id: i + 1, running: false, freq: 10, duty: 0.2, temperature: 30, objectTemp: 30, magneticMt: 1,
  })),
  system: {},
  sessions: [],
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
jest.mock("@/components/domain/CoilParameterPanel", () => ({ CoilParameterPanel: () => null }));
jest.mock("@/components/domain/AiProPanel", () => ({ AiProPanel: () => null }));
jest.mock("@/components/domain/EFieldBar", () => ({ EFieldBar: () => null }));
jest.mock("@/components/domain/PatientGate", () => ({
  PatientGate: ({ children }: { children: React.ReactNode }) => children,
}));

import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import React from "react";

import { apiPost } from "@/services/apiClient";
import { ControlScreen } from "@/screens/ControlScreen";

const notIstekleri = () =>
  (apiPost as jest.Mock).mock.calls.filter((c) => c[0] === "/session/notes").map((c) => c[1] as Record<string, unknown>);

async function seansBitirVeNotKaydet(dbSeans: number | null) {
  (apiPost as jest.Mock).mockClear();
  mockAktif = false;
  mockDbSeans = null;
  const u = render(<ControlScreen />);
  await act(async () => {});
  mockAktif = true;
  mockDbSeans = dbSeans;
  u.rerender(<ControlScreen />);
  await act(async () => {});
  mockAktif = false; // seans bitti → gözlem modalı açılır (kimlik bitişten sonra da korunur)
  u.rerender(<ControlScreen />);
  await act(async () => {});
  fireEvent.press(u.getByText("💾 Kaydet"));
  await waitFor(() => expect(notIstekleri().length).toBe(1));
  return notIstekleri()[0];
}

it("KRİTİK D1.66: seans bitince gözlem notu O seansın DB kimliğiyle gönderilir", async () => {
  const govde = await seansBitirVeNotKaydet(42);
  expect(govde.session_id).toBe(42);
  expect(govde.patient_name).toBe("Boncuk");
});

it("KARŞIT: kimlik bilinmiyorsa (eski sunucu) alan gönderilmez — sunucu eski istemci dalına düşer", async () => {
  const govde = await seansBitirVeNotKaydet(null);
  expect("session_id" in govde).toBe(false);
});
