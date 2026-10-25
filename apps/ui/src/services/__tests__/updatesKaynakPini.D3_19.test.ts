// Author: mertaygn, cglrgrkn
/**
 * D3.19 (B-6.6) — uykudaki ikinci mobil güncelleme yolu (`updates.ts` / UpdateBanner) TEK kaynağın kaynak pinine (`kaynakGuvenli`)
 * bağlı. Ölçülen (HEAD): `_safeApkUrl` host düzeyi regex'i başka hesabın github.com deposunu, `evil.githubusercontent.com`'u ve
 * `raw.githubusercontent.com/baska-hesap/…`'ı kabul ediyordu → manifest'e `apkUrl` yazıldığı gün başka hesabın deposundan APK açtırılırdı.
 * GERÇEK modül; yalnız `fetch` (manifest) sahte, Platform android.
 */
import { Platform } from "react-native";
import { checkMobileUpdate } from "@/services/updates";
import { kaynakGuvenli } from "@/services/indirmeKaynagi";
import { readFileSync } from "fs";
import { join } from "path";

const orijinalOS = Platform.OS;
beforeAll(() => { Object.defineProperty(Platform, "OS", { configurable: true, get: () => "android" }); });
afterAll(() => { Object.defineProperty(Platform, "OS", { configurable: true, get: () => orijinalOS }); });

function manifest(apkUrl: string) {
  (global as { fetch?: unknown }).fetch = jest.fn(async () => ({ ok: true, json: async () => ({ version: "99.0.0", apkUrl }) }) as unknown as Response);
}

test.each([
  "https://github.com/baska-hesap/kotu/releases/download/v1/x.apk",
  "https://evil.githubusercontent.com/x.apk",
  "https://raw.githubusercontent.com/baska-hesap/depo/main/x.apk",
  "http://github.com/mert61-python/pemf-update/releases/download/v1/x.apk",
])("KRİTİK D3.19: yabancı kaynak %s → güncelleme YOK (indirme bağlantısı verilmez)", async (url) => {
  manifest(url);
  const r = await checkMobileUpdate();
  expect(r.available).toBe(false);
  expect(r.apkUrl).toBeUndefined();
});

test("KARŞIT D3.19: yayın deposu yolu kabul edilir — OTA pini ile AYNI karar", async () => {
  const url = "https://github.com/mert61-python/pemf-update/releases/download/mobil-v99/PEMF_Vet_Mobil.apk";
  manifest(url);
  const r = await checkMobileUpdate();
  expect(r.available).toBe(true);
  expect(r.apkUrl).toBe(url);
  expect(kaynakGuvenli(url)).toBe(true);
});

test("YAPISAL D3.19: OTA (mobileUpdate) ve ikinci yol (updates) AYNI tek kaynağı kullanır; kendi host regex'i YOK", () => {
  const dizin = join(__dirname, "..");
  const mu = readFileSync(join(dizin, "mobileUpdate.ts"), "utf8");
  const up = readFileSync(join(dizin, "updates.ts"), "utf8");
  expect(mu).toMatch(/import \{ kaynakGuvenli \} from "@\/services\/indirmeKaynagi";/);
  expect(mu).not.toMatch(/export function kaynakGuvenli/);
  expect(up).toMatch(/from "@\/services\/indirmeKaynagi"/);
  expect(up).toContain("kaynakGuvenli(url)");
  expect(up).not.toMatch(/githubusercontent\\.com\)/);
});
