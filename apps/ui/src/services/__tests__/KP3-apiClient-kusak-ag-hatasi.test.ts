/**
 * KP-3 C · apiClient hesap kuşağı (CH1 · Y151) — AĞ HATASI kolları (mevcut CH1 testi yanıt / HTTP hatası kollarını ölçer):
 *  - apiGet: istek uçuştayken hesap değişir ve istek AĞ HATASIYLA düşerse eski hesabın isteği YENİDEN DENENMEZ (yeni hesabın
 *    adına eski belirteçle ikinci istek gitmez) — fallback döner.
 *  - apiPost: uçuştaki isteğin ZAMAN AŞIMI yeni hesaba "zaman aşımı" balonu GÖSTERMEZ; karşıt: kuşak aynıysa balon gösterilir.
 * SAHTE (en alt kat): fetch · bildirim köprüsü (toast yakalanır). GERÇEK: apiClient + yapılandırma.
 */
import { apiGet, apiPost, hesapKusagiArtir } from "../apiClient";
import * as toastBridge from "../toastBridge";
import { serviceConfig } from "@/services/config";

function reddedilenFetch(): { reddet: (e: unknown) => void } {
  let reddet: (e: unknown) => void = () => {};
  global.fetch = jest.fn(() => new Promise((_, rj) => { reddet = rj; })) as unknown as typeof fetch;
  return { reddet: (e) => reddet(e) };
}
const abort = () => Object.assign(new Error("The operation was aborted."), { name: "AbortError" });

let toasts: string[];
beforeEach(() => {
  serviceConfig.apiBaseUrl = "http://192.168.1.147:18080/api";
  serviceConfig.apiToken = "";
  toasts = [];
  jest.spyOn(toastBridge, "emitToast").mockImplementation((m: string) => { toasts.push(m); return true; });
  jest.spyOn(console, "error").mockImplementation(() => undefined);
});
afterEach(() => jest.restoreAllMocks());

it("apiGet: hesap değişip istek ağ hatasıyla düşerse YENİDEN DENENMEZ, fallback döner", async () => {
  const f = reddedilenFetch();
  const p = apiGet<string>("/jeton/bakiye", "YOK", { silent: true });
  await Promise.resolve();
  hesapKusagiArtir();
  f.reddet(new TypeError("Failed to fetch"));
  expect(await p).toBe("YOK");
  await new Promise((r) => setTimeout(r, 600)); // ürünün geri-çekilmesi 400 ms — sonrasında ikinci istek OLMAMALI
  expect(global.fetch).toHaveBeenCalledTimes(1);
});

it("apiPost: hesap değiştiyse zaman aşımı balonu YOK; kuşak aynıysa VAR", async () => {
  let f = reddedilenFetch();
  let p = apiPost("/ai/analiz", {}, "YOK");
  await Promise.resolve();
  hesapKusagiArtir();
  f.reddet(abort());
  expect(await p).toBe("YOK");
  expect(toasts).toEqual([]);
  f = reddedilenFetch();
  p = apiPost("/ai/analiz", {}, "YOK");
  await Promise.resolve();
  f.reddet(abort());
  expect(await p).toBe("YOK");
  expect(toasts).toHaveLength(1);
});
