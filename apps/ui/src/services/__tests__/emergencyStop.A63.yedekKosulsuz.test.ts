// Author: mertaygn, cglrgrkn
/**
 * D1.105 · A-63 (sahip) — istemcinin 2. ve 3. YEDEK acil durdurma adımları teyitten BAĞIMSIZ, HER ZAMAN koşar.
 * ==========================================================================================================
 * SAHİP KARARI A-63 uygulama kısıtı: "Yedek gönderimler (backend E-stop ×2, seans durdurma, `stop_all`, istemcinin 2. ve
 * 3. yedek adımları) teyitten BAĞIMSIZ, her zaman koşar. Değişen yalnız ekrandaki teyit ölçütüdür; gönderim azaltılamaz
 * (Ö.4-Y8)." Plan zinciri C1-13: backend `confirmed:true` dönünce `performEmergencyStop` 1. adımda ERKEN dönüyor, 2. adım
 * (yetkili uç) ile 3. adım (`/session/stop` + `stop_all_coils`) HİÇ gönderilmiyordu. D1.105 ESP kapalıyken teyidi STM'e
 * bağladığı için bu artık HER başarılı basışta olurdu → E-stop gönderimi AZALIRDI. Bu kapı onu engeller.
 *
 * Ölçüt: gerçek `performEmergencyStop`; sahte olan `fetch` (1. adım) ve `apiPost` (2./3. adım kaydedici). HTTP 200'e
 * bakılmaz — giden İSTEKLER sayılır.
 * ⚠️ MUTASYON: teyitli yanıtta erken dönüş (bugünkü `if (data?.confirmed === true) return …`) geri gelirse KIRMIZI.
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

beforeEach(() => {
  mockApiPost.mockReset();
  (global as { fetch: unknown }).fetch = jest.fn();
});

it("KRİTİK: 1. adım TEYİTLİ (ESP kapalı, STM onayı — A-63) → 2. ve 3. yedek adımlar YİNE gönderilir, sonuç teyitli", async () => {
  fetchMock().mockResolvedValue({
    ok: true, status: 200,
    json: async () => ({ status: "success", confirmed: true, stmStopped: true, mqttResults: [{ coilId: 8, mqtt: "devre_disi" }] }),
  });
  mockApiPost.mockResolvedValue({ status: "success", confirmed: true });
  const res = await performEmergencyStop();
  expect(res.confirmed).toBe(true);
  expect(fetchMock()).toHaveBeenCalledTimes(1);
  // SGI-3.2: `stop_all_coils` 1. adımın yanıtını beklemeden gider; `/session/stop` 1./2. adımdan SONRA.
  expect(yollar()).toEqual(["/hardware/emergency_stop", "/hardware/command", "/session/stop"]);
  expect(mockApiPost.mock.calls[1][1]).toEqual({ command: "stop_all_coils", params: {} });
});

it("KRİTİK: 2. adım teyitli olsa da 3. adım (seans + stop_all) YİNE gönderilir", async () => {
  fetchMock().mockRejectedValue(new Error("bridge erisilemedi"));
  mockApiPost.mockResolvedValueOnce({ status: "success", confirmed: true }).mockResolvedValue({ status: "success" });
  const res = await performEmergencyStop();
  expect(res.confirmed).toBe(true);
  expect(yollar()).toEqual(["/hardware/emergency_stop", "/hardware/command", "/session/stop"]);
});

it("KARŞIT: son çare (3. adım) başarısı tek başına teyit DEĞİL (ESP/STM teyidi yok)", async () => {
  fetchMock().mockResolvedValue({ ok: true, status: 200, json: async () => ({ status: "partial", confirmed: false }) });
  mockApiPost.mockResolvedValueOnce({ status: "partial", confirmed: false }).mockResolvedValue({ status: "success" });
  const res = await performEmergencyStop();
  expect(res.confirmed).toBe(false);
  expect(yollar()).toEqual(["/hardware/emergency_stop", "/hardware/command", "/session/stop"]);
});
