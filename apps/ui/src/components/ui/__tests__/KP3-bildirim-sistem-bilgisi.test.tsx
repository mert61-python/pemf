/**
 * KP-3 C · NotificationCenter + SystemInfoPanel kapsanmayan kolları — her test bir DAVRANIŞ iddiası:
 *  - Bildirimleri temizle: ONAY verilirse temizlenir, reddedilirse liste KALIR; kompakt kipte (Ana Ekran kartı) bildirimler iç kaydırıcı
 *    OLMADAN listelenir.
 *  - Sistem bilgisi: gerçek veri + canlı bağlantı + başlangıç zamanı varsa çalışma süresi HER SANİYE ilerler; bağlantı canlı değilse "—"
 *    (bayat süre gösterilmez).
 * SAHTE: canlı veri bağlamı (girdi) · onay penceresi.
 */
let mockCanli: Record<string, unknown> = {};
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => mockCanli }));
const mockOnay = jest.fn(async (..._a: unknown[]) => true);
jest.mock("@/services/apiClient", () => ({ platformConfirm: (...a: unknown[]) => mockOnay(...a) }));

import React from "react";
import { ScrollView } from "react-native";
import { act, fireEvent, render } from "@testing-library/react-native";
import i18n from "i18next";
import { NotificationCenter } from "@/components/ui/NotificationCenter";
import { SystemInfoPanel } from "@/components/domain/SystemInfoPanel";
import { formatUptime } from "@/utils/uptime";

const T = (k: string): string => (i18n.t as unknown as (k: string) => string)(k);
const BILDIRIMLER = [
  { id: 1, level: "warning", message: "Bobin 3 sıcak", timestamp: "2026-11-07T10:00:00Z", read: false },
  { id: 2, level: "info", message: "Seans bitti", timestamp: "2026-11-07T10:05:00Z", read: true },
];

afterEach(() => { jest.useRealTimers(); mockOnay.mockReset(); mockOnay.mockImplementation(async () => true); });

describe("NotificationCenter", () => {
  it("temizle: onayla → temizlenir; reddet → kalır", async () => {
    const temizle = jest.fn();
    mockCanli = { snapshot: { notifications: BILDIRIMLER }, unreadCount: 1, markAllRead: jest.fn(), clearNotifications: temizle };
    const u = render(<NotificationCenter />);
    mockOnay.mockImplementationOnce(async () => false);
    await act(async () => { fireEvent.press(u.getByText(T("ortak.temizle"))); });
    expect(temizle).not.toHaveBeenCalled();
    await act(async () => { fireEvent.press(u.getByText(T("ortak.temizle"))); });
    expect(temizle).toHaveBeenCalledTimes(1);
    expect(mockOnay.mock.calls[0][0]).toBe(T("kabuk.bildirim.temizleBaslik"));
  });

  it("kompakt kipte bildirimler iç kaydırıcı OLMADAN listelenir", () => {
    mockCanli = { snapshot: { notifications: BILDIRIMLER }, unreadCount: 0, markAllRead: jest.fn(), clearNotifications: jest.fn() };
    const u = render(<NotificationCenter compact />);
    expect(u.getByText("Bobin 3 sıcak")).toBeTruthy();
    expect(u.getByText("Seans bitti")).toBeTruthy();
    expect(u.UNSAFE_queryAllByType(ScrollView)).toHaveLength(0);
  });
});

describe("SystemInfoPanel", () => {
  it("canlı + gerçek veri + başlangıç varsa süre her saniye ilerler; canlı değilse '—'", () => {
    jest.useFakeTimers({ now: new Date("2026-11-07T12:00:00Z") });
    const bas = "2026-11-07T11:00:00Z"; // backend ISO başlangıç zamanı
    mockCanli = { snapshot: { system: { startTime: bas }, stm: "online" }, connectionQuality: "live", haveRealData: true };
    const u = render(<SystemInfoPanel />);
    const ilk = formatUptime(bas, Date.now());
    expect(u.getByText(ilk)).toBeTruthy();
    act(() => { jest.advanceTimersByTime(3000); });
    expect(u.getByText(formatUptime(bas, Date.now()))).toBeTruthy();
    expect(formatUptime(bas, Date.now())).not.toBe(ilk);
    mockCanli = { ...mockCanli, connectionQuality: "offline" };
    u.rerender(<SystemInfoPanel />);
    expect(u.queryByText(formatUptime(bas, Date.now()))).toBeNull();
    expect(u.getAllByText("—").length).toBeGreaterThan(0);
  });
});
