/**
 * KP-3 C · deviceRegistry kenar kolları — her test bir DAVRANIŞ iddiası ("kod yanlış" yalnız gerçekten kayıt yoksa denir):
 *  - Supabase istemcisi KURULAMAZSA sonuç "hata" (internet / yapılandırma) — "yok" (kod yanlış) DEĞİL; sonraki çağrı kurmayı yeniden dener.
 *  - Adresi olan ama HİÇ heartbeat'i (last_seen) olmayan cihaz canlı sayılmaz → "bayat" (adres döndürülmez).
 *  - RPC yanıt vermezse keşif DONMAZ: 6 sn'de "hata" (5,999 sn'de hâlâ bekliyor).
 * SAHTE (en alt kat): @supabase/supabase-js `createClient` (ağ istemcisi). GERÇEK: deviceRegistry.
 */
const mockRpc = jest.fn();
let mockKurulumAtar = false;
const mockKurulum = jest.fn(() => {
  if (mockKurulumAtar) throw new Error("supabaseUrl is required (aparat)");
  return { rpc: mockRpc };
});
jest.mock("@supabase/supabase-js", () => ({ createClient: () => mockKurulum() }));

import { getRemoteUrlForDevice, uzakCihaziKimlikleCoz, uzakCihaziKodlaCoz } from "@/services/deviceRegistry";

beforeEach(() => { mockRpc.mockReset(); mockKurulum.mockClear(); });
afterEach(() => jest.useRealTimers());

// ⚠️ Sıra önemli: istemci modül düzeyinde önbelleğe alınır — "kurulamaz" senaryosu İLK test (henüz istemci yok).
it("istemci kurulamazsa 'hata' (kod yanlış değil); sonraki çağrı kurmayı yeniden dener", async () => {
  mockKurulumAtar = true;
  expect(await uzakCihaziKodlaCoz("MVPDDN")).toEqual({ durum: "hata" });
  expect(mockRpc).not.toHaveBeenCalled();
  mockKurulumAtar = false;
  mockRpc.mockResolvedValue({ data: [], error: null });
  expect(await uzakCihaziKodlaCoz("MVPDDN")).toEqual({ durum: "yok" });
  expect(mockKurulum).toHaveBeenCalledTimes(2);
});

it("heartbeat'i hiç olmayan cihaz 'bayat' — adres döndürülmez", async () => {
  mockRpc.mockResolvedValue({ data: [{ device_id: "1", tunnel_url: "https://t.example.com", last_seen: null }], error: null });
  const c = await uzakCihaziKimlikleCoz("1");
  expect(c.durum).toBe("bayat");
  expect(await getRemoteUrlForDevice("1")).toBeNull();
});

it("RPC yanıt vermezse 6 sn'de 'hata' (keşif donmaz)", async () => {
  jest.useFakeTimers();
  mockRpc.mockReturnValue(new Promise(() => undefined));
  let sonuc: unknown = "bekliyor";
  void uzakCihaziKodlaCoz("ASILI").then((r) => { sonuc = r; });
  await jest.advanceTimersByTimeAsync(5999);
  expect(sonuc).toBe("bekliyor");
  await jest.advanceTimersByTimeAsync(1);
  expect(sonuc).toEqual({ durum: "hata" });
});
