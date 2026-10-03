// Author: mertaygn, cglrgrkn
/**
 * D1.89 · İG-6.11 (b) + İNCELEME-2 §10 #5 — Kontrol ekranı seans kartı ÖLÇÜLEN yoğunluğu WS `activeTreatment`ten gösterir;
 * AI Pro'nun bobin 1 duty'si "YOĞUNLUK (kayıt) … mT" DEĞİL, "DUTY … %" olarak görünür.
 * ===================================================================================================================
 * ÖLÇÜLEN KUSUR (aday İG-6.11, gerçek web + alan telemetrisi: REST `measuredIntensityMt: 2.345` iken kartta "YOĞUNLUK
 * (ölçülen)" YOK): kart yalnız `useSessionControl`ün yerel kopyasını okuyordu; o kopya ölçülen alanı HİÇ doldurmuyor.
 * AI Pro'da kart (Kontrol açılışta `/session/active` okur, AI seansında `intensity` yok) "YOĞUNLUK (kayıt) 0 mT" yazıyordu.
 *
 * Veri ELLE YAZILMADI: `/session/active` yanıtı ve WS `activeTreatment` `__fixtures__/kayitGorunumu.D189.json`dan (GERÇEK
 * backend; bayatlık kapısı `tests/test_D189_…`). GERÇEK: `ControlScreen`, `useSessionControl`, `apiClient`,
 * `SessionProgressCard`; sahte olan `fetch` ve bağlamlar.
 * ⚠️ MUTASYON: kart yeniden yalnız yerel kopyaya bağlanırsa ya da duty temsili geçirilmezse KIRMIZI.
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
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: "veterinarian" }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operator: "Dr. X" }) }));
jest.mock("@/context/AppNavContext", () => ({ useAppNav: () => ({ navigate: jest.fn(), goTo: jest.fn() }) }));
jest.mock("@/components/domain/AiProPanel", () => ({ AiProPanel: () => null }));
jest.mock("@/components/domain/EFieldBar", () => ({ EFieldBar: () => null }));
jest.mock("@/components/domain/ObservationNotesModal", () => ({ ObservationNotesModal: () => null }));
jest.mock("@/components/domain/CoilParameterPanel", () => ({ CoilParameterPanel: () => null }));
jest.mock("@/components/domain/PatientGate", () => ({
  PatientGate: ({ children }: { children: React.ReactNode }) => children,
}));

import { act, render } from "@testing-library/react-native";
import React from "react";
import { Alert } from "react-native";
import { ControlScreen } from "@/screens/ControlScreen";

const F: any = require("./__fixtures__/kayitGorunumu.D189.json");
let mockAktif: unknown;
const yanit = (o: unknown) =>
  Promise.resolve({ ok: true, status: 200, json: async () => o, text: async () => JSON.stringify(o) });

beforeEach(() => {
  jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
  (global as any).fetch = jest.fn((url: string) => {
    const yol = String(url).replace("http://127.0.0.1:8000/api", "");
    if (yol === "/session/active") return yanit(mockAktif);
    return yanit({ status: "success" });
  });
});

async function kart(aktif: unknown, at: unknown) {
  mockAktif = aktif;
  mockSnap = {
    gateway: "devre_disi", mqtt: "devre_disi", stm: "online",
    patient: { name: "Boncuk", species: "Kedi", breed: "", owner: "S" },
    activeTreatment: at, notifications: [],
    coils: [1, 2, 3, 4, 5, 6, 7].map((id) => ({ id, connected: true, running: true })),
  };
  const u = render(<ControlScreen />);
  await act(async () => {});
  await act(async () => {});
  expect(u.queryByText("AKTİF SEANS")).not.toBeNull(); // aparat: kart aktif seansı gösteriyor
  return u;
}

it("KRİTİK (İG-6.11 b): elle seansta WS'teki ÖLÇÜLEN yoğunluk kartta '(ölçülen)' olarak çizilir", async () => {
  const u = await kart(F.aktifElle, F.canliElle);
  expect(u.queryByText("YOĞUNLUK (ölçülen)")).not.toBeNull();
  // Anlık ölçülen ve "TEPE (seans)" bu fikstürde aynı sayı (0.80) — ikisi de WS'ten gelir, iki çip.
  expect(u.queryAllByText("0.80 mT")).toHaveLength(2);
  expect(u.queryByText("TEPE (seans)")).not.toBeNull();
});

it("KRİTİK (§10 #5): AI Pro'da kart bobin 1 duty'sini '%' ve DUTY etiketiyle gösterir; 'YOĞUNLUK (kayıt) … mT' YOK", async () => {
  const duty = F.canliAiPro.dutyTemsilYuzde;
  const u = await kart(F.aktifAiPro, F.canliAiPro);
  expect(u.queryByText("DUTY (AI planı, bobin 1)")).not.toBeNull();
  expect(u.queryByText(`%${duty}`)).not.toBeNull();
  expect(u.queryByText("YOĞUNLUK (kayıt)")).toBeNull();
  expect(u.queryByText(/^0 mT$/)).toBeNull();
});

it("KARŞIT: WS'te seans AKTİF DEĞİLSE önceki ölçüm karta taşınmaz (reçete '(kayıt)')", async () => {
  const u = await kart(F.aktifElle, { ...F.canliElle, isActive: false });
  expect(u.queryByText("YOĞUNLUK (ölçülen)")).toBeNull();
  expect(u.queryByText("YOĞUNLUK (kayıt)")).not.toBeNull();
  expect(u.queryByText("1.5 mT")).not.toBeNull();
});
