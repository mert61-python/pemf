/**
 * KP-8 · src/screens/KpiDashboardScreen.tsx kalan dalları — her test bir DAVRANIŞ iddiası (KP3-KpiDashboard-kollari düzeneği):
 *  - Ekran söküldükten sonra gelen KPI özeti / geçmiş istatistiği durum yazmaz; söküm sonrası yedek uca (istatistik) GİDİLMEZ.
 *  - Geçmiş istatistiği alanları hiç göndermezse sayılar 0, tamamlanma oranı "—" (sıfıra bölme yok), ortalama 0 dk.
 *  - Son 7 gün: tarih yoksa "—", kısa dizge aynen, tiresiz uzun dizge 5. karakterden; sayısız adet 0 (grafik bozulmaz);
 *    mod dağılımında sayısız adet 0.
 *  - Canlı veri bayatsa uyarı (alert) çıkar ve anlık kartlar soluklaşır; bobin listesi hiç gelmezse kartlar 0 / 7 (STM yuvaları).
 *  - Bobin tablosu: bağlı olmayan satır soluk, ÖLÇÜLEN 45 °C üstü kırmızı, frekans 0 → "—".
 *  - "Anlık Güç" göstergesi açılırsa (A-64 / Y154 bayrağı — sahada KAPALI) yalnız güvenilir + ölçülmüş akım sayılır; W sütunu
 *    güvenilmez / sıfır akımda "—".
 *  - `hesaplaOrtSicaklik` liste yerine boş değer alırsa "ölçüm yok" (çökmez).
 * SAHTE: apiClient (ağ sınırı) · grafik kitaplığı (aldığı veri kaydedilir) · canlı veri / profil bağlamları; bayrak testte açılıp
 *   `finally`de geri kapatılır (modül dışa aktarımı ekranda her çizimde okunur).
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
const mockCanli: { snapshot: Record<string, unknown>; connectionQuality: string; sensorHistory: Record<number, unknown[]> } = {
  snapshot: {},
  connectionQuality: "live",
  sensorHistory: {},
};
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({
    snapshot: mockCanli.snapshot,
    wsConnected: true, connectionQuality: mockCanli.connectionQuality, haveRealData: true, telemetryStale: false,
    sensorHistory: mockCanli.sensorHistory,
    unreadCount: 0, markAllRead: jest.fn(), clearNotifications: jest.fn(), refresh: jest.fn(), reconnect: jest.fn(), aiVisionFresh: false,
  }),
}));
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: "veterinarian" }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
const mockCubuk: Array<{ data: { labels: string[]; datasets: Array<{ data: number[] }> } }> = [];
const mockPasta: Array<{ data: Array<{ name: string; population: number }> }> = [];
jest.mock("react-native-chart-kit", () => ({
  BarChart: (p: { data: { labels: string[]; datasets: Array<{ data: number[] }> } }) => { mockCubuk.push(p); return null; },
  PieChart: (p: { data: Array<{ name: string; population: number }> }) => { mockPasta.push(p); return null; },
}));

import React from "react";
import { StyleSheet, Text, View, type ViewStyle } from "react-native";
import { act, fireEvent, render } from "@testing-library/react-native";
import i18n from "i18next";
import { KpiDashboardScreen, hesaplaOrtSicaklik } from "@/screens/KpiDashboardScreen";
import * as bobinGucu from "@/utils/bobinGucu";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
const BOS_SEANS = { isActive: false, mode: "Sistem Hazır", frequencyHz: 0, intensityMt: 0, remainingMin: 0, elapsedSec: 0, durationSec: 0 };
const anlik = (coils?: unknown[], ek: Record<string, unknown> = {}) => ({
  gateway: "online", mqtt: "online", stm: "online", notifications: [], system: {}, activeTreatment: BOS_SEANS,
  ...(coils === undefined ? {} : { coils }), ...ek,
});
const bobin = (id: number, ek: Record<string, unknown> = {}) => ({
  id, connected: true, running: false, magneticMt: 0, objectTemp: 0, currentA: 0, frequencyHz: 10, ...ek,
});
const ertele = <V,>() => {
  let coz!: (v: V) => void;
  const p = new Promise<V>((r) => { coz = r; });
  return { p, coz };
};
const olc = async (u: ReturnType<typeof render>) => {
  const kutular = u.UNSAFE_getAllByType(View).filter((v) => typeof v.props.onLayout === "function");
  await act(async () => { for (const k of kutular) fireEvent(k, "layout", { nativeEvent: { layout: { width: 320, height: 200 } } }); });
};
/** Hücrenin satırı: hücreyi kapsayan en yakın View. */
const satirOf = (hucre: { parent: unknown }) => {
  let s = (hucre as { parent: { type: unknown; parent: unknown; props: { style?: unknown } } | null }).parent;
  while (s && s.type !== View) s = s.parent as typeof s;
  return s as unknown as { props: { style?: unknown }; findAllByType: (t: unknown) => Array<{ props: { children?: unknown } }> };
};

beforeEach(async () => {
  mockApiGet.mockReset();
  mockCubuk.length = 0;
  mockPasta.length = 0;
  mockCanli.snapshot = anlik([]);
  mockCanli.connectionQuality = "live";
  mockCanli.sensorHistory = {};
  await act(async () => { await i18n.changeLanguage("tr"); });
});

it("söküldükten sonra gelen KPI özeti durum yazmaz ve yedek istatistik ucu ÇAĞRILMAZ", async () => {
  const ozet = ertele<null>();
  mockApiGet.mockImplementation((yol: string) => (yol === "/kpi/summary" ? ozet.p : Promise.resolve({ total_sessions: 3 })));
  const hata = jest.spyOn(console, "error").mockImplementation(() => {});
  try {
    const u = render(<KpiDashboardScreen />);
    u.unmount();
    await act(async () => { ozet.coz(null); });
    expect(mockApiGet.mock.calls.map((c) => c[0])).toEqual(["/kpi/summary"]);
    expect(hata).not.toHaveBeenCalled();
  } finally {
    hata.mockRestore();
  }
});

it("söküldükten sonra gelen geçmiş istatistiği durum yazmaz (hata yok)", async () => {
  const ist = ertele<Record<string, unknown>>();
  mockApiGet.mockImplementation((yol: string) => (yol === "/kpi/summary" ? Promise.resolve(null) : ist.p));
  const hata = jest.spyOn(console, "error").mockImplementation(() => {});
  try {
    const u = render(<KpiDashboardScreen />);
    await act(async () => {});
    expect(mockApiGet.mock.calls.map((c) => c[0])).toEqual(["/kpi/summary", "/history/statistics"]);
    u.unmount();
    await act(async () => { ist.coz({ total_sessions: 9, completed_sessions: 9 }); });
    expect(hata).not.toHaveBeenCalled();
  } finally {
    hata.mockRestore();
  }
});

it("geçmiş istatistiği alanları göndermezse sayılar 0, tamamlanma oranı '—', ortalama 0 dk", async () => {
  mockApiGet.mockImplementation(async (yol: string) => (yol === "/history/statistics" ? {} : null));
  const u = render(<KpiDashboardScreen />);
  await act(async () => {});
  await act(async () => {});
  expect(u.getByLabelText(`${T("ayarlar.sistemBilgi.toplamSeans")}: 0`)).toBeTruthy();
  expect(u.getByLabelText(`${T("ana.kpi.tamamlanmaOrani")}: —`)).toBeTruthy();
  expect(u.getByLabelText(`${T("ana.kpi.ortSure")}: ${T("ana.kpi.sureDk", { sure: 0 })}`)).toBeTruthy();
});

it("7 gün: tarihsiz '—', kısa dizge aynen, tiresiz uzun dizge 5. karakterden; sayısız adet 0 · mod sayısı sayısızsa 0", async () => {
  mockApiGet.mockImplementation(async (yol: string) => (yol === "/kpi/summary" ? {
    totalSessions: 4, completedSessions: 4, stoppedSessions: 0, avgDurationMin: 10,
    last7Days: [{ count: 1 }, { date: "", count: 2 }, { date: "abc", count: "x" }, { date: "2026/11/07", count: null }],
    modeDistribution: { Manuel: "çok" },
  } : null));
  const u = render(<KpiDashboardScreen />);
  await act(async () => {});
  await olc(u);
  const son = mockCubuk[mockCubuk.length - 1].data;
  // en eski SOLDA (sunucu yeniden eskiye gönderir)
  expect(son.labels).toEqual(["11/07", "abc", "—", "—"]);
  expect(son.datasets[0].data).toEqual([0, 0, 2, 1]);
  const pasta = mockPasta[mockPasta.length - 1].data.map((d) => d.population);
  expect(pasta).toEqual([0]);
});

it("canlı veri bayatsa uyarı çıkar ve anlık kartlar soluklaşır; bobin listesi hiç gelmezse kartlar 0 / 7 (STM yuvaları)", async () => {
  mockApiGet.mockResolvedValue(null);
  mockCanli.snapshot = anlik(undefined);
  mockCanli.connectionQuality = "reconnecting";
  const u = render(<KpiDashboardScreen />);
  await act(async () => {});
  const uyari = u.getByText(T("ana.kpi.bayatUyari"));
  expect(uyari.props.accessibilityRole).toBe("alert");
  const kart = u.getByLabelText(`${T("ana.bagliBobin")}: 0 / 7`);
  let ata = kart.parent;
  let soluk = false;
  while (ata) {
    if (StyleSheet.flatten(ata.props.style)?.opacity === 0.55) { soluk = true; break; }
    ata = ata.parent;
  }
  expect(soluk).toBe(true);
});

it("bobin tablosu: bağlı olmayan satır soluk, ölçülen 45 °C üstü kırmızı, frekans 0 → '—'", async () => {
  mockApiGet.mockResolvedValue(null);
  mockCanli.snapshot = anlik([
    bobin(1, { objectTemp: 50, measuredFields: ["objectTemp"], frequencyHz: 0 }),
    bobin(2, { connected: false, objectTemp: 30, measuredFields: ["objectTemp"] }),
  ]);
  const u = render(<KpiDashboardScreen />);
  await act(async () => {});
  const sicak = u.getByText("50.0");
  expect(StyleSheet.flatten(sicak.props.style).color).toBe("#ef4444");
  const serin = u.getByText("30.0");
  expect(StyleSheet.flatten(serin.props.style).color).toBe("#fb923c");
  expect(StyleSheet.flatten(satirOf(serin).props.style as ViewStyle).opacity).toBe(0.35);
  const satir1 = satirOf(sicak);
  expect(StyleSheet.flatten(satir1.props.style as ViewStyle).opacity).toBeUndefined();
  const metin1 = satir1.findAllByType(Text).map((x) => String(x.props.children));
  expect(metin1[metin1.length - 1]).toBe("—");
  expect(satirOf(serin).findAllByType(Text).map((x) => String(x.props.children)).pop()).toBe("10");
});

it("'Anlık Güç' açılırsa yalnız güvenilir + ölçülmüş akım sayılır; W sütunu güvenilmez / sıfır akımda '—'", async () => {
  const bg = bobinGucu as unknown as { ANLIK_GUC_GORUNUR: boolean };
  bg.ANLIK_GUC_GORUNUR = true;
  try {
    expect(bobinGucu.ANLIK_GUC_GORUNUR).toBe(true); // açılabildi (aksi hâlde test hiçbir şey sınamaz)
    mockApiGet.mockResolvedValue(null);
    mockCanli.snapshot = anlik([
      bobin(1, { running: true, currentA: 1, measuredFields: ["currentA"] }),
      bobin(2, { running: true, currentA: 2, akimGuvenilmez: true, measuredFields: ["currentA"] }),
      bobin(3, { running: true, currentA: 3, measuredFields: [] }),
      bobin(4, { running: true, currentA: 0, measuredFields: ["currentA"] }),
    ]);
    const u = render(<KpiDashboardScreen />);
    await act(async () => {});
    // 1 A × 1 A × 8,9 Ω = 8,9 W — 2 (güvenilmez) ve 3 (ölçülmemiş) sayılmaz.
    expect(u.getByLabelText(`${T("ana.kpi.anlikGuc")}: 8.9 W`)).toBeTruthy();
    expect(u.getByText("W")).toBeTruthy();
    const wHucresi = (id: number) => {
      const s = satirOf(u.getAllByText(String(id)).find((x) => satirOf(x).findAllByType(Text).length >= 4)!);
      const m = s.findAllByType(Text).map((x) => String(x.props.children));
      return m[m.length - 2]; // W, Hz'den hemen önce
    };
    expect(wHucresi(1)).toBe("8.90");
    expect(wHucresi(2)).toBe("—");
    expect(wHucresi(3)).toBe("—");
    expect(wHucresi(4)).toBe("—");
  } finally {
    bg.ANLIK_GUC_GORUNUR = false;
  }
});

it("hesaplaOrtSicaklik liste yerine boş değer alırsa 'ölçüm yok' (çökmez)", () => {
  expect(hesaplaOrtSicaklik(null as unknown as [])).toEqual({ olcumVar: false, deger: 0, olcenSayisi: 0 });
});
