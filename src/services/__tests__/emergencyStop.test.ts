// Author: mertaygn, cglrgrkn
/**
 * emergencyStop — acil durdurmanın TEK KAYNAĞI (hasta güvenliği).
 *
 * ⚠️ 2026-08-09 DENETİMİ — "TEYİT YALANI" KAPATILDI.
 * Bu dosyanın eski hâli, kapatılan hatayı SÖZLEŞME olarak kilitliyordu: `stmStopped VEYA
 * herhangi-bir-bobin-success` teyit sayılıyordu. Bu bir VEYA olduğu için STM durup 3 ESP
 * bobininin ÜÇÜ birden başarısız olsa bile arayüz "çıktılar kesildi" diyordu. Backend AYNI
 * yanıtta doğru cevabı (`confirmed` = TÜM transport'lar) zaten gönderiyordu.
 *
 * Kilitlenen davranışlar:
 *   - teyit YALNIZ backend'in `confirmed` alanından okunur, istemci YENİDEN TÜRETMEZ,
 *   - kısmi durdurma (STM ok / ESP başarısız) teyit SAYILMAZ,
 *   - son çare yolu ESP'yi kapsamadığı için ASLA teyit iddia etmez,
 *   - bridge isteği kimlik bilgisiyle gider (header'sız gidince uzaktan hep 401 alıyordu),
 *   - ASLA throw etmez (acil durdurma akışı kırılmamalı).
 */
jest.mock("@/services/apiClient", () => ({
  apiPost: jest.fn(),
  authHeaders: jest.fn(() => ({ "X-API-Key": "dev-token" })),
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { bridgeBaseUrl: "https://tunnel.example/api" },
}));

import { apiPost } from "@/services/apiClient";
import { performEmergencyStop } from "@/services/emergencyStop";

const mockApiPost = apiPost as jest.Mock;
const fetchMock = () => (global as unknown as { fetch: jest.Mock }).fetch;

/** Bridge yanıtı üret. */
const bridge = (govde: unknown, ok = true, status = 200) =>
  fetchMock().mockResolvedValue({ ok, status, json: async () => govde });

beforeEach(() => {
  mockApiPost.mockReset();
  (global as { fetch: unknown }).fetch = jest.fn();
});

// ── teyit yalnız backend'den ──────────────────────────────────────────────────

it("backend confirmed:true → confirmed:true ve YEDEK yol ÇAĞRILMAZ", async () => {
  bridge({ status: "success", confirmed: true, stmStopped: true, mqttResults: [{ mqtt: "success" }] });
  const res = await performEmergencyStop();
  expect(res.confirmed).toBe(true);
  expect(mockApiPost).not.toHaveBeenCalled(); // gereksiz ikinci tur yok
});

it("KRİTİK: STM durdu ama ESP bobinleri DURMADI → teyit YOK", async () => {
  // Backend `confirmed:false, status:"partial"` der. Eski istemci bunu `stmStopped` VEYA'sıyla
  // "durdu" sayıyordu: ESP bobinleri HASTANIN ÜZERİNDE çalışırken operatöre "kesildi" deniyordu.
  bridge({
    status: "partial", confirmed: false, stmStopped: true,
    mqttResults: [{ mqtt: "mqtt_unavailable" }, { mqtt: "mqtt_unavailable" }, { mqtt: "mqtt_unavailable" }],
  });
  mockApiPost.mockResolvedValue(null);            // yedek yollar da teyit veremiyor
  expect((await performEmergencyStop()).confirmed).toBe(false);
});

it("KRİTİK: 8 bobinden yalnız 1'i onaylandı → teyit YOK (kısmi durdurma teyit değildir)", async () => {
  bridge({
    status: "partial", confirmed: false, stmStopped: false,
    mqttResults: [{ mqtt: "success" }, { mqtt: "mqtt_unavailable" }, { mqtt: "mqtt_unavailable" }],
  });
  mockApiPost.mockResolvedValue(null);
  expect((await performEmergencyStop()).confirmed).toBe(false);
});

it("KRİTİK: ESP durdu ama STM DURMADI → teyit YOK", async () => {
  bridge({
    status: "partial", confirmed: false, stmStopped: false,
    mqttResults: [{ mqtt: "success" }, { mqtt: "success" }, { mqtt: "success" }],
  });
  mockApiPost.mockResolvedValue(null);
  expect((await performEmergencyStop()).confirmed).toBe(false);
});

it("bridge 2xx ama `confirmed` alanı YOKSA teyit sayılmaz (eski backend / bozuk yanıt)", async () => {
  bridge({ stmStopped: true, mqttResults: [{ mqtt: "success" }] });   // confirmed alanı yok
  mockApiPost.mockResolvedValue(null);
  const res = await performEmergencyStop();
  expect(res.confirmed).toBe(false);
  expect(mockApiPost).toHaveBeenCalled();          // yedek gerçekten denendi
});

// ── yedek yollar ──────────────────────────────────────────────────────────────

it("bridge 401 → yedek AYNI yetkili uca gider; backend teyit ederse confirmed:true", async () => {
  bridge({}, false, 401);
  mockApiPost.mockResolvedValueOnce({ confirmed: true, status: "success" });
  const res = await performEmergencyStop();
  expect(res.confirmed).toBe(true);
  expect(mockApiPost.mock.calls[0][0]).toBe("/hardware/emergency_stop");
});

it("KRİTİK: son çare (STM-only) yolu teyit İDDİA ETMEZ — ESP'yi kapsamıyor", async () => {
  // Eskiden burada `/hardware/command` yanıtı "success" ise confirmed:true dönüyordu. O uç
  // yalnız STM 1-5'i durdurur; ESP 6-8 hakkında HİÇBİR kanıt yoktur.
  bridge({}, false, 500);
  mockApiPost
    .mockResolvedValueOnce(null)                    // yetkili uç da başarısız
    .mockResolvedValueOnce({ status: "ok" })        // /session/stop
    .mockResolvedValueOnce({ status: "success" });  // /hardware/command → STM durdu
  const res = await performEmergencyStop();
  expect(res.confirmed).toBe(false);
  // ...ama komutlar YİNE DE gönderilmiş olmalı (teyit edememek, denememek demek değildir).
  const yollar = mockApiPost.mock.calls.map((c) => c[0]);
  expect(yollar).toContain("/session/stop");
  expect(yollar).toContain("/hardware/command");
  expect(mockApiPost.mock.calls[2][1]).toEqual({ command: "stop_all_coils", params: {} });
});

it("hiçbir yol teyit veremezse confirmed:false (kullanıcı fiziksel düğmeye yönlendirilmeli)", async () => {
  fetchMock().mockRejectedValue(new Error("network"));
  mockApiPost.mockResolvedValue(null);
  expect((await performEmergencyStop()).confirmed).toBe(false);
});

// ── değişmeyen sözleşmeler (regresyon kapıları) ───────────────────────────────

it("REGRESYON: bridge isteği X-API-Key ile gider (uzaktan 401 alıp yedek yola düşmesin)", async () => {
  bridge({ confirmed: true });
  await performEmergencyStop();
  const [url, init] = fetchMock().mock.calls[0];
  expect(String(url)).toContain("/hardware/emergency_stop");
  expect((init.headers as Record<string, string>)["X-API-Key"]).toBe("dev-token");
});

it("KRİTİK: hiçbir koşulda THROW ETMEZ (acil durdurma akışı kırılmamalı)", async () => {
  fetchMock().mockImplementation(() => { throw new Error("boom"); });
  mockApiPost.mockImplementation(() => { throw new Error("boom2"); });
  await expect(performEmergencyStop()).resolves.toEqual({ confirmed: false });
});
