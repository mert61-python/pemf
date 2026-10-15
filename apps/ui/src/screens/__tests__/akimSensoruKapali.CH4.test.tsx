// Author: mertaygn, cglrgrkn
/**
 * CH4 · Y154 (sahip 2026-10-15) — AKIM SENSÖRÜ TÜMDEN KAPALI: akım HİÇ GÖSTERİLMEZ.
 * ==================================================================================
 * ÖLÇÜLEN DURUM (taban `cc76f758`): Sensörler ekranı "Akım", kontrol paneli "A", KPI bobin tablosu "A" sütunu her bobinde
 * çiziliyordu (ölçüm yoksa "—"); `measuredFields`'te `currentA` olan bobinde sayı görünüyordu (TD5 öncesi yüzen girişte 10–115 A).
 * SÖZLEŞME: tek bayrak backend'de (`utils/akim_olcumu.py` → anlık görüntü `akimOlcumu`, varsayılan false). Arayüz akım satırını /
 * sütununu YALNIZ `akimOlcumu === true` iken çizer; alanı göndermeyen eski backend → gizli. "Anlık Güç" A-64 gereği kalıcı gizli.
 * Açıkken TD5 yolu aynen (karşıt testler). Backend kapısı: tests/test_CH4_akim_sensoru_TUMDEN_KAPALI_Y154.py.
 * ⚠️ MUTASYON: `akimOlcumuAcik` hep true dönerse ya da ekranlardan biri bayrağı okumazsa KIRMIZI.
 */
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => null),
  apiPost: jest.fn(async () => null),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  authHeaders: jest.fn(() => ({})),
}));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://127.0.0.1:65530/api" } }));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("@/services/therapyLimits", () => ({
  clampTherapyParams: (p: unknown) => ({ values: p, warnings: [] }),
}));

let mockSnap: any;
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({
    snapshot: mockSnap, wsConnected: true, connectionQuality: "live",
    haveRealData: true, telemetryStale: false, sensorHistory: {},
    unreadCount: 0, markAllRead: jest.fn(), clearNotifications: jest.fn(),
    refresh: jest.fn(), reconnect: jest.fn(), aiVisionFresh: false,
  }),
}));
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: "veterinarian" }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));

import React from "react";
import { render, waitFor } from "@testing-library/react-native";
import { apiGet } from "@/services/apiClient";
import { KpiDashboardScreen } from "@/screens/KpiDashboardScreen";
import { SensorMonitorScreen } from "@/screens/SensorMonitorScreen";
import { CoilParameterPanel } from "@/components/domain/CoilParameterPanel";
import { akimOlcumuAcik } from "@/utils/olculenAlan";

// Bobin 2: backend'in son bildirdiği akım 1,234 A ve `measuredFields`'te `currentA` (TD5 öncesi / bayrak açıkken olası durum).
const bobin2 = {
  id: 2, connected: true, running: true, frequencyHz: 100, dutyCycle: 40, magneticMt: 0, objectTemp: 0, ambientTemp: 0,
  currentA: 1.234, stm32Driven: true, measuredFields: ["currentA"], akimGuvenilmez: false,
};
const bobin3Guvenilmez = { ...bobin2, id: 3, currentA: 0, measuredFields: [], akimGuvenilmez: true };

function duz(d: any): string {
  if (d == null || typeof d === "boolean") return "";
  if (typeof d === "string" || typeof d === "number") return String(d);
  if (Array.isArray(d)) return d.map(duz).join("");
  const ic = (d.children || []).map(duz).join("");
  return d.type === "Text" ? ic : ` ${ic} `;
}

function snap(akimOlcumu: boolean | undefined) {
  const s: any = {
    gateway: "online", mqtt: "online", stm: "online",
    patient: { name: "", species: "", breed: "", owner: "" },
    activeTreatment: { isActive: true, mode: "Manuel", frequencyHz: 100, intensityMt: 1, remainingMin: 5, elapsedSec: 0, durationSec: 300 },
    notifications: [], coils: [bobin2, bobin3Guvenilmez], system: {}, sessions: [],
  };
  if (akimOlcumu !== undefined) s.akimOlcumu = akimOlcumu;
  return s;
}

describe.each([
  ["backend bayrağı false", false],
  ["alanı göndermeyen eski backend", undefined],
])("KAPALI (%s)", (_ad, bayrak) => {
  it("KRİTİK Sensörler: 'Akım' satırı ve akım sayısı ÇİZİLMEZ, TD5 'Akım ölçümü yok' metni de yok", () => {
    mockSnap = snap(bayrak);
    const metin = duz(render(<SensorMonitorScreen />).toJSON());
    expect(metin).toMatch(/Bobin 2/); // vakum değil
    expect(metin).not.toMatch(/Akım/);
    expect(metin).not.toMatch(/1\.234/);
  });

  it("KRİTİK KPI: bobin tablosunda 'A' sütunu ve akım sayısı YOK, 'Anlık Güç' yok", async () => {
    (apiGet as jest.Mock).mockResolvedValue({ totalSessions: 3 });
    mockSnap = snap(bayrak);
    const u = render(<KpiDashboardScreen />);
    await waitFor(() => expect(apiGet).toHaveBeenCalled());
    const metin = duz(u.toJSON());
    const tablo = metin.slice(metin.indexOf("Bobin Detayları"));
    expect(tablo).toMatch(/Bobin/);
    expect(tablo).not.toMatch(/1\.234/);
    expect(tablo).not.toMatch(/(^|\s)A(\s|$)/);
    expect(metin).not.toMatch(/Anlık Güç/);
  });
});

it("KRİTİK kontrol paneli: bayrak kapalıyken (varsayılan prop) 'A' okuması ÇİZİLMEZ; açıkken çizilir", () => {
  const ortak = {
    coilId: 2, connected: true, running: true, objectTemp: 0, frequencyHz: 100, dutyCycle: 40, magneticMt: 0, currentA: 1.234,
    measuredFields: ["currentA"], stm32Driven: true, stmConnected: true,
  };
  const kapali = render(<CoilParameterPanel {...ortak} />);
  expect(kapali.queryByText("A")).toBeNull();
  expect(kapali.queryByText("1.234")).toBeNull();
  expect(kapali.getByText("Hz")).toBeTruthy(); // vakum değil
  const acik = render(<CoilParameterPanel {...ortak} akimOlcumu />);
  expect(acik.getByText("A")).toBeTruthy();
  expect(acik.getByText("1.234")).toBeTruthy();
});

it("KARŞIT açık (sensör takılıp bayrak açılırsa): Sensörler + KPI akımı gösterir, TD5 'Akım ölçümü yok' korunur", async () => {
  mockSnap = snap(true);
  const sensor = duz(render(<SensorMonitorScreen />).toJSON());
  expect(sensor).toMatch(/1\.234 A/);
  expect(sensor).toMatch(/Akım ölçümü yok/);
  (apiGet as jest.Mock).mockResolvedValue({ totalSessions: 3 });
  const u = render(<KpiDashboardScreen />);
  await waitFor(() => expect(apiGet).toHaveBeenCalled());
  const metin = duz(u.toJSON());
  expect(metin.slice(metin.indexOf("Bobin Detayları"))).toMatch(/1\.234/);
});

it("tek kaynak: bayrak yalnız `true` ile açılır", () => {
  expect(akimOlcumuAcik({ akimOlcumu: true })).toBe(true);
  expect(akimOlcumuAcik({ akimOlcumu: false })).toBe(false);
  expect(akimOlcumuAcik({})).toBe(false);
  expect(akimOlcumuAcik(null)).toBe(false);
  expect(akimOlcumuAcik({ akimOlcumu: "true" as any })).toBe(false);
});
