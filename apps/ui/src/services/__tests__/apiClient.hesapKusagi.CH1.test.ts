// Author: mertaygn, cglrgrkn
/**
 * CH1 · Y151 — HESAP KUŞAĞI: uçuştaki istek eski hesabın belirteciyle döner → ATILIR.
 * ==================================================================================
 * YARIŞ: A hesabındayken başlayan bir okuma (jeton bakiyesi, liste, abonelik) B'ye geçildikten SONRA dönerse B'nin ekranına A'nın verisi
 * yazılırdı. SÖZLEŞME: `apiGet` / `apiPost` / `apiDelete` isteğin başladığı kuşağı tutar; yanıt geldiğinde kuşak değişmişse çağırana
 * `fallback` döner, `onHttpError` / hata balonu ÇAĞRILMAZ. Karşıt: kuşak değişmediyse veri aynen gelir.
 * ⚠️ MUTASYON: kuşak denetimi silinirse KRİTİK testler KIRMIZI.
 */
import { apiDelete, apiGet, apiPost, hesapKusagi, hesapKusagiArtir } from "../apiClient";
import * as toastBridge from "../toastBridge";

import { serviceConfig } from "@/services/config";

type Cozucu = (r: unknown) => void;

function bekleyenFetch(): { coz: (govde: unknown, ok?: boolean, status?: number) => void } {
  let coz: Cozucu = () => {};
  global.fetch = jest.fn(() => new Promise((r) => { coz = r; })) as unknown as typeof fetch;
  return {
    coz: (govde, ok = true, status = 200) =>
      coz({ ok, status, text: async () => JSON.stringify(govde), json: async () => govde }),
  };
}

beforeEach(() => {
  serviceConfig.apiBaseUrl = "http://192.168.1.147:8000/api";
  serviceConfig.apiToken = "";
});
afterEach(() => jest.restoreAllMocks());

it("KRİTİK apiGet: hesap değişince eski hesabın uçuştaki yanıtı ATILIR (fallback)", async () => {
  const f = bekleyenFetch();
  const p = apiGet<{ kalan: number } | null>("/jeton/bakiye", null, { silent: true });
  await Promise.resolve();
  hesapKusagiArtir();
  f.coz({ kalan: 94 });
  expect(await p).toBeNull();
});

it("KRİTİK apiPost: eski hesabın HATA yanıtı yeni hesaba balon / onHttpError ÜRETMEZ", async () => {
  const toasts: string[] = [];
  jest.spyOn(toastBridge, "emitToast").mockImplementation((m: string) => { toasts.push(m); return true; });
  const onHttpError = jest.fn();
  const f = bekleyenFetch();
  const p = apiPost("/ai/log", {}, "YOK", { onHttpError });
  await Promise.resolve();
  hesapKusagiArtir();
  f.coz({ detail: "A hesabının hatası" }, false, 500);
  expect(await p).toBe("YOK");
  expect(onHttpError).not.toHaveBeenCalled();
  expect(toasts).toEqual([]);
});

it("KRİTİK apiDelete: eski hesabın yanıtı ATILIR", async () => {
  const f = bekleyenFetch();
  const p = apiDelete("/x", "YOK", { silent: true });
  await Promise.resolve();
  hesapKusagiArtir();
  f.coz({ ok: true });
  expect(await p).toBe("YOK");
});

it("KARŞIT: kuşak değişmediyse yanıt AYNEN gelir; kuşak her artışta büyür", async () => {
  const once = hesapKusagi();
  expect(hesapKusagiArtir()).toBe(once + 1);
  const f = bekleyenFetch();
  const p = apiGet<{ kalan: number } | null>("/jeton/bakiye", null, { silent: true });
  await Promise.resolve();
  f.coz({ kalan: 7 });
  expect(await p).toEqual({ kalan: 7 });
});
