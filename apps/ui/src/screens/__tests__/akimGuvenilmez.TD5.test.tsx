// Author: mertaygn, cglrgrkn
/**
 * TD5 (tezgâh Oturum 13 · K4, K5, A4) — güvenilmez akım ve "Anlık Güç".
 * =====================================================================
 * ÖLÇÜLEN KUSUR: PSU kapalıyken takılı olmayan ACS712 girişleri 10–115 A "ölçtü"; KPI "Anlık Güç" `COIL_R = 0.5` × sahte akım²
 * ile 6,3 W gösterdi (A-64 "gizle" kararı kodlanmamıştı); bobin tablosunda W sütunu da aynı sayıdan.
 * SÖZLEŞME: backend güvenilmez akımı yazmaz ve `akimGuvenilmez: true` koyar (tests/test_TD5_akim_GUVENILMEZ_yazilmaz_TEK_bildirim.py)
 * → Sensörler ekranı ve KPI tablosu akımı sayı olarak göstermez ("Akım ölçümü yok"); "Anlık Güç" (kart + W sütunu) GİZLİ;
 * bobin direnci tek kaynakta 8,9 Ω (tezgâh LCR).
 * ⚠️ MUTASYON: `ANLIK_GUC_GORUNUR` true yapılırsa ya da `akimGuvenilmez` koşulu kaldırılırsa KIRMIZI.
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
import { SensorMonitorScreen } from "@/screens/SensorMonitorScreen";
import { ANLIK_GUC_GORUNUR, BOBIN_DIRENCI_OHM, bobinGucuW } from "@/utils/bobinGucu";
import { akimOlcumuYokMetni } from "@/utils/olculenAlan";

// Bobin 1: güvenilmez akım (backend `currentA`'yı YAZMADI ama son sayı donmuş olabilir) · bobin 2: güvenilir 1,234 A.
const guvenilmez1 = {
  id: 1, connected: true, running: true, frequencyHz: 100, dutyCycle: 40, magneticMt: 0, objectTemp: 0, ambientTemp: 0,
  currentA: 74.63, stm32Driven: true, measuredFields: ["currentA"], akimGuvenilmez: true,
};
const guvenilir2 = { ...guvenilmez1, id: 2, currentA: 1.234, akimGuvenilmez: false };

function duz(d: any): string {
  if (d == null || typeof d === "boolean") return "";
  if (typeof d === "string" || typeof d === "number") return String(d);
  if (Array.isArray(d)) return d.map(duz).join("");
  const ic = (d.children || []).map(duz).join("");
  return d.type === "Text" ? ic : ` ${ic} `;
}

function snap(coils: any[]) {
  return {
    gateway: "online", mqtt: "online", stm: "online",
    patient: { name: "", species: "", breed: "", owner: "" },
    activeTreatment: { isActive: true, mode: "Manuel", frequencyHz: 100, intensityMt: 1, remainingMin: 5, elapsedSec: 0, durationSec: 300 },
    notifications: [], coils, system: {}, sessions: [],
    // CH4 · Y154: akım sensörü varsayılan KAPALI (akım hiç çizilmez); TD5 yolu yalnız bayrak AÇIKKEN geçerlidir.
    akimOlcumu: true,
  };
}

it("KRİTİK KPI: 'Anlık Güç' (kart) GİZLİ, tabloda güvenilmez akım sayı DEĞİL; güvenilir akım görünür", async () => {
  (apiGet as jest.Mock).mockResolvedValue({ totalSessions: 3 });
  mockSnap = snap([guvenilmez1, guvenilir2]);
  const u = render(<KpiDashboardScreen />);
  await waitFor(() => expect(apiGet).toHaveBeenCalled());
  const metin = duz(u.toJSON());
  expect(metin).not.toMatch(/Anlık Güç/);
  const tablo = metin.slice(metin.indexOf("Bobin Detayları"));
  expect(tablo).not.toMatch(/74\.63/);
  expect(tablo).toMatch(/1\.234/);
});

it("KRİTİK Sensörler: güvenilmez akım sayı DEĞİL, 'Akım ölçümü yok' yazılır", () => {
  mockSnap = snap([guvenilmez1, guvenilir2]);
  const metin = duz(render(<SensorMonitorScreen />).toJSON());
  expect(metin).not.toMatch(/74\.630/);
  expect(metin).toContain(akimOlcumuYokMetni());
  expect(metin).toMatch(/1\.234 A/);
});

it("tek kaynak: bobin direnci 8,9 Ω, A-64 göstergesi kapalı", () => {
  expect(BOBIN_DIRENCI_OHM).toBe(8.9);
  expect(ANLIK_GUC_GORUNUR).toBe(false);
  expect(bobinGucuW(2)).toBeCloseTo(35.6, 6);
});
