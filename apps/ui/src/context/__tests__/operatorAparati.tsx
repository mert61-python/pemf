// Author: mertaygn, cglrgrkn
/**
 * OPERATÖR KİMLİĞİ ZİNCİRİ — ortak jest aparatı (2-B: D2.E13 · D2.32 · D2.E14 · D2.70 · D2.42 · D2.72).
 *
 * GERÇEK: `AuthProvider`, `OperatorProvider`, `OperatorSwitcher`, `apiClient` (başlıkları — `X-PEMF-Operator` dahil — ürün
 * kurar). SAHTE yalnız EN ALT katta: `fetch` (ağ sınırı; her isteği yöntem + yol + operatör jetonu + gövde ile KAYDEDER) ve
 * Supabase istemcisi (çağıran test dosyası `jest.mock("@/services/supabaseAuth", …)` ile `supabaseSahte`yi verir — jest.mock
 * çağrısı dosyada olmalı, hoist edilir).
 *
 * Ortam: jsdom + react-native-web (`jest.mock("react-native", () => jest.requireActual("react-native-web"))`), react-dom
 * kökü. Masaüstü/web dağıtımının gerçek olay yolu (pencere yakalama dinleyicileri, DOM tıklaması) böyle ölçülür.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";

export interface Istek {
  yontem: string;
  yol: string;
  operator: string | null;
  govde: unknown;
}

export interface SahteOperator {
  email: string;
  display_name: string;
}

type Yanitla = (yol: string, govde: unknown, yontem: string, operator: string | null) => [number, unknown] | undefined;

/** Sahte ağ sınırı. `ozel` önce sorulur; yoksa operatör uçları ve boş `{}`. */
export function sahteSunucu(operatorler: SahteOperator[], ozel?: Yanitla) {
  const kayit: Istek[] = [];
  const fetchSahte = jest.fn(async (url: unknown, init: { method?: string; headers?: Record<string, string>; body?: unknown } = {}) => {
    // ⚠️ `new URL` KULLANILMAZ: bu ortamda (expo/RN polyfill) `URL` kurucu değil (ölçüldü: "URL is not a constructor").
    const yol = String(url).replace(/^[a-z]+:\/\/[^/]+/i, "").replace(/^\/api/, "");
    const basliklar = init.headers || {};
    const operator = basliklar["X-PEMF-Operator"] ?? null;
    let govde: unknown;
    try {
      govde = typeof init.body === "string" ? JSON.parse(init.body) : undefined;
    } catch {
      govde = init.body;
    }
    const yontem = init.method || "GET";
    kayit.push({ yontem, yol, operator, govde });
    const yanit = (durum: number, veri: unknown) => ({
      ok: durum < 400,
      status: durum,
      text: async () => JSON.stringify(veri),
      json: async () => veri,
      headers: { get: () => "application/json" },
    });
    const o = ozel?.(yol, govde, yontem, operator);
    if (o) return yanit(o[0], o[1]);
    if (yol === "/operators") return yanit(200, { ok: true, data: operatorler });
    if (yol === "/operators/verify") {
      const e = (govde as { email?: string })?.email || "";
      return yanit(200, { ok: true, operator_token: `JETON-${e}` });
    }
    if (yol === "/operators/lock") return yanit(200, { ok: true });
    return yanit(200, {});
  });
  return { kayit, fetchSahte };
}

/** Supabase istemcisinin en alt kat sahtesi: oturum açık (`eposta`), ağ yok. */
export function supabaseSahte(eposta: string) {
  const oturum = { access_token: "sahte-erisim", user: { email: eposta, user_metadata: {} } };
  return {
    supabaseAuth: {
      auth: {
        onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => undefined } } }),
        setSession: async () => ({ data: { session: null }, error: null }),
      },
    },
    getCurrentSession: async () => oturum,
    signOutUser: async () => undefined,
  };
}

/** react-dom kökü (jsdom). */
export class Sahne {
  kap: HTMLDivElement;
  kok: Root;
  constructor() {
    this.kap = document.createElement("div");
    document.body.appendChild(this.kap);
    this.kok = createRoot(this.kap);
  }
  async ciz(el: React.ReactElement) {
    await act(async () => this.kok.render(el));
    await this.bosalt();
  }
  /** Bekleyen söz/zamanlayıcı mikro-görevlerini boşalt. */
  async bosalt(n = 5) {
    for (let i = 0; i < n; i++) await act(async () => { await Promise.resolve(); });
  }
  async sok() {
    await act(async () => this.kok.unmount());
    document.body.innerHTML = "";
  }
  /** `aria-label` ile eleman (RN-web `accessibilityLabel` → `aria-label`). */
  etiket(ad: string): HTMLElement {
    const el = document.querySelector(`[aria-label="${ad}"]`) as HTMLElement | null;
    if (!el) throw new Error(`aria-label="${ad}" bulunamadi. Govde: ${document.body.textContent?.slice(0, 400)}`);
    return el;
  }
  varMi(ad: string): boolean {
    return !!document.querySelector(`[aria-label="${ad}"]`);
  }
  async tikla(ad: string) {
    const el = this.etiket(ad);
    await act(async () => { el.click(); });
    await this.bosalt();
  }
  /** Görünen METNİ tam olarak `metin` olan en derin elemana tıkla (etiketsiz düğmeler; tıklama atadaki basılabilir öğeye
   *  kabarcıklanır). */
  async metneTikla(metin: string) {
    const adaylar = Array.from(document.querySelectorAll("*")).filter(
      (e) => (e.textContent || "").trim() === metin && !Array.from(e.children).some((c) => (c.textContent || "").trim() === metin),
    ) as HTMLElement[];
    if (!adaylar.length) throw new Error(`metin "${metin}" bulunamadi. Govde: ${document.body.textContent?.slice(0, 300)}`);
    await act(async () => { adaylar[0].click(); });
    await this.bosalt();
  }
  /** Denetimli giriş alanına gerçek `input` olayıyla metin yaz (React değer ayarlayıcısı üzerinden). */
  async yaz(ad: string, metin: string) {
    const el = this.etiket(ad) as HTMLInputElement;
    const ayarla = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    await act(async () => {
      ayarla.call(el, metin);
      el.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await this.bosalt();
  }
  /** Zamanı (sahte zamanlayıcı) ilerlet ve mikro-görevleri boşalt. */
  async ilerlet(ms: number) {
    await act(async () => { jest.advanceTimersByTime(ms); });
    await this.bosalt();
  }
  metin(): string {
    return document.body.textContent || "";
  }
}

/** Operatör çipinden PIN'le geçiş (GERÇEK OperatorSwitcher akışı). */
export async function pinleSec(s: Sahne, gorunenAd: string, pin = "123456") {
  await s.tikla(cipEtiketi());
  await s.tikla(`Seç: ${gorunenAd}`);
  await s.yaz("PIN", pin);
  await s.tikla("Geçiş yap");
}

/** Üst bardaki operatör çipinin o anki `aria-label`ı ("Operatör seç" ya da "Aktif operatör: X. Değiştir."). */
export function cipEtiketi(): string {
  const el = document.querySelector('[aria-label="Operatör seç"], [aria-label^="Aktif operatör:"]');
  if (!el) throw new Error(`operator cipi yok. Govde: ${document.body.textContent?.slice(0, 300)}`);
  return el.getAttribute("aria-label") || "";
}

/** Çipin gösterdiği aktif operatör (yoksa null). */
export function aktifOperator(): string | null {
  const el = document.querySelector('[aria-label^="Aktif operatör:"]');
  const m = el?.getAttribute("aria-label")?.match(/^Aktif operatör: (.*)\. Değiştir\.$/);
  return m ? m[1] : null;
}
