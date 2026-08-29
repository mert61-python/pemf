// Author: mertaygn, cglrgrkn
/**
 * DOZ KAYNAĞI ROZETİ — sessiz wellness düşüşünün ekrandaki karşılığı (denetim 2026-08-28 #01).
 *
 * Backend `/hardware/auto_preset`, seçilen hedefin literatürde karşılığı yoksa SESSİZCE genel
 * (wellness) dozunu döndürüyordu: `source: "default_wellness"`. Bu alan yanıtta zaten VARDI ama
 * arayüz hiç okumuyordu — ekranda tek bir fark yoktu. Vet "Enflamasyon Azaltma" seçip 87 Hz
 * beklerken 77 Hz alıyor, farkı göremiyordu; seans kaydına da o hedef adı yazılıyordu.
 *
 * Sözlük tarafı (hangi hedef hangi dozu alır) `tests/test_literatur_hedef_sozlesmesi.py`'de
 * kilitli. BU dosya kablolamayı kilitler: kaynak neyse ekranda karşılığı görünsün.
 *
 * ⚠️ Düşüş yolunun KENDİSİ korunuyor: karşılıksız hedefte yine doz döner (seans engellenmez),
 * yalnız artık sessiz değil.
 */
let mockKaynak = "literature_exact";
const mockApiPost = jest.fn(async () => ({
  status: "success",
  parameters: { freq: 87, duty: 47, duration: 27, intensity: 1.25, source: mockKaynak },
}));

jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => null),
  apiPost: (...a: unknown[]) => mockApiPost(...(a as [])),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  authHeaders: jest.fn(() => ({})),
}));

jest.mock("@/hooks/useSessionControl", () => ({
  useSessionControl: () => ({
    isActive: false, treatment: null, elapsedSec: 0, remainingSec: 600,
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
  activeTreatment: { isActive: false, mode: "Manuel", frequencyHz: 10, intensityMt: 1, remainingMin: 10, elapsedSec: 0, durationSec: 600 },
  notifications: [],
  coils: Array.from({ length: 8 }, (_, i) => ({
    id: i + 1, running: false, connected: true, freq: 10, duty: 0.2, temperature: 30, objectTemp: 30, magneticMt: 1,
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
jest.mock("@/components/domain/CoilParameterPanel", () => ({ CoilParameterPanel: () => null }));
jest.mock("@/components/domain/AiProPanel", () => ({ AiProPanel: () => null }));
jest.mock("@/components/domain/EFieldBar", () => ({ EFieldBar: () => null }));
jest.mock("@/components/domain/ObservationNotesModal", () => ({ ObservationNotesModal: () => null }));
jest.mock("@/components/domain/PatientGate", () => ({
  PatientGate: ({ children }: { children: React.ReactNode }) => children,
}));

import { act, fireEvent, render, screen } from "@testing-library/react-native";
import React from "react";

import { ControlScreen } from "@/screens/ControlScreen";

/** Otomatik sekmesini aç ve bir hedef çipine bas (auto_preset çağrısını tetikler). */
async function hedefSec(hedef: string) {
  const u = render(<ControlScreen />);
  await act(async () => {});
  fireEvent.press(screen.getByText("Otomatik"));
  await act(async () => {});
  fireEvent.press(screen.getByText(hedef));
  await act(async () => {});
  return u;
}

beforeEach(() => {
  mockApiPost.mockClear();
  mockKaynak = "literature_exact";
});

it("KRİTİK: literatür karşılığı YOKSA operatör uyarılır (sessiz wellness düşüşü görünür olur)", async () => {
  mockKaynak = "default_wellness";
  await hedefSec("Enflamasyon Azaltma");

  expect(mockApiPost).toHaveBeenCalled();
  expect(screen.getByText(/literatür protokolü yok/i)).toBeTruthy();
  expect(screen.getByText(/genel \(wellness\) dozu/i)).toBeTruthy();
});

it("literatür protokolü uygulandığında yanıltıcı uyarı GÖSTERİLMEZ", async () => {
  mockKaynak = "literature_exact";
  await hedefSec("Enflamasyon Azaltma");

  expect(screen.queryByText(/literatür protokolü yok/i)).toBeNull();
  expect(screen.getByText(/Literatür protokolü uygulandı/i)).toBeTruthy();
});

it("düşüş yolu KORUNUR: karşılıksız hedefte parametreler yine dolar (seans engellenmez)", async () => {
  mockKaynak = "default_wellness";
  await hedefSec("Sinir Rejenerasyonu");

  // Backend'in döndürdüğü değerler alanlara yazılmış olmalı — uyarı bilgilendirmedir, blokaj değil.
  expect(screen.getByDisplayValue("87")).toBeTruthy();
  expect(screen.getByDisplayValue("27")).toBeTruthy();
});
