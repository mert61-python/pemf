/**
 * KP-3 C · services/discovery — KEŞİF MERDİVENİ (her test bir davranış iddiası):
 *  - Kod takası: jeton gelirse saklanır (true); jetonsuz 200 / 403 / ağ hatası → false. Kod gövdede gider; çıplak IP :8000'e tamamlanır.
 *  - Kimlik yolu erişimi: aynı ağda jeton cihazdan alınır; değilse SAKLI anahtar `/api/system/info`'ya karşı sınanır (YALNIZ 2xx geçer —
 *    429 "bağlandı" sayılmaz); bozuk jeton gövdesi saklı anahtara düşer; ikisi de ulaşılamazsa false.
 *  - Zaman aşımı: yanıtsız uç HEALTH_TIMEOUT_MS (2,5 sn) sonra İPTAL edilir → false (askıda kalmaz).
 *  - Tam merdiven: kayıtlı adres sağlıklı ama BİÇİMİ geçersizse UYGULANMAZ (uyarı) → mDNS (bağlantı-yerel 169.254 atlanır) bulur;
 *    mDNS taraması her durumda durdurulur ve dinleyiciler sökülür (stop atsa bile).
 *  - Uzak (tünel) + LAN YÜKSELTMESİ: kayıtlı cihaz kimliğiyle tünel bulunur; cihazın `localIp`'sine ulaşılıyorsa LAN'a geçilir (güncel
 *    jeton alınır); `localIp` özel ağ IP'si değilse (`10.evil.com`, 127.x) ya da tünel sağlığı 5xx ise tünelde KALINIR.
 *  - Alt ağ taraması: telefonun alt ağı ÖNCE; PEMF olmayan / hata veren hostlar yok sayılır; iki PEMF yanıtlarsa uyarı + İLKİ seçilir,
 *    kimlik ve jeton YALNIZ kazanandan yazılır.
 *  - Nesil koruması: tam tur sürerken hafif yoklama bağlarsa tam tur adres UYGULAMAZ (null) — iki kaynak WS hedefini çırpındırmaz.
 *  - Web: köken sağlıklıysa "current"; hafif / hemen kipleri web'de koşmaz; web'de LAN yükseltmesi YAPILMAZ.
 *  - "kayitliHemen": kayıtlı ÖZEL ağ adresi sağlık denetimi BEKLEMEDEN uygulanır (eski anahtar da okunur); tünel adresi, geçersiz biçim ve
 *    depo hatası → null. Tek uçuş: eşzamanlı iki tam keşif AYNI sözü paylaşır.
 * SAHTE (en alt kat): fetch (URL tablosu), react-native-zeroconf, NetInfo (yerel modüller), Supabase cihaz kaydı (`deviceRegistry`);
 * GERÇEK: config (adres doğrulama + kalıcılık), apiClient (`isPrivateHost`), duzHttpKapisi, AsyncStorage (jest.setup bellek sahtesi).
 */
const mockZc = { kip: "paketYok" as "paketYok" | "bul" | "sessiz" | "kurucuAtar", adres: [] as string[], durdur: 0, sok: 0, stopAtar: false };
jest.mock(
  "react-native-zeroconf",
  () => {
    class Zeroconf {
      private h: Record<string, (s: unknown) => void> = {};
      constructor() {
        if (mockZc.kip === "kurucuAtar") throw new Error("native modül yok");
      }
      on(e: string, f: (s: unknown) => void) { this.h[e] = f; }
      scan() {
        if (mockZc.kip === "bul") setTimeout(() => this.h.resolved?.({ addresses: mockZc.adres, port: 8000 }), 0);
      }
      stop() { mockZc.durdur += 1; if (mockZc.stopAtar) throw new Error("stop düştü"); }
      removeDeviceListeners() { mockZc.sok += 1; }
    }
    return {
      __esModule: true,
      get default() {
        if (mockZc.kip === "paketYok") throw new Error("Cannot find module 'react-native-zeroconf'");
        return Zeroconf;
      },
    };
  },
  { virtual: true },
);
let mockNetIp = "10.0.5.23";
jest.mock("@react-native-community/netinfo", () => ({
  __esModule: true,
  default: { fetch: jest.fn(async () => ({ type: "wifi", details: { ipAddress: mockNetIp } })) },
}));
let mockUzakUrl: string | null = null;
jest.mock("@/services/deviceRegistry", () => ({ getRemoteUrlForDevice: jest.fn(async () => mockUzakUrl) }));

import AsyncStorage from "@react-native-async-storage/async-storage";
import { Platform } from "react-native";
import { checkHealth, discoverBackend, exchangeCodeForToken, kimlikYoluErisimi } from "@/services/discovery";
import { getStoredDeviceId, serviceConfig, setStoredApiToken, setStoredDeviceId, updateServiceConfig } from "@/services/config";

type Kayit = { url: string; init: { method?: string; body?: string; headers?: Record<string, string>; signal?: AbortSignal } };
let istekler: Kayit[] = [];
let tablo: Record<string, [number, unknown] | "askida" | ((k: Kayit) => Promise<unknown>)> = {};
const PEMF = (deviceId?: string, ek: object = {}) => [200, { service: "PEMF-Vet", ...(deviceId ? { deviceId } : {}), ...ek }] as [number, unknown];

function askidaYanit(k: Kayit) {
  return new Promise((_c, reddet) => {
    k.init.signal?.addEventListener("abort", () => reddet(Object.assign(new Error("aborted"), { name: "AbortError" })));
  });
}

const ilkOS = Platform.OS;
const ilkTaban = serviceConfig.apiBaseUrl.replace(/\/api$/, "");
beforeEach(async () => {
  istekler = [];
  tablo = {};
  mockZc.kip = "paketYok";
  mockZc.adres = [];
  mockZc.durdur = 0;
  mockZc.sok = 0;
  mockZc.stopAtar = false;
  mockNetIp = "10.0.5.23";
  mockUzakUrl = null;
  await AsyncStorage.clear();
  await setStoredApiToken("");
  (Platform as { OS: string }).OS = "android";
  global.fetch = jest.fn((u: unknown, init: Kayit["init"] = {}) => {
    const k: Kayit = { url: String(u), init };
    istekler.push(k);
    const y = tablo[k.url];
    if (y === "askida") return askidaYanit(k);
    if (typeof y === "function") return y(k);
    if (!y) return Promise.reject(new TypeError("Network request failed"));
    const [durum, govde] = y;
    return Promise.resolve({ ok: durum >= 200 && durum < 300, status: durum, json: async () => govde });
  }) as unknown as typeof fetch;
});
afterEach(() => {
  jest.useRealTimers();
  jest.restoreAllMocks();
  (Platform as { OS: string }).OS = ilkOS;
  updateServiceConfig(ilkTaban);
});

const urller = () => istekler.map((k) => k.url);

describe("kod takası (exchangeCodeForToken)", () => {
  const UC = "http://192.168.1.40:8000/api/auth/exchange";
  it("jeton gelirse saklanır; jetonsuz 200 / 403 / ağ hatası → false; kod gövdede, çıplak IP :8000'e tamamlanır", async () => {
    tablo[UC] = [200, { token: "T-1" }];
    await expect(exchangeCodeForToken("192.168.1.40", "AB12CD")).resolves.toBe(true);
    expect(serviceConfig.apiToken).toBe("T-1");
    expect(JSON.parse(istekler[0].init.body!)).toEqual({ code: "AB12CD" });
    expect(istekler[0].init.method).toBe("POST");
    tablo[UC] = [200, {}];
    await expect(exchangeCodeForToken("192.168.1.40", "AB12CD")).resolves.toBe(false);
    tablo[UC] = [403, { detail: "yanlış kod" }];
    await expect(exchangeCodeForToken("192.168.1.40", "AB12CD")).resolves.toBe(false);
    delete tablo[UC];
    await expect(exchangeCodeForToken("192.168.1.40", "AB12CD")).resolves.toBe(false);
    expect(serviceConfig.apiToken).toBe("T-1"); // başarısız takaslar saklı jetonu BOZMAZ
  });
});

describe("kimlik yolu erişimi (kimlikYoluErisimi)", () => {
  const B = "https://abc.trycloudflare.com";
  it("aynı ağda jeton cihazdan; değilse saklı anahtar /api/system/info'ya karşı (yalnız 2xx); bozuk gövde saklıya düşer; ağ yok → false", async () => {
    tablo[`${B}/api/auth/token`] = [200, { token: "T-2" }];
    await expect(kimlikYoluErisimi(B)).resolves.toBe(true);
    expect(serviceConfig.apiToken).toBe("T-2");
    expect(urller()).not.toContain(`${B}/api/system/info`);

    tablo[`${B}/api/auth/token`] = [403, {}];
    tablo[`${B}/api/system/info`] = [200, {}];
    await expect(kimlikYoluErisimi(B)).resolves.toBe(true);
    expect(istekler[istekler.length - 1].init.headers).toEqual({ "X-API-Key": "T-2" });
    tablo[`${B}/api/system/info`] = [429, {}];
    await expect(kimlikYoluErisimi(B)).resolves.toBe(false);

    tablo[`${B}/api/auth/token`] = async () => ({ ok: true, status: 200, json: async () => { throw new SyntaxError("bozuk"); } });
    tablo[`${B}/api/system/info`] = [401, {}];
    await setStoredApiToken("");
    await expect(kimlikYoluErisimi(B)).resolves.toBe(false);
    expect(istekler[istekler.length - 1].init.headers).toEqual({}); // anahtar yoksa başlık da yok

    delete tablo[`${B}/api/auth/token`];
    delete tablo[`${B}/api/system/info`];
    await expect(kimlikYoluErisimi(B)).resolves.toBe(false);
  });
});

describe("zaman aşımı", () => {
  /** Söz bitene dek: mikro-görevleri boşalt, bitmediyse saati 2,5 sn ilerlet (en çok `adim` kez). */
  async function bekleVeIlerlet<T>(p: Promise<T>, adim: number): Promise<T> {
    let bitti = false;
    p.then(() => { bitti = true; }, () => { bitti = true; });
    for (let i = 0; i < adim + 2 && !bitti; i++) {
      for (let j = 0; j < 40; j++) await Promise.resolve();
      if (!bitti) jest.advanceTimersByTime(2500);
    }
    return p;
  }
  it("yanıtsız uçlar 2,5 sn sonra İPTAL edilir → false; sağlık iyi ama jeton ucu yanıtsızsa sağlık yine true", async () => {
    jest.useFakeTimers({ doNotFake: ["nextTick", "queueMicrotask"] });
    tablo["http://192.168.1.40:8000/api/auth/exchange"] = "askida";
    await expect(bekleVeIlerlet(exchangeCodeForToken("192.168.1.40", "X"), 1)).resolves.toBe(false);
    tablo["http://192.168.1.40:8000/api/auth/token"] = "askida";
    tablo["http://192.168.1.40:8000/api/system/info"] = "askida";
    await expect(bekleVeIlerlet(kimlikYoluErisimi("192.168.1.40"), 2)).resolves.toBe(false);
    tablo["http://192.168.1.40:8000/api/health"] = PEMF("D-1");
    await expect(bekleVeIlerlet(checkHealth("192.168.1.40"), 1)).resolves.toBe(true);
    expect(await getStoredDeviceId()).toBe("D-1");
  });
});

describe("tam merdiven (yerel)", () => {
  it("kayıtlı adres sağlıklı ama biçimi geçersiz → UYGULANMAZ (uyarı); mDNS bulur (169.254 atlanır); tarama durdurulur", async () => {
    const uyari = jest.spyOn(console, "warn").mockImplementation(() => undefined);
    const BOZUK = "http://192.168.1.40:8000/yol/";
    await AsyncStorage.setItem("@pemf_server_address", BOZUK);
    tablo["http://192.168.1.40:8000/yol/api/health"] = PEMF();
    mockZc.kip = "bul";
    mockZc.adres = ["169.254.3.3", "fe80::1", "192.168.1.41"];
    tablo["http://192.168.1.41:8000/api/health"] = PEMF("D-41");
    const r = await discoverBackend();
    expect(r).toEqual({ address: "http://192.168.1.41:8000", source: "mdns" });
    expect(uyari).toHaveBeenCalledWith("Keşif: geçersiz adres biçimi, uygulanmadı:", BOZUK);
    expect(await AsyncStorage.getItem("@pemf_server_address")).toBe("http://192.168.1.41:8000");
    expect(serviceConfig.apiBaseUrl).toBe("http://192.168.1.41:8000/api");
    expect([mockZc.durdur, mockZc.sok]).toEqual([1, 1]);
  });

  it("alt ağ: telefonun alt ağı ÖNCE; PEMF olmayan / hatalı hostlar yok sayılır; iki PEMF → uyarı + İLKİ; kimlik + jeton YALNIZ kazanandan", async () => {
    const uyari = jest.spyOn(console, "warn").mockImplementation(() => undefined);
    tablo["http://10.0.5.1:8000/api/health"] = PEMF("A");
    tablo["http://10.0.5.100:8000/api/health"] = PEMF("B");
    tablo["http://10.0.5.2:8000/api/health"] = [200, { status: "online" }]; // yönlendirici — PEMF değil
    tablo["http://10.0.5.101:8000/api/health"] = [500, {}];
    tablo["http://10.0.5.1:8000/api/auth/token"] = [200, { token: "A-T" }];
    tablo["http://10.0.5.100:8000/api/auth/token"] = [200, { token: "B-T" }];
    const r = await discoverBackend();
    expect(r).toEqual({ address: "http://10.0.5.1:8000", source: "subnet" });
    expect(uyari).toHaveBeenCalledWith("Keşif: 2 PEMF cihazı bulundu, 10.0.5.1 seçildi.");
    expect(await getStoredDeviceId()).toBe("A");
    expect(serviceConfig.apiToken).toBe("A-T");
    expect(urller()).not.toContain("http://10.0.5.100:8000/api/auth/token");
    expect(urller().find((u) => /^http:\/\/[\d.]+:8000\/api\/health$/.test(u))).toBe("http://10.0.5.1:8000/api/health"); // telefonun alt ağı ÖNCE
  });
});

describe("uzak (tünel) + LAN yükseltmesi", () => {
  const TUNEL = "https://abc.trycloudflare.com";
  async function uzakHazirla(ek: object) {
    await setStoredDeviceId("DEV-7");
    mockUzakUrl = TUNEL;
    tablo[`${TUNEL}/api/health`] = PEMF("DEV-7", ek);
    tablo[`${TUNEL}/api/auth/token`] = [403, {}];
  }

  it("localIp'ye ulaşılıyorsa LAN'a GEÇİLİR ve güncel jeton alınır", async () => {
    await uzakHazirla({ localIp: "192.168.1.40" });
    tablo["http://192.168.1.40:8000/api/health"] = PEMF("DEV-7");
    tablo["http://192.168.1.40:8000/api/auth/token"] = [200, { token: "LAN-T" }];
    const r = await discoverBackend();
    expect(r).toEqual({ address: "http://192.168.1.40:8000", source: "subnet" });
    expect(serviceConfig.apiBaseUrl).toBe("http://192.168.1.40:8000/api");
    expect(serviceConfig.apiToken).toBe("LAN-T");
  });

  it.each([
    ["özel ağ olmayan ad (10.evil.com) — o ad yanıt verse bile", { localIp: "10.evil.com" }, "http://10.evil.com:8000"],
    ["geri döngü (127.0.0.1) — orada bir PEMF yanıt verse bile", { localIp: "127.0.0.1" }, "http://127.0.0.1:8000"],
    ["LAN'a ulaşılamıyor", { localIp: "192.168.1.40" }, null],
  ])("%s → tünelde KALINIR", async (_ad, ek, yanitlayan) => {
    await uzakHazirla(ek);
    if (yanitlayan) {
      tablo[`${yanitlayan}/api/health`] = PEMF("DEV-7");
      tablo[`${yanitlayan}/api/auth/token`] = [200, { token: "SAHTE-T" }];
    }
    const r = await discoverBackend();
    expect(r).toEqual({ address: TUNEL, source: "remote" });
    expect(serviceConfig.apiBaseUrl).toBe(`${TUNEL}/api`);
    expect(serviceConfig.apiToken).not.toBe("SAHTE-T");
  });

  it("tünel sağlığı yükseltme sırasında 5xx dönerse tünelde kalınır", async () => {
    await uzakHazirla({ localIp: "192.168.1.40" });
    let n = 0;
    tablo[`${TUNEL}/api/health`] = async () => {
      n += 1;
      return n === 1
        ? { ok: true, status: 200, json: async () => ({ service: "PEMF-Vet", deviceId: "DEV-7", localIp: "192.168.1.40" }) }
        : { ok: false, status: 503, json: async () => ({}) };
    };
    tablo["http://192.168.1.40:8000/api/health"] = PEMF("DEV-7");
    const r = await discoverBackend();
    expect(r).toEqual({ address: TUNEL, source: "remote" });
    expect(urller()).not.toContain("http://192.168.1.40:8000/api/health");
  });
});

describe("nesil koruması + tek uçuş", () => {
  it("tam tur sürerken hafif yoklama bağlarsa tam tur adres UYGULAMAZ (null)", async () => {
    const KAYITLI = "192.168.1.40";
    await AsyncStorage.setItem("@pemf_server_address", KAYITLI);
    let serbest: () => void = () => undefined;
    let ilk = true;
    tablo["http://192.168.1.40:8000/api/health"] = (k) => {
      const yanit = { ok: true, status: 200, json: async () => ({ service: "PEMF-Vet", deviceId: "D-9" }) };
      if (!ilk) return Promise.resolve(yanit);
      ilk = false;
      void k;
      return new Promise((coz) => { serbest = () => coz(yanit); });
    };
    tablo["http://192.168.1.40:8000/api/auth/token"] = [200, { token: "T-9" }];
    const tam = discoverBackend("tam");
    await new Promise((c) => setTimeout(c, 0));
    await expect(discoverBackend("hafif")).resolves.toEqual({ address: KAYITLI, source: "saved" });
    serbest();
    await expect(tam).resolves.toBeNull();
  });

  it("eşzamanlı iki tam keşif AYNI sözü paylaşır", async () => {
    const a = discoverBackend();
    const b = discoverBackend();
    expect(b).toBe(a);
    await a;
  });
});

describe("web", () => {
  it("köken sağlıklıysa 'current'; hafif / hemen kipleri koşmaz; web'de LAN yükseltmesi YAPILMAZ", async () => {
    (Platform as { OS: string }).OS = "web";
    updateServiceConfig("https://klinik.example");
    tablo["https://klinik.example/api/health"] = PEMF("W-1");
    await expect(discoverBackend()).resolves.toEqual({ address: "https://klinik.example", source: "current" });
    await expect(discoverBackend("hafif")).resolves.toBeNull();
    await expect(discoverBackend("kayitliHemen")).resolves.toBeNull();

    delete tablo["https://klinik.example/api/health"];
    const TUNEL = "https://abc.trycloudflare.com";
    await setStoredDeviceId("W-1");
    await AsyncStorage.setItem("@pemf_server_address", TUNEL);
    tablo[`${TUNEL}/api/health`] = PEMF("W-1", { localIp: "192.168.1.40" });
    tablo["http://192.168.1.40:8000/api/health"] = PEMF("W-1");
    await expect(discoverBackend()).resolves.toEqual({ address: TUNEL, source: "saved" });
    expect(urller()).not.toContain("http://192.168.1.40:8000/api/health");
  });
});

describe("kayitliHemen + hafif mDNS", () => {
  it("kayıtlı ÖZEL ağ adresi sağlık BEKLEMEDEN uygulanır (eski anahtar da); tünel / geçersiz biçim / depo hatası → null", async () => {
    await AsyncStorage.setItem("@pemf_server_ip", "192.168.1.40");
    await expect(discoverBackend("kayitliHemen")).resolves.toEqual({ address: "192.168.1.40", source: "saved" });
    expect(istekler).toHaveLength(0);
    expect(serviceConfig.apiBaseUrl).toBe("http://192.168.1.40:8000/api");
    await AsyncStorage.setItem("@pemf_server_address", "https://abc.trycloudflare.com");
    await expect(discoverBackend("kayitliHemen")).resolves.toBeNull();
    await AsyncStorage.setItem("@pemf_server_address", "192.168.1.40/evil");
    await expect(discoverBackend("kayitliHemen")).resolves.toBeNull();
    jest.spyOn(AsyncStorage, "getItem").mockRejectedValueOnce(new Error("depo kilitli"));
    await expect(discoverBackend("kayitliHemen")).resolves.toBeNull();
  });

  it("hafif: kayıtlı adres yoksa mDNS ile bağlanır", async () => {
    mockZc.kip = "bul";
    mockZc.adres = ["192.168.1.41"];
    tablo["http://192.168.1.41:8000/api/health"] = PEMF("D-41");
    await expect(discoverBackend("hafif")).resolves.toEqual({ address: "http://192.168.1.41:8000", source: "mdns" });
  });

  it("mDNS yanıtsızsa süre sonunda null; stop() atsa da dinleyiciler SÖKÜLÜR; kurucu atarsa null", async () => {
    jest.useFakeTimers({ doNotFake: ["nextTick", "queueMicrotask"] });
    mockZc.kip = "sessiz";
    mockZc.stopAtar = true;
    const p = discoverBackend("hafif");
    for (let i = 0; i < 10; i++) await Promise.resolve();
    jest.advanceTimersByTime(2500);
    await expect(p).resolves.toBeNull();
    expect([mockZc.durdur, mockZc.sok]).toEqual([1, 1]);
    jest.useRealTimers();
    mockZc.kip = "kurucuAtar";
    await expect(discoverBackend("hafif")).resolves.toBeNull();
  });
});
