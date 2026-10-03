// Author: mertaygn, cglrgrkn
/**
 * D1.82 · B-6.35 + Y47 — HİÇBİR durdurma düğmesi bir istek sürerken KİLİTLENMEZ (Kontrol ekranı "⏹ Durdur", seans
 * kartı "⏹ Durdur"); başlatma uçuştayken verilen durdurma, geç gelen başlatma yanıtından SONRA STOP'u YENİDEN gönderir.
 * ==================================================================================================================
 * ÖLÇÜLEN KUSUR (06-2 g5a+g5b): `useSessionControl` başlatma ve durdurma için TEK `loading` kullanıyordu; Kontrol
 * ekranının ana "⏹ Durdur"u `disabled={loading}` → `/session/start` askıdayken (≤ 8 sn, `apiClient` zaman aşımı) durdurma
 * basılamıyordu (0 istek). Seans kartının "⏹ Durdur"u da `disabled={loading}`. Sahip kararı Y47: hiçbir durdurma düğmesi
 * istek sürerken kilitlenmez. Planın "uyandırır" notu: durdurma askıdaki başlatmadan ÖNCE işlenirse geç gelen START
 * bobini durdurmadan SONRA başlatabilir (İG-5.3 sınıfı) → başlatma yanıtından sonra STOP yeniden gönderilmeli.
 *
 * GERÇEK olanlar: `ControlScreen`, `useSessionControl`, `apiClient`, `SessionProgressCard`. Sahte olan YALNIZ `fetch`
 * (`/session/start` asılı söz, yanıtı test verir) ve bağlamlar (canlı veri, kimlik, hasta kapısı).
 *
 * ⚠️ MUTASYON: ana Durdur'a ya da seans kartı Durdur'una `disabled={loading}` geri konursa ya da başlatma sonrası
 * yeniden STOP silinirse KIRMIZI. `durdurmaTuruParalel` T3 (çift basış ref koruması) ayrı dosyada yeşil kalır.
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
// Bobin başı paneller ayrı kapıda (CoilParameterPanel.D182); burada ana Durdur ve seans kartı ölçülür.
jest.mock("@/components/domain/CoilParameterPanel", () => ({ CoilParameterPanel: () => null }));
jest.mock("@/components/domain/PatientGate", () => ({
  PatientGate: ({ children }: { children: React.ReactNode }) => children,
}));

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";
import { Alert } from "react-native";
import { ControlScreen } from "@/screens/ControlScreen";

type Cagri = { yol: string; govde: any };
const cagrilar: Cagri[] = [];
let startCoz: ((o: unknown) => void) | null = null;
let stopAsili = false;
const stopCozuculer: ((o: unknown) => void)[] = [];
const yanit = (o: unknown) =>
  Promise.resolve({ ok: true, status: 200, json: async () => o, text: async () => JSON.stringify(o) });

beforeEach(() => {
  cagrilar.length = 0;
  startCoz = null;
  stopAsili = false;
  stopCozuculer.length = 0;
  jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
  (global as any).fetch = jest.fn((url: string, init?: any) => {
    const yol = String(url).replace("http://127.0.0.1:8000/api", "");
    cagrilar.push({ yol, govde: init?.body ? JSON.parse(init.body) : undefined });
    if (yol === "/session/start") return new Promise((res) => { startCoz = (o) => res(yanit(o) as any); });
    if (yol === "/session/stop" && stopAsili) return new Promise((res) => { stopCozuculer.push((o) => res(yanit(o) as any)); });
    if (yol === "/session/active") return yanit({ is_active: false });
    return yanit({ status: "success" });
  });
  mockSnap = {
    gateway: "devre_disi", mqtt: "devre_disi", stm: "online",
    patient: { name: "Boncuk", species: "Kedi", breed: "", owner: "S" },
    activeTreatment: { isActive: false, mode: "Sistem Hazır", frequencyHz: 0, intensityMt: 0, remainingMin: 0, elapsedSec: 0, durationSec: 0 },
    notifications: [],
    coils: [1, 2, 3, 4, 5, 6, 7].map((id) => ({
      id, running: false, connected: true, stm32Driven: true, frequencyHz: 0, dutyCycle: 0,
      objectTemp: 0, magneticMt: 0, currentA: 0, ambientTemp: 0, measuredFields: [],
    })).concat([{ id: 8, running: false, connected: false, stm32Driven: false, frequencyHz: 0, dutyCycle: 0,
      objectTemp: 0, magneticMt: 0, currentA: 0, ambientTemp: 0, measuredFields: [] }]),
    system: {}, sessions: [],
  };
});
afterEach(() => jest.restoreAllMocks());

const yollar = () => cagrilar.map((c) => c.yol);
const say = (y: string) => yollar().filter((x) => x === y).length;

async function ekran() {
  const u = render(<ControlScreen />);
  await act(async () => {});
  return u;
}

describe("D1.82 / Y47 — durdurma düğmeleri istek sürerken kilitlenmez", () => {
  it("KRİTİK: /session/start ASKIDAYKEN ana '⏹ Durdur' basılabilir ve STOP istekleri gider", async () => {
    const u = await ekran();
    await act(async () => {
      fireEvent.press(u.getByText("▶ Başlat"));
    });
    expect(say("/session/start")).toBe(1); // aparat: başlatma uçuşta
    expect(startCoz).not.toBeNull();
    const durdur = u.getByText("⏹ Durdur");
    await act(async () => {
      fireEvent.press(durdur);
    });
    expect(say("/session/stop")).toBeGreaterThanOrEqual(1);
    expect(cagrilar.some((c) => c.yol === "/coil/batch" && c.govde?.start === false)).toBe(true);
  });

  it("KRİTİK: başlatma uçuştayken Durdur verildiyse, başlatma yanıtı 'success' dönünce STOP YENİDEN gider", async () => {
    const u = await ekran();
    await act(async () => {
      fireEvent.press(u.getByText("▶ Başlat"));
    });
    await act(async () => {
      fireEvent.press(u.getByText("⏹ Durdur"));
    });
    const onceki = say("/session/stop");
    await act(async () => {
      startCoz!({ status: "success", session: { id: 1 } });
    });
    await act(async () => {});
    expect(say("/session/stop")).toBeGreaterThan(onceki);
    // Son söz durdurmanındır: başlatma yanıtından SONRA en az bir STOP.
    const sonStart = yollar().lastIndexOf("/session/start");
    expect(yollar().slice(sonStart + 1)).toContain("/session/stop");
  });

  it("KRİTİK: başlatma uçuştayken Durdur verildiyse, başlatma yanıtı BAŞARISIZ/BOŞ (zaman aşımı) dönse de STOP YENİDEN gider", async () => {
    // 1-E incelemesi (i-5.1): "yalnız başarılı yanıtta yinele" mutantı bu kol olmadan 508/508 YEŞİL kalıyordu. Zaman aşımı
    // sunucunun isteği işlemediği anlamına gelmez (geç işlenen START durdurmadan SONRA başlatabilir).
    const u = await ekran();
    await act(async () => {
      fireEvent.press(u.getByText("▶ Başlat"));
    });
    await act(async () => {
      fireEvent.press(u.getByText("⏹ Durdur"));
    });
    const onceki = say("/session/stop");
    await act(async () => {
      startCoz!(null); // apiClient: boş/başarısız yanıt → null (zaman aşımıyla aynı dal)
    });
    await act(async () => {});
    expect(say("/session/stop")).toBeGreaterThan(onceki);
    const sonStart = yollar().lastIndexOf("/session/start");
    expect(yollar().slice(sonStart + 1)).toContain("/session/stop");
  });

  it("KRİTİK: seans kartının '⏹ Durdur'u /session/stop ASKIDAYKEN de basılabilir (ikinci basış yeni istek)", async () => {
    const u = await ekran();
    await act(async () => {
      fireEvent.press(u.getByText("▶ Başlat"));
    });
    await act(async () => {
      startCoz!({ status: "success", session: { id: 1 } });
    });
    const kart = u.getByLabelText("Seansı durdur"); // aparat: seans aktif, kart çizildi
    stopAsili = true;
    await act(async () => {
      fireEvent.press(kart);
    });
    expect(say("/session/stop")).toBe(1);
    const kart2 = u.getByLabelText("Seansı durdur");
    expect(kart2.props.accessibilityState?.disabled).not.toBe(true);
    await act(async () => {
      fireEvent.press(kart2);
    });
    expect(say("/session/stop")).toBe(2);
    await act(async () => {
      stopCozuculer.forEach((c) => c({ status: "success" }));
    });
  });
});
