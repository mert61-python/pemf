/**
 * CT3 (istem 66) · dosyaIndir BOŞ / EKSİK yanıt kolları — indirme sunucu eksik yanıt verdiğinde de operatöre ANLAMLI bir şey söyler:
 *  - Masaüstü (yerel backend) yolunda sunucu `{"status": "bos"}`u İLETİSİZ dönerse "Dışa aktarılacak kayıt yok." denir (boş toast DEĞİL).
 *  - Tarayıcı yolunda yanıtta `content-type` başlığı HİÇ yoksa gövde dosya olarak indirilir ve başarı bildirilir (çökme / "hata" DEĞİL).
 *  - Tarayıcı yolunda `text/plain` gövdesi BOŞSA "Dışa aktarılacak kayıt yok." denir ve dosya ÜRETİLMEZ.
 * Ölçüldü (28-11, ilk GitHub koşusu @ 6d1ebb75 ve 31a88eb4 — `istemci-jest-kapsam` eseri): üç kol da HİÇ koşmuyordu
 * (dosyaIndir.ts satır 53 / 63 / 65 `||` sağ kolları); jest global dal kapsamı 10 378 / 10 994 = %94,39 < taban %94,4.
 * SAHTE (en alt kat): fetch · expo-file-system / expo-sharing · DOM `<a>` · URL.createObjectURL · Platform.OS.
 * GERÇEK: dosyaIndir + backendKonumu + düz-HTTP kapısı + i18n.
 */
const mockFetch = jest.fn();
let mockPlatformOS = "web";
jest.mock("react-native", () => ({ Platform: { get OS() { return mockPlatformOS; } } }));
jest.mock("expo-file-system/legacy", () => ({ cacheDirectory: "/tmp/", downloadAsync: jest.fn(), deleteAsync: jest.fn() }));
jest.mock("expo-sharing", () => ({ isAvailableAsync: jest.fn(), shareAsync: jest.fn() }));
const mockConfig = { apiBaseUrl: "http://localhost:8000/api", apiToken: "" };
jest.mock("@/services/config", () => ({ get serviceConfig() { return mockConfig; } }));

import i18n from "i18next";
import { downloadFileWithAuth } from "@/services/dosyaIndir";

const T = (k: string, o?: Record<string, unknown>): string =>
  (i18n.t as unknown as (k: string, o?: Record<string, unknown>) => string)(k, o);
let toastlar: [string, string | undefined][] = [];
const toast = (m: string, t?: "success" | "error" | "info") => { toastlar.push([m, t]); };
let tiklamaSayisi = 0;

beforeEach(() => {
  toastlar = [];
  tiklamaSayisi = 0;
  mockPlatformOS = "web";
  mockConfig.apiBaseUrl = "http://localhost:8000/api";
  mockFetch.mockReset();
  (globalThis as Record<string, unknown>).fetch = mockFetch;
  (globalThis as Record<string, unknown>).URL = Object.assign(
    function (u: string, b?: string) { return new (jest.requireActual("url").URL)(u, b); },
    { createObjectURL: () => "blob:sahte", revokeObjectURL: () => undefined },
  );
  const a = { href: "", download: "", click: () => { tiklamaSayisi += 1; }, remove: () => undefined };
  (globalThis as Record<string, unknown>).document = { createElement: () => a, body: { appendChild: () => undefined } };
});

const yanit = (o: { tur: string | null; json?: unknown; metin?: string }) => ({
  ok: true,
  status: 200,
  headers: { get: () => o.tur },
  json: async () => o.json ?? {},
  text: async () => o.metin ?? "",
  blob: async () => ({ size: 10 }),
});

it("masaüstü yolu: 'bos' yanıtı İLETİSİZ gelirse 'Dışa aktarılacak kayıt yok' denir (boş bildirim değil)", async () => {
  mockFetch.mockResolvedValue(yanit({ tur: "application/json", json: { status: "bos" } }));
  await downloadFileWithAuth("http://localhost:8000/api/history/export_csv", "g.csv", toast);
  expect(String(mockFetch.mock.calls[0][0])).toContain("kaydet=1");
  expect(toastlar).toEqual([[T("seans.gecmis.disaAktarilacakYok"), "info"]]);
  expect(toastlar[0][0]).toBeTruthy();
});

it("tarayıcı yolu: content-type başlığı HİÇ yoksa dosya indirilir ve başarı bildirilir (çökmez)", async () => {
  mockConfig.apiBaseUrl = "https://klinik.example.com/api";
  mockFetch.mockResolvedValue(yanit({ tur: null }));
  await downloadFileWithAuth("https://klinik.example.com/api/history/export_pdf", "r.pdf", toast);
  expect(tiklamaSayisi).toBe(1);
  expect(toastlar).toEqual([[T("seans.indir.baslatildi", { safeName: "r.pdf" }), "success"]]);
});

it("tarayıcı yolu: BOŞ text/plain gövdesi → 'Dışa aktarılacak kayıt yok', dosya ÜRETİLMEZ", async () => {
  mockConfig.apiBaseUrl = "https://klinik.example.com/api";
  mockFetch.mockResolvedValue(yanit({ tur: "text/plain; charset=utf-8", metin: "" }));
  await downloadFileWithAuth("https://klinik.example.com/api/history/export_csv", "g.csv", toast);
  expect(tiklamaSayisi).toBe(0);
  expect(toastlar).toEqual([[T("seans.gecmis.disaAktarilacakYok"), "info"]]);
});
