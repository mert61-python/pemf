// Author: mertaygn, cglrgrkn
/**
 * D3I-A1.2 — D3.47 · A-60: kimlik yolunda saklı anahtarın SINANMASI (`discovery.kimlikYoluErisimi` → `/api/system/info`) "anahtar
 * geçerli"yi YALNIZ 2xx'ten çıkarmalı. HEAD `res.status !== 401` → 429 / 503 / 500 / 404 / 400 "geçerli" sayılıyor: anahtar
 * DOĞRULANMADAN `{ durum: "ok" }` + "Cihaz eşleştirildi ve bağlanıldı ✓", bağlantı ve kalıcı adres yeni cihaza geçiyor; sonraki her
 * istek 401 / WS 1008 (A-60'ın kapattığı İG-6.50 durumu).
 * Backend'de ÖLÇÜLDÜ (`tests/test_D3I_eslesme_system_info_YALNIZ_2xx_anahtar_gecerli.py`, süreç içi TestClient): kimlik zorunluyken uzak
 * istemci YANLIŞ anahtarla hız sınırı kovası doluyken 429 (rate-limit auth'tan DIŞTA), auth katmanı yüklenemezken 503 / 500 alır.
 * Sahte EN ALT katta: `global.fetch` (backend modeli: `/api/system/info` yalnız DOĞRU `X-API-Key` ile 200, yanlış / eksikte 401 —
 * ya da sabit kod) ve bulut kaydı. Yapılandırma / keşif / düz-HTTP kapısı / eşleştirme GERÇEK.
 */
jest.mock("@/services/deviceRegistry", () => ({
  uzakCihaziKimlikleCoz: jest.fn(async () => ({
    durum: "bulundu",
    url: mockUzakAdres.deger,
    device: { device_id: "PEMF-KIMLIK-0001" },
  })),
  uzakCihaziKodlaCoz: jest.fn(async () => ({ durum: "yok" })),
  getRemoteUrlForDevice: jest.fn(async () => null),
}));
const mockUzakAdres = { deger: "https://abc-def.trycloudflare.com" };

import AsyncStorage from "@react-native-async-storage/async-storage";
import { serviceConfig, updateServiceConfig } from "../config";
import { cihazaBaglan } from "../pairing";

const KIMLIK = "PEMF-KIMLIK-0001-UZUN-KIMLIK"; // > 8 karakter → kimlik yolu
const DOGRU = "D3I-dogru-anahtar";
const SAGLIK = { status: 200, govde: { service: "PEMF-Vet", deviceId: "PEMF-KIMLIK-0001" } };

type Yanit = { status: number; govde?: unknown } | Error | ((anahtar: string) => { status: number; govde?: unknown });
function ag(tablo: Record<string, Yanit>) {
  const cagri: string[] = [];
  (global as { fetch: unknown }).fetch = jest.fn(async (url: string, init?: { headers?: Record<string, string> }) => {
    const anahtar = init?.headers?.["X-API-Key"] ?? "";
    cagri.push(`${url} ${anahtar || "-"}`);
    const k = Object.keys(tablo).find((t) => String(url).includes(t));
    const t = k ? tablo[k] : { status: 404 };
    if (t instanceof Error) throw t;
    const y = typeof t === "function" ? t(anahtar) : t;
    return { ok: y.status >= 200 && y.status < 300, status: y.status, json: async () => y.govde ?? {} };
  });
  return cagri;
}
/** Backend modeli (kimlik zorunlu, uzak istemci): yalnız DOĞRU anahtar 200, gerisi 401. */
const kimlikZorunlu = (anahtar: string) => ({ status: anahtar === DOGRU ? 200 : 401 });

function oncekiCihazdaKaldi() {
  expect(serviceConfig.apiBaseUrl.startsWith("http://192.168.1.5:8000")).toBe(true);
  const adresYazimi = (AsyncStorage.setItem as jest.Mock).mock.calls.filter((c) => c[0] === "@pemf_server_address");
  expect(adresYazimi).toEqual([]);
}

beforeEach(() => {
  mockUzakAdres.deger = "https://abc-def.trycloudflare.com";
  updateServiceConfig("http://192.168.1.5:8000"); // ÖNCEKİ cihaz (A)
  serviceConfig.apiToken = "baska-cihazin-anahtari";
  (AsyncStorage.setItem as jest.Mock).mockClear();
  jest.spyOn(console, "error").mockImplementation(() => {});
  jest.spyOn(console, "warn").mockImplementation(() => {});
});
afterEach(() => jest.restoreAllMocks());

it.each([429, 503, 500, 404, 400, 302])(
  "KRİTİK: anahtar sondası %i (anahtar DOĞRULANMADI) → jeton_yok; bağlantı ve kalıcı adres ÖNCEKİ cihazda",
  async (kod) => {
    const cagri = ag({ "/api/health": SAGLIK, "/api/auth/token": { status: 403 }, "/api/system/info": { status: kod } });
    expect(await cihazaBaglan(KIMLIK)).toEqual({ durum: "jeton_yok" });
    // sonda GERÇEKTEN koştu, saklı anahtarla (kör kapı değil):
    expect(cagri.some((c) => c.includes("/api/system/info baska-cihazin-anahtari"))).toBe(true);
    oncekiCihazdaKaldi();
  },
);

it("KRİTİK: ağ hatası / zaman aşımı (fetch fırlatır) → jeton_yok", async () => {
  ag({ "/api/health": SAGLIK, "/api/auth/token": new Error("ağ"), "/api/system/info": new Error("zaman aşımı") });
  expect(await cihazaBaglan(KIMLIK)).toEqual({ durum: "jeton_yok" });
  oncekiCihazdaKaldi();
});

it("KRİTİK: genel http adresi — düz-HTTP kapısı anahtarı GÖNDERMEZ (GuvensizBaglantiHatasi) → jeton_yok", async () => {
  mockUzakAdres.deger = "http://203.0.113.5:8000";
  const cagri = ag({ "/api/health": SAGLIK, "/api/system/info": { status: 200 } });
  expect(await cihazaBaglan(KIMLIK)).toEqual({ durum: "jeton_yok" });
  expect(cagri.filter((c) => c.includes("/api/system/info") || c.includes("/api/auth/token"))).toEqual([]);
  oncekiCihazdaKaldi();
});

it("KARŞIT: kimlik zorunlu cihaz — saklı anahtar YANLIŞ → jeton_yok; DOĞRU → ok (anahtar başlıkta gider)", async () => {
  ag({ "/api/health": SAGLIK, "/api/auth/token": { status: 403 }, "/api/system/info": kimlikZorunlu });
  expect(await cihazaBaglan(KIMLIK)).toEqual({ durum: "jeton_yok" });
  serviceConfig.apiToken = DOGRU;
  const s = await cihazaBaglan(KIMLIK);
  expect(s.durum).toBe("ok");
  expect(serviceConfig.apiBaseUrl.startsWith("https://abc-def.trycloudflare.com")).toBe(true);
});

it("KARŞIT: kimlik zorunluluğu KAPALI cihaz (system/info anahtarsız 200 / 204) → ok", async () => {
  serviceConfig.apiToken = "";
  ag({ "/api/health": SAGLIK, "/api/auth/token": { status: 403 }, "/api/system/info": { status: 200 } });
  expect((await cihazaBaglan(KIMLIK)).durum).toBe("ok");
  updateServiceConfig("http://192.168.1.5:8000");
  ag({ "/api/health": SAGLIK, "/api/auth/token": { status: 403 }, "/api/system/info": { status: 204 } });
  expect((await cihazaBaglan(KIMLIK)).durum).toBe("ok");
});

it("KARŞIT: LAN'da anahtar cihazdan alınır (A-01) → ok, system/info sondası GEREKMEZ", async () => {
  const cagri = ag({ "/api/health": SAGLIK, "/api/auth/token": { status: 200, govde: { token: "cihaz-anahtari-lan" } } });
  expect((await cihazaBaglan(KIMLIK)).durum).toBe("ok");
  expect(serviceConfig.apiToken).toBe("cihaz-anahtari-lan");
  expect(cagri.some((c) => c.includes("/api/system/info"))).toBe(false);
});
