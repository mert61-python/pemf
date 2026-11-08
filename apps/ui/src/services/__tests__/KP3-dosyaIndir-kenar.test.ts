/**
 * KP-3 C · dosyaIndir kenar kolları — her test bir DAVRANIŞ iddiası (indirme ASLA sessiz düşmez, yanlış teşhis vermez):
 *  - Masaüstü (yerel backend) yolunda sunucu gövdesi JSON değilse "sunucu beklenmeyen yanıt verdi" denir (genel "hata" değil).
 *  - Tarayıcı yolunda geçici nesne adresi indirme bittikten SONRA (10 sn) bırakılır — hemen değil (indirme kesilmesin), hiç değil de
 *    değil (bellek sızmasın).
 *  - Native yolda sunucu 200 dışı dönerse "İndirilemedi" denir ve hata gövdesi PAYLAŞILMAZ.
 * SAHTE (en alt kat): fetch · expo-file-system / expo-sharing · DOM `<a>` · URL.createObjectURL / revokeObjectURL · Platform.OS.
 * GERÇEK: dosyaIndir + backendKonumu + düz-HTTP kapısı + i18n.
 */
const mockFetch = jest.fn();
const mockDownloadAsync = jest.fn();
const mockShareAsync = jest.fn();
const mockIsSharingAvailable = jest.fn();
const mockDeleteAsync = jest.fn();
let mockPlatformOS = "web";
jest.mock("react-native", () => ({ Platform: { get OS() { return mockPlatformOS; } } }));
jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "/tmp/",
  downloadAsync: (...a: unknown[]) => mockDownloadAsync(...(a as [])),
  deleteAsync: (...a: unknown[]) => mockDeleteAsync(...(a as [])),
}));
jest.mock("expo-sharing", () => ({
  isAvailableAsync: (...a: unknown[]) => mockIsSharingAvailable(...(a as [])),
  shareAsync: (...a: unknown[]) => mockShareAsync(...(a as [])),
}));
const mockConfig = { apiBaseUrl: "http://localhost:8000/api", apiToken: "" };
jest.mock("@/services/config", () => ({ get serviceConfig() { return mockConfig; } }));

import i18n from "i18next";
import { downloadFileWithAuth } from "@/services/dosyaIndir";

const T = (k: string): string => (i18n.t as unknown as (k: string) => string)(k);
let toastlar: [string, string | undefined][] = [];
const toast = (m: string, t?: "success" | "error" | "info") => { toastlar.push([m, t]); };
const birakilan: string[] = [];

beforeEach(() => {
  toastlar = [];
  birakilan.length = 0;
  mockPlatformOS = "web";
  mockConfig.apiBaseUrl = "http://localhost:8000/api";
  for (const m of [mockFetch, mockDownloadAsync, mockShareAsync, mockIsSharingAvailable]) m.mockReset();
  mockDeleteAsync.mockReset().mockResolvedValue(undefined);
  (globalThis as Record<string, unknown>).fetch = mockFetch;
  (globalThis as Record<string, unknown>).URL = Object.assign(
    function (u: string, b?: string) { return new (jest.requireActual("url").URL)(u, b); },
    { createObjectURL: () => "blob:sahte", revokeObjectURL: (u: string) => { birakilan.push(u); } },
  );
  const a = { href: "", download: "", click: () => undefined, remove: () => undefined };
  (globalThis as Record<string, unknown>).document = { createElement: () => a, body: { appendChild: () => undefined } };
});
afterEach(() => jest.useRealTimers());

const yanit = (o: Partial<{ ok: boolean; status: number; tur: string; json: () => Promise<unknown> }>) => ({
  ok: o.ok ?? true,
  status: o.status ?? 200,
  headers: { get: () => o.tur ?? "application/pdf" },
  json: o.json ?? (async () => ({})),
  text: async () => "",
  blob: async () => ({ size: 10 }),
});

it("masaüstü yolu: JSON olmayan gövde → 'sunucu beklenmeyen yanıt verdi' (genel hata değil)", async () => {
  mockFetch.mockResolvedValue(yanit({ tur: "text/html", json: async () => { throw new SyntaxError("Unexpected token <"); } }));
  await downloadFileWithAuth("http://localhost:8000/api/history/export_csv", "g.csv", toast);
  expect(toastlar).toEqual([[T("seans.indir.sunucuBeklenmeyen"), "error"]]);
});

it("tarayıcı yolu: nesne adresi 10 sn sonra bırakılır (hemen değil)", async () => {
  jest.useFakeTimers();
  mockConfig.apiBaseUrl = "https://klinik.example.com/api";
  mockFetch.mockResolvedValue(yanit({ tur: "text/csv" }));
  await downloadFileWithAuth("https://klinik.example.com/api/history/export_csv", "g.csv", toast);
  expect(toastlar[0][1]).toBe("success");
  jest.advanceTimersByTime(9999);
  expect(birakilan).toEqual([]);
  jest.advanceTimersByTime(1);
  expect(birakilan).toEqual(["blob:sahte"]);
});

it("native yol: sunucu 200 dışı → 'İndirilemedi', hata gövdesi paylaşılmaz", async () => {
  mockPlatformOS = "android";
  mockConfig.apiBaseUrl = "https://klinik.example.com/api";
  mockDownloadAsync.mockResolvedValue({ uri: "/tmp/r.pdf", status: 404 });
  mockIsSharingAvailable.mockResolvedValue(true);
  await downloadFileWithAuth("https://klinik.example.com/api/history/export_pdf", "r.pdf", toast);
  expect(toastlar).toEqual([[T("seans.indir.indirilemedi"), "error"]]);
  expect(mockShareAsync).not.toHaveBeenCalled();
});
