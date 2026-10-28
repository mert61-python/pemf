// Author: mertaygn, cglrgrkn
/**
 * L1-7.10 · İG-6.11 (a) — Kontrol ekranı açıkken BAŞKA yerde (ikinci istemci / AI Pro) başlatılan seans: uyarı bandı "seans bağlamı
 * dışında" DEMEZ, AKTİF SEANS'ı söyler (TR + EN).
 * ===================================================================================================================
 * ÖLÇÜLEN (HEAD `ebf1c3fe`, sonda `_inceleme/L1-7.10/sonda/zz_l1710_sonda.test.tsx`): açılışta `/session/active` boş; ardından WS
 * `activeTreatment.isActive=true` (GERÇEK backend fikstürü `kayitGorunumu.D189.json` `canliElle`) + bobin 1-2 çalışıyor →
 * 30 sn sonra kart hâlâ "Seans Bekleniyor", `/session/active` yalnız 1 kez okundu (yoklama YALNIZ yerel seans aktifken), bant
 * "⚠️ DONANIM ÇALIŞIYOR — … seans bağlamı dışında" — aktif bir seans varken YANLIŞ.
 * SÖZLEŞME: YALNIZ bant METNİ değişir; bandın görünme koşulu (`!isActive && çalışan bobin`), ACİL DURDUR ve kartın Durdur yolu AYNI
 * (kart yerel seansı izlemeye devam eder — kartın uzak seansı benimsemesi STOP yolunu değiştirir → [SAHİBE], RAPOR_C3 L1-7.10).
 * GERÇEK: `ControlScreen`, `useSessionControl`, `apiClient`, `SessionProgressCard`; sahte olan `fetch` ve bağlamlar.
 * ⚠️ MUTASYON: metin seçimi WS seansına bakmazsa (hep eski metin) ya da bant koşulu değişirse KIRMIZI.
 */
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:65530/api", bridgeBaseUrl: "http://127.0.0.1:65530/api", apiToken: "" },
}));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn(() => true) }));
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
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const F: any = require("./__fixtures__/kayitGorunumu.D189.json");
const depo = { setItem: async () => undefined };
const yanit = (o: unknown) => Promise.resolve({ ok: true, status: 200, json: async () => o, text: async () => JSON.stringify(o) });

const TR_UZAK =
  "⚠️ AKTİF SEANS sürüyor — bu kartın dışında başlatıldı (başka istemci ya da AI Pro); 2 bobin enerjili. Aşağıdaki ACİL DURDUR ile durdurabilirsiniz.";
const TR_ESKI = "⚠️ DONANIM ÇALIŞIYOR — 2 bobin enerjili, seans bağlamı dışında. Aşağıdaki ACİL DURDUR ile durdurabilirsiniz.";
const EN_UZAK =
  "⚠️ ACTIVE SESSION running — started outside this card (another client or AI Pro); 2 coils energized. You can stop it with EMERGENCY STOP below.";

beforeEach(() => {
  jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
  // Açılışta yerel seans YOK (bu istemci başlatmadı).
  (global as any).fetch = jest.fn((url: string) =>
    String(url).endsWith("/session/active") ? yanit({ is_active: false }) : yanit({ status: "success" }),
  );
});

afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

async function ekran(wsAktif: boolean) {
  mockSnap = {
    gateway: "devre_disi", mqtt: "devre_disi", stm: "online",
    patient: { name: "", species: "", breed: "", owner: "" },
    activeTreatment: wsAktif ? F.canliElle : { ...F.canliElle, isActive: false },
    notifications: [],
    coils: [1, 2, 3, 4, 5, 6, 7].map((id) => ({ id, connected: true, running: id <= 2 })),
  };
  const u = render(<ControlScreen />);
  await act(async () => {});
  await act(async () => {});
  return u;
}

it("KRİTİK TR: WS'te AKTİF seans varken bant AKTİF SEANS'ı söyler, 'seans bağlamı dışında' DEMEZ", async () => {
  const u = await ekran(true);
  expect(u.queryByText(TR_UZAK)).not.toBeNull();
  expect(u.queryByText(/seans bağlamı dışında/)).toBeNull();
});

it("KARŞIT: WS'te seans YOKKEN çalışan bobin → eski 'DONANIM ÇALIŞIYOR … seans bağlamı dışında' bandı AYNEN", async () => {
  const u = await ekran(false);
  expect(u.queryByText(TR_ESKI)).not.toBeNull();
  expect(u.queryByText(/AKTİF SEANS sürüyor/)).toBeNull();
});

it("DEĞİŞMEYEN: ACİL DURDUR düğmesi her iki durumda da çizilir (bant metni STOP yoluna bağlanmaz)", async () => {
  for (const ws of [true, false]) {
    const u = await ekran(ws);
    expect(u.getByLabelText("Tüm bobinleri acil durdur")).toBeTruthy();
    expect(u.getByText("🚨 TÜM BOBİNLERİ ACİL DURDUR")).toBeTruthy();
    u.unmount();
  }
});

it("KRİTİK EN: aynı bant İngilizce", async () => {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
  const u = await ekran(true);
  expect(u.queryByText(EN_UZAK)).not.toBeNull();
  expect(u.queryByText(/outside a session context/)).toBeNull();
});

// TUR 2 (çürütücü kolu): tek bobin enerjiliyken katalog `_one` biçimini kullanır — TR / EN `_one` değeri ayrı bir girdidir; yalnız 2 bobinli
// senaryo onu hiç çizmiyordu (mutant `cur1710_n2`: TR `_one`'a eski "seans bağlamı dışında" metni YAŞIYORDU).
async function ekranTekBobin() {
  mockSnap = {
    gateway: "devre_disi", mqtt: "devre_disi", stm: "online",
    patient: { name: "", species: "", breed: "", owner: "" },
    activeTreatment: F.canliElle,
    notifications: [],
    coils: [1, 2, 3, 4, 5, 6, 7].map((id) => ({ id, connected: true, running: id === 1 })),
  };
  const u = render(<ControlScreen />);
  await act(async () => {});
  await act(async () => {});
  return u;
}

it("KRİTİK TR + EN (tek bobin — `_one` biçimi): WS'te AKTİF seans varken bant AKTİF SEANS'ı söyler, 'seans bağlamı dışında' DEMEZ", async () => {
  const tr = await ekranTekBobin();
  expect(
    tr.queryByText(
      "⚠️ AKTİF SEANS sürüyor — bu kartın dışında başlatıldı (başka istemci ya da AI Pro); 1 bobin enerjili. Aşağıdaki ACİL DURDUR ile durdurabilirsiniz.",
    ),
  ).not.toBeNull();
  expect(tr.queryByText(/seans bağlamı dışında/)).toBeNull();
  tr.unmount();
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
  const en = await ekranTekBobin();
  expect(
    en.queryByText(
      "⚠️ ACTIVE SESSION running — started outside this card (another client or AI Pro); 1 coil energized. You can stop it with EMERGENCY STOP below.",
    ),
  ).not.toBeNull();
  expect(en.queryByText(/outside a session context/)).toBeNull();
});
