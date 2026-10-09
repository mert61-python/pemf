/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * D2-3.5 (2-D bağımsız incelemesi, A3) — Ayarlar → Veri Taşıma: (a) yedek alma / geri yükleme isteği AĞ HATASIYLA (fetch reddi — zaman
 * aşımı DEĞİL) düşerse ekran HİÇBİR şey söylemiyor (`apiPost` bu dalda tost göstermez; `SettingsScreen` "hata mesajını apiPost gösterdi"
 * varsayar); uzun geri yükleme sırasında bağlantı koparsa işlem cihazda sürüyor olabilir — Y84'ün zaman aşımı metninin ikizi yok.
 * (b) Seçilen yedek dosyası okunamazsa (`arrayBuffer` reddi) `setTasimaMesgul("import")` geri alınmıyor: düğmeler KALICI kilitli,
 * "Yükleniyor…" sonsuza dek, işlenmeyen ret, neden yok.
 * Aparat 2-D kapısından AYNEN (SettingsVeriTasima.D2E01_E03.web.test.tsx satır 21–144): GERÇEK SettingsScreen + apiClient + toastBridge.
 * Depo yeri: apps/ui/src/screens/__tests__/VeriTasimaAgHatasi.D2_3_5.web.test.tsx
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
const mockToast = jest.fn();
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: mockToast }) }));
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ setUserMode: jest.fn(), isExpert: true, isResearcher: false }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: null }) }));
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => ({ reconnect: jest.fn(), wsConnected: true }) }));
jest.mock("@/hooks/useTeardownGuard", () => ({ useTeardownGuard: () => (f: unknown) => f }));
jest.mock("@/services/discovery", () => ({ checkHealth: jest.fn(), discoverBackend: jest.fn() }));
jest.mock("@/services/supabaseAuth", () => ({ updateProfile: jest.fn() }));
jest.mock("@/services/pairing", () => ({ cihazaBaglan: jest.fn(), eslesmeMesaji: jest.fn() }));
jest.mock("expo-linear-gradient", () => {
  const R = require("react");
  const { View } = require("react-native-web");
  return { LinearGradient: ({ children, style }: { children?: unknown; style?: unknown }) => R.createElement(View, { style }, children) };
});

import React from "react";
import { SettingsScreen } from "@/screens/SettingsScreen";
import { serviceConfig } from "@/services/config";
import { setToastHandler } from "@/services/toastBridge";
import { Sahne } from "../../context/__tests__/operatorAparati";

const PAROLA = "klinik-yedek-2026-ekran";
const mockHata = jest.fn();
const NodeURL = require("url").URL;

type Cagri = { yol: string; yontem: string; govde: Record<string, unknown> | null; sinyal: AbortSignal | null | undefined };
let cagrilar: Cagri[];
let yanit: (yol: string) => unknown | null;
let s: Sahne;
let eskiURL: unknown;

function sahteYanit(veri: unknown, durum = 200) {
  const govde = JSON.stringify(veri);
  return {
    ok: durum >= 200 && durum < 300,
    status: durum,
    headers: { get: () => "application/json" },
    text: async () => govde,
    json: async () => JSON.parse(govde),
  };
}

beforeEach(() => {
  jest.useFakeTimers();
  mockToast.mockReset();
  mockHata.mockReset();
  setToastHandler((m: string, t?: string) => mockHata(m, t));
  eskiURL = (global as unknown as { URL: unknown }).URL;
  const U = class extends NodeURL {} as unknown as { createObjectURL: unknown; revokeObjectURL: unknown };
  U.createObjectURL = jest.fn(() => "blob:yedek");
  U.revokeObjectURL = jest.fn();
  (global as unknown as { URL: unknown }).URL = U;
  cagrilar = [];
  yanit = () => null;
  (global as unknown as { fetch: unknown }).fetch = jest.fn((url: string, init?: RequestInit) => {
    const yol = String(url).replace(/^[a-z]+:\/\/[^/]+/i, "").replace(/^\/api/, "");
    const yontem = (init?.method || "GET").toUpperCase();
    cagrilar.push({ yol, yontem, govde: init?.body ? JSON.parse(String(init.body)) : null, sinyal: init?.signal });
    const r = yontem === "POST" ? yanit(yol) : null;
    if (r) return Promise.resolve(r);
    if (yontem === "GET") return Promise.resolve(sahteYanit({}));
    return new Promise((_coz, reddet) => {
      // asılı istek: yalnız iptal (AbortController) sonlandırır — gerçek fetch gibi
      init?.signal?.addEventListener("abort", () => reddet(Object.assign(new Error("aborted"), { name: "AbortError" })));
    });
  });
  s = new Sahne();
});
afterEach(async () => {
  await s.sok();
  setToastHandler(null);
  (global as unknown as { URL: unknown }).URL = eskiURL;
  jest.useRealTimers();
});

async function ekran(taban: string) {
  serviceConfig.apiBaseUrl = taban;
  await s.ciz(<SettingsScreen />);
}

async function disaAktarBaslat() {
  await s.tikla("Klinik verilerini şifreli dosyaya aktar");
  await s.yaz("Yedek parolası", PAROLA);
  await s.yaz("Yedek parolası tekrar", PAROLA);
  await s.tikla("Yedeği oluştur");
}

async function iceAktarBaslat() {
  const gercekOlustur = document.createElement.bind(document);
  let girdi: HTMLInputElement | null = null;
  const casus = jest.spyOn(document, "createElement").mockImplementation(((ad: string, sec?: ElementCreationOptions) => {
    const el = gercekOlustur(ad, sec);
    if (ad === "input") {
      girdi = el as HTMLInputElement;
      jest.spyOn(girdi, "click").mockImplementation(() => {});
    }
    return el;
  }) as typeof document.createElement);
  const onay = jest.spyOn(window, "confirm").mockImplementation((m?: string) => {
    sonOnayMetni = String(m ?? "");
    return true;
  });
  try {
    await s.tikla("Şifreli yedekten geri yükle");
    expect(girdi).not.toBeNull();
    const dosya = { name: "yedek.pemfbak", arrayBuffer: async () => new Uint8Array([80, 69, 77, 70]).buffer };
    Object.defineProperty(girdi!, "files", { value: [dosya] });
    await s.bosalt();
    void (girdi as unknown as { onchange: () => Promise<void> }).onchange();
    await s.bosalt();
    await s.yaz("Yedek parolası", PAROLA);
    await s.tikla("Devam et");
    await s.bosalt(10);
  } finally {
    casus.mockRestore();
    onay.mockRestore();
  }
}

const metinler = () => [...mockHata.mock.calls, ...mockToast.mock.calls].map((c) => String(c[0]));
let sonOnayMetni = "";

// ── D2-3.5 KAPI ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────
function agReddi() {
  // `fetch` reddi (TypeError "Failed to fetch") — zaman aşımı DEĞİL: bağlantı koptu / istek ulaşmadı. Diğer istekler aparatın fetch'ine.
  const asil = (global as unknown as { fetch: jest.Mock }).fetch;
  (global as unknown as { fetch: unknown }).fetch = jest.fn((url: string, init?: RequestInit) => {
    const yol = String(url).replace(/^[a-z]+:\/\/[^/]+/i, "").replace(/^\/api/, "");
    if (yol === "/data/export" || yol === "/data/import") {
      cagrilar.push({ yol, yontem: "POST", govde: null, sinyal: init?.signal });
      return Promise.reject(Object.assign(new TypeError("Failed to fetch"), { name: "TypeError" }));
    }
    return asil(url, init);
  });
}

describe("D2-3.5 — veri taşıma: ağ hatası SESSİZ değil, dosya okunamazsa düğmeler kilitli KALMAZ", () => {
  it("KRİTİK: geri yükleme isteği AĞ HATASIYLA düşerse ekran işlemin cihazda başlamış olabileceğini söyler ('Tekrar deneyin' demez)", async () => {
    agReddi();
    await ekran("http://192.168.1.50:8000/api");
    await iceAktarBaslat();
    await s.ilerlet(2000);
    await s.bosalt(10);
    expect(cagrilar.some((c) => c.yol === "/data/import")).toBe(true); // ARA: istek gerçekten gönderildi
    const m = metinler();
    expect(m.filter((x) => /başlamış olabilir|sürüyor olabilir/.test(x)).length).toBe(1);
    expect(m.filter((x) => /tekrar deneyin/i.test(x))).toEqual([]);
    expect(s.etiket("Şifreli yedekten geri yükle").getAttribute("aria-disabled")).not.toBe("true");
  });

  it("KRİTİK: yedek alma isteği AĞ HATASIYLA düşerse ekran bunu söyler (yedek OLUŞTURULMADI)", async () => {
    agReddi();
    await ekran("http://192.168.1.50:8000/api");
    await disaAktarBaslat();
    await s.ilerlet(2000);
    await s.bosalt(10);
    expect(metinler().filter((x) => /OLUŞTURULMADI|oluşturulamadı/i.test(x)).length).toBe(1);
  });

  it("KRİTİK: seçilen yedek dosyası OKUNAMAZSA düğmeler açılır, 'Yükleniyor…' kalmaz ve neden söylenir", async () => {
    await ekran("http://192.168.1.50:8000/api");
    const gercekOlustur = document.createElement.bind(document);
    let girdi: HTMLInputElement | null = null;
    const casus = jest.spyOn(document, "createElement").mockImplementation(((a: string, sec?: ElementCreationOptions) => {
      const el = gercekOlustur(a, sec);
      if (a === "input") { girdi = el as HTMLInputElement; jest.spyOn(girdi, "click").mockImplementation(() => {}); }
      return el;
    }) as typeof document.createElement);
    const onay = jest.spyOn(window, "confirm").mockImplementation(() => true);
    try {
      await s.tikla("Şifreli yedekten geri yükle");
      const dosya = { name: "yedek.pemfbak", arrayBuffer: async () => { throw new DOMException("dosya okunamadı", "NotReadableError"); } };
      Object.defineProperty(girdi!, "files", { value: [dosya] });
      await s.bosalt();
      void (girdi as unknown as { onchange: () => Promise<void> }).onchange().catch(() => undefined);
      await s.bosalt();
      await s.yaz("Yedek parolası", PAROLA);
      await s.tikla("Devam et");
      await s.bosalt(10);
      await s.ilerlet(2000);
    } finally {
      casus.mockRestore(); onay.mockRestore();
    }
    expect({
      kilitli: s.etiket("Şifreli yedekten geri yükle").getAttribute("aria-disabled") === "true",
      yukleniyor: s.metin().includes("Yükleniyor…"),
      neden: metinler().some((x) => /okunamadı/i.test(x)),
    }).toEqual({ kilitli: false, yukleniyor: false, neden: true });
  });

  it("KARŞIT: sunucu 409 ile yanıt verirse yalnız sunucunun gerekçesi gösterilir (ağ metni EKLENMEZ)", async () => {
    yanit = (yol) => (yol === "/data/import" ? sahteYanit({ detail: "Geri yükleme bu cihazda sürüyor — bitince kayıtlar görünür." }, 409) : null);
    await ekran("http://192.168.1.50:8000/api");
    await iceAktarBaslat();
    await s.bosalt(10);
    const m = metinler();
    expect(m.length).toBe(1);
    expect(m[0]).toContain("Geri yükleme bu cihazda sürüyor");
  });
});
