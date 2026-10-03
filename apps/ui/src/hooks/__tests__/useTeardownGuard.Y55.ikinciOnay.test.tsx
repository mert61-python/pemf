// Author: mertaygn, cglrgrkn
/**
 * Y55 (sahip, S-E1) — STM BAĞLI DEĞİLKEN çıkış / profil değişimi: ACİL DURDUR yine ÖNCE gönderilir; teyit gelmezse İKİNCİ
 * onay sorulur ("ACİL DURDUR teyit edilemedi — STM bağlı değil, bobinleri kontrol edin. Yine de çıkılsın mı?"); evet →
 * çıkılır, hayır → ekranda kalınır.
 * ======================================================================================================================
 * ÖLÇÜLEN KUSUR (D1.E03 kapısı, `onceki`): kalıcı kopuklukta (kart sökülü, kablo çıkık) teyit HİÇ gelemez; kapı teyitsiz
 * durdurmada söküm iptal ettiği için çıkış HER SEFERİNDE iptal oluyordu — operatör uygulamadan çıkamıyordu. Gerekçe (sahip):
 * STM paket gelmeyince bobinleri kendi bekçisiyle ~1,5 sn'de durdurur (DENETİM-08 ölçümü).
 * DEĞİŞMEYEN: E-stop gönderimi atlanmaz/kapılanmaz (Ö.4-Y8); STM ÇEVRİMİÇİYKEN teyitsiz durdurma yine İPTAL; mandal ve
 * "teyitsiz" durumu backend'dedir — kapı Sıfırla çağırmaz.
 *
 * Dizi ELLE YAZILMADI: D1.74'ün GERÇEK backend kaydı (`stmKopusuManuelBobin.ws.json`: manuel bobin + kopuş).
 */
const mockSira: string[] = [];
const mockCevap: Record<string, boolean> = {};
const mockConfirm = jest.fn(async (title: string, _body: string, _ok?: string) => {
  mockSira.push(`onay:${title}`);
  return mockCevap[title] ?? true;
});
let mockTeyit = true;
const mockPost = jest.fn(async (_p: string, _b: unknown, fb: unknown) => fb);
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async (_p: string, fb: unknown) => fb),
  apiPost: (p: string, b: unknown, fb: unknown) => mockPost(p, b, fb),
  platformAlert: jest.fn((t: string) => mockSira.push(`uyari:${t}`)),
  platformConfirm: (t: string, b: string, o?: string) => mockConfirm(t, b, o),
}));
jest.mock("@/services/emergencyStop", () => ({
  performEmergencyStop: jest.fn(async () => {
    mockSira.push("estop");
    return { confirmed: mockTeyit };
  }),
  EMERGENCY_STOP_UNCONFIRMED_TITLE: "TEYITSIZ",
  EMERGENCY_STOP_UNCONFIRMED_BODY: "govde",
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api", websocketUrl: "ws://127.0.0.1:8000/ws", apiToken: "" },
  loadStoredApiToken: jest.fn(async () => undefined),
}));
jest.mock("@/services/discovery", () => ({ discoverBackend: jest.fn(async () => null) }));
jest.mock("@/hooks/useNetworkReachability", () => ({ useNetworkReachability: () => undefined }));
jest.mock("@/hooks/useForegroundReconnect", () => ({ useForegroundReconnect: () => undefined }));
const mockWs: { onMessage?: (m: any) => void; onState?: (c: boolean) => void } = {};
jest.mock("@/services/wsClient", () => ({
  connectPemfWebSocket: (onMessage: any, onState: any) => {
    mockWs.onMessage = onMessage;
    mockWs.onState = onState;
    return () => undefined;
  },
}));

import React from "react";
import { render, act } from "@testing-library/react-native";
import { LiveDataProvider } from "@/context/LiveDataContext";
import { useTeardownGuard } from "@/hooks/useTeardownGuard";

const dizi: any[] = require("../../context/__tests__/__fixtures__/stmKopusuManuelBobin.ws.json");
const IKINCI = "ACİL DURDUR teyit edilemedi";

let guard: ReturnType<typeof useTeardownGuard>;
function Yakala() {
  guard = useTeardownGuard();
  return null;
}

async function kur(mesajlar: any[]) {
  render(
    <LiveDataProvider>
      <Yakala />
    </LiveDataProvider>
  );
  await act(async () => {
    mockWs.onState?.(true);
  });
  for (const m of mesajlar) {
    await act(async () => {
      mockWs.onMessage?.(m);
    });
  }
}

async function cik(etiket = "Çıkış yapmak"): Promise<boolean | undefined> {
  let sonuc: boolean | undefined;
  await act(async () => {
    sonuc = await guard(etiket, { confirmWhenIdle: { title: "Çıkış Yap", body: "genel" } });
  });
  return sonuc;
}

beforeEach(() => {
  mockSira.length = 0;
  mockConfirm.mockClear();
  mockPost.mockClear();
  for (const k of Object.keys(mockCevap)) delete mockCevap[k];
  mockTeyit = true;
});

describe("Y55 — STM bağlı değilken teyitsiz ACİL DURDUR'dan sonra İKİNCİ onayla çıkılır", () => {
  it("KRİTİK: kopuşta E-stop ÖNCE gider, teyit gelmez → ikinci onay; EVET → çıkılır", async () => {
    mockTeyit = false;
    await kur(dizi);
    const sonuc = await cik();
    expect(mockSira[1]).toBe("estop");
    expect(mockSira).toEqual([mockSira[0], "estop", `onay:${IKINCI}`]);
    const govde = mockConfirm.mock.calls[1][1];
    expect(govde).toMatch(/STM bağlı değil/);
    expect(govde).toMatch(/bobinleri kontrol edin/);
    expect(govde).toMatch(/Yine de çıkılsın mı\?/);
    expect(sonuc).toBe(true);
  });

  it("KRİTİK: ikinci onayda HAYIR → ekranda kalınır (söküm yok)", async () => {
    mockTeyit = false;
    mockCevap[IKINCI] = false;
    await kur(dizi);
    expect(await cik("Profil değiştirmek")).toBe(false);
    expect(mockSira).toContain("estop");
  });

  it("KRİTİK: AKTİF SEANS sürerken STM koptu (belirsiz değil, seans) — teyitsizse yine ikinci onay sorulur", async () => {
    mockTeyit = false;
    const ilk = { ...dizi[0], data: { ...dizi[0].data, stm: "online" } };
    await kur([
      ilk,
      { type: "session_update", data: { isActive: true, mode: "Manuel Seans" } },
      { type: "stm_status", data: { stm: "warning", connected: false } },
    ]);
    const sonuc = await cik();
    expect(mockSira).toEqual([mockSira[0], "estop", `onay:${IKINCI}`]);
    expect(sonuc).toBe(true);
  });

  it("KARŞIT: STM ÇEVRİMİÇİ + bobin çalışıyor + teyitsiz → bugünkü gibi İPTAL (ikinci onay YOK)", async () => {
    mockTeyit = false;
    await kur(dizi.slice(0, 16)); // kopuştan ÖNCE: STM online, bobin çalıştı
    const sonuc = await cik();
    expect(mockConfirm).toHaveBeenCalledTimes(1);
    expect(mockSira).toEqual([mockSira[0], "estop", "uyari:TEYITSIZ"]);
    expect(sonuc).toBe(false);
  });

  it("KARŞIT: teyit gelirse ikinci onay YOK; kapı mandalı/teyidi SIFIRLAMAZ (Sıfırla çağrısı yok)", async () => {
    await kur(dizi);
    expect(await cik()).toBe(true);
    expect(mockConfirm).toHaveBeenCalledTimes(1);
    mockTeyit = false;
    await cik();
    expect(mockPost.mock.calls.filter(([p]) => String(p).includes("estop_mandali"))).toEqual([]);
  });
});
