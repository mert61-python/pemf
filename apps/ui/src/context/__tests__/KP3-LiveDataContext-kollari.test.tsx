/**
 * KP-3 C · LiveDataContext kapsanmayan kolları — her test bir DAVRANIŞ iddiası (A47 düzeneğinin aynısı; GERÇEK `LiveDataProvider`):
 *  - WS iletileri: `session_control` etkin tedaviyi, `stm_uyum` kart-paket uyum kararını yazar; `notification` listenin BAŞINA
 *    eklenir ve okunmamış sayacı artar (liste 50'de tavanlanır); bilinmeyen tür ve bobin kimliği / verisi EKSİK telemetri yok sayılır.
 *  - ACİL DURDUR yapışkanlığı: durdurmadan sonraki 3 sn içinde gelen geç `coil_status` (running) ve `session_tick` (isActive) bobini /
 *    seansı yeniden "çalışıyor" GÖSTEREMEZ; 3 sn sonra gelen gerçek değer yazılır.
 *  - Bildirimleri temizle: liste ve sayaç sıfırlanır, sunucuya sessiz temizleme isteği gider.
 *  - HTTP yedeği (`refresh`): anlık görüntü gelirse yazılır ve "gerçek veri" işaretlenir; boş yanıtta değişiklik yok.
 *  - Keşif: yerel istemcide açılışta kayıtlı adres ÖNCE uygulanır ("kayitliHemen"); keşif adresi DEĞİŞTİRİRSE soket yeniden kurulur,
 *    değiştirmezse kurulmaz; keşif hata fırlatsa da sağlayıcı ayakta kalır.
 * SAHTE: wsClient (soket sınırı), apiClient, config, discovery (keşif sınırı), ağ erişilebilirliği / ön plan kancaları.
 */
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async (_p: string, fb: unknown) => fb),
  apiPost: jest.fn(async (_p: string, _b: unknown, fb: unknown) => fb),
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://192.168.1.5:8000/api", websocketUrl: "ws://192.168.1.5:8000/ws", apiToken: "" },
  loadStoredApiToken: jest.fn(async () => undefined),
}));
const mockKesif = jest.fn(async (..._a: unknown[]): Promise<unknown> => null);
jest.mock("@/services/discovery", () => ({ discoverBackend: (...a: unknown[]) => mockKesif(...a) }));
jest.mock("@/hooks/useNetworkReachability", () => ({ useNetworkReachability: () => undefined }));
jest.mock("@/hooks/useForegroundReconnect", () => ({ useForegroundReconnect: () => undefined }));
const mockWs: { onMessage?: (m: any) => void; onState?: (c: boolean) => void; yenidenKesif?: () => void; kurulum: number } = { kurulum: 0 };
jest.mock("@/services/wsClient", () => ({
  connectPemfWebSocket: (onMessage: any, onState: any, yenidenKesif: any) => {
    mockWs.onMessage = onMessage;
    mockWs.onState = onState;
    mockWs.yenidenKesif = yenidenKesif;
    mockWs.kurulum += 1;
    return () => undefined;
  },
}));

import React from "react";
import { act, render } from "@testing-library/react-native";
import { LiveDataProvider, useLiveData } from "@/context/LiveDataContext";

const { apiGet, apiPost } = jest.requireMock("@/services/apiClient") as { apiGet: jest.Mock; apiPost: jest.Mock };
const { serviceConfig } = jest.requireMock("@/services/config") as { serviceConfig: { websocketUrl: string } };

let ctx: ReturnType<typeof useLiveData>;
function Probe() {
  ctx = useLiveData();
  return null;
}
const ilet = async (m: unknown) => { await act(async () => { mockWs.onMessage?.(m); }); };
async function kur() {
  render(<LiveDataProvider><Probe /></LiveDataProvider>);
  await act(async () => { await Promise.resolve(); });
  await act(async () => { await Promise.resolve(); });
  await act(async () => { mockWs.onState?.(true); });
}
const bobin = (id: number, running = false) => ({ id, running, connected: true, frequencyHz: 0, dutyCycle: 0, objectTemp: 0, magneticMt: 0,
  ambientTemp: 0, currentA: 0, measuredFields: [] });
const ANLIK = {
  gateway: "online", mqtt: "online", stm: "online", notifications: [], system: {},
  activeTreatment: { isActive: false, mode: "Sistem Hazır", frequencyHz: 0, intensityMt: 0, remainingMin: 0, elapsedSec: 0, durationSec: 0 },
  coils: [1, 2, 3, 4, 5, 6, 7].map((i) => bobin(i)),
};

let saat = 1_000_000;
beforeEach(() => {
  saat = 1_000_000;
  jest.spyOn(Date, "now").mockImplementation(() => saat);
  mockWs.kurulum = 0;
  mockKesif.mockReset();
  mockKesif.mockResolvedValue(null);
  apiGet.mockClear();
  apiPost.mockClear();
  serviceConfig.websocketUrl = "ws://192.168.1.5:8000/ws";
});
afterEach(() => jest.restoreAllMocks());

describe("WS iletileri", () => {
  it("session_control / stm_uyum yazılır; bildirim başa eklenir + sayaç (50 tavan); bilinmeyen ve eksik telemetri yok sayılır", async () => {
    await kur();
    await ilet({ type: "snapshot", data: ANLIK });
    const tedavi = { isActive: true, mode: "Manuel", frequencyHz: 50, intensityMt: 1, remainingMin: 10, elapsedSec: 5, durationSec: 600 };
    await ilet({ type: "session_control", data: tedavi });
    expect(ctx.snapshot.activeTreatment).toMatchObject({ isActive: true, mode: "Manuel", frequencyHz: 50 });
    await ilet({ type: "stm_uyum", data: { uyumlu: false, neden: "paket_surumu" } });
    expect((ctx.snapshot as { stmUyum?: unknown }).stmUyum).toEqual({ uyumlu: false, neden: "paket_surumu" });
    for (let i = 0; i < 52; i++) await ilet({ type: "notification", data: { id: `n${i}`, title: `B${i}`, read: false } });
    expect(ctx.snapshot.notifications).toHaveLength(50);
    expect(ctx.snapshot.notifications[0]).toMatchObject({ id: "n51" });
    expect(ctx.unreadCount).toBe(52);
    const once = JSON.stringify(ctx.snapshot);
    await ilet({ type: "bilinmeyen_tur", data: { x: 1 } });
    for (const tur of ["sensor_data", "coil_status", "coil_ack", "stm_coil_update"]) {
      await ilet({ type: tur, coilId: 0, data: { running: true } });
      await ilet({ type: tur, coilId: 3 });
    }
    expect(JSON.stringify(ctx.snapshot)).toBe(once);
  });

  it("ACİL DURDUR sonrası 3 sn içinde geç 'çalışıyor' iletileri bobini / seansı geri ÇALIŞTIRAMAZ; 3 sn sonra gerçek değer yazılır", async () => {
    await kur();
    await ilet({ type: "snapshot", data: { ...ANLIK, coils: ANLIK.coils.map((c) => ({ ...c, running: true })) } });
    await ilet({ type: "emergency_stop", data: {} });
    expect(ctx.snapshot.coils.every((c) => !c.running)).toBe(true);
    saat += 1500;
    await ilet({ type: "coil_status", coilId: 2, data: { ...bobin(2), running: true } });
    await ilet({ type: "session_tick", data: { ...ANLIK.activeTreatment, isActive: true, mode: "Manuel" } });
    expect(ctx.snapshot.coils.find((c) => c.id === 2)?.running).toBe(false);
    expect(ctx.snapshot.activeTreatment.isActive).toBe(false);
    saat += 2000;
    await ilet({ type: "coil_status", coilId: 2, data: { ...bobin(2), running: true } });
    await ilet({ type: "session_tick", data: { ...ANLIK.activeTreatment, isActive: true, mode: "Manuel" } });
    expect(ctx.snapshot.coils.find((c) => c.id === 2)?.running).toBe(true);
    expect(ctx.snapshot.activeTreatment.isActive).toBe(true);
  });

  it("bildirimleri temizle: liste + sayaç sıfır, sunucuya sessiz temizleme isteği", async () => {
    await kur();
    await ilet({ type: "notification", data: { id: "n1", title: "B", read: false } });
    await act(async () => { await ctx.clearNotifications(); });
    expect(ctx.snapshot.notifications).toEqual([]);
    expect(ctx.unreadCount).toBe(0);
    expect(apiPost).toHaveBeenCalledWith("/notifications/clear", {}, null, { silent: true });
  });
});

describe("HTTP yedeği + keşif", () => {
  it("refresh: anlık görüntü yazılır ve gerçek veri işaretlenir; boş yanıtta değişiklik yok", async () => {
    await kur();
    apiGet.mockResolvedValueOnce(null);
    await act(async () => { await ctx.refresh(); });
    expect(ctx.snapshot.coils.length).not.toBe(3);
    apiGet.mockResolvedValueOnce({ ...ANLIK, coils: [bobin(1, true), bobin(2), bobin(3)] });
    await act(async () => { await ctx.refresh(); });
    expect(apiGet).toHaveBeenLastCalledWith("/dashboard-snapshot", null, { silent: true });
    expect(ctx.snapshot.coils.find((c) => c.id === 1)?.running).toBe(true);
    expect(ctx.haveRealData).toBe(true);
  });

  it("yerelde açılışta kayıtlı adres ÖNCE; sonraki keşif adresi değiştirirse soket yeniden kurulur, değiştirmezse kurulmaz", async () => {
    let hedef = "ws://192.168.1.5:8000/ws";
    mockKesif.mockImplementation(async (kip?: unknown) => {
      if (kip === "kayitliHemen") return { address: "192.168.1.5", source: "saved" };
      serviceConfig.websocketUrl = hedef;
      return { address: hedef, source: "mdns" };
    });
    await kur();
    await act(async () => { await Promise.resolve(); });
    expect(mockKesif.mock.calls[0]).toEqual(["kayitliHemen"]);
    const ilk = mockWs.kurulum;
    await act(async () => { mockWs.yenidenKesif?.(); await Promise.resolve(); });
    await act(async () => { await Promise.resolve(); });
    expect(mockWs.kurulum).toBe(ilk); // adres AYNI → sağlıklı soket yıkılmaz
    hedef = "ws://192.168.1.77:8000/ws";
    await act(async () => { mockWs.yenidenKesif?.(); await Promise.resolve(); });
    await act(async () => { await Promise.resolve(); });
    expect(mockWs.kurulum).toBe(ilk + 1); // adres DEĞİŞTİ → yeniden kurulum
  });

  it("keşif hata fırlatsa da sağlayıcı ayakta kalır ve soket kurulur", async () => {
    mockKesif.mockImplementation(async (kip?: unknown) => {
      if (kip === "kayitliHemen") return null;
      throw new Error("ağ yok");
    });
    await kur();
    await act(async () => { await Promise.resolve(); });
    expect(mockWs.kurulum).toBe(1);
    await ilet({ type: "session_control", data: { ...ANLIK.activeTreatment, isActive: true } });
    expect(ctx.snapshot.activeTreatment.isActive).toBe(true);
  });
});
