// Author: mertaygn, cglrgrkn
/**
 * D3.47 · A-60 (sahip) — CİHAZ KİMLİĞİYLE eşleşmede erişim anahtarı ŞART; alınamazsa "bağlanıldı" DENMEZ, eksik olan söylenir.
 * (A-01: LAN güvenilir — `/api/auth/token` LAN'a açık kalır; bu dosya yalnız A-60 kolunu ölçer.)
 *
 * ÖLÇÜLEN (HEAD): `cihazaBaglan(<kimlik>)` kimlik yolunda `tokenOk = true` sabiti — tünel adresinde anahtar alınamadığı (403) ve saklı
 * anahtar cihazda 401 aldığı hâlde `{ durum: "ok" }` + bağlantı yeni cihaza geçiyor ("Cihaz eşleştirildi ve bağlanıldı ✓"); sonraki her
 * istek 401 / WS 1008 (İG-6.50).
 * Sahte EN ALT katta: `global.fetch` (URL'ye göre yanıt) ve bulut kaydı (`deviceRegistry`). Yapılandırma / keşif / eşleştirme GERÇEK.
 */
jest.mock("@/services/deviceRegistry", () => ({
  uzakCihaziKimlikleCoz: jest.fn(async () => ({
    durum: "bulundu",
    url: "https://abc-def.trycloudflare.com",
    device: { device_id: "PEMF-KIMLIK-0001" },
  })),
  uzakCihaziKodlaCoz: jest.fn(async () => ({
    durum: "bulundu",
    url: "https://abc-def.trycloudflare.com",
    device: { device_id: "PEMF-KIMLIK-0001" },
  })),
  getRemoteUrlForDevice: jest.fn(async () => null),
}));

import i18n from "i18next";
import { serviceConfig, updateServiceConfig } from "../config";
import { cihazaBaglan, eslesmeMesaji } from "../pairing";

const KIMLIK = "PEMF-KIMLIK-0001-UZUN-KIMLIK"; // > 8 karakter → kimlik yolu

type Yanit = { status: number; govde?: unknown };
function ag(tablo: Record<string, Yanit>) {
  const cagri: string[] = [];
  (global as { fetch: unknown }).fetch = jest.fn(async (url: string, init?: { headers?: Record<string, string> }) => {
    cagri.push(`${url} ${init?.headers?.["X-API-Key"] ?? "-"}`);
    const anahtar = Object.keys(tablo).find((k) => String(url).includes(k));
    const y = anahtar ? tablo[anahtar] : { status: 404 };
    return { ok: y.status >= 200 && y.status < 300, status: y.status, json: async () => y.govde ?? {} };
  });
  return cagri;
}
const SAGLIK = { status: 200, govde: { service: "PEMF-Vet", deviceId: "PEMF-KIMLIK-0001" } };

beforeEach(() => {
  updateServiceConfig("http://192.168.1.5:8000"); // ÖNCEKİ cihaz (A)
  serviceConfig.apiToken = "";
  jest.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(() => jest.restoreAllMocks());

it("KRİTİK: tünelde anahtar alınamıyor + saklı anahtar yok (401) → jeton_yok, bağlantı ÖNCEKİ cihazda", async () => {
  ag({ "/api/health": SAGLIK, "/api/auth/token": { status: 403 }, "/api/system/info": { status: 401 } });
  const s = await cihazaBaglan(KIMLIK);
  expect(s).toEqual({ durum: "jeton_yok" });
  expect(serviceConfig.apiBaseUrl.startsWith("http://192.168.1.5:8000")).toBe(true);
});

it("KRİTİK: saklı anahtar BU cihazda geçmiyor (401) → jeton_yok", async () => {
  serviceConfig.apiToken = "baska-cihazin-anahtari";
  const cagri = ag({ "/api/health": SAGLIK, "/api/auth/token": { status: 403 }, "/api/system/info": { status: 401 } });
  expect(await cihazaBaglan(KIMLIK)).toEqual({ durum: "jeton_yok" });
  expect(cagri.some((c) => c.includes("/api/system/info baska-cihazin-anahtari"))).toBe(true);
});

it("KARŞIT: LAN'da anahtar cihazdan alınır (A-01) → ok, anahtar saklanır", async () => {
  ag({ "/api/health": SAGLIK, "/api/auth/token": { status: 200, govde: { token: "cihaz-anahtari-lan" } } });
  const s = await cihazaBaglan(KIMLIK);
  expect(s.durum).toBe("ok");
  expect(serviceConfig.apiToken).toBe("cihaz-anahtari-lan");
  expect(serviceConfig.apiBaseUrl.startsWith("https://abc-def.trycloudflare.com")).toBe(true);
});

it("KARŞIT: saklı anahtar bu cihazda GEÇİYOR (200) → ok", async () => {
  serviceConfig.apiToken = "dogru-anahtar";
  ag({ "/api/health": SAGLIK, "/api/auth/token": { status: 403 }, "/api/system/info": { status: 200 } });
  expect((await cihazaBaglan(KIMLIK)).durum).toBe("ok");
});

it("KARŞIT: kod yolu değişmedi — takas düşerse kod_reddedildi", async () => {
  ag({ "/api/health": SAGLIK, "/api/auth/exchange": { status: 403 } });
  expect(await cihazaBaglan("A3F9K2")).toEqual({ durum: "kod_reddedildi" });
});

it("TR + EN: jeton_yok 'bağlanıldı' DEMEZ, eksik olanı ve çaresini söyler; önceki cihaz bağlamı ayrı", async () => {
  await i18n.changeLanguage("tr");
  const tr = eslesmeMesaji({ durum: "jeton_yok" });
  expect(tr).toContain("erişim anahtarı alınamadı");
  expect(tr).not.toContain("bağlanıldı ✓");
  expect(eslesmeMesaji({ durum: "jeton_yok" }, { oncekiCihazaBagli: true })).toContain("önceki cihazda kaldı");
  await i18n.changeLanguage("en");
  expect(eslesmeMesaji({ durum: "jeton_yok" })).toContain("no access key could be obtained");
  await i18n.changeLanguage("tr");
});
