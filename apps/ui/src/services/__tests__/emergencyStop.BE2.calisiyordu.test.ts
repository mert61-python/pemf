// Author: mertaygn, cglrgrkn
/**
 * BE 2b · Y227 — `performEmergencyStop` iki E-stop yanıtının (1. adım bridge + 2. adım yetkili uç) "durdurma ANINDA çalışıyor muydu"
 * bilgisini birleştirir: aynı basışta İKİNCİ istek bobinleri zaten durmuş görür → biri `true` derse `true`; biri okunamadı (`null`)
 * derse `null`; ikisi de `false` → `false`; alanı taşıyan yanıt yoksa `undefined` (eski backend → kayan düğme eski davranışta kalır).
 * Gönderim DEĞİŞMEZ (A-63): her durumda 1 bridge + 3 yedek istek.
 * Sahte: `fetch` (1. adım) ve `apiPost` (2./3. adım) — gerçek `performEmergencyStop`.
 */
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
const yanit = (ek: Record<string, unknown>) => ({ status: "partial", confirmed: false, stmKartYaniti: "yanitsiz", ...ek });

beforeEach(() => {
  mockApiPost.mockReset();
  (global as { fetch: unknown }).fetch = jest.fn();
});

it.each([
  ["1. adım çalışıyordu, 2. adım boştaydı (bobinler 1. adımla durdu)", { calisiyordu: true }, { calisiyordu: false }, true],
  ["1. adım boştaydı, 2. adım çalışıyordu", { calisiyordu: false }, { calisiyordu: true }, true],
  ["ikisi de boştaydı", { calisiyordu: false }, { calisiyordu: false }, false],
  ["biri okunamadı", { calisiyordu: null }, { calisiyordu: false }, null],
  ["okunamadı + boştaydı (ters sıra)", { calisiyordu: false }, { calisiyordu: null }, null],
  ["eski backend (alan yok)", {}, {}, undefined],
  ["1. adım yanıtsız, 2. adım boştaydı", null, { calisiyordu: false }, false],
])("KRİTİK: %s (1. adım %j, 2. adım %j) → calisiyordu = %s; gönderim AYNI", async (_ad, bir, iki, beklenen) => {
  if (bir === null) fetchMock().mockRejectedValue(new Error("bridge erisilemedi"));
  else fetchMock().mockResolvedValue({ ok: true, status: 200, json: async () => yanit(bir) });
  mockApiPost.mockResolvedValueOnce(yanit(iki)).mockResolvedValue({ status: "success" });
  const res = await performEmergencyStop();
  expect(res.confirmed).toBe(false);
  expect(res.calisiyordu).toBe(beklenen);
  expect(fetchMock()).toHaveBeenCalledTimes(1);
  expect(yollar()).toEqual(["/hardware/emergency_stop", "/hardware/command", "/session/stop"]);
});
