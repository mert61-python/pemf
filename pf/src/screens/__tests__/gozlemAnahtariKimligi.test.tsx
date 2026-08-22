// Author: mertaygn, cglrgrkn
/**
 * GÖZLEM MODALI SEANS KİMLİĞİ — 2. tur denetimi [4.1] KABLOLAMA yarısı (2026-08-20).
 *
 * Modal sözleşmesi (`obsKey` değişti → sıfırla) gozlemNotuKorunmasi.test.tsx'te; BU dosya
 * ControlScreen'in o anahtarı GERÇEKTEN ürettiğini kilitler: her seans (isActive yükselen
 * kenarı) YENİ bir obsKey almalı — aksi hâlde aynı isimli iki hastada modal sözleşmesi
 * hiç tetiklenemez ve A'nın notu B'nin tıbbi kaydına gider.
 *
 * ⚠️ DAVRANIŞSAL: gerçek ControlScreen çizilir, mock'lanmış hook'un isActive'i iki tam
 * seans döngüsünde (aktif→pasif ×2) çevrilir; modal'a GİDEN session prop'ları yakalanır.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const yakalananlar: any[] = [];
jest.mock("@/components/domain/ObservationNotesModal", () => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ObservationNotesModal: (props: any) => {
    yakalananlar.push({ visible: props.visible, session: props.session });
    return null;
  },
}));

let mockAktif = false;
jest.mock("@/hooks/useSessionControl", () => ({
  useSessionControl: () => ({
    isActive: mockAktif,
    treatment: mockAktif
      ? { mode: "Manuel", frequencyHz: 10, intensityMt: 1, durationSec: 600 }
      : null,
    elapsedSec: 0,
    remainingSec: 600,
    loading: false,
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
  // bobinler DURUYOR → hardwareRunningOutOfSession false (modal görünürlüğü serbest)
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

import { act, render } from "@testing-library/react-native";
import React from "react";

import { ControlScreen } from "@/screens/ControlScreen";

async function seansDongusu(u: ReturnType<typeof render>) {
  mockAktif = true;
  u.rerender(<ControlScreen />);
  await act(async () => {});
  mockAktif = false;
  u.rerender(<ControlScreen />);
  await act(async () => {});
}

it("KRİTİK [2.tur 4.1]: her seans modal'a FARKLI obsKey taşır (aynı-isim kimlik ayracı)", async () => {
  yakalananlar.length = 0;
  mockAktif = false;
  const u = render(<ControlScreen />);
  await act(async () => {});

  await seansDongusu(u); // 1. seans: başla → bitir
  const ilk = [...yakalananlar].reverse().find((y) => y.session)?.session;
  await seansDongusu(u); // 2. seans (AYNI hasta adı "Boncuk")
  const ikinci = [...yakalananlar].reverse().find((y) => y.session)?.session;

  expect(ilk?.patientName).toBe("Boncuk");
  expect(ikinci?.patientName).toBe("Boncuk");
  expect(typeof ilk?.obsKey).toBe("number");
  expect(typeof ikinci?.obsKey).toBe("number");
  expect(ikinci?.obsKey).not.toBe(ilk?.obsKey);
});
