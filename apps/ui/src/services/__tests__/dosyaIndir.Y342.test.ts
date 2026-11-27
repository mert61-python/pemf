// Author: mertaygn, cglrgrkn
/**
 * Y342 (sahip 27-11; istem 63 YS3 e): masaüstü uygulamasında "İndir" (`kaydet=1`) dosyayı backend artık Masaüstüne DEĞİL, bulut
 * eşitlemesi dışındaki "PEMF Vet\Raporlar" klasörüne yazar → başarı bildirimi "masaüstüne" DEMEZ; klasörü ve açma yolunu söyler
 * (TR + EN). Telefon / tarayıcı indirmesi (tarayıcının kendi indirme klasörü) bu dosyanın konusu değil — `dosyaIndir.test.ts`.
 */
const mockFetch = jest.fn();
jest.mock("react-native", () => ({ Platform: { OS: "web" } }));
jest.mock("expo-file-system/legacy", () => ({ cacheDirectory: "/tmp/", downloadAsync: jest.fn(), deleteAsync: jest.fn() }));
jest.mock("expo-sharing", () => ({ isAvailableAsync: jest.fn(), shareAsync: jest.fn() }));
jest.mock("@/services/config", () => ({ get serviceConfig() { return { apiBaseUrl: "http://localhost:8000/api", apiToken: "" }; } }));

import { act } from "@testing-library/react-native";

import { downloadFileWithAuth } from "@/services/dosyaIndir";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };
let toastlar: [string, string | undefined][] = [];
const toast = (m: string, t?: "success" | "error" | "info") => { toastlar.push([m, t]); };

beforeEach(() => {
  toastlar = [];
  mockFetch.mockReset().mockResolvedValue({
    ok: true,
    status: 200,
    headers: { get: () => "application/json" },
    json: async () => ({ status: "success", yol: "C:\\Users\\vet\\PEMF Vet\\Raporlar\\PEMF_Gecmis.csv", ad: "PEMF_Gecmis.csv" }),
  });
  (globalThis as Record<string, unknown>).fetch = mockFetch;
});
afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

test("KRİTİK Y342: kaydet=1 başarısı RAPORLAR klasörünü ve açma yolunu söyler — 'masaüstü' DEMEZ", async () => {
  await downloadFileWithAuth("http://localhost:8000/api/history/export_csv", "PEMF_Gecmis.csv", toast);
  expect(String(mockFetch.mock.calls[0][0])).toContain("kaydet=1");
  expect(toastlar).toEqual([
    ["Raporlar klasörüne kaydedildi: PEMF_Gecmis.csv — Seans Geçmişi'ndeki «📂 Raporlar klasörü» ile açın.", "success"],
  ]);
  expect(toastlar[0][0].toLowerCase()).not.toContain("masaüst");
});

test("EN: bildirim İngilizce (Reports folder)", async () => {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
  await downloadFileWithAuth("http://localhost:8000/api/history/export_csv", "PEMF_Gecmis.csv", toast);
  expect(toastlar).toEqual([
    ["Saved to the Reports folder: PEMF_Gecmis.csv — open it with “📂 Reports folder” in Session History.", "success"],
  ]);
});
