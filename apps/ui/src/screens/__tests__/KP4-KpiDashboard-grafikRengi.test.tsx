/**
 * KP-4 B1 · src/screens/KpiDashboardScreen.tsx — çubuk grafiğin renk sözleşmesi: grafik kitaplığı ızgara / eksen / etiket için renk
 * işlevini OPAKLIKLA çağırır; çubuk rengi (mor) ve etiket rengi (açık gri) verilen opaklığı uygular, opaklık verilmezse TAM opaktır
 * (koyu zeminde okunurluk — KP-3 "çubuk ince / zar zor seçiliyor" düzeltmesinin renk yarısı).
 * SAHTE: apiClient (ağ sınırı) · grafik kitaplığı (aldığı yapılandırma kaydedilir) · canlı veri / profil bağlamları (KP-3 düzeneği).
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
const mockCubuk: Array<{ chartConfig: { color: (o?: number) => string; labelColor: (o?: number) => string } }> = [];
jest.mock("react-native-chart-kit", () => ({
  BarChart: (p: (typeof mockCubuk)[number]) => { mockCubuk.push(p); return null; },
  PieChart: () => null,
}));

import React from "react";
import { View } from "react-native";
import { act, fireEvent, render } from "@testing-library/react-native";
import { KpiDashboardScreen } from "@/screens/KpiDashboardScreen";

it("KRİTİK: çubuk ve etiket renkleri kitaplığın verdiği opaklığı uygular; verilmezse tam opak", async () => {
  mockApiGet.mockImplementation(async (yol: string) => (yol === "/kpi/summary" ? {
    totalSessions: 3, completedSessions: 3, stoppedSessions: 0, avgDurationMin: 20,
    last7Days: [{ date: "2026-11-07", count: 3 }], modeDistribution: { Manuel: 3 },
  } : null));
  const u = render(<KpiDashboardScreen />);
  await act(async () => {});
  const kutular = u.UNSAFE_getAllByType(View).filter((v) => typeof v.props.onLayout === "function");
  await act(async () => { for (const k of kutular) fireEvent(k, "layout", { nativeEvent: { layout: { width: 320, height: 200 } } }); });
  const cfg = mockCubuk[mockCubuk.length - 1].chartConfig;
  expect(cfg.color(0.3)).toBe("rgba(167, 139, 250, 0.3)");
  expect(cfg.color()).toBe("rgba(167, 139, 250, 1)");
  expect(cfg.labelColor(0.5)).toBe("rgba(203, 213, 225, 0.5)");
  expect(cfg.labelColor()).toBe("rgba(203, 213, 225, 1)");
});
