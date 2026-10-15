// Author: mertaygn, cglrgrkn
/**
 * CH1 · Y151 — park edilen (etkin olmayan) e-posta hesaplarının belirteçleri bugünkü TEK hesapla AYNI güvenlik düzeyinde saklanır.
 * =================================================================================================================================
 * SÖZLEŞME (`services/hesapDeposu`): depo = supabase-js'e verilen depo (`supabaseAuth.oturumDeposu`):
 *   · native (Android / iOS) → SecureStore (Keystore / Keychain, parçalı) — AsyncStorage'a (düz metin) YAZILMAZ;
 *   · masaüstü penceresi (loopback) → YALNIZ BELLEK — localStorage / AsyncStorage'a YAZILMAZ (otorite launcher);
 *   · LAN / mobil web → AsyncStorage (bugünkü tek oturumla aynı yer).
 * Bozuk / okunamayan depo "yok" sayılır (fırlatmaz); belirteç DEĞERİ günlüğe yazılmaz; aynı e-posta tekrar park edilince yerine yazılır.
 * ⚠️ MUTASYON: depo AsyncStorage'a sabitlenirse native / masaüstü kolu KIRMIZI; e-posta karşılaştırması büyük-küçük harfe duyarlı
 * olursa yineleme kolu KIRMIZI.
 */
const KEY = "pemf-hesaplar-v1";
const RT = "PARK-YENILEME-BELIRTECI-GIZLI";

const localDepo = new Map<string, string>();
function pencereyiKur(hostname: string | null) {
  const ls = {
    getItem: (k: string) => (localDepo.has(k) ? localDepo.get(k)! : null),
    setItem: (k: string, v: string) => { localDepo.set(k, v); },
    removeItem: (k: string) => { localDepo.delete(k); },
    clear: () => localDepo.clear(),
  };
  const g = globalThis as Record<string, unknown>;
  if (!g.window) g.window = {};
  const w = g.window as Record<string, unknown>;
  Object.defineProperty(w, "location", { value: hostname == null ? undefined : { hostname }, configurable: true, writable: true });
  Object.defineProperty(w, "localStorage", { value: ls, configurable: true, writable: true });
}

const mockGuvenli = new Map<string, string>();
jest.mock("@react-native-async-storage/async-storage", () =>
  require("@react-native-async-storage/async-storage/jest/async-storage-mock"),
);
jest.mock("expo-secure-store", () => ({
  getItemAsync: async (k: string) => (mockGuvenli.has(k) ? mockGuvenli.get(k)! : null),
  setItemAsync: async (k: string, v: string) => { mockGuvenli.set(k, v); },
  deleteItemAsync: async (k: string) => { mockGuvenli.delete(k); },
}));
jest.mock("@supabase/supabase-js", () => ({ createClient: () => ({ auth: {} }) }));

type AS = { getItem: (k: string) => Promise<string | null>; getAllKeys: () => Promise<string[]>; multiGet: (k: string[]) => Promise<[string, string | null][]> };

function yukle(os: string) {
  jest.resetModules();
  /* eslint-disable @typescript-eslint/no-require-imports */
  const RN = require("react-native");
  RN.Platform.OS = os;
  const ASmod = require("@react-native-async-storage/async-storage");
  const as: AS = ASmod.default ?? ASmod;
  const depo = require("@/services/hesapDeposu");
  /* eslint-enable @typescript-eslint/no-require-imports */
  return { depo, as };
}

async function asyncStorageIcerik(as: AS): Promise<string> {
  const anahtarlar = await as.getAllKeys();
  return (await as.multiGet(anahtarlar)).map(([k, v]) => `${k}=${v}`).join("\n");
}

const A = { email: "a@klinik.com", access_token: "AT-A", refresh_token: RT, expires_at: 1 };

beforeEach(() => {
  localDepo.clear();
  mockGuvenli.clear();
});

it("KRİTİK native: park edilen yenileme belirteci SecureStore'a gider, AsyncStorage'a (düz metin) GİTMEZ", async () => {
  pencereyiKur(null);
  const { depo, as } = yukle("android");
  await depo.parkEt(A);
  const guvenli = [...mockGuvenli.values()].join("");
  expect(guvenli).toContain(RT);
  expect(await asyncStorageIcerik(as)).not.toContain(RT);
  expect((await depo.parkHesaplari()).map((h: { email: string }) => h.email)).toEqual(["a@klinik.com"]);
});

it("KRİTİK masaüstü penceresi (loopback): YALNIZ BELLEK — localStorage / AsyncStorage / SecureStore'a yazılmaz", async () => {
  pencereyiKur("127.0.0.1");
  const { depo, as } = yukle("web");
  await depo.parkEt(A);
  expect((await depo.parkHesaplari())[0].refresh_token).toBe(RT); // pencere ömrü boyunca bellekte
  expect([...localDepo.values()].join("")).not.toContain(RT);
  expect(await asyncStorageIcerik(as)).not.toContain(RT);
  expect([...mockGuvenli.values()].join("")).not.toContain(RT);
});

it("KARŞIT LAN / mobil web: bugünkü tek oturumla AYNI yer (AsyncStorage)", async () => {
  pencereyiKur("192.168.1.20");
  const { depo, as } = yukle("web");
  await depo.parkEt(A);
  expect(await as.getItem(KEY)).toContain(RT);
});

it("aynı e-posta (büyük-küçük harf farkıyla) yeniden park edilince YERİNE yazılır; çıkar / tümünü sil", async () => {
  pencereyiKur(null);
  const { depo } = yukle("android");
  await depo.parkEt(A);
  await depo.parkEt({ ...A, email: "A@Klinik.com", refresh_token: "YENI-RT" });
  await depo.parkEt({ email: "b@klinik.com", access_token: "AT-B", refresh_token: "RT-B" });
  const liste = await depo.parkHesaplari();
  expect(liste.map((h: { email: string }) => h.email.toLowerCase())).toEqual(["a@klinik.com", "b@klinik.com"]);
  expect(liste[0].refresh_token).toBe("YENI-RT");
  expect((await depo.parkHesabi("B@KLINIK.COM"))?.refresh_token).toBe("RT-B");
  await depo.parktanCikar("a@KLINIK.com");
  expect((await depo.parkHesaplari()).map((h: { email: string }) => h.email)).toEqual(["b@klinik.com"]);
  await depo.hepsiniSil();
  expect(await depo.parkHesaplari()).toEqual([]);
  expect([...mockGuvenli.values()].join("")).not.toContain("RT-B");
});

it("bozuk depo 'yok' sayılır (fırlatmaz) ve belirteç değeri günlüğe YAZILMAZ", async () => {
  pencereyiKur(null);
  const { depo } = yukle("android");
  const spy = [jest.spyOn(console, "log"), jest.spyOn(console, "warn"), jest.spyOn(console, "error")];
  mockGuvenli.set(KEY, "{bozuk json " + RT);
  expect(await depo.parkHesaplari()).toEqual([]);
  await depo.parkEt({ email: "", access_token: "x", refresh_token: RT }); // geçersiz → yok sayılır
  const yazilan = spy.flatMap((s) => s.mock.calls.flat()).map(String).join("\n");
  expect(yazilan).not.toContain(RT);
  spy.forEach((s) => s.mockRestore());
});
