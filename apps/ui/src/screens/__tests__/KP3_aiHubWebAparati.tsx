/**
 * KP-2 · AI Hub WEB aparatı (jsdom + react-native-web + react-dom kökü). Test dosyası DEĞİL (testMatch `*.test.tsx` dışı).
 * KP-3: KP-2'de alınmayan taslaktan (`DENETIM\ZINCIR\taban\KP2\ajan\kp2a_alinmayan\`) DEĞİŞMEDEN alındı. Taslağın kırmızılığı
 * aparattan değil, çağıran dosyada güvenli-alan sahtesi olmamasındandı (gerçek ToastProvider → `react-native-safe-area-context`'in
 * yerel özelliği react-native-web altında yüklenemiyor; ölçüldü) — çağıran dosyalar artık onu sahteler.
 *
 * GERÇEK: AiHubScreen (+ modülleri), ToastProvider (iletiler ekranda `role="alert"`), apiClient, korunanFetch, config.
 * SAHTE yalnız EN ALT katta (tarayıcı sınırı):
 *  · `fetch` — her isteği yöntem + yol + gövde (çok parçalı → `FormData`) ile KAYDEDER; `blob:` URL'si okunursa tarayıcı gibi o URL'ye
 *    bağlı Blob'u döndürür.
 *  · `<input type=file>`'ın `click`'i — açılan seçicinin `accept` / `capture` öznitelikleri kaydedilir, `dosyaSiradaki` seçilir.
 *  · `URL.createObjectURL` / `revokeObjectURL` (jsdom'da yok) — URL ↔ Blob eşlemi tutulur, serbest bırakılan URL'ler kaydedilir.
 *  · `Date.now` — ürünün `Button`'ı aynı etiketin 400 ms içindeki ikinci basışını yutar; `saatiIlerlet()` gerçek bekleme olmadan aşar.
 * Çağıran test dosyası: `@jest-environment jsdom`, `jest.mock("react-native", () => jest.requireActual("react-native-web"))`, bağlam ve
 * expo modül sahteleri (jest.mock dosyada olmalı — hoist).
 */
import React, { act } from "react";
import { AiHubScreen } from "@/screens/AiHubScreen";
import { ToastProvider } from "@/components/ui/ToastProvider";
import { Sahne } from "../../context/__tests__/operatorAparati";

export interface KayitliIstek {
  yontem: string;
  yol: string;
  govde: unknown;
  basliklar: Record<string, string>;
}

type Yanit = [number, unknown] | { hata: unknown } | { blob: Blob | null } | undefined;
type Ozel = (yol: string, govde: unknown, yontem: string) => Yanit;

export const web = {
  istekler: [] as KayitliIstek[],
  dosyaSiradaki: null as File | null,
  acilanSeciciler: [] as Array<{ accept: string; capture: string | null }>,
  serbestBirakilan: [] as string[],
  nesneUrlleri: new Map<string, Blob>(),
  /** createObjectURL'ın üreteceği URL biçimi (varsayılan `blob:kp2-N`). */
  urlUret: null as null | ((b: Blob, n: number) => string),
};

let kayma = 0;
let tiklamaYamasi: jest.SpyInstance | null = null;
let saatYamasi: jest.SpyInstance | null = null;
let eskiUrl: { var: boolean; deger: unknown; create?: unknown; revoke?: unknown } | null = null;
let sayac = 0;

export function saatiIlerlet() {
  kayma += 1000;
}

const yanitNesnesi = (durum: number, veri: unknown) => ({
  ok: durum < 400,
  status: durum,
  json: async () => veri,
  text: async () => JSON.stringify(veri),
  headers: { get: () => "application/json" },
});

/** Tarayıcı sahtelerini kur (her testte `beforeEach`). */
export function webKur(ozel?: Ozel) {
  web.istekler = [];
  web.dosyaSiradaki = null;
  web.acilanSeciciler = [];
  web.serbestBirakilan = [];
  web.nesneUrlleri = new Map();
  web.urlUret = null;
  kayma = 0;
  const gercekSimdi = Date.now.bind(Date);
  saatYamasi = jest.spyOn(Date, "now").mockImplementation(() => gercekSimdi() + kayma);
  tiklamaYamasi = jest.spyOn(HTMLInputElement.prototype, "click").mockImplementation(function (this: HTMLInputElement) {
    if (this.type !== "file") return;
    web.acilanSeciciler.push({ accept: this.accept, capture: (this as unknown as { capture?: string }).capture ?? null });
    const f = web.dosyaSiradaki;
    if (!f) return;
    web.dosyaSiradaki = null;
    Object.defineProperty(this, "files", { value: [f], configurable: true });
    (this.onchange as ((e: unknown) => void) | null)?.({ target: this });
  });
  const g = globalThis as unknown as { URL?: Record<string, unknown> };
  eskiUrl = { var: "URL" in globalThis, deger: g.URL, create: g.URL?.createObjectURL, revoke: g.URL?.revokeObjectURL };
  const U = g.URL ?? {};
  U.createObjectURL = (b: Blob) => {
    sayac += 1;
    const url = web.urlUret ? web.urlUret(b, sayac) : `blob:kp2-${sayac}`;
    web.nesneUrlleri.set(url, b);
    return url;
  };
  U.revokeObjectURL = (u: string) => {
    web.serbestBirakilan.push(u);
  };
  g.URL = U;
  global.fetch = jest.fn(async (url: unknown, init: { method?: string; body?: unknown; headers?: Record<string, string>; signal?: AbortSignal } = {}) => {
    const ham = String(url);
    if (ham.startsWith("blob:")) {
      const b = web.nesneUrlleri.get(ham);
      if (!b) throw new TypeError("Failed to fetch");
      return { ok: true, status: 200, blob: async () => b };
    }
    const yol = ham.replace(/^[a-z]+:\/\/[^/]+/i, "").replace(/^\/api/, "");
    const yontem = init.method || "GET";
    let govde: unknown = init.body;
    if (typeof init.body === "string") {
      try { govde = JSON.parse(init.body); } catch { govde = init.body; }
    }
    web.istekler.push({ yontem, yol, govde, basliklar: init.headers || {} });
    const o = ozel?.(yol, govde, yontem);
    if (o && "hata" in (o as object)) throw (o as { hata: unknown }).hata;
    // KP-7 B: `{ askida: true }` — yanıt vermeyen sunucu; istek yalnız iptal sinyaliyle (zaman aşımı) reddedilir.
    if (o && "askida" in (o as object)) {
      return new Promise((_coz, reddet) => {
        init.signal?.addEventListener("abort", () => reddet(Object.assign(new Error("aborted"), { name: "AbortError" })));
      });
    }
    if (o && "blob" in (o as object)) return { ok: true, status: 200, blob: async () => (o as { blob: Blob | null }).blob };
    if (Array.isArray(o)) return yanitNesnesi(o[0], o[1]);
    if (yontem === "GET" && yol.startsWith("/ai/log")) return yanitNesnesi(200, { status: "success", data: [] });
    if (yontem === "POST" && yol === "/ai/log") return yanitNesnesi(200, { status: "success", id: 1 });
    return yanitNesnesi(200, {});
  }) as unknown as typeof fetch;
}

export function webSok() {
  tiklamaYamasi?.mockRestore();
  tiklamaYamasi = null;
  saatYamasi?.mockRestore();
  saatYamasi = null;
  const g = globalThis as unknown as { URL?: Record<string, unknown> };
  if (eskiUrl) {
    if (!eskiUrl.deger) {
      if (eskiUrl.var) g.URL = eskiUrl.deger as Record<string, unknown>;
      else delete g.URL;
    } else if (g.URL) {
      g.URL.createObjectURL = eskiUrl.create;
      g.URL.revokeObjectURL = eskiUrl.revoke;
    }
  }
  eskiUrl = null;
}

/** AiHubScreen'i gerçek ToastProvider içinde çiz. */
export async function ekraniCiz(s: Sahne) {
  await s.ciz(
    <ToastProvider>
      <AiHubScreen />
    </ToastProvider>,
  );
}

/** Görünen metni tam `metin` olan EN SON (en derin) elemana tıkla — aynı metin ipucu satırında da geçebilir, düğme sonda. */
export async function metneBas(s: Sahne, metin: string) {
  saatiIlerlet();
  const adaylar = Array.from(document.querySelectorAll("*")).filter(
    (e) => (e.textContent || "").trim() === metin && !Array.from(e.children).some((c) => (c.textContent || "").trim() === metin),
  ) as HTMLElement[];
  if (!adaylar.length) throw new Error(`metin "${metin}" bulunamadi. Govde: ${document.body.textContent?.slice(0, 400)}`);
  await act(async () => { adaylar[adaylar.length - 1].click(); });
  await s.bosalt(8);
}

/** `aria-label` ile (ilk) elemana tıkla. */
export async function etiketeBas(s: Sahne, etiket: string) {
  saatiIlerlet();
  await s.tikla(etiket);
  await s.bosalt(4);
}

/** Ekrandaki ileti (ToastProvider `role="alert"`). */
export function ileti(): string | null {
  const el = document.querySelector('[role="alert"]');
  return el ? (el.textContent || "").trim() : null;
}

/** Verilen uca giden POST istekleri. */
export function postlar(yol: string): KayitliIstek[] {
  return web.istekler.filter((i) => i.yontem === "POST" && i.yol === yol);
}

/** Çok parçalı gövdedeki alan değerleri (jsdom FormData). */
export function alanlar(govde: unknown): Record<string, unknown> {
  const c: Record<string, unknown> = {};
  if (govde instanceof FormData) govde.forEach((v, k) => { c[k] = v; });
  return c;
}

/** Blob/File içeriğini metin olarak oku. */
export function blobMetni(b: unknown): Promise<string> {
  return new Promise((coz) => {
    if (!(b instanceof Blob)) return coz(String(b));
    const r = new FileReader();
    r.onload = () => coz(String(r.result));
    r.readAsText(b);
  });
}

export { Sahne };
