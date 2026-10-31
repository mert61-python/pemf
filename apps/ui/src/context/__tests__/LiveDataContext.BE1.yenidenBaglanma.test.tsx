// Author: mertaygn, cglrgrkn
/**
 * BE 1 · Y229 — TELEFON (yerel) YENİDEN BAĞLANMA: PC'den önce açılan uygulama ~96 sn yeşile dönmüyordu.
 * ===================================================================================================
 * ÖLÇÜLEN KUSUR (31.10 canlı, S23 + 1.9.51): PC kapalıyken soğuk açılan telefon 70 sn PC'ye TEK TCP göndermedi — kayıtlı adres
 * sağlık denetimi geçmeden uygulanmıyor, soket telefonun KENDİ 127.0.0.1'ini arıyordu; yeniden keşif yalnız her 4. soket
 * hatasında ve 20 sn soğuma ilk iki tetiği yutuyordu (açılıştan 95,9 sn sonra yeşil). Elle "yeniden bağlan" / ön plana dönüş de
 * soğumaya takılıyordu; arka plandan dönüşte soket doğrulanmadan ~2 sn YANLIŞ YEŞİL yanıyordu.
 *
 * KAPI (sahte saat; ağ modeli `baglantiAparati.tsx`): PC kapalıyken soğuk açılış + backend 25 sn sonra → canlı ≤ 10 sn ·
 * açıkken 30 sn kesinti → ≤ 6 sn · soğumadayken elle dokunma / ön plan / ağ dönüşü keşif BAŞLATIR · dönüşte doğrulamasız
 * "live" YOK. Web'in davranışı DEĞİŞMEZ: `LiveDataContext.BE1.web.test.tsx`.
 */
jest.mock("@/services/apiClient", () => ({
  ...jest.requireActual("@/services/apiClient"),
  apiGet: jest.fn(async (_p: string, fb: unknown) => fb),
  apiPost: jest.fn(async (_p: string, _b: unknown, fb: unknown) => fb),
}));
// İnternet / bulut yok (Supabase cihaz kaydı erişilemez) — G/Ç sınırı.
jest.mock("@/services/deviceRegistry", () => ({ getRemoteUrlForDevice: jest.fn(async () => null) }));
jest.mock(
  "react-native-zeroconf",
  () => {
    const ap = require("./baglantiAparati");
    return {
      __esModule: true,
      default: class {
        h: Record<string, (v: unknown) => void> = {};
        on(ev: string, cb: (v: unknown) => void) {
          this.h[ev] = cb;
        }
        scan() {
          ap.mockMdnsDurum.taramalar += 1;
          const ip = ap.mdnsIp();
          if (ip) setTimeout(() => this.h.resolved?.({ addresses: [ip], port: 8000 }), 300);
        }
        stop() {}
        removeDeviceListeners() {}
      },
    };
  },
  { virtual: true }
);
const mockNet: { dinleyici: ((s: unknown) => void) | null } = { dinleyici: null };
jest.mock("@react-native-community/netinfo", () => ({
  __esModule: true,
  // Telefon kendi hotspot'unun SAHİBİYKEN NetInfo IP vermez (ölçüldü) → alt ağ taraması PC'nin alt ağını bilemez.
  default: {
    fetch: async () => ({ type: "wifi", isConnected: true, details: {} }),
    addEventListener: (cb: (s: unknown) => void) => {
      mockNet.dinleyici = cb;
      return () => {};
    },
  },
}));

import React from "react";
import { AppState } from "react-native";
import { act, render } from "@testing-library/react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { LiveDataProvider } from "@/context/LiveDataContext";
import { serviceConfig } from "@/services/config";
import {
  PC,
  Probe,
  SahteWS,
  ag,
  agiSifirla,
  backendiKapat,
  ilerle,
  ilerleKadar,
  ilkCanliSonra,
  iz,
  iziSifirla,
  sahteFetch,
} from "./baglantiAparati";

let appDinleyici: ((s: string) => void) | null = null;
let origWS: unknown;
let origFetch: unknown;
let sok: ReturnType<typeof render> | null = null;

beforeEach(async () => {
  jest.useFakeTimers();
  agiSifirla();
  iziSifirla();
  await AsyncStorage.clear();
  serviceConfig.apiBaseUrl = "http://127.0.0.1:8000/api";
  serviceConfig.bridgeBaseUrl = "http://127.0.0.1:8000/api";
  serviceConfig.websocketUrl = "ws://127.0.0.1:8000/ws";
  serviceConfig.apiToken = "";
  origWS = (global as unknown as { WebSocket: unknown }).WebSocket;
  (global as unknown as { WebSocket: unknown }).WebSocket = SahteWS;
  origFetch = global.fetch;
  global.fetch = jest.fn(sahteFetch) as unknown as typeof fetch;
  jest.spyOn(AppState, "addEventListener").mockImplementation(((_t: string, cb: (s: string) => void) => {
    appDinleyici = cb;
    return { remove: () => {} };
  }) as never);
});

afterEach(async () => {
  sok?.unmount();
  sok = null;
  // Uçuştaki keşif turları (modül düzeyinde tek uçuş) bir sonraki teste taşmasın.
  await ilerle(90000, 1000);
  jest.restoreAllMocks();
  (global as unknown as { WebSocket: unknown }).WebSocket = origWS;
  global.fetch = origFetch as typeof fetch;
  jest.clearAllTimers();
  jest.useRealTimers();
});

async function kayitliAdres(adres: string) {
  await AsyncStorage.setItem("@pemf_server_address", adres);
  await AsyncStorage.setItem("@pemf_device_id", "cihaz-1");
}

function ac() {
  sok = render(
    <LiveDataProvider>
      <Probe />
    </LiveDataProvider>
  );
}

/** Alt ağ taraması yapıldı mı — yalnız TAM keşif merdiveni (4. adım) PC / kayıtlı adres DIŞINDAKİ IPv4 hostları yoklar. */
const altAgYoklamasi = (sonra: number) =>
  ag.saglik.filter((s) => s.t >= sonra && /^\d+\.\d+\.\d+\.\d+$/.test(s.host) && s.host !== PC && s.host !== "127.0.0.1").length;
/** Bir tam turun alt ağ taraması (her turda bir kez yoklanan host). */
const turSayisi = () => ag.saglik.filter((s) => s.host === "192.168.1.100").length;
/** Saati ilerletmeden bekleyen işleri boşalt. */
const bosalt = () => act(async () => {});

describe("BE 1 — telefon yeniden bağlanma (sahte saat)", () => {
  // Faz: backend'in açılış anı yoklama tikine denk gelmesin diye 25 sn'nin yanında 27,5 ve 31 sn de (aralık mutantını yakalar).
  it.each([
    ["dusur", 25000],
    ["rst", 25000],
    ["dusur", 27500],
    ["dusur", 31000],
  ] as const)(
    "KRİTİK (a)+(b): PC kapalıyken soğuk açılış, backend %s modelinde %i ms sonra → canlı ≤ 10 sn",
    async (model, acilis) => {
      ag.model = model;
      await kayitliAdres(`http://${PC}:8000`);
      ac();
      await ilerle(acilis);
      expect(iz.durum).toBe("offline");
      ag.backend = true;
      const ayakta = Date.now();
      const canli = await ilerleKadar(() => iz.durum === "live", 20000);
      expect(canli).not.toBeNull();
      expect(canli! - ayakta).toBeLessThanOrEqual(10000);
    }
  );

  it.each([25000, 31000])("KRİTİK (b): kayıtlı adres BAYAT (hotspot alt ağı değişti) → kısa mDNS yoklaması backend %i ms'de açılınca ≤ 10 sn'de bulur", async (acilis) => {
    await kayitliAdres("http://10.141.253.20:8000");
    ac();
    await ilerle(acilis);
    expect(iz.durum).toBe("offline");
    ag.backend = true;
    const ayakta = Date.now();
    const canli = await ilerleKadar(() => iz.durum === "live", 20000);
    expect(canli).not.toBeNull();
    expect(canli! - ayakta).toBeLessThanOrEqual(10000);
    expect(serviceConfig.websocketUrl).toBe(`ws://${PC}:8000/ws`);
  });

  it("(a) kayıtlı ÖZEL ağ adresi açılışta sağlık denetimi BEKLENMEDEN uygulanır — ilk soket PC'ye gider (127.0.0.1'e değil)", async () => {
    await kayitliAdres(`http://${PC}:8000`);
    ac();
    await ilerle(500);
    expect(ag.soketler.length).toBeGreaterThan(0);
    expect(ag.soketler[0].url).toBe(`ws://${PC}:8000/ws`);
  });

  it("(a) TÜNEL (https) kayıtlı adres sağlık + cihaz kimliği denetimi olmadan UYGULANMAZ", async () => {
    await kayitliAdres("https://eski-tunel.trycloudflare.com");
    ac();
    await ilerle(500);
    expect(serviceConfig.websocketUrl).not.toContain("trycloudflare");
  });

  it.each(["rst", "dusur"] as const)("KRİTİK: uygulama açıkken 30 sn kesinti → backend dönünce canlı ≤ 6 sn [%s]", async (model) => {
    ag.model = model;
    ag.backend = true;
    await kayitliAdres(`http://${PC}:8000`);
    ac();
    expect(await ilerleKadar(() => iz.durum === "live", 5000)).not.toBeNull();
    await ilerle(10000);
    backendiKapat();
    await ilerle(30000);
    expect(iz.durum).toBe("offline");
    ag.backend = true;
    const ayakta = Date.now();
    const canli = await ilerleKadar(() => iz.durum === "live", 20000);
    expect(canli).not.toBeNull();
    expect(canli! - ayakta).toBeLessThanOrEqual(6000);
  });

  it("KRİTİK (c): soğumadayken ELLE yeniden bağlan keşif BAŞLATIR (tam merdiven alt ağa ulaşır)", async () => {
    await kayitliAdres(`http://${PC}:8000`);
    ac();
    // İlk tam keşif başarısız biter (~40 sn) → 20 sn soğuma başlar.
    await ilerle(45000, 100);
    const once = Date.now();
    await ilerle(100);
    iz.reconnect();
    await ilerle(8000, 100);
    expect(altAgYoklamasi(once)).toBeGreaterThan(0);
  });

  it("KRİTİK (c): keşif SÜRERKEN dokunma yutulmaz — tur bitince soğumaya takılmadan yeniden koşar", async () => {
    await kayitliAdres(`http://${PC}:8000`);
    ac();
    await ilerle(10000, 100);
    iz.reconnect();
    await ilerle(55000, 100);
    expect(turSayisi()).toBeGreaterThanOrEqual(2);
  });

  it("KRİTİK (c): soğumadayken ÖN PLANA dönüş keşif başlatır", async () => {
    await kayitliAdres(`http://${PC}:8000`);
    ac();
    await ilerle(45000, 100);
    const once = Date.now();
    expect(appDinleyici).not.toBeNull();
    await ilerle(100);
    appDinleyici!("background");
    appDinleyici!("active");
    await ilerle(8000, 100);
    expect(altAgYoklamasi(once)).toBeGreaterThan(0);
  });

  it("KRİTİK (c): soğumadayken AĞ DÖNÜŞÜ (NetInfo) keşif başlatır", async () => {
    await kayitliAdres(`http://${PC}:8000`);
    ac();
    await ilerle(45000, 100);
    const once = Date.now();
    expect(mockNet.dinleyici).not.toBeNull();
    mockNet.dinleyici!({ isConnected: false });
    mockNet.dinleyici!({ isConnected: true });
    await ilerle(9500, 100);
    expect(altAgYoklamasi(once)).toBeGreaterThan(0);
  });

  it("KRİTİK (d): arka plandan dönüşte soket DOĞRULANMADAN 'live' YOK — ölü soket (Samsung keser, onclose geç)", async () => {
    ag.backend = true;
    await kayitliAdres(`http://${PC}:8000`);
    ac();
    expect(await ilerleKadar(() => iz.durum === "live", 5000)).not.toBeNull();
    await ilerle(2000);
    const eski = ag.soketler.filter((s) => s.readyState === 1);
    expect(eski.length).toBe(1);
    appDinleyici!("background");
    // JS donuk: zamanlayıcı koşmaz, yalnız saat ilerler; sunucu soketi kesti ama `onclose` henüz gelmedi.
    eski[0].olu = true;
    jest.setSystemTime(Date.now() + 60000);
    const donus = Date.now();
    await bosalt();
    appDinleyici!("active");
    await ilerle(50);
    expect(iz.durum).toBe("offline");
    await ilerle(2000);
    eski[0].sunucuKapatti(); // geç gelen onclose
    const canli = await ilerleKadar(() => iz.durum === "live", 8000);
    expect(canli).not.toBeNull();
    // İlk "live", dönüşten SONRA bir canlılık kanıtından (yeni soket açıldı / pong) önce GELMEZ.
    const ilk = ilkCanliSonra(donus)!;
    expect(ag.kanitlar.some((k) => k >= donus && k <= ilk)).toBe(true);
  });

  it("(d) canlı soket: dönüşte kısa 'doğrulanıyor' (offline), pong gelince 'live' — yeni soket AÇILMAZ", async () => {
    ag.backend = true;
    await kayitliAdres(`http://${PC}:8000`);
    ac();
    expect(await ilerleKadar(() => iz.durum === "live", 5000)).not.toBeNull();
    await ilerle(2000);
    const soketSayisi = ag.soketler.length;
    appDinleyici!("background");
    jest.setSystemTime(Date.now() + 3000);
    const donus = Date.now();
    await bosalt();
    appDinleyici!("active");
    await bosalt();
    expect(iz.durum).toBe("offline");
    const canli = await ilerleKadar(() => iz.durum === "live", 2000, 10);
    expect(canli).not.toBeNull();
    expect(canli! - donus).toBeLessThan(1000);
    expect(ag.kanitlar.some((k) => k >= donus && k <= canli!)).toBe(true);
    expect(ag.soketler.length).toBe(soketSayisi);
  });
});
