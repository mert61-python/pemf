// Author: mertaygn, cglrgrkn
/**
 * TD3 — `performEmergencyStop` kartın STOP reddini (`stmKartYaniti:"red"`) `kartReddetti` olarak taşır; teyit yine YALNIZ backend'in
 * `confirmed`'ından (istemci yeniden türetmez). Bir adım teyit verdiyse `kartReddetti` false (operatöre yanlış alarm yok). Yedek
 * adımlar teyitten ve redden BAĞIMSIZ koşar (A-63 · Ö.4-Y8).
 */
jest.mock("@/services/apiClient", () => ({
  apiPost: jest.fn(),
  authHeaders: jest.fn(() => ({ "X-API-Key": "dev-token" })),
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { bridgeBaseUrl: "https://tunnel.example/api" },
}));

import { apiPost } from "@/services/apiClient";
import {
  EMERGENCY_STOP_KART_RED_BODY,
  EMERGENCY_STOP_KART_RED_TITLE,
  performEmergencyStop,
} from "@/services/emergencyStop";

const mockApiPost = apiPost as jest.Mock;
const fetchMock = () => (global as unknown as { fetch: jest.Mock }).fetch;
const bridge = (govde: unknown) => fetchMock().mockResolvedValue({ ok: true, status: 200, json: async () => govde });
const RED = { status: "partial", confirmed: false, stmStopped: true, stmKartYaniti: "red", mqttResults: [{ mqtt: "devre_disi" }] };

beforeEach(() => {
  mockApiPost.mockReset();
  (global as { fetch: unknown }).fetch = jest.fn();
});

it("KRİTİK: backend kart reddi → confirmed:false, kartReddetti:true ve yedek yollar YİNE gönderilir", async () => {
  bridge(RED);
  mockApiPost.mockImplementation(async (p: string) => (p === "/hardware/emergency_stop" ? RED : null));
  const res = await performEmergencyStop();
  expect(res).toEqual({ confirmed: false, kartReddetti: true });
  expect(mockApiPost.mock.calls.map((c) => c[0])).toEqual(["/hardware/emergency_stop", "/hardware/command", "/session/stop"]);
});

it("KARŞIT: yedek adım teyit verdiyse kartReddetti false", async () => {
  bridge(RED);
  mockApiPost.mockImplementation(async (p: string) =>
    p === "/hardware/emergency_stop" ? { confirmed: true, stmKartYaniti: "kabul" } : null
  );
  expect(await performEmergencyStop()).toEqual({ confirmed: true, kartReddetti: false });
});

it("KARŞIT: yalnız teyitsiz (kart yanıtı yok) → kartReddetti false", async () => {
  bridge({ status: "partial", confirmed: false, stmStopped: false, stmKartYaniti: null });
  mockApiPost.mockResolvedValue(null);
  expect(await performEmergencyStop()).toEqual({ confirmed: false, kartReddetti: false });
});

it("metin EYLEM söyler (gücü kes / USB)", () => {
  expect(EMERGENCY_STOP_KART_RED_TITLE).toContain("REDDETTİ");
  expect(EMERGENCY_STOP_KART_RED_BODY).toMatch(/gücünü kesin ya da USB kablosunu çıkarın/);
});
