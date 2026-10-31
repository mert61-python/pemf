// Author: mertaygn, cglrgrkn
/**
 * BE 1 (Y229) — mobil yeniden bağlanma kapısının SAHTE AĞI. Sahte EN ALT katta: `fetch`, `WebSocket`, mDNS (Zeroconf), NetInfo,
 * AppState ve AsyncStorage. Keşif merdiveni (`discovery.ts`), soket istemcisi (`wsClient.ts`), adres yapılandırması (`config.ts`)
 * ve `LiveDataContext` GERÇEK koşar; ölçülen tek çıktı `connectionQuality`'nin sahte saatle zamanıdır.
 *
 * Ağ modeli (31.10 canlı ölçümü — `DENETIM\ZINCIR\baglanti\gozlem-2026-10-31.log`):
 * - PC adresi `PC`; backend `ag.backend` iken `/api/health` + `/api/auth/token` yanıtlar, soket ~30 ms'de açılır.
 * - Backend YOKKEN PC'ye giden istek `ag.model`e göre: "dusur" (güvenlik duvarı SYN'i düşürür — istek istemcinin zaman
 *   aşımına dek asılı; soket SYN'i 1 / 3 / 7. sn'de yeniden gönderir, o an backend ayaktaysa bağlanır) ya da "rst" (bağlantı
 *   reddi ~5 ms). Telefonun kendi 127.0.0.1'i her zaman reddeder; başka her adres yanıtsızdır (asılı → zaman aşımı).
 * - mDNS yalnız backend ayaktayken (`mockMdns.ip()`) yayın yapar.
 */
import { useEffect } from "react";
import { act } from "@testing-library/react-native";
import { useLiveData } from "@/context/LiveDataContext";

export const PC = "10.235.247.50";

export const ag = {
  backend: false,
  model: "dusur" as "dusur" | "rst",
  /** `/api/health` istekleri (zaman, host). */
  saglik: [] as { t: number; host: string }[],
  soketler: [] as SahteWS[],
  /** Son "canlılık kanıtı" (soket açıldı ya da pong geldi) zamanı — doğrulamasız "live" yok iddiası için. */
  kanitlar: [] as number[],
};

export function agiSifirla(): void {
  ag.backend = false;
  ag.model = "dusur";
  ag.saglik = [];
  ag.soketler = [];
  ag.kanitlar = [];
}

function hostOf(url: string): string {
  return String(url).replace(/^[a-z]+:\/\//i, "").split("/")[0].split(":")[0];
}

function yanit(govde: unknown) {
  return { ok: true, status: 200, json: async () => govde, text: async () => JSON.stringify(govde), headers: { get: () => null } };
}

export function sahteFetch(url: string, init?: { signal?: AbortSignal }): Promise<unknown> {
  const host = hostOf(url);
  const yol = "/" + String(url).replace(/^[a-z]+:\/\/[^/]+\/?/i, "");
  if (yol.startsWith("/api/health")) ag.saglik.push({ t: Date.now(), host });
  if (host === PC && ag.backend) {
    const govde = yol.startsWith("/api/health")
      ? { service: "PEMF-Vet", status: "online", deviceId: "cihaz-1" }
      : yol.startsWith("/api/auth/token")
        ? { token: "jeton-1" }
        : {};
    return new Promise((res) => setTimeout(() => res(yanit(govde)), 20));
  }
  if (host === "127.0.0.1" || (host === PC && ag.model === "rst")) {
    return new Promise((_r, rej) => setTimeout(() => rej(new TypeError("Network request failed")), 5));
  }
  return new Promise((_r, rej) => {
    init?.signal?.addEventListener?.("abort", () => rej(Object.assign(new Error("Aborted"), { name: "AbortError" })));
  });
}

export class SahteWS {
  url: string;
  readyState = 0;
  /** Sunucu tarafında öldü ama JS donuktu (arka plan): ileti / pong gelmez, `onclose` geç gelir. */
  olu = false;
  onopen: (() => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(url: string) {
    this.url = url;
    ag.soketler.push(this);
    const host = hostOf(url);
    if (host === PC && ag.backend) setTimeout(() => this.ac(), 30);
    else if (host === "127.0.0.1" || (host === PC && ag.model === "rst")) setTimeout(() => this.sunucuKapatti(), 5);
    else if (host === PC) {
      for (const d of [1000, 3000, 7000]) setTimeout(() => ag.backend && this.ac(), d);
    }
  }
  ac() {
    if (this.readyState !== 0) return;
    this.readyState = 1;
    ag.kanitlar.push(Date.now());
    this.onopen?.();
  }
  send(d: string) {
    if (this.readyState !== 1 || this.olu || !ag.backend) return;
    let m: { type?: string } = {};
    try {
      m = JSON.parse(d);
    } catch {
      return;
    }
    if (m.type === "ping")
      setTimeout(() => {
        if (this.readyState !== 1 || this.olu) return;
        ag.kanitlar.push(Date.now());
        this.onmessage?.({ data: JSON.stringify({ type: "pong" }) });
      }, 20);
  }
  close() {
    this.readyState = 3;
  }
  sunucuKapatti() {
    if (this.readyState === 3) return;
    this.readyState = 3;
    this.onclose?.({ code: 1006 });
  }
}

/** Sunucu süreci öldü: açık soketler kapanır (PC açık → işletim sistemi bağlantıyı keser). */
export function backendiKapat(): void {
  ag.backend = false;
  for (const s of ag.soketler) if (s.readyState === 1) s.sunucuKapatti();
}

export const mockMdnsDurum = { taramalar: 0 };
export function mdnsIp(): string | null {
  return ag.backend ? PC : null;
}

export const iz = { durum: "offline" as string, gecmis: [] as [number, string][], reconnect: (() => {}) as () => void };
export function iziSifirla(): void {
  iz.durum = "offline";
  iz.gecmis = [];
  iz.reconnect = () => {};
}

export function Probe() {
  const { connectionQuality, reconnect } = useLiveData();
  iz.reconnect = reconnect;
  useEffect(() => {
    iz.durum = connectionQuality;
    iz.gecmis.push([Date.now(), connectionQuality]);
  }, [connectionQuality]);
  return null;
}

/** Sahte saati `ms` ilerlet (adım adım: her adımda bekleyen söz zincirleri boşalır). */
export async function ilerle(ms: number, adim = 50): Promise<void> {
  for (let t = 0; t < ms; t += adim) {
    await act(async () => {
      jest.advanceTimersByTime(adim);
    });
  }
}

/** Koşul sağlanana dek (en çok `azami` ms) ilerlet; sağlandığı anın saatini döndürür (yoksa null). */
export async function ilerleKadar(kosul: () => boolean, azami: number, adim = 50): Promise<number | null> {
  for (let t = 0; t <= azami; t += adim) {
    if (kosul()) return Date.now();
    await act(async () => {
      jest.advanceTimersByTime(adim);
    });
  }
  return kosul() ? Date.now() : null;
}

/** `t`den SONRA ilk "live" geçişinin zamanı. */
export function ilkCanliSonra(t: number): number | null {
  const g = iz.gecmis.find(([z, d]) => z >= t && d === "live");
  return g ? g[0] : null;
}
