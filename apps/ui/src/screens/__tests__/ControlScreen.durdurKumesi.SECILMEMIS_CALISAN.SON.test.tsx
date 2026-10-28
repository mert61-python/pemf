// Author: mertaygn, cglrgrkn
/**
 * SON-A1.7 (22-SON A1a §5 · İG-6.32 farklı yöntemle) — Kontrol ekranı "Durdur": seçimden ÇIKARILMIŞ ama ÇALIŞAN bobine de STOP gider.
 * ==============================================================================================================================
 * `ControlScreen.handleStopManual` notu: "DURDURULACAK KÜME: 'o an SEÇİLİ olanlar' DEĞİL, 'gerçekten ÇALIŞANLAR + seçili olanlar'. Kullanıcı
 * bir bobini başlattıktan sonra seçimden çıkarırsa 'Durdur' o bobine hiç komut göndermiyordu → hayvanın üzerinde sessizce enerjili kalıyordu."
 * ÖLÇÜLEN KÖRLÜK (uç 8b002fc0): küme kurulurken `...runningIds` düşürülünce `ControlScreen`'i anan 22 jest dosyası 200 / 200 YEŞİL.
 *
 * GERÇEK: `ControlScreen` (+ gerçek `apiClient` / `useSessionControl`). Sahte EN ALT katta: `global.fetch` (yol + gövde kaydedici) ve ekran
 * kabuğu bağlamları (`ControlScreen.IG634_635` aparatıyla AYNI). Ö.4-Y8: yalnız kapı — durdurma davranışı değişmez.
 */
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api", bridgeBaseUrl: "http://127.0.0.1:8000/api", apiToken: "" },
}));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn(() => true) }));
jest.mock("@/services/deviceRegistry", () => ({ getRemoteUrlForDevice: jest.fn(async () => null) }));
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));
let mockSnap: Record<string, unknown>;
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({
    snapshot: mockSnap, wsConnected: true, connectionQuality: "live", haveRealData: true,
    telemetryStale: false, sensorHistory: {}, unreadCount: 0, markAllRead: jest.fn(),
    clearNotifications: jest.fn(), refresh: jest.fn(), reconnect: jest.fn(), aiVisionFresh: false,
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
const mockHasta = { id: "1", name: "Boncuk" };
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({
    navigate: jest.fn(), goTo: jest.fn(), navigateTo: jest.fn(),
    selectedPatient: mockHasta, setSelectedPatient: jest.fn(),
  }),
}));
jest.mock("@/components/domain/AiProPanel", () => ({ AiProPanel: () => null }));
jest.mock("@/components/domain/EFieldBar", () => ({ EFieldBar: () => null }));
jest.mock("@/components/domain/ObservationNotesModal", () => ({ ObservationNotesModal: () => null }));
jest.mock("@/components/domain/CoilParameterPanel", () => ({ CoilParameterPanel: () => null }));

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";
import { Alert } from "react-native";
import { ControlScreen } from "@/screens/ControlScreen";

const istekler: { yol: string; govde: Record<string, unknown> }[] = [];
const yanit = (o: unknown) =>
  Promise.resolve({ ok: true, status: 200, json: async () => o, text: async () => JSON.stringify(o) });

const bobinler = (calisan: number[]) =>
  [1, 2, 3, 4, 5, 6, 7].map((id) => ({
    id, running: calisan.includes(id), connected: true, stm32Driven: true, frequencyHz: 0, dutyCycle: 0,
    objectTemp: 0, magneticMt: 0, currentA: 0, ambientTemp: 0, measuredFields: [],
  }));

beforeEach(() => {
  istekler.length = 0;
  jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
  jest.spyOn(console, "error").mockImplementation(() => {});
  (global as { fetch: unknown }).fetch = jest.fn((url: string, init?: { body?: string }) => {
    const yol = String(url).replace("http://127.0.0.1:8000/api", "");
    let govde: Record<string, unknown> = {};
    try {
      govde = JSON.parse(init?.body ?? "{}");
    } catch {
      govde = {};
    }
    istekler.push({ yol, govde });
    if (yol === "/session/active") return yanit({ is_active: false });
    return yanit({ status: "success", results: [] });
  });
  mockSnap = {
    gateway: "devre_disi", mqtt: "devre_disi", stm: "online",
    patient: null,
    activeTreatment: { isActive: false, mode: "Sistem Hazır", frequencyHz: 0, intensityMt: 0, remainingMin: 0, elapsedSec: 0, durationSec: 0 },
    notifications: [],
    coils: bobinler([3]),
    system: {}, sessions: [],
  };
});
afterEach(() => jest.restoreAllMocks());

it("KRİTİK: çalışan bobin 3 seçimden ÇIKARILDIKTAN sonra 'Durdur' STOP kümesinde bobin 3'ü TAŞIR", async () => {
  const u = render(<ControlScreen />);
  await act(async () => {});
  const secili3 = u.getAllByLabelText("Bobin 3, seçili, çevrimiçi");
  expect(secili3.length).toBeGreaterThan(0); // aparat: varsayılan seçim tüm slotlar; bobin 3 seçili
  await act(async () => {
    fireEvent.press(secili3[secili3.length - 1]);
  });
  expect(u.queryAllByLabelText("Bobin 3, seçili değil, çevrimiçi").length).toBeGreaterThan(0); // aparat: seçimden çıktı
  istekler.length = 0;
  await act(async () => {
    fireEvent.press(u.getByText("⏹ Durdur"));
  });
  await act(async () => {});
  const toplu = istekler.filter((i) => i.yol === "/coil/batch" && i.govde.start === false);
  expect(toplu.length).toBeGreaterThan(0); // aparat: STM durdurma toplu isteği gitti
  const hedefler = toplu.flatMap((i) => (Array.isArray(i.govde.coil_ids) ? (i.govde.coil_ids as number[]) : []));
  expect({ bobin3Durduruldu: hedefler.includes(3), hedefler }).toEqual({ bobin3Durduruldu: true, hedefler });
  u.unmount();
});
