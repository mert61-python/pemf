// Author: mertaygn, cglrgrkn
/**
 * MASAÜSTÜ PENCERESİ OTURUMU KALICI TUTMAMALI — "güncelleme sonrası e-posta+şifre yeniden" (saha 2026-09-03).
 *
 * Kök neden (USN-journal + GoTrue kaynağıyla ölçüldü): launcher'ın açtığı pencere (127.0.0.1) supabase-js
 * ile AYNI refresh-token ailesinin kendi kalıcı kopyasını `localStorage["sb-<ref>-auth-token"]`de tutuyor
 * ve her açılışta launcher devrinden ÖNCE o ESKİ jetonla `_recoverAndRefresh` deniyordu. Launcher-yalnız
 * açılışlar aileyi ≥2 nesil döndürünce GoTrue reuse-detection TÜM AİLEYİ iptal ediyor → launcher'ın taze
 * jetonu da ölüyor → sonraki açılışta giriş ekranı.
 *
 * Değişmezler (mutasyon-korumalı):
 *  1) Loopback host'ta supabase-js'e verilen storage BELLEK-İÇİ: tohumlanan bayat kopya getItem'da
 *     GÖRÜNMEZ, localStorage'daki eski anahtar TEMİZLENİR ve yazılanlar AsyncStorage'a GİTMEZ.
 *     (Temizleme silinir / AsyncStorage'a dönülürse → KIRMIZI.)
 *  2) KARŞIT KANIT: loopback DEĞİLSE (LAN tarayıcı / mobil web) eski kalıcı yol AYNEN korunur — AsyncStorage
 *     tohumu getItem'da görünür. (Koşul kaldırılıp herkes belleğe geçirilirse → KIRMIZI.)
 *  3) Native'de (Platform.OS != web) loopback kontrolü devre dışı.
 *
 * ⚠️ `jest.isolateModules` TAZE bir modül kaydı açar: Platform.OS mutasyonu ve AsyncStorage tohumu
 *    modülün göreceği kopyada olmalı → ikisi de izole kayıt İÇİNDE yapılır.
 */
const KEY = "sb-wmsxonunkphjeregpvuj-auth-token";
const TOHUM = JSON.stringify({ access_token: "ESKI", refresh_token: "ESKI-2-NESIL", expires_at: 1 });

// window.location + window.localStorage'ı kontrol edilebilir bir şimle sabitle (jsdom olsun olmasın).
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

jest.mock("@react-native-async-storage/async-storage", () =>
  require("@react-native-async-storage/async-storage/jest/async-storage-mock"),
);
jest.mock("expo-secure-store", () => ({
  getItemAsync: async () => null,
  setItemAsync: async () => undefined,
  deleteItemAsync: async () => undefined,
}));

// `createClient`ı yakala → üretimde kullanılan storage adaptörünü al.
const tutucu: { opts: unknown } = { opts: null };
jest.mock("@supabase/supabase-js", () => ({
  createClient: (_u: string, _k: string, o: unknown) => {
    tutucu.opts = o;
    return { auth: {} };
  },
}));

type Adaptor = {
  getItem: (k: string) => Promise<string | null>;
  setItem: (k: string, v: string) => Promise<void>;
  removeItem: (k: string) => Promise<void>;
};
type AsyncStorageLike = { getItem: (k: string) => Promise<string | null>; setItem: (k: string, v: string) => Promise<void> };
type Yuklenen = { st: Adaptor; AS: AsyncStorageLike; masaustuLoopbackMi: () => boolean };

/**
 * Modülü TAZE ana kayıtta yükle. ⚠️ `jest.isolateModules` KULLANILMAZ: react-native'in `Platform`
 * getter'ı tembel `require` ile çözülür ve izole kayıt YALNIZ callback içinde aktiftir → callback
 * dışında yapılan çağrılar (getItem/masaustuLoopbackMi) ana kayıttaki Platform'u (OS=ios) görür ve
 * test sahte-kırmızı/yeşil olur (ölçüldü). `resetModules` + ana kayıtta mutasyon her yerde tutarlıdır.
 */
function moduluYukle(os: string, hazirla?: (AS: AsyncStorageLike) => void): Yuklenen {
  tutucu.opts = null;
  jest.resetModules();
  /* eslint-disable @typescript-eslint/no-require-imports */
  const RN = require("react-native");
  RN.Platform.OS = os;
  const ASmod = require("@react-native-async-storage/async-storage");
  const AS: AsyncStorageLike = ASmod.default ?? ASmod;
  hazirla?.(AS);
  const mod = require("@/services/supabaseAuth");
  /* eslint-enable @typescript-eslint/no-require-imports */
  const opts = tutucu.opts as { auth?: { storage?: Adaptor } } | null;
  const st = opts?.auth?.storage;
  if (!st) throw new Error("createClient storage yakalanamadı");
  return { st, AS, masaustuLoopbackMi: mod.masaustuLoopbackMi };
}

describe("supabaseAuth masaüstü (loopback) oturum deposu", () => {
  beforeEach(() => { localDepo.clear(); });

  it("KRİTİK: loopback'te bayat kalıcı kopya SUNULMAZ, localStorage TEMİZLENİR, yazılanlar AsyncStorage'a GİTMEZ", async () => {
    pencereyiKur("127.0.0.1");
    localDepo.set(KEY, TOHUM); // eski kurulumdan kalan 2-nesil-geri jeton
    const { st, AS, masaustuLoopbackMi } = moduluYukle("web");
    expect(masaustuLoopbackMi()).toBe(true);
    expect(await st.getItem(KEY)).toBeNull();      // _recoverAndRefresh bayat jetonu göremez
    expect(localDepo.get(KEY)).toBeUndefined();    // kalıcı kopya temizlendi
    await st.setItem(KEY, "TAZE");
    expect(await st.getItem(KEY)).toBe("TAZE");    // pencere ömrü boyunca bellekte
    expect(await AS.getItem(KEY)).toBeNull();      // kalıcılık YOK (bellek adaptörü)
    expect(localDepo.has(KEY)).toBe(false);
    await st.removeItem(KEY);
    expect(await st.getItem(KEY)).toBeNull();
  });

  it("loopback 'localhost' da masaüstü sayılır", () => {
    pencereyiKur("localhost");
    expect(moduluYukle("web").masaustuLoopbackMi()).toBe(true);
  });

  it("KARŞIT KANIT: loopback DEĞİLSE (LAN/mobil web) kalıcı yol korunur — AsyncStorage tohumu görünür", async () => {
    pencereyiKur("192.168.1.20");
    const { st, AS, masaustuLoopbackMi } = moduluYukle("web", (as) => { void as.setItem(KEY, TOHUM); });
    expect(masaustuLoopbackMi()).toBe(false);
    expect(await st.getItem(KEY)).toBe(TOHUM);
    expect(await AS.getItem(KEY)).toBe(TOHUM);
  });

  it("native'de (Platform.OS != web) loopback kontrolü devre dışı", () => {
    pencereyiKur("127.0.0.1");
    expect(moduluYukle("ios").masaustuLoopbackMi()).toBe(false);
  });

  it("window.location yoksa (native runtime) masaüstü sayılmaz", () => {
    pencereyiKur(null);
    expect(moduluYukle("web").masaustuLoopbackMi()).toBe(false);
  });
});
