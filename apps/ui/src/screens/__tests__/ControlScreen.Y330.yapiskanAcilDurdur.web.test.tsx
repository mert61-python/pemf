// Author: mertaygn, cglrgrkn
/**
 * Y330 (sahip 26-11; Y60 DEĞİŞTİ · istem 63 YS2 f): Kontrol ekranında aşağı kaydırınca "TÜM BOBİNLERİ ACİL DURDUR" görünür alandan
 * çıkıyordu (görünürde yalnız tek bobin "Bobini durdur" düğmeleri kalıyordu). YENİ DÜĞME EKLENMEZ — ekranın KENDİ düğmesi kaydırırken
 * SABİT (yapışkan) kalır: üç istemci de react-native-web → CSS `position: sticky` (kaydırma kabı AppShell ScrollView'ı; düğme akıştaki
 * yerini korur → hiçbir denetimi kalıcı örtmez). Basınca AYNI `performEmergencyStop` yolu (aynı 4 durdurma isteği — İG-6.34 kapısıyla
 * bit bit aynı). Ekranda TEK "tüm bobinler" düğmesi (yeni düğme yok); A-51 işareti aynen.
 * ⚠️ jsdom yerleşim / kaydırma hesaplamaz: "kaydırılmış ekranda görünür" sözleşmesi düğmenin yapışkan stiliyle ölçülür (CSS sticky tarayıcıda
 * kaydırma kabının üst kenarına yapışır); gerçek kaydırma tezgâh listesinde (masaüstü + telefon).
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
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

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";
import { Alert, StyleSheet } from "react-native";
import { ControlScreen } from "@/screens/ControlScreen";

const cagrilar: string[] = [];
const yanit = (o: unknown) =>
  Promise.resolve({ ok: true, status: 200, json: async () => o, text: async () => JSON.stringify(o) });
const ESTOP_DORTLU = ["/hardware/command", "/hardware/emergency_stop", "/hardware/emergency_stop", "/session/stop"];

beforeEach(() => {
  cagrilar.length = 0;
  jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
  jest.spyOn(console, "error").mockImplementation(() => {});
  (global as { fetch: unknown }).fetch = jest.fn((url: string) => {
    const yol = String(url).replace("http://127.0.0.1:8000/api", "");
    cagrilar.push(yol);
    if (yol === "/session/active") return yanit({ is_active: false });
    if (yol === "/hardware/emergency_stop") return yanit({ confirmed: true, status: "success" });
    return yanit({ status: "success" });
  });
  mockSnap = {
    gateway: "devre_disi", mqtt: "devre_disi", stm: "online", patient: null,
    activeTreatment: { isActive: false, mode: "Sistem Hazır", frequencyHz: 0, intensityMt: 0, remainingMin: 0, elapsedSec: 0, durationSec: 0 },
    notifications: [],
    coils: [1, 2, 3, 4, 5, 6, 7].map((id) => ({
      id, running: id === 1, connected: true, stm32Driven: true, frequencyHz: 0, dutyCycle: 0,
      objectTemp: 0, magneticMt: 0, currentA: 0, ambientTemp: 0, measuredFields: [],
    })),
    system: {}, sessions: [],
  };
});
afterEach(() => jest.restoreAllMocks());

const durdurmalar = () => cagrilar.filter((y) => /\/hardware\/emergency_stop|\/hardware\/command|\/session\/stop/.test(y)).sort();

it("KRİTİK Y330: ekranın KENDİ 'Tüm bobinleri acil durdur' düğmesi kaydırırken yapışkan (sticky, üstte, katmanda önde)", async () => {
  const u = render(<ControlScreen />);
  await act(async () => {});
  const dugmeler = u.queryAllByLabelText("Tüm bobinleri acil durdur");
  expect(dugmeler).toHaveLength(1); // YENİ düğme eklenmedi
  const stil = StyleSheet.flatten(u.getByTestId("kontrol-acil-durdur-tum").props.style) as Record<string, unknown>;
  expect(stil.position).toBe("sticky");
  expect(typeof stil.top).toBe("number");
  expect(Number(stil.top)).toBeGreaterThanOrEqual(0);
  expect(Number(stil.zIndex)).toBeGreaterThanOrEqual(10);
  expect(stil.position).not.toBe("fixed"); // akıştaki yerini korur → hiçbir denetimi kalıcı örtmez
  u.unmount();
});

it("KRİTİK Y330: yapışkan düğmeye basış AYNI acil durdurma yolunu çağırır (4 durdurma isteği)", async () => {
  const u = render(<ControlScreen />);
  await act(async () => {});
  await act(async () => {
    fireEvent.press(u.getByTestId("kontrol-acil-durdur-tum"));
  });
  await act(async () => {});
  expect(durdurmalar()).toEqual(ESTOP_DORTLU);
  u.unmount();
});
