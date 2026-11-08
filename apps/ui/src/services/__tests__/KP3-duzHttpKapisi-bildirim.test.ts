/**
 * KP-3 C · duzHttpKapisi — soket adresi kuralı + engellenen isteği bildirme (her test bir DAVRANIŞ iddiası):
 *  - Soket adresi: `ws(s)://` olmayan / boş adres GÜVENSİZ sayılır; `wss` her yerde, `ws` yalnız yerel ağda güvenli.
 *  - Engellenen düz-HTTP isteği kullanıcıya AYNI taban için BİR kez söylenir (yeniden bağlanma döngüsü pencere yağdırmaz); bildirim
 *    kabuğu (toast) varsa yalnız toast, yoksa yerel uyarı (native Alert / web `window.alert`).
 * SAHTE: platform (Alert / Platform.OS / window.alert). GERÇEK: duzHttpKapisi + toastBridge + i18n.
 */
import { Alert, Platform } from "react-native";
import i18n from "i18next";
import { guvensizBaglantiBildir, soketAdresiGuvenliMi } from "@/services/duzHttpKapisi";
import { setToastHandler } from "@/services/toastBridge";

const T = (k: string): string => (i18n.t as unknown as (k: string) => string)(k);
let hataSus: jest.SpyInstance;
beforeEach(() => { hataSus = jest.spyOn(console, "error").mockImplementation(() => undefined); });
afterEach(() => { hataSus.mockRestore(); setToastHandler(null); jest.restoreAllMocks(); });

it("soket adresi: ws(s) olmayan / boş adres güvensiz; wss her yerde, ws yalnız yerel ağda", () => {
  expect(soketAdresiGuvenliMi("")).toBe(false);
  expect(soketAdresiGuvenliMi("http://192.168.1.5:8000/ws")).toBe(false);
  expect(soketAdresiGuvenliMi("kamera:/akis")).toBe(false);
  expect(soketAdresiGuvenliMi("wss://pemf.example.com/ws")).toBe(true);
  expect(soketAdresiGuvenliMi("ws://192.168.1.5:8000/ws")).toBe(true);
  expect(soketAdresiGuvenliMi("ws://203.0.113.9:8000/ws")).toBe(false);
});

it("bildirim: aynı taban için bir kez; toast varsa yalnız toast, yoksa yerel uyarı", () => {
  const uyari = jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
  const toast = jest.fn();
  setToastHandler(toast);
  guvensizBaglantiBildir("http://203.0.113.9:8000/api/kare?x=1");
  guvensizBaglantiBildir("http://203.0.113.9:8000/ws");
  expect(toast).toHaveBeenCalledTimes(1);
  expect(toast.mock.calls[0][0]).toContain(T("ortak.hata.sifresizAdres"));
  expect(toast.mock.calls[0][1]).toBe("error");
  expect(uyari).not.toHaveBeenCalled();
  setToastHandler(null);
  guvensizBaglantiBildir("http://198.51.100.7/api");
  expect(uyari).toHaveBeenCalledTimes(1);
  expect(uyari).toHaveBeenCalledWith(T("ortak.hata.guvensizBaglanti"), T("ortak.hata.sifresizAdres"));
});

it("web'de kabuk yoksa tarayıcı uyarısı", () => {
  const os = Platform.OS;
  Object.defineProperty(Platform, "OS", { configurable: true, get: () => "web" });
  const g = global as unknown as { window?: { alert?: (m: string) => void } };
  const oncekiPencere = g.window;
  const pencereUyari = jest.fn();
  g.window = { ...(oncekiPencere || {}), alert: pencereUyari };
  try {
    guvensizBaglantiBildir("http://192.0.2.44:9000/x");
    expect(pencereUyari).toHaveBeenCalledTimes(1);
    expect(pencereUyari.mock.calls[0][0]).toBe(`${T("ortak.hata.guvensizBaglanti")}\n${T("ortak.hata.sifresizAdres")}`);
  } finally {
    g.window = oncekiPencere;
    Object.defineProperty(Platform, "OS", { configurable: true, get: () => os });
  }
});
