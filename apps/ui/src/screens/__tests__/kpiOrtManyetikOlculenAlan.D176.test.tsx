// Author: mertaygn, cglrgrkn
/**
 * D1.76 · B-1.24 · Y6 (İNCELEME-2 i6-F-1) — KPI "Ort. Manyetik" YALNIZ alanı ölçülen çalışan bobinlerin ortalamasıdır.
 *
 * Ölçülen kusur (`60567e4`): D1.76 canlı E-alanının B girdisini yalnız `measuredFields`te `magneticMt` olan bobinlerden
 * almaya çekti (7 bobin çalışırken yalnız bobin 6 ölçüyorsa 1,842 mT → eskiden 0,263 mT). KPI kartı AYNI hesabı hâlâ tüm
 * çalışan bobinler üzerinden yapıyordu: GERÇEK ekranda "Ort. Manyetik 0.26 mT"; hiçbir bobin ölçmezken "0.00 mT".
 * `measuredFields` YOKSA (eski backend) eski davranış korunur (`utils/olculenAlan`).
 * ⚠️ DAVRANIŞSAL: GERÇEK `KpiDashboardScreen`, canlı veri `LiveDataContext` sahtesiyle.
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

function duz(d: any): string {
  if (d == null || typeof d === "boolean") return "";
  if (typeof d === "string" || typeof d === "number") return String(d);
  if (Array.isArray(d)) return d.map(duz).join("");
  const ic = (d.children || []).map(duz).join("");
  return d.type === "Text" ? ic : ` ${ic} `;
}

const temel = { connected: true, running: true, frequencyHz: 1, dutyCycle: 30, objectTemp: 0, ambientTemp: 0, currentA: 0.5, stm32Driven: true };
const akim = (id: number) => ({ ...temel, id, magneticMt: 0, measuredFields: ["currentA"] });
const alan = (id: number, mt: number) => ({ ...temel, id, currentA: 0, magneticMt: mt, measuredFields: ["magneticMt"] });
const sessiz = (id: number) => ({ ...temel, id, currentA: 0, magneticMt: 0, measuredFields: [] as string[] });
// Alan sensörü SUSMUŞ bobin: sayı `_live_state`te DONMUŞ (1,8 mT) ama `measuredFields`ten düşmüş (D1.67).
const bayat = (id: number) => ({ ...temel, id, currentA: 0, magneticMt: 1.8, measuredFields: [] as string[] });

/** "Ort. Manyetik" kartının metni (etiket + değer). */
async function kart(coils: any[]) {
  (apiGet as jest.Mock).mockResolvedValue({ totalSessions: 3 });
  mockSnap = {
    gateway: "online", mqtt: "online", stm: "online",
    patient: { name: "", species: "", breed: "", owner: "" },
    activeTreatment: { isActive: true, mode: "AI Pro", frequencyHz: 1, intensityMt: 1, remainingMin: 5, elapsedSec: 0, durationSec: 300 },
    notifications: [], coils, system: {}, sessions: [],
  };
  const u = render(<KpiDashboardScreen />);
  await waitFor(() => expect(apiGet).toHaveBeenCalled());
  const m = duz(u.toJSON());
  const i = m.indexOf("Ort. Manyetik");
  expect(i).toBeGreaterThanOrEqual(0);
  return m.slice(i, i + 40).replace(/\s+/g, " ");
}

it("KRİTİK: 7 bobin çalışıyor, yalnız bobin 6 alan ölçüyor (1,842 mT) → ortalama 1.84 mT (ölçülmeyenin 0.0'ı ve bayat 1,8'i GİRMEZ)", async () => {
  const s = await kart([akim(1), akim(2), akim(3), akim(4), akim(5), alan(6, 1.842), bayat(7)]);
  expect(s).toMatch(/Ort\. Manyetik \(1 bobin\)\s*1\.84 mT/);
  expect(s).not.toMatch(/0\.26/);
});

it("KRİTİK (Y6): hiçbir çalışan bobin alan ölçmüyor → 'ölçüm yok' (0.00 mT DEĞİL)", async () => {
  const s = await kart([akim(1), akim(2), sessiz(7)]);
  expect(s).toMatch(/ölçüm yok/);
  expect(s).not.toMatch(/0\.00 mT/);
});

it("KARŞIT: çalışan bobinlerin hepsi ölçüyorsa ortalama aynen (1,0 ve 2,0 → 1.50 mT)", async () => {
  const s = await kart([alan(6, 1.0), alan(7, 2.0)]);
  expect(s).toMatch(/1\.50 mT/);
});

it("KARŞIT (sürüm kayması): measuredFields göndermeyen eski backend eski ortalamayı görür", async () => {
  const eski = (id: number, mt: number) => ({ ...temel, id, magneticMt: mt });
  const s = await kart([eski(1, 1.0), eski(2, 3.0)]);
  expect(s).toMatch(/2\.00 mT/);
});
