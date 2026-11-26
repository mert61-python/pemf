/**
 * KP-3 C · src/screens/KpiDashboardScreen.tsx kapsanmayan kolları — her test bir DAVRANIŞ iddiası (crashGuards düzeneği):
 *  - KPI özeti alınamazsa geçmiş istatistiğine düşülür; ESKİ alan adı (`average_duration`) da okunur → toplam, tamamlanma oranı ve
 *    ortalama süre (yuvarlanmış) gösterilir.
 *  - Son 7 gün grafiği: tarih saniye-epoch, milisaniye-epoch ya da ISO dizge gelse de "AA-GG" etiketi olur (en eski solda).
 *  - Mod dağılımı: her mod okunur etiketiyle ve sayısıyla lejantta; grafik yalnız ölçüm (genişlik) gelince çizilir.
 * SAHTE: apiClient (ağ sınırı) · grafik kitaplığı (aldığı veri kaydedilir) · canlı veri / profil bağlamları.
 */
const mockApiGet = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => mockApiGet(...a),
  apiPost: jest.fn(async () => null),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  authHeaders: jest.fn(() => ({})),
}));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://192.168.1.5:8000/api" } }));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({
    snapshot: { gateway: "online", mqtt: "online", stm: "online", coils: [], notifications: [], system: {},
      activeTreatment: { isActive: false, mode: "Sistem Hazır", frequencyHz: 0, intensityMt: 0, remainingMin: 0, elapsedSec: 0, durationSec: 0 } },
    wsConnected: true, connectionQuality: "live", haveRealData: true, telemetryStale: false, sensorHistory: {},
    unreadCount: 0, markAllRead: jest.fn(), clearNotifications: jest.fn(), refresh: jest.fn(), reconnect: jest.fn(), aiVisionFresh: false,
  }),
}));
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: "veterinarian" }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
const mockCubuk: { data: { labels: string[] } }[] = [];
const mockPasta: { data: { name: string; population: number }[] }[] = [];
jest.mock("react-native-chart-kit", () => ({
  BarChart: (p: { data: { labels: string[] } }) => { mockCubuk.push(p); return null; },
  PieChart: (p: { data: { name: string; population: number }[] }) => { mockPasta.push(p); return null; },
}));

import React from "react";
import { View } from "react-native";
import { act, fireEvent, render } from "@testing-library/react-native";
import i18n from "i18next";
import { KpiDashboardScreen } from "@/screens/KpiDashboardScreen";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
const p2 = (x: number) => String(x).padStart(2, "0");
const aaGg = (ms: number) => { const d = new Date(ms); return `${p2(d.getMonth() + 1)}-${p2(d.getDate())}`; };

beforeEach(() => {
  mockApiGet.mockReset();
  mockCubuk.length = 0;
  mockPasta.length = 0;
});

it("özet yoksa geçmiş istatistiğine düşülür; eski alan adı (average_duration) da okunur", async () => {
  mockApiGet.mockImplementation(async (yol: string) =>
    yol === "/history/statistics" ? { total_sessions: 12, completed_sessions: 9, average_duration: 17.6 } : null);
  const u = render(<KpiDashboardScreen />);
  await act(async () => {});
  await act(async () => {});
  expect(u.getByLabelText(`${T("ayarlar.sistemBilgi.toplamSeans")}: 12`)).toBeTruthy();
  expect(u.getByLabelText(`${T("ana.kpi.tamamlanmaOrani")}: %75`)).toBeTruthy(); // ODD K-8: TR yüzde "%75"
  expect(u.getByLabelText(`${T("ana.kpi.ortSure")}: ${T("ana.kpi.sureDk", { sure: 18 })}`)).toBeTruthy();
});

it("7 gün etiketleri: saniye / ms epoch ve ISO → AA-GG (en eski solda); mod lejantı okunur etiket + sayı; grafik ölçümden sonra", async () => {
  // ⚠️ İngilizcede: Türkçede AI Pro hedef etiketi ham kayıt değeriyle AYNI ("Kedi Organ · Mide") → çeviri gözlenemezdi (ölçüldü).
  await act(async () => { await i18n.changeLanguage("en"); });
  const sn = 1_699_000_000;
  mockApiGet.mockImplementation(async (yol: string) => (yol === "/kpi/summary" ? {
    totalSessions: 5, completedSessions: 5, stoppedSessions: 0, avgDurationMin: 20,
    last7Days: [{ date: "2026-11-07", count: 1 }, { date: (sn + 86400) * 1000, count: 2 }, { date: sn, count: 3 }],
    modeDistribution: { Manuel: 3, "AI Pro · Kedi Organ · Mide": 2 },
  } : null));
  const u = render(<KpiDashboardScreen />);
  await act(async () => {});
  expect(mockCubuk).toHaveLength(0); // genişlik ölçülmeden grafik yok
  const kutular = u.UNSAFE_getAllByType(View).filter((v) => typeof v.props.onLayout === "function");
  await act(async () => { for (const k of kutular) fireEvent(k, "layout", { nativeEvent: { layout: { width: 320, height: 200 } } }); });
  const etiketler = mockCubuk[mockCubuk.length - 1].data.labels;
  expect(etiketler).toEqual([aaGg(sn * 1000), aaGg((sn + 86400) * 1000), "11-07"]);
  const pasta = mockPasta[mockPasta.length - 1].data.map((d) => [d.name, d.population]);
  const aiPro = `AI Pro · ${T("ai.modul.kediOrgan.ad")} · ${T("ai.organ.ad.mide")}`;
  expect(aiPro).not.toBe("AI Pro · Kedi Organ · Mide"); // gerçekten çevrildi
  expect(pasta[0][1]).toBe(3);
  expect(pasta[1]).toEqual([aiPro, 2]);
  expect(u.getByText(`${aiPro} (2)`)).toBeTruthy();
  await act(async () => { await i18n.changeLanguage("tr"); });
});
