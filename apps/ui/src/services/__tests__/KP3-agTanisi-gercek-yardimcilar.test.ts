/**
 * KP-3 C · services/agTanisi — GERÇEK yardımcılar (saglikSor / telefonIp) ile tanı. agTanisi.test.ts bu ikisini hep ENJEKTE ettiği için
 * gerçek gövdeleri hiç koşmuyordu. Her test bir DAVRANIŞ iddiası:
 *  - Tünel ayakta (PEMF-Vet sağlık yanıtı) + telefon aynı /24'te + yerel adres ulaşılmaz → "izolasyon" (cihaz IP'siyle).
 *  - Tünel !ok ya da başka bir :8000 sunucusu (service ≠ PEMF-Vet) → cihaz AYAKTA sayılmaz → "cihaz_kapali".
 *  - Sağlık yanıtında yerel IP yok → "bilinmiyor"; telefonun Wi-Fi adresi okunamaz / IPv4 değil / NetInfo patlar → "bilinmiyor" (tahmin YOK).
 * SAHTE (en alt kat): global fetch, @react-native-community/netinfo; kimlik okuma ve bulut çözümü enjekte.
 */
jest.mock("@react-native-community/netinfo", () => ({ __esModule: true, default: { fetch: jest.fn() } }));

import NetInfo from "@react-native-community/netinfo";
import type { UzakCozumleme } from "../deviceRegistry";
import { agTanisiYap } from "../agTanisi";

const TUNEL = "https://x.trycloudflare.com";
const CIHAZ = "192.168.1.44";
const ilkFetch = global.fetch;
const kimlik = {
  kimlikOku: async () => "140936350360443",
  uzakCoz: async () => ({ durum: "bulundu", device: { device_id: "1" }, url: TUNEL }) as unknown as UzakCozumleme,
};
const netFetch = NetInfo.fetch as unknown as jest.Mock;

function saglik(yanitlar: Record<string, unknown>) {
  global.fetch = jest.fn((url: string) => {
    const y = yanitlar[url];
    if (y === undefined) return Promise.reject(new TypeError("Network request failed"));
    if (y === "!ok") return Promise.resolve({ ok: false, json: async () => ({}) });
    return Promise.resolve({ ok: true, json: async () => y });
  }) as unknown as typeof fetch;
}

afterEach(() => {
  global.fetch = ilkFetch;
  netFetch.mockReset();
});

it("tünel ayakta + aynı alt ağ + yerel ulaşılmaz → izolasyon", async () => {
  saglik({ [`${TUNEL}/api/health`]: { service: "PEMF-Vet", localIp: CIHAZ } });
  netFetch.mockResolvedValue({ details: { ipAddress: "192.168.1.87" } });
  await expect(agTanisiYap(kimlik)).resolves.toEqual({ durum: "izolasyon", cihazIp: CIHAZ });
  expect((global.fetch as jest.Mock).mock.calls.map((c) => c[0])).toEqual([`${TUNEL}/api/health`, `http://${CIHAZ}:8000/api/health`]);
});

it("tünel !ok ya da PEMF olmayan sunucu → cihaz_kapali", async () => {
  saglik({ [`${TUNEL}/api/health`]: "!ok" });
  await expect(agTanisiYap(kimlik)).resolves.toEqual({ durum: "cihaz_kapali" });
  saglik({ [`${TUNEL}/api/health`]: { service: "baska-sunucu", localIp: CIHAZ } });
  await expect(agTanisiYap(kimlik)).resolves.toEqual({ durum: "cihaz_kapali" });
});

it("yerel IP yok / telefon adresi okunamaz → bilinmiyor", async () => {
  saglik({ [`${TUNEL}/api/health`]: { service: "PEMF-Vet" } });
  await expect(agTanisiYap(kimlik)).resolves.toEqual({ durum: "bilinmiyor" });
  saglik({ [`${TUNEL}/api/health`]: { service: "PEMF-Vet", localIp: CIHAZ } });
  netFetch.mockResolvedValue({ details: { ipAddress: "fe80::1" } });
  await expect(agTanisiYap(kimlik)).resolves.toEqual({ durum: "bilinmiyor" });
  netFetch.mockRejectedValue(new Error("netinfo yok"));
  await expect(agTanisiYap(kimlik)).resolves.toEqual({ durum: "bilinmiyor" });
});
