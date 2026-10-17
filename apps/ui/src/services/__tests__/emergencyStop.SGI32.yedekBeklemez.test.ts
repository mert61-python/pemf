// Author: mertaygn, cglrgrkn
// SGI-3.2 (A3 · K3 · TD3) — ÖNCE-KIRMIZI: yedek STOP adımları 1. adımın YANITINI beklememeli.
// TD3 (2d28ad05) backend'de STOP porta yazıldıktan SONRA kartın yanıtını ≤ 0,25 sn bekliyor (NACK'li / yanıtsız kartta tam süre;
// ölçüldü: ebeveyn e77537fc 0–15 ms → uç 250–282 ms). `performEmergencyStop` adımları SIRAYLA `await` ettiği için 2. adım (yetkili
// uç) ve `stop_all_coils` bu bekleme kadar (×2) GEÇ gidiyordu. A-63 · 1-C i3-F-5: yedekler her zaman ve GECİKMEDEN koşar (Ö.4:
// gecikme de kapılanmadır). Ölçüt: 1. ve 2. adımın yanıtı GELMEMİŞKEN giden istekler. `/session/stop` 1./2. adımdan SONRA kalır
// (E-stop'un seans kaydını "acil-durdurma" kapatmasıyla yarışmasın).
jest.mock("@/services/apiClient", () => ({
  apiPost: jest.fn(),
  authHeaders: jest.fn(() => ({})),
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { bridgeBaseUrl: "http://127.0.0.1:8000/api" },
}));

import { apiPost } from "@/services/apiClient";
import { performEmergencyStop } from "@/services/emergencyStop";

const mockApiPost = apiPost as jest.Mock;
const fetchMock = () => (global as unknown as { fetch: jest.Mock }).fetch;
const yollar = () => mockApiPost.mock.calls.map((c) => c[0]);

beforeEach(() => {
  mockApiPost.mockReset();
  (global as { fetch: unknown }).fetch = jest.fn();
});

it("SGI-3.2 KRİTİK: kart yanıtı beklenirken (1. ve 2. adım yanıtsız) yedek E-stop ve stop_all_coils YİNE hemen gider", async () => {
  let bitir1: (v: unknown) => void = () => undefined;
  let bitir2: (v: unknown) => void = () => undefined;
  fetchMock().mockImplementation(() => new Promise((res) => { bitir1 = res; }));
  mockApiPost.mockImplementation((yol: string) =>
    yol === "/hardware/emergency_stop"
      ? new Promise((res) => { bitir2 = res; })
      : Promise.resolve({ status: "success" }));
  const p = performEmergencyStop();
  await new Promise((r) => setTimeout(r, 30));
  expect(fetchMock()).toHaveBeenCalledTimes(1);
  // 1. adım yanıtsızken 2. adım (yetkili uç) ve stop_all_coils GİTMİŞ olmalı
  expect(yollar()).toEqual(["/hardware/emergency_stop", "/hardware/command"]);
  expect(mockApiPost.mock.calls[1][1]).toEqual({ command: "stop_all_coils", params: {} });
  bitir1({ ok: true, status: 200, json: async () => ({ confirmed: false, stmKartYaniti: "red" }) });
  bitir2({ confirmed: false, stmKartYaniti: "red" });
  await expect(p).resolves.toEqual({ confirmed: false, kartReddetti: true });
  // A-63: hiçbir adım AZALMADI — seans durdurma 1./2. adımdan sonra yine gitti
  expect(yollar()).toEqual(["/hardware/emergency_stop", "/hardware/command", "/session/stop"]);
});

it("SGI-3.2 KARŞIT: /session/stop 1. adımın yanıtından ÖNCE gitmez (E-stop'un seans kaydıyla yarışmaz)", async () => {
  let bitir1: (v: unknown) => void = () => undefined;
  fetchMock().mockImplementation(() => new Promise((res) => { bitir1 = res; }));
  mockApiPost.mockImplementation(() => Promise.resolve({ status: "success", confirmed: true }));
  const p = performEmergencyStop();
  await new Promise((r) => setTimeout(r, 30));
  expect(yollar()).not.toContain("/session/stop");
  bitir1({ ok: true, status: 200, json: async () => ({ confirmed: true }) });
  await expect(p).resolves.toEqual({ confirmed: true, kartReddetti: false });
  expect(yollar()).toContain("/session/stop");
});

it("SGI-3.2 KARŞIT: teyit hâlâ 1. VEYA 2. adımın backend teyidinden gelir; 3. adım teyit vermez", async () => {
  fetchMock().mockResolvedValue({ ok: true, status: 200, json: async () => ({ confirmed: false }) });
  mockApiPost.mockImplementation((yol: string) =>
    Promise.resolve(yol === "/hardware/emergency_stop" ? { confirmed: true } : { status: "success" }));
  await expect(performEmergencyStop()).resolves.toEqual({ confirmed: true, kartReddetti: false });
  mockApiPost.mockReset();
  mockApiPost.mockImplementation((yol: string) =>
    Promise.resolve(yol === "/hardware/emergency_stop" ? { confirmed: false } : { status: "success", confirmed: true }));
  await expect(performEmergencyStop()).resolves.toEqual({ confirmed: false, kartReddetti: false });
});
