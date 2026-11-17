/**
 * KP-8 · duzHttpKapisi + apiClient platform yardımcıları kalan dallar (KP3-duzHttpKapisi-bildirim deseni; sahte yalnız platform sınırı):
 *  - `isPrivateHost` boş / tanımsız ana makineyi özel ağ SAYMAZ.
 *  - Engellenen düz-HTTP bildirimi adres ŞEMASIZ / boşsa da çökmez (taban = ham adres / boş); web'de pencere nesnesi YOKSA (SSR /
 *    işçi) uyarı atlanır, çökmez.
 *  - `platformAlert` / `platformConfirm` web'de pencere YOKSA: uyarı sessizce atlanır, onay "evet" SAYILMAZ (false).
 */
import { Platform } from "react-native";
import { guvensizBaglantiBildir, isPrivateHost } from "@/services/duzHttpKapisi";
import { platformAlert, platformConfirm } from "@/services/apiClient";
import { setToastHandler } from "@/services/toastBridge";

let hataSus: jest.SpyInstance;
const g = global as unknown as { window?: unknown };
let os: string;
let pencereVarMi: boolean;
let pencere: unknown;
beforeEach(() => {
  hataSus = jest.spyOn(console, "error").mockImplementation(() => undefined);
  os = Platform.OS;
  pencereVarMi = "window" in g;
  pencere = g.window;
});
afterEach(() => {
  hataSus.mockRestore();
  setToastHandler(null);
  Object.defineProperty(Platform, "OS", { configurable: true, get: () => os });
  if (pencereVarMi) g.window = pencere; else delete g.window;
});
/** Web + pencere YOK (SSR / işçi bağlamı). */
function webPencereYok() {
  Object.defineProperty(Platform, "OS", { configurable: true, get: () => "web" });
  delete g.window;
}

it("isPrivateHost: boş / tanımsız ana makine özel ağ DEĞİL", () => {
  expect(isPrivateHost("")).toBe(false);
  expect(isPrivateHost(undefined as unknown as string)).toBe(false);
});

it("şemasız / boş adres bildirimi çökmez; toast ham adresle; web'de pencere yoksa uyarı atlanır", () => {
  const toast = jest.fn();
  setToastHandler(toast);
  guvensizBaglantiBildir("kp8-semasiz-adres");
  expect(hataSus).toHaveBeenCalledWith(expect.any(String), "kp8-semasiz-adres");
  expect(toast).toHaveBeenCalledTimes(1);
  guvensizBaglantiBildir(undefined as unknown as string);
  expect(hataSus).toHaveBeenLastCalledWith(expect.any(String), "");
  setToastHandler(null);
  webPencereYok();
  expect(() => guvensizBaglantiBildir("http://203.0.113.77/x")).not.toThrow();
});

it("platformAlert / platformConfirm: web'de pencere yoksa uyarı atlanır, onay false", async () => {
  webPencereYok();
  expect(() => platformAlert("Başlık", "Metin")).not.toThrow();
  await expect(platformConfirm("Başlık", "Metin")).resolves.toBe(false);
});
