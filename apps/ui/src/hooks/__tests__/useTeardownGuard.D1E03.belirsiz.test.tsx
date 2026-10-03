// Author: mertaygn, cglrgrkn
/**
 * D1.E03 · İG-6.41 · A-59 — STM "BELİRSİZ"ken çıkış / profil değişimi GÜVENLİK ONAYI ister ve kabuk sökülmeden
 * ÖNCE ACİL DURDUR gönderilir. "Belirsiz" = çalışıyor sayılır (sahip kararı A-59).
 * ==============================================================================================================
 * ÖLÇÜLEN KUSUR (aday doğrulaması İG-6.41, gerçek backend + web): manuel sürüş sırasında STM koptu → kayan ACİL DURDUR
 * "(bağlantı yok)" gösterirken "Farklı Bir Profile Geçiş Yap" hiç onay sormadan kabuğu söküyor (karşılama ekranında
 * durdurma kontrolü 0); "Çıkış Yap" yalnız genel bir onay soruyor, güvenlik uyarısı ve E-stop yok. Neden: kapı yalnız
 * `running` / `isActive`'e bakıyordu; kopuşta bobinler `running:false` görünür ("durdu" değil "bilinmiyor").
 *
 * Dizi ELLE YAZILMADI: D1.74'ün `__fixtures__/stmKopusuManuelBobin.ws.json`'u (GERÇEK backend, seanssız manuel bobin +
 * kopuş; bayatlık kapısı pytest'te). D1.74'ten önce bu senaryoda "belirsiz" hiç oluşmuyordu (override) → kapı D1.74'e bağlı.
 *
 * ⚠️ MUTASYON: kapıdan `donanimBelirsiz` koşulu silinirse KRİTİK kollar; belirsizlik kilidi kaldırılırsa (STM
 * çevrimdışı = her zaman belirsiz) donanımsız makine KARŞIT kolu KIRILIR.
 */
const mockSira: string[] = [];
const mockConfirm = jest.fn(async (title: string, _body: string, _ok?: string) => {
  mockSira.push(`onay:${title}`);
  return true;
});
let mockTeyit = true;
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async (_p: string, fb: unknown) => fb),
  apiPost: jest.fn(async (_p: string, _b: unknown, fb: unknown) => fb),
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

beforeEach(() => {
  mockSira.length = 0;
  mockConfirm.mockClear();
  mockTeyit = true;
});

describe("D1.E03 / A-59 — STM belirsizken kabuk sökümü", () => {
  it("KRİTİK: kopuştan sonra profil değişimi GÜVENLİK onayı ister ve ACİL DURDUR sökümden ÖNCE gider", async () => {
    await kur(dizi);
    let sonuc: boolean | undefined;
    await act(async () => {
      sonuc = await guard("Profil değiştirmek");
    });
    expect(mockConfirm).toHaveBeenCalledTimes(1);
    const [baslik, govde] = mockConfirm.mock.calls[0];
    expect(baslik).toMatch(/çalışıyor olabilir/i);
    expect(govde).toMatch(/BİLİNMİYOR/);
    expect(govde).toMatch(/ACİL DURDUR/);
    expect(mockSira).toEqual([`onay:${baslik}`, "estop"]);
    expect(sonuc).toBe(true);
  });

  it("KRİTİK: durdurma teyit edilemezse (STM kopuk) söküm İPTAL — operatör durdurma kontrolünü kaybetmez", async () => {
    mockTeyit = false;
    await kur(dizi);
    let sonuc: boolean | undefined;
    await act(async () => {
      sonuc = await guard("Çıkış yapmak", { confirmWhenIdle: { title: "Çıkış Yap", body: "genel" } });
    });
    // Güvenlik onayı GENEL çıkış onayının yerine geçer (boşta sorulan genel onay DEĞİL).
    expect(mockConfirm).toHaveBeenCalledTimes(1);
    expect(mockConfirm.mock.calls[0][0]).toMatch(/çalışıyor olabilir/i);
    expect(mockSira).toContain("estop");
    expect(sonuc).toBe(false);
  });

  it("KRİTİK: bobin güncellemesi HİÇ görülmeden AKTİF SEANS + STM kopuşu da belirsizdir (kural: 'bobin YA DA aktif tedavi')", async () => {
    // 1-E incelemesi (i-7.1): kilidi yalnız çalışan bobinle kuran mutant (aktif seansı saymayan) 455/455 YEŞİL kalıyordu.
    // Periyodik `stm_coil_update`ler geri-basınçta düşebilir (D1.71) — o zaman aktif seans tek "çalışıyordu" kanıtıdır.
    const ilk = { ...dizi[0], data: { ...dizi[0].data, stm: "online" } };
    await kur([
      ilk,
      { type: "session_update", data: { isActive: true, mode: "Manuel Seans" } },
      { type: "stm_status", data: { stm: "warning", connected: false } },
      { type: "session_update", data: { isActive: false, mode: "Acil Durdurma" } },
    ]);
    let sonuc: boolean | undefined;
    await act(async () => {
      sonuc = await guard("Profil değiştirmek");
    });
    expect(mockConfirm).toHaveBeenCalledTimes(1);
    expect(mockConfirm.mock.calls[0][0]).toMatch(/çalışıyor olabilir/i);
    expect(mockSira).toContain("estop");
    expect(sonuc).toBe(true);
  });

  it("KARŞIT: hiç çalışmamış donanımsız makinede (STM çevrimdışı) güvenlik onayı ve E-stop YOK — gürültü yok", async () => {
    await kur(dizi.slice(0, 1)); // yalnız ilk anlık görüntü: stm 'warning', hiçbir bobin hiç çalışmadı
    let sonuc: boolean | undefined;
    await act(async () => {
      sonuc = await guard("Profil değiştirmek");
    });
    expect(mockConfirm).not.toHaveBeenCalled();
    expect(mockSira).not.toContain("estop");
    expect(sonuc).toBe(true);
  });

  it("KARŞIT: STM yeniden çevrimiçi ve boşta → belirsizlik kalkar, onay sorulmaz", async () => {
    const kopus = dizi.findIndex((m) => m.type === "stm_status" && m.data?.stm === "warning");
    const geriGeldi = { type: "stm_status", data: { stm: "online", connected: true } };
    await kur([...dizi, geriGeldi]);
    expect(kopus).toBeGreaterThan(0);
    let sonuc: boolean | undefined;
    await act(async () => {
      sonuc = await guard("Profil değiştirmek");
    });
    expect(mockConfirm).not.toHaveBeenCalled();
    expect(sonuc).toBe(true);
  });
});
