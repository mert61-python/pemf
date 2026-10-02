// Author: mertaygn, cglrgrkn
/**
 * D1.67 · A-47 madde 4 · Y6 — 1-D inceleme i2-F-3: `measuredFields`'e bakmayan ekranlar bayat/ölçülmemiş değeri SAYI
 * olarak göstermez.
 *
 * Ölçülen kusur: D1.67 sonrası backend susan sensörün alanını `measuredFields`ten düşürür ama SAYI `_live_state`te
 * donmuş kalır (bobin 6: 45.0 °C / 1.80 mT). Panel ve Sensör ekranı `measuredFields`e bakıyordu; şu yüzeyler bakmıyordu:
 *   - KPI "Ort. Sıcaklık" (`hesaplaOrtSicaklik`, ölçüt `objectTemp > 0`) → 60 sn'dir gelmeyen 45 °C canlı ortalama;
 *   - Ana Ekran `CoilCard` → bayat "45.0 C" / "1.80 mT"; hiç sıcaklık ölçmeyen STM bobini 1 → "0.0 C" (Y6);
 *   - KPI "Bobin Detayları" tablosu → bayat / ölçülmemiş sıcaklık, alan, akım.
 * `measuredFields` YOKSA (eski backend / aparat) eski davranış korunur (bkz. `utils/olculenAlan`).
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
let mockGecmis: any = {};
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({
    snapshot: mockSnap, wsConnected: true, connectionQuality: "live",
    haveRealData: true, telemetryStale: false, sensorHistory: mockGecmis,
    unreadCount: 0, markAllRead: jest.fn(), clearNotifications: jest.fn(),
    refresh: jest.fn(), reconnect: jest.fn(), aiVisionFresh: false,
  }),
}));
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: "veterinarian" }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));

import React from "react";
import { render, waitFor } from "@testing-library/react-native";
import { apiGet } from "@/services/apiClient";
import { CoilCard } from "@/components/domain/CoilCard";
import { KpiDashboardScreen, hesaplaOrtSicaklik } from "@/screens/KpiDashboardScreen";

// Backend'in D1.67 süpürgesinden sonraki bobin 6 anlık görüntüsü: sıcaklık/alan 60 sn'dir gelmiyor → liste boş,
// sayılar DONMUŞ kaldı.
const bayat6 = {
  id: 6, connected: true, running: true, frequencyHz: 100, dutyCycle: 40,
  magneticMt: 1.8, objectTemp: 45.0, ambientTemp: 26.0, currentA: 0, stm32Driven: true,
  measuredFields: [] as string[],
};
const taze6 = { ...bayat6, measuredFields: ["objectTemp", "magneticMt"] };
// Bobin 1: yalnız akım ölçer (ACS712) — sıcaklık/alan sensörü YOK.
const akimli1 = { ...bayat6, id: 1, objectTemp: 0, magneticMt: 0, currentA: 1.234, measuredFields: ["currentA"] };

function duz(d: any): string {
  if (d == null || typeof d === "boolean") return "";
  if (typeof d === "string" || typeof d === "number") return String(d);
  if (Array.isArray(d)) return d.map(duz).join("");
  const ic = (d.children || []).map(duz).join("");
  return d.type === "Text" ? ic : ` ${ic} `;
}

it("KRİTİK KPI: bayat (measuredFields boş) 45 °C 'Ort. Sıcaklık'ta ÖLÇÜLMÜŞ sayılmaz", () => {
  expect(hesaplaOrtSicaklik([bayat6])).toEqual({ olcumVar: false, deger: 0, olcenSayisi: 0 });
  // Bayat bobin, taze ölçen bobinin yanında da sayılmaz (ölçen sayısı 1).
  expect(hesaplaOrtSicaklik([taze6, { ...bayat6, id: 7, objectTemp: 30 }])).toEqual({ olcumVar: true, deger: 45, olcenSayisi: 1 });
});

it("KARŞIT KPI: taze ölçülen 45 °C ortalamaya girer", () => {
  expect(hesaplaOrtSicaklik([taze6])).toEqual({ olcumVar: true, deger: 45, olcenSayisi: 1 });
});

it("KRİTİK CoilCard (Ana Ekran): bayat 45.0 C / 1.80 mT sayı olarak GÖSTERİLMEZ", () => {
  const metin = duz(render(<CoilCard coil={bayat6 as any} />).toJSON());
  expect(metin).not.toMatch(/45\.0/);
  expect(metin).not.toMatch(/1\.80/);
  expect(metin).toMatch(/Sıcaklık\s*—/);
});

it("KRİTİK CoilCard (Ana Ekran): hiç sıcaklık ölçmeyen STM bobini 1 '0.0 C' göstermez (Y6)", () => {
  const metin = duz(render(<CoilCard coil={akimli1 as any} />).toJSON());
  expect(metin).not.toMatch(/0\.0 C/);
  expect(metin).not.toMatch(/0\.00 mT/);
});

it("KARŞIT CoilCard: taze ölçülen sıcaklık ve alan sayı olarak görünür", () => {
  const metin = duz(render(<CoilCard coil={taze6 as any} />).toJSON());
  expect(metin).toMatch(/45\.0 C/);
  expect(metin).toMatch(/1\.80 mT/);
});

async function kpiTablosu(coils: any[], gecmis: any = {}) {
  (apiGet as jest.Mock).mockResolvedValue({ totalSessions: 3 });
  mockGecmis = gecmis;
  mockSnap = {
    gateway: "online", mqtt: "online", stm: "online",
    patient: { name: "", species: "", breed: "", owner: "" },
    activeTreatment: { isActive: true, mode: "Manuel", frequencyHz: 100, intensityMt: 1, remainingMin: 5, elapsedSec: 0, durationSec: 300 },
    notifications: [], coils, system: {}, sessions: [],
  };
  const u = render(<KpiDashboardScreen />);
  await waitFor(() => expect(apiGet).toHaveBeenCalled());
  return u;
}

it("KRİTİK KPI tablosu: bayat bobin 6 satırında 45.0 / 1.80 YOK; ölçmeyen bobin 1'de sıcaklık/alan 0.0 YOK", async () => {
  // sensorHistory'nin SON noktası da bayattır (sensör sustuğundan beri yeni nokta gelmedi).
  const u = await kpiTablosu([akimli1, bayat6], { 6: [{ t: 1, objectTemp: 45.0, magneticMt: 1.8, currentA: 0 }] });
  const metin = duz(u.toJSON());
  const tablo = metin.slice(metin.indexOf("Bobin Detayları"));
  expect(tablo).not.toMatch(/45\.0/);
  expect(tablo).not.toMatch(/1\.80/);
  expect(tablo).not.toMatch(/\b0\.0\b/); // bobin 1 sıcaklığı ölçülmüyor
  expect(tablo).toMatch(/1\.234/); // KARŞIT (aynı satır): bobin 1'in ÖLÇÜLEN akımı görünür
});

it("KARŞIT KPI tablosu: taze ölçülen bobin 6 değerleri görünür", async () => {
  const u = await kpiTablosu([taze6]);
  const metin = duz(u.toJSON());
  const tablo = metin.slice(metin.indexOf("Bobin Detayları"));
  expect(tablo).toMatch(/45\.0/);
  expect(tablo).toMatch(/1\.80/);
});
