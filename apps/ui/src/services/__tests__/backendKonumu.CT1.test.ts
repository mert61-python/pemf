// CT1 f (istem 66 · Y311 kapsam cırcırı): `backendBuMakinede` üç kolu — yerel / uzak / ÇÖZÜLEMEYEN adres (URL atar → catch).
// ⚠️ Ölçüldü (27-11, CI eşi Node 22, tam jest): satır kapsamı %99,98 (9198 / 9199) — tek açık satır bu dosyanın catch kolu
// (`return false`); taban %100 (tests/kapsam_tabani.json). Kollar test ortamının URL uygulamasından bağımsız olsun diye Node'un
// WHATWG URL'si kullanılır.
const mockConfig = { apiBaseUrl: "http://localhost:8000/api" };
// getter: içe aktarma (hoist) anında mockConfig henüz TDZ'de — değer çağrı anında okunur
jest.mock("@/services/config", () => ({
  get serviceConfig() {
    return mockConfig;
  },
}));

import { backendBuMakinede } from "@/services/backendKonumu";

const NodeURL = (require("url") as { URL: typeof URL }).URL;
const g = globalThis as unknown as { URL: typeof URL };
const asilURL = g.URL;

beforeEach(() => {
  g.URL = NodeURL;
});
afterEach(() => {
  g.URL = asilURL;
});

describe("backendBuMakinede", () => {
  it.each([
    ["http://localhost:18080/api", true],
    ["http://127.0.0.1:18080/api", true],
    ["/api", true],
    ["https://klinik.example.com/api", false],
    ["http://192.168.1.147:18080/api", false],
  ])("%s → %s", (adres, beklenen) => {
    mockConfig.apiBaseUrl = adres;
    expect(backendBuMakinede()).toBe(beklenen);
  });

  it("çözülemeyen adres (URL kurucusu atar) → false: yerel SAYILMAZ, dosya karşı makineye yazdırılmaz", () => {
    mockConfig.apiBaseUrl = "http://[::1";
    expect(() => new NodeURL(mockConfig.apiBaseUrl, "http://localhost")).toThrow();
    expect(backendBuMakinede()).toBe(false);
  });
});
